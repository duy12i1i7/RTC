import copy
import json
from pathlib import Path
import unittest

from scripts.run_rmw_docker_quic_durable_failover_probe import probe_ok, service_ok


ROOT = Path(__file__).resolve().parents[1]
ARTIFACT = (
    ROOT
    / "results_rmw_socket"
    / "docker_quic_durable_failover_probe_summary.json"
)


class QuicDurableFailoverTest(unittest.TestCase):
    @unittest.skipUnless(ARTIFACT.is_file(), "external Docker evidence artifact absent")
    def test_validators_reject_missing_cursor_or_dedup_recovery(self) -> None:
        summary = json.loads(ARTIFACT.read_text(encoding="utf-8"))
        phases = summary["runs"][0]["phases"]
        for phase in phases:
            self.assertTrue(probe_ok(phase["probe"], phase["mode"]))
            self.assertTrue(service_ok(phase["service"], phase["mode"]))
        prefix = copy.deepcopy(phases[1]["service"])
        prefix["metrics"]["duplicate_frames"] = 0
        self.assertFalse(service_ok(prefix, "resume-prefix"))
        tail = copy.deepcopy(phases[2]["service"])
        tail["metrics"]["recovered_consumers"] = 0
        self.assertFalse(service_ok(tail, "resume-tail"))

    @unittest.skipUnless(ARTIFACT.is_file(), "external Docker evidence artifact absent")
    def test_canonical_docker_netem_artifact_passes_five_runs(self) -> None:
        summary = json.loads(ARTIFACT.read_text(encoding="utf-8"))
        self.assertEqual(summary["status"], "ok")
        self.assertEqual(summary["run_count"], 5)
        self.assertEqual(summary["successful_runs"], 5)
        self.assertEqual(summary["container_count_per_run"], 6)
        self.assertEqual(summary["gateway_instance_count_per_run"], 3)
        self.assertTrue(summary["real_quic_v1_h3"])
        self.assertTrue(summary["tls_peer_verification_required"])
        self.assertTrue(summary["sqlite_wal_full_sync_claim"])
        self.assertTrue(summary["active_passive_frame_recovery_claim"])
        self.assertTrue(summary["failover_dedup_recovery_claim"])
        self.assertTrue(summary["failover_consumer_cursor_resume_claim"])
        self.assertTrue(summary["sequential_gateway_instance_failover_claim"])
        self.assertFalse(summary["active_active_consensus_claim"])
        self.assertFalse(summary["cluster_wide_admission_state_claim"])
        self.assertFalse(summary["production_readiness"])
        for run in summary["runs"]:
            self.assertEqual(run["status"], "ok")
            self.assertEqual(run["phase_count"], 3)
            self.assertEqual(
                [phase["mode"] for phase in run["phases"]],
                ["publish", "resume-prefix", "resume-tail"],
            )
            for phase in run["phases"]:
                self.assertEqual(phase["status"], "ok")
                self.assertTrue(phase["netem_configured_both_containers"])
                self.assertGreaterEqual(phase["service_qlog_file_count"], 1)
                self.assertGreater(phase["client_qlog_file_count"], 0)
                self.assertGreater(phase["qlog_total_bytes"], 0)
                self.assertTrue(probe_ok(phase["probe"], phase["mode"]))
                self.assertTrue(service_ok(phase["service"], phase["mode"]))

    def test_durable_store_service_and_cpp_probe_are_wired(self) -> None:
        state = (ROOT / "fleetqox" / "quic_gateway_state.py").read_text()
        service = (ROOT / "scripts" / "fleetrmw_quic_gateway_service.py").read_text()
        probe = (
            ROOT
            / "ros2_ws"
            / "src"
            / "rmw_fleetqox_cpp"
            / "src"
            / "quic_durable_failover_probe.cpp"
        ).read_text()
        cmake = (
            ROOT / "ros2_ws" / "src" / "rmw_fleetqox_cpp" / "CMakeLists.txt"
        ).read_text()
        self.assertIn("class GatewayDurableStore", state)
        self.assertIn("PRAGMA journal_mode=WAL", state)
        self.assertIn("PRAGMA synchronous=FULL", state)
        self.assertIn("--state-db", service)
        self.assertIn("resume-prefix", probe)
        self.assertIn("resume-tail", probe)
        self.assertIn("fleetrmw_quic_durable_failover_probe", cmake)
        capabilities = json.loads(
            (
                ROOT
                / "ros2_ws"
                / "src"
                / "rmw_fleetqox_cpp"
                / "capabilities.json"
            ).read_text()
        )
        self.assertTrue(
            capabilities["supported"][
                "stateful_quic_gateway_failover_consumer_cursor_resume"
            ]
        )
        self.assertTrue(
            capabilities["claim_boundaries"][
                "quic_gateway_active_passive_frame_recovery_claim"
            ]
        )


if __name__ == "__main__":
    unittest.main()

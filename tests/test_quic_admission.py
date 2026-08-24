import copy
import json
from pathlib import Path
import unittest

from scripts.run_rmw_docker_quic_admission_probe import probe_ok, service_ok


ROOT = Path(__file__).resolve().parents[1]
ARTIFACT = ROOT / "results_rmw_socket" / "docker_quic_admission_probe_summary.json"


class QuicGatewayAdmissionTest(unittest.TestCase):
    @unittest.skipUnless(ARTIFACT.is_file(), "external Docker evidence artifact absent")
    def test_validators_reject_unaccounted_admission(self) -> None:
        summary = json.loads(ARTIFACT.read_text(encoding="utf-8"))
        run = summary["runs"][0]
        self.assertTrue(probe_ok(run["probe"]))
        self.assertTrue(service_ok(run["service"]))
        mutated = copy.deepcopy(run["service"])
        mutated["metrics"]["admission"]["accepted_total"] = 4
        self.assertFalse(service_ok(mutated))

    @unittest.skipUnless(ARTIFACT.is_file(), "external Docker evidence artifact absent")
    def test_canonical_docker_netem_artifact_passes_five_runs(self) -> None:
        summary = json.loads(ARTIFACT.read_text(encoding="utf-8"))
        self.assertEqual(summary["status"], "ok")
        self.assertEqual(summary["run_count"], 5)
        self.assertEqual(summary["successful_runs"], 5)
        self.assertEqual(summary["container_count_per_run"], 2)
        self.assertTrue(summary["real_quic_v1_h3"])
        self.assertTrue(summary["tls_peer_verification_required"])
        self.assertTrue(summary["fleet_gateway_admission_policy_claim"])
        self.assertTrue(summary["per_stream_traffic_class_quota_claim"])
        self.assertTrue(summary["shared_fleet_quota_claim"])
        self.assertTrue(summary["publisher_admission_allowlist_claim"])
        self.assertTrue(summary["admission_rejection_state_isolation_claim"])
        self.assertTrue(summary["admission_epoch_replenishment_claim"])
        self.assertFalse(summary["production_quic_backend_claim"])
        self.assertFalse(summary["production_readiness"])
        for run in summary["runs"]:
            self.assertEqual(run["status"], "ok")
            self.assertTrue(run["netem_configured_both_containers"])
            self.assertGreaterEqual(run["service_qlog_file_count"], 1)
            self.assertGreaterEqual(run["client_qlog_file_count"], 4)
            self.assertGreater(run["qlog_total_bytes"], 0)
            self.assertTrue(probe_ok(run["probe"]))
            self.assertTrue(service_ok(run["service"]))

    def test_policy_service_and_cpp_probe_are_wired(self) -> None:
        state = (ROOT / "fleetqox" / "quic_gateway_state.py").read_text()
        service = (ROOT / "scripts" / "fleetrmw_quic_gateway_service.py").read_text()
        probe = (
            ROOT
            / "ros2_ws"
            / "src"
            / "rmw_fleetqox_cpp"
            / "src"
            / "quic_admission_probe.cpp"
        ).read_text()
        cmake = (
            ROOT / "ros2_ws" / "src" / "rmw_fleetqox_cpp" / "CMakeLists.txt"
        ).read_text()
        self.assertIn("class GatewayAdmissionPolicy", state)
        self.assertIn("fleet_quota_exhausted", state)
        self.assertIn("stream_quota_exhausted", state)
        self.assertIn("--admission-policy", service)
        self.assertIn("fleet_admission_policy_claim", probe)
        self.assertIn("fleetrmw_quic_admission_probe", cmake)


if __name__ == "__main__":
    unittest.main()

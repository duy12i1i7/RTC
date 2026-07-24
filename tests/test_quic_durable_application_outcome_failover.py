import copy
import json
from pathlib import Path
import unittest

from scripts.run_rmw_docker_quic_durable_application_outcome_failover_probe import (
    probe_ok,
    service_ok,
)


ROOT = Path(__file__).resolve().parents[1]
ARTIFACT = (
    ROOT
    / "results_rmw_socket"
    / "docker_quic_durable_application_outcome_failover_probe_summary.json"
)


class QuicDurableApplicationOutcomeFailoverTest(unittest.TestCase):
    def test_canonical_docker_netem_failover_passes_five_runs(self) -> None:
        summary = json.loads(ARTIFACT.read_text(encoding="utf-8"))
        self.assertEqual(summary["status"], "ok")
        self.assertEqual(summary["run_count"], 5)
        self.assertEqual(summary["successful_runs"], 5)
        self.assertEqual(summary["container_count_per_run"], 4)
        self.assertEqual(summary["gateway_instance_count_per_run"], 2)
        self.assertTrue(summary["real_quic_v1_h3"])
        self.assertTrue(summary["mutual_tls_client_authentication_required"])
        self.assertTrue(summary["publisher_identity_binding_required"])
        for claim in (
            "sqlite_wal_full_sync_claim",
            "application_outcome_atomic_admission_commit_claim",
            "application_outcome_failover_recovery_claim",
            "application_outcome_cross_gateway_idempotence_claim",
            "application_outcome_admission_effect_after_failover_claim",
            "sequential_gateway_instance_failover_claim",
        ):
            self.assertTrue(summary[claim])
        self.assertFalse(summary["active_active_consensus_claim"])
        self.assertFalse(summary["distributed_database_claim"])
        self.assertFalse(summary["production_readiness"])
        for run in summary["runs"]:
            self.assertEqual(run["status"], "ok")
            for mode in ("seed", "resume"):
                phase = run[mode]
                self.assertTrue(phase["netem_configured_both_containers"])
                self.assertGreater(phase["qlog_file_count"], 0)
                self.assertGreater(phase["qlog_total_bytes"], 0)
                self.assertTrue(probe_ok(phase["probe"], mode))
                self.assertTrue(service_ok(phase["service"], mode))

    def test_validators_reject_lost_outcome_or_double_debt(self) -> None:
        run = json.loads(ARTIFACT.read_text(encoding="utf-8"))["runs"][0]
        resume = run["resume"]
        self.assertTrue(probe_ok(resume["probe"], "resume"))
        self.assertTrue(service_ok(resume["service"], "resume"))

        mutated = copy.deepcopy(resume["service"])
        mutated["metrics"]["recovered_application_outcomes"] = 0
        self.assertFalse(service_ok(mutated, "resume"))
        mutated = copy.deepcopy(resume["service"])
        mutated["metrics"]["application_outcome_updates"] = 1
        self.assertFalse(service_ok(mutated, "resume"))
        mutated = copy.deepcopy(resume["service"])
        mutated["metrics"]["durable_state"]["application_outcome_count"] = 0
        self.assertFalse(service_ok(mutated, "resume"))

    def test_store_cpp_probe_and_build_are_wired(self) -> None:
        state = (ROOT / "fleetqox" / "quic_gateway_state.py").read_text()
        postgres = (ROOT / "fleetqox" / "quic_gateway_postgres.py").read_text()
        probe = (
            ROOT / "ros2_ws" / "src" / "rmw_fleetqox_cpp" / "src"
            / "quic_durable_application_outcome_failover_probe.cpp"
        ).read_text()
        cmake = (
            ROOT / "ros2_ws" / "src" / "rmw_fleetqox_cpp" / "CMakeLists.txt"
        ).read_text()
        for source in (state, postgres):
            self.assertIn("CREATE TABLE IF NOT EXISTS application_outcomes", source)
            self.assertIn("def commit_application_outcome", source)
        self.assertIn("duplicate_outcome_idempotent", probe)
        self.assertIn(
            "fleetrmw_quic_durable_application_outcome_failover_probe", cmake
        )
        capabilities = json.loads((
            ROOT / "ros2_ws" / "src" / "rmw_fleetqox_cpp" / "capabilities.json"
        ).read_text())
        self.assertTrue(capabilities["supported"][
            "stateful_quic_gateway_application_outcome_durable_state"
        ])
        self.assertTrue(capabilities["claim_boundaries"][
            "quic_gateway_application_outcome_cross_gateway_idempotence_claim"
        ])


if __name__ == "__main__":
    unittest.main()

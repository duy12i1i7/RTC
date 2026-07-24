import copy
import json
from pathlib import Path
import unittest

from scripts.run_rmw_docker_quic_postgres_application_outcome_failover_probe import (
    case_ok,
    service_ok,
)


ROOT = Path(__file__).resolve().parents[1]
ARTIFACT = (
    ROOT
    / "results_rmw_socket"
    / "docker_quic_postgresql_application_outcome_failover_probe_summary.json"
)


class QuicPostgresApplicationOutcomeFailoverTest(unittest.TestCase):
    def test_canonical_postgresql_outcome_failover_passes_five_runs(self) -> None:
        summary = json.loads(ARTIFACT.read_text(encoding="utf-8"))
        self.assertEqual(summary["status"], "ok")
        self.assertEqual(summary["run_count"], 5)
        self.assertEqual(summary["successful_runs"], 5)
        self.assertEqual(summary["container_count_per_run"], 5)
        self.assertEqual(summary["gateway_instance_count_per_run"], 2)
        self.assertEqual(summary["database_instance_count_per_run"], 1)
        for claim in (
            "networked_postgresql_durable_state_claim",
            "synchronous_commit_claim",
            "postgresql_writer_fencing_claim",
            "application_outcome_atomic_admission_commit_claim",
            "application_outcome_postgresql_failover_recovery_claim",
            "application_outcome_cross_gateway_idempotence_claim",
            "application_outcome_admission_effect_after_failover_claim",
        ):
            self.assertTrue(summary[claim])
        self.assertLess(summary["max_gateway_replacement_latency_ms"], 8000)
        self.assertFalse(summary["database_process_failover_claim"])
        self.assertFalse(summary["replicated_database_claim"])
        self.assertFalse(summary["active_active_consensus_claim"])
        self.assertFalse(summary["production_readiness"])
        for run in summary["runs"]:
            self.assertTrue(case_ok(run))
            self.assertTrue(run["database"]["server_version"].startswith("16."))

    def test_validator_rejects_lost_outcome_and_fence_regression(self) -> None:
        run = json.loads(ARTIFACT.read_text(encoding="utf-8"))["runs"][0]
        replacement = run["replacement"]
        self.assertTrue(service_ok(
            replacement["service"], mode="resume", holder="gateway-b", token=2
        ))
        mutated = copy.deepcopy(run)
        mutated["replacement"]["service"]["metrics"][
            "recovered_application_outcomes"
        ] = 0
        self.assertFalse(case_ok(mutated))
        mutated = copy.deepcopy(run)
        mutated["replacement"]["service"]["metrics"]["durable_state"][
            "writer_lease"
        ]["fence_token"] = 1
        self.assertFalse(case_ok(mutated))
        mutated = copy.deepcopy(run)
        mutated["replacement"]["service"]["metrics"][
            "application_outcome_updates"
        ] = 1
        self.assertFalse(case_ok(mutated))

    def test_postgresql_outcome_transaction_is_wired(self) -> None:
        postgres = (ROOT / "fleetqox" / "quic_gateway_postgres.py").read_text()
        self.assertIn("CREATE TABLE IF NOT EXISTS application_outcomes", postgres)
        self.assertIn("def commit_application_outcome", postgres)
        self.assertIn("ON CONFLICT(domain_id, topic, publisher_id", postgres)
        self.assertIn("self._verify_writer_lease", postgres)
        capabilities = json.loads((
            ROOT / "ros2_ws" / "src" / "rmw_fleetqox_cpp" / "capabilities.json"
        ).read_text())
        self.assertTrue(capabilities["supported"][
            "stateful_quic_gateway_application_outcome_postgresql_durable_state"
        ])
        self.assertTrue(capabilities["claim_boundaries"][
            "quic_gateway_application_outcome_postgresql_failover_recovery_claim"
        ])


if __name__ == "__main__":
    unittest.main()

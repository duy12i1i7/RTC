import copy
import json
from pathlib import Path
import unittest

from scripts.run_rmw_docker_quic_durable_admission_failover_probe import (
    probe_ok,
    service_ok,
)


ROOT = Path(__file__).resolve().parents[1]
ARTIFACT = (
    ROOT
    / "results_rmw_socket"
    / "docker_quic_durable_admission_failover_probe_summary.json"
)


class QuicDurableAdmissionFailoverTest(unittest.TestCase):
    def test_validators_reject_reset_quota_or_repair_state(self) -> None:
        summary = json.loads(ARTIFACT.read_text(encoding="utf-8"))
        run = summary["runs"][0]
        self.assertTrue(probe_ok(run["seed"]["probe"], "seed"))
        self.assertTrue(service_ok(run["seed"]["service"], "seed"))
        self.assertTrue(probe_ok(run["resume"]["probe"], "resume"))
        self.assertTrue(service_ok(run["resume"]["service"], "resume"))

        mutated = copy.deepcopy(run["resume"]["service"])
        mutated["metrics"]["admission"]["accepted_total"] = 0
        self.assertFalse(service_ok(mutated, "resume"))
        mutated = copy.deepcopy(run["resume"]["service"])
        mutated["metrics"]["admission"]["repair_admitted_count"] = 0
        self.assertFalse(service_ok(mutated, "resume"))
        mutated = copy.deepcopy(run["resume"]["service"])
        mutated["metrics"]["recovered_admission_state"] = 0
        self.assertFalse(service_ok(mutated, "resume"))

    def test_canonical_docker_netem_failover_passes_five_runs(self) -> None:
        summary = json.loads(ARTIFACT.read_text(encoding="utf-8"))
        self.assertEqual(summary["status"], "ok")
        self.assertEqual(summary["run_count"], 5)
        self.assertEqual(summary["successful_runs"], 5)
        self.assertEqual(summary["container_count_per_run"], 5)
        self.assertEqual(summary["gateway_instance_count_per_run"], 3)
        self.assertTrue(summary["real_quic_v1_h3"])
        self.assertTrue(summary["sqlite_wal_full_sync_claim"])
        self.assertTrue(summary["frame_and_admission_single_transaction_claim"])
        self.assertTrue(summary["admission_quota_failover_recovery_claim"])
        self.assertTrue(summary["repair_capacity_failover_recovery_claim"])
        self.assertTrue(
            summary["policy_fingerprint_mismatch_fail_closed_claim"]
        )
        self.assertTrue(summary["sequential_gateway_instance_failover_claim"])
        self.assertFalse(summary["active_active_consensus_claim"])
        self.assertFalse(summary["distributed_database_claim"])
        self.assertFalse(summary["production_readiness"])
        for run in summary["runs"]:
            self.assertEqual(run["status"], "ok")
            self.assertTrue(service_ok(run["seed"]["service"], "seed"))
            self.assertTrue(service_ok(run["resume"]["service"], "resume"))
            self.assertTrue(
                run["mismatch_control"]["fingerprint_mismatch_fail_closed"]
            )

    def test_store_policy_state_and_cpp_probe_are_wired(self) -> None:
        state = (ROOT / "fleetqox" / "quic_gateway_state.py").read_text()
        probe = (
            ROOT
            / "ros2_ws"
            / "src"
            / "rmw_fleetqox_cpp"
            / "src"
            / "quic_durable_admission_failover_probe.cpp"
        ).read_text()
        self.assertIn("CREATE TABLE IF NOT EXISTS admission_state", state)
        self.assertIn("def export_durable_state", state)
        self.assertIn("def restore_durable_state", state)
        self.assertIn("policy_fingerprint", state)
        self.assertIn("resumed_repair_rejected", probe)


if __name__ == "__main__":
    unittest.main()

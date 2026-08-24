import copy
import json
from pathlib import Path
import unittest

from scripts.run_rmw_docker_quic_automatic_standby_takeover_probe import (
    automatic_takeover_service_ok,
    case_ok,
)


ROOT = Path(__file__).resolve().parents[1]
ARTIFACT = (
    ROOT
    / "results_rmw_socket"
    / "docker_quic_automatic_standby_takeover_probe_summary.json"
)


class QuicAutomaticStandbyTakeoverTest(unittest.TestCase):
    @unittest.skipUnless(ARTIFACT.is_file(), "external Docker evidence artifact absent")
    def test_validators_reject_sequential_start_or_unrecovered_state(self) -> None:
        summary = json.loads(ARTIFACT.read_text(encoding="utf-8"))
        run = summary["runs"][0]
        self.assertTrue(case_ok(run))
        self.assertTrue(automatic_takeover_service_ok(run["standby"]["service"]))

        mutated = copy.deepcopy(run)
        mutated["standby_observed_waiting_while_active_live"] = False
        self.assertFalse(case_ok(mutated))
        mutated = copy.deepcopy(run)
        mutated["standby"]["service"]["writer_lease_acquisition_attempts"] = 1
        self.assertFalse(case_ok(mutated))
        mutated = copy.deepcopy(run)
        mutated["standby"]["service"]["metrics"]["recovered_admission_state"] = 0
        self.assertFalse(case_ok(mutated))
        mutated = copy.deepcopy(run)
        mutated["standby"]["service"]["metrics"]["durable_state"][
            "writer_lease"
        ]["fence_token"] = 1
        self.assertFalse(case_ok(mutated))

    @unittest.skipUnless(ARTIFACT.is_file(), "external Docker evidence artifact absent")
    def test_canonical_docker_netem_automatic_takeover_passes_five_runs(
        self,
    ) -> None:
        summary = json.loads(ARTIFACT.read_text(encoding="utf-8"))
        self.assertEqual(summary["status"], "ok")
        self.assertEqual(summary["run_count"], 5)
        self.assertEqual(summary["successful_runs"], 5)
        self.assertEqual(summary["container_count_per_run"], 4)
        self.assertTrue(summary["real_quic_v1_h3"])
        self.assertTrue(summary["automatic_shared_store_standby_takeover_claim"])
        self.assertTrue(summary["standby_waits_while_active_lease_live_claim"])
        self.assertTrue(summary["monotonic_fence_token_takeover_claim"])
        self.assertTrue(summary["post_takeover_admission_recovery_claim"])
        self.assertLess(summary["max_takeover_latency_ms"], 8000)
        self.assertFalse(summary["consensus_leader_election_claim"])
        self.assertFalse(summary["active_active_consensus_claim"])
        self.assertFalse(summary["distributed_database_claim"])
        self.assertFalse(summary["production_readiness"])
        for run in summary["runs"]:
            self.assertTrue(case_ok(run))

    def test_wait_helper_and_service_flags_are_wired(self) -> None:
        helper = (ROOT / "fleetqox" / "quic_gateway_lease.py").read_text()
        service = (ROOT / "scripts" / "fleetrmw_quic_gateway_service.py").read_text()
        self.assertIn("acquire_gateway_state_with_lease_wait", helper)
        self.assertIn("timed out waiting for durable writer lease", helper)
        self.assertIn("--writer-lease-wait-timeout-ms", service)
        self.assertIn('"status": "writer_lease_waiting"', service)


if __name__ == "__main__":
    unittest.main()

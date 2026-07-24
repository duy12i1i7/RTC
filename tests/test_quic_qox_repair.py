import copy
import json
from pathlib import Path
import unittest

from scripts.run_rmw_docker_quic_qox_repair_probe import probe_ok, service_ok


ROOT = Path(__file__).resolve().parents[1]
ARTIFACT = ROOT / "results_rmw_socket" / "docker_quic_qox_repair_probe_summary.json"


class QuicQoxRepairTest(unittest.TestCase):
    def test_validators_reject_unaccounted_repair_capacity(self) -> None:
        summary = json.loads(ARTIFACT.read_text(encoding="utf-8"))
        run = summary["runs"][0]
        self.assertTrue(probe_ok(run["probe"]))
        self.assertTrue(service_ok(run["service"]))
        mutated = copy.deepcopy(run["service"])
        mutated["metrics"]["admission"]["repair_allocated_bytes"] = 0
        self.assertFalse(service_ok(mutated))

    def test_canonical_docker_netem_artifact_passes_five_runs(self) -> None:
        summary = json.loads(ARTIFACT.read_text(encoding="utf-8"))
        self.assertEqual(summary["status"], "ok")
        self.assertEqual(summary["run_count"], 5)
        self.assertEqual(summary["successful_runs"], 5)
        self.assertTrue(summary["qos_qoe_metadata_wire_claim"])
        self.assertTrue(summary["qos_qoe_admission_score_claim"])
        self.assertTrue(summary["fleet_repair_scheduler_gateway_coupling_claim"])
        self.assertTrue(summary["repair_capacity_defer_fail_closed_claim"])
        self.assertTrue(
            summary["h3_connection_reuse_across_admission_operations_claim"]
        )
        self.assertFalse(summary["production_quic_backend_claim"])
        self.assertFalse(summary["production_readiness"])
        for run in summary["runs"]:
            self.assertEqual(run["status"], "ok")
            self.assertTrue(run["netem_configured_both_containers"])
            self.assertGreaterEqual(run["service_qlog_file_count"], 1)
            self.assertEqual(run["client_qlog_file_count"], 3)
            self.assertGreater(run["qlog_total_bytes"], 0)
            self.assertTrue(probe_ok(run["probe"]))
            self.assertTrue(service_ok(run["service"]))

    def test_wire_metadata_scheduler_and_cpp_probe_are_wired(self) -> None:
        header = (
            ROOT
            / "ros2_ws"
            / "src"
            / "rmw_fleetqox_cpp"
            / "include"
            / "rmw_fleetqox_cpp"
            / "data_frame.hpp"
        ).read_text()
        state = (ROOT / "fleetqox" / "quic_gateway_state.py").read_text()
        probe = (
            ROOT
            / "ros2_ws"
            / "src"
            / "rmw_fleetqox_cpp"
            / "src"
            / "quic_qox_repair_probe.cpp"
        ).read_text()
        self.assertIn("double qoe_debt", header)
        self.assertIn("bool repair_requested", header)
        self.assertIn("FleetRepairScheduler", state)
        self.assertIn("admission_score", state)
        self.assertIn("qos_qoe_admission_repair_coupling_claim", probe)


if __name__ == "__main__":
    unittest.main()

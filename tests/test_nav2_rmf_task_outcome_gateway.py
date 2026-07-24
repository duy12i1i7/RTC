import copy
import json
from pathlib import Path
import unittest

from scripts.run_rmw_docker_nav2_rmf_task_outcome_gateway_probe import (
    probe_ok,
    service_ok,
)


ROOT = Path(__file__).resolve().parents[1]
ARTIFACT = (
    ROOT
    / "results_rmw_socket"
    / "docker_nav2_rmf_task_outcome_gateway_probe_summary.json"
)


class Nav2RmfTaskOutcomeGatewayTest(unittest.TestCase):
    def test_chained_real_workload_outcomes_pass_gateway_five_times(self) -> None:
        summary = json.loads(ARTIFACT.read_text(encoding="utf-8"))
        self.assertEqual(summary["status"], "ok")
        self.assertEqual(summary["run_count"], 5)
        self.assertEqual(summary["successful_runs"], 5)
        self.assertTrue(summary["source_workload_task_outcome_mapping_valid"])
        self.assertTrue(summary["source_artifact_chained_submission"])
        self.assertTrue(summary["nav2_rmf_task_outcome_gateway_submission_claim"])
        self.assertTrue(summary["task_outcome_submission_session_reuse_claim"])
        self.assertFalse(summary["same_process_live_ros_result_submission_claim"])
        self.assertFalse(summary["production_quic_backend_claim"])
        self.assertFalse(summary["production_readiness"])
        for run in summary["runs"]:
            self.assertEqual(run["status"], "ok")
            self.assertTrue(run["netem_configured_both_containers"])
            self.assertGreater(run["qlog_file_count"], 0)
            self.assertGreater(run["qlog_total_bytes"], 0)
            self.assertTrue(probe_ok(run["probe"]))
            self.assertTrue(service_ok(run["service"]))

    def test_validators_reject_missing_failure_or_session_reuse(self) -> None:
        run = json.loads(ARTIFACT.read_text(encoding="utf-8"))["runs"][0]
        mutated = copy.deepcopy(run["probe"])
        mutated["connection_reuse_count"] = 3
        self.assertFalse(probe_ok(mutated))
        mutated = copy.deepcopy(run["service"])
        mutated["metrics"]["application_task_outcome_failures"] = 0
        self.assertFalse(service_ok(mutated))
        mutated = copy.deepcopy(run["service"])
        mutated["metrics"]["application_outcome_updates"] = 2
        self.assertFalse(service_ok(mutated))

    def test_cpp_submitter_and_manifest_record_both_submission_paths(self) -> None:
        cmake = (
            ROOT / "ros2_ws" / "src" / "rmw_fleetqox_cpp" / "CMakeLists.txt"
        ).read_text(encoding="utf-8")
        source = (
            ROOT
            / "ros2_ws"
            / "src"
            / "rmw_fleetqox_cpp"
            / "src"
            / "quic_task_outcome_submit_probe.cpp"
        ).read_text(encoding="utf-8")
        capabilities = json.loads((
            ROOT
            / "ros2_ws"
            / "src"
            / "rmw_fleetqox_cpp"
            / "capabilities.json"
        ).read_text(encoding="utf-8"))
        self.assertIn("fleetrmw_quic_task_outcome_submit_probe", cmake)
        self.assertIn("FLEETQOX_TASK_OUTCOME_NDJSON", source)
        self.assertTrue(capabilities["claim_boundaries"][
            "nav2_rmf_application_outcome_gateway_submission_claim"
        ])
        self.assertTrue(capabilities["claim_boundaries"][
            "nav2_rmf_live_ros_same_process_outcome_submission_claim"
        ])


if __name__ == "__main__":
    unittest.main()

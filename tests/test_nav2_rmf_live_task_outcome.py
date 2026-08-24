import copy
import json
from pathlib import Path
import unittest

from scripts.run_rmw_docker_nav2_rmf_live_task_outcome_probe import (
    evidence_run_ok,
)


ROOT = Path(__file__).resolve().parents[1]
ARTIFACT = (
    ROOT
    / "results_rmw_socket"
    / "docker_nav2_rmf_live_task_outcome_probe_summary.json"
)


class Nav2RmfLiveTaskOutcomeTest(unittest.TestCase):
    @unittest.skipUnless(ARTIFACT.is_file(), "external Docker evidence artifact absent")
    def test_actual_results_submit_from_live_ros_process_five_times(self) -> None:
        summary = json.loads(ARTIFACT.read_text(encoding="utf-8"))
        self.assertEqual(
            summary["schema_version"],
            "fleetrmw.docker_nav2_rmf_live_task_outcome_probe.v1",
        )
        self.assertEqual(summary["status"], "ok")
        self.assertEqual(summary["run_count"], 5)
        self.assertEqual(summary["successful_runs"], 5)
        self.assertEqual(summary["failed_run_count"], 0)
        self.assertTrue(
            summary["same_process_live_ros_result_submission_claim"]
        )
        self.assertTrue(summary["actual_terminal_result_mapping_claim"])
        self.assertTrue(summary["task_outcome_submission_session_reuse_claim"])
        self.assertTrue(
            summary["netem_configured_both_gateway_and_ros_client"]
        )
        self.assertFalse(summary["production_quic_backend_claim"])
        self.assertFalse(summary["production_readiness"])
        self.assertTrue(all(evidence_run_ok(row) for row in summary["runs"]))

    @unittest.skipUnless(ARTIFACT.is_file(), "external Docker evidence artifact absent")
    def test_each_run_proves_pid_context_mtls_and_task_failure_pressure(self) -> None:
        summary = json.loads(ARTIFACT.read_text(encoding="utf-8"))
        for row in summary["runs"]:
            submission = row["task_outcome_gateway_submission"]
            service = row["gateway_service"]
            metrics = service["metrics"]
            transport = service["transport_metrics"]
            self.assertEqual(submission["process_id"], row["client_process_id"])
            self.assertTrue(
                row["rclpy_context_active_during_gateway_submission"]
            )
            self.assertTrue(row["ros_node_alive_during_gateway_submission"])
            self.assertEqual(submission["connections_created"], 1)
            self.assertEqual(submission["handshakes_completed"], 1)
            self.assertEqual(submission["streams_opened"], 6)
            self.assertEqual(submission["connection_reuse_count"], 5)
            self.assertEqual(metrics["application_outcome_updates"], 3)
            self.assertEqual(metrics["application_task_outcome_updates"], 3)
            self.assertEqual(metrics["application_task_outcome_failures"], 1)
            self.assertEqual(transport["client_certificates_accepted"], 1)
            self.assertEqual(
                transport["publisher_identity_authorization_rejected"], 0
            )

    @unittest.skipUnless(ARTIFACT.is_file(), "external Docker evidence artifact absent")
    def test_validator_rejects_false_same_process_and_missing_failure(self) -> None:
        row = json.loads(ARTIFACT.read_text(encoding="utf-8"))["runs"][0]
        mutated = copy.deepcopy(row)
        mutated["client_process_id"] += 1
        self.assertFalse(evidence_run_ok(mutated))
        mutated = copy.deepcopy(row)
        mutated["gateway_service"]["metrics"][
            "application_task_outcome_failures"
        ] = 0
        self.assertFalse(evidence_run_ok(mutated))
        mutated = copy.deepcopy(row)
        mutated["task_outcome_gateway_submission"]["connection_reuse_count"] = 4
        self.assertFalse(evidence_run_ok(mutated))

    def test_manifest_exposes_live_boundary_but_not_production_quic(self) -> None:
        capabilities = json.loads(
            (
                ROOT
                / "ros2_ws"
                / "src"
                / "rmw_fleetqox_cpp"
                / "capabilities.json"
            ).read_text(encoding="utf-8")
        )
        self.assertTrue(
            capabilities["supported"][
                "docker_nav2_rmf_live_task_outcome_5run_mtls_netem"
            ]
        )
        self.assertTrue(
            capabilities["supported"][
                "nav2_rmf_live_task_outcome_service_repeat_reliability"
            ]
        )
        self.assertTrue(
            capabilities["claim_boundaries"][
                "nav2_rmf_live_ros_same_process_outcome_submission_claim"
            ]
        )
        self.assertFalse(capabilities["production_ready"])
        self.assertFalse(
            capabilities["claim_boundaries"]["production_quic_backend_claim"]
        )


if __name__ == "__main__":
    unittest.main()

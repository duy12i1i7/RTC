import copy
import json
from pathlib import Path
import unittest

from scripts.run_rmw_docker_router_nav2_rmf_action_workload import (
    task_outcomes_ok,
)


ROOT = Path(__file__).resolve().parents[1]
ARTIFACT = (
    ROOT
    / "results_rmw_socket"
    / "docker_router_nav2_rmf_action_workload_concurrency8_summary.json"
)


class Nav2RmfTaskOutcomeTest(unittest.TestCase):
    def test_real_upstream_terminal_results_map_to_gateway_documents(self) -> None:
        summary = json.loads(ARTIFACT.read_text(encoding="utf-8"))
        self.assertEqual(summary["status"], "ok")
        self.assertTrue(summary["nav2_application_outcome_mapping_claim"])
        self.assertTrue(summary["rmf_application_outcome_mapping_claim"])
        self.assertTrue(summary["task_outcome_delivery_success_separation_claim"])
        self.assertFalse(summary["task_outcome_gateway_submission_performed"])
        self.assertTrue(task_outcomes_ok(summary["client"]))

        outcomes = summary["client"]["application_outcomes"]
        self.assertEqual(
            [row["terminal_status"] for row in outcomes],
            ["succeeded", "canceled", "succeeded"],
        )
        self.assertEqual(
            [row["task_succeeded"] for row in outcomes],
            [True, False, True],
        )
        self.assertEqual([row["delivered"] for row in outcomes], [True] * 3)

    def test_validator_rejects_conflated_cancel_and_delivery(self) -> None:
        client = json.loads(ARTIFACT.read_text(encoding="utf-8"))["client"]
        mutated = copy.deepcopy(client)
        mutated["application_outcomes"][1]["delivered"] = False
        self.assertFalse(task_outcomes_ok(mutated))
        mutated = copy.deepcopy(client)
        mutated["application_outcomes"][1]["task_succeeded"] = True
        self.assertFalse(task_outcomes_ok(mutated))
        mutated = copy.deepcopy(client)
        mutated["task_outcome_gateway_submission_performed"] = True
        self.assertFalse(task_outcomes_ok(mutated))

    def test_workload_imports_the_shared_strict_adapter(self) -> None:
        source = (
            ROOT
            / "scripts"
            / "run_rmw_docker_router_nav2_rmf_action_workload.py"
        ).read_text(encoding="utf-8")
        self.assertIn("from fleetqox.task_outcome import (", source)
        self.assertIn("nav2_application_outcome(", source)
        self.assertIn("rmf_application_outcome(", source)
        self.assertIn("submit_live_task_outcomes(", source)
        self.assertIn("--live-task-outcome-gateway", source)
        capabilities = json.loads((
            ROOT
            / "ros2_ws"
            / "src"
            / "rmw_fleetqox_cpp"
            / "capabilities.json"
        ).read_text(encoding="utf-8"))
        self.assertTrue(capabilities["claim_boundaries"][
            "nav2_rmf_application_outcome_mapping_claim"
        ])
        self.assertTrue(capabilities["claim_boundaries"][
            "nav2_rmf_application_outcome_gateway_submission_claim"
        ])
        self.assertTrue(capabilities["claim_boundaries"][
            "nav2_rmf_live_ros_same_process_outcome_submission_claim"
        ])


if __name__ == "__main__":
    unittest.main()

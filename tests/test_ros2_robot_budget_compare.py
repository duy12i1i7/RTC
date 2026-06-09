import json
import unittest
from tempfile import TemporaryDirectory
from pathlib import Path

from scripts.compare_ros2_robot_budget_summaries import compare_summary_specs


class Ros2RobotBudgetCompareTest(unittest.TestCase):
    def test_compare_summary_specs_reports_deltas(self) -> None:
        with TemporaryDirectory() as tmpdir:
            baseline = Path(tmpdir) / "baseline.json"
            candidate = Path(tmpdir) / "candidate.json"
            baseline.write_text(json.dumps(_summary("base", 0.80, 0.30, 100.0)))
            candidate.write_text(json.dumps(_summary("candidate", 0.90, 0.20, 80.0)))

            result = compare_summary_specs(
                [f"baseline:{baseline}", f"candidate:{candidate}"]
            )

        self.assertEqual(result["baseline_label"], "baseline")
        rows = {row["label"]: row for row in result["policies"]}
        self.assertAlmostEqual(
            rows["candidate"]["delta_vs_baseline"][
                "per_robot_min_control_delivery_ratio_mean"
            ],
            0.10,
        )
        self.assertAlmostEqual(
            rows["candidate"]["delta_vs_baseline"]["deadline_miss_ratio_mean"],
            -0.10,
        )


def _summary(policy: str, min_ctrl: float, deadline_miss: float, p95: float) -> dict:
    return {
        "policies": [
            {
                "policy": policy,
                "runs": 2,
                "per_robot_budget_pass_ratio": 0.5,
                "per_robot_min_control_delivery_ratio_mean": min_ctrl,
                "per_robot_max_deadline_miss_ratio_mean": 0.25,
                "per_robot_rx_jain_index_mean": 1.0,
                "per_robot_control_delivery_jain_index_mean": 0.99,
                "per_robot_deadline_success_jain_index_mean": 0.98,
                "per_robot_latency_p95_spread_ms_mean": 4.0,
                "rx_mean": 10.0,
                "loss_ratio_mean": 0.1,
                "control_delivery_ratio_mean": min_ctrl,
                "deadline_miss_ratio_mean": deadline_miss,
                "latency_p95_ms_mean": p95,
                "semantic_utility_delivered_mean": 42.0,
            }
        ],
        "comparison_rows": [
            {
                "seed": 7,
                "per_robot_budget_pass": True,
                "per_robot_min_control_delivery_ratio": min_ctrl,
                "per_robot_max_deadline_miss_ratio": 0.25,
                "per_robot_worst_control_delivery_robot": "robot_0001",
                "rx": 10,
                "control_delivery_ratio": min_ctrl,
                "deadline_miss_ratio": deadline_miss,
                "latency_p95_ms": p95,
            }
        ],
    }


if __name__ == "__main__":
    unittest.main()

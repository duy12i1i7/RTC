import argparse
import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from scripts.run_ros2_n_robot_qoe_quota_matrix import (
    aggregate_plans,
    build_matrix_plan,
    invalid_infrastructure_reasons,
    positive_ints,
)


class Ros2NRobotQoeQuotaMatrixTest(unittest.TestCase):
    def test_build_matrix_plan_uses_robot_count_and_seed_label(self) -> None:
        args = _args()

        plan = build_matrix_plan(args, robot_count=4, seeds=[7, 13, 29])

        self.assertIn("4robot_qoe_recovery_quota_3seed_v1", plan.scenario)
        self.assertEqual(plan.summary_path, Path("out/dynamic_objective_transition_4robot_qoe_recovery_quota_3seed_summary.json"))
        self.assertIn("--robot-count", plan.command)
        self.assertEqual(plan.command[plan.command.index("--robot-count") + 1], "4")
        self.assertEqual(plan.command[plan.command.index("--seeds") + 1], "7,13,29")
        self.assertIn("--projection-quality-delivery-mode", plan.command)
        self.assertIn("--transport-volatility-probe-quota-scale", plan.command)
        self.assertIn("--control-lease-ack-retransmit", plan.command)
        self.assertIn("--egress-feedback-control-lease-ack-immediate", plan.command)
        self.assertIn("--egress-feedback-control-lease-ack-adaptive", plan.command)
        self.assertEqual(
            plan.command[plan.command.index("--egress-feedback-control-lease-ack-window-events") + 1],
            "8",
        )
        self.assertEqual(
            plan.command[plan.command.index("--egress-feedback-control-lease-ack-adaptive-min-events") + 1],
            "4",
        )
        self.assertEqual(
            plan.command[plan.command.index("--egress-feedback-control-lease-ack-adaptive-max-events") + 1],
            "16",
        )
        self.assertEqual(
            plan.command[plan.command.index("--egress-feedback-control-lease-ack-adaptive-success-step") + 1],
            "2",
        )
        self.assertEqual(
            plan.command[plan.command.index("--egress-feedback-control-lease-ack-adaptive-failure-multiplier") + 1],
            "1.5",
        )
        self.assertEqual(
            plan.command[plan.command.index("--egress-feedback-control-lease-ack-adaptive-max-age-ms") + 1],
            "75.0",
        )
        self.assertNotIn(
            "--egress-feedback-control-lease-ack-adaptive-no-piggyback-first",
            plan.command,
        )

    def test_aggregate_plans_reports_best_count_with_budget_and_quality(self) -> None:
        with TemporaryDirectory() as tmpdir:
            base = Path(tmpdir)
            plan4 = _plan(base, 4)
            plan8 = _plan(base, 8)
            plan16 = _plan(base, 16)
            plan4.summary_path.write_text(json.dumps(_summary(4, budget=1.0, quality=1.0)))
            plan8.summary_path.write_text(json.dumps(_summary(8, budget=1.0, quality=1.0)))
            plan16.summary_path.write_text(json.dumps(_summary(16, budget=1.0, quality=0.5)))

            result = aggregate_plans([plan16, plan4, plan8])

        self.assertEqual(result["best_robot_count"], 8)
        rows = {row["robot_count"]: row for row in result["rows"]}
        self.assertEqual(rows[4]["status"], "summarized")
        self.assertEqual(rows[16]["quality_gate_robot_coverage_ratio_mean"], 0.5)

    def test_aggregate_plans_marks_zero_traffic_summary_invalid(self) -> None:
        with TemporaryDirectory() as tmpdir:
            base = Path(tmpdir)
            plan = _plan(base, 8)
            plan.summary_path.write_text(json.dumps(_invalid_summary(8)))

            result = aggregate_plans([plan])

        self.assertIsNone(result["best_robot_count"])
        row = result["rows"][0]
        self.assertEqual(row["status"], "invalid_infrastructure")
        self.assertIn("no_packets_received", row["invalid_reasons"])
        self.assertIn("no_ros_robot_coverage", row["invalid_reasons"])

    def test_invalid_infrastructure_reasons_ignores_valid_zero_quality_run(self) -> None:
        row = {
            "runs": 1,
            "rx_mean": 64,
            "control_delivery_ratio_mean": 0.4,
            "decision_robot_coverage_ratio_mean": 1.0,
            "received_robot_coverage_ratio_mean": 1.0,
            "comparison_rows": [{"rx": 64}],
        }

        self.assertEqual(invalid_infrastructure_reasons(row), [])

    def test_aggregate_plans_marks_missing_summary(self) -> None:
        with TemporaryDirectory() as tmpdir:
            plan = _plan(Path(tmpdir), 4)

            result = aggregate_plans([plan])

        self.assertIsNone(result["best_robot_count"])
        self.assertEqual(result["rows"][0]["status"], "missing_summary")

    def test_positive_ints_rejects_non_positive_values(self) -> None:
        with self.assertRaises(ValueError):
            positive_ints("4,0", "--robot-counts")


def _args() -> argparse.Namespace:
    return argparse.Namespace(
        scenario_prefix="scenario",
        output_dir=Path("out"),
        bridge_config="experiments/bridge.json",
        rmw="rmw_zenoh_cpp",
        policy="fleetqox_semantic_contract_budgeted_deadline_first",
        seconds=4.0,
        rate_hz=10.0,
        bridge_max_batches=80,
        transition_segment_s=1.5,
        probe_quota_scale=1.0,
        probe_max_per_robot_per_tick=1,
        control_lease_ack_retransmit="on",
        egress_feedback_control_lease_ack_immediate=True,
        egress_feedback_control_lease_ack_window_events=8,
        egress_feedback_control_lease_ack_adaptive=True,
        egress_feedback_control_lease_ack_adaptive_min_events=4,
        egress_feedback_control_lease_ack_adaptive_max_events=16,
        egress_feedback_control_lease_ack_adaptive_success_step=2,
        egress_feedback_control_lease_ack_adaptive_failure_multiplier=1.5,
        egress_feedback_control_lease_ack_adaptive_max_age_ms=75.0,
        egress_feedback_control_lease_ack_adaptive_piggyback_first=True,
        binding_objective_summary="autonomy_safety:summary.json",
        binding_objective_schedule="balanced_safety_utility@0,autonomy_safety@1.5",
    )


def _plan(base: Path, robot_count: int):
    args = _args()
    args.output_dir = base
    return build_matrix_plan(args, robot_count=robot_count, seeds=[7])


def _summary(robot_count: int, *, budget: float, quality: float) -> dict:
    return {
        "policies": [
            {
                "policy": "dynamic_objective/fleetqox/rmw_zenoh_cpp",
                "runs": 1,
                "robot_count_mean": robot_count,
                "per_robot_budget_pass_ratio": budget,
                "per_robot_min_control_delivery_ratio_mean": 0.95,
                "per_robot_max_deadline_miss_ratio_mean": 0.10,
                "decision_robot_coverage_ratio_mean": 1.0,
                "received_robot_coverage_ratio_mean": 1.0,
                "egress_robot_coverage_ratio_mean": 1.0,
                "lease_robot_coverage_ratio_mean": 1.0,
                "quality_gate_robot_coverage_ratio_mean": quality,
                "egress_monitor_robot_coverage_ratio_mean": 1.0,
                "rx_mean": 100.0,
                "loss_ratio_mean": 0.01,
                "control_delivery_ratio_mean": 1.0,
                "deadline_miss_ratio_mean": 0.08,
                "latency_p95_ms_mean": 300.0,
                "semantic_utility_delivered_mean": 700.0,
                "quality_gate_robots_observed": [
                    f"robot_{index:04d}" for index in range(robot_count)
                ],
            }
        ],
        "comparison_rows": [
            {
                "seed": 7,
                "status": "ran",
                "robot_count": robot_count,
                "rx": 100,
                "control_delivery_ratio": 1.0,
                "deadline_miss_ratio": 0.08,
                "latency_p95_ms": 300.0,
                "per_robot_budget_pass": budget >= 1.0,
                "per_robot_min_control_delivery_ratio": 0.95,
                "per_robot_max_deadline_miss_ratio": 0.10,
                "quality_gate_robot_coverage_ratio": quality,
            }
        ],
    }


def _invalid_summary(robot_count: int) -> dict:
    summary = _summary(robot_count, budget=0.0, quality=0.0)
    policy = summary["policies"][0]
    policy.update(
        {
            "decision_robot_coverage_ratio_mean": 0.0,
            "received_robot_coverage_ratio_mean": 0.0,
            "egress_robot_coverage_ratio_mean": 0.0,
            "lease_robot_coverage_ratio_mean": 0.0,
            "egress_monitor_robot_coverage_ratio_mean": 0.0,
            "rx_mean": 0.0,
            "control_delivery_ratio_mean": 0.0,
        }
    )
    summary["comparison_rows"][0].update(
        {
            "rx": 0,
            "control_delivery_ratio": 0.0,
            "status": "ran",
        }
    )
    return summary


if __name__ == "__main__":
    unittest.main()

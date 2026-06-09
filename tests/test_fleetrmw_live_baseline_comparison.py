import unittest
from pathlib import Path

from scripts.compare_fleetrmw_live_baselines import (
    build_comparison,
    direct_rows_for_summary,
    fleet_matched_rows,
    fleet_mode_rows,
    fleet_profile_rows,
    parse_ros2_summary_args,
    parse_direct_summary_args,
    render_markdown,
    ros2_rows_for_summary,
    summarize_comparison,
)


class FleetRmwLiveBaselineComparisonTest(unittest.TestCase):
    def test_extracts_fleetrmw_mode_rows_with_repair_cost(self) -> None:
        rows = fleet_mode_rows(_ablation_summary(), source=Path("ablation.json"))

        self.assertEqual(rows[0]["policy"], "rmw_fleetqox_cpp/control_state")
        self.assertEqual(rows[0]["success_ratio"], 1.0)
        self.assertAlmostEqual(rows[0]["latency_metric_ms"], 125.0)
        self.assertAlmostEqual(rows[0]["repair_cost_frames_mean"], 14.0)
        self.assertEqual(rows[1]["failure_kind_counts"], {"delivery_failed": 1})

    def test_extracts_fleetrmw_profile_rows_from_sweeps(self) -> None:
        rows = fleet_profile_rows(_ablation_summary(), source=Path("ablation.json"))
        by_key = {(row["profile"], row["mode"]): row for row in rows}

        self.assertEqual(by_key[("wifi", "control_state")]["ok_runs"], 2)
        self.assertEqual(by_key[("wifi", "state_only")]["ok_runs"], 1)
        self.assertEqual(by_key[("wifi", "state_only")]["failure_kind_counts"], {"delivery_failed": 1})
        self.assertAlmostEqual(by_key[("wifi", "control_state")]["max_ok_loss_scale"], 0.5)

    def test_ros2_rows_extract_policy_metrics(self) -> None:
        rows = ros2_rows_for_summary(_ros2_summary(), profile="wifi", source=Path("wifi.json"))

        self.assertEqual(rows[0]["policy"], "data_frame/rmw_zenoh_cpp")
        self.assertEqual(rows[0]["comparability"], "indirect_named_profile")
        self.assertAlmostEqual(rows[0]["delivery_metric"], 1.0)
        self.assertAlmostEqual(rows[0]["latency_p95_ms_mean"], 38.0)

    def test_extracts_fleetrmw_matched_rows_with_terminal_guard(self) -> None:
        rows = fleet_matched_rows(_matched_summary(), source=Path("matched.json"))

        self.assertEqual(rows[0]["comparability"], "fleet_router_redundancy_4robot")
        self.assertEqual(rows[0]["state_terminal_guard_payload"], "terminal_guard")
        self.assertEqual(rows[0]["terminal_guard_algorithm"], "deadline_sequence_repair_v1")
        self.assertEqual(rows[0]["terminal_guard_repeat_count"], 5)
        self.assertEqual(rows[0]["terminal_horizon"]["risk_score"], 2.25)
        self.assertEqual(rows[0]["state_expected_count"], 12)
        self.assertAlmostEqual(rows[0]["delivery_metric"], 1.0)

    def test_summary_and_markdown_keep_comparability_caveat(self) -> None:
        fleet_modes = fleet_mode_rows(_ablation_summary(), source=Path("ablation.json"))
        fleet_profiles = fleet_profile_rows(_ablation_summary(), source=Path("ablation.json"))
        fleet_matched = fleet_matched_rows(_matched_summary(), source=Path("matched.json"))
        ros2_rows = ros2_rows_for_summary(_ros2_summary(), profile="wifi", source=Path("wifi.json"))
        direct_rows = direct_rows_for_summary(_direct_summary(), source=Path("direct.json"))
        summary = summarize_comparison(
            fleetrmw_mode_rows=fleet_modes,
            fleetrmw_profile_rows=fleet_profiles,
            fleetrmw_matched_rows=fleet_matched,
            ros2_policy_rows=ros2_rows,
            direct_rmw_rows=direct_rows,
        )
        markdown = render_markdown(
            {
                "schema_version": "fleetrmw.live_baseline_comparison.v1",
                "status": "ok",
                "comparability_contract": {
                    "direct_claim_allowed": False,
                    "reason": "topology differs",
                },
                "fleetrmw_mode_rows": fleet_modes,
                "fleetrmw_matched_rows": fleet_matched,
                "ros2_policy_rows": ros2_rows,
                "summary": summary,
            }
        )

        self.assertEqual(summary["fleetrmw_best_policy"], "rmw_fleetqox_cpp/control_state")
        self.assertEqual(summary["ros2_profile_winners"][0]["policy"], "data_frame/rmw_zenoh_cpp")
        self.assertIn("Direct claim allowed: `False`", markdown)
        self.assertIn("Direct ROS 2 RMW Seed Rows", markdown)
        self.assertIn("FleetRMW Matched 4-Robot Profile Rows", markdown)
        self.assertIn("deadline_sequence_repair_v1 r=5.000 a=2.000 w=1.000/2000.000ms d=4000.000ms", markdown)
        self.assertIn("direct.json", markdown)
        self.assertIn("Research Gaps", markdown)
        self.assertIn("rmw_fleetqox_cpp/control_state", markdown)

    def test_parse_ros2_summary_args_accepts_profile_paths(self) -> None:
        parsed = parse_ros2_summary_args(["wifi:results/wifi.json", "results/wan_summary.json"])

        self.assertEqual(parsed["wifi"], Path("results/wifi.json"))
        self.assertEqual(parsed["wan"], Path("results/wan_summary.json"))

    def test_parse_direct_summary_args_preserves_paths(self) -> None:
        parsed = parse_direct_summary_args([Path("a.json"), Path("b.json")])

        self.assertEqual(parsed, [Path("a.json"), Path("b.json")])

    def test_direct_rows_extract_delivery_and_skip_reason(self) -> None:
        rows = direct_rows_for_summary(_direct_summary(), source=Path("direct.json"))

        self.assertEqual(rows[0]["evidence_family"], "ros2_direct_rmw")
        self.assertEqual(rows[0]["delivery_metric"], 1.0)
        self.assertTrue(rows[0]["netem_applied"])
        self.assertEqual(rows[1]["status"], "skipped")
        self.assertEqual(rows[1]["reason"], "rmw_unavailable")


def _ablation_summary() -> dict[str, object]:
    return {
        "summary": {
            "ranking": [
                {
                    "mode": "control_state",
                    "run_count": 2,
                    "ok_run_count": 2,
                    "ok_control_delivery_latency_ms_mean": 75.0,
                    "ok_state_delivery_latency_ms_mean": 50.0,
                    "max_all_profiles_ok_loss_scale": 0.5,
                    "repair_cost_frames_mean": 14.0,
                    "failure_kind_counts": {},
                },
                {
                    "mode": "state_only",
                    "run_count": 2,
                    "ok_run_count": 1,
                    "ok_control_delivery_latency_ms_mean": 90.0,
                    "ok_state_delivery_latency_ms_mean": 40.0,
                    "max_all_profiles_ok_loss_scale": 0.1,
                    "repair_cost_frames_mean": 6.0,
                    "failure_kind_counts": {"delivery_failed": 1},
                },
            ],
        },
        "sweeps": [
            {
                "mode": "control_state",
                "sweep": {
                    "runs": [
                        _fleet_run("wifi", 0.1, "ok", 70.0, 40.0),
                        _fleet_run("wifi", 0.5, "ok", 80.0, 50.0),
                    ],
                },
            },
            {
                "mode": "state_only",
                "sweep": {
                    "runs": [
                        _fleet_run("wifi", 0.1, "ok", 80.0, 45.0),
                        _fleet_run("wifi", 0.5, "failed", 0.0, 0.0),
                    ],
                },
            },
        ],
    }


def _fleet_run(
    profile: str,
    loss_scale: float,
    status: str,
    control_latency_ms: float,
    state_latency_ms: float,
) -> dict[str, object]:
    return {
        "profile": profile,
        "loss_scale": loss_scale,
        "status": status,
        "failure_kind": "delivery_failed" if status != "ok" else "none",
        "control_delivery_latency_ms_mean": control_latency_ms,
        "state_delivery_latency_ms_mean": state_latency_ms,
    }


def _ros2_summary() -> dict[str, object]:
    return {
        "policies": [
            {
                "policy": "data_frame/rmw_zenoh_cpp",
                "runs": 3,
                "control_delivery_ratio_mean": 1.0,
                "latency_p95_ms_mean": 38.0,
                "latency_p99_ms_mean": 63.0,
                "loss_ratio_mean": 0.02,
                "deadline_miss_ratio_mean": 0.0,
                "semantic_utility_delivered_mean": 458.0,
                "pareto_frontier": True,
            },
            {
                "policy": "event_json/rmw_fastrtps_cpp",
                "runs": 3,
                "control_delivery_ratio_mean": 0.95,
                "latency_p95_ms_mean": 61.0,
                "latency_p99_ms_mean": 81.0,
                "loss_ratio_mean": 0.04,
                "deadline_miss_ratio_mean": 0.0,
                "semantic_utility_delivered_mean": 430.0,
                "pareto_frontier": False,
            },
        ],
    }


def _matched_summary() -> dict[str, object]:
    return {
        "robot_count": 4,
        "runs": [
            {
                "profile": "wifi",
                "status": "ok",
                "robot_count": 4,
                "topic_count": 8,
                "control_payload_count": 32,
                "state_payload_count": 32,
                "control_payloads_per_publisher": 3,
                "state_payloads_per_publisher": 3,
                "terminal_guard_algorithm": "deadline_sequence_repair_v1",
                "terminal_guard_repeat_count": 5,
                "terminal_guard_router_dwell_ms": 4000,
                "terminal_guard_required_sequence": 4,
                "terminal_horizon": {
                    "algorithm": "deadline_sequence_repair_v1",
                    "repeat_count": 5,
                    "router_dwell_ms": 4000,
                    "startup_settle_ms": 1000,
                    "pre_publish_wait_ms": 0,
                    "post_plan_settle_ms": 0,
                    "pre_payload_warmup_count": 1,
                    "pre_payload_warmup_ack_count": 1,
                    "pre_payload_warmup_ack_timeout_ms": 2000,
                    "app_repair_cycle_count": 2,
                    "tail_repair_repeat_count": 5,
                    "required_sequence": 4,
                    "proactive_data_repeats": 1,
                    "risk_score": 2.25,
                    "scaled_primary_loss": 0.018,
                    "scaled_backup_loss": 0.0035,
                    "latency_budget_ms": 160.0,
                },
                "control_wire_payloads_per_publisher": 20,
                "state_wire_payloads_per_publisher": 20,
                "control_delivery_latency_ms_mean": 42.0,
                "state_delivery_latency_ms_mean": 33.0,
                "state_terminal_guard_payload": "terminal_guard",
                "primary_expected_forwarded_topic_source_sequences": (
                    "/robot_0000/cmd_vel=4;/robot_0001/cmd_vel=4"
                ),
                "backup_expected_forwarded_topic_source_sequences": (
                    "/robot_0000/odom=4;/robot_0001/odom=4"
                ),
                "netem_status": {
                    "primary_wifi": {"status": "applied"},
                    "backup_5g": {"status": "applied"},
                },
            }
        ],
    }


def _direct_summary() -> dict[str, object]:
    return {
        "runs": [
            {
                "rmw": "rmw_fastrtps_cpp",
                "profile": "wifi",
                "status": "ok",
                "control_delivery_ratio": 1.0,
                "state_delivery_ratio": 1.0,
                "control_latency_ms_p95": 10.0,
                "state_latency_ms_p95": 11.0,
                "netem_applied": True,
            },
            {
                "rmw": "rmw_cyclonedds_cpp",
                "profile": "wifi",
                "status": "skipped",
                "reason": "rmw_unavailable",
                "control_delivery_ratio": 0.0,
                "state_delivery_ratio": 0.0,
                "netem_applied": False,
            },
        ],
    }


if __name__ == "__main__":
    unittest.main()

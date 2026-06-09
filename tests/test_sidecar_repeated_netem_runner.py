import argparse
import sys
import unittest
from pathlib import Path

from scripts.run_sidecar_repeated_netem import (
    annotate_records_with_profiles,
    build_netem_command,
    build_run_plan,
    lagrangian_option_values,
    netem_values_for,
    parse_ints,
    profile_for_scenario,
    summarize_profiles,
    write_report_if_requested,
)


class SidecarRepeatedNetemRunnerTest(unittest.TestCase):
    def test_parse_ints(self) -> None:
        self.assertEqual(parse_ints("7, 13,29", "--seeds"), [7, 13, 29])

    def test_build_run_plan_names_seeded_matrix_outputs(self) -> None:
        plans = build_run_plan("sweep", [7, 13], Path("results"))

        self.assertEqual(plans[0].scenario, "sweep_seed_7")
        self.assertEqual(plans[1].metrics_path, Path("results/sweep_seed_13_matrix_metrics.jsonl"))

    def test_build_run_plan_expands_named_profiles(self) -> None:
        plans = build_run_plan("sweep", [7, 13], Path("results"), ["wifi", "wan"])

        self.assertEqual(plans[0].scenario, "sweep_wifi_seed_7")
        self.assertEqual(plans[1].profile, "wifi")
        self.assertEqual(plans[2].scenario, "sweep_wan_seed_7")
        self.assertEqual(plans[3].metrics_path, Path("results/sweep_wan_seed_13_matrix_metrics.jsonl"))

    def test_build_netem_command_uses_closed_loop_and_explicit_policies(self) -> None:
        args = argparse.Namespace(
            robots=10,
            seconds=2,
            capacity_bytes_per_second=120_000,
            delay_ms=20,
            jitter_ms=5,
            loss_percent=1,
            rate_mbit=20,
            output_dir=Path("results"),
            closed_loop_feed=True,
            policy_label=None,
            lagrangian_deadline_risk_budget=None,
            lagrangian_initial_deadline_lambda=None,
            lagrangian_risk_barrier_start=None,
            lagrangian_risk_barrier_scale=None,
            lagrangian_deadline_drop_risk=None,
        )
        plan = build_run_plan("sweep", [7], Path("results"))[0]

        command = build_netem_command(args, ["fleetqox_csds", "fleetqox_predictive"], plan)

        self.assertEqual(command[:4], [sys.executable, "-m", "scripts.run_sidecar_netem", "--run"])
        self.assertIn("--closed-loop-feed", command)
        self.assertIn("sweep_seed_7", command)
        self.assertEqual(command.count("--policy"), 2)

    def test_build_netem_command_passes_lagrangian_variant_options(self) -> None:
        args = argparse.Namespace(
            robots=10,
            seconds=2,
            capacity_bytes_per_second=120_000,
            delay_ms=20,
            jitter_ms=5,
            loss_percent=1,
            rate_mbit=20,
            output_dir=Path("results"),
            closed_loop_feed=False,
            policy_label="lag_012",
            lagrangian_deadline_risk_budget=0.08,
            lagrangian_initial_deadline_lambda=1.8,
            lagrangian_risk_barrier_start=0.62,
            lagrangian_risk_barrier_scale=12.0,
            lagrangian_deadline_drop_risk=0.45,
        )
        plan = build_run_plan("sweep", [7], Path("results"))[0]

        command = build_netem_command(args, ["fleetqox_predictive_lagrangian"], plan)

        self.assertIn("--policy-label", command)
        self.assertIn("lag_012", command)
        self.assertIn("--lagrangian-risk-barrier-start", command)
        self.assertIn("0.62", command)
        self.assertEqual(
            lagrangian_option_values(args)[-1],
            ("--lagrangian-deadline-drop-risk", 0.45),
        )

    def test_build_netem_command_uses_profile_values(self) -> None:
        args = argparse.Namespace(
            robots=10,
            seconds=2,
            capacity_bytes_per_second=1,
            delay_ms=2,
            jitter_ms=3,
            loss_percent=4,
            rate_mbit=5,
            output_dir=Path("results"),
            closed_loop_feed=False,
            policy_label=None,
            lagrangian_deadline_risk_budget=None,
            lagrangian_initial_deadline_lambda=None,
            lagrangian_risk_barrier_start=None,
            lagrangian_risk_barrier_scale=None,
            lagrangian_deadline_drop_risk=None,
        )
        plan = build_run_plan("sweep", [7], Path("results"), ["wan"])[0]

        command = build_netem_command(args, ["fleetqox_predictive"], plan)

        self.assertEqual(netem_values_for(args, None)["delay_ms"], 2)
        self.assertIn("--delay-ms", command)
        self.assertIn("60", command)
        self.assertIn("--rate-mbit", command)
        self.assertIn("10", command)

    def test_profile_annotation_and_summary(self) -> None:
        plans = build_run_plan("sweep", [7], Path("results"), ["wifi"])
        records = [
            {
                "policy": "fleetqox",
                "scenario": "sweep_wifi_seed_7_fleetqox",
                "semantic_utility_delivered": 100,
                "control_starvation_events": 0,
                "deadline_miss_ratio": 0.0,
                "loss_ratio": 0.0,
                "latency_p95_ms": 20.0,
                "latency_p99_ms": 25.0,
                "rx": 10,
                "tx": 10,
                "compacted_rx": 1,
                "bytes_rx": 100,
            }
        ]

        annotated = annotate_records_with_profiles(records, plans)
        summaries = summarize_profiles(annotated, plans)

        self.assertEqual(profile_for_scenario("sweep_wifi_seed_7_fleetqox", plans), "wifi")
        self.assertEqual(annotated[0]["profile"], "wifi")
        self.assertEqual(summaries[0]["profile"], "wifi")
        self.assertEqual(summaries[0]["policies"][0]["runs"], 1)

    def test_write_report_skips_when_metric_files_are_missing(self) -> None:
        args = argparse.Namespace(report=True)
        plans = build_run_plan("missing", [7], Path("results"))

        result = write_report_if_requested(args, plans)

        self.assertTrue(result["report_skipped"])
        self.assertIn("missing_seed_7_matrix_metrics.jsonl", result["missing_metrics"][0])


if __name__ == "__main__":
    unittest.main()

import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from fleetqox.sidecar_repeated import (
    dominates,
    read_sidecar_metric_records,
    render_repeated_markdown_report,
    summarize_repeated_sidecar_metrics,
)
from scripts.report_sidecar_repeated import expand_metric_paths


class SidecarRepeatedTest(unittest.TestCase):
    def test_summarize_repeated_metrics_computes_ci_and_pareto(self) -> None:
        records = [
            _record("better", 100, 0, 0.0, 0.0, 1000),
            _record("better", 110, 0, 0.0, 0.0, 1010),
            _record("dominated", 90, 0, 0.0, 0.01, 980),
            _record("utility_tradeoff", 150, 5, 0.02, 0.02, 1200),
        ]

        summary = summarize_repeated_sidecar_metrics(records)
        by_policy = {row["policy"]: row for row in summary["policies"]}

        self.assertEqual(by_policy["better"]["runs"], 2)
        self.assertAlmostEqual(
            by_policy["better"]["semantic_utility_delivered_mean"],
            105.0,
        )
        self.assertGreater(by_policy["better"]["semantic_utility_delivered_ci95"], 0.0)
        self.assertTrue(by_policy["better"]["pareto_frontier"])
        self.assertFalse(by_policy["dominated"]["pareto_frontier"])
        self.assertIn("utility_tradeoff", summary["pareto_frontier"])

    def test_dominates_respects_mixed_objectives(self) -> None:
        left = {
            "semantic_utility_delivered_mean": 100.0,
            "control_starvation_events_mean": 0.0,
            "deadline_miss_ratio_mean": 0.0,
            "loss_ratio_mean": 0.0,
        }
        right = {
            "semantic_utility_delivered_mean": 90.0,
            "control_starvation_events_mean": 0.0,
            "deadline_miss_ratio_mean": 0.0,
            "loss_ratio_mean": 0.01,
        }

        self.assertTrue(dominates(left, right))
        self.assertFalse(dominates(right, left))

    def test_read_records_and_render_markdown(self) -> None:
        with TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "metrics.jsonl"
            path.write_text(
                json.dumps(_record("fleetqox", 42, 0, 0.0, 0.0, 10)) + "\n",
                encoding="utf-8",
            )

            records = read_sidecar_metric_records([path])
            summary = summarize_repeated_sidecar_metrics(records)
            report = render_repeated_markdown_report(
                summary,
                title="Smoke",
                metrics_paths=[path],
            )

        self.assertEqual(records[0]["policy"], "fleetqox")
        self.assertIn("# Smoke", report)
        self.assertIn("Policy Summary", report)

    def test_render_markdown_includes_profile_summaries(self) -> None:
        summary = summarize_repeated_sidecar_metrics(
            [_record("fleetqox", 42, 0, 0.0, 0.0, 10)]
        )
        profile_summary = summarize_repeated_sidecar_metrics(
            [_record("fleetqox", 42, 0, 0.0, 0.0, 10)]
        )
        profile_summary["profile"] = "wifi"
        profile_summary["config"] = {
            "capacity_bytes_per_second": 120_000,
            "delay_ms": 20,
            "jitter_ms": 5,
            "loss_percent": 1,
            "rate_mbit": 20,
        }
        summary["profiles"] = [profile_summary]

        report = render_repeated_markdown_report(summary, title="Profiles")

        self.assertIn("Profile Summaries", report)
        self.assertIn("`wifi`", report)
        self.assertIn("120000.0 B/s", report)

    def test_expand_metric_paths_supports_globs(self) -> None:
        with TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            one = root / "one_metrics.jsonl"
            two = root / "two_metrics.jsonl"
            one.write_text("", encoding="utf-8")
            two.write_text("", encoding="utf-8")

            paths = expand_metric_paths([str(root / "*_metrics.jsonl")])

        self.assertEqual([path.name for path in paths], ["one_metrics.jsonl", "two_metrics.jsonl"])


def _record(
    policy: str,
    utility: float,
    control_misses: int,
    deadline_miss: float,
    loss: float,
    rx: int,
) -> dict[str, object]:
    return {
        "policy": policy,
        "scenario": f"{policy}_scenario",
        "semantic_utility_delivered": utility,
        "control_starvation_events": control_misses,
        "deadline_miss_ratio": deadline_miss,
        "loss_ratio": loss,
        "latency_p95_ms": 20.0,
        "latency_p99_ms": 30.0,
        "rx": rx,
        "tx": rx,
        "compacted_rx": 0,
        "bytes_rx": rx * 10,
    }


if __name__ == "__main__":
    unittest.main()

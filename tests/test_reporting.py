import csv
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from fleetqox.reporting import (
    component_winners,
    load_summary,
    render_markdown_report,
    write_summary_csv,
)
from fleetqox.ros2_perf import write_perf_records_jsonl


class ReportingTest(unittest.TestCase):
    def test_component_winners(self) -> None:
        winners = component_winners(
            [
                {"scenario": "wifi", "component": "control", "rmw": "a", "rank_score": 0.3},
                {"scenario": "wifi", "component": "control", "rmw": "b", "rank_score": 0.4},
            ]
        )

        self.assertEqual(winners[0]["best_rmw"], "b")

    def test_render_markdown_report(self) -> None:
        summary = {
            "groups": [],
            "ranking": [
                {
                    "scenario": "wifi",
                    "component": "state",
                    "rmw": "rmw_zenoh_cpp",
                    "runs": 3,
                    "rank_score": 0.95,
                    "qoe_score_mean": 0.96,
                    "latency_p95_ms_mean": 34.3,
                    "latency_p99_ms_mean": 42.9,
                    "jitter_p95_ms_mean": 11.9,
                    "loss_ratio_mean": 0.0,
                    "deadline_miss_ratio_mean": 0.0,
                    "throughput_mbps_mean": 0.15,
                    "cpu_mean": 0.1,
                    "memory_mean": 80.0,
                }
            ],
        }

        report = render_markdown_report(summary, title="Baseline")

        self.assertIn("# Baseline", report)
        self.assertIn("rmw_zenoh_cpp", report)
        self.assertIn("Component Winners", report)

    def test_write_summary_csv(self) -> None:
        summary = {
            "ranking": [
                {
                    "scenario": "wifi",
                    "component": "control",
                    "rmw": "rmw_a",
                    "runs": 1,
                    "rank_score": 0.5,
                }
            ]
        }
        with TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "report.csv"
            write_summary_csv(summary, path)
            with path.open(encoding="utf-8") as handle:
                rows = list(csv.DictReader(handle))

        self.assertEqual(rows[0]["rmw"], "rmw_a")

    def test_load_summary_from_metrics(self) -> None:
        with TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "metrics.jsonl"
            write_perf_records_jsonl(
                [
                    {
                        "scenario": "wifi",
                        "component": "control",
                        "rmw": "rmw_a",
                        "latency_p95_ms": 10,
                        "latency_p99_ms": 12,
                        "jitter_p95_ms": 1,
                        "loss_ratio": 0.01,
                        "deadline_miss_ratio": 0.02,
                        "throughput_mbps": 1,
                        "cpu_mean": 1,
                        "memory_mean": 10,
                        "qoe_score": 0.9,
                    }
                ],
                path,
            )
            summary = load_summary(None, path)

        self.assertEqual(summary["ranking"][0]["rmw"], "rmw_a")


if __name__ == "__main__":
    unittest.main()

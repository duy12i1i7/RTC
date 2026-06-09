import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from fleetqox.comparison import (
    BaselineInput,
    compare_baselines,
    render_comparison_markdown,
    write_comparison_csv,
)
from fleetqox.ros2_perf import write_perf_records_jsonl


class ComparisonTest(unittest.TestCase):
    def test_compare_baselines_computes_deadline_delta(self) -> None:
        with TemporaryDirectory() as tmpdir:
            wifi = Path(tmpdir) / "wifi.jsonl"
            roaming = Path(tmpdir) / "roaming.jsonl"
            write_perf_records_jsonl(
                [
                    _record("wifi_loss_jitter", "control", "rmw_a", deadline=0.1),
                ],
                wifi,
            )
            write_perf_records_jsonl(
                [
                    _record("roaming_capacity_drop", "control", "rmw_a", deadline=1.0),
                ],
                roaming,
            )

            comparison = compare_baselines(
                [
                    BaselineInput("wifi", wifi),
                    BaselineInput("roaming", roaming),
                ]
            )

        self.assertEqual(len(comparison["deltas"]), 1)
        self.assertAlmostEqual(
            comparison["deltas"][0]["deadline_miss_ratio_delta"],
            0.9,
        )
        self.assertEqual(comparison["deltas"][0]["interpretation"], "deadline collapse")

    def test_render_and_write_comparison(self) -> None:
        comparison = {
            "baselines": [{"name": "a", "metrics_path": "a.jsonl", "summary_path": ""}],
            "rows": [],
            "deltas": [],
            "observations": ["No baseline rows were available."],
        }
        report = render_comparison_markdown(comparison, title="Compare")

        self.assertIn("# Compare", report)
        self.assertIn("Delta vs Reference", report)
        with TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "delta.csv"
            write_comparison_csv(comparison, path)
            self.assertIn("rank_score_delta", path.read_text(encoding="utf-8"))


def _record(
    scenario: str,
    component: str,
    rmw: str,
    *,
    deadline: float,
) -> dict[str, object]:
    return {
        "scenario": scenario,
        "component": component,
        "rmw": rmw,
        "latency_p95_ms": 20.0,
        "latency_p99_ms": 25.0,
        "jitter_p95_ms": 3.0,
        "loss_ratio": 0.01,
        "deadline_miss_ratio": deadline,
        "throughput_mbps": 1.0,
        "cpu_mean": 0.1,
        "memory_mean": 10.0,
        "qoe_score": 0.8,
    }


if __name__ == "__main__":
    unittest.main()

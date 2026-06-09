import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from fleetqox.ros2_perf import build_perf_commands, parse_perf_csv, summarize_perf_records, write_perf_records_jsonl
from fleetqox.testbed import iter_scenarios, load_manifest


class Ros2PerfTest(unittest.TestCase):
    def test_build_commands_for_t1_scenario(self) -> None:
        manifest = load_manifest("experiments/testbed_manifest.json")
        scenario = next(item for item in iter_scenarios(manifest) if item.tier == "T1")

        commands = build_perf_commands(scenario, "results_t1", executable="perf_test")

        self.assertTrue(commands)
        self.assertTrue(any(command.rmw == "rmw_fastrtps_cpp" for command in commands))
        self.assertIn("--communicator", commands[0].command)
        self.assertIn("RMW_IMPLEMENTATION", commands[0].env)

    def test_parse_perf_csv_best_effort(self) -> None:
        with TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "log.csv"
            path.write_text(
                "latency_ms,cpu_percent,samples_sent,samples_received\n"
                "1.0,10,10,9\n"
                "3.0,20,20,18\n",
                encoding="utf-8",
            )
            record = parse_perf_csv(path)

        self.assertEqual(record["rows"], 2)
        self.assertEqual(record["latency_p50_ms"], 1.0)
        self.assertEqual(record["latency_p99_ms"], 3.0)
        self.assertEqual(record["samples_lost"], 2)

    def test_parse_performance_test_csv_with_metadata(self) -> None:
        with TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "log.csv"
            path.write_text(
                "Experiment id: x\n"
                "---EXPERIMENT-START---\n"
                "T_experiment,\tT_loop,\treceived,\tsent,\tlost,\tlatency_mean (ms),\tru_maxrss,\tcpu_usage (%)\n"
                "1.0,\t1.0,\t10,\t0,\t0,\t2.5,\t100,\t3.0\n"
                "2.0,\t1.0,\t12,\t0,\t1,\t3.5,\t120,\t4.0\n",
                encoding="utf-8",
            )
            record = parse_perf_csv(path, deadline_ms=3.0)

        self.assertEqual(record["rows"], 2)
        self.assertEqual(record["samples_received"], 22)
        self.assertEqual(record["samples_lost"], 1)
        self.assertAlmostEqual(record["loss_ratio"], 1 / 23)
        self.assertEqual(record["latency_p50_ms"], 2.5)
        self.assertEqual(record["jitter_mean_ms"], 1.0)
        self.assertEqual(record["memory_mean"], 110)
        self.assertEqual(record["deadline_miss_ratio"], 13 / 23)
        self.assertFalse(record["no_samples"])

    def test_parse_zero_sample_run_marks_no_samples(self) -> None:
        with TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "log.csv"
            path.write_text(
                "T_experiment,\tT_loop,\treceived,\tsent,\tlost,\tlatency_mean (ms)\n"
                "1.0,\t1.0,\t0,\t0,\t0,\t-nan\n",
                encoding="utf-8",
            )
            record = parse_perf_csv(path)

        self.assertTrue(record["no_samples"])
        self.assertEqual(record["delivery_ratio"], 0.0)

    def test_summarize_perf_records_ranks_by_qoe(self) -> None:
        summary = summarize_perf_records(
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
                    "throughput_mbps": 1.0,
                    "cpu_mean": 2.0,
                    "memory_mean": 100.0,
                    "qoe_score": 0.9,
                },
                {
                    "scenario": "wifi",
                    "component": "control",
                    "rmw": "rmw_b",
                    "latency_p95_ms": 100,
                    "latency_p99_ms": 120,
                    "jitter_p95_ms": 10,
                    "loss_ratio": 0.2,
                    "deadline_miss_ratio": 0.3,
                    "throughput_mbps": 0.5,
                    "cpu_mean": 2.0,
                    "memory_mean": 100.0,
                    "qoe_score": 0.4,
                },
            ]
        )

        self.assertEqual(summary["ranking"][0]["rmw"], "rmw_a")

    def test_write_perf_records_jsonl(self) -> None:
        with TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "metrics.jsonl"
            write_perf_records_jsonl([{"status": "skipped", "scenario": "x"}], path)
            text = path.read_text(encoding="utf-8")

        self.assertIn('"status": "skipped"', text)


if __name__ == "__main__":
    unittest.main()

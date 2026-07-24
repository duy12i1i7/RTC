from __future__ import annotations

from pathlib import Path
import unittest

from scripts.run_omnetpp_docker_parity import (
    DEFAULT_THRESHOLDS,
    POLICIES,
    ROOT,
    _data_rate_bps,
    compare_policy_rows,
)
from scripts.generate_unified_benchmark_report import extract_metrics


def _policy_rows(*, p99_ms: float = 4.0, rx: int = 9) -> list[dict[str, object]]:
    return [
        {
            "policy": policy,
            "tx": 10,
            "rx": rx,
            "bytes": rx * 100,
            "deadline_miss_ratio": 0.1,
            "p50_ms": 2.0,
            "p99_ms": p99_ms,
            "utility": rx * 5.0,
        }
        for policy in POLICIES
    ]


class OmnetppParityRunnerTest(unittest.TestCase):
    def test_identical_policy_rows_pass_all_bounds(self) -> None:
        rows = _policy_rows()
        comparisons = compare_policy_rows(
            rows, rows, thresholds=dict(DEFAULT_THRESHOLDS)
        )
        self.assertEqual([row["status"] for row in comparisons], ["ok"] * 3)
        self.assertTrue(all(row["tx_equal"] for row in comparisons))

    def test_p99_bound_is_enforced(self) -> None:
        comparisons = compare_policy_rows(
            _policy_rows(p99_ms=4.0),
            _policy_rows(p99_ms=50.0),
            thresholds=dict(DEFAULT_THRESHOLDS),
        )
        self.assertEqual([row["status"] for row in comparisons], ["failed"] * 3)
        self.assertTrue(
            all(
                row["p99_latency_delta_ms"]
                > DEFAULT_THRESHOLDS["p99_latency_delta_ms"]
                for row in comparisons
            )
        )

    def test_missing_policy_fails_closed(self) -> None:
        comparisons = compare_policy_rows(
            _policy_rows()[:-1],
            _policy_rows(),
            thresholds=dict(DEFAULT_THRESHOLDS),
        )
        self.assertEqual(comparisons[-1]["status"], "failed")
        self.assertEqual(comparisons[-1]["reason"], "policy_missing")

    def test_utility_delta_is_relative(self) -> None:
        left = _policy_rows()
        right = _policy_rows()
        for row in right:
            row["utility"] = float(row["utility"]) * 0.95
        comparisons = compare_policy_rows(
            left, right, thresholds=dict(DEFAULT_THRESHOLDS)
        )
        self.assertTrue(
            all(abs(float(row["normalized_utility_delta"]) - 0.05) < 1e-12 for row in comparisons)
        )

    def test_data_rate_parser_uses_decimal_network_units(self) -> None:
        self.assertEqual(_data_rate_bps("54Mbps"), 54_000_000)
        self.assertEqual(_data_rate_bps("6Mbps"), 6_000_000)
        self.assertEqual(_data_rate_bps("1000000"), 1_000_000)

    def test_runtime_project_is_not_a_placeholder(self) -> None:
        directory = ROOT / "external" / "omnetpp"
        required = {
            "Dockerfile",
            "FleetQoxTraceReplay.ned",
            "TraceDrivenUdpApp.ned",
            "TraceDrivenUdpApp.h",
            "TraceDrivenUdpApp.cc",
            "omnetpp.ini",
        }
        self.assertTrue(required.issubset({path.name for path in directory.iterdir()}))
        source = (directory / "TraceDrivenUdpApp.cc").read_text(encoding="utf-8")
        topology = (directory / "FleetQoxTraceReplay.ned").read_text(
            encoding="utf-8"
        )
        dockerfile = (directory / "Dockerfile").read_text(encoding="utf-8")
        self.assertIn("socket_.sendTo", source)
        self.assertIn("socketDataArrived", source)
        self.assertIn("policy,tx,rx,bytes,deadline_miss_ratio", source)
        self.assertIn("FleetQoxPointToPointLink", topology)
        self.assertIn("backboneRouter", topology)
        self.assertIn("omnetpp-6.4", dockerfile)
        self.assertIn("inet-framework/inet", dockerfile)

    def test_runner_keeps_full_fidelity_claims_false(self) -> None:
        source = (ROOT / "scripts" / "run_omnetpp_docker_parity.py").read_text(
            encoding="utf-8"
        )
        self.assertIn('"full_tsn_mesh_parity_claim": False', source)
        self.assertIn('"high_fidelity_wireless_parity_claim": False', source)
        self.assertIn("matched_trace_seed_policy_link_profile", source)
        self.assertIn("p2p_star", source)

    def test_unified_report_extracts_runtime_parity_metrics(self) -> None:
        metrics = extract_metrics(
            {
                "runtime_case_count": 27,
                "runtime_case_pass_count": 27,
                "parity_case_pass_count": 27,
                "total_packet_rows": 72_213,
                "max_delivery_ratio_delta": 0.0184,
                "max_p99_latency_delta_ms": 1.24,
                "full_tsn_mesh_parity_claim": False,
            }
        )
        self.assertEqual(metrics["runtime_case_pass_count"], 27)
        self.assertEqual(metrics["parity_case_pass_count"], 27)
        self.assertEqual(metrics["total_packet_rows"], 72_213)
        self.assertFalse(metrics["full_tsn_mesh_parity_claim"])


if __name__ == "__main__":
    unittest.main()

from copy import deepcopy
from pathlib import Path
import unittest

from scripts.aggregate_same_hop_offered_load_sensitivity import (
    EXPECTED_SEEDS,
    EXPECTED_SYSTEMS,
    aggregate_summaries,
    payload_offered_mbit_s,
)
from scripts.generate_unified_benchmark_report import classify_path


def interval_summary(interval_ms: int) -> dict:
    rows = [
        {
            "system": system,
            "status": "ok",
            "robot_count": 16,
            "seed": seed,
            "result": {
                "publish_interval_ms": interval_ms,
                "payload_bytes": 32768,
                "payload_size_min_bytes": 32768,
                "payload_size_max_bytes": 32768,
                "payload_size_contract_ok": True,
            },
        }
        for seed in EXPECTED_SEEDS
        for system in EXPECTED_SYSTEMS
    ]
    aggregates = [
        {
            "system": system,
            "robot_count": 16,
            "ok_run_count": 3,
            "run_count": 3,
            "control_delivery_ratio_mean": 1.0,
            "state_delivery_ratio_mean": 1.0,
            "control_latency_ms_p95_mean": 10.0,
            "state_latency_ms_p95_mean": 11.0,
        }
        for system in EXPECTED_SYSTEMS
    ]
    return {
        "schema_version": "fleetrmw.same_hop_rmw_comparison.v4",
        "status": "ok",
        "image": "image",
        "profile": "roaming",
        "netem_loss_scale": 0.25,
        "samples": 5,
        "payload_bytes": 32768,
        "publish_interval_ms": interval_ms,
        "timeout_s": 25.0,
        "publisher_reliability_horizon_s": 6.0,
        "relay_scope": "rclcpp_generic_serialized_passthrough",
        "robot_counts": [16],
        "seeds": list(EXPECTED_SEEDS),
        "systems": list(EXPECTED_SYSTEMS),
        "run_count": 12,
        "ok_run_count": 12,
        "failed_run_count": 0,
        "skipped_run_count": 0,
        "reused_row_count": 0,
        "executed_row_count": 12,
        "relay_expected_count": 1920,
        "relay_payload_count": 1920,
        "payload_size_contract_ok": True,
        "serialized_relay_contract_ok": True,
        "middle_rmw_termination_republish_contract_ok": True,
        "middle_hop_processing_equivalent": True,
        "latency_comparison_allowed": True,
        "resume_configuration_validation_enabled": True,
        "aggregates": aggregates,
        "runs": rows,
    }


class SameHopOfferedLoadSensitivityTest(unittest.TestCase):
    def test_payload_offered_rate(self):
        self.assertAlmostEqual(
            payload_offered_mbit_s(
                payload_bytes=32768,
                robot_count=16,
                publish_interval_ms=2000,
            ),
            4.194304,
        )

    def test_aggregates_complete_interval_campaign(self):
        sources = [
            (Path(f"interval-{interval}.json"), interval_summary(interval))
            for interval in (50, 500, 2000)
        ]
        summary = aggregate_summaries(sources)
        self.assertEqual(summary["status"], "ok")
        self.assertEqual(summary["ok_run_count"], 36)
        self.assertEqual(summary["relay_payload_count"], 5760)
        self.assertEqual(
            summary["fully_successful_publish_interval_ms"],
            [50, 500, 2000],
        )
        self.assertTrue(summary["offered_load_sensitivity_comparison_allowed"])
        self.assertEqual(
            summary["payload_offered_rate_scope"],
            "source_publisher_application_payload_only_excludes_ros_wire_and_relay_hop",
        )
        self.assertEqual(
            classify_path(Path("offered-load.json"), summary),
            "comparison/dds-cyclone-zenoh",
        )

    def test_preserves_all_failed_overload_cell(self):
        sources = [
            (Path(f"interval-{interval}.json"), interval_summary(interval))
            for interval in (50, 500, 2000)
        ]
        overloaded = sources[0][1]
        overloaded["status"] = "failed"
        overloaded["ok_run_count"] = 0
        overloaded["failed_run_count"] = 12
        overloaded["relay_payload_count"] = 0
        for row in overloaded["runs"]:
            row["status"] = "failed"
        summary = aggregate_summaries(sources)
        self.assertEqual(summary["status"], "partial")
        self.assertEqual(summary["failed_run_count"], 12)
        self.assertEqual(
            summary["fully_successful_publish_interval_ms"],
            [500, 2000],
        )
        self.assertTrue(summary["complete_measurement_matrix_contract_ok"])
        self.assertFalse(summary["latency_distribution_comparison_allowed"])

    def test_rejects_non_interval_configuration_drift(self):
        sources = [
            (Path(f"interval-{interval}.json"), interval_summary(interval))
            for interval in (50, 500, 2000)
        ]
        mismatched = deepcopy(sources)
        mismatched[1][1]["payload_bytes"] = 4096
        with self.assertRaisesRegex(ValueError, "payload size differs"):
            aggregate_summaries(mismatched)


if __name__ == "__main__":
    unittest.main()

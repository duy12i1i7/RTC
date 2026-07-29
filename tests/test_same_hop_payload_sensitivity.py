from copy import deepcopy
from pathlib import Path
import unittest

from scripts.aggregate_same_hop_payload_sensitivity import (
    EXPECTED_SEEDS,
    EXPECTED_SYSTEMS,
    aggregate_summaries,
)
from scripts.generate_unified_benchmark_report import classify_path


def payload_summary(payload_bytes: int) -> dict:
    rows = [
        {
            "system": system,
            "status": "ok",
            "robot_count": 16,
            "seed": seed,
            "result": {
                "payload_bytes": payload_bytes,
                "payload_size_min_bytes": payload_bytes,
                "payload_size_max_bytes": payload_bytes,
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
        "payload_bytes": payload_bytes,
        "publish_interval_ms": 50,
        "timeout_s": 25.0,
        "publisher_reliability_horizon_s": 6.0,
        "relay_scope": "rclcpp_generic_serialized_passthrough",
        "robot_counts": [16],
        "seeds": list(EXPECTED_SEEDS),
        "systems": list(EXPECTED_SYSTEMS),
        "run_count": 12,
        "ok_run_count": 12,
        "reused_row_count": 0,
        "executed_row_count": 12,
        "relay_expected_count": 1920,
        "relay_payload_count": 1920,
        "payload_size_contract_ok": True,
        "serialized_relay_contract_ok": True,
        "middle_rmw_termination_republish_contract_ok": True,
        "publisher_ack_horizon_contract_ok": True,
        "middle_hop_processing_equivalent": True,
        "latency_comparison_allowed": True,
        "resume_configuration_validation_enabled": True,
        "aggregates": aggregates,
        "runs": rows,
    }


class SameHopPayloadSensitivityTest(unittest.TestCase):
    def test_aggregates_exact_payload_campaign(self):
        sources = [
            (Path(f"payload-{size}.json"), payload_summary(size))
            for size in (256, 4096, 32768)
        ]
        summary = aggregate_summaries(sources)
        self.assertEqual(summary["status"], "ok")
        self.assertEqual(summary["ok_run_count"], 36)
        self.assertEqual(summary["relay_payload_count"], 5760)
        self.assertTrue(summary["exact_payload_size_contract_ok"])
        self.assertTrue(summary["payload_sensitivity_comparison_allowed"])
        self.assertFalse(summary["latency_superiority_claim_allowed"])
        self.assertEqual(
            classify_path(Path("payload.json"), summary),
            "comparison/dds-cyclone-zenoh",
        )

    def test_rejects_payload_evidence_mismatch(self):
        sources = [
            (Path(f"payload-{size}.json"), payload_summary(size))
            for size in (256, 4096, 32768)
        ]
        mismatched = deepcopy(sources)
        mismatched[1][1]["runs"][0]["result"]["payload_size_max_bytes"] = 4095
        with self.assertRaisesRegex(ValueError, "exact-payload coverage"):
            aggregate_summaries(mismatched)

    def test_rejects_non_payload_configuration_drift(self):
        sources = [
            (Path(f"payload-{size}.json"), payload_summary(size))
            for size in (256, 4096, 32768)
        ]
        mismatched = deepcopy(sources)
        mismatched[2][1]["profile"] = "wan"
        with self.assertRaisesRegex(ValueError, "configuration differs"):
            aggregate_summaries(mismatched)

    def test_preserves_measured_delivery_failures_as_complete_campaign(self):
        sources = [
            (Path(f"payload-{size}.json"), payload_summary(size))
            for size in (256, 4096, 32768)
        ]
        sources[1][1]["status"] = "partial"
        sources[1][1]["ok_run_count"] = 11
        sources[1][1]["failed_run_count"] = 1
        sources[1][1]["runs"][0]["status"] = "failed"
        sources[1][1]["relay_payload_count"] = 1919
        summary = aggregate_summaries(sources)
        self.assertEqual(summary["status"], "partial")
        self.assertEqual(summary["ok_run_count"], 35)
        self.assertEqual(summary["failed_run_count"], 1)
        self.assertTrue(summary["complete_measurement_matrix_contract_ok"])
        self.assertTrue(summary["payload_sensitivity_comparison_allowed"])
        self.assertTrue(summary["latency_distribution_comparison_allowed"])

    def test_accepts_complete_all_failed_payload_frontier(self):
        sources = [
            (Path(f"payload-{size}.json"), payload_summary(size))
            for size in (256, 4096, 32768)
        ]
        frontier = sources[2][1]
        frontier["status"] = "failed"
        frontier["ok_run_count"] = 0
        frontier["failed_run_count"] = 12
        frontier["relay_payload_count"] = 0
        for row in frontier["runs"]:
            row["status"] = "failed"
        summary = aggregate_summaries(sources)
        self.assertEqual(summary["status"], "partial")
        self.assertEqual(summary["ok_run_count"], 24)
        self.assertEqual(summary["failed_run_count"], 12)
        self.assertTrue(summary["complete_measurement_matrix_contract_ok"])
        self.assertTrue(summary["payload_sensitivity_comparison_allowed"])
        self.assertFalse(summary["latency_distribution_comparison_allowed"])


if __name__ == "__main__":
    unittest.main()

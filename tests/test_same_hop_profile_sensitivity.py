from copy import deepcopy
from pathlib import Path
import unittest

from scripts.aggregate_same_hop_profile_sensitivity import (
    EXPECTED_PROFILES,
    EXPECTED_SYSTEMS,
    aggregate_summaries,
)
from scripts.generate_unified_benchmark_report import classify_path


def profile_summary(profile: str) -> dict:
    rows = [
        {
            "profile": profile,
            "system": system,
            "status": "ok",
        }
        for _seed in (7, 13, 29)
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
    fresh = profile != "roaming"
    return {
        "schema_version": "fleetrmw.same_hop_rmw_comparison.v4",
        "status": "ok",
        "profile": profile,
        "robot_counts": [16],
        "systems": list(EXPECTED_SYSTEMS),
        "image": "image",
        "netem_loss_scale": 0.25,
        "samples": 5,
        "publish_interval_ms": 50,
        "timeout_s": 25.0,
        "publisher_reliability_horizon_s": 6.0,
        "relay_scope": "rclcpp_generic_serialized_passthrough",
        "run_count": 12,
        "ok_run_count": 12,
        "reused_row_count": 0 if fresh else 12,
        "executed_row_count": 12 if fresh else 0,
        "relay_expected_count": 1920,
        "relay_payload_count": 1920,
        "serialized_relay_contract_ok": True,
        "middle_rmw_termination_republish_contract_ok": True,
        "publisher_ack_horizon_contract_ok": True,
        "middle_hop_processing_equivalent": True,
        "latency_comparison_allowed": True,
        "resume_configuration_validation_enabled": True,
        "aggregates": aggregates,
        "runs": rows,
    }


class SameHopProfileSensitivityTest(unittest.TestCase):
    def test_aggregates_three_matched_profiles(self):
        sources = [
            (Path(f"{profile}.json"), profile_summary(profile))
            for profile in EXPECTED_PROFILES
        ]
        summary = aggregate_summaries(sources)
        self.assertEqual(summary["status"], "ok")
        self.assertEqual(summary["ok_run_count"], 36)
        self.assertEqual(summary["relay_payload_count"], 5760)
        self.assertEqual(summary["executed_row_count"], 24)
        self.assertEqual(summary["reused_row_count"], 12)
        self.assertTrue(summary["profile_sensitivity_comparison_allowed"])
        self.assertFalse(summary["latency_superiority_claim_allowed"])
        self.assertEqual(
            classify_path(Path("profile.json"), summary),
            "comparison/dds-cyclone-zenoh",
        )

    def test_rejects_non_profile_configuration_mismatch(self):
        sources = [
            (Path(f"{profile}.json"), profile_summary(profile))
            for profile in EXPECTED_PROFILES
        ]
        mismatched = deepcopy(sources)
        mismatched[1][1]["samples"] = 6
        with self.assertRaisesRegex(ValueError, "configuration differs"):
            aggregate_summaries(mismatched)


if __name__ == "__main__":
    unittest.main()

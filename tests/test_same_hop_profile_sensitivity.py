from copy import deepcopy
from pathlib import Path
import unittest

from scripts.aggregate_same_hop_profile_sensitivity import (
    EXPECTED_PROFILES,
    EXPECTED_SYSTEMS,
    aggregate_summaries,
)
from scripts.generate_unified_benchmark_report import classify_path


def profile_summary(
    profile: str,
    robot_counts: tuple[int, ...] = (16,),
) -> dict:
    rows = [
        {
            "profile": profile,
            "system": system,
            "robot_count": robot_count,
            "seed": seed,
            "status": "ok",
        }
        for robot_count in robot_counts
        for seed in (7, 13, 29)
        for system in EXPECTED_SYSTEMS
    ]
    aggregates = [
        {
            "system": system,
            "robot_count": robot_count,
            "ok_run_count": 3,
            "run_count": 3,
            "control_delivery_ratio_mean": 1.0,
            "state_delivery_ratio_mean": 1.0,
            "control_latency_ms_p95_mean": 10.0,
            "state_latency_ms_p95_mean": 11.0,
        }
        for robot_count in robot_counts
        for system in EXPECTED_SYSTEMS
    ]
    fresh = profile != "roaming"
    run_count = len(robot_counts) * 3 * len(EXPECTED_SYSTEMS)
    return {
        "schema_version": "fleetrmw.same_hop_rmw_comparison.v4",
        "status": "ok",
        "profile": profile,
        "robot_counts": list(robot_counts),
        "systems": list(EXPECTED_SYSTEMS),
        "image": "image",
        "netem_loss_scale": 0.25,
        "samples": 5,
        "publish_interval_ms": 50,
        "timeout_s": 25.0,
        "publisher_reliability_horizon_s": 6.0,
        "relay_scope": "rclcpp_generic_serialized_passthrough",
        "run_count": run_count,
        "ok_run_count": run_count,
        "reused_row_count": 0 if fresh else run_count,
        "executed_row_count": run_count if fresh else 0,
        "relay_expected_count": sum(robot_counts) * 2 * 5 * 3 * 4,
        "relay_payload_count": sum(robot_counts) * 2 * 5 * 3 * 4,
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

    def test_rejects_row_outside_declared_seed_coverage(self):
        sources = [
            (Path(f"{profile}.json"), profile_summary(profile))
            for profile in EXPECTED_PROFILES
        ]
        sources[0][1]["runs"][0]["seed"] = 31
        with self.assertRaisesRegex(ValueError, "outside source coverage"):
            aggregate_summaries(sources)

    def test_aggregates_complete_profile_by_scale_matrix(self):
        sources = []
        for profile in EXPECTED_PROFILES:
            sources.append(
                (
                    Path(f"{profile}-8-32.json"),
                    profile_summary(profile, (8, 32)),
                )
            )
            sources.append(
                (
                    Path(f"{profile}-16.json"),
                    profile_summary(profile, (16,)),
                )
            )
        summary = aggregate_summaries(
            sources,
            expected_robot_counts=(8, 16, 32),
        )
        self.assertEqual(summary["status"], "ok")
        self.assertEqual(summary["ok_run_count"], 108)
        self.assertEqual(summary["relay_payload_count"], 20160)
        self.assertEqual(summary["executed_row_count"], 72)
        self.assertEqual(summary["reused_row_count"], 36)
        self.assertTrue(summary["profile_robot_scale_coverage_contract_ok"])


if __name__ == "__main__":
    unittest.main()

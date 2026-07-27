import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

from scripts.generate_unified_benchmark_report import summarize_artifact


ROOT = Path(__file__).resolve().parents[1]
RUNNER = ROOT / "scripts" / "run_same_hop_rmw_comparison.py"


def load_runner():
    spec = importlib.util.spec_from_file_location("same_hop_runner", RUNNER)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class SameHopRmwComparisonTest(unittest.TestCase):
    def test_runner_has_all_baselines(self):
        module = load_runner()
        self.assertEqual(
            module.DEFAULT_RMWS,
            "rmw_fastrtps_cpp,rmw_cyclonedds_cpp,rmw_zenoh_cpp",
        )

    def test_failed_resume_rows_require_explicit_rerun(self):
        module = load_runner()
        row = {
            "status": "failed",
            "reason": "",
            "result": {
                "control_expected_count": 160,
                "state_expected_count": 160,
                "control_payload_count": 159,
                "state_payload_count": 160,
                "publisher_returncode": 0,
                "subscriber_returncode": 1,
                "router_returncode": 0,
            },
        }
        self.assertTrue(
            module.should_reuse_prior_row(
                row,
                rerun_failed_rows=False,
            )
        )
        self.assertFalse(
            module.should_reuse_prior_row(
                row,
                rerun_failed_rows=True,
            )
        )

    def test_claim_boundary_matches_relay_semantics(self):
        source = RUNNER.read_text()
        self.assertIn('"comparison_design": "matched_one_middle_hop_caveated"', source)
        self.assertIn('"hop_count_matched": True', source)
        self.assertIn('"delivery_reliability_comparison_allowed": True', source)
        self.assertIn('"latency_superiority_claim_allowed": False', source)
        self.assertIn('"direct_claim_allowed": False', source)
        self.assertIn('"middle_hop_processing_equivalent": False', source)
        self.assertIn('"serialized_relay_contract_ok": serialized_relay_contract_ok', source)
        self.assertIn('"middle_payload_serialization_state_matched":', source)
        self.assertIn("RMW termination/republish", source)

    def test_runner_uses_same_profile_and_reliability_horizon(self):
        source = RUNNER.read_text()
        self.assertIn("netem_loss_scale=netem_loss_scale", source)
        self.assertIn("publisher_linger_s=6.0", source)
        self.assertIn('"publisher_reliability_horizon_s": 6.0', source)
        self.assertIn('"publisher_ack_horizon_contract_ok":', source)
        self.assertIn("--rerun-failed", source)
        self.assertIn('"rerun_failed_rows": rerun_failed_rows', source)

    def test_old_resume_rows_cannot_satisfy_serialized_relay_contract(self):
        module = load_runner()
        module.cleanup_reusable_build = lambda **_: None
        prior_rows = [
            module.normalize_row(
                {
                    "status": "ok",
                    "robot_count": 2,
                    "repetition_seed": 7,
                },
                system="rmw_fleetqox_cpp_router",
            ),
            module.normalize_row(
                {
                    "status": "ok",
                    "robot_count": 2,
                    "repetition_seed": 7,
                    "relay_scope": "rclpy_std_msgs_string_deserialize_republish",
                },
                system="rmw_fastrtps_cpp",
            ),
        ]

        summary = module.run_comparison(
            root=ROOT,
            image="unused",
            robot_counts=[2],
            seeds=[7],
            rmws=["rmw_fastrtps_cpp"],
            profile="roaming",
            netem_loss_scale=0.1,
            samples=3,
            publish_interval_ms=30,
            timeout_s=25.0,
            prior_rows=prior_rows,
        )

        self.assertEqual(summary["status"], "partial")
        self.assertFalse(summary["serialized_relay_contract_ok"])
        self.assertIsNone(summary["middle_application_deserialization"])

    def test_unified_report_classifies_and_preserves_same_hop_metrics(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            artifact = root / "same_hop_rmw_comparison_summary.json"
            artifact.write_text(
                json.dumps(
                    {
                        "schema_version": "fleetrmw.same_hop_rmw_comparison.v2",
                        "status": "partial",
                        "run_count": 36,
                        "ok_run_count": 32,
                        "failed_run_count": 4,
                        "hop_count_matched": True,
                        "source_netem_profile_matched": True,
                        "reliable_qos_matched": True,
                        "publisher_ack_wait_supported_count": 36,
                        "publisher_ack_wait_complete_count": 36,
                        "publisher_ack_horizon_contract_ok": True,
                        "relay_scope": "rclcpp_generic_serialized_passthrough",
                        "serialized_relay_contract_ok": True,
                        "middle_payload_serialization_state_matched": True,
                        "middle_application_deserialization": False,
                        "relay_expected_count": 5040,
                        "relay_payload_count": 5030,
                        "middle_hop_processing_equivalent": False,
                        "delivery_reliability_comparison_allowed": True,
                        "latency_superiority_claim_allowed": False,
                        "aggregates": [
                            {"system": "rmw_fleetqox_cpp_router"},
                            {"system": "rmw_cyclonedds_cpp"},
                        ],
                    }
                ),
                encoding="utf-8",
            )

            summary = summarize_artifact(path=artifact, root=root)

            self.assertEqual(summary["category"], "comparison/dds-cyclone-zenoh")
            self.assertEqual(summary["metrics"]["relay_payload_count"], 5030)
            self.assertTrue(summary["metrics"]["serialized_relay_contract_ok"])
            self.assertTrue(
                summary["metrics"]["middle_payload_serialization_state_matched"]
            )
            self.assertFalse(
                summary["metrics"]["middle_application_deserialization"]
            )
            self.assertTrue(
                summary["metrics"]["publisher_ack_horizon_contract_ok"]
            )
            self.assertTrue(
                summary["metrics"]["delivery_reliability_comparison_allowed"]
            )
            self.assertFalse(summary["metrics"]["latency_superiority_claim_allowed"])
            self.assertEqual(summary["metrics"]["aggregate_system_count"], 2)


if __name__ == "__main__":
    unittest.main()

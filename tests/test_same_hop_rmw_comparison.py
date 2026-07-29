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


def common_relay_result(
    *,
    system: str = "rmw_fleetqox_cpp",
    profile: str = "roaming",
    loss_scale: float = 0.1,
    samples: int = 3,
    payload_bytes: int = 0,
    publish_interval_ms: int = 30,
) -> dict:
    return {
        "status": "ok",
        "image": "unused",
        "rmw": system,
        "profile": profile,
        "netem_loss_scale": loss_scale,
        "netem_enabled": True,
        "netem_required": True,
        "samples": samples,
        "payload_bytes": payload_bytes,
        "payload_size_contract_ok": True,
        "publish_interval_ms": publish_interval_ms,
        "publisher_linger_s": 6.0,
        "fleetqox_loss_resilient_fragment_chunk_bytes": (
            1024 if system == "rmw_fleetqox_cpp" else None
        ),
        "fleetqox_reliable_max_retransmissions": (
            6 if system == "rmw_fleetqox_cpp" else None
        ),
        "robot_count": 2,
        "topic_count": 4,
        "repetition_seed": 7,
        "relay_mode": "generic_serialized",
        "relay_scope": "rclcpp_generic_serialized_passthrough",
        "middle_payload_remains_serialized": True,
        "middle_application_deserialization": False,
        "middle_rmw_termination_republish": True,
        "relay_expected_count": 12,
        "relay_payload_count": 12,
        "control_expected_count": 6,
        "state_expected_count": 6,
        "control_payload_count": 6,
        "state_payload_count": 6,
        "control_delivery_ratio": 1.0,
        "state_delivery_ratio": 1.0,
        "min_topic_delivery_ratio": 1.0,
        "publisher": {
            "ack_wait_supported": True,
            "ack_wait_complete": True,
            "unacked_topic_count": 0,
        },
    }


class SameHopRmwComparisonTest(unittest.TestCase):
    def test_runner_has_all_baselines(self):
        module = load_runner()
        self.assertEqual(
            module.DEFAULT_RMWS,
            "rmw_fastrtps_cpp,rmw_cyclonedds_cpp,rmw_zenoh_cpp",
        )

    def test_failed_resume_rows_require_explicit_rerun(self):
        module = load_runner()
        result = common_relay_result()
        result.update(
            {
                "status": "failed",
                "control_expected_count": 160,
                "state_expected_count": 160,
                "control_payload_count": 159,
                "state_payload_count": 160,
                "publisher_returncode": 0,
                "subscriber_returncode": 1,
                "router_returncode": 0,
            }
        )
        row = {
            "status": "failed",
            "reason": "",
            "result": result,
        }
        self.assertTrue(
            module.should_reuse_prior_row(
                row,
                rerun_failed_rows=False,
                image="unused",
                profile="roaming",
                netem_loss_scale=0.1,
                samples=3,
                payload_bytes=0,
                publish_interval_ms=30,
            )
        )
        self.assertFalse(
            module.should_reuse_prior_row(
                row,
                rerun_failed_rows=True,
                image="unused",
                profile="roaming",
                netem_loss_scale=0.1,
                samples=3,
                payload_bytes=0,
                publish_interval_ms=30,
            )
        )

    def test_resume_configuration_mismatch_fails_closed(self):
        module = load_runner()
        row = module.normalize_row(
            common_relay_result(),
            system="rmw_fleetqox_cpp",
        )
        expected = {
            "image": "unused",
            "profile": "roaming",
            "netem_loss_scale": 0.1,
            "samples": 3,
            "payload_bytes": 0,
            "publish_interval_ms": 30,
        }
        self.assertTrue(
            module.prior_row_matches_configuration(row, **expected)
        )
        for key, value in (
            ("image", "different"),
            ("profile", "wifi"),
            ("netem_loss_scale", 0.25),
            ("samples", 4),
            ("payload_bytes", 4096),
            ("publish_interval_ms", 31),
        ):
            mismatched = dict(expected)
            mismatched[key] = value
            self.assertFalse(
                module.prior_row_matches_configuration(row, **mismatched),
                key,
            )
        wrong_fragment = common_relay_result()
        wrong_fragment["fleetqox_loss_resilient_fragment_chunk_bytes"] = 0
        self.assertFalse(
            module.prior_row_matches_configuration(
                module.normalize_row(
                    wrong_fragment,
                    system="rmw_fleetqox_cpp",
                ),
                **expected,
            )
        )

    def test_resume_loader_uses_summary_configuration_for_legacy_rows(self):
        module = load_runner()
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "summary.json"
            result = common_relay_result()
            result.pop("publish_interval_ms")
            row = module.normalize_row(result, system="rmw_fleetqox_cpp")
            path.write_text(
                json.dumps(
                    {
                        "image": "unused",
                        "profile": "roaming",
                        "netem_loss_scale": 0.1,
                        "samples": 3,
                        "payload_bytes": 0,
                        "publish_interval_ms": 30,
                        "runs": [row],
                    }
                ),
                encoding="utf-8",
            )
            loaded = module.load_same_hop_prior_rows(path)
        self.assertEqual(len(loaded), 1)
        self.assertTrue(
            module.prior_row_matches_configuration(
                loaded[0],
                image="unused",
                profile="roaming",
                netem_loss_scale=0.1,
                samples=3,
                payload_bytes=0,
                publish_interval_ms=30,
            )
        )

    def test_metadata_only_legacy_row_does_not_require_exact_size_evidence(self):
        module = load_runner()
        module.cleanup_reusable_build = lambda **_: None
        legacy_result = common_relay_result()
        legacy_result.pop("payload_bytes")
        legacy_result.pop("payload_size_contract_ok")
        summary = module.run_comparison(
            root=ROOT,
            image="unused",
            robot_counts=[2],
            seeds=[7],
            rmws=[],
            profile="roaming",
            netem_loss_scale=0.1,
            samples=3,
            payload_bytes=0,
            publish_interval_ms=30,
            timeout_s=25.0,
            prior_rows=[
                module.normalize_row(
                    legacy_result,
                    system="rmw_fleetqox_cpp",
                )
            ],
        )
        self.assertEqual(summary["status"], "ok")
        self.assertEqual(summary["reused_row_count"], 1)
        self.assertTrue(summary["payload_size_contract_ok"])

    def test_claim_boundary_matches_relay_semantics(self):
        source = RUNNER.read_text()
        self.assertIn(
            '"comparison_design": "matched_generic_serialized_rmw_middle"',
            source,
        )
        self.assertIn('"hop_count_matched": True', source)
        self.assertIn('"delivery_reliability_comparison_allowed": True', source)
        self.assertIn('"latency_comparison_allowed": middle_processing_equivalent', source)
        self.assertIn('"latency_superiority_claim_allowed": False', source)
        self.assertIn('"direct_claim_allowed": False', source)
        self.assertIn(
            '"middle_hop_processing_equivalent": middle_processing_equivalent',
            source,
        )
        self.assertIn('"serialized_relay_contract_ok": serialized_relay_contract_ok', source)
        self.assertIn(
            '"middle_rmw_termination_republish_contract_ok":',
            source,
        )
        self.assertIn('"middle_payload_serialization_state_matched":', source)
        self.assertIn("same rclcpp generic", source)
        self.assertIn("prior_row_matches_configuration", source)
        self.assertIn('"resume_configuration_validation_enabled": True', source)
        self.assertIn(
            '"resume_configuration_mismatch_policy":',
            source,
        )

    def test_legacy_generic_relay_fields_are_strict_contract_evidence(self):
        module = load_runner()
        result = {
            "relay_scope": "rclcpp_generic_serialized_passthrough",
            "middle_payload_remains_serialized": True,
            "middle_application_deserialization": False,
            "relay": {
                "schema_version": "fleetrmw.generic_serialized_relay_probe.v1",
                "relay_scope": "rclcpp_generic_serialized_passthrough",
                "generic_subscription": True,
                "generic_publisher": True,
                "application_deserialization": False,
            },
        }
        self.assertEqual(
            module.middle_termination_republish_evidence(result),
            "strict_generic_relay_contract",
        )
        result["relay"]["generic_publisher"] = False
        self.assertIsNone(module.middle_termination_republish_evidence(result))

    def test_runner_uses_same_profile_and_reliability_horizon(self):
        source = RUNNER.read_text()
        self.assertIn("netem_loss_scale=netem_loss_scale", source)
        self.assertIn("publisher_linger_s=6.0", source)
        self.assertIn('"publisher_reliability_horizon_s": 6.0', source)
        self.assertIn('"publisher_ack_horizon_contract_ok":', source)
        self.assertIn("--rerun-failed", source)
        self.assertIn('"rerun_failed_rows": rerun_failed_rows', source)

    def test_typed_resume_row_is_rerun_through_generic_relay(self):
        module = load_runner()
        module.cleanup_reusable_build = lambda **_: None
        module.run_relay = lambda **kwargs: common_relay_result(
            system=kwargs["rmw"],
        )
        fleet_result = common_relay_result()
        typed_result = common_relay_result(system="rmw_fastrtps_cpp")
        typed_result.update(
            {
                "relay_mode": "rclpy_typed",
                "relay_scope": "rclpy_std_msgs_string_deserialize_republish",
                "middle_payload_remains_serialized": False,
                "middle_application_deserialization": True,
                "middle_rmw_termination_republish": False,
            }
        )
        prior_rows = [
            module.normalize_row(
                fleet_result,
                system="rmw_fleetqox_cpp",
            ),
            module.normalize_row(
                typed_result,
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
            payload_bytes=0,
            publish_interval_ms=30,
            timeout_s=25.0,
            prior_rows=prior_rows,
        )

        self.assertEqual(summary["status"], "ok")
        self.assertTrue(summary["serialized_relay_contract_ok"])
        self.assertEqual(summary["reused_row_count"], 1)
        self.assertEqual(summary["executed_row_count"], 1)
        self.assertEqual(summary["resume_configuration_mismatch_count"], 1)

    def test_unified_report_classifies_and_preserves_same_hop_metrics(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            artifact = root / "same_hop_rmw_comparison_summary.json"
            artifact.write_text(
                json.dumps(
                    {
                        "schema_version": "fleetrmw.same_hop_rmw_comparison.v4",
                        "status": "ok",
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
                        "middle_rmw_termination_republish_contract_ok": True,
                        "relay_expected_count": 6720,
                        "relay_payload_count": 6720,
                        "middle_hop_processing_equivalent": True,
                        "delivery_reliability_comparison_allowed": True,
                        "latency_comparison_allowed": True,
                        "latency_superiority_claim_allowed": False,
                        "aggregates": [
                            {"system": "rmw_fleetqox_cpp"},
                            {"system": "rmw_cyclonedds_cpp"},
                        ],
                    }
                ),
                encoding="utf-8",
            )

            summary = summarize_artifact(path=artifact, root=root)

            self.assertEqual(summary["category"], "comparison/dds-cyclone-zenoh")
            self.assertEqual(summary["metrics"]["relay_payload_count"], 6720)
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
            self.assertTrue(summary["metrics"]["latency_comparison_allowed"])
            self.assertTrue(summary["metrics"]["middle_hop_processing_equivalent"])
            self.assertFalse(summary["metrics"]["latency_superiority_claim_allowed"])
            self.assertEqual(summary["metrics"]["aggregate_system_count"], 2)


if __name__ == "__main__":
    unittest.main()

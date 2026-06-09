import unittest

from fleetqox.projection_identity import projection_signature_record
from fleetqox.projection_quality_gate import (
    ProjectionGatePolicy,
    ProjectionQuality,
    ProjectionQualityGate,
)


class ProjectionQualityGateTest(unittest.TestCase):
    def test_accepts_raw_equivalent_odom_projection(self) -> None:
        gate = ProjectionQualityGate()

        decision = gate.evaluate(_quality("typed_odom", "raw_equivalent_projection"))

        self.assertEqual(decision.status, "accept")
        self.assertTrue(decision.publish)
        self.assertEqual(decision.as_log_record()["contract_id"], "fcid1-test")
        self.assertEqual(decision.as_log_record()["source_sample_id"], "fsid1-test")
        self.assertTrue(decision.as_log_record()["projection_payload_present"])
        self.assertEqual(decision.as_log_record()["projection_payload_event_id"], 7)

    def test_accepts_downsampled_scan_inside_envelope(self) -> None:
        gate = ProjectionQualityGate()

        decision = gate.evaluate(
            _quality(
                "typed_scan",
                "downsampled_projection",
                projected_sample_count=60,
                source_sample_count=180,
                downsample_stride=3,
                collision_risk=0.2,
            )
        )

        self.assertEqual(decision.status, "accept")
        self.assertTrue(decision.publish)

    def test_rejects_downsampled_scan_when_collision_risk_is_high(self) -> None:
        gate = ProjectionQualityGate()

        decision = gate.evaluate(
            _quality(
                "typed_scan",
                "downsampled_projection",
                projected_sample_count=60,
                source_sample_count=180,
                downsample_stride=3,
                collision_risk=0.8,
            )
        )

        self.assertEqual(decision.status, "drop_high_risk_downsampled_projection")
        self.assertFalse(decision.publish)
        self.assertIn("collision risk", decision.reason)

    def test_rejects_downsampled_scan_with_too_few_ranges(self) -> None:
        gate = ProjectionQualityGate()

        decision = gate.evaluate(
            _quality(
                "typed_scan",
                "downsampled_projection",
                projected_sample_count=12,
                source_sample_count=180,
                downsample_stride=10,
                collision_risk=0.1,
            )
        )

        self.assertEqual(decision.status, "drop_downsampled_projection")
        self.assertFalse(decision.publish)

    def test_rejects_degraded_projection_by_default(self) -> None:
        gate = ProjectionQualityGate()

        decision = gate.evaluate(_quality("typed_scan", "degraded_projection"))

        self.assertEqual(decision.status, "drop_projection")
        self.assertFalse(decision.publish)

    def test_can_ignore_unmanaged_projection_kinds(self) -> None:
        gate = ProjectionQualityGate(ProjectionGatePolicy(allowed_projection_kinds=("typed_scan",)))

        decision = gate.evaluate(_quality("typed_odom", "raw_equivalent_projection"))

        self.assertEqual(decision.status, "ignore_projection_kind")
        self.assertFalse(decision.publish)

    def test_rejects_stale_projection(self) -> None:
        gate = ProjectionQualityGate(ProjectionGatePolicy(max_projection_age_ms=100.0))

        decision = gate.evaluate(_quality("typed_odom", "raw_equivalent_projection", age_ms=120.0))

        self.assertEqual(decision.status, "drop_stale_projection")
        self.assertFalse(decision.publish)

    def test_accepts_compact_quality_with_signature_but_without_payload(self) -> None:
        projection_payload = _projection_payload("typed_odom")
        quality = ProjectionQuality.from_payload(
            {
                "schema_version": "fleetrmw.projection_quality.v1",
                "kind": "typed_projection_quality",
                "contract_id": "fcid1-test",
                "source_sample_id": "fsid1-test",
                "event_id": 7,
                "robot_id": "robot_0000",
                "flow_id": "robot_0000:state",
                "source_topic": "/robot_0000/odom",
                "source_msg_type": "nav_msgs/msg/Odometry",
                "projection_kind": "typed_odom",
                "projection_topic": "/fleetrmw/robot_0000/local_odom",
                "projection_msg_type": "nav_msgs/msg/Odometry",
                "fidelity_class": "raw_equivalent_projection",
                "lossy": False,
                "age_ms": 20.0,
                "deadline_ms": 160.0,
                "task_criticality": 0.5,
                "collision_risk": 0.1,
                "operator_attention": 0.0,
                "projection_payload_embedded": False,
                **projection_signature_record("typed_odom", projection_payload),
            }
        )

        decision = ProjectionQualityGate().evaluate(quality)

        self.assertEqual(decision.status, "accept")
        self.assertTrue(decision.publish)
        self.assertFalse(decision.as_log_record()["projection_payload_embedded"])
        self.assertFalse(decision.as_log_record()["projection_payload_present"])
        self.assertRegex(str(decision.as_log_record()["projection_signature"]), r"^[0-9a-f]{64}$")


def _quality(
    projection_kind: str,
    fidelity_class: str,
    *,
    projected_sample_count: int | None = None,
    source_sample_count: int | None = None,
    downsample_stride: int | None = None,
    collision_risk: float = 0.1,
    age_ms: float = 20.0,
) -> ProjectionQuality:
    projection_payload = _projection_payload(projection_kind)
    return ProjectionQuality.from_payload(
        {
            "schema_version": "fleetrmw.projection_quality.v1",
            "kind": "typed_projection_quality",
            "contract_id": "fcid1-test",
            "source_sample_id": "fsid1-test",
            "event_id": 7,
            "robot_id": "robot_0000",
            "flow_id": "robot_0000:state",
            "source_topic": "/robot_0000/scan",
            "source_msg_type": "sensor_msgs/msg/LaserScan",
            "projection_kind": projection_kind,
            "projection_topic": f"/fleetrmw/robot_0000/{projection_kind}",
            "projection_msg_type": "sensor_msgs/msg/LaserScan",
            "fidelity_class": fidelity_class,
            "lossy": fidelity_class != "raw_equivalent_projection",
            "degradation_reasons": ["range_downsampled"] if fidelity_class == "downsampled_projection" else [],
            "source_sample_count": source_sample_count,
            "projected_sample_count": projected_sample_count,
            "downsample_stride": downsample_stride,
            "age_ms": age_ms,
            "deadline_ms": 160.0,
            "task_criticality": 0.5,
            "collision_risk": collision_risk,
            "operator_attention": 0.0,
            **projection_signature_record(projection_kind, projection_payload),
            "projection_payload": projection_payload,
        }
    )


def _projection_payload(projection_kind: str) -> dict[str, object]:
    base = {
        "schema_version": "fleetrmw.typed_projection.v1",
        "kind": projection_kind,
        "contract_id": "fcid1-test",
        "source_sample_id": "fsid1-test",
        "event_id": 7,
        "robot_id": "robot_0000",
        "flow_id": "robot_0000:state",
        "source_topic": "/robot_0000/scan",
        "projection_topic": f"/fleetrmw/robot_0000/{projection_kind}",
        "header": {"frame_id": "robot_0000/base_scan", "stamp": {"sec": 1, "nanosec": 2}},
    }
    if projection_kind == "typed_odom":
        return base | {
            "odometry": {
                "child_frame_id": "robot_0000",
                "pose": {
                    "position": {"x": 1.0, "y": 2.0, "z": 0.0},
                    "orientation": {"x": 0.0, "y": 0.0, "z": 0.1, "w": 0.99},
                    "covariance": [0.0] * 36,
                },
                "twist": {
                    "linear": {"x": 0.1, "y": 0.0, "z": 0.0},
                    "angular": {"x": 0.0, "y": 0.0, "z": 0.1},
                    "covariance": [0.0] * 36,
                },
            }
        }
    if projection_kind == "typed_scan":
        return base | {
            "scan": {
                "angle_min": -1.0,
                "angle_max": 1.0,
                "angle_increment": 0.1,
                "range_min": 0.12,
                "range_max": 8.0,
                "ranges": [1.0, 1.1, 1.2],
                "intensities": [],
                "source_sample_count": 6,
                "downsample_stride": 2,
            }
        }
    return base


if __name__ == "__main__":
    unittest.main()

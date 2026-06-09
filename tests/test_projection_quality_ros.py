import math
import unittest
from types import SimpleNamespace

from fleetqox.projection_identity import projection_signature_record
from fleetqox.projection_quality_ros import (
    FLEETRMW_PROJECTION_QUALITY_MSG_TYPE,
    projection_quality_message_from_payload,
    projection_quality_payload_from_message,
)


class ProjectionQualityRosTest(unittest.TestCase):
    def test_round_trips_projection_quality_message(self) -> None:
        payload = _quality_payload()

        message = projection_quality_message_from_payload(FakeProjectionQuality, payload)
        round_trip = projection_quality_payload_from_message(message)

        self.assertEqual(FLEETRMW_PROJECTION_QUALITY_MSG_TYPE, "fleetrmw_interfaces/msg/ProjectionQuality")
        self.assertTrue(message.identity.has_event_id)
        self.assertEqual(message.identity.event_id, 7)
        self.assertEqual(round_trip["event_id"], 7)
        self.assertEqual(round_trip["contract_id"], "fcid1-test")
        self.assertEqual(round_trip["source_sample_id"], "fsid1-test")
        self.assertEqual(round_trip["robot_id"], "robot_0000")
        self.assertEqual(round_trip["projection_kind"], "typed_odom")
        self.assertEqual(round_trip["projection_signature"], payload["projection_signature"])
        self.assertFalse(round_trip["projection_payload_embedded"])
        self.assertEqual(round_trip["source_sample_count"], None)
        self.assertEqual(round_trip["projected_sample_count"], None)
        self.assertEqual(round_trip["downsample_stride"], None)

    def test_unknown_float_fields_use_nan_in_ros_message(self) -> None:
        payload = _quality_payload() | {"valid_until_timestamp_ms": None}

        message = projection_quality_message_from_payload(FakeProjectionQuality, payload)

        self.assertTrue(math.isnan(message.valid_until_timestamp_ms))
        self.assertIsNone(projection_quality_payload_from_message(message)["valid_until_timestamp_ms"])


class FakeProjectionQuality:
    def __init__(self) -> None:
        self.identity = SimpleNamespace(
            schema_version="",
            contract_id="",
            source_sample_id="",
            has_event_id=False,
            event_id=0,
            robot_id="",
            flow_id="",
            source_topic="",
            projection_kind="",
            projection_topic="",
            projection_msg_type="",
            projection_signature_version="",
            projection_signature_algorithm="",
            projection_signature="",
        )
        self.schema_version = ""
        self.kind = ""
        self.source_msg_type = ""
        self.action = ""
        self.wire_mode = ""
        self.valid_until_timestamp_ms = 0.0
        self.deadline_ms = 0.0
        self.lifespan_ms = 0.0
        self.age_ms = 0.0
        self.semantic_utility = 0.0
        self.task_criticality = 0.0
        self.collision_risk = 0.0
        self.operator_attention = 0.0
        self.coordination_pressure = 0.0
        self.raw_serialized_sample_preserved = False
        self.reconstruction = ""
        self.fidelity_class = ""
        self.lossy = False
        self.degradation_reasons = []
        self.source_sample_count = -1
        self.projected_sample_count = -1
        self.downsample_stride = -1
        self.projection_payload_embedded = False


def _quality_payload() -> dict[str, object]:
    projection_payload = {
        "header": {"frame_id": "odom", "stamp": {"sec": 1, "nanosec": 2}},
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
        },
    }
    return {
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
        "action": "send",
        "wire_mode": "native",
        "valid_until_timestamp_ms": 90.0,
        "deadline_ms": 160.0,
        "lifespan_ms": 90.0,
        "age_ms": 20.0,
        "semantic_utility": 4.0,
        "task_criticality": 0.5,
        "collision_risk": 0.1,
        "operator_attention": 0.0,
        "coordination_pressure": 0.2,
        "raw_serialized_sample_preserved": False,
        "reconstruction": "typed_projection_from_semantic_payload",
        "fidelity_class": "raw_equivalent_projection",
        "lossy": False,
        "degradation_reasons": [],
        "source_sample_count": None,
        "projected_sample_count": None,
        "downsample_stride": None,
        "projection_payload_embedded": False,
        **projection_signature_record("typed_odom", projection_payload),
    }


if __name__ == "__main__":
    unittest.main()

import unittest

from fleetqox.projection_identity import projection_signature
from fleetqox.rmw_contract import (
    PUBLISHER_ID_VERSION,
    PROJECTION_QUALITY_SCHEMA_VERSION,
    QUALIFIED_PROJECTION_SCHEMA_VERSION,
    SAMPLE_CONTRACT_SCHEMA_VERSION,
    SAMPLE_ENVELOPE_SCHEMA_VERSION,
    SOURCE_SAMPLE_ID_VERSION,
    TYPED_PROJECTION_SCHEMA_VERSION,
    publisher_id_for_fields,
    projected_sample_from_sidecar_event,
    sample_envelope_for_fields,
    sample_envelope_from_payload,
    source_sample_id_for_fields,
    source_sample_id_from_semantic_payload,
    typed_projection_payload_base,
)
from fleetqox.sidecar_contract import SIDECAR_TRACE_SCHEMA_VERSION


class RmwContractTest(unittest.TestCase):
    def test_typed_projection_base_carries_delivery_boundary_metadata(self) -> None:
        event = _event(action="send", wire_mode="native")

        payload = typed_projection_payload_base(
            event,
            kind="typed_odom",
            projection_topic="/fleetrmw/robot_0000/local_odom",
        )

        self.assertEqual(payload["schema_version"], TYPED_PROJECTION_SCHEMA_VERSION)
        self.assertEqual(payload["contract_id"], "fcid1-test")
        self.assertEqual(payload["source_sample_id"], "fsid1-test")
        self.assertEqual(payload["event_id"], 7)
        self.assertEqual(payload["robot_id"], "robot_0000")
        self.assertEqual(payload["flow_id"], "robot_0000:state")
        self.assertEqual(payload["source_topic"], "/robot_0000/odom")
        self.assertEqual(payload["valid_until_timestamp_ms"], 350.0)

    def test_projected_sample_builds_quality_contract_with_stable_signature(self) -> None:
        projection_payload = _odom_projection_payload()

        contract = projected_sample_from_sidecar_event(
            event=_event(action="send", wire_mode="native"),
            semantic_payload={"msg_type": "nav_msgs/msg/Odometry"},
            projection_kind="typed_odom",
            projection_topic="/fleetrmw/robot_0000/local_odom",
            projection_msg_type="nav_msgs/msg/Odometry",
            projection_payload=projection_payload,
            include_projection_payload=False,
        )

        quality = contract.quality_payload()
        self.assertEqual(contract.contract_payload()["schema_version"], SAMPLE_CONTRACT_SCHEMA_VERSION)
        self.assertEqual(quality["schema_version"], PROJECTION_QUALITY_SCHEMA_VERSION)
        self.assertEqual(quality["contract_id"], "fcid1-test")
        self.assertEqual(quality["source_sample_id"], "fsid1-test")
        self.assertEqual(quality["fidelity_class"], "raw_equivalent_projection")
        self.assertFalse(quality["lossy"])
        self.assertEqual(quality["projection_payload_embedded"], False)
        self.assertNotIn("projection_payload", quality)
        self.assertEqual(
            quality["projection_signature"],
            projection_signature("typed_odom", projection_payload),
        )

    def test_qualified_payload_binds_sample_and_quality_without_sideband(self) -> None:
        projection_payload = _odom_projection_payload()
        contract = projected_sample_from_sidecar_event(
            event=_event(action="send", wire_mode="native"),
            semantic_payload={"msg_type": "nav_msgs/msg/Odometry"},
            projection_kind="typed_odom",
            projection_topic="/fleetrmw/robot_0000/local_odom",
            projection_msg_type="nav_msgs/msg/Odometry",
            projection_payload=projection_payload,
            include_projection_payload=False,
        )

        qualified = contract.qualified_payload(kind="qualified_odom")

        self.assertEqual(qualified["schema_version"], QUALIFIED_PROJECTION_SCHEMA_VERSION)
        self.assertEqual(qualified["sample"]["odometry"]["pose"]["position"]["x"], 1.2)
        self.assertEqual(qualified["quality"]["contract_id"], "fcid1-test")
        self.assertEqual(qualified["quality"]["source_sample_id"], "fsid1-test")
        self.assertEqual(qualified["quality"]["projection_kind"], "typed_odom")
        self.assertEqual(qualified["quality"]["projection_payload_embedded"], False)

    def test_downsampled_scan_contract_exposes_sample_counts_and_lossiness(self) -> None:
        projection_payload = _scan_projection_payload()

        contract = projected_sample_from_sidecar_event(
            event=_event(action="send", wire_mode="native"),
            semantic_payload={"msg_type": "sensor_msgs/msg/LaserScan"},
            projection_kind="typed_scan",
            projection_topic="/fleetrmw/robot_0000/local_scan",
            projection_msg_type="sensor_msgs/msg/LaserScan",
            projection_payload=projection_payload,
            include_projection_payload=False,
        )

        quality = contract.quality_payload()
        self.assertEqual(quality["fidelity_class"], "downsampled_projection")
        self.assertTrue(quality["lossy"])
        self.assertEqual(quality["source_sample_count"], 6)
        self.assertEqual(quality["projected_sample_count"], 3)
        self.assertEqual(quality["downsample_stride"], 2)
        self.assertIn("range_downsampled", quality["degradation_reasons"])

    def test_source_sample_id_derives_from_header_stamp(self) -> None:
        source_id = source_sample_id_from_semantic_payload(
            robot_id="robot_0000",
            topic="/robot_0000/odom",
            msg_type="nav_msgs/msg/Odometry",
            semantic_payload={"header": {"frame_id": "odom", "stamp": {"sec": 10, "nanosec": 20}}},
        )

        self.assertRegex(str(source_id), r"^fsid1-[0-9a-f]{32}$")
        self.assertEqual(
            source_id,
            source_sample_id_for_fields(
                robot_id="robot_0000",
                topic="/robot_0000/odom",
                msg_type="nav_msgs/msg/Odometry",
                stamp_sec=10,
                stamp_nanosec=20,
                frame_id="odom",
            ),
        )
        self.assertNotIn(SOURCE_SAMPLE_ID_VERSION, str(source_id))

    def test_source_sample_id_derives_from_publisher_gid_and_sequence_without_header(self) -> None:
        source_id = source_sample_id_from_semantic_payload(
            robot_id="robot_0000",
            topic="/robot_0000/cmd_vel",
            msg_type="geometry_msgs/msg/Twist",
            semantic_payload={
                "source_metadata": {
                    "publisher_gid": "01020304",
                    "sequence_number": 42,
                }
            },
        )

        self.assertRegex(str(source_id), r"^fsid1-[0-9a-f]{32}$")
        self.assertEqual(
            source_id,
            source_sample_id_for_fields(
                robot_id="robot_0000",
                topic="/robot_0000/cmd_vel",
                msg_type="geometry_msgs/msg/Twist",
                publisher_gid="01020304",
                sequence_number=42,
            ),
        )

    def test_sample_envelope_builds_native_publisher_and_source_identity(self) -> None:
        envelope = sample_envelope_for_fields(
            robot_id="robot_0000",
            topic="/robot_0000/cmd_vel",
            msg_type="geometry_msgs/msg/Twist",
            node_name="/controller",
            rmw_implementation="rmw_fleetrmw_cpp",
            source_sequence_number=42,
            source_timestamp_ns=123_456_789,
            received_timestamp_ns=123_456_999,
        )

        payload = envelope.as_payload()

        self.assertEqual(payload["schema_version"], SAMPLE_ENVELOPE_SCHEMA_VERSION)
        self.assertRegex(envelope.publisher_id, r"^fpub1-[0-9a-f]{32}$")
        self.assertRegex(envelope.source_sample_id, r"^fsid1-[0-9a-f]{32}$")
        self.assertNotIn(PUBLISHER_ID_VERSION, envelope.publisher_id)
        self.assertEqual(payload["source_sequence_number"], 42)
        self.assertEqual(envelope.source_metadata_payload()["publisher_id"], envelope.publisher_id)
        self.assertEqual(envelope.source_metadata_payload()["sequence_number"], 42)
        self.assertNotIn("publisher_gid", envelope.source_metadata_payload())

    def test_sample_envelope_parser_derives_missing_ids_from_payload(self) -> None:
        publisher_id = publisher_id_for_fields(
            robot_id="robot_0000",
            topic="/robot_0000/odom",
            msg_type="nav_msgs/msg/Odometry",
            node_name="/state_estimator",
        )
        envelope = sample_envelope_from_payload(
            {
                "robot_id": "robot_0000",
                "topic": "/robot_0000/odom",
                "msg_type": "nav_msgs/msg/Odometry",
                "publisher_id": publisher_id,
                "source_sequence_number": 7,
                "source_timestamp_ns": 222,
            }
        )

        self.assertIsNotNone(envelope)
        assert envelope is not None
        self.assertEqual(envelope.publisher_id, publisher_id)
        self.assertEqual(
            envelope.source_sample_id,
            source_sample_id_for_fields(
                robot_id="robot_0000",
                topic="/robot_0000/odom",
                msg_type="nav_msgs/msg/Odometry",
                publisher_id=publisher_id,
                sequence_number=7,
                source_timestamp_ns=222,
            ),
        )
        self.assertEqual(sample_envelope_from_payload({"topic": "/robot_0000/odom"}), None)

    def test_source_sample_id_prefers_nested_sample_envelope(self) -> None:
        envelope = sample_envelope_for_fields(
            robot_id="robot_0000",
            topic="/robot_0000/cmd_vel",
            msg_type="geometry_msgs/msg/Twist",
            source_sequence_number=11,
            source_timestamp_ns=333,
        )

        source_id = source_sample_id_from_semantic_payload(
            robot_id="robot_0000",
            topic="/robot_0000/cmd_vel",
            msg_type="geometry_msgs/msg/Twist",
            semantic_payload={
                "source_metadata": {"sequence_number": 999, "source_timestamp_ns": 999},
                "sample_envelope": envelope.as_payload(),
            },
        )

        self.assertEqual(source_id, envelope.source_sample_id)


def _event(*, action: str, wire_mode: str) -> dict[str, object]:
    return {
        "schema_version": SIDECAR_TRACE_SCHEMA_VERSION,
        "event_type": "packet",
        "scenario": "test",
        "policy": "fleetqox_semantic_contract_adaptive",
        "contract_id": "fcid1-test",
        "source_sample_id": "fsid1-test",
        "event_id": 7,
        "timestamp_ms": 0.0,
        "tick": 1,
        "flow_id": "robot_0000:state",
        "flow_class": "state",
        "topic": "/robot_0000/odom",
        "robot_id": "robot_0000",
        "src": "robot_0000",
        "dst": "fleet_controller",
        "action": action,
        "bytes": 128,
        "original_bytes": 96,
        "degraded": wire_mode != "native",
        "deadline_ms": 120,
        "source_deadline_ms": 120,
        "lifespan_ms": 350,
        "qos_reliability": "reliable",
        "reliability": "reliable",
        "wire_mode": wire_mode,
        "predicted_slack_ms": 12.0,
        "reason": "unit test",
        "priority": 0.9,
        "semantic_utility": 5.0,
        "age_ms": 5.0,
        "queue_depth": 1,
        "task_criticality": 0.45,
        "collision_risk": 0.2,
        "operator_attention": 0.1,
        "coordination_pressure": 0.3,
    }


def _odom_projection_payload() -> dict[str, object]:
    return {
        "schema_version": TYPED_PROJECTION_SCHEMA_VERSION,
        "kind": "typed_odom",
        "event_id": 7,
        "robot_id": "robot_0000",
        "flow_id": "robot_0000:state",
        "source_topic": "/robot_0000/odom",
        "wire_mode": "native",
        "action": "send",
        "valid_until_timestamp_ms": 350.0,
        "projection_topic": "/fleetrmw/robot_0000/local_odom",
        "header": {"frame_id": "odom", "stamp": {"sec": 1, "nanosec": 2}},
        "odometry": {
            "child_frame_id": "robot_0000",
            "pose": {
                "position": {"x": 1.2, "y": 0.3, "z": 0.0},
                "orientation": {"x": 0.0, "y": 0.0, "z": 0.1, "w": 0.99},
                "covariance": [0.0] * 36,
            },
            "twist": {
                "linear": {"x": 0.2, "y": 0.0, "z": 0.0},
                "angular": {"x": 0.0, "y": 0.0, "z": 0.1},
                "covariance": [0.0] * 36,
            },
        },
    }


def _scan_projection_payload() -> dict[str, object]:
    return {
        "schema_version": TYPED_PROJECTION_SCHEMA_VERSION,
        "kind": "typed_scan",
        "event_id": 7,
        "robot_id": "robot_0000",
        "flow_id": "robot_0000:perception",
        "source_topic": "/robot_0000/scan",
        "wire_mode": "native",
        "action": "send",
        "valid_until_timestamp_ms": 300.0,
        "projection_topic": "/fleetrmw/robot_0000/local_scan",
        "header": {"frame_id": "robot_0000/base_scan", "stamp": {"sec": 1, "nanosec": 2}},
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
        },
    }


if __name__ == "__main__":
    unittest.main()

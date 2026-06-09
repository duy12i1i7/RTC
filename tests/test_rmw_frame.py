import unittest

from fleetqox.rmw_frame import (
    DATA_FRAME_MAGIC,
    DATA_FRAME_SCHEMA_VERSION,
    data_frame_from_sidecar_event,
    decode_data_frame,
    encode_data_frame,
    frame_id_for_payload,
    sidecar_event_from_data_frame,
)


class RmwFrameTest(unittest.TestCase):
    def test_data_frame_preserves_contract_and_native_sample_envelope(self) -> None:
        frame = data_frame_from_sidecar_event(_event())

        self.assertEqual(frame["schema_version"], DATA_FRAME_SCHEMA_VERSION)
        self.assertRegex(str(frame["frame_id"]), r"^ffrm1-[0-9a-f]{32}$")
        self.assertEqual(frame["contract"]["contract_id"], "fcid1-contract")
        self.assertEqual(frame["contract"]["source_sample_id"], "fsid1-source")
        self.assertEqual(frame["sample_envelope"]["publisher_id"], "fpub1-native")
        self.assertEqual(frame["sample_envelope"]["source_sequence_number"], 42)
        self.assertEqual(frame["source_metadata"]["publisher_id"], "fpub1-native")
        self.assertEqual(frame["semantic_payload"]["msg_type"], "nav_msgs/msg/Odometry")
        self.assertEqual(frame["fleet_optimizer"]["mode"], "unicast")
        self.assertEqual(frame["qox"]["semantic_utility"], 5.0)
        self.assertEqual(frame["timing"]["send_monotonic_ns"], 987_654_321)
        self.assertEqual(frame["frame_id"], frame_id_for_payload(frame))

    def test_data_frame_codec_round_trips_with_padding(self) -> None:
        frame = data_frame_from_sidecar_event(_event())

        encoded = encode_data_frame(frame, target_size=2048)
        decoded = decode_data_frame(encoded)

        self.assertTrue(encoded.startswith(DATA_FRAME_MAGIC))
        self.assertEqual(len(encoded), 2048)
        self.assertEqual(decoded, frame)

    def test_decode_rejects_non_frame_or_wrong_schema(self) -> None:
        self.assertEqual(decode_data_frame(b'{"schema_version":"fleetrmw.sidecar.trace.v1"}'), None)
        encoded = encode_data_frame({"schema_version": "wrong"})

        self.assertEqual(decode_data_frame(encoded), None)

    def test_data_frame_reconstructs_sidecar_event_view(self) -> None:
        frame = data_frame_from_sidecar_event(_event())

        event = sidecar_event_from_data_frame(frame)

        self.assertEqual(event["schema_version"], "fleetrmw.sidecar.trace.v1")
        self.assertEqual(event["event_type"], "packet")
        self.assertEqual(event["contract_id"], "fcid1-contract")
        self.assertEqual(event["source_sample_id"], "fsid1-source")
        self.assertEqual(event["data_frame_id"], frame["frame_id"])
        self.assertEqual(event["sample_envelope"]["publisher_id"], "fpub1-native")
        self.assertEqual(event["semantic_payload"]["msg_type"], "nav_msgs/msg/Odometry")
        self.assertEqual(event["fleet_optimizer"]["selected_paths"], ["backup_5g"])
        self.assertEqual(event["semantic_utility"], 5.0)
        self.assertEqual(event["send_monotonic_ns"], 987_654_321)


def _event() -> dict[str, object]:
    return {
        "event_id": 9,
        "scenario": "frame_test",
        "policy": "fleetqox_semantic_contract_adaptive",
        "contract_id": "fcid1-contract",
        "source_sample_id": "fsid1-source",
        "sample_envelope": {
            "schema_version": "fleetrmw.sample_envelope.v1",
            "publisher_id": "fpub1-native",
            "source_sample_id": "fsid1-source",
            "robot_id": "robot_0000",
            "topic": "/robot_0000/odom",
            "msg_type": "nav_msgs/msg/Odometry",
            "source_sequence_number": 42,
            "source_timestamp_ns": 123_000,
            "received_timestamp_ns": 124_000,
        },
        "source_metadata": {
            "publisher_id": "fpub1-native",
            "sequence_number": 42,
            "source_timestamp_ns": 123_000,
        },
        "semantic_payload": {
            "msg_type": "nav_msgs/msg/Odometry",
            "header": {"stamp": {"sec": 1, "nanosec": 2}, "frame_id": "odom"},
        },
        "fleet_optimizer": {
            "schema_version": "fleetrmw.fleet_optimizer_decision.v1",
            "action": "send",
            "mode": "unicast",
            "selected_paths": ["backup_5g"],
            "allocated_bytes": 512,
            "utility_score": 8.5,
            "best_path_score": 0.8,
            "fleet_fairness_debt": 0.0,
            "reason": "test",
        },
        "src": "robot_0000",
        "dst": "fleet_controller",
        "robot_id": "robot_0000",
        "flow_id": "robot_0000:state",
        "flow_class": "state",
        "topic": "/robot_0000/odom",
        "source_msg_type": "nav_msgs/msg/Odometry",
        "action": "send",
        "wire_mode": "native",
        "reliability": "reliable",
        "qos_reliability": "reliable",
        "deadline_ms": 120,
        "lifespan_ms": 350,
        "bytes": 512,
        "original_bytes": 320,
        "timestamp_ms": 10.0,
        "tick": 3,
        "age_ms": 4.0,
        "predicted_slack_ms": 40.0,
        "send_monotonic_ns": 987_654_321,
        "semantic_utility": 5.0,
        "task_criticality": 0.45,
        "collision_risk": 0.1,
        "operator_attention": 0.0,
        "coordination_pressure": 0.2,
    }


if __name__ == "__main__":
    unittest.main()

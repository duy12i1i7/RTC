import json
import unittest

from fleetqox.rmw_frame import data_frame_from_sidecar_event, encode_data_frame
from scripts.udp_trace_receiver import _decode


class UdpTraceReceiverTest(unittest.TestCase):
    def test_decode_accepts_legacy_sidecar_json(self) -> None:
        payload = json.dumps(_event()).encode("utf-8") + b"   "

        decoded = _decode(payload)

        self.assertIsNotNone(decoded)
        assert decoded is not None
        self.assertEqual(decoded["event_id"], 3)
        self.assertEqual(decoded["send_monotonic_ns"], 1000)

    def test_decode_accepts_fleetrmw_data_frame(self) -> None:
        frame = data_frame_from_sidecar_event(_event())

        decoded = _decode(encode_data_frame(frame, target_size=2048))

        self.assertIsNotNone(decoded)
        assert decoded is not None
        self.assertEqual(decoded["event_id"], 3)
        self.assertEqual(decoded["flow_id"], "robot_0000:state")
        self.assertEqual(decoded["semantic_utility"], 4.5)
        self.assertEqual(decoded["send_monotonic_ns"], 1000)

    def test_decode_rejects_frame_without_send_timestamp(self) -> None:
        event = _event()
        del event["send_monotonic_ns"]

        self.assertEqual(_decode(encode_data_frame(data_frame_from_sidecar_event(event))), None)


def _event() -> dict[str, object]:
    return {
        "event_id": 3,
        "timestamp_ms": 10.0,
        "tick": 2,
        "policy": "fleetqox_semantic_contract_adaptive",
        "flow_id": "robot_0000:state",
        "flow_class": "state",
        "src": "robot_0000",
        "dst": "fleet_controller",
        "robot_id": "robot_0000",
        "topic": "/robot_0000/odom",
        "source_msg_type": "nav_msgs/msg/Odometry",
        "action": "send",
        "wire_mode": "native",
        "reliability": "reliable",
        "qos_reliability": "reliable",
        "bytes": 512,
        "original_bytes": 320,
        "deadline_ms": 120.0,
        "lifespan_ms": 350.0,
        "predicted_slack_ms": 50.0,
        "semantic_utility": 4.5,
        "send_monotonic_ns": 1000,
    }


if __name__ == "__main__":
    unittest.main()

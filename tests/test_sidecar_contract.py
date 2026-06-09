import unittest

from fleetqox.sidecar_contract import (
    SIDECAR_TRACE_SCHEMA_VERSION,
    event_errors,
    validate_event,
)


class SidecarContractTest(unittest.TestCase):
    def test_valid_packet_event_passes(self) -> None:
        event = _event()

        validate_event(event)
        self.assertEqual(event_errors(event), [])

    def test_rejects_packet_with_drop_action(self) -> None:
        event = _event()
        event["action"] = "drop"

        self.assertTrue(any("packet event" in error for error in event_errors(event)))

    def test_accepts_control_intent_packet(self) -> None:
        event = _event()
        event["action"] = "send_intent"
        event["wire_mode"] = "control_intent"

        self.assertEqual(event_errors(event), [])

    def test_accepts_supervisory_intent_packet(self) -> None:
        event = _event()
        event["action"] = "send_supervisory_intent"
        event["wire_mode"] = "supervisory_intent"
        event["deadline_ms"] = 260
        event["lifespan_ms"] = 260

        self.assertEqual(event_errors(event), [])


def _event() -> dict[str, object]:
    return {
        "schema_version": SIDECAR_TRACE_SCHEMA_VERSION,
        "event_type": "packet",
        "scenario": "test",
        "policy": "fleetqox_predictive",
        "timestamp_ms": 0.0,
        "flow_id": "robot_1:cmd",
        "flow_class": "control",
        "topic": "/cmd_vel",
        "robot_id": "robot_1",
        "src": "fleet_controller",
        "dst": "robot_1",
        "action": "send_compacted",
        "bytes": 52,
        "original_bytes": 96,
        "deadline_ms": 45,
        "lifespan_ms": 90,
        "qos_reliability": "reliable",
        "reliability": "best_effort_fresh",
        "wire_mode": "semantic_delta",
        "predicted_slack_ms": 25.0,
        "semantic_utility": 5.0,
    }


if __name__ == "__main__":
    unittest.main()

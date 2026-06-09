import argparse
import unittest
from unittest.mock import patch

from scripts.run_ros2_local_controller_lease import (
    flush_feedback_window as flush_local_feedback_window,
    local_controller_feedback_record,
)
from scripts.run_ros2_projection_quality_gate import (
    flush_feedback_window as flush_quality_feedback_window,
    quality_gate_feedback_record,
)


class Ros2FeedbackProducerTest(unittest.TestCase):
    def test_local_controller_feedback_tracks_command_delivery(self) -> None:
        record = {
            "event_type": "command",
            "robot_id": "robot_0001",
            "publish": True,
            "requested_command": {"linear": {"x": 0.1}},
            "now_ms": 120.0,
            "lease": {
                "event_id": 42,
                "robot_id": "robot_0001",
                "flow_id": "robot_0001:cmd",
                "action": "send_intent",
                "wire_mode": "control_intent",
                "deadline_ms": 45.0,
                "local_expires_at_ms": 180.0,
            },
        }

        feedback = local_controller_feedback_record(record)

        self.assertIsNotNone(feedback)
        assert feedback is not None
        self.assertEqual(feedback["source"], "local_controller")
        self.assertEqual(feedback["robot_id"], "robot_0001")
        self.assertEqual(feedback["flow_class"], "control")
        self.assertTrue(feedback["control_delivered"])
        self.assertEqual(feedback["control_delivery_ratio"], 1.0)
        self.assertTrue(feedback["deadline_met"])
        self.assertEqual(feedback["action"], "send_intent")
        self.assertEqual(feedback["wire_mode"], "control_intent")
        self.assertEqual(feedback["feedback_sample_count"], 1)

    def test_local_controller_ignores_plain_lease_update(self) -> None:
        record = {
            "event_type": "lease",
            "robot_id": "robot_0001",
            "publish": False,
            "requested_command": None,
            "lease": {"robot_id": "robot_0001"},
        }

        self.assertIsNone(local_controller_feedback_record(record))

    def test_quality_gate_feedback_maps_projection_to_qoe_risk(self) -> None:
        record = {
            "event_type": "qualified_projection",
            "robot_id": "robot_0001",
            "flow_id": "robot_0001:scan",
            "projection_kind": "typed_scan",
            "status": "drop_downsampled_projection",
            "publish": False,
            "age_ms": 180.0,
            "deadline_ms": 120.0,
        }

        feedback = quality_gate_feedback_record(record)

        self.assertIsNotNone(feedback)
        assert feedback is not None
        self.assertEqual(feedback["source"], "projection_quality_gate")
        self.assertEqual(feedback["flow_class"], "perception")
        self.assertEqual(feedback["qoe_risk"], 1.0)
        self.assertEqual(feedback["latency_deadline_ratio"], 1.5)
        self.assertEqual(feedback["feedback_sample_count"], 1)

    def test_quality_gate_feedback_ignores_unmanaged_projection_kind(self) -> None:
        record = {
            "robot_id": "robot_0001",
            "projection_kind": "debug_projection",
            "status": "ignore_projection_kind",
            "publish": False,
        }

        self.assertIsNone(quality_gate_feedback_record(record))

    def test_feedback_flush_batches_records(self) -> None:
        args = argparse.Namespace(
            feedback_sidecar_host="127.0.0.1",
            feedback_sidecar_port=8765,
            feedback_timeout_s=0.01,
            feedback_every_decisions=2,
        )
        records = [{"robot_id": "robot_0001"}, {"robot_id": "robot_0002"}]

        with patch(
            "scripts.run_ros2_local_controller_lease.send_robot_feedback",
            return_value={"applied": 2},
        ) as send:
            sent, failed = flush_local_feedback_window(args, records)

        self.assertEqual(sent, 2)
        self.assertEqual(failed, 0)
        self.assertEqual(records, [])
        send.assert_called_once()

    def test_quality_feedback_flush_waits_for_full_window(self) -> None:
        args = argparse.Namespace(
            feedback_sidecar_host="127.0.0.1",
            feedback_sidecar_port=8765,
            feedback_timeout_s=0.01,
            feedback_every_decisions=3,
        )
        records = [{"robot_id": "robot_0001"}]

        with patch("scripts.run_ros2_projection_quality_gate.send_robot_feedback") as send:
            sent, failed = flush_quality_feedback_window(args, records)

        self.assertEqual(sent, 0)
        self.assertEqual(failed, 0)
        self.assertEqual(records, [{"robot_id": "robot_0001"}])
        send.assert_not_called()


if __name__ == "__main__":
    unittest.main()

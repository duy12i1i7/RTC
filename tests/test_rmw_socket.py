import socket
import unittest

from fleetqox.rmw_ack import ACK_NACK_SCHEMA_VERSION
from fleetqox.rmw_frame import decode_data_frame
from fleetqox.rmw_socket import (
    FleetRmwSocketConfig,
    FleetRmwSocketListener,
    FleetRmwSocketTalker,
)
from fleetqox.rmw_transport_loop import (
    RMW_TRANSPORT_LOOP_SCHEMA_VERSION,
    FleetRmwSocketLoopConfig,
    FleetRmwSocketTransportLoop,
)
from fleetqox.ros2_shim import Ros2QoS, Ros2Sample
from scripts.run_rmw_socket_smoke import parse_robot_sequences, run_socket_smoke


class RmwSocketTest(unittest.TestCase):
    def test_udp_publish_take_returns_ack_nack(self) -> None:
        with _listener() as listener, _talker() as talker:
            sent = talker.publish(
                _sample("robot_0000", 1),
                timestamp_ms=20.0,
                tick=1,
                destination=listener.address,
            )

            received = listener.receive_once(timeout_s=1.0)
            feedback = talker.receive_feedback(timeout_s=1.0)

        self.assertIsNotNone(received)
        self.assertIsNotNone(feedback)
        assert received is not None
        assert feedback is not None
        self.assertEqual(sent["status"], "sent")
        self.assertEqual(received["status"], "taken")
        self.assertTrue(received["feedback_sent"])
        self.assertEqual(feedback["feedback"]["schema_version"], ACK_NACK_SCHEMA_VERSION)
        self.assertEqual(feedback["feedback"]["ack"]["source_sequence_number"], 1)
        self.assertEqual(
            feedback["feedback"]["ack"]["source_sample_id"],
            sent["published"]["event"]["source_sample_id"],
        )

    def test_udp_gap_feedback_reports_missing_range_and_late_sample_closes_it(self) -> None:
        with _listener() as listener, _talker() as talker:
            _round_trip(talker, listener, _sample("robot_0001", 1), tick=1)
            third = _round_trip(talker, listener, _sample("robot_0001", 3), tick=3)
            second = _round_trip(talker, listener, _sample("robot_0001", 2), tick=2)

        self.assertEqual(third["feedback"]["nack"]["missing_sequence_ranges"], [[2, 2]])
        self.assertEqual(third["feedback"]["state"]["highest_contiguous_sequence"], 1)
        self.assertEqual(second["feedback"]["nack"]["missing_sequence_ranges"], [])
        self.assertEqual(second["feedback"]["state"]["highest_contiguous_sequence"], 3)
        self.assertTrue(second["feedback"]["state"]["out_of_order"])

    def test_talker_retransmits_missing_sequence_from_nack(self) -> None:
        with _listener() as listener, _talker() as talker:
            _round_trip(talker, listener, _sample("robot_0003", 1), tick=1)
            talker.publish(
                _sample("robot_0003", 2),
                timestamp_ms=40.0,
                tick=2,
                destination=("127.0.0.1", _unused_udp_port()),
            )
            third = _round_trip(talker, listener, _sample("robot_0003", 3), tick=3)
            retransmit = talker.retransmit_from_feedback(
                third["feedback"],
                destination=listener.address,
            )
            received = listener.receive_once(timeout_s=1.0)
            late = talker.receive_feedback(timeout_s=1.0)

        self.assertEqual(third["feedback"]["nack"]["missing_sequence_ranges"], [[2, 2]])
        self.assertEqual(retransmit["status"], "retransmitted")
        self.assertEqual(retransmit["retransmitted_sequences"], [2])
        self.assertIsNotNone(received)
        self.assertIsNotNone(late)
        assert late is not None
        self.assertEqual(late["feedback"]["nack"]["missing_sequence_ranges"], [])
        self.assertEqual(late["feedback"]["state"]["highest_contiguous_sequence"], 3)
        self.assertTrue(late["feedback"]["state"]["out_of_order"])

    def test_udp_frame_preserves_source_qos_liveliness(self) -> None:
        sample = _sample(
            "robot_0002",
            1,
            qos=Ros2QoS(deadline_ms=45.0, lifespan_ms=90.0, liveliness_lease_ms=750.0),
        )
        with _listener() as listener, _talker() as talker:
            sent = talker.publish(sample, timestamp_ms=20.0, tick=1, destination=listener.address)
            received = listener.receive_once(timeout_s=1.0)
            feedback = talker.receive_feedback(timeout_s=1.0)

        self.assertIsNotNone(received)
        self.assertIsNotNone(feedback)
        decoded = decode_data_frame(sent["published"]["encoded"])
        assert decoded is not None
        delivery = decoded["delivery"]
        self.assertEqual(delivery["source_deadline_ms"], 45.0)
        self.assertEqual(delivery["source_lifespan_ms"], 90.0)
        self.assertEqual(delivery["liveliness_lease_ms"], 750.0)
        assert received is not None
        event = received["taken"]["event"]
        self.assertEqual(event["source_lifespan_ms"], 90.0)
        self.assertEqual(event["liveliness_lease_ms"], 750.0)

    def test_socket_smoke_counts_gap_and_late_sample(self) -> None:
        summary = run_socket_smoke(
            robot_count=2,
            samples_per_robot=3,
            skip_initial={("robot_0000", 2)},
        )

        self.assertEqual(summary["published"], 6)
        self.assertEqual(summary["taken"], 6)
        self.assertEqual(summary["retransmitted"], 1)
        self.assertEqual(summary["ack_nack_feedback"], 6)
        self.assertEqual(summary["missing_sequence_range_count"], 1)
        self.assertEqual(summary["late_out_of_order_count"], 1)
        self.assertEqual(summary["initial_skips"], ["robot_0000:2"])

    def test_socket_smoke_skip_every_exercises_multiple_retransmits(self) -> None:
        summary = run_socket_smoke(
            robot_count=3,
            samples_per_robot=5,
            skip_every=2,
        )

        self.assertEqual(summary["published"], 15)
        self.assertEqual(summary["taken"], 15)
        self.assertEqual(summary["retransmitted"], 6)
        self.assertEqual(summary["ack_nack_feedback"], 15)
        self.assertEqual(summary["missing_sequence_range_count"], 6)
        self.assertEqual(summary["late_out_of_order_count"], 6)
        self.assertEqual(len(summary["initial_skips"]), 6)

    def test_transport_loop_runs_persistent_multi_stream_retransmit(self) -> None:
        loop = FleetRmwSocketTransportLoop(
            FleetRmwSocketLoopConfig(robot_count=2, samples_per_robot=5, skip_every=2)
        )

        summary = loop.run()

        self.assertEqual(summary["schema_version"], RMW_TRANSPORT_LOOP_SCHEMA_VERSION)
        self.assertEqual(summary["published"], 10)
        self.assertEqual(summary["taken"], 10)
        self.assertEqual(summary["retransmitted"], 4)
        self.assertEqual(summary["missing_sequence_range_count"], 4)
        self.assertEqual(summary["late_out_of_order_count"], 4)
        self.assertEqual(len(summary["retransmit_records"]), 4)

    def test_parse_robot_sequences(self) -> None:
        self.assertEqual(parse_robot_sequences(["robot_0000:2"]), {("robot_0000", 2)})

        with self.assertRaises(ValueError):
            parse_robot_sequences(["robot_0000"])


def _round_trip(
    talker: FleetRmwSocketTalker,
    listener: FleetRmwSocketListener,
    sample: Ros2Sample,
    *,
    tick: int,
) -> dict[str, object]:
    talker.publish(sample, timestamp_ms=float(tick * 20), tick=tick, destination=listener.address)
    received = listener.receive_once(timeout_s=1.0)
    feedback = talker.receive_feedback(timeout_s=1.0)
    if received is None or feedback is None:
        raise AssertionError("socket round trip did not produce feedback")
    return {
        "received": received,
        "feedback": feedback["feedback"],
    }


def _listener() -> FleetRmwSocketListener:
    return FleetRmwSocketListener(FleetRmwSocketConfig(timeout_s=1.0))


def _talker() -> FleetRmwSocketTalker:
    return FleetRmwSocketTalker(FleetRmwSocketConfig(timeout_s=1.0))


def _sample(robot_id: str, sequence: int, *, qos: Ros2QoS | None = None) -> Ros2Sample:
    return Ros2Sample(
        topic=f"/{robot_id}/cmd_vel",
        msg_type="geometry_msgs/msg/Twist",
        robot_id=robot_id,
        qos=qos or Ros2QoS(),
        sequence_number=sequence,
        source_timestamp_ns=sequence * 1_000_000,
        semantic_payload={
            "msg_type": "geometry_msgs/msg/Twist",
            "source_sequence_number": sequence,
            "twist": {"linear": {"x": 0.1 * sequence}, "angular": {"z": 0.1}},
        },
    )


def _unused_udp_port() -> int:
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])
    finally:
        sock.close()


if __name__ == "__main__":
    unittest.main()

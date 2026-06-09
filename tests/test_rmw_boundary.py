import unittest

from fleetqox.rmw_ack import ACK_NACK_SCHEMA_VERSION
from fleetqox.rmw_boundary import (
    RMW_BOUNDARY_PUBLISH_SCHEMA_VERSION,
    RMW_BOUNDARY_TAKE_SCHEMA_VERSION,
    FleetRmwBoundary,
    FleetRmwBoundaryConfig,
)
from fleetqox.rmw_frame import DATA_FRAME_SCHEMA_VERSION, decode_data_frame
from fleetqox.ros2_shim import Ros2QoS, Ros2Sample


class RmwBoundaryTest(unittest.TestCase):
    def test_publish_assigns_native_identity_and_data_frame(self) -> None:
        boundary = FleetRmwBoundary()

        result = boundary.publish(
            Ros2Sample(
                topic="/robot_0000/cmd_vel",
                msg_type="geometry_msgs/msg/Twist",
                robot_id="robot_0000",
                sequence_number=7,
                source_timestamp_ns=7_000_000,
                semantic_payload={"msg_type": "geometry_msgs/msg/Twist"},
            ),
            timestamp_ms=140.0,
            tick=7,
        )

        self.assertEqual(result["schema_version"], RMW_BOUNDARY_PUBLISH_SCHEMA_VERSION)
        self.assertEqual(result["frame"]["schema_version"], DATA_FRAME_SCHEMA_VERSION)
        self.assertEqual(result["sample_envelope"]["source_sequence_number"], 7)
        self.assertRegex(str(result["sample_envelope"]["publisher_id"]), r"^fpub1-[0-9a-f]{32}$")
        self.assertEqual(result["event"]["source_metadata"]["source_sequence_number"], 7)
        self.assertEqual(decode_data_frame(result["encoded"]), result["frame"])

    def test_data_frame_preserves_source_qos_and_liveliness(self) -> None:
        boundary = FleetRmwBoundary()

        result = boundary.publish(
            Ros2Sample(
                topic="/robot_0000/cmd_vel",
                msg_type="geometry_msgs/msg/Twist",
                robot_id="robot_0000",
                qos=Ros2QoS(deadline_ms=45.0, lifespan_ms=90.0, liveliness_lease_ms=750.0),
                sequence_number=7,
                source_timestamp_ns=7_000_000,
            ),
            timestamp_ms=140.0,
            tick=7,
        )

        delivery = result["frame"]["delivery"]
        self.assertEqual(delivery["source_deadline_ms"], 45.0)
        self.assertEqual(delivery["source_lifespan_ms"], 90.0)
        self.assertEqual(delivery["liveliness_lease_ms"], 750.0)
        taken = boundary.take(result["encoded"])
        self.assertEqual(taken["event"]["source_lifespan_ms"], 90.0)
        self.assertEqual(taken["event"]["liveliness_lease_ms"], 750.0)

    def test_take_reconstructs_local_sample_and_ack_nack(self) -> None:
        boundary = FleetRmwBoundary()
        published = boundary.publish(
            Ros2Sample(
                topic="/robot_0001/cmd_vel",
                msg_type="geometry_msgs/msg/Twist",
                robot_id="robot_0001",
                sequence_number=1,
                source_timestamp_ns=1_000_000,
                semantic_payload={
                    "msg_type": "geometry_msgs/msg/Twist",
                    "twist": {"linear": {"x": 0.2}},
                },
            ),
            timestamp_ms=20.0,
            tick=1,
        )

        taken = boundary.take(published["encoded"])

        self.assertEqual(taken["schema_version"], RMW_BOUNDARY_TAKE_SCHEMA_VERSION)
        self.assertEqual(taken["status"], "taken")
        self.assertEqual(taken["frame_id"], published["frame"]["frame_id"])
        self.assertEqual(taken["local_sample"]["twist"]["linear"]["x"], 0.2)
        self.assertEqual(taken["ack_nack"]["schema_version"], ACK_NACK_SCHEMA_VERSION)
        self.assertEqual(taken["ack_nack"]["ack"]["source_sequence_number"], 1)
        self.assertEqual(taken["ack_nack"]["ack"]["source_timestamp_ns"], 1_000_000)
        self.assertIn("fpub1-", taken["ack_nack"]["stream_key"][-1])

    def test_take_reports_gap_and_late_sample_closes_it(self) -> None:
        boundary = FleetRmwBoundary()
        first = _publish_sequence(boundary, 1)
        third = _publish_sequence(boundary, 3)
        second = _publish_sequence(boundary, 2)

        first_ack = boundary.take(first["encoded"])["ack_nack"]
        third_ack = boundary.take(third["encoded"])["ack_nack"]
        second_ack = boundary.take(second["encoded"])["ack_nack"]

        self.assertEqual(first_ack["nack"]["missing_sequence_ranges"], [])
        self.assertEqual(third_ack["nack"]["missing_sequence_ranges"], [[2, 2]])
        self.assertEqual(third_ack["state"]["highest_contiguous_sequence"], 1)
        self.assertEqual(second_ack["nack"]["missing_sequence_ranges"], [])
        self.assertEqual(second_ack["state"]["highest_contiguous_sequence"], 3)
        self.assertTrue(second_ack["state"]["out_of_order"])

    def test_publish_allocates_monotonic_source_sequence_when_absent(self) -> None:
        boundary = FleetRmwBoundary(FleetRmwBoundaryConfig(packet_target_size=2048))

        first = boundary.publish(_sample_without_sequence(), timestamp_ms=10.0, tick=1)
        second = boundary.publish(_sample_without_sequence(), timestamp_ms=20.0, tick=2)

        self.assertEqual(first["sample_envelope"]["source_sequence_number"], 1)
        self.assertEqual(second["sample_envelope"]["source_sequence_number"], 2)
        self.assertEqual(first["sample_envelope"]["publisher_id"], second["sample_envelope"]["publisher_id"])
        self.assertEqual(len(first["encoded"]), 2048)

    def test_take_ignores_non_fleetrmw_payload(self) -> None:
        boundary = FleetRmwBoundary()

        result = boundary.take(b"not a frame")

        self.assertEqual(result["status"], "ignored")
        self.assertEqual(result["reason"], "not_fleetrmw_data_frame")


def _publish_sequence(boundary: FleetRmwBoundary, sequence: int) -> dict[str, object]:
    return boundary.publish(
        Ros2Sample(
            topic="/robot_0000/cmd_vel",
            msg_type="geometry_msgs/msg/Twist",
            robot_id="robot_0000",
            sequence_number=sequence,
            source_timestamp_ns=sequence * 1_000_000,
        ),
        timestamp_ms=float(sequence * 20),
        tick=sequence,
    )


def _sample_without_sequence() -> Ros2Sample:
    return Ros2Sample(
        topic="/robot_0002/cmd_vel",
        msg_type="geometry_msgs/msg/Twist",
        robot_id="robot_0002",
    )


if __name__ == "__main__":
    unittest.main()

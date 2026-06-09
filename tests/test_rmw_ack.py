import unittest

from fleetqox.rmw_ack import (
    ACK_NACK_SCHEMA_VERSION,
    RmwAckNackTracker,
    ack_nack_feedback_record,
    ack_nack_id_for_payload,
    source_sequence_number,
    source_stream_key,
)


class RmwAckNackTest(unittest.TestCase):
    def test_source_stream_key_prefers_publisher_identity(self) -> None:
        record = _record(1) | {
            "sample_envelope": {
                "publisher_id": "fpub1-native",
                "topic": "/robot_0000/cmd_vel",
                "source_sequence_number": 1,
            }
        }

        self.assertEqual(
            source_stream_key(record),
            ("source_stream", "robot_0000", "/robot_0000/cmd_vel", "fpub1-native"),
        )
        self.assertEqual(source_sequence_number(record), 1)

    def test_ack_nack_feedback_record_has_stable_id_and_source_identity(self) -> None:
        record = _record(4)

        feedback = ack_nack_feedback_record(
            record,
            stream=source_stream_key(record),
            missing_sequence_ranges=[(2, 3)],
            highest_contiguous_sequence=1,
            highest_observed_sequence=4,
        )

        self.assertEqual(feedback["schema_version"], ACK_NACK_SCHEMA_VERSION)
        self.assertRegex(str(feedback["ack_nack_id"]), r"^fack1-[0-9a-f]{32}$")
        self.assertEqual(feedback["ack"]["source_sequence_number"], 4)
        self.assertEqual(feedback["ack"]["source_sample_id"], "fsid1-4")
        self.assertEqual(feedback["nack"]["missing_sequence_ranges"], [[2, 3]])
        self.assertEqual(feedback["ack_nack_id"], ack_nack_id_for_payload(feedback))

    def test_tracker_reports_gap_and_closes_it_on_late_sample(self) -> None:
        tracker = RmwAckNackTracker()

        first = tracker.observe(_record(1))
        third = tracker.observe(_record(3))
        second = tracker.observe(_record(2))

        assert first is not None
        assert third is not None
        assert second is not None
        self.assertEqual(first["nack"]["missing_sequence_ranges"], [])
        self.assertEqual(first["state"]["highest_contiguous_sequence"], 1)
        self.assertEqual(third["nack"]["missing_sequence_ranges"], [[2, 2]])
        self.assertEqual(third["state"]["highest_contiguous_sequence"], 1)
        self.assertEqual(third["state"]["highest_observed_sequence"], 3)
        self.assertEqual(second["nack"]["missing_sequence_ranges"], [])
        self.assertEqual(second["state"]["highest_contiguous_sequence"], 3)
        self.assertTrue(second["state"]["out_of_order"])

    def test_tracker_reports_missing_first_sequence_when_stream_starts_late(self) -> None:
        tracker = RmwAckNackTracker()

        second = tracker.observe(_record(2))
        first = tracker.observe(_record(1))

        assert second is not None
        assert first is not None
        self.assertEqual(second["nack"]["missing_sequence_ranges"], [[1, 1]])
        self.assertEqual(second["state"]["highest_contiguous_sequence"], 0)
        self.assertEqual(second["state"]["highest_observed_sequence"], 2)
        self.assertEqual(first["nack"]["missing_sequence_ranges"], [])
        self.assertEqual(first["state"]["highest_contiguous_sequence"], 2)
        self.assertTrue(first["state"]["out_of_order"])

    def test_tracker_marks_duplicate_without_new_gap(self) -> None:
        tracker = RmwAckNackTracker()

        tracker.observe(_record(1))
        duplicate = tracker.observe(_record(1))

        assert duplicate is not None
        self.assertTrue(duplicate["state"]["duplicate"])
        self.assertEqual(duplicate["nack"]["missing_sequence_ranges"], [])

    def test_tracker_ignores_records_without_stream_or_sequence(self) -> None:
        tracker = RmwAckNackTracker()

        self.assertIsNone(tracker.observe({"robot_id": "robot_0000"}))
        self.assertIsNone(tracker.observe({"source_sequence_number": 1}))


def _record(sequence: int) -> dict[str, object]:
    return {
        "source": "egress_ack",
        "robot_id": "robot_0000",
        "flow_id": "robot_0000:cmd",
        "source_topic": "/robot_0000/cmd_vel",
        "event_id": sequence + 10,
        "source_sample_id": f"fsid1-{sequence}",
        "source_sequence_number": sequence,
        "source_timestamp_ns": 1_000 + sequence,
        "source_received_timestamp_ns": 2_000 + sequence,
    }


if __name__ == "__main__":
    unittest.main()

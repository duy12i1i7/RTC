import unittest

from scripts.run_rmw_boundary_smoke import parse_skip_take, run_smoke


class RmwBoundarySmokeTest(unittest.TestCase):
    def test_run_smoke_counts_frames_and_gap_feedback(self) -> None:
        summary = run_smoke(
            robot_count=2,
            samples_per_robot=3,
            skip_take={("robot_0000", 2)},
        )

        self.assertEqual(summary["published"], 6)
        self.assertEqual(summary["taken"], 5)
        self.assertEqual(summary["ack_nack_feedback"], 5)
        self.assertEqual(summary["missing_sequence_range_count"], 1)
        self.assertEqual(summary["skipped_takes"], ["robot_0000:2"])
        self.assertTrue(any("robot_0000" in stream for stream in summary["streams_with_gaps"]))

    def test_parse_skip_take(self) -> None:
        self.assertEqual(parse_skip_take(["robot_0000:2"]), {("robot_0000", 2)})

        with self.assertRaises(ValueError):
            parse_skip_take(["robot_0000"])


if __name__ == "__main__":
    unittest.main()

import unittest

from fleetqox.task_outcome import (
    TaskOutcomeCorrelation,
    build_task_application_outcome,
    nav2_application_outcome,
    rmf_application_outcome,
)


class TaskOutcomeTest(unittest.TestCase):
    def setUp(self) -> None:
        self.correlation = TaskOutcomeCorrelation(
            domain_id=42,
            topic="/fleetqox/tasks",
            publisher_id="task-client",
            source_sequence_number=7,
        )

    def test_nav2_success_and_cancel_keep_delivery_distinct_from_task_success(
        self,
    ) -> None:
        success = nav2_application_outcome(
            self.correlation,
            goal_status=4,
            observed_latency_ms=80.0,
            deadline_ms=100.0,
        )
        canceled = nav2_application_outcome(
            self.correlation,
            goal_status=5,
            observed_latency_ms=90.0,
            deadline_ms=100.0,
        )
        self.assertTrue(success["delivered"])
        self.assertTrue(success["deadline_met"])
        self.assertTrue(success["task_succeeded"])
        self.assertEqual(success["terminal_status"], "succeeded")
        self.assertTrue(canceled["delivered"])
        self.assertTrue(canceled["deadline_met"])
        self.assertFalse(canceled["task_succeeded"])
        self.assertEqual(canceled["terminal_status"], "canceled")

    def test_rmf_rejection_and_timeout_are_fail_closed(self) -> None:
        rejected = rmf_application_outcome(
            self.correlation,
            response_received=True,
            response_success=False,
            observed_latency_ms=10.0,
            deadline_ms=50.0,
        )
        timeout = rmf_application_outcome(
            self.correlation,
            response_received=False,
            response_success=False,
            observed_latency_ms=50.0,
            deadline_ms=50.0,
        )
        self.assertEqual(rejected["terminal_status"], "rejected")
        self.assertTrue(rejected["delivered"])
        self.assertFalse(rejected["task_succeeded"])
        self.assertEqual(timeout["terminal_status"], "timed_out")
        self.assertFalse(timeout["delivered"])
        self.assertFalse(timeout["deadline_met"])

    def test_invalid_identity_status_and_latency_are_rejected(self) -> None:
        with self.assertRaises(ValueError):
            TaskOutcomeCorrelation(-1, "/task", "publisher", 1)
        with self.assertRaises(ValueError):
            nav2_application_outcome(
                self.correlation,
                goal_status=2,
                observed_latency_ms=1.0,
                deadline_ms=2.0,
            )
        with self.assertRaises(ValueError):
            build_task_application_outcome(
                self.correlation,
                task_kind="nav2",
                terminal_status="aborted",
                observed_latency_ms=float("nan"),
                deadline_ms=2.0,
            )
        with self.assertRaises(ValueError):
            build_task_application_outcome(
                self.correlation,
                task_kind="rmf",
                terminal_status="rejected",
                observed_latency_ms=2.0,
                deadline_ms=3.0,
                result_received=False,
            )


if __name__ == "__main__":
    unittest.main()

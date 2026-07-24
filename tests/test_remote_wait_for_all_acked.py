import json
from pathlib import Path
import unittest

from scripts.run_rmw_docker_remote_wait_for_all_acked_probe import (
    PROBE_SCHEMA_VERSION,
    publisher_ok,
    subscriber_ok,
)


ROOT = Path(__file__).resolve().parents[1]
ARTIFACT = (
    ROOT
    / "results_rmw_socket"
    / "docker_remote_wait_for_all_acked_probe_summary.json"
)


class RemoteWaitForAllAckedTest(unittest.TestCase):
    def test_validators_reject_partial_ack_as_completion(self) -> None:
        publisher = {
            "schema_version": PROBE_SCHEMA_VERSION,
            "mode": "publisher",
            "status": "ok",
            "remote_two_reader_ack_snapshot_claim": True,
            "matched_subscription_count": 2,
            "empty_wait_ok": True,
            "published": True,
            "partial_ack_timeout": True,
            "partial_wait_elapsed_ms": 200,
            "partial_expected_ack_count": 2,
            "partial_observed_ack_count": 1,
            "all_acked_wait_ok": True,
            "completed_expected_ack_count": 2,
            "completed_observed_ack_count": 2,
            "zero_timeout_after_ack_ok": True,
            "clean_teardown": True,
        }
        subscriber = {
            "schema_version": PROBE_SCHEMA_VERSION,
            "mode": "subscriber",
            "subscriber_index": 1,
            "status": "ok",
            "sample_taken": True,
            "payload_ok": True,
            "clean_teardown": True,
        }
        self.assertTrue(publisher_ok(publisher))
        self.assertTrue(subscriber_ok(subscriber, 1))
        publisher["partial_ack_timeout"] = False
        self.assertFalse(publisher_ok(publisher))
        publisher["partial_ack_timeout"] = True
        publisher["completed_observed_ack_count"] = 1
        self.assertFalse(publisher_ok(publisher))

    def test_canonical_remote_four_container_artifact_passes_five_runs(self) -> None:
        self.assertTrue(ARTIFACT.is_file())
        summary = json.loads(ARTIFACT.read_text(encoding="utf-8"))
        self.assertEqual(summary["status"], "ok")
        self.assertEqual(summary["run_count"], 5)
        self.assertEqual(summary["successful_runs"], 5)
        self.assertEqual(summary["container_count_per_run"], 4)
        self.assertTrue(summary["real_udp_router"])
        self.assertTrue(summary["remote_two_reader_ack_snapshot_claim"])
        self.assertTrue(summary["partial_ack_never_misreported_complete"])
        self.assertTrue(summary["all_remote_subscribers_acknowledged"])
        self.assertTrue(summary["clean_teardown"])
        for run in summary["runs"]:
            self.assertEqual(run["status"], "ok")
            self.assertTrue(publisher_ok(run["publisher"]))
            self.assertTrue(subscriber_ok(run["subscriber_one"], 1))
            self.assertTrue(subscriber_ok(run["subscriber_two"], 2))
            self.assertGreaterEqual(run["router"]["ack_nack_frames"], 2)
            self.assertGreaterEqual(run["router"]["ack_nack_forwarded"], 2)


if __name__ == "__main__":
    unittest.main()

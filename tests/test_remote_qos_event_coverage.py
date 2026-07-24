import json
from pathlib import Path
import tempfile
import unittest

from scripts.summarize_remote_qos_event_coverage import EVENT_TYPES, summarize


class RemoteQosEventCoverageTest(unittest.TestCase):
    def write_sources(self, root: Path) -> None:
        graph_run = {
            "status": "ok",
            "observer": {
                "matched_ok": True,
                "qos_ok": True,
                "type_ok": True,
                "liveliness_ok": True,
                "publication_callback_events": 2,
                "subscription_callback_events": 2,
                "liveliness_callback_events": 2,
            },
        }
        graph = {
            "schema_version": "fleetrmw.docker_remote_event_probe.v1",
            "status": "ok",
            "run_count": 5,
            "ok_run_count": 5,
            "netem_applied": True,
            "real_udp_multicontainer": True,
            "remote_matched_event_production": True,
            "remote_qos_event_production": True,
            "remote_type_event_production": True,
            "remote_liveliness_event_production": True,
            "runs": [graph_run for _ in range(5)],
        }
        manual_run = {
            "status": "ok",
            "advertiser": {
                "remote_publisher_liveliness_lost_event_claim": True,
                "initial_lost_not_ready": True,
                "first_lost_taken": True,
                "second_lost_taken": True,
                "lost_event_cleared": True,
                "lost_callback_events": 2,
            },
        }
        manual = {
            "schema_version": "fleetrmw.docker_remote_manual_liveliness_probe.v1",
            "status": "ok",
            "run_count": 5,
            "ok_run_count": 5,
            "netem_applied": True,
            "real_udp_multicontainer": True,
            "remote_publisher_liveliness_lost_event_claim": True,
            "runs": [manual_run for _ in range(5)],
        }
        deadline_endpoint = {
            "status": "ok",
            "initial_not_ready": True,
            "cleared_not_ready": True,
            "callback_events": 1,
            "total_count": 1,
        }
        deadline_run = {
            "status": "ok",
            "advertiser": deadline_endpoint,
            "observer": deadline_endpoint,
        }
        deadline = {
            "schema_version": "fleetrmw.docker_remote_deadline_event_probe.v1",
            "status": "ok",
            "run_count": 5,
            "ok_run_count": 5,
            "netem_applied": True,
            "real_udp_multicontainer": True,
            "remote_offered_deadline_missed_event_claim": True,
            "remote_requested_deadline_missed_event_claim": True,
            "remote_deadline_missed_event_repeated_claim": True,
            "runs": [deadline_run for _ in range(5)],
        }
        message_run = {
            "status": "ok",
            "subscriber": {
                "message_lost_wait_ready": True,
                "message_lost_taken": True,
                "message_lost_callback_events": 1,
                "message_lost_total_count": 1,
            },
        }
        message = {
            "schema_version": "fleetrmw.docker_message_lost_interprocess_probe.v1",
            "status": "ok",
            "run_count": 5,
            "ok_run_count": 5,
            "netem_applied": True,
            "remote_message_lost_waitable_claim": True,
            "repeated_remote_message_lost_claim": True,
            "runs": [message_run for _ in range(5)],
        }
        artifacts = {
            "docker_remote_event_probe_summary.json": graph,
            "docker_remote_manual_liveliness_probe_summary.json": manual,
            "docker_remote_deadline_event_probe_summary.json": deadline,
            "docker_message_lost_interprocess_probe_summary.json": message,
        }
        for name, data in artifacts.items():
            (root / name).write_text(json.dumps(data), encoding="utf-8")

    def test_all_eleven_jazzy_event_types_are_covered(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.write_sources(root)
            summary = summarize(root)
            self.assertEqual(summary["status"], "ok")
            self.assertEqual(summary["event_type_count"], 11)
            self.assertEqual(summary["event_types_covered"], EVENT_TYPES)
            self.assertEqual(summary["component_execution_count"], 20)
            self.assertTrue(summary["remote_all_jazzy_event_types_path_claim"])
            self.assertTrue(summary["remote_event_wait_take_callback_coverage_claim"])
            self.assertFalse(summary["full_dds_event_semantics_covered"])

    def test_missing_callback_fails_only_affected_event_family(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.write_sources(root)
            path = root / "docker_message_lost_interprocess_probe_summary.json"
            data = json.loads(path.read_text(encoding="utf-8"))
            data["runs"][0]["subscriber"]["message_lost_callback_events"] = 0
            path.write_text(json.dumps(data), encoding="utf-8")
            summary = summarize(root)
            self.assertEqual(summary["status"], "failed")
            self.assertEqual(len(summary["event_types_covered"]), 10)
            self.assertFalse(
                summary["event_coverage"]["RMW_EVENT_MESSAGE_LOST"]["covered"]
            )


if __name__ == "__main__":
    unittest.main()

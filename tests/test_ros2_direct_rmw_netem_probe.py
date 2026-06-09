import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from scripts.run_ros2_direct_rmw_netem_probe import (
    SCHEMA_VERSION,
    netem_status_ok,
    parse_last_json,
    ros_command,
    topic_specs_for_robot_count,
    write_probe_scripts,
)
from scripts.run_ros2_direct_rmw_netem_matrix import (
    parse_csv,
    render_markdown,
    row_from_probe,
    summarize_rows,
)


class Ros2DirectRmwNetemProbeTest(unittest.TestCase):
    def test_ros_command_sets_rmw_and_domain(self) -> None:
        command = ros_command(
            rmw="rmw_fastrtps_cpp",
            domain_id=123,
            python_path="/work/probe.py",
        )

        self.assertIn("source /opt/ros/jazzy/setup.bash", command)
        self.assertIn("RMW_IMPLEMENTATION=rmw_fastrtps_cpp", command)
        self.assertIn("ROS_DOMAIN_ID=123", command)
        self.assertIn("python3 /work/probe.py", command)

    def test_write_probe_scripts_injects_runtime_parameters(self) -> None:
        with TemporaryDirectory() as tmpdir:
            subscriber = Path(tmpdir) / "subscriber.py"
            publisher = Path(tmpdir) / "publisher.py"

            write_probe_scripts(
                subscriber_script=subscriber,
                publisher_script=publisher,
                samples=5,
                publish_interval_ms=250,
                timeout_s=7.5,
            )

            self.assertIn("SAMPLES = 5", subscriber.read_text())
            self.assertIn("TIMEOUT_S = 7.5", subscriber.read_text())
            self.assertIn("PUBLISH_INTERVAL_S = 0.25", publisher.read_text())

    def test_topic_specs_keep_legacy_default_and_scale_by_robot(self) -> None:
        legacy = topic_specs_for_robot_count(1)
        scaled = topic_specs_for_robot_count(3)

        self.assertEqual([spec["topic"] for spec in legacy], ["/robot_0000/cmd_vel", "/robot_0001/odom"])
        self.assertEqual(len(scaled), 6)
        self.assertIn({"topic": "/robot_0002/cmd_vel", "kind": "control", "flow": "robot_0002/cmd_vel"}, scaled)
        self.assertIn({"topic": "/robot_0002/odom", "kind": "state", "flow": "robot_0002/odom"}, scaled)

    def test_netem_status_respects_required_flag(self) -> None:
        self.assertTrue(netem_status_ok({}, enabled=False, required=True))
        self.assertFalse(netem_status_ok({}, enabled=True, required=True))
        self.assertFalse(
            netem_status_ok({"direct_pub": {"status": "missing_tc"}}, enabled=True, required=True)
        )
        self.assertTrue(
            netem_status_ok({"direct_pub": {"status": "applied"}}, enabled=True, required=True)
        )
        self.assertTrue(
            netem_status_ok({"direct_pub": {"status": "missing_tc"}}, enabled=True, required=False)
        )

    def test_parse_last_json_skips_log_noise(self) -> None:
        parsed = parse_last_json("noise\n" + json.dumps({"schema_version": SCHEMA_VERSION, "status": "ok"}))

        self.assertEqual(parsed["schema_version"], SCHEMA_VERSION)
        self.assertEqual(parsed["status"], "ok")

    def test_matrix_summary_separates_ok_skipped_and_failed(self) -> None:
        rows = [
            row_from_probe(_probe("rmw_fastrtps_cpp", "wifi", "ok"), seed=7),
            row_from_probe(_probe("rmw_cyclonedds_cpp", "wifi", "skipped"), seed=7),
            row_from_probe(_probe("rmw_zenoh_cpp", "wifi", "failed"), seed=7),
        ]
        summary = summarize_rows(rows)
        markdown = render_markdown(
            {
                "status": summary["status"],
                "image": "localhost/fleetrmw/rmw-netem:jazzy",
                "rmws": ["rmw_fastrtps_cpp", "rmw_cyclonedds_cpp", "rmw_zenoh_cpp"],
                "profiles": ["wifi"],
                "seeds": [7],
                "netem_loss_scale": 0.1,
                "netem_required": True,
                "summary": summary,
            }
        )

        self.assertEqual(summary["status"], "partial")
        self.assertEqual(summary["ok_run_count"], 1)
        self.assertEqual(summary["skipped_run_count"], 1)
        self.assertEqual(summary["failed_run_count"], 1)
        self.assertEqual(rows[2]["reason"], "delivery_failed:missing_control_state")
        self.assertIn("ROS 2 Direct RMW Netem Matrix V1", markdown)
        self.assertIn("1/0/0", markdown)

    def test_parse_csv_deduplicates_values(self) -> None:
        self.assertEqual(parse_csv("a,b,a", "--rmws"), ["a", "b"])
        with self.assertRaises(SystemExit):
            parse_csv("", "--rmws")


def _probe(rmw: str, profile: str, status: str) -> dict[str, object]:
    return {
        "status": status,
        "reason": "rmw_unavailable" if status == "skipped" else "",
        "rmw": rmw,
        "profile": profile,
        "netem_status": {"direct_pub": {"status": "applied"}} if status != "skipped" else {},
        "control_payload_count": 3 if status == "ok" else 0,
        "state_payload_count": 3 if status == "ok" else 0,
        "control_delivery_ratio": 1.0 if status == "ok" else 0.0,
        "state_delivery_ratio": 1.0 if status == "ok" else 0.0,
        "control_latency_ms_mean": 10.0 if status == "ok" else 0.0,
        "state_latency_ms_mean": 11.0 if status == "ok" else 0.0,
        "control_latency_ms_p95": 15.0 if status == "ok" else 0.0,
        "state_latency_ms_p95": 16.0 if status == "ok" else 0.0,
        "rmw_probe": {"available": status != "skipped"},
    }


if __name__ == "__main__":
    unittest.main()

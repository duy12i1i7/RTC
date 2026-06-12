"""Run ROS 2 CLI pub/echo message coverage against rmw_fleetqox_cpp."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import subprocess
from typing import Any


SCHEMA_VERSION = "fleetrmw.rmw_ros2_cli_message_matrix.v1"
DEFAULT_IMAGE = "ros:jazzy-ros-base"


CASES: list[dict[str, Any]] = [
    {
        "name": "std_msgs_string",
        "topic": "/fleetqox/matrix_string",
        "type": "std_msgs/msg/String",
        "yaml": "{data: fleetqox matrix string}",
        "expected": ["data: fleetqox matrix string"],
    },
    {
        "name": "builtin_interfaces_time",
        "topic": "/fleetqox/matrix_time",
        "type": "builtin_interfaces/msg/Time",
        "yaml": "{sec: 42, nanosec: 123456789}",
        "expected": ["sec: 42", "nanosec: 123456789"],
    },
    {
        "name": "builtin_interfaces_duration",
        "topic": "/fleetqox/matrix_duration",
        "type": "builtin_interfaces/msg/Duration",
        "yaml": "{sec: -3, nanosec: 250000000}",
        "expected": ["sec: -3", "nanosec: 250000000"],
    },
    {
        "name": "geometry_msgs_twist",
        "topic": "/fleetqox/matrix_twist",
        "type": "geometry_msgs/msg/Twist",
        "yaml": "{linear: {x: 0.25, y: 0.0, z: 0.0}, angular: {x: 0.0, y: 0.0, z: -0.5}}",
        "expected": ["linear:", "x: 0.25", "angular:", "z: -0.5"],
    },
    {
        "name": "geometry_msgs_pose_stamped",
        "topic": "/fleetqox/matrix_pose_stamped",
        "type": "geometry_msgs/msg/PoseStamped",
        "yaml": (
            "{header: {stamp: {sec: 5, nanosec: 6}, frame_id: map}, "
            "pose: {position: {x: 1.5, y: -2.0, z: 0.25}, "
            "orientation: {x: 0.0, y: 0.0, z: 0.707, w: 0.707}}}"
        ),
        "expected": ["frame_id: map", "sec: 5", "x: 1.5", "y: -2.0", "w: 0.707"],
    },
    {
        "name": "sensor_msgs_laserscan",
        "topic": "/fleetqox/matrix_scan",
        "type": "sensor_msgs/msg/LaserScan",
        "yaml": (
            "{header: {frame_id: laser}, angle_min: 0.0, angle_max: 1.0, "
            "angle_increment: 0.5, time_increment: 0.0, scan_time: 0.1, "
            "range_min: 0.05, range_max: 10.0, ranges: [1.0, 2.0, 3.0], "
            "intensities: [10.0, 20.0, 30.0]}"
        ),
        "expected": ["frame_id: laser", "ranges:", "- 1.0", "intensities:", "- 10.0"],
    },
    {
        "name": "nav_msgs_odometry",
        "topic": "/fleetqox/matrix_odom",
        "type": "nav_msgs/msg/Odometry",
        "yaml": (
            "{header: {frame_id: odom}, child_frame_id: base_link, "
            "pose: {pose: {position: {x: 1.0, y: 2.0, z: 0.0}, orientation: {x: 0.0, y: 0.0, z: 0.0, w: 1.0}}, "
            "covariance: [0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, "
            "0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, "
            "0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0]}, "
            "twist: {twist: {linear: {x: 0.1, y: 0.0, z: 0.0}, angular: {x: 0.0, y: 0.0, z: 0.2}}, "
            "covariance: [0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, "
            "0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, "
            "0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0]}}"
        ),
        "expected": ["frame_id: odom", "child_frame_id: base_link", "position:", "x: 1.0", "angular:", "z: 0.2"],
    },
    {
        "name": "nav_msgs_path",
        "topic": "/fleetqox/matrix_path",
        "type": "nav_msgs/msg/Path",
        "yaml": (
            "{header: {stamp: {sec: 8, nanosec: 9}, frame_id: map}, poses: ["
            "{header: {frame_id: map}, pose: {position: {x: 1.0, y: 2.0, z: 0.0}, "
            "orientation: {x: 0.0, y: 0.0, z: 0.0, w: 1.0}}}, "
            "{header: {frame_id: map}, pose: {position: {x: 3.0, y: 4.0, z: 0.0}, "
            "orientation: {x: 0.0, y: 0.0, z: 0.0, w: 1.0}}}]}"
        ),
        "expected": ["frame_id: map", "poses:", "x: 1.0", "y: 4.0", "w: 1.0"],
    },
]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--image", default=DEFAULT_IMAGE)
    parser.add_argument("--summary-json", default="results_rmw_socket/docker_ros2_cli_message_matrix_summary.json")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    root = Path(__file__).resolve().parents[1]
    summary = run_matrix(root=root, image=args.image)
    summary_path = root / args.summary_json
    summary_path.parent.mkdir(parents=True, exist_ok=True)
    summary_path.write_text(json.dumps(summary, sort_keys=True) + "\n", encoding="utf-8")

    if args.json:
        print(json.dumps(summary, sort_keys=True))
    else:
        print("fleetrmw-ros2-cli-message-matrix")
        print(f"  status: {summary['status']}")
        print(f"  passed: {summary['passed']}/{summary['case_count']}")
    return 0 if summary["status"] == "ok" else 1


def run_matrix(*, root: Path, image: str) -> dict[str, Any]:
    command = """
source /opt/ros/jazzy/setup.bash
rm -rf /tmp/fleetrmw_build /tmp/fleetrmw_install /tmp/fleetrmw_log
colcon --log-base /tmp/fleetrmw_log build \
  --base-paths ros2_ws/src \
  --packages-select fleetrmw_interfaces rmw_fleetqox_cpp \
  --build-base /tmp/fleetrmw_build \
  --install-base /tmp/fleetrmw_install \
  --cmake-args -DCMAKE_BUILD_TYPE=Release >/tmp/fleetrmw_build.log 2>&1
build_ret=$?
if [ "$build_ret" -ne 0 ]; then
  cat /tmp/fleetrmw_build.log >&2
  exit "$build_ret"
fi
source /tmp/fleetrmw_install/setup.bash
export RMW_IMPLEMENTATION=rmw_fleetqox_cpp
python3 - <<'PY'
import json
import os
import subprocess
import time

cases = __CASES_JSON__
base_port = 48260
results = []
for index, case in enumerate(cases):
    bind = f"127.0.0.1:{base_port + index}"
    echo_env = os.environ.copy()
    echo_env["FLEETQOX_RMW_BIND"] = bind
    pub_env = os.environ.copy()
    pub_env["FLEETQOX_RMW_PEERS"] = bind
    echo_cmd = [
        "ros2", "topic", "echo", "--no-daemon", "--once", "--timeout", "8",
        case["topic"], case["type"],
    ]
    pub_cmd = [
        "ros2", "topic", "pub", "--times", "3", "--rate", "5",
        "--wait-matching-subscriptions", "0",
        case["topic"], case["type"], case["yaml"],
    ]
    echo = subprocess.Popen(
        echo_cmd,
        env=echo_env,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    time.sleep(0.7)
    pub = subprocess.run(
        pub_cmd,
        env=pub_env,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    echo_stdout, echo_stderr = echo.communicate()
    matched = all(expected in echo_stdout for expected in case["expected"])
    ok = (
        echo.returncode == 0 and
        pub.returncode == 0 and
        echo_stderr == "" and
        pub.stderr == "" and
        matched
    )
    results.append({
        "name": case["name"],
        "topic": case["topic"],
        "type": case["type"],
        "status": "ok" if ok else "failed",
        "expected_matched": matched,
        "echo_returncode": echo.returncode,
        "pub_returncode": pub.returncode,
        "echo_stdout": echo_stdout,
        "echo_stderr": echo_stderr,
        "pub_stdout": pub.stdout,
        "pub_stderr": pub.stderr,
    })
passed = sum(1 for result in results if result["status"] == "ok")
summary = {
    "schema_version": "__SCHEMA_VERSION__",
    "status": "ok" if passed == len(results) else "failed",
    "case_count": len(results),
    "passed": passed,
    "cases": results,
}
print(json.dumps(summary, sort_keys=True))
PY
"""
    command = command.replace("__CASES_JSON__", json.dumps(CASES))
    command = command.replace("__SCHEMA_VERSION__", SCHEMA_VERSION)
    result = subprocess.run(
        [
            "docker", "run", "--rm",
            "--entrypoint", "bash",
            "-v", f"{root}:/work",
            "-w", "/work",
            image,
            "-lc", command,
        ],
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    if result.returncode != 0:
        return {
            "schema_version": SCHEMA_VERSION,
            "status": "failed",
            "docker_returncode": result.returncode,
            "docker_stdout": result.stdout,
            "docker_stderr": result.stderr,
        }
    lines = [line for line in result.stdout.splitlines() if line.strip().startswith("{")]
    if not lines:
        return {
            "schema_version": SCHEMA_VERSION,
            "status": "failed",
            "docker_returncode": result.returncode,
            "docker_stdout": result.stdout,
            "docker_stderr": result.stderr,
        }
    summary = json.loads(lines[-1])
    summary["docker_returncode"] = result.returncode
    summary["docker_stderr"] = result.stderr
    return summary


if __name__ == "__main__":
    raise SystemExit(main())

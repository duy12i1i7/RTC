"""Run a Docker rclpy.action smoke probe against rmw_fleetqox_cpp."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import subprocess
from typing import Any


SCHEMA_VERSION = "fleetrmw.rmw_docker_rclpy_action_probe.v1"
DEFAULT_IMAGE = "ros:jazzy-ros-base"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--image", default=DEFAULT_IMAGE)
    parser.add_argument(
        "--summary-json",
        default="results_rmw_socket/docker_rmw_rclpy_action_probe_summary.json",
    )
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    root = Path(__file__).resolve().parents[1]
    summary = run_probe(root=root, image=args.image)
    summary_path = root / args.summary_json
    summary_path.parent.mkdir(parents=True, exist_ok=True)
    summary_path.write_text(json.dumps(summary, sort_keys=True) + "\n", encoding="utf-8")

    if args.json:
        print(json.dumps(summary, sort_keys=True))
    else:
        print("fleetrmw-rclpy-action-probe")
        print(f"  status: {summary['status']}")
        print(f"  available: {summary.get('probe', {}).get('available')}")
        print(f"  result_status: {summary.get('probe', {}).get('result_status')}")
    return 0 if summary["status"] == "ok" else 1


def run_probe(*, root: Path, image: str) -> dict[str, Any]:
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
python3 - <<'PY' > /tmp/fleetrmw_rclpy_action_probe.out 2> /tmp/fleetrmw_rclpy_action_probe.err
import json
import time
import traceback

import rclpy
from rclpy.action import ActionClient, ActionServer
from rclpy.executors import MultiThreadedExecutor
from tf2_msgs.action import LookupTransform


def spin_until(executor, predicate, timeout_sec):
    deadline = time.time() + timeout_sec
    while time.time() < deadline:
        executor.spin_once(timeout_sec=0.05)
        if predicate():
            return True
    return predicate()


summary = {
    "schema_version": "fleetrmw.rclpy_action_probe.v1",
    "status": "pending",
    "action_name": "/fleetqox/lookup_transform",
    "action_type": "tf2_msgs/action/LookupTransform",
}
executor = None
server = None
client = None
server_node = None
client_node = None
try:
    rclpy.init()
    server_node = rclpy.create_node("fleetqox_action_server")
    client_node = rclpy.create_node("fleetqox_action_client")
    events = []

    def execute_callback(goal_handle):
        events.append("execute")
        result = LookupTransform.Result()
        result.transform.header.frame_id = goal_handle.request.target_frame
        result.transform.child_frame_id = goal_handle.request.source_frame
        result.transform.transform.rotation.w = 1.0
        result.error.error = 0
        result.error.error_string = "ok"
        goal_handle.succeed()
        return result

    server = ActionServer(
        server_node,
        LookupTransform,
        summary["action_name"],
        execute_callback)
    client = ActionClient(client_node, LookupTransform, summary["action_name"])
    executor = MultiThreadedExecutor(num_threads=2)
    executor.add_node(server_node)
    executor.add_node(client_node)

    summary["available"] = spin_until(executor, lambda: client.server_is_ready(), 3.0)
    goal = LookupTransform.Goal()
    goal.target_frame = "map"
    goal.source_frame = "base_link"

    send_future = client.send_goal_async(goal)
    summary["send_done"] = spin_until(executor, lambda: send_future.done(), 3.0)
    if summary["send_done"]:
        goal_handle = send_future.result()
        summary["goal_accepted"] = bool(goal_handle.accepted)
        spin_until(executor, lambda: "execute" in events, 3.0)
        result_future = goal_handle.get_result_async()
        summary["result_done"] = spin_until(executor, lambda: result_future.done(), 3.0)
        if summary["result_done"]:
            result_wrapper = result_future.result()
            result = result_wrapper.result
            summary["result_status"] = int(result_wrapper.status)
            summary["result_frame"] = result.transform.header.frame_id
            summary["result_child_frame"] = result.transform.child_frame_id
            summary["result_error"] = int(result.error.error)
            summary["result_error_string"] = result.error.error_string
    summary["events"] = events
    summary["status"] = "ok" if (
        summary.get("available") is True and
        summary.get("send_done") is True and
        summary.get("goal_accepted") is True and
        summary.get("result_done") is True and
        summary.get("result_status") == 4 and
        summary.get("result_frame") == "map" and
        summary.get("result_child_frame") == "base_link" and
        summary.get("result_error") == 0 and
        "execute" in events
    ) else "failed"
except Exception as exc:
    summary["status"] = "exception"
    summary["exception"] = repr(exc)
    summary["traceback"] = traceback.format_exc()
finally:
    if executor is not None:
        try:
            executor.shutdown()
        except Exception:
            pass
    for entity in (server, client):
        if entity is not None:
            try:
                entity.destroy()
            except Exception:
                pass
    for node in (server_node, client_node):
        if node is not None:
            try:
                node.destroy_node()
            except Exception:
                pass
    try:
        rclpy.shutdown()
    except Exception:
        pass
print(json.dumps(summary, sort_keys=True))
PY
probe_ret=$?
PROBE_RET="$probe_ret" python3 - <<'PY'
import json
import os
from pathlib import Path

stdout = Path("/tmp/fleetrmw_rclpy_action_probe.out").read_text()
stderr = Path("/tmp/fleetrmw_rclpy_action_probe.err").read_text()
probe = {}
for line in reversed(stdout.splitlines()):
    stripped = line.strip()
    if stripped.startswith("{"):
        try:
            probe = json.loads(stripped)
        except json.JSONDecodeError:
            probe = {"status": "parse_failed", "raw": stripped}
        break
if not probe:
    probe = {"status": "missing", "raw_stdout": stdout}
summary = {
    "schema_version": "fleetrmw.rmw_docker_rclpy_action_probe.v1",
    "status": "pending",
    "probe": probe,
    "probe_stdout": stdout,
    "probe_stderr": stderr,
    "probe_returncode": int(os.environ["PROBE_RET"]),
}
summary["status"] = "ok" if (
    summary["probe_returncode"] == 0 and
    probe.get("status") == "ok" and
    probe.get("available") is True and
    probe.get("goal_accepted") is True and
    probe.get("result_done") is True and
    probe.get("result_status") == 4 and
    probe.get("result_frame") == "map" and
    probe.get("result_child_frame") == "base_link" and
    probe.get("result_error") == 0 and
    probe.get("events") == ["execute"] and
    stderr == ""
) else "failed"
print(json.dumps(summary, sort_keys=True))
PY
"""
    result = subprocess.run(
        [
            "docker",
            "run",
            "--rm",
            "--entrypoint",
            "bash",
            "-v",
            f"{root}:/work",
            "-w",
            "/work",
            image,
            "-lc",
            command,
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
    summary: dict[str, Any] = json.loads(lines[-1])
    summary["docker_returncode"] = result.returncode
    summary["docker_stderr"] = result.stderr
    return summary


if __name__ == "__main__":
    raise SystemExit(main())

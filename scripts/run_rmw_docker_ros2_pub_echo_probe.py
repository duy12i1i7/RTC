"""Run a Docker ROS 2 CLI pub/echo probe against rmw_fleetqox_cpp."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import shlex
import subprocess
from typing import Any


SCHEMA_VERSION = "fleetrmw.rmw_ros2_pub_echo_probe.v1"
DEFAULT_IMAGE = "ros:jazzy-ros-base"
DEFAULT_TOPIC = "/fleetqox/cli_echo"
DEFAULT_TYPE = "std_msgs/msg/String"
DEFAULT_PAYLOAD = "fleetqox cli echo"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--image", default=DEFAULT_IMAGE)
    parser.add_argument("--topic", default=DEFAULT_TOPIC)
    parser.add_argument("--payload", default=DEFAULT_PAYLOAD)
    parser.add_argument("--subscriber-bind", default="127.0.0.1:48253")
    parser.add_argument("--summary-json", default="results_rmw_socket/docker_ros2_pub_echo_probe_summary.json")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    root = Path(__file__).resolve().parents[1]
    summary = run_probe(
        root=root,
        image=args.image,
        topic=args.topic,
        payload=args.payload,
        subscriber_bind=args.subscriber_bind,
    )
    summary_path = root / args.summary_json
    summary_path.parent.mkdir(parents=True, exist_ok=True)
    summary_path.write_text(json.dumps(summary, sort_keys=True) + "\n", encoding="utf-8")

    if args.json:
        print(json.dumps(summary, sort_keys=True))
    else:
        print("fleetrmw-ros2-pub-echo-probe")
        print(f"  status: {summary['status']}")
        print(f"  echo_received: {summary['echo_received']}")
        print(f"  echo_returncode: {summary['echo_returncode']}")
        print(f"  pub_returncode: {summary['pub_returncode']}")
    return 0 if summary["status"] == "ok" else 1


def run_probe(
    *,
    root: Path,
    image: str,
    topic: str,
    payload: str,
    subscriber_bind: str,
) -> dict[str, Any]:
    quoted_topic = shlex.quote(topic)
    quoted_payload_yaml = shlex.quote("{data: " + payload + "}")
    quoted_subscriber_bind = shlex.quote(subscriber_bind)
    command = f"""
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
FLEETQOX_RMW_BIND={quoted_subscriber_bind} \
  ros2 topic echo --no-daemon --once --timeout 8 {quoted_topic} {DEFAULT_TYPE} \
  > /tmp/fleetrmw_echo.out 2> /tmp/fleetrmw_echo.err &
echo_pid=$!
sleep 0.7
FLEETQOX_RMW_PEERS={quoted_subscriber_bind} \
  ros2 topic pub --times 3 --rate 5 --wait-matching-subscriptions 0 \
  {quoted_topic} {DEFAULT_TYPE} {quoted_payload_yaml} \
  > /tmp/fleetrmw_pub.out 2> /tmp/fleetrmw_pub.err
pub_ret=$?
wait "$echo_pid"
echo_ret=$?
ECHO_RET="$echo_ret" PUB_RET="$pub_ret" python3 - <<'PY'
import json
import os
from pathlib import Path

topic = {topic!r}
expected_type = {DEFAULT_TYPE!r}
payload = {payload!r}
echo_stdout = Path("/tmp/fleetrmw_echo.out").read_text()
echo_stderr = Path("/tmp/fleetrmw_echo.err").read_text()
pub_stdout = Path("/tmp/fleetrmw_pub.out").read_text()
pub_stderr = Path("/tmp/fleetrmw_pub.err").read_text()
expected_echo = "data: " + payload
summary = {{
    "schema_version": {SCHEMA_VERSION!r},
    "status": "pending",
    "topic": topic,
    "expected_type": expected_type,
    "payload": payload,
    "echo_received": expected_echo in echo_stdout,
    "echo_stdout": echo_stdout,
    "echo_stderr": echo_stderr,
    "pub_stdout": pub_stdout,
    "pub_stderr": pub_stderr,
    "echo_returncode": int(os.environ["ECHO_RET"]),
    "pub_returncode": int(os.environ["PUB_RET"]),
}}
summary["status"] = "ok" if (
    summary["echo_returncode"] == 0 and
    summary["pub_returncode"] == 0 and
    summary["echo_received"] and
    echo_stderr == "" and
    pub_stderr == ""
) else "failed"
print(json.dumps(summary, sort_keys=True))
PY
"""
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

"""Run Docker ROS 2 CLI service-call probe against rmw_fleetqox_cpp."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import shlex
import subprocess
from typing import Any


SCHEMA_VERSION = "fleetrmw.rmw_ros2_service_call_probe.v1"
DEFAULT_IMAGE = "ros:jazzy-ros-base"
DEFAULT_SERVICE = "/fleetqox/set_bool"
DEFAULT_TYPE = "std_srvs/srv/SetBool"
DEFAULT_REQUEST = "{data: true}"
EXPECTED_MESSAGE = "fleetqox set_bool accepted"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--image", default=DEFAULT_IMAGE)
    parser.add_argument("--service", default=DEFAULT_SERVICE)
    parser.add_argument("--service-bind", default="127.0.0.1:48290")
    parser.add_argument("--client-bind", default="127.0.0.1:48291")
    parser.add_argument("--startup-delay", type=float, default=0.4)
    parser.add_argument("--hold-ms", type=int, default=8000)
    parser.add_argument("--call-timeout", type=int, default=7)
    parser.add_argument(
        "--summary-json",
        default="results_rmw_socket/docker_ros2_service_call_probe_summary.json",
    )
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    root = Path(__file__).resolve().parents[1]
    summary = run_probe(
        root=root,
        image=args.image,
        service=args.service,
        service_bind=args.service_bind,
        client_bind=args.client_bind,
        startup_delay=args.startup_delay,
        hold_ms=args.hold_ms,
        call_timeout=args.call_timeout,
    )
    summary_path = root / args.summary_json
    summary_path.parent.mkdir(parents=True, exist_ok=True)
    summary_path.write_text(json.dumps(summary, sort_keys=True) + "\n", encoding="utf-8")

    if args.json:
        print(json.dumps(summary, sort_keys=True))
    else:
        print("fleetrmw-ros2-service-call-probe")
        print(f"  status: {summary['status']}")
        print(f"  response_found: {summary['response_found']}")
        print(f"  server_saw_request: {summary['server_saw_request']}")
    return 0 if summary["status"] == "ok" else 1


def run_probe(
    *,
    root: Path,
    image: str,
    service: str,
    service_bind: str,
    client_bind: str,
    startup_delay: float,
    hold_ms: int,
    call_timeout: int,
) -> dict[str, Any]:
    quoted_service = shlex.quote(service)
    quoted_service_bind = shlex.quote(service_bind)
    quoted_client_bind = shlex.quote(client_bind)
    quoted_request = shlex.quote(DEFAULT_REQUEST)
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
FLEETQOX_RMW_BIND={quoted_service_bind} \
FLEETQOX_RMW_PEERS={quoted_client_bind} \
  /tmp/fleetrmw_install/rmw_fleetqox_cpp/lib/rmw_fleetqox_cpp/fleetrmw_rcl_service_node \
  --service {quoted_service} --hold-ms {hold_ms} \
  > /tmp/fleetrmw_service_node.out 2> /tmp/fleetrmw_service_node.err &
service_pid=$!
sleep {startup_delay}
FLEETQOX_RMW_BIND={quoted_client_bind} \
FLEETQOX_RMW_PEERS={quoted_service_bind} \
  timeout {call_timeout} ros2 service call {quoted_service} {DEFAULT_TYPE} {quoted_request} \
  > /tmp/fleetrmw_service_call.out 2> /tmp/fleetrmw_service_call.err
call_ret=$?
wait "$service_pid"
service_ret=$?
CALL_RET="$call_ret" SERVICE_RET="$service_ret" python3 - <<'PY'
import json
import os
from pathlib import Path

service = {service!r}
expected_type = {DEFAULT_TYPE!r}
expected_message = {EXPECTED_MESSAGE!r}
call_stdout = Path("/tmp/fleetrmw_service_call.out").read_text()
call_stderr = Path("/tmp/fleetrmw_service_call.err").read_text()
service_node_stdout = Path("/tmp/fleetrmw_service_node.out").read_text()
service_node_stderr = Path("/tmp/fleetrmw_service_node.err").read_text()
try:
    service_summary = json.loads(service_node_stdout.strip().splitlines()[-1])
except Exception:
    service_summary = {{"status": "parse_failed", "raw_stdout": service_node_stdout}}
response_found = "success=True" in call_stdout and expected_message in call_stdout
server_saw_request = int(service_summary.get("request_count", 0)) >= 1
summary = {{
    "schema_version": {SCHEMA_VERSION!r},
    "status": "pending",
    "service": service,
    "expected_type": expected_type,
    "expected_message": expected_message,
    "response_found": response_found,
    "server_saw_request": server_saw_request,
    "service_call_stdout": call_stdout,
    "service_call_stderr": call_stderr,
    "service_node_stdout": service_node_stdout,
    "service_node_stderr": service_node_stderr,
    "service_node": service_summary,
    "service_call_returncode": int(os.environ["CALL_RET"]),
    "service_node_returncode": int(os.environ["SERVICE_RET"]),
}}
summary["status"] = "ok" if (
    summary["service_call_returncode"] == 0 and
    summary["service_node_returncode"] == 0 and
    response_found and
    server_saw_request and
    call_stderr == "" and
    service_node_stderr == "" and
    service_summary.get("status") == "ok"
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

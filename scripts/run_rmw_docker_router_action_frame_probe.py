"""Run a Docker router-mediated action-frame transport probe for rmw_fleetqox_cpp."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import subprocess
from typing import Any


SCHEMA_VERSION = "fleetrmw.rmw_docker_router_action_frame_probe.v1"
DEFAULT_IMAGE = "ros:jazzy-ros-base"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--image", default=DEFAULT_IMAGE)
    parser.add_argument(
        "--summary-json",
        default="results_rmw_socket/docker_rmw_router_action_frame_probe_summary.json",
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
        print("fleetrmw-router-action-frame-probe")
        print(f"  status: {summary['status']}")
        print(f"  probe_status: {summary.get('probe', {}).get('status')}")
        print(f"  router_action_forwarded: {summary.get('router', {}).get('action_forwarded')}")
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
/tmp/fleetrmw_install/rmw_fleetqox_cpp/lib/rmw_fleetqox_cpp/fleetrmw_udp_router_probe \
  --bind 127.0.0.1:48310 \
  --expected-frames 0 \
  --expected-action-frames 5 \
  --expected-graph-advertisements 2 \
  --timeout-ms 5000 \
  > /tmp/fleetrmw_action_router.out 2> /tmp/fleetrmw_action_router.err &
router_pid=$!
sleep 0.2
/tmp/fleetrmw_install/rmw_fleetqox_cpp/lib/rmw_fleetqox_cpp/fleetrmw_action_router_probe \
  --router 127.0.0.1:48310 \
  --server-bind 127.0.0.1:48311 \
  --client-bind 127.0.0.1:48312 \
  --timeout-ms 3500 \
  > /tmp/fleetrmw_action_router_probe.out 2> /tmp/fleetrmw_action_router_probe.err
probe_ret=$?
wait "$router_pid"
router_ret=$?
PROBE_RET="$probe_ret" ROUTER_RET="$router_ret" python3 - <<'PY'
import json
import os
from pathlib import Path


def parse_last_json(path: str) -> dict:
    text = Path(path).read_text()
    for line in reversed(text.splitlines()):
        stripped = line.strip()
        if stripped.startswith("{"):
            try:
                return json.loads(stripped)
            except json.JSONDecodeError:
                return {"status": "parse_failed", "raw": stripped}
    return {"status": "missing", "raw": text}


probe_stdout = Path("/tmp/fleetrmw_action_router_probe.out").read_text()
probe_stderr = Path("/tmp/fleetrmw_action_router_probe.err").read_text()
router_stdout = Path("/tmp/fleetrmw_action_router.out").read_text()
router_stderr = Path("/tmp/fleetrmw_action_router.err").read_text()
probe = parse_last_json("/tmp/fleetrmw_action_router_probe.out")
router = parse_last_json("/tmp/fleetrmw_action_router.out")
summary = {
    "schema_version": "fleetrmw.rmw_docker_router_action_frame_probe.v1",
    "status": "pending",
    "probe": probe,
    "router": router,
    "probe_stdout": probe_stdout,
    "probe_stderr": probe_stderr,
    "router_stdout": router_stdout,
    "router_stderr": router_stderr,
    "probe_returncode": int(os.environ["PROBE_RET"]),
    "router_returncode": int(os.environ["ROUTER_RET"]),
}
summary["status"] = "ok" if (
    summary["probe_returncode"] == 0 and
    summary["router_returncode"] == 0 and
    probe.get("status") == "ok" and
    probe.get("server_received_roles") == ["goal", "cancel"] and
    probe.get("client_received_roles") == ["feedback", "status", "result"] and
    router.get("status") == "ok" and
    router.get("action_frames", 0) >= 5 and
    router.get("action_forwarded", 0) >= 5 and
    router.get("graph_action_servers", 0) >= 1 and
    router.get("graph_action_clients", 0) >= 1 and
    router.get("expected_action_frames") == 5 and
    probe_stderr == "" and
    router_stderr == ""
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

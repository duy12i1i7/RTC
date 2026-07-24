"""Run the FleetRMW automatic graph-guard and subscription wait probe in Docker."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import subprocess
from typing import Any


SCHEMA_VERSION = "fleetrmw.rmw_docker_wait_probe.v1"
DEFAULT_IMAGE = "ros:jazzy-ros-base"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--image", default=DEFAULT_IMAGE)
    parser.add_argument(
        "--summary-json",
        default="results_rmw_socket/docker_rmw_wait_probe_summary.json",
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
        print("fleetrmw-rmw-wait-probe")
        print(f"  status: {summary['status']}")
        print(f"  graph_guard_automatic: {summary.get('probe', {}).get('graph_guard_automatic')}")
        print(f"  subscription_ready: {summary.get('probe', {}).get('subscription_ready')}")
        print(f"  wait_contract: {summary.get('probe', {}).get('max_conditions_enforced')}")
    return 0 if summary["status"] == "ok" else 1


def run_probe(*, root: Path, image: str) -> dict[str, Any]:
    command = """
source /opt/ros/jazzy/setup.bash
rm -rf /tmp/fleetrmw_build /tmp/fleetrmw_install /tmp/fleetrmw_log
export CMAKE_BUILD_PARALLEL_LEVEL=2
colcon --log-base /tmp/fleetrmw_log build \
  --executor sequential \
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
/tmp/fleetrmw_install/rmw_fleetqox_cpp/lib/rmw_fleetqox_cpp/fleetrmw_wait_probe \
  > /tmp/fleetrmw_wait_probe.out 2> /tmp/fleetrmw_wait_probe.err
probe_ret=$?
PROBE_RET="$probe_ret" python3 - <<'PY'
import json
import os
from pathlib import Path

stdout = Path("/tmp/fleetrmw_wait_probe.out").read_text()
stderr = Path("/tmp/fleetrmw_wait_probe.err").read_text()
probe = {}
for line in reversed(stdout.splitlines()):
    stripped = line.strip()
    if stripped.startswith("{"):
        probe = json.loads(stripped)
        break
summary = {
    "schema_version": "fleetrmw.rmw_docker_wait_probe.v1",
    "status": "pending",
    "probe": probe,
    "probe_stdout": stdout,
    "probe_stderr": stderr,
    "probe_returncode": int(os.environ["PROBE_RET"]),
}
summary["status"] = "ok" if (
    summary["probe_returncode"] == 0 and
    probe.get("status") == "ok" and
    probe.get("graph_guard_automatic") is True and
    probe.get("graph_guard_ready") is True and
    probe.get("subscription_ready") is True and
    probe.get("max_conditions_enforced") is True and
    probe.get("guard_conditions_external_to_capacity") is True and
    probe.get("zero_max_conditions_unbounded") is True and
    probe.get("null_entry_rejected") is True and
    probe.get("cross_context_same_domain") is True and
    probe.get("cross_context_rejected") is True and
    probe.get("shutdown_context_rejected") is True and
    probe.get("publisher_owner_node_enforced") is True and
    probe.get("subscription_owner_node_enforced") is True and
    probe.get("publish_ret") == 0 and
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
    lines = [line for line in result.stdout.splitlines() if line.strip().startswith("{")]
    if result.returncode != 0 or not lines:
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

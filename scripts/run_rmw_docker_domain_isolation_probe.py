"""Build and run the FleetRMW ROS domain-isolation probe in Docker."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import subprocess
from typing import Any


SCHEMA_VERSION = "fleetrmw.rmw_docker_domain_isolation_probe.v1"
DEFAULT_IMAGE = "ros:jazzy-ros-base"


def run_probe(*, root: Path, image: str) -> dict[str, Any]:
    command = r"""
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
/tmp/fleetrmw_install/rmw_fleetqox_cpp/lib/rmw_fleetqox_cpp/fleetrmw_domain_isolation_probe \
  > /tmp/fleetrmw_domain_isolation_probe.out \
  2> /tmp/fleetrmw_domain_isolation_probe.err
probe_ret=$?
PROBE_RET="$probe_ret" python3 - <<'PY'
import json
import os
from pathlib import Path

stdout = Path("/tmp/fleetrmw_domain_isolation_probe.out").read_text()
stderr = Path("/tmp/fleetrmw_domain_isolation_probe.err").read_text()
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
required_true = (
    "graph_guard_domain_a_ready",
    "graph_guard_cross_domain_suppressed",
    "graph_counts_isolated",
    "data_plane_isolated",
    "pubsub_type_data_plane_isolated",
    "same_domain_sample_taken",
    "service_availability_isolated",
    "service_data_plane_isolated",
    "remote_graph_isolated",
)
status_ok = (
    int(os.environ["PROBE_RET"]) == 0
    and probe.get("status") == "ok"
    and all(probe.get(key) is True for key in required_true)
    and probe.get("cross_domain_sample_taken") is False
    and probe.get("wrong_type_sample_taken") is False
    and stderr == ""
)
summary = {
    "schema_version": "fleetrmw.rmw_docker_domain_isolation_probe.v1",
    "status": "ok" if status_ok else "failed",
    "probe": probe,
    "probe_stdout": stdout,
    "probe_stderr": stderr,
    "probe_returncode": int(os.environ["PROBE_RET"]),
}
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


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--image", default=DEFAULT_IMAGE)
    parser.add_argument(
        "--summary-json",
        default="results_rmw_socket/docker_rmw_domain_isolation_probe_summary.json",
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
        probe = summary.get("probe", {})
        print("fleetrmw-rmw-domain-isolation-probe")
        print(f"  status: {summary['status']}")
        print(f"  graph_counts_isolated: {probe.get('graph_counts_isolated')}")
        print(f"  data_plane_isolated: {probe.get('data_plane_isolated')}")
        print(f"  service_data_plane_isolated: {probe.get('service_data_plane_isolated')}")
    return 0 if summary["status"] == "ok" else 1


if __name__ == "__main__":
    raise SystemExit(main())

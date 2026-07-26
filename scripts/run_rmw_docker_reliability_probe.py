"""Run a Docker ACK/NACK retransmission probe against rmw_fleetqox_cpp."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import subprocess
from typing import Any


SCHEMA_VERSION = "fleetrmw.rmw_docker_reliability_probe.v1"
DEFAULT_IMAGE = "ros:jazzy-ros-base"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--image", default=DEFAULT_IMAGE)
    parser.add_argument("--summary-json", default="results_rmw_socket/docker_rmw_reliability_probe_summary.json")
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
        print("fleetrmw-rmw-reliability-probe")
        print(f"  status: {summary['status']}")
        print(f"  dropped: {summary.get('probe', {}).get('test_dropped_frames')}")
        print(f"  retransmissions: {summary.get('probe', {}).get('nack_retransmissions')}")
        print(
            "  initial-sequence timeout retransmissions: "
            f"{summary.get('initial_sequence_probe', {}).get('reliable_timeout_retransmissions')}"
        )
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
FLEETQOX_RMW_DROP_SOURCE_SEQUENCES=2 \
  /tmp/fleetrmw_install/rmw_fleetqox_cpp/lib/rmw_fleetqox_cpp/fleetrmw_reliability_probe \
  > /tmp/fleetrmw_reliability_probe.out 2> /tmp/fleetrmw_reliability_probe.err
probe_ret=$?
FLEETQOX_RMW_DROP_SOURCE_SEQUENCES=1 \
FLEETQOX_RMW_RELIABLE_ACK_TIMEOUT_MS=100 \
FLEETQOX_RMW_RELIABLE_MAX_RETRANSMISSIONS=3 \
  /tmp/fleetrmw_install/rmw_fleetqox_cpp/lib/rmw_fleetqox_cpp/fleetrmw_reliability_probe \
  > /tmp/fleetrmw_initial_reliability_probe.out \
  2> /tmp/fleetrmw_initial_reliability_probe.err
initial_probe_ret=$?
PROBE_RET="$probe_ret" INITIAL_PROBE_RET="$initial_probe_ret" python3 - <<'PY'
import json
import os
from pathlib import Path

def parse_probe(path):
    stdout = Path(path).read_text()
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
    return stdout, probe


stdout, probe = parse_probe("/tmp/fleetrmw_reliability_probe.out")
stderr = Path("/tmp/fleetrmw_reliability_probe.err").read_text()
initial_stdout, initial_probe = parse_probe(
    "/tmp/fleetrmw_initial_reliability_probe.out"
)
initial_stderr = Path("/tmp/fleetrmw_initial_reliability_probe.err").read_text()
payloads = set(probe.get("received_payloads", []))
initial_payloads = set(initial_probe.get("received_payloads", []))
summary = {
    "schema_version": "fleetrmw.rmw_docker_reliability_probe.v1",
    "status": "pending",
    "probe": probe,
    "initial_sequence_probe": initial_probe,
    "probe_stdout": stdout,
    "probe_stderr": stderr,
    "probe_returncode": int(os.environ["PROBE_RET"]),
    "initial_sequence_probe_stdout": initial_stdout,
    "initial_sequence_probe_stderr": initial_stderr,
    "initial_sequence_probe_returncode": int(os.environ["INITIAL_PROBE_RET"]),
}
summary["status"] = "ok" if (
    summary["probe_returncode"] == 0 and
    probe.get("status") == "ok" and
    probe.get("test_dropped_frames", 0) >= 1 and
    probe.get("ack_nack_sent", 0) >= 2 and
    probe.get("ack_nack_received", 0) >= 2 and
    probe.get("nack_retransmissions", 0) >= 1 and
    {"one", "two", "three"}.issubset(payloads) and
    stderr == "" and
    summary["initial_sequence_probe_returncode"] == 0 and
    initial_probe.get("status") == "ok" and
    initial_probe.get("drop_source_sequences") == [1] and
    initial_probe.get("test_dropped_frames", 0) >= 1 and
    initial_probe.get("reliable_timeout_retransmissions", 0) >= 1 and
    {"one", "two", "three"}.issubset(initial_payloads) and
    initial_stderr == ""
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
    summary: dict[str, Any] = json.loads(lines[-1])
    summary["docker_returncode"] = result.returncode
    summary["docker_stderr"] = result.stderr
    return summary


if __name__ == "__main__":
    raise SystemExit(main())

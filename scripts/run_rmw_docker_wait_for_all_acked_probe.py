"""Build and repeatedly verify FleetRMW publisher ACK waiting in Docker."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import subprocess
from typing import Any


SCHEMA_VERSION = "fleetrmw.rmw_docker_wait_for_all_acked_probe.v1"
DEFAULT_IMAGE = "localhost/fleetrmw/rmw-netem:jazzy"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--image", default=DEFAULT_IMAGE)
    parser.add_argument("--runs", type=int, default=5)
    parser.add_argument(
        "--summary-json",
        default="results_rmw_socket/docker_rmw_wait_for_all_acked_probe_summary.json",
    )
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    if args.runs < 2:
        parser.error("--runs must be at least 2 to exercise repeatability")

    root = Path(__file__).resolve().parents[1]
    summary = run_probe(root=root, image=args.image, runs=args.runs)
    summary_path = root / args.summary_json
    summary_path.parent.mkdir(parents=True, exist_ok=True)
    summary_path.write_text(json.dumps(summary, sort_keys=True) + "\n", encoding="utf-8")
    if args.json:
        print(json.dumps(summary, sort_keys=True))
    else:
        print("fleetrmw-rmw-wait-for-all-acked-probe")
        print(f"  status: {summary['status']}")
        print(f"  successful_runs: {summary.get('successful_runs', 0)}/{args.runs}")
        print(f"  all_subscribers_acknowledged: {summary.get('all_subscribers_acknowledged')}")
    return 0 if summary["status"] == "ok" else 1


def run_probe(*, root: Path, image: str, runs: int) -> dict[str, Any]:
    command = r"""
source /opt/ros/jazzy/setup.bash
rm -rf /tmp/fleetrmw_acked_build /tmp/fleetrmw_acked_install /tmp/fleetrmw_acked_log
colcon --log-base /tmp/fleetrmw_acked_log build \
  --base-paths ros2_ws/src \
  --packages-select fleetrmw_interfaces rmw_fleetqox_cpp \
  --build-base /tmp/fleetrmw_acked_build \
  --install-base /tmp/fleetrmw_acked_install \
  --cmake-args -DCMAKE_BUILD_TYPE=Release >/tmp/fleetrmw_acked_build.log 2>&1
build_ret=$?
if [ "$build_ret" -ne 0 ]; then
  cat /tmp/fleetrmw_acked_build.log >&2
  exit "$build_ret"
fi
source /tmp/fleetrmw_acked_install/setup.bash
export RMW_IMPLEMENTATION=rmw_fleetqox_cpp
export FLEETQOX_RMW_TEST_ACK_DELAY_SUBSCRIPTION_SUFFIX=-2
export FLEETQOX_RMW_TEST_ACK_DELAY_MS=400
RUN_COUNT="${RUN_COUNT}" python3 - <<'PY'
import json
import os
from pathlib import Path
import subprocess

probe_path = Path(
    "/tmp/fleetrmw_acked_install/rmw_fleetqox_cpp/lib/"
    "rmw_fleetqox_cpp/fleetrmw_wait_for_all_acked_probe"
)


def parse_probe(stdout: str) -> dict:
    for line in reversed(stdout.splitlines()):
        stripped = line.strip()
        if stripped.startswith("{"):
            try:
                return json.loads(stripped)
            except json.JSONDecodeError:
                return {"status": "parse_failed", "raw": stripped}
    return {"status": "missing", "raw_stdout": stdout}


def valid_run(item: dict) -> bool:
    probe = item["probe"]
    return (
        item["returncode"] == 0
        and item["stderr"] == ""
        and probe.get("schema_version") == "fleetrmw.rmw_wait_for_all_acked_probe.v1"
        and probe.get("status") == "ok"
        and probe.get("matched_subscription_count") == 2
        and probe.get("empty_wait_ok") is True
        and probe.get("partial_ack_timeout") is True
        and int(probe.get("partial_wait_elapsed_ms", 0)) >= 150
        and probe.get("partial_expected_ack_count") == 2
        and probe.get("partial_observed_ack_count") == 1
        and probe.get("all_acked_wait_ok") is True
        and probe.get("completed_expected_ack_count") == 2
        and probe.get("completed_observed_ack_count") == 2
        and probe.get("zero_timeout_after_ack_ok") is True
        and probe.get("null_publisher_rejected") is True
        and int(probe.get("wait_timeout_count", 0)) >= 1
    )


run_count = int(os.environ["RUN_COUNT"])
runs = []
for index in range(run_count):
    result = subprocess.run(
        [str(probe_path)],
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    runs.append({
        "index": index,
        "returncode": result.returncode,
        "probe": parse_probe(result.stdout),
        "stderr": result.stderr,
    })

successful_runs = sum(valid_run(item) for item in runs)
summary = {
    "schema_version": "fleetrmw.rmw_docker_wait_for_all_acked_probe.v1",
    "status": "ok" if successful_runs == run_count else "failed",
    "run_count": run_count,
    "successful_runs": successful_runs,
    "ok_run_count": successful_runs,
    "failed_run_count": run_count - successful_runs,
    "all_subscribers_acknowledged": all(
        item["probe"].get("completed_observed_ack_count") == 2
        and item["probe"].get("all_acked_wait_ok") is True
        for item in runs
    ),
    "partial_ack_never_misreported_complete": all(
        item["probe"].get("partial_observed_ack_count") == 1
        and item["probe"].get("partial_ack_timeout") is True
        for item in runs
    ),
    "runs": runs,
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
            "-e",
            f"RUN_COUNT={runs}",
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

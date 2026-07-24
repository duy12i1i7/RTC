"""Build and repeatedly verify FleetRMW take-sequence semantics in Docker."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import subprocess
from typing import Any


SCHEMA_VERSION = "fleetrmw.rmw_docker_take_sequence_probe.v1"
DEFAULT_IMAGE = "localhost/fleetrmw/rmw-netem:jazzy"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--image", default=DEFAULT_IMAGE)
    parser.add_argument("--runs", type=int, default=5)
    parser.add_argument(
        "--summary-json",
        default="results_rmw_socket/docker_rmw_take_sequence_probe_summary.json",
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
        print("fleetrmw-rmw-take-sequence-probe")
        print(f"  status: {summary['status']}")
        print(f"  successful_runs: {summary.get('successful_runs', 0)}/{args.runs}")
        audit = summary.get("symbol_audit", {})
        print(f"  required_symbol_parity: {audit.get('required_symbol_parity')}")
    return 0 if summary["status"] == "ok" else 1


def run_probe(*, root: Path, image: str, runs: int) -> dict[str, Any]:
    command = r"""
source /opt/ros/jazzy/setup.bash
rm -rf /tmp/fleetrmw_take_build /tmp/fleetrmw_take_install /tmp/fleetrmw_take_log
colcon --log-base /tmp/fleetrmw_take_log build \
  --base-paths ros2_ws/src \
  --packages-select fleetrmw_interfaces rmw_fleetqox_cpp \
  --build-base /tmp/fleetrmw_take_build \
  --install-base /tmp/fleetrmw_take_install \
  --cmake-args -DCMAKE_BUILD_TYPE=Release >/tmp/fleetrmw_take_build.log 2>&1
build_ret=$?
if [ "$build_ret" -ne 0 ]; then
  cat /tmp/fleetrmw_take_build.log >&2
  exit "$build_ret"
fi
source /tmp/fleetrmw_take_install/setup.bash
export RMW_IMPLEMENTATION=rmw_fleetqox_cpp
RUN_COUNT="${RUN_COUNT}" python3 - <<'PY'
import json
import os
from pathlib import Path
import subprocess

schema = "fleetrmw.rmw_docker_take_sequence_probe.v1"
probe_path = Path(
    "/tmp/fleetrmw_take_install/rmw_fleetqox_cpp/lib/"
    "rmw_fleetqox_cpp/fleetrmw_take_sequence_probe"
)
fleet_library = Path(
    "/tmp/fleetrmw_take_install/rmw_fleetqox_cpp/lib/librmw_fleetqox_cpp.so"
)
baseline_library = Path("/opt/ros/jazzy/lib/librmw_fastrtps_cpp.so")


def exported_rmw_symbols(path: Path) -> list[str]:
    result = subprocess.run(
        ["nm", "-D", "--defined-only", str(path)],
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    if result.returncode != 0:
        raise RuntimeError(f"nm failed for {path}: {result.stderr.strip()}")
    symbols = set()
    for line in result.stdout.splitlines():
        fields = line.split()
        if fields and fields[-1].startswith("rmw_"):
            symbols.add(fields[-1])
    return sorted(symbols)


def parse_probe(stdout: str) -> dict:
    for line in reversed(stdout.splitlines()):
        stripped = line.strip()
        if stripped.startswith("{"):
            try:
                return json.loads(stripped)
            except json.JSONDecodeError:
                return {"status": "parse_failed", "raw": stripped}
    return {"status": "missing", "raw_stdout": stdout}


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

fleet_symbols = exported_rmw_symbols(fleet_library)
baseline_symbols = exported_rmw_symbols(baseline_library)
missing_baseline_symbols = sorted(set(baseline_symbols) - set(fleet_symbols))
symbol_audit = {
    "baseline": "rmw_fastrtps_cpp (ROS 2 Jazzy image)",
    "baseline_library": str(baseline_library),
    "fleet_library": str(fleet_library),
    "baseline_rmw_symbol_count": len(baseline_symbols),
    "fleet_rmw_symbol_count": len(fleet_symbols),
    "missing_baseline_symbols": missing_baseline_symbols,
    "rmw_take_sequence_exported": "rmw_take_sequence" in fleet_symbols,
    "required_symbol_parity": not missing_baseline_symbols,
}


def valid_run(item: dict) -> bool:
    probe = item["probe"]
    return (
        item["returncode"] == 0
        and item["stderr"] == ""
        and probe.get("schema_version") == "fleetrmw.rmw_take_sequence_probe.v1"
        and probe.get("status") == "ok"
        and probe.get("symbol_exported") is True
        and probe.get("first_taken") == 3
        and probe.get("first_order_ok") is True
        and probe.get("partial_taken") == 2
        and probe.get("partial_take_ok") is True
        and probe.get("empty_sequences_unchanged") is True
        and probe.get("invalid_capacity_unchanged") is True
        and probe.get("concurrent_call_count") == 2
        and probe.get("concurrent_taken_total") == 20
        and probe.get("concurrent_sequences_consecutive") is True
        and probe.get("concurrent_combined_order_complete") is True
        and probe.get("thread_safe_same_subscription_take_sequence") is True
    )


successful_runs = sum(valid_run(item) for item in runs)
summary = {
    "schema_version": schema,
    "status": "ok" if (
        successful_runs == run_count
        and symbol_audit["rmw_take_sequence_exported"]
        and symbol_audit["required_symbol_parity"]
    ) else "failed",
    "run_count": run_count,
    "successful_runs": successful_runs,
    "ok_run_count": successful_runs,
    "failed_run_count": run_count - successful_runs,
    "all_runs_thread_safe": all(
        item["probe"].get("thread_safe_same_subscription_take_sequence") is True
        for item in runs
    ),
    "baseline_rmw_symbol_count": symbol_audit["baseline_rmw_symbol_count"],
    "fleet_rmw_symbol_count": symbol_audit["fleet_rmw_symbol_count"],
    "missing_baseline_symbol_count": len(missing_baseline_symbols),
    "rmw_take_sequence_exported": symbol_audit["rmw_take_sequence_exported"],
    "required_symbol_parity": symbol_audit["required_symbol_parity"],
    "runs": runs,
    "symbol_audit": symbol_audit,
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

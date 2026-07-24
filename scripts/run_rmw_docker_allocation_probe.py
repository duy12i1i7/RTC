"""Build and run the FleetRMW publisher/subscription allocation ABI probe."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import subprocess
import sys
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.run_rmw_docker_shared_memory_probe import parse_last_json


SCHEMA_VERSION = "fleetrmw.docker_allocation_probe.v2"
DEFAULT_IMAGE = "localhost/fleetrmw/rmw-netem:jazzy"


def parse_json_rows(stdout: str) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for line in stdout.splitlines():
        line = line.strip()
        if not line.startswith("{"):
            continue
        try:
            data = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(data, dict):
            rows.append(data)
    return rows


def allocation_probe_ok(probe: dict[str, Any]) -> bool:
    return (
        probe.get("status") == "ok"
        and probe.get("allocation_lifecycle_ok") is True
        and probe.get("publish_take_with_allocation_ok") is True
        and probe.get("payload_scratch_reuse_ok") is True
        and probe.get("completed_operations") == 8
        and probe.get("publisher_allocation_uses") == 8
        and probe.get("subscription_allocation_uses") == 8
        and probe.get("publisher_capacity_growths") == 0
        and probe.get("subscription_capacity_growths") == 0
        and probe.get("deep_preallocation") is False
    )


def run_probe(*, root: Path, image: str, iterations: int = 1) -> dict[str, Any]:
    run_count = max(iterations, 1)
    command = (
        "source /opt/ros/jazzy/setup.bash && "
        "rm -rf /tmp/fq-allocation-build /tmp/fq-allocation-install /tmp/fq-allocation-log && "
        "colcon --log-base /tmp/fq-allocation-log build --base-paths ros2_ws/src "
        "--packages-select rmw_fleetqox_cpp --build-base /tmp/fq-allocation-build "
        "--install-base /tmp/fq-allocation-install --cmake-args -DCMAKE_BUILD_TYPE=Release "
        ">/dev/null && source /tmp/fq-allocation-install/setup.bash && "
        f"for i in $(seq 1 {run_count}); do "
        "/tmp/fq-allocation-install/rmw_fleetqox_cpp/lib/rmw_fleetqox_cpp/"
        "fleetrmw_allocation_probe || exit $?; done"
    )
    completed = subprocess.run(
        [
            "docker", "run", "--rm", "--entrypoint", "bash",
            "-v", f"{root}:/work", "-w", "/work", image, "-lc", command,
        ],
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    rows = parse_json_rows(completed.stdout)
    probe = rows[-1] if rows else parse_last_json(completed.stdout)
    ok_run_count = sum(1 for row in rows if allocation_probe_ok(row))
    ok = (
        completed.returncode == 0
        and len(rows) == run_count
        and ok_run_count == run_count
    )
    publisher_capacities = {
        int(row["publisher_payload_capacity_after"])
        for row in rows
        if isinstance(row.get("publisher_payload_capacity_after"), int)
    }
    subscription_capacities = {
        int(row["subscription_payload_capacity_after"])
        for row in rows
        if isinstance(row.get("subscription_payload_capacity_after"), int)
    }
    return {
        "schema_version": SCHEMA_VERSION,
        "status": "ok" if ok else "failed",
        "image": image,
        "returncode": completed.returncode,
        "run_count": run_count,
        "ok_run_count": ok_run_count,
        "allocation_abi_supported": ok,
        "allocation_payload_scratch_reuse": ok,
        "payload_scratch_operation_count_per_run": 8,
        "payload_scratch_total_publisher_uses": sum(
            int(row.get("publisher_allocation_uses", 0)) for row in rows
        ),
        "payload_scratch_total_subscription_uses": sum(
            int(row.get("subscription_allocation_uses", 0)) for row in rows
        ),
        "payload_scratch_total_capacity_growths": sum(
            int(row.get("publisher_capacity_growths", 0))
            + int(row.get("subscription_capacity_growths", 0))
            for row in rows
        ),
        "publisher_payload_capacities": sorted(publisher_capacities),
        "subscription_payload_capacities": sorted(subscription_capacities),
        "deep_preallocation": False,
        "allocation_repeated_lifecycle_claim": ok and run_count >= 5,
        "probe": probe,
        "runs": rows,
        "stdout": completed.stdout,
        "stderr": completed.stderr,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--image", default=DEFAULT_IMAGE)
    parser.add_argument("--iterations", type=int, default=1)
    parser.add_argument(
        "--summary-json",
        default="results_rmw_socket/docker_allocation_probe_summary.json",
    )
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    summary = run_probe(root=ROOT, image=args.image, iterations=args.iterations)
    output = ROOT / args.summary_json
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    if args.json:
        print(json.dumps(summary, sort_keys=True))
    else:
        print(f"status={summary['status']}")
    return 0 if summary["status"] == "ok" else 1


if __name__ == "__main__":
    raise SystemExit(main())

"""Build and run the FleetRMW QoS event ABI, deadline-production, and readiness probe."""

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


SCHEMA_VERSION = "fleetrmw.docker_qos_event_probe.v1"
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


def qos_event_probe_ok(probe: dict[str, Any]) -> bool:
    return (
        probe.get("status") == "ok"
        and probe.get("event_object_abi_ok") is True
        and probe.get("event_production") is True
        and int(probe.get("offered_total_count_change", 0)) >= 1
        and int(probe.get("requested_total_count_change", 0)) >= 1
        and int(probe.get("publisher_callback_events", 0)) >= 1
        and int(probe.get("subscription_callback_events", 0)) >= 1
        and probe.get("wait_event_readiness") is True
        and probe.get("publisher_wait_ready") is True
        and probe.get("subscription_wait_ready") is True
        and probe.get("timer_driven_idle_deadline_events") is True
        and probe.get("idle_publisher_wait_ready") is True
        and probe.get("idle_subscription_wait_ready") is True
    )


def run_probe(*, root: Path, image: str, iterations: int = 1) -> dict[str, Any]:
    run_count = max(iterations, 1)
    command = (
        "source /opt/ros/jazzy/setup.bash && "
        "rm -rf /tmp/fq-qos-event-build /tmp/fq-qos-event-install /tmp/fq-qos-event-log && "
        "colcon --log-base /tmp/fq-qos-event-log build --base-paths ros2_ws/src "
        "--packages-select rmw_fleetqox_cpp --build-base /tmp/fq-qos-event-build "
        "--install-base /tmp/fq-qos-event-install --cmake-args -DCMAKE_BUILD_TYPE=Release "
        ">/dev/null && source /tmp/fq-qos-event-install/setup.bash && "
        f"for i in $(seq 1 {run_count}); do "
        "/tmp/fq-qos-event-install/rmw_fleetqox_cpp/lib/rmw_fleetqox_cpp/"
        "fleetrmw_qos_event_probe || exit $?; done"
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
    ok_run_count = sum(1 for row in rows if qos_event_probe_ok(row))
    ok = (
        completed.returncode == 0
        and len(rows) == run_count
        and ok_run_count == run_count
    )
    return {
        "schema_version": SCHEMA_VERSION,
        "status": "ok" if ok else "failed",
        "image": image,
        "returncode": completed.returncode,
        "run_count": run_count,
        "ok_run_count": ok_run_count,
        "qos_event_object_abi_supported": ok,
        "event_production": ok,
        "deadline_event_production_scope": "timer_idle_and_next_publish_or_receive_after_gap",
        "wait_event_readiness": ok,
        "wait_event_readiness_scope": "deadline_status_unread_count",
        "timer_driven_idle_deadline_events": ok,
        "timer_driven_idle_deadline_scope": "after_first_publish_or_receive",
        "qos_event_repeated_deadline_waitable_claim": ok and run_count >= 5,
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
        default="results_rmw_socket/docker_qos_event_probe_summary.json",
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

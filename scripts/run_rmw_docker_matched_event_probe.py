"""Build and run the FleetRMW publication/subscription matched-event probe."""

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


SCHEMA_VERSION = "fleetrmw.docker_matched_event_probe.v1"
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


def matched_event_probe_ok(probe: dict[str, Any]) -> bool:
    return (
        probe.get("status") == "ok"
        and probe.get("matched_event_production") is True
        and probe.get("publication_matched_supported") is True
        and probe.get("subscription_matched_supported") is True
        and probe.get("publication_connect_taken") is True
        and probe.get("publication_disconnect_taken") is True
        and probe.get("publication_connect_current_count") == 1
        and probe.get("publication_disconnect_current_count") == 0
        and probe.get("publication_disconnect_current_count_change") == -1
        and int(probe.get("publication_callback_events", 0)) >= 2
        and probe.get("subscription_connect_taken") is True
        and probe.get("subscription_disconnect_taken") is True
        and probe.get("subscription_connect_current_count") == 1
        and probe.get("subscription_disconnect_current_count") == 0
        and probe.get("subscription_disconnect_current_count_change") == -1
        and int(probe.get("subscription_callback_events", 0)) >= 2
    )


def run_probe(*, root: Path, image: str, iterations: int = 1) -> dict[str, Any]:
    run_count = max(iterations, 1)
    command = (
        "source /opt/ros/jazzy/setup.bash && "
        "rm -rf /tmp/fq-matched-event-build /tmp/fq-matched-event-install "
        "/tmp/fq-matched-event-log && "
        "colcon --log-base /tmp/fq-matched-event-log build --base-paths ros2_ws/src "
        "--packages-select rmw_fleetqox_cpp --build-base /tmp/fq-matched-event-build "
        "--install-base /tmp/fq-matched-event-install --cmake-args -DCMAKE_BUILD_TYPE=Release "
        ">/dev/null && source /tmp/fq-matched-event-install/setup.bash && "
        f"for i in $(seq 1 {run_count}); do "
        "/tmp/fq-matched-event-install/rmw_fleetqox_cpp/lib/rmw_fleetqox_cpp/"
        "fleetrmw_matched_event_probe || exit $?; done"
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
    ok_run_count = sum(1 for row in rows if matched_event_probe_ok(row))
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
        "matched_event_production": ok,
        "matched_event_scope": "local_same_process_compatible_endpoint_create_destroy",
        "matched_event_repeated_claim": ok and run_count >= 5,
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
        default="results_rmw_socket/docker_matched_event_probe_summary.json",
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

"""Build and run the FleetRMW message-lost QoS event probe."""

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


SCHEMA_VERSION = "fleetrmw.docker_message_lost_event_probe.v1"
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


def message_lost_probe_ok(probe: dict[str, Any]) -> bool:
    return (
        probe.get("status") == "ok"
        and probe.get("message_lost_event_production") is True
        and probe.get("message_lost_supported") is True
        and probe.get("message_lost_taken") is True
        and probe.get("message_lost_wait_ready") is True
        and probe.get("message_lost_total_count") == 1
        and probe.get("message_lost_total_count_change") == 1
        and int(probe.get("message_lost_callback_events", 0)) >= 1
        and probe.get("payload_taken") is True
        and probe.get("second_payload_taken") is False
        and probe.get("received_payload") == "second"
        and probe.get("best_effort_gap_detected") is True
        and probe.get("best_effort_gap_received_frames") == 3
        and probe.get("best_effort_gap_total_count") == 1
        and probe.get("best_effort_gap_total_count_change") == 1
        and int(probe.get("best_effort_gap_callback_events", 0)) >= 1
        and probe.get("best_effort_gap_payload_count") == 3
        and probe.get("repair_suppressed_false_message_lost") is True
        and probe.get("repair_received_frames") == 4
        and probe.get("repair_observer_message_lost_taken") is False
        and probe.get("repair_observer_message_lost_total_count") == 0
        and probe.get("repair_observer_callback_events") == 0
        and probe.get("repair_observer_payload_count") == 4
        and probe.get("repair_reliable_payload_count") == 4
        and probe.get("reliable_history_exhaustion_detected") is True
        and probe.get("reliable_history_exhaustion_received_frames") == 3
        and probe.get("reliable_history_exhaustion_total_count") == 1
        and int(probe.get("reliable_history_exhaustion_callback_events", 0)) == 1
        and probe.get("unrecoverable_loss_notices_sent") == 1
        and probe.get("unrecoverable_loss_notices_received") == 1
        and probe.get("unrecoverable_loss_samples_reported") == 1
        and probe.get("reliable_history_exhaustion_payload_count") == 3
    )


def run_probe(*, root: Path, image: str, iterations: int = 1) -> dict[str, Any]:
    run_count = max(iterations, 1)
    command = (
        "source /opt/ros/jazzy/setup.bash && "
        "rm -rf /tmp/fq-message-lost-build /tmp/fq-message-lost-install "
        "/tmp/fq-message-lost-log && "
        "colcon --log-base /tmp/fq-message-lost-log build --base-paths ros2_ws/src "
        "--packages-select rmw_fleetqox_cpp --build-base /tmp/fq-message-lost-build "
        "--install-base /tmp/fq-message-lost-install --cmake-args -DCMAKE_BUILD_TYPE=Release "
        ">/dev/null && source /tmp/fq-message-lost-install/setup.bash && "
        "export FLEETQOX_RMW_DROP_SOURCE_SEQUENCES=3 && "
        "export FLEETQOX_RMW_MESSAGE_LOST_GAP_GRACE_MS=100 && "
        f"for i in $(seq 1 {run_count}); do "
        "/tmp/fq-message-lost-install/rmw_fleetqox_cpp/lib/rmw_fleetqox_cpp/"
        "fleetrmw_message_lost_event_probe || exit $?; done"
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
    ok_run_count = sum(1 for row in rows if message_lost_probe_ok(row))
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
        "message_lost_event_production": ok,
        "message_lost_event_scope": (
            "local_keep_last_overwrite_best_effort_gap_repair_suppression_"
            "and_reliable_history_exhaustion"
        ),
        "message_lost_repeated_event_claim": ok and run_count >= 5,
        "message_lost_total_count": probe.get("message_lost_total_count"),
        "message_lost_total_count_change": probe.get("message_lost_total_count_change"),
        "message_lost_callback_events": probe.get("message_lost_callback_events"),
        "best_effort_gap_detected": probe.get("best_effort_gap_detected"),
        "best_effort_gap_received_frames": probe.get("best_effort_gap_received_frames"),
        "best_effort_gap_total_count": probe.get("best_effort_gap_total_count"),
        "best_effort_gap_callback_events": probe.get("best_effort_gap_callback_events"),
        "repair_suppressed_false_message_lost": probe.get(
            "repair_suppressed_false_message_lost"
        ),
        "repair_received_frames": probe.get("repair_received_frames"),
        "repair_observer_message_lost_total_count": probe.get(
            "repair_observer_message_lost_total_count"
        ),
        "reliable_history_exhaustion_detected": probe.get(
            "reliable_history_exhaustion_detected"
        ),
        "reliable_history_exhaustion_received_frames": probe.get(
            "reliable_history_exhaustion_received_frames"
        ),
        "reliable_history_exhaustion_total_count": probe.get(
            "reliable_history_exhaustion_total_count"
        ),
        "unrecoverable_loss_notices_sent": probe.get(
            "unrecoverable_loss_notices_sent"
        ),
        "unrecoverable_loss_notices_received": probe.get(
            "unrecoverable_loss_notices_received"
        ),
        "unrecoverable_loss_samples_reported": probe.get(
            "unrecoverable_loss_samples_reported"
        ),
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
        default="results_rmw_socket/docker_message_lost_event_probe_summary.json",
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

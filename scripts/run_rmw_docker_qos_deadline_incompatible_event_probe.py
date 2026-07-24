"""Build and run the FleetRMW deadline-incompatible QoS event probe."""

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


SCHEMA_VERSION = "fleetrmw.docker_qos_deadline_incompatible_event_probe.v1"
DEFAULT_IMAGE = "localhost/fleetrmw/rmw-netem:jazzy"
RMW_QOS_POLICY_DEADLINE = 1 << 2


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


def qos_deadline_incompatible_probe_ok(probe: dict[str, Any]) -> bool:
    return (
        probe.get("status") == "ok"
        and probe.get("qos_deadline_incompatible_event_production") is True
        and probe.get("offered_taken") is True
        and probe.get("offered_wait_ready") is True
        and probe.get("offered_total_count") == 1
        and probe.get("offered_total_count_change") == 1
        and probe.get("offered_last_policy_kind") == RMW_QOS_POLICY_DEADLINE
        and int(probe.get("offered_callback_events", 0)) >= 1
        and probe.get("offered_incompatible_endpoint_matched_taken") is False
        and probe.get("offered_incompatible_endpoint_matched_wait_ready") is False
        and probe.get("requested_taken") is True
        and probe.get("requested_wait_ready") is True
        and probe.get("requested_total_count") == 1
        and probe.get("requested_total_count_change") == 1
        and probe.get("requested_last_policy_kind") == RMW_QOS_POLICY_DEADLINE
        and int(probe.get("requested_callback_events", 0)) >= 1
        and probe.get("requested_incompatible_endpoint_matched_taken") is False
        and probe.get("requested_incompatible_endpoint_matched_wait_ready") is False
        and probe.get("missing_offered_deadline_offered_event_claim") is True
        and probe.get("missing_offered_deadline_requested_event_claim") is True
        and probe.get("missing_offered_total_count") == 1
        and probe.get("missing_requested_total_count") == 1
        and probe.get("missing_offered_last_policy_kind") == RMW_QOS_POLICY_DEADLINE
        and probe.get("missing_requested_last_policy_kind") == RMW_QOS_POLICY_DEADLINE
        and probe.get("missing_offered_matched_taken") is False
        and probe.get("missing_requested_matched_taken") is False
        and probe.get("scenario_count") == 4
    )


def run_probe(*, root: Path, image: str, iterations: int = 1) -> dict[str, Any]:
    run_count = max(iterations, 1)
    command = (
        "source /opt/ros/jazzy/setup.bash && "
        "rm -rf /tmp/fq-qos-deadline-incompat-build "
        "/tmp/fq-qos-deadline-incompat-install /tmp/fq-qos-deadline-incompat-log && "
        "colcon --log-base /tmp/fq-qos-deadline-incompat-log build --base-paths ros2_ws/src "
        "--packages-select rmw_fleetqox_cpp --build-base /tmp/fq-qos-deadline-incompat-build "
        "--install-base /tmp/fq-qos-deadline-incompat-install "
        "--cmake-args -DCMAKE_BUILD_TYPE=Release >/dev/null && "
        "source /tmp/fq-qos-deadline-incompat-install/setup.bash && "
        f"for i in $(seq 1 {run_count}); do "
        "/tmp/fq-qos-deadline-incompat-install/rmw_fleetqox_cpp/lib/rmw_fleetqox_cpp/"
        "fleetrmw_qos_deadline_incompatible_event_probe || exit $?; done"
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
    ok_run_count = sum(1 for row in rows if qos_deadline_incompatible_probe_ok(row))
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
        "qos_deadline_incompatible_event_production": ok,
        "qos_deadline_incompatible_event_scope": "local_same_process_deadline_mismatch",
        "qos_deadline_incompatible_repeated_event_claim": ok and run_count >= 5,
        "qos_missing_offered_deadline_incompatible_event_claim": ok,
        "qos_missing_offered_deadline_incompatible_repeated_claim": (
            ok and run_count >= 5
        ),
        "offered_total_count": probe.get("offered_total_count"),
        "offered_total_count_change": probe.get("offered_total_count_change"),
        "offered_last_policy_kind": probe.get("offered_last_policy_kind"),
        "offered_callback_events": probe.get("offered_callback_events"),
        "offered_incompatible_endpoint_matched_taken": probe.get(
            "offered_incompatible_endpoint_matched_taken"
        ),
        "offered_incompatible_endpoint_matched_wait_ready": probe.get(
            "offered_incompatible_endpoint_matched_wait_ready"
        ),
        "requested_total_count": probe.get("requested_total_count"),
        "requested_total_count_change": probe.get("requested_total_count_change"),
        "requested_last_policy_kind": probe.get("requested_last_policy_kind"),
        "requested_callback_events": probe.get("requested_callback_events"),
        "requested_incompatible_endpoint_matched_taken": probe.get(
            "requested_incompatible_endpoint_matched_taken"
        ),
        "requested_incompatible_endpoint_matched_wait_ready": probe.get(
            "requested_incompatible_endpoint_matched_wait_ready"
        ),
        "missing_offered_deadline_offered_event_claim": probe.get(
            "missing_offered_deadline_offered_event_claim"
        ),
        "missing_offered_deadline_requested_event_claim": probe.get(
            "missing_offered_deadline_requested_event_claim"
        ),
        "missing_offered_total_count": probe.get("missing_offered_total_count"),
        "missing_requested_total_count": probe.get("missing_requested_total_count"),
        "missing_offered_last_policy_kind": probe.get(
            "missing_offered_last_policy_kind"
        ),
        "missing_requested_last_policy_kind": probe.get(
            "missing_requested_last_policy_kind"
        ),
        "scenario_count": probe.get("scenario_count"),
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
        default="results_rmw_socket/docker_qos_deadline_incompatible_event_probe_summary.json",
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

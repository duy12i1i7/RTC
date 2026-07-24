"""Build and repeat the complete Jazzy RMW QoS-event waitability matrix."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import subprocess
import sys
from typing import Any, Callable


ROOT = Path(__file__).resolve().parents[1]
SCHEMA_VERSION = "fleetrmw.docker_qos_event_waitability_matrix.v1"
DEFAULT_IMAGE = "localhost/fleetrmw/rmw-netem:jazzy"

EVENT_TYPES = [
    "RMW_EVENT_LIVELINESS_CHANGED",
    "RMW_EVENT_REQUESTED_DEADLINE_MISSED",
    "RMW_EVENT_REQUESTED_QOS_INCOMPATIBLE",
    "RMW_EVENT_MESSAGE_LOST",
    "RMW_EVENT_SUBSCRIPTION_INCOMPATIBLE_TYPE",
    "RMW_EVENT_SUBSCRIPTION_MATCHED",
    "RMW_EVENT_LIVELINESS_LOST",
    "RMW_EVENT_OFFERED_DEADLINE_MISSED",
    "RMW_EVENT_OFFERED_QOS_INCOMPATIBLE",
    "RMW_EVENT_PUBLISHER_INCOMPATIBLE_TYPE",
    "RMW_EVENT_PUBLICATION_MATCHED",
]


def parse_json_rows(stdout: str) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for line in stdout.splitlines():
        line = line.strip()
        if not line.startswith("{"):
            continue
        try:
            value = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(value, dict):
            rows.append(value)
    return rows


def all_true(row: dict[str, Any], *keys: str) -> bool:
    return all(row.get(key) is True for key in keys)


def deadline_ok(row: dict[str, Any]) -> bool:
    return (
        row.get("status") == "ok"
        and all_true(
            row,
            "offered_deadline_supported",
            "requested_deadline_supported",
            "wait_event_readiness",
            "publisher_wait_ready",
            "subscription_wait_ready",
            "publisher_taken",
            "subscription_taken",
        )
        and row.get("initial_publisher_wait_ready") is False
        and row.get("initial_subscription_wait_ready") is False
        and row.get("publisher_wait_ready_after_clear") is False
        and row.get("subscription_wait_ready_after_clear") is False
    )


def matched_ok(row: dict[str, Any]) -> bool:
    return (
        row.get("status") == "ok"
        and all_true(
            row,
            "publication_matched_supported",
            "subscription_matched_supported",
            "publication_connect_wait_ready",
            "publication_disconnect_wait_ready",
            "subscription_connect_wait_ready",
            "subscription_disconnect_wait_ready",
            "publication_connect_taken",
            "publication_disconnect_taken",
            "subscription_connect_taken",
            "subscription_disconnect_taken",
        )
        and row.get("publication_initial_wait_ready") is False
        and row.get("subscription_initial_wait_ready") is False
    )


def qos_incompatible_ok(row: dict[str, Any]) -> bool:
    return row.get("status") == "ok" and all_true(
        row,
        "offered_qos_incompatible_supported",
        "requested_qos_incompatible_supported",
        "offered_wait_ready",
        "requested_wait_ready",
        "durability_offered_wait_ready",
        "durability_requested_wait_ready",
        "offered_taken",
        "requested_taken",
        "durability_offered_taken",
        "durability_requested_taken",
    )


def deadline_incompatible_ok(row: dict[str, Any]) -> bool:
    return row.get("status") == "ok" and all_true(
        row,
        "offered_wait_ready",
        "requested_wait_ready",
        "offered_taken",
        "requested_taken",
    )


def type_incompatible_ok(row: dict[str, Any]) -> bool:
    return row.get("status") == "ok" and all_true(
        row,
        "publisher_incompatible_type_supported",
        "subscription_incompatible_type_supported",
        "publisher_wait_ready",
        "subscription_wait_ready",
        "publisher_taken",
        "subscription_taken",
    )


def liveliness_ok(row: dict[str, Any]) -> bool:
    return (
        row.get("status") == "ok"
        and all_true(
            row,
            "liveliness_lost_supported",
            "liveliness_changed_supported",
            "alive_wait_ready",
            "lost_wait_ready",
            "not_alive_wait_ready",
            "reassert_wait_ready",
            "alive_taken",
            "lost_taken",
            "not_alive_taken",
            "reassert_taken",
        )
        and row.get("initial_changed_wait_ready") is False
        and row.get("lost_initial_wait_ready") is False
    )


def message_lost_ok(row: dict[str, Any]) -> bool:
    return row.get("status") == "ok" and all_true(
        row,
        "message_lost_supported",
        "message_lost_wait_ready",
        "message_lost_taken",
    )


COMPONENTS: list[tuple[str, str, Callable[[dict[str, Any]], bool]]] = [
    ("fleetrmw_qos_event_probe", "fleetrmw.qos_event_probe.v1", deadline_ok),
    ("fleetrmw_matched_event_probe", "fleetrmw.matched_event_probe.v1", matched_ok),
    (
        "fleetrmw_qos_incompatible_event_probe",
        "fleetrmw.qos_incompatible_event_probe.v1",
        qos_incompatible_ok,
    ),
    (
        "fleetrmw_qos_deadline_incompatible_event_probe",
        "fleetrmw.qos_deadline_incompatible_event_probe.v1",
        deadline_incompatible_ok,
    ),
    (
        "fleetrmw_type_incompatible_event_probe",
        "fleetrmw.type_incompatible_event_probe.v1",
        type_incompatible_ok,
    ),
    (
        "fleetrmw_liveliness_event_probe",
        "fleetrmw.liveliness_event_probe.v1",
        liveliness_ok,
    ),
    (
        "fleetrmw_message_lost_event_probe",
        "fleetrmw.message_lost_event_probe.v1",
        message_lost_ok,
    ),
]


def run_probe(*, image: str, iterations: int) -> dict[str, Any]:
    run_count = max(iterations, 1)
    executable_dir = (
        "/tmp/fq-event-matrix-install/rmw_fleetqox_cpp/lib/rmw_fleetqox_cpp"
    )
    component_commands = " && ".join(
        f"{executable_dir}/{executable}" for executable, _, _ in COMPONENTS
    )
    command = (
        "source /opt/ros/jazzy/setup.bash && "
        "rm -rf /tmp/fq-event-matrix-build /tmp/fq-event-matrix-install "
        "/tmp/fq-event-matrix-log && "
        "colcon --log-base /tmp/fq-event-matrix-log build --base-paths ros2_ws/src "
        "--packages-select rmw_fleetqox_cpp "
        "--build-base /tmp/fq-event-matrix-build "
        "--install-base /tmp/fq-event-matrix-install "
        "--cmake-args -DCMAKE_BUILD_TYPE=Release >/dev/null && "
        "source /tmp/fq-event-matrix-install/setup.bash && "
        f"for i in $(seq 1 {run_count}); do {component_commands} || exit $?; done"
    )
    completed = subprocess.run(
        [
            "docker",
            "run",
            "--rm",
            "--entrypoint",
            "bash",
            "-v",
            f"{ROOT}:/work",
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
    expected_schemas = [schema for _, schema, _ in COMPONENTS]
    parsed_rows = [
        row for row in parse_json_rows(completed.stdout)
        if row.get("schema_version") in expected_schemas
    ]
    matrix_runs: list[dict[str, Any]] = []
    component_count = len(COMPONENTS)
    for index in range(run_count):
        rows = parsed_rows[index * component_count:(index + 1) * component_count]
        ordered = [row.get("schema_version") for row in rows] == expected_schemas
        component_results = {
            schema: validator(row)
            for row, (_, schema, validator) in zip(rows, COMPONENTS)
        }
        ok = ordered and len(rows) == component_count and all(component_results.values())
        matrix_runs.append(
            {
                "iteration": index + 1,
                "status": "ok" if ok else "failed",
                "component_results": component_results,
            }
        )
    ok_run_count = sum(run.get("status") == "ok" for run in matrix_runs)
    ok = (
        completed.returncode == 0
        and len(parsed_rows) == run_count * component_count
        and ok_run_count == run_count
    )
    return {
        "schema_version": SCHEMA_VERSION,
        "status": "ok" if ok else "failed",
        "image": image,
        "returncode": completed.returncode,
        "run_count": run_count,
        "ok_run_count": ok_run_count,
        "component_count": component_count,
        "component_execution_count": len(parsed_rows),
        "event_type_count": len(EVENT_TYPES),
        "event_types_covered": EVENT_TYPES,
        "waitability_scope": "all_11_jazzy_rmw_event_types_local_production_wait_take",
        "qos_event_waitability_matrix_claim": ok,
        "full_qos_event_waitable_readiness_claim": ok,
        "qos_event_waitability_repeated_claim": ok and run_count >= 5,
        "runs": matrix_runs,
        "component_rows": parsed_rows,
        "stdout": completed.stdout,
        "stderr": completed.stderr,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--image", default=DEFAULT_IMAGE)
    parser.add_argument("--iterations", type=int, default=1)
    parser.add_argument(
        "--summary-json",
        default="results_rmw_socket/docker_qos_event_waitability_matrix_summary.json",
    )
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    summary = run_probe(image=args.image, iterations=args.iterations)
    output = ROOT / args.summary_json
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(summary, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    if args.json:
        print(json.dumps(summary, sort_keys=True))
    else:
        print(f"status={summary['status']}")
    return 0 if summary["status"] == "ok" else 1


if __name__ == "__main__":
    raise SystemExit(main())

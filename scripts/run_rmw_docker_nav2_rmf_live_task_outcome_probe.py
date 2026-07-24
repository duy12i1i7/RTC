#!/usr/bin/env python3
"""Repeat live Nav2/RMF result submission from the active ROS client process."""

from __future__ import annotations

import argparse
import gc
import json
from pathlib import Path
import time
from typing import Any

try:
    from scripts.run_rmw_docker_router_nav2_rmf_action_workload import (
        DEFAULT_IMAGE,
        live_task_outcome_service_ok,
        live_task_outcome_submission_ok,
        run_probe as run_workload,
        task_outcomes_ok,
    )
except ModuleNotFoundError:
    from run_rmw_docker_router_nav2_rmf_action_workload import (
        DEFAULT_IMAGE,
        live_task_outcome_service_ok,
        live_task_outcome_submission_ok,
        run_probe as run_workload,
        task_outcomes_ok,
    )


ROOT = Path(__file__).resolve().parents[1]
SCHEMA_VERSION = "fleetrmw.docker_nav2_rmf_live_task_outcome_probe.v1"


def run_ok(row: dict[str, Any]) -> bool:
    client = row.get("client", {})
    service = row.get("gateway_service", {})
    return (
        row.get("status") == "ok"
        and row.get("nav2_upstream") is True
        and row.get("rmf_upstream") is True
        and row.get("lifecycle_transport") is True
        and row.get("task_outcome_gateway_submission_performed") is True
        and row.get("same_process_live_ros_result_submission_claim") is True
        and row.get("task_outcome_submission_session_reuse_claim") is True
        and row.get("gateway_netem_configured_both_containers") is True
        and row.get("gateway_qlog_file_count", 0) >= 2
        and row.get("gateway_qlog_total_bytes", 0) > 0
        and row.get("production_quic_backend_claim") is False
        and row.get("production_readiness") is False
        and task_outcomes_ok(client, expected_gateway_submission=True)
        and live_task_outcome_submission_ok(client)
        and live_task_outcome_service_ok(service)
    )


def evidence_run_ok(row: dict[str, Any]) -> bool:
    """Validate one compact canonical evidence row."""

    client = {
        "application_outcomes": row.get("application_outcomes"),
        "task_outcome_gateway_submission_performed": row.get(
            "task_outcome_gateway_submission_performed"
        ),
        "task_outcome_gateway_submission": row.get(
            "task_outcome_gateway_submission"
        ),
        "process_id": row.get("client_process_id"),
        "rclpy_context_active_during_gateway_submission": row.get(
            "rclpy_context_active_during_gateway_submission"
        ),
        "ros_node_alive_during_gateway_submission": row.get(
            "ros_node_alive_during_gateway_submission"
        ),
    }
    router = row.get("router", {})
    return (
        row.get("status") == "ok"
        and row.get("nav2_upstream") is True
        and row.get("rmf_upstream") is True
        and row.get("navigation_batch") is True
        and row.get("rmf_batch") is True
        and row.get("lifecycle_transport") is True
        and row.get("same_process_live_ros_result_submission_claim") is True
        and row.get("task_outcome_submission_session_reuse_claim") is True
        and row.get("gateway_ready") is True
        and row.get("gateway_exit_code") == 0
        and row.get("gateway_netem_configured_both_containers") is True
        and row.get("gateway_qlog_file_count", 0) >= 2
        and row.get("gateway_qlog_total_bytes", 0) > 0
        and row.get("client_returncode") == 0
        and row.get("server_returncode") == 0
        and row.get("router_returncode") == 0
        and router.get("status") == "ok"
        and int(router.get("service_frames", 0)) >= 106
        and int(router.get("service_forwarded", 0)) >= 106
        and task_outcomes_ok(client, expected_gateway_submission=True)
        and live_task_outcome_submission_ok(client)
        and live_task_outcome_service_ok(row.get("gateway_service", {}))
    )


def compact_run(index: int, row: dict[str, Any]) -> dict[str, Any]:
    client = row.get("client", {})
    router = row.get("router", {})
    return {
        "index": index,
        "status": "ok" if run_ok(row) else "failed",
        "schema_version": row.get("schema_version"),
        "nav2_upstream": row.get("nav2_upstream"),
        "rmf_upstream": row.get("rmf_upstream"),
        "navigation_batch": row.get("navigation_batch"),
        "rmf_batch": row.get("rmf_batch"),
        "lifecycle_transport": row.get("lifecycle_transport"),
        "task_outcome_gateway_submission_performed": row.get(
            "task_outcome_gateway_submission_performed"
        ),
        "same_process_live_ros_result_submission_claim": row.get(
            "same_process_live_ros_result_submission_claim"
        ),
        "task_outcome_submission_session_reuse_claim": row.get(
            "task_outcome_submission_session_reuse_claim"
        ),
        "gateway_ready": row.get("gateway_ready"),
        "gateway_exit_code": row.get("gateway_exit_code"),
        "gateway_netem_configured_both_containers": row.get(
            "gateway_netem_configured_both_containers"
        ),
        "gateway_qlog_file_count": row.get("gateway_qlog_file_count"),
        "gateway_qlog_total_bytes": row.get("gateway_qlog_total_bytes"),
        "client_process_id": client.get("process_id"),
        "rclpy_context_active_during_gateway_submission": client.get(
            "rclpy_context_active_during_gateway_submission"
        ),
        "ros_node_alive_during_gateway_submission": client.get(
            "ros_node_alive_during_gateway_submission"
        ),
        "application_outcomes": client.get("application_outcomes", []),
        "task_outcome_gateway_submission": client.get(
            "task_outcome_gateway_submission", {}
        ),
        "gateway_service": row.get("gateway_service", {}),
        "router": {
            key: router.get(key)
            for key in (
                "status",
                "service_frames",
                "service_forwarded",
                "graph_services",
                "graph_clients",
            )
        },
        "client_returncode": row.get("client_returncode"),
        "server_returncode": row.get("server_returncode"),
        "router_returncode": row.get("router_returncode"),
        "client_stderr": "" if run_ok(row) else row.get("client_stderr", ""),
        "gateway_service_logs": (
            "" if run_ok(row) else row.get("gateway_service_logs", "")
        ),
    }


def run_probe(
    *,
    root: Path,
    image: str,
    iterations: int,
    upstream_concurrency: int,
    cooldown_s: float = 2.0,
) -> dict[str, Any]:
    run_count = max(1, iterations)
    concurrency = max(1, upstream_concurrency)
    runs: list[dict[str, Any]] = []
    for index in range(1, run_count + 1):
        result = run_workload(
            root=root,
            image=image,
            upstream_concurrency=concurrency,
            live_task_outcome_gateway=True,
        )
        runs.append(compact_run(index, result))
        del result
        gc.collect()
        if index < run_count and cooldown_s > 0.0:
            time.sleep(cooldown_s)
    successful_runs = sum(row.get("status") == "ok" for row in runs)
    status = (
        "ok"
        if len(runs) == successful_runs == run_count
        else "docker_unavailable"
        if runs and all(
            row.get("schema_version") is not None
            and row.get("status") == "failed"
            for row in runs
        )
        and result.get("status") == "docker_unavailable"
        else "failed"
    )
    return {
        "schema_version": SCHEMA_VERSION,
        "status": status,
        "run_count": run_count,
        "successful_runs": successful_runs,
        "failed_run_count": run_count - successful_runs,
        "upstream_concurrency": concurrency,
        "cooldown_s": max(0.0, cooldown_s),
        "real_ros2_nav2_rmf_workload": True,
        "same_process_live_ros_result_submission_claim": status == "ok",
        "actual_terminal_result_mapping_claim": status == "ok",
        "mutual_tls_client_authentication_required": True,
        "publisher_identity_uri_san_binding_required": True,
        "task_outcome_submission_session_reuse_claim": status == "ok",
        "netem_configured_both_gateway_and_ros_client": status == "ok",
        "production_quic_backend_claim": False,
        "production_readiness": False,
        "runs": runs,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--image", default=DEFAULT_IMAGE)
    parser.add_argument("--iterations", type=int, default=5)
    parser.add_argument("--upstream-concurrency", type=int, default=8)
    parser.add_argument("--cooldown-s", type=float, default=2.0)
    parser.add_argument(
        "--summary-json",
        default=(
            "results_rmw_socket/"
            "docker_nav2_rmf_live_task_outcome_probe_summary.json"
        ),
    )
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    summary = run_probe(
        root=ROOT,
        image=args.image,
        iterations=args.iterations,
        upstream_concurrency=args.upstream_concurrency,
        cooldown_s=max(0.0, args.cooldown_s),
    )
    path = ROOT / args.summary_json
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(summary, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    if args.json:
        print(json.dumps(summary, sort_keys=True))
    else:
        print("fleetrmw-nav2-rmf-live-task-outcome")
        print(f"  status: {summary['status']}")
        print(
            f"  successful_runs: "
            f"{summary['successful_runs']}/{summary['run_count']}"
        )
    return 0 if summary["status"] == "ok" else 1


if __name__ == "__main__":
    raise SystemExit(main())

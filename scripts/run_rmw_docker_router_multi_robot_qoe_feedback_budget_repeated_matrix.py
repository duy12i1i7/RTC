"""Repeat subscriber-QoE-driven fleet budgeting under stochastic netem loss."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.run_rmw_docker_router_multi_robot_budgeted_fleet_plan_probe import (
    DEFAULT_IMAGE,
    DEFAULT_TOPIC_PREFIX,
    run_probe,
)


SCHEMA_VERSION = "fleetrmw.rmw_router_multi_robot_qoe_feedback_budget_repeated_matrix.v1"
SEED_SEMANTICS = (
    "repetition_id_only; current tc netem image does not expose deterministic "
    "random seeding"
)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--image", default=DEFAULT_IMAGE)
    parser.add_argument("--robot-count", type=int, default=4)
    parser.add_argument("--protected-robot-budget", type=int, default=2)
    parser.add_argument("--topic-prefix", default=f"{DEFAULT_TOPIC_PREFIX}_qoe_feedback_matrix")
    parser.add_argument("--deadline-ms", type=int, default=250)
    parser.add_argument("--primary-profile", default="roaming")
    parser.add_argument("--backup-profile", default="wifi")
    parser.add_argument("--loss-percents", default="0.02")
    parser.add_argument("--repetitions", default="7,13")
    parser.add_argument("--fail-on-row-failure", action="store_true")
    parser.add_argument(
        "--summary-json",
        default=(
            "results_rmw_socket/"
            "docker_router_multi_robot_qoe_feedback_budget_repeated_matrix_summary.json"
        ),
    )
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    root = ROOT
    robot_count = max(args.robot_count, 1)
    protected_budget = min(max(args.protected_robot_budget, 0), robot_count)
    repetitions = parse_ints(args.repetitions)
    loss_percents = parse_floats(args.loss_percents)
    rows: list[dict[str, Any]] = []
    for loss_percent in loss_percents:
        for repetition_id in repetitions:
            result = run_probe(
                root=root,
                image=args.image,
                robot_count=robot_count,
                protected_robot_budget=protected_budget,
                topic_prefix=f"{args.topic_prefix}/rep-{repetition_id}",
                deadline_ms=max(args.deadline_ms, 1),
                primary_profile=args.primary_profile,
                backup_profile=args.backup_profile,
                loss_percent=loss_percent,
                qoe_feedback=True,
            )
            rows.append({
                "repetition_id": repetition_id,
                "loss_percent": loss_percent,
                "status": result.get("status", "failed"),
                "evidence_ok": result.get("status") == "ok",
                "robots_ok": result.get("robots_ok", 0),
                "protected_robots": result.get("protected_robots", []),
                "max_latency_ms": result.get("max_latency_ms", 0.0),
                "deadline_success_jain_index": result.get(
                    "deadline_success_jain_index", 0.0
                ),
                "actual_path_transmissions": result.get("actual_path_transmissions", 0),
                "full_redundancy_path_transmissions": result.get(
                    "full_redundancy_path_transmissions", 0
                ),
                "path_transmission_reduction_ratio": result.get(
                    "path_transmission_reduction_ratio", 0.0
                ),
                "total_nack_retransmissions": result.get(
                    "total_nack_retransmissions", 0
                ),
                "result": result,
            })

    ok_rows = [row for row in rows if row["evidence_ok"]]
    status = "failed"
    if rows:
        status = "ok" if len(ok_rows) == len(rows) else "partial"
        if not ok_rows:
            status = "failed"
    summary = {
        "schema_version": SCHEMA_VERSION,
        "status": status,
        "image": args.image,
        "robot_count": robot_count,
        "protected_robot_budget": protected_budget,
        "deadline_ms": max(args.deadline_ms, 1),
        "primary_profile": args.primary_profile,
        "backup_profile": args.backup_profile,
        "loss_percents": loss_percents,
        "repetitions": repetitions,
        "seed_semantics": SEED_SEMANTICS,
        "run_count": len(rows),
        "ok_run_count": len(ok_rows),
        "failed_run_count": len(rows) - len(ok_rows),
        "max_observed_latency_ms": max(
            (float(row["max_latency_ms"]) for row in rows), default=0.0
        ),
        "min_deadline_success_jain_index": min(
            (float(row["deadline_success_jain_index"]) for row in rows), default=0.0
        ),
        "total_actual_path_transmissions": sum(
            int(row["actual_path_transmissions"]) for row in rows
        ),
        "total_full_redundancy_path_transmissions": sum(
            int(row["full_redundancy_path_transmissions"]) for row in rows
        ),
        "total_nack_retransmissions": sum(
            int(row["total_nack_retransmissions"]) for row in rows
        ),
        "rows": rows,
    }
    output = root / args.summary_json
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(summary, sort_keys=True) + "\n", encoding="utf-8")

    if args.json:
        print(json.dumps(summary, sort_keys=True))
    else:
        print("fleetrmw-router-multi-robot-qoe-feedback-budget-repeated-matrix")
        print(f"  status: {status}")
        print(f"  ok/runs: {len(ok_rows)}/{len(rows)}")
        print(f"  max_observed_latency_ms: {summary['max_observed_latency_ms']:.3f}")
        print(f"  total_actual_path_transmissions: {summary['total_actual_path_transmissions']}")
    if args.fail_on_row_failure and status != "ok":
        return 1
    return 0 if status in ("ok", "partial") else 1


def parse_ints(value: str) -> list[int]:
    result = [int(item.strip()) for item in value.split(",") if item.strip()]
    if not result:
        raise ValueError("at least one repetition id is required")
    return result


def parse_floats(value: str) -> list[float]:
    result = [max(0.0, float(item.strip())) for item in value.split(",") if item.strip()]
    if not result:
        raise ValueError("at least one loss percent is required")
    return result


if __name__ == "__main__":
    raise SystemExit(main())

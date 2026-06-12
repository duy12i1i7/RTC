"""Measure live QoE protection migration as the ROS 2 fleet grows."""

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


SCHEMA_VERSION = "fleetrmw.rmw_router_qoe_protection_migration_scale_matrix.v1"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--image", default=DEFAULT_IMAGE)
    parser.add_argument("--robot-counts", default="4,8")
    parser.add_argument(
        "--topic-prefix", default=f"{DEFAULT_TOPIC_PREFIX}_qoe_migration_scale"
    )
    parser.add_argument("--deadline-ms", type=int, default=250)
    parser.add_argument("--primary-profile", default="roaming")
    parser.add_argument("--backup-profile", default="wifi")
    parser.add_argument("--loss-percent", type=float, default=0.02)
    parser.add_argument("--sequential-min-samples", type=int, default=3)
    parser.add_argument("--sequential-max-samples", type=int, default=5)
    parser.add_argument("--fail-on-row-failure", action="store_true")
    parser.add_argument(
        "--summary-json",
        default=(
            "results_rmw_socket/"
            "docker_router_qoe_protection_migration_scale_matrix_summary.json"
        ),
    )
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    robot_counts = parse_robot_counts(args.robot_counts)
    rows: list[dict[str, Any]] = []
    for robot_count in robot_counts:
        protected_budget = max(1, robot_count // 2)
        result = run_probe(
            root=ROOT,
            image=args.image,
            robot_count=robot_count,
            protected_robot_budget=protected_budget,
            topic_prefix=f"{args.topic_prefix}/robots-{robot_count}",
            deadline_ms=max(args.deadline_ms, 1),
            primary_profile=args.primary_profile,
            backup_profile=args.backup_profile,
            loss_percent=max(args.loss_percent, 0.0),
            qoe_migration=True,
            event_triggered_feedback=True,
            sequential_qoe_feedback=True,
            sequential_min_samples=max(args.sequential_min_samples, 1),
            sequential_max_samples=max(args.sequential_max_samples, 1),
        )
        expected_epoch_sets = [
            [f"robot_{index:04d}" for index in range(protected_budget)],
            [
                f"robot_{index:04d}"
                for index in range(robot_count - protected_budget, robot_count)
            ],
        ]
        observed_epoch_sets = result.get("controller_epoch_protected_robots", [])
        migration_ok = observed_epoch_sets == expected_epoch_sets
        evidence_ok = result.get("status") == "ok" and migration_ok
        rows.append({
            "robot_count": robot_count,
            "protected_robot_budget": protected_budget,
            "status": "ok" if evidence_ok else "failed",
            "evidence_ok": evidence_ok,
            "migration_ok": migration_ok,
            "expected_epoch_protected_robots": expected_epoch_sets,
            "observed_epoch_protected_robots": observed_epoch_sets,
            "robots_ok": result.get("robots_ok", 0),
            "sequential_qoe_epochs": result.get("sequential_qoe_epochs", []),
            "first_sequential_samples": result.get("first_sequential_samples", 0),
            "second_sequential_samples": result.get("second_sequential_samples", 0),
            "final_sequential_samples": result.get("final_sequential_samples", 0),
            "total_source_frames": result.get("total_source_frames", 0),
            "publisher_barrier_ready": result.get("publisher_barrier_ready", False),
            "publisher_barrier_wait_ms": result.get("publisher_barrier_wait_ms", 0.0),
            "max_latency_ms": result.get("max_latency_ms", 0.0),
            "deadline_success_jain_index": result.get(
                "deadline_success_jain_index", 0.0
            ),
            "max_feedback_epoch_wait_ms": result.get(
                "max_feedback_epoch_wait_ms", 0.0
            ),
            "max_controller_actuation_ms": result.get(
                "max_controller_actuation_ms", 0.0
            ),
            "max_epoch_convergence_ms": result.get(
                "max_epoch_convergence_ms", 0.0
            ),
            "network_transition_actuation_ms": result.get(
                "network_transition_actuation_ms", 0.0
            ),
            "protected_set_churn": result.get("protected_set_churn", 0),
            "protection_migration_count": result.get(
                "protection_migration_count", 0
            ),
            "actual_path_transmissions": result.get(
                "actual_path_transmissions", 0
            ),
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
    status = "ok" if rows and len(ok_rows) == len(rows) else "failed"
    total_actual = sum(int(row["actual_path_transmissions"]) for row in rows)
    total_full = sum(int(row["full_redundancy_path_transmissions"]) for row in rows)
    summary = {
        "schema_version": SCHEMA_VERSION,
        "status": status,
        "image": args.image,
        "robot_counts": robot_counts,
        "deadline_ms": max(args.deadline_ms, 1),
        "primary_profile": args.primary_profile,
        "backup_profile": args.backup_profile,
        "loss_percent": max(args.loss_percent, 0.0),
        "sequential_min_samples": max(args.sequential_min_samples, 1),
        "sequential_max_samples": max(args.sequential_max_samples, 1),
        "run_count": len(rows),
        "ok_run_count": len(ok_rows),
        "failed_run_count": len(rows) - len(ok_rows),
        "max_observed_latency_ms": max(
            (float(row["max_latency_ms"]) for row in rows), default=0.0
        ),
        "min_deadline_success_jain_index": min(
            (float(row["deadline_success_jain_index"]) for row in rows),
            default=0.0,
        ),
        "max_feedback_epoch_wait_ms": max(
            (float(row["max_feedback_epoch_wait_ms"]) for row in rows),
            default=0.0,
        ),
        "max_controller_actuation_ms": max(
            (float(row["max_controller_actuation_ms"]) for row in rows),
            default=0.0,
        ),
        "max_epoch_convergence_ms": max(
            (float(row["max_epoch_convergence_ms"]) for row in rows),
            default=0.0,
        ),
        "max_network_transition_actuation_ms": max(
            (float(row["network_transition_actuation_ms"]) for row in rows),
            default=0.0,
        ),
        "max_publisher_barrier_wait_ms": max(
            (float(row["publisher_barrier_wait_ms"]) for row in rows),
            default=0.0,
        ),
        "total_protected_set_churn": sum(
            int(row["protected_set_churn"]) for row in rows
        ),
        "total_protection_migrations": sum(
            int(row["protection_migration_count"]) for row in rows
        ),
        "total_actual_path_transmissions": total_actual,
        "total_full_redundancy_path_transmissions": total_full,
        "aggregate_path_transmission_reduction_ratio": (
            1.0 - total_actual / total_full if total_full else 0.0
        ),
        "total_nack_retransmissions": sum(
            int(row["total_nack_retransmissions"]) for row in rows
        ),
        "rows": rows,
    }
    output = ROOT / args.summary_json
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(summary, sort_keys=True) + "\n", encoding="utf-8")

    if args.json:
        print(json.dumps(summary, sort_keys=True))
    else:
        print("fleetrmw-router-qoe-protection-migration-scale-matrix")
        print(f"  status: {status}")
        print(f"  ok/runs: {len(ok_rows)}/{len(rows)}")
        print(f"  max_epoch_convergence_ms: {summary['max_epoch_convergence_ms']:.3f}")
        print(f"  max_controller_actuation_ms: {summary['max_controller_actuation_ms']:.3f}")
        print(
            "  aggregate_path_transmission_reduction_ratio: "
            f"{summary['aggregate_path_transmission_reduction_ratio']:.6f}"
        )
    if args.fail_on_row_failure and status != "ok":
        return 1
    return 0 if status == "ok" else 1


def parse_robot_counts(value: str) -> list[int]:
    result = [int(item.strip()) for item in value.split(",") if item.strip()]
    if not result or any(item <= 1 for item in result):
        raise ValueError("robot counts must contain values greater than one")
    return result


if __name__ == "__main__":
    raise SystemExit(main())

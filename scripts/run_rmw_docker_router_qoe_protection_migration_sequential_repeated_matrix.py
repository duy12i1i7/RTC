"""Repeat sequential-QoE protection migration under stochastic netem loss."""

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


SCHEMA_VERSION = (
    "fleetrmw.rmw_router_qoe_protection_migration_sequential_repeated_matrix.v1"
)
SEED_SEMANTICS = (
    "repetition_id_only; current tc netem image does not expose deterministic "
    "random seeding"
)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--image", default=DEFAULT_IMAGE)
    parser.add_argument("--robot-counts", default="4,8")
    parser.add_argument("--repetitions", default="7,13")
    parser.add_argument("--loss-percents", default="0.02")
    parser.add_argument(
        "--topic-prefix",
        default=f"{DEFAULT_TOPIC_PREFIX}_qoe_migration_sequential_repeated",
    )
    parser.add_argument("--deadline-ms", type=int, default=250)
    parser.add_argument("--primary-profile", default="roaming")
    parser.add_argument("--backup-profile", default="wifi")
    parser.add_argument("--sequential-min-samples", type=int, default=3)
    parser.add_argument("--sequential-max-samples", type=int, default=5)
    parser.add_argument("--sequential-confidence-level", type=float, default=0.95)
    parser.add_argument("--sequential-min-sample-stddev", type=float, default=0.005)
    parser.add_argument("--sequential-separation-margin", type=float, default=0.01)
    parser.add_argument("--sequential-migration-hysteresis", type=float, default=0.01)
    parser.add_argument("--sequential-confidence-fallback", action="store_true")
    parser.add_argument("--sequential-fallback-extra-robots", type=int, default=0)
    parser.add_argument("--fallback-recovery-samples", type=int, default=1)
    parser.add_argument("--fail-on-row-failure", action="store_true")
    parser.add_argument(
        "--summary-json",
        default=(
            "results_rmw_socket/"
            "docker_router_qoe_protection_migration_sequential_repeated_matrix_summary.json"
        ),
    )
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    robot_counts = parse_ints(args.robot_counts, minimum=2)
    repetitions = parse_ints(args.repetitions, minimum=0)
    loss_percents = parse_floats(args.loss_percents)
    rows: list[dict[str, Any]] = []
    for robot_count in robot_counts:
        protected_budget = max(1, robot_count // 2)
        expected_epoch_sets = [
            [f"robot_{index:04d}" for index in range(protected_budget)],
            [
                f"robot_{index:04d}"
                for index in range(robot_count - protected_budget, robot_count)
            ],
        ]
        for loss_percent in loss_percents:
            for repetition_id in repetitions:
                result = run_probe(
                    root=ROOT,
                    image=args.image,
                    robot_count=robot_count,
                    protected_robot_budget=protected_budget,
                    topic_prefix=(
                        f"{args.topic_prefix}/robots-{robot_count}/"
                        f"loss-{loss_percent:g}/rep-{repetition_id}"
                    ),
                    deadline_ms=max(args.deadline_ms, 1),
                    primary_profile=args.primary_profile,
                    backup_profile=args.backup_profile,
                    loss_percent=max(loss_percent, 0.0),
                    qoe_migration=True,
                    event_triggered_feedback=True,
                    sequential_qoe_feedback=True,
                    sequential_min_samples=max(args.sequential_min_samples, 1),
                    sequential_max_samples=max(args.sequential_max_samples, 1),
                    sequential_confidence_level=args.sequential_confidence_level,
                    sequential_min_sample_stddev=max(args.sequential_min_sample_stddev, 0.0),
                    sequential_separation_margin=max(args.sequential_separation_margin, 0.0),
                    sequential_migration_hysteresis=max(args.sequential_migration_hysteresis, 0.0),
                    sequential_confidence_fallback=args.sequential_confidence_fallback,
                    sequential_fallback_extra_robots=max(
                        args.sequential_fallback_extra_robots,
                        0,
                    ),
                    fallback_recovery_samples=max(args.fallback_recovery_samples, 1),
                )
                observed_epoch_sets = result.get("controller_epoch_protected_robots", [])
                migration_ok = observed_epoch_sets == expected_epoch_sets
                confidence_epoch_count = sum(
                    1
                    for epoch in result.get("sequential_qoe_epochs", [])
                    if epoch.get("confidence_separated") is True
                )
                sequential_epoch_count = len(result.get("sequential_qoe_epochs", []))
                all_epochs_confident = (
                    sequential_epoch_count > 0
                    and confidence_epoch_count == sequential_epoch_count
                )
                evidence_ok = (
                    result.get("status") == "ok"
                    and migration_ok
                    and all_epochs_confident
                )
                failure_mode = classify_failure(
                    result,
                    migration_ok=migration_ok,
                    all_epochs_confident=all_epochs_confident,
                )
                confidence_fallback_applied = bool(
                    result.get("confidence_fallback_applied", False)
                )
                fallback_recovery = result.get("fallback_recovery", {})
                if not isinstance(fallback_recovery, dict):
                    fallback_recovery = {}
                fallback_repair = result.get("fallback_repair", {})
                if not isinstance(fallback_repair, dict):
                    fallback_repair = {}
                qoe_recovery_ok = (
                    "returncode" not in result
                    and result.get("publisher_barrier_ready") is not False
                    and result.get("feedback_ready") is not False
                    and result.get("second_feedback_ready") is not False
                    and migration_ok
                    and fallback_recovery.get("status") == "ok"
                    and fallback_repair.get("status") != "unresolved"
                )
                rows.append({
                    "robot_count": robot_count,
                    "protected_robot_budget": protected_budget,
                    "loss_percent": loss_percent,
                    "repetition_id": repetition_id,
                    "status": "ok" if evidence_ok else "failed",
                    "evidence_ok": evidence_ok,
                    "strict_evidence_ok": evidence_ok,
                    "qoe_recovery_ok": qoe_recovery_ok,
                    "failure_mode": failure_mode,
                    "confidence_fallback_applied": confidence_fallback_applied,
                    "confidence_fallback_count": len(
                        result.get("confidence_fallback_actuations", [])
                    ),
                    "feedback_safe_mode_count": result.get(
                        "feedback_safe_mode_count",
                        0,
                    ),
                    "fallback_recovery_status": (
                        fallback_recovery.get("status", "not_applicable")
                    ),
                    "fallback_recovery_robots_ok": (
                        fallback_recovery.get("robots_ok", 0)
                    ),
                    "fallback_recovery_robot_count": (
                        fallback_recovery.get("robot_count", 0)
                    ),
                    "fallback_repair_status": fallback_repair.get(
                        "status",
                        "not_applicable",
                    ),
                    "fallback_repair_deadline_ok_robot_count": fallback_repair.get(
                        "deadline_ok_robot_count",
                        0,
                    ),
                    "fallback_repair_delivered_robot_count": fallback_repair.get(
                        "delivered_robot_count",
                        0,
                    ),
                    "fallback_repair_unresolved_robot_count": fallback_repair.get(
                        "unresolved_robot_count",
                        0,
                    ),
                    "fallback_repair_explicit_candidate_count": fallback_repair.get(
                        "explicit_candidate_count",
                        0,
                    ),
                    "fallback_repair_missing_sequence_count": fallback_repair.get(
                        "missing_sequence_count",
                        0,
                    ),
                    "fallback_repair_late_sequence_count": fallback_repair.get(
                        "late_sequence_count",
                        0,
                    ),
                    "fallback_repair_evidence_robot_count": fallback_repair.get(
                        "repair_evidence_robot_count",
                        0,
                    ),
                    "fallback_repair_nack_retransmission_count": fallback_repair.get(
                        "nack_retransmission_count",
                        0,
                    ),
                    "fallback_repair_idle_ack_nack_count": fallback_repair.get(
                        "idle_repair_ack_nack_count",
                        0,
                    ),
                    "migration_ok": migration_ok,
                    "all_epochs_confident": all_epochs_confident,
                    "confidence_epoch_count": confidence_epoch_count,
                    "sequential_epoch_count": sequential_epoch_count,
                    "confidence_epoch_ratio": (
                        confidence_epoch_count / sequential_epoch_count
                        if sequential_epoch_count else 0.0
                    ),
                    "sample_counts": [
                        int(epoch.get("sample_count", 0))
                        for epoch in result.get("sequential_qoe_epochs", [])
                    ],
                    "observed_epoch_protected_robots": observed_epoch_sets,
                    "robots_ok": result.get("robots_ok", 0),
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
    total_actual = sum(int(row["actual_path_transmissions"]) for row in rows)
    total_full = sum(int(row["full_redundancy_path_transmissions"]) for row in rows)
    status = "ok" if rows and len(ok_rows) == len(rows) else "partial"
    if rows and not ok_rows:
        status = "failed"
    summary = {
        "schema_version": SCHEMA_VERSION,
        "status": status,
        "image": args.image,
        "robot_counts": robot_counts,
        "repetitions": repetitions,
        "loss_percents": loss_percents,
        "seed_semantics": SEED_SEMANTICS,
        "deadline_ms": max(args.deadline_ms, 1),
        "primary_profile": args.primary_profile,
        "backup_profile": args.backup_profile,
        "sequential_min_samples": max(args.sequential_min_samples, 1),
        "sequential_max_samples": max(args.sequential_max_samples, 1),
        "sequential_confidence_level": min(
            0.999999,
            max(0.000001, args.sequential_confidence_level),
        ),
        "sequential_min_sample_stddev": max(args.sequential_min_sample_stddev, 0.0),
        "sequential_separation_margin": max(args.sequential_separation_margin, 0.0),
        "sequential_migration_hysteresis": max(args.sequential_migration_hysteresis, 0.0),
        "sequential_confidence_fallback": args.sequential_confidence_fallback,
        "sequential_fallback_extra_robots": max(
            args.sequential_fallback_extra_robots,
            0,
        ),
        "fallback_recovery_samples": max(args.fallback_recovery_samples, 1),
        "run_count": len(rows),
        "ok_run_count": len(ok_rows),
        "failed_run_count": len(rows) - len(ok_rows),
        "qoe_recovered_run_count": sum(
            1 for row in rows if row.get("qoe_recovery_ok")
        ),
        "failure_mode_counts": failure_mode_counts(rows),
        "fallback_repair_status_counts": value_counts(rows, "fallback_repair_status"),
        "confidence_fallback_run_count": sum(
            1 for row in rows if row.get("confidence_fallback_applied")
        ),
        "feedback_safe_mode_run_count": sum(
            1 for row in rows if int(row.get("feedback_safe_mode_count", 0)) > 0
        ),
        "fallback_recovery_ok_run_count": sum(
            1 for row in rows if row.get("fallback_recovery_status") == "ok"
        ),
        "fallback_repair_unresolved_run_count": sum(
            1 for row in rows if row.get("fallback_repair_status") == "unresolved"
        ),
        "fallback_repair_deadline_ok_robot_count": sum(
            int(row["fallback_repair_deadline_ok_robot_count"]) for row in rows
        ),
        "fallback_repair_delivered_robot_count": sum(
            int(row["fallback_repair_delivered_robot_count"]) for row in rows
        ),
        "fallback_repair_unresolved_robot_count": sum(
            int(row["fallback_repair_unresolved_robot_count"]) for row in rows
        ),
        "fallback_repair_explicit_candidate_count": sum(
            int(row["fallback_repair_explicit_candidate_count"]) for row in rows
        ),
        "fallback_repair_missing_sequence_count": sum(
            int(row["fallback_repair_missing_sequence_count"]) for row in rows
        ),
        "fallback_repair_late_sequence_count": sum(
            int(row["fallback_repair_late_sequence_count"]) for row in rows
        ),
        "fallback_repair_evidence_robot_count": sum(
            int(row["fallback_repair_evidence_robot_count"]) for row in rows
        ),
        "fallback_repair_nack_retransmission_count": sum(
            int(row["fallback_repair_nack_retransmission_count"]) for row in rows
        ),
        "fallback_repair_idle_ack_nack_count": sum(
            int(row["fallback_repair_idle_ack_nack_count"]) for row in rows
        ),
        "confidence_epoch_count": sum(
            int(row["confidence_epoch_count"]) for row in rows
        ),
        "sequential_epoch_count": sum(
            int(row["sequential_epoch_count"]) for row in rows
        ),
        "min_confidence_epoch_ratio": min(
            (float(row["confidence_epoch_ratio"]) for row in rows),
            default=0.0,
        ),
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
        print("fleetrmw-router-qoe-protection-migration-sequential-repeated-matrix")
        print(f"  status: {status}")
        print(f"  ok/runs: {len(ok_rows)}/{len(rows)}")
        print(f"  qoe_recovered/runs: {summary['qoe_recovered_run_count']}/{len(rows)}")
        print(f"  confidence_epochs: {summary['confidence_epoch_count']}/{summary['sequential_epoch_count']}")
        print(f"  max_epoch_convergence_ms: {summary['max_epoch_convergence_ms']:.3f}")
        print(
            "  aggregate_path_transmission_reduction_ratio: "
            f"{summary['aggregate_path_transmission_reduction_ratio']:.6f}"
        )
    if args.fail_on_row_failure and status != "ok":
        return 1
    return 0 if rows else 1


def parse_ints(value: str, *, minimum: int) -> list[int]:
    result = [int(item.strip()) for item in value.split(",") if item.strip()]
    if not result or any(item < minimum for item in result):
        raise ValueError(f"values must be at least {minimum}")
    return result


def classify_failure(
    result: dict[str, Any],
    *,
    migration_ok: bool,
    all_epochs_confident: bool,
) -> str:
    if result.get("status") == "ok" and migration_ok and all_epochs_confident:
        return "ok"
    if "returncode" in result:
        return "docker_or_build_error"
    if result.get("publisher_barrier_ready") is False:
        return "publisher_barrier_timeout"
    if result.get("feedback_ready") is False or result.get("second_feedback_ready") is False:
        return "subscriber_feedback_timeout"
    epochs = result.get("sequential_qoe_epochs", [])
    recovery = result.get("fallback_recovery", {})
    recovery_ok = isinstance(recovery, dict) and recovery.get("status") == "ok"
    repair = result.get("fallback_repair", {})
    repair_status = (
        str(repair.get("status", "not_applicable"))
        if isinstance(repair, dict) else "not_applicable"
    )
    if epochs and not all_epochs_confident:
        if result.get("confidence_fallback_applied") is True and recovery_ok:
            if repair_status == "unresolved":
                return "confidence_fallback_recovery_unresolved_prewindow"
            if repair_status == "repaired_late":
                return "confidence_fallback_repaired_late"
            if repair_status == "repaired_on_time":
                return "confidence_fallback_repaired_on_time"
            if repair_status == "late":
                return "confidence_fallback_late_delivery"
            return "confidence_fallback_recovered_window"
        if result.get("status") == "ok" and result.get("confidence_fallback_applied") is True:
            return "confidence_fallback_applied"
        if result.get("confidence_fallback_applied") is True:
            return "confidence_fallback_delivery_failure"
        if int(result.get("feedback_safe_mode_count", 0) or 0) > 0:
            if recovery_ok:
                return "feedback_safe_mode_recovered_window"
            return "feedback_safe_mode_delivery_failure"
        return "confidence_not_separated"
    if not migration_ok:
        return "migration_mismatch"
    robot_count = int(result.get("robot_count", 0) or 0)
    if int(result.get("robots_ok", 0) or 0) < robot_count:
        return "robot_delivery_failure"
    primary = result.get("primary_router", {})
    backup = result.get("backup_router", {})
    if primary.get("status") != "ok" or backup.get("status") != "ok":
        return "router_failure"
    if int(result.get("total_nack_retransmissions", 0) or 0) > 0:
        if repair_status == "repaired_on_time":
            return "ack_nack_repaired_on_time"
        if repair_status == "repaired_late":
            return "ack_nack_repaired_late"
        if repair_status == "unresolved":
            return "ack_nack_repair_unresolved"
        return "unexpected_retransmission"
    return "path_accounting_or_unknown"


def failure_mode_counts(rows: list[dict[str, Any]]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for row in rows:
        mode = str(row.get("failure_mode", "unknown"))
        counts[mode] = counts.get(mode, 0) + 1
    return dict(sorted(counts.items()))


def value_counts(rows: list[dict[str, Any]], key: str) -> dict[str, int]:
    counts: dict[str, int] = {}
    for row in rows:
        value = str(row.get(key, "unknown"))
        counts[value] = counts.get(value, 0) + 1
    return dict(sorted(counts.items()))


def parse_floats(value: str) -> list[float]:
    result = [max(0.0, float(item.strip())) for item in value.split(",") if item.strip()]
    if not result:
        raise ValueError("at least one loss percent is required")
    return result


if __name__ == "__main__":
    raise SystemExit(main())

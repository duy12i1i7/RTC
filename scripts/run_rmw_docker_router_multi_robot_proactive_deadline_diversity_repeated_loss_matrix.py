"""Repeat concurrent fleet deadline diversity under stochastic loss."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

try:
    from scripts.run_rmw_docker_router_multi_robot_proactive_deadline_diversity_probe import (
        DEFAULT_IMAGE,
        DEFAULT_TOPIC_PREFIX,
        run_probe,
    )
except ModuleNotFoundError:
    from run_rmw_docker_router_multi_robot_proactive_deadline_diversity_probe import (
        DEFAULT_IMAGE,
        DEFAULT_TOPIC_PREFIX,
        run_probe,
    )


SCHEMA_VERSION = "fleetrmw.rmw_router_multi_robot_proactive_deadline_diversity_repeated_loss_matrix.v1"
SEED_SEMANTICS = (
    "repetition_id_only; current tc netem image does not expose deterministic "
    "random seeding"
)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--image", default=DEFAULT_IMAGE)
    parser.add_argument("--robot-count", type=int, default=4)
    parser.add_argument("--topic-prefix", default=DEFAULT_TOPIC_PREFIX)
    parser.add_argument("--deadline-ms", type=int, default=100)
    parser.add_argument("--primary-profile", default="roaming")
    parser.add_argument("--backup-profile", default="wifi")
    parser.add_argument("--loss-percents", default="0.02")
    parser.add_argument("--repetitions", default="7,13")
    parser.add_argument("--fail-on-row-failure", action="store_true")
    parser.add_argument(
        "--summary-json",
        default=(
            "results_rmw_socket/"
            "docker_router_multi_robot_proactive_deadline_diversity_"
            "repeated_loss_matrix_summary.json"
        ),
    )
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    repetitions = parse_ints(args.repetitions)
    loss_percents = parse_floats(args.loss_percents)
    root = Path(__file__).resolve().parents[1]
    robot_count = max(args.robot_count, 1)
    rows: list[dict[str, Any]] = []
    for loss_percent in loss_percents:
        for repetition_id in repetitions:
            result = run_probe(
                root=root,
                image=args.image,
                robot_count=robot_count,
                topic_prefix=f"{args.topic_prefix}/rep-{repetition_id}",
                deadline_ms=max(args.deadline_ms, 1),
                primary_profile=args.primary_profile,
                backup_profile=args.backup_profile,
                loss_percent=loss_percent,
            )
            rows.append({
                "repetition_id": repetition_id,
                "loss_percent": loss_percent,
                "status": result.get("status", "failed"),
                "evidence_ok": result.get("status") == "ok",
                "robots_ok": result.get("robots_ok", 0),
                "max_latency_ms": result.get("max_latency_ms", 0.0),
                "deadline_success_jain_index": result.get(
                    "deadline_success_jain_index", 0.0
                ),
                "protected_source_frames": result.get(
                    "protected_source_frames", 0
                ),
                "proactive_path_transmissions": result.get(
                    "proactive_path_transmissions", 0
                ),
                "total_nack_retransmissions": result.get(
                    "total_nack_retransmissions", 0
                ),
                "primary_fault_observed": result.get(
                    "primary_fault_observed", False
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
            (float(row["max_latency_ms"]) for row in rows),
            default=0.0,
        ),
        "min_deadline_success_jain_index": min(
            (float(row["deadline_success_jain_index"]) for row in rows),
            default=0.0,
        ),
        "total_protected_source_frames": sum(
            int(row["protected_source_frames"]) for row in rows
        ),
        "total_proactive_path_transmissions": sum(
            int(row["proactive_path_transmissions"]) for row in rows
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
        print("fleetrmw-router-multi-robot-proactive-deadline-diversity-repeated-loss-matrix")
        print(f"  status: {status}")
        print(f"  ok/runs: {len(ok_rows)}/{len(rows)}")
        print(f"  max_observed_latency_ms: {summary['max_observed_latency_ms']:.3f}")
        print(
            "  min_deadline_success_jain_index: "
            f"{summary['min_deadline_success_jain_index']:.6f}"
        )
        print(f"  total_nack_retransmissions: {summary['total_nack_retransmissions']}")
    if args.fail_on_row_failure and status != "ok":
        return 1
    return 0 if status in ("ok", "partial") else 1


def parse_ints(value: str) -> list[int]:
    result = [int(item.strip()) for item in value.split(",") if item.strip()]
    if not result:
        raise ValueError("at least one repetition id is required")
    return result


def parse_floats(value: str) -> list[float]:
    result = [
        max(0.0, float(item.strip()))
        for item in value.split(",")
        if item.strip()
    ]
    if not result:
        raise ValueError("at least one loss percent is required")
    return result


if __name__ == "__main__":
    raise SystemExit(main())

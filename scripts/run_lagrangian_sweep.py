"""Run an offline parameter sweep for FleetQoX Lagrangian admission."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from fleetqox.lagrangian_sweep import (
    build_lagrangian_configs,
    run_lagrangian_sweep,
    summarize_lagrangian_sweep,
    write_lagrangian_sweep_markdown,
    write_lagrangian_sweep_records,
    write_lagrangian_sweep_summary,
)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--robots", default="10,25")
    parser.add_argument("--seeds", default="7,13")
    parser.add_argument("--seconds", type=int, default=10)
    parser.add_argument("--capacity-mode", choices=["shared_cell", "linear", "fixed"], default="shared_cell")
    parser.add_argument("--base-capacity", type=int, default=180_000)
    parser.add_argument("--per-robot-capacity", type=int, default=2_800)
    parser.add_argument("--knee-robots", type=int, default=25)
    parser.add_argument("--deadline-risk-budgets", default="0.04,0.08")
    parser.add_argument("--initial-deadline-lambdas", default="1.8,3.0")
    parser.add_argument("--risk-barrier-starts", default="0.62,0.70")
    parser.add_argument("--risk-barrier-scales", default="12.0")
    parser.add_argument("--deadline-drop-risks", default="0.45,0.55,0.96")
    parser.add_argument("--control-miss-target", type=float, default=0.05)
    parser.add_argument("--include-baselines", action=argparse.BooleanOptionalAction, default=True)
    parser.add_argument(
        "--records",
        type=Path,
        default=Path("results_lagrangian_sweep/lagrangian_sweep_v1_records.jsonl"),
    )
    parser.add_argument(
        "--summary",
        type=Path,
        default=Path("results_lagrangian_sweep/lagrangian_sweep_v1_summary.json"),
    )
    parser.add_argument(
        "--markdown",
        type=Path,
        default=Path("docs/LAGRANGIAN_SWEEP_V1.md"),
    )
    parser.add_argument("--title", default="Lagrangian Parameter Sweep V1")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    robot_counts = parse_ints(args.robots, "--robots")
    seeds = parse_ints(args.seeds, "--seeds")
    configs = build_lagrangian_configs(
        deadline_risk_budgets=parse_floats(args.deadline_risk_budgets, "--deadline-risk-budgets"),
        initial_deadline_lambdas=parse_floats(
            args.initial_deadline_lambdas,
            "--initial-deadline-lambdas",
        ),
        risk_barrier_starts=parse_floats(args.risk_barrier_starts, "--risk-barrier-starts"),
        risk_barrier_scales=parse_floats(args.risk_barrier_scales, "--risk-barrier-scales"),
        deadline_drop_risks=parse_floats(args.deadline_drop_risks, "--deadline-drop-risks"),
    )
    records = run_lagrangian_sweep(
        robot_counts=robot_counts,
        seeds=seeds,
        seconds=args.seconds,
        configs=configs,
        capacity_mode=args.capacity_mode,
        base_capacity=args.base_capacity,
        per_robot_capacity=args.per_robot_capacity,
        knee_robots=args.knee_robots,
        include_baselines=args.include_baselines,
    )
    summary = summarize_lagrangian_sweep(records, control_miss_target=args.control_miss_target)

    write_lagrangian_sweep_records(records, args.records)
    write_lagrangian_sweep_summary(summary, args.summary)
    write_lagrangian_sweep_markdown(
        summary,
        args.markdown,
        title=args.title,
        records_path=args.records,
        summary_path=args.summary,
    )

    result = {
        "records": str(args.records),
        "summary": str(args.summary),
        "markdown": str(args.markdown),
        "metric_rows": len(records),
        "candidates": len(summary["ranking"]),
        "pareto_frontier": summary["pareto_frontier"],
    }
    if args.json:
        print(json.dumps(result, sort_keys=True))
        return
    print(f"Lagrangian sweep records written: {args.records}")
    print(f"Lagrangian sweep summary written: {args.summary}")
    print(f"Lagrangian sweep report written: {args.markdown}")


def parse_ints(value: str, option: str) -> list[int]:
    try:
        parsed = [int(part.strip()) for part in value.split(",") if part.strip()]
    except ValueError as exc:
        raise SystemExit(f"{option} must be a comma-separated integer list") from exc
    if not parsed or any(item <= 0 for item in parsed):
        raise SystemExit(f"{option} must contain positive integers")
    return parsed


def parse_floats(value: str, option: str) -> list[float]:
    try:
        parsed = [float(part.strip()) for part in value.split(",") if part.strip()]
    except ValueError as exc:
        raise SystemExit(f"{option} must be a comma-separated numeric list") from exc
    if not parsed:
        raise SystemExit(f"{option} must contain at least one number")
    return parsed


if __name__ == "__main__":
    main()

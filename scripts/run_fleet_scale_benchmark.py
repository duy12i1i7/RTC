"""Run the local fleet-scale QoS/QoE benchmark matrix."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from fleetqox.fleet_scale import (
    run_fleet_scale_matrix,
    summarize_fleet_scale,
    write_fleet_markdown,
    write_fleet_records_jsonl,
    write_fleet_summary_csv,
    write_fleet_summary_json,
)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--robots", default="10,25,50,100")
    parser.add_argument("--seeds", default="7,13,29")
    parser.add_argument("--seconds", type=int, default=30)
    parser.add_argument("--capacity-mode", choices=["shared_cell", "linear", "fixed"], default="shared_cell")
    parser.add_argument("--base-capacity", type=int, default=180_000)
    parser.add_argument("--per-robot-capacity", type=int, default=2_800)
    parser.add_argument("--knee-robots", type=int, default=25)
    parser.add_argument("--records", type=Path, default=Path("results_fleet_scale/fleet_scale_v1_records.jsonl"))
    parser.add_argument("--summary", type=Path, default=Path("results_fleet_scale/fleet_scale_v1_summary.json"))
    parser.add_argument("--markdown", type=Path, default=Path("results_fleet_scale/fleet_scale_v1_report.md"))
    parser.add_argument("--csv", type=Path, default=Path("results_fleet_scale/fleet_scale_v1_report.csv"))
    parser.add_argument("--title", default="Fleet-Scale QoS/QoE Benchmark v1")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    robot_counts = _parse_ints(args.robots, "--robots")
    seeds = _parse_ints(args.seeds, "--seeds")
    if args.seconds <= 0:
        raise SystemExit("--seconds must be positive")

    records = run_fleet_scale_matrix(
        robot_counts,
        seeds,
        seconds=args.seconds,
        capacity_mode=args.capacity_mode,
        base_capacity=args.base_capacity,
        per_robot_capacity=args.per_robot_capacity,
        knee_robots=args.knee_robots,
    )
    summary = summarize_fleet_scale(records)
    write_fleet_records_jsonl(records, args.records)
    write_fleet_summary_json(summary, args.summary)
    write_fleet_summary_csv(summary, args.csv)
    write_fleet_markdown(
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
        "csv": str(args.csv),
        "runs": len(records),
        "groups": len(summary.get("groups", [])),
    }
    if args.json:
        print(json.dumps(result, sort_keys=True))
        return
    print(f"Fleet-scale records written: {args.records}")
    print(f"Fleet-scale summary written: {args.summary}")
    print(f"Fleet-scale report written: {args.markdown}")
    print(f"Fleet-scale CSV written: {args.csv}")


def _parse_ints(value: str, option: str) -> list[int]:
    try:
        parsed = [int(part.strip()) for part in value.split(",") if part.strip()]
    except ValueError as exc:
        raise SystemExit(f"{option} must be a comma-separated integer list") from exc
    if not parsed or any(item <= 0 for item in parsed):
        raise SystemExit(f"{option} must contain positive integers")
    return parsed


if __name__ == "__main__":
    main()

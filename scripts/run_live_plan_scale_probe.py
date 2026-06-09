"""Run the FleetRMW live path-plan scale probe."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from fleetqox.live_plan_scale import (
    LivePlanScaleConfig,
    run_live_plan_scale_probe,
    write_live_plan_scale_markdown,
    write_live_plan_scale_summary,
)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--robots", type=int, default=100)
    parser.add_argument("--ticks", type=int, default=12)
    parser.add_argument("--seed", type=int, default=7)
    parser.add_argument(
        "--summary",
        type=Path,
        default=Path("results_rmw_socket/live_plan_scale_probe_summary.json"),
    )
    parser.add_argument(
        "--markdown",
        type=Path,
        default=Path("results_rmw_socket/live_plan_scale_probe_report.md"),
    )
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    summary = run_live_plan_scale_probe(
        LivePlanScaleConfig(
            robot_count=args.robots,
            ticks=args.ticks,
            seed=args.seed,
        )
    )
    write_live_plan_scale_summary(summary, args.summary)
    write_live_plan_scale_markdown(summary, args.markdown)

    result = {
        "status": summary["status"],
        "schema_version": summary["schema_version"],
        "summary": str(args.summary),
        "markdown": str(args.markdown),
        "robot_count": summary["robot_count"],
        "topic_count": summary["topic_count"],
        "final_rule_count": summary["final_rule_count"],
        "decision_ms": summary["decision_ms"],
        "final_mode_counts": summary["final_mode_counts"],
    }
    if args.json:
        print(json.dumps(result, sort_keys=True))
    else:
        print("fleetrmw-live-plan-scale-probe")
        print(f"  status: {result['status']}")
        print(f"  robots: {result['robot_count']}")
        print(f"  topics: {result['topic_count']}")
        print(f"  final_rules: {result['final_rule_count']}")
        print(f"  summary: {args.summary}")
    return 0 if summary["status"] == "ok" else 1


if __name__ == "__main__":
    raise SystemExit(main())

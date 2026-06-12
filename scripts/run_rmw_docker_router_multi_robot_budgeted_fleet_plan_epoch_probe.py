"""Run an online redundancy-budget epoch transition with active ROS 2 publishers."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.run_rmw_docker_router_multi_robot_budgeted_fleet_plan_probe import (
    DEFAULT_IMAGE,
    DEFAULT_TOPIC_PREFIX,
    run_probe,
)


SCHEMA_VERSION = "fleetrmw.rmw_router_multi_robot_budgeted_fleet_plan_epoch_probe.v1"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--image", default=DEFAULT_IMAGE)
    parser.add_argument("--robot-count", type=int, default=4)
    parser.add_argument("--protected-robot-budget", type=int, default=2)
    parser.add_argument("--topic-prefix", default=f"{DEFAULT_TOPIC_PREFIX}_epoch")
    parser.add_argument("--deadline-ms", type=int, default=100)
    parser.add_argument("--primary-profile", default="roaming")
    parser.add_argument("--backup-profile", default="wifi")
    parser.add_argument("--loss-percent", type=float, default=0.02)
    parser.add_argument(
        "--summary-json",
        default=(
            "results_rmw_socket/"
            "docker_router_multi_robot_budgeted_fleet_plan_epoch_probe_summary.json"
        ),
    )
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    summary = run_probe(
        root=ROOT,
        image=args.image,
        robot_count=max(args.robot_count, 1),
        protected_robot_budget=max(args.protected_robot_budget, 0),
        topic_prefix=args.topic_prefix,
        deadline_ms=max(args.deadline_ms, 1),
        primary_profile=args.primary_profile,
        backup_profile=args.backup_profile,
        loss_percent=max(args.loss_percent, 0.0),
        epoch_transition=True,
    )
    summary["schema_version"] = SCHEMA_VERSION
    output = ROOT / args.summary_json
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(summary, sort_keys=True) + "\n", encoding="utf-8")

    if args.json:
        print(json.dumps(summary, sort_keys=True))
    else:
        print("fleetrmw-router-multi-robot-budgeted-fleet-plan-epoch-probe")
        print(f"  status: {summary['status']}")
        print(f"  robots_ok: {summary.get('robots_ok')}/{summary.get('robot_count')}")
        print(f"  actual_path_transmissions: {summary.get('actual_path_transmissions')}")
        print(f"  path_transmission_reduction_ratio: {summary.get('path_transmission_reduction_ratio')}")
    return 0 if summary["status"] == "ok" else 1


if __name__ == "__main__":
    raise SystemExit(main())

"""Run an extended moving-base upstream Nav2 NavigateToPose workload.

This runner reuses the full-stack moving-base Nav2 NavigateToPose probe with a
longer unobstructed goal than the default CI-light `x=0.6` case. It exercises
the same planner/controller/bt_navigator pipeline, dynamic `/odom` and `/tf`,
and `/cmd_vel` feedback through FleetRMW while requiring substantially more
fake-base translation.

This remains an extended single-goal smoke workload. It does not claim
obstacle-field recovery or a long/soak navigation workload.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.run_rmw_docker_nav2_navigate_to_pose_probe import (  # noqa: E402
    DEFAULT_IMAGE,
    run_probe,
)


SCHEMA_VERSION = "fleetrmw.docker_nav2_navigate_to_pose_extended_moving_probe.v1"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--image", default=DEFAULT_IMAGE)
    parser.add_argument("--port-base", type=int, default=6400)
    parser.add_argument("--goal-x", type=float, default=1.2)
    parser.add_argument(
        "--summary-json",
        default=(
            "results_rmw_socket/"
            "docker_nav2_navigate_to_pose_extended_moving_probe_summary.json"
        ),
    )
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    summary = run_probe(
        root=ROOT,
        image=args.image,
        port_base=args.port_base,
        goal_x=args.goal_x,
        moving_base=True,
        schema_version=SCHEMA_VERSION,
    )
    moved = float(summary.get("fake_base_moved_distance", 0.0) or 0.0)
    cmd_vel_count = int(summary.get("fake_base_cmd_vel_count", 0) or 0)
    extended_ok = (
        summary.get("status") == "ok"
        and summary.get("navigate_to_pose_goal_succeeded") is True
        and summary.get("cmd_vel_topic_forwarded") is True
        and float(summary.get("navigation_goal_x", 0.0) or 0.0) >= 1.0
        and moved >= 0.8
        and cmd_vel_count >= 6
    )
    summary["extended_moving_navigation_claim"] = bool(extended_ok)
    summary["extended_moving_navigation_scope"] = (
        "single_goal_unobstructed_1m_plus_fake_base_nav2_bt_pipeline"
    )
    summary["long_navigation_workload_claim"] = False
    output = ROOT / args.summary_json
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    if args.json:
        print(json.dumps(summary, sort_keys=True))
    else:
        print(
            f"status={summary['status']} "
            f"navigate_to_pose={summary.get('navigate_to_pose_goal_succeeded')} "
            f"extended={summary.get('extended_moving_navigation_claim')} "
            f"cmd_vel={summary.get('fake_base_cmd_vel_count')} "
            f"moved={summary.get('fake_base_moved_distance')}"
        )
    return 0 if summary["status"] == "ok" and extended_ok else 1


if __name__ == "__main__":
    raise SystemExit(main())

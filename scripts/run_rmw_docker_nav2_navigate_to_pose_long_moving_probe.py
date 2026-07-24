"""Run a repeated moving-base upstream Nav2 NavigateToPose workload.

This runner wraps the extended moving-base Nav2 NavigateToPose probe and
executes it across fresh Docker processes/ports. It is intended to close the
first long-workload boundary for FleetRMW's upstream Nav2 planner/controller
path by requiring repeated successful 1m-plus fake-base navigation goals,
aggregate `/cmd_vel` feedback, aggregate fake-base movement, and repeated
FleetRMW router action/service traffic.

It remains an unobstructed repeated moving-base workload. It does not claim
obstacle-field recovery or autonomous recovery from planner/controller failure.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.run_rmw_docker_nav2_navigate_to_pose_extended_moving_probe import (  # noqa: E402
    DEFAULT_IMAGE,
    run_probe,
)


SCHEMA_VERSION = "fleetrmw.docker_nav2_navigate_to_pose_long_moving_probe.v1"


def row_extended_moving_ok(row: dict[str, Any]) -> bool:
    moved = float(row.get("fake_base_moved_distance", 0.0) or 0.0)
    cmd_vel_count = int(row.get("fake_base_cmd_vel_count", 0) or 0)
    goal_x = float(row.get("navigation_goal_x", 0.0) or 0.0)
    return (
        row.get("extended_moving_navigation_claim") is True
        or (
            row.get("status") == "ok"
            and row.get("navigate_to_pose_goal_succeeded") is True
            and row.get("cmd_vel_topic_forwarded") is True
            and goal_x >= 1.0
            and moved >= 0.8
            and cmd_vel_count >= 6
        )
    )


def aggregate(
    rows: list[dict[str, Any]],
    *,
    min_iterations: int,
    min_total_moved_distance: float,
    min_total_cmd_vel_count: int,
) -> dict[str, Any]:
    ok_rows = [row for row in rows if row.get("status") == "ok"]
    total_service_frames = sum(int(row.get("fleetqox_router_service_frames", 0)) for row in rows)
    total_forwarded_frames = sum(int(row.get("fleetqox_router_forwarded_frames", 0)) for row in rows)
    total_received_frames = sum(int(row.get("fleetqox_router_received_frames", 0)) for row in rows)
    total_cmd_vel = sum(int(row.get("fake_base_cmd_vel_count", 0)) for row in rows)
    total_moved_distance = sum(float(row.get("fake_base_moved_distance", 0.0)) for row in rows)
    max_goal_x = max((float(row.get("navigation_goal_x", 0.0) or 0.0) for row in rows), default=0.0)
    min_moved_distance = min(
        (float(row.get("fake_base_moved_distance", 0.0) or 0.0) for row in rows),
        default=0.0,
    )
    all_ok = len(ok_rows) == len(rows) and len(rows) >= min_iterations
    all_extended = all(row_extended_moving_ok(row) for row in ok_rows)
    all_navigation_succeeded = all(
        row.get("navigate_to_pose_goal_succeeded") is True for row in ok_rows
    )
    all_cmd_vel_forwarded = all(row.get("cmd_vel_topic_forwarded") is True for row in ok_rows)
    long_ok = (
        all_ok
        and all_extended
        and all_navigation_succeeded
        and all_cmd_vel_forwarded
        and total_moved_distance >= min_total_moved_distance
        and total_cmd_vel >= min_total_cmd_vel_count
    )
    return {
        "schema_version": SCHEMA_VERSION,
        "status": "ok" if long_ok else "failed",
        "run_count": len(rows),
        "ok_run_count": len(ok_rows),
        "failed_run_count": len(rows) - len(ok_rows),
        "navigate_to_pose_long_moving_workload": bool(long_ok),
        "navigate_to_pose_goal_succeeded_run_count": sum(
            1 for row in rows if row.get("navigate_to_pose_goal_succeeded") is True
        ),
        "extended_moving_navigation_run_count": sum(
            1 for row in rows if row_extended_moving_ok(row)
        ),
        "moving_robot_navigation_claim": bool(long_ok),
        "extended_moving_navigation_claim": bool(long_ok),
        "long_navigation_workload_claim": bool(long_ok),
        "long_navigation_workload_scope": (
            "repeated_unobstructed_1m_plus_moving_base_nav2_bt_pipeline"
        ),
        "obstacle_field_recovery_claim": False,
        "total_fake_base_cmd_vel_count": total_cmd_vel,
        "total_fake_base_moved_distance": total_moved_distance,
        "min_fake_base_moved_distance": min_moved_distance,
        "max_navigation_goal_x": max_goal_x,
        "min_required_iterations": min_iterations,
        "min_required_total_fake_base_moved_distance": min_total_moved_distance,
        "min_required_total_fake_base_cmd_vel_count": min_total_cmd_vel_count,
        "total_fleetqox_router_service_frames": total_service_frames,
        "total_fleetqox_router_forwarded_frames": total_forwarded_frames,
        "total_fleetqox_router_received_frames": total_received_frames,
        "min_service_frames_per_run": min(
            (int(row.get("fleetqox_router_service_frames", 0)) for row in rows),
            default=0,
        ),
        "rows": rows,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--image", default=DEFAULT_IMAGE)
    parser.add_argument("--iterations", type=int, default=3)
    parser.add_argument("--port-base", type=int, default=6600)
    parser.add_argument("--port-stride", type=int, default=100)
    parser.add_argument("--goal-x", type=float, default=1.2)
    parser.add_argument("--min-total-moved-distance", type=float, default=2.4)
    parser.add_argument("--min-total-cmd-vel-count", type=int, default=18)
    parser.add_argument(
        "--summary-json",
        default=(
            "results_rmw_socket/"
            "docker_nav2_navigate_to_pose_long_moving_probe_summary.json"
        ),
    )
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    rows: list[dict[str, Any]] = []
    for index in range(args.iterations):
        port_base = args.port_base + index * args.port_stride
        row = run_probe(
            root=ROOT,
            image=args.image,
            port_base=port_base,
            goal_x=args.goal_x,
            moving_base=True,
            schema_version=(
                "fleetrmw.docker_nav2_navigate_to_pose_extended_moving_probe.v1"
            ),
        )
        row["iteration"] = index
        row["port_base"] = port_base
        rows.append(row)
    summary = aggregate(
        rows,
        min_iterations=args.iterations,
        min_total_moved_distance=args.min_total_moved_distance,
        min_total_cmd_vel_count=args.min_total_cmd_vel_count,
    )
    output = ROOT / args.summary_json
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    if args.json:
        print(json.dumps(summary, sort_keys=True))
    else:
        print(
            f"status={summary['status']} ok={summary['ok_run_count']}/{summary['run_count']} "
            f"long={summary['long_navigation_workload_claim']} "
            f"cmd_vel={summary['total_fake_base_cmd_vel_count']} "
            f"moved={summary['total_fake_base_moved_distance']:.3f}"
        )
    return 0 if summary["status"] == "ok" else 1


if __name__ == "__main__":
    raise SystemExit(main())

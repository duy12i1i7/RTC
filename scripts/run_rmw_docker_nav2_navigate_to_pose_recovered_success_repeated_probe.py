"""Repeat the recovered-success Nav2 NavigateToPose FleetRMW probe.

This is a CI-friendly repetition wrapper around
`run_rmw_docker_nav2_navigate_to_pose_recovered_success_probe.py`. It proves a
real Spin recovery action followed by a successful short
`ComputePathToPose -> FollowPath` NavigateToPose pipeline can be brought up and
executed repeatedly with fresh ports and fresh Docker processes.

This remains a repeated smoke workload. It does not claim obstacle-field
autonomous recovery or a long/soak navigation workload.
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

from scripts.run_rmw_docker_nav2_navigate_to_pose_recovered_success_probe import (  # noqa: E402
    DEFAULT_IMAGE,
    run_probe,
)


SCHEMA_VERSION = (
    "fleetrmw.docker_nav2_navigate_to_pose_recovered_success_repeated_probe.v1"
)


def aggregate(rows: list[dict[str, Any]]) -> dict[str, Any]:
    ok_rows = [row for row in rows if row.get("status") == "ok"]
    total_service_frames = sum(int(row.get("fleetqox_router_service_frames", 0)) for row in rows)
    total_forwarded_frames = sum(int(row.get("fleetqox_router_forwarded_frames", 0)) for row in rows)
    total_received_frames = sum(int(row.get("fleetqox_router_received_frames", 0)) for row in rows)
    total_cmd_vel = sum(int(row.get("fake_base_cmd_vel_count", 0)) for row in rows)
    total_moved_distance = sum(float(row.get("fake_base_moved_distance", 0.0)) for row in rows)
    max_abs_theta = max(
        (float(row.get("fake_base_max_abs_theta", 0.0)) for row in rows),
        default=0.0,
    )
    all_ok = len(ok_rows) == len(rows) and bool(rows)
    spin_success_count = sum(1 for row in rows if row.get("spin_goal_succeeded") is True)
    recovered_success_count = sum(
        1 for row in rows if row.get("successful_recovered_navigation_claim") is True
    )
    return {
        "schema_version": SCHEMA_VERSION,
        "status": "ok" if all_ok else "failed",
        "run_count": len(rows),
        "ok_run_count": len(ok_rows),
        "failed_run_count": len(rows) - len(ok_rows),
        "navigate_to_pose_recovered_success_repeated_smoke": True,
        "spin_goal_succeeded_run_count": spin_success_count,
        "successful_recovered_navigation_run_count": recovered_success_count,
        "navigate_to_pose_goal_succeeded_run_count": sum(
            1 for row in rows if row.get("navigate_to_pose_goal_succeeded") is True
        ),
        "nav2_recovery_behavior_claim": all(
            row.get("nav2_recovery_behavior_claim") is True for row in ok_rows
        ) if ok_rows else False,
        "successful_recovered_navigation_claim": all(
            row.get("successful_recovered_navigation_claim") is True for row in ok_rows
        ) if ok_rows else False,
        "successful_recovered_navigation_scope": (
            "repeated_spin_recovery_action_then_successful_navigate_to_pose"
        ),
        "obstacle_field_recovery_claim": False,
        "long_navigation_workload_claim": False,
        "total_fake_base_cmd_vel_count": total_cmd_vel,
        "total_fake_base_moved_distance": total_moved_distance,
        "max_fake_base_abs_theta": max_abs_theta,
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
    parser.add_argument("--iterations", type=int, default=2)
    parser.add_argument("--port-base", type=int, default=6200)
    parser.add_argument("--port-stride", type=int, default=100)
    parser.add_argument("--spin-dist", type=float, default=0.35)
    parser.add_argument("--goal-x", type=float, default=0.6)
    parser.add_argument(
        "--summary-json",
        default=(
            "results_rmw_socket/"
            "docker_nav2_navigate_to_pose_recovered_success_repeated_probe_summary.json"
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
            spin_dist=args.spin_dist,
            goal_x=args.goal_x,
        )
        row["iteration"] = index
        row["port_base"] = port_base
        rows.append(row)
    summary = aggregate(rows)
    output = ROOT / args.summary_json
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    if args.json:
        print(json.dumps(summary, sort_keys=True))
    else:
        print(
            f"status={summary['status']} ok={summary['ok_run_count']}/{summary['run_count']} "
            f"recovered={summary['successful_recovered_navigation_run_count']} "
            f"service_frames={summary['total_fleetqox_router_service_frames']}"
        )
    return 0 if summary["status"] == "ok" else 1


if __name__ == "__main__":
    raise SystemExit(main())

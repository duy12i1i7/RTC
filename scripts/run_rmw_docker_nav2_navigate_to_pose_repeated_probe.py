"""Repeat the upstream Nav2 NavigateToPose FleetRMW probe.

This is a CI-friendly repetition wrapper around
`run_rmw_docker_nav2_navigate_to_pose_probe.py`. It proves the same
planner/controller/bt_navigator same-pose BT pipeline can be brought up and
executed repeatedly with fresh ports and fresh Docker processes.
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

from scripts.run_rmw_docker_nav2_navigate_to_pose_probe import (  # noqa: E402
    DEFAULT_IMAGE,
    run_probe,
)


SCHEMA_VERSION = "fleetrmw.docker_nav2_navigate_to_pose_repeated_probe.v1"


def aggregate(rows: list[dict[str, Any]]) -> dict[str, Any]:
    ok_rows = [row for row in rows if row.get("status") == "ok"]
    total_service_frames = sum(int(row.get("fleetqox_router_service_frames", 0)) for row in rows)
    total_forwarded_frames = sum(int(row.get("fleetqox_router_forwarded_frames", 0)) for row in rows)
    total_received_frames = sum(int(row.get("fleetqox_router_received_frames", 0)) for row in rows)
    return {
        "schema_version": SCHEMA_VERSION,
        "status": "ok" if len(ok_rows) == len(rows) and rows else "failed",
        "run_count": len(rows),
        "ok_run_count": len(ok_rows),
        "failed_run_count": len(rows) - len(ok_rows),
        "navigate_to_pose_repeated_smoke": True,
        "navigate_to_pose_goal_succeeded_run_count": sum(
            1 for row in rows if row.get("navigate_to_pose_goal_succeeded") is True
        ),
        "full_nav2_navigation_stack_claim": all(
            row.get("full_nav2_navigation_stack_claim") is True for row in ok_rows
        ) if ok_rows else False,
        "moving_robot_navigation_claim": False,
        "recovery_behavior_claim": False,
        "long_navigation_workload_claim": False,
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
    parser.add_argument("--port-base", type=int, default=5200)
    parser.add_argument("--port-stride", type=int, default=100)
    parser.add_argument(
        "--summary-json",
        default="results_rmw_socket/docker_nav2_navigate_to_pose_repeated_probe_summary.json",
    )
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    rows: list[dict[str, Any]] = []
    for index in range(args.iterations):
        port_base = args.port_base + index * args.port_stride
        row = run_probe(root=ROOT, image=args.image, port_base=port_base)
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
            f"service_frames={summary['total_fleetqox_router_service_frames']}"
        )
    return 0 if summary["status"] == "ok" else 1


if __name__ == "__main__":
    raise SystemExit(main())

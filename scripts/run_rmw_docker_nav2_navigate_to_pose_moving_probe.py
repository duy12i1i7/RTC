"""Run a small moving-base upstream Nav2 NavigateToPose workload.

This runner reuses the full-stack Nav2 NavigateToPose probe but replaces the
static odometry publisher with a fake base node. The fake base subscribes to
Nav2 `/cmd_vel`, integrates a short forward motion, and publishes dynamic
`/odom` and `/tf` through FleetRMW. The claim is intentionally CI-light: one
short unobstructed goal, no recovery behavior, and no long soak workload.
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


SCHEMA_VERSION = "fleetrmw.docker_nav2_navigate_to_pose_moving_probe.v1"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--image", default=DEFAULT_IMAGE)
    parser.add_argument("--port-base", type=int, default=5400)
    parser.add_argument("--goal-x", type=float, default=0.6)
    parser.add_argument(
        "--summary-json",
        default="results_rmw_socket/docker_nav2_navigate_to_pose_moving_probe_summary.json",
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
    output = ROOT / args.summary_json
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    if args.json:
        print(json.dumps(summary, sort_keys=True))
    else:
        print(
            f"status={summary['status']} "
            f"navigate_to_pose={summary.get('navigate_to_pose_goal_succeeded')} "
            f"moving={summary.get('moving_robot_navigation_claim')} "
            f"cmd_vel={summary.get('fake_base_cmd_vel_count')}"
        )
    return 0 if summary["status"] == "ok" else 1


if __name__ == "__main__":
    raise SystemExit(main())

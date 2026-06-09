"""Run the online fleet path-plan controller probe."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from fleetqox.fleet_optimizer import FleetFlowDemand, FleetOptimizerConfig, RobotQoEState
from fleetqox.model import FlowClass
from fleetqox.online_fleet_planner import (
    FleetTopicDemand,
    OnlineFleetPathPlanner,
    OnlineFleetPlannerConfig,
    PathObservation,
)


SCHEMA_VERSION = "fleetrmw.online_fleet_path_plan_probe.v1"
DEFAULT_TOPIC = "/robot_0000/cmd_vel"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--topic", default=DEFAULT_TOPIC)
    parser.add_argument(
        "--summary-json",
        default="results_fleet_optimizer/online_fleet_path_plan_probe_summary.json",
    )
    parser.add_argument(
        "--markdown",
        default="docs/ONLINE_FLEET_PATH_PLAN_CONTROLLER_V1.md",
    )
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    summary = run_probe(topic=args.topic)
    summary_path = ROOT / args.summary_json
    summary_path.parent.mkdir(parents=True, exist_ok=True)
    summary_path.write_text(json.dumps(summary, sort_keys=True) + "\n", encoding="utf-8")
    markdown_path = ROOT / args.markdown
    markdown_path.parent.mkdir(parents=True, exist_ok=True)
    markdown_path.write_text(render_markdown(summary), encoding="utf-8")

    if args.json:
        print(json.dumps(summary, sort_keys=True))
    else:
        print("fleetrmw-online-fleet-path-plan-probe")
        print(f"  status: {summary['status']}")
        print(f"  final_path_plan: {summary['final_path_plan']}")
        print(f"  changed_ticks: {summary['changed_ticks']}")
    return 0 if summary["status"] == "ok" else 1


def run_probe(*, topic: str = DEFAULT_TOPIC) -> dict[str, Any]:
    demand = FleetTopicDemand(
        topic,
        FleetFlowDemand(
            flow_id="robot_0000/cmd_vel",
            robot_id="robot_0000",
            flow_class=FlowClass.CONTROL,
            deadline_ms=30.0,
            payload_bytes=680,
            rate_hz=20.0,
            criticality=0.95,
            qoe_weight=0.10,
            age_ms=8.0,
            lifespan_ms=90.0,
        ),
    )
    robot_states = [
        RobotQoEState(
            "robot_0000",
            control_delivery_ratio=0.91,
            deadline_miss_ratio=0.16,
            qoe_score=0.80,
        )
    ]
    planner = OnlineFleetPathPlanner(
        OnlineFleetPlannerConfig(
            optimizer=FleetOptimizerConfig(
                capacity_bytes_per_tick=4096,
                redundant_deadline_ms=35.0,
                redundancy_risk_threshold=1.0,
            ),
            telemetry_alpha=1.0,
            min_dwell_ticks=2,
            switch_score_margin=0.25,
        )
    )
    plans = [
        planner.update(
            tick=0,
            observations=[
                PathObservation("primary_wifi", 10.0, 1.0, 100, 99, 1, 0, 20_000, 200_000),
                PathObservation("backup_5g", 24.0, 5.0, 100, 97, 3, 5, 84_000, 200_000),
            ],
            demands=[demand],
            robot_states=robot_states,
        ),
        planner.update(
            tick=1,
            observations=[
                PathObservation("primary_wifi", 58.0, 22.0, 100, 82, 16, 24, 176_000, 200_000),
                PathObservation("backup_5g", 24.0, 5.0, 100, 96, 3, 4, 84_000, 200_000),
            ],
            demands=[demand],
            robot_states=robot_states,
        ),
        planner.update(
            tick=2,
            observations=[
                PathObservation("primary_wifi", 86.0, 28.0, 100, 74, 28, 36, 180_000, 200_000),
                PathObservation("backup_5g", 12.0, 2.0, 100, 99, 1, 1, 24_000, 200_000),
            ],
            demands=[demand],
            robot_states=robot_states,
        ),
        planner.update(
            tick=3,
            observations=[
                PathObservation("primary_wifi", 88.0, 28.0, 100, 74, 28, 36, 180_000, 200_000),
                PathObservation("backup_5g", 12.0, 2.0, 100, 99, 1, 1, 24_000, 200_000),
            ],
            demands=[demand],
            robot_states=robot_states,
        ),
    ]
    plan_dicts = [plan.as_dict() for plan in plans]
    path_plans = [plan.path_plan_env for plan in plans]
    changed_ticks = [plan.tick for plan in plans if plan.changed_topics]
    held_ticks = [
        plan.tick
        for plan in plans
        if plan.topic_decisions and plan.topic_decisions[0].held_by_dwell
    ]
    status = (
        path_plans[0] == f"{topic}=primary_wifi"
        and path_plans[1] == f"{topic}=backup_5g+primary_wifi"
        and path_plans[2] == f"{topic}=backup_5g+primary_wifi"
        and path_plans[3] == f"{topic}=backup_5g"
        and held_ticks == [2]
        and changed_ticks == [0, 1, 3]
    )
    return {
        "schema_version": SCHEMA_VERSION,
        "status": "ok" if status else "failed",
        "topic": topic,
        "path_plans": path_plans,
        "final_path_plan": path_plans[-1],
        "changed_ticks": changed_ticks,
        "held_ticks": held_ticks,
        "plans": plan_dicts,
    }


def render_markdown(summary: dict[str, Any]) -> str:
    rows = [
        f"| {index} | `{plan}` |"
        for index, plan in enumerate(summary.get("path_plans", []))
    ]
    return "\n".join(
        [
            "# Online Fleet Path Plan Controller V1",
            "",
            "This artifact verifies the closed-loop planner that converts measured per-path observations into `FLEETQOX_RMW_FLEET_PATH_PLAN` rules.",
            "",
            f"- Summary: `results_fleet_optimizer/online_fleet_path_plan_probe_summary.json`",
            f"- Schema: `{summary['schema_version']}`",
            f"- Status: `{summary['status']}`",
            f"- Changed ticks: `{summary['changed_ticks']}`",
            f"- Held ticks: `{summary['held_ticks']}`",
            "",
            "| tick | path plan |",
            "|---:|---|",
            *rows,
            "",
            "## Interpretation",
            "",
            "- Tick `0` starts on the best primary Wi-Fi path.",
            "- Tick `1` moves urgent control traffic to redundant backup-plus-primary paths after the primary path degrades.",
            "- Tick `2` intentionally holds the redundant plan because the anti-flapping dwell guard has not expired.",
            "- Tick `3` narrows to backup-only after the backup path becomes stable enough and the dwell guard allows the change.",
            "",
        ]
    )


if __name__ == "__main__":
    raise SystemExit(main())

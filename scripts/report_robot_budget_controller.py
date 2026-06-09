"""Offline smoke report for the per-robot budget-aware admission wrapper."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Callable, Iterable

from fleetqox.control_plane import (
    PredictiveAdmissionController,
    RobotBudgetAwareAdmissionController,
)
from fleetqox.model import (
    FlowClass,
    FlowDecision,
    FlowObservation,
    FlowSpec,
    NetworkLink,
    QoEProfile,
    QoSProfile,
    TaskContext,
)
from fleetqox.sidecar_metrics import jain_index


PolicyFn = Callable[
    [Iterable[tuple[FlowSpec, FlowObservation]], NetworkLink],
    list[FlowDecision],
]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--ticks", type=int, default=12)
    parser.add_argument(
        "--summary-json",
        type=Path,
        default=Path("results_robot_budget/robot_budget_controller_smoke_summary.json"),
    )
    parser.add_argument(
        "--markdown",
        type=Path,
        default=Path("results_robot_budget/robot_budget_controller_smoke_report.md"),
    )
    args = parser.parse_args()

    link = NetworkLink(capacity_bytes_per_tick=96, loss=0.01, jitter_ms=2, rtt_ms=20)
    records = [
        run_policy(
            "predictive_baseline",
            PredictiveAdmissionController().schedule,
            ticks=args.ticks,
            link=link,
        ),
        run_policy(
            "robot_budget_aware",
            RobotBudgetAwareAdmissionController(
                PredictiveAdmissionController().schedule
            ).schedule,
            ticks=args.ticks,
            link=link,
        ),
    ]
    summary = {
        "schema_version": "fleetrmw.robot_budget_controller_smoke.v1",
        "ticks": args.ticks,
        "link": {
            "capacity_bytes_per_tick": link.capacity_bytes_per_tick,
            "loss": link.loss,
            "jitter_ms": link.jitter_ms,
            "rtt_ms": link.rtt_ms,
        },
        "policies": records,
    }
    args.summary_json.parent.mkdir(parents=True, exist_ok=True)
    args.markdown.parent.mkdir(parents=True, exist_ok=True)
    args.summary_json.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n")
    args.markdown.write_text(render_markdown(summary))
    print(
        "robot-budget-controller "
        f"policies={len(records)} summary={args.summary_json} markdown={args.markdown}"
    )
    return 0


def run_policy(
    label: str,
    policy: PolicyFn,
    *,
    ticks: int,
    link: NetworkLink,
) -> dict[str, object]:
    robots = ["robot_0000", "robot_0001"]
    offered = {robot: 0 for robot in robots}
    delivered = {robot: 0 for robot in robots}
    actions: dict[str, dict[str, int]] = {robot: {} for robot in robots}
    timeline: list[dict[str, object]] = []

    flows = [_control_flow(robot) for robot in robots]
    for tick in range(ticks):
        candidates = [(flow, _observation(flow, tick)) for flow in flows]
        decisions = {decision.flow_id: decision for decision in policy(candidates, link)}
        row: dict[str, object] = {"tick": tick}
        for flow, _obs in candidates:
            robot_id = flow.robot_id
            decision = decisions[flow.flow_id]
            offered[robot_id] += 1
            actions[robot_id][decision.action] = actions[robot_id].get(decision.action, 0) + 1
            sent = decision.action.startswith("send")
            if sent:
                delivered[robot_id] += 1
            row[robot_id] = {
                "action": decision.action,
                "reason": decision.reason,
                "sent": sent,
            }
        timeline.append(row)

    ratios = {
        robot: delivered[robot] / max(1, offered[robot])
        for robot in robots
    }
    return {
        "policy": label,
        "offered": offered,
        "delivered": delivered,
        "control_delivery_ratio_by_robot": ratios,
        "min_control_delivery_ratio": min(ratios.values()),
        "control_delivery_jain_index": jain_index(ratios.values()),
        "actions_by_robot": actions,
        "timeline": timeline,
    }


def render_markdown(summary: dict[str, object]) -> str:
    policies = summary.get("policies", [])
    lines = [
        "# Robot Budget Controller Smoke",
        "",
        "This deterministic smoke keeps two robots contending for one control",
        "packet slot per tick.  The baseline has no robot-level SLO memory; the",
        "budget-aware wrapper maintains per-robot virtual queues and promotes",
        "the robot that missed its control budget in previous ticks.",
        "",
        "| policy | robot_0000 delivery | robot_0001 delivery | min delivery | Jain |",
        "| --- | ---: | ---: | ---: | ---: |",
    ]
    for item in policies if isinstance(policies, list) else []:
        if not isinstance(item, dict):
            continue
        ratios = item.get("control_delivery_ratio_by_robot", {})
        ratio_map = ratios if isinstance(ratios, dict) else {}
        lines.append(
            "| "
            f"`{item.get('policy', '')}` | "
            f"{_fmt(ratio_map.get('robot_0000', 0.0))} | "
            f"{_fmt(ratio_map.get('robot_0001', 0.0))} | "
            f"{_fmt(item.get('min_control_delivery_ratio', 0.0))} | "
            f"{_fmt(item.get('control_delivery_jain_index', 0.0))} |"
        )
    lines.append("")
    lines.append("## Interpretation")
    lines.append("")
    lines.append(
        "The useful signal is not absolute throughput in this artificial one-slot"
        " setup.  The signal is whether the controller converts per-robot SLO"
        " debt into future scheduling pressure, preventing a stable starvation"
        " pattern under identical control flows."
    )
    return "\n".join(lines) + "\n"


def _control_flow(robot_id: str) -> FlowSpec:
    return FlowSpec(
        flow_id=f"{robot_id}:cmd",
        robot_id=robot_id,
        topic=f"/{robot_id}/cmd_vel",
        flow_class=FlowClass.CONTROL,
        qos=QoSProfile(deadline_ms=45, lifespan_ms=135),
        qoe=QoEProfile(),
        nominal_size_bytes=96,
        nominal_rate_hz=10,
        causal_task_gain=0.8,
    )


def _observation(flow: FlowSpec, tick: int) -> FlowObservation:
    return FlowObservation(
        age_ms=10.0 + (tick % 2),
        queue_depth=1,
        measured_loss=0.01,
        measured_rtt_ms=20,
        observed_jitter_ms=2,
        task=TaskContext(
            task_id="budget_smoke",
            robot_id=flow.robot_id,
            task_criticality=1.0,
            collision_risk=0.6,
            operator_attention=0.0,
            coordination_pressure=0.2,
        ),
    )


def _fmt(value: object) -> str:
    return f"{float(value):.4f}"


if __name__ == "__main__":
    raise SystemExit(main())

"""Run a deterministic fleet-level QoS/QoE optimizer probe."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from fleetqox.fleet_optimizer import (
    FleetFlowDemand,
    FleetOptimizerConfig,
    FleetQoEPathOptimizer,
    PathTelemetry,
    RobotQoEState,
    decisions_to_dicts,
    static_primary_decisions,
    summarize_decisions,
    summary_to_dict,
)
from fleetqox.model import FlowClass


SCHEMA_VERSION = "fleetrmw.fleet_optimizer_probe.v1"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--robots", type=int, default=16)
    parser.add_argument("--capacity-bytes", type=int, default=58_000)
    parser.add_argument("--summary-json", default="results_fleet_optimizer/fleet_optimizer_probe_summary.json")
    parser.add_argument("--markdown", default="docs/FLEET_LEVEL_QOS_QOE_OPTIMIZER_V1.md")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    summary = run_probe(robots=args.robots, capacity_bytes=args.capacity_bytes)
    summary_path = ROOT / args.summary_json
    summary_path.parent.mkdir(parents=True, exist_ok=True)
    summary_path.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    markdown_path = ROOT / args.markdown
    markdown_path.parent.mkdir(parents=True, exist_ok=True)
    markdown_path.write_text(render_markdown(summary, args.summary_json), encoding="utf-8")

    if args.json:
        print(json.dumps(summary, sort_keys=True))
    else:
        print("fleet-optimizer-probe")
        print(f"  status: {summary['status']}")
        print(f"  optimizer_delivery: {summary['optimizer']['expected_delivery_ratio']:.4f}")
        print(f"  static_delivery: {summary['static_primary']['expected_delivery_ratio']:.4f}")
    return 0 if summary["status"] == "ok" else 1


def run_probe(*, robots: int, capacity_bytes: int) -> dict[str, Any]:
    if robots <= 0:
        raise ValueError("robots must be positive")
    paths = synthetic_paths()
    flows = synthetic_flows(robots)
    robot_states = synthetic_robot_states(robots)
    optimizer = FleetQoEPathOptimizer(
        FleetOptimizerConfig(
            capacity_bytes_per_tick=capacity_bytes,
            redundant_deadline_ms=35.0,
            redundancy_risk_threshold=1.45,
            failover_risk_margin=0.25,
        )
    )
    optimizer_decisions = optimizer.decide(flows, paths, robot_states)
    static_decisions = static_primary_decisions(
        flows,
        "primary_wifi",
        capacity_bytes_per_tick=capacity_bytes,
    )
    optimizer_summary = summarize_decisions(
        optimizer_decisions,
        flows,
        paths,
        policy="fleet_qoe_optimizer",
    )
    static_summary = summarize_decisions(
        static_decisions,
        flows,
        paths,
        policy="static_primary",
    )
    optimizer_dict = summary_to_dict(optimizer_summary)
    static_dict = summary_to_dict(static_summary)
    improvements = {
        "expected_delivery_delta": optimizer_dict["expected_delivery_ratio"] - static_dict["expected_delivery_ratio"],
        "deadline_success_delta": optimizer_dict["expected_deadline_success_ratio"]
        - static_dict["expected_deadline_success_ratio"],
        "qoe_utility_delta": optimizer_dict["qoe_utility"] - static_dict["qoe_utility"],
        "control_fairness_delta": optimizer_dict["control_delivery_jain_index"]
        - static_dict["control_delivery_jain_index"],
    }
    status = (
        improvements["expected_delivery_delta"] > 0.08
        and improvements["deadline_success_delta"] > 0.10
        and improvements["qoe_utility_delta"] > 4.0
        and optimizer_dict["send_count"] > 0
        and optimizer_dict["redundant_count"] >= 1
        and any(
            decision.selected_paths and decision.selected_paths[0] == "backup_5g"
            for decision in optimizer_decisions
            if decision.mode.value == "unicast"
        )
    )
    return {
        "schema_version": SCHEMA_VERSION,
        "status": "ok" if status else "failed",
        "robots": robots,
        "capacity_bytes_per_tick": capacity_bytes,
        "paths": [path.__dict__ for path in paths],
        "optimizer": optimizer_dict,
        "static_primary": static_dict,
        "improvements": improvements,
        "optimizer_decisions": decisions_to_dicts(optimizer_decisions),
        "static_decisions": decisions_to_dicts(static_decisions),
    }


def synthetic_paths() -> list[PathTelemetry]:
    return [
        PathTelemetry(
            "primary_wifi",
            latency_ms=58.0,
            jitter_ms=22.0,
            loss=0.18,
            nack_rate=0.16,
            deadline_miss_ratio=0.24,
            bandwidth_utilization=0.88,
        ),
        PathTelemetry(
            "backup_5g",
            latency_ms=24.0,
            jitter_ms=5.0,
            loss=0.035,
            nack_rate=0.025,
            deadline_miss_ratio=0.04,
            bandwidth_utilization=0.42,
        ),
        PathTelemetry(
            "low_cost_wan",
            latency_ms=115.0,
            jitter_ms=35.0,
            loss=0.08,
            nack_rate=0.05,
            deadline_miss_ratio=0.18,
            bandwidth_utilization=0.36,
        ),
    ]


def synthetic_robot_states(robots: int) -> list[RobotQoEState]:
    states = []
    for index in range(robots):
        debt_group = index % 4 == 0
        states.append(
            RobotQoEState(
                robot_id=f"robot_{index:04d}",
                control_delivery_ratio=0.90 if debt_group else 0.985,
                deadline_miss_ratio=0.18 if debt_group else 0.04,
                qoe_score=0.78 if index % 5 == 0 else 0.95,
            )
        )
    return states


def synthetic_flows(robots: int) -> list[FleetFlowDemand]:
    flows: list[FleetFlowDemand] = []
    for index in range(robots):
        robot = f"robot_{index:04d}"
        debt_bonus = 0.08 if index % 4 == 0 else 0.0
        flows.append(
            FleetFlowDemand(
                flow_id=f"{robot}/cmd_vel",
                robot_id=robot,
                flow_class=FlowClass.CONTROL,
                deadline_ms=30.0,
                payload_bytes=680,
                rate_hz=20.0,
                criticality=0.95 + debt_bonus,
                age_ms=14.0,
                lifespan_ms=90.0,
            )
        )
        flows.append(
            FleetFlowDemand(
                flow_id=f"{robot}/odom",
                robot_id=robot,
                flow_class=FlowClass.STATE,
                deadline_ms=95.0,
                payload_bytes=900,
                rate_hz=15.0,
                criticality=0.65 + debt_bonus,
                age_ms=38.0,
                lifespan_ms=180.0,
            )
        )
        flows.append(
            FleetFlowDemand(
                flow_id=f"{robot}/scan",
                robot_id=robot,
                flow_class=FlowClass.PERCEPTION,
                deadline_ms=180.0,
                payload_bytes=4200,
                rate_hz=8.0,
                criticality=0.38,
                qoe_weight=0.28,
                age_ms=55.0,
                lifespan_ms=320.0,
            )
        )
        if index % 5 == 0:
            flows.append(
                FleetFlowDemand(
                    flow_id=f"{robot}/operator_view",
                    robot_id=robot,
                    flow_class=FlowClass.HUMAN_QOE,
                    deadline_ms=120.0,
                    payload_bytes=3600,
                    rate_hz=6.0,
                    criticality=0.35,
                    qoe_weight=0.9,
                    age_ms=48.0,
                    lifespan_ms=260.0,
                )
            )
    return flows


def render_markdown(summary: dict[str, Any], summary_path: str) -> str:
    rows = [
        ("static_primary", summary["static_primary"]),
        ("fleet_qoe_optimizer", summary["optimizer"]),
    ]
    lines = [
        "# Fleet-Level QoS/QoE Optimizer V1",
        "",
        "This artifact introduces the fleet-level path optimizer above the RMW/router data plane.",
        "",
        f"- Summary: `{summary_path}`",
        f"- Robots: `{summary['robots']}`",
        f"- Capacity bytes/tick: `{summary['capacity_bytes_per_tick']}`",
        "",
        "## Policy Comparison",
        "",
        "| policy | delivery | deadline success | control fairness | QoE utility | redundant | drops | bytes |",
        "|---|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for policy, row in rows:
        lines.append(
            "| "
            + " | ".join(
                [
                    policy,
                    _fmt(row["expected_delivery_ratio"]),
                    _fmt(row["expected_deadline_success_ratio"]),
                    _fmt(row["control_delivery_jain_index"]),
                    _fmt(row["qoe_utility"]),
                    str(row["redundant_count"]),
                    str(row["drop_count"]),
                    str(row["bytes_allocated"]),
                ]
            )
            + " |"
        )
    lines.extend(
        [
            "",
            "## Improvement",
            "",
        ]
    )
    for key, value in summary["improvements"].items():
        lines.append(f"- `{key}`: `{_fmt(value)}`")
    lines.extend(
        [
            "",
            "## Interpretation",
            "",
            "- The optimizer scores each path using loss, latency, jitter, NACK rate, deadline misses, and utilization.",
            "- Robot-level QoE debt increases utility for robots with weak recent delivery or deadline performance.",
            "- The policy can choose unicast, redundant routing, semantic degradation, or defer/drop under fleet capacity pressure.",
            "",
        ]
    )
    return "\n".join(lines)


def _fmt(value: object) -> str:
    return f"{float(value):.4f}"


if __name__ == "__main__":
    raise SystemExit(main())

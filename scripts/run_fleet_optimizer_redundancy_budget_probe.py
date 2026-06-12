"""Probe failure-domain-aware fleet redundancy budgeting."""

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
    TransportMode,
    decisions_to_dicts,
)
from fleetqox.model import FlowClass


SCHEMA_VERSION = "fleetrmw.fleet_optimizer_redundancy_budget_probe.v1"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--robots", type=int, default=4)
    parser.add_argument("--payload-bytes", type=int, default=700)
    parser.add_argument("--protected-robot-budget", type=int, default=2)
    parser.add_argument(
        "--summary-json",
        default=(
            "results_rmw_socket/"
            "fleet_optimizer_redundancy_budget_probe_summary.json"
        ),
    )
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    summary = run_probe(
        robots=max(args.robots, 1),
        payload_bytes=max(args.payload_bytes, 1),
        protected_robot_budget=max(args.protected_robot_budget, 0),
    )
    output = ROOT / args.summary_json
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(summary, sort_keys=True) + "\n", encoding="utf-8")

    if args.json:
        print(json.dumps(summary, sort_keys=True))
    else:
        print("fleetrmw-fleet-optimizer-redundancy-budget-probe")
        print(f"  status: {summary['status']}")
        print(f"  redundant_count: {summary['redundant_count']}")
        print(f"  unicast_count: {summary['unicast_count']}")
        print(f"  path_transmissions: {summary['path_transmissions']}")
        print(f"  full_redundancy_path_transmissions: {summary['full_redundancy_path_transmissions']}")
    return 0 if summary["status"] == "ok" else 1


def run_probe(
    *,
    robots: int,
    payload_bytes: int,
    protected_robot_budget: int,
) -> dict[str, Any]:
    flows = [
        FleetFlowDemand(
            flow_id=f"robot_{index:04d}/cmd_vel",
            robot_id=f"robot_{index:04d}",
            flow_class=FlowClass.CONTROL,
            deadline_ms=80.0,
            payload_bytes=payload_bytes,
            rate_hz=20.0,
            criticality=1.0,
        )
        for index in range(robots)
    ]
    protected_count = min(protected_robot_budget, robots)
    robot_states = [
        RobotQoEState(
            robot_id=f"robot_{index:04d}",
            control_delivery_ratio=0.78 if index < protected_count else 0.99,
            deadline_miss_ratio=0.22 if index < protected_count else 0.0,
            qoe_score=0.72 if index < protected_count else 0.98,
        )
        for index in range(robots)
    ]
    paths = [
        PathTelemetry(
            "wifi_5ghz",
            latency_ms=70.0,
            jitter_ms=18.0,
            loss=0.08,
            nack_rate=0.06,
            failure_domain="warehouse_ap",
        ),
        PathTelemetry(
            "wifi_24ghz",
            latency_ms=76.0,
            jitter_ms=22.0,
            loss=0.1,
            nack_rate=0.08,
            failure_domain="warehouse_ap",
        ),
        PathTelemetry(
            "private_5g",
            latency_ms=34.0,
            jitter_ms=5.0,
            loss=0.02,
            nack_rate=0.01,
            failure_domain="private_5g_core",
        ),
    ]
    redundancy_budget = protected_count * payload_bytes
    optimizer = FleetQoEPathOptimizer(
        FleetOptimizerConfig(
            capacity_bytes_per_tick=robots * payload_bytes + redundancy_budget,
            redundant_deadline_ms=100.0,
            redundancy_risk_threshold=0.1,
            redundancy_budget_bytes_per_tick=redundancy_budget,
            require_failure_domain_diversity=True,
        )
    )
    decisions = optimizer.decide(flows, paths, robot_states)
    redundant = [decision for decision in decisions if decision.mode is TransportMode.REDUNDANT]
    unicast = [decision for decision in decisions if decision.mode is TransportMode.UNICAST]
    dropped = [decision for decision in decisions if decision.mode is TransportMode.DROP]
    protected_robots = sorted(decision.robot_id for decision in redundant)
    expected_protected = [f"robot_{index:04d}" for index in range(protected_count)]
    domain_map = {path.path_id: path.failure_domain for path in paths}
    failure_domain_diverse = all(
        len({domain_map[path_id] for path_id in decision.selected_paths})
        == len(decision.selected_paths)
        for decision in redundant
    )
    path_transmissions = sum(len(decision.selected_paths) for decision in decisions)
    full_redundancy_path_transmissions = robots * 2
    reduction_ratio = (
        1.0 - path_transmissions / full_redundancy_path_transmissions
        if full_redundancy_path_transmissions > 0 else 0.0
    )
    status = (
        len(redundant) == protected_count
        and len(unicast) == robots - protected_count
        and not dropped
        and protected_robots == expected_protected
        and failure_domain_diverse
        and path_transmissions == robots + protected_count
    )
    return {
        "schema_version": SCHEMA_VERSION,
        "status": "ok" if status else "failed",
        "robot_count": robots,
        "payload_bytes": payload_bytes,
        "protected_robot_budget": protected_count,
        "redundancy_budget_bytes_per_tick": redundancy_budget,
        "redundant_count": len(redundant),
        "unicast_count": len(unicast),
        "drop_count": len(dropped),
        "protected_robots": protected_robots,
        "failure_domain_diverse": failure_domain_diverse,
        "path_transmissions": path_transmissions,
        "full_redundancy_path_transmissions": full_redundancy_path_transmissions,
        "path_transmission_reduction_ratio": reduction_ratio,
        "decisions": decisions_to_dicts(decisions),
    }


if __name__ == "__main__":
    raise SystemExit(main())

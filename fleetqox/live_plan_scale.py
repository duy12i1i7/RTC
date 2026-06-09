"""Fleet-scale live path-plan probe helpers."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import random
import time
from pathlib import Path
from typing import Iterable

from .fleet_optimizer import (
    FleetFlowDemand,
    FleetOptimizerConfig,
    RobotQoEState,
    TransportMode,
)
from .model import FlowClass
from .online_fleet_planner import (
    FleetTopicDemand,
    OnlineFleetPathPlan,
    OnlineFleetPathPlanner,
    OnlineFleetPlannerConfig,
    PathObservation,
)


SCHEMA_VERSION = "fleetrmw.live_plan_scale_probe.v1"


@dataclass(frozen=True)
class LivePlanScaleConfig:
    robot_count: int = 100
    ticks: int = 12
    seed: int = 7
    control_payload_bytes: int = 680
    state_payload_bytes: int = 900
    control_deadline_ms: float = 30.0
    state_deadline_ms: float = 120.0


def run_live_plan_scale_probe(config: LivePlanScaleConfig | None = None) -> dict[str, object]:
    cfg = config or LivePlanScaleConfig()
    if cfg.robot_count <= 0:
        raise ValueError("robot_count must be positive")
    if cfg.ticks <= 0:
        raise ValueError("ticks must be positive")

    rng = random.Random(cfg.seed)
    demands = build_scaled_demands(cfg, rng)
    robot_states = build_scaled_robot_states(cfg, rng)
    planner = OnlineFleetPathPlanner(
        OnlineFleetPlannerConfig(
            optimizer=FleetOptimizerConfig(
                capacity_bytes_per_tick=max(4096, cfg.robot_count * 2600),
                redundant_deadline_ms=35.0,
                redundancy_risk_threshold=1.0,
            ),
            telemetry_alpha=1.0,
            min_dwell_ticks=0,
            switch_score_margin=0.20,
        )
    )

    decision_times_ms = []
    changed_topic_counts = []
    plan_bytes = []
    last_plan: OnlineFleetPathPlan | None = None
    for tick in range(cfg.ticks):
        started_ns = time.perf_counter_ns()
        plan = planner.update(
            tick=tick,
            observations=observations_for_tick(tick, cfg.ticks),
            demands=demands,
            robot_states=robot_states,
        )
        elapsed_ms = (time.perf_counter_ns() - started_ns) / 1_000_000.0
        decision_times_ms.append(elapsed_ms)
        changed_topic_counts.append(len(plan.changed_topics))
        plan_bytes.append(len(plan.path_plan_env.encode("utf-8")))
        last_plan = plan

    assert last_plan is not None
    final_rules = _parse_plan_rules(last_plan.path_plan_env)
    mode_counts = _mode_counts(last_plan)
    status = (
        len(final_rules) == len(demands)
        and mode_counts.get(TransportMode.REDUNDANT.value, 0) >= cfg.robot_count
        and mode_counts.get(TransportMode.UNICAST.value, 0) >= cfg.robot_count
    )
    return {
        "schema_version": SCHEMA_VERSION,
        "status": "ok" if status else "failed",
        "robot_count": cfg.robot_count,
        "topic_count": len(demands),
        "ticks": cfg.ticks,
        "seed": cfg.seed,
        "path_count": len(last_plan.path_telemetry),
        "decision_ms": {
            "min": min(decision_times_ms),
            "p50": _percentile(decision_times_ms, 50.0),
            "p95": _percentile(decision_times_ms, 95.0),
            "max": max(decision_times_ms),
            "mean": sum(decision_times_ms) / len(decision_times_ms),
        },
        "changed_topics": {
            "max": max(changed_topic_counts),
            "final": len(last_plan.changed_topics),
        },
        "path_plan_bytes": {
            "max": max(plan_bytes),
            "final": plan_bytes[-1],
        },
        "final_rule_count": len(final_rules),
        "final_mode_counts": mode_counts,
        "final_path_plan_sha256": hashlib.sha256(
            last_plan.path_plan_env.encode("utf-8")
        ).hexdigest(),
        "final_path_plan_preview": _path_plan_preview(last_plan.path_plan_env),
        "final_topic_decision_preview": [
            decision.as_dict() for decision in last_plan.topic_decisions[: min(8, len(last_plan.topic_decisions))]
        ],
    }


def build_scaled_demands(
    config: LivePlanScaleConfig,
    rng: random.Random,
) -> tuple[FleetTopicDemand, ...]:
    demands: list[FleetTopicDemand] = []
    for index in range(config.robot_count):
        robot_id = f"robot_{index:04d}"
        control_jitter = rng.randint(-40, 40)
        state_jitter = rng.randint(-60, 60)
        demands.append(
            FleetTopicDemand(
                f"/{robot_id}/cmd_vel",
                FleetFlowDemand(
                    flow_id=f"{robot_id}/cmd_vel",
                    robot_id=robot_id,
                    flow_class=FlowClass.CONTROL,
                    deadline_ms=config.control_deadline_ms,
                    payload_bytes=max(128, config.control_payload_bytes + control_jitter),
                    rate_hz=20.0,
                    criticality=0.95,
                    qoe_weight=0.15 if index % 5 == 0 else 0.05,
                    age_ms=12.0,
                    lifespan_ms=90.0,
                ),
            )
        )
        demands.append(
            FleetTopicDemand(
                f"/{robot_id}/odom",
                FleetFlowDemand(
                    flow_id=f"{robot_id}/odom",
                    robot_id=robot_id,
                    flow_class=FlowClass.STATE,
                    deadline_ms=config.state_deadline_ms,
                    payload_bytes=max(128, config.state_payload_bytes + state_jitter),
                    rate_hz=10.0,
                    criticality=0.45,
                    qoe_weight=0.02,
                    age_ms=10.0,
                    lifespan_ms=250.0,
                ),
            )
        )
    return tuple(demands)


def build_scaled_robot_states(
    config: LivePlanScaleConfig,
    rng: random.Random,
) -> tuple[RobotQoEState, ...]:
    states = []
    for index in range(config.robot_count):
        robot_id = f"robot_{index:04d}"
        if index % 11 == 0:
            states.append(
                RobotQoEState(
                    robot_id,
                    control_delivery_ratio=0.88 + rng.random() * 0.04,
                    deadline_miss_ratio=0.14 + rng.random() * 0.08,
                    qoe_score=0.72 + rng.random() * 0.08,
                )
            )
        else:
            states.append(
                RobotQoEState(
                    robot_id,
                    control_delivery_ratio=0.97 + rng.random() * 0.03,
                    deadline_miss_ratio=rng.random() * 0.03,
                    qoe_score=0.91 + rng.random() * 0.08,
                )
            )
    return tuple(states)


def observations_for_tick(tick: int, ticks: int) -> tuple[PathObservation, ...]:
    degrade_after = max(1, ticks // 3)
    primary_degraded = tick >= degrade_after
    if primary_degraded:
        primary = PathObservation(
            "primary_wifi",
            latency_ms=58.0,
            jitter_ms=22.0,
            loss=0.18,
            nack_rate=0.16,
            deadline_miss_ratio=0.24,
            bandwidth_utilization=0.74,
        )
    else:
        primary = PathObservation(
            "primary_wifi",
            latency_ms=10.0,
            jitter_ms=1.0,
            loss=0.01,
            nack_rate=0.01,
            deadline_miss_ratio=0.0,
            bandwidth_utilization=0.10,
        )
    backup = PathObservation(
        "backup_5g",
        latency_ms=24.0,
        jitter_ms=5.0,
        loss=0.035,
        nack_rate=0.025,
        deadline_miss_ratio=0.04,
        bandwidth_utilization=0.42,
    )
    return (primary, backup)


def write_live_plan_scale_summary(summary: dict[str, object], output: str | Path) -> None:
    Path(output).parent.mkdir(parents=True, exist_ok=True)
    Path(output).write_text(json.dumps(summary, indent=2, sort_keys=True), encoding="utf-8")


def render_live_plan_scale_markdown(summary: dict[str, object]) -> str:
    decision_ms = summary.get("decision_ms", {})
    path_plan_bytes = summary.get("path_plan_bytes", {})
    changed_topics = summary.get("changed_topics", {})
    mode_counts = summary.get("final_mode_counts", {})
    lines = [
        "# Live Plan Scale Probe V1",
        "",
        f"- Status: `{summary.get('status')}`",
        f"- Robots: `{summary.get('robot_count')}`",
        f"- Topics: `{summary.get('topic_count')}`",
        f"- Ticks: `{summary.get('ticks')}`",
        f"- Final rules: `{summary.get('final_rule_count')}`",
        f"- Final plan SHA-256: `{summary.get('final_path_plan_sha256')}`",
        "",
        "## Timing",
        "",
        f"- Decision p50 ms: `{_format_metric(_mapping_float(decision_ms, 'p50'))}`",
        f"- Decision p95 ms: `{_format_metric(_mapping_float(decision_ms, 'p95'))}`",
        f"- Decision max ms: `{_format_metric(_mapping_float(decision_ms, 'max'))}`",
        "",
        "## Plan Shape",
        "",
        f"- Max changed topics: `{changed_topics.get('max', 0)}`",
        f"- Final changed topics: `{changed_topics.get('final', 0)}`",
        f"- Max plan bytes: `{path_plan_bytes.get('max', 0)}`",
        f"- Final plan bytes: `{path_plan_bytes.get('final', 0)}`",
        f"- Mode counts: `{mode_counts}`",
        "",
    ]
    return "\n".join(lines)


def write_live_plan_scale_markdown(summary: dict[str, object], output: str | Path) -> None:
    Path(output).parent.mkdir(parents=True, exist_ok=True)
    Path(output).write_text(render_live_plan_scale_markdown(summary), encoding="utf-8")


def _parse_plan_rules(plan_env: str) -> dict[str, tuple[str, ...]]:
    rules = {}
    for raw_rule in plan_env.split(";"):
        if not raw_rule:
            continue
        topic, _, paths = raw_rule.partition("=")
        if not topic or not paths:
            continue
        rules[topic] = tuple(path for path in paths.split("+") if path)
    return rules


def _mode_counts(plan: OnlineFleetPathPlan) -> dict[str, int]:
    counts: dict[str, int] = {}
    for decision in plan.optimizer_decisions:
        key = decision.mode.value
        counts[key] = counts.get(key, 0) + 1
    return counts


def _path_plan_preview(plan_env: str, *, limit: int = 8) -> list[str]:
    return [rule for rule in plan_env.split(";") if rule][:limit]


def _percentile(values: Iterable[float], percentile: float) -> float:
    ordered = sorted(values)
    if not ordered:
        return 0.0
    if len(ordered) == 1:
        return ordered[0]
    rank = (len(ordered) - 1) * min(100.0, max(0.0, percentile)) / 100.0
    lower = int(rank)
    upper = min(len(ordered) - 1, lower + 1)
    fraction = rank - lower
    return ordered[lower] * (1.0 - fraction) + ordered[upper] * fraction


def _mapping_float(mapping: object, key: str) -> float:
    if not isinstance(mapping, dict):
        return 0.0
    try:
        return float(mapping.get(key, 0.0))
    except (TypeError, ValueError):
        return 0.0


def _format_metric(value: float) -> str:
    return f"{value:.4f}"

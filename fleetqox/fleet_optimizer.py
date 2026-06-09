"""Fleet-level QoS/QoE path optimizer.

This module models the control-plane decision that sits above the current
RMW/router data plane.  It turns path telemetry, robot fairness debt, and ROS-like
flow QoS into per-flow transport modes: unicast, redundant, degraded, or drop.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
import math
from statistics import mean
from typing import Iterable, Mapping, Sequence

from .model import FlowClass


class TransportMode(str, Enum):
    UNICAST = "unicast"
    REDUNDANT = "redundant"
    DEGRADED = "degraded"
    DROP = "drop"


@dataclass(frozen=True)
class PathTelemetry:
    path_id: str
    latency_ms: float
    jitter_ms: float
    loss: float
    nack_rate: float = 0.0
    deadline_miss_ratio: float = 0.0
    bandwidth_utilization: float = 0.0


@dataclass(frozen=True)
class RobotQoEState:
    robot_id: str
    control_delivery_ratio: float = 1.0
    deadline_miss_ratio: float = 0.0
    qoe_score: float = 1.0


@dataclass(frozen=True)
class FleetFlowDemand:
    flow_id: str
    robot_id: str
    flow_class: FlowClass
    deadline_ms: float
    payload_bytes: int
    rate_hz: float
    criticality: float
    qoe_weight: float = 0.0
    age_ms: float = 0.0
    lifespan_ms: float = 250.0


@dataclass(frozen=True)
class OptimizerWeights:
    loss: float = 3.2
    latency: float = 1.8
    jitter: float = 1.2
    nack: float = 2.2
    deadline_miss: float = 2.8
    utilization: float = 0.9
    class_value: float = 3.0
    criticality: float = 2.4
    qoe: float = 1.5
    fairness_debt: float = 2.0
    age_pressure: float = 1.0


@dataclass(frozen=True)
class FleetOptimizerConfig:
    capacity_bytes_per_tick: int = 96_000
    redundant_deadline_ms: float = 40.0
    redundancy_risk_threshold: float = 1.65
    failover_risk_margin: float = 0.35
    degrade_floor: float = 0.35
    min_critical_admission_score: float = 7.5
    min_best_effort_admission_score: float = 2.0
    max_redundant_paths: int = 2
    weights: OptimizerWeights = field(default_factory=OptimizerWeights)


@dataclass(frozen=True)
class FleetPathDecision:
    flow_id: str
    robot_id: str
    action: str
    mode: TransportMode
    selected_paths: tuple[str, ...]
    allocated_bytes: int
    utility_score: float
    best_path_score: float
    fleet_fairness_debt: float
    reason: str


@dataclass(frozen=True)
class FleetOptimizerSummary:
    schema_version: str
    policy: str
    decision_count: int
    send_count: int
    redundant_count: int
    degraded_count: int
    drop_count: int
    bytes_allocated: int
    expected_delivery_ratio: float
    expected_deadline_success_ratio: float
    control_delivery_jain_index: float
    qoe_utility: float
    mode_counts: Mapping[str, int]


class FleetQoEPathOptimizer:
    """QoS/QoE-aware path optimizer for fleet communication."""

    def __init__(self, config: FleetOptimizerConfig | None = None) -> None:
        self.config = config or FleetOptimizerConfig()

    def decide(
        self,
        flows: Iterable[FleetFlowDemand],
        paths: Iterable[PathTelemetry],
        robot_states: Iterable[RobotQoEState] = (),
    ) -> list[FleetPathDecision]:
        path_list = list(paths)
        if not path_list:
            raise ValueError("at least one path is required")
        if self.config.capacity_bytes_per_tick < 0:
            raise ValueError("capacity_bytes_per_tick must be non-negative")
        robot_map = {state.robot_id: state for state in robot_states}
        scored: list[tuple[float, FleetFlowDemand, tuple[PathTelemetry, ...], float, float]] = []
        decisions: list[FleetPathDecision] = []

        for flow in flows:
            self._validate_flow(flow)
            fairness_debt = self._fairness_debt(robot_map.get(flow.robot_id))
            if flow.age_ms > flow.lifespan_ms:
                decisions.append(
                    FleetPathDecision(
                        flow.flow_id,
                        flow.robot_id,
                        "drop",
                        TransportMode.DROP,
                        (),
                        0,
                        0.0,
                        math.inf,
                        fairness_debt,
                        "stale beyond lifespan",
                    )
                )
                continue
            ranked_paths = tuple(sorted(path_list, key=lambda path: self.path_score(path, flow)))
            best_score = self.path_score(ranked_paths[0], flow)
            utility = self.utility_score(flow, fairness_debt)
            scored.append((utility / max(1, flow.payload_bytes), flow, ranked_paths, best_score, fairness_debt))

        remaining = self.config.capacity_bytes_per_tick
        for _, flow, ranked_paths, best_score, fairness_debt in sorted(
            scored,
            key=lambda item: (item[0], self.utility_score(item[1], item[4])),
            reverse=True,
        ):
            utility = self.utility_score(flow, fairness_debt)
            mode, selected_paths, reason = self._choose_mode(flow, ranked_paths, best_score)
            bytes_needed = flow.payload_bytes * max(1, len(selected_paths))
            if utility < self._admission_floor(flow):
                decisions.append(
                    FleetPathDecision(
                        flow.flow_id,
                        flow.robot_id,
                        "drop",
                        TransportMode.DROP,
                        (),
                        0,
                        utility,
                        best_score,
                        fairness_debt,
                        "below admission floor",
                    )
                )
                continue
            if bytes_needed <= remaining:
                remaining -= bytes_needed
                decisions.append(
                    FleetPathDecision(
                        flow.flow_id,
                        flow.robot_id,
                        "send",
                        mode,
                        selected_paths,
                        bytes_needed,
                        utility,
                        best_score,
                        fairness_debt,
                        reason,
                    )
                )
                continue
            if self._degradable(flow) and flow.payload_bytes * self.config.degrade_floor <= remaining:
                degraded_bytes = max(1, int(flow.payload_bytes * self.config.degrade_floor))
                remaining -= degraded_bytes
                decisions.append(
                    FleetPathDecision(
                        flow.flow_id,
                        flow.robot_id,
                        "send_degraded",
                        TransportMode.DEGRADED,
                        (ranked_paths[0].path_id,),
                        degraded_bytes,
                        utility,
                        best_score,
                        fairness_debt,
                        "capacity pressure: semantic degradation",
                    )
                )
            else:
                decisions.append(
                    FleetPathDecision(
                        flow.flow_id,
                        flow.robot_id,
                        "defer",
                        TransportMode.DROP,
                        (),
                        0,
                        utility,
                        best_score,
                        fairness_debt,
                        "insufficient fleet capacity",
                    )
                )
        return sorted(decisions, key=lambda decision: decision.flow_id)

    def path_score(self, path: PathTelemetry, flow: FleetFlowDemand) -> float:
        weights = self.config.weights
        deadline = max(1.0, flow.deadline_ms)
        return (
            weights.loss * _clip01(path.loss)
            + weights.latency * max(0.0, path.latency_ms / deadline)
            + weights.jitter * max(0.0, path.jitter_ms / deadline)
            + weights.nack * _clip01(path.nack_rate)
            + weights.deadline_miss * _clip01(path.deadline_miss_ratio)
            + weights.utilization * _clip01(path.bandwidth_utilization)
        )

    def utility_score(self, flow: FleetFlowDemand, fairness_debt: float = 0.0) -> float:
        weights = self.config.weights
        age_pressure = min(2.0, flow.age_ms / max(1.0, flow.deadline_ms))
        return (
            weights.class_value * _class_value(flow.flow_class)
            + weights.criticality * _clip01(flow.criticality)
            + weights.qoe * _clip01(flow.qoe_weight)
            + weights.fairness_debt * fairness_debt
            + weights.age_pressure * age_pressure
        )

    def _choose_mode(
        self,
        flow: FleetFlowDemand,
        ranked_paths: Sequence[PathTelemetry],
        best_score: float,
    ) -> tuple[TransportMode, tuple[str, ...], str]:
        best = ranked_paths[0]
        second = ranked_paths[1] if len(ranked_paths) > 1 else None
        urgent = flow.deadline_ms <= self.config.redundant_deadline_ms
        qoe_sensitive = flow.qoe_weight >= 0.65
        critical = flow.flow_class in {
            FlowClass.SAFETY,
            FlowClass.CONTROL,
            FlowClass.COORDINATION,
        }
        if (
            second is not None
            and (urgent or qoe_sensitive or critical)
            and best_score >= self.config.redundancy_risk_threshold
        ):
            selected = tuple(path.path_id for path in ranked_paths[: self.config.max_redundant_paths])
            return TransportMode.REDUNDANT, selected, "high-risk urgent/QoE flow: redundant paths"
        return TransportMode.UNICAST, (best.path_id,), "best scored path"

    def _fairness_debt(self, state: RobotQoEState | None) -> float:
        if state is None:
            return 0.0
        control_debt = max(0.0, 0.98 - state.control_delivery_ratio)
        deadline_debt = _clip01(state.deadline_miss_ratio)
        qoe_debt = max(0.0, 0.92 - state.qoe_score)
        return _clip01(control_debt + deadline_debt + qoe_debt)

    def _admission_floor(self, flow: FleetFlowDemand) -> float:
        if flow.flow_class in {FlowClass.SAFETY, FlowClass.CONTROL, FlowClass.COORDINATION}:
            return self.config.min_critical_admission_score
        return self.config.min_best_effort_admission_score

    def _degradable(self, flow: FleetFlowDemand) -> bool:
        return flow.flow_class in {FlowClass.PERCEPTION, FlowClass.HUMAN_QOE, FlowClass.DEBUG, FlowClass.BULK}

    def _validate_flow(self, flow: FleetFlowDemand) -> None:
        if flow.payload_bytes <= 0:
            raise ValueError("payload_bytes must be positive")
        if flow.rate_hz <= 0:
            raise ValueError("rate_hz must be positive")
        if flow.deadline_ms <= 0 or flow.lifespan_ms <= 0:
            raise ValueError("deadline_ms and lifespan_ms must be positive")


def summarize_decisions(
    decisions: Iterable[FleetPathDecision],
    flows: Iterable[FleetFlowDemand],
    paths: Iterable[PathTelemetry],
    *,
    policy: str,
) -> FleetOptimizerSummary:
    decision_list = list(decisions)
    flow_map = {flow.flow_id: flow for flow in flows}
    path_map = {path.path_id: path for path in paths}
    sent = [decision for decision in decision_list if decision.action.startswith("send")]
    mode_counts: dict[str, int] = {}
    for decision in decision_list:
        mode_counts[decision.mode.value] = mode_counts.get(decision.mode.value, 0) + 1
    delivery_values = []
    deadline_values = []
    qoe_values = []
    per_robot_control: dict[str, list[float]] = {}
    for decision in sent:
        flow = flow_map[decision.flow_id]
        selected = [path_map[path_id] for path_id in decision.selected_paths if path_id in path_map]
        delivery = _expected_delivery(selected)
        deadline = _expected_deadline_success(selected, flow)
        delivery_values.append(delivery)
        deadline_values.append(deadline)
        qoe_values.append(delivery * deadline * (1.0 + flow.qoe_weight + flow.criticality))
        if flow.flow_class is FlowClass.CONTROL:
            per_robot_control.setdefault(flow.robot_id, []).append(delivery * deadline)
    control_delivery = [mean(values) for values in per_robot_control.values()]
    return FleetOptimizerSummary(
        schema_version="fleetrmw.fleet_optimizer_summary.v1",
        policy=policy,
        decision_count=len(decision_list),
        send_count=len(sent),
        redundant_count=sum(1 for decision in decision_list if decision.mode is TransportMode.REDUNDANT),
        degraded_count=sum(1 for decision in decision_list if decision.mode is TransportMode.DEGRADED),
        drop_count=sum(1 for decision in decision_list if decision.action in {"drop", "defer"}),
        bytes_allocated=sum(decision.allocated_bytes for decision in decision_list),
        expected_delivery_ratio=mean(delivery_values) if delivery_values else 0.0,
        expected_deadline_success_ratio=mean(deadline_values) if deadline_values else 0.0,
        control_delivery_jain_index=jain_index(control_delivery),
        qoe_utility=sum(qoe_values),
        mode_counts=mode_counts,
    )


def static_primary_decisions(
    flows: Iterable[FleetFlowDemand],
    primary_path_id: str,
    *,
    capacity_bytes_per_tick: int,
) -> list[FleetPathDecision]:
    decisions = []
    remaining = capacity_bytes_per_tick
    for flow in flows:
        if flow.payload_bytes <= remaining:
            remaining -= flow.payload_bytes
            decisions.append(
                FleetPathDecision(
                    flow.flow_id,
                    flow.robot_id,
                    "send",
                    TransportMode.UNICAST,
                    (primary_path_id,),
                    flow.payload_bytes,
                    _class_value(flow.flow_class),
                    0.0,
                    0.0,
                    "static primary path",
                )
            )
        else:
            decisions.append(
                FleetPathDecision(
                    flow.flow_id,
                    flow.robot_id,
                    "defer",
                    TransportMode.DROP,
                    (),
                    0,
                    _class_value(flow.flow_class),
                    0.0,
                    0.0,
                    "static primary capacity exhausted",
                )
            )
    return decisions


def decisions_to_dicts(decisions: Iterable[FleetPathDecision]) -> list[dict[str, object]]:
    return [
        {
            "flow_id": decision.flow_id,
            "robot_id": decision.robot_id,
            "action": decision.action,
            "mode": decision.mode.value,
            "selected_paths": list(decision.selected_paths),
            "allocated_bytes": decision.allocated_bytes,
            "utility_score": decision.utility_score,
            "best_path_score": decision.best_path_score,
            "fleet_fairness_debt": decision.fleet_fairness_debt,
            "reason": decision.reason,
        }
        for decision in decisions
    ]


def summary_to_dict(summary: FleetOptimizerSummary) -> dict[str, object]:
    return {
        "schema_version": summary.schema_version,
        "policy": summary.policy,
        "decision_count": summary.decision_count,
        "send_count": summary.send_count,
        "redundant_count": summary.redundant_count,
        "degraded_count": summary.degraded_count,
        "drop_count": summary.drop_count,
        "bytes_allocated": summary.bytes_allocated,
        "expected_delivery_ratio": summary.expected_delivery_ratio,
        "expected_deadline_success_ratio": summary.expected_deadline_success_ratio,
        "control_delivery_jain_index": summary.control_delivery_jain_index,
        "qoe_utility": summary.qoe_utility,
        "mode_counts": dict(summary.mode_counts),
    }


def jain_index(values: Iterable[float]) -> float:
    items = [max(0.0, value) for value in values]
    if not items:
        return 1.0
    numerator = sum(items) ** 2
    denominator = len(items) * sum(value * value for value in items)
    return numerator / denominator if denominator > 0 else 1.0


def _expected_delivery(paths: Sequence[PathTelemetry]) -> float:
    if not paths:
        return 0.0
    miss_probability = 1.0
    for path in paths:
        miss_probability *= _clip01(path.loss)
    return 1.0 - miss_probability


def _expected_deadline_success(paths: Sequence[PathTelemetry], flow: FleetFlowDemand) -> float:
    if not paths:
        return 0.0
    success_values = []
    for path in paths:
        lateness = max(0.0, path.latency_ms + path.jitter_ms - flow.deadline_ms)
        success_values.append(max(0.0, 1.0 - lateness / max(1.0, flow.deadline_ms)))
    return max(success_values)


def _class_value(flow_class: FlowClass) -> float:
    return {
        FlowClass.SAFETY: 4.2,
        FlowClass.CONTROL: 3.8,
        FlowClass.COORDINATION: 3.2,
        FlowClass.STATE: 2.4,
        FlowClass.HUMAN_QOE: 2.1,
        FlowClass.PERCEPTION: 1.5,
        FlowClass.DEBUG: 0.4,
        FlowClass.BULK: 0.2,
    }[flow_class]


def _clip01(value: float) -> float:
    return min(1.0, max(0.0, value))

"""Online fleet path-plan controller.

The planner closes the loop between per-path observations and the fleet-level
QoS/QoE optimizer. It smooths measured path outcomes, applies a small
anti-flapping guard per topic, and exports the topic-to-path plan consumed by
the C++ `fleet_plan` RMW mode.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterable, Mapping

from .fleet_optimizer import (
    FleetFlowDemand,
    FleetOptimizerConfig,
    FleetPathDecision,
    FleetQoEPathOptimizer,
    PathTelemetry,
    RobotQoEState,
    TransportMode,
    decisions_to_dicts,
)


SCHEMA_VERSION = "fleetrmw.online_fleet_path_plan.v1"


@dataclass(frozen=True)
class PathObservation:
    path_id: str
    latency_ms: float
    jitter_ms: float
    sent_frames: int = 0
    delivered_frames: int = 0
    nack_frames: int = 0
    deadline_miss_frames: int = 0
    bytes_sent: int = 0
    capacity_bytes: int = 0
    loss: float | None = None
    nack_rate: float | None = None
    deadline_miss_ratio: float | None = None
    bandwidth_utilization: float | None = None

    def to_telemetry(self) -> PathTelemetry:
        sent = max(0, int(self.sent_frames))
        delivered = max(0, int(self.delivered_frames))
        denominator = max(1, sent)
        loss = _clip01(1.0 - delivered / denominator) if self.loss is None else _clip01(self.loss)
        nack_rate = (
            _clip01(max(0, int(self.nack_frames)) / denominator)
            if self.nack_rate is None
            else _clip01(self.nack_rate)
        )
        deadline_miss_ratio = (
            _clip01(max(0, int(self.deadline_miss_frames)) / denominator)
            if self.deadline_miss_ratio is None
            else _clip01(self.deadline_miss_ratio)
        )
        bandwidth_utilization = (
            _clip01(max(0, int(self.bytes_sent)) / max(1, int(self.capacity_bytes)))
            if self.bandwidth_utilization is None
            else _clip01(self.bandwidth_utilization)
        )
        return PathTelemetry(
            path_id=self.path_id,
            latency_ms=max(0.0, float(self.latency_ms)),
            jitter_ms=max(0.0, float(self.jitter_ms)),
            loss=loss,
            nack_rate=nack_rate,
            deadline_miss_ratio=deadline_miss_ratio,
            bandwidth_utilization=bandwidth_utilization,
        )


@dataclass(frozen=True)
class FleetTopicDemand:
    topic: str
    demand: FleetFlowDemand


@dataclass(frozen=True)
class OnlineFleetPlannerConfig:
    optimizer: FleetOptimizerConfig = field(default_factory=FleetOptimizerConfig)
    telemetry_alpha: float = 0.45
    min_dwell_ticks: int = 2
    switch_score_margin: float = 0.25
    emergency_score_margin: float = 0.75


@dataclass(frozen=True)
class TopicPlanDecision:
    topic: str
    flow_id: str
    robot_id: str
    action: str
    mode: str
    selected_paths: tuple[str, ...]
    optimizer_selected_paths: tuple[str, ...]
    changed: bool
    held_by_dwell: bool
    dwell_ticks: int
    previous_paths: tuple[str, ...]
    reason: str

    def as_dict(self) -> dict[str, object]:
        return {
            "topic": self.topic,
            "flow_id": self.flow_id,
            "robot_id": self.robot_id,
            "action": self.action,
            "mode": self.mode,
            "selected_paths": list(self.selected_paths),
            "optimizer_selected_paths": list(self.optimizer_selected_paths),
            "changed": self.changed,
            "held_by_dwell": self.held_by_dwell,
            "dwell_ticks": self.dwell_ticks,
            "previous_paths": list(self.previous_paths),
            "reason": self.reason,
        }


@dataclass(frozen=True)
class OnlineFleetPathPlan:
    schema_version: str
    tick: int
    path_plan_env: str
    changed_topics: tuple[str, ...]
    topic_decisions: tuple[TopicPlanDecision, ...]
    optimizer_decisions: tuple[FleetPathDecision, ...]
    path_telemetry: tuple[PathTelemetry, ...]

    def as_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "tick": self.tick,
            "path_plan_env": self.path_plan_env,
            "changed_topics": list(self.changed_topics),
            "topic_decisions": [decision.as_dict() for decision in self.topic_decisions],
            "optimizer_decisions": decisions_to_dicts(self.optimizer_decisions),
            "path_telemetry": [
                {
                    "path_id": path.path_id,
                    "latency_ms": path.latency_ms,
                    "jitter_ms": path.jitter_ms,
                    "loss": path.loss,
                    "nack_rate": path.nack_rate,
                    "deadline_miss_ratio": path.deadline_miss_ratio,
                    "bandwidth_utilization": path.bandwidth_utilization,
                }
                for path in self.path_telemetry
            ],
        }


class OnlineFleetPathPlanner:
    """Online controller that converts path observations into RMW path plans."""

    def __init__(self, config: OnlineFleetPlannerConfig | None = None) -> None:
        self.config = config or OnlineFleetPlannerConfig()
        self._optimizer = FleetQoEPathOptimizer(self.config.optimizer)
        self._smoothed_paths: dict[str, PathTelemetry] = {}
        self._topic_paths: dict[str, tuple[str, ...]] = {}
        self._topic_last_change: dict[str, int] = {}
        self._last_tick = -1

    def update(
        self,
        *,
        tick: int,
        observations: Iterable[PathObservation],
        demands: Iterable[FleetTopicDemand],
        robot_states: Iterable[RobotQoEState] = (),
    ) -> OnlineFleetPathPlan:
        if tick < self._last_tick:
            raise ValueError("tick must be monotonic")
        self._last_tick = tick
        path_telemetry = self._update_path_telemetry(observations)
        topic_demands = list(demands)
        demand_by_flow = {item.demand.flow_id: item for item in topic_demands}
        optimizer_decisions = tuple(
            self._optimizer.decide(
                [item.demand for item in topic_demands],
                path_telemetry,
                robot_states,
            )
        )
        path_by_id = {path.path_id: path for path in path_telemetry}
        topic_decisions = []
        changed_topics = []
        for decision in optimizer_decisions:
            topic_demand = demand_by_flow.get(decision.flow_id)
            if topic_demand is None:
                continue
            topic_plan = self._topic_plan_decision(
                tick=tick,
                topic=topic_demand.topic,
                decision=decision,
                demand=topic_demand.demand,
                path_by_id=path_by_id,
            )
            topic_decisions.append(topic_plan)
            if topic_plan.changed:
                changed_topics.append(topic_plan.topic)
        return OnlineFleetPathPlan(
            schema_version=SCHEMA_VERSION,
            tick=tick,
            path_plan_env=path_plan_env_from_topic_decisions(topic_decisions),
            changed_topics=tuple(changed_topics),
            topic_decisions=tuple(sorted(topic_decisions, key=lambda item: item.topic)),
            optimizer_decisions=optimizer_decisions,
            path_telemetry=path_telemetry,
        )

    def _update_path_telemetry(
        self,
        observations: Iterable[PathObservation],
    ) -> tuple[PathTelemetry, ...]:
        alpha = _clip01(self.config.telemetry_alpha)
        for observation in observations:
            current = observation.to_telemetry()
            previous = self._smoothed_paths.get(current.path_id)
            self._smoothed_paths[current.path_id] = (
                current if previous is None else _smooth_path(previous, current, alpha)
            )
        if not self._smoothed_paths:
            raise ValueError("at least one path observation is required")
        return tuple(sorted(self._smoothed_paths.values(), key=lambda path: path.path_id))

    def _topic_plan_decision(
        self,
        *,
        tick: int,
        topic: str,
        decision: FleetPathDecision,
        demand: FleetFlowDemand,
        path_by_id: Mapping[str, PathTelemetry],
    ) -> TopicPlanDecision:
        previous_paths = self._topic_paths.get(topic, ())
        optimizer_paths = tuple(decision.selected_paths)
        if decision.action not in {"send", "send_degraded"} or decision.mode is TransportMode.DROP:
            selected_paths: tuple[str, ...] = ()
            held = False
        else:
            selected_paths, held = self._guard_path_switch(
                tick=tick,
                topic=topic,
                previous_paths=previous_paths,
                candidate_paths=optimizer_paths,
                demand=demand,
                path_by_id=path_by_id,
            )
        changed = selected_paths != previous_paths
        if changed:
            self._topic_paths[topic] = selected_paths
            self._topic_last_change[topic] = tick
        dwell_ticks = tick - self._topic_last_change.get(topic, tick)
        return TopicPlanDecision(
            topic=topic,
            flow_id=decision.flow_id,
            robot_id=decision.robot_id,
            action=decision.action,
            mode=decision.mode.value,
            selected_paths=selected_paths,
            optimizer_selected_paths=optimizer_paths,
            changed=changed,
            held_by_dwell=held,
            dwell_ticks=max(0, dwell_ticks),
            previous_paths=previous_paths,
            reason=decision.reason,
        )

    def _guard_path_switch(
        self,
        *,
        tick: int,
        topic: str,
        previous_paths: tuple[str, ...],
        candidate_paths: tuple[str, ...],
        demand: FleetFlowDemand,
        path_by_id: Mapping[str, PathTelemetry],
    ) -> tuple[tuple[str, ...], bool]:
        if not previous_paths or previous_paths == candidate_paths:
            return candidate_paths, False
        dwell = tick - self._topic_last_change.get(topic, tick)
        previous_score = _selected_path_score(previous_paths, demand, path_by_id, self._optimizer)
        candidate_score = _selected_path_score(candidate_paths, demand, path_by_id, self._optimizer)
        score_gain = previous_score - candidate_score
        if (
            dwell >= self.config.min_dwell_ticks
            or score_gain >= self.config.switch_score_margin
            or score_gain >= self.config.emergency_score_margin
        ):
            return candidate_paths, False
        return previous_paths, True


def path_plan_env_from_topic_decisions(decisions: Iterable[TopicPlanDecision]) -> str:
    rules = []
    for decision in sorted(decisions, key=lambda item: item.topic):
        if not decision.selected_paths:
            continue
        rules.append(f"{decision.topic}={'+'.join(decision.selected_paths)}")
    return ";".join(rules)


def optimizer_payload_from_plan(
    plan: OnlineFleetPathPlan,
    *,
    path_targets: Mapping[str, Mapping[str, object]] | None = None,
) -> dict[str, object]:
    payload: dict[str, object] = {
        "schema_version": plan.schema_version,
        "paths": [
            {
                "path_id": path.path_id,
                "latency_ms": path.latency_ms,
                "jitter_ms": path.jitter_ms,
                "loss": path.loss,
                "nack_rate": path.nack_rate,
                "deadline_miss_ratio": path.deadline_miss_ratio,
                "bandwidth_utilization": path.bandwidth_utilization,
            }
            for path in plan.path_telemetry
        ],
        "decisions": [decision.as_dict() for decision in plan.topic_decisions],
    }
    if path_targets:
        payload["path_targets"] = {str(key): dict(value) for key, value in path_targets.items()}
    return payload


def _smooth_path(previous: PathTelemetry, current: PathTelemetry, alpha: float) -> PathTelemetry:
    return PathTelemetry(
        path_id=current.path_id,
        latency_ms=_ewma(previous.latency_ms, current.latency_ms, alpha),
        jitter_ms=_ewma(previous.jitter_ms, current.jitter_ms, alpha),
        loss=_ewma(previous.loss, current.loss, alpha),
        nack_rate=_ewma(previous.nack_rate, current.nack_rate, alpha),
        deadline_miss_ratio=_ewma(
            previous.deadline_miss_ratio,
            current.deadline_miss_ratio,
            alpha,
        ),
        bandwidth_utilization=_ewma(
            previous.bandwidth_utilization,
            current.bandwidth_utilization,
            alpha,
        ),
    )


def _selected_path_score(
    path_ids: tuple[str, ...],
    demand: FleetFlowDemand,
    path_by_id: Mapping[str, PathTelemetry],
    optimizer: FleetQoEPathOptimizer,
) -> float:
    scores = [
        optimizer.path_score(path_by_id[path_id], demand)
        for path_id in path_ids
        if path_id in path_by_id
    ]
    if not scores:
        return float("inf")
    return min(scores)


def _ewma(previous: float, current: float, alpha: float) -> float:
    return previous * (1.0 - alpha) + current * alpha


def _clip01(value: float) -> float:
    return min(1.0, max(0.0, value))

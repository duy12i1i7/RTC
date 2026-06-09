"""Causal Semantic Deadline Scheduler.

This is the first research prototype of the FleetRMW control plane. It models
the scheduling decision that a future RMW or sidecar bridge would apply before
choosing a concrete transport.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, List, Sequence, Tuple

from .model import FlowClass, FlowDecision, FlowObservation, FlowSpec, NetworkLink


_CRITICAL_CLASSES = {
    FlowClass.SAFETY,
    FlowClass.CONTROL,
    FlowClass.COORDINATION,
    FlowClass.STATE,
}


@dataclass(frozen=True)
class SchedulerWeights:
    """Tunable weights for research experiments."""

    causal_gain: float = 3.0
    risk_reduction: float = 2.2
    freshness: float = 2.0
    deadline: float = 2.4
    operator_qoe: float = 1.7
    coordination: float = 1.2
    reliability_penalty: float = 0.8
    bandwidth_cost: float = 1.1
    redundancy_penalty: float = 1.5
    stale_penalty: float = 6.0


class CausalSemanticDeadlineScheduler:
    """Schedule fleet communication by task value rather than topic name.

    The algorithm has three parts:

    1. reject stale samples whose lifespan has already expired;
    2. reserve a configurable budget for safety/control/state traffic;
    3. rank remaining flows by causal semantic utility per network byte.
    """

    def __init__(
        self,
        weights: SchedulerWeights | None = None,
        critical_budget_fraction: float = 0.55,
        qoe_budget_fraction: float = 0.12,
        degradation_floor: float = 0.18,
    ) -> None:
        if not 0.0 <= critical_budget_fraction <= 1.0:
            raise ValueError("critical_budget_fraction must be in [0, 1]")
        if not 0.0 <= qoe_budget_fraction <= 1.0:
            raise ValueError("qoe_budget_fraction must be in [0, 1]")
        if not 0.0 < degradation_floor <= 1.0:
            raise ValueError("degradation_floor must be in (0, 1]")
        self.weights = weights or SchedulerWeights()
        self.critical_budget_fraction = critical_budget_fraction
        self.qoe_budget_fraction = qoe_budget_fraction
        self.degradation_floor = degradation_floor

    def schedule(
        self,
        candidates: Iterable[Tuple[FlowSpec, FlowObservation]],
        link: NetworkLink,
    ) -> List[FlowDecision]:
        """Return one decision for every candidate flow."""

        link.validates()
        scored: list[tuple[float, float, FlowSpec, FlowObservation]] = []
        decisions: list[FlowDecision] = []

        for spec, obs in candidates:
            spec.validates()
            if obs.age_ms > spec.qos.lifespan_ms:
                decisions.append(
                    FlowDecision(
                        flow_id=spec.flow_id,
                        action="drop",
                        priority=-self.weights.stale_penalty,
                        allocated_bytes=0,
                        reason="stale beyond lifespan",
                    )
                )
                continue
            priority = self._priority(spec, obs, link)
            bytes_needed = self._effective_size(spec, obs)
            density = priority / max(1.0, bytes_needed)
            scored.append((priority, density, spec, obs))

        critical, opportunistic = self._partition(scored)
        remaining = link.capacity_bytes_per_tick
        critical_budget = int(link.capacity_bytes_per_tick * self.critical_budget_fraction)

        selected_critical, remaining_critical_budget = self._admit_by_priority(
            critical,
            capacity=min(critical_budget, remaining),
            allow_degradation=True,
            class_name="critical reservation",
        )
        decisions.extend(selected_critical)
        remaining -= sum(decision.allocated_bytes for decision in selected_critical)

        leftover_reserved = max(0, remaining_critical_budget)
        shared_budget = remaining + leftover_reserved

        focused_qoe = [
            entry
            for entry in opportunistic
            if entry[2].flow_class is FlowClass.HUMAN_QOE
            and entry[3].task.operator_attention > 0
        ]
        qoe_budget = min(
            shared_budget,
            int(link.capacity_bytes_per_tick * self.qoe_budget_fraction),
        )
        selected_qoe, remaining_qoe_budget = self._admit_by_density(
            focused_qoe,
            capacity=qoe_budget,
        )
        decisions.extend(selected_qoe)
        shared_budget -= qoe_budget - remaining_qoe_budget
        selected_qoe_ids = {decision.flow_id for decision in selected_qoe}

        remaining_opportunistic = [
            entry for entry in opportunistic if entry[2].flow_id not in selected_qoe_ids
        ]
        selected_rest, _ = self._admit_by_density(
            remaining_opportunistic + self._rejected_critical_as_opportunistic(
                critical,
                selected_critical,
            ),
            capacity=shared_budget,
        )
        decisions.extend(selected_rest)

        decided_ids = {decision.flow_id for decision in decisions}
        for _, _, spec, _ in scored:
            if spec.flow_id not in decided_ids:
                decisions.append(
                    FlowDecision(
                        flow_id=spec.flow_id,
                        action="defer",
                        priority=self._class_floor(spec.flow_class),
                        allocated_bytes=0,
                        reason="insufficient capacity",
                    )
                )

        return sorted(decisions, key=lambda item: item.flow_id)

    def _partition(
        self,
        scored: Sequence[tuple[float, float, FlowSpec, FlowObservation]],
    ) -> tuple[
        list[tuple[float, float, FlowSpec, FlowObservation]],
        list[tuple[float, float, FlowSpec, FlowObservation]],
    ]:
        critical = []
        opportunistic = []
        for entry in scored:
            _, _, spec, _ = entry
            if spec.flow_class in _CRITICAL_CLASSES:
                critical.append(entry)
            else:
                opportunistic.append(entry)
        return critical, opportunistic

    def _admit_by_priority(
        self,
        scored: Sequence[tuple[float, float, FlowSpec, FlowObservation]],
        capacity: int,
        allow_degradation: bool,
        class_name: str,
    ) -> tuple[list[FlowDecision], int]:
        decisions: list[FlowDecision] = []
        remaining = capacity
        for priority, _, spec, obs in sorted(scored, key=lambda item: item[0], reverse=True):
            bytes_needed = self._effective_size(spec, obs)
            if bytes_needed <= remaining:
                decisions.append(
                    FlowDecision(
                        flow_id=spec.flow_id,
                        action="send",
                        priority=priority,
                        allocated_bytes=bytes_needed,
                        reason=class_name,
                    )
                )
                remaining -= bytes_needed
                continue
            if allow_degradation and self._degradable(spec):
                degraded_bytes = self._degraded_size(bytes_needed)
                if degraded_bytes <= remaining:
                    decisions.append(
                        FlowDecision(
                            flow_id=spec.flow_id,
                            action="send_degraded",
                            priority=priority,
                            allocated_bytes=degraded_bytes,
                            reason=f"{class_name}: degraded",
                            degraded=True,
                        )
                    )
                    remaining -= degraded_bytes
        return decisions, remaining

    def _admit_by_density(
        self,
        scored: Sequence[tuple[float, float, FlowSpec, FlowObservation]],
        capacity: int,
    ) -> tuple[list[FlowDecision], int]:
        decisions: list[FlowDecision] = []
        remaining = capacity
        for priority, density, spec, obs in sorted(
            scored,
            key=lambda item: (item[1], item[0]),
            reverse=True,
        ):
            bytes_needed = self._effective_size(spec, obs)
            if bytes_needed <= remaining:
                decisions.append(
                    FlowDecision(
                        flow_id=spec.flow_id,
                        action="send",
                        priority=priority,
                        allocated_bytes=bytes_needed,
                        reason="semantic utility per byte",
                    )
                )
                remaining -= bytes_needed
                continue
            if self._degradable(spec):
                degraded_bytes = self._degraded_size(bytes_needed)
                if degraded_bytes <= remaining:
                    decisions.append(
                        FlowDecision(
                            flow_id=spec.flow_id,
                            action="send_degraded",
                            priority=priority,
                            allocated_bytes=degraded_bytes,
                            reason="semantic utility per byte: degraded",
                            degraded=True,
                        )
                    )
                    remaining -= degraded_bytes
        return decisions, remaining

    def _rejected_critical_as_opportunistic(
        self,
        critical: Sequence[tuple[float, float, FlowSpec, FlowObservation]],
        selected: Sequence[FlowDecision],
    ) -> list[tuple[float, float, FlowSpec, FlowObservation]]:
        selected_ids = {decision.flow_id for decision in selected}
        return [entry for entry in critical if entry[2].flow_id not in selected_ids]

    def _priority(self, spec: FlowSpec, obs: FlowObservation, link: NetworkLink) -> float:
        task = obs.task.clipped()
        age_ratio = min(2.0, obs.age_ms / spec.qos.lifespan_ms)
        deadline_ratio = min(2.0, obs.age_ms / spec.qos.deadline_ms)
        qoe = (
            spec.qoe.smoothness_weight
            + spec.qoe.freeze_penalty
            + spec.qoe.visual_confidence_weight
        ) * task.operator_attention
        reliability_pressure = (
            link.loss
            + obs.measured_loss
            + max(0.0, obs.measured_rtt_ms - spec.qos.deadline_ms)
            / spec.qos.deadline_ms
        )
        class_floor = self._class_floor(spec.flow_class)
        score = (
            class_floor
            + self.weights.causal_gain * spec.causal_task_gain
            + self.weights.risk_reduction * task.collision_risk * task.task_criticality
            + self.weights.freshness * age_ratio
            + self.weights.deadline * deadline_ratio
            + self.weights.operator_qoe * qoe
            + self.weights.coordination * task.coordination_pressure
            - self.weights.reliability_penalty * reliability_pressure
            - self.weights.bandwidth_cost * self._bandwidth_cost(spec)
            - self.weights.redundancy_penalty * spec.redundancy
        )
        return score

    def _class_floor(self, flow_class: FlowClass) -> float:
        return {
            FlowClass.SAFETY: 12.0,
            FlowClass.CONTROL: 10.0,
            FlowClass.COORDINATION: 8.0,
            FlowClass.STATE: 6.0,
            FlowClass.PERCEPTION: 3.0,
            FlowClass.HUMAN_QOE: 4.0,
            FlowClass.DEBUG: 0.5,
            FlowClass.BULK: 0.1,
        }[flow_class]

    def _bandwidth_cost(self, spec: FlowSpec) -> float:
        return (spec.nominal_size_bytes * spec.nominal_rate_hz) / 1_000_000.0

    def _effective_size(self, spec: FlowSpec, obs: FlowObservation) -> int:
        queued_factor = min(3, max(1, obs.queue_depth))
        return max(1, int(spec.nominal_size_bytes * spec.semantic_delta_ratio * queued_factor))

    def _degradable(self, spec: FlowSpec) -> bool:
        return spec.flow_class in {
            FlowClass.PERCEPTION,
            FlowClass.HUMAN_QOE,
            FlowClass.DEBUG,
            FlowClass.BULK,
        }

    def _degraded_size(self, bytes_needed: int) -> int:
        return max(1, int(bytes_needed * self.degradation_floor))

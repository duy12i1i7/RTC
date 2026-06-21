"""Fleet-wide source-sequence repair admission and path scheduling."""

from __future__ import annotations

from dataclasses import dataclass
import math
from typing import Iterable, Sequence


REPAIR_SCHEDULE_SCHEMA_VERSION = "fleetrmw.fleet_repair_schedule.v1"


@dataclass(frozen=True)
class RepairPath:
    path_id: str
    latency_ms: float
    loss: float
    failure_domain: str = ""
    bandwidth_utilization: float = 0.0


@dataclass(frozen=True)
class RepairDemand:
    topic: str
    robot_id: str
    publisher_id: str
    source_sequence_number: int
    payload_bytes: int
    remaining_deadline_ms: float
    qoe_debt: float
    criticality: float
    age_ms: float = 0.0
    prior_attempts: int = 0

    @property
    def demand_id(self) -> str:
        return (
            f"{self.publisher_id}:{self.source_sequence_number}:"
            f"{self.robot_id}:{self.topic}"
        )


@dataclass(frozen=True)
class FleetRepairSchedulerConfig:
    capacity_bytes: int
    max_admitted_repairs: int | None = None
    max_paths_per_repair: int = 2
    require_failure_domain_diversity: bool = True
    min_expected_success: float = 0.25
    criticality_weight: float = 4.0
    qoe_debt_weight: float = 3.0
    urgency_weight: float = 3.5
    success_weight: float = 4.0
    latency_penalty: float = 0.75
    lateness_penalty: float = 6.0
    prior_attempt_penalty: float = 0.75
    byte_cost_weight: float = 0.05


@dataclass(frozen=True)
class RepairDecision:
    demand_id: str
    topic: str
    robot_id: str
    publisher_id: str
    source_sequence_number: int
    action: str
    selected_paths: tuple[str, ...]
    allocated_bytes: int
    expected_success: float
    expected_latency_ms: float
    remaining_deadline_ms: float
    utility: float
    reason: str

    def as_dict(self) -> dict[str, object]:
        return {
            "demand_id": self.demand_id,
            "topic": self.topic,
            "robot_id": self.robot_id,
            "publisher_id": self.publisher_id,
            "source_sequence_number": self.source_sequence_number,
            "action": self.action,
            "selected_paths": list(self.selected_paths),
            "allocated_bytes": self.allocated_bytes,
            "expected_success": self.expected_success,
            "expected_latency_ms": self.expected_latency_ms,
            "remaining_deadline_ms": self.remaining_deadline_ms,
            "utility": self.utility,
            "reason": self.reason,
        }


@dataclass(frozen=True)
class FleetRepairSchedule:
    decisions: tuple[RepairDecision, ...]
    capacity_bytes: int

    @property
    def admitted(self) -> tuple[RepairDecision, ...]:
        return tuple(decision for decision in self.decisions if decision.action == "repair")

    @property
    def allocated_bytes(self) -> int:
        return sum(decision.allocated_bytes for decision in self.admitted)

    @property
    def policy_text(self) -> str:
        rules = []
        for decision in sorted(
            self.admitted,
            key=lambda item: (item.topic, item.source_sequence_number, item.publisher_id),
        ):
            rules.append(
                f"{decision.topic}={'+'.join(decision.selected_paths)}"
                f"|sequences={decision.source_sequence_number}|attempts=1"
            )
        return ";".join(rules)

    def as_dict(self) -> dict[str, object]:
        return {
            "schema_version": REPAIR_SCHEDULE_SCHEMA_VERSION,
            "capacity_bytes": self.capacity_bytes,
            "allocated_bytes": self.allocated_bytes,
            "admitted_count": len(self.admitted),
            "deferred_count": len(self.decisions) - len(self.admitted),
            "policy_text": self.policy_text,
            "decisions": [decision.as_dict() for decision in self.decisions],
        }


@dataclass(frozen=True)
class _RepairOption:
    paths: tuple[RepairPath, ...]
    cost: int
    success: float
    latency_ms: float
    utility: float


class FleetRepairScheduler:
    """Solve deadline/QoE-aware repair admission under one fleet capacity."""

    def __init__(self, config: FleetRepairSchedulerConfig) -> None:
        if config.capacity_bytes < 0:
            raise ValueError("capacity_bytes must be non-negative")
        if config.max_paths_per_repair <= 0:
            raise ValueError("max_paths_per_repair must be positive")
        self.config = config

    def schedule(
        self,
        demands: Iterable[RepairDemand],
        paths: Iterable[RepairPath],
    ) -> FleetRepairSchedule:
        demand_list = sorted(demands, key=lambda demand: demand.demand_id)
        path_list = tuple(paths)
        if demand_list and not path_list:
            raise ValueError("at least one repair path is required")
        options = [self._options(demand, path_list) for demand in demand_list]

        # State: (used bytes, admitted count) -> (utility, selected option indexes).
        states: dict[tuple[int, int], tuple[float, tuple[int, ...]]] = {
            (0, 0): (0.0, ())
        }
        for demand_options in options:
            next_states: dict[tuple[int, int], tuple[float, tuple[int, ...]]] = {}
            for (used, admitted), (utility, selected) in states.items():
                self._keep_state(next_states, (used, admitted), utility, selected + (-1,))
                for option_index, option in enumerate(demand_options):
                    next_used = used + option.cost
                    next_admitted = admitted + 1
                    if next_used > self.config.capacity_bytes:
                        continue
                    if (
                        self.config.max_admitted_repairs is not None
                        and next_admitted > self.config.max_admitted_repairs
                    ):
                        continue
                    self._keep_state(
                        next_states,
                        (next_used, next_admitted),
                        utility + option.utility,
                        selected + (option_index,),
                    )
            states = self._pareto_prune(next_states)

        _, (_, selected_options) = max(
            states.items(),
            key=lambda item: (
                item[1][0],
                item[0][1],
                -item[0][0],
                tuple(-index for index in item[1][1]),
            ),
        )
        decisions = []
        for demand, demand_options, selected_index in zip(
            demand_list,
            options,
            selected_options,
        ):
            if selected_index < 0:
                decisions.append(self._deferred_decision(demand))
                continue
            option = demand_options[selected_index]
            decisions.append(self._repair_decision(demand, option))
        return FleetRepairSchedule(tuple(decisions), self.config.capacity_bytes)

    def _options(
        self,
        demand: RepairDemand,
        paths: Sequence[RepairPath],
    ) -> tuple[_RepairOption, ...]:
        if demand.payload_bytes <= 0:
            raise ValueError("repair payload_bytes must be positive")
        ranked = sorted(paths, key=lambda path: self._path_risk(path, demand))
        candidates: list[tuple[RepairPath, ...]] = [(ranked[0],)]
        if self.config.max_paths_per_repair > 1:
            for second in ranked[1:]:
                if (
                    self.config.require_failure_domain_diversity
                    and ranked[0].failure_domain
                    and second.failure_domain == ranked[0].failure_domain
                ):
                    continue
                candidates.append((ranked[0], second))
                break
        result = []
        for selected in candidates:
            success = 1.0
            for path in selected:
                success *= _clip01(path.loss)
            success = 1.0 - success
            if success < self.config.min_expected_success:
                continue
            latency_ms = min(max(0.0, path.latency_ms) for path in selected)
            result.append(
                _RepairOption(
                    paths=selected,
                    cost=demand.payload_bytes * len(selected),
                    success=success,
                    latency_ms=latency_ms,
                    utility=self._utility(demand, success, latency_ms, len(selected)),
                )
            )
        return tuple(result)

    def _utility(
        self,
        demand: RepairDemand,
        success: float,
        latency_ms: float,
        path_count: int,
    ) -> float:
        deadline = max(1.0, demand.remaining_deadline_ms)
        slack_ratio = (demand.remaining_deadline_ms - latency_ms) / deadline
        deadline_pressure = 100.0 / deadline
        latency_ratio = max(0.0, latency_ms / deadline)
        lateness = max(0.0, -slack_ratio)
        normalized_cost = demand.payload_bytes * path_count / max(
            1,
            self.config.capacity_bytes,
        )
        return (
            self.config.criticality_weight * _clip01(demand.criticality)
            + self.config.qoe_debt_weight * _clip01(demand.qoe_debt)
            + self.config.urgency_weight * math.log1p(deadline_pressure)
            + self.config.success_weight * success
            - self.config.latency_penalty * latency_ratio
            - self.config.lateness_penalty * lateness
            - self.config.prior_attempt_penalty * max(0, demand.prior_attempts)
            - self.config.byte_cost_weight * normalized_cost
        )

    @staticmethod
    def _path_risk(path: RepairPath, demand: RepairDemand) -> float:
        deadline = max(1.0, demand.remaining_deadline_ms)
        return (
            4.0 * _clip01(path.loss)
            + 2.0 * max(0.0, path.latency_ms / deadline)
            + _clip01(path.bandwidth_utilization)
        )

    @staticmethod
    def _keep_state(
        states: dict[tuple[int, int], tuple[float, tuple[int, ...]]],
        key: tuple[int, int],
        utility: float,
        selected: tuple[int, ...],
    ) -> None:
        current = states.get(key)
        if current is None or (utility, selected) > current:
            states[key] = (utility, selected)

    @staticmethod
    def _pareto_prune(
        states: dict[tuple[int, int], tuple[float, tuple[int, ...]]],
    ) -> dict[tuple[int, int], tuple[float, tuple[int, ...]]]:
        result = {}
        best_by_admitted: dict[int, float] = {}
        for key, value in sorted(states.items(), key=lambda item: (item[0][1], item[0][0])):
            used, admitted = key
            utility = value[0]
            best = best_by_admitted.get(admitted, -math.inf)
            if utility + 1e-12 < best:
                continue
            best_by_admitted[admitted] = max(best, utility)
            result[(used, admitted)] = value
        return result

    @staticmethod
    def _repair_decision(
        demand: RepairDemand,
        option: _RepairOption,
    ) -> RepairDecision:
        return RepairDecision(
            demand_id=demand.demand_id,
            topic=demand.topic,
            robot_id=demand.robot_id,
            publisher_id=demand.publisher_id,
            source_sequence_number=demand.source_sequence_number,
            action="repair",
            selected_paths=tuple(path.path_id for path in option.paths),
            allocated_bytes=option.cost,
            expected_success=option.success,
            expected_latency_ms=option.latency_ms,
            remaining_deadline_ms=demand.remaining_deadline_ms,
            utility=option.utility,
            reason="fleet-wide deadline/QoE repair admission",
        )

    @staticmethod
    def _deferred_decision(demand: RepairDemand) -> RepairDecision:
        return RepairDecision(
            demand_id=demand.demand_id,
            topic=demand.topic,
            robot_id=demand.robot_id,
            publisher_id=demand.publisher_id,
            source_sequence_number=demand.source_sequence_number,
            action="defer",
            selected_paths=(),
            allocated_bytes=0,
            expected_success=0.0,
            expected_latency_ms=math.inf,
            remaining_deadline_ms=demand.remaining_deadline_ms,
            utility=0.0,
            reason="not admitted by shared fleet repair capacity",
        )


def _clip01(value: float) -> float:
    return min(1.0, max(0.0, float(value)))

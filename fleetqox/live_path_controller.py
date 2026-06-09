"""Live telemetry-to-path-plan controller for FleetRMW.

This module consumes router/subscriber telemetry records, aggregates them into
per-path observations, and updates the file-backed `fleet_plan` consumed by the
C++ RMW transport.
"""

from __future__ import annotations

from dataclasses import dataclass, field
import json
import os
from pathlib import Path
import tempfile
from typing import Iterable, Mapping, Sequence

from .fleet_optimizer import FleetFlowDemand, FleetOptimizerConfig, RobotQoEState
from .online_fleet_planner import (
    FleetTopicDemand,
    OnlineFleetPathPlan,
    OnlineFleetPathPlanner,
    OnlineFleetPlannerConfig,
    PathObservation,
)


ROUTER_TELEMETRY_SCHEMA_VERSION = "fleetrmw.router_path_telemetry.v1"
SUBSCRIBER_TELEMETRY_SCHEMA_VERSION = "fleetrmw.subscriber_delivery_telemetry.v1"
CONTROLLER_SCHEMA_VERSION = "fleetrmw.live_path_plan_controller.v1"


@dataclass(frozen=True)
class RouterTelemetryRecord:
    path_id: str
    topic: str
    sequence_number: int
    event: str = "data_frame"
    latency_ms: float = 0.0
    jitter_ms: float = 0.0
    sent_frames: int = 1
    delivered_frames: int = 1
    nack_frames: int = 0
    bytes_sent: int = 0
    capacity_bytes: int = 0
    loss: float | None = None
    nack_rate: float | None = None
    deadline_miss_ratio: float | None = None
    bandwidth_utilization: float | None = None

    @classmethod
    def from_mapping(cls, data: Mapping[str, object]) -> "RouterTelemetryRecord":
        return cls(
            path_id=str(data.get("path_id", data.get("path", ""))),
            topic=str(data.get("topic", "")),
            sequence_number=_int_value(
                data.get("source_sequence_number", data.get("sequence_number", 0))
            ),
            event=str(data.get("event", "data_frame")),
            latency_ms=_float_value(data.get("latency_ms", 0.0)),
            jitter_ms=_float_value(data.get("jitter_ms", 0.0)),
            sent_frames=max(0, _int_value(data.get("sent_frames", 1))),
            delivered_frames=max(0, _int_value(data.get("delivered_frames", 1))),
            nack_frames=max(0, _int_value(data.get("nack_frames", 0))),
            bytes_sent=max(0, _int_value(data.get("bytes_sent", data.get("payload_bytes", 0)))),
            capacity_bytes=max(0, _int_value(data.get("capacity_bytes", 0))),
            loss=_optional_fraction(data.get("loss")),
            nack_rate=_optional_fraction(data.get("nack_rate")),
            deadline_miss_ratio=_optional_fraction(data.get("deadline_miss_ratio")),
            bandwidth_utilization=_optional_fraction(data.get("bandwidth_utilization")),
        )

    def as_path_observation(self) -> PathObservation:
        return PathObservation(
            path_id=self.path_id,
            latency_ms=self.latency_ms,
            jitter_ms=self.jitter_ms,
            sent_frames=self.sent_frames,
            delivered_frames=self.delivered_frames,
            nack_frames=self.nack_frames,
            bytes_sent=self.bytes_sent,
            capacity_bytes=self.capacity_bytes,
            loss=self.loss,
            nack_rate=self.nack_rate,
            deadline_miss_ratio=self.deadline_miss_ratio,
            bandwidth_utilization=self.bandwidth_utilization,
        )


@dataclass(frozen=True)
class SubscriberDeliveryTelemetryRecord:
    robot_id: str
    topic: str
    sequence_number: int
    event: str = "take"
    latency_ms: float = 0.0
    deadline_ms: float = 0.0
    deadline_missed: bool = False
    delivered: bool = True
    duplicate: bool = False

    @classmethod
    def from_mapping(cls, data: Mapping[str, object]) -> "SubscriberDeliveryTelemetryRecord":
        return cls(
            robot_id=str(data.get("robot_id", "")),
            topic=str(data.get("topic", "")),
            sequence_number=_int_value(
                data.get("source_sequence_number", data.get("sequence_number", 0))
            ),
            event=str(data.get("event", "take")),
            latency_ms=max(0.0, _float_value(data.get("latency_ms", 0.0))),
            deadline_ms=max(0.0, _float_value(data.get("deadline_ms", 0.0))),
            deadline_missed=_bool_value(data.get("deadline_missed", False)),
            delivered=_bool_value(data.get("delivered", True)),
            duplicate=_bool_value(data.get("duplicate", False)),
        )


@dataclass
class PathObservationAccumulator:
    path_id: str
    latency_values: list[float] = field(default_factory=list)
    jitter_values: list[float] = field(default_factory=list)
    sent_frames: int = 0
    delivered_frames: int = 0
    nack_frames: int = 0
    bytes_sent: int = 0
    capacity_bytes: int = 0
    loss_values: list[float] = field(default_factory=list)
    nack_rate_values: list[float] = field(default_factory=list)
    deadline_miss_values: list[float] = field(default_factory=list)
    utilization_values: list[float] = field(default_factory=list)

    def add(self, record: RouterTelemetryRecord) -> None:
        self.latency_values.append(record.latency_ms)
        self.jitter_values.append(record.jitter_ms)
        self.sent_frames += record.sent_frames
        self.delivered_frames += record.delivered_frames
        self.nack_frames += record.nack_frames
        self.bytes_sent += record.bytes_sent
        self.capacity_bytes = max(self.capacity_bytes, record.capacity_bytes)
        if record.loss is not None:
            self.loss_values.append(record.loss)
        if record.nack_rate is not None:
            self.nack_rate_values.append(record.nack_rate)
        if record.deadline_miss_ratio is not None:
            self.deadline_miss_values.append(record.deadline_miss_ratio)
        if record.bandwidth_utilization is not None:
            self.utilization_values.append(record.bandwidth_utilization)

    def observation(self) -> PathObservation:
        return PathObservation(
            path_id=self.path_id,
            latency_ms=_mean(self.latency_values),
            jitter_ms=_mean(self.jitter_values),
            sent_frames=self.sent_frames,
            delivered_frames=self.delivered_frames,
            nack_frames=self.nack_frames,
            bytes_sent=self.bytes_sent,
            capacity_bytes=self.capacity_bytes,
            loss=_mean(self.loss_values) if self.loss_values else None,
            nack_rate=_mean(self.nack_rate_values) if self.nack_rate_values else None,
            deadline_miss_ratio=_mean(self.deadline_miss_values)
            if self.deadline_miss_values
            else None,
            bandwidth_utilization=_mean(self.utilization_values)
            if self.utilization_values
            else None,
        )


class RouterTelemetryAggregator:
    """Accumulate router telemetry records into current path observations."""

    def __init__(self, seed_observations: Iterable[PathObservation] = ()) -> None:
        self._seed_observations = {item.path_id: item for item in seed_observations}
        self._accumulators: dict[str, PathObservationAccumulator] = {}
        self._record_count = 0

    @property
    def record_count(self) -> int:
        return self._record_count

    def ingest(self, record: RouterTelemetryRecord) -> None:
        if not record.path_id:
            return
        accumulator = self._accumulators.setdefault(
            record.path_id,
            PathObservationAccumulator(record.path_id),
        )
        accumulator.add(record)
        self._record_count += 1

    def observations(self) -> list[PathObservation]:
        observations = dict(self._seed_observations)
        for path_id, accumulator in self._accumulators.items():
            observations[path_id] = accumulator.observation()
        return sorted(observations.values(), key=lambda item: item.path_id)


@dataclass
class SubscriberRobotAccumulator:
    robot_id: str
    delivered: int = 0
    total: int = 0
    deadline_misses: int = 0
    latency_values: list[float] = field(default_factory=list)
    deadline_values: list[float] = field(default_factory=list)

    def add(self, record: SubscriberDeliveryTelemetryRecord) -> None:
        if record.duplicate:
            return
        self.total += 1
        if record.delivered:
            self.delivered += 1
        if record.deadline_missed:
            self.deadline_misses += 1
        self.latency_values.append(record.latency_ms)
        if record.deadline_ms > 0:
            self.deadline_values.append(record.deadline_ms)

    def state(self) -> RobotQoEState:
        total = max(1, self.total)
        deadline = _mean(self.deadline_values)
        latency = _mean(self.latency_values)
        latency_ratio = latency / max(1.0, deadline) if deadline > 0 else 0.0
        return RobotQoEState(
            robot_id=self.robot_id,
            control_delivery_ratio=min(1.0, max(0.0, self.delivered / total)),
            deadline_miss_ratio=min(1.0, max(0.0, self.deadline_misses / total)),
            qoe_score=min(1.0, max(0.0, 1.0 - 0.5 * latency_ratio)),
        )


class SubscriberDeliveryAggregator:
    """Aggregate subscriber-visible delivery telemetry into robot QoE states."""

    def __init__(self, seed_states: Iterable[RobotQoEState] = ()) -> None:
        self._seed_states = {state.robot_id: state for state in seed_states}
        self._accumulators: dict[str, SubscriberRobotAccumulator] = {}
        self._record_count = 0

    @property
    def record_count(self) -> int:
        return self._record_count

    def ingest(self, record: SubscriberDeliveryTelemetryRecord) -> None:
        if not record.robot_id:
            return
        accumulator = self._accumulators.setdefault(
            record.robot_id,
            SubscriberRobotAccumulator(record.robot_id),
        )
        accumulator.add(record)
        self._record_count += 1

    def robot_states(self) -> list[RobotQoEState]:
        states = dict(self._seed_states)
        for robot_id, accumulator in self._accumulators.items():
            states[robot_id] = accumulator.state()
        return sorted(states.values(), key=lambda item: item.robot_id)


class JsonlTelemetryTailer:
    """Read newly appended JSONL records from one or more telemetry files."""

    def __init__(self, paths: Sequence[Path | str], *, kind: str = "router") -> None:
        self.paths = [Path(path) for path in paths]
        self.kind = kind
        self._offsets = {path: 0 for path in self.paths}

    def poll(self) -> list[RouterTelemetryRecord | SubscriberDeliveryTelemetryRecord]:
        records: list[RouterTelemetryRecord | SubscriberDeliveryTelemetryRecord] = []
        for path in self.paths:
            if not path.exists():
                continue
            with path.open("r", encoding="utf-8") as handle:
                handle.seek(self._offsets.get(path, 0))
                for line in handle:
                    record = (
                        parse_subscriber_telemetry_line(line)
                        if self.kind == "subscriber"
                        else parse_router_telemetry_line(line)
                    )
                    if record is not None:
                        records.append(record)
                self._offsets[path] = handle.tell()
        return records


@dataclass(frozen=True)
class LivePathPlanControllerConfig:
    plan_file: Path
    telemetry_files: tuple[Path, ...]
    demands: tuple[FleetTopicDemand, ...]
    subscriber_telemetry_files: tuple[Path, ...] = ()
    seed_observations: tuple[PathObservation, ...] = ()
    robot_states: tuple[RobotQoEState, ...] = ()
    optimizer: FleetOptimizerConfig = field(default_factory=FleetOptimizerConfig)
    telemetry_alpha: float = 0.65
    min_dwell_ticks: int = 0
    switch_score_margin: float = 0.20


class LivePathPlanController:
    """Tail router telemetry and refresh an RMW fleet-plan file."""

    def __init__(self, config: LivePathPlanControllerConfig) -> None:
        self.config = config
        self._tailer = JsonlTelemetryTailer(config.telemetry_files)
        self._subscriber_tailer = JsonlTelemetryTailer(
            config.subscriber_telemetry_files,
            kind="subscriber",
        )
        self._aggregator = RouterTelemetryAggregator(config.seed_observations)
        self._subscriber_aggregator = SubscriberDeliveryAggregator(config.robot_states)
        self._planner = OnlineFleetPathPlanner(
            OnlineFleetPlannerConfig(
                optimizer=config.optimizer,
                telemetry_alpha=config.telemetry_alpha,
                min_dwell_ticks=config.min_dwell_ticks,
                switch_score_margin=config.switch_score_margin,
            )
        )
        self._tick = 0
        self._last_plan: OnlineFleetPathPlan | None = None

    @property
    def last_plan(self) -> OnlineFleetPathPlan | None:
        return self._last_plan

    @property
    def record_count(self) -> int:
        return self._aggregator.record_count

    @property
    def subscriber_record_count(self) -> int:
        return self._subscriber_aggregator.record_count

    def poll_once(self) -> OnlineFleetPathPlan:
        for record in self._tailer.poll():
            if isinstance(record, RouterTelemetryRecord):
                self._aggregator.ingest(record)
        for record in self._subscriber_tailer.poll():
            if isinstance(record, SubscriberDeliveryTelemetryRecord):
                self._subscriber_aggregator.ingest(record)
        observations = self._aggregator.observations()
        robot_states = self._subscriber_aggregator.robot_states()
        plan = self._planner.update(
            tick=self._tick,
            observations=observations,
            demands=self.config.demands,
            robot_states=robot_states,
        )
        self._tick += 1
        atomic_write_text(self.config.plan_file, plan.path_plan_env + "\n")
        self._last_plan = plan
        return plan

    def summary(self) -> dict[str, object]:
        return {
            "schema_version": CONTROLLER_SCHEMA_VERSION,
            "record_count": self.record_count,
            "subscriber_record_count": self.subscriber_record_count,
            "last_plan": None if self._last_plan is None else self._last_plan.as_dict(),
            "plan_file": str(self.config.plan_file),
            "telemetry_files": [str(path) for path in self.config.telemetry_files],
            "subscriber_telemetry_files": [
                str(path) for path in self.config.subscriber_telemetry_files
            ],
            "robot_states": [
                {
                    "robot_id": state.robot_id,
                    "control_delivery_ratio": state.control_delivery_ratio,
                    "deadline_miss_ratio": state.deadline_miss_ratio,
                    "qoe_score": state.qoe_score,
                }
                for state in self._subscriber_aggregator.robot_states()
            ],
        }


def parse_router_telemetry_line(line: str) -> RouterTelemetryRecord | None:
    stripped = line.strip()
    if not stripped:
        return None
    try:
        data = json.loads(stripped)
    except json.JSONDecodeError:
        return None
    if not isinstance(data, Mapping):
        return None
    schema = str(data.get("schema_version", ""))
    if schema and schema != ROUTER_TELEMETRY_SCHEMA_VERSION:
        return None
    return RouterTelemetryRecord.from_mapping(data)


def parse_subscriber_telemetry_line(line: str) -> SubscriberDeliveryTelemetryRecord | None:
    stripped = line.strip()
    if not stripped:
        return None
    try:
        data = json.loads(stripped)
    except json.JSONDecodeError:
        return None
    if not isinstance(data, Mapping):
        return None
    schema = str(data.get("schema_version", ""))
    if schema and schema != SUBSCRIBER_TELEMETRY_SCHEMA_VERSION:
        return None
    return SubscriberDeliveryTelemetryRecord.from_mapping(data)


def atomic_write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        "w",
        encoding="utf-8",
        dir=path.parent,
        prefix=f"{path.name}.tmp-{os.getpid()}-",
        delete=False,
    ) as handle:
        handle.write(text)
        tmp = Path(handle.name)
    os.replace(tmp, path)


def _mean(values: Sequence[float]) -> float:
    return sum(values) / len(values) if values else 0.0


def _int_value(value: object) -> int:
    try:
        return int(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return 0


def _float_value(value: object) -> float:
    try:
        return float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return 0.0


def _optional_fraction(value: object) -> float | None:
    if value is None:
        return None
    parsed = _float_value(value)
    if parsed > 1.0:
        parsed /= 100.0
    return min(1.0, max(0.0, parsed))


def _bool_value(value: object) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.lower() in {"1", "true", "yes", "y", "on"}
    return bool(value)

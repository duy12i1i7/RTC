"""Live ROS 2 bridge helpers for feeding FleetRMW sidecar batches.

The module is dependency-free at import time.  The executable bridge imports
``rclpy`` lazily, while the config, buffering, and TCP handoff logic remain
unit-testable on machines without ROS 2 installed.
"""

from __future__ import annotations

from dataclasses import dataclass, field
import json
import socket
import time
from pathlib import Path
from typing import Callable, Mapping

from .model import NetworkLink
from .ros2_shim import Ros2QoS, Ros2Sample, Ros2SidecarAdapter
from .transport_selector import (
    AdaptiveBindingDecision,
    TransportBinding,
    TransportBindingManager,
    transport_binding_payload,
)


ClockMs = Callable[[], float]
LiveLinkProvider = Callable[[int, float, NetworkLink], NetworkLink]
TransportBindingProviderResult = (
    AdaptiveBindingDecision | TransportBinding | Mapping[str, object] | None
)
TransportBindingProvider = Callable[..., TransportBindingProviderResult]


@dataclass(frozen=True)
class LiveBindingContext:
    """Runtime context for transport binding selection in a live bridge tick."""

    tick: int
    timestamp_ms: float
    elapsed_s: float


@dataclass(frozen=True)
class BridgeTopicConfig:
    """A live ROS 2 subscription that should be observed by FleetRMW."""

    topic: str
    msg_type: str
    qos: Ros2QoS = field(default_factory=Ros2QoS)
    robot_id: str | None = None
    node_name: str = ""
    flow_id: str | None = None
    nominal_rate_hz: float | None = None
    task_id: str = "ros2_live"
    task_criticality: float | None = None
    collision_risk: float | None = None
    operator_attention: float | None = None
    coordination_pressure: float | None = None
    operator_visible: bool | None = None
    tags: Mapping[str, str] = field(default_factory=dict)

    @classmethod
    def from_payload(cls, payload: Mapping[str, object]) -> "BridgeTopicConfig":
        qos = payload.get("qos", {})
        tags = payload.get("tags", {})
        return cls(
            topic=str(payload["topic"]),
            msg_type=str(payload["msg_type"]),
            qos=Ros2QoS.from_payload(qos),
            robot_id=_optional_str(payload.get("robot_id")),
            node_name=str(payload.get("node_name", "")),
            flow_id=_optional_str(payload.get("flow_id")),
            nominal_rate_hz=_optional_float(payload.get("nominal_rate_hz", payload.get("rate_hz"))),
            task_id=str(payload.get("task_id", "ros2_live")),
            task_criticality=_optional_float(payload.get("task_criticality")),
            collision_risk=_optional_float(payload.get("collision_risk")),
            operator_attention=_optional_float(payload.get("operator_attention")),
            coordination_pressure=_optional_float(payload.get("coordination_pressure")),
            operator_visible=_optional_bool(payload.get("operator_visible")),
            tags=dict(tags) if isinstance(tags, Mapping) else {},
        )

    def to_sample(
        self,
        *,
        payload_size_bytes: int | None,
        age_ms: float,
        queue_depth: int,
        contract_id: str | None = None,
        source_sample_id: str | None = None,
        publisher_gid: str | None = None,
        sequence_number: int | None = None,
        source_timestamp_ns: int | None = None,
        received_timestamp_ns: int | None = None,
        semantic_payload: Mapping[str, object] | None = None,
    ) -> Ros2Sample:
        tags = {"bridge": "rclpy_live", **dict(self.tags)}
        return Ros2Sample(
            topic=self.topic,
            msg_type=self.msg_type,
            qos=self.qos,
            robot_id=self.robot_id,
            node_name=self.node_name,
            flow_id=self.flow_id,
            contract_id=contract_id,
            source_sample_id=source_sample_id,
            publisher_gid=publisher_gid,
            sequence_number=sequence_number,
            source_timestamp_ns=source_timestamp_ns,
            received_timestamp_ns=received_timestamp_ns,
            payload_size_bytes=payload_size_bytes,
            nominal_rate_hz=self.nominal_rate_hz,
            age_ms=age_ms,
            queue_depth=queue_depth,
            task_id=self.task_id,
            task_criticality=self.task_criticality,
            collision_risk=self.collision_risk,
            operator_attention=self.operator_attention,
            coordination_pressure=self.coordination_pressure,
            operator_visible=self.operator_visible,
            tags=tags,
            semantic_payload=semantic_payload,
        )


@dataclass(frozen=True)
class LiveBridgeConfig:
    """Runtime configuration for a live ROS 2 sidecar bridge."""

    topics: tuple[BridgeTopicConfig, ...]
    scenario: str = "ros2_live_bridge"
    sidecar_host: str = "127.0.0.1"
    sidecar_port: int = 8765
    flush_period_ms: float = 20.0
    link: NetworkLink = field(default_factory=lambda: NetworkLink(capacity_bytes_per_tick=588))
    link_schedule: tuple["LiveLinkScheduleEntry", ...] = ()
    include_feedback: bool = False
    transport_binding: "LiveTransportBindingConfig | None" = None

    @classmethod
    def from_payload(cls, payload: Mapping[str, object]) -> "LiveBridgeConfig":
        topics_payload = payload.get("topics", [])
        if not isinstance(topics_payload, list):
            raise ValueError("topics must be a list")
        sidecar_payload = payload.get("sidecar", {})
        sidecar = dict(sidecar_payload) if isinstance(sidecar_payload, Mapping) else {}
        return cls(
            topics=tuple(BridgeTopicConfig.from_payload(item) for item in topics_payload if isinstance(item, Mapping)),
            scenario=str(payload.get("scenario", "ros2_live_bridge")),
            sidecar_host=str(sidecar.get("host", payload.get("sidecar_host", "127.0.0.1"))),
            sidecar_port=int(sidecar.get("port", payload.get("sidecar_port", 8765))),
            flush_period_ms=float(payload.get("flush_period_ms", 20.0)),
            link=link_from_bridge_payload(payload.get("link", {})),
            link_schedule=tuple(
                LiveLinkScheduleEntry.from_payload(item)
                for item in payload.get("link_schedule", [])
                if isinstance(item, Mapping)
            ),
            include_feedback=bool(payload.get("include_feedback", False)),
            transport_binding=LiveTransportBindingConfig.from_payload(
                payload.get("transport_binding")
            ),
        )

    def validates(self) -> None:
        if not self.topics:
            raise ValueError("at least one topic is required")
        if self.flush_period_ms <= 0:
            raise ValueError("flush_period_ms must be positive")
        self.link.validates()
        previous_at_s = -1.0
        for entry in self.link_schedule:
            entry.validates()
            if entry.at_s < previous_at_s:
                raise ValueError("link_schedule entries must be sorted by at_s")
            previous_at_s = entry.at_s
        if self.transport_binding:
            self.transport_binding.validates()


@dataclass(frozen=True)
class LiveLinkScheduleEntry:
    """A scheduled link profile for one continuous live bridge run."""

    at_s: float
    link: NetworkLink
    profile: str | None = None

    @classmethod
    def from_payload(cls, payload: Mapping[str, object]) -> "LiveLinkScheduleEntry":
        return cls(
            at_s=float(payload.get("at_s", payload.get("offset_s", 0.0))),
            link=link_from_bridge_payload(payload),
            profile=_optional_str(payload.get("profile")),
        )

    def validates(self) -> None:
        if self.at_s < 0:
            raise ValueError("link_schedule.at_s must be non-negative")
        self.link.validates()

    def as_payload(self) -> dict[str, object]:
        payload = _link_payload_for_selector(self.link)
        payload["at_s"] = self.at_s
        if self.profile:
            payload["profile"] = self.profile
        return payload


@dataclass(frozen=True)
class LiveTransportBindingConfig:
    """Selector summary binding config for the live bridge loop."""

    summary: Path
    objective_summaries: Mapping[str, Path] = field(default_factory=dict)
    profile: str | None = None
    objective: str | None = None
    auto_profile: bool = False
    adaptive_profile: bool = False
    smoothing_alpha: float = 0.35
    hysteresis_margin: float = 0.06
    min_dwell_ticks: int = 2
    objective_schedule: tuple["LiveObjectiveScheduleEntry", ...] = ()

    @classmethod
    def from_payload(
        cls,
        payload: object,
    ) -> "LiveTransportBindingConfig | None":
        if payload is None or payload == "":
            return None
        data = dict(payload) if isinstance(payload, Mapping) else {}
        summary = data.get("summary", data.get("summary_json"))
        if summary is None or summary == "":
            raise ValueError("transport_binding.summary is required")
        return cls(
            summary=Path(str(summary)),
            objective_summaries={
                str(objective): Path(str(path))
                for objective, path in _mapping_items(
                    data.get("objective_summaries", data.get("summaries", {}))
                )
                if objective and path
            },
            profile=_optional_str(data.get("profile")),
            objective=_optional_str(data.get("objective")),
            auto_profile=bool(data.get("auto_profile", False)),
            adaptive_profile=bool(data.get("adaptive_profile", False)),
            smoothing_alpha=float(data.get("smoothing_alpha", 0.35)),
            hysteresis_margin=float(data.get("hysteresis_margin", 0.06)),
            min_dwell_ticks=int(data.get("min_dwell_ticks", 2)),
            objective_schedule=tuple(
                LiveObjectiveScheduleEntry.from_payload(item)
                for item in data.get("objective_schedule", [])
                if isinstance(item, Mapping)
            ),
        )

    def validates(self) -> None:
        if self.profile and (self.auto_profile or self.adaptive_profile):
            raise ValueError(
                "transport binding profile conflicts with auto/adaptive mode"
            )
        if self.auto_profile and self.adaptive_profile:
            raise ValueError("choose either auto_profile or adaptive_profile")
        if not 0 < self.smoothing_alpha <= 1:
            raise ValueError("smoothing_alpha must be in (0, 1]")
        if self.hysteresis_margin < 0:
            raise ValueError("hysteresis_margin must be non-negative")
        if self.min_dwell_ticks < 0:
            raise ValueError("min_dwell_ticks must be non-negative")
        previous_at_s = -1.0
        for entry in self.objective_schedule:
            entry.validates()
            if entry.at_s < previous_at_s:
                raise ValueError("objective_schedule entries must be sorted by at_s")
            previous_at_s = entry.at_s


@dataclass(frozen=True)
class LiveObjectiveScheduleEntry:
    """Scheduled QoS/QoE objective for one continuous live bridge run."""

    at_s: float
    objective: str

    @classmethod
    def from_payload(cls, payload: Mapping[str, object]) -> "LiveObjectiveScheduleEntry":
        return cls(
            at_s=float(payload.get("at_s", payload.get("offset_s", 0.0))),
            objective=str(payload.get("objective", "")),
        )

    def validates(self) -> None:
        if self.at_s < 0:
            raise ValueError("objective_schedule.at_s must be non-negative")
        if not self.objective:
            raise ValueError("objective_schedule.objective must be non-empty")

    def as_payload(self) -> dict[str, object]:
        return {"at_s": self.at_s, "objective": self.objective}


@dataclass
class _BufferedSample:
    config: BridgeTopicConfig
    payload_size_bytes: int | None
    received_ms: float
    queue_depth: int
    publisher_gid: str | None = None
    sequence_number: int | None = None
    source_timestamp_ns: int | None = None
    received_timestamp_ns: int | None = None
    semantic_payload: Mapping[str, object] | None = None


class Ros2LiveSampleBuffer:
    """Coalesce live ROS 2 callbacks into one sidecar batch per tick."""

    def __init__(
        self,
        *,
        adapter: Ros2SidecarAdapter | None = None,
        scenario: str = "ros2_live_bridge",
        link: NetworkLink | None = None,
        include_feedback: bool = False,
        link_provider: LiveLinkProvider | None = None,
        transport_binding: TransportBinding | Mapping[str, object] | None = None,
        transport_binding_provider: TransportBindingProvider | None = None,
        clock_ms: ClockMs | None = None,
    ) -> None:
        self.adapter = adapter or Ros2SidecarAdapter()
        self.scenario = scenario
        self.link = link or NetworkLink(capacity_bytes_per_tick=588)
        self.include_feedback = include_feedback
        self.link_provider = link_provider
        self.transport_binding = transport_binding_payload(transport_binding)
        self.transport_binding_provider = transport_binding_provider
        self.clock_ms = clock_ms or _monotonic_ms
        self._latest: dict[str, _BufferedSample] = {}
        self._tick = 0
        self._started_ms: float | None = None

    def record_sample(
        self,
        config: BridgeTopicConfig,
        *,
        payload_size_bytes: int | None,
        received_ms: float | None = None,
        publisher_gid: str | None = None,
        sequence_number: int | None = None,
        source_timestamp_ns: int | None = None,
        received_timestamp_ns: int | None = None,
        semantic_payload: Mapping[str, object] | None = None,
    ) -> None:
        now = self.clock_ms() if received_ms is None else received_ms
        key = config.flow_id or f"{config.topic}:{config.robot_id or ''}"
        previous = self._latest.get(key)
        queue_depth = 1 if previous is None else previous.queue_depth + 1
        self._latest[key] = _BufferedSample(
            config=config,
            payload_size_bytes=payload_size_bytes,
            received_ms=now,
            queue_depth=queue_depth,
            publisher_gid=publisher_gid,
            sequence_number=sequence_number,
            source_timestamp_ns=source_timestamp_ns,
            received_timestamp_ns=received_timestamp_ns,
            semantic_payload=semantic_payload,
        )

    def pending_count(self) -> int:
        return len(self._latest)

    def drain_samples(self, *, timestamp_ms: float | None = None) -> list[Ros2Sample]:
        now = self.clock_ms() if timestamp_ms is None else timestamp_ms
        samples = [
            item.config.to_sample(
                payload_size_bytes=item.payload_size_bytes,
                age_ms=max(0.0, now - item.received_ms),
                queue_depth=item.queue_depth,
                publisher_gid=item.publisher_gid,
                sequence_number=item.sequence_number,
                source_timestamp_ns=item.source_timestamp_ns,
                received_timestamp_ns=item.received_timestamp_ns,
                semantic_payload=item.semantic_payload,
            )
            for item in self._latest.values()
        ]
        self._latest.clear()
        return samples

    def drain_batch(self, *, timestamp_ms: float | None = None) -> dict[str, object]:
        now = self.clock_ms() if timestamp_ms is None else timestamp_ms
        samples = self.drain_samples(timestamp_ms=now)
        link = self._link_for_batch(now)
        if self._started_ms is None:
            self._started_ms = now
        context = LiveBindingContext(
            tick=self._tick,
            timestamp_ms=now,
            elapsed_s=max(0.0, (now - self._started_ms) / 1000.0),
        )
        transport_binding, transport_binding_estimate = (
            self._transport_binding_payloads_for_batch(link, context)
        )
        batch = self.adapter.build_batch(
            samples,
            scenario=self.scenario,
            link=link,
            timestamp_ms=now,
            tick=self._tick,
            include_feedback=self.include_feedback,
            transport_binding=transport_binding,
            transport_binding_estimate=transport_binding_estimate,
        )
        self._tick += 1
        return batch

    def _link_for_batch(self, timestamp_ms: float) -> NetworkLink:
        if self.link_provider:
            self.link = self.link_provider(self._tick, timestamp_ms, self.link)
        return self.link

    def _transport_binding_payloads_for_batch(
        self,
        link: NetworkLink,
        context: LiveBindingContext,
    ) -> tuple[dict[str, object] | None, dict[str, object] | None]:
        if self.transport_binding_provider:
            result = _call_transport_binding_provider(
                self.transport_binding_provider,
                link,
                context,
            )
            return _binding_provider_payloads(result)
        return self.transport_binding, None


class SidecarTcpClient:
    """Newline-delimited JSON client for a running SidecarRuntime TCP server."""

    def __init__(self, host: str, port: int, *, timeout_s: float = 5.0) -> None:
        self.host = host
        self.port = port
        self.timeout_s = timeout_s
        self._socket: socket.socket | None = None
        self._file = None

    def connect(self) -> None:
        if self._socket is not None:
            return
        self._socket = socket.create_connection((self.host, self.port), timeout=self.timeout_s)
        self._file = self._socket.makefile("rwb")

    def send_batch(self, batch: Mapping[str, object]) -> dict[str, object]:
        self.connect()
        if self._file is None:
            raise RuntimeError("sidecar TCP client is not connected")
        self._file.write((json.dumps(batch, sort_keys=True) + "\n").encode("utf-8"))
        self._file.flush()
        raw = self._file.readline()
        if not raw:
            raise ConnectionError("sidecar closed the TCP connection")
        return json.loads(raw.decode("utf-8"))

    def stop(self) -> dict[str, object] | None:
        if self._file is None:
            return None
        self._file.write(b'{"type":"stop"}\n')
        self._file.flush()
        raw = self._file.readline()
        return json.loads(raw.decode("utf-8")) if raw else None

    def close(self) -> None:
        if self._file is not None:
            self._file.close()
            self._file = None
        if self._socket is not None:
            self._socket.close()
            self._socket = None

    def __enter__(self) -> "SidecarTcpClient":
        self.connect()
        return self

    def __exit__(self, *_exc: object) -> None:
        self.close()


def load_bridge_config(path: str | Path) -> LiveBridgeConfig:
    with Path(path).open("r", encoding="utf-8") as handle:
        config = LiveBridgeConfig.from_payload(json.load(handle))
    config.validates()
    return config


def transport_binding_provider_for_config(
    config: LiveBridgeConfig,
) -> TransportBindingProvider | None:
    binding_config = config.transport_binding
    if binding_config is None:
        return None
    manager = TransportBindingManager(_combined_transport_selector_result(binding_config))

    def active_objective(context: LiveBindingContext | None) -> str | None:
        return _objective_for_context(binding_config, context)

    if binding_config.adaptive_profile:
        estimator = manager.adaptive_estimator(
            smoothing_alpha=binding_config.smoothing_alpha,
            hysteresis_margin=binding_config.hysteresis_margin,
            min_dwell_ticks=binding_config.min_dwell_ticks,
        )

        def adaptive_provider(
            link: NetworkLink,
            context: LiveBindingContext | None = None,
        ) -> AdaptiveBindingDecision:
            return estimator.update_from_link_payload(
                _link_payload_for_selector(link),
                objective=active_objective(context),
            )

        return adaptive_provider
    if binding_config.auto_profile:
        return lambda link, context=None: manager.binding_for_link_payload(
            _link_payload_for_selector(link),
            objective=active_objective(context),
        )
    if binding_config.profile:
        return lambda _link, context=None: manager.binding_for_profile(
            binding_config.profile,
            objective=active_objective(context),
        )
    binding = manager.bindings[0]
    return lambda _link: binding


def link_provider_for_config(config: LiveBridgeConfig) -> LiveLinkProvider | None:
    if not config.link_schedule:
        return None
    return ScheduledLiveLinkProvider(config.link_schedule)


class ScheduledLiveLinkProvider:
    """Return a scheduled NetworkLink for one continuous live bridge run."""

    def __init__(self, schedule: tuple[LiveLinkScheduleEntry, ...]) -> None:
        if not schedule:
            raise ValueError("link schedule must not be empty")
        self.schedule = schedule
        self._started_ms: float | None = None

    def __call__(
        self,
        _tick: int,
        timestamp_ms: float,
        _current: NetworkLink,
    ) -> NetworkLink:
        if self._started_ms is None:
            self._started_ms = timestamp_ms
        elapsed_s = max(0.0, (timestamp_ms - self._started_ms) / 1000.0)
        selected = self.schedule[0]
        for entry in self.schedule:
            if entry.at_s <= elapsed_s:
                selected = entry
            else:
                break
        return selected.link


def _binding_provider_payloads(
    result: TransportBindingProviderResult,
) -> tuple[dict[str, object] | None, dict[str, object] | None]:
    if isinstance(result, AdaptiveBindingDecision):
        return result.binding.as_payload(), result.estimate.as_payload()
    if isinstance(result, Mapping) and "binding" in result:
        estimate = result.get("estimate")
        return (
            transport_binding_payload(result.get("binding")),
            dict(estimate) if isinstance(estimate, Mapping) else None,
        )
    return transport_binding_payload(result), None


def _call_transport_binding_provider(
    provider: TransportBindingProvider,
    link: NetworkLink,
    context: LiveBindingContext,
) -> TransportBindingProviderResult:
    try:
        return provider(link, context)
    except TypeError as exc:
        try:
            return provider(link)
        except TypeError:
            raise exc


def _combined_transport_selector_result(
    binding_config: LiveTransportBindingConfig,
) -> dict[str, object]:
    summaries = [binding_config.summary, *binding_config.objective_summaries.values()]
    bindings: list[dict[str, object]] = []
    selections: list[dict[str, object]] = []
    sources: list[str] = []
    seen_bindings: set[tuple[str, str]] = set()
    seen_sources: set[str] = set()
    for path in summaries:
        source = str(path)
        if source not in seen_sources:
            sources.append(source)
            seen_sources.add(source)
        with path.open("r", encoding="utf-8") as handle:
            summary = json.load(handle)
        for binding in summary.get("bindings", []):
            if not isinstance(binding, Mapping):
                continue
            key = (str(binding.get("profile", "")), str(binding.get("objective", "")))
            if key in seen_bindings:
                continue
            bindings.append(dict(binding))
            seen_bindings.add(key)
        for selection in summary.get("selections", []):
            if isinstance(selection, Mapping):
                selections.append(dict(selection))
    return {
        "bindings": bindings,
        "selections": selections,
        "sources": sources,
    }


def _objective_for_context(
    binding_config: LiveTransportBindingConfig,
    context: LiveBindingContext | None,
) -> str | None:
    selected = binding_config.objective
    if context is None or not binding_config.objective_schedule:
        return selected
    for entry in binding_config.objective_schedule:
        if entry.at_s <= context.elapsed_s:
            selected = entry.objective
        else:
            break
    return selected


def link_from_bridge_payload(payload: object) -> NetworkLink:
    data = dict(payload) if isinstance(payload, Mapping) else {}
    return NetworkLink(
        capacity_bytes_per_tick=int(data.get("capacity_bytes_per_tick", 588)),
        loss=float(data.get("loss", data.get("loss_ratio", 0.0))),
        jitter_ms=float(data.get("jitter_ms", 0.0)),
        rtt_ms=float(data.get("rtt_ms", 20.0)),
    )


def _link_payload_for_selector(link: NetworkLink) -> dict[str, object]:
    return {
        "capacity_bytes_per_tick": link.capacity_bytes_per_tick,
        "loss": link.loss,
        "jitter_ms": link.jitter_ms,
        "rtt_ms": link.rtt_ms,
    }


def _monotonic_ms() -> float:
    return time.monotonic() * 1000.0


def _optional_str(value: object) -> str | None:
    if value is None or value == "":
        return None
    return str(value)


def _optional_float(value: object) -> float | None:
    try:
        return None if value is None or value == "" else float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None


def _mapping_items(payload: object):
    if not isinstance(payload, Mapping):
        return []
    return payload.items()


def _optional_bool(value: object) -> bool | None:
    if value is None or value == "":
        return None
    if isinstance(value, bool):
        return value
    return str(value).lower() in {"1", "true", "yes", "on"}

"""ROS 2-facing adapter boundary for FleetRMW sidecar batches.

This module deliberately avoids importing ``rclpy``.  A real ROS 2 bridge can
translate live subscriptions into :class:`Ros2Sample` records, while tests and
replay tools can feed the same schema without a ROS installation.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from fnmatch import fnmatch
import re
from typing import Iterable, Mapping

from .model import (
    FlowClass,
    FlowObservation,
    FlowSpec,
    NetworkLink,
    QoEProfile,
    QoSProfile,
    TaskContext,
)
from .rmw_contract import (
    FleetRmwSampleEnvelope,
    contract_id_for_fields,
    sample_envelope_from_payload,
    source_sample_id_from_semantic_payload,
)
from .sidecar_runtime import (
    flow_spec_to_payload,
    link_to_payload,
    observation_to_payload,
)
from .transport_selector import TransportBinding, transport_binding_payload


@dataclass(frozen=True)
class Ros2QoS:
    """Dependency-free subset of ROS 2 QoS metadata."""

    reliability: str = "system_default"
    durability: str = "volatile"
    depth: int | None = None
    deadline_ms: float | None = None
    lifespan_ms: float | None = None
    liveliness_lease_ms: float | None = None

    @classmethod
    def from_payload(cls, payload: object) -> "Ros2QoS":
        data = dict(payload) if isinstance(payload, Mapping) else {}
        return cls(
            reliability=str(data.get("reliability", data.get("reliability_policy", "system_default"))),
            durability=str(data.get("durability", data.get("durability_policy", "volatile"))),
            depth=_optional_int(data.get("depth", data.get("history_depth"))),
            deadline_ms=_duration_ms(data, "deadline"),
            lifespan_ms=_duration_ms(data, "lifespan"),
            liveliness_lease_ms=_duration_ms(data, "liveliness_lease"),
        )

    def to_fleet_qos(self, defaults: "TopicDefaults", flow_class: FlowClass) -> QoSProfile:
        return QoSProfile(
            reliability=_normalize_reliability(self.reliability, flow_class),
            durability=_normalize_durability(self.durability),
            depth=max(1, self.depth if self.depth is not None else defaults.depth),
            deadline_ms=self.deadline_ms or defaults.deadline_ms,
            lifespan_ms=self.lifespan_ms or defaults.lifespan_ms,
            liveliness_lease_ms=self.liveliness_lease_ms or defaults.liveliness_lease_ms,
        )


@dataclass(frozen=True)
class Ros2TopicRule:
    """Override automatic topic inference for a ROS 2 topic family."""

    pattern: str
    flow_class: FlowClass
    logical_name: str | None = None
    robot_id: str | None = None
    nominal_size_bytes: int | None = None
    nominal_rate_hz: float | None = None
    causal_task_gain: float | None = None
    semantic_delta_ratio: float | None = None
    redundancy: float | None = None
    operator_visible: bool | None = None

    def matches(self, topic: str) -> bool:
        return fnmatch(topic, self.pattern)


@dataclass(frozen=True)
class Ros2Sample:
    """One ROS 2 sample observation as seen by a shim or replay feeder."""

    topic: str
    msg_type: str = ""
    qos: Ros2QoS = field(default_factory=Ros2QoS)
    robot_id: str | None = None
    node_name: str = ""
    flow_id: str | None = None
    contract_id: str | None = None
    source_sample_id: str | None = None
    publisher_gid: str | None = None
    sequence_number: int | None = None
    source_timestamp_ns: int | None = None
    received_timestamp_ns: int | None = None
    sample_envelope: FleetRmwSampleEnvelope | None = None
    payload_size_bytes: int | None = None
    nominal_rate_hz: float | None = None
    age_ms: float = 0.0
    queue_depth: int = 1
    measured_loss: float | None = None
    measured_rtt_ms: float | None = None
    observed_jitter_ms: float | None = None
    task_id: str = "ros2_live"
    task_criticality: float | None = None
    collision_risk: float | None = None
    operator_attention: float | None = None
    coordination_pressure: float | None = None
    operator_visible: bool | None = None
    tags: Mapping[str, str] = field(default_factory=dict)
    semantic_payload: Mapping[str, object] | None = None

    @classmethod
    def from_payload(cls, payload: Mapping[str, object]) -> "Ros2Sample":
        qos = payload.get("qos", {})
        tags = payload.get("tags", {})
        semantic_payload = payload.get("semantic_payload")
        sample_envelope = sample_envelope_from_payload(payload.get("sample_envelope"))
        source_metadata = dict(payload.get("source_metadata", {})) if isinstance(payload.get("source_metadata"), Mapping) else {}
        return cls(
            topic=str(payload["topic"]),
            msg_type=str(payload.get("msg_type", payload.get("type", ""))),
            qos=Ros2QoS.from_payload(qos),
            robot_id=_optional_str(payload.get("robot_id")),
            node_name=str(payload.get("node_name", "")),
            flow_id=_optional_str(payload.get("flow_id")),
            contract_id=_optional_str(payload.get("contract_id")),
            source_sample_id=_optional_str(payload.get("source_sample_id")),
            publisher_gid=_optional_str(payload.get("publisher_gid")) or _optional_str(source_metadata.get("publisher_gid")),
            sequence_number=_first_optional_int(
                payload.get("sequence_number"),
                payload.get("publication_sequence_number"),
                payload.get("source_sequence_number"),
                source_metadata.get("sequence_number"),
                source_metadata.get("publication_sequence_number"),
            ),
            source_timestamp_ns=_first_optional_int(
                payload.get("source_timestamp_ns"),
                source_metadata.get("source_timestamp_ns"),
            ),
            received_timestamp_ns=_first_optional_int(
                payload.get("received_timestamp_ns"),
                source_metadata.get("received_timestamp_ns"),
            ),
            sample_envelope=sample_envelope,
            payload_size_bytes=_optional_int(payload.get("payload_size_bytes", payload.get("bytes"))),
            nominal_rate_hz=_optional_float(payload.get("nominal_rate_hz", payload.get("rate_hz"))),
            age_ms=float(payload.get("age_ms", 0.0)),
            queue_depth=int(payload.get("queue_depth", 1)),
            measured_loss=_optional_float(payload.get("measured_loss")),
            measured_rtt_ms=_optional_float(payload.get("measured_rtt_ms")),
            observed_jitter_ms=_optional_float(payload.get("observed_jitter_ms")),
            task_id=str(payload.get("task_id", "ros2_live")),
            task_criticality=_optional_float(payload.get("task_criticality")),
            collision_risk=_optional_float(payload.get("collision_risk")),
            operator_attention=_optional_float(payload.get("operator_attention")),
            coordination_pressure=_optional_float(payload.get("coordination_pressure")),
            operator_visible=_optional_bool(payload.get("operator_visible")),
            tags=dict(tags) if isinstance(tags, Mapping) else {},
            semantic_payload=dict(semantic_payload) if isinstance(semantic_payload, Mapping) else None,
        )


@dataclass(frozen=True)
class TopicDefaults:
    """FleetQoX defaults inferred from topic semantics."""

    flow_class: FlowClass
    logical_name: str
    reliability: str
    depth: int
    deadline_ms: float
    lifespan_ms: float
    liveliness_lease_ms: float
    nominal_size_bytes: int
    nominal_rate_hz: float
    causal_task_gain: float
    semantic_delta_ratio: float = 1.0
    redundancy: float = 0.0
    operator_visible: bool = False


class Ros2SidecarAdapter:
    """Build FleetRMW sidecar batches from ROS 2-like sample records."""

    def __init__(self, topic_rules: Iterable[Ros2TopicRule] | None = None) -> None:
        self.topic_rules = tuple(topic_rules or ())

    def flow_spec_for_sample(self, sample: Ros2Sample) -> FlowSpec:
        rule = self._rule_for(sample.topic)
        defaults = defaults_for_topic(sample.topic, sample.msg_type, rule)
        flow_class = rule.flow_class if rule else defaults.flow_class
        robot_id = sample.robot_id or (rule.robot_id if rule else None) or infer_robot_id(sample.topic, sample.node_name)
        logical_name = (rule.logical_name if rule else None) or defaults.logical_name
        qos = sample.qos.to_fleet_qos(defaults, flow_class)
        qoe = qoe_for_sample(sample, defaults, rule)
        size = sample.payload_size_bytes or rule_value(rule, "nominal_size_bytes") or estimate_message_size(
            sample.msg_type,
            defaults,
        )
        rate = sample.nominal_rate_hz or rule_value(rule, "nominal_rate_hz") or defaults.nominal_rate_hz
        gain = rule_value(rule, "causal_task_gain")
        delta = rule_value(rule, "semantic_delta_ratio")
        redundancy = rule_value(rule, "redundancy")
        flow_id = sample.flow_id or f"{robot_id}:{logical_name}"
        tags = {
            "ros2_msg_type": sample.msg_type,
            "ros2_node": sample.node_name,
            **dict(sample.tags),
        }
        return FlowSpec(
            flow_id=flow_id,
            robot_id=robot_id,
            topic=sample.topic,
            flow_class=flow_class,
            qos=qos,
            qoe=qoe,
            nominal_size_bytes=max(1, int(size)),
            nominal_rate_hz=max(0.001, float(rate)),
            causal_task_gain=float(gain if gain is not None else defaults.causal_task_gain),
            redundancy=float(redundancy if redundancy is not None else defaults.redundancy),
            semantic_delta_ratio=float(delta if delta is not None else defaults.semantic_delta_ratio),
            tags={key: value for key, value in tags.items() if value},
        )

    def observation_for_sample(self, sample: Ros2Sample, flow: FlowSpec, link: NetworkLink) -> FlowObservation:
        return FlowObservation(
            age_ms=max(0.0, sample.age_ms),
            queue_depth=max(1, sample.queue_depth),
            measured_loss=sample.measured_loss if sample.measured_loss is not None else link.loss,
            measured_rtt_ms=sample.measured_rtt_ms if sample.measured_rtt_ms is not None else link.rtt_ms,
            observed_jitter_ms=sample.observed_jitter_ms if sample.observed_jitter_ms is not None else link.jitter_ms,
            task=TaskContext(
                task_id=sample.task_id,
                robot_id=flow.robot_id,
                task_criticality=_defaulted(sample.task_criticality, default_task_criticality(flow.flow_class)),
                collision_risk=_defaulted(sample.collision_risk, default_collision_risk(flow.flow_class)),
                operator_attention=_defaulted(
                    sample.operator_attention,
                    1.0 if flow.qoe.operator_visible else 0.0,
                ),
                coordination_pressure=_defaulted(
                    sample.coordination_pressure,
                    default_coordination_pressure(flow.flow_class),
                ),
            ).clipped(),
        )

    def build_batch(
        self,
        samples: Iterable[Ros2Sample | Mapping[str, object]],
        *,
        scenario: str,
        link: NetworkLink,
        timestamp_ms: float,
        tick: int,
        include_feedback: bool = False,
        transport_binding: TransportBinding | Mapping[str, object] | None = None,
        transport_binding_estimate: Mapping[str, object] | None = None,
    ) -> dict[str, object]:
        flows = []
        for raw_sample in samples:
            sample = raw_sample if isinstance(raw_sample, Ros2Sample) else Ros2Sample.from_payload(raw_sample)
            flow = self.flow_spec_for_sample(sample)
            obs = self.observation_for_sample(sample, flow, link)
            sample_envelope = sample.sample_envelope
            source_sample_id = (
                sample.source_sample_id
                or (sample_envelope.source_sample_id if sample_envelope else None)
                or source_sample_id_from_semantic_payload(
                    robot_id=flow.robot_id,
                    topic=sample.topic,
                    msg_type=sample.msg_type,
                    semantic_payload=sample.semantic_payload,
                    publisher_id=sample_envelope.publisher_id if sample_envelope else None,
                    publisher_gid=sample.publisher_gid,
                    sequence_number=sample.sequence_number,
                    source_timestamp_ns=sample.source_timestamp_ns,
                )
            )
            contract_id = sample.contract_id or contract_id_for_fields(
                scenario=scenario,
                tick=tick,
                flow_id=flow.flow_id,
                robot_id=flow.robot_id,
                topic=sample.topic,
                msg_type=sample.msg_type,
                source_sample_id=source_sample_id,
            )
            source_sample_id = source_sample_id or contract_id
            source_metadata = (
                sample_envelope.source_metadata_payload()
                if sample_envelope
                else source_metadata_payload_for_sample(sample)
            )
            flows.append(
                {
                    "contract_id": contract_id,
                    "source_sample_id": source_sample_id,
                    "flow": flow_spec_to_payload(flow),
                    "observation": observation_to_payload(obs),
                    **({"source_metadata": source_metadata} if source_metadata else {}),
                    **({"sample_envelope": sample_envelope.as_payload()} if sample_envelope else {}),
                    **({"semantic_payload": dict(sample.semantic_payload)} if sample.semantic_payload else {}),
                }
            )
        batch: dict[str, object] = {
            "type": "batch",
            "scenario": scenario,
            "timestamp_ms": timestamp_ms,
            "tick": tick,
            "link": link_to_payload(link),
            "flows": flows,
        }
        if include_feedback:
            batch["include_feedback"] = True
        binding_payload = transport_binding_payload(transport_binding)
        if binding_payload:
            batch["transport_binding"] = binding_payload
        if transport_binding_estimate:
            batch["transport_binding_estimate"] = dict(transport_binding_estimate)
        return batch

    def _rule_for(self, topic: str) -> Ros2TopicRule | None:
        for rule in self.topic_rules:
            if rule.matches(topic):
                return rule
        return None


def defaults_for_topic(topic: str, msg_type: str = "", rule: Ros2TopicRule | None = None) -> TopicDefaults:
    if rule:
        base = _defaults_for_class(rule.flow_class)
        return TopicDefaults(
            flow_class=rule.flow_class,
            logical_name=rule.logical_name or base.logical_name,
            reliability=base.reliability,
            depth=base.depth,
            deadline_ms=base.deadline_ms,
            lifespan_ms=base.lifespan_ms,
            liveliness_lease_ms=base.liveliness_lease_ms,
            nominal_size_bytes=rule.nominal_size_bytes or base.nominal_size_bytes,
            nominal_rate_hz=rule.nominal_rate_hz or base.nominal_rate_hz,
            causal_task_gain=rule.causal_task_gain if rule.causal_task_gain is not None else base.causal_task_gain,
            semantic_delta_ratio=rule.semantic_delta_ratio if rule.semantic_delta_ratio is not None else base.semantic_delta_ratio,
            redundancy=rule.redundancy if rule.redundancy is not None else base.redundancy,
            operator_visible=rule.operator_visible if rule.operator_visible is not None else base.operator_visible,
        )

    normalized = topic.lower()
    msg = msg_type.lower()
    if _contains_any(normalized, ("cmd_vel", "cmd/vel", "trajectory_cmd", "twist_cmd")):
        return _defaults_for_class(FlowClass.CONTROL)
    if _contains_any(normalized, ("estop", "e_stop", "emergency", "safety")):
        return _defaults_for_class(FlowClass.SAFETY)
    if _contains_any(normalized, ("coord", "intent", "reservation", "formation")):
        return _defaults_for_class(FlowClass.COORDINATION)
    if _contains_any(normalized, ("debug", "log", "trace")):
        return _defaults_for_class(FlowClass.DEBUG)
    if _contains_any(normalized, ("image", "camera", "video", "qoe")) or "image" in msg:
        if "qoe" in normalized or "front_camera" in normalized:
            return _defaults_for_class(FlowClass.HUMAN_QOE)
        return _defaults_for_class(FlowClass.PERCEPTION)
    if _contains_any(normalized, ("scan", "lidar", "pointcloud", "points", "obstacle", "costmap", "map")):
        return _defaults_for_class(FlowClass.PERCEPTION)
    if _contains_any(normalized, ("state", "odom", "tf", "joint_states", "battery", "pose")):
        return _defaults_for_class(FlowClass.STATE)
    return _defaults_for_class(FlowClass.STATE)


def infer_robot_id(topic: str, node_name: str = "") -> str:
    haystack = f"{topic}/{node_name}"
    for token in re.split(r"[^A-Za-z0-9_-]+", haystack):
        if re.fullmatch(r"(robot|tb|turtlebot)[A-Za-z0-9_-]*", token, flags=re.IGNORECASE):
            return token
    return "robot_0000"


def estimate_message_size(msg_type: str, defaults: TopicDefaults) -> int:
    msg = msg_type.lower()
    if "compressedimage" in msg:
        return 9000
    if "image" in msg:
        return 50_000
    if "pointcloud2" in msg or "point_cloud" in msg:
        return 40_000
    if "laserscan" in msg:
        return 2200
    if "odometry" in msg:
        return 320
    if "twist" in msg:
        return 96
    if "imu" in msg:
        return 240
    if "battery" in msg:
        return 128
    if "string" in msg or "diagnostic" in msg:
        return max(defaults.nominal_size_bytes, 512)
    return defaults.nominal_size_bytes


def qoe_for_sample(
    sample: Ros2Sample,
    defaults: TopicDefaults,
    rule: Ros2TopicRule | None,
) -> QoEProfile:
    operator_visible = sample.operator_visible
    if operator_visible is None and rule and rule.operator_visible is not None:
        operator_visible = rule.operator_visible
    if operator_visible is None:
        operator_visible = defaults.operator_visible
    if defaults.flow_class is not FlowClass.HUMAN_QOE:
        return QoEProfile(operator_visible=bool(operator_visible))
    return QoEProfile(
        operator_visible=bool(operator_visible),
        smoothness_weight=0.8,
        freeze_penalty=1.0,
        visual_confidence_weight=0.7,
    )


def default_task_criticality(flow_class: FlowClass) -> float:
    return {
        FlowClass.SAFETY: 1.0,
        FlowClass.CONTROL: 0.9,
        FlowClass.COORDINATION: 0.75,
        FlowClass.STATE: 0.45,
        FlowClass.PERCEPTION: 0.55,
        FlowClass.HUMAN_QOE: 0.5,
        FlowClass.DEBUG: 0.05,
        FlowClass.BULK: 0.02,
    }[flow_class]


def default_collision_risk(flow_class: FlowClass) -> float:
    return 0.8 if flow_class in {FlowClass.SAFETY, FlowClass.CONTROL} else 0.1


def default_coordination_pressure(flow_class: FlowClass) -> float:
    return 0.8 if flow_class is FlowClass.COORDINATION else 0.15 if flow_class is FlowClass.CONTROL else 0.0


def _defaults_for_class(flow_class: FlowClass) -> TopicDefaults:
    table = {
        FlowClass.SAFETY: TopicDefaults(flow_class, "safety", "reliable", 1, 30.0, 80.0, 300.0, 80, 50.0, 1.0),
        FlowClass.CONTROL: TopicDefaults(flow_class, "cmd", "reliable", 1, 45.0, 90.0, 500.0, 96, 50.0, 0.85),
        FlowClass.COORDINATION: TopicDefaults(flow_class, "coord", "reliable", 2, 80.0, 200.0, 500.0, 192, 8.0, 0.7),
        FlowClass.STATE: TopicDefaults(flow_class, "state", "reliable", 3, 120.0, 350.0, 800.0, 320, 10.0, 0.55, 0.55),
        FlowClass.PERCEPTION: TopicDefaults(flow_class, "perception", "best_effort", 1, 160.0, 300.0, 800.0, 2200, 8.0, 0.55, 0.35, 0.2),
        FlowClass.HUMAN_QOE: TopicDefaults(flow_class, "video", "best_effort", 1, 120.0, 180.0, 500.0, 9000, 12.0, 0.5, 0.75, 0.15, True),
        FlowClass.DEBUG: TopicDefaults(flow_class, "debug", "best_effort", 5, 1000.0, 2500.0, 3000.0, 1800, 2.0, 0.02, 1.0, 0.8),
        FlowClass.BULK: TopicDefaults(flow_class, "bulk", "best_effort", 5, 2000.0, 5000.0, 5000.0, 20_000, 1.0, 0.01, 1.0, 0.8),
    }
    return table[flow_class]


def _normalize_reliability(value: str, flow_class: FlowClass) -> str:
    normalized = value.lower()
    if "best" in normalized:
        return "best_effort"
    if "reliable" in normalized:
        return "reliable"
    return "reliable" if flow_class in {FlowClass.SAFETY, FlowClass.CONTROL, FlowClass.COORDINATION, FlowClass.STATE} else "best_effort"


def _normalize_durability(value: str) -> str:
    normalized = value.lower()
    if "transient" in normalized:
        return "transient_local"
    return "volatile"


def _duration_ms(data: Mapping[str, object], name: str) -> float | None:
    for key, scale in (
        (f"{name}_ms", 1.0),
        (f"{name}_sec", 1000.0),
        (f"{name}_s", 1000.0),
        (f"{name}_ns", 1.0 / 1_000_000.0),
    ):
        value = _optional_float(data.get(key))
        if value is not None:
            return value * scale
    value = data.get(name)
    if isinstance(value, Mapping):
        sec = _optional_float(value.get("sec")) or 0.0
        nsec = _optional_float(value.get("nanosec", value.get("nsec"))) or 0.0
        return sec * 1000.0 + nsec / 1_000_000.0
    return _optional_float(value)


def _contains_any(value: str, needles: tuple[str, ...]) -> bool:
    return any(needle in value for needle in needles)


def _defaulted(value: float | None, default: float) -> float:
    return default if value is None else value


def _optional_str(value: object) -> str | None:
    if value is None or value == "":
        return None
    return str(value)


def _optional_int(value: object) -> int | None:
    try:
        return None if value is None or value == "" else int(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None


def _first_optional_int(*values: object) -> int | None:
    for value in values:
        parsed = _optional_int(value)
        if parsed is not None:
            return parsed
    return None


def _optional_float(value: object) -> float | None:
    try:
        return None if value is None or value == "" else float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None


def _optional_bool(value: object) -> bool | None:
    if value is None or value == "":
        return None
    if isinstance(value, bool):
        return value
    return str(value).lower() in {"1", "true", "yes", "on"}


def rule_value(rule: Ros2TopicRule | None, field_name: str) -> object | None:
    if rule is None:
        return None
    return getattr(rule, field_name)


def source_metadata_payload_for_sample(sample: Ros2Sample) -> dict[str, object]:
    metadata: dict[str, object] = {}
    if sample.publisher_gid:
        metadata["publisher_gid"] = sample.publisher_gid
    if sample.sequence_number is not None:
        metadata["sequence_number"] = sample.sequence_number
    if sample.source_timestamp_ns is not None:
        metadata["source_timestamp_ns"] = sample.source_timestamp_ns
    if sample.received_timestamp_ns is not None:
        metadata["received_timestamp_ns"] = sample.received_timestamp_ns
    return metadata

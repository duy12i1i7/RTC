"""FleetRMW sample contract between admission and local delivery.

This module is intentionally dependency-free.  It represents the boundary a
future RMW implementation should preserve after the control plane has decided
how a ROS sample may travel, but before a concrete data plane or local ROS
topic adapter publishes it.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from typing import Mapping

from .projection_identity import projection_signature_record


CONTRACT_ID_VERSION = "fleetrmw.contract_id.v1"
PUBLISHER_ID_VERSION = "fleetrmw.publisher_id.v1"
SAMPLE_ENVELOPE_SCHEMA_VERSION = "fleetrmw.sample_envelope.v1"
SOURCE_SAMPLE_ID_VERSION = "fleetrmw.source_sample_id.v1"
TYPED_PROJECTION_SCHEMA_VERSION = "fleetrmw.typed_projection.v1"
PROJECTION_QUALITY_SCHEMA_VERSION = "fleetrmw.projection_quality.v1"
QUALIFIED_PROJECTION_SCHEMA_VERSION = "fleetrmw.qualified_projection.v1"
SAMPLE_CONTRACT_SCHEMA_VERSION = "fleetrmw.rmw_sample_contract.v1"


@dataclass(frozen=True)
class FleetRmwSampleEnvelope:
    """Native FleetRMW source-sample envelope before admission/projection."""

    publisher_id: str
    source_sample_id: str
    robot_id: str
    topic: str
    msg_type: str
    source_sequence_number: int | None = None
    source_timestamp_ns: int | None = None
    received_timestamp_ns: int | None = None
    publisher_gid: str | None = None
    node_name: str | None = None
    rmw_implementation: str | None = None

    def as_payload(self) -> dict[str, object]:
        return {
            "schema_version": SAMPLE_ENVELOPE_SCHEMA_VERSION,
            "publisher_id": self.publisher_id,
            "source_sample_id": self.source_sample_id,
            "robot_id": self.robot_id,
            "topic": self.topic,
            "msg_type": self.msg_type,
            **({"source_sequence_number": self.source_sequence_number} if self.source_sequence_number is not None else {}),
            **({"source_timestamp_ns": self.source_timestamp_ns} if self.source_timestamp_ns is not None else {}),
            **({"received_timestamp_ns": self.received_timestamp_ns} if self.received_timestamp_ns is not None else {}),
            **({"publisher_gid": self.publisher_gid} if self.publisher_gid else {}),
            **({"node_name": self.node_name} if self.node_name else {}),
            **({"rmw_implementation": self.rmw_implementation} if self.rmw_implementation else {}),
        }

    def source_metadata_payload(self) -> dict[str, object]:
        """Compatibility view for the existing sidecar source_metadata field."""

        return {
            "publisher_id": self.publisher_id,
            **({"publisher_gid": self.publisher_gid} if self.publisher_gid else {}),
            **({"sequence_number": self.source_sequence_number} if self.source_sequence_number is not None else {}),
            **({"source_sequence_number": self.source_sequence_number} if self.source_sequence_number is not None else {}),
            **({"source_timestamp_ns": self.source_timestamp_ns} if self.source_timestamp_ns is not None else {}),
            **({"received_timestamp_ns": self.received_timestamp_ns} if self.received_timestamp_ns is not None else {}),
        }


@dataclass(frozen=True)
class FleetRmwSampleIdentity:
    """Stable identity for a projected FleetRMW sample."""

    contract_id: str | None
    source_sample_id: str | None
    event_id: int | None
    robot_id: str | None
    flow_id: str | None
    source_topic: str | None
    source_msg_type: str | None
    projection_kind: str
    projection_topic: str
    projection_msg_type: str
    projection_signature_version: str
    projection_signature_algorithm: str
    projection_signature: str

    def as_payload(self) -> dict[str, object]:
        return {
            "contract_id": self.contract_id,
            "source_sample_id": self.source_sample_id,
            "event_id": self.event_id,
            "robot_id": self.robot_id,
            "flow_id": self.flow_id,
            "source_topic": self.source_topic,
            "source_msg_type": self.source_msg_type,
            "projection_kind": self.projection_kind,
            "projection_topic": self.projection_topic,
            "projection_msg_type": self.projection_msg_type,
            "projection_signature_version": self.projection_signature_version,
            "projection_signature_algorithm": self.projection_signature_algorithm,
            "projection_signature": self.projection_signature,
        }


@dataclass(frozen=True)
class FleetRmwDeliveryContract:
    """Admission, timing, and fidelity contract attached to a projected sample."""

    action: str | None
    wire_mode: str | None
    valid_until_timestamp_ms: float | None
    deadline_ms: float | None
    lifespan_ms: float | None
    age_ms: float | None
    semantic_utility: float | None
    task_criticality: float | None
    collision_risk: float | None
    operator_attention: float | None
    coordination_pressure: float | None
    raw_serialized_sample_preserved: bool
    reconstruction: str
    fidelity_class: str
    lossy: bool
    degradation_reasons: tuple[str, ...]
    source_sample_count: int | None
    projected_sample_count: int | None
    downsample_stride: int | None

    def as_payload(self) -> dict[str, object]:
        return {
            "action": self.action,
            "wire_mode": self.wire_mode,
            "valid_until_timestamp_ms": self.valid_until_timestamp_ms,
            "deadline_ms": self.deadline_ms,
            "lifespan_ms": self.lifespan_ms,
            "age_ms": self.age_ms,
            "semantic_utility": self.semantic_utility,
            "task_criticality": self.task_criticality,
            "collision_risk": self.collision_risk,
            "operator_attention": self.operator_attention,
            "coordination_pressure": self.coordination_pressure,
            "raw_serialized_sample_preserved": self.raw_serialized_sample_preserved,
            "reconstruction": self.reconstruction,
            "fidelity_class": self.fidelity_class,
            "lossy": self.lossy,
            "degradation_reasons": list(self.degradation_reasons),
            "source_sample_count": self.source_sample_count,
            "projected_sample_count": self.projected_sample_count,
            "downsample_stride": self.downsample_stride,
        }


@dataclass(frozen=True)
class FleetRmwProjectedSample:
    """A reconstructed ROS-facing sample plus its FleetRMW delivery contract."""

    identity: FleetRmwSampleIdentity
    delivery: FleetRmwDeliveryContract
    sample_payload: Mapping[str, object]
    projection_payload_embedded: bool = False

    def contract_payload(self) -> dict[str, object]:
        return {
            "schema_version": SAMPLE_CONTRACT_SCHEMA_VERSION,
            "identity": self.identity.as_payload(),
            "delivery": self.delivery.as_payload(),
        }

    def quality_payload(self) -> dict[str, object]:
        quality = {
            "schema_version": PROJECTION_QUALITY_SCHEMA_VERSION,
            "kind": "typed_projection_quality",
            **self.identity.as_payload(),
            **self.delivery.as_payload(),
            "projection_payload_embedded": self.projection_payload_embedded,
        }
        if self.projection_payload_embedded:
            quality["projection_payload"] = dict(self.sample_payload)
        return quality

    def qualified_payload(self, *, kind: str) -> dict[str, object]:
        return {
            "schema_version": QUALIFIED_PROJECTION_SCHEMA_VERSION,
            "kind": kind,
            "sample": dict(self.sample_payload),
            "quality": self.quality_payload(),
        }


def projected_sample_from_sidecar_event(
    *,
    event: Mapping[str, object],
    semantic_payload: Mapping[str, object],
    projection_kind: str,
    projection_topic: str,
    projection_msg_type: str,
    projection_payload: Mapping[str, object],
    include_projection_payload: bool = True,
) -> FleetRmwProjectedSample:
    """Build a FleetRMW sample contract from a sidecar packet event."""

    signature = projection_signature_record(projection_kind, projection_payload)
    fidelity = projection_fidelity(
        event=event,
        projection_kind=projection_kind,
        projection_payload=projection_payload,
    )
    return FleetRmwProjectedSample(
        identity=FleetRmwSampleIdentity(
            contract_id=_optional_str(event.get("contract_id")),
            source_sample_id=_optional_str(event.get("source_sample_id")),
            event_id=_optional_int(event.get("event_id")),
            robot_id=_optional_str(event.get("robot_id")),
            flow_id=_optional_str(event.get("flow_id")),
            source_topic=_optional_str(event.get("topic")),
            source_msg_type=_optional_str(semantic_payload.get("msg_type")),
            projection_kind=projection_kind,
            projection_topic=projection_topic,
            projection_msg_type=projection_msg_type,
            projection_signature_version=str(signature["projection_signature_version"]),
            projection_signature_algorithm=str(signature["projection_signature_algorithm"]),
            projection_signature=str(signature["projection_signature"]),
        ),
        delivery=FleetRmwDeliveryContract(
            action=_optional_str(event.get("action")),
            wire_mode=_optional_str(event.get("wire_mode")),
            valid_until_timestamp_ms=valid_until_timestamp_ms(event),
            deadline_ms=_optional_float(event.get("deadline_ms")),
            lifespan_ms=_optional_float(event.get("lifespan_ms")),
            age_ms=_optional_float(event.get("age_ms")),
            semantic_utility=_optional_float(event.get("semantic_utility")),
            task_criticality=_optional_float(event.get("task_criticality")),
            collision_risk=_optional_float(event.get("collision_risk")),
            operator_attention=_optional_float(event.get("operator_attention")),
            coordination_pressure=_optional_float(event.get("coordination_pressure")),
            raw_serialized_sample_preserved=False,
            reconstruction="typed_projection_from_semantic_payload",
            fidelity_class=str(fidelity["fidelity_class"]),
            lossy=bool(fidelity["lossy"]),
            degradation_reasons=tuple(str(item) for item in _sequence(fidelity["degradation_reasons"])),
            source_sample_count=_optional_int(fidelity.get("source_sample_count")),
            projected_sample_count=_optional_int(fidelity.get("projected_sample_count")),
            downsample_stride=_optional_int(fidelity.get("downsample_stride")),
        ),
        sample_payload=dict(projection_payload),
        projection_payload_embedded=include_projection_payload,
    )


def typed_projection_payload_base(
    event: Mapping[str, object],
    *,
    kind: str,
    projection_topic: str,
) -> dict[str, object]:
    return {
        "schema_version": TYPED_PROJECTION_SCHEMA_VERSION,
        "kind": kind,
        "contract_id": _optional_str(event.get("contract_id")),
        "source_sample_id": _optional_str(event.get("source_sample_id")),
        "event_id": _optional_int(event.get("event_id")),
        "robot_id": _optional_str(event.get("robot_id")),
        "flow_id": _optional_str(event.get("flow_id")),
        "source_topic": _optional_str(event.get("topic")),
        "wire_mode": _optional_str(event.get("wire_mode")),
        "action": _optional_str(event.get("action")),
        "valid_until_timestamp_ms": valid_until_timestamp_ms(event),
        "projection_topic": projection_topic,
    }


def contract_id_for_fields(
    *,
    scenario: str,
    tick: int,
    flow_id: str,
    robot_id: str,
    topic: str,
    msg_type: str,
    source_sample_id: str | None = None,
) -> str:
    """Build a stable FleetRMW contract ID for one shim-visible sample."""

    payload = {
        "schema_version": CONTRACT_ID_VERSION,
        "scenario": scenario,
        "tick": int(tick),
        "flow_id": flow_id,
        "robot_id": robot_id,
        "topic": topic,
        "msg_type": msg_type,
        "source_sample_id": source_sample_id or "",
    }
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")
    return f"fcid1-{hashlib.sha256(encoded).hexdigest()[:32]}"


def publisher_id_for_fields(
    *,
    robot_id: str,
    topic: str,
    msg_type: str,
    node_name: str | None = None,
    publisher_gid: str | None = None,
    rmw_implementation: str | None = None,
) -> str:
    """Build a stable FleetRMW publisher endpoint identity."""

    payload = {
        "schema_version": PUBLISHER_ID_VERSION,
        "robot_id": robot_id,
        "topic": topic,
        "msg_type": msg_type,
        "node_name": node_name or "",
        "publisher_gid": publisher_gid or "",
        "rmw_implementation": rmw_implementation or "",
    }
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")
    return f"fpub1-{hashlib.sha256(encoded).hexdigest()[:32]}"


def sample_envelope_for_fields(
    *,
    robot_id: str,
    topic: str,
    msg_type: str,
    publisher_id: str | None = None,
    source_sample_id: str | None = None,
    source_sequence_number: int | None = None,
    source_timestamp_ns: int | None = None,
    received_timestamp_ns: int | None = None,
    publisher_gid: str | None = None,
    node_name: str | None = None,
    rmw_implementation: str | None = None,
) -> FleetRmwSampleEnvelope:
    """Build the native source envelope a future rmw_fleetrmw data plane owns."""

    effective_publisher_id = publisher_id or publisher_id_for_fields(
        robot_id=robot_id,
        topic=topic,
        msg_type=msg_type,
        node_name=node_name,
        publisher_gid=publisher_gid,
        rmw_implementation=rmw_implementation,
    )
    if source_sample_id is None and source_sequence_number is None and source_timestamp_ns is None:
        raise ValueError("sample envelope requires source_sample_id, source_sequence_number, or source_timestamp_ns")
    effective_source_sample_id = source_sample_id or source_sample_id_for_fields(
        robot_id=robot_id,
        topic=topic,
        msg_type=msg_type,
        publisher_id=effective_publisher_id,
        publisher_gid=publisher_gid,
        sequence_number=source_sequence_number,
        source_timestamp_ns=source_timestamp_ns,
    )
    return FleetRmwSampleEnvelope(
        publisher_id=effective_publisher_id,
        source_sample_id=effective_source_sample_id,
        robot_id=robot_id,
        topic=topic,
        msg_type=msg_type,
        source_sequence_number=source_sequence_number,
        source_timestamp_ns=source_timestamp_ns,
        received_timestamp_ns=received_timestamp_ns,
        publisher_gid=publisher_gid,
        node_name=node_name,
        rmw_implementation=rmw_implementation,
    )


def sample_envelope_from_payload(payload: object) -> FleetRmwSampleEnvelope | None:
    """Parse a FleetRMW sample envelope payload, deriving missing IDs if possible."""

    data = _mapping(payload)
    if not data:
        return None
    robot_id = _optional_str(data.get("robot_id"))
    topic = _optional_str(data.get("topic"))
    msg_type = _optional_str(data.get("msg_type") or data.get("type"))
    if not robot_id or not topic or not msg_type:
        return None
    source_sequence_number = _first_optional_int(
        data.get("source_sequence_number"),
        data.get("sequence_number"),
        data.get("publication_sequence_number"),
    )
    source_timestamp_ns = _first_optional_int(data.get("source_timestamp_ns"), data.get("source_timestamp"))
    received_timestamp_ns = _first_optional_int(data.get("received_timestamp_ns"), data.get("received_timestamp"))
    source_sample_id = _optional_str(data.get("source_sample_id"))
    if source_sample_id is None and source_sequence_number is None and source_timestamp_ns is None:
        return None
    return sample_envelope_for_fields(
        robot_id=robot_id,
        topic=topic,
        msg_type=msg_type,
        publisher_id=_optional_str(data.get("publisher_id")),
        source_sample_id=source_sample_id,
        source_sequence_number=source_sequence_number,
        source_timestamp_ns=source_timestamp_ns,
        received_timestamp_ns=received_timestamp_ns,
        publisher_gid=_optional_str(data.get("publisher_gid")),
        node_name=_optional_str(data.get("node_name")),
        rmw_implementation=_optional_str(data.get("rmw_implementation")),
    )


def source_sample_id_for_fields(
    *,
    robot_id: str,
    topic: str,
    msg_type: str,
    stamp_sec: int | None = None,
    stamp_nanosec: int | None = None,
    frame_id: str | None = None,
    publisher_id: str | None = None,
    publisher_gid: str | None = None,
    sequence_number: int | None = None,
    source_timestamp_ns: int | None = None,
) -> str:
    """Build a stable ID for the original ROS/RMW-visible source sample."""

    payload = {
        "schema_version": SOURCE_SAMPLE_ID_VERSION,
        "robot_id": robot_id,
        "topic": topic,
        "msg_type": msg_type,
        "stamp_sec": stamp_sec,
        "stamp_nanosec": stamp_nanosec,
        "frame_id": frame_id or "",
        "publisher_id": publisher_id or "",
        "publisher_gid": publisher_gid or "",
        "sequence_number": sequence_number,
    }
    if source_timestamp_ns is not None:
        payload["source_timestamp_ns"] = source_timestamp_ns
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")
    return f"fsid1-{hashlib.sha256(encoded).hexdigest()[:32]}"


def source_sample_id_from_semantic_payload(
    *,
    robot_id: str,
    topic: str,
    msg_type: str,
    semantic_payload: Mapping[str, object] | None,
    publisher_id: str | None = None,
    publisher_gid: str | None = None,
    sequence_number: int | None = None,
    source_timestamp_ns: int | None = None,
) -> str | None:
    """Derive source identity from semantic payload metadata when available."""

    if not isinstance(semantic_payload, Mapping):
        if sequence_number is None and source_timestamp_ns is None:
            return None
        return source_sample_id_for_fields(
            robot_id=robot_id,
            topic=topic,
            msg_type=msg_type,
            publisher_id=publisher_id,
            publisher_gid=publisher_gid,
            sequence_number=sequence_number,
            source_timestamp_ns=source_timestamp_ns,
        )
    explicit = _optional_str(semantic_payload.get("source_sample_id"))
    if explicit:
        return explicit
    sample_envelope = sample_envelope_from_payload(semantic_payload.get("sample_envelope"))
    if sample_envelope is not None:
        return sample_envelope.source_sample_id
    source_metadata = _mapping(semantic_payload.get("source_metadata"))
    effective_publisher_id = (
        _optional_str(semantic_payload.get("publisher_id"))
        or _optional_str(source_metadata.get("publisher_id"))
        or publisher_id
    )
    effective_publisher_gid = (
        _optional_str(semantic_payload.get("publisher_gid"))
        or _optional_str(source_metadata.get("publisher_gid"))
        or publisher_gid
    )
    effective_sequence_number = _first_optional_int(
        semantic_payload.get("sequence_number"),
        semantic_payload.get("source_sequence_number"),
        semantic_payload.get("publication_sequence_number"),
        source_metadata.get("sequence_number"),
        source_metadata.get("source_sequence_number"),
        source_metadata.get("publication_sequence_number"),
        sequence_number,
    )
    effective_source_timestamp_ns = _first_optional_int(
        semantic_payload.get("source_timestamp_ns"),
        source_metadata.get("source_timestamp_ns"),
        source_timestamp_ns,
    )
    header = _mapping(semantic_payload.get("header"))
    stamp = _mapping(header.get("stamp"))
    stamp_sec = _optional_int(stamp.get("sec"))
    stamp_nanosec = _optional_int(stamp.get("nanosec"))
    has_header_stamp = stamp_sec is not None or stamp_nanosec is not None
    has_rmw_sample_id = effective_sequence_number is not None or effective_source_timestamp_ns is not None
    if not has_header_stamp and not has_rmw_sample_id:
        return None
    return source_sample_id_for_fields(
        robot_id=robot_id,
        topic=topic,
        msg_type=msg_type,
        stamp_sec=(stamp_sec or 0) if has_header_stamp else None,
        stamp_nanosec=(stamp_nanosec or 0) if has_header_stamp else None,
        frame_id=_optional_str(header.get("frame_id")),
        publisher_id=effective_publisher_id,
        publisher_gid=effective_publisher_gid,
        sequence_number=effective_sequence_number,
        source_timestamp_ns=effective_source_timestamp_ns,
    )


def projection_fidelity(
    *,
    event: Mapping[str, object],
    projection_kind: str,
    projection_payload: Mapping[str, object],
) -> dict[str, object]:
    action = str(event.get("action", ""))
    wire_mode = str(event.get("wire_mode", "native"))
    degradation_reasons: list[str] = []
    downsample_stride: int | None = None
    source_sample_count: int | None = None
    projected_sample_count: int | None = None

    if action != "send" or wire_mode != "native":
        degradation_reasons.append(f"wire_mode:{wire_mode}")
    if projection_kind == "typed_twist" and wire_mode in {"control_intent", "supervisory_intent"}:
        degradation_reasons.append("control_authority_projection")
    if projection_kind == "typed_scan":
        scan_map = _mapping(projection_payload.get("scan"))
        downsample_stride = _optional_int(scan_map.get("downsample_stride")) or 1
        source_sample_count = _optional_int(scan_map.get("source_sample_count"))
        projected_sample_count = len(_float_list(scan_map.get("ranges")))
        if downsample_stride > 1:
            degradation_reasons.append("range_downsampled")
    if projection_kind == "typed_odom":
        odom_map = _mapping(projection_payload.get("odometry"))
        pose_map = _mapping(odom_map.get("pose"))
        twist_map = _mapping(odom_map.get("twist"))
        if not _float_list(pose_map.get("covariance"), limit=36):
            degradation_reasons.append("pose_covariance_missing")
        if not _float_list(twist_map.get("covariance"), limit=36):
            degradation_reasons.append("twist_covariance_missing")

    if projection_kind == "typed_scan" and downsample_stride and downsample_stride > 1:
        fidelity_class = "downsampled_projection"
    elif action == "send" and wire_mode == "native" and not degradation_reasons:
        fidelity_class = "raw_equivalent_projection"
    elif wire_mode in {"native", "semantic_delta"}:
        fidelity_class = "semantic_projection"
    else:
        fidelity_class = "degraded_projection"

    return {
        "fidelity_class": fidelity_class,
        "lossy": fidelity_class != "raw_equivalent_projection",
        "degradation_reasons": degradation_reasons,
        "source_sample_count": source_sample_count,
        "projected_sample_count": projected_sample_count,
        "downsample_stride": downsample_stride,
    }


def valid_until_timestamp_ms(event: Mapping[str, object]) -> float | None:
    timestamp_ms = _optional_float(event.get("timestamp_ms"))
    lifespan_ms = _optional_float(event.get("lifespan_ms"))
    if timestamp_ms is None or lifespan_ms is None:
        return None
    return timestamp_ms + lifespan_ms


def _mapping(value: object) -> dict:
    return dict(value) if isinstance(value, Mapping) else {}


def _sequence(value: object) -> list:
    return list(value) if isinstance(value, list | tuple) else []


def _float_list(value: object, *, limit: int | None = None) -> list[float]:
    items = _sequence(value)
    if limit is not None:
        items = items[:limit]
    values = []
    for item in items:
        try:
            values.append(float(item))  # type: ignore[arg-type]
        except (TypeError, ValueError):
            values.append(0.0)
    return values


def _optional_str(value: object) -> str | None:
    if value is None or value == "":
        return None
    return str(value)


def _optional_int(value: object) -> int | None:
    try:
        return None if value is None or value == "" else int(float(value))  # type: ignore[arg-type]
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

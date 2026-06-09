"""Dependency-free FleetRMW data-plane frame codec.

The current sidecar runtime still emits padded JSON events for the Docker T3
ROS 2 bridge.  This module defines the cleaner frame shape a future
``rmw_fleetrmw`` data plane can encode over UDP, QUIC, Zenoh, WebRTC, or shared
memory without depending on DDS callback metadata.
"""

from __future__ import annotations

import hashlib
import json
from typing import Mapping


DATA_FRAME_SCHEMA_VERSION = "fleetrmw.data_frame.v1"
DATA_FRAME_ID_VERSION = "fleetrmw.data_frame_id.v1"
DATA_FRAME_MAGIC = b"FRMW1\n"
SIDECAR_TRACE_SCHEMA_VERSION = "fleetrmw.sidecar.trace.v1"


def data_frame_from_sidecar_event(event: Mapping[str, object]) -> dict[str, object]:
    """Build a FleetRMW data-plane frame from a sidecar packet event."""

    frame = {
        "schema_version": DATA_FRAME_SCHEMA_VERSION,
        "kind": "sidecar_packet_frame",
        "frame_id": "",
        "event_id": _optional_int(event.get("event_id")),
        "contract": {
            "contract_id": _optional_str(event.get("contract_id")),
            "source_sample_id": _optional_str(event.get("source_sample_id")),
            "policy": _optional_str(event.get("policy")),
            "scenario": _optional_str(event.get("scenario")),
        },
        "route": {
            "src": _optional_str(event.get("src")),
            "dst": _optional_str(event.get("dst")),
            "robot_id": _optional_str(event.get("robot_id")),
            "flow_id": _optional_str(event.get("flow_id")),
            "flow_class": _optional_str(event.get("flow_class")),
            "topic": _optional_str(event.get("topic")),
            "source_msg_type": _optional_str(event.get("source_msg_type")),
        },
        "delivery": {
            "action": _optional_str(event.get("action")),
            "wire_mode": _optional_str(event.get("wire_mode")),
            "reliability": _optional_str(event.get("reliability")),
            "qos_reliability": _optional_str(event.get("qos_reliability")),
            "deadline_ms": _optional_float(event.get("deadline_ms")),
            "source_deadline_ms": _optional_float(event.get("source_deadline_ms")),
            "lifespan_ms": _optional_float(event.get("lifespan_ms")),
            "source_lifespan_ms": _optional_float(event.get("source_lifespan_ms")),
            "liveliness_lease_ms": _optional_float(event.get("liveliness_lease_ms")),
            "ack_recovery_horizon_ms": _optional_float(event.get("ack_recovery_horizon_ms")),
            "bytes": _optional_int(event.get("bytes")),
            "original_bytes": _optional_int(event.get("original_bytes")),
        },
        "qox": {
            "semantic_utility": _optional_float(event.get("semantic_utility")),
            "task_criticality": _optional_float(event.get("task_criticality")),
            "collision_risk": _optional_float(event.get("collision_risk")),
            "operator_attention": _optional_float(event.get("operator_attention")),
            "coordination_pressure": _optional_float(event.get("coordination_pressure")),
        },
        "timing": {
            "timestamp_ms": _optional_float(event.get("timestamp_ms")),
            "tick": _optional_int(event.get("tick")),
            "age_ms": _optional_float(event.get("age_ms")),
            "predicted_slack_ms": _optional_float(event.get("predicted_slack_ms")),
            "send_monotonic_ns": _optional_int(event.get("send_monotonic_ns")),
        },
    }
    sample_envelope = _mapping(event.get("sample_envelope"))
    if sample_envelope:
        frame["sample_envelope"] = sample_envelope
    source_metadata = _mapping(event.get("source_metadata"))
    if source_metadata:
        frame["source_metadata"] = source_metadata
    semantic_payload = _mapping(event.get("semantic_payload"))
    if semantic_payload:
        frame["semantic_payload"] = semantic_payload
    fleet_optimizer = _mapping(event.get("fleet_optimizer"))
    if fleet_optimizer:
        frame["fleet_optimizer"] = fleet_optimizer
    frame["frame_id"] = frame_id_for_payload(frame)
    return _strip_none(frame)


def sidecar_event_from_data_frame(frame: Mapping[str, object]) -> dict[str, object]:
    """Reconstruct the sidecar event view used by the current egress router."""

    contract = _mapping(frame.get("contract"))
    route = _mapping(frame.get("route"))
    delivery = _mapping(frame.get("delivery"))
    timing = _mapping(frame.get("timing"))
    qox = _mapping(frame.get("qox"))
    source_metadata = _mapping(frame.get("source_metadata"))
    sample_envelope = _mapping(frame.get("sample_envelope"))
    semantic_payload = _mapping(frame.get("semantic_payload"))
    fleet_optimizer = _mapping(frame.get("fleet_optimizer"))
    reliability = _optional_str(delivery.get("reliability")) or "best_effort"
    event = {
        "schema_version": SIDECAR_TRACE_SCHEMA_VERSION,
        "event_type": "packet",
        "scenario": _optional_str(contract.get("scenario")) or "",
        "policy": _optional_str(contract.get("policy")) or "",
        **({"contract_id": contract["contract_id"]} if contract.get("contract_id") else {}),
        **({"source_sample_id": contract["source_sample_id"]} if contract.get("source_sample_id") else {}),
        "event_id": _optional_int(frame.get("event_id")),
        "timestamp_ms": _optional_float(timing.get("timestamp_ms")) or 0.0,
        "tick": _optional_int(timing.get("tick")) or 0,
        "flow_id": _optional_str(route.get("flow_id")) or "",
        "flow_class": _optional_str(route.get("flow_class")) or "",
        "topic": _optional_str(route.get("topic")) or "",
        "source_msg_type": _optional_str(route.get("source_msg_type")) or "",
        "robot_id": _optional_str(route.get("robot_id")) or "",
        "src": _optional_str(route.get("src")) or "",
        "dst": _optional_str(route.get("dst")) or "",
        "action": _optional_str(delivery.get("action")) or "send",
        "bytes": _optional_int(delivery.get("bytes")) or 0,
        "original_bytes": _optional_int(delivery.get("original_bytes")) or 0,
        "degraded": _optional_str(delivery.get("wire_mode")) not in {"", "native", None},
        "deadline_ms": _optional_float(delivery.get("deadline_ms")) or 1.0,
        **({"source_deadline_ms": delivery["source_deadline_ms"]} if delivery.get("source_deadline_ms") is not None else {}),
        "lifespan_ms": _optional_float(delivery.get("lifespan_ms")) or 1.0,
        **({"source_lifespan_ms": delivery["source_lifespan_ms"]} if delivery.get("source_lifespan_ms") is not None else {}),
        **({"liveliness_lease_ms": delivery["liveliness_lease_ms"]} if delivery.get("liveliness_lease_ms") is not None else {}),
        **({"ack_recovery_horizon_ms": delivery["ack_recovery_horizon_ms"]} if delivery.get("ack_recovery_horizon_ms") is not None else {}),
        "qos_reliability": _optional_str(delivery.get("qos_reliability")) or reliability,
        "reliability": reliability,
        "wire_mode": _optional_str(delivery.get("wire_mode")) or "native",
        "predicted_slack_ms": _optional_float(timing.get("predicted_slack_ms")) or 0.0,
        "semantic_utility": _optional_float(qox.get("semantic_utility")) or 0.0,
        **({"send_monotonic_ns": timing["send_monotonic_ns"]} if timing.get("send_monotonic_ns") is not None else {}),
        **({"age_ms": timing["age_ms"]} if timing.get("age_ms") is not None else {}),
        **({"task_criticality": qox["task_criticality"]} if qox.get("task_criticality") is not None else {}),
        **({"collision_risk": qox["collision_risk"]} if qox.get("collision_risk") is not None else {}),
        **({"operator_attention": qox["operator_attention"]} if qox.get("operator_attention") is not None else {}),
        **({"coordination_pressure": qox["coordination_pressure"]} if qox.get("coordination_pressure") is not None else {}),
        **({"source_metadata": source_metadata} if source_metadata else {}),
        **({"sample_envelope": sample_envelope} if sample_envelope else {}),
        **({"semantic_payload": semantic_payload} if semantic_payload else {}),
        **({"fleet_optimizer": fleet_optimizer} if fleet_optimizer else {}),
        "data_frame_id": _optional_str(frame.get("frame_id")) or "",
    }
    return event


def frame_id_for_payload(frame: Mapping[str, object]) -> str:
    """Build a stable frame ID from routing, contract, and timing fields."""

    payload = {
        "schema_version": DATA_FRAME_ID_VERSION,
        "contract": frame.get("contract"),
        "route": frame.get("route"),
        "timing": frame.get("timing"),
        "sample_envelope": frame.get("sample_envelope"),
    }
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")
    return f"ffrm1-{hashlib.sha256(encoded).hexdigest()[:32]}"


def encode_data_frame(frame: Mapping[str, object], *, target_size: int | None = None) -> bytes:
    """Encode a data frame with a small magic prefix and optional padding."""

    body = DATA_FRAME_MAGIC + json.dumps(frame, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")
    if target_size is None or len(body) >= target_size:
        return body
    return body + b" " * (target_size - len(body))


def decode_data_frame(data: bytes, *, validate_schema: bool = True) -> dict[str, object] | None:
    """Decode a FleetRMW data frame, returning ``None`` for non-frame bytes."""

    raw = data.rstrip(b" ")
    if not raw.startswith(DATA_FRAME_MAGIC):
        return None
    try:
        payload = json.loads(raw[len(DATA_FRAME_MAGIC) :].decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return None
    if not isinstance(payload, dict):
        return None
    if validate_schema and payload.get("schema_version") != DATA_FRAME_SCHEMA_VERSION:
        return None
    return payload


def _strip_none(value: object) -> object:
    if isinstance(value, Mapping):
        return {
            str(key): stripped
            for key, item in value.items()
            if (stripped := _strip_none(item)) is not None
        }
    if isinstance(value, list | tuple):
        stripped_items = [_strip_none(item) for item in value]
        return [item for item in stripped_items if item is not None]
    return value


def _mapping(value: object) -> dict[str, object]:
    return dict(value) if isinstance(value, Mapping) else {}


def _optional_str(value: object) -> str | None:
    if value is None or value == "":
        return None
    return str(value)


def _optional_int(value: object) -> int | None:
    try:
        return None if value is None or value == "" else int(float(value))  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None


def _optional_float(value: object) -> float | None:
    try:
        return None if value is None or value == "" else float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None

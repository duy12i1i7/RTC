"""Adapters between projection-quality payloads and ROS interface messages."""

from __future__ import annotations

import math
from typing import Mapping


FLEETRMW_PROJECTION_QUALITY_MSG_TYPE = "fleetrmw_interfaces/msg/ProjectionQuality"
FLEETRMW_QUALIFIED_ODOMETRY_MSG_TYPE = "fleetrmw_interfaces/msg/QualifiedOdometry"
FLEETRMW_QUALIFIED_LASER_SCAN_MSG_TYPE = "fleetrmw_interfaces/msg/QualifiedLaserScan"
UNKNOWN_FLOAT = math.nan
UNKNOWN_INT = -1


def projection_quality_message_from_payload(message_cls, payload: Mapping[str, object]):
    message = message_cls()
    assign_projection_quality_message(message, payload)
    return message


def assign_projection_quality_message(message: object, payload: Mapping[str, object]) -> None:
    identity = message.identity
    event_id = _optional_int(payload.get("event_id"))
    identity.schema_version = str(payload.get("schema_version", ""))
    if hasattr(identity, "contract_id"):
        identity.contract_id = str(payload.get("contract_id") or "")
    if hasattr(identity, "source_sample_id"):
        identity.source_sample_id = str(payload.get("source_sample_id") or "")
    identity.has_event_id = event_id is not None
    identity.event_id = int(event_id or 0)
    identity.robot_id = str(payload.get("robot_id") or "")
    identity.flow_id = str(payload.get("flow_id") or "")
    identity.source_topic = str(payload.get("source_topic") or "")
    identity.projection_kind = str(payload.get("projection_kind") or "")
    identity.projection_topic = str(payload.get("projection_topic") or "")
    identity.projection_msg_type = str(payload.get("projection_msg_type") or "")
    identity.projection_signature_version = str(payload.get("projection_signature_version") or "")
    identity.projection_signature_algorithm = str(payload.get("projection_signature_algorithm") or "")
    identity.projection_signature = str(payload.get("projection_signature") or "")

    message.schema_version = str(payload.get("schema_version") or "")
    message.kind = str(payload.get("kind") or "")
    message.source_msg_type = str(payload.get("source_msg_type") or "")
    message.action = str(payload.get("action") or "")
    message.wire_mode = str(payload.get("wire_mode") or "")
    message.valid_until_timestamp_ms = _float_or_unknown(payload.get("valid_until_timestamp_ms"))
    message.deadline_ms = _float_or_unknown(payload.get("deadline_ms"))
    message.lifespan_ms = _float_or_unknown(payload.get("lifespan_ms"))
    message.age_ms = _float_or_unknown(payload.get("age_ms"))
    message.semantic_utility = _float_or_unknown(payload.get("semantic_utility"))
    message.task_criticality = _float_or_unknown(payload.get("task_criticality"))
    message.collision_risk = _float_or_unknown(payload.get("collision_risk"))
    message.operator_attention = _float_or_unknown(payload.get("operator_attention"))
    message.coordination_pressure = _float_or_unknown(payload.get("coordination_pressure"))
    message.raw_serialized_sample_preserved = _bool(payload.get("raw_serialized_sample_preserved"), default=False)
    message.reconstruction = str(payload.get("reconstruction") or "")
    message.fidelity_class = str(payload.get("fidelity_class") or "")
    message.lossy = _bool(payload.get("lossy"), default=True)
    reasons = payload.get("degradation_reasons", [])
    message.degradation_reasons = [str(item) for item in reasons] if isinstance(reasons, list | tuple) else []
    message.source_sample_count = _int_or_unknown(payload.get("source_sample_count"))
    message.projected_sample_count = _int_or_unknown(payload.get("projected_sample_count"))
    message.downsample_stride = _int_or_unknown(payload.get("downsample_stride"))
    message.projection_payload_embedded = _bool(payload.get("projection_payload_embedded"), default=False)


def projection_quality_payload_from_message(message: object) -> dict[str, object]:
    identity = message.identity
    event_id = int(identity.event_id) if bool(identity.has_event_id) else None
    return {
        "schema_version": str(message.schema_version),
        "kind": str(message.kind),
        "contract_id": str(getattr(identity, "contract_id", "")),
        "source_sample_id": str(getattr(identity, "source_sample_id", "")),
        "event_id": event_id,
        "robot_id": str(identity.robot_id),
        "flow_id": str(identity.flow_id),
        "source_topic": str(identity.source_topic),
        "source_msg_type": str(message.source_msg_type),
        "projection_kind": str(identity.projection_kind),
        "projection_topic": str(identity.projection_topic),
        "projection_msg_type": str(identity.projection_msg_type),
        "action": str(message.action),
        "wire_mode": str(message.wire_mode),
        "valid_until_timestamp_ms": _none_if_unknown_float(message.valid_until_timestamp_ms),
        "deadline_ms": _none_if_unknown_float(message.deadline_ms),
        "lifespan_ms": _none_if_unknown_float(message.lifespan_ms),
        "age_ms": _none_if_unknown_float(message.age_ms),
        "semantic_utility": _none_if_unknown_float(message.semantic_utility),
        "task_criticality": _none_if_unknown_float(message.task_criticality),
        "collision_risk": _none_if_unknown_float(message.collision_risk),
        "operator_attention": _none_if_unknown_float(message.operator_attention),
        "coordination_pressure": _none_if_unknown_float(message.coordination_pressure),
        "raw_serialized_sample_preserved": bool(message.raw_serialized_sample_preserved),
        "reconstruction": str(message.reconstruction),
        "fidelity_class": str(message.fidelity_class),
        "lossy": bool(message.lossy),
        "degradation_reasons": [str(item) for item in message.degradation_reasons],
        "source_sample_count": _none_if_unknown_int(message.source_sample_count),
        "projected_sample_count": _none_if_unknown_int(message.projected_sample_count),
        "downsample_stride": _none_if_unknown_int(message.downsample_stride),
        "projection_signature_version": str(identity.projection_signature_version),
        "projection_signature_algorithm": str(identity.projection_signature_algorithm),
        "projection_signature": str(identity.projection_signature),
        "projection_payload_embedded": bool(message.projection_payload_embedded),
    }


def _float_or_unknown(value: object) -> float:
    try:
        return UNKNOWN_FLOAT if value is None else float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return UNKNOWN_FLOAT


def _int_or_unknown(value: object) -> int:
    try:
        return UNKNOWN_INT if value is None else int(float(value))  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return UNKNOWN_INT


def _none_if_unknown_float(value: object) -> float | None:
    try:
        numeric = float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None
    return None if math.isnan(numeric) else numeric


def _none_if_unknown_int(value: object) -> int | None:
    try:
        numeric = int(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None
    return None if numeric == UNKNOWN_INT else numeric


def _optional_int(value: object) -> int | None:
    try:
        return None if value is None else int(float(value))  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None


def _bool(value: object, *, default: bool) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    return str(value).lower() in {"1", "true", "yes", "on"}

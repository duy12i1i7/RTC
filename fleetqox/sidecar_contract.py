"""FleetRMW sidecar/RMW-shim decision trace contract.

The contract is intentionally transport-neutral. A future ROS 2 sidecar or RMW
shim can emit these events before handing bytes to UDP/QUIC/TCP/Zenoh-like data
planes. Simulators and replay tools can then evaluate the same decisions.
"""

from __future__ import annotations

from typing import Mapping


SIDECAR_TRACE_SCHEMA_VERSION = "fleetrmw.sidecar.trace.v1"

ADMITTED_ACTIONS = frozenset(
    {
        "send",
        "send_degraded",
        "send_compacted",
        "send_intent",
        "send_supervisory_intent",
    }
)
NON_ADMITTED_ACTIONS = frozenset({"defer", "drop"})
VALID_ACTIONS = ADMITTED_ACTIONS | NON_ADMITTED_ACTIONS

VALID_RELIABILITY = frozenset({"reliable", "best_effort", "best_effort_fresh"})
VALID_WIRE_MODES = frozenset(
    {
        "native",
        "semantic_delta",
        "degraded",
        "control_intent",
        "supervisory_intent",
        "",
    }
)

REQUIRED_EVENT_FIELDS = (
    "schema_version",
    "event_type",
    "scenario",
    "policy",
    "timestamp_ms",
    "flow_id",
    "flow_class",
    "topic",
    "robot_id",
    "src",
    "dst",
    "action",
    "bytes",
    "original_bytes",
    "deadline_ms",
    "lifespan_ms",
    "qos_reliability",
    "reliability",
    "wire_mode",
    "predicted_slack_ms",
    "semantic_utility",
)


def is_admitted_action(action: object) -> bool:
    return str(action) in ADMITTED_ACTIONS


def event_errors(event: Mapping[str, object]) -> list[str]:
    errors: list[str] = []
    for field in REQUIRED_EVENT_FIELDS:
        if field not in event:
            errors.append(f"missing field: {field}")

    schema = event.get("schema_version")
    if schema != SIDECAR_TRACE_SCHEMA_VERSION:
        errors.append(f"unsupported schema_version: {schema}")

    event_type = event.get("event_type")
    if event_type not in {"packet", "decision"}:
        errors.append(f"invalid event_type: {event_type}")

    action = event.get("action")
    if action not in VALID_ACTIONS:
        errors.append(f"invalid action: {action}")
    if event_type == "packet" and action not in ADMITTED_ACTIONS:
        errors.append(f"packet event has non-admitted action: {action}")
    if event_type == "decision" and action not in NON_ADMITTED_ACTIONS:
        errors.append(f"decision event has admitted action: {action}")

    reliability = event.get("reliability")
    if reliability not in VALID_RELIABILITY:
        errors.append(f"invalid reliability: {reliability}")

    wire_mode = event.get("wire_mode")
    if wire_mode not in VALID_WIRE_MODES:
        errors.append(f"invalid wire_mode: {wire_mode}")

    for field in ("bytes", "original_bytes"):
        value = _float_or_none(event.get(field))
        if value is None or value < 0:
            errors.append(f"{field} must be non-negative")
    for field in ("deadline_ms", "lifespan_ms"):
        value = _float_or_none(event.get(field))
        if value is None or value <= 0:
            errors.append(f"{field} must be positive")
    return errors


def validate_event(event: Mapping[str, object]) -> None:
    errors = event_errors(event)
    if errors:
        raise ValueError("; ".join(errors))


def _float_or_none(value: object) -> float | None:
    try:
        return float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None

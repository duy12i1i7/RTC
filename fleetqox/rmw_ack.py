"""FleetRMW source-sequence ACK/NACK primitives.

This module is dependency-free on purpose.  It models the feedback payload a
future ``rmw_fleetqox_cpp`` boundary should produce before the current Python
sidecar bridge is replaced.
"""

from __future__ import annotations

from dataclasses import dataclass, field
import hashlib
import json
from typing import Mapping


ACK_NACK_SCHEMA_VERSION = "fleetrmw.ack_nack.v1"
ACK_NACK_ID_VERSION = "fleetrmw.ack_nack_id.v1"


@dataclass
class RmwSourceSequenceState:
    highest_contiguous_sequence: int | None = None
    highest_observed_sequence: int | None = None
    observed_sequences: set[int] = field(default_factory=set)


class RmwAckNackTracker:
    """Track per-stream source sequence gaps and emit ACK/NACK feedback records."""

    def __init__(self, *, window_size: int = 256) -> None:
        self.window_size = max(1, int(window_size))
        self._streams: dict[tuple[str, ...], RmwSourceSequenceState] = {}

    def observe(self, record: Mapping[str, object]) -> dict[str, object] | None:
        stream = source_stream_key(record)
        sequence = source_sequence_number(record)
        if stream is None or sequence is None:
            return None
        state = self._streams.setdefault(stream, RmwSourceSequenceState())
        duplicate = sequence in state.observed_sequences
        previous_highest = state.highest_observed_sequence
        out_of_order = previous_highest is not None and sequence < previous_highest
        state.observed_sequences.add(sequence)
        state.highest_observed_sequence = (
            sequence
            if previous_highest is None
            else max(previous_highest, sequence)
        )
        self._advance_contiguous(state)
        self._trim_observed(state)
        return ack_nack_feedback_record(
            record,
            stream=stream,
            missing_sequence_ranges=missing_sequence_ranges(state),
            highest_contiguous_sequence=state.highest_contiguous_sequence,
            highest_observed_sequence=state.highest_observed_sequence,
            duplicate=duplicate,
            out_of_order=out_of_order,
        )

    def _advance_contiguous(self, state: RmwSourceSequenceState) -> None:
        if not state.observed_sequences:
            return
        if state.highest_contiguous_sequence is None:
            state.highest_contiguous_sequence = 0
        assert state.highest_contiguous_sequence is not None
        while state.highest_contiguous_sequence + 1 in state.observed_sequences:
            state.highest_contiguous_sequence += 1

    def _trim_observed(self, state: RmwSourceSequenceState) -> None:
        if state.highest_observed_sequence is None:
            return
        floor = state.highest_observed_sequence - self.window_size
        state.observed_sequences = {
            sequence
            for sequence in state.observed_sequences
            if sequence >= floor
        }


def ack_nack_feedback_record(
    record: Mapping[str, object],
    *,
    stream: tuple[str, ...] | None = None,
    missing_sequence_ranges: list[tuple[int, int]] | None = None,
    highest_contiguous_sequence: int | None = None,
    highest_observed_sequence: int | None = None,
    duplicate: bool = False,
    out_of_order: bool = False,
) -> dict[str, object]:
    stream = stream or source_stream_key(record) or ("unknown",)
    sequence = source_sequence_number(record)
    payload = {
        "schema_version": ACK_NACK_SCHEMA_VERSION,
        "kind": "source_sequence_ack_nack",
        "ack_nack_id": "",
        "source": str(record.get("source", "rmw_boundary")),
        "robot_id": _optional_str(record.get("robot_id")) or "",
        "flow_id": _optional_str(record.get("flow_id")) or "",
        "source_topic": _optional_str(record.get("source_topic") or record.get("topic")) or "",
        "stream_key": list(stream),
        "ack": {
            "event_id": _optional_int(record.get("event_id")),
            "source_sample_id": _optional_str(record.get("source_sample_id")),
            "source_sequence_number": sequence,
            "source_timestamp_ns": _first_optional_int(
                record.get("source_timestamp_ns"),
                _mapping_value(record.get("source_metadata"), "source_timestamp_ns"),
                _mapping_value(record.get("sample_envelope"), "source_timestamp_ns"),
            ),
            "source_received_timestamp_ns": _first_optional_int(
                record.get("source_received_timestamp_ns"),
                record.get("received_timestamp_ns"),
                _mapping_value(record.get("source_metadata"), "received_timestamp_ns"),
                _mapping_value(record.get("sample_envelope"), "received_timestamp_ns"),
            ),
        },
        "nack": {
            "missing_sequence_ranges": [
                [start, end]
                for start, end in (missing_sequence_ranges or [])
            ],
        },
        "state": {
            "highest_contiguous_sequence": highest_contiguous_sequence,
            "highest_observed_sequence": highest_observed_sequence,
            "duplicate": bool(duplicate),
            "out_of_order": bool(out_of_order),
        },
    }
    payload = _strip_none(payload)
    payload["ack_nack_id"] = ack_nack_id_for_payload(payload)
    return payload


def source_stream_key(record: Mapping[str, object]) -> tuple[str, ...] | None:
    robot_id = _optional_str(record.get("robot_id"))
    topic = _optional_str(
        record.get("source_topic")
        or record.get("topic")
        or _mapping_value(record.get("sample_envelope"), "topic")
        or _mapping_value(record.get("semantic_payload"), "source_topic")
        or record.get("flow_id")
    )
    if not robot_id or not topic:
        return None
    publisher_id = _optional_str(
        record.get("publisher_id")
        or _mapping_value(record.get("source_metadata"), "publisher_id")
        or _mapping_value(record.get("sample_envelope"), "publisher_id")
    )
    if publisher_id:
        return ("source_stream", robot_id, topic, publisher_id)
    return ("source_stream", robot_id, topic)


def source_sequence_number(record: Mapping[str, object]) -> int | None:
    return _first_optional_int(
        record.get("source_sequence_number"),
        _mapping_value(record.get("source_metadata"), "source_sequence_number"),
        _mapping_value(record.get("source_metadata"), "sequence_number"),
        _mapping_value(record.get("sample_envelope"), "source_sequence_number"),
        _mapping_value(record.get("semantic_payload"), "source_sequence_number"),
        _mapping_value(_mapping_value(record.get("semantic_payload"), "source_metadata"), "sequence_number"),
    )


def missing_sequence_ranges(state: RmwSourceSequenceState) -> list[tuple[int, int]]:
    if (
        state.highest_contiguous_sequence is None
        or state.highest_observed_sequence is None
        or state.highest_observed_sequence <= state.highest_contiguous_sequence
    ):
        return []
    ranges: list[tuple[int, int]] = []
    start: int | None = None
    previous: int | None = None
    for sequence in range(
        state.highest_contiguous_sequence + 1,
        state.highest_observed_sequence + 1,
    ):
        if sequence in state.observed_sequences:
            if start is not None and previous is not None:
                ranges.append((start, previous))
            start = None
            previous = None
            continue
        if start is None:
            start = sequence
        previous = sequence
    if start is not None and previous is not None:
        ranges.append((start, previous))
    return ranges


def ack_nack_id_for_payload(payload: Mapping[str, object]) -> str:
    body = {
        "schema_version": ACK_NACK_ID_VERSION,
        "stream_key": payload.get("stream_key"),
        "ack": payload.get("ack"),
        "nack": payload.get("nack"),
        "state": payload.get("state"),
    }
    encoded = json.dumps(body, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")
    return f"fack1-{hashlib.sha256(encoded).hexdigest()[:32]}"


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


def _mapping_value(value: object, key: str) -> object:
    if not isinstance(value, Mapping):
        return None
    return value.get(key)


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

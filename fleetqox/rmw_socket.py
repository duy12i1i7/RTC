"""Socket-backed FleetRMW publish/take boundary.

This module is intentionally small and dependency-free.  It wraps the in-memory
``FleetRmwBoundary`` with UDP datagrams so the data-frame and ACK/NACK contract
can be exercised over a real transport before implementing ``rmw_fleetqox_cpp``.
"""

from __future__ import annotations

from dataclasses import dataclass
import json
import socket
import time
from types import TracebackType
from typing import Mapping

from .rmw_ack import ACK_NACK_SCHEMA_VERSION
from .rmw_ack import source_sequence_number, source_stream_key
from .rmw_boundary import FleetRmwBoundary
from .ros2_shim import Ros2Sample


RMW_SOCKET_PUBLISH_SCHEMA_VERSION = "fleetrmw.rmw_socket_publish.v1"
RMW_SOCKET_TAKE_SCHEMA_VERSION = "fleetrmw.rmw_socket_take.v1"
RMW_SOCKET_FEEDBACK_SCHEMA_VERSION = "fleetrmw.rmw_socket_feedback.v1"
RMW_SOCKET_RETRANSMIT_SCHEMA_VERSION = "fleetrmw.rmw_socket_retransmit.v1"
DEFAULT_DATAGRAM_BYTES = 65_535


@dataclass(frozen=True)
class FleetRmwSocketConfig:
    host: str = "127.0.0.1"
    port: int = 0
    timeout_s: float = 0.25
    max_datagram_bytes: int = DEFAULT_DATAGRAM_BYTES
    recovery_horizon_ms: float = 2000.0
    history_per_stream: int = 256


@dataclass
class _SentFrame:
    payload: bytes
    destination: tuple[str, int]
    sent_monotonic_ms: float


class FleetRmwSocketTalker:
    """Publish FleetRMW data frames and receive ACK/NACK feedback over UDP."""

    def __init__(
        self,
        config: FleetRmwSocketConfig | None = None,
        *,
        boundary: FleetRmwBoundary | None = None,
    ) -> None:
        self.config = config or FleetRmwSocketConfig()
        self.boundary = boundary or FleetRmwBoundary()
        self._socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self._socket.bind((self.config.host, self.config.port))
        self._socket.settimeout(self.config.timeout_s)
        self._sent_frames: dict[tuple[tuple[str, ...], int], _SentFrame] = {}

    @property
    def address(self) -> tuple[str, int]:
        host, port = self._socket.getsockname()
        return str(host), int(port)

    def publish(
        self,
        sample: Ros2Sample | Mapping[str, object],
        *,
        timestamp_ms: float,
        tick: int,
        destination: tuple[str, int],
    ) -> dict[str, object]:
        published = self.boundary.publish(sample, timestamp_ms=timestamp_ms, tick=tick)
        encoded = published["encoded"]
        if not isinstance(encoded, bytes):
            raise TypeError("FleetRmwBoundary.publish returned a non-bytes frame")
        sent_bytes = self._socket.sendto(encoded, destination)
        self._remember_sent_frame(published, payload=encoded, destination=destination)
        return {
            "schema_version": RMW_SOCKET_PUBLISH_SCHEMA_VERSION,
            "status": "sent",
            "source_address": list(self.address),
            "destination": [destination[0], int(destination[1])],
            "sent_bytes": sent_bytes,
            "published": published,
        }

    def retransmit_from_feedback(
        self,
        feedback: Mapping[str, object],
        *,
        destination: tuple[str, int] | None = None,
        max_frames: int | None = None,
    ) -> dict[str, object]:
        ack_nack = _ack_nack_payload(feedback)
        if ack_nack is None:
            return {
                "schema_version": RMW_SOCKET_RETRANSMIT_SCHEMA_VERSION,
                "status": "ignored",
                "reason": "not_ack_nack_feedback",
            }
        self._prune_sent_frames()
        stream = tuple(str(part) for part in ack_nack.get("stream_key", []))
        requested = _missing_sequences(ack_nack)
        retransmitted: list[int] = []
        missing: list[int] = []
        limit = len(requested) if max_frames is None else max(0, int(max_frames))
        for sequence in requested:
            if len(retransmitted) >= limit:
                break
            frame = self._sent_frames.get((stream, sequence))
            if frame is None:
                missing.append(sequence)
                continue
            target = destination or frame.destination
            self._socket.sendto(frame.payload, target)
            frame.sent_monotonic_ms = _monotonic_ms()
            retransmitted.append(sequence)
        return {
            "schema_version": RMW_SOCKET_RETRANSMIT_SCHEMA_VERSION,
            "status": "retransmitted" if retransmitted else "no_match",
            "stream_key": list(stream),
            "requested_sequences": requested,
            "retransmitted_sequences": retransmitted,
            "missing_sequences": missing,
        }

    def receive_feedback(self, *, timeout_s: float | None = None) -> dict[str, object] | None:
        previous_timeout = self._socket.gettimeout()
        if timeout_s is not None:
            self._socket.settimeout(timeout_s)
        try:
            payload, remote = self._socket.recvfrom(self.config.max_datagram_bytes)
        except socket.timeout:
            return None
        finally:
            if timeout_s is not None:
                self._socket.settimeout(previous_timeout)
        feedback = decode_ack_nack_feedback(payload)
        if feedback is None:
            return None
        return {
            "schema_version": RMW_SOCKET_FEEDBACK_SCHEMA_VERSION,
            "remote_address": [str(remote[0]), int(remote[1])],
            "feedback": feedback,
        }

    def close(self) -> None:
        self._socket.close()

    def _remember_sent_frame(
        self,
        published: Mapping[str, object],
        *,
        payload: bytes,
        destination: tuple[str, int],
    ) -> None:
        event = published.get("event")
        if not isinstance(event, Mapping):
            return
        stream = source_stream_key(event)
        sequence = source_sequence_number(event)
        if stream is None or sequence is None:
            return
        self._sent_frames[(stream, sequence)] = _SentFrame(
            payload=payload,
            destination=(destination[0], int(destination[1])),
            sent_monotonic_ms=_monotonic_ms(),
        )
        self._prune_sent_frames()

    def _prune_sent_frames(self) -> None:
        now_ms = _monotonic_ms()
        horizon_ms = max(0.0, float(self.config.recovery_horizon_ms))
        expired = [
            key
            for key, frame in self._sent_frames.items()
            if now_ms - frame.sent_monotonic_ms > horizon_ms
        ]
        for key in expired:
            self._sent_frames.pop(key, None)
        per_stream: dict[tuple[str, ...], list[int]] = {}
        for stream, sequence in self._sent_frames:
            per_stream.setdefault(stream, []).append(sequence)
        limit = max(1, int(self.config.history_per_stream))
        for stream, sequences in per_stream.items():
            for sequence in sorted(sequences)[:-limit]:
                self._sent_frames.pop((stream, sequence), None)

    def __enter__(self) -> "FleetRmwSocketTalker":
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        self.close()


class FleetRmwSocketListener:
    """Receive FleetRMW data frames, take them, and reply with ACK/NACK."""

    def __init__(
        self,
        config: FleetRmwSocketConfig | None = None,
        *,
        boundary: FleetRmwBoundary | None = None,
    ) -> None:
        self.config = config or FleetRmwSocketConfig()
        self.boundary = boundary or FleetRmwBoundary()
        self._socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self._socket.bind((self.config.host, self.config.port))
        self._socket.settimeout(self.config.timeout_s)

    @property
    def address(self) -> tuple[str, int]:
        host, port = self._socket.getsockname()
        return str(host), int(port)

    def receive_once(
        self,
        *,
        send_feedback: bool = True,
        timeout_s: float | None = None,
    ) -> dict[str, object] | None:
        previous_timeout = self._socket.gettimeout()
        if timeout_s is not None:
            self._socket.settimeout(timeout_s)
        try:
            payload, remote = self._socket.recvfrom(self.config.max_datagram_bytes)
        except socket.timeout:
            return None
        finally:
            if timeout_s is not None:
                self._socket.settimeout(previous_timeout)
        taken = self.boundary.take(payload)
        feedback = taken.get("ack_nack") if isinstance(taken, Mapping) else None
        feedback_sent = False
        feedback_bytes = 0
        if send_feedback and isinstance(feedback, Mapping):
            encoded_feedback = encode_ack_nack_feedback(feedback)
            feedback_bytes = self._socket.sendto(encoded_feedback, remote)
            feedback_sent = True
        return {
            "schema_version": RMW_SOCKET_TAKE_SCHEMA_VERSION,
            "status": taken.get("status", "unknown") if isinstance(taken, Mapping) else "unknown",
            "local_address": list(self.address),
            "remote_address": [str(remote[0]), int(remote[1])],
            "received_bytes": len(payload),
            "feedback_sent": feedback_sent,
            "feedback_bytes": feedback_bytes,
            "taken": taken,
        }

    def close(self) -> None:
        self._socket.close()

    def __enter__(self) -> "FleetRmwSocketListener":
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        self.close()


def encode_ack_nack_feedback(feedback: Mapping[str, object]) -> bytes:
    return json.dumps(feedback, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")


def decode_ack_nack_feedback(payload: bytes) -> dict[str, object] | None:
    try:
        decoded = json.loads(payload.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return None
    if not isinstance(decoded, dict):
        return None
    if decoded.get("schema_version") != ACK_NACK_SCHEMA_VERSION:
        return None
    return decoded


def _ack_nack_payload(feedback: Mapping[str, object]) -> dict[str, object] | None:
    if feedback.get("schema_version") == ACK_NACK_SCHEMA_VERSION:
        return dict(feedback)
    nested = feedback.get("feedback")
    if isinstance(nested, Mapping) and nested.get("schema_version") == ACK_NACK_SCHEMA_VERSION:
        return dict(nested)
    return None


def _missing_sequences(feedback: Mapping[str, object]) -> list[int]:
    nack = feedback.get("nack")
    if not isinstance(nack, Mapping):
        return []
    sequences: list[int] = []
    for item in nack.get("missing_sequence_ranges", []):
        if not isinstance(item, list | tuple) or len(item) != 2:
            continue
        try:
            start = int(item[0])
            end = int(item[1])
        except (TypeError, ValueError):
            continue
        if end < start:
            continue
        sequences.extend(range(start, end + 1))
    return sequences


def _monotonic_ms() -> float:
    return time.monotonic_ns() / 1_000_000.0

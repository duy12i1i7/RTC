"""Submit live ROS task outcomes over one authenticated HTTP/3 session.

The aioquic imports are intentionally lazy.  Most FleetQoX unit tests run
without aioquic installed, while the Docker integration image pins the exact
runtime used by the gateway.
"""

from __future__ import annotations

import asyncio
import json
import math
import os
from pathlib import Path
import ssl
import time
from typing import Any, Mapping, Sequence

from .quic_gateway_state import (
    APPLICATION_OUTCOME_API_PATH,
    DATA_FRAME_MAGIC,
    GATEWAY_API_PATH,
)
from .task_outcome import (
    APPLICATION_OUTCOME_SCHEMA_VERSION,
    TASK_KINDS,
    TERMINAL_STATUSES,
)


CLIENT_SCHEMA_VERSION = "fleetrmw.live_task_outcome_client.v1"
DATA_FRAME_SCHEMA_VERSION = "fleetrmw.data_frame.v1"


def task_seed_frame(outcome: Mapping[str, Any]) -> bytes:
    """Create the admitted data-frame identity referenced by one outcome."""

    normalized = _validate_outcome(outcome)
    payload = json.dumps(
        {
            "task_kind": normalized["task_kind"],
            "source_sequence_number": normalized["source_sequence_number"],
        },
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    document = {
        "schema_version": DATA_FRAME_SCHEMA_VERSION,
        "kind": "sidecar_packet_frame",
        "domain_id": normalized["domain_id"],
        "route": {
            "robot_id": "nav2-rmf-workload",
            "topic": normalized["topic"],
            "flow_class": "control",
        },
        "sample_envelope": {
            "robot_id": "nav2-rmf-workload",
            "topic": normalized["topic"],
            "publisher_id": normalized["publisher_id"],
            "source_sequence_number": normalized["source_sequence_number"],
            "source_timestamp_ns": time.time_ns(),
        },
        "delivery": {"deadline_ms": normalized["deadline_ms"]},
        "qox": {"task_criticality": 1.0},
        "serialized_payload": {
            "encoding": "hex",
            "size": len(payload),
            "data": payload.hex(),
        },
    }
    return DATA_FRAME_MAGIC + json.dumps(
        document,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")


def submit_live_task_outcomes(
    *,
    host: str,
    port: int,
    ca_file: str | Path,
    client_certificate: str | Path,
    client_private_key: str | Path,
    outcomes: Sequence[Mapping[str, Any]],
    timeout_s: float = 10.0,
    qlog_dir: str | Path | None = None,
) -> dict[str, Any]:
    """Synchronously seed and report outcomes on one mTLS/H3 connection."""

    if not isinstance(host, str) or not host:
        raise ValueError("task outcome gateway host is required")
    if not isinstance(port, int) or isinstance(port, bool) or not 1 <= port <= 65535:
        raise ValueError("task outcome gateway port is invalid")
    if (
        not isinstance(timeout_s, (int, float))
        or isinstance(timeout_s, bool)
        or float(timeout_s) <= 0.0
    ):
        raise ValueError("task outcome gateway timeout must be positive")
    normalized = [_validate_outcome(row) for row in outcomes]
    if not normalized:
        raise ValueError("at least one task outcome is required")
    identities = {
        (
            row["domain_id"],
            row["topic"],
            row["publisher_id"],
            row["source_sequence_number"],
        )
        for row in normalized
    }
    if len(identities) != len(normalized):
        raise ValueError("task outcome identities must be unique")
    return asyncio.run(
        _submit_live_task_outcomes(
            host=host,
            port=port,
            ca_file=str(ca_file),
            client_certificate=str(client_certificate),
            client_private_key=str(client_private_key),
            outcomes=normalized,
            timeout_s=float(timeout_s),
            qlog_dir=str(qlog_dir) if qlog_dir is not None else None,
        )
    )


async def _submit_live_task_outcomes(
    *,
    host: str,
    port: int,
    ca_file: str,
    client_certificate: str,
    client_private_key: str,
    outcomes: list[dict[str, Any]],
    timeout_s: float,
    qlog_dir: str | None,
) -> dict[str, Any]:
    try:
        from aioquic.asyncio import QuicConnectionProtocol
        from aioquic.asyncio.client import connect
        from aioquic.h3.connection import H3_ALPN, H3Connection
        from aioquic.h3.events import DataReceived, HeadersReceived
        from aioquic.quic.configuration import QuicConfiguration
        from aioquic.quic.events import ConnectionTerminated, ProtocolNegotiated
    except ImportError as exc:
        raise RuntimeError(
            "aioquic is required for live task outcome submission"
        ) from exc

    class TaskOutcomeH3Protocol(QuicConnectionProtocol):
        def __init__(self, *args: Any, **kwargs: Any) -> None:
            super().__init__(*args, **kwargs)
            self.http: Any = None
            self.responses: dict[int, dict[str, Any]] = {}
            self.pending: dict[int, asyncio.Future[dict[str, Any]]] = {}

        def quic_event_received(self, event: Any) -> None:
            if isinstance(event, ProtocolNegotiated) and event.alpn_protocol in H3_ALPN:
                self.http = H3Connection(self._quic)
            if isinstance(event, ConnectionTerminated):
                error = ConnectionError(
                    f"QUIC connection terminated with error {event.error_code}"
                )
                for future in self.pending.values():
                    if not future.done():
                        future.set_exception(error)
            if self.http is None:
                return
            for http_event in self.http.handle_event(event):
                if isinstance(http_event, HeadersReceived):
                    response = self.responses.setdefault(
                        http_event.stream_id,
                        {"status": 0, "headers": {}, "body": bytearray()},
                    )
                    response["headers"].update(
                        {
                            name.decode("ascii"): value.decode(
                                "utf-8", errors="replace"
                            )
                            for name, value in http_event.headers
                        }
                    )
                    raw_status = response["headers"].get(":status", "0")
                    response["status"] = int(raw_status)
                    if http_event.stream_ended:
                        self._complete(http_event.stream_id)
                elif isinstance(http_event, DataReceived):
                    response = self.responses.setdefault(
                        http_event.stream_id,
                        {"status": 0, "headers": {}, "body": bytearray()},
                    )
                    response["body"].extend(http_event.data)
                    if http_event.stream_ended:
                        self._complete(http_event.stream_id)

        def _complete(self, stream_id: int) -> None:
            future = self.pending.pop(stream_id, None)
            response = self.responses.pop(stream_id, None)
            if future is None or future.done() or response is None:
                return
            future.set_result(
                {
                    "stream_id": stream_id,
                    "status": response["status"],
                    "body": bytes(response["body"]).decode(
                        "utf-8", errors="replace"
                    ),
                }
            )

        async def post(self, path: str, body: bytes) -> dict[str, Any]:
            if self.http is None:
                raise RuntimeError("HTTP/3 session was not negotiated")
            stream_id = self._quic.get_next_available_stream_id()
            future: asyncio.Future[dict[str, Any]] = (
                asyncio.get_running_loop().create_future()
            )
            self.pending[stream_id] = future
            self.responses[stream_id] = {
                "status": 0,
                "headers": {},
                "body": bytearray(),
            }
            self.http.send_headers(
                stream_id=stream_id,
                headers=[
                    (b":method", b"POST"),
                    (b":scheme", b"https"),
                    (b":authority", f"{host}:{port}".encode("ascii")),
                    (b":path", path.encode("ascii")),
                    (b"content-type", b"application/octet-stream"),
                    (b"content-length", str(len(body)).encode("ascii")),
                ],
                end_stream=not body,
            )
            if body:
                self.http.send_data(
                    stream_id=stream_id,
                    data=body,
                    end_stream=True,
                )
            self.transmit()
            return await asyncio.wait_for(future, timeout=timeout_s)

    configuration = QuicConfiguration(
        is_client=True,
        alpn_protocols=H3_ALPN,
    )
    configuration.verify_mode = ssl.CERT_REQUIRED
    configuration.load_verify_locations(cafile=ca_file)
    configuration.load_cert_chain(client_certificate, client_private_key)
    if qlog_dir:
        from aioquic.quic.logger import QuicFileLogger

        Path(qlog_dir).mkdir(parents=True, exist_ok=True)
        configuration.quic_logger = QuicFileLogger(qlog_dir)

    started_ns = time.monotonic_ns()
    responses: list[dict[str, Any]] = []
    async with connect(
        host,
        port,
        configuration=configuration,
        create_protocol=TaskOutcomeH3Protocol,
        wait_connected=True,
    ) as protocol:
        if not isinstance(protocol, TaskOutcomeH3Protocol):
            raise RuntimeError("aioquic returned an unexpected client protocol")
        for row in outcomes:
            response = await protocol.post(GATEWAY_API_PATH, task_seed_frame(row))
            responses.append({"kind": "seed_frame", **response})
        for row in outcomes:
            body = json.dumps(
                row,
                sort_keys=True,
                separators=(",", ":"),
                allow_nan=False,
            ).encode("utf-8")
            response = await protocol.post(APPLICATION_OUTCOME_API_PATH, body)
            responses.append({"kind": "application_outcome", **response})

    seed_responses = [row for row in responses if row["kind"] == "seed_frame"]
    outcome_responses = [
        row for row in responses if row["kind"] == "application_outcome"
    ]
    ok = (
        len(seed_responses) == len(outcomes)
        and len(outcome_responses) == len(outcomes)
        and all(row["status"] == 200 for row in responses)
    )
    stream_count = len(responses)
    return {
        "schema_version": CLIENT_SCHEMA_VERSION,
        "status": "ok" if ok else "failed",
        "process_id": os.getpid(),
        "real_quic_v1_h3": True,
        "mutual_tls_required": True,
        "server_certificate_verification_required": True,
        "connections_created": 1,
        "handshakes_completed": 1,
        "streams_opened": stream_count,
        "connection_reuse_count": max(0, stream_count - 1),
        "seed_frames_sent": sum(row["status"] == 200 for row in seed_responses),
        "task_outcomes_submitted": sum(
            row["status"] == 200 for row in outcome_responses
        ),
        "task_outcome_submission_session_reuse_claim": (
            ok and stream_count > 1
        ),
        "elapsed_ms": (time.monotonic_ns() - started_ns) / 1_000_000.0,
        "responses": responses,
        "production_readiness": False,
    }


def _validate_outcome(outcome: Mapping[str, Any]) -> dict[str, Any]:
    if not isinstance(outcome, Mapping):
        raise ValueError("task outcome must be an object")
    document = dict(outcome)
    if document.get("schema_version") != APPLICATION_OUTCOME_SCHEMA_VERSION:
        raise ValueError("unsupported task outcome schema")
    required_strings = ("topic", "publisher_id", "task_kind", "terminal_status")
    if any(
        not isinstance(document.get(key), str) or not document[key]
        for key in required_strings
    ):
        raise ValueError("task outcome string fields are invalid")
    if not document["topic"].startswith("/"):
        raise ValueError("task outcome topic must be absolute")
    if document["task_kind"] not in TASK_KINDS:
        raise ValueError("task outcome kind is invalid")
    if document["terminal_status"] not in TERMINAL_STATUSES:
        raise ValueError("task outcome terminal status is invalid")
    domain_id = document.get("domain_id")
    sequence = document.get("source_sequence_number")
    if (
        not isinstance(domain_id, int)
        or isinstance(domain_id, bool)
        or domain_id < 0
        or not isinstance(sequence, int)
        or isinstance(sequence, bool)
        or sequence <= 0
    ):
        raise ValueError("task outcome identity is invalid")
    for key in ("delivered", "deadline_met", "task_succeeded"):
        if not isinstance(document.get(key), bool):
            raise ValueError("task outcome boolean fields are invalid")
    for key in ("observed_latency_ms", "deadline_ms"):
        value = document.get(key)
        if (
            not isinstance(value, (int, float))
            or isinstance(value, bool)
            or not math.isfinite(float(value))
            or float(value) < 0.0
        ):
            raise ValueError("task outcome timing fields are invalid")
    if float(document["deadline_ms"]) <= 0.0:
        raise ValueError("task outcome deadline must be positive")
    expected_success = (
        document["delivered"] and document["terminal_status"] == "succeeded"
    )
    if document["task_succeeded"] is not expected_success:
        raise ValueError("task outcome task success contradicts terminal status")
    return document

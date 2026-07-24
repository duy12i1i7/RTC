"""Stateful FleetQoX backend for the public-API ngtcp2 QUIC server.

The transport edge and state engine communicate over a local Unix socket with
an intentionally small length-prefixed protocol.  Mutual TLS remains at the
ngtcp2/GnuTLS edge; the verified certificate identity is carried in every
backend request and rechecked against publisher-owned request bodies.
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
import json
import os
from pathlib import Path
import signal
import socket
import struct
import threading
from typing import BinaryIO
from urllib.parse import urlsplit

from .quic_gateway_state import (
    APPLICATION_OUTCOME_API_PATH,
    GATEWAY_API_PATH,
    FleetQoxGatewayState,
    FrameValidationError,
    GatewayAdmissionPolicy,
    GatewayResponse,
    parse_data_frame,
)


SCHEMA_VERSION = "fleetrmw.public_quic_gateway_backend.v1"
REQUEST_MAGIC = b"FQBE1REQ"
RESPONSE_MAGIC = b"FQBE1RES"
REQUEST_HEADER = struct.Struct("!8sIIII")
RESPONSE_HEADER = struct.Struct("!8sIII")
MAX_METHOD_BYTES = 16
MAX_PATH_BYTES = 16_384
MAX_IDENTITY_BYTES = 4096
DEFAULT_MAX_BODY_BYTES = 1_048_576


class BackendProtocolError(ValueError):
    """Raised when the local edge/backend protocol is malformed."""


@dataclass(frozen=True)
class BackendRequest:
    method: str
    path: str
    client_identity: str
    body: bytes


def _read_exact(stream: BinaryIO, length: int) -> bytes:
    chunks = bytearray()
    while len(chunks) < length:
        chunk = stream.read(length - len(chunks))
        if not chunk:
            raise BackendProtocolError("truncated backend message")
        chunks.extend(chunk)
    return bytes(chunks)


def read_backend_request(
    stream: BinaryIO,
    *,
    max_body_bytes: int = DEFAULT_MAX_BODY_BYTES,
) -> BackendRequest:
    header = _read_exact(stream, REQUEST_HEADER.size)
    magic, method_length, path_length, identity_length, body_length = (
        REQUEST_HEADER.unpack(header)
    )
    if magic != REQUEST_MAGIC:
        raise BackendProtocolError("invalid backend request magic")
    if not 0 < method_length <= MAX_METHOD_BYTES:
        raise BackendProtocolError("invalid backend method length")
    if not 0 < path_length <= MAX_PATH_BYTES:
        raise BackendProtocolError("invalid backend path length")
    if identity_length > MAX_IDENTITY_BYTES:
        raise BackendProtocolError("invalid backend identity length")
    if body_length > max_body_bytes:
        raise BackendProtocolError("backend request body too large")
    try:
        method = _read_exact(stream, method_length).decode("ascii")
        path = _read_exact(stream, path_length).decode("utf-8")
        identity = _read_exact(stream, identity_length).decode("utf-8")
    except UnicodeDecodeError as exc:
        raise BackendProtocolError("invalid backend request encoding") from exc
    body = _read_exact(stream, body_length)
    return BackendRequest(
        method=method,
        path=path,
        client_identity=identity,
        body=body,
    )


def encode_backend_request(request: BackendRequest) -> bytes:
    method = request.method.encode("ascii")
    path = request.path.encode("utf-8")
    identity = request.client_identity.encode("utf-8")
    if not 0 < len(method) <= MAX_METHOD_BYTES:
        raise BackendProtocolError("invalid backend method length")
    if not 0 < len(path) <= MAX_PATH_BYTES:
        raise BackendProtocolError("invalid backend path length")
    if len(identity) > MAX_IDENTITY_BYTES:
        raise BackendProtocolError("invalid backend identity length")
    if len(request.body) > 0xFFFFFFFF:
        raise BackendProtocolError("backend request body too large")
    return b"".join(
        (
            REQUEST_HEADER.pack(
                REQUEST_MAGIC,
                len(method),
                len(path),
                len(identity),
                len(request.body),
            ),
            method,
            path,
            identity,
            request.body,
        )
    )


def encode_backend_response(response: GatewayResponse) -> bytes:
    content_type = response.content_type.encode("ascii")
    if len(content_type) > 4096 or len(response.body) > 0xFFFFFFFF:
        raise BackendProtocolError("backend response too large")
    return b"".join(
        (
            RESPONSE_HEADER.pack(
                RESPONSE_MAGIC,
                response.status,
                len(content_type),
                len(response.body),
            ),
            content_type,
            response.body,
        )
    )


def read_backend_response(stream: BinaryIO) -> GatewayResponse:
    header = _read_exact(stream, RESPONSE_HEADER.size)
    magic, status, content_type_length, body_length = RESPONSE_HEADER.unpack(header)
    if magic != RESPONSE_MAGIC:
        raise BackendProtocolError("invalid backend response magic")
    if not 100 <= status <= 599:
        raise BackendProtocolError("invalid backend response status")
    if content_type_length > 4096:
        raise BackendProtocolError("invalid backend content-type length")
    try:
        content_type = _read_exact(stream, content_type_length).decode("ascii")
    except UnicodeDecodeError as exc:
        raise BackendProtocolError("invalid backend response encoding") from exc
    body = _read_exact(stream, body_length)
    return GatewayResponse(
        status=status,
        body=body,
        content_type=content_type,
    )


class PublicQuicGatewayBackend:
    """Identity-aware adapter around the shared FleetQoxGatewayState engine."""

    def __init__(
        self,
        state: FleetQoxGatewayState,
        *,
        require_client_identity: bool = True,
    ) -> None:
        self.state = state
        self.require_client_identity = require_client_identity
        self.identity_rejections = 0
        self.protocol_rejections = 0

    @staticmethod
    def _json_response(status: int, document: dict[str, object]) -> GatewayResponse:
        return GatewayResponse(
            status=status,
            body=json.dumps(
                document, separators=(",", ":"), sort_keys=True
            ).encode("utf-8"),
        )

    def dispatch(self, request: BackendRequest) -> GatewayResponse:
        if self.require_client_identity and not request.client_identity:
            self.identity_rejections += 1
            return self._json_response(401, {"error": "missing_client_identity"})

        path = urlsplit(request.path).path
        if request.method == "POST" and path == GATEWAY_API_PATH:
            try:
                metadata = parse_data_frame(
                    request.body,
                    max_frame_bytes=self.state.max_frame_bytes,
                )
            except FrameValidationError:
                # Let the shared state engine account for invalid frames.
                pass
            else:
                if (
                    request.client_identity
                    and metadata.publisher_id != request.client_identity
                ):
                    self.identity_rejections += 1
                    return self._json_response(
                        403, {"error": "publisher_identity_mismatch"}
                    )

        if request.method == "POST" and path == APPLICATION_OUTCOME_API_PATH:
            try:
                document = json.loads(request.body.decode("utf-8"))
            except (UnicodeDecodeError, json.JSONDecodeError):
                document = None
            publisher_id = (
                document.get("publisher_id")
                if isinstance(document, dict)
                else None
            )
            if (
                request.client_identity
                and publisher_id != request.client_identity
            ):
                self.identity_rejections += 1
                return self._json_response(
                    403, {"error": "application_outcome_identity_mismatch"}
                )

        return self.state.handle_request(
            request.method,
            request.path,
            request.body,
        )

    def snapshot(self) -> dict[str, object]:
        return {
            "schema_version": SCHEMA_VERSION,
            "identity_rejections": self.identity_rejections,
            "protocol_rejections": self.protocol_rejections,
            "require_client_identity": self.require_client_identity,
            "state": self.state.snapshot(),
        }


class PublicQuicGatewayBackendServer:
    def __init__(
        self,
        socket_path: str | Path,
        backend: PublicQuicGatewayBackend,
        *,
        max_body_bytes: int = DEFAULT_MAX_BODY_BYTES,
    ) -> None:
        self.socket_path = Path(socket_path)
        self.backend = backend
        self.max_body_bytes = max_body_bytes
        self._stop = threading.Event()
        self._listener: socket.socket | None = None

    def stop(self) -> None:
        self._stop.set()
        listener = self._listener
        if listener is not None:
            try:
                listener.close()
            except OSError:
                pass

    def serve_forever(self) -> None:
        self.socket_path.parent.mkdir(parents=True, exist_ok=True)
        self.socket_path.unlink(missing_ok=True)
        listener = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self._listener = listener
        try:
            listener.bind(str(self.socket_path))
            os.chmod(self.socket_path, 0o600)
            listener.listen(128)
            listener.settimeout(0.2)
            print(
                json.dumps(
                    {
                        "schema_version": SCHEMA_VERSION,
                        "status": "ready",
                        "socket": str(self.socket_path),
                        "stateful": True,
                    },
                    sort_keys=True,
                ),
                flush=True,
            )
            while not self._stop.is_set():
                try:
                    connection, _ = listener.accept()
                except socket.timeout:
                    continue
                except OSError:
                    if self._stop.is_set():
                        break
                    raise
                with connection:
                    stream = connection.makefile("rwb", buffering=0)
                    try:
                        request = read_backend_request(
                            stream,
                            max_body_bytes=self.max_body_bytes,
                        )
                        response = self.backend.dispatch(request)
                    except BackendProtocolError as exc:
                        self.backend.protocol_rejections += 1
                        response = self.backend._json_response(
                            400, {"error": str(exc)}
                        )
                    stream.write(encode_backend_response(response))
        finally:
            self._listener = None
            listener.close()
            self.socket_path.unlink(missing_ok=True)


def build_argument_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    parser.add_argument("--socket", required=True)
    parser.add_argument("--max-frames-per-topic", type=int, default=1024)
    parser.add_argument("--max-frame-bytes", type=int, default=DEFAULT_MAX_BODY_BYTES)
    parser.add_argument("--dedup-capacity-per-topic", type=int)
    parser.add_argument("--max-batch-frames", type=int, default=64)
    parser.add_argument("--admission-policy")
    parser.add_argument("--state-db")
    parser.add_argument("--writer-lease-instance-id")
    parser.add_argument("--writer-lease-ms", type=int, default=5000)
    parser.add_argument("--summary-json")
    parser.add_argument(
        "--allow-missing-client-identity",
        action="store_true",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_argument_parser().parse_args(argv)
    admission_policy = None
    if args.admission_policy:
        document = json.loads(Path(args.admission_policy).read_text())
        if not isinstance(document, dict):
            raise ValueError("gateway admission policy must be a JSON object")
        admission_policy = GatewayAdmissionPolicy.from_document(document)
    state = FleetQoxGatewayState(
        max_frames_per_topic=args.max_frames_per_topic,
        max_frame_bytes=args.max_frame_bytes,
        dedup_capacity_per_topic=args.dedup_capacity_per_topic,
        admission_policy=admission_policy,
        max_batch_frames=args.max_batch_frames,
        durable_state_path=args.state_db,
        durable_writer_id=args.writer_lease_instance_id,
        durable_writer_lease_ms=args.writer_lease_ms,
    )
    backend = PublicQuicGatewayBackend(
        state,
        require_client_identity=not args.allow_missing_client_identity,
    )
    server = PublicQuicGatewayBackendServer(
        args.socket,
        backend,
        max_body_bytes=args.max_frame_bytes,
    )

    def request_stop(signum: int, frame: object) -> None:
        del signum, frame
        server.stop()

    signal.signal(signal.SIGINT, request_stop)
    signal.signal(signal.SIGTERM, request_stop)
    try:
        server.serve_forever()
    finally:
        summary = {
            "schema_version": SCHEMA_VERSION,
            "status": "stopped",
            "clean_teardown": True,
            "metrics": backend.snapshot(),
        }
        state.close()
        if args.summary_json:
            output = Path(args.summary_json)
            output.parent.mkdir(parents=True, exist_ok=True)
            output.write_text(
                json.dumps(summary, indent=2, sort_keys=True) + "\n",
                encoding="utf-8",
            )
        print(json.dumps(summary, sort_keys=True), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

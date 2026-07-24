#!/usr/bin/env python3
"""Concurrent, test-only delay proxy for the public QUIC state backend."""

from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor
import json
import os
from pathlib import Path
import signal
import socket
import threading
import time
from urllib.parse import parse_qs, urlsplit

from fleetqox.public_quic_gateway_backend import (
    BackendProtocolError,
    BackendRequest,
    encode_backend_request,
    encode_backend_response,
    read_backend_request,
    read_backend_response,
)
from fleetqox.quic_gateway_state import GatewayResponse


SCHEMA_VERSION = "fleetrmw.public_quic_backend_delay_proxy.v1"


class DelayProxy:
    """Forward bounded backend requests, delaying selected consumer IDs."""

    def __init__(
        self,
        listen_path: str | Path,
        upstream_path: str | Path,
        *,
        delay_prefixes: tuple[str, ...],
        delay_ms: int,
        workers: int,
        max_in_flight: int,
    ) -> None:
        if delay_ms < 0:
            raise ValueError("delay_ms must be nonnegative")
        if workers <= 0 or max_in_flight <= 0:
            raise ValueError("workers and max_in_flight must be positive")
        self.listen_path = Path(listen_path)
        self.upstream_path = Path(upstream_path)
        self.delay_prefixes = delay_prefixes
        self.delay_ms = delay_ms
        self.workers = workers
        self.max_in_flight = max_in_flight
        self._stop = threading.Event()
        self._listener: socket.socket | None = None
        self._executor = ThreadPoolExecutor(
            max_workers=workers,
            thread_name_prefix="fleetqox-delay-proxy",
        )
        self._slots = threading.BoundedSemaphore(max_in_flight)
        self._metrics_lock = threading.Lock()
        self._requests_total = 0
        self._delayed_requests = 0
        self._forwarded_requests = 0
        self._overload_rejections = 0
        self._failures = 0
        self._active_requests = 0
        self._max_active_requests = 0
        self._forwarded_consumer_ids: list[str] = []

    def stop(self) -> None:
        self._stop.set()
        listener = self._listener
        if listener is not None:
            try:
                listener.close()
            except OSError:
                pass

    def _consumer_id(self, request: BackendRequest) -> str:
        query = parse_qs(urlsplit(request.path).query)
        values = query.get("consumer_id", ())
        return values[0] if values else ""

    def _should_delay(self, request: BackendRequest) -> tuple[bool, str]:
        consumer_id = self._consumer_id(request)
        return (
            any(consumer_id.startswith(prefix) for prefix in self.delay_prefixes),
            consumer_id,
        )

    @staticmethod
    def _error_response(status: int, error: str) -> GatewayResponse:
        return GatewayResponse(
            status=status,
            content_type="application/json",
            body=json.dumps(
                {"error": error},
                separators=(",", ":"),
                sort_keys=True,
            ).encode("utf-8"),
        )

    def _send_response(
        self,
        connection: socket.socket,
        response: GatewayResponse,
    ) -> None:
        try:
            connection.sendall(encode_backend_response(response))
        except OSError:
            pass

    def _handle_connection(self, connection: socket.socket) -> None:
        with self._metrics_lock:
            self._requests_total += 1
            self._active_requests += 1
            self._max_active_requests = max(
                self._max_active_requests,
                self._active_requests,
            )
        try:
            with connection:
                connection.settimeout(5.0)
                stream = connection.makefile("rb", buffering=0)
                request = read_backend_request(stream)
                delayed, consumer_id = self._should_delay(request)
                if delayed:
                    with self._metrics_lock:
                        self._delayed_requests += 1
                    print(
                        "FLEETQOX_BACKEND_DELAY_PROXY_DELAYING "
                        f"consumer_id={consumer_id} delay_ms={self.delay_ms}",
                        flush=True,
                    )
                    time.sleep(self.delay_ms / 1000.0)
                with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as upstream:
                    upstream.settimeout(5.0)
                    upstream.connect(str(self.upstream_path))
                    upstream.sendall(encode_backend_request(request))
                    response = read_backend_response(
                        upstream.makefile("rb", buffering=0)
                    )
                with self._metrics_lock:
                    self._forwarded_requests += 1
                    self._forwarded_consumer_ids.append(consumer_id)
                self._send_response(connection, response)
        except (BackendProtocolError, OSError, TimeoutError) as exc:
            with self._metrics_lock:
                self._failures += 1
            self._send_response(
                connection,
                self._error_response(502, f"delay_proxy_failure:{type(exc).__name__}"),
            )
        finally:
            with self._metrics_lock:
                self._active_requests -= 1
            self._slots.release()

    def serve_forever(self) -> None:
        self.listen_path.parent.mkdir(parents=True, exist_ok=True)
        self.listen_path.unlink(missing_ok=True)
        listener = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self._listener = listener
        try:
            listener.bind(str(self.listen_path))
            os.chmod(self.listen_path, 0o600)
            listener.listen(128)
            listener.settimeout(0.2)
            print(
                json.dumps(
                    {
                        "schema_version": SCHEMA_VERSION,
                        "status": "ready",
                        "listen_socket": str(self.listen_path),
                        "upstream_socket": str(self.upstream_path),
                        "delay_ms": self.delay_ms,
                        "delay_prefixes": self.delay_prefixes,
                        "workers": self.workers,
                        "max_in_flight": self.max_in_flight,
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
                if not self._slots.acquire(blocking=False):
                    with self._metrics_lock:
                        self._overload_rejections += 1
                    with connection:
                        self._send_response(
                            connection,
                            self._error_response(503, "delay_proxy_overloaded"),
                        )
                    continue
                self._executor.submit(self._handle_connection, connection)
        finally:
            self._listener = None
            listener.close()
            self.listen_path.unlink(missing_ok=True)
            self._executor.shutdown(wait=True, cancel_futures=False)

    def snapshot(self) -> dict[str, object]:
        with self._metrics_lock:
            return {
                "schema_version": SCHEMA_VERSION,
                "status": "stopped",
                "clean_teardown": True,
                "delay_ms": self.delay_ms,
                "delay_prefixes": list(self.delay_prefixes),
                "workers": self.workers,
                "max_in_flight": self.max_in_flight,
                "requests_total": self._requests_total,
                "delayed_requests": self._delayed_requests,
                "forwarded_requests": self._forwarded_requests,
                "overload_rejections": self._overload_rejections,
                "failures": self._failures,
                "active_requests": self._active_requests,
                "max_active_requests": self._max_active_requests,
                "forwarded_consumer_ids": list(
                    self._forwarded_consumer_ids
                ),
            }


def build_argument_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    parser.add_argument("--listen-socket", required=True)
    parser.add_argument("--upstream-socket", required=True)
    parser.add_argument("--delay-prefix", action="append", default=[])
    parser.add_argument("--delay-ms", type=int, default=1500)
    parser.add_argument("--workers", type=int, default=16)
    parser.add_argument("--max-in-flight", type=int, default=64)
    parser.add_argument("--summary-json")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_argument_parser().parse_args(argv)
    proxy = DelayProxy(
        args.listen_socket,
        args.upstream_socket,
        delay_prefixes=tuple(args.delay_prefix),
        delay_ms=args.delay_ms,
        workers=args.workers,
        max_in_flight=args.max_in_flight,
    )

    def request_stop(signum: int, frame: object) -> None:
        del signum, frame
        proxy.stop()

    signal.signal(signal.SIGINT, request_stop)
    signal.signal(signal.SIGTERM, request_stop)
    try:
        proxy.serve_forever()
    finally:
        summary = proxy.snapshot()
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

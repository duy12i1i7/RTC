#!/usr/bin/env python3
"""Promote a PostgreSQL standby only after winning an etcd quorum lease."""

from __future__ import annotations

import argparse
import importlib
import json
import ssl
import time
from typing import Any
from urllib import error, request

from fleetqox.postgres_failover_dcs import EtcdQuorumLease


SCHEMA_VERSION = "fleetrmw.postgresql_failover_controller.v1"


def database_recovery_state(psycopg: Any, dsn: str) -> bool | None:
    try:
        connection = psycopg.connect(dsn, connect_timeout=1, autocommit=True)
        try:
            return bool(connection.execute("SELECT pg_is_in_recovery()").fetchone()[0])
        finally:
            connection.close()
    except (psycopg.OperationalError, psycopg.InterfaceError):
        return None


def emit(document: dict[str, Any]) -> None:
    print(json.dumps(document, sort_keys=True), flush=True)


def request_fence(args: argparse.Namespace, lease_id: str) -> dict[str, Any]:
    payload = json.dumps(
        {"controller_id": args.controller_id, "lease_id": lease_id},
        separators=(",", ":"),
    ).encode()
    call = request.Request(
        args.fence_url,
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        context = ssl.create_default_context(cafile=args.fence_ca)
        context.load_cert_chain(
            certfile=args.fence_cert, keyfile=args.fence_key
        )
        with request.urlopen(
            call,
            timeout=args.fence_timeout_ms / 1000.0,
            context=context,
        ) as response:
            document = json.loads(response.read().decode())
    except (
        error.HTTPError,
        error.URLError,
        TimeoutError,
        ssl.SSLError,
        json.JSONDecodeError,
    ):
        return {"hard_fence_confirmed": False}
    return document if isinstance(document, dict) else {"hard_fence_confirmed": False}


def run_controller(args: argparse.Namespace) -> int:
    psycopg = importlib.import_module("psycopg")
    dcs = EtcdQuorumLease(
        tuple(part for part in args.etcd_endpoints.split(",") if part),
        timeout_s=args.dcs_timeout_ms / 1000.0,
        ca_file=args.etcd_ca,
        cert_file=args.etcd_cert,
        key_file=args.etcd_key,
    )
    started = time.monotonic()
    deadline = started + args.max_runtime_ms / 1000.0
    primary_failures = 0
    lease_attempts = 0
    quorum_acquisition_failures = 0
    dcs_request_failures = 0
    emit(
        {
            "schema_version": SCHEMA_VERSION,
            "status": "monitoring",
            "controller_id": args.controller_id,
            "dcs_endpoint_count": len(dcs.endpoints),
            "failure_threshold": args.failure_threshold,
        }
    )
    while time.monotonic() < deadline:
        primary_state = database_recovery_state(psycopg, args.primary_dsn)
        standby_state = database_recovery_state(psycopg, args.standby_dsn)
        if standby_state is False and primary_state is not False:
            emit(
                {
                    "schema_version": SCHEMA_VERSION,
                    "status": "promotion_observed",
                    "controller_id": args.controller_id,
                    "dcs_lock_acquired": False,
                    "primary_failures": primary_failures,
                    "lease_attempts": lease_attempts,
                    "quorum_acquisition_failures": quorum_acquisition_failures,
                    "dcs_request_failures": dcs_request_failures,
                    "elapsed_ms": round((time.monotonic() - started) * 1000.0),
                }
            )
            return 0
        if primary_state is False:
            primary_failures = 0
            time.sleep(args.poll_ms / 1000.0)
            continue
        primary_failures += 1
        if primary_failures < args.failure_threshold:
            time.sleep(args.poll_ms / 1000.0)
            continue
        lease_attempts += 1
        try:
            lease = dcs.acquire(
                key=args.lease_key,
                value=args.controller_id,
                ttl_s=args.lease_ttl_s,
            )
        except RuntimeError:
            quorum_acquisition_failures += 1
            emit(
                {
                    "schema_version": SCHEMA_VERSION,
                    "status": "quorum_unavailable",
                    "controller_id": args.controller_id,
                    "dcs_lock_acquired": False,
                    "primary_failures": primary_failures,
                    "lease_attempts": lease_attempts,
                    "quorum_acquisition_failures": (
                        quorum_acquisition_failures
                    ),
                }
            )
            time.sleep(args.poll_ms / 1000.0)
            continue
        dcs_request_failures += lease.request_failures
        if not lease.acquired:
            time.sleep(args.poll_ms / 1000.0)
            continue
        fence = request_fence(args, lease.lease_id)
        if fence.get("hard_fence_confirmed") is not True:
            emit(
                {
                    "schema_version": SCHEMA_VERSION,
                    "status": "fencing_failed",
                    "controller_id": args.controller_id,
                    "dcs_lock_acquired": True,
                    "lease_id": lease.lease_id,
                    "cluster_id": lease.cluster_id,
                    "revision": lease.revision,
                    "hard_fence_confirmed": False,
                }
            )
            return 1
        try:
            connection = psycopg.connect(
                args.standby_dsn, connect_timeout=2, autocommit=True
            )
            try:
                promoted = bool(
                    connection.execute("SELECT pg_promote(true, 10)").fetchone()[0]
                )
            finally:
                connection.close()
        except (psycopg.OperationalError, psycopg.InterfaceError):
            promoted = False
        if not promoted:
            emit(
                {
                    "schema_version": SCHEMA_VERSION,
                    "status": "promotion_failed",
                    "controller_id": args.controller_id,
                    "dcs_lock_acquired": True,
                    "lease_id": lease.lease_id,
                    "cluster_id": lease.cluster_id,
                    "revision": lease.revision,
                }
            )
            return 1
        if database_recovery_state(psycopg, args.standby_dsn) is not False:
            return 1
        promotion_confirmed_unix_ns = time.time_ns()
        emit(
            {
                "schema_version": SCHEMA_VERSION,
                "status": "promoted",
                "controller_id": args.controller_id,
                "dcs_lock_acquired": True,
                "lease_id": lease.lease_id,
                "cluster_id": lease.cluster_id,
                "revision": lease.revision,
                "hard_fence_confirmed": True,
                "fenced_container": fence.get("target_container", ""),
                "fence_confirmed_unix_ns": fence.get(
                    "fence_confirmed_unix_ns"
                ),
                "promotion_confirmed_unix_ns": promotion_confirmed_unix_ns,
                "primary_failures": primary_failures,
                "lease_attempts": lease_attempts,
                "quorum_acquisition_failures": quorum_acquisition_failures,
                "dcs_request_failures": dcs_request_failures,
                "elapsed_ms": round((time.monotonic() - started) * 1000.0),
            }
        )
        return 0
    emit(
        {
            "schema_version": SCHEMA_VERSION,
            "status": "timed_out",
            "controller_id": args.controller_id,
            "dcs_lock_acquired": False,
            "primary_failures": primary_failures,
            "lease_attempts": lease_attempts,
            "quorum_acquisition_failures": quorum_acquisition_failures,
            "dcs_request_failures": dcs_request_failures,
            "elapsed_ms": round((time.monotonic() - started) * 1000.0),
        }
    )
    return 1


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--controller-id", required=True)
    parser.add_argument("--primary-dsn", required=True)
    parser.add_argument("--standby-dsn", required=True)
    parser.add_argument("--etcd-endpoints", required=True)
    parser.add_argument("--etcd-ca")
    parser.add_argument("--etcd-cert")
    parser.add_argument("--etcd-key")
    parser.add_argument("--lease-key", default="/fleetqox/postgresql/failover")
    parser.add_argument("--fence-url", required=True)
    parser.add_argument("--fence-ca", required=True)
    parser.add_argument("--fence-cert", required=True)
    parser.add_argument("--fence-key", required=True)
    parser.add_argument("--fence-timeout-ms", type=int, default=7000)
    parser.add_argument("--lease-ttl-s", type=int, default=15)
    parser.add_argument("--failure-threshold", type=int, default=3)
    parser.add_argument("--poll-ms", type=int, default=100)
    parser.add_argument("--dcs-timeout-ms", type=int, default=500)
    parser.add_argument("--max-runtime-ms", type=int, default=30000)
    args = parser.parse_args()
    if (
        args.lease_ttl_s <= 0
        or args.failure_threshold <= 0
        or args.poll_ms <= 0
        or args.dcs_timeout_ms <= 0
        or args.max_runtime_ms <= 0
        or args.fence_timeout_ms <= 0
    ):
        parser.error("controller timing and threshold values must be positive")
    tls_values = (args.etcd_ca, args.etcd_cert, args.etcd_key)
    if any(tls_values) and not all(tls_values):
        parser.error("etcd TLS requires --etcd-ca, --etcd-cert, and --etcd-key")
    if not args.fence_url.startswith("https://"):
        parser.error("fence URL must use HTTPS")
    return args


def main() -> int:
    return run_controller(parse_args())


if __name__ == "__main__":
    raise SystemExit(main())

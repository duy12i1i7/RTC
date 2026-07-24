#!/usr/bin/env python3
"""Perform a safe PostgreSQL failback after winning an etcd quorum lease."""

from __future__ import annotations

import argparse
import importlib
import json
import ssl
import time
from typing import Any
from urllib import error, request

from fleetqox.postgres_failover_dcs import EtcdQuorumLease


SCHEMA_VERSION = "fleetrmw.postgresql_failback_controller.v1"
POLICY = "prefer-original-when-synchronous"


def database_recovery_state(psycopg: Any, dsn: str) -> bool | None:
    try:
        connection = psycopg.connect(dsn, connect_timeout=1, autocommit=True)
        try:
            return bool(connection.execute("SELECT pg_is_in_recovery()").fetchone()[0])
        finally:
            connection.close()
    except (psycopg.OperationalError, psycopg.InterfaceError):
        return None


def synchronous_replay_gap(
    psycopg: Any, dsn: str, application_name: str,
) -> dict[str, Any] | None:
    try:
        connection = psycopg.connect(dsn, connect_timeout=1, autocommit=True)
        try:
            row = connection.execute(
                "SELECT state, sync_state, "
                "pg_wal_lsn_diff(pg_current_wal_flush_lsn(), replay_lsn)::bigint "
                "FROM pg_stat_replication WHERE application_name=%s",
                (application_name,),
            ).fetchone()
        finally:
            connection.close()
    except (psycopg.OperationalError, psycopg.InterfaceError):
        return None
    if row is None:
        return None
    return {
        "state": str(row[0]),
        "sync_state": str(row[1]),
        "replay_gap_bytes": int(row[2]),
    }


def emit(document: dict[str, Any]) -> None:
    print(json.dumps(document, sort_keys=True), flush=True)


def request_switchover(args: argparse.Namespace, lease_id: str) -> dict[str, Any]:
    payload = json.dumps(
        {"controller_id": args.controller_id, "lease_id": lease_id},
        separators=(",", ":"),
    ).encode()
    call = request.Request(
        args.switchover_url,
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        context = ssl.create_default_context(cafile=args.switchover_ca)
        context.load_cert_chain(
            certfile=args.switchover_cert, keyfile=args.switchover_key
        )
        with request.urlopen(
            call,
            timeout=args.switchover_timeout_ms / 1000.0,
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
        return {"graceful_stop_confirmed": False}
    return (
        document
        if isinstance(document, dict)
        else {"graceful_stop_confirmed": False}
    )


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
    safe_samples = 0
    lease_attempts = 0
    quorum_acquisition_failures = 0
    dcs_request_failures = 0
    unsafe_preconditions_emitted = False
    emit(
        {
            "schema_version": SCHEMA_VERSION,
            "status": "monitoring",
            "controller_id": args.controller_id,
            "policy": args.policy,
            "dcs_endpoint_count": len(dcs.endpoints),
            "safe_sample_threshold": args.safe_sample_threshold,
        }
    )
    while time.monotonic() < deadline:
        current_state = database_recovery_state(psycopg, args.current_primary_dsn)
        target_state = database_recovery_state(psycopg, args.target_standby_dsn)
        if target_state is False and current_state is not False:
            emit(
                {
                    "schema_version": SCHEMA_VERSION,
                    "status": "failback_observed",
                    "controller_id": args.controller_id,
                    "policy": args.policy,
                    "dcs_lock_acquired": False,
                    "safe_samples": safe_samples,
                    "lease_attempts": lease_attempts,
                    "quorum_acquisition_failures": quorum_acquisition_failures,
                    "dcs_request_failures": dcs_request_failures,
                    "elapsed_ms": round((time.monotonic() - started) * 1000.0),
                }
            )
            return 0
        replication = (
            synchronous_replay_gap(
                psycopg,
                args.current_primary_dsn,
                args.replication_application,
            )
            if current_state is False and target_state is True
            else None
        )
        safe = (
            replication is not None
            and replication.get("state") == "streaming"
            and replication.get("sync_state") == "sync"
            and replication.get("replay_gap_bytes") == 0
        )
        if (
            current_state is False
            and target_state is True
            and not safe
            and not unsafe_preconditions_emitted
        ):
            emit(
                {
                    "schema_version": SCHEMA_VERSION,
                    "status": "unsafe_preconditions",
                    "controller_id": args.controller_id,
                    "policy": args.policy,
                    "dcs_lock_acquired": False,
                    "current_primary_read_write": True,
                    "target_standby_in_recovery": True,
                    "replication": replication,
                }
            )
            unsafe_preconditions_emitted = True
        safe_samples = safe_samples + 1 if safe else 0
        if safe_samples < args.safe_sample_threshold:
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
                    "policy": args.policy,
                    "dcs_lock_acquired": False,
                    "safe_samples": safe_samples,
                    "synchronous_replay_gap_bytes": 0,
                    "lease_attempts": lease_attempts,
                    "quorum_acquisition_failures": quorum_acquisition_failures,
                }
            )
            time.sleep(args.poll_ms / 1000.0)
            continue
        dcs_request_failures += lease.request_failures
        if not lease.acquired:
            time.sleep(args.poll_ms / 1000.0)
            continue
        switchover = request_switchover(args, lease.lease_id)
        if switchover.get("graceful_stop_confirmed") is not True:
            emit(
                {
                    "schema_version": SCHEMA_VERSION,
                    "status": "source_stop_failed",
                    "controller_id": args.controller_id,
                    "policy": args.policy,
                    "dcs_lock_acquired": True,
                    "lease_id": lease.lease_id,
                    "cluster_id": lease.cluster_id,
                    "revision": lease.revision,
                    "graceful_stop_confirmed": False,
                }
            )
            return 1
        try:
            connection = psycopg.connect(
                args.target_standby_dsn, connect_timeout=2, autocommit=True
            )
            try:
                promoted = bool(
                    connection.execute("SELECT pg_promote(true, 10)").fetchone()[0]
                )
                if promoted:
                    connection.execute(
                        "ALTER SYSTEM RESET synchronous_standby_names"
                    )
                    connection.execute("SELECT pg_reload_conf()")
            finally:
                connection.close()
        except (psycopg.OperationalError, psycopg.InterfaceError):
            promoted = False
        if not promoted or database_recovery_state(
            psycopg, args.target_standby_dsn
        ) is not False:
            emit(
                {
                    "schema_version": SCHEMA_VERSION,
                    "status": "promotion_failed",
                    "controller_id": args.controller_id,
                    "policy": args.policy,
                    "dcs_lock_acquired": True,
                    "lease_id": lease.lease_id,
                    "cluster_id": lease.cluster_id,
                    "revision": lease.revision,
                    "graceful_stop_confirmed": True,
                }
            )
            return 1
        promotion_confirmed_unix_ns = time.time_ns()
        emit(
            {
                "schema_version": SCHEMA_VERSION,
                "status": "failed_back",
                "controller_id": args.controller_id,
                "policy": args.policy,
                "dcs_lock_acquired": True,
                "lease_id": lease.lease_id,
                "cluster_id": lease.cluster_id,
                "revision": lease.revision,
                "safe_samples": safe_samples,
                "synchronous_replay_gap_bytes": 0,
                "graceful_stop_confirmed": True,
                "synchronous_standby_names_reset": True,
                "stopped_container": switchover.get("target_container", ""),
                "source_stop_confirmed_unix_ns": switchover.get(
                    "stop_confirmed_unix_ns"
                ),
                "promotion_confirmed_unix_ns": promotion_confirmed_unix_ns,
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
            "policy": args.policy,
            "dcs_lock_acquired": False,
            "safe_samples": safe_samples,
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
    parser.add_argument("--policy", choices=(POLICY,), default=POLICY)
    parser.add_argument("--current-primary-dsn", required=True)
    parser.add_argument("--target-standby-dsn", required=True)
    parser.add_argument("--replication-application", required=True)
    parser.add_argument("--etcd-endpoints", required=True)
    parser.add_argument("--etcd-ca")
    parser.add_argument("--etcd-cert")
    parser.add_argument("--etcd-key")
    parser.add_argument("--lease-key", default="/fleetqox/postgresql/failback")
    parser.add_argument("--switchover-url", required=True)
    parser.add_argument("--switchover-ca", required=True)
    parser.add_argument("--switchover-cert", required=True)
    parser.add_argument("--switchover-key", required=True)
    parser.add_argument("--switchover-timeout-ms", type=int, default=12000)
    parser.add_argument("--lease-ttl-s", type=int, default=20)
    parser.add_argument("--safe-sample-threshold", type=int, default=3)
    parser.add_argument("--poll-ms", type=int, default=100)
    parser.add_argument("--dcs-timeout-ms", type=int, default=500)
    parser.add_argument("--max-runtime-ms", type=int, default=30000)
    args = parser.parse_args()
    if (
        args.lease_ttl_s <= 0
        or args.safe_sample_threshold <= 0
        or args.poll_ms <= 0
        or args.dcs_timeout_ms <= 0
        or args.max_runtime_ms <= 0
        or args.switchover_timeout_ms <= 0
    ):
        parser.error("controller timing and thresholds must be positive")
    tls_values = (args.etcd_ca, args.etcd_cert, args.etcd_key)
    if any(tls_values) and not all(tls_values):
        parser.error("etcd TLS requires --etcd-ca, --etcd-cert, and --etcd-key")
    if not args.switchover_url.startswith("https://"):
        parser.error("switchover URL must use HTTPS")
    return args


def main() -> int:
    return run_controller(parse_args())


if __name__ == "__main__":
    raise SystemExit(main())

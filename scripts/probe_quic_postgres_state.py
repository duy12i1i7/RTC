#!/usr/bin/env python3
"""Exercise PostgreSQL recovery, lease takeover, and stale-writer fencing."""

from __future__ import annotations

import argparse
import json
import os
from typing import Any
from urllib.parse import urlsplit

from fleetqox.quic_gateway_state import (
    DATA_FRAME_MAGIC,
    FleetQoxGatewayState,
    FrameAdmissionError,
    FramePersistenceError,
    GatewayAdmissionPolicy,
)


SCHEMA_VERSION = "fleetrmw.quic_postgresql_state_probe.v1"
TOPIC = "/fleetqox/postgresql"
PUBLISHER = "postgresql-probe-publisher"


def frame(
    sequence: int,
    *,
    topic: str = TOPIC,
    repair_requested: bool = False,
) -> bytes:
    payload = f"postgresql-frame-{sequence}".encode()
    document: dict[str, Any] = {
        "schema_version": "fleetrmw.data_frame.v1",
        "kind": "sidecar_packet_frame",
        "domain_id": 42,
        "route": {
            "robot_id": "robot-postgresql",
            "topic": topic,
            "flow_class": "control",
        },
        "sample_envelope": {
            "robot_id": "robot-postgresql",
            "topic": topic,
            "publisher_id": PUBLISHER,
            "source_sequence_number": sequence,
            "source_timestamp_ns": sequence * 1000,
        },
        "qox": {"qoe_debt": 1.0, "task_criticality": 1.0},
        "serialized_payload": {
            "encoding": "hex",
            "size": len(payload),
            "data": payload.hex(),
        },
    }
    if repair_requested:
        document["repair"] = {"requested": True, "prior_attempts": 0}
    return DATA_FRAME_MAGIC + json.dumps(
        document, separators=(",", ":"), allow_nan=False
    ).encode()


def policy() -> GatewayAdmissionPolicy:
    return GatewayAdmissionPolicy.from_document(
        {
            "schema_version": "fleetrmw.quic_gateway_admission_policy.v1",
            "default_action": "allow",
            "rules": [
                {
                    "domain_id": 42,
                    "topic": TOPIC,
                    "traffic_class": "control",
                    "max_accepted_frames": 1,
                    "allowed_publishers": [PUBLISHER],
                }
            ],
            "repair": {
                "capacity_bytes": 4096,
                "max_admitted": 1,
                "paths": [
                    {
                        "path_id": "private_5g",
                        "latency_ms": 10.0,
                        "loss": 0.01,
                        "failure_domain": "private_5g",
                    }
                ],
            },
        }
    )


def run_probe(dsn: str) -> dict[str, Any]:
    clocks = {"active": 1000.0, "standby": 1000.0}
    active: FleetQoxGatewayState | None = None
    standby: FleetQoxGatewayState | None = None
    concurrent_writer_fenced = False
    stale_writer_fenced = False
    resumed_repair_rejected = False
    cursor_recovered = False
    duplicate_recovered = False
    try:
        active = FleetQoxGatewayState(
            max_frames_per_topic=8,
            durable_state_path=dsn,
            durable_writer_id="gateway-a",
            durable_writer_lease_ms=1000,
            admission_policy=policy(),
            wall_clock=lambda: clocks["active"],
        )
        normal = active.publish(frame(1))
        repair = active.publish(frame(2, repair_requested=True))
        first_take = active.take(
            domain_id=42, topic=TOPIC, consumer_id="postgresql-consumer"
        )
        active_before = active.snapshot()

        try:
            FleetQoxGatewayState(
                max_frames_per_topic=8,
                durable_state_path=dsn,
                durable_writer_id="gateway-b",
                durable_writer_lease_ms=1000,
                admission_policy=policy(),
                wall_clock=lambda: clocks["standby"],
            )
        except FramePersistenceError as exc:
            concurrent_writer_fenced = "writer lease is held by 'gateway-a'" in str(exc)

        clocks["active"] = 1002.0
        clocks["standby"] = 1002.0
        standby = FleetQoxGatewayState(
            max_frames_per_topic=8,
            durable_state_path=dsn,
            durable_writer_id="gateway-b",
            durable_writer_lease_ms=1000,
            admission_policy=policy(),
            wall_clock=lambda: clocks["standby"],
        )
        standby_recovered = standby.snapshot()

        try:
            active.publish(frame(99, topic="/fleetqox/stale-writer"))
        except FramePersistenceError as exc:
            stale_writer_fenced = "writer fence rejected" in str(exc)

        duplicate = standby.publish(frame(1))
        duplicate_recovered = duplicate.duplicate and not duplicate.accepted
        cursor_recovered = (
            standby.take(
                domain_id=42, topic=TOPIC, consumer_id="postgresql-consumer"
            )
            == frame(2, repair_requested=True)
        )
        try:
            standby.publish(frame(3, repair_requested=True))
        except FrameAdmissionError as exc:
            resumed_repair_rejected = exc.reason_code == "stream_quota_exhausted"

        final = standby.snapshot()
        durable = final.get("durable_state") or {}
        lease = durable.get("writer_lease") or {}
        endpoint = str(durable.get("endpoint", ""))
        parsed_endpoint = urlsplit(endpoint)
        checks = {
            "normal_admitted": normal.accepted and normal.admission_action == "normal",
            "repair_admitted": repair.accepted and repair.admission_action == "repair",
            "initial_cursor_committed": first_take == frame(1),
            "concurrent_writer_fenced": concurrent_writer_fenced,
            "takeover_token_incremented": lease.get("fence_token") == 2,
            "stale_writer_fenced": stale_writer_fenced,
            "frames_recovered": standby_recovered.get("recovered_frames") == 2,
            "dedup_recovered": standby_recovered.get("recovered_dedup_keys") == 2,
            "admission_recovered": standby_recovered.get("recovered_admission_state") == 1,
            "cursor_recovered": cursor_recovered,
            "duplicate_recovered": duplicate_recovered,
            "repair_budget_recovered": resumed_repair_rejected,
            "postgresql_backend": durable.get("backend") == "postgresql",
            "synchronous_commit": durable.get("synchronous_commit") == "on",
            "credential_redaction": (
                parsed_endpoint.username is None
                and parsed_endpoint.password is None
                and "fleetqox-probe" not in endpoint
            ),
            "transaction_counts": (
                durable.get("retained_frame_count") == 2
                and durable.get("dedup_key_count") == 2
                and durable.get("consumer_cursor_count") == 1
                and durable.get("admission_state_count") == 1
            ),
            "active_writer_state_rolled_back": (
                active.snapshot()["admission"]["accepted_cumulative"]
                == active_before["admission"]["accepted_cumulative"]
            ),
        }
        return {
            "schema_version": SCHEMA_VERSION,
            "status": "ok" if all(checks.values()) else "failed",
            "checks": checks,
            "active_before_takeover": active_before,
            "standby_after_recovery": standby_recovered,
            "final": final,
            "networked_database": True,
            "transactional_frame_and_admission_state": True,
            "single_writer_fencing": True,
            "database_process_failover": False,
            "replicated_database": False,
            "consensus_backend": False,
            "production_readiness": False,
        }
    finally:
        if active is not None:
            active.close()
        if standby is not None:
            standby.close()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dsn", default=os.environ.get("FLEETQOX_POSTGRES_DSN", ""))
    args = parser.parse_args()
    if not args.dsn:
        parser.error("--dsn or FLEETQOX_POSTGRES_DSN is required")
    result = run_probe(args.dsn)
    print(json.dumps(result, sort_keys=True, separators=(",", ":")))
    return 0 if result["status"] == "ok" else 1


if __name__ == "__main__":
    raise SystemExit(main())

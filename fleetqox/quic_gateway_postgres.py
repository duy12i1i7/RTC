"""Networked PostgreSQL durable-state backend for the FleetQoX QUIC gateway."""

from __future__ import annotations

import importlib
import json
from typing import Any

from .quic_gateway_state import (
    FrameMetadata,
    FramePersistenceError,
    FramePersistenceUnavailableError,
    FrameValidationError,
    StoredFrame,
    TopicHistory,
    parse_data_frame,
)


class PostgresGatewayDurableStore:
    """PostgreSQL store with transactional leases and stale-writer fencing."""

    SCHEMA_VERSION = "fleetrmw.quic_gateway_postgresql_durable_state.v1"
    _LEASE_ADVISORY_LOCK_KEY = 0x46514F5857524954  # FQOXWRIT

    def __init__(self, dsn: str) -> None:
        if not dsn.startswith(("postgresql://", "postgres://")):
            raise ValueError("PostgreSQL durable state requires a PostgreSQL URL")
        self._writer_lease_id: str | None = None
        self._writer_fence_token: int | None = None
        self._writer_lease_ms: int | None = None
        self._last_snapshot: dict[str, Any] | None = None
        try:
            self._psycopg = importlib.import_module("psycopg")
        except ModuleNotFoundError as exc:
            raise FramePersistenceError(
                "PostgreSQL durable state requires python3-psycopg"
            ) from exc
        try:
            self._connection = self._psycopg.connect(
                dsn,
                connect_timeout=2,
                options="-c synchronous_commit=on -c statement_timeout=15000",
            )
            with self._connection.transaction():
                self._connection.execute(
                    """
                    CREATE TABLE IF NOT EXISTS durable_metadata (
                      key TEXT PRIMARY KEY,
                      value TEXT NOT NULL
                    )
                    """
                )
                self._connection.execute(
                    """
                    CREATE TABLE IF NOT EXISTS frames (
                      domain_id BIGINT NOT NULL,
                      topic TEXT NOT NULL,
                      frame_offset BIGINT NOT NULL,
                      payload BYTEA NOT NULL,
                      publisher_id TEXT NOT NULL,
                      source_sequence_number BIGINT NOT NULL,
                      PRIMARY KEY (domain_id, topic, frame_offset)
                    )
                    """
                )
                self._connection.execute(
                    """
                    CREATE TABLE IF NOT EXISTS dedup_keys (
                      ordinal BIGSERIAL PRIMARY KEY,
                      domain_id BIGINT NOT NULL,
                      topic TEXT NOT NULL,
                      publisher_id TEXT NOT NULL,
                      source_sequence_number BIGINT NOT NULL,
                      UNIQUE (domain_id, topic, publisher_id, source_sequence_number)
                    )
                    """
                )
                self._connection.execute(
                    """
                    CREATE TABLE IF NOT EXISTS application_outcomes (
                      ordinal BIGSERIAL PRIMARY KEY,
                      domain_id BIGINT NOT NULL,
                      topic TEXT NOT NULL,
                      publisher_id TEXT NOT NULL,
                      source_sequence_number BIGINT NOT NULL,
                      UNIQUE (domain_id, topic, publisher_id, source_sequence_number),
                      FOREIGN KEY
                        (domain_id, topic, publisher_id, source_sequence_number)
                        REFERENCES dedup_keys
                          (domain_id, topic, publisher_id, source_sequence_number)
                        ON DELETE CASCADE
                    )
                    """
                )
                self._connection.execute(
                    """
                    CREATE TABLE IF NOT EXISTS consumer_cursors (
                      domain_id BIGINT NOT NULL,
                      topic TEXT NOT NULL,
                      consumer_id TEXT NOT NULL,
                      next_offset BIGINT NOT NULL,
                      PRIMARY KEY (domain_id, topic, consumer_id)
                    )
                    """
                )
                self._connection.execute(
                    """
                    CREATE TABLE IF NOT EXISTS admission_state (
                      singleton_id SMALLINT PRIMARY KEY CHECK (singleton_id = 1),
                      policy_fingerprint TEXT NOT NULL,
                      state_json TEXT NOT NULL
                    )
                    """
                )
                self._connection.execute(
                    """
                    CREATE TABLE IF NOT EXISTS writer_lease (
                      singleton_id SMALLINT PRIMARY KEY CHECK (singleton_id = 1),
                      holder_id TEXT NOT NULL,
                      fence_token BIGINT NOT NULL,
                      expires_unix_ms BIGINT NOT NULL
                    )
                    """
                )
                existing = self._connection.execute(
                    "SELECT value FROM durable_metadata WHERE key='schema_version'"
                ).fetchone()
                if existing is not None and existing[0] != self.SCHEMA_VERSION:
                    raise FramePersistenceError(
                        f"unsupported PostgreSQL durable state schema {existing[0]!r}"
                    )
                self._connection.execute(
                    "INSERT INTO durable_metadata(key, value) VALUES(%s, %s) "
                    "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                    ("schema_version", self.SCHEMA_VERSION),
                )
        except FramePersistenceError:
            if hasattr(self, "_connection"):
                self._connection.close()
            raise
        except Exception as exc:
            if hasattr(self, "_connection"):
                self._connection.close()
            raise self._wrapped_error(
                "could not initialize PostgreSQL gateway state", exc
            ) from exc

    def _is_unavailable(self, exc: Exception) -> bool:
        return isinstance(
            exc,
            (self._psycopg.OperationalError, self._psycopg.InterfaceError),
        )

    def _wrapped_error(
        self, context: str, exc: Exception
    ) -> FramePersistenceError:
        error_type = (
            FramePersistenceUnavailableError
            if self._is_unavailable(exc)
            else FramePersistenceError
        )
        detail = "durable backend unavailable" if self._is_unavailable(exc) else str(exc)
        return error_type(f"{context}: {detail}")

    def recover(
        self,
        *,
        max_frame_bytes: int,
        max_frames_per_topic: int,
        dedup_capacity_per_topic: int,
    ) -> tuple[
        dict[tuple[int, str], TopicHistory],
        dict[tuple[int, str, str], int],
        int,
        int,
        int,
    ]:
        topics: dict[tuple[int, str], TopicHistory] = {}
        try:
            with self._connection.transaction():
                rows = self._connection.execute(
                    "SELECT domain_id, topic, frame_offset, payload, publisher_id, "
                    "source_sequence_number FROM frames "
                    "ORDER BY domain_id, topic, frame_offset"
                ).fetchall()
                for domain_id, topic, offset, raw_payload, publisher_id, sequence in rows:
                    payload = bytes(raw_payload)
                    metadata = parse_data_frame(payload, max_frame_bytes=max_frame_bytes)
                    if (
                        metadata.domain_id != domain_id
                        or metadata.topic != topic
                        or metadata.publisher_id != publisher_id
                        or metadata.source_sequence_number != sequence
                        or offset < 0
                    ):
                        raise FramePersistenceError(
                            "PostgreSQL frame index does not match FleetRMW payload"
                        )
                    history = topics.setdefault((domain_id, topic), TopicHistory())
                    history.records.append(StoredFrame(offset, payload, metadata))
                    history.next_offset = max(history.next_offset, offset + 1)

                dedup_count = 0
                for domain_id, topic, publisher_id, sequence in self._connection.execute(
                    "SELECT domain_id, topic, publisher_id, source_sequence_number "
                    "FROM dedup_keys ORDER BY ordinal"
                ).fetchall():
                    history = topics.setdefault((domain_id, topic), TopicHistory())
                    history.recent_keys[(publisher_id, sequence)] = None
                    dedup_count += 1

                for stream_key, history in topics.items():
                    while len(history.records) > max_frames_per_topic:
                        stale = history.records.popleft()
                        self._connection.execute(
                            "DELETE FROM frames WHERE domain_id=%s AND topic=%s "
                            "AND frame_offset=%s",
                            (*stream_key, stale.offset),
                        )
                    while len(history.recent_keys) > dedup_capacity_per_topic:
                        publisher_id, sequence = history.recent_keys.popitem(last=False)[0]
                        self._connection.execute(
                            "DELETE FROM dedup_keys WHERE domain_id=%s AND topic=%s "
                            "AND publisher_id=%s AND source_sequence_number=%s",
                            (*stream_key, publisher_id, sequence),
                        )
                        dedup_count -= 1
                outcome_count = 0
                for domain_id, topic, publisher_id, sequence in (
                    self._connection.execute(
                        "SELECT domain_id, topic, publisher_id, "
                        "source_sequence_number FROM application_outcomes "
                        "ORDER BY ordinal"
                    ).fetchall()
                ):
                    history = topics.setdefault((domain_id, topic), TopicHistory())
                    if (publisher_id, sequence) not in history.recent_keys:
                        raise FramePersistenceError(
                            "PostgreSQL application outcome lacks its accepted "
                            "frame key"
                        )
                    history.application_outcome_keys[(publisher_id, sequence)] = None
                    outcome_count += 1
                cursors = {
                    (domain_id, topic, consumer_id): next_offset
                    for domain_id, topic, consumer_id, next_offset in (
                        self._connection.execute(
                            "SELECT domain_id, topic, consumer_id, next_offset "
                            "FROM consumer_cursors"
                        ).fetchall()
                    )
                    if next_offset >= 0
                }
        except FramePersistenceError:
            raise
        except Exception as exc:
            raise self._wrapped_error(
                "could not recover PostgreSQL gateway state", exc
            ) from exc
        frame_count = sum(len(history.records) for history in topics.values())
        return topics, cursors, frame_count, dedup_count, outcome_count

    def _lock_lease_transaction(self) -> None:
        self._connection.execute(
            "SELECT pg_advisory_xact_lock(%s)",
            (self._LEASE_ADVISORY_LOCK_KEY,),
        )

    def acquire_writer_lease(
        self, *, holder_id: str, lease_ms: int, now_unix_ms: int
    ) -> int:
        if not holder_id or lease_ms <= 0 or now_unix_ms < 0:
            raise ValueError("durable writer lease configuration is invalid")
        try:
            with self._connection.transaction():
                self._lock_lease_transaction()
                row = self._connection.execute(
                    "SELECT holder_id, fence_token, expires_unix_ms FROM writer_lease "
                    "WHERE singleton_id=1 FOR UPDATE"
                ).fetchone()
                if row is not None and row[0] != holder_id and row[2] > now_unix_ms:
                    raise FramePersistenceError(
                        f"durable writer lease is held by {row[0]!r}"
                    )
                if row is not None and row[0] == holder_id and row[2] > now_unix_ms:
                    fence_token = int(row[1])
                else:
                    fence_token = (int(row[1]) if row is not None else 0) + 1
                self._connection.execute(
                    "INSERT INTO writer_lease(singleton_id, holder_id, fence_token, "
                    "expires_unix_ms) VALUES(1, %s, %s, %s) "
                    "ON CONFLICT(singleton_id) DO UPDATE SET "
                    "holder_id=excluded.holder_id, fence_token=excluded.fence_token, "
                    "expires_unix_ms=excluded.expires_unix_ms",
                    (holder_id, fence_token, now_unix_ms + lease_ms),
                )
        except FramePersistenceError:
            raise
        except Exception as exc:
            raise self._wrapped_error(
                "could not acquire PostgreSQL writer lease", exc
            ) from exc
        self._writer_lease_id = holder_id
        self._writer_fence_token = fence_token
        self._writer_lease_ms = lease_ms
        return fence_token

    def renew_writer_lease(self, *, now_unix_ms: int) -> int:
        if (
            self._writer_lease_id is None
            or self._writer_fence_token is None
            or self._writer_lease_ms is None
        ):
            raise FramePersistenceError("durable writer lease is not configured")
        try:
            with self._connection.transaction():
                self._lock_lease_transaction()
                row = self._connection.execute(
                    "SELECT holder_id, fence_token, expires_unix_ms FROM writer_lease "
                    "WHERE singleton_id=1 FOR UPDATE"
                ).fetchone()
                if (
                    row is None
                    or row[0] != self._writer_lease_id
                    or int(row[1]) != self._writer_fence_token
                    or int(row[2]) <= now_unix_ms
                ):
                    raise FramePersistenceError(
                        "durable writer lease was lost or expired"
                    )
                expires = now_unix_ms + self._writer_lease_ms
                self._connection.execute(
                    "UPDATE writer_lease SET expires_unix_ms=%s WHERE singleton_id=1",
                    (expires,),
                )
                return expires
        except FramePersistenceError:
            raise
        except Exception as exc:
            raise self._wrapped_error(
                "could not renew PostgreSQL writer lease", exc
            ) from exc

    def release_writer_lease(self, *, now_unix_ms: int) -> None:
        if self._writer_lease_id is None or self._writer_fence_token is None:
            return
        try:
            with self._connection.transaction():
                self._lock_lease_transaction()
                self._connection.execute(
                    "UPDATE writer_lease SET expires_unix_ms=%s WHERE singleton_id=1 "
                    "AND holder_id=%s AND fence_token=%s",
                    (
                        now_unix_ms,
                        self._writer_lease_id,
                        self._writer_fence_token,
                    ),
                )
        except Exception as exc:
            raise self._wrapped_error(
                "could not release PostgreSQL writer lease", exc
            ) from exc
        finally:
            self._writer_lease_id = None
            self._writer_fence_token = None
            self._writer_lease_ms = None

    def _verify_writer_lease(self, *, now_unix_ms: int) -> None:
        if self._writer_lease_id is None or self._writer_fence_token is None:
            return
        row = self._connection.execute(
            "SELECT holder_id, fence_token, expires_unix_ms FROM writer_lease "
            "WHERE singleton_id=1 FOR UPDATE"
        ).fetchone()
        if (
            row is None
            or row[0] != self._writer_lease_id
            or int(row[1]) != self._writer_fence_token
            or int(row[2]) <= now_unix_ms
        ):
            raise FramePersistenceError(
                "durable writer fence rejected a stale or expired writer"
            )

    def load_admission_state(
        self, *, policy_fingerprint: str
    ) -> dict[str, Any] | None:
        try:
            with self._connection.transaction():
                row = self._connection.execute(
                    "SELECT policy_fingerprint, state_json FROM admission_state "
                    "WHERE singleton_id=1"
                ).fetchone()
        except Exception as exc:
            raise self._wrapped_error(
                "could not recover PostgreSQL admission state", exc
            ) from exc
        if row is None:
            return None
        stored_fingerprint, encoded = row
        if stored_fingerprint != policy_fingerprint:
            raise FramePersistenceError(
                "durable admission policy fingerprint does not match configuration"
            )
        try:
            document = json.loads(encoded)
        except (TypeError, json.JSONDecodeError) as exc:
            raise FramePersistenceError(
                f"durable admission state is invalid: {exc}"
            ) from exc
        if not isinstance(document, dict):
            raise FramePersistenceError("durable admission state must be an object")
        return document

    def append_frame(
        self,
        *,
        metadata: FrameMetadata,
        offset: int,
        payload: bytes,
        evict_offset: int | None,
        dedup_capacity_per_topic: int,
        admission_state: dict[str, Any] | None = None,
        now_unix_ms: int | None = None,
    ) -> None:
        try:
            with self._connection.transaction():
                if self._writer_lease_id is not None:
                    if now_unix_ms is None:
                        raise FramePersistenceError(
                            "durable writer fence requires a wall-clock timestamp"
                        )
                    self._verify_writer_lease(now_unix_ms=now_unix_ms)
                self._connection.execute(
                    "INSERT INTO frames(domain_id, topic, frame_offset, payload, "
                    "publisher_id, source_sequence_number) VALUES(%s, %s, %s, %s, %s, %s)",
                    (
                        metadata.domain_id,
                        metadata.topic,
                        offset,
                        bytes(payload),
                        metadata.publisher_id,
                        metadata.source_sequence_number,
                    ),
                )
                self._connection.execute(
                    "INSERT INTO dedup_keys(domain_id, topic, publisher_id, "
                    "source_sequence_number) VALUES(%s, %s, %s, %s)",
                    (
                        metadata.domain_id,
                        metadata.topic,
                        metadata.publisher_id,
                        metadata.source_sequence_number,
                    ),
                )
                if evict_offset is not None:
                    self._connection.execute(
                        "DELETE FROM frames WHERE domain_id=%s AND topic=%s "
                        "AND frame_offset=%s",
                        (metadata.domain_id, metadata.topic, evict_offset),
                    )
                stale_ordinals = self._connection.execute(
                    "SELECT ordinal FROM dedup_keys WHERE domain_id=%s AND topic=%s "
                    "ORDER BY ordinal DESC OFFSET %s",
                    (
                        metadata.domain_id,
                        metadata.topic,
                        dedup_capacity_per_topic,
                    ),
                ).fetchall()
                if stale_ordinals:
                    self._connection.execute(
                        "DELETE FROM dedup_keys WHERE ordinal = ANY(%s)",
                        ([row[0] for row in stale_ordinals],),
                    )
                if admission_state is not None:
                    fingerprint = admission_state.get("policy_fingerprint")
                    if not isinstance(fingerprint, str) or not fingerprint:
                        raise FramePersistenceError(
                            "durable admission state lacks a policy fingerprint"
                        )
                    encoded = json.dumps(
                        admission_state,
                        sort_keys=True,
                        separators=(",", ":"),
                        allow_nan=False,
                    )
                    self._connection.execute(
                        "INSERT INTO admission_state(singleton_id, policy_fingerprint, "
                        "state_json) VALUES(1, %s, %s) "
                        "ON CONFLICT(singleton_id) DO UPDATE SET "
                        "policy_fingerprint=excluded.policy_fingerprint, "
                        "state_json=excluded.state_json",
                        (fingerprint, encoded),
                    )
        except FramePersistenceError:
            raise
        except Exception as exc:
            raise self._wrapped_error(
                "could not commit PostgreSQL gateway frame", exc
            ) from exc

    def set_cursor(
        self,
        *,
        domain_id: int,
        topic: str,
        consumer_id: str,
        next_offset: int,
        now_unix_ms: int | None = None,
    ) -> None:
        try:
            with self._connection.transaction():
                if self._writer_lease_id is not None:
                    if now_unix_ms is None:
                        raise FramePersistenceError(
                            "durable writer fence requires a wall-clock timestamp"
                        )
                    self._verify_writer_lease(now_unix_ms=now_unix_ms)
                self._connection.execute(
                    "INSERT INTO consumer_cursors(domain_id, topic, consumer_id, "
                    "next_offset) VALUES(%s, %s, %s, %s) "
                    "ON CONFLICT(domain_id, topic, consumer_id) DO UPDATE SET "
                    "next_offset=excluded.next_offset",
                    (domain_id, topic, consumer_id, next_offset),
                )
        except FramePersistenceError:
            raise
        except Exception as exc:
            raise self._wrapped_error(
                "could not commit PostgreSQL gateway cursor", exc
            ) from exc

    def commit_application_outcome(
        self,
        *,
        domain_id: int,
        topic: str,
        publisher_id: str,
        source_sequence_number: int,
        capacity_per_topic: int,
        admission_state: dict[str, Any],
        now_unix_ms: int | None = None,
    ) -> bool:
        """Atomically store one outcome key and its post-outcome admission state."""

        try:
            with self._connection.transaction():
                if self._writer_lease_id is not None:
                    if now_unix_ms is None:
                        raise FramePersistenceError(
                            "durable writer fence requires a wall-clock timestamp"
                        )
                    self._verify_writer_lease(now_unix_ms=now_unix_ms)
                known = self._connection.execute(
                    "SELECT 1 FROM dedup_keys WHERE domain_id=%s AND topic=%s "
                    "AND publisher_id=%s AND source_sequence_number=%s",
                    (domain_id, topic, publisher_id, source_sequence_number),
                ).fetchone()
                if known is None:
                    raise FramePersistenceError(
                        "durable application outcome references an unknown frame"
                    )
                inserted = self._connection.execute(
                    "INSERT INTO application_outcomes(domain_id, topic, publisher_id, "
                    "source_sequence_number) VALUES(%s, %s, %s, %s) "
                    "ON CONFLICT(domain_id, topic, publisher_id, "
                    "source_sequence_number) DO NOTHING RETURNING ordinal",
                    (domain_id, topic, publisher_id, source_sequence_number),
                ).fetchone()
                if inserted is None:
                    return False
                stale_ordinals = self._connection.execute(
                    "SELECT ordinal FROM application_outcomes WHERE domain_id=%s "
                    "AND topic=%s ORDER BY ordinal DESC OFFSET %s",
                    (domain_id, topic, capacity_per_topic),
                ).fetchall()
                if stale_ordinals:
                    self._connection.execute(
                        "DELETE FROM application_outcomes WHERE ordinal = ANY(%s)",
                        ([row[0] for row in stale_ordinals],),
                    )
                fingerprint = admission_state.get("policy_fingerprint")
                if not isinstance(fingerprint, str) or not fingerprint:
                    raise FramePersistenceError(
                        "durable admission state lacks a policy fingerprint"
                    )
                encoded = json.dumps(
                    admission_state,
                    sort_keys=True,
                    separators=(",", ":"),
                    allow_nan=False,
                )
                self._connection.execute(
                    "INSERT INTO admission_state(singleton_id, policy_fingerprint, "
                    "state_json) VALUES(1, %s, %s) "
                    "ON CONFLICT(singleton_id) DO UPDATE SET "
                    "policy_fingerprint=excluded.policy_fingerprint, "
                    "state_json=excluded.state_json",
                    (fingerprint, encoded),
                )
                return True
        except FramePersistenceError:
            raise
        except Exception as exc:
            raise self._wrapped_error(
                "could not commit PostgreSQL application outcome", exc
            ) from exc

    def snapshot(self) -> dict[str, Any]:
        try:
            with self._connection.transaction():
                frame_count = self._connection.execute(
                    "SELECT COUNT(*) FROM frames"
                ).fetchone()[0]
                dedup_count = self._connection.execute(
                    "SELECT COUNT(*) FROM dedup_keys"
                ).fetchone()[0]
                consumer_count = self._connection.execute(
                    "SELECT COUNT(*) FROM consumer_cursors"
                ).fetchone()[0]
                admission_count = self._connection.execute(
                    "SELECT COUNT(*) FROM admission_state"
                ).fetchone()[0]
                application_outcome_count = self._connection.execute(
                    "SELECT COUNT(*) FROM application_outcomes"
                ).fetchone()[0]
                writer_lease = self._connection.execute(
                    "SELECT holder_id, fence_token, expires_unix_ms FROM writer_lease "
                    "WHERE singleton_id=1"
                ).fetchone()
                synchronous_commit = self._connection.execute(
                    "SHOW synchronous_commit"
                ).fetchone()[0]
                in_recovery = self._connection.execute(
                    "SELECT pg_is_in_recovery()"
                ).fetchone()[0]
                server_version = self._connection.execute(
                    "SHOW server_version"
                ).fetchone()[0]
        except Exception as exc:
            if self._is_unavailable(exc) and self._last_snapshot is not None:
                return {
                    **self._last_snapshot,
                    "available": False,
                    "snapshot_stale": True,
                    "last_error": "durable backend unavailable",
                }
            raise self._wrapped_error(
                "could not inspect PostgreSQL gateway state", exc
            ) from exc
        info = self._connection.info
        snapshot = {
            "schema_version": self.SCHEMA_VERSION,
            "backend": "postgresql",
            "endpoint": f"postgresql://{info.host}:{info.port}/{info.dbname}",
            "available": True,
            "snapshot_stale": False,
            "synchronous_commit": str(synchronous_commit),
            "server_version": str(server_version),
            "in_recovery": bool(in_recovery),
            "retained_frame_count": int(frame_count),
            "dedup_key_count": int(dedup_count),
            "consumer_cursor_count": int(consumer_count),
            "admission_state_count": int(admission_count),
            "application_outcome_count": int(application_outcome_count),
            "writer_lease": (
                {
                    "holder_id": writer_lease[0],
                    "fence_token": int(writer_lease[1]),
                    "expires_unix_ms": int(writer_lease[2]),
                }
                if writer_lease is not None
                else None
            ),
        }
        self._last_snapshot = snapshot
        return dict(snapshot)

    def close(self) -> None:
        self._connection.close()

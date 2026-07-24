"""Minimal etcd-v3 quorum lease used by PostgreSQL failover controllers."""

from __future__ import annotations

import base64
from dataclasses import dataclass
import json
import ssl
from typing import Any
from urllib import error, request


@dataclass(frozen=True)
class DcsLeaseResult:
    acquired: bool
    endpoint: str
    lease_id: str
    cluster_id: str
    revision: str
    request_failures: int


@dataclass(frozen=True)
class DcsValue:
    value: str
    lease_id: str
    cluster_id: str
    revision: str


class EtcdQuorumLease:
    """Acquire a one-shot, TTL-bound compare-and-put lease through etcd v3."""

    def __init__(
        self,
        endpoints: tuple[str, ...],
        *,
        timeout_s: float = 0.75,
        ca_file: str | None = None,
        cert_file: str | None = None,
        key_file: str | None = None,
    ) -> None:
        normalized = tuple(endpoint.rstrip("/") for endpoint in endpoints if endpoint)
        if not normalized or timeout_s <= 0.0:
            raise ValueError("etcd endpoints and timeout must be configured")
        self.endpoints = normalized
        self.timeout_s = timeout_s
        self._next_endpoint = 0
        tls_values = (ca_file, cert_file, key_file)
        if any(tls_values) and not all(tls_values):
            raise ValueError("etcd TLS requires CA, certificate, and private key")
        self._ssl_context: ssl.SSLContext | None = None
        if all(tls_values):
            self._ssl_context = ssl.create_default_context(cafile=ca_file)
            self._ssl_context.load_cert_chain(
                certfile=str(cert_file), keyfile=str(key_file)
            )

    def _post(self, path: str, payload: dict[str, Any]) -> tuple[dict[str, Any], str, int]:
        failures = 0
        encoded = json.dumps(payload, separators=(",", ":")).encode()
        for offset in range(len(self.endpoints)):
            index = (self._next_endpoint + offset) % len(self.endpoints)
            endpoint = self.endpoints[index]
            call = request.Request(
                endpoint + path,
                data=encoded,
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            try:
                with request.urlopen(
                    call, timeout=self.timeout_s, context=self._ssl_context
                ) as response:
                    document = json.loads(response.read().decode())
            except (
                error.HTTPError,
                error.URLError,
                TimeoutError,
                ssl.SSLError,
                json.JSONDecodeError,
            ):
                failures += 1
                continue
            if not isinstance(document, dict):
                failures += 1
                continue
            self._next_endpoint = (index + 1) % len(self.endpoints)
            return document, endpoint, failures
        raise RuntimeError(f"etcd quorum request failed on {failures} endpoint(s)")

    def acquire(self, *, key: str, value: str, ttl_s: int = 15) -> DcsLeaseResult:
        if not key or not value or ttl_s <= 0:
            raise ValueError("etcd lease key, value, and TTL must be valid")
        failures = 0
        lease, endpoint, grant_failures = self._post(
            "/v3/lease/grant", {"TTL": ttl_s}
        )
        failures += grant_failures
        lease_id = str(lease.get("ID", ""))
        if not lease_id:
            raise RuntimeError("etcd lease grant returned no lease ID")
        key64 = base64.b64encode(key.encode()).decode()
        value64 = base64.b64encode(value.encode()).decode()
        transaction, endpoint, txn_failures = self._post(
            "/v3/kv/txn",
            {
                "compare": [
                    {
                        "key": key64,
                        "target": "CREATE",
                        "createRevision": "0",
                    }
                ],
                "success": [
                    {
                        "requestPut": {
                            "key": key64,
                            "value": value64,
                            "lease": lease_id,
                        }
                    }
                ],
                "failure": [{"requestRange": {"key": key64}}],
            },
        )
        failures += txn_failures
        header = transaction.get("header", {})
        return DcsLeaseResult(
            acquired=transaction.get("succeeded") is True,
            endpoint=endpoint,
            lease_id=lease_id,
            cluster_id=str(header.get("cluster_id", "")),
            revision=str(header.get("revision", "")),
            request_failures=failures,
        )

    def get(self, *, key: str) -> DcsValue | None:
        if not key:
            raise ValueError("etcd lookup key must be non-empty")
        key64 = base64.b64encode(key.encode()).decode()
        document, _, _ = self._post("/v3/kv/range", {"key": key64})
        rows = document.get("kvs", [])
        if not isinstance(rows, list) or not rows:
            return None
        row = rows[0]
        if not isinstance(row, dict):
            return None
        try:
            value = base64.b64decode(str(row.get("value", ""))).decode()
        except (ValueError, UnicodeDecodeError):
            return None
        header = document.get("header", {})
        return DcsValue(
            value=value,
            lease_id=str(row.get("lease", "")),
            cluster_id=str(header.get("cluster_id", "")),
            revision=str(header.get("revision", "")),
        )

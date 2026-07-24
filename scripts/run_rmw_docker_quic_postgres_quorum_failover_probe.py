#!/usr/bin/env python3
"""Validate quorum-gated automatic PostgreSQL promotion and gateway takeover."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import shutil
import subprocess
import time
from typing import Any
from urllib.parse import urlsplit

try:
    from scripts.run_rmw_docker_quic_admission_probe import certificate_command
    from scripts.run_rmw_docker_quic_postgres_failover_probe import (
        postgres_service_ok,
    )
    from scripts.run_rmw_docker_quic_postgres_replication_failover_probe import (
        DATABASE_PASSWORD,
        PRIMARY_ALIAS,
        STANDBY_ALIAS,
        active_failure_service_ok,
        phase_evidence,
        replication_checkpoint,
        service_command,
        sql,
        standby_service_ok,
        start_gateway,
        start_replication_cluster,
        wait_container_stopped,
        wait_postgres,
    )
    from scripts.run_rmw_docker_quic_stateful_gateway_probe import (
        DEFAULT_IMAGE,
        json_rows,
        run,
        wait_service_ready,
    )
    from scripts.run_rmw_docker_quic_writer_fencing_probe import (
        run_client,
        stop_service,
    )
except ModuleNotFoundError:
    from run_rmw_docker_quic_admission_probe import certificate_command
    from run_rmw_docker_quic_postgres_failover_probe import postgres_service_ok
    from run_rmw_docker_quic_postgres_replication_failover_probe import (
        DATABASE_PASSWORD,
        PRIMARY_ALIAS,
        STANDBY_ALIAS,
        active_failure_service_ok,
        phase_evidence,
        replication_checkpoint,
        service_command,
        sql,
        standby_service_ok,
        start_gateway,
        start_replication_cluster,
        wait_container_stopped,
        wait_postgres,
    )
    from run_rmw_docker_quic_stateful_gateway_probe import (
        DEFAULT_IMAGE,
        json_rows,
        run,
        wait_service_ready,
    )
    from run_rmw_docker_quic_writer_fencing_probe import run_client, stop_service


ROOT = Path(__file__).resolve().parents[1]
SCHEMA_VERSION = "fleetrmw.docker_quic_postgresql_quorum_failover_probe.v1"
CONTROLLER_SCHEMA_VERSION = "fleetrmw.postgresql_failover_controller.v1"
FENCE_SCHEMA_VERSION = "fleetrmw.postgresql_fence_agent.v1"
FAILBACK_CONTROLLER_SCHEMA_VERSION = "fleetrmw.postgresql_failback_controller.v1"
SWITCHOVER_AGENT_SCHEMA_VERSION = "fleetrmw.postgresql_switchover_agent.v1"
ETCD_IMAGE = "quay.io/coreos/etcd:v3.5.17"
ETCD_ALIASES = ("fleetqox-etcd1", "fleetqox-etcd2", "fleetqox-etcd3")
FENCE_AGENT_ALIAS = "fleetqox-fence-agent"
FENCE_AGENT_PORT = 4510
SWITCHOVER_AGENT_ALIAS = "fleetqox-switchover-agent"
SWITCHOVER_AGENT_PORT = 4511
FAILBACK_LEASE_KEY = "/fleetqox/postgresql/failback"
REJOIN_APPLICATION = "fleetqox_rejoined_primary"
REJOIN_SLOT = "fleetqox_rejoined_primary_slot"
POST_FAILBACK_APPLICATION = "fleetqox_post_failback_standby"
POST_FAILBACK_SLOT = "fleetqox_post_failback_standby_slot"


def etcd_endpoints(count: int = 3) -> str:
    return ",".join(f"https://{name}:2379" for name in ETCD_ALIASES[:count])


def etcd_certificate_command(certs: Path, root: Path) -> str:
    prefix = f"/work/{certs.relative_to(root)}"
    sans = ",".join(f"DNS:{name}" for name in ETCD_ALIASES)
    return (
        "openssl req -x509 -newkey rsa:2048 -nodes "
        f"-keyout {prefix}/ca.key -out {prefix}/ca.crt "
        "-subj /CN=FleetQoX-etcd-CA "
        "-addext basicConstraints=critical,CA:TRUE "
        "-addext keyUsage=critical,keyCertSign,cRLSign -days 1 >/dev/null 2>&1 && "
        "openssl req -new -newkey rsa:2048 -nodes "
        f"-keyout {prefix}/server.key -out {prefix}/server.csr "
        "-subj /CN=fleetqox-etcd "
        f"-addext subjectAltName={sans} "
        "-addext extendedKeyUsage=serverAuth,clientAuth >/dev/null 2>&1 && "
        f"openssl x509 -req -in {prefix}/server.csr -CA {prefix}/ca.crt "
        f"-CAkey {prefix}/ca.key -CAcreateserial -out {prefix}/server.crt "
        "-days 1 -copy_extensions copy >/dev/null 2>&1 && "
        "openssl req -new -newkey rsa:2048 -nodes "
        f"-keyout {prefix}/client.key -out {prefix}/client.csr "
        "-subj /CN=fleetqox-failover-controller "
        "-addext extendedKeyUsage=clientAuth >/dev/null 2>&1 && "
        f"openssl x509 -req -in {prefix}/client.csr -CA {prefix}/ca.crt "
        f"-CAkey {prefix}/ca.key -CAcreateserial -out {prefix}/client.crt "
        "-days 1 -copy_extensions copy >/dev/null 2>&1 && "
        "openssl req -new -newkey rsa:2048 -nodes "
        f"-keyout {prefix}/fence-server.key -out {prefix}/fence-server.csr "
        f"-subj /CN={FENCE_AGENT_ALIAS} "
        f"-addext subjectAltName=DNS:{FENCE_AGENT_ALIAS},IP:127.0.0.1 "
        "-addext extendedKeyUsage=serverAuth >/dev/null 2>&1 && "
        f"openssl x509 -req -in {prefix}/fence-server.csr "
        f"-CA {prefix}/ca.crt -CAkey {prefix}/ca.key -CAcreateserial "
        f"-out {prefix}/fence-server.crt -days 1 -copy_extensions copy "
        ">/dev/null 2>&1 && "
        "openssl req -new -newkey rsa:2048 -nodes "
        f"-keyout {prefix}/switchover-server.key "
        f"-out {prefix}/switchover-server.csr "
        f"-subj /CN={SWITCHOVER_AGENT_ALIAS} "
        f"-addext subjectAltName=DNS:{SWITCHOVER_AGENT_ALIAS},IP:127.0.0.1 "
        "-addext extendedKeyUsage=serverAuth >/dev/null 2>&1 && "
        f"openssl x509 -req -in {prefix}/switchover-server.csr "
        f"-CA {prefix}/ca.crt -CAkey {prefix}/ca.key -CAcreateserial "
        f"-out {prefix}/switchover-server.crt -days 1 -copy_extensions copy "
        ">/dev/null 2>&1 && "
        "for id in controller-1 controller-2 "
        "failback-controller-1 failback-controller-2; do "
        "openssl req -new -newkey rsa:2048 -nodes "
        f"-keyout {prefix}/$id.key -out {prefix}/$id.csr "
        "-subj /CN=$id -addext extendedKeyUsage=clientAuth "
        ">/dev/null 2>&1 && "
        f"openssl x509 -req -in {prefix}/$id.csr -CA {prefix}/ca.crt "
        f"-CAkey {prefix}/ca.key -CAcreateserial -out {prefix}/$id.crt "
        "-days 1 -copy_extensions copy >/dev/null 2>&1 || exit 1; "
        "done"
    )


def etcdctl_tls_args() -> list[str]:
    return [
        "--cacert=/certs/ca.crt",
        "--cert=/certs/client.crt",
        "--key=/certs/client.key",
    ]


def start_etcd_cluster(
    *, root: Path, certs: Path, network: str, names: tuple[str, str, str]
) -> dict[str, Any]:
    initial_cluster = ",".join(
        f"etcd{index}=https://{alias}:2380"
        for index, alias in enumerate(ETCD_ALIASES, 1)
    )
    starts = []
    for index, (name, alias) in enumerate(zip(names, ETCD_ALIASES), 1):
        starts.append(
            run([
                "docker", "run", "-d", "--name", name,
                "--network", network, "--network-alias", alias,
                "-v", f"{certs}:/certs:ro",
                ETCD_IMAGE, "/usr/local/bin/etcd",
                "--name", f"etcd{index}", "--data-dir", "/etcd-data",
                "--listen-client-urls", "https://0.0.0.0:2379",
                "--advertise-client-urls", f"https://{alias}:2379",
                "--listen-peer-urls", "https://0.0.0.0:2380",
                "--initial-advertise-peer-urls", f"https://{alias}:2380",
                "--cert-file", "/certs/server.crt",
                "--key-file", "/certs/server.key",
                "--trusted-ca-file", "/certs/ca.crt",
                "--client-cert-auth=true",
                "--peer-cert-file", "/certs/server.crt",
                "--peer-key-file", "/certs/server.key",
                "--peer-trusted-ca-file", "/certs/ca.crt",
                "--peer-client-cert-auth=true",
                "--initial-cluster", initial_cluster,
                "--initial-cluster-state", "new",
            ])
        )
    healthy = False
    unauthenticated_client_rejected = False
    status_rows: list[dict[str, Any]] = []
    if all(result.returncode == 0 for result in starts):
        deadline = time.monotonic() + 15.0
        while time.monotonic() < deadline:
            health = run([
                "docker", "exec", names[0], "/usr/local/bin/etcdctl",
                *etcdctl_tls_args(),
                f"--endpoints={etcd_endpoints()}", "endpoint", "health",
            ])
            if health.returncode == 0:
                healthy = True
                break
            time.sleep(0.2)
        if healthy:
            status = run([
                "docker", "exec", names[0], "/usr/local/bin/etcdctl",
                *etcdctl_tls_args(),
                "--write-out=json", f"--endpoints={etcd_endpoints()}",
                "endpoint", "status",
            ])
            try:
                parsed = json.loads(status.stdout)
            except json.JSONDecodeError:
                parsed = []
            if isinstance(parsed, list):
                status_rows = [row for row in parsed if isinstance(row, dict)]
            unauthenticated = run([
                "docker", "exec", names[0], "/usr/local/bin/etcdctl",
                "--cacert=/certs/ca.crt",
                f"--endpoints={etcd_endpoints()}", "endpoint", "health",
            ])
            unauthenticated_client_rejected = unauthenticated.returncode != 0
    cluster_ids = {
        str(row.get("Status", {}).get("header", {}).get("cluster_id", ""))
        for row in status_rows
    }
    leaders = {
        str(row.get("Status", {}).get("leader", "")) for row in status_rows
    }
    valid = (
        healthy and unauthenticated_client_rejected
        and len(status_rows) == 3 and len(cluster_ids) == 1
        and "" not in cluster_ids and len(leaders) == 1 and "0" not in leaders
    )
    return {
        "status": "ok" if valid else "failed",
        "image": ETCD_IMAGE,
        "member_count": len(status_rows),
        "healthy_member_count": len(status_rows) if healthy else 0,
        "cluster_id": next(iter(cluster_ids), ""),
        "leader_id": next(iter(leaders), ""),
        "raft_consensus": valid,
        "mutual_tls": valid,
        "unauthenticated_client_rejected": unauthenticated_client_rejected,
        "start_returncodes": [result.returncode for result in starts],
        "members": status_rows,
    }


def wait_two_member_quorum(member: str, timeout_s: float = 15.0) -> bool:
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        result = run([
            "docker", "exec", member, "/usr/local/bin/etcdctl",
            *etcdctl_tls_args(),
            f"--endpoints={etcd_endpoints(2)}", "endpoint", "health",
        ])
        if result.returncode == 0:
            return True
        time.sleep(0.2)
    return False


def start_controller(
    *, root: Path, certs: Path, image: str, network: str, name: str,
    controller_id: str,
) -> bool:
    controller_certificate = certs / f"{controller_id}.crt"
    controller_key = certs / f"{controller_id}.key"
    primary_dsn = (
        f"postgresql://postgres:{DATABASE_PASSWORD}@{PRIMARY_ALIAS}:5432/fleetqox"
    )
    standby_dsn = (
        f"postgresql://postgres:{DATABASE_PASSWORD}@{STANDBY_ALIAS}:5432/fleetqox"
    )
    started = run([
        "docker", "run", "-d", "--name", name, "--network", network,
        "--entrypoint", "python3", "-v", f"{root}:/work", "-w", "/work",
        image, "scripts/fleetqox_postgres_failover_controller.py",
        "--controller-id", controller_id,
        "--primary-dsn", primary_dsn, "--standby-dsn", standby_dsn,
        "--etcd-endpoints", etcd_endpoints(),
        "--etcd-ca", f"/work/{(certs / 'ca.crt').relative_to(root)}",
        "--etcd-cert", f"/work/{controller_certificate.relative_to(root)}",
        "--etcd-key", f"/work/{controller_key.relative_to(root)}",
        "--fence-url", f"https://{FENCE_AGENT_ALIAS}:{FENCE_AGENT_PORT}/fence",
        "--fence-ca", f"/work/{(certs / 'ca.crt').relative_to(root)}",
        "--fence-cert", f"/work/{controller_certificate.relative_to(root)}",
        "--fence-key", f"/work/{controller_key.relative_to(root)}",
        "--failure-threshold", "3", "--poll-ms", "100",
        "--dcs-timeout-ms", "500", "--max-runtime-ms", "30000",
    ])
    if started.returncode != 0:
        return False
    deadline = time.monotonic() + 5.0
    while time.monotonic() < deadline:
        logs = run(["docker", "logs", name]).stdout
        if '"status": "monitoring"' in logs:
            return True
        inspected = run(
            ["docker", "inspect", "-f", "{{.State.Running}}", name]
        )
        if inspected.returncode != 0 or inspected.stdout.strip() != "true":
            return False
        time.sleep(0.1)
    return False


def start_fence_agent(
    *, root: Path, certs: Path, image: str, network: str, name: str,
    primary: str,
) -> bool:
    started = run([
        "docker", "run", "-d", "--name", name, "--network", network,
        "--network-alias", FENCE_AGENT_ALIAS,
        "--entrypoint", "python3", "-v", f"{root}:/work",
        "-v", "/var/run/docker.sock:/var/run/docker.sock", "-w", "/work",
        image, "scripts/fleetqox_postgres_fence_agent.py",
        "--port", str(FENCE_AGENT_PORT), "--target-container", primary,
        "--tls-ca", f"/work/{(certs / 'ca.crt').relative_to(root)}",
        "--tls-cert", f"/work/{(certs / 'fence-server.crt').relative_to(root)}",
        "--tls-key", f"/work/{(certs / 'fence-server.key').relative_to(root)}",
        "--etcd-endpoints", etcd_endpoints(),
        "--etcd-ca", f"/work/{(certs / 'ca.crt').relative_to(root)}",
        "--etcd-cert", f"/work/{(certs / 'client.crt').relative_to(root)}",
        "--etcd-key", f"/work/{(certs / 'client.key').relative_to(root)}",
    ])
    if started.returncode != 0:
        return False
    deadline = time.monotonic() + 5.0
    while time.monotonic() < deadline:
        logs = run(["docker", "logs", name]).stdout
        if '"status": "ready"' in logs:
            return True
        inspected = run(
            ["docker", "inspect", "-f", "{{.State.Running}}", name]
        )
        if inspected.returncode != 0 or inspected.stdout.strip() != "true":
            return False
        time.sleep(0.1)
    return False


def start_switchover_agent(
    *, root: Path, certs: Path, image: str, network: str, name: str,
    current_primary: str,
) -> bool:
    started = run([
        "docker", "run", "-d", "--name", name, "--network", network,
        "--network-alias", SWITCHOVER_AGENT_ALIAS,
        "--entrypoint", "python3", "-v", f"{root}:/work",
        "-v", "/var/run/docker.sock:/var/run/docker.sock", "-w", "/work",
        image, "scripts/fleetqox_postgres_switchover_agent.py",
        "--port", str(SWITCHOVER_AGENT_PORT),
        "--target-container", current_primary,
        "--tls-ca", f"/work/{(certs / 'ca.crt').relative_to(root)}",
        "--tls-cert",
        f"/work/{(certs / 'switchover-server.crt').relative_to(root)}",
        "--tls-key",
        f"/work/{(certs / 'switchover-server.key').relative_to(root)}",
        "--etcd-endpoints", etcd_endpoints(),
        "--etcd-ca", f"/work/{(certs / 'ca.crt').relative_to(root)}",
        "--etcd-cert", f"/work/{(certs / 'client.crt').relative_to(root)}",
        "--etcd-key", f"/work/{(certs / 'client.key').relative_to(root)}",
        "--lease-key", FAILBACK_LEASE_KEY,
    ])
    if started.returncode != 0:
        return False
    deadline = time.monotonic() + 5.0
    while time.monotonic() < deadline:
        logs = run(["docker", "logs", name]).stdout
        if '"status": "ready"' in logs:
            return True
        inspected = run([
            "docker", "inspect", "-f", "{{.State.Running}}", name
        ])
        if inspected.returncode != 0 or inspected.stdout.strip() != "true":
            return False
        time.sleep(0.1)
    return False


def start_failback_controller(
    *, root: Path, certs: Path, image: str, network: str, name: str,
    controller_id: str,
) -> bool:
    controller_certificate = certs / f"{controller_id}.crt"
    controller_key = certs / f"{controller_id}.key"
    current_primary_dsn = (
        f"postgresql://postgres:{DATABASE_PASSWORD}@{STANDBY_ALIAS}:5432/fleetqox"
    )
    target_standby_dsn = (
        f"postgresql://postgres:{DATABASE_PASSWORD}@{PRIMARY_ALIAS}:5432/fleetqox"
    )
    started = run([
        "docker", "run", "-d", "--name", name, "--network", network,
        "--entrypoint", "python3", "-v", f"{root}:/work", "-w", "/work",
        image, "scripts/fleetqox_postgres_failback_controller.py",
        "--controller-id", controller_id,
        "--current-primary-dsn", current_primary_dsn,
        "--target-standby-dsn", target_standby_dsn,
        "--replication-application", REJOIN_APPLICATION,
        "--etcd-endpoints", etcd_endpoints(),
        "--etcd-ca", f"/work/{(certs / 'ca.crt').relative_to(root)}",
        "--etcd-cert", f"/work/{controller_certificate.relative_to(root)}",
        "--etcd-key", f"/work/{controller_key.relative_to(root)}",
        "--lease-key", FAILBACK_LEASE_KEY,
        "--switchover-url",
        f"https://{SWITCHOVER_AGENT_ALIAS}:{SWITCHOVER_AGENT_PORT}/switchover",
        "--switchover-ca", f"/work/{(certs / 'ca.crt').relative_to(root)}",
        "--switchover-cert",
        f"/work/{controller_certificate.relative_to(root)}",
        "--switchover-key", f"/work/{controller_key.relative_to(root)}",
        "--safe-sample-threshold", "3", "--poll-ms", "100",
        "--dcs-timeout-ms", "500", "--max-runtime-ms", "30000",
    ])
    if started.returncode != 0:
        return False
    deadline = time.monotonic() + 5.0
    while time.monotonic() < deadline:
        logs = run(["docker", "logs", name]).stdout
        if '"status": "monitoring"' in logs:
            return True
        inspected = run([
            "docker", "inspect", "-f", "{{.State.Running}}", name
        ])
        if inspected.returncode != 0 or inspected.stdout.strip() != "true":
            return False
        time.sleep(0.1)
    return False


def fence_security_negative_controls(
    name: str, primary: str, *, root: Path, certs: Path
) -> dict[str, bool]:
    ca = f"/work/{(certs / 'ca.crt').relative_to(root)}"
    cert = f"/work/{(certs / 'controller-1.crt').relative_to(root)}"
    key = f"/work/{(certs / 'controller-1.key').relative_to(root)}"
    unauthenticated_script = (
        "import json,ssl,urllib.error,urllib.request;"
        f"c=ssl.create_default_context(cafile={ca!r});"
        "r=urllib.request.Request('https://127.0.0.1:4510/fence',"
        "data=json.dumps({'controller_id':'controller-1',"
        "'lease_id':'-1'}).encode(),headers={'content-type':'application/json'},"
        "method='POST');"
        "\ntry: urllib.request.urlopen(r,timeout=2,context=c); raise SystemExit(1)"
        "\nexcept Exception: raise SystemExit(0)"
    )
    unauthenticated = run([
        "docker", "exec", name, "python3", "-c", unauthenticated_script
    ])
    forged_lease_script = (
        "import json,ssl,urllib.error,urllib.request;"
        f"c=ssl.create_default_context(cafile={ca!r});"
        f"c.load_cert_chain(certfile={cert!r},keyfile={key!r});"
        "r=urllib.request.Request('https://127.0.0.1:4510/fence',"
        "data=json.dumps({'controller_id':'controller-1',"
        "'lease_id':'-1'}).encode(),headers={'content-type':'application/json'},"
        "method='POST');"
        "\ntry: urllib.request.urlopen(r,timeout=2,context=c); raise SystemExit(1)"
        "\nexcept urllib.error.HTTPError as e: raise SystemExit(0 if e.code==403 else 1)"
    )
    forged = run([
        "docker", "exec", name, "python3", "-c", forged_lease_script
    ])
    running = run([
        "docker", "inspect", "-f", "{{.State.Running}}", primary
    ])
    return {
        "unauthenticated_client_rejected": unauthenticated.returncode == 0,
        "authenticated_forged_lease_rejected": forged.returncode == 0,
        "primary_remained_running": (
            running.returncode == 0 and running.stdout.strip() == "true"
        ),
    }


def switchover_security_negative_controls(
    name: str, current_primary: str, *, root: Path, certs: Path,
) -> dict[str, bool]:
    ca = f"/work/{(certs / 'ca.crt').relative_to(root)}"
    cert = (
        f"/work/{(certs / 'failback-controller-1.crt').relative_to(root)}"
    )
    key = f"/work/{(certs / 'failback-controller-1.key').relative_to(root)}"
    unauthenticated_script = (
        "import json,ssl,urllib.request;"
        f"c=ssl.create_default_context(cafile={ca!r});"
        "r=urllib.request.Request('https://127.0.0.1:4511/switchover',"
        "data=json.dumps({'controller_id':'failback-controller-1',"
        "'lease_id':'-1'}).encode(),headers={'content-type':'application/json'},"
        "method='POST');"
        "\ntry: urllib.request.urlopen(r,timeout=2,context=c); raise SystemExit(1)"
        "\nexcept Exception: raise SystemExit(0)"
    )
    unauthenticated = run([
        "docker", "exec", name, "python3", "-c", unauthenticated_script
    ])
    forged_lease_script = (
        "import json,ssl,urllib.error,urllib.request;"
        f"c=ssl.create_default_context(cafile={ca!r});"
        f"c.load_cert_chain(certfile={cert!r},keyfile={key!r});"
        "r=urllib.request.Request('https://127.0.0.1:4511/switchover',"
        "data=json.dumps({'controller_id':'failback-controller-1',"
        "'lease_id':'-1'}).encode(),headers={'content-type':'application/json'},"
        "method='POST');"
        "\ntry: urllib.request.urlopen(r,timeout=2,context=c); raise SystemExit(1)"
        "\nexcept urllib.error.HTTPError as e: "
        "raise SystemExit(0 if e.code==403 else 1)"
    )
    forged = run([
        "docker", "exec", name, "python3", "-c", forged_lease_script
    ])
    running = run([
        "docker", "inspect", "-f", "{{.State.Running}}", current_primary
    ])
    return {
        "unauthenticated_client_rejected": unauthenticated.returncode == 0,
        "authenticated_forged_lease_rejected": forged.returncode == 0,
        "current_primary_remained_running": (
            running.returncode == 0 and running.stdout.strip() == "true"
        ),
    }


def collect_fence_agent(name: str) -> dict[str, Any]:
    logs = run(["docker", "logs", name]).stdout
    events = [
        row for row in json_rows(logs)
        if row.get("schema_version") == FENCE_SCHEMA_VERSION
        and row.get("status") != "ready"
    ]
    final = events[-1] if events else {}
    return {
        "status": "ok" if len(events) == 1 and final else "failed",
        "event_count": len(events),
        "telemetry": final,
        "logs": "" if len(events) == 1 and final else logs[-4000:],
    }


def collect_switchover_agent(name: str) -> dict[str, Any]:
    logs = run(["docker", "logs", name]).stdout
    events = [
        row for row in json_rows(logs)
        if row.get("schema_version") == SWITCHOVER_AGENT_SCHEMA_VERSION
        and row.get("status") != "ready"
    ]
    final = events[-1] if events else {}
    return {
        "status": "ok" if len(events) == 1 and final else "failed",
        "event_count": len(events),
        "telemetry": final,
        "logs": "" if len(events) == 1 and final else logs[-4000:],
    }


def wait_controllers_quorum_blocked(
    names: tuple[str, str], timeout_s: float = 10.0
) -> bool:
    return wait_controllers_event(names, "quorum_unavailable", timeout_s)


def wait_controllers_event(
    names: tuple[str, str], status: str, timeout_s: float = 10.0,
) -> bool:
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        if all(
            f'"status": "{status}"'
            in run(["docker", "logs", name]).stdout
            for name in names
        ):
            return True
        time.sleep(0.1)
    return False


def configure_failback_replication_mode(
    source: str, *, synchronous: bool,
) -> dict[str, Any]:
    configured = sql(
        source,
        (
            "ALTER SYSTEM SET synchronous_standby_names = "
            f"'{REJOIN_APPLICATION}'"
            if synchronous
            else "ALTER SYSTEM RESET synchronous_standby_names"
        ),
    )
    reloaded = (
        sql(source, "SELECT pg_reload_conf()")
        if configured.returncode == 0
        else subprocess.CompletedProcess([], 1, "", "configuration_failed")
    )
    expected = "sync" if synchronous else "async"
    replication_row = ""
    if reloaded.returncode == 0:
        deadline = time.monotonic() + 10.0
        while time.monotonic() < deadline:
            status = sql(
                source,
                "SELECT state || '|' || sync_state || '|' || "
                "COALESCE(pg_wal_lsn_diff(pg_current_wal_flush_lsn(), "
                "replay_lsn)::bigint, -1) FROM pg_stat_replication WHERE "
                f"application_name='{REJOIN_APPLICATION}'",
            )
            replication_row = status.stdout.strip()
            parts = replication_row.split("|")
            if (
                len(parts) == 3
                and parts[:2] == ["streaming", expected]
                and parts[2].lstrip("-").isdigit()
                and (not synchronous or parts[2] == "0")
            ):
                break
            time.sleep(0.2)
    parts = replication_row.split("|")
    valid = (
        configured.returncode == reloaded.returncode == 0
        and len(parts) == 3
        and parts[:2] == ["streaming", expected]
        and parts[2].lstrip("-").isdigit()
        and (not synchronous or parts[2] == "0")
    )
    return {
        "status": "ok" if valid else "failed",
        "requested_mode": expected,
        "replication_status": replication_row,
        "replay_gap_bytes": int(parts[2]) if valid else None,
    }


def inject_primary_partition(image: str, primary: str) -> subprocess.CompletedProcess[str]:
    return run([
        "docker", "run", "--rm", "--network", f"container:{primary}",
        "--cap-add", "NET_ADMIN", "--entrypoint", "bash", image, "-lc",
        "tc qdisc replace dev eth0 root netem loss 100% && "
        "tc qdisc show dev eth0",
    ])


def rejoin_fenced_primary_as_standby(
    *, primary: str, source: str, network: str, postgres_image: str,
    suffix: str,
) -> dict[str, Any]:
    bootstrap_name = f"fleetrmw-pg-rejoin-bootstrap-{suffix}"
    target_pgdata = "/var/lib/postgresql/data"
    bootstrap = (
        "find \"$PGDATA\" -mindepth 1 -maxdepth 1 -exec rm -rf -- {} + && "
        "chown -R postgres:postgres \"$PGDATA\" && "
        "exec gosu postgres pg_basebackup "
        f"-d \"host={STANDBY_ALIAS} port=5432 user=replicator "
        f"password={DATABASE_PASSWORD} application_name={REJOIN_APPLICATION}\" "
        "-D \"$PGDATA\" -Fp -Xs -P -R -c fast "
        f"-C -S {REJOIN_SLOT}"
    )
    rebuilt = run([
        "docker", "run", "--rm", "--name", bootstrap_name,
        "--network", network, "--volumes-from", f"{primary}:rw",
        "-e", f"PGDATA={target_pgdata}", "--entrypoint", "sh",
        postgres_image, "-c", bootstrap,
    ])
    restarted = (
        run(["docker", "start", primary])
        if rebuilt.returncode == 0
        else subprocess.CompletedProcess([], 1, "", "rebuild_failed")
    )
    target_ready = restarted.returncode == 0 and wait_postgres(primary, timeout_s=15.0)
    target_recovery = (
        sql(primary, "SELECT pg_is_in_recovery()")
        if target_ready
        else subprocess.CompletedProcess([], 1, "", "target_not_ready")
    )
    streaming_row = ""
    if target_recovery.returncode == 0 and target_recovery.stdout.strip() == "t":
        deadline = time.monotonic() + 10.0
        while time.monotonic() < deadline:
            streaming = sql(
                source,
                "SELECT application_name || '|' || state FROM pg_stat_replication "
                f"WHERE application_name='{REJOIN_APPLICATION}'",
            )
            streaming_row = streaming.stdout.strip()
            if streaming.returncode == 0 and streaming_row == (
                f"{REJOIN_APPLICATION}|streaming"
            ):
                break
            time.sleep(0.2)
    configured = sql(
        source,
        "ALTER SYSTEM SET synchronous_standby_names = "
        f"'{REJOIN_APPLICATION}'",
    ) if streaming_row == f"{REJOIN_APPLICATION}|streaming" else (
        subprocess.CompletedProcess([], 1, "", "standby_not_streaming")
    )
    reloaded = (
        sql(source, "SELECT pg_reload_conf()")
        if configured.returncode == 0
        else subprocess.CompletedProcess([], 1, "", "sync_not_configured")
    )
    sync_row = ""
    if reloaded.returncode == 0:
        deadline = time.monotonic() + 10.0
        while time.monotonic() < deadline:
            status = sql(
                source,
                "SELECT application_name || '|' || state || '|' || sync_state || "
                "'|' || COALESCE(pg_wal_lsn_diff(flush_lsn, '0/0')::text, '') || "
                "'|' || COALESCE(pg_wal_lsn_diff(replay_lsn, '0/0')::text, '') "
                "FROM pg_stat_replication WHERE application_name="
                f"'{REJOIN_APPLICATION}'",
            )
            sync_row = status.stdout.strip()
            parts = sync_row.split("|")
            if (
                status.returncode == 0 and len(parts) == 5
                and parts[:3] == [REJOIN_APPLICATION, "streaming", "sync"]
                and parts[3].isdigit() and parts[4].isdigit()
                and int(parts[3]) > 0 and int(parts[4]) > 0
            ):
                break
            time.sleep(0.2)
    source_recovery = sql(source, "SELECT pg_is_in_recovery()")
    recovered = (
        sql(
            primary,
            "SELECT (SELECT COUNT(*) FROM frames) || '|' || "
            "(SELECT COUNT(*) FROM admission_state)",
        )
        if target_ready else subprocess.CompletedProcess([], 1, "", "target_not_ready")
    )
    parts = sync_row.split("|")
    valid_sync = (
        len(parts) == 5
        and parts[:3] == [REJOIN_APPLICATION, "streaming", "sync"]
        and parts[3].isdigit() and parts[4].isdigit()
        and int(parts[3]) > 0 and int(parts[4]) > 0
    )
    valid = (
        rebuilt.returncode == restarted.returncode == 0
        and target_ready
        and target_recovery.returncode == 0
        and target_recovery.stdout.strip() == "t"
        and source_recovery.returncode == 0
        and source_recovery.stdout.strip() == "f"
        and configured.returncode == reloaded.returncode == 0
        and valid_sync
        and recovered.returncode == 0
        and recovered.stdout.strip() == "2|1"
    )
    return {
        "status": "ok" if valid else "failed",
        "method": "fresh_physical_basebackup_with_dedicated_slot",
        "bootstrap_returncode": rebuilt.returncode,
        "bootstrap_stderr": rebuilt.stderr[-3000:],
        "restart_returncode": restarted.returncode,
        "target_ready": target_ready,
        "target_in_recovery": target_recovery.stdout.strip() == "t",
        "source_read_write": source_recovery.stdout.strip() == "f",
        "replication_status": sync_row,
        "flush_lsn_bytes": int(parts[3]) if valid_sync else 0,
        "replay_lsn_bytes": int(parts[4]) if valid_sync else 0,
        "recovered_frame_count": 2 if recovered.stdout.strip() == "2|1" else 0,
        "recovered_admission_state_count": (
            1 if recovered.stdout.strip() == "2|1" else 0
        ),
        "old_primary_role_after_rejoin": "synchronous_read_only_standby",
    }


def restore_post_failback_standby(
    *, source: str, standby: str, network: str, postgres_image: str,
) -> dict[str, Any]:
    removed = run(["docker", "rm", "-f", standby])
    target_pgdata = "/var/lib/postgresql/data/pgdata"
    bootstrap = (
        "mkdir -p \"$PGDATA\" && "
        "chown -R postgres:postgres /var/lib/postgresql/data && "
        "gosu postgres pg_basebackup "
        f"-d \"host={PRIMARY_ALIAS} port=5432 user=replicator "
        f"password={DATABASE_PASSWORD} "
        f"application_name={POST_FAILBACK_APPLICATION}\" "
        "-D \"$PGDATA\" -Fp -Xs -P -R -c fast "
        f"-C -S {POST_FAILBACK_SLOT} && "
        "chmod 700 \"$PGDATA\" && "
        "exec gosu postgres postgres -D \"$PGDATA\" -c hot_standby=on"
    )
    started = run([
        "docker", "run", "-d", "--name", standby,
        "--network", network, "--network-alias", STANDBY_ALIAS,
        "-e", f"PGDATA={target_pgdata}",
        "-e", f"PGPASSWORD={DATABASE_PASSWORD}",
        "--entrypoint", "sh", postgres_image, "-c", bootstrap,
    ])
    ready = started.returncode == 0 and wait_postgres(standby, timeout_s=15.0)
    target_recovery = (
        sql(standby, "SELECT pg_is_in_recovery()")
        if ready else subprocess.CompletedProcess([], 1, "", "target_not_ready")
    )
    streaming_row = ""
    if target_recovery.returncode == 0 and target_recovery.stdout.strip() == "t":
        deadline = time.monotonic() + 10.0
        while time.monotonic() < deadline:
            streaming = sql(
                source,
                "SELECT application_name || '|' || state FROM pg_stat_replication "
                f"WHERE application_name='{POST_FAILBACK_APPLICATION}'",
            )
            streaming_row = streaming.stdout.strip()
            if streaming_row == f"{POST_FAILBACK_APPLICATION}|streaming":
                break
            time.sleep(0.2)
    configured = (
        sql(
            source,
            "ALTER SYSTEM SET synchronous_standby_names = "
            f"'{POST_FAILBACK_APPLICATION}'",
        )
        if streaming_row == f"{POST_FAILBACK_APPLICATION}|streaming"
        else subprocess.CompletedProcess([], 1, "", "standby_not_streaming")
    )
    reloaded = (
        sql(source, "SELECT pg_reload_conf()")
        if configured.returncode == 0
        else subprocess.CompletedProcess([], 1, "", "sync_not_configured")
    )
    sync_row = ""
    if reloaded.returncode == 0:
        deadline = time.monotonic() + 10.0
        while time.monotonic() < deadline:
            status = sql(
                source,
                "SELECT application_name || '|' || state || '|' || sync_state || "
                "'|' || COALESCE(pg_wal_lsn_diff(flush_lsn, '0/0')::text, '') || "
                "'|' || COALESCE(pg_wal_lsn_diff(replay_lsn, '0/0')::text, '') "
                "FROM pg_stat_replication WHERE application_name="
                f"'{POST_FAILBACK_APPLICATION}'",
            )
            sync_row = status.stdout.strip()
            parts = sync_row.split("|")
            if (
                len(parts) == 5
                and parts[:3] == [POST_FAILBACK_APPLICATION, "streaming", "sync"]
                and parts[3].isdigit() and parts[4].isdigit()
                and int(parts[3]) > 0 and int(parts[4]) > 0
            ):
                break
            time.sleep(0.2)
    recovered = (
        sql(
            standby,
            "SELECT (SELECT COUNT(*) FROM frames) || '|' || "
            "(SELECT COUNT(*) FROM admission_state)",
        )
        if ready else subprocess.CompletedProcess([], 1, "", "target_not_ready")
    )
    parts = sync_row.split("|")
    valid_sync = (
        len(parts) == 5
        and parts[:3] == [POST_FAILBACK_APPLICATION, "streaming", "sync"]
        and parts[3].isdigit() and parts[4].isdigit()
        and int(parts[3]) > 0 and int(parts[4]) > 0
    )
    valid = (
        removed.returncode == started.returncode == 0 and ready
        and target_recovery.returncode == 0
        and target_recovery.stdout.strip() == "t"
        and configured.returncode == reloaded.returncode == 0
        and valid_sync
        and recovered.returncode == 0 and recovered.stdout.strip() == "2|1"
    )
    logs = (
        run(["docker", "logs", standby]).stdout
        if started.returncode == 0 else ""
    )
    return {
        "status": "ok" if valid else "failed",
        "method": "fresh_post_failback_physical_standby",
        "old_container_remove_returncode": removed.returncode,
        "start_returncode": started.returncode,
        "start_stderr": started.stderr[-3000:],
        "container_logs": "" if valid else logs[-5000:],
        "target_ready": ready,
        "target_in_recovery": target_recovery.stdout.strip() == "t",
        "replication_status": sync_row,
        "flush_lsn_bytes": int(parts[3]) if valid_sync else 0,
        "replay_lsn_bytes": int(parts[4]) if valid_sync else 0,
        "recovered_frame_count": 2 if recovered.stdout.strip() == "2|1" else 0,
        "recovered_admission_state_count": (
            1 if recovered.stdout.strip() == "2|1" else 0
        ),
    }


def collect_controller(name: str) -> dict[str, Any]:
    wait_container_stopped(name, timeout_s=10.0)
    inspected = run(["docker", "inspect", "-f", "{{.State.ExitCode}}", name])
    exit_code = (
        int(inspected.stdout.strip())
        if inspected.returncode == 0 and inspected.stdout.strip() else -1
    )
    logs = run(["docker", "logs", name]).stdout
    rows = json_rows(logs)
    final = rows[-1] if rows else {}
    run(["docker", "rm", "-f", name])
    return {
        "status": "ok" if exit_code == 0 and final else "failed",
        "exit_code": exit_code,
        "telemetry": final,
        "monitoring_event_observed": any(
            row.get("status") == "monitoring" for row in rows
        ),
        "unsafe_preconditions_observed": any(
            row.get("status") == "unsafe_preconditions" for row in rows
        ),
        "logs": "" if exit_code == 0 and final else logs[-4000:],
    }


def controllers_ok(rows: list[dict[str, Any]]) -> bool:
    telemetry = [row.get("telemetry", {}) for row in rows]
    promoted = [row for row in telemetry if row.get("status") == "promoted"]
    observed = [
        row for row in telemetry if row.get("status") == "promotion_observed"
    ]
    return (
        len(rows) == 2
        and all(row.get("status") == "ok" for row in rows)
        and all(row.get("monitoring_event_observed") is True for row in rows)
        and len(promoted) == len(observed) == 1
        and promoted[0].get("schema_version") == CONTROLLER_SCHEMA_VERSION
        and promoted[0].get("dcs_lock_acquired") is True
        and bool(promoted[0].get("lease_id"))
        and bool(promoted[0].get("cluster_id"))
        and int(promoted[0].get("revision", 0)) > 0
        and promoted[0].get("primary_failures", 0) >= 3
        and all(row.get("quorum_acquisition_failures", 0) >= 1 for row in telemetry)
        and promoted[0].get("hard_fence_confirmed") is True
        and bool(promoted[0].get("fenced_container"))
        and int(promoted[0].get("fence_confirmed_unix_ns", 0)) > 0
        and int(promoted[0].get("promotion_confirmed_unix_ns", 0))
        >= int(promoted[0].get("fence_confirmed_unix_ns", 0))
        and observed[0].get("schema_version") == CONTROLLER_SCHEMA_VERSION
        and observed[0].get("dcs_lock_acquired") is False
    )


def failback_controllers_ok(rows: list[dict[str, Any]]) -> bool:
    telemetry = [row.get("telemetry", {}) for row in rows]
    winners = [row for row in telemetry if row.get("status") == "failed_back"]
    observed = [
        row for row in telemetry if row.get("status") == "failback_observed"
    ]
    return (
        len(rows) == 2
        and all(row.get("status") == "ok" for row in rows)
        and all(row.get("monitoring_event_observed") is True for row in rows)
        and all(row.get("unsafe_preconditions_observed") is True for row in rows)
        and len(winners) == len(observed) == 1
        and winners[0].get("schema_version")
        == FAILBACK_CONTROLLER_SCHEMA_VERSION
        and winners[0].get("policy") == "prefer-original-when-synchronous"
        and winners[0].get("dcs_lock_acquired") is True
        and bool(winners[0].get("lease_id"))
        and bool(winners[0].get("cluster_id"))
        and int(winners[0].get("revision", 0)) > 0
        and winners[0].get("safe_samples", 0) >= 3
        and winners[0].get("synchronous_replay_gap_bytes") == 0
        and winners[0].get("graceful_stop_confirmed") is True
        and winners[0].get("synchronous_standby_names_reset") is True
        and bool(winners[0].get("stopped_container"))
        and int(winners[0].get("source_stop_confirmed_unix_ns", 0)) > 0
        and int(winners[0].get("promotion_confirmed_unix_ns", 0))
        >= int(winners[0].get("source_stop_confirmed_unix_ns", 0))
        and all(
            row.get("quorum_acquisition_failures", 0) >= 1
            for row in telemetry
        )
        and observed[0].get("schema_version")
        == FAILBACK_CONTROLLER_SCHEMA_VERSION
        and observed[0].get("dcs_lock_acquired") is False
    )


def failback_service_ok(row: dict[str, Any]) -> bool:
    durable = row.get("metrics", {}).get("durable_state", {})
    endpoint = urlsplit(str(durable.get("endpoint", "")))
    return (
        postgres_service_ok(
            row, mode="resume", holder="gateway-c", token=3,
            automatic_wait=False, resume_requires_wait=False,
        )
        and durable.get("available") is True
        and durable.get("snapshot_stale") is False
        and durable.get("in_recovery") is False
        and endpoint.hostname == PRIMARY_ALIAS
    )


def case_ok(row: dict[str, Any]) -> bool:
    control = row.get("quorum_loss_control", {})
    failback_control = row.get("failback_quorum_loss_control", {})
    promotion = row.get("automatic_promotion", {})
    active = row.get("active", {})
    standby = row.get("standby", {})
    failback = row.get("failback", {})
    planned_failback = row.get("planned_failback", {})
    final_redundancy = row.get("post_failback_redundancy", {})
    fence_agent = row.get("fence_agent", {})
    fence = fence_agent.get("telemetry", {})
    switchover_agent = row.get("switchover_agent", {})
    switchover = switchover_agent.get("telemetry", {})
    promoted = [
        item.get("telemetry", {}) for item in row.get("controllers", [])
        if item.get("telemetry", {}).get("status") == "promoted"
    ]
    failed_back = [
        item.get("telemetry", {}) for item in row.get("failback_controllers", [])
        if item.get("telemetry", {}).get("status") == "failed_back"
    ]
    return (
        row.get("etcd_cluster", {}).get("status") == "ok"
        and row.get("etcd_cluster", {}).get("mutual_tls") is True
        and row.get("postgresql_cluster", {}).get("status") == "ok"
        and row.get("replication_before_failure", {}).get("status") == "ok"
        and row.get("standby_observed_waiting_while_primary_live") is True
        and row.get("unauthorized_fence_rejected_while_primary_running") is True
        and row.get("fence_security_negative_controls", {}).get(
            "unauthenticated_client_rejected"
        ) is True
        and row.get("fence_security_negative_controls", {}).get(
            "authenticated_forged_lease_rejected"
        ) is True
        and row.get("fence_security_negative_controls", {}).get(
            "primary_remained_running"
        ) is True
        and control.get("dcs_members_killed") == 2
        and control.get("primary_partition_returncode") == 0
        and control.get("primary_partition_fault")
        == "primary_network_namespace_egress_loss_100_percent"
        and control.get("primary_partition_netem_configured") is True
        and control.get("active_gateway_exited_on_database_loss") is True
        and control.get("primary_remained_running_without_quorum") is True
        and control.get("standby_remained_in_recovery_without_quorum") is True
        and control.get("gateway_standby_not_ready_without_quorum") is True
        and control.get("controllers_remained_running_without_quorum") is True
        and control.get("all_controllers_observed_quorum_unavailable") is True
        and control.get("quorum_restore_returncode") == 0
        and control.get("two_of_three_quorum_restored") is True
        and promotion.get("promoted_read_write") is True
        and promotion.get("promoted_by_exactly_one_controller") is True
        and promotion.get("primary_hard_fenced_after_quorum_restore") is True
        and fence_agent.get("status") == "ok"
        and fence_agent.get("event_count") == 1
        and fence.get("status") == "fenced"
        and fence.get("dcs_lease_authorized") is True
        and fence.get("mtls_client_authenticated") is True
        and fence.get("peer_common_name") == fence.get("controller_id")
        and fence.get("running_before") is True
        and fence.get("docker_kill_status") == 204
        and fence.get("running_after") is False
        and fence.get("hard_fence_confirmed") is True
        and fence.get("target_container")
        == control.get("partitioned_primary_container")
        and len(promoted) == 1
        and fence.get("controller_id") == promoted[0].get("controller_id")
        and fence.get("lease_id") == promoted[0].get("lease_id")
        and fence.get("target_container") == promoted[0].get("fenced_container")
        and int(fence.get("fence_confirmed_unix_ns", 0)) > 0
        and int(promoted[0].get("promotion_confirmed_unix_ns", 0))
        >= int(fence.get("fence_confirmed_unix_ns", 0))
        and controllers_ok(row.get("controllers", []))
        and 0 <= row.get("database_failure_to_gateway_ready_ms", -1) < 30000
        and active.get("status") == standby.get("status") == "ok"
        and active_failure_service_ok(active.get("service", {}))
        and standby_service_ok(standby.get("service", {}))
        and row.get("seeded_frames_recovered") is True
        and row.get("seeded_admission_state_recovered") is True
        and row.get("post_failover_rejoin", {}).get("status") == "ok"
        and row.get("post_failover_rejoin", {}).get("target_in_recovery") is True
        and row.get("post_failover_rejoin", {}).get("source_read_write") is True
        and row.get("post_failover_rejoin", {}).get("replication_status", "").endswith(
            "|streaming|sync|" + str(
                row.get("post_failover_rejoin", {}).get("flush_lsn_bytes", 0)
            ) + "|" + str(
                row.get("post_failover_rejoin", {}).get("replay_lsn_bytes", 0)
            )
        )
        and row.get("post_failover_rejoin", {}).get("flush_lsn_bytes", 0) > 0
        and row.get("post_failover_rejoin", {}).get("replay_lsn_bytes", 0) > 0
        and row.get("post_failover_rejoin", {}).get("recovered_frame_count") == 2
        and row.get("post_failover_rejoin", {}).get(
            "recovered_admission_state_count"
        ) == 1
        and failback_control.get("unsafe_replication_control", {}).get(
            "status"
        ) == "ok"
        and failback_control.get("unsafe_replication_control", {}).get(
            "requested_mode"
        ) == "async"
        and failback_control.get(
            "all_controllers_rejected_unsafe_replication"
        ) is True
        and failback_control.get(
            "database_roles_unchanged_while_unsafe"
        ) is True
        and failback_control.get("dcs_member_kill_returncode") == 0
        and failback_control.get(
            "synchronous_replication_restored_without_quorum", {}
        ).get("status") == "ok"
        and failback_control.get(
            "synchronous_replication_restored_without_quorum", {}
        ).get("requested_mode") == "sync"
        and failback_control.get(
            "synchronous_replication_restored_without_quorum", {}
        ).get("replay_gap_bytes") == 0
        and failback_control.get(
            "all_controllers_observed_quorum_unavailable"
        ) is True
        and failback_control.get(
            "database_roles_unchanged_without_quorum"
        ) is True
        and failback_control.get("quorum_restore_returncode") == 0
        and failback_control.get("two_of_three_quorum_restored") is True
        and all(row.get("switchover_security_negative_controls", {}).values())
        and failback_controllers_ok(row.get("failback_controllers", []))
        and len(failed_back) == 1
        and switchover_agent.get("status") == "ok"
        and switchover_agent.get("event_count") == 1
        and switchover.get("status") == "stopped"
        and switchover.get("dcs_lease_authorized") is True
        and switchover.get("mtls_client_authenticated") is True
        and switchover.get("peer_common_name")
        == switchover.get("controller_id")
        and switchover.get("controller_id") == failed_back[0].get("controller_id")
        and switchover.get("lease_id") == failed_back[0].get("lease_id")
        and switchover.get("target_container")
        == failed_back[0].get("stopped_container")
        and switchover.get("running_before") is True
        and switchover.get("docker_stop_status") == 204
        and switchover.get("running_after") is False
        and switchover.get("graceful_stop_confirmed") is True
        and int(switchover.get("stop_confirmed_unix_ns", 0)) > 0
        and int(failed_back[0].get("promotion_confirmed_unix_ns", 0))
        >= int(switchover.get("stop_confirmed_unix_ns", 0))
        and planned_failback.get("status") == "ok"
        and planned_failback.get("mode") == "automatic_policy_dcs_switchover"
        and planned_failback.get("policy") == "prefer-original-when-synchronous"
        and planned_failback.get("synchronous_replay_gap_bytes_before_stop") == 0
        and planned_failback.get("old_primary_in_recovery_before") is True
        and planned_failback.get("current_primary_read_write_before") is True
        and planned_failback.get("current_primary_stopped_before_promotion") is True
        and planned_failback.get("original_primary_read_write_after") is True
        and planned_failback.get("former_primary_running_after_promotion") is False
        and planned_failback.get("recovered_frame_count") == 2
        and planned_failback.get("recovered_admission_state_count") == 1
        and 0 <= row.get("planned_failback_to_gateway_ready_ms", -1) < 20000
        and failback.get("status") == "ok"
        and failback_service_ok(failback.get("service", {}))
        and final_redundancy.get("status") == "ok"
        and final_redundancy.get("target_in_recovery") is True
        and final_redundancy.get("flush_lsn_bytes", 0) > 0
        and final_redundancy.get("replay_lsn_bytes", 0) > 0
        and final_redundancy.get("recovered_frame_count") == 2
        and final_redundancy.get("recovered_admission_state_count") == 1
        and row.get("postgresql_shutdown_returncodes") == [0, 0]
        and row.get("etcd_shutdown_returncodes") == [0, 0, 0]
        and row.get("fence_agent_shutdown_returncode") == 0
        and row.get("switchover_agent_shutdown_returncode") == 0
    )


def run_case(
    *, root: Path, image: str, network: str, install: str,
    temp_root: Path, index: int,
) -> dict[str, Any]:
    suffix = f"{os.getpid()}-{index}"
    etcd_names = tuple(f"fleetrmw-etcd{n}-{suffix}" for n in range(1, 4))
    primary = f"fleetrmw-quorum-primary-{suffix}"
    replica = f"fleetrmw-quorum-replica-{suffix}"
    active_name = f"fleetrmw-quorum-gateway-a-{suffix}"
    standby_name = f"fleetrmw-quorum-gateway-b-{suffix}"
    failback_name = f"fleetrmw-quorum-gateway-c-{suffix}"
    fence_agent_name = f"fleetrmw-pg-fence-agent-{suffix}"
    switchover_agent_name = f"fleetrmw-pg-switchover-agent-{suffix}"
    controller_names = (
        f"fleetrmw-pg-controller-a-{suffix}",
        f"fleetrmw-pg-controller-b-{suffix}",
    )
    failback_controller_names = (
        f"fleetrmw-pg-failback-controller-a-{suffix}",
        f"fleetrmw-pg-failback-controller-b-{suffix}",
    )
    case_root = temp_root / f"run-{index}"
    certs = temp_root / "certs"
    etcd_certs = temp_root / "etcd-certs"
    qlogs = {
        key: case_root / key
        for key in (
            "active-service-qlogs", "active-client-qlogs",
            "standby-service-qlogs", "standby-client-qlogs",
            "failback-service-qlogs", "failback-client-qlogs",
        )
    }
    for path in qlogs.values():
        path.mkdir(parents=True, exist_ok=True)
    etcd = start_etcd_cluster(
        root=root, certs=etcd_certs, network=network, names=etcd_names
    )
    postgres = (
        start_replication_cluster(network=network, primary=primary, standby=replica)
        if etcd["status"] == "ok" else {"status": "skipped"}
    )
    fence_agent_ready = (
        start_fence_agent(
            root=root, certs=etcd_certs, image=image, network=network,
            name=fence_agent_name, primary=primary,
        )
        if postgres["status"] == "ok" else False
    )
    fence_security_controls = (
        fence_security_negative_controls(
            fence_agent_name, primary, root=root, certs=etcd_certs
        )
        if fence_agent_ready else {
            "unauthenticated_client_rejected": False,
            "authenticated_forged_lease_rejected": False,
            "primary_remained_running": False,
        }
    )
    forged_fence_rejected = all(fence_security_controls.values())
    active_ready = standby_waiting = standby_ready = False
    seed = subprocess.CompletedProcess([], 1, "", "cluster_not_ready")
    resume = subprocess.CompletedProcess([], 1, "", "standby_not_ready")
    failback_client = subprocess.CompletedProcess([], 1, "", "failback_not_ready")
    controller_started = [False, False]
    failback_controller_started = [False, False]
    checkpoint: dict[str, Any] = {"status": "skipped"}
    active_exit = standby_exit = failback_exit = -1
    active_logs = standby_logs = failback_logs = ""
    active_service: dict[str, Any] = {}
    standby_service: dict[str, Any] = {}
    failback_service: dict[str, Any] = {}
    dcs_kills = [subprocess.CompletedProcess([], 1, "", "not_started")] * 2
    primary_partition = subprocess.CompletedProcess([], 1, "", "not_started")
    active_stopped = False
    primary_running_without_quorum = False
    replica_still_recovery = False
    gateway_not_ready = False
    controllers_running = False
    controllers_quorum_blocked = False
    quorum_restore = subprocess.CompletedProcess([], 1, "", "not_started")
    quorum_restored = False
    promoted_read_write = False
    failover_latency_ms = -1
    controller_rows: list[dict[str, Any]] = []
    failback_controller_rows: list[dict[str, Any]] = []
    fence_agent_row: dict[str, Any] = {"status": "skipped"}
    switchover_agent_row: dict[str, Any] = {"status": "skipped"}
    primary_hard_fenced = False
    rejoin: dict[str, Any] = {"status": "skipped"}
    planned_failback: dict[str, Any] = {"status": "skipped"}
    final_redundancy: dict[str, Any] = {"status": "skipped"}
    failback_ready = False
    failback_latency_ms = -1
    switchover_agent_ready = False
    switchover_security_controls = {
        "unauthenticated_client_rejected": False,
        "authenticated_forged_lease_rejected": False,
        "current_primary_remained_running": False,
    }
    failback_quorum_kill = subprocess.CompletedProcess([], 1, "", "not_started")
    failback_quorum_restore = subprocess.CompletedProcess([], 1, "", "not_started")
    unsafe_replication_control: dict[str, Any] = {"status": "skipped"}
    restored_sync_control: dict[str, Any] = {"status": "skipped"}
    failback_unsafe_preconditions_blocked = False
    failback_roles_unchanged_while_unsafe = False
    failback_controllers_quorum_blocked = False
    failback_roles_unchanged_without_quorum = False
    failback_quorum_restored = False
    try:
        if postgres["status"] == "ok" and forged_fence_rejected:
            active_ready = start_gateway(
                root=root, image=image, network=network, name=active_name,
                command=service_command(
                    root=root, temp_root=temp_root, holder="gateway-a",
                    qlogs=qlogs["active-service-qlogs"], wait_for_lease=False,
                ),
                waiting=False,
            )
        if active_ready:
            seed = run_client(
                root=root, image=image, network=network, install=install,
                name=f"fleetrmw-quorum-seed-{suffix}", certs=certs,
                qlogs=qlogs["active-client-qlogs"], mode="seed",
            )
        if seed.returncode == 0:
            standby_waiting = start_gateway(
                root=root, image=image, network=network, name=standby_name,
                command=service_command(
                    root=root, temp_root=temp_root, holder="gateway-b",
                    qlogs=qlogs["standby-service-qlogs"], wait_for_lease=True,
                ),
                waiting=True,
            )
        if standby_waiting:
            for controller_index, controller_name in enumerate(controller_names):
                controller_started[controller_index] = start_controller(
                    root=root, certs=etcd_certs, image=image, network=network,
                    name=controller_name,
                    controller_id=f"controller-{controller_index + 1}",
                )
        if all(controller_started):
            time.sleep(1.2)
            checkpoint = replication_checkpoint(primary)
            failover_started = time.monotonic()
            dcs_kills = [
                run(["docker", "kill", etcd_names[1]]),
                run(["docker", "kill", etcd_names[2]]),
            ]
            primary_partition = inject_primary_partition(image, primary)
            active_stopped = wait_container_stopped(active_name)
            time.sleep(2.5)
            primary_state = run([
                "docker", "inspect", "-f", "{{.State.Running}}", primary
            ])
            primary_running_without_quorum = (
                primary_state.returncode == 0
                and primary_state.stdout.strip() == "true"
            )
            recovery = sql(replica, "SELECT pg_is_in_recovery()")
            replica_still_recovery = (
                recovery.returncode == 0 and recovery.stdout.strip() == "t"
            )
            gateway_not_ready = not wait_service_ready(standby_name, timeout_s=0.3)
            controller_states = [
                run([
                    "docker", "inspect", "-f", "{{.State.Running}}", name
                ])
                for name in controller_names
            ]
            controllers_running = all(
                state.returncode == 0 and state.stdout.strip() == "true"
                for state in controller_states
            )
            controllers_quorum_blocked = wait_controllers_quorum_blocked(
                controller_names
            )
            quorum_restore = run(["docker", "start", etcd_names[1]])
            quorum_restored = (
                quorum_restore.returncode == 0
                and wait_two_member_quorum(etcd_names[0])
            )
            standby_ready = wait_service_ready(standby_name, timeout_s=25.0)
            failover_latency_ms = round(
                (time.monotonic() - failover_started) * 1000.0
            )
            promoted = sql(replica, "SELECT pg_is_in_recovery()")
            promoted_read_write = (
                promoted.returncode == 0 and promoted.stdout.strip() == "f"
            )
            fenced_state = run([
                "docker", "inspect", "-f", "{{.State.Running}}", primary
            ])
            primary_hard_fenced = (
                fenced_state.returncode == 0
                and fenced_state.stdout.strip() == "false"
            )
        if standby_ready:
            resume = run_client(
                root=root, image=image, network=network, install=install,
                name=f"fleetrmw-quorum-resume-{suffix}", certs=certs,
                qlogs=qlogs["standby-client-qlogs"], mode="resume",
            )
            time.sleep(1.2)
        if resume.returncode == 0:
            rejoin = rejoin_fenced_primary_as_standby(
                primary=primary, source=replica, network=network,
                postgres_image=str(postgres.get("image", "postgres:16-alpine")),
                suffix=suffix,
            )
        if rejoin.get("status") == "ok":
            standby_exit, standby_logs, standby_service = stop_service(standby_name)
            if standby_exit == 0 and standby_service_ok(standby_service):
                switchover_agent_ready = start_switchover_agent(
                    root=root, certs=etcd_certs, image=image, network=network,
                    name=switchover_agent_name, current_primary=replica,
                )
            if switchover_agent_ready:
                switchover_security_controls = (
                    switchover_security_negative_controls(
                        switchover_agent_name, replica,
                        root=root, certs=etcd_certs,
                    )
                )
            if switchover_agent_ready and all(
                switchover_security_controls.values()
            ):
                unsafe_replication_control = configure_failback_replication_mode(
                    replica, synchronous=False
                )
            if unsafe_replication_control.get("status") == "ok":
                for controller_index, controller_name in enumerate(
                    failback_controller_names
                ):
                    failback_controller_started[controller_index] = (
                        start_failback_controller(
                            root=root, certs=etcd_certs, image=image,
                            network=network, name=controller_name,
                            controller_id=(
                                f"failback-controller-{controller_index + 1}"
                            ),
                        )
                    )
            if all(failback_controller_started):
                failback_unsafe_preconditions_blocked = wait_controllers_event(
                    failback_controller_names, "unsafe_preconditions"
                )
                unsafe_target = sql(primary, "SELECT pg_is_in_recovery()")
                unsafe_source = sql(replica, "SELECT pg_is_in_recovery()")
                unsafe_source_container = run([
                    "docker", "inspect", "-f", "{{.State.Running}}", replica
                ])
                failback_roles_unchanged_while_unsafe = (
                    unsafe_target.returncode == 0
                    and unsafe_target.stdout.strip() == "t"
                    and unsafe_source.returncode == 0
                    and unsafe_source.stdout.strip() == "f"
                    and unsafe_source_container.returncode == 0
                    and unsafe_source_container.stdout.strip() == "true"
                )
            if (
                failback_unsafe_preconditions_blocked
                and failback_roles_unchanged_while_unsafe
            ):
                failback_quorum_kill = run(["docker", "kill", etcd_names[1]])
            if failback_quorum_kill.returncode == 0:
                restored_sync_control = configure_failback_replication_mode(
                    replica, synchronous=True
                )
            if restored_sync_control.get("status") == "ok":
                failback_controllers_quorum_blocked = (
                    wait_controllers_quorum_blocked(failback_controller_names)
                )
                target_without_quorum = sql(primary, "SELECT pg_is_in_recovery()")
                source_without_quorum = sql(replica, "SELECT pg_is_in_recovery()")
                source_container_without_quorum = run([
                    "docker", "inspect", "-f", "{{.State.Running}}", replica
                ])
                failback_roles_unchanged_without_quorum = (
                    target_without_quorum.returncode == 0
                    and target_without_quorum.stdout.strip() == "t"
                    and source_without_quorum.returncode == 0
                    and source_without_quorum.stdout.strip() == "f"
                    and source_container_without_quorum.returncode == 0
                    and source_container_without_quorum.stdout.strip() == "true"
                )
            if (
                failback_controllers_quorum_blocked
                and failback_roles_unchanged_without_quorum
            ):
                failback_started = time.monotonic()
                failback_quorum_restore = run(["docker", "start", etcd_names[1]])
                failback_quorum_restored = (
                    failback_quorum_restore.returncode == 0
                    and wait_two_member_quorum(etcd_names[0])
                )
            if failback_quorum_restored:
                failback_controller_rows = [
                    collect_controller(name) for name in failback_controller_names
                ]
                switchover_agent_row = collect_switchover_agent(
                    switchover_agent_name
                )
                winner = next(
                    (
                        row.get("telemetry", {})
                        for row in failback_controller_rows
                        if row.get("telemetry", {}).get("status") == "failed_back"
                    ),
                    {},
                )
                target_after = sql(primary, "SELECT pg_is_in_recovery()")
                source_state = run([
                    "docker", "inspect", "-f", "{{.State.Running}}", replica
                ])
                recovered_after = sql(
                    primary,
                    "SELECT (SELECT COUNT(*) FROM frames) || '|' || "
                    "(SELECT COUNT(*) FROM admission_state)",
                )
                planned_failback = {
                    "status": (
                        "ok" if failback_controllers_ok(failback_controller_rows)
                        else "failed"
                    ),
                    "mode": "automatic_policy_dcs_switchover",
                    "policy": winner.get("policy"),
                    "synchronous_replay_gap_bytes_before_stop": winner.get(
                        "synchronous_replay_gap_bytes"
                    ),
                    "old_primary_in_recovery_before": True,
                    "current_primary_read_write_before": True,
                    "current_primary_stopped_before_promotion": (
                        winner.get("graceful_stop_confirmed") is True
                        and int(winner.get("promotion_confirmed_unix_ns", 0))
                        >= int(winner.get("source_stop_confirmed_unix_ns", 0))
                    ),
                    "original_primary_read_write_after": (
                        target_after.returncode == 0
                        and target_after.stdout.strip() == "f"
                    ),
                    "former_primary_running_after_promotion": (
                        source_state.returncode == 0
                        and source_state.stdout.strip() == "true"
                    ),
                    "recovered_frame_count": (
                        2 if recovered_after.stdout.strip() == "2|1" else 0
                    ),
                    "recovered_admission_state_count": (
                        1 if recovered_after.stdout.strip() == "2|1" else 0
                    ),
                    "dcs_lock_acquired": winner.get("dcs_lock_acquired"),
                    "controller_id": winner.get("controller_id"),
                    "lease_id": winner.get("lease_id"),
                    "cluster_id": winner.get("cluster_id"),
                    "revision": winner.get("revision"),
                }
            if planned_failback.get("status") == "ok":
                failback_ready = start_gateway(
                    root=root, image=image, network=network, name=failback_name,
                    command=service_command(
                        root=root, temp_root=temp_root, holder="gateway-c",
                        qlogs=qlogs["failback-service-qlogs"],
                        wait_for_lease=False,
                    ),
                    waiting=False,
                )
            if failback_ready:
                failback_latency_ms = round(
                    (time.monotonic() - failback_started) * 1000.0
                )
                failback_client = run_client(
                    root=root, image=image, network=network, install=install,
                    name=f"fleetrmw-quorum-failback-{suffix}", certs=certs,
                    qlogs=qlogs["failback-client-qlogs"], mode="resume",
                )
                time.sleep(1.2)
            if failback_ready:
                failback_exit, failback_logs, failback_service = stop_service(
                    failback_name
                )
            if failback_client.returncode == 0 and failback_exit == 0:
                final_redundancy = restore_post_failback_standby(
                    source=primary, standby=replica, network=network,
                    postgres_image=str(
                        postgres.get("image", "postgres:16-alpine")
                    ),
                )
        active_exit, active_logs, active_service = stop_service(active_name)
        if standby_exit == -1:
            standby_exit, standby_logs, standby_service = stop_service(standby_name)
        if failback_ready and failback_exit == -1:
            failback_exit, failback_logs, failback_service = stop_service(
                failback_name
            )
        controller_rows = [collect_controller(name) for name in controller_names]
        fence_agent_row = collect_fence_agent(fence_agent_name)
    finally:
        run(["docker", "rm", "-f", active_name])
        run(["docker", "rm", "-f", standby_name])
        run(["docker", "rm", "-f", failback_name])
        for name in controller_names:
            run(["docker", "rm", "-f", name])
        for name in failback_controller_names:
            run(["docker", "rm", "-f", name])
        fence_agent_remove = run(["docker", "rm", "-f", fence_agent_name])
        switchover_agent_remove = run([
            "docker", "rm", "-f", switchover_agent_name
        ])
        postgres_removes = [
            run(["docker", "rm", "-f", primary]),
            run(["docker", "rm", "-f", replica]),
        ]
        etcd_removes = [
            run(["docker", "rm", "-f", name]) for name in etcd_names
        ]
    active = phase_evidence(
        client=seed, logs=active_logs, service=active_service,
        exit_code=active_exit, mode="seed",
        service_valid=active_failure_service_ok(active_service),
        qlog_dirs=(qlogs["active-service-qlogs"], qlogs["active-client-qlogs"]),
        expected_exit=1,
    )
    standby = phase_evidence(
        client=resume, logs=standby_logs, service=standby_service,
        exit_code=standby_exit, mode="resume",
        service_valid=standby_service_ok(standby_service),
        qlog_dirs=(qlogs["standby-service-qlogs"], qlogs["standby-client-qlogs"]),
        expected_exit=0,
    )
    failback = phase_evidence(
        client=failback_client, logs=failback_logs, service=failback_service,
        exit_code=failback_exit, mode="resume",
        service_valid=failback_service_ok(failback_service),
        qlog_dirs=(
            qlogs["failback-service-qlogs"], qlogs["failback-client-qlogs"]
        ),
        expected_exit=0,
    )
    recovered = standby_service.get("metrics", {})
    result = {
        "index": index,
        "etcd_cluster": etcd,
        "postgresql_cluster": postgres,
        "replication_before_failure": checkpoint,
        "standby_observed_waiting_while_primary_live": standby_waiting,
        "unauthorized_fence_rejected_while_primary_running": forged_fence_rejected,
        "fence_security_negative_controls": fence_security_controls,
        "quorum_loss_control": {
            "dcs_members_killed": sum(call.returncode == 0 for call in dcs_kills),
            "dcs_kill_returncodes": [call.returncode for call in dcs_kills],
            "partitioned_primary_container": primary,
            "primary_partition_returncode": primary_partition.returncode,
            "primary_partition_fault": (
                "primary_network_namespace_egress_loss_100_percent"
            ),
            "primary_partition_netem_configured": (
                "loss 100%" in primary_partition.stdout
            ),
            "active_gateway_exited_on_database_loss": active_stopped,
            "primary_remained_running_without_quorum": (
                primary_running_without_quorum
            ),
            "standby_remained_in_recovery_without_quorum": replica_still_recovery,
            "gateway_standby_not_ready_without_quorum": gateway_not_ready,
            "controllers_remained_running_without_quorum": controllers_running,
            "all_controllers_observed_quorum_unavailable": (
                controllers_quorum_blocked
            ),
            "quorum_restore_returncode": quorum_restore.returncode,
            "two_of_three_quorum_restored": quorum_restored,
        },
        "automatic_promotion": {
            "promoted_read_write": promoted_read_write,
            "promoted_by_exactly_one_controller": (
                sum(
                    row.get("telemetry", {}).get("status") == "promoted"
                    for row in controller_rows
                )
                == 1
            ),
            "primary_hard_fenced_after_quorum_restore": primary_hard_fenced,
        },
        "controllers": controller_rows,
        "fence_agent": fence_agent_row,
        "database_failure_to_gateway_ready_ms": failover_latency_ms,
        "active": active,
        "standby": standby,
        "seeded_frames_recovered": recovered.get("recovered_frames") == 2,
        "seeded_admission_state_recovered": (
            recovered.get("recovered_admission_state") == 1
        ),
        "post_failover_rejoin": rejoin,
        "failback_quorum_loss_control": {
            "unsafe_replication_control": unsafe_replication_control,
            "all_controllers_rejected_unsafe_replication": (
                failback_unsafe_preconditions_blocked
            ),
            "database_roles_unchanged_while_unsafe": (
                failback_roles_unchanged_while_unsafe
            ),
            "dcs_member_kill_returncode": failback_quorum_kill.returncode,
            "synchronous_replication_restored_without_quorum": (
                restored_sync_control
            ),
            "all_controllers_observed_quorum_unavailable": (
                failback_controllers_quorum_blocked
            ),
            "database_roles_unchanged_without_quorum": (
                failback_roles_unchanged_without_quorum
            ),
            "quorum_restore_returncode": failback_quorum_restore.returncode,
            "two_of_three_quorum_restored": failback_quorum_restored,
        },
        "switchover_security_negative_controls": (
            switchover_security_controls
        ),
        "failback_controllers": failback_controller_rows,
        "switchover_agent": switchover_agent_row,
        "planned_failback": planned_failback,
        "planned_failback_to_gateway_ready_ms": failback_latency_ms,
        "failback": failback,
        "post_failback_redundancy": final_redundancy,
        "postgresql_shutdown_returncodes": [
            call.returncode for call in postgres_removes
        ],
        "etcd_shutdown_returncodes": [call.returncode for call in etcd_removes],
        "fence_agent_shutdown_returncode": fence_agent_remove.returncode,
        "switchover_agent_shutdown_returncode": (
            switchover_agent_remove.returncode
        ),
    }
    result["status"] = "ok" if case_ok(result) else "failed"
    return result


def run_probe(
    *, root: Path, image: str, iterations: int, keep_temp: bool
) -> dict[str, Any]:
    run_count = max(1, iterations)
    temp_root = root / f".tmp_fleetrmw_quic_pg_quorum_{os.getpid()}"
    certs = temp_root / "certs"
    etcd_certs = temp_root / "etcd-certs"
    certs.mkdir(parents=True, exist_ok=True)
    etcd_certs.mkdir(parents=True, exist_ok=True)
    policy = {
        "schema_version": "fleetrmw.quic_gateway_admission_policy.v1",
        "default_action": "deny", "max_accepted_frames": 1,
        "rules": [{
            "domain_id": 42, "topic": "/fleetqox/durable_admission",
            "traffic_class": "control", "max_accepted_frames": 1,
            "allowed_publishers": ["durable-admission-publisher"],
        }],
        "repair": {
            "capacity_bytes": 1024, "max_admitted": 1,
            "paths": [{
                "path_id": "private_5g", "latency_ms": 20.0,
                "loss": 0.01, "failure_domain": "private_5g",
            }],
        },
    }
    (temp_root / "admission-policy.json").write_text(
        json.dumps(policy, sort_keys=True) + "\n", encoding="utf-8"
    )
    build_root = "/work/.tmp_fleetrmw_quic_pg_quorum_build"
    install = "/work/.tmp_fleetrmw_quic_pg_quorum_install"
    log_root = "/work/.tmp_fleetrmw_quic_pg_quorum_log"
    cert_result = run([
        "docker", "run", "--rm", "--entrypoint", "bash",
        "-v", f"{root}:/work", "-w", "/work", image, "-lc",
        certificate_command(certs, root),
    ])
    etcd_cert_result = run([
        "docker", "run", "--rm", "--entrypoint", "bash",
        "-v", f"{root}:/work", "-w", "/work", image, "-lc",
        etcd_certificate_command(etcd_certs, root),
    ])
    build = run([
        "docker", "run", "--rm", "--entrypoint", "bash",
        "-v", f"{root}:/work", "-w", "/work", image, "-lc",
        "source /opt/ros/jazzy/setup.bash && "
        f"rm -rf {build_root} {install} {log_root} && "
        f"colcon --log-base {log_root} build --base-paths ros2_ws/src "
        "--packages-select rmw_fleetqox_cpp "
        f"--build-base {build_root} --install-base {install} "
        "--cmake-args -DCMAKE_BUILD_TYPE=Release",
    ])
    network = f"fleetrmw-pg-quorum-net-{os.getpid()}"
    network_result = run(["docker", "network", "create", network])
    rows: list[dict[str, Any]] = []
    try:
        if (
            cert_result.returncode == etcd_cert_result.returncode
            == build.returncode == network_result.returncode == 0
        ):
            for index in range(1, run_count + 1):
                rows.append(run_case(
                    root=root, image=image, network=network, install=install,
                    temp_root=temp_root, index=index,
                ))
    finally:
        run(["docker", "network", "rm", network])
        if not keep_temp:
            cleanup = run([
                "docker", "run", "--rm", "--entrypoint", "bash",
                "-v", f"{root}:/work", image, "-lc",
                f"rm -rf {build_root} {install} {log_root}",
            ])
            if cleanup.returncode == 0:
                shutil.rmtree(temp_root, ignore_errors=True)
    successful = sum(row.get("status") == "ok" for row in rows)
    status = "ok" if (
        cert_result.returncode == etcd_cert_result.returncode
        == build.returncode == network_result.returncode == 0
        and len(rows) == successful == run_count
    ) else "failed"
    latencies = [
        row["database_failure_to_gateway_ready_ms"] for row in rows
        if row.get("database_failure_to_gateway_ready_ms", -1) >= 0
    ]
    failback_latencies = [
        row["planned_failback_to_gateway_ready_ms"] for row in rows
        if row.get("planned_failback_to_gateway_ready_ms", -1) >= 0
    ]
    return {
        "schema_version": SCHEMA_VERSION,
        "status": status,
        "run_count": run_count,
        "successful_runs": successful,
        "failed_run_count": run_count - successful,
        "container_count_per_run": 19,
        "etcd_member_count_per_run": 3,
        "postgresql_instance_count_per_run": 3,
        "failover_controller_count_per_run": 2,
        "failback_controller_count_per_run": 2,
        "gateway_instance_count_per_run": 3,
        "real_quic_v1_h3": True,
        "etcd_raft_quorum_claim": status == "ok",
        "quorum_loss_promotion_fail_closed_claim": status == "ok",
        "n_minus_one_quorum_recovery_claim": status == "ok",
        "single_dcs_promotion_winner_claim": status == "ok",
        "automatic_database_promotion_claim": status == "ok",
        "synchronous_replication_seeded_state_continuity_claim": status == "ok",
        "gateway_takeover_after_quorum_promotion_claim": status == "ok",
        "max_database_failure_to_gateway_ready_ms": (
            max(latencies) if latencies else None
        ),
        "primary_hard_fenced_by_orchestrator_before_promotion": False,
        "dcs_authorized_docker_stonith_claim": status == "ok",
        "controller_stonith_claim": status == "ok",
        "fence_agent_mutual_tls_claim": status == "ok",
        "fence_client_identity_binding_claim": status == "ok",
        "fenced_primary_rejoined_as_synchronous_standby_claim": status == "ok",
        "post_failover_redundancy_restored_claim": status == "ok",
        "docker_automated_rejoin_claim": status == "ok",
        "production_automatic_rejoin_claim": False,
        "controlled_planned_failback_claim": status == "ok",
        "original_primary_role_restored_claim": status == "ok",
        "post_failback_gateway_token3_state_continuity_claim": status == "ok",
        "post_failback_synchronous_redundancy_claim": status == "ok",
        "automatic_failback_policy_claim": status == "ok",
        "unsafe_failback_preconditions_fail_closed_claim": status == "ok",
        "failback_quorum_loss_fail_closed_claim": status == "ok",
        "single_dcs_failback_winner_claim": status == "ok",
        "dcs_authorized_graceful_switchover_claim": status == "ok",
        "max_planned_failback_to_gateway_ready_ms": (
            max(failback_latencies) if failback_latencies else None
        ),
        "docker_live_primary_partition_fenced_before_promotion_claim": (
            status == "ok"
        ),
        "network_partition_split_brain_tolerance_claim": False,
        "automatic_failback_claim": status == "ok",
        "production_automatic_failback_claim": False,
        "etcd_mutual_tls_claim": status == "ok",
        "regional_disaster_recovery_claim": False,
        "production_readiness": False,
        "certificate_returncode": cert_result.returncode,
        "etcd_certificate_returncode": etcd_cert_result.returncode,
        "build_returncode": build.returncode,
        "build_stderr": build.stderr[-4000:],
        "network_returncode": network_result.returncode,
        "runs": rows,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--image", default=DEFAULT_IMAGE)
    parser.add_argument("--iterations", type=int, default=5)
    parser.add_argument("--keep-temp", action="store_true")
    parser.add_argument(
        "--summary-json",
        default=(
            "results_rmw_socket/"
            "docker_quic_postgresql_quorum_failover_probe_summary.json"
        ),
    )
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    summary = run_probe(
        root=ROOT, image=args.image, iterations=args.iterations,
        keep_temp=args.keep_temp,
    )
    output = ROOT / args.summary_json
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(summary, sort_keys=True) + "\n", encoding="utf-8")
    if args.json:
        print(json.dumps(summary, sort_keys=True))
    else:
        print("fleetrmw-quic-postgresql-quorum-failover-probe")
        print(f"  status: {summary['status']}")
        print(f"  successful_runs: {summary['successful_runs']}/{summary['run_count']}")
    return 0 if summary["status"] == "ok" else 1


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
"""Validate synchronous PostgreSQL promotion plus QUIC gateway takeover."""

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
    from scripts.run_rmw_docker_quic_durable_admission_failover_probe import probe_ok
    from scripts.run_rmw_docker_quic_postgres_failover_probe import (
        GATEWAY_ALIAS,
        POSTGRES_IMAGE,
        POSTGRES_SCHEMA_VERSION,
        postgres_service_ok,
        wait_standby_waiting,
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
    from run_rmw_docker_quic_durable_admission_failover_probe import probe_ok
    from run_rmw_docker_quic_postgres_failover_probe import (
        GATEWAY_ALIAS,
        POSTGRES_IMAGE,
        POSTGRES_SCHEMA_VERSION,
        postgres_service_ok,
        wait_standby_waiting,
    )
    from run_rmw_docker_quic_stateful_gateway_probe import (
        DEFAULT_IMAGE,
        json_rows,
        run,
        wait_service_ready,
    )
    from run_rmw_docker_quic_writer_fencing_probe import run_client, stop_service


ROOT = Path(__file__).resolve().parents[1]
SCHEMA_VERSION = "fleetrmw.docker_quic_postgresql_replication_failover_probe.v1"
PRIMARY_ALIAS = "fleetqox-pg-primary"
STANDBY_ALIAS = "fleetqox-pg-standby"
DATABASE_PASSWORD = "fleetqox-replication-probe"
REPLICATION_APPLICATION = "fleetqox_standby"
REPLICATION_SLOT = "fleetqox_slot"


def wait_postgres(container: str, timeout_s: float = 30.0) -> bool:
    deadline = time.monotonic() + timeout_s
    consecutive_ready = 0
    while time.monotonic() < deadline:
        checked = run([
            "docker", "exec", container, "pg_isready", "-U", "postgres",
            "-d", "fleetqox",
        ])
        if checked.returncode == 0:
            consecutive_ready += 1
            if consecutive_ready >= 3:
                return True
            time.sleep(0.2)
            continue
        consecutive_ready = 0
        inspected = run(
            ["docker", "inspect", "-f", "{{.State.Running}}", container]
        )
        if inspected.returncode != 0 or inspected.stdout.strip() != "true":
            return False
        time.sleep(0.2)
    return False


def sql(container: str, query: str) -> subprocess.CompletedProcess[str]:
    return run([
        "docker", "exec", "-e", f"PGPASSWORD={DATABASE_PASSWORD}",
        container, "psql", "-U", "postgres", "-d", "fleetqox",
        "-v", "ON_ERROR_STOP=1", "-Atc", query,
    ])


def start_replication_cluster(
    *, network: str, primary: str, standby: str,
) -> dict[str, Any]:
    primary_start = run([
        "docker", "run", "-d", "--name", primary,
        "--network", network, "--network-alias", PRIMARY_ALIAS,
        "-e", f"POSTGRES_PASSWORD={DATABASE_PASSWORD}",
        "-e", "POSTGRES_DB=fleetqox", POSTGRES_IMAGE,
        "-c", "wal_level=replica", "-c", "max_wal_senders=10",
        "-c", "max_replication_slots=10", "-c", "synchronous_commit=on",
    ])
    primary_ready = primary_start.returncode == 0 and wait_postgres(primary)
    role = subprocess.CompletedProcess([], 1, "", "primary_not_ready")
    hba = subprocess.CompletedProcess([], 1, "", "primary_not_ready")
    standby_start = subprocess.CompletedProcess([], 1, "", "primary_not_ready")
    standby_ready = False
    if primary_ready:
        role = sql(
            primary,
            "CREATE ROLE replicator WITH REPLICATION LOGIN PASSWORD "
            f"'{DATABASE_PASSWORD}'",
        )
        hba = run([
            "docker", "exec", primary, "sh", "-c",
            "printf 'host replication replicator all scram-sha-256\\n' "
            ">> \"$PGDATA/pg_hba.conf\"",
        ])
        if role.returncode == hba.returncode == 0:
            sql(primary, "SELECT pg_reload_conf()")
            bootstrap = (
                "mkdir -p \"$PGDATA\" && "
                "chown -R postgres:postgres /var/lib/postgresql/data && "
                "gosu postgres pg_basebackup "
                f"-d \"host={PRIMARY_ALIAS} port=5432 user=replicator "
                f"password={DATABASE_PASSWORD} application_name="
                f"{REPLICATION_APPLICATION}\" "
                "-D \"$PGDATA\" -Fp -Xs -P -R "
                f"-C -S {REPLICATION_SLOT} && "
                "chmod 700 \"$PGDATA\" && "
                "exec gosu postgres postgres -D \"$PGDATA\" -c hot_standby=on"
            )
            standby_start = run([
                "docker", "run", "-d", "--name", standby,
                "--network", network, "--network-alias", STANDBY_ALIAS,
                "-e", "PGDATA=/var/lib/postgresql/data/pgdata",
                "-e", f"PGPASSWORD={DATABASE_PASSWORD}",
                "--entrypoint", "sh", POSTGRES_IMAGE, "-c", bootstrap,
            ])
            standby_ready = (
                standby_start.returncode == 0 and wait_postgres(standby)
            )
    sync_configured = False
    replication_row = ""
    if standby_ready:
        configured = sql(
            primary,
            "ALTER SYSTEM SET synchronous_standby_names = "
            f"'{REPLICATION_APPLICATION}'",
        )
        reloaded = sql(primary, "SELECT pg_reload_conf()")
        if configured.returncode == reloaded.returncode == 0:
            deadline = time.monotonic() + 10.0
            while time.monotonic() < deadline:
                status = sql(
                    primary,
                    "SELECT application_name || '|' || state || '|' || sync_state "
                    "FROM pg_stat_replication WHERE application_name="
                    f"'{REPLICATION_APPLICATION}'",
                )
                replication_row = status.stdout.strip()
                if replication_row == f"{REPLICATION_APPLICATION}|streaming|sync":
                    sync_configured = True
                    break
                time.sleep(0.2)
    version = sql(primary, "SHOW server_version") if primary_ready else role
    ok = (
        primary_ready and role.returncode == hba.returncode == 0
        and standby_ready and sync_configured and version.returncode == 0
    )
    return {
        "status": "ok" if ok else "failed",
        "image": POSTGRES_IMAGE,
        "primary_ready": primary_ready,
        "standby_ready": standby_ready,
        "streaming_replication": "streaming" in replication_row,
        "synchronous_replication": replication_row.endswith("|sync"),
        "replication_status": replication_row,
        "server_version": version.stdout.strip(),
        "primary_start_returncode": primary_start.returncode,
        "standby_start_returncode": standby_start.returncode,
        "replication_role_returncode": role.returncode,
        "replication_hba_returncode": hba.returncode,
        "replication_role_stderr": role.stderr[-2000:],
        "replication_hba_stderr": hba.stderr[-2000:],
        "primary_start_stderr": primary_start.stderr[-2000:],
        "standby_start_stderr": standby_start.stderr[-2000:],
    }


def replication_checkpoint(primary: str) -> dict[str, Any]:
    query = (
        "SELECT application_name || '|' || state || '|' || sync_state || '|' || "
        "COALESCE(pg_wal_lsn_diff(flush_lsn, '0/0')::text, '') || '|' || "
        "COALESCE(pg_wal_lsn_diff(replay_lsn, '0/0')::text, '') "
        "FROM pg_stat_replication WHERE application_name="
        f"'{REPLICATION_APPLICATION}'"
    )
    result = sql(primary, query)
    parts = result.stdout.strip().split("|")
    valid = (
        result.returncode == 0 and len(parts) == 5
        and parts[:3] == [REPLICATION_APPLICATION, "streaming", "sync"]
        and parts[3].isdigit() and parts[4].isdigit()
        and int(parts[3]) > 0 and int(parts[4]) > 0
    )
    return {
        "status": "ok" if valid else "failed",
        "application_name": parts[0] if len(parts) == 5 else "",
        "state": parts[1] if len(parts) == 5 else "",
        "sync_state": parts[2] if len(parts) == 5 else "",
        "flush_lsn_bytes": int(parts[3]) if len(parts) == 5 and parts[3].isdigit() else 0,
        "replay_lsn_bytes": int(parts[4]) if len(parts) == 5 and parts[4].isdigit() else 0,
        "returncode": result.returncode,
    }


def service_command(
    *, root: Path, temp_root: Path, holder: str, qlogs: Path,
    wait_for_lease: bool,
) -> str:
    certs = temp_root / "certs"
    policy = temp_root / "admission-policy.json"
    dsn = (
        f"postgresql://postgres:{DATABASE_PASSWORD}@{PRIMARY_ALIAS}:5432,"
        f"{STANDBY_ALIAS}:5432/fleetqox?target_session_attrs=read-write"
        "&tcp_user_timeout=1000"
    )
    wait = (
        " --writer-lease-wait-timeout-ms 30000 --writer-lease-retry-ms 100"
        if wait_for_lease else ""
    )
    return (
        "tc qdisc replace dev eth0 root netem delay 5ms 1ms loss 0.2% && "
        "tc qdisc show dev eth0 && "
        "exec python3 scripts/fleetrmw_quic_gateway_service.py "
        "--host 0.0.0.0 --port 4504 "
        f"--certificate /work/{(certs / 'server.crt').relative_to(root)} "
        f"--private-key /work/{(certs / 'server.key').relative_to(root)} "
        f"--admission-policy /work/{policy.relative_to(root)} "
        f"--state-db '{dsn}' --writer-lease-instance-id {holder} "
        "--writer-lease-ms 3000 "
        f"--qlog-dir /work/{qlogs.relative_to(root)} "
        "--max-frames-per-topic 8 --max-frame-bytes 65536"
        + wait
    )


def start_gateway(
    *, root: Path, image: str, network: str, name: str, command: str,
    waiting: bool,
) -> bool:
    started = run([
        "docker", "run", "-d", "--name", name,
        "--network", network, "--network-alias", GATEWAY_ALIAS,
        "--cap-add", "NET_ADMIN", "--entrypoint", "bash",
        "-v", f"{root}:/work", "-w", "/work", image, "-lc", command,
    ])
    if started.returncode != 0:
        return False
    return wait_standby_waiting(name) if waiting else wait_service_ready(name)


def wait_container_stopped(container: str, timeout_s: float = 8.0) -> bool:
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        inspected = run(
            ["docker", "inspect", "-f", "{{.State.Running}}", container]
        )
        if inspected.returncode == 0 and inspected.stdout.strip() == "false":
            return True
        time.sleep(0.1)
    return False


def active_failure_service_ok(row: dict[str, Any]) -> bool:
    metrics = row.get("metrics", {})
    durable = metrics.get("durable_state", {})
    admission = metrics.get("admission", {})
    lease = durable.get("writer_lease", {})
    endpoint = urlsplit(str(durable.get("endpoint", "")))
    return (
        row.get("status") == "stopped"
        and row.get("clean_teardown") is True
        and row.get("writer_lease_lost") is True
        and row.get("writer_lease_instance_id") == "gateway-a"
        and row.get("automatic_standby_wait_configured") is False
        and metrics.get("accepted_frames") == 2
        and metrics.get("durable_frame_commits") == 2
        and metrics.get("durable_admission_commits") == 2
        and metrics.get("durable_writer_lease_renewals", 0) >= 1
        and metrics.get("durable_writer_lease_failures") == 1
        and metrics.get("retained_frames") == 2
        and durable.get("schema_version") == POSTGRES_SCHEMA_VERSION
        and durable.get("backend") == "postgresql"
        and durable.get("available") is False
        and durable.get("snapshot_stale") is True
        and durable.get("synchronous_commit") == "on"
        and durable.get("in_recovery") is False
        and endpoint.hostname == PRIMARY_ALIAS
        and endpoint.username is None
        and lease.get("holder_id") == "gateway-a"
        and lease.get("fence_token") == 1
        and admission.get("accepted_total") == 1
        and admission.get("accepted_cumulative") == 2
        and admission.get("repair_admitted_count") == 1
        and row.get("transport_metrics", {}).get("connections_created") == 1
    )


def standby_service_ok(row: dict[str, Any]) -> bool:
    durable = row.get("metrics", {}).get("durable_state", {})
    endpoint = urlsplit(str(durable.get("endpoint", "")))
    return (
        postgres_service_ok(
            row, mode="resume", holder="gateway-b", token=2,
            automatic_wait=True,
        )
        and durable.get("available") is True
        and durable.get("snapshot_stale") is False
        and durable.get("in_recovery") is False
        and str(durable.get("server_version", "")).startswith("16.")
        and endpoint.hostname == STANDBY_ALIAS
    )


def phase_evidence(
    *, client: subprocess.CompletedProcess[str], logs: str,
    service: dict[str, Any], exit_code: int, mode: str,
    service_valid: bool, qlog_dirs: tuple[Path, Path], expected_exit: int,
) -> dict[str, Any]:
    probes = json_rows(client.stdout)
    probe = probes[-1] if probes else {}
    qlogs = [
        path for directory in qlog_dirs for path in directory.glob("*")
        if path.is_file()
    ]
    netem = "qdisc netem" in logs and "qdisc netem" in client.stdout
    qlog_ok = bool(qlogs) and all(path.stat().st_size > 0 for path in qlogs)
    ok = (
        client.returncode == 0 and exit_code == expected_exit
        and probe_ok(probe, mode) and service_valid and netem and qlog_ok
    )
    return {
        "mode": mode,
        "status": "ok" if ok else "failed",
        "probe": probe,
        "service": service,
        "service_validation": service_valid,
        "netem_configured_both_containers": netem,
        "qlog_file_count": len(qlogs),
        "qlog_total_bytes": sum(path.stat().st_size for path in qlogs),
        "client_returncode": client.returncode,
        "service_exit_code": exit_code,
        "service_logs": "" if ok else logs,
        "client_stdout": "" if ok else client.stdout,
        "client_stderr": "" if ok else client.stderr,
    }


def case_ok(row: dict[str, Any]) -> bool:
    active = row.get("active", {})
    standby = row.get("standby", {})
    promotion = row.get("promotion", {})
    return (
        row.get("cluster", {}).get("status") == "ok"
        and row.get("replication_before_failure", {}).get("status") == "ok"
        and row.get("standby_observed_waiting_while_primary_live") is True
        and promotion.get("primary_kill_returncode") == 0
        and promotion.get("active_gateway_exited_on_database_loss") is True
        and promotion.get("standby_promotion_returncode") == 0
        and promotion.get("promoted_read_write") is True
        and promotion.get("promoted_host") == STANDBY_ALIAS
        and 0 <= row.get("database_failure_to_gateway_ready_ms", -1) < 15000
        and active.get("status") == standby.get("status") == "ok"
        and active.get("qlog_file_count", 0) > 0
        and standby.get("qlog_file_count", 0) > 0
        and active_failure_service_ok(active.get("service", {}))
        and standby_service_ok(standby.get("service", {}))
        and probe_ok(active.get("probe", {}), "seed")
        and probe_ok(standby.get("probe", {}), "resume")
        and row.get("seeded_frames_recovered_after_database_promotion") is True
        and row.get("seeded_admission_state_recovered_after_database_promotion") is True
        and row.get("cluster_shutdown", {}).get("remove_returncodes") == [0, 0]
    )


def run_case(
    *, root: Path, image: str, network: str, install: str,
    temp_root: Path, index: int,
) -> dict[str, Any]:
    suffix = f"{os.getpid()}-{index}"
    primary = f"fleetrmw-pg-primary-{suffix}"
    replica = f"fleetrmw-pg-standby-{suffix}"
    active_name = f"fleetrmw-pg-gateway-a-{suffix}"
    standby_name = f"fleetrmw-pg-gateway-b-{suffix}"
    case_root = temp_root / f"run-{index}"
    certs = temp_root / "certs"
    qlogs = {
        key: case_root / key
        for key in (
            "active-service-qlogs", "active-client-qlogs",
            "standby-service-qlogs", "standby-client-qlogs",
        )
    }
    for path in qlogs.values():
        path.mkdir(parents=True, exist_ok=True)
    cluster = start_replication_cluster(
        network=network, primary=primary, standby=replica
    )
    active_ready = standby_waiting = standby_ready = False
    active_stopped_on_loss = False
    seed = subprocess.CompletedProcess([], 1, "", "cluster_not_ready")
    resume = subprocess.CompletedProcess([], 1, "", "standby_not_ready")
    active_exit = standby_exit = -1
    active_logs = standby_logs = ""
    active_service: dict[str, Any] = {}
    standby_service: dict[str, Any] = {}
    checkpoint: dict[str, Any] = {"status": "skipped"}
    primary_kill = subprocess.CompletedProcess([], 1, "", "not_started")
    promote = subprocess.CompletedProcess([], 1, "", "not_started")
    promoted_host = ""
    promoted_read_write = False
    failover_latency_ms = -1
    try:
        if cluster["status"] == "ok":
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
                name=f"fleetrmw-pg-seed-{suffix}", certs=certs,
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
            time.sleep(1.2)
            checkpoint = replication_checkpoint(primary)
            failover_started = time.monotonic()
            primary_kill = run(["docker", "kill", primary])
            time.sleep(0.5)
            promote = run([
                "docker", "exec", "-u", "postgres", replica, "pg_ctl",
                "-D", "/var/lib/postgresql/data/pgdata", "promote", "-w",
            ])
            active_stopped_on_loss = wait_container_stopped(active_name)
            standby_ready = wait_service_ready(standby_name, timeout_s=15.0)
            failover_latency_ms = round(
                (time.monotonic() - failover_started) * 1000.0
            )
            if promote.returncode == 0:
                promoted = sql(replica, "SELECT pg_is_in_recovery()")
                promoted_read_write = (
                    promoted.returncode == 0 and promoted.stdout.strip() == "f"
                )
                promoted_host = STANDBY_ALIAS if promoted_read_write else ""
        if standby_ready:
            resume = run_client(
                root=root, image=image, network=network, install=install,
                name=f"fleetrmw-pg-resume-{suffix}", certs=certs,
                qlogs=qlogs["standby-client-qlogs"], mode="resume",
            )
            time.sleep(1.2)
        active_exit, active_logs, active_service = stop_service(active_name)
        standby_exit, standby_logs, standby_service = stop_service(standby_name)
    finally:
        run(["docker", "rm", "-f", active_name])
        run(["docker", "rm", "-f", standby_name])
        primary_remove = run(["docker", "rm", "-f", primary])
        replica_remove = run(["docker", "rm", "-f", replica])
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
    recovered_metrics = standby_service.get("metrics", {})
    result = {
        "index": index,
        "cluster": cluster,
        "replication_before_failure": checkpoint,
        "standby_observed_waiting_while_primary_live": standby_waiting,
        "database_failure_to_gateway_ready_ms": failover_latency_ms,
        "promotion": {
            "primary_kill_returncode": primary_kill.returncode,
            "active_gateway_exited_on_database_loss": active_stopped_on_loss,
            "standby_promotion_returncode": promote.returncode,
            "promoted_read_write": promoted_read_write,
            "promoted_host": promoted_host,
        },
        "active": active,
        "standby": standby,
        "seeded_frames_recovered_after_database_promotion": (
            recovered_metrics.get("recovered_frames") == 2
        ),
        "seeded_admission_state_recovered_after_database_promotion": (
            recovered_metrics.get("recovered_admission_state") == 1
        ),
        "cluster_shutdown": {
            "remove_returncodes": [
                primary_remove.returncode, replica_remove.returncode
            ]
        },
    }
    result["status"] = "ok" if case_ok(result) else "failed"
    return result


def run_probe(
    *, root: Path, image: str, iterations: int, keep_temp: bool
) -> dict[str, Any]:
    run_count = max(1, iterations)
    temp_root = root / f".tmp_fleetrmw_quic_pg_replication_{os.getpid()}"
    certs = temp_root / "certs"
    certs.mkdir(parents=True, exist_ok=True)
    policy = {
        "schema_version": "fleetrmw.quic_gateway_admission_policy.v1",
        "default_action": "deny",
        "max_accepted_frames": 1,
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
    build_root = "/work/.tmp_fleetrmw_quic_pg_replication_build"
    install = "/work/.tmp_fleetrmw_quic_pg_replication_install"
    log_root = "/work/.tmp_fleetrmw_quic_pg_replication_log"
    cert_result = run([
        "docker", "run", "--rm", "--entrypoint", "bash",
        "-v", f"{root}:/work", "-w", "/work", image, "-lc",
        certificate_command(certs, root),
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
    network = f"fleetrmw-pg-replication-net-{os.getpid()}"
    network_result = run(["docker", "network", "create", network])
    rows: list[dict[str, Any]] = []
    try:
        if cert_result.returncode == build.returncode == network_result.returncode == 0:
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
        cert_result.returncode == build.returncode == network_result.returncode == 0
        and len(rows) == successful == run_count
    ) else "failed"
    latencies = [
        row["database_failure_to_gateway_ready_ms"] for row in rows
        if row.get("database_failure_to_gateway_ready_ms", -1) >= 0
    ]
    return {
        "schema_version": SCHEMA_VERSION,
        "status": status,
        "run_count": run_count,
        "successful_runs": successful,
        "failed_run_count": run_count - successful,
        "container_count_per_run": 6,
        "database_instance_count_per_run": 2,
        "gateway_instance_count_per_run": 2,
        "real_quic_v1_h3": True,
        "postgresql_streaming_replication_claim": status == "ok",
        "postgresql_synchronous_replication_claim": status == "ok",
        "database_process_failure_injected_claim": status == "ok",
        "manual_database_standby_promotion_claim": status == "ok",
        "gateway_reconnect_to_promoted_database_claim": status == "ok",
        "seeded_frame_admission_zero_loss_claim": status == "ok",
        "post_promotion_monotonic_fence_token_claim": status == "ok",
        "max_database_failure_to_gateway_ready_ms": (
            max(latencies) if latencies else None
        ),
        "automatic_database_leader_election_claim": False,
        "consensus_backend_claim": False,
        "network_partition_split_brain_tolerance_claim": False,
        "active_active_gateway_claim": False,
        "regional_disaster_recovery_claim": False,
        "production_readiness": False,
        "certificate_returncode": cert_result.returncode,
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
            "docker_quic_postgresql_replication_failover_probe_summary.json"
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
        print("fleetrmw-quic-postgresql-replication-failover-probe")
        print(f"  status: {summary['status']}")
        print(f"  successful_runs: {summary['successful_runs']}/{summary['run_count']}")
    return 0 if summary["status"] == "ok" else 1


if __name__ == "__main__":
    raise SystemExit(main())

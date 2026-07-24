#!/usr/bin/env python3
"""Prove durable application outcomes across PostgreSQL-backed gateway failover."""

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
    from scripts.run_rmw_docker_quic_mtls_probe import certificate_command
    from scripts.run_rmw_docker_quic_durable_application_outcome_failover_probe import (
        policy_document,
        probe_ok,
    )
    from scripts.run_rmw_docker_quic_postgres_failover_probe import (
        POSTGRES_ALIAS,
        POSTGRES_IMAGE,
        POSTGRES_PASSWORD,
        POSTGRES_SCHEMA_VERSION,
        start_postgres,
        stop_postgres,
    )
    from scripts.run_rmw_docker_quic_stateful_gateway_probe import (
        DEFAULT_IMAGE,
        SERVICE_SCHEMA_VERSION,
        json_rows,
        run,
        wait_service_ready,
    )
    from scripts.run_rmw_docker_quic_writer_fencing_probe import stop_service
except ModuleNotFoundError:
    from run_rmw_docker_quic_mtls_probe import certificate_command
    from run_rmw_docker_quic_durable_application_outcome_failover_probe import (
        policy_document,
        probe_ok,
    )
    from run_rmw_docker_quic_postgres_failover_probe import (
        POSTGRES_ALIAS,
        POSTGRES_IMAGE,
        POSTGRES_PASSWORD,
        POSTGRES_SCHEMA_VERSION,
        start_postgres,
        stop_postgres,
    )
    from run_rmw_docker_quic_stateful_gateway_probe import (
        DEFAULT_IMAGE,
        SERVICE_SCHEMA_VERSION,
        json_rows,
        run,
        wait_service_ready,
    )
    from run_rmw_docker_quic_writer_fencing_probe import stop_service


ROOT = Path(__file__).resolve().parents[1]
SCHEMA_VERSION = (
    "fleetrmw.docker_quic_postgresql_application_outcome_failover_probe.v1"
)
GATEWAY_ALIAS = "fleetqox-mtls-gateway"


def service_ok(
    row: dict[str, Any], *, mode: str, holder: str, token: int
) -> bool:
    seed = mode == "seed"
    metrics = row.get("metrics", {})
    admission = metrics.get("admission", {})
    durable = metrics.get("durable_state", {})
    transport = row.get("transport_metrics", {})
    lease = durable.get("writer_lease", {})
    endpoint = urlsplit(str(durable.get("endpoint", "")))
    common = (
        row.get("schema_version") == SERVICE_SCHEMA_VERSION
        and row.get("status") == "stopped"
        and row.get("clean_teardown") is True
        and row.get("client_certificate_required") is True
        and row.get("publisher_identity_binding") is True
        and row.get("publisher_identity_source") == "uri_san"
        and row.get("client_crl_configured") is True
        and row.get("admission_policy_configured") is True
        and row.get("durable_state_configured") is True
        and row.get("writer_lease_configured") is True
        and row.get("writer_lease_instance_id") == holder
        and row.get("writer_lease_ms") == 3000
        and row.get("writer_lease_lost") is False
        and row.get("automatic_standby_wait_configured") is False
        and row.get("application_outcome_qoe_debt_configured") is True
        and row.get("writer_lease_acquisition_attempts") == 1
        and metrics.get("durable_state_enabled") is True
        and metrics.get("durable_persistence_failures") == 0
        and metrics.get("durable_writer_lease_acquires") == 1
        and metrics.get("durable_writer_lease_renewals", 0) >= 1
        and metrics.get("durable_writer_lease_failures") == 0
        and metrics.get("invalid_frames") == 0
        and metrics.get("invalid_application_outcomes") == 0
        and metrics.get("application_outcome_unknown_frames") == 0
        and metrics.get("application_outcome_key_count") == 1
        and metrics.get("topic_count") == 1
        and durable.get("schema_version") == POSTGRES_SCHEMA_VERSION
        and durable.get("backend") == "postgresql"
        and durable.get("available") is True
        and durable.get("snapshot_stale") is False
        and durable.get("synchronous_commit") == "on"
        and durable.get("in_recovery") is False
        and durable.get("application_outcome_count") == 1
        and durable.get("admission_state_count") == 1
        and endpoint.username is None
        and endpoint.password is None
        and POSTGRES_PASSWORD not in str(durable.get("endpoint", ""))
        and lease.get("holder_id") == holder
        and lease.get("fence_token") == token
        and lease.get("expires_unix_ms", 0) > 0
        and admission.get("rejected_by_reason") == {}
        and admission.get("application_outcome_qoe_debt_enabled") is True
        and admission.get("application_outcome_qoe_debt_ewma_alpha") == 1.0
        and admission.get("application_outcome_qoe_debt_updates") == 1
        and admission.get("active_observation_count") == 1
        and admission.get("active_observations_by_source")
        == {"application_outcome": 1}
        and admission.get("active_observations_by_qoe_debt_source")
        == {"gateway_derived_outcome": 1}
        and admission.get("observation_updates") == 1
        and transport.get("publisher_identity_authorization_rejected") == 0
        and transport.get(
            "application_outcome_identity_authorization_rejected"
        ) == 0
        and transport.get("malformed_h3_requests_rejected") == 0
    )
    if not common:
        return False
    if seed:
        return (
            metrics.get("requests_total") == 2
            and metrics.get("post_requests") == 1
            and metrics.get("get_requests") == 0
            and metrics.get("application_outcome_requests") == 1
            and metrics.get("application_outcome_updates") == 1
            and metrics.get("application_outcome_duplicates") == 0
            and metrics.get("accepted_frames") == 1
            and metrics.get("dequeued_frames") == 0
            and metrics.get("retained_frames") == 1
            and metrics.get("durable_frame_commits") == 1
            and metrics.get("durable_application_outcome_commits") == 1
            and metrics.get("durable_admission_commits") == 2
            and metrics.get("recovered_frames") == 0
            and metrics.get("recovered_dedup_keys") == 0
            and metrics.get("recovered_admission_state") == 0
            and metrics.get("recovered_application_outcomes") == 0
            and durable.get("retained_frame_count") == 1
            and durable.get("dedup_key_count") == 1
            and durable.get("consumer_cursor_count") == 0
            and admission.get("accepted_total") == 1
            and admission.get("accepted_cumulative") == 1
            and admission.get("observation_score_uses") == 0
            and transport.get("connections_created") == 2
            and transport.get("h3_sessions_negotiated") == 2
            and transport.get("client_certificates_accepted") == 2
        )
    return (
        metrics.get("requests_total") == 4
        and metrics.get("post_requests") == 1
        and metrics.get("get_requests") == 2
        and metrics.get("application_outcome_requests") == 1
        and metrics.get("application_outcome_updates") == 0
        and metrics.get("application_outcome_duplicates") == 1
        and metrics.get("accepted_frames") == 1
        and metrics.get("dequeued_frames") == 2
        and metrics.get("retained_frames") == 2
        and metrics.get("durable_frame_commits") == 1
        and metrics.get("durable_application_outcome_commits") == 0
        and metrics.get("durable_admission_commits") == 1
        and metrics.get("recovered_frames") == 1
        and metrics.get("recovered_dedup_keys") == 1
        and metrics.get("recovered_admission_state") == 1
        and metrics.get("recovered_application_outcomes") == 1
        and durable.get("retained_frame_count") == 2
        and durable.get("dedup_key_count") == 2
        and durable.get("consumer_cursor_count") == 1
        and admission.get("accepted_total") == 2
        and admission.get("accepted_cumulative") == 2
        and admission.get("observation_score_uses") == 1
        and transport.get("connections_created") == 3
        and transport.get("h3_sessions_negotiated") == 3
        and transport.get("client_certificates_accepted") == 3
    )


def service_command(
    *, root: Path, temp_root: Path, holder: str, qlogs: Path
) -> str:
    certs = temp_root / "certs"
    policy = temp_root / "admission-policy.json"
    dsn = f"postgresql://postgres:{POSTGRES_PASSWORD}@{POSTGRES_ALIAS}:5432/fleetqox"
    return (
        "tc qdisc replace dev eth0 root netem delay 11ms 2ms loss 0.2% && "
        "tc qdisc show dev eth0 && "
        "exec python3 scripts/fleetrmw_quic_gateway_service.py "
        "--host 0.0.0.0 --port 4503 "
        f"--certificate /work/{(certs / 'server.crt').relative_to(root)} "
        f"--private-key /work/{(certs / 'server.key').relative_to(root)} "
        f"--client-ca /work/{(certs / 'client-ca.crt').relative_to(root)} "
        f"--client-crl /work/{(certs / 'client.crl.pem').relative_to(root)} "
        "--require-client-certificate "
        "--publisher-identity-uri-prefix spiffe://fleetqox/publishers/ "
        f"--admission-policy /work/{policy.relative_to(root)} "
        f"--state-db '{dsn}' "
        f"--writer-lease-instance-id {holder} --writer-lease-ms 3000 "
        f"--qlog-dir /work/{qlogs.relative_to(root)} "
        "--max-frames-per-topic 8 --max-frame-bytes 65536"
    )


def run_client(
    *, root: Path, image: str, network: str, install: str, name: str,
    certs: Path, qlogs: Path, mode: str,
) -> subprocess.CompletedProcess[str]:
    command = (
        "source /opt/ros/jazzy/setup.bash && "
        f"source {install}/setup.bash && "
        "tc qdisc replace dev eth0 root netem delay 9ms 2ms loss 0.2% && "
        "tc qdisc show dev eth0 && "
        "export FLEETQOX_RMW_REMOTE_TRANSPORT=quic_gateway && "
        "export FLEETQOX_RMW_QUIC_BACKEND=inprocess && "
        f"export FLEETQOX_RMW_QUIC_GATEWAY={GATEWAY_ALIAS}:4503 && "
        "export FLEETQOX_RMW_QUIC_SNI=localhost && "
        "export FLEETQOX_RMW_QUIC_TIMEOUT=8s && "
        f"export FLEETQOX_RMW_QUIC_CA_FILE=/work/"
        f"{(certs / 'server-ca.crt').relative_to(root)} && "
        f"export FLEETQOX_RMW_QUIC_CLIENT_CERT_FILE=/work/"
        f"{(certs / 'client.crt').relative_to(root)} && "
        f"export FLEETQOX_RMW_QUIC_CLIENT_KEY_FILE=/work/"
        f"{(certs / 'client.key').relative_to(root)} && "
        f"export FLEETQOX_RMW_QUIC_QLOG_DIR=/work/{qlogs.relative_to(root)} && "
        f"{install}/rmw_fleetqox_cpp/lib/rmw_fleetqox_cpp/"
        f"fleetrmw_quic_durable_application_outcome_failover_probe {mode}"
    )
    return run([
        "docker", "run", "--rm", "--name", name,
        "--network", network, "--cap-add", "NET_ADMIN",
        "--entrypoint", "bash", "-v", f"{root}:/work", "-w", "/work",
        image, "-lc", command,
    ])


def run_phase(
    *, root: Path, image: str, network: str, install: str,
    temp_root: Path, index: int, mode: str, holder: str, token: int,
) -> dict[str, Any]:
    suffix = f"{os.getpid()}-{index}-{mode}"
    phase_root = temp_root / f"run-{index}" / mode
    service_qlogs = phase_root / "service-qlogs"
    client_qlogs = phase_root / "client-qlogs"
    service_qlogs.mkdir(parents=True, exist_ok=True)
    client_qlogs.mkdir(parents=True, exist_ok=True)
    service_name = f"fleetrmw-pg-outcome-service-{suffix}"
    started = run([
        "docker", "run", "-d", "--name", service_name,
        "--network", network, "--network-alias", GATEWAY_ALIAS,
        "--cap-add", "NET_ADMIN", "--entrypoint", "bash",
        "-v", f"{root}:/work", "-w", "/work", image, "-lc",
        service_command(
            root=root, temp_root=temp_root, holder=holder, qlogs=service_qlogs
        ),
    ])
    ready = started.returncode == 0 and wait_service_ready(service_name)
    client = subprocess.CompletedProcess([], 1, "", "service_not_ready")
    if ready:
        client = run_client(
            root=root, image=image, network=network, install=install,
            name=f"fleetrmw-pg-outcome-client-{suffix}",
            certs=temp_root / "certs", qlogs=client_qlogs, mode=mode,
        )
        time.sleep(1.2)
    exit_code, logs, service = stop_service(service_name)
    rows = json_rows(client.stdout)
    probe = rows[-1] if rows else {}
    qlogs = [
        path for directory in (service_qlogs, client_qlogs)
        for path in directory.glob("*") if path.is_file()
    ]
    netem_ok = "qdisc netem" in logs and "qdisc netem" in client.stdout
    qlog_ok = bool(qlogs) and all(path.stat().st_size > 0 for path in qlogs)
    service_valid = service_ok(service, mode=mode, holder=holder, token=token)
    ok = (
        ready and client.returncode == 0 and exit_code == 0
        and probe_ok(probe, mode) and service_valid and netem_ok and qlog_ok
    )
    return {
        "mode": mode,
        "status": "ok" if ok else "failed",
        "probe": probe,
        "service": service,
        "postgresql_service_validation": service_valid,
        "netem_configured_both_containers": netem_ok,
        "qlog_file_count": len(qlogs),
        "qlog_total_bytes": sum(path.stat().st_size for path in qlogs),
        "client_returncode": client.returncode,
        "service_exit_code": exit_code,
        "client_stdout": "" if ok else client.stdout,
        "client_stderr": "" if ok else client.stderr,
        "service_logs": "" if ok else logs,
    }


def case_ok(row: dict[str, Any]) -> bool:
    database = row.get("database", {})
    shutdown = row.get("database_shutdown", {})
    return (
        row.get("status") == "ok"
        and database.get("status") == "ok"
        and database.get("ready") is True
        and database.get("image") == POSTGRES_IMAGE
        and bool(database.get("server_version"))
        and shutdown.get("running_through_gateway_takeover") is True
        and shutdown.get("clean_database_logs") is True
        and shutdown.get("remove_returncode") == 0
        and 0 <= row.get("gateway_replacement_latency_ms", -1) < 8000
        and row.get("active", {}).get("status") == "ok"
        and row.get("replacement", {}).get("status") == "ok"
        and probe_ok(row["active"].get("probe", {}), "seed")
        and probe_ok(row["replacement"].get("probe", {}), "resume")
        and service_ok(
            row["active"].get("service", {}), mode="seed",
            holder="gateway-a", token=1,
        )
        and service_ok(
            row["replacement"].get("service", {}), mode="resume",
            holder="gateway-b", token=2,
        )
    )


def run_case(
    *, root: Path, image: str, network: str, install: str,
    temp_root: Path, index: int,
) -> dict[str, Any]:
    suffix = f"{os.getpid()}-{index}"
    database_name = f"fleetrmw-pg-outcome-db-{suffix}"
    database = start_postgres(network=network, name=database_name)
    active: dict[str, Any] = {"status": "skipped"}
    replacement: dict[str, Any] = {"status": "skipped"}
    replacement_latency_ms = -1
    try:
        if database["status"] == "ok":
            active = run_phase(
                root=root, image=image, network=network, install=install,
                temp_root=temp_root, index=index, mode="seed",
                holder="gateway-a", token=1,
            )
        if active["status"] == "ok":
            replacement_started = time.monotonic()
            replacement = run_phase(
                root=root, image=image, network=network, install=install,
                temp_root=temp_root, index=index, mode="resume",
                holder="gateway-b", token=2,
            )
            replacement_latency_ms = round(
                (time.monotonic() - replacement_started) * 1000.0
            )
    finally:
        database_shutdown = stop_postgres(database_name)
    row = {
        "index": index,
        "database": database,
        "database_shutdown": database_shutdown,
        "gateway_replacement_latency_ms": replacement_latency_ms,
        "active": active,
        "replacement": replacement,
    }
    row["status"] = "ok"
    if not case_ok(row):
        row["status"] = "failed"
    return row


def run_probe(
    *, root: Path, image: str, iterations: int, keep_temp: bool
) -> dict[str, Any]:
    run_count = max(1, iterations)
    temp_root = root / f".tmp_fleetrmw_quic_pg_outcome_{os.getpid()}"
    certs = temp_root / "certs"
    certs.mkdir(parents=True, exist_ok=True)
    (temp_root / "admission-policy.json").write_text(
        json.dumps(policy_document(), sort_keys=True) + "\n", encoding="utf-8"
    )
    build_root = "/work/.tmp_fleetrmw_quic_pg_outcome_build"
    install = "/work/.tmp_fleetrmw_quic_pg_outcome_install"
    log_root = "/work/.tmp_fleetrmw_quic_pg_outcome_log"
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
    network = f"fleetrmw-pg-outcome-net-{os.getpid()}"
    network_result = run(["docker", "network", "create", network])
    runs: list[dict[str, Any]] = []
    try:
        if cert_result.returncode == build.returncode == network_result.returncode == 0:
            for index in range(1, run_count + 1):
                runs.append(run_case(
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
    successful = sum(row.get("status") == "ok" for row in runs)
    status = "ok" if (
        cert_result.returncode == build.returncode == network_result.returncode == 0
        and len(runs) == successful == run_count
    ) else "failed"
    latencies = [
        row["gateway_replacement_latency_ms"] for row in runs
        if row.get("gateway_replacement_latency_ms", -1) >= 0
    ]
    return {
        "schema_version": SCHEMA_VERSION,
        "status": status,
        "run_count": run_count,
        "successful_runs": successful,
        "failed_run_count": run_count - successful,
        "container_count_per_run": 5,
        "gateway_instance_count_per_run": 2,
        "database_instance_count_per_run": 1,
        "real_quic_v1_h3": True,
        "mutual_tls_client_authentication_required": True,
        "publisher_identity_binding_required": True,
        "networked_postgresql_durable_state_claim": status == "ok",
        "synchronous_commit_claim": status == "ok",
        "postgresql_writer_fencing_claim": status == "ok",
        "application_outcome_atomic_admission_commit_claim": status == "ok",
        "application_outcome_postgresql_failover_recovery_claim": status == "ok",
        "application_outcome_cross_gateway_idempotence_claim": status == "ok",
        "application_outcome_admission_effect_after_failover_claim": status == "ok",
        "max_gateway_replacement_latency_ms": max(latencies, default=-1),
        "database_process_failover_claim": False,
        "replicated_database_claim": False,
        "active_active_consensus_claim": False,
        "production_readiness": False,
        "certificate_returncode": cert_result.returncode,
        "build_returncode": build.returncode,
        "build_stderr": build.stderr[-4000:],
        "network_returncode": network_result.returncode,
        "runs": runs,
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
            "docker_quic_postgresql_application_outcome_failover_probe_summary.json"
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
        print("fleetrmw-quic-postgresql-application-outcome-failover-probe")
        print(f"  status: {summary['status']}")
        print(f"  successful_runs: {summary['successful_runs']}/{summary['run_count']}")
    return 0 if summary["status"] == "ok" else 1


if __name__ == "__main__":
    raise SystemExit(main())

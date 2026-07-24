#!/usr/bin/env python3
"""Prove application-outcome QoE debt survives QUIC gateway failover."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import shutil
import subprocess
import time
from typing import Any

try:
    from scripts.run_rmw_docker_quic_mtls_probe import certificate_command
    from scripts.run_rmw_docker_quic_stateful_gateway_probe import (
        DEFAULT_IMAGE,
        SERVICE_SCHEMA_VERSION,
        json_rows,
        run,
        wait_service_ready,
    )
except ModuleNotFoundError:
    from run_rmw_docker_quic_mtls_probe import certificate_command
    from run_rmw_docker_quic_stateful_gateway_probe import (
        DEFAULT_IMAGE,
        SERVICE_SCHEMA_VERSION,
        json_rows,
        run,
        wait_service_ready,
    )


ROOT = Path(__file__).resolve().parents[1]
SCHEMA_VERSION = (
    "fleetrmw.docker_quic_durable_application_outcome_failover_probe.v1"
)
PROBE_SCHEMA_VERSION = (
    "fleetrmw.quic_durable_application_outcome_failover_probe.v1"
)


def probe_ok(row: dict[str, Any], mode: str) -> bool:
    seed = mode == "seed"
    return (
        row.get("schema_version") == PROBE_SCHEMA_VERSION
        and row.get("status") == "ok"
        and row.get("mode") == mode
        and row.get("seed_admitted") is seed
        and row.get("outcome_accepted") is seed
        and row.get("duplicate_outcome_idempotent") is (not seed)
        and row.get("low_admitted_after_failover") is (not seed)
        and row.get("payloads_replayed") is (not seed)
        and row.get("connections_created") == (2 if seed else 3)
        and row.get("handshakes_completed") == (2 if seed else 3)
        and row.get("streams_opened") == (2 if seed else 4)
        and row.get("connection_reuse_count") == (0 if seed else 1)
        and row.get("tls_peer_verification_required") is True
        and row.get("mutual_tls_required") is True
        and row.get("subprocess_backed") is False
        and row.get("production_readiness") is False
    )


def service_ok(row: dict[str, Any], mode: str) -> bool:
    seed = mode == "seed"
    metrics = row.get("metrics", {})
    admission = metrics.get("admission", {})
    durable = metrics.get("durable_state", {})
    transport = row.get("transport_metrics", {})
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
        and row.get("application_outcome_qoe_debt_configured") is True
        and metrics.get("durable_state_enabled") is True
        and metrics.get("durable_persistence_failures") == 0
        and metrics.get("invalid_frames") == 0
        and metrics.get("invalid_application_outcomes") == 0
        and metrics.get("application_outcome_unknown_frames") == 0
        and metrics.get("application_outcome_key_count") == 1
        and metrics.get("topic_count") == 1
        and durable.get("schema_version")
        == "fleetrmw.quic_gateway_durable_state.v1"
        and durable.get("journal_mode") == "wal"
        and durable.get("synchronous") == "full"
        and durable.get("application_outcome_count") == 1
        and durable.get("admission_state_count") == 1
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
        and transport.get("missing_client_certificates_rejected") == 0
        and transport.get("untrusted_client_certificates_rejected") == 0
        and transport.get("revoked_client_certificates_rejected") == 0
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
        and admission.get("accepted_total") == 2
        and admission.get("accepted_cumulative") == 2
        and admission.get("observation_score_uses") == 1
        and transport.get("connections_created") == 3
        and transport.get("h3_sessions_negotiated") == 3
        and transport.get("client_certificates_accepted") == 3
    )


def policy_document() -> dict[str, Any]:
    return {
        "schema_version": "fleetrmw.quic_gateway_admission_policy.v1",
        "default_action": "deny",
        "observation_ttl_ms": 60000,
        "application_outcome_qoe_debt": {
            "enabled": True,
            "ewma_alpha": 1.0,
        },
        "rules": [{
            "domain_id": 42,
            "topic": "/fleetqox/durable_application_outcome",
            "traffic_class": "control",
            "max_accepted_frames": 2,
            "allowed_publishers": ["mtls-publisher"],
            "min_admission_score": 0.45,
        }],
    }


def run_phase(
    *, root: Path, image: str, network: str, install: str,
    temp_root: Path, index: int, mode: str,
) -> dict[str, Any]:
    suffix = f"{os.getpid()}-{index}-{mode}"
    service_name = f"fleetrmw-durable-outcome-service-{suffix}"
    phase_root = temp_root / f"run-{index}" / mode
    service_qlogs = phase_root / "service-qlogs"
    client_qlogs = phase_root / "client-qlogs"
    service_qlogs.mkdir(parents=True, exist_ok=True)
    client_qlogs.mkdir(parents=True, exist_ok=True)
    certs = temp_root / "certs"
    policy = temp_root / "admission-policy.json"
    database = temp_root / f"run-{index}" / "gateway-state.sqlite3"
    service_command = (
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
        f"--state-db /work/{database.relative_to(root)} "
        f"--qlog-dir /work/{service_qlogs.relative_to(root)} "
        "--max-frames-per-topic 8 --max-frame-bytes 65536"
    )
    started = run([
        "docker", "run", "-d", "--name", service_name,
        "--network", network, "--network-alias", "fleetqox-mtls-gateway",
        "--cap-add", "NET_ADMIN", "--entrypoint", "bash",
        "-v", f"{root}:/work", "-w", "/work", image, "-lc", service_command,
    ])
    ready = started.returncode == 0 and wait_service_ready(service_name)
    client = subprocess.CompletedProcess([], 1, "", "service_not_ready")
    service_exit_code = -1
    service_logs = ""
    try:
        if ready:
            client_command = (
                "source /opt/ros/jazzy/setup.bash && "
                f"source {install}/setup.bash && "
                "tc qdisc replace dev eth0 root netem delay 9ms 2ms loss 0.2% && "
                "tc qdisc show dev eth0 && "
                "export FLEETQOX_RMW_REMOTE_TRANSPORT=quic_gateway && "
                "export FLEETQOX_RMW_QUIC_BACKEND=inprocess && "
                "export FLEETQOX_RMW_QUIC_GATEWAY=fleetqox-mtls-gateway:4503 && "
                "export FLEETQOX_RMW_QUIC_SNI=localhost && "
                "export FLEETQOX_RMW_QUIC_TIMEOUT=8s && "
                f"export FLEETQOX_RMW_QUIC_CA_FILE=/work/"
                f"{(certs / 'server-ca.crt').relative_to(root)} && "
                f"export FLEETQOX_RMW_QUIC_CLIENT_CERT_FILE=/work/"
                f"{(certs / 'client.crt').relative_to(root)} && "
                f"export FLEETQOX_RMW_QUIC_CLIENT_KEY_FILE=/work/"
                f"{(certs / 'client.key').relative_to(root)} && "
                f"export FLEETQOX_RMW_QUIC_QLOG_DIR=/work/"
                f"{client_qlogs.relative_to(root)} && "
                f"{install}/rmw_fleetqox_cpp/lib/rmw_fleetqox_cpp/"
                f"fleetrmw_quic_durable_application_outcome_failover_probe {mode}"
            )
            client = run([
                "docker", "run", "--rm",
                "--name", f"fleetrmw-durable-outcome-client-{suffix}",
                "--network", network, "--cap-add", "NET_ADMIN",
                "--entrypoint", "bash", "-v", f"{root}:/work",
                "-w", "/work", image, "-lc", client_command,
            ])
        time.sleep(0.5)
        run(["docker", "stop", "--time", "3", service_name])
        inspected = run([
            "docker", "inspect", "-f", "{{.State.ExitCode}}", service_name
        ])
        if inspected.returncode == 0 and inspected.stdout.strip():
            service_exit_code = int(inspected.stdout.strip())
        service_logs = run(["docker", "logs", service_name]).stdout
    finally:
        run(["docker", "rm", "-f", service_name])

    probe_rows = json_rows(client.stdout)
    service_rows = json_rows(service_logs)
    probe = probe_rows[-1] if probe_rows else {}
    service = service_rows[-1] if service_rows else {}
    qlogs = [
        path
        for directory in (service_qlogs, client_qlogs)
        for path in directory.glob("*")
        if path.is_file()
    ]
    netem_ok = "qdisc netem" in service_logs and "qdisc netem" in client.stdout
    qlog_ok = qlogs and all(path.stat().st_size > 0 for path in qlogs)
    ok = (
        ready and client.returncode == 0 and service_exit_code == 0
        and probe_ok(probe, mode) and service_ok(service, mode)
        and netem_ok and bool(qlog_ok)
    )
    return {
        "mode": mode,
        "status": "ok" if ok else "failed",
        "probe": probe,
        "service": service,
        "netem_configured_both_containers": netem_ok,
        "qlog_file_count": len(qlogs),
        "qlog_total_bytes": sum(path.stat().st_size for path in qlogs),
        "client_returncode": client.returncode,
        "service_exit_code": service_exit_code,
        "client_stdout": "" if ok else client.stdout,
        "client_stderr": "" if ok else client.stderr,
        "service_logs": "" if ok else service_logs,
    }


def run_case(
    *, root: Path, image: str, network: str, install: str,
    temp_root: Path, index: int,
) -> dict[str, Any]:
    seed = run_phase(
        root=root, image=image, network=network, install=install,
        temp_root=temp_root, index=index, mode="seed",
    )
    resume = (
        run_phase(
            root=root, image=image, network=network, install=install,
            temp_root=temp_root, index=index, mode="resume",
        )
        if seed["status"] == "ok" else {"status": "skipped"}
    )
    ok = seed["status"] == resume["status"] == "ok"
    return {
        "index": index,
        "status": "ok" if ok else "failed",
        "seed": seed,
        "resume": resume,
    }


def run_probe(
    *, root: Path, image: str, iterations: int, keep_temp: bool
) -> dict[str, Any]:
    run_count = max(1, iterations)
    temp_root = root / f".tmp_fleetrmw_quic_durable_outcome_{os.getpid()}"
    certs = temp_root / "certs"
    certs.mkdir(parents=True, exist_ok=True)
    (temp_root / "admission-policy.json").write_text(
        json.dumps(policy_document(), sort_keys=True) + "\n", encoding="utf-8"
    )
    build_root = "/work/.tmp_fleetrmw_quic_durable_outcome_build"
    install = "/work/.tmp_fleetrmw_quic_durable_outcome_install"
    log_root = "/work/.tmp_fleetrmw_quic_durable_outcome_log"
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
    network = f"fleetrmw-durable-outcome-net-{os.getpid()}"
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
    return {
        "schema_version": SCHEMA_VERSION,
        "status": status,
        "run_count": run_count,
        "successful_runs": successful,
        "failed_run_count": run_count - successful,
        "container_count_per_run": 4,
        "gateway_instance_count_per_run": 2,
        "real_quic_v1_h3": True,
        "mutual_tls_client_authentication_required": True,
        "publisher_identity_binding_required": True,
        "sqlite_wal_full_sync_claim": status == "ok",
        "application_outcome_atomic_admission_commit_claim": status == "ok",
        "application_outcome_failover_recovery_claim": status == "ok",
        "application_outcome_cross_gateway_idempotence_claim": status == "ok",
        "application_outcome_admission_effect_after_failover_claim": status == "ok",
        "sequential_gateway_instance_failover_claim": status == "ok",
        "active_active_consensus_claim": False,
        "distributed_database_claim": False,
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
            "docker_quic_durable_application_outcome_failover_probe_summary.json"
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
        print("fleetrmw-quic-durable-application-outcome-failover-probe")
        print(f"  status: {summary['status']}")
        print(f"  successful_runs: {summary['successful_runs']}/{summary['run_count']}")
    return 0 if summary["status"] == "ok" else 1


if __name__ == "__main__":
    raise SystemExit(main())

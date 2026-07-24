#!/usr/bin/env python3
"""Validate durable admission/repair recovery and policy fingerprint fencing."""

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
    from scripts.run_rmw_docker_quic_admission_probe import certificate_command
    from scripts.run_rmw_docker_quic_stateful_gateway_probe import (
        DEFAULT_IMAGE,
        SERVICE_SCHEMA_VERSION,
        json_rows,
        run,
        wait_service_ready,
    )
except ModuleNotFoundError:
    from run_rmw_docker_quic_admission_probe import certificate_command
    from run_rmw_docker_quic_stateful_gateway_probe import (
        DEFAULT_IMAGE,
        SERVICE_SCHEMA_VERSION,
        json_rows,
        run,
        wait_service_ready,
    )


ROOT = Path(__file__).resolve().parents[1]
SCHEMA_VERSION = "fleetrmw.docker_quic_durable_admission_failover_probe.v1"
PROBE_SCHEMA_VERSION = "fleetrmw.quic_durable_admission_failover_probe.v1"


def probe_ok(row: dict[str, Any], mode: str) -> bool:
    seed = mode == "seed"
    return (
        row.get("schema_version") == PROBE_SCHEMA_VERSION
        and row.get("status") == "ok"
        and row.get("mode") == mode
        and row.get("normal_admitted") is seed
        and row.get("repair_admitted") is seed
        and row.get("resumed_repair_rejected") is (not seed)
        and row.get("connections_created") == 1
        and row.get("handshakes_completed") == 1
        and row.get("streams_opened") == (2 if seed else 1)
        and row.get("connection_reuse_count") == (1 if seed else 0)
        and row.get("frames_sent") == (2 if seed else 0)
        and row.get("frames_failed") == (0 if seed else 1)
        and row.get("tls_peer_verification_required") is True
        and row.get("subprocess_backed") is False
        and row.get("production_readiness") is False
    )


def service_ok(row: dict[str, Any], mode: str) -> bool:
    metrics = row.get("metrics", {})
    admission = metrics.get("admission", {})
    durable = metrics.get("durable_state", {})
    transport = row.get("transport_metrics", {})
    common = (
        row.get("schema_version") == SERVICE_SCHEMA_VERSION
        and row.get("status") == "stopped"
        and row.get("clean_teardown") is True
        and row.get("admission_policy_configured") is True
        and row.get("durable_state_configured") is True
        and metrics.get("durable_state_enabled") is True
        and metrics.get("durable_persistence_failures") == 0
        and metrics.get("retained_frames") == 2
        and durable.get("schema_version")
        == "fleetrmw.quic_gateway_durable_state.v1"
        and durable.get("journal_mode") == "wal"
        and durable.get("synchronous") == "full"
        and durable.get("retained_frame_count") == 2
        and durable.get("dedup_key_count") == 2
        and durable.get("admission_state_count") == 1
        and admission.get("accepted_total") == 1
        and admission.get("accepted_cumulative") == 2
        and admission.get("accepted_by_class") == {"control": 2}
        and admission.get("repair_admitted_count") == 1
        and admission.get("repair_allocated_bytes", 0) > 0
        and transport.get("connections_created") == 1
        and transport.get("h3_sessions_negotiated") == 1
    )
    if not common:
        return False
    if mode == "seed":
        return (
            metrics.get("requests_total") == 2
            and metrics.get("post_requests") == 2
            and metrics.get("accepted_frames") == 2
            and metrics.get("duplicate_frames") == 0
            and metrics.get("durable_frame_commits") == 2
            and metrics.get("durable_admission_commits") == 2
            and metrics.get("recovered_frames") == 0
            and metrics.get("recovered_admission_state") == 0
            and admission.get("repair_deferred_count") == 0
            and admission.get("rejected_by_reason") == {}
        )
    return (
        metrics.get("requests_total") == 1
        and metrics.get("post_requests") == 1
        and metrics.get("accepted_frames") == 0
        and metrics.get("duplicate_frames") == 0
        and metrics.get("durable_frame_commits") == 0
        and metrics.get("durable_admission_commits") == 0
        and metrics.get("recovered_frames") == 2
        and metrics.get("recovered_dedup_keys") == 2
        and metrics.get("recovered_admission_state") == 1
        and admission.get("repair_deferred_count") == 1
        and admission.get("rejected_by_reason")
        == {"stream_quota_exhausted": 1}
    )


def run_phase(
    *,
    root: Path,
    image: str,
    network: str,
    install: str,
    temp_root: Path,
    index: int,
    mode: str,
) -> dict[str, Any]:
    suffix = f"{os.getpid()}-{index}-{mode}"
    service_name = f"fleetrmw-durable-admission-service-{suffix}"
    phase_root = temp_root / f"run-{index}" / mode
    service_qlogs = phase_root / "service-qlogs"
    client_qlogs = phase_root / "client-qlogs"
    service_qlogs.mkdir(parents=True, exist_ok=True)
    client_qlogs.mkdir(parents=True, exist_ok=True)
    certs = temp_root / "certs"
    policy = temp_root / "admission-policy.json"
    database = temp_root / f"run-{index}" / "gateway-state.sqlite3"
    service_command = (
        "tc qdisc replace dev eth0 root netem delay 5ms 1ms loss 0.2% && "
        "tc qdisc show dev eth0 && "
        "exec python3 scripts/fleetrmw_quic_gateway_service.py "
        "--host 0.0.0.0 --port 4503 "
        f"--certificate /work/{(certs / 'server.crt').relative_to(root)} "
        f"--private-key /work/{(certs / 'server.key').relative_to(root)} "
        f"--admission-policy /work/{policy.relative_to(root)} "
        f"--state-db /work/{database.relative_to(root)} "
        f"--qlog-dir /work/{service_qlogs.relative_to(root)} "
        "--max-frames-per-topic 8 --max-frame-bytes 65536"
    )
    started = run(
        [
            "docker", "run", "-d", "--name", service_name,
            "--network", network,
            "--network-alias", "fleetqox-admission-gateway",
            "--cap-add", "NET_ADMIN",
            "--entrypoint", "bash",
            "-v", f"{root}:/work", "-w", "/work", image, "-lc", service_command,
        ]
    )
    ready = started.returncode == 0 and wait_service_ready(service_name)
    client = subprocess.CompletedProcess([], 1, "", "service_not_ready")
    service_exit_code = -1
    service_logs = ""
    try:
        if ready:
            client_command = (
                "source /opt/ros/jazzy/setup.bash && "
                f"source {install}/setup.bash && "
                "tc qdisc replace dev eth0 root netem delay 7ms 2ms loss 0.2% && "
                "tc qdisc show dev eth0 && "
                "export FLEETQOX_RMW_REMOTE_TRANSPORT=quic_gateway && "
                "export FLEETQOX_RMW_QUIC_BACKEND=inprocess && "
                "export FLEETQOX_RMW_QUIC_GATEWAY=fleetqox-admission-gateway:4503 && "
                "export FLEETQOX_RMW_QUIC_URI=https://localhost:4503/fleetrmw/v1/frames && "
                "export FLEETQOX_RMW_QUIC_SNI=localhost && "
                "export FLEETQOX_RMW_QUIC_TIMEOUT=8s && "
                f"export FLEETQOX_RMW_QUIC_CA_FILE=/work/{(certs / 'ca.crt').relative_to(root)} && "
                f"export FLEETQOX_RMW_QUIC_QLOG_DIR=/work/{client_qlogs.relative_to(root)} && "
                f"{install}/rmw_fleetqox_cpp/lib/rmw_fleetqox_cpp/"
                f"fleetrmw_quic_durable_admission_failover_probe {mode}"
            )
            client = run(
                [
                    "docker", "run", "--rm",
                    "--name", f"fleetrmw-durable-admission-client-{suffix}",
                    "--network", network, "--cap-add", "NET_ADMIN",
                    "--entrypoint", "bash", "-v", f"{root}:/work",
                    "-w", "/work", image, "-lc", client_command,
                ]
            )
        time.sleep(0.3)
        run(["docker", "stop", "--time", "3", service_name])
        inspected = run(
            ["docker", "inspect", "-f", "{{.State.ExitCode}}", service_name]
        )
        if inspected.returncode == 0 and inspected.stdout.strip():
            service_exit_code = int(inspected.stdout.strip())
        service_logs = run(["docker", "logs", service_name]).stdout
    finally:
        run(["docker", "rm", "-f", service_name])

    probe_rows = json_rows(client.stdout)
    service_rows = json_rows(service_logs)
    probe = probe_rows[-1] if probe_rows else {}
    service = service_rows[-1] if service_rows else {}
    qlog_files = [
        path
        for directory in (service_qlogs, client_qlogs)
        for path in directory.glob("*")
        if path.is_file()
    ]
    netem_ok = "qdisc netem" in service_logs and "qdisc netem" in client.stdout
    qlog_ok = qlog_files and all(path.stat().st_size > 0 for path in qlog_files)
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
        "qlog_file_count": len(qlog_files),
        "qlog_total_bytes": sum(path.stat().st_size for path in qlog_files),
        "client_returncode": client.returncode,
        "service_exit_code": service_exit_code,
        "client_stdout": "" if ok else client.stdout,
        "client_stderr": "" if ok else client.stderr,
        "service_logs": "" if ok else service_logs,
    }


def run_mismatch_control(
    *, root: Path, image: str, temp_root: Path, index: int
) -> dict[str, Any]:
    certs = temp_root / "certs"
    policy = temp_root / "mismatched-admission-policy.json"
    database = temp_root / f"run-{index}" / "gateway-state.sqlite3"
    command = (
        "python3 scripts/fleetrmw_quic_gateway_service.py "
        "--host 127.0.0.1 --port 4503 "
        f"--certificate /work/{(certs / 'server.crt').relative_to(root)} "
        f"--private-key /work/{(certs / 'server.key').relative_to(root)} "
        f"--admission-policy /work/{policy.relative_to(root)} "
        f"--state-db /work/{database.relative_to(root)}"
    )
    result = run(
        [
            "docker", "run", "--rm", "--entrypoint", "bash",
            "-v", f"{root}:/work", "-w", "/work", image, "-lc", command,
        ]
    )
    combined = result.stdout + result.stderr
    ok = result.returncode != 0 and "fingerprint does not match" in combined
    return {
        "status": "ok" if ok else "failed",
        "returncode": result.returncode,
        "fingerprint_mismatch_fail_closed": ok,
        "output": "" if ok else combined[-4000:],
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
    mismatch = (
        run_mismatch_control(root=root, image=image, temp_root=temp_root, index=index)
        if resume["status"] == "ok" else {"status": "skipped"}
    )
    ok = seed["status"] == resume["status"] == mismatch["status"] == "ok"
    return {
        "index": index,
        "status": "ok" if ok else "failed",
        "seed": seed,
        "resume": resume,
        "mismatch_control": mismatch,
    }


def run_probe(
    *, root: Path, image: str, iterations: int, keep_temp: bool
) -> dict[str, Any]:
    run_count = max(1, iterations)
    temp_root = root / f".tmp_fleetrmw_quic_durable_admission_{os.getpid()}"
    certs = temp_root / "certs"
    certs.mkdir(parents=True, exist_ok=True)
    policy_document = {
        "schema_version": "fleetrmw.quic_gateway_admission_policy.v1",
        "default_action": "deny",
        "max_accepted_frames": 1,
        "rules": [{
            "domain_id": 42,
            "topic": "/fleetqox/durable_admission",
            "traffic_class": "control",
            "max_accepted_frames": 1,
            "allowed_publishers": ["durable-admission-publisher"],
        }],
        "repair": {
            "capacity_bytes": 1024,
            "max_admitted": 1,
            "paths": [{
                "path_id": "private_5g", "latency_ms": 20.0,
                "loss": 0.01, "failure_domain": "private_5g",
            }],
        },
    }
    (temp_root / "admission-policy.json").write_text(
        json.dumps(policy_document, sort_keys=True) + "\n", encoding="utf-8"
    )
    mismatch = {**policy_document, "max_accepted_frames": 2}
    (temp_root / "mismatched-admission-policy.json").write_text(
        json.dumps(mismatch, sort_keys=True) + "\n", encoding="utf-8"
    )
    build_root = "/work/.tmp_fleetrmw_quic_durable_admission_build"
    install = "/work/.tmp_fleetrmw_quic_durable_admission_install"
    log_root = "/work/.tmp_fleetrmw_quic_durable_admission_log"
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
    network = f"fleetrmw-durable-admission-net-{os.getpid()}"
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
    return {
        "schema_version": SCHEMA_VERSION,
        "status": status,
        "run_count": run_count,
        "successful_runs": successful,
        "failed_run_count": run_count - successful,
        "container_count_per_run": 5,
        "gateway_instance_count_per_run": 3,
        "real_quic_v1_h3": True,
        "sqlite_wal_full_sync_claim": status == "ok",
        "frame_and_admission_single_transaction_claim": status == "ok",
        "admission_quota_failover_recovery_claim": status == "ok",
        "repair_capacity_failover_recovery_claim": status == "ok",
        "policy_fingerprint_mismatch_fail_closed_claim": status == "ok",
        "sequential_gateway_instance_failover_claim": status == "ok",
        "active_active_consensus_claim": False,
        "distributed_database_claim": False,
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
        default="results_rmw_socket/docker_quic_durable_admission_failover_probe_summary.json",
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
        print("fleetrmw-quic-durable-admission-failover-probe")
        print(f"  status: {summary['status']}")
        print(f"  successful_runs: {summary['successful_runs']}/{summary['run_count']}")
    return 0 if summary["status"] == "ok" else 1


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
"""Validate single-writer lease fencing and manual active/passive takeover."""

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
    from scripts.run_rmw_docker_quic_durable_admission_failover_probe import (
        probe_ok,
        service_ok,
    )
    from scripts.run_rmw_docker_quic_stateful_gateway_probe import (
        DEFAULT_IMAGE,
        json_rows,
        run,
        wait_service_ready,
    )
except ModuleNotFoundError:
    from run_rmw_docker_quic_admission_probe import certificate_command
    from run_rmw_docker_quic_durable_admission_failover_probe import (
        probe_ok,
        service_ok,
    )
    from run_rmw_docker_quic_stateful_gateway_probe import (
        DEFAULT_IMAGE,
        json_rows,
        run,
        wait_service_ready,
    )


ROOT = Path(__file__).resolve().parents[1]
SCHEMA_VERSION = "fleetrmw.docker_quic_writer_fencing_probe.v1"


def service_with_lease_ok(
    row: dict[str, Any], *, mode: str, holder: str, token: int
) -> bool:
    metrics = row.get("metrics", {})
    durable = metrics.get("durable_state", {})
    lease = durable.get("writer_lease", {})
    return (
        service_ok(row, mode)
        and row.get("writer_lease_configured") is True
        and row.get("writer_lease_instance_id") == holder
        and row.get("writer_lease_ms") == 3000
        and metrics.get("durable_writer_lease_acquires") == 1
        and metrics.get("durable_writer_lease_renewals", 0) >= 1
        and metrics.get("durable_writer_lease_failures") == 0
        and lease.get("holder_id") == holder
        and lease.get("fence_token") == token
        and lease.get("expires_unix_ms", 0) > 0
    )


def service_command(
    *, root: Path, temp_root: Path, index: int, holder: str, qlogs: Path
) -> str:
    certs = temp_root / "certs"
    policy = temp_root / "admission-policy.json"
    database = temp_root / f"run-{index}" / "gateway-state.sqlite3"
    return (
        "tc qdisc replace dev eth0 root netem delay 5ms 1ms loss 0.2% && "
        "tc qdisc show dev eth0 && "
        "exec python3 scripts/fleetrmw_quic_gateway_service.py "
        "--host 0.0.0.0 --port 4504 "
        f"--certificate /work/{(certs / 'server.crt').relative_to(root)} "
        f"--private-key /work/{(certs / 'server.key').relative_to(root)} "
        f"--admission-policy /work/{policy.relative_to(root)} "
        f"--state-db /work/{database.relative_to(root)} "
        f"--writer-lease-instance-id {holder} --writer-lease-ms 3000 "
        f"--qlog-dir /work/{qlogs.relative_to(root)} "
        "--max-frames-per-topic 8 --max-frame-bytes 65536"
    )


def start_service(
    *, root: Path, image: str, network: str, name: str,
    command: str, alias: str,
) -> bool:
    started = run([
        "docker", "run", "-d", "--name", name,
        "--network", network, "--network-alias", alias,
        "--cap-add", "NET_ADMIN", "--entrypoint", "bash",
        "-v", f"{root}:/work", "-w", "/work", image, "-lc", command,
    ])
    return started.returncode == 0 and wait_service_ready(name)


def stop_service(name: str) -> tuple[int, str, dict[str, Any]]:
    run(["docker", "stop", "--time", "3", name])
    inspected = run(["docker", "inspect", "-f", "{{.State.ExitCode}}", name])
    exit_code = (
        int(inspected.stdout.strip())
        if inspected.returncode == 0 and inspected.stdout.strip() else -1
    )
    logs = run(["docker", "logs", name]).stdout
    rows = json_rows(logs)
    service = rows[-1] if rows else {}
    run(["docker", "rm", "-f", name])
    return exit_code, logs, service


def run_client(
    *, root: Path, image: str, network: str, install: str,
    name: str, certs: Path, qlogs: Path, mode: str,
) -> subprocess.CompletedProcess[str]:
    command = (
        "source /opt/ros/jazzy/setup.bash && "
        f"source {install}/setup.bash && "
        "tc qdisc replace dev eth0 root netem delay 7ms 2ms loss 0.2% && "
        "tc qdisc show dev eth0 && "
        "export FLEETQOX_RMW_REMOTE_TRANSPORT=quic_gateway && "
        "export FLEETQOX_RMW_QUIC_BACKEND=inprocess && "
        "export FLEETQOX_RMW_QUIC_GATEWAY=fleetqox-admission-gateway:4504 && "
        "export FLEETQOX_RMW_QUIC_URI=https://localhost:4504/fleetrmw/v1/frames && "
        "export FLEETQOX_RMW_QUIC_SNI=localhost && "
        "export FLEETQOX_RMW_QUIC_TIMEOUT=8s && "
        f"export FLEETQOX_RMW_QUIC_CA_FILE=/work/{(certs / 'ca.crt').relative_to(root)} && "
        f"export FLEETQOX_RMW_QUIC_QLOG_DIR=/work/{qlogs.relative_to(root)} && "
        f"{install}/rmw_fleetqox_cpp/lib/rmw_fleetqox_cpp/"
        f"fleetrmw_quic_durable_admission_failover_probe {mode}"
    )
    return run([
        "docker", "run", "--rm", "--name", name,
        "--network", network, "--cap-add", "NET_ADMIN",
        "--entrypoint", "bash", "-v", f"{root}:/work", "-w", "/work",
        image, "-lc", command,
    ])


def blocked_standby_control(
    *, root: Path, image: str, network: str, command: str, name: str
) -> dict[str, Any]:
    result = run([
        "docker", "run", "--rm", "--name", name,
        "--network", network, "--cap-add", "NET_ADMIN",
        "--entrypoint", "bash", "-v", f"{root}:/work", "-w", "/work",
        image, "-lc", command,
    ])
    combined = result.stdout + result.stderr
    ok = result.returncode != 0 and "writer lease is held by 'gateway-a'" in combined
    return {
        "status": "ok" if ok else "failed",
        "returncode": result.returncode,
        "concurrent_standby_fenced": ok,
        "output": "" if ok else combined[-4000:],
    }


def phase_result(
    *, ready: bool, client: subprocess.CompletedProcess[str],
    exit_code: int, logs: str, service: dict[str, Any], mode: str,
    holder: str, token: int, qlog_dirs: tuple[Path, Path],
) -> dict[str, Any]:
    rows = json_rows(client.stdout)
    probe = rows[-1] if rows else {}
    qlogs = [
        path for directory in qlog_dirs for path in directory.glob("*")
        if path.is_file()
    ]
    netem_ok = "qdisc netem" in logs and "qdisc netem" in client.stdout
    qlog_ok = qlogs and all(path.stat().st_size > 0 for path in qlogs)
    ok = (
        ready and client.returncode == 0 and exit_code == 0
        and probe_ok(probe, mode)
        and service_with_lease_ok(service, mode=mode, holder=holder, token=token)
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
        "service_exit_code": exit_code,
        "client_stdout": "" if ok else client.stdout,
        "client_stderr": "" if ok else client.stderr,
        "service_logs": "" if ok else logs,
    }


def run_case(
    *, root: Path, image: str, network: str, install: str,
    temp_root: Path, index: int,
) -> dict[str, Any]:
    suffix = f"{os.getpid()}-{index}"
    case_root = temp_root / f"run-{index}"
    certs = temp_root / "certs"
    active_service_qlogs = case_root / "active-service-qlogs"
    active_client_qlogs = case_root / "active-client-qlogs"
    takeover_service_qlogs = case_root / "takeover-service-qlogs"
    takeover_client_qlogs = case_root / "takeover-client-qlogs"
    blocked_qlogs = case_root / "blocked-service-qlogs"
    for path in (
        active_service_qlogs, active_client_qlogs, takeover_service_qlogs,
        takeover_client_qlogs, blocked_qlogs,
    ):
        path.mkdir(parents=True, exist_ok=True)

    active_name = f"fleetrmw-fenced-active-{suffix}"
    active_ready = start_service(
        root=root, image=image, network=network, name=active_name,
        alias="fleetqox-admission-gateway",
        command=service_command(
            root=root, temp_root=temp_root, index=index,
            holder="gateway-a", qlogs=active_service_qlogs,
        ),
    )
    active_client = subprocess.CompletedProcess([], 1, "", "service_not_ready")
    blocked = {"status": "skipped"}
    if active_ready:
        active_client = run_client(
            root=root, image=image, network=network, install=install,
            name=f"fleetrmw-fenced-seed-client-{suffix}", certs=certs,
            qlogs=active_client_qlogs, mode="seed",
        )
        time.sleep(1.2)
        blocked = blocked_standby_control(
            root=root, image=image, network=network,
            name=f"fleetrmw-fenced-blocked-{suffix}",
            command=service_command(
                root=root, temp_root=temp_root, index=index,
                holder="gateway-b", qlogs=blocked_qlogs,
            ),
        )
    active_exit, active_logs, active_service = stop_service(active_name)
    active = phase_result(
        ready=active_ready, client=active_client, exit_code=active_exit,
        logs=active_logs, service=active_service, mode="seed",
        holder="gateway-a", token=1,
        qlog_dirs=(active_service_qlogs, active_client_qlogs),
    )

    takeover_name = f"fleetrmw-fenced-takeover-{suffix}"
    takeover_ready = False
    takeover_client = subprocess.CompletedProcess([], 1, "", "prerequisite_failed")
    takeover_exit = -1
    takeover_logs = ""
    takeover_service: dict[str, Any] = {}
    if active["status"] == blocked["status"] == "ok":
        takeover_ready = start_service(
            root=root, image=image, network=network, name=takeover_name,
            alias="fleetqox-admission-gateway",
            command=service_command(
                root=root, temp_root=temp_root, index=index,
                holder="gateway-c", qlogs=takeover_service_qlogs,
            ),
        )
        if takeover_ready:
            takeover_client = run_client(
                root=root, image=image, network=network, install=install,
                name=f"fleetrmw-fenced-resume-client-{suffix}", certs=certs,
                qlogs=takeover_client_qlogs, mode="resume",
            )
            time.sleep(1.2)
        takeover_exit, takeover_logs, takeover_service = stop_service(takeover_name)
    takeover = phase_result(
        ready=takeover_ready, client=takeover_client, exit_code=takeover_exit,
        logs=takeover_logs, service=takeover_service, mode="resume",
        holder="gateway-c", token=2,
        qlog_dirs=(takeover_service_qlogs, takeover_client_qlogs),
    )
    ok = active["status"] == blocked["status"] == takeover["status"] == "ok"
    return {
        "index": index,
        "status": "ok" if ok else "failed",
        "active": active,
        "blocked_standby": blocked,
        "takeover": takeover,
    }


def run_probe(
    *, root: Path, image: str, iterations: int, keep_temp: bool
) -> dict[str, Any]:
    run_count = max(1, iterations)
    temp_root = root / f".tmp_fleetrmw_quic_writer_fencing_{os.getpid()}"
    certs = temp_root / "certs"
    certs.mkdir(parents=True, exist_ok=True)
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
    build_root = "/work/.tmp_fleetrmw_quic_writer_fencing_build"
    install = "/work/.tmp_fleetrmw_quic_writer_fencing_install"
    log_root = "/work/.tmp_fleetrmw_quic_writer_fencing_log"
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
    network = f"fleetrmw-writer-fencing-net-{os.getpid()}"
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
        "real_quic_v1_h3": True,
        "sqlite_single_writer_lease_claim": status == "ok",
        "concurrent_standby_startup_fenced_claim": status == "ok",
        "monotonic_fence_token_takeover_claim": status == "ok",
        "lease_renewal_claim": status == "ok",
        "post_takeover_admission_recovery_claim": status == "ok",
        "manual_active_passive_takeover_claim": status == "ok",
        "automatic_leader_election_claim": False,
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
        default="results_rmw_socket/docker_quic_writer_fencing_probe_summary.json",
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
        print("fleetrmw-quic-writer-fencing-probe")
        print(f"  status: {summary['status']}")
        print(f"  successful_runs: {summary['successful_runs']}/{summary['run_count']}")
    return 0 if summary["status"] == "ok" else 1


if __name__ == "__main__":
    raise SystemExit(main())

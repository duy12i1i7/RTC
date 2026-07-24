#!/usr/bin/env python3
"""Validate automatic shared-SQLite standby takeover under Docker/netem."""

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
        run,
        wait_service_ready,
    )
    from scripts.run_rmw_docker_quic_writer_fencing_probe import (
        phase_result,
        run_client,
        service_command,
        service_with_lease_ok,
        start_service,
        stop_service,
    )
except ModuleNotFoundError:
    from run_rmw_docker_quic_admission_probe import certificate_command
    from run_rmw_docker_quic_stateful_gateway_probe import (
        DEFAULT_IMAGE,
        run,
        wait_service_ready,
    )
    from run_rmw_docker_quic_writer_fencing_probe import (
        phase_result,
        run_client,
        service_command,
        service_with_lease_ok,
        start_service,
        stop_service,
    )


ROOT = Path(__file__).resolve().parents[1]
SCHEMA_VERSION = "fleetrmw.docker_quic_automatic_standby_takeover_probe.v1"
GATEWAY_ALIAS = "fleetqox-admission-gateway"


def wait_standby_waiting(container: str, timeout_s: float = 5.0) -> bool:
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        logs = run(["docker", "logs", container]).stdout
        if (
            '"status": "writer_lease_waiting"' in logs
            and '"instance_id": "gateway-b"' in logs
        ):
            state = run(
                ["docker", "inspect", "-f", "{{.State.Running}}", container]
            )
            return state.returncode == 0 and state.stdout.strip() == "true"
        state = run(
            ["docker", "inspect", "-f", "{{.State.Running}}", container]
        )
        if state.returncode != 0 or state.stdout.strip() != "true":
            return False
        time.sleep(0.1)
    return False


def start_waiting_standby(
    *, root: Path, image: str, network: str, name: str, command: str
) -> bool:
    started = run([
        "docker", "run", "-d", "--name", name,
        "--network", network, "--network-alias", GATEWAY_ALIAS,
        "--cap-add", "NET_ADMIN", "--entrypoint", "bash",
        "-v", f"{root}:/work", "-w", "/work", image, "-lc",
        command
        + " --writer-lease-wait-timeout-ms 10000 --writer-lease-retry-ms 100",
    ])
    return started.returncode == 0 and wait_standby_waiting(name)


def automatic_takeover_service_ok(row: dict[str, Any]) -> bool:
    return (
        service_with_lease_ok(
            row, mode="resume", holder="gateway-b", token=2
        )
        and row.get("automatic_standby_wait_configured") is True
        and row.get("writer_lease_acquisition_attempts", 0) >= 2
        and row.get("writer_lease_acquisition_wait_ms", 0) > 0
    )


def case_ok(row: dict[str, Any]) -> bool:
    return (
        row.get("active", {}).get("status") == "ok"
        and row.get("standby", {}).get("status") == "ok"
        and row.get("standby_observed_waiting_while_active_live") is True
        and row.get("automatic_takeover_service_validation") is True
        and automatic_takeover_service_ok(
            row.get("standby", {}).get("service", {})
        )
        and 0 <= row.get("takeover_latency_ms", -1) < 8000
    )


def run_case(
    *, root: Path, image: str, network: str, install: str,
    temp_root: Path, index: int,
) -> dict[str, Any]:
    suffix = f"{os.getpid()}-{index}"
    case_root = temp_root / f"run-{index}"
    certs = temp_root / "certs"
    active_service_qlogs = case_root / "active-service-qlogs"
    active_client_qlogs = case_root / "active-client-qlogs"
    standby_service_qlogs = case_root / "standby-service-qlogs"
    standby_client_qlogs = case_root / "standby-client-qlogs"
    for path in (
        active_service_qlogs,
        active_client_qlogs,
        standby_service_qlogs,
        standby_client_qlogs,
    ):
        path.mkdir(parents=True, exist_ok=True)

    active_name = f"fleetrmw-auto-active-{suffix}"
    standby_name = f"fleetrmw-auto-standby-{suffix}"
    active_ready = start_service(
        root=root,
        image=image,
        network=network,
        name=active_name,
        alias=GATEWAY_ALIAS,
        command=service_command(
            root=root,
            temp_root=temp_root,
            index=index,
            holder="gateway-a",
            qlogs=active_service_qlogs,
        ),
    )
    seed_client = subprocess.CompletedProcess([], 1, "", "service_not_ready")
    standby_waiting = False
    active_exit = -1
    active_logs = ""
    active_service: dict[str, Any] = {}
    takeover_latency_ms = -1
    standby_ready = False
    resume_client = subprocess.CompletedProcess([], 1, "", "standby_not_ready")
    standby_exit = -1
    standby_logs = ""
    standby_service: dict[str, Any] = {}
    try:
        if active_ready:
            seed_client = run_client(
                root=root,
                image=image,
                network=network,
                install=install,
                name=f"fleetrmw-auto-seed-client-{suffix}",
                certs=certs,
                qlogs=active_client_qlogs,
                mode="seed",
            )
        if active_ready and seed_client.returncode == 0:
            standby_waiting = start_waiting_standby(
                root=root,
                image=image,
                network=network,
                name=standby_name,
                command=service_command(
                    root=root,
                    temp_root=temp_root,
                    index=index,
                    holder="gateway-b",
                    qlogs=standby_service_qlogs,
                ),
            )
        if standby_waiting:
            time.sleep(1.2)
        takeover_started = time.monotonic()
        active_exit, active_logs, active_service = stop_service(active_name)
        if standby_waiting:
            standby_ready = wait_service_ready(standby_name, timeout_s=8.0)
            takeover_latency_ms = round(
                (time.monotonic() - takeover_started) * 1000.0
            )
        if standby_ready:
            resume_client = run_client(
                root=root,
                image=image,
                network=network,
                install=install,
                name=f"fleetrmw-auto-resume-client-{suffix}",
                certs=certs,
                qlogs=standby_client_qlogs,
                mode="resume",
            )
            time.sleep(1.2)
        standby_exit, standby_logs, standby_service = stop_service(standby_name)
    finally:
        run(["docker", "rm", "-f", active_name])
        run(["docker", "rm", "-f", standby_name])

    active = phase_result(
        ready=active_ready,
        client=seed_client,
        exit_code=active_exit,
        logs=active_logs,
        service=active_service,
        mode="seed",
        holder="gateway-a",
        token=1,
        qlog_dirs=(active_service_qlogs, active_client_qlogs),
    )
    standby = phase_result(
        ready=standby_ready,
        client=resume_client,
        exit_code=standby_exit,
        logs=standby_logs,
        service=standby_service,
        mode="resume",
        holder="gateway-b",
        token=2,
        qlog_dirs=(standby_service_qlogs, standby_client_qlogs),
    )
    automatic_ok = automatic_takeover_service_ok(standby_service)
    result = {
        "index": index,
        "standby_observed_waiting_while_active_live": standby_waiting,
        "takeover_latency_ms": takeover_latency_ms,
        "automatic_takeover_service_validation": automatic_ok,
        "active": active,
        "standby": standby,
    }
    result["status"] = "ok" if case_ok(result) else "failed"
    return result


def run_probe(
    *, root: Path, image: str, iterations: int, keep_temp: bool
) -> dict[str, Any]:
    run_count = max(1, iterations)
    temp_root = root / f".tmp_fleetrmw_quic_automatic_takeover_{os.getpid()}"
    certs = temp_root / "certs"
    certs.mkdir(parents=True, exist_ok=True)
    policy = {
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
                "path_id": "private_5g",
                "latency_ms": 20.0,
                "loss": 0.01,
                "failure_domain": "private_5g",
            }],
        },
    }
    (temp_root / "admission-policy.json").write_text(
        json.dumps(policy, sort_keys=True) + "\n", encoding="utf-8"
    )
    build_root = "/work/.tmp_fleetrmw_quic_automatic_takeover_build"
    install = "/work/.tmp_fleetrmw_quic_automatic_takeover_install"
    log_root = "/work/.tmp_fleetrmw_quic_automatic_takeover_log"
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
    network = f"fleetrmw-auto-takeover-net-{os.getpid()}"
    network_result = run(["docker", "network", "create", network])
    rows: list[dict[str, Any]] = []
    try:
        if cert_result.returncode == build.returncode == network_result.returncode == 0:
            for index in range(1, run_count + 1):
                rows.append(run_case(
                    root=root,
                    image=image,
                    network=network,
                    install=install,
                    temp_root=temp_root,
                    index=index,
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
        row["takeover_latency_ms"]
        for row in rows
        if row.get("takeover_latency_ms", -1) >= 0
    ]
    return {
        "schema_version": SCHEMA_VERSION,
        "status": status,
        "run_count": run_count,
        "successful_runs": successful,
        "failed_run_count": run_count - successful,
        "container_count_per_run": 4,
        "real_quic_v1_h3": True,
        "automatic_shared_store_standby_takeover_claim": status == "ok",
        "standby_waits_while_active_lease_live_claim": status == "ok",
        "monotonic_fence_token_takeover_claim": status == "ok",
        "post_takeover_admission_recovery_claim": status == "ok",
        "max_takeover_latency_ms": max(latencies) if latencies else None,
        "consensus_leader_election_claim": False,
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
        default=(
            "results_rmw_socket/"
            "docker_quic_automatic_standby_takeover_probe_summary.json"
        ),
    )
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    summary = run_probe(
        root=ROOT,
        image=args.image,
        iterations=args.iterations,
        keep_temp=args.keep_temp,
    )
    output = ROOT / args.summary_json
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(summary, sort_keys=True) + "\n", encoding="utf-8")
    if args.json:
        print(json.dumps(summary, sort_keys=True))
    else:
        print("fleetrmw-quic-automatic-standby-takeover-probe")
        print(f"  status: {summary['status']}")
        print(f"  successful_runs: {summary['successful_runs']}/{summary['run_count']}")
    return 0 if summary["status"] == "ok" else 1


if __name__ == "__main__":
    raise SystemExit(main())

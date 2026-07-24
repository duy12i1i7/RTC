#!/usr/bin/env python3
"""Prove per-identity active-worker isolation in the public ngtcp2 edge."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.fleetqox_public_quic_backend_delay_proxy import (
    SCHEMA_VERSION as PROXY_SCHEMA_VERSION,
)
from scripts.run_rmw_docker_ngtcp2_public_async_backend_probe import (
    DEFAULT_BASE_IMAGE,
    DEFAULT_SERVER_IMAGE,
    docker_logs,
    finish_client,
    load_json,
    response_has_status,
    run,
    stop_server,
    wait_for_log,
)
from scripts.run_rmw_docker_ngtcp2_public_identity_fairness_probe import (
    PUBLISHER_A,
    PUBLISHER_B,
    fairness_certificate_command,
    run_exec_client,
    start_client_container,
    start_exec_client,
    start_server,
    wait_client_ready,
)
from scripts.run_rmw_docker_ngtcp2_public_stateful_gateway_probe import (
    BACKEND_SCHEMA_VERSION,
)


SCHEMA_VERSION = "fleetrmw.docker_ngtcp2_public_active_worker_isolation.v1"
WORKERS = 2
QUEUE_CAPACITY = 8
PER_IDENTITY_QUEUE_CAPACITY = 4


def run_phase(
    *,
    root: Path,
    image: str,
    network: str,
    certs: Path,
    run_root: Path,
    suffix: str,
    active_limit: int,
) -> dict[str, Any]:
    phase_name = "isolated" if active_limit == 1 else "unisolated"
    server_name = f"fq-public-active-{phase_name}-server-{suffix}"
    client_name = f"fq-public-active-{phase_name}-client-{suffix}"
    qlogs = run_root / "client-qlogs"
    qlogs.mkdir(parents=True, exist_ok=True)
    start, backend_path, proxy_path = start_server(
        root=root,
        image=image,
        network=network,
        name=server_name,
        certs=certs,
        run_root=run_root,
        workers=WORKERS,
        queue_capacity=QUEUE_CAPACITY,
        per_identity_queue_capacity=PER_IDENTITY_QUEUE_CAPACITY,
        per_identity_active_limit=active_limit,
    )
    ready_marker = (
        f"FLEETQOX_STATE_BACKEND_ASYNC_READY workers={WORKERS} "
        f"queue_capacity={QUEUE_CAPACITY} "
        f"per_identity_queue_capacity={PER_IDENTITY_QUEUE_CAPACITY} "
        f"per_identity_active_limit={active_limit}"
    )
    server_ready = (
        start.returncode == 0
        and wait_for_log(server_name, ready_marker)
        and wait_for_log(server_name, PROXY_SCHEMA_VERSION)
    )
    client_start = start_client_container(
        root=root,
        image=image,
        network=network,
        name=client_name,
        certs=certs,
    )
    client_ready = client_start.returncode == 0 and wait_client_ready(client_name)

    first: subprocess.Popen[str] | None = None
    second: subprocess.Popen[str] | None = None
    first_result = subprocess.CompletedProcess([], 1, "", "not_started")
    second_result = subprocess.CompletedProcess([], 1, "", "not_started")
    victim_b = subprocess.CompletedProcess([], 1, "", "not_started")
    victim_elapsed_ms = 0.0
    victim_completed_while_both_a_clients_open = False
    second_a_reached_proxy_before_victim = False
    two_a_requests_submitted = False
    server_exit = -1
    logs = ""
    try:
        if server_ready and client_ready:
            first = start_exec_client(
                root=root,
                container=client_name,
                certs=certs,
                certificate_name="publisher-a",
                consumer_id="queue-a1",
                qlog=qlogs / "a1.qlog",
            )
            first_delayed = wait_for_log(
                server_name,
                (
                    "FLEETQOX_BACKEND_DELAY_PROXY_DELAYING "
                    "consumer_id=queue-a1"
                ),
                timeout_s=8.0,
            )
            second = start_exec_client(
                root=root,
                container=client_name,
                certs=certs,
                certificate_name="publisher-a",
                consumer_id="queue-a2",
                qlog=qlogs / "a2.qlog",
            )
            two_a_requests_submitted = first_delayed and wait_for_log(
                server_name,
                "FLEETQOX_STATE_BACKEND_ASYNC_QUEUED",
                count=2,
                timeout_s=8.0,
            )
            if active_limit > 1:
                second_a_reached_proxy_before_victim = wait_for_log(
                    server_name,
                    (
                        "FLEETQOX_BACKEND_DELAY_PROXY_DELAYING "
                        "consumer_id=queue-a2"
                    ),
                    timeout_s=8.0,
                )
            victim_start = time.monotonic()
            victim_b = run_exec_client(
                root=root,
                container=client_name,
                certs=certs,
                certificate_name="publisher-b",
                consumer_id="victim-b",
                qlog=qlogs / "victim-b.qlog",
            )
            victim_elapsed_ms = (time.monotonic() - victim_start) * 1000.0
            victim_completed_while_both_a_clients_open = (
                response_has_status(victim_b, 204)
                and first.poll() is None
                and second.poll() is None
            )
            first_result = finish_client(first)
            second_result = finish_client(second)
        if server_ready:
            server_exit, logs = stop_server(server_name)
    finally:
        run(["docker", "rm", "-f", client_name], timeout=20.0)
        for process in (first, second):
            if process is not None and process.poll() is None:
                process.kill()
        run(["docker", "rm", "-f", server_name], timeout=20.0)

    backend = load_json(backend_path)
    proxy = load_json(proxy_path)
    state = backend.get("metrics", {}).get("state", {})
    qlog_files = list(qlogs.glob("*.qlog"))
    forwarded = proxy.get("forwarded_consumer_ids", [])
    a_active_one_count = logs.count(
        f"FLEETQOX_STATE_BACKEND_ACTIVE identity={PUBLISHER_A} "
        "identity_active=1"
    )
    a_active_two_count = logs.count(
        f"FLEETQOX_STATE_BACKEND_ACTIVE identity={PUBLISHER_A} "
        "identity_active=2"
    )
    b_active_one_count = logs.count(
        f"FLEETQOX_STATE_BACKEND_ACTIVE identity={PUBLISHER_B} "
        "identity_active=1"
    )
    common_ok = (
        server_ready
        and client_ready
        and two_a_requests_submitted
        and response_has_status(first_result, 204)
        and response_has_status(second_result, 204)
        and response_has_status(victim_b, 204)
        and server_exit == 0
        and backend.get("schema_version") == BACKEND_SCHEMA_VERSION
        and backend.get("clean_teardown") is True
        and state.get("requests_total") == 3
        and state.get("get_requests") == 3
        and state.get("empty_takes") == 3
        and proxy.get("schema_version") == PROXY_SCHEMA_VERSION
        and proxy.get("clean_teardown") is True
        and proxy.get("requests_total") == 3
        and proxy.get("delayed_requests") == 2
        and proxy.get("forwarded_requests") == 3
        and proxy.get("failures") == 0
        and logs.count("FLEETQOX_STATE_BACKEND_ASYNC_QUEUED") == 3
        and logs.count("FLEETQOX_STATE_BACKEND_ACTIVE") == 3
        and logs.count("FLEETQOX_STATE_BACKEND_RELEASED") == 3
        and logs.count("FLEETQOX_STATE_BACKEND_RESPONSE") == 3
        and logs.count("FLEETQOX_STATE_BACKEND_QUEUE_FULL") == 0
        and logs.count("FLEETQOX_STATE_BACKEND_IDENTITY_QUEUE_FULL") == 0
        and b_active_one_count == 1
        and len(qlog_files) == 3
        and all(path.stat().st_size > 0 for path in qlog_files)
    )
    if active_limit == 1:
        behavior_ok = (
            victim_completed_while_both_a_clients_open
            and not second_a_reached_proxy_before_victim
            and a_active_one_count == 2
            and a_active_two_count == 0
            and len(forwarded) == 3
            and forwarded[0] == "victim-b"
            and set(forwarded[1:]) == {"queue-a1", "queue-a2"}
            and proxy.get("max_active_requests", 0) >= 2
        )
    else:
        behavior_ok = (
            second_a_reached_proxy_before_victim
            and a_active_one_count == 1
            and a_active_two_count == 1
            and len(forwarded) == 3
            and forwarded[0] in {"queue-a1", "queue-a2"}
            and set(forwarded) == {"queue-a1", "queue-a2", "victim-b"}
            and proxy.get("max_active_requests", 0) >= 2
        )
    ok = common_ok and behavior_ok
    return {
        "status": "ok" if ok else "failed",
        "active_limit": active_limit,
        "server_ready": server_ready,
        "client_ready": client_ready,
        "server_exit_code": server_exit,
        "two_a_requests_submitted": two_a_requests_submitted,
        "second_a_reached_proxy_before_victim": (
            second_a_reached_proxy_before_victim
        ),
        "victim_b_http_204": response_has_status(victim_b, 204),
        "victim_b_elapsed_ms": round(victim_elapsed_ms, 3),
        "victim_b_completed_while_both_a_clients_open": (
            victim_completed_while_both_a_clients_open
        ),
        "publisher_a_active_one_count": a_active_one_count,
        "publisher_a_active_two_count": a_active_two_count,
        "publisher_b_active_one_count": b_active_one_count,
        "forwarded_consumer_ids": forwarded,
        "backend": backend,
        "proxy": proxy,
        "client_qlog_file_count": len(qlog_files),
        "first_a_stderr": "" if ok else first_result.stderr,
        "second_a_stderr": "" if ok else second_result.stderr,
        "victim_b_stderr": "" if ok else victim_b.stderr,
        "server_logs": "" if ok else logs,
    }


def run_iteration(
    *,
    root: Path,
    image: str,
    network: str,
    certs: Path,
    temp_root: Path,
    index: int,
) -> dict[str, Any]:
    suffix = f"{os.getpid()}-{index}"
    isolated = run_phase(
        root=root,
        image=image,
        network=network,
        certs=certs,
        run_root=temp_root / f"run-{index}" / "isolated",
        suffix=suffix,
        active_limit=1,
    )
    unisolated = run_phase(
        root=root,
        image=image,
        network=network,
        certs=certs,
        run_root=temp_root / f"run-{index}" / "unisolated",
        suffix=suffix,
        active_limit=2,
    )
    contrast = (
        isolated.get("status") == "ok"
        and unisolated.get("status") == "ok"
        and isolated.get("victim_b_elapsed_ms", float("inf"))
        < unisolated.get("victim_b_elapsed_ms", 0.0)
    )
    return {
        "index": index,
        "status": "ok" if contrast else "failed",
        "isolated_phase": isolated,
        "unisolated_control_phase": unisolated,
        "matched_active_limit_contrast": contrast,
        "netem_server": "delay 11ms 2ms",
        "netem_client": "delay 9ms 2ms",
    }


def run_probe(
    *,
    root: Path,
    base_image: str,
    server_image: str,
    iterations: int,
    skip_server_build: bool,
    keep_temp: bool,
) -> dict[str, Any]:
    build = subprocess.CompletedProcess([], 0, "", "")
    if not skip_server_build:
        build = run(
            [
                "docker",
                "build",
                "--build-arg",
                f"BASE_IMAGE={base_image}",
                "-f",
                "external/ngtcp2-public-mtls/Dockerfile",
                "-t",
                server_image,
                ".",
            ],
            timeout=600.0,
        )
    temp_root = root / f".tmp_fleetrmw_public_active_{os.getpid()}"
    certs = temp_root / "certs"
    certs.mkdir(parents=True, exist_ok=True)
    certificate = run(
        [
            "docker",
            "run",
            "--rm",
            "--entrypoint",
            "bash",
            "-v",
            f"{root}:/work",
            "-w",
            "/work",
            base_image,
            "-lc",
            fairness_certificate_command(certs, root),
        ],
        timeout=180.0,
    )
    network = f"fq-public-active-net-{os.getpid()}"
    network_result = run(["docker", "network", "create", network], timeout=20.0)
    rows: list[dict[str, Any]] = []
    try:
        if all(
            result.returncode == 0
            for result in (build, certificate, network_result)
        ):
            for index in range(max(1, iterations)):
                rows.append(
                    run_iteration(
                        root=root,
                        image=server_image,
                        network=network,
                        certs=certs,
                        temp_root=temp_root,
                        index=index,
                    )
                )
    finally:
        run(["docker", "network", "rm", network], timeout=20.0)
        if not keep_temp:
            shutil.rmtree(temp_root, ignore_errors=True)
    run_count = max(1, iterations)
    ok_count = sum(row.get("status") == "ok" for row in rows)
    ok = (
        all(
            result.returncode == 0
            for result in (build, certificate, network_result)
        )
        and len(rows) == run_count
        and ok_count == run_count
    )
    return {
        "schema_version": SCHEMA_VERSION,
        "status": "ok" if ok else "failed",
        "run_count": run_count,
        "ok_run_count": ok_count,
        "per_identity_active_worker_limit_claim": ok,
        "active_worker_cross_publisher_isolation_claim": ok,
        "matched_active_limit_contrast_claim": ok,
        "certificate_derived_identity_scheduling_claim": ok,
        "real_state_engine_behind_test_delay_proxy_claim": ok,
        "docker_netem_both_ends_claim": ok,
        "aioquic_server_runtime_used": False,
        "production_quic_backend_claim": False,
        "server_build_returncode": build.returncode,
        "certificate_returncode": certificate.returncode,
        "network_returncode": network_result.returncode,
        "runs": rows,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-image", default=DEFAULT_BASE_IMAGE)
    parser.add_argument("--server-image", default=DEFAULT_SERVER_IMAGE)
    parser.add_argument("--iterations", type=int, default=1)
    parser.add_argument("--skip-server-build", action="store_true")
    parser.add_argument("--keep-temp", action="store_true")
    parser.add_argument(
        "--summary-json",
        default=(
            "results_rmw_socket/"
            "docker_ngtcp2_public_active_worker_isolation_summary.json"
        ),
    )
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    summary = run_probe(
        root=ROOT,
        base_image=args.base_image,
        server_image=args.server_image,
        iterations=args.iterations,
        skip_server_build=args.skip_server_build,
        keep_temp=args.keep_temp,
    )
    output = ROOT / args.summary_json
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(summary, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    if args.json:
        print(json.dumps(summary, sort_keys=True))
    else:
        print(f"status={summary['status']}")
    return 0 if summary["status"] == "ok" else 1


if __name__ == "__main__":
    raise SystemExit(main())

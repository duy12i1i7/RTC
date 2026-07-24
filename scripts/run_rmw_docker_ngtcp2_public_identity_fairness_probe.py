#!/usr/bin/env python3
"""Prove certificate-derived identity and fair public-edge backend queuing."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import shlex
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
from scripts.run_rmw_docker_ngtcp2_public_stateful_gateway_probe import (
    BACKEND_SCHEMA_VERSION,
    stateful_certificate_command,
)


SCHEMA_VERSION = "fleetrmw.docker_ngtcp2_public_identity_fairness.v1"
IDENTITY_PREFIX = "spiffe://fleetqox/publishers/"
PUBLISHER_A = "fairness-publisher-a"
PUBLISHER_B = "fairness-publisher-b"
DELAY_MS = 1500


def fairness_certificate_command(certs: Path, root: Path) -> str:
    prefix = f"/work/{certs.relative_to(root)}"

    def issue(name: str, identity: str) -> str:
        uri = f"{IDENTITY_PREFIX}{identity}"
        return (
            "openssl req -new -newkey rsa:2048 -nodes "
            f"-keyout {prefix}/{name}.key -out {prefix}/{name}.csr "
            f"-subj /CN={identity} -addext extendedKeyUsage=clientAuth "
            f"-addext subjectAltName=URI:{uri} >/dev/null 2>&1 && "
            f"openssl x509 -req -in {prefix}/{name}.csr "
            f"-CA {prefix}/client-ca.crt -CAkey {prefix}/client-ca.key "
            f"-CAcreateserial -out {prefix}/{name}.crt "
            "-days 1 -copy_extensions copy >/dev/null 2>&1"
        )

    return (
        stateful_certificate_command(certs, root)
        + " && "
        + issue("publisher-a", PUBLISHER_A)
        + " && "
        + issue("publisher-b", PUBLISHER_B)
        + " && "
        + (
            "openssl req -new -newkey rsa:2048 -nodes "
            f"-keyout {prefix}/outsider.key -out {prefix}/outsider.csr "
            "-subj /CN=fairness-outsider "
            "-addext extendedKeyUsage=clientAuth "
            "-addext subjectAltName=URI:spiffe://other/publishers/fairness-outsider "
            ">/dev/null 2>&1 && "
            f"openssl x509 -req -in {prefix}/outsider.csr "
            f"-CA {prefix}/client-ca.crt -CAkey {prefix}/client-ca.key "
            f"-CAcreateserial -out {prefix}/outsider.crt "
            "-days 1 -copy_extensions copy >/dev/null 2>&1"
        )
    )


def server_command(
    *,
    root: Path,
    certs: Path,
    run_root: Path,
) -> tuple[str, Path, Path]:
    cert_root = f"/work/{certs.relative_to(root)}"
    htdocs = run_root / "htdocs"
    server_qlogs = run_root / "server-qlogs"
    backend_summary = run_root / "backend-summary.json"
    proxy_summary = run_root / "proxy-summary.json"
    htdocs.mkdir(parents=True, exist_ok=True)
    server_qlogs.mkdir(parents=True, exist_ok=True)
    (htdocs / "index.html").write_text(
        "identity fairness probe\n",
        encoding="utf-8",
    )
    htdocs_root = f"/work/{htdocs.relative_to(root)}"
    server_qlog_root = f"/work/{server_qlogs.relative_to(root)}"
    backend_summary_path = f"/work/{backend_summary.relative_to(root)}"
    proxy_summary_path = f"/work/{proxy_summary.relative_to(root)}"
    upstream_socket = "/tmp/fleetqox-fairness-upstream.sock"
    proxy_socket = "/tmp/fleetqox-fairness-proxy.sock"
    command = (
        "set -uo pipefail; "
        f"rm -f {upstream_socket} {proxy_socket} "
        f"{shlex.quote(backend_summary_path)} {shlex.quote(proxy_summary_path)}; "
        "python3 -m fleetqox.public_quic_gateway_backend "
        f"--socket {upstream_socket} --max-frames-per-topic 8 "
        "--max-frame-bytes 65536 "
        f"--summary-json {shlex.quote(backend_summary_path)} & "
        "backend_pid=$!; "
        "for attempt in $(seq 1 100); do "
        f"test -S {upstream_socket} && break; sleep 0.05; done; "
        f"test -S {upstream_socket}; "
        "python3 scripts/fleetqox_public_quic_backend_delay_proxy.py "
        f"--listen-socket {proxy_socket} --upstream-socket {upstream_socket} "
        "--delay-prefix queue-a "
        f"--delay-ms {DELAY_MS} --workers 8 --max-in-flight 16 "
        f"--summary-json {shlex.quote(proxy_summary_path)} & "
        "proxy_pid=$!; "
        "for attempt in $(seq 1 100); do "
        f"test -S {proxy_socket} && break; sleep 0.05; done; "
        f"test -S {proxy_socket}; "
        "tc qdisc replace dev eth0 root netem delay 11ms 2ms; "
        "fleetqox-public-mtls-server "
        f"--htdocs={shlex.quote(htdocs_root)} "
        f"--qlog-dir={shlex.quote(server_qlog_root)} "
        "--verify-client --no-quic-dump --no-http-dump "
        f"'*' 4433 {cert_root}/server.key {cert_root}/server.crt & "
        "server_pid=$!; echo \"$server_pid\" >/tmp/fleetqox-public-server.pid; "
        "wait \"$server_pid\"; server_rc=$?; "
        "kill -TERM \"$proxy_pid\" 2>/dev/null || true; "
        "wait \"$proxy_pid\" || true; "
        "kill -TERM \"$backend_pid\" 2>/dev/null || true; "
        "wait \"$backend_pid\" || true; exit \"$server_rc\""
    )
    return command, backend_summary, proxy_summary


def start_server(
    *,
    root: Path,
    image: str,
    network: str,
    name: str,
    certs: Path,
    run_root: Path,
    workers: int = 1,
    queue_capacity: int = 4,
    per_identity_queue_capacity: int = 2,
    per_identity_active_limit: int | None = None,
) -> tuple[subprocess.CompletedProcess[str], Path, Path]:
    command, backend_summary, proxy_summary = server_command(
        root=root,
        certs=certs,
        run_root=run_root,
    )
    cert_root = f"/work/{certs.relative_to(root)}"
    active_limit_args = (
        []
        if per_identity_active_limit is None
        else [
            "-e",
            (
                "FLEETQOX_STATE_BACKEND_PER_IDENTITY_ACTIVE_LIMIT="
                f"{per_identity_active_limit}"
            ),
        ]
    )
    result = run(
        [
            "docker",
            "run",
            "-d",
            "--name",
            name,
            "--network",
            network,
            "--network-alias",
            "fleetqox-mtls-gateway",
            "--cap-add",
            "NET_ADMIN",
            "--entrypoint",
            "bash",
            "-e",
            f"FLEETQOX_GNUTLS_CLIENT_CA={cert_root}/client-ca.crt",
            "-e",
            f"FLEETQOX_GNUTLS_CLIENT_CRL={cert_root}/client.crl.pem",
            "-e",
            f"FLEETQOX_GNUTLS_CLIENT_URI_PREFIX={IDENTITY_PREFIX}",
            "-e",
            "FLEETQOX_STATE_BACKEND_SOCKET=/tmp/fleetqox-fairness-proxy.sock",
            "-e",
            f"FLEETQOX_STATE_BACKEND_WORKERS={workers}",
            "-e",
            f"FLEETQOX_STATE_BACKEND_QUEUE_CAPACITY={queue_capacity}",
            "-e",
            (
                "FLEETQOX_STATE_BACKEND_PER_IDENTITY_QUEUE_CAPACITY="
                f"{per_identity_queue_capacity}"
            ),
            *active_limit_args,
            "-v",
            f"{root}:/work",
            "-w",
            "/work",
            image,
            "-lc",
            command,
        ],
        timeout=30.0,
    )
    return result, backend_summary, proxy_summary


def start_client_container(
    *,
    root: Path,
    image: str,
    network: str,
    name: str,
    certs: Path,
) -> subprocess.CompletedProcess[str]:
    cert_root = f"/work/{certs.relative_to(root)}"
    command = (
        f"cp {cert_root}/server-ca.crt "
        "/usr/local/share/ca-certificates/fleetqox-public-ca.crt && "
        "update-ca-certificates >/dev/null 2>&1 && "
        "tc qdisc replace dev eth0 root netem delay 9ms 2ms && "
        "touch /tmp/fleetqox-client-ready && exec sleep infinity"
    )
    return run(
        [
            "docker",
            "run",
            "-d",
            "--name",
            name,
            "--network",
            network,
            "--cap-add",
            "NET_ADMIN",
            "--entrypoint",
            "bash",
            "-v",
            f"{root}:/work",
            "-w",
            "/work",
            image,
            "-lc",
            command,
        ],
        timeout=30.0,
    )


def wait_client_ready(container: str, timeout_s: float = 10.0) -> bool:
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        ready = run(
            [
                "docker",
                "exec",
                container,
                "test",
                "-f",
                "/tmp/fleetqox-client-ready",
            ],
            timeout=10.0,
        )
        if ready.returncode == 0:
            return True
        time.sleep(0.05)
    return False


def client_exec_args(
    *,
    root: Path,
    container: str,
    certs: Path,
    certificate_name: str,
    consumer_id: str,
    qlog: Path,
) -> list[str]:
    cert_root = f"/work/{certs.relative_to(root)}"
    qlog_path = f"/work/{qlog.relative_to(root)}"
    uri = (
        "https://fleetqox-mtls-gateway:4433/fleetrmw/v1/frames?"
        "domain_id=42&topic=%2Ffleetqox%2Ffairness&consumer_id="
        f"{consumer_id}"
    )
    command = (
        "gtlsclient fleetqox-mtls-gateway 4433 "
        f"{shlex.quote(uri)} "
        f"--key={cert_root}/{certificate_name}.key "
        f"--cert={cert_root}/{certificate_name}.crt "
        "--disable-early-data --exit-on-all-streams-close "
        "--no-quic-dump --no-http-dump "
        f"--qlog-file={qlog_path}"
    )
    return ["docker", "exec", container, "bash", "-lc", command]


def start_exec_client(
    *,
    root: Path,
    container: str,
    certs: Path,
    certificate_name: str,
    consumer_id: str,
    qlog: Path,
) -> subprocess.Popen[str]:
    return subprocess.Popen(
        client_exec_args(
            root=root,
            container=container,
            certs=certs,
            certificate_name=certificate_name,
            consumer_id=consumer_id,
            qlog=qlog,
        ),
        cwd=ROOT,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )


def run_exec_client(
    *,
    root: Path,
    container: str,
    certs: Path,
    certificate_name: str,
    consumer_id: str,
    qlog: Path,
) -> subprocess.CompletedProcess[str]:
    return run(
        client_exec_args(
            root=root,
            container=container,
            certs=certs,
            certificate_name=certificate_name,
            consumer_id=consumer_id,
            qlog=qlog,
        ),
        timeout=15.0,
    )


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
    server_name = f"fq-public-fairness-server-{suffix}"
    client_name = f"fq-public-fairness-client-{suffix}"
    run_root = temp_root / f"run-{index}"
    qlogs = run_root / "client-qlogs"
    qlogs.mkdir(parents=True, exist_ok=True)
    start, backend_path, proxy_path = start_server(
        root=root,
        image=image,
        network=network,
        name=server_name,
        certs=certs,
        run_root=run_root,
    )
    server_ready = (
        start.returncode == 0
        and wait_for_log(
            server_name,
            (
                "FLEETQOX_STATE_BACKEND_ASYNC_READY workers=1 "
                "queue_capacity=4 per_identity_queue_capacity=2"
            ),
        )
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
    active: list[subprocess.Popen[str]] = []
    completed_a: list[subprocess.CompletedProcess[str]] = []
    rejected_a = subprocess.CompletedProcess([], 1, "", "not_started")
    victim_b = subprocess.CompletedProcess([], 1, "", "not_started")
    outsider = subprocess.CompletedProcess([], 1, "", "not_started")
    victim_overtook_queued_a = False
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
            active.append(first)
            first_delayed = wait_for_log(
                server_name,
                (
                    "FLEETQOX_BACKEND_DELAY_PROXY_DELAYING "
                    "consumer_id=queue-a1"
                ),
                timeout_s=8.0,
            )
            for sequence in (2, 3):
                active.append(
                    start_exec_client(
                        root=root,
                        container=client_name,
                        certs=certs,
                        certificate_name="publisher-a",
                        consumer_id=f"queue-a{sequence}",
                        qlog=qlogs / f"a{sequence}.qlog",
                    )
                )
            noisy_queue_full = first_delayed and wait_for_log(
                server_name,
                "identity=fairness-publisher-a identity_pending=2",
                timeout_s=8.0,
            )
            rejected_a = run_exec_client(
                root=root,
                container=client_name,
                certs=certs,
                certificate_name="publisher-a",
                consumer_id="queue-a4",
                qlog=qlogs / "a4-rejected.qlog",
            )
            victim_b = run_exec_client(
                root=root,
                container=client_name,
                certs=certs,
                certificate_name="publisher-b",
                consumer_id="victim-b",
                qlog=qlogs / "victim-b.qlog",
            )
            victim_overtook_queued_a = (
                noisy_queue_full
                and response_has_status(victim_b, 204)
                and any(process.poll() is None for process in active[1:])
            )
            completed_a = [finish_client(process) for process in active]
            outsider = run_exec_client(
                root=root,
                container=client_name,
                certs=certs,
                certificate_name="outsider",
                consumer_id="outsider",
                qlog=qlogs / "outsider-rejected.qlog",
            )
        if server_ready:
            server_exit, logs = stop_server(server_name)
    finally:
        run(["docker", "rm", "-f", client_name], timeout=20.0)
        for process in active:
            if process.poll() is None:
                process.kill()
        run(["docker", "rm", "-f", server_name], timeout=20.0)

    backend = load_json(backend_path)
    proxy = load_json(proxy_path)
    qlog_files = list(qlogs.glob("*.qlog"))
    state = backend.get("metrics", {}).get("state", {})
    all_a_ok = (
        len(completed_a) == 3
        and all(response_has_status(result, 204) for result in completed_a)
    )
    outsider_output = outsider.stdout + outsider.stderr
    outsider_fail_closed = "[:status:" not in outsider_output
    forwarded_consumer_ids = proxy.get("forwarded_consumer_ids", [])
    fair_forward_order = (
        len(forwarded_consumer_ids) == 4
        and forwarded_consumer_ids[0] == "queue-a1"
        and set(forwarded_consumer_ids[1:])
        == {"queue-a2", "queue-a3", "victim-b"}
        and forwarded_consumer_ids.index("victim-b")
        < max(
            forwarded_consumer_ids.index("queue-a2"),
            forwarded_consumer_ids.index("queue-a3"),
        )
    )
    ok = (
        server_ready
        and client_ready
        and all_a_ok
        and response_has_status(rejected_a, 429)
        and response_has_status(victim_b, 204)
        and outsider_fail_closed
        and victim_overtook_queued_a
        and server_exit == 0
        and backend.get("schema_version") == BACKEND_SCHEMA_VERSION
        and backend.get("clean_teardown") is True
        and state.get("requests_total") == 4
        and state.get("get_requests") == 4
        and state.get("empty_takes") == 4
        and proxy.get("schema_version") == PROXY_SCHEMA_VERSION
        and proxy.get("clean_teardown") is True
        and proxy.get("requests_total") == 4
        and proxy.get("delayed_requests") == 3
        and proxy.get("forwarded_requests") == 4
        and fair_forward_order
        and proxy.get("failures") == 0
        and logs.count(
            "FLEETQOX_PUBLIC_MTLS_IDENTITY identity=fairness-publisher-a"
        )
        == 4
        and logs.count(
            "FLEETQOX_PUBLIC_MTLS_IDENTITY identity=fairness-publisher-b"
        )
        == 1
        and logs.count(
            "reason=backend_client_identity_unavailable"
        )
        == 1
        and logs.count("FLEETQOX_STATE_BACKEND_ASYNC_QUEUED") == 4
        and logs.count("FLEETQOX_STATE_BACKEND_IDENTITY_QUEUE_FULL") == 1
        and logs.count("FLEETQOX_STATE_BACKEND_QUEUE_FULL") == 0
        and logs.count("FLEETQOX_STATE_BACKEND_RESPONSE") == 4
        and len(qlog_files) == 6
        and all(path.stat().st_size > 0 for path in qlog_files)
    )
    return {
        "index": index,
        "status": "ok" if ok else "failed",
        "server_ready": server_ready,
        "client_ready": client_ready,
        "server_exit_code": server_exit,
        "publisher_a_three_http_204": all_a_ok,
        "publisher_a_overload_http_429": response_has_status(rejected_a, 429),
        "publisher_b_http_204": response_has_status(victim_b, 204),
        "out_of_prefix_identity_fail_closed": outsider_fail_closed,
        "publisher_b_overtook_queued_publisher_a": victim_overtook_queued_a,
        "backend": backend,
        "proxy": proxy,
        "forwarded_consumer_ids": forwarded_consumer_ids,
        "fair_forward_order": fair_forward_order,
        "publisher_a_bound_identity_count": logs.count(
            "FLEETQOX_PUBLIC_MTLS_IDENTITY identity=fairness-publisher-a"
        ),
        "publisher_b_bound_identity_count": logs.count(
            "FLEETQOX_PUBLIC_MTLS_IDENTITY identity=fairness-publisher-b"
        ),
        "server_async_queued_count": logs.count(
            "FLEETQOX_STATE_BACKEND_ASYNC_QUEUED"
        ),
        "server_identity_queue_full_count": logs.count(
            "FLEETQOX_STATE_BACKEND_IDENTITY_QUEUE_FULL"
        ),
        "server_global_queue_full_count": logs.count(
            "FLEETQOX_STATE_BACKEND_QUEUE_FULL"
        ),
        "server_backend_response_count": logs.count(
            "FLEETQOX_STATE_BACKEND_RESPONSE"
        ),
        "client_qlog_file_count": len(qlog_files),
        "netem_server": "delay 11ms 2ms",
        "netem_client": "delay 9ms 2ms",
        "publisher_a_stderr": (
            ""
            if ok
            else [result.stderr for result in completed_a]
        ),
        "publisher_a_rejected_stderr": "" if ok else rejected_a.stderr,
        "publisher_b_stderr": "" if ok else victim_b.stderr,
        "outsider_stderr": "" if ok else outsider.stderr,
        "server_logs": "" if ok else logs,
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
    temp_root = root / f".tmp_fleetrmw_public_fairness_{os.getpid()}"
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
    network = f"fq-public-fairness-net-{os.getpid()}"
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
        "per_connection_certificate_uri_san_identity_claim": ok,
        "multi_publisher_identity_selection_claim": ok,
        "out_of_prefix_identity_fail_closed_claim": ok,
        "per_identity_backend_queue_limit_claim": ok,
        "round_robin_backend_queue_fairness_claim": ok,
        "cross_publisher_overload_isolation_claim": ok,
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
            "docker_ngtcp2_public_identity_fairness_summary.json"
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

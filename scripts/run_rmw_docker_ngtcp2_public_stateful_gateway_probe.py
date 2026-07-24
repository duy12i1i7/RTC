#!/usr/bin/env python3
"""Prove the stateful FleetQoX engine behind the public ngtcp2 mTLS edge."""

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

from scripts.run_rmw_docker_quic_mtls_probe import certificate_command
from fleetqox.quic_gateway_state import DATA_FRAME_MAGIC


SCHEMA_VERSION = "fleetrmw.docker_ngtcp2_public_stateful_gateway.v1"
PROBE_SCHEMA_VERSION = "fleetrmw.quic_stateful_gateway_probe.v1"
BACKEND_SCHEMA_VERSION = "fleetrmw.public_quic_gateway_backend.v2"
DEFAULT_SERVER_IMAGE = "localhost/fleetrmw/ngtcp2-public-mtls:0.12.1"
DEFAULT_BASE_IMAGE = "localhost/fleetrmw/rmw-netem:jazzy"
PUBLISHER_ID = "stateful-gateway-publisher"
PUBLISHER_URI = f"spiffe://fleetqox/publishers/{PUBLISHER_ID}"


def run(
    command: list[str],
    *,
    timeout: float = 600.0,
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        command,
        cwd=ROOT,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=timeout,
        check=False,
    )


def json_rows(output: str) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for line in output.splitlines():
        if not line.strip().startswith("{"):
            continue
        try:
            value = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(value, dict):
            rows.append(value)
    return rows


def wait_ready(container: str, timeout_s: float = 10.0) -> bool:
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        logs = run(["docker", "logs", container], timeout=10.0)
        if (
            logs.returncode == 0
            and BACKEND_SCHEMA_VERSION in logs.stdout + logs.stderr
            and '"status": "ready"' in logs.stdout + logs.stderr
        ):
            return True
        state = run(
            ["docker", "inspect", "-f", "{{.State.Running}}", container],
            timeout=10.0,
        )
        if state.returncode != 0 or state.stdout.strip() != "true":
            return False
        time.sleep(0.1)
    return False


def stateful_certificate_command(certs: Path, root: Path) -> str:
    prefix = f"/work/{certs.relative_to(root)}"
    return (
        certificate_command(certs, root)
        + " && openssl req -new -newkey rsa:2048 -nodes "
        f"-keyout {prefix}/stateful-client.key "
        f"-out {prefix}/stateful-client.csr "
        f"-subj /CN={PUBLISHER_ID} "
        "-addext extendedKeyUsage=clientAuth "
        f"-addext subjectAltName=URI:{PUBLISHER_URI} >/dev/null 2>&1 && "
        f"openssl x509 -req -in {prefix}/stateful-client.csr "
        f"-CA {prefix}/client-ca.crt -CAkey {prefix}/client-ca.key "
        f"-CAcreateserial -out {prefix}/stateful-client.crt "
        "-days 1 -copy_extensions copy >/dev/null 2>&1"
    )


def probe_ok(probe: dict[str, Any]) -> bool:
    return (
        probe.get("schema_version") == PROBE_SCHEMA_VERSION
        and probe.get("status") == "ok"
        and probe.get("stateful_gateway_roundtrip_claim") is True
        and probe.get("per_consumer_replay_claim") is True
        and probe.get("invalid_frame_http_status_fail_closed_claim") is True
        and probe.get("alpha_connections_created") == 1
        and probe.get("alpha_handshakes_completed") == 1
        and probe.get("alpha_streams_opened") == 7
        and probe.get("alpha_connection_reuse_count") == 6
        and probe.get("beta_connections_created") == 1
        and probe.get("beta_handshakes_completed") == 1
        and probe.get("beta_streams_opened") == 3
        and probe.get("beta_connection_reuse_count") == 2
    )


def forged_frame() -> bytes:
    payload = b"forged-identity-payload"
    document = {
        "schema_version": "fleetrmw.data_frame.v1",
        "kind": "sidecar_packet_frame",
        "domain_id": 42,
        "route": {
            "robot_id": "forged-robot",
            "topic": "/fleetqox/gateway",
        },
        "sample_envelope": {
            "robot_id": "forged-robot",
            "topic": "/fleetqox/gateway",
            "publisher_id": "forged-publisher",
            "source_sequence_number": 99,
            "source_timestamp_ns": 99_000,
        },
        "serialized_payload": {
            "encoding": "hex",
            "size": len(payload),
            "data": payload.hex(),
        },
    }
    return DATA_FRAME_MAGIC + json.dumps(
        document, separators=(",", ":")
    ).encode()


def backend_ok(summary: dict[str, Any]) -> bool:
    adapter = summary.get("metrics", {})
    state = adapter.get("state", {}) if isinstance(adapter, dict) else {}
    return (
        summary.get("schema_version") == BACKEND_SCHEMA_VERSION
        and summary.get("status") == "stopped"
        and summary.get("clean_teardown") is True
        and adapter.get("identity_rejections") == 1
        and adapter.get("protocol_rejections") == 0
        and adapter.get("require_client_identity") is True
        and adapter.get("accept_public_path_observations") is False
        and adapter.get("public_path_telemetry_requests") == 4
        and adapter.get("public_path_observation_updates") == 0
        and adapter.get("public_path_missing_rtt_samples") == 0
        and adapter.get("last_public_path_telemetry", {}).get(
            "rtt_initialized"
        )
        is True
        and adapter.get("last_public_path_telemetry", {}).get(
            "smoothed_rtt_us", 0
        )
        > 0
        and adapter.get("public_path_loss_semantics")
        == "raw_ngtcp2_stream_packet_loss_count_not_loss_ratio"
        and adapter.get("public_path_rttvar_semantics")
        == "ngtcp2_rttvar_mean_deviation_used_as_jitter_proxy"
        and state.get("requests_total") == 11
        and state.get("post_requests") == 5
        and state.get("get_requests") == 6
        and state.get("accepted_frames") == 3
        and state.get("duplicate_frames") == 1
        and state.get("invalid_frames") == 1
        and state.get("dequeued_frames") == 6
        and state.get("retained_frames") == 3
        and state.get("consumer_count") == 2
    )


def stop_server(container: str) -> tuple[int, str]:
    stop = run(
        [
            "docker",
            "exec",
            container,
            "bash",
            "-lc",
            "kill -INT \"$(cat /tmp/fleetqox-public-server.pid)\"",
        ],
        timeout=20.0,
    )
    wait = run(["docker", "wait", container], timeout=20.0)
    logs = run(["docker", "logs", container], timeout=20.0)
    exit_code = (
        int(wait.stdout.strip())
        if wait.returncode == 0 and wait.stdout.strip().isdigit()
        else -1
    )
    return exit_code if stop.returncode == 0 else -1, logs.stdout + logs.stderr


def run_iteration(
    *,
    root: Path,
    base_image: str,
    server_image: str,
    network: str,
    install: str,
    temp_root: Path,
    index: int,
) -> dict[str, Any]:
    suffix = f"{os.getpid()}-{index}"
    server_name = f"fq-public-stateful-{suffix}"
    client_name = f"fq-public-stateful-client-{suffix}"
    certs = temp_root / "certs"
    run_root = temp_root / f"run-{index}"
    htdocs = run_root / "htdocs"
    server_qlogs = run_root / "server-qlogs"
    client_qlogs = run_root / "client-qlogs"
    backend_summary = run_root / "backend-summary.json"
    forged_payload = run_root / "forged.frame"
    for directory in (htdocs, server_qlogs, client_qlogs):
        directory.mkdir(parents=True, exist_ok=True)
    (htdocs / "index.html").write_text("stateful gateway\n", encoding="utf-8")
    forged_payload.write_bytes(forged_frame())

    cert_root = f"/work/{certs.relative_to(root)}"
    htdocs_root = f"/work/{htdocs.relative_to(root)}"
    server_qlog_root = f"/work/{server_qlogs.relative_to(root)}"
    backend_summary_path = f"/work/{backend_summary.relative_to(root)}"
    backend_socket = "/tmp/fleetqox-stateful-backend.sock"
    server_command = (
        "set -euo pipefail; "
        f"rm -f {backend_socket} {shlex.quote(backend_summary_path)}; "
        "python3 -m fleetqox.public_quic_gateway_backend "
        f"--socket {backend_socket} --max-frames-per-topic 8 "
        "--max-frame-bytes 65536 "
        f"--summary-json {shlex.quote(backend_summary_path)} & "
        "backend_pid=$!; "
        "for attempt in $(seq 1 100); do "
        f"test -S {backend_socket} && break; sleep 0.05; done; "
        f"test -S {backend_socket}; "
        "tc qdisc replace dev eth0 root netem delay 11ms 2ms loss 0.2%; "
        "fleetqox-public-mtls-server "
        f"--htdocs={shlex.quote(htdocs_root)} "
        f"--qlog-dir={shlex.quote(server_qlog_root)} "
        "--verify-client --no-quic-dump --no-http-dump "
        f"'*' 4433 {cert_root}/server.key {cert_root}/server.crt & "
        "server_pid=$!; echo \"$server_pid\" >/tmp/fleetqox-public-server.pid; "
        "wait \"$server_pid\"; server_rc=$?; "
        "kill -TERM \"$backend_pid\" 2>/dev/null || true; "
        "wait \"$backend_pid\" || true; exit \"$server_rc\""
    )
    start = run(
        [
            "docker",
            "run",
            "-d",
            "--name",
            server_name,
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
            f"FLEETQOX_GNUTLS_REQUIRED_CLIENT_URI_SAN={PUBLISHER_URI}",
            "-e",
            "FLEETQOX_GNUTLS_CLIENT_URI_PREFIX=spiffe://fleetqox/publishers/",
            "-e",
            f"FLEETQOX_STATE_BACKEND_SOCKET={backend_socket}",
            "-v",
            f"{root}:/work",
            "-w",
            "/work",
            server_image,
            "-lc",
            server_command,
        ],
        timeout=30.0,
    )
    ready = start.returncode == 0 and wait_ready(server_name)
    client = subprocess.CompletedProcess([], 1, "", "server_not_ready")
    forged = subprocess.CompletedProcess([], 1, "", "server_not_ready")
    server_exit = -1
    server_logs = ""
    try:
        if ready:
            uri = (
                "https://localhost:4433/fleetrmw/v1/frames?"
                "domain_id=42&topic=%2Ffleetqox%2Fgateway&consumer_id=alpha"
            )
            probe_binary = (
                f"{install}/rmw_fleetqox_cpp/lib/rmw_fleetqox_cpp/"
                "fleetrmw_quic_stateful_gateway_probe"
            )
            client_command = (
                "source /opt/ros/jazzy/setup.bash && "
                f"source {install}/setup.bash && "
                "tc qdisc replace dev eth0 root netem delay 9ms 2ms loss 0.2% && "
                "export FLEETQOX_RMW_REMOTE_TRANSPORT=quic_gateway && "
                "export FLEETQOX_RMW_QUIC_BACKEND=inprocess && "
                "export FLEETQOX_RMW_QUIC_GATEWAY=fleetqox-mtls-gateway:4433 && "
                f"export FLEETQOX_RMW_QUIC_URI='{uri}' && "
                "export FLEETQOX_RMW_QUIC_SNI=localhost && "
                "export FLEETQOX_RMW_QUIC_TIMEOUT=8s && "
                f"export FLEETQOX_RMW_QUIC_CA_FILE={cert_root}/server-ca.crt && "
                f"export FLEETQOX_RMW_QUIC_CLIENT_CERT_FILE={cert_root}/stateful-client.crt && "
                f"export FLEETQOX_RMW_QUIC_CLIENT_KEY_FILE={cert_root}/stateful-client.key && "
                f"export FLEETQOX_RMW_QUIC_QLOG_DIR=/work/{client_qlogs.relative_to(root)} && "
                + probe_binary
            )
            client = run(
                [
                    "docker",
                    "run",
                    "--rm",
                    "--name",
                    client_name,
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
                    base_image,
                    "-lc",
                    client_command,
                ],
                timeout=90.0,
            )
            forged_qlog = f"/work/{(client_qlogs / 'forged.qlog').relative_to(root)}"
            forged_command = (
                f"cp {cert_root}/server-ca.crt "
                "/usr/local/share/ca-certificates/fleetqox-public-ca.crt && "
                "update-ca-certificates >/dev/null 2>&1 && "
                "tc qdisc replace dev eth0 root netem delay 9ms 2ms loss 0.2% && "
                "gtlsclient fleetqox-mtls-gateway 4433 "
                "'https://fleetqox-mtls-gateway:4433/fleetrmw/v1/frames?"
                "domain_id=42&topic=%2Ffleetqox%2Fgateway&consumer_id=forged' "
                "--http-method=POST "
                f"--data /work/{forged_payload.relative_to(root)} "
                f"--key={cert_root}/stateful-client.key "
                f"--cert={cert_root}/stateful-client.crt "
                "--disable-early-data --exit-on-all-streams-close "
                "--no-quic-dump --no-http-dump "
                f"--qlog-file={forged_qlog}"
            )
            forged = run(
                [
                    "docker",
                    "run",
                    "--rm",
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
                    server_image,
                    "-lc",
                    forged_command,
                ],
                timeout=60.0,
            )
        if ready:
            server_exit, server_logs = stop_server(server_name)
    finally:
        run(["docker", "rm", "-f", server_name], timeout=20.0)

    probe_rows = json_rows(client.stdout)
    probe = next(
        (
            row
            for row in probe_rows
            if row.get("schema_version") == PROBE_SCHEMA_VERSION
        ),
        {},
    )
    backend = (
        json.loads(backend_summary.read_text(encoding="utf-8"))
        if backend_summary.exists()
        else {}
    )
    server_qlog_files = [path for path in server_qlogs.glob("*") if path.is_file()]
    client_qlog_files = [path for path in client_qlogs.glob("*") if path.is_file()]
    response_count = server_logs.count("FLEETQOX_STATE_BACKEND_RESPONSE")
    verified_count = server_logs.count("FLEETQOX_PUBLIC_MTLS_VERIFIED")
    identity_count = server_logs.count("FLEETQOX_PUBLIC_MTLS_IDENTITY")
    ok = (
        ready
        and client.returncode == 0
        and server_exit == 0
        and probe_ok(probe)
        and backend_ok(backend)
        and forged.returncode == 0
        and "[:status: 403]" in forged.stderr
        and response_count == 12
        and verified_count == 4
        and identity_count == 4
        and len(server_qlog_files) >= 4
        and len(client_qlog_files) >= 4
        and all(path.stat().st_size > 0 for path in server_qlog_files)
        and all(path.stat().st_size > 0 for path in client_qlog_files)
    )
    return {
        "index": index,
        "status": "ok" if ok else "failed",
        "server_ready": ready,
        "client_returncode": client.returncode,
        "forged_identity_returncode": forged.returncode,
        "forged_identity_http_403": "[:status: 403]" in forged.stderr,
        "server_exit_code": server_exit,
        "probe": probe,
        "backend": backend,
        "backend_response_count": response_count,
        "verified_client_count": verified_count,
        "bound_identity_count": identity_count,
        "server_qlog_file_count": len(server_qlog_files),
        "client_qlog_file_count": len(client_qlog_files),
        "netem_server": "delay 11ms 2ms loss 0.2%",
        "netem_client": "delay 9ms 2ms loss 0.2%",
        "client_stderr": "" if ok else client.stderr,
        "forged_stderr": "" if ok else forged.stderr,
        "server_logs": "" if ok else server_logs,
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
    server_build = subprocess.CompletedProcess([], 0, "", "")
    if not skip_server_build:
        server_build = run(
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
            ]
        )
    temp_root = root / f".tmp_fleetrmw_public_stateful_{os.getpid()}"
    certs = temp_root / "certs"
    certs.mkdir(parents=True, exist_ok=True)
    cert = run(
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
            stateful_certificate_command(certs, root),
        ],
        timeout=180.0,
    )
    build_root = "/work/.tmp_fleetrmw_public_stateful_build"
    install = "/work/.tmp_fleetrmw_public_stateful_install"
    log_root = "/work/.tmp_fleetrmw_public_stateful_log"
    build = run(
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
            "source /opt/ros/jazzy/setup.bash && "
            f"rm -rf {build_root} {install} {log_root} && "
            f"colcon --log-base {log_root} build --base-paths ros2_ws/src "
            "--packages-select rmw_fleetqox_cpp "
            f"--build-base {build_root} --install-base {install} "
            "--cmake-args -DCMAKE_BUILD_TYPE=Release",
        ],
        timeout=600.0,
    )
    network = f"fq-public-stateful-net-{os.getpid()}"
    network_result = run(["docker", "network", "create", network], timeout=20.0)
    rows: list[dict[str, Any]] = []
    try:
        if all(
            result.returncode == 0
            for result in (server_build, cert, build, network_result)
        ):
            for index in range(max(1, iterations)):
                rows.append(
                    run_iteration(
                        root=root,
                        base_image=base_image,
                        server_image=server_image,
                        network=network,
                        install=install,
                        temp_root=temp_root,
                        index=index,
                    )
                )
    finally:
        run(["docker", "network", "rm", network], timeout=20.0)
        if not keep_temp:
            run(
                [
                    "docker",
                    "run",
                    "--rm",
                    "--entrypoint",
                    "bash",
                    "-v",
                    f"{root}:/work",
                    base_image,
                    "-lc",
                    f"rm -rf {build_root} {install} {log_root}",
                ],
                timeout=60.0,
            )
            shutil.rmtree(temp_root, ignore_errors=True)
    run_count = max(1, iterations)
    ok_count = sum(row.get("status") == "ok" for row in rows)
    ok = (
        all(
            result.returncode == 0
            for result in (server_build, cert, build, network_result)
        )
        and len(rows) == run_count
        and ok_count == run_count
    )
    return {
        "schema_version": SCHEMA_VERSION,
        "status": "ok" if ok else "failed",
        "run_count": run_count,
        "ok_run_count": ok_count,
        "public_api_stateful_gateway_backend_integrated_claim": ok,
        "public_api_stateful_history_dedup_cursor_claim": ok,
        "public_api_stateful_identity_binding_claim": ok,
        "public_api_stateful_session_reuse_claim": ok,
        "public_api_path_telemetry_forwarded_claim": ok,
        "docker_netem_both_ends_claim": ok,
        "aioquic_server_runtime_used": False,
        "aioquic_private_server_hook_required": False,
        "native_public_path_metrics_integrated": False,
        "production_quic_backend_claim": False,
        "server_build_returncode": server_build.returncode,
        "certificate_returncode": cert.returncode,
        "rmw_build_returncode": build.returncode,
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
            "docker_ngtcp2_public_stateful_gateway_summary.json"
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

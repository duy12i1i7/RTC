#!/usr/bin/env python3
"""Repeat the stateful FleetRMW QUIC/H3 gateway with the in-process C++ client."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import shutil
import subprocess
import time
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
SCHEMA_VERSION = "fleetrmw.docker_quic_stateful_gateway_probe.v1"
SERVICE_SCHEMA_VERSION = "fleetrmw.quic_gateway_service.v1"
PROBE_SCHEMA_VERSION = "fleetrmw.quic_stateful_gateway_probe.v1"
DEFAULT_IMAGE = "localhost/fleetrmw/rmw-netem:jazzy"


def run(command: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        command,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )


def json_rows(output: str) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for line in output.splitlines():
        line = line.strip()
        if not line.startswith("{"):
            continue
        try:
            value = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(value, dict):
            rows.append(value)
    return rows


def wait_service_ready(container: str, timeout_s: float = 8.0) -> bool:
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        logs = run(["docker", "logs", container]).stdout
        if (
            SERVICE_SCHEMA_VERSION in logs
            and '"status": "ready"' in logs
            and '"stateful": true' in logs
        ):
            return True
        state = run(
            ["docker", "inspect", "-f", "{{.State.Running}}", container]
        )
        if state.returncode != 0 or state.stdout.strip() != "true":
            return False
        time.sleep(0.1)
    return False


def probe_ok(probe: dict[str, Any]) -> bool:
    return (
        probe.get("schema_version") == PROBE_SCHEMA_VERSION
        and probe.get("status") == "ok"
        and probe.get("backend") == "inprocess"
        and probe.get("subprocess_backed") is False
        and probe.get("stateful_gateway_roundtrip_claim") is True
        and probe.get("per_consumer_replay_claim") is True
        and probe.get("invalid_frame_http_status_fail_closed_claim") is True
        and probe.get("published_request_count") == 4
        and probe.get("unique_frame_count") == 3
        and probe.get("consumer_count") == 2
        and probe.get("alpha_received_count") == 3
        and probe.get("beta_received_count") == 3
        and probe.get("alpha_connections_created") == 1
        and probe.get("alpha_handshakes_completed") == 1
        and probe.get("alpha_streams_opened") == 7
        and probe.get("alpha_connection_reuse_count") == 6
        and probe.get("beta_connections_created") == 1
        and probe.get("beta_handshakes_completed") == 1
        and probe.get("beta_streams_opened") == 3
        and probe.get("beta_connection_reuse_count") == 2
        and probe.get("tls_peer_verification_required") is True
        and probe.get("quic_v1_h3") is True
        and probe.get("production_readiness") is False
    )


def service_ok(service: dict[str, Any]) -> bool:
    metrics = service.get("metrics", {})
    transport_metrics = service.get("transport_metrics", {})
    return (
        service.get("schema_version") == SERVICE_SCHEMA_VERSION
        and service.get("status") == "stopped"
        and service.get("clean_teardown") is True
        and metrics.get("schema_version") == "fleetrmw.quic_gateway_state.v1"
        and metrics.get("requests_total") == 11
        and metrics.get("post_requests") == 5
        and metrics.get("get_requests") == 6
        and metrics.get("accepted_frames") == 3
        and metrics.get("duplicate_frames") == 1
        and metrics.get("invalid_frames") == 1
        and metrics.get("dequeued_frames") == 6
        and metrics.get("empty_takes") == 0
        and metrics.get("topic_count") == 1
        and metrics.get("consumer_count") == 2
        and metrics.get("retained_frames") == 3
        and metrics.get("evicted_frames") == 0
        and metrics.get("consumer_overruns") == 0
        and transport_metrics.get("connections_created") == 3
        and transport_metrics.get("h3_sessions_negotiated") == 3
    )


def run_case(
    *,
    root: Path,
    image: str,
    network: str,
    install: str,
    temp_root: Path,
    index: int,
) -> dict[str, Any]:
    suffix = f"{os.getpid()}-{index}"
    service_name = f"fleetrmw-stateful-quic-service-{suffix}"
    client_name = f"fleetrmw-stateful-quic-client-{suffix}"
    case_root = temp_root / f"run-{index}"
    service_qlogs = case_root / "service-qlogs"
    client_qlogs = case_root / "client-qlogs"
    service_qlogs.mkdir(parents=True, exist_ok=True)
    client_qlogs.mkdir(parents=True, exist_ok=True)
    certs = temp_root / "certs"
    probe_binary = (
        f"{install}/rmw_fleetqox_cpp/lib/rmw_fleetqox_cpp/"
        "fleetrmw_quic_stateful_gateway_probe"
    )
    service_command = (
        "tc qdisc replace dev eth0 root netem delay 5ms 1ms loss 0.2% && "
        "tc qdisc show dev eth0 && "
        "exec python3 scripts/fleetrmw_quic_gateway_service.py "
        "--host 0.0.0.0 --port 4495 "
        f"--certificate /work/{certs.relative_to(root)}/server.crt "
        f"--private-key /work/{certs.relative_to(root)}/server.key "
        f"--qlog-dir /work/{service_qlogs.relative_to(root)} "
        "--max-frames-per-topic 8 --max-frame-bytes 65536"
    )
    service_start = run(
        [
            "docker",
            "run",
            "-d",
            "--name",
            service_name,
            "--network",
            network,
            "--network-alias",
            "fleetqox-quic-gateway",
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
            service_command,
        ]
    )
    ready = service_start.returncode == 0 and wait_service_ready(service_name)
    client = subprocess.CompletedProcess([], 1, "", "service_not_ready")
    service_exit_code = -1
    service_logs = ""
    try:
        if ready:
            uri = (
                "https://localhost:4495/fleetrmw/v1/frames?"
                "domain_id=42&topic=%2Ffleetqox%2Fgateway&consumer_id=alpha"
            )
            client_command = (
                "source /opt/ros/jazzy/setup.bash && "
                f"source {install}/setup.bash && "
                "tc qdisc replace dev eth0 root netem delay 7ms 2ms loss 0.2% && "
                "tc qdisc show dev eth0 && "
                "export FLEETQOX_RMW_REMOTE_TRANSPORT=quic_gateway && "
                "export FLEETQOX_RMW_QUIC_BACKEND=inprocess && "
                "export FLEETQOX_RMW_QUIC_GATEWAY=fleetqox-quic-gateway:4495 && "
                f"export FLEETQOX_RMW_QUIC_URI='{uri}' && "
                "export FLEETQOX_RMW_QUIC_SNI=localhost && "
                "export FLEETQOX_RMW_QUIC_TIMEOUT=8s && "
                f"export FLEETQOX_RMW_QUIC_CA_FILE=/work/{certs.relative_to(root)}/ca.crt && "
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
                    image,
                    "-lc",
                    client_command,
                ]
            )
            # Let delayed CONNECTION_CLOSE datagrams reach the server so aioquic
            # can finalize one qlog trace per client connection before shutdown.
            time.sleep(0.5)
        run(["docker", "stop", "--time", "3", service_name])
        exit_result = run(
            ["docker", "inspect", "-f", "{{.State.ExitCode}}", service_name]
        )
        if exit_result.returncode == 0 and exit_result.stdout.strip():
            service_exit_code = int(exit_result.stdout.strip())
        service_logs = run(["docker", "logs", service_name]).stdout
    finally:
        run(["docker", "rm", "-f", service_name])

    client_rows = json_rows(client.stdout)
    probe = client_rows[-1] if client_rows else {}
    service_rows = json_rows(service_logs)
    service = service_rows[-1] if service_rows else {}
    service_qlog_files = [path for path in service_qlogs.glob("*") if path.is_file()]
    client_qlog_files = [path for path in client_qlogs.glob("*") if path.is_file()]
    netem_ok = "qdisc netem" in service_logs and "qdisc netem" in client.stdout
    qlog_ok = (
        len(service_qlog_files) >= 1
        and len(client_qlog_files) >= 3
        and all(path.stat().st_size > 0 for path in service_qlog_files + client_qlog_files)
    )
    ok = (
        ready
        and client.returncode == 0
        and service_exit_code == 0
        and probe_ok(probe)
        and service_ok(service)
        and netem_ok
        and qlog_ok
    )
    return {
        "index": index,
        "status": "ok" if ok else "failed",
        "service_ready": ready,
        "client_returncode": client.returncode,
        "service_exit_code": service_exit_code,
        "probe": probe,
        "service": service,
        "service_qlog_file_count": len(service_qlog_files),
        "service_qlog_bytes": sum(path.stat().st_size for path in service_qlog_files),
        "client_qlog_file_count": len(client_qlog_files),
        "client_qlog_bytes": sum(path.stat().st_size for path in client_qlog_files),
        "netem_configured_both_containers": netem_ok,
        "client_stdout": "" if ok else client.stdout,
        "client_stderr": "" if ok else client.stderr,
        "service_logs": "" if ok else service_logs,
    }


def run_probe(
    *, root: Path, image: str, iterations: int, keep_temp: bool
) -> dict[str, Any]:
    run_count = max(1, iterations)
    temp_root = root / f".tmp_fleetrmw_quic_stateful_gateway_{os.getpid()}"
    certs = temp_root / "certs"
    certs.mkdir(parents=True, exist_ok=True)
    build_root = "/work/.tmp_fleetrmw_quic_stateful_gateway_build"
    install = "/work/.tmp_fleetrmw_quic_stateful_gateway_install"
    log_root = "/work/.tmp_fleetrmw_quic_stateful_gateway_log"
    cert_command = (
        "openssl req -x509 -newkey rsa:2048 -nodes "
        f"-keyout /work/{certs.relative_to(root)}/ca.key "
        f"-out /work/{certs.relative_to(root)}/ca.crt "
        "-subj /CN=FleetQoX-Stateful-Gateway-CA "
        "-addext basicConstraints=critical,CA:TRUE "
        "-addext keyUsage=critical,keyCertSign,cRLSign -days 1 >/dev/null 2>&1 && "
        "openssl req -new -newkey rsa:2048 -nodes "
        f"-keyout /work/{certs.relative_to(root)}/server.key "
        f"-out /work/{certs.relative_to(root)}/server.csr "
        "-subj /CN=localhost "
        "-addext subjectAltName=DNS:localhost,DNS:fleetqox-quic-gateway "
        "-addext extendedKeyUsage=serverAuth >/dev/null 2>&1 && "
        f"openssl x509 -req -in /work/{certs.relative_to(root)}/server.csr "
        f"-CA /work/{certs.relative_to(root)}/ca.crt "
        f"-CAkey /work/{certs.relative_to(root)}/ca.key -CAcreateserial "
        f"-out /work/{certs.relative_to(root)}/server.crt "
        "-days 1 -copy_extensions copy >/dev/null 2>&1"
    )
    cert_result = run(
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
            image,
            "-lc",
            cert_command,
        ]
    )
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
            image,
            "-lc",
            "source /opt/ros/jazzy/setup.bash && "
            f"rm -rf {build_root} {install} {log_root} && "
            f"colcon --log-base {log_root} build --base-paths ros2_ws/src "
            "--packages-select rmw_fleetqox_cpp "
            f"--build-base {build_root} --install-base {install} "
            "--cmake-args -DCMAKE_BUILD_TYPE=Release",
        ]
    )
    network = f"fleetrmw-stateful-quic-net-{os.getpid()}"
    network_result = run(["docker", "network", "create", network])
    runs: list[dict[str, Any]] = []
    try:
        if (
            cert_result.returncode == 0
            and build.returncode == 0
            and network_result.returncode == 0
        ):
            for index in range(1, run_count + 1):
                runs.append(
                    run_case(
                        root=root,
                        image=image,
                        network=network,
                        install=install,
                        temp_root=temp_root,
                        index=index,
                    )
                )
    finally:
        run(["docker", "network", "rm", network])
        if not keep_temp:
            cleanup = run(
                [
                    "docker",
                    "run",
                    "--rm",
                    "--entrypoint",
                    "bash",
                    "-v",
                    f"{root}:/work",
                    image,
                    "-lc",
                    f"rm -rf {build_root} {install} {log_root}",
                ]
            )
            if cleanup.returncode == 0:
                shutil.rmtree(temp_root, ignore_errors=True)

    successful_runs = sum(run_row.get("status") == "ok" for run_row in runs)
    status = (
        "ok"
        if cert_result.returncode == 0
        and build.returncode == 0
        and network_result.returncode == 0
        and len(runs) == run_count
        and successful_runs == run_count
        else "failed"
    )
    return {
        "schema_version": SCHEMA_VERSION,
        "status": status,
        "run_count": run_count,
        "successful_runs": successful_runs,
        "failed_run_count": run_count - successful_runs,
        "server": "python3-aioquic QUIC v1/H3 stateful FleetQoX gateway",
        "client": "in-process C++ ngtcp2/GnuTLS/nghttp3 backend",
        "subprocess_backed_client": False,
        "real_quic_v1_h3": True,
        "tls_peer_verification_required": True,
        "netem": "service 5ms +/-1ms 0.2% loss; client 7ms +/-2ms 0.2% loss",
        "stateful_fleetqox_quic_gateway_service_claim": status == "ok",
        "bounded_topic_history_claim": status == "ok",
        "publisher_sequence_deduplication_claim": status == "ok",
        "independent_consumer_cursor_replay_claim": status == "ok",
        "invalid_frame_http_status_fail_closed_claim": status == "ok",
        "production_quic_backend_claim": False,
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
        default="results_rmw_socket/docker_quic_stateful_gateway_probe_summary.json",
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
        print("fleetrmw-quic-stateful-gateway-probe")
        print(f"  status: {summary['status']}")
        print(f"  successful_runs: {summary['successful_runs']}/{summary['run_count']}")
    return 0 if summary["status"] == "ok" else 1


if __name__ == "__main__":
    raise SystemExit(main())

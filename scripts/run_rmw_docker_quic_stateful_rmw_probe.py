#!/usr/bin/env python3
"""Exercise public RMW publish/take through the stateful QUIC/H3 gateway."""

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
    from scripts.run_rmw_docker_quic_stateful_gateway_probe import (
        DEFAULT_IMAGE,
        SERVICE_SCHEMA_VERSION,
        json_rows,
        run,
        wait_service_ready,
    )
except ModuleNotFoundError:
    from run_rmw_docker_quic_stateful_gateway_probe import (
        DEFAULT_IMAGE,
        SERVICE_SCHEMA_VERSION,
        json_rows,
        run,
        wait_service_ready,
    )


ROOT = Path(__file__).resolve().parents[1]
SCHEMA_VERSION = "fleetrmw.docker_quic_stateful_rmw_probe.v1"
PROBE_SCHEMA_VERSION = "fleetrmw.quic_stateful_rmw_probe.v1"


def endpoint_ok(row: dict[str, Any], mode: str) -> bool:
    return (
        row.get("schema_version") == PROBE_SCHEMA_VERSION
        and row.get("mode") == mode
        and row.get("status") == "ok"
        and row.get("topic") == "/fleetqox/stateful_rmw"
        and row.get("message_count") == 3
        and row.get("completed_count") == 3
        and row.get("ordered_payloads") is True
        and row.get("frames_sent") == (3 if mode == "publisher" else 0)
        and row.get("frames_received") == (3 if mode == "subscriber" else 0)
        and row.get("connections_created") == 1
        and row.get("handshakes_completed") == 1
        and row.get("streams_opened") == 3
        and row.get("connection_reuse_count") == 2
        and row.get("rmw_publish_path_integrated") is (mode == "publisher")
        and row.get("rmw_take_path_integrated") is (mode == "subscriber")
        and row.get("stateful_gateway_interprocess_claim") is True
        and row.get("tls_peer_verification_required") is True
        and row.get("subprocess_backed") is False
        and row.get("production_readiness") is False
        and (
            mode != "subscriber"
            or row.get("last_payload") == "fleetqox-stateful-rmw-3"
        )
    )


def service_ok(row: dict[str, Any]) -> bool:
    metrics = row.get("metrics", {})
    transport = row.get("transport_metrics", {})
    return (
        row.get("schema_version") == SERVICE_SCHEMA_VERSION
        and row.get("status") == "stopped"
        and row.get("clean_teardown") is True
        and metrics.get("requests_total") == 6
        and metrics.get("post_requests") == 3
        and metrics.get("get_requests") == 3
        and metrics.get("accepted_frames") == 3
        and metrics.get("duplicate_frames") == 0
        and metrics.get("invalid_frames") == 0
        and metrics.get("dequeued_frames") == 3
        and metrics.get("empty_takes") == 0
        and metrics.get("topic_count") == 1
        and metrics.get("consumer_count") == 1
        and metrics.get("retained_frames") == 3
        and metrics.get("evicted_frames") == 0
        and metrics.get("consumer_overruns") == 0
        and transport.get("connections_created") == 2
        and transport.get("h3_sessions_negotiated") == 2
    )


def run_endpoint(
    *,
    root: Path,
    image: str,
    network: str,
    name: str,
    mode: str,
    install: str,
    certs: Path,
    qlogs: Path,
) -> subprocess.CompletedProcess[str]:
    uri = (
        "https://localhost:4496/fleetrmw/v1/frames?"
        "domain_id=42&topic=%2Ffleetqox%2Fstateful_rmw&"
        f"consumer_id=rmw-{mode}"
    )
    command = (
        "source /opt/ros/jazzy/setup.bash && "
        f"source {install}/setup.bash && "
        "tc qdisc replace dev eth0 root netem delay 7ms 2ms loss 0.2% && "
        "tc qdisc show dev eth0 && "
        "export FLEETQOX_RMW_REMOTE_TRANSPORT=quic_gateway && "
        "export FLEETQOX_RMW_QUIC_BACKEND=inprocess && "
        "export FLEETQOX_RMW_QUIC_GATEWAY=fleetqox-stateful-rmw-gateway:4496 && "
        f"export FLEETQOX_RMW_QUIC_URI='{uri}' && "
        "export FLEETQOX_RMW_QUIC_SNI=localhost && "
        "export FLEETQOX_RMW_QUIC_TIMEOUT=8s && "
        "export FLEETQOX_RMW_QUIC_GATEWAY_TAKE_ON_DEMAND=1 && "
        f"export FLEETQOX_RMW_QUIC_CA_FILE=/work/{certs.relative_to(root)}/ca.crt && "
        f"export FLEETQOX_RMW_QUIC_QLOG_DIR=/work/{qlogs.relative_to(root)} && "
        f"{install}/rmw_fleetqox_cpp/lib/rmw_fleetqox_cpp/"
        f"fleetrmw_quic_stateful_rmw_probe --mode {mode}"
    )
    return run(
        [
            "docker",
            "run",
            "--rm",
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
        ]
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
    service_name = f"fleetrmw-stateful-rmw-service-{suffix}"
    case_root = temp_root / f"run-{index}"
    service_qlogs = case_root / "service-qlogs"
    publisher_qlogs = case_root / "publisher-qlogs"
    subscriber_qlogs = case_root / "subscriber-qlogs"
    for directory in (service_qlogs, publisher_qlogs, subscriber_qlogs):
        directory.mkdir(parents=True, exist_ok=True)
    certs = temp_root / "certs"
    service_command = (
        "tc qdisc replace dev eth0 root netem delay 5ms 1ms loss 0.2% && "
        "tc qdisc show dev eth0 && "
        "exec python3 scripts/fleetrmw_quic_gateway_service.py "
        "--host 0.0.0.0 --port 4496 "
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
            "fleetqox-stateful-rmw-gateway",
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
    publisher = subprocess.CompletedProcess([], 1, "", "service_not_ready")
    subscriber = subprocess.CompletedProcess([], 1, "", "publisher_not_ready")
    service_exit_code = -1
    service_logs = ""
    try:
        if ready:
            publisher = run_endpoint(
                root=root,
                image=image,
                network=network,
                name=f"fleetrmw-stateful-rmw-publisher-{suffix}",
                mode="publisher",
                install=install,
                certs=certs,
                qlogs=publisher_qlogs,
            )
        if publisher.returncode == 0:
            subscriber = run_endpoint(
                root=root,
                image=image,
                network=network,
                name=f"fleetrmw-stateful-rmw-subscriber-{suffix}",
                mode="subscriber",
                install=install,
                certs=certs,
                qlogs=subscriber_qlogs,
            )
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

    publisher_rows = json_rows(publisher.stdout)
    subscriber_rows = json_rows(subscriber.stdout)
    service_rows = json_rows(service_logs)
    publisher_row = publisher_rows[-1] if publisher_rows else {}
    subscriber_row = subscriber_rows[-1] if subscriber_rows else {}
    service_row = service_rows[-1] if service_rows else {}
    service_qlog_files = list(service_qlogs.glob("*"))
    publisher_qlog_files = list(publisher_qlogs.glob("*"))
    subscriber_qlog_files = list(subscriber_qlogs.glob("*"))
    qlog_files = service_qlog_files + publisher_qlog_files + subscriber_qlog_files
    netem_ok = all(
        "qdisc netem" in output
        for output in (service_logs, publisher.stdout, subscriber.stdout)
    )
    qlog_ok = (
        len(service_qlog_files) >= 1
        and len(publisher_qlog_files) == 1
        and len(subscriber_qlog_files) == 1
        and all(path.is_file() and path.stat().st_size > 0 for path in qlog_files)
    )
    ok = (
        ready
        and publisher.returncode == 0
        and subscriber.returncode == 0
        and service_exit_code == 0
        and endpoint_ok(publisher_row, "publisher")
        and endpoint_ok(subscriber_row, "subscriber")
        and service_ok(service_row)
        and netem_ok
        and qlog_ok
    )
    return {
        "index": index,
        "status": "ok" if ok else "failed",
        "service_ready": ready,
        "publisher_returncode": publisher.returncode,
        "subscriber_returncode": subscriber.returncode,
        "service_exit_code": service_exit_code,
        "publisher": publisher_row,
        "subscriber": subscriber_row,
        "service": service_row,
        "service_qlog_file_count": len(service_qlog_files),
        "publisher_qlog_file_count": len(publisher_qlog_files),
        "subscriber_qlog_file_count": len(subscriber_qlog_files),
        "qlog_total_bytes": sum(path.stat().st_size for path in qlog_files),
        "netem_configured_all_containers": netem_ok,
        "publisher_stdout": "" if ok else publisher.stdout,
        "publisher_stderr": "" if ok else publisher.stderr,
        "subscriber_stdout": "" if ok else subscriber.stdout,
        "subscriber_stderr": "" if ok else subscriber.stderr,
        "service_logs": "" if ok else service_logs,
    }


def run_probe(
    *, root: Path, image: str, iterations: int, keep_temp: bool
) -> dict[str, Any]:
    run_count = max(1, iterations)
    temp_root = root / f".tmp_fleetrmw_quic_stateful_rmw_{os.getpid()}"
    certs = temp_root / "certs"
    certs.mkdir(parents=True, exist_ok=True)
    build_root = "/work/.tmp_fleetrmw_quic_stateful_rmw_build"
    install = "/work/.tmp_fleetrmw_quic_stateful_rmw_install"
    log_root = "/work/.tmp_fleetrmw_quic_stateful_rmw_log"
    cert_command = (
        "openssl req -x509 -newkey rsa:2048 -nodes "
        f"-keyout /work/{certs.relative_to(root)}/ca.key "
        f"-out /work/{certs.relative_to(root)}/ca.crt "
        "-subj /CN=FleetQoX-Stateful-RMW-CA "
        "-addext basicConstraints=critical,CA:TRUE "
        "-addext keyUsage=critical,keyCertSign,cRLSign -days 1 >/dev/null 2>&1 && "
        "openssl req -new -newkey rsa:2048 -nodes "
        f"-keyout /work/{certs.relative_to(root)}/server.key "
        f"-out /work/{certs.relative_to(root)}/server.csr "
        "-subj /CN=localhost "
        "-addext subjectAltName=DNS:localhost,DNS:fleetqox-stateful-rmw-gateway "
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
    network = f"fleetrmw-stateful-rmw-net-{os.getpid()}"
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

    successful_runs = sum(row.get("status") == "ok" for row in runs)
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
        "container_count_per_run": 3,
        "publisher": "public rmw_publish std_msgs/String",
        "subscriber": "public rmw_take std_msgs/String",
        "gateway": "stateful aioquic QUIC v1/H3 FleetQoX service",
        "real_quic_v1_h3": True,
        "tls_peer_verification_required": True,
        "subprocess_backed_clients": False,
        "stateful_gateway_interprocess_rmw_publish_take_claim": status == "ok",
        "rmw_publish_path_integrated_claim": status == "ok",
        "rmw_take_path_integrated_claim": status == "ok",
        "persistent_session_reuse_both_endpoints_claim": status == "ok",
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
        default="results_rmw_socket/docker_quic_stateful_rmw_probe_summary.json",
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
        print("fleetrmw-quic-stateful-rmw-probe")
        print(f"  status: {summary['status']}")
        print(f"  successful_runs: {summary['successful_runs']}/{summary['run_count']}")
    return 0 if summary["status"] == "ok" else 1


if __name__ == "__main__":
    raise SystemExit(main())

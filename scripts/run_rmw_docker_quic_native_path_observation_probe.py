#!/usr/bin/env python3
"""Contrast externally-unfed admission with native QUIC path observations."""

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
SCHEMA_VERSION = "fleetrmw.docker_quic_native_path_observation_probe.v1"
PROBE_SCHEMA_VERSION = "fleetrmw.quic_native_path_observation_probe.v1"
ADAPTER_MODE = "pinned_aioquic_0_9_25_private_recovery_observer"


def probe_ok(row: dict[str, Any], *, expect_success: bool) -> bool:
    return (
        row.get("schema_version") == PROBE_SCHEMA_VERSION
        and row.get("status") == "ok"
        and row.get("expected_success") is expect_success
        and row.get("send_success") is expect_success
        and row.get("expected_qox_rejection") is (not expect_success)
        and row.get("connections_created") == 1
        and row.get("handshakes_completed") == 1
        and row.get("streams_opened") == 1
        and row.get("frames_sent") == (1 if expect_success else 0)
        and row.get("frames_failed") == (0 if expect_success else 1)
        and row.get("external_observation_request_sent") is False
        and row.get("mutual_tls_client_authentication_required") is True
        and row.get("subprocess_backed") is False
        and row.get("production_readiness") is False
    )


def service_ok(row: dict[str, Any], *, native: bool) -> bool:
    metrics = row.get("metrics", {})
    admission = metrics.get("admission", {})
    transport = row.get("transport_metrics", {})
    adapter = row.get("path_observer_adapter", {})
    common = (
        row.get("schema_version") == SERVICE_SCHEMA_VERSION
        and row.get("status") == "stopped"
        and row.get("clean_teardown") is True
        and row.get("client_certificate_required") is True
        and row.get("publisher_identity_binding") is True
        and row.get("publisher_identity_source") == "uri_san"
        and row.get("admission_policy_configured") is True
        and row.get("native_path_observations_configured") is native
        and metrics.get("requests_total") == 1
        and metrics.get("post_requests") == 1
        and metrics.get("observation_requests") == 0
        and metrics.get("get_requests") == 0
        and metrics.get("invalid_frames") == 0
        and transport.get("connections_created") == 1
        and transport.get("h3_sessions_negotiated") == 1
        and transport.get("client_certificates_accepted") == 1
        and transport.get("publisher_identity_authorization_rejected") == 0
        and transport.get("mtls_private_adapter_installs") == 1
    )
    if not common:
        return False
    if not native:
        return (
            adapter.get("adapter_mode") == "disabled"
            and metrics.get("accepted_frames") == 0
            and metrics.get("retained_frames") == 0
            and admission.get("rejected_by_reason")
            == {"qox_score_below_threshold": 1}
            and admission.get("observation_updates") == 0
            and admission.get("observation_score_uses") == 0
            and transport.get("native_path_observer_installs") == 0
            and transport.get("native_path_observation_updates") == 0
        )
    return (
        adapter.get("adapter_mode") == ADAPTER_MODE
        and adapter.get("runtime_version") == "0.9.25"
        and adapter.get("supported_version") == "0.9.25"
        and adapter.get("exact_version_match") is True
        and adapter.get("compatible") is True
        and adapter.get("public_path_metrics_api") is False
        and adapter.get("production_supported") is False
        and metrics.get("accepted_frames") == 1
        and metrics.get("retained_frames") == 1
        and admission.get("rejected_by_reason") == {}
        and admission.get("active_observation_count") == 1
        and admission.get("active_observations_by_source")
        == {"quic_session_native": 1}
        and admission.get("observation_updates") == 1
        and admission.get("observation_updates_by_source")
        == {"quic_session_native": 1}
        and admission.get("observation_score_uses") == 1
        and transport.get("native_path_observer_installs") == 1
        and transport.get("native_path_observation_updates") == 1
        and transport.get("native_path_samples_unavailable") == 0
        and transport.get("native_path_packets_sent", 0) > 0
        and transport.get("native_path_latest_rtt_ms", 0.0) >= 20.0
        and transport.get("native_path_latest_rtt_variation_ms", -1.0) >= 0.0
        and 0.0 <= transport.get("native_path_latest_loss", -1.0) <= 1.0
    )


def run_client(
    *,
    root: Path,
    image: str,
    network: str,
    name: str,
    install: str,
    certs: Path,
    qlogs: Path,
    expect_success: bool,
) -> subprocess.CompletedProcess[str]:
    uri = (
        "https://localhost:4502/fleetrmw/v1/frames?"
        "domain_id=42&topic=%2Ffleetqox%2Fnative_path"
    )
    command = (
        "source /opt/ros/jazzy/setup.bash && "
        f"source {install}/setup.bash && "
        "tc qdisc replace dev eth0 root netem delay 30ms 2ms && "
        "tc qdisc show dev eth0 && "
        "export FLEETQOX_RMW_REMOTE_TRANSPORT=quic_gateway && "
        "export FLEETQOX_RMW_QUIC_BACKEND=inprocess && "
        "export FLEETQOX_RMW_QUIC_GATEWAY=fleetqox-mtls-gateway:4502 && "
        f"export FLEETQOX_RMW_QUIC_URI='{uri}' && "
        "export FLEETQOX_RMW_QUIC_SNI=localhost && "
        "export FLEETQOX_RMW_QUIC_TIMEOUT=8s && "
        f"export FLEETQOX_RMW_QUIC_CA_FILE=/work/{(certs / 'server-ca.crt').relative_to(root)} && "
        f"export FLEETQOX_RMW_QUIC_CLIENT_CERT_FILE=/work/{(certs / 'client.crt').relative_to(root)} && "
        f"export FLEETQOX_RMW_QUIC_CLIENT_KEY_FILE=/work/{(certs / 'client.key').relative_to(root)} && "
        f"export FLEETQOX_RMW_QUIC_QLOG_DIR=/work/{qlogs.relative_to(root)} && "
        f"export FLEETQOX_NATIVE_PATH_EXPECT_SUCCESS={'1' if expect_success else '0'} && "
        f"{install}/rmw_fleetqox_cpp/lib/rmw_fleetqox_cpp/"
        "fleetrmw_quic_native_path_observation_probe"
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


def run_service_case(
    *,
    root: Path,
    image: str,
    network: str,
    install: str,
    temp_root: Path,
    index: int,
    native: bool,
) -> dict[str, Any]:
    mode = "native" if native else "baseline"
    suffix = f"{os.getpid()}-{index}-{mode}"
    service_name = f"fleetrmw-native-path-service-{suffix}"
    case_root = temp_root / f"run-{index}" / mode
    service_qlogs = case_root / "service-qlogs"
    client_qlogs = case_root / "client-qlogs"
    service_qlogs.mkdir(parents=True, exist_ok=True)
    client_qlogs.mkdir(parents=True, exist_ok=True)
    certs = temp_root / "certs"
    policy = temp_root / "admission-policy.json"
    native_arg = "--native-path-observations " if native else ""
    service_command = (
        "tc qdisc replace dev eth0 root netem delay 30ms 2ms && "
        "tc qdisc show dev eth0 && "
        "exec python3 scripts/fleetrmw_quic_gateway_service.py "
        "--host 0.0.0.0 --port 4502 "
        f"--certificate /work/{(certs / 'server.crt').relative_to(root)} "
        f"--private-key /work/{(certs / 'server.key').relative_to(root)} "
        f"--client-ca /work/{(certs / 'client-ca.crt').relative_to(root)} "
        f"--client-crl /work/{(certs / 'client.crl.pem').relative_to(root)} "
        "--require-client-certificate "
        "--publisher-identity-uri-prefix spiffe://fleetqox/publishers/ "
        f"--admission-policy /work/{policy.relative_to(root)} "
        + native_arg
        + f"--qlog-dir /work/{service_qlogs.relative_to(root)} "
        "--max-frames-per-topic 8 --max-frame-bytes 65536"
    )
    started = run(
        [
            "docker",
            "run",
            "-d",
            "--name",
            service_name,
            "--network",
            network,
            "--network-alias",
            "fleetqox-mtls-gateway",
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
    ready = started.returncode == 0 and wait_service_ready(service_name)
    client = subprocess.CompletedProcess([], 1, "", "service_not_ready")
    service_exit_code = -1
    service_logs = ""
    try:
        if ready:
            client = run_client(
                root=root,
                image=image,
                network=network,
                name=f"fleetrmw-native-path-client-{suffix}",
                install=install,
                certs=certs,
                qlogs=client_qlogs,
                expect_success=native,
            )
        time.sleep(0.5)
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
    qlog_ok = len(qlog_files) >= 1 and all(
        path.stat().st_size > 0 for path in qlog_files
    )
    ok = (
        ready
        and client.returncode == 0
        and service_exit_code == 0
        and probe_ok(probe, expect_success=native)
        and service_ok(service, native=native)
        and netem_ok
        and qlog_ok
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


def run_probe(
    *, root: Path, image: str, iterations: int, keep_temp: bool
) -> dict[str, Any]:
    run_count = max(1, iterations)
    temp_root = root / f".tmp_fleetrmw_quic_native_path_{os.getpid()}"
    certs = temp_root / "certs"
    certs.mkdir(parents=True, exist_ok=True)
    policy = temp_root / "admission-policy.json"
    policy.write_text(
        json.dumps(
            {
                "schema_version": "fleetrmw.quic_gateway_admission_policy.v1",
                "default_action": "deny",
                "rules": [
                    {
                        "domain_id": 42,
                        "topic": "/fleetqox/native_path",
                        "traffic_class": "control",
                        "max_accepted_frames": 1,
                        "allowed_publishers": ["mtls-publisher"],
                        "min_admission_score": 0.32,
                    }
                ],
            },
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    build_root = "/work/.tmp_fleetrmw_quic_native_path_build"
    install = "/work/.tmp_fleetrmw_quic_native_path_install"
    log_root = "/work/.tmp_fleetrmw_quic_native_path_log"
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
            certificate_command(certs, root),
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
    network = f"fleetrmw-native-path-net-{os.getpid()}"
    network_result = run(["docker", "network", "create", network])
    rows: list[dict[str, Any]] = []
    try:
        if (
            cert_result.returncode == 0
            and build.returncode == 0
            and network_result.returncode == 0
        ):
            for index in range(1, run_count + 1):
                baseline = run_service_case(
                    root=root,
                    image=image,
                    network=network,
                    install=install,
                    temp_root=temp_root,
                    index=index,
                    native=False,
                )
                native = run_service_case(
                    root=root,
                    image=image,
                    network=network,
                    install=install,
                    temp_root=temp_root,
                    index=index,
                    native=True,
                )
                rows.append(
                    {
                        "index": index,
                        "status": (
                            "ok"
                            if baseline["status"] == native["status"] == "ok"
                            else "failed"
                        ),
                        "baseline": baseline,
                        "native": native,
                    }
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

    successful = sum(row.get("status") == "ok" for row in rows)
    status = (
        "ok"
        if cert_result.returncode == 0
        and build.returncode == 0
        and network_result.returncode == 0
        and len(rows) == run_count
        and successful == run_count
        else "failed"
    )
    return {
        "schema_version": SCHEMA_VERSION,
        "status": status,
        "run_count": run_count,
        "successful_runs": successful,
        "failed_run_count": run_count - successful,
        "container_count_per_run": 4,
        "real_quic_v1_h3": True,
        "mutual_tls_client_authentication_required": True,
        "publisher_identity_binding_required": True,
        "external_observation_api_used": False,
        "native_quic_path_observation_claim": status == "ok",
        "native_rtt_admission_effect_claim": status == "ok",
        "baseline_contrast_claim": status == "ok",
        "aioquic_exact_version_pin_claim": status == "ok",
        "aioquic_private_path_observer_fingerprint_claim": status == "ok",
        "aioquic_public_path_metrics_api_claim": False,
        "jitter_measurement_kind": "quic_recovery_rtt_variance_proxy",
        "production_quic_backend_claim": False,
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
            "docker_quic_native_path_observation_probe_summary.json"
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
        print("fleetrmw-quic-native-path-observation-probe")
        print(f"  status: {summary['status']}")
        print(f"  successful_runs: {summary['successful_runs']}/{summary['run_count']}")
    return 0 if summary["status"] == "ok" else 1


if __name__ == "__main__":
    raise SystemExit(main())

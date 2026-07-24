#!/usr/bin/env python3
"""Validate stateful QUIC gateway mutual-TLS client authentication."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import shlex
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
SCHEMA_VERSION = "fleetrmw.docker_quic_mtls_probe.v1"
PROBE_SCHEMA_VERSION = "fleetrmw.quic_mtls_probe.v1"


def client_ok(
    row: dict[str, Any],
    *,
    expect_success: bool,
    certificate_configured: bool,
    expect_authorization_failure: bool = False,
) -> bool:
    return (
        row.get("schema_version") == PROBE_SCHEMA_VERSION
        and row.get("status") == "ok"
        and row.get("expected_success") is expect_success
        and row.get("expected_authorization_failure") is expect_authorization_failure
        and row.get("transport_configured") is True
        and row.get("client_certificate_configured") is certificate_configured
        and row.get("send_success") is expect_success
        and row.get("client_auth_fail_closed") is (
            not expect_success and not expect_authorization_failure
        )
        and row.get("authorization_fail_closed") is expect_authorization_failure
        and row.get("connections_created") == 1
        and row.get("handshakes_completed") == 1
        and row.get("streams_opened") == 1
        and row.get("frames_sent") == (1 if expect_success else 0)
        and row.get("frames_failed") == (0 if expect_success else 1)
        and row.get("mutual_tls_client_authentication_claim") is expect_success
        and row.get("tls_peer_verification_required") is True
        and row.get("subprocess_backed") is False
        and row.get("production_readiness") is False
        and (expect_success or bool(row.get("error")))
    )


def service_ok(row: dict[str, Any]) -> bool:
    metrics = row.get("metrics", {})
    transport = row.get("transport_metrics", {})
    return (
        row.get("schema_version") == SERVICE_SCHEMA_VERSION
        and row.get("status") == "stopped"
        and row.get("clean_teardown") is True
        and row.get("client_certificate_required") is True
        and row.get("publisher_identity_binding") is True
        and row.get("publisher_identity_source") == "uri_san"
        and row.get("client_crl_configured") is True
        and row.get("mtls_adapter", {}).get("adapter_mode")
        == "pinned_aioquic_0_9_25_private_server_client_auth"
        and row.get("mtls_adapter", {}).get("runtime_version") == "0.9.25"
        and row.get("mtls_adapter", {}).get("supported_version") == "0.9.25"
        and row.get("mtls_adapter", {}).get("exact_version_match") is True
        and row.get("mtls_adapter", {}).get("compatible") is True
        and row.get("mtls_adapter", {}).get("public_server_client_auth_api") is False
        and row.get("mtls_adapter", {}).get("production_supported") is False
        and metrics.get("requests_total") == 1
        and metrics.get("post_requests") == 1
        and metrics.get("get_requests") == 0
        and metrics.get("accepted_frames") == 1
        and metrics.get("duplicate_frames") == 0
        and metrics.get("invalid_frames") == 0
        and metrics.get("dequeued_frames") == 0
        and metrics.get("topic_count") == 1
        and metrics.get("consumer_count") == 0
        and metrics.get("retained_frames") == 1
        and transport.get("connections_created") == 5
        and transport.get("h3_sessions_negotiated") == 5
        and transport.get("client_certificates_accepted") == 2
        and transport.get("missing_client_certificates_rejected") == 1
        and transport.get("untrusted_client_certificates_rejected") == 1
        and transport.get("revoked_client_certificates_rejected") == 1
        and transport.get("publisher_identity_authorization_rejected") == 1
        and transport.get("mtls_private_adapter_installs") == 5
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
    expect_authorization_failure: bool = False,
    certificate: str = "",
    private_key: str = "",
) -> subprocess.CompletedProcess[str]:
    client_credentials = ""
    if certificate and private_key:
        client_credentials = (
            f"export FLEETQOX_RMW_QUIC_CLIENT_CERT_FILE=/work/"
            f"{(certs / certificate).relative_to(root)} && "
            f"export FLEETQOX_RMW_QUIC_CLIENT_KEY_FILE=/work/"
            f"{(certs / private_key).relative_to(root)} && "
        )
    uri = (
        "https://localhost:4497/fleetrmw/v1/frames?"
        "domain_id=42&topic=%2Ffleetqox%2Fmtls&consumer_id=mtls-probe"
    )
    command = (
        "source /opt/ros/jazzy/setup.bash && "
        f"source {install}/setup.bash && "
        "tc qdisc replace dev eth0 root netem delay 7ms 2ms loss 0.2% && "
        "tc qdisc show dev eth0 && "
        "export FLEETQOX_RMW_REMOTE_TRANSPORT=quic_gateway && "
        "export FLEETQOX_RMW_QUIC_BACKEND=inprocess && "
        "export FLEETQOX_RMW_QUIC_GATEWAY=fleetqox-mtls-gateway:4497 && "
        f"export FLEETQOX_RMW_QUIC_URI='{uri}' && "
        "export FLEETQOX_RMW_QUIC_SNI=localhost && "
        "export FLEETQOX_RMW_QUIC_TIMEOUT=8s && "
        f"export FLEETQOX_RMW_QUIC_CA_FILE=/work/{(certs / 'server-ca.crt').relative_to(root)} && "
        f"export FLEETQOX_RMW_QUIC_QLOG_DIR=/work/{qlogs.relative_to(root)} && "
        f"export FLEETQOX_RMW_QUIC_MTLS_EXPECT_SUCCESS={'1' if expect_success else '0'} && "
        f"export FLEETQOX_RMW_QUIC_MTLS_EXPECT_AUTHORIZATION_FAILURE="
        f"{'1' if expect_authorization_failure else '0'} && "
        + client_credentials
        + f"{install}/rmw_fleetqox_cpp/lib/rmw_fleetqox_cpp/fleetrmw_quic_mtls_probe"
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
    service_name = f"fleetrmw-mtls-service-{suffix}"
    case_root = temp_root / f"run-{index}"
    service_qlogs = case_root / "service-qlogs"
    valid_qlogs = case_root / "valid-qlogs"
    missing_qlogs = case_root / "missing-qlogs"
    untrusted_qlogs = case_root / "untrusted-qlogs"
    impersonator_qlogs = case_root / "impersonator-qlogs"
    revoked_qlogs = case_root / "revoked-qlogs"
    for directory in (
        service_qlogs,
        valid_qlogs,
        missing_qlogs,
        untrusted_qlogs,
        impersonator_qlogs,
        revoked_qlogs,
    ):
        directory.mkdir(parents=True, exist_ok=True)
    certs = temp_root / "certs"
    service_command = (
        "tc qdisc replace dev eth0 root netem delay 5ms 1ms loss 0.2% && "
        "tc qdisc show dev eth0 && "
        "exec python3 scripts/fleetrmw_quic_gateway_service.py "
        "--host 0.0.0.0 --port 4497 "
        f"--certificate /work/{(certs / 'server.crt').relative_to(root)} "
        f"--private-key /work/{(certs / 'server.key').relative_to(root)} "
        f"--client-ca /work/{(certs / 'client-ca.crt').relative_to(root)} "
        f"--client-crl /work/{(certs / 'client.crl.pem').relative_to(root)} "
        "--require-client-certificate "
        "--publisher-identity-uri-prefix spiffe://fleetqox/publishers/ "
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
    ready = service_start.returncode == 0 and wait_service_ready(service_name)
    empty = subprocess.CompletedProcess([], 1, "", "service_not_ready")
    valid = empty
    missing = empty
    untrusted = empty
    impersonator = empty
    revoked = empty
    service_exit_code = -1
    service_logs = ""
    try:
        if ready:
            valid = run_client(
                root=root,
                image=image,
                network=network,
                name=f"fleetrmw-mtls-valid-{suffix}",
                install=install,
                certs=certs,
                qlogs=valid_qlogs,
                expect_success=True,
                certificate="client.crt",
                private_key="client.key",
            )
            missing = run_client(
                root=root,
                image=image,
                network=network,
                name=f"fleetrmw-mtls-missing-{suffix}",
                install=install,
                certs=certs,
                qlogs=missing_qlogs,
                expect_success=False,
            )
            untrusted = run_client(
                root=root,
                image=image,
                network=network,
                name=f"fleetrmw-mtls-untrusted-{suffix}",
                install=install,
                certs=certs,
                qlogs=untrusted_qlogs,
                expect_success=False,
                certificate="untrusted-client.crt",
                private_key="untrusted-client.key",
            )
            impersonator = run_client(
                root=root,
                image=image,
                network=network,
                name=f"fleetrmw-mtls-impersonator-{suffix}",
                install=install,
                certs=certs,
                qlogs=impersonator_qlogs,
                expect_success=False,
                expect_authorization_failure=True,
                certificate="impersonator.crt",
                private_key="impersonator.key",
            )
            revoked = run_client(
                root=root,
                image=image,
                network=network,
                name=f"fleetrmw-mtls-revoked-{suffix}",
                install=install,
                certs=certs,
                qlogs=revoked_qlogs,
                expect_success=False,
                certificate="revoked-client.crt",
                private_key="revoked-client.key",
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

    def last_row(result: subprocess.CompletedProcess[str]) -> dict[str, Any]:
        rows = json_rows(result.stdout)
        return rows[-1] if rows else {}

    valid_row = last_row(valid)
    missing_row = last_row(missing)
    untrusted_row = last_row(untrusted)
    impersonator_row = last_row(impersonator)
    revoked_row = last_row(revoked)
    service_rows = json_rows(service_logs)
    service_row = service_rows[-1] if service_rows else {}
    qlog_groups = [
        list(service_qlogs.glob("*")),
        list(valid_qlogs.glob("*")),
        list(missing_qlogs.glob("*")),
        list(untrusted_qlogs.glob("*")),
        list(impersonator_qlogs.glob("*")),
        list(revoked_qlogs.glob("*")),
    ]
    all_qlogs = [path for group in qlog_groups for path in group]
    netem_ok = all(
        "qdisc netem" in output
        for output in (
            service_logs,
            valid.stdout,
            missing.stdout,
            untrusted.stdout,
            impersonator.stdout,
            revoked.stdout,
        )
    )
    qlog_ok = (
        all(len(group) >= 1 for group in qlog_groups)
        and all(path.is_file() and path.stat().st_size > 0 for path in all_qlogs)
    )
    ok = (
        ready
        and valid.returncode == 0
        and missing.returncode == 0
        and untrusted.returncode == 0
        and impersonator.returncode == 0
        and revoked.returncode == 0
        and service_exit_code == 0
        and client_ok(valid_row, expect_success=True, certificate_configured=True)
        and client_ok(missing_row, expect_success=False, certificate_configured=False)
        and client_ok(untrusted_row, expect_success=False, certificate_configured=True)
        and client_ok(
            impersonator_row,
            expect_success=False,
            certificate_configured=True,
            expect_authorization_failure=True,
        )
        and client_ok(revoked_row, expect_success=False, certificate_configured=True)
        and service_ok(service_row)
        and netem_ok
        and qlog_ok
    )
    return {
        "index": index,
        "status": "ok" if ok else "failed",
        "service_ready": ready,
        "valid_returncode": valid.returncode,
        "missing_returncode": missing.returncode,
        "untrusted_returncode": untrusted.returncode,
        "impersonator_returncode": impersonator.returncode,
        "revoked_returncode": revoked.returncode,
        "service_exit_code": service_exit_code,
        "valid_client": valid_row,
        "missing_certificate_client": missing_row,
        "untrusted_certificate_client": untrusted_row,
        "trusted_impersonator_client": impersonator_row,
        "revoked_certificate_client": revoked_row,
        "service": service_row,
        "service_qlog_file_count": len(qlog_groups[0]),
        "valid_qlog_file_count": len(qlog_groups[1]),
        "missing_qlog_file_count": len(qlog_groups[2]),
        "untrusted_qlog_file_count": len(qlog_groups[3]),
        "impersonator_qlog_file_count": len(qlog_groups[4]),
        "revoked_qlog_file_count": len(qlog_groups[5]),
        "qlog_total_bytes": sum(path.stat().st_size for path in all_qlogs),
        "netem_configured_all_containers": netem_ok,
        "valid_stdout": "" if ok else valid.stdout,
        "valid_stderr": "" if ok else valid.stderr,
        "missing_stdout": "" if ok else missing.stdout,
        "missing_stderr": "" if ok else missing.stderr,
        "untrusted_stdout": "" if ok else untrusted.stdout,
        "untrusted_stderr": "" if ok else untrusted.stderr,
        "impersonator_stdout": "" if ok else impersonator.stdout,
        "impersonator_stderr": "" if ok else impersonator.stderr,
        "revoked_stdout": "" if ok else revoked.stdout,
        "revoked_stderr": "" if ok else revoked.stderr,
        "service_logs": "" if ok else service_logs,
    }


def certificate_command(certs: Path, root: Path) -> str:
    prefix = f"/work/{certs.relative_to(root)}"
    crl_python = (
        "from cryptography import x509; "
        "from cryptography.hazmat.primitives import hashes,serialization; "
        "from datetime import datetime,timedelta; from pathlib import Path; "
        f"p=Path('{prefix}'); now=datetime.utcnow(); "
        "ca=x509.load_pem_x509_certificate((p/'client-ca.crt').read_bytes()); "
        "key=serialization.load_pem_private_key((p/'client-ca.key').read_bytes(),None); "
        "peer=x509.load_pem_x509_certificate((p/'revoked-client.crt').read_bytes()); "
        "entry=x509.RevokedCertificateBuilder().serial_number(peer.serial_number)."
        "revocation_date(now).build(); "
        "crl=x509.CertificateRevocationListBuilder().issuer_name(ca.subject)."
        "last_update(now).next_update(now+timedelta(days=1))."
        "add_revoked_certificate(entry).sign(key,hashes.SHA256()); "
        "(p/'client.crl.pem').write_bytes(crl.public_bytes(serialization.Encoding.PEM))"
    )
    return (
        "openssl req -x509 -newkey rsa:2048 -nodes "
        f"-keyout {prefix}/server-ca.key -out {prefix}/server-ca.crt "
        "-subj /CN=FleetQoX-mTLS-Server-CA "
        "-addext basicConstraints=critical,CA:TRUE "
        "-addext keyUsage=critical,keyCertSign,cRLSign -days 1 >/dev/null 2>&1 && "
        "openssl req -new -newkey rsa:2048 -nodes "
        f"-keyout {prefix}/server.key -out {prefix}/server.csr "
        "-subj /CN=localhost "
        "-addext subjectAltName=DNS:localhost,DNS:fleetqox-mtls-gateway "
        "-addext extendedKeyUsage=serverAuth >/dev/null 2>&1 && "
        f"openssl x509 -req -in {prefix}/server.csr -CA {prefix}/server-ca.crt "
        f"-CAkey {prefix}/server-ca.key -CAcreateserial -out {prefix}/server.crt "
        "-days 1 -copy_extensions copy >/dev/null 2>&1 && "
        "openssl req -x509 -newkey rsa:2048 -nodes "
        f"-keyout {prefix}/client-ca.key -out {prefix}/client-ca.crt "
        "-subj /CN=FleetQoX-mTLS-Client-CA "
        "-addext basicConstraints=critical,CA:TRUE "
        "-addext keyUsage=critical,keyCertSign,cRLSign -days 1 >/dev/null 2>&1 && "
        "openssl req -new -newkey rsa:2048 -nodes "
        f"-keyout {prefix}/client.key -out {prefix}/client.csr "
        "-subj /CN=mtls-publisher "
        "-addext extendedKeyUsage=clientAuth "
        "-addext subjectAltName=URI:spiffe://fleetqox/publishers/mtls-publisher "
        ">/dev/null 2>&1 && "
        f"openssl x509 -req -in {prefix}/client.csr -CA {prefix}/client-ca.crt "
        f"-CAkey {prefix}/client-ca.key -CAcreateserial -out {prefix}/client.crt "
        "-days 1 -copy_extensions copy >/dev/null 2>&1 && "
        "openssl req -new -newkey rsa:2048 -nodes "
        f"-keyout {prefix}/impersonator.key -out {prefix}/impersonator.csr "
        "-subj /CN=trusted-but-wrong-publisher "
        "-addext extendedKeyUsage=clientAuth "
        "-addext subjectAltName=URI:spiffe://fleetqox/publishers/trusted-but-wrong-publisher "
        ">/dev/null 2>&1 && "
        f"openssl x509 -req -in {prefix}/impersonator.csr "
        f"-CA {prefix}/client-ca.crt -CAkey {prefix}/client-ca.key "
        f"-CAcreateserial -out {prefix}/impersonator.crt "
        "-days 1 -copy_extensions copy >/dev/null 2>&1 && "
        "openssl req -new -newkey rsa:2048 -nodes "
        f"-keyout {prefix}/revoked-client.key -out {prefix}/revoked-client.csr "
        "-subj /CN=mtls-publisher "
        "-addext extendedKeyUsage=clientAuth "
        "-addext subjectAltName=URI:spiffe://fleetqox/publishers/mtls-publisher "
        ">/dev/null 2>&1 && "
        f"openssl x509 -req -in {prefix}/revoked-client.csr "
        f"-CA {prefix}/client-ca.crt -CAkey {prefix}/client-ca.key "
        f"-CAcreateserial -out {prefix}/revoked-client.crt "
        "-days 1 -copy_extensions copy >/dev/null 2>&1 && "
        "openssl req -x509 -newkey rsa:2048 -nodes "
        f"-keyout {prefix}/untrusted-ca.key -out {prefix}/untrusted-ca.crt "
        "-subj /CN=FleetQoX-Untrusted-Client-CA "
        "-addext basicConstraints=critical,CA:TRUE "
        "-addext keyUsage=critical,keyCertSign,cRLSign -days 1 >/dev/null 2>&1 && "
        "openssl req -new -newkey rsa:2048 -nodes "
        f"-keyout {prefix}/untrusted-client.key -out {prefix}/untrusted-client.csr "
        "-subj /CN=fleetqox-untrusted-client "
        "-addext extendedKeyUsage=clientAuth >/dev/null 2>&1 && "
        f"openssl x509 -req -in {prefix}/untrusted-client.csr "
        f"-CA {prefix}/untrusted-ca.crt -CAkey {prefix}/untrusted-ca.key "
        f"-CAcreateserial -out {prefix}/untrusted-client.crt "
        "-days 1 -copy_extensions copy >/dev/null 2>&1 && "
        f"python3 -c {shlex.quote(crl_python)}"
    )


def run_probe(
    *, root: Path, image: str, iterations: int, keep_temp: bool
) -> dict[str, Any]:
    run_count = max(1, iterations)
    temp_root = root / f".tmp_fleetrmw_quic_mtls_{os.getpid()}"
    certs = temp_root / "certs"
    certs.mkdir(parents=True, exist_ok=True)
    build_root = "/work/.tmp_fleetrmw_quic_mtls_build"
    install = "/work/.tmp_fleetrmw_quic_mtls_install"
    log_root = "/work/.tmp_fleetrmw_quic_mtls_log"
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
    network = f"fleetrmw-mtls-net-{os.getpid()}"
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
        "container_count_per_run": 6,
        "real_quic_v1_h3": True,
        "server_certificate_verification_required": True,
        "client_certificate_verification_required": True,
        "valid_client_certificate_accepted_claim": status == "ok",
        "missing_client_certificate_fail_closed_claim": status == "ok",
        "untrusted_client_certificate_fail_closed_claim": status == "ok",
        "mutual_tls_client_authentication_claim": status == "ok",
        "client_certificate_publisher_identity_binding_claim": status == "ok",
        "client_certificate_uri_san_publisher_identity_binding_claim": status == "ok",
        "trusted_certificate_publisher_impersonation_fail_closed_claim": status == "ok",
        "unauthorized_identity_state_isolation_claim": status == "ok",
        "revoked_client_certificate_fail_closed_claim": status == "ok",
        "aioquic_exact_version_pin_claim": status == "ok",
        "aioquic_private_hook_fingerprint_claim": status == "ok",
        "aioquic_private_adapter_fail_closed_claim": status == "ok",
        "aioquic_public_server_client_auth_api_claim": False,
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
        default="results_rmw_socket/docker_quic_mtls_probe_summary.json",
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
        print("fleetrmw-quic-mtls-probe")
        print(f"  status: {summary['status']}")
        print(f"  successful_runs: {summary['successful_runs']}/{summary['run_count']}")
    return 0 if summary["status"] == "ok" else 1


if __name__ == "__main__":
    raise SystemExit(main())

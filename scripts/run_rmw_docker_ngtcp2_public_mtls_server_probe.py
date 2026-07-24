#!/usr/bin/env python3
"""Exercise the public-API ngtcp2/GnuTLS mutual-TLS server under netem."""

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


SCHEMA_VERSION = "fleetrmw.docker_ngtcp2_public_mtls_server.v1"
DEFAULT_IMAGE = "localhost/fleetrmw/ngtcp2-public-mtls:0.12.1"
DEFAULT_BASE_IMAGE = "localhost/fleetrmw/rmw-netem:jazzy"
REQUIRED_URI_SAN = "spiffe://fleetqox/publishers/mtls-publisher"


def run(
    command: list[str],
    *,
    timeout: float = 180.0,
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


def docker_rm(name: str) -> None:
    run(["docker", "rm", "-f", name], timeout=20.0)


def docker_network_rm(name: str) -> None:
    run(["docker", "network", "rm", name], timeout=20.0)


def wait_for_server(name: str, timeout: float = 10.0) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        inspect = run(
            ["docker", "inspect", "-f", "{{.State.Running}}", name],
            timeout=10.0,
        )
        if inspect.returncode == 0 and inspect.stdout.strip() == "true":
            time.sleep(0.25)
            return True
        time.sleep(0.1)
    return False


def client_command(
    *,
    cert_root: str,
    qlog_file: str,
    key_name: str | None,
    cert_name: str | None,
    streams: int,
) -> str:
    credentials = ""
    if key_name is not None and cert_name is not None:
        credentials = (
            f"--key={shlex.quote(cert_root + '/' + key_name)} "
            f"--cert={shlex.quote(cert_root + '/' + cert_name)} "
        )
    return (
        "cp "
        f"{shlex.quote(cert_root + '/server-ca.crt')} "
        "/usr/local/share/ca-certificates/fleetqox-public-server-ca.crt && "
        "update-ca-certificates >/dev/null 2>&1 && "
        "tc qdisc add dev eth0 root netem delay 9ms 2ms loss 0.2% && "
        "gtlsclient "
        f"{credentials}"
        "--disable-early-data --no-quic-dump --no-http-dump "
        f"--qlog-file={shlex.quote(qlog_file)} "
        f"--nstreams={streams} --exit-on-all-streams-close "
        "fleetqox-public-server 4433 "
        "https://fleetqox-public-server:4433/index.html"
    )


def run_client(
    *,
    root: Path,
    image: str,
    network: str,
    name: str,
    certs: Path,
    qlog: Path,
    key_name: str | None,
    cert_name: str | None,
    streams: int,
) -> subprocess.CompletedProcess[str]:
    cert_root = f"/work/{certs.relative_to(root)}"
    qlog_file = f"/work/{qlog.relative_to(root)}"
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
            client_command(
                cert_root=cert_root,
                qlog_file=qlog_file,
                key_name=key_name,
                cert_name=cert_name,
                streams=streams,
            ),
        ],
        timeout=60.0,
    )


def negative_client_was_rejected(
    completed: subprocess.CompletedProcess[str] | None,
) -> bool:
    """Recognize a QUIC/TLS rejection independent of the example client's exit code.

    ngtcp2 v0.12.1's gtlsclient exits zero after a peer CONNECTION_CLOSE, including
    a TLS-alert CRYPTO_ERROR.  The protocol trace is therefore the authoritative
    signal: a rejected client sees the close but never receives HTTP response
    headers.
    """
    if completed is None:
        return False
    trace = completed.stderr
    return (
        "CONNECTION_CLOSE" in trace
        and "CRYPTO_ERROR" in trace
        and "response headers started" not in trace
        and "[:status: 200]" not in trace
    )


def run_iteration(
    *,
    root: Path,
    image: str,
    index: int,
    temp_root: Path,
) -> dict[str, Any]:
    suffix = f"{os.getpid()}-{index}"
    network = f"fq-public-mtls-net-{suffix}"
    server_name = f"fq-public-mtls-server-{suffix}"
    certs = temp_root / "certs"
    htdocs = temp_root / f"htdocs-{index}"
    qlogs = temp_root / f"qlogs-{index}"
    server_qlogs = qlogs / "server"
    htdocs.mkdir(parents=True, exist_ok=True)
    server_qlogs.mkdir(parents=True, exist_ok=True)
    (htdocs / "index.html").write_text(
        "fleetqox public api mtls server\n", encoding="utf-8"
    )

    network_result = run(["docker", "network", "create", network], timeout=20.0)
    if network_result.returncode != 0:
        return {
            "index": index,
            "status": "failed",
            "reason": "network_create_failed",
            "stderr": network_result.stderr,
        }

    cert_root = f"/work/{certs.relative_to(root)}"
    htdocs_root = f"/work/{htdocs.relative_to(root)}"
    server_qlog_root = f"/work/{server_qlogs.relative_to(root)}"
    server_command = (
        "tc qdisc add dev eth0 root netem delay 11ms 2ms loss 0.2% && "
        "exec fleetqox-public-mtls-server "
        f"--htdocs={shlex.quote(htdocs_root)} "
        f"--qlog-dir={shlex.quote(server_qlog_root)} "
        "--verify-client "
        "--no-quic-dump --no-http-dump "
        f"'*' 4433 {shlex.quote(cert_root + '/server.key')} "
        f"{shlex.quote(cert_root + '/server.crt')}"
    )
    server = run(
        [
            "docker",
            "run",
            "-d",
            "--name",
            server_name,
            "--network",
            network,
            "--network-alias",
            "fleetqox-public-server",
            "--cap-add",
            "NET_ADMIN",
            "--entrypoint",
            "bash",
            "-e",
            f"FLEETQOX_GNUTLS_CLIENT_CA={cert_root}/client-ca.crt",
            "-e",
            f"FLEETQOX_GNUTLS_CLIENT_CRL={cert_root}/client.crl.pem",
            "-e",
            f"FLEETQOX_GNUTLS_REQUIRED_CLIENT_URI_SAN={REQUIRED_URI_SAN}",
            "-v",
            f"{root}:/work",
            "-w",
            "/work",
            image,
            "-lc",
            server_command,
        ],
        timeout=20.0,
    )

    try:
        ready = server.returncode == 0 and wait_for_server(server_name)
        clients: dict[str, subprocess.CompletedProcess[str]] = {}
        cases = (
            ("valid", "client.key", "client.crt", 6),
            ("missing", None, None, 1),
            ("untrusted", "untrusted-client.key", "untrusted-client.crt", 1),
            ("wrong_uri", "impersonator.key", "impersonator.crt", 1),
            ("revoked", "revoked-client.key", "revoked-client.crt", 1),
        )
        if ready:
            for label, key_name, cert_name, streams in cases:
                clients[label] = run_client(
                    root=root,
                    image=image,
                    network=network,
                    name=f"fq-public-mtls-{label}-{suffix}",
                    certs=certs,
                    qlog=qlogs / f"{label}.qlog",
                    key_name=key_name,
                    cert_name=cert_name,
                    streams=streams,
                )
        logs = run(["docker", "logs", server_name], timeout=20.0)
        qlog_files = sorted(server_qlogs.glob("*"))
        valid_qlog = qlogs / "valid.qlog"
        valid = clients.get("valid")
        server_logs = logs.stdout + logs.stderr
        verified_count = server_logs.count("FLEETQOX_PUBLIC_MTLS_VERIFIED")
        uri_reject_count = server_logs.count("reason=uri_san_mismatch")
        certificate_reject_count = server_logs.count(
            "FLEETQOX_PUBLIC_MTLS_REJECT verify_result="
        )
        valid_submit_count = (
            0
            if valid is None
            else valid.stderr.count("submit request headers")
        )
        valid_response_count = (
            0 if valid is None else valid.stderr.count("[:status: 200]")
        )
        negative_rejections = {
            label: negative_client_was_rejected(clients.get(label))
            for label in ("missing", "untrusted", "wrong_uri", "revoked")
        }
        positive_ok = (
            valid is not None
            and valid.returncode == 0
            and valid_submit_count == 6
            and valid_response_count == 6
            and valid_qlog.is_file()
            and valid_qlog.stat().st_size > 0
            and len(qlog_files) >= 1
            and all(path.stat().st_size > 0 for path in qlog_files)
        )
        negative_ok = all(negative_rejections.values())
        log_evidence_ok = (
            verified_count == 1
            and uri_reject_count >= 1
            and certificate_reject_count >= 2
        )
        ok = ready and positive_ok and negative_ok and log_evidence_ok
        return {
            "index": index,
            "status": "ok" if ok else "failed",
            "server_ready": ready,
            "valid_returncode": None if valid is None else valid.returncode,
            "missing_returncode": None
            if clients.get("missing") is None
            else clients["missing"].returncode,
            "untrusted_returncode": None
            if clients.get("untrusted") is None
            else clients["untrusted"].returncode,
            "wrong_uri_returncode": None
            if clients.get("wrong_uri") is None
            else clients["wrong_uri"].returncode,
            "revoked_returncode": None
            if clients.get("revoked") is None
            else clients["revoked"].returncode,
            "valid_stream_count": valid_response_count,
            "valid_submit_request_count": valid_submit_count,
            "valid_response_200_count": valid_response_count,
            "negative_protocol_rejections": negative_rejections,
            "verified_client_count": verified_count,
            "uri_san_rejection_count": uri_reject_count,
            "certificate_rejection_count": certificate_reject_count,
            "server_qlog_file_count": len(qlog_files),
            "client_qlog_bytes": valid_qlog.stat().st_size
            if valid_qlog.is_file()
            else 0,
            "server_qlog_bytes": sum(path.stat().st_size for path in qlog_files),
            "netem_client": "delay 9ms 2ms loss 0.2%",
            "netem_server": "delay 11ms 2ms loss 0.2%",
            "public_gnutls_api_verification": True,
            "private_aioquic_hook_used": False,
            "valid_stderr": "" if ok or valid is None else valid.stderr,
            "negative_stderr": {}
            if ok
            else {
                label: completed.stderr
                for label, completed in clients.items()
                if label != "valid"
            },
            "server_logs": "" if ok else server_logs,
        }
    finally:
        docker_rm(server_name)
        docker_network_rm(network)


def run_probe(
    *,
    root: Path,
    image: str,
    base_image: str,
    iterations: int,
    keep_temp: bool,
    skip_build: bool,
) -> dict[str, Any]:
    dockerfile = root / "external/ngtcp2-public-mtls/Dockerfile"
    build = subprocess.CompletedProcess([], 0, "", "")
    if not skip_build:
        build = run(
            [
                "docker",
                "build",
                "--build-arg",
                f"BASE_IMAGE={base_image}",
                "-f",
                str(dockerfile),
                "-t",
                image,
                ".",
            ],
            timeout=600.0,
        )
    temp_root = root / f".tmp_fleetrmw_public_mtls_{os.getpid()}"
    certs = temp_root / "certs"
    certs.mkdir(parents=True, exist_ok=True)
    certificate_result = run(
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
            certificate_command(certs, root),
        ],
        timeout=120.0,
    )
    rows: list[dict[str, Any]] = []
    try:
        if build.returncode == 0 and certificate_result.returncode == 0:
            for index in range(max(1, iterations)):
                rows.append(
                    run_iteration(
                        root=root,
                        image=image,
                        index=index,
                        temp_root=temp_root,
                    )
                )
        ok_count = sum(row.get("status") == "ok" for row in rows)
        run_count = max(1, iterations)
        ok = (
            build.returncode == 0
            and certificate_result.returncode == 0
            and len(rows) == run_count
            and ok_count == run_count
        )
        return {
            "schema_version": SCHEMA_VERSION,
            "status": "ok" if ok else "failed",
            "image": image,
            "base_image": base_image,
            "ngtcp2_source_commit": "a4ba3f20d70d4a4d79674cee1093c55b4c1d78ed",
            "run_count": run_count,
            "ok_run_count": ok_count,
            "public_api_mtls_server_claim": ok,
            "public_api_client_ca_verification_claim": ok,
            "public_api_crl_revocation_claim": ok,
            "public_api_uri_san_binding_claim": ok,
            "single_connection_six_h3_streams_claim": ok,
            "docker_netem_both_ends_claim": ok,
            "aioquic_private_server_hook_required": False,
            "stateful_gateway_backend_integrated": False,
            "production_quic_backend_claim": False,
            "runs": rows,
            "build_returncode": build.returncode,
            "certificate_returncode": certificate_result.returncode,
            "build_stderr": "" if build.returncode == 0 else build.stderr,
            "certificate_stderr": ""
            if certificate_result.returncode == 0
            else certificate_result.stderr,
        }
    finally:
        if not keep_temp:
            shutil.rmtree(temp_root, ignore_errors=True)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--image", default=DEFAULT_IMAGE)
    parser.add_argument("--base-image", default=DEFAULT_BASE_IMAGE)
    parser.add_argument("--iterations", type=int, default=1)
    parser.add_argument("--skip-build", action="store_true")
    parser.add_argument("--keep-temp", action="store_true")
    parser.add_argument(
        "--summary-json",
        default="results_rmw_socket/docker_ngtcp2_public_mtls_server_summary.json",
    )
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    summary = run_probe(
        root=ROOT,
        image=args.image,
        base_image=args.base_image,
        iterations=args.iterations,
        keep_temp=args.keep_temp,
        skip_build=args.skip_build,
    )
    output = ROOT / args.summary_json
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    if args.json:
        print(json.dumps(summary, sort_keys=True))
    else:
        print(f"status={summary['status']}")
    return 0 if summary["status"] == "ok" else 1


if __name__ == "__main__":
    raise SystemExit(main())

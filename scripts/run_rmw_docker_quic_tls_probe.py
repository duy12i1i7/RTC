"""Verify a real ngtcp2/GnuTLS QUIC/TLS handshake and payload transfer in Docker.

This runner is deliberately scoped to a transport dependency/data-plane proof.
It must not be counted as an integrated rmw_fleetqox_cpp QUIC backend: the RMW
still uses UDP/SHM for application delivery until a native QUIC path is wired
into the publisher/subscription transport.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import subprocess
import sys
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.run_rmw_docker_shared_memory_probe import parse_last_json


SCHEMA_VERSION = "fleetrmw.docker_quic_tls_probe.v1"
DEFAULT_IMAGE = "localhost/fleetrmw/rmw-netem:jazzy"


def container_probe_script(*, payload_size: int, port: int) -> str:
    return f"""
python3 - <<'PY'
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import tempfile
import time

schema_version = {SCHEMA_VERSION!r}
payload_size = {payload_size}
port = {port}

def excerpt(text: str, limit: int = 4000) -> str:
    if len(text) <= limit:
        return text
    return text[: limit // 2] + "\\n...<truncated>...\\n" + text[-limit // 2 :]

def finish(summary: dict, rc: int = 0) -> None:
    print(json.dumps(summary, sort_keys=True))
    raise SystemExit(rc)

gtlsclient = shutil.which("gtlsclient") or "/usr/bin/gtlsclient"
gtlsserver = shutil.which("gtlsserver") or "/usr/sbin/gtlsserver"
missing = [
    binary for binary in (gtlsclient, gtlsserver, "openssl")
    if shutil.which(binary) is None and not Path(binary).exists()
]
if missing:
    finish({{
        "schema_version": schema_version,
        "status": "failed",
        "stage": "dependency_check",
        "missing": missing,
        "rmw_integrated_backend": False,
    }}, 1)

with tempfile.TemporaryDirectory(prefix="fleetrmw-quic-") as tmp_text:
    tmp = Path(tmp_text)
    htdocs = tmp / "htdocs"
    download = tmp / "download"
    qlogs = tmp / "qlogs"
    htdocs.mkdir()
    download.mkdir()
    qlogs.mkdir()
    key = tmp / "server.key"
    cert = tmp / "server.crt"
    payload = (b"fleetqox-real-quic-tls-" * ((payload_size // 23) + 2))[:payload_size]
    source_file = htdocs / "fleetqox.bin"
    source_file.write_bytes(payload)
    expected_sha256 = hashlib.sha256(payload).hexdigest()

    cert_proc = subprocess.run(
        [
            "openssl", "req", "-x509", "-newkey", "rsa:2048", "-nodes",
            "-keyout", str(key), "-out", str(cert), "-subj", "/CN=localhost",
            "-days", "1",
        ],
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    if cert_proc.returncode != 0:
        finish({{
            "schema_version": schema_version,
            "status": "failed",
            "stage": "certificate_generation",
            "stdout": cert_proc.stdout,
            "stderr": cert_proc.stderr,
            "rmw_integrated_backend": False,
        }}, 1)

    server_log = tmp / "server.log"
    client_log = tmp / "client.log"
    server_cmd = [
        gtlsserver,
        "127.0.0.1",
        str(port),
        str(key),
        str(cert),
        "-d",
        str(htdocs),
        "--qlog-dir",
        str(qlogs),
        "--timeout=10s",
        "--handshake-timeout=5s",
        "--no-quic-dump",
        "--no-http-dump",
    ]
    with server_log.open("w", encoding="utf-8") as server_out:
        server = subprocess.Popen(
            server_cmd,
            stdout=server_out,
            stderr=subprocess.STDOUT,
            text=True,
        )

    try:
        time.sleep(0.75)
        if server.poll() is not None:
            finish({{
                "schema_version": schema_version,
                "status": "failed",
                "stage": "server_start",
                "server_returncode": server.returncode,
                "server_log": excerpt(server_log.read_text(errors="replace")),
                "rmw_integrated_backend": False,
            }}, 1)

        client_cmd = [
            gtlsclient,
            "127.0.0.1",
            str(port),
            f"https://localhost:{{port}}/fleetqox.bin",
            "--download",
            str(download),
            "--exit-on-all-streams-close",
            "--timeout=5s",
            "--sni=localhost",
            "--no-quic-dump",
            "--no-http-dump",
        ]
        with client_log.open("w", encoding="utf-8") as client_out:
            client = subprocess.run(
                client_cmd,
                stdout=client_out,
                stderr=subprocess.STDOUT,
                text=True,
                check=False,
                timeout=20,
            )
    finally:
        if server.poll() is None:
            server.terminate()
            try:
                server.wait(timeout=2)
            except subprocess.TimeoutExpired:
                server.kill()
                server.wait(timeout=2)

    client_output = client_log.read_text(errors="replace")
    server_output = server_log.read_text(errors="replace")
    downloaded = download / "fleetqox.bin"
    downloaded_bytes = downloaded.read_bytes() if downloaded.exists() else b""
    downloaded_sha256 = hashlib.sha256(downloaded_bytes).hexdigest() if downloaded_bytes else ""
    qlog_files = sorted(qlogs.glob("*"))

    client_handshake = "QUIC handshake has completed" in client_output
    server_handshake = "QUIC handshake has completed" in server_output
    alpn_h3 = "Negotiated ALPN is h3" in client_output and "Negotiated ALPN is h3" in server_output
    tls_cipher = "Negotiated cipher suite is" in client_output and "Negotiated cipher suite is" in server_output
    quic_v1 = "version=0x00000001" in client_output and "version=0x00000001" in server_output
    payload_ok = len(downloaded_bytes) == payload_size and downloaded_sha256 == expected_sha256
    ok = (
        client.returncode == 0
        and client_handshake
        and server_handshake
        and alpn_h3
        and tls_cipher
        and quic_v1
        and payload_ok
        and len(qlog_files) >= 1
    )
    finish({{
        "schema_version": schema_version,
        "status": "ok" if ok else "failed",
        "transport": "ngtcp2_gtls_quic_tls_h3",
        "quic_version": "0x00000001",
        "alpn": "h3" if alpn_h3 else "",
        "tls_handshake_complete": client_handshake and server_handshake,
        "tls_cipher_observed": tls_cipher,
        "payload_size": payload_size,
        "downloaded_size": len(downloaded_bytes),
        "payload_sha256": expected_sha256,
        "downloaded_sha256": downloaded_sha256,
        "qlog_file_count": len(qlog_files),
        "qlog_total_bytes": sum(path.stat().st_size for path in qlog_files),
        "not_bare_udp_transport": True,
        "rmw_integrated_backend": False,
        "client_returncode": client.returncode,
        "server_returncode": server.returncode,
        "client_log_excerpt": excerpt(client_output),
        "server_log_excerpt": excerpt(server_output),
    }}, 0 if ok else 1)
PY
"""


def run_probe(*, root: Path, image: str, payload_size: int, port: int) -> dict[str, Any]:
    command = [
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
        container_probe_script(payload_size=payload_size, port=port),
    ]
    run = subprocess.run(
        command,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    parsed = parse_last_json(run.stdout)
    if not parsed:
        parsed = {
            "schema_version": SCHEMA_VERSION,
            "status": "failed",
            "stage": "parse_summary",
        }
    parsed.update(
        {
            "image": image,
            "docker_returncode": run.returncode,
            "docker_stderr": run.stderr,
        }
    )
    if run.returncode != 0 and parsed.get("status") == "ok":
        parsed["status"] = "failed"
        parsed["stage"] = "docker_returncode"
    return parsed


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--image", default=DEFAULT_IMAGE)
    parser.add_argument("--payload-size", type=int, default=65536)
    parser.add_argument("--port", type=int, default=4443)
    parser.add_argument(
        "--summary-json",
        default="results_rmw_socket/docker_quic_tls_probe_summary.json",
    )
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    summary = run_probe(
        root=root,
        image=args.image,
        payload_size=max(args.payload_size, 1),
        port=args.port,
    )
    output = root / args.summary_json
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    if args.json:
        print(json.dumps(summary, sort_keys=True))
    else:
        print(f"status={summary['status']} payload_size={summary.get('payload_size')}")
    return 0 if summary["status"] == "ok" else 1


if __name__ == "__main__":
    raise SystemExit(main())

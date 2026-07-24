#!/usr/bin/env python3
"""Contrast fleet admission without/with public-ngtcp2 path telemetry."""

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

from fleetqox.quic_gateway_state import (
    ADMISSION_POLICY_SCHEMA_VERSION,
    DATA_FRAME_MAGIC,
)
from scripts.run_rmw_docker_ngtcp2_public_stateful_gateway_probe import (
    BACKEND_SCHEMA_VERSION,
    DEFAULT_BASE_IMAGE,
    DEFAULT_SERVER_IMAGE,
    PUBLISHER_ID,
    PUBLISHER_URI,
    run,
    stateful_certificate_command,
)


SCHEMA_VERSION = "fleetrmw.docker_ngtcp2_public_path_admission.v1"
TOPIC = "/fleetqox/gateway"
REQUEST_PATH = (
    "/fleetrmw/v1/frames?"
    "domain_id=42&topic=%2Ffleetqox%2Fgateway&consumer_id=path-admission"
)


def frame(sequence: int) -> bytes:
    payload = f"public-path-{sequence}".encode()
    document = {
        "schema_version": "fleetrmw.data_frame.v1",
        "kind": "sidecar_packet_frame",
        "domain_id": 42,
        "route": {"robot_id": "robot-path", "topic": TOPIC},
        "sample_envelope": {
            "robot_id": "robot-path",
            "topic": TOPIC,
            "publisher_id": PUBLISHER_ID,
            "source_sequence_number": sequence,
            "source_timestamp_ns": sequence * 1000,
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


def admission_policy() -> dict[str, Any]:
    return {
        "schema_version": ADMISSION_POLICY_SCHEMA_VERSION,
        "default_action": "deny",
        "observation_ttl_ms": 5000,
        "rules": [
            {
                "domain_id": 42,
                "topic": TOPIC,
                "traffic_class": "control",
                "max_accepted_frames": 4,
                "allowed_publishers": [PUBLISHER_ID],
                "min_admission_score": 0.0001,
            }
        ],
    }


def wait_ready(container: str, timeout_s: float = 10.0) -> bool:
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        logs = run(["docker", "logs", container], timeout=10.0)
        combined = logs.stdout + logs.stderr
        if (
            logs.returncode == 0
            and BACKEND_SCHEMA_VERSION in combined
            and '"status": "ready"' in combined
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
    waited = run(["docker", "wait", container], timeout=20.0)
    logs = run(["docker", "logs", container], timeout=20.0)
    exit_code = (
        int(waited.stdout.strip())
        if waited.returncode == 0 and waited.stdout.strip().isdigit()
        else -1
    )
    return exit_code if stop.returncode == 0 else -1, logs.stdout + logs.stderr


def backend_phase_ok(
    summary: dict[str, Any],
    *,
    enabled: bool,
) -> bool:
    metrics = summary.get("metrics", {})
    state = metrics.get("state", {}) if isinstance(metrics, dict) else {}
    admission = state.get("admission", {}) if isinstance(state, dict) else {}
    expected_status = 1 if enabled else 0
    expected_source = {"ngtcp2_public_api": 1} if enabled else {}
    expected_rejections = {} if enabled else {"qox_score_below_threshold": 1}
    expected_requests = 2 if enabled else 1
    return (
        summary.get("schema_version") == BACKEND_SCHEMA_VERSION
        and summary.get("status") == "stopped"
        and summary.get("clean_teardown") is True
        and metrics.get("accept_public_path_observations") is enabled
        and metrics.get("identity_rejections") == 0
        and metrics.get("protocol_rejections") == 0
        and metrics.get("public_path_telemetry_requests") == 1
        and metrics.get("public_path_observation_updates") == expected_status
        and metrics.get("public_path_missing_rtt_samples") == 0
        and metrics.get("public_path_loss_semantics")
        == "raw_ngtcp2_stream_packet_loss_count_not_loss_ratio"
        and metrics.get("public_path_rttvar_semantics")
        == "ngtcp2_rttvar_mean_deviation_used_as_jitter_proxy"
        and metrics.get("last_public_path_telemetry", {}).get(
            "rtt_initialized"
        )
        is True
        and metrics.get("last_public_path_telemetry", {}).get(
            "smoothed_rtt_us", 0
        )
        > 0
        and state.get("accepted_frames") == expected_status
        and state.get("requests_total") == expected_requests
        and state.get("post_requests") == 1
        and state.get("get_requests") == expected_status
        and state.get("dequeued_frames") == expected_status
        and state.get("retained_frames") == expected_status
        and state.get("observation_requests") == 0
        and admission.get("observation_updates") == expected_status
        and admission.get("observation_updates_by_source") == expected_source
        and admission.get("observation_score_uses") == expected_status
        and admission.get("rejected_by_reason") == expected_rejections
    )


def run_phase(
    *,
    root: Path,
    server_image: str,
    network: str,
    temp_root: Path,
    certs: Path,
    index: int,
    enabled: bool,
) -> dict[str, Any]:
    phase = "native" if enabled else "baseline"
    suffix = f"{os.getpid()}-{index}-{phase}"
    server_name = f"fq-public-path-{suffix}"
    phase_root = temp_root / f"run-{index}" / phase
    htdocs = phase_root / "htdocs"
    server_qlogs = phase_root / "server-qlogs"
    client_qlogs = phase_root / "client-qlogs"
    backend_summary = phase_root / "backend-summary.json"
    policy_path = phase_root / "admission-policy.json"
    frame_path = phase_root / "frame.bin"
    for directory in (htdocs, server_qlogs, client_qlogs):
        directory.mkdir(parents=True, exist_ok=True)
    (htdocs / "index.html").write_text("public path admission\n", encoding="utf-8")
    policy_path.write_text(
        json.dumps(admission_policy(), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    frame_path.write_bytes(frame(index + 1))

    cert_root = f"/work/{certs.relative_to(root)}"
    htdocs_root = f"/work/{htdocs.relative_to(root)}"
    server_qlog_root = f"/work/{server_qlogs.relative_to(root)}"
    backend_summary_path = f"/work/{backend_summary.relative_to(root)}"
    policy_container_path = f"/work/{policy_path.relative_to(root)}"
    backend_socket = "/tmp/fleetqox-path-admission-backend.sock"
    observation_flag = " --accept-public-path-observations" if enabled else ""
    server_command = (
        "set -euo pipefail; "
        f"rm -f {backend_socket} {shlex.quote(backend_summary_path)}; "
        "python3 -m fleetqox.public_quic_gateway_backend "
        f"--socket {backend_socket} --max-frames-per-topic 8 "
        "--max-frame-bytes 65536 "
        f"--admission-policy {shlex.quote(policy_container_path)}"
        f"{observation_flag} "
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
    started = run(
        [
            "docker",
            "run",
            "-d",
            "--name",
            server_name,
            "--network",
            network,
            "--network-alias",
            "fleetqox-path-gateway",
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
    ready = started.returncode == 0 and wait_ready(server_name)
    post = subprocess.CompletedProcess([], 1, "", "server_not_ready")
    take = subprocess.CompletedProcess([], 1, "", "not_run")
    server_exit = -1
    server_logs = ""
    try:
        if ready:
            common = (
                f"cp {cert_root}/server-ca.crt "
                "/usr/local/share/ca-certificates/fleetqox-public-ca.crt && "
                "update-ca-certificates >/dev/null 2>&1 && "
                "tc qdisc replace dev eth0 root netem delay 9ms 2ms loss 0.2% && "
            )
            post_command = (
                common
                + "gtlsclient fleetqox-path-gateway 4433 "
                f"'https://fleetqox-path-gateway:4433{REQUEST_PATH}' "
                "--http-method=POST "
                f"--data /work/{frame_path.relative_to(root)} "
                f"--key={cert_root}/stateful-client.key "
                f"--cert={cert_root}/stateful-client.crt "
                "--disable-early-data --exit-on-all-streams-close "
                "--no-quic-dump --no-http-dump "
                f"--qlog-file=/work/{(client_qlogs / 'post.qlog').relative_to(root)}"
            )
            post = run(
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
                    post_command,
                ],
                timeout=60.0,
            )
            if enabled:
                take_command = (
                    common
                    + "gtlsclient fleetqox-path-gateway 4433 "
                    f"'https://fleetqox-path-gateway:4433{REQUEST_PATH}' "
                    f"--key={cert_root}/stateful-client.key "
                    f"--cert={cert_root}/stateful-client.crt "
                    "--disable-early-data --exit-on-all-streams-close "
                    "--no-quic-dump --no-http-dump "
                    f"--qlog-file=/work/{(client_qlogs / 'take.qlog').relative_to(root)}"
                )
                take = run(
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
                        take_command,
                    ],
                    timeout=60.0,
                )
        if ready:
            server_exit, server_logs = stop_server(server_name)
    finally:
        run(["docker", "rm", "-f", server_name], timeout=20.0)

    backend = (
        json.loads(backend_summary.read_text(encoding="utf-8"))
        if backend_summary.exists()
        else {}
    )
    expected_status = 200 if enabled else 429
    post_status_ok = f"[:status: {expected_status}]" in post.stderr
    take_ok = (
        not enabled
        or (
            take.returncode == 0
            and "[:status: 200]" in take.stderr
            and "[content-type: application/vnd.fleetrmw.frame]" in take.stderr
        )
    )
    telemetry_log_count = server_logs.count("FLEETQOX_PUBLIC_PATH_TELEMETRY")
    ok = (
        ready
        and post.returncode == 0
        and post_status_ok
        and take_ok
        and server_exit == 0
        and backend_phase_ok(backend, enabled=enabled)
        and telemetry_log_count == (2 if enabled else 1)
    )
    return {
        "phase": phase,
        "status": "ok" if ok else "failed",
        "server_ready": ready,
        "post_returncode": post.returncode,
        "post_http_status": expected_status if post_status_ok else None,
        "take_returncode": take.returncode,
        "take_http_200_and_frame_content_type": take_ok if enabled else None,
        "server_exit_code": server_exit,
        "backend": backend,
        "public_path_telemetry_log_count": telemetry_log_count,
        "netem_server": "delay 11ms 2ms loss 0.2%",
        "netem_client": "delay 9ms 2ms loss 0.2%",
        "post_stderr": "" if ok else post.stderr,
        "take_stdout": "" if ok else take.stdout,
        "take_stderr": "" if ok else take.stderr,
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
    temp_root = root / f".tmp_fleetrmw_public_path_admission_{os.getpid()}"
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
    network = f"fq-public-path-admission-net-{os.getpid()}"
    network_result = run(["docker", "network", "create", network], timeout=20.0)
    rows: list[dict[str, Any]] = []
    try:
        if all(
            result.returncode == 0
            for result in (server_build, cert, network_result)
        ):
            for index in range(max(1, iterations)):
                phases = [
                    run_phase(
                        root=root,
                        server_image=server_image,
                        network=network,
                        temp_root=temp_root,
                        certs=certs,
                        index=index,
                        enabled=enabled,
                    )
                    for enabled in (False, True)
                ]
                rows.append(
                    {
                        "index": index,
                        "status": (
                            "ok"
                            if all(phase["status"] == "ok" for phase in phases)
                            else "failed"
                        ),
                        "phases": phases,
                    }
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
            for result in (server_build, cert, network_result)
        )
        and len(rows) == run_count
        and ok_count == run_count
    )
    return {
        "schema_version": SCHEMA_VERSION,
        "status": "ok" if ok else "failed",
        "run_count": run_count,
        "ok_run_count": ok_count,
        "public_ngtcp2_api_path_metrics_claim": ok,
        "public_path_metrics_admission_contrast_claim": ok,
        "external_observation_api_requests": 0,
        "raw_stream_loss_count_not_ratio_claim": ok,
        "docker_netem_both_ends_claim": ok,
        "aioquic_server_runtime_used": False,
        "aioquic_private_server_hook_required": False,
        "production_quic_backend_claim": False,
        "server_build_returncode": server_build.returncode,
        "certificate_returncode": cert.returncode,
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
            "docker_ngtcp2_public_path_admission_summary.json"
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
    output = Path(args.summary_json)
    if not output.is_absolute():
        output = ROOT / output
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

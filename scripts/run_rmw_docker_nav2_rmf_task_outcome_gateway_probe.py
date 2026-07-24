#!/usr/bin/env python3
"""Submit terminal Nav2/RMF workload outcomes to the authenticated QUIC gateway."""

from __future__ import annotations

import argparse
import hashlib
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
    from scripts.run_rmw_docker_router_nav2_rmf_action_workload import (
        task_outcomes_ok,
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
    from run_rmw_docker_router_nav2_rmf_action_workload import task_outcomes_ok


ROOT = Path(__file__).resolve().parents[1]
SCHEMA_VERSION = "fleetrmw.docker_nav2_rmf_task_outcome_gateway_probe.v1"
PROBE_SCHEMA_VERSION = "fleetrmw.quic_task_outcome_submit_probe.v1"
DEFAULT_SOURCE = (
    "results_rmw_socket/"
    "docker_router_nav2_rmf_action_workload_concurrency8_summary.json"
)


def probe_ok(row: dict[str, Any]) -> bool:
    return (
        row.get("schema_version") == PROBE_SCHEMA_VERSION
        and row.get("status") == "ok"
        and row.get("source_workload_outcome_count") == 3
        and row.get("seed_frames_sent") == 3
        and row.get("task_outcomes_submitted") == 3
        and row.get("connections_created") == 2
        and row.get("handshakes_completed") == 2
        and row.get("streams_opened") == 6
        and row.get("connection_reuse_count") == 4
        and row.get("task_outcome_gateway_submission_performed") is True
        and row.get("task_outcome_submission_session_reuse_claim") is True
        and row.get("mutual_tls_required") is True
        and row.get("subprocess_backed") is False
        and row.get("production_readiness") is False
    )


def service_ok(row: dict[str, Any]) -> bool:
    metrics = row.get("metrics", {})
    admission = metrics.get("admission", {})
    transport = row.get("transport_metrics", {})
    return (
        row.get("schema_version") == SERVICE_SCHEMA_VERSION
        and row.get("status") == "stopped"
        and row.get("clean_teardown") is True
        and row.get("client_certificate_required") is True
        and row.get("publisher_identity_binding") is True
        and row.get("publisher_identity_source") == "uri_san"
        and row.get("application_outcome_qoe_debt_configured") is True
        and metrics.get("requests_total") == 6
        and metrics.get("post_requests") == 3
        and metrics.get("get_requests") == 0
        and metrics.get("application_outcome_requests") == 3
        and metrics.get("application_outcome_updates") == 3
        and metrics.get("application_outcome_duplicates") == 0
        and metrics.get("application_outcome_unknown_frames") == 0
        and metrics.get("invalid_application_outcomes") == 0
        and metrics.get("application_task_outcome_updates") == 3
        and metrics.get("application_task_outcome_failures") == 1
        and metrics.get("accepted_frames") == 3
        and metrics.get("invalid_frames") == 0
        and metrics.get("retained_frames") == 3
        and metrics.get("application_outcome_key_count") == 3
        and admission.get("accepted_total") == 3
        and admission.get("application_outcome_qoe_debt_updates") == 3
        and admission.get("application_task_outcome_updates") == 3
        and admission.get("application_task_outcome_failures") == 1
        and admission.get("active_observation_count") == 1
        and admission.get("active_observations_by_source")
        == {"application_outcome": 1}
        and transport.get("connections_created") == 2
        and transport.get("h3_sessions_negotiated") == 2
        and transport.get("client_certificates_accepted") == 2
        and transport.get("publisher_identity_authorization_rejected") == 0
        and transport.get("application_outcome_identity_authorization_rejected") == 0
        and transport.get("malformed_h3_requests_rejected") == 0
        and transport.get("mtls_private_adapter_installs") == 2
    )


def policy_document() -> dict[str, Any]:
    return {
        "schema_version": "fleetrmw.quic_gateway_admission_policy.v1",
        "default_action": "deny",
        "application_outcome_qoe_debt": {"enabled": True, "ewma_alpha": 1.0},
        "rules": [{
            "domain_id": 42,
            "topic": "/fleetqox/nav2_rmf_tasks",
            "traffic_class": "control",
            "max_accepted_frames": 3,
            "allowed_publishers": ["nav2-rmf-workload-client"],
        }],
    }


def run_client(
    *, root: Path, image: str, network: str, name: str, install: str,
    certs: Path, qlogs: Path, outcome_file: Path,
) -> subprocess.CompletedProcess[str]:
    command = (
        "source /opt/ros/jazzy/setup.bash && "
        f"source {install}/setup.bash && "
        "tc qdisc replace dev eth0 root netem delay 9ms 2ms loss 0.2% && "
        "tc qdisc show dev eth0 && "
        "export FLEETQOX_RMW_REMOTE_TRANSPORT=quic_gateway && "
        "export FLEETQOX_RMW_QUIC_BACKEND=inprocess && "
        "export FLEETQOX_RMW_QUIC_GATEWAY=fleetqox-mtls-gateway:4511 && "
        "export FLEETQOX_RMW_QUIC_SNI=localhost && "
        "export FLEETQOX_RMW_QUIC_TIMEOUT=8s && "
        f"export FLEETQOX_RMW_QUIC_CA_FILE=/work/"
        f"{(certs / 'server-ca.crt').relative_to(root)} && "
        f"export FLEETQOX_RMW_QUIC_CLIENT_CERT_FILE=/work/"
        f"{(certs / 'client.crt').relative_to(root)} && "
        f"export FLEETQOX_RMW_QUIC_CLIENT_KEY_FILE=/work/"
        f"{(certs / 'client.key').relative_to(root)} && "
        f"export FLEETQOX_RMW_QUIC_QLOG_DIR=/work/{qlogs.relative_to(root)} && "
        f"export FLEETQOX_TASK_OUTCOME_NDJSON=/work/{outcome_file.relative_to(root)} && "
        f"{install}/rmw_fleetqox_cpp/lib/rmw_fleetqox_cpp/"
        "fleetrmw_quic_task_outcome_submit_probe"
    )
    return run([
        "docker", "run", "--rm", "--name", name,
        "--network", network, "--cap-add", "NET_ADMIN",
        "--entrypoint", "bash", "-v", f"{root}:/work", "-w", "/work",
        image, "-lc", command,
    ])


def run_case(
    *, root: Path, image: str, network: str, install: str,
    temp_root: Path, index: int,
) -> dict[str, Any]:
    suffix = f"{os.getpid()}-{index}"
    service_name = f"fleetrmw-task-outcome-service-{suffix}"
    case_root = temp_root / f"run-{index}"
    service_qlogs = case_root / "service-qlogs"
    client_qlogs = case_root / "client-qlogs"
    service_qlogs.mkdir(parents=True, exist_ok=True)
    client_qlogs.mkdir(parents=True, exist_ok=True)
    certs = temp_root / "certs"
    policy = temp_root / "admission-policy.json"
    outcome_file = temp_root / "task-outcomes.ndjson"
    service_command = (
        "tc qdisc replace dev eth0 root netem delay 11ms 2ms loss 0.2% && "
        "tc qdisc show dev eth0 && "
        "exec python3 scripts/fleetrmw_quic_gateway_service.py "
        "--host 0.0.0.0 --port 4511 "
        f"--certificate /work/{(certs / 'server.crt').relative_to(root)} "
        f"--private-key /work/{(certs / 'server.key').relative_to(root)} "
        f"--client-ca /work/{(certs / 'client-ca.crt').relative_to(root)} "
        f"--client-crl /work/{(certs / 'client.crl.pem').relative_to(root)} "
        "--require-client-certificate "
        "--publisher-identity-uri-prefix spiffe://fleetqox/publishers/ "
        f"--admission-policy /work/{policy.relative_to(root)} "
        f"--qlog-dir /work/{service_qlogs.relative_to(root)} "
        "--max-frames-per-topic 8 --max-frame-bytes 65536"
    )
    started = run([
        "docker", "run", "-d", "--name", service_name,
        "--network", network, "--network-alias", "fleetqox-mtls-gateway",
        "--cap-add", "NET_ADMIN", "--entrypoint", "bash",
        "-v", f"{root}:/work", "-w", "/work", image, "-lc", service_command,
    ])
    ready = started.returncode == 0 and wait_service_ready(service_name)
    client = subprocess.CompletedProcess([], 1, "", "service_not_ready")
    service_exit_code = -1
    service_logs = ""
    try:
        if ready:
            client = run_client(
                root=root, image=image, network=network,
                name=f"fleetrmw-task-outcome-client-{suffix}", install=install,
                certs=certs, qlogs=client_qlogs, outcome_file=outcome_file,
            )
        time.sleep(0.5)
        run(["docker", "stop", "--time", "3", service_name])
        inspected = run([
            "docker", "inspect", "-f", "{{.State.ExitCode}}", service_name
        ])
        if inspected.returncode == 0 and inspected.stdout.strip():
            service_exit_code = int(inspected.stdout.strip())
        service_logs = run(["docker", "logs", service_name]).stdout
    finally:
        run(["docker", "rm", "-f", service_name])

    probe_rows = json_rows(client.stdout)
    service_rows = json_rows(service_logs)
    probe = probe_rows[-1] if probe_rows else {}
    service = service_rows[-1] if service_rows else {}
    qlogs = [
        path
        for directory in (service_qlogs, client_qlogs)
        for path in directory.glob("*")
        if path.is_file()
    ]
    netem_ok = "qdisc netem" in service_logs and "qdisc netem" in client.stdout
    qlog_ok = bool(qlogs) and all(path.stat().st_size > 0 for path in qlogs)
    ok = (
        ready and client.returncode == 0 and service_exit_code == 0
        and probe_ok(probe) and service_ok(service) and netem_ok and qlog_ok
    )
    return {
        "index": index,
        "status": "ok" if ok else "failed",
        "probe": probe,
        "service": service,
        "netem_configured_both_containers": netem_ok,
        "qlog_file_count": len(qlogs),
        "qlog_total_bytes": sum(path.stat().st_size for path in qlogs),
        "client_returncode": client.returncode,
        "service_exit_code": service_exit_code,
        "client_stdout": "" if ok else client.stdout,
        "client_stderr": "" if ok else client.stderr,
        "service_logs": "" if ok else service_logs,
    }


def run_probe(
    *, root: Path, image: str, iterations: int, source_summary_path: Path,
    keep_temp: bool,
) -> dict[str, Any]:
    source_bytes = source_summary_path.read_bytes()
    source = json.loads(source_bytes)
    source_ok = source.get("status") == "ok" and task_outcomes_ok(
        source.get("client", {})
    )
    outcomes = source.get("client", {}).get("application_outcomes", [])
    run_count = max(1, iterations)
    temp_root = root / f".tmp_fleetrmw_nav2_rmf_task_outcome_{os.getpid()}"
    certs = temp_root / "certs"
    certs.mkdir(parents=True, exist_ok=True)
    (temp_root / "admission-policy.json").write_text(
        json.dumps(policy_document(), sort_keys=True) + "\n", encoding="utf-8"
    )
    (temp_root / "task-outcomes.ndjson").write_text(
        "".join(json.dumps(row, sort_keys=True) + "\n" for row in outcomes),
        encoding="utf-8",
    )
    build_root = "/work/.tmp_fleetrmw_nav2_rmf_task_outcome_build"
    install = "/work/.tmp_fleetrmw_nav2_rmf_task_outcome_install"
    log_root = "/work/.tmp_fleetrmw_nav2_rmf_task_outcome_log"
    cert_result = run([
        "docker", "run", "--rm", "--entrypoint", "bash",
        "-v", f"{root}:/work", "-w", "/work", image, "-lc",
        certificate_command(certs, root).replace(
            "mtls-publisher", "nav2-rmf-workload-client"
        ),
    ])
    build = run([
        "docker", "run", "--rm", "--entrypoint", "bash",
        "-v", f"{root}:/work", "-w", "/work", image, "-lc",
        "source /opt/ros/jazzy/setup.bash && "
        f"rm -rf {build_root} {install} {log_root} && "
        "export CMAKE_BUILD_PARALLEL_LEVEL=2 && "
        f"colcon --log-base {log_root} build --executor sequential "
        "--base-paths ros2_ws/src --packages-select rmw_fleetqox_cpp "
        f"--build-base {build_root} --install-base {install} "
        "--cmake-args -DCMAKE_BUILD_TYPE=Release",
    ])
    network = f"fleetrmw-task-outcome-net-{os.getpid()}"
    network_result = run(["docker", "network", "create", network])
    runs: list[dict[str, Any]] = []
    try:
        if (
            source_ok and cert_result.returncode == 0
            and build.returncode == 0 and network_result.returncode == 0
        ):
            for index in range(1, run_count + 1):
                runs.append(run_case(
                    root=root, image=image, network=network, install=install,
                    temp_root=temp_root, index=index,
                ))
    finally:
        run(["docker", "network", "rm", network])
        if not keep_temp:
            cleanup = run([
                "docker", "run", "--rm", "--entrypoint", "bash",
                "-v", f"{root}:/work", image, "-lc",
                f"rm -rf {build_root} {install} {log_root}",
            ])
            if cleanup.returncode == 0:
                shutil.rmtree(temp_root, ignore_errors=True)

    successful = sum(row.get("status") == "ok" for row in runs)
    status = "ok" if (
        source_ok and cert_result.returncode == build.returncode
        == network_result.returncode == 0
        and len(runs) == successful == run_count
    ) else "failed"
    return {
        "schema_version": SCHEMA_VERSION,
        "status": status,
        "run_count": run_count,
        "successful_runs": successful,
        "failed_run_count": run_count - successful,
        "source_workload_summary": str(source_summary_path.relative_to(root)),
        "source_workload_sha256": hashlib.sha256(source_bytes).hexdigest(),
        "source_workload_status": source.get("status"),
        "source_workload_task_outcome_mapping_valid": source_ok,
        "source_artifact_chained_submission": True,
        "same_process_live_ros_result_submission_claim": False,
        "nav2_rmf_task_outcome_gateway_submission_claim": status == "ok",
        "task_outcome_submission_session_reuse_claim": status == "ok",
        "mutual_tls_client_authentication_required": True,
        "publisher_identity_binding_required": True,
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
    parser.add_argument("--source-summary", default=DEFAULT_SOURCE)
    parser.add_argument(
        "--summary-json",
        default=(
            "results_rmw_socket/"
            "docker_nav2_rmf_task_outcome_gateway_probe_summary.json"
        ),
    )
    parser.add_argument("--keep-temp", action="store_true")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    summary = run_probe(
        root=ROOT,
        image=args.image,
        iterations=args.iterations,
        source_summary_path=ROOT / args.source_summary,
        keep_temp=args.keep_temp,
    )
    path = ROOT / args.summary_json
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n")
    if args.json:
        print(json.dumps(summary, sort_keys=True))
    else:
        print("fleetrmw-nav2-rmf-task-outcome-gateway-probe")
        print(f"  status: {summary['status']}")
        print(f"  successful_runs: {summary['successful_runs']}")
    return 0 if summary["status"] == "ok" else 1


if __name__ == "__main__":
    raise SystemExit(main())

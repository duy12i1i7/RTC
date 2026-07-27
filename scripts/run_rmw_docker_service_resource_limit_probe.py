"""Run the bounded FleetRMW service resource/backpressure probe in Docker."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.run_rmw_docker_router_service_call_probe import parse_last_json


SCHEMA_VERSION = "fleetrmw.rmw_docker_service_resource_limit_probe.v1"
DEFAULT_IMAGE = "localhost/fleetrmw/rmw-netem:jazzy"
NETEM_PROFILE = "delay 8ms 2ms"
RESOURCE_LIMIT = 4
REQUEST_COUNT = 10


def run_command(
    command: list[str], *, check: bool = True
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        command,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=check,
    )


def docker_shell(
    *,
    root: Path,
    image: str,
    command: str,
    net_admin: bool = False,
    check: bool = True,
) -> subprocess.CompletedProcess[str]:
    docker_command = [
        "docker",
        "run",
        "--rm",
        "--entrypoint",
        "bash",
    ]
    if net_admin:
        docker_command.extend(["--cap-add", "NET_ADMIN"])
    docker_command.extend(
        [
            "-v",
            f"{root}:/work",
            "-w",
            "/work",
            image,
            "-lc",
            command,
        ]
    )
    return run_command(docker_command, check=check)


def run_probe(*, root: Path, image: str, iterations: int) -> dict[str, Any]:
    suffix = f"{os.getpid()}"
    build_base = f"/work/.tmp_fleetrmw_service_resource_build_{suffix}"
    install_base = f"/work/.tmp_fleetrmw_service_resource_install_{suffix}"
    log_base = f"/work/.tmp_fleetrmw_service_resource_log_{suffix}"
    try:
        docker_shell(
            root=root,
            image=image,
            command=(
                "source /opt/ros/jazzy/setup.bash && "
                f"rm -rf {build_base} {install_base} {log_base} && "
                f"colcon --log-base {log_base} build --base-paths ros2_ws/src "
                "--packages-select rmw_fleetqox_cpp "
                f"--build-base {build_base} --install-base {install_base} "
                "--cmake-args -DCMAKE_BUILD_TYPE=Release"
            ),
        )
        runs = []
        for iteration in range(iterations):
            result = docker_shell(
                root=root,
                image=image,
                net_admin=True,
                check=False,
                command=(
                    "source /opt/ros/jazzy/setup.bash && "
                    f"source {install_base}/setup.bash && "
                    "export RMW_IMPLEMENTATION=rmw_fleetqox_cpp && "
                    "export FLEETQOX_RMW_TRACE_SERVICE=1 && "
                    f"export FLEETQOX_RMW_SERVICE_REQUEST_QUEUE_LIMIT={RESOURCE_LIMIT} && "
                    f"export FLEETQOX_RMW_SERVICE_RESPONSE_QUEUE_LIMIT={RESOURCE_LIMIT} && "
                    f"export FLEETQOX_RMW_SERVICE_PENDING_RESPONSE_LIMIT={RESOURCE_LIMIT} && "
                    f"export FLEETQOX_RMW_SERVICE_DEDUPE_HISTORY_LIMIT={RESOURCE_LIMIT} && "
                    f"export FLEETQOX_RMW_SERVICE_RESPONSE_REPLAY_LIMIT={RESOURCE_LIMIT} && "
                    f"tc qdisc replace dev lo root netem {NETEM_PROFILE} && "
                    f"{install_base}/rmw_fleetqox_cpp/lib/rmw_fleetqox_cpp/"
                    "fleetrmw_service_resource_limit_probe"
                ),
            )
            combined_logs = result.stdout + result.stderr
            probe = parse_last_json(combined_logs)
            resource_limit_trace_count = combined_logs.count(
                "event=request_queue_resource_limit"
            )
            duplicate_trace_count = combined_logs.count(
                "event=drop_duplicate_request"
            )
            ok = (
                result.returncode == 0
                and probe.get("status") == "ok"
                and int(probe.get("request_count", 0)) == REQUEST_COUNT
                and int(probe.get("unique_requests_taken", 0)) == REQUEST_COUNT
                and int(probe.get("unique_responses_taken", 0)) == REQUEST_COUNT
                and int(probe.get("request_queue_limit", 0)) == RESOURCE_LIMIT
                and int(probe.get("response_queue_limit", 0)) == RESOURCE_LIMIT
                and int(probe.get("dedupe_history_limit", 0)) == RESOURCE_LIMIT
                and int(probe.get("response_replay_limit", 0)) == RESOURCE_LIMIT
                and int(probe.get("request_queue_resource_drops", 0)) == 8
                and int(probe.get("response_queue_resource_drops", -1)) == 0
                and int(probe.get("request_dedupe_evictions", 0)) == 6
                and int(probe.get("response_dedupe_evictions", 0)) == 6
                and int(probe.get("response_replay_evictions", 0)) == 6
                and int(probe.get("request_queue_max_observed", 0)) == RESOURCE_LIMIT
                and int(probe.get("response_queue_max_observed", 0)) <= RESOURCE_LIMIT
                and int(probe.get("pending_response_max_observed", 0)) <= 1
                and int(probe.get("response_replay_max_observed", 0)) == RESOURCE_LIMIT
                and probe.get("duplicate_request_suppressed") is True
                and probe.get("resource_repair_exact_delivery") is True
                and probe.get("cleanup_ok") is True
                and resource_limit_trace_count == 8
                and duplicate_trace_count == 1
            )
            runs.append(
                {
                    "iteration": iteration,
                    "status": "ok" if ok else "failed",
                    "returncode": result.returncode,
                    "netem_applied": result.returncode == 0,
                    "netem_profile": NETEM_PROFILE,
                    "resource_limit_trace_count": resource_limit_trace_count,
                    "duplicate_trace_count": duplicate_trace_count,
                    "probe": probe,
                    "stdout": result.stdout,
                    "stderr": result.stderr,
                }
            )
        ok_run_count = sum(run["status"] == "ok" for run in runs)
        status = "ok" if ok_run_count == iterations else "failed"
        return {
            "schema_version": SCHEMA_VERSION,
            "status": status,
            "image": image,
            "run_count": iterations,
            "ok_run_count": ok_run_count,
            "request_count": REQUEST_COUNT,
            "request_queue_limit": RESOURCE_LIMIT,
            "response_queue_limit": RESOURCE_LIMIT,
            "dedupe_history_limit": RESOURCE_LIMIT,
            "response_replay_limit": RESOURCE_LIMIT,
            "request_queue_resource_drops": sum(
                int(run["probe"].get("request_queue_resource_drops", 0))
                for run in runs
            ),
            "unique_requests_taken": sum(
                int(run["probe"].get("unique_requests_taken", 0))
                for run in runs
            ),
            "unique_responses_taken": sum(
                int(run["probe"].get("unique_responses_taken", 0))
                for run in runs
            ),
            "netem_applied_all": all(run["netem_applied"] for run in runs),
            "bounded_service_queue_claim": status == "ok",
            "bounded_service_dedupe_history_claim": status == "ok",
            "bounded_service_response_replay_claim": status == "ok",
            "service_resource_backpressure_repair_claim": status == "ok",
            "full_exactly_once_service_semantics_claim": False,
            "runs": runs,
        }
    except subprocess.CalledProcessError as exc:
        return {
            "schema_version": SCHEMA_VERSION,
            "status": "failed",
            "image": image,
            "run_count": iterations,
            "ok_run_count": 0,
            "returncode": exc.returncode,
            "stdout": exc.stdout,
            "stderr": exc.stderr,
        }
    finally:
        docker_shell(
            root=root,
            image=image,
            command=f"rm -rf {build_base} {install_base} {log_base}",
            check=False,
        )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--image", default=DEFAULT_IMAGE)
    parser.add_argument("--iterations", type=int, default=5)
    parser.add_argument(
        "--summary-json",
        default=(
            "results_rmw_socket/"
            "docker_service_resource_limit_probe_summary.json"
        ),
    )
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    if args.iterations < 1:
        parser.error("--iterations must be positive")
    summary = run_probe(root=ROOT, image=args.image, iterations=args.iterations)
    output = ROOT / args.summary_json
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(summary, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(summary, sort_keys=True) if args.json else summary["status"])
    return 0 if summary["status"] == "ok" else 1


if __name__ == "__main__":
    raise SystemExit(main())

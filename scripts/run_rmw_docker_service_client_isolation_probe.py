"""Run FleetRMW noisy/quiet service-client isolation in Docker/netem."""

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


SCHEMA_VERSION = "fleetrmw.rmw_docker_service_client_isolation_probe.v1"
DEFAULT_IMAGE = "localhost/fleetrmw/rmw-netem:jazzy"
NETEM_PROFILE = "delay 8ms 2ms"
REQUEST_QUEUE_LIMIT = 4
PER_CLIENT_REQUEST_QUEUE_LIMIT = 2


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
    docker_command = ["docker", "run", "--rm", "--entrypoint", "bash"]
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
    suffix = str(os.getpid())
    build_base = f"/work/.tmp_fleetrmw_service_isolation_build_{suffix}"
    install_base = f"/work/.tmp_fleetrmw_service_isolation_install_{suffix}"
    log_base = f"/work/.tmp_fleetrmw_service_isolation_log_{suffix}"
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
                    "export FLEETQOX_RMW_SERVICE_REQUEST_QUEUE_LIMIT="
                    f"{REQUEST_QUEUE_LIMIT} && "
                    "export FLEETQOX_RMW_SERVICE_PER_CLIENT_REQUEST_QUEUE_LIMIT="
                    f"{PER_CLIENT_REQUEST_QUEUE_LIMIT} && "
                    "export FLEETQOX_RMW_SERVICE_RESPONSE_QUEUE_LIMIT=4 && "
                    "export FLEETQOX_RMW_SERVICE_PENDING_RESPONSE_LIMIT=16 && "
                    "export FLEETQOX_RMW_SERVICE_DEDUPE_HISTORY_LIMIT=16 && "
                    "export FLEETQOX_RMW_SERVICE_RESPONSE_REPLAY_LIMIT=16 && "
                    f"tc qdisc replace dev lo root netem {NETEM_PROFILE} && "
                    f"{install_base}/rmw_fleetqox_cpp/lib/rmw_fleetqox_cpp/"
                    "fleetrmw_service_client_isolation_probe"
                ),
            )
            logs = result.stdout + result.stderr
            probe = parse_last_json(logs)
            per_client_drop_traces = logs.count(
                "event=request_client_resource_limit"
            )
            ok = (
                result.returncode == 0
                and probe.get("status") == "ok"
                and int(probe.get("noisy_request_count", 0)) == 8
                and int(probe.get("quiet_request_count", 0)) == 2
                and int(probe.get("request_queue_limit", 0)) == REQUEST_QUEUE_LIMIT
                and int(probe.get("per_client_request_queue_limit", 0))
                == PER_CLIENT_REQUEST_QUEUE_LIMIT
                and int(probe.get("global_resource_drops", -1)) == 0
                and int(probe.get("per_client_resource_drops", 0)) == 12
                and int(probe.get("request_queue_max_observed", 0))
                == REQUEST_QUEUE_LIMIT
                and int(probe.get("per_client_max_observed", 0))
                == PER_CLIENT_REQUEST_QUEUE_LIMIT
                and int(probe.get("first_wave_request_count", 0)) == 4
                and probe.get("quiet_admitted_first_wave") is True
                and int(probe.get("unique_requests_taken", 0)) == 10
                and int(probe.get("noisy_responses_taken", 0)) == 8
                and int(probe.get("quiet_responses_taken", 0)) == 2
                and probe.get("exact_delivery") is True
                and probe.get("cleanup_ok") is True
                and per_client_drop_traces == 12
            )
            runs.append(
                {
                    "iteration": iteration,
                    "status": "ok" if ok else "failed",
                    "returncode": result.returncode,
                    "netem_applied": result.returncode == 0,
                    "netem_profile": NETEM_PROFILE,
                    "per_client_drop_trace_count": per_client_drop_traces,
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
            "noisy_request_count": 8,
            "quiet_request_count": 2,
            "request_queue_limit": REQUEST_QUEUE_LIMIT,
            "per_client_request_queue_limit": PER_CLIENT_REQUEST_QUEUE_LIMIT,
            "per_client_resource_drops": sum(
                int(run["probe"].get("per_client_resource_drops", 0))
                for run in runs
            ),
            "unique_requests_taken": sum(
                int(run["probe"].get("unique_requests_taken", 0))
                for run in runs
            ),
            "noisy_responses_taken": sum(
                int(run["probe"].get("noisy_responses_taken", 0))
                for run in runs
            ),
            "quiet_responses_taken": sum(
                int(run["probe"].get("quiet_responses_taken", 0))
                for run in runs
            ),
            "netem_applied_all": all(run["netem_applied"] for run in runs),
            "quiet_client_first_wave_admission_claim": status == "ok",
            "per_client_service_pending_isolation_claim": status == "ok",
            "service_noisy_neighbor_bounded_fairness_claim": status == "ok",
            "weighted_service_fairness_claim": False,
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
            "docker_service_client_isolation_probe_summary.json"
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

"""Run FleetRMW smooth weighted service scheduling in Docker/netem."""

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


SCHEMA_VERSION = "fleetrmw.rmw_docker_service_weighted_fairness_probe.v1"
DEFAULT_IMAGE = "localhost/fleetrmw/rmw-netem:jazzy"
NETEM_PROFILE = "delay 8ms 2ms"
LOW_WEIGHT = 1
HIGH_WEIGHT = 3
MEASURED_REQUESTS = 40


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
    build_base = f"/work/.tmp_fleetrmw_service_weighted_build_{suffix}"
    install_base = f"/work/.tmp_fleetrmw_service_weighted_install_{suffix}"
    log_base = f"/work/.tmp_fleetrmw_service_weighted_log_{suffix}"
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
                    "export FLEETQOX_RMW_SERVICE_SCHEDULER=weighted && "
                    "export FLEETQOX_RMW_SERVICE_REQUEST_QUEUE_LIMIT=256 && "
                    "export FLEETQOX_RMW_SERVICE_PENDING_RESPONSE_LIMIT=64 && "
                    "export FLEETQOX_RMW_SERVICE_DEDUPE_HISTORY_LIMIT=256 && "
                    f"tc qdisc replace dev lo root netem {NETEM_PROFILE} && "
                    f"{install_base}/rmw_fleetqox_cpp/lib/rmw_fleetqox_cpp/"
                    "fleetrmw_service_weighted_fairness_probe"
                ),
            )
            logs = result.stdout + result.stderr
            probe = parse_last_json(logs)
            weight_trace_count = logs.count("weight=3")
            ok = (
                result.returncode == 0
                and probe.get("status") == "ok"
                and probe.get("request_path") == "rmw_send_request"
                and int(probe.get("low_weight", 0)) == LOW_WEIGHT
                and int(probe.get("high_weight", 0)) == HIGH_WEIGHT
                and int(probe.get("measured_requests", 0)) == MEASURED_REQUESTS
                and int(probe.get("low_dequeues", 0)) == 10
                and int(probe.get("high_dequeues", 0)) == 30
                and int(probe.get("maximum_high_streak", 0)) <= HIGH_WEIGHT
                and int(probe.get("weighted_dequeues", 0))
                == MEASURED_REQUESTS
                and probe.get("weighted_service_ratio_claim") is True
                and probe.get("per_client_fifo_claim") is True
                and probe.get("bounded_weighted_starvation_claim") is True
                and probe.get("cleanup_ok") is True
                and weight_trace_count >= 64
            )
            runs.append(
                {
                    "iteration": iteration,
                    "status": "ok" if ok else "failed",
                    "returncode": result.returncode,
                    "netem_applied": result.returncode == 0,
                    "netem_profile": NETEM_PROFILE,
                    "weight_trace_count": weight_trace_count,
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
            "scheduler": "smooth_weighted_round_robin",
            "request_path": "rmw_send_request",
            "low_weight": LOW_WEIGHT,
            "high_weight": HIGH_WEIGHT,
            "measured_requests_per_run": MEASURED_REQUESTS,
            "low_dequeues": sum(
                int(run["probe"].get("low_dequeues", 0)) for run in runs
            ),
            "high_dequeues": sum(
                int(run["probe"].get("high_dequeues", 0)) for run in runs
            ),
            "weighted_dequeues": sum(
                int(run["probe"].get("weighted_dequeues", 0)) for run in runs
            ),
            "maximum_high_streak": max(
                (
                    int(run["probe"].get("maximum_high_streak", 0))
                    for run in runs
                ),
                default=0,
            ),
            "netem_applied_all": all(run["netem_applied"] for run in runs),
            "service_weight_wire_metadata_claim": status == "ok",
            "weighted_service_fairness_claim": status == "ok",
            "weighted_service_ratio_claim": status == "ok",
            "weighted_service_per_client_fifo_claim": status == "ok",
            "weighted_service_starvation_bound_claim": status == "ok",
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
            "docker_service_weighted_fairness_probe_summary.json"
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

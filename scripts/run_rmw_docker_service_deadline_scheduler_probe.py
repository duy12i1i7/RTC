"""Run FleetRMW deadline-aware service scheduling in Docker/netem."""

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


SCHEMA_VERSION = "fleetrmw.rmw_docker_service_deadline_scheduler_probe.v1"
DEFAULT_IMAGE = "localhost/fleetrmw/rmw-netem:jazzy"
NETEM_PROFILE = "delay 8ms 2ms"
URGENT_DEADLINE_MS = 20
RELAXED_DEADLINE_MS = 200
DEADLINE_AGING_MS = 100


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
    build_base = f"/work/.tmp_fleetrmw_service_deadline_build_{suffix}"
    install_base = f"/work/.tmp_fleetrmw_service_deadline_install_{suffix}"
    log_base = f"/work/.tmp_fleetrmw_service_deadline_log_{suffix}"
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
                    "export FLEETQOX_RMW_SERVICE_SCHEDULER=deadline && "
                    "export FLEETQOX_RMW_SERVICE_DEADLINE_AGING_MS="
                    f"{DEADLINE_AGING_MS} && "
                    "export FLEETQOX_RMW_SERVICE_REQUEST_QUEUE_LIMIT=16 && "
                    "export FLEETQOX_RMW_SERVICE_PENDING_RESPONSE_LIMIT=16 && "
                    f"tc qdisc replace dev lo root netem {NETEM_PROFILE} && "
                    f"{install_base}/rmw_fleetqox_cpp/lib/rmw_fleetqox_cpp/"
                    "fleetrmw_service_deadline_scheduler_probe"
                ),
            )
            logs = result.stdout + result.stderr
            probe = parse_last_json(logs)
            deadline_trace_count = logs.count("deadline_ns=20000000")
            ok = (
                result.returncode == 0
                and probe.get("status") == "ok"
                and probe.get("request_path") == "rmw_send_request"
                and int(probe.get("urgent_deadline_ms", 0))
                == URGENT_DEADLINE_MS
                and int(probe.get("relaxed_deadline_ms", 0))
                == RELAXED_DEADLINE_MS
                and int(probe.get("deadline_aging_ms", 0))
                == DEADLINE_AGING_MS
                and probe.get("deadline_order") == [1, 0]
                and probe.get("aging_order") == [0, 1]
                and int(probe.get("deadline_dequeues", 0)) == 4
                and int(probe.get("deadline_aged_dequeues", 0)) == 1
                and probe.get("earliest_deadline_first_claim") is True
                and probe.get("deadline_aging_starvation_bound_claim") is True
                and probe.get("cleanup_ok") is True
                and deadline_trace_count >= 4
            )
            runs.append(
                {
                    "iteration": iteration,
                    "status": "ok" if ok else "failed",
                    "returncode": result.returncode,
                    "netem_applied": result.returncode == 0,
                    "netem_profile": NETEM_PROFILE,
                    "deadline_trace_count": deadline_trace_count,
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
            "scheduler": "earliest_deadline_first",
            "request_path": "rmw_send_request",
            "urgent_deadline_ms": URGENT_DEADLINE_MS,
            "relaxed_deadline_ms": RELAXED_DEADLINE_MS,
            "deadline_aging_ms": DEADLINE_AGING_MS,
            "deadline_order": [1, 0],
            "aging_order": [0, 1],
            "deadline_dequeues": sum(
                int(run["probe"].get("deadline_dequeues", 0))
                for run in runs
            ),
            "deadline_aged_dequeues": sum(
                int(run["probe"].get("deadline_aged_dequeues", 0))
                for run in runs
            ),
            "netem_applied_all": all(run["netem_applied"] for run in runs),
            "service_request_deadline_wire_metadata_claim": status == "ok",
            "service_earliest_deadline_first_claim": status == "ok",
            "service_deadline_aging_starvation_bound_claim": status == "ok",
            "deadline_aware_service_scheduling_claim": status == "ok",
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
            "docker_service_deadline_scheduler_probe_summary.json"
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

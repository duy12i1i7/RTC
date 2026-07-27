"""Run bounded asynchronous service-repair admission in Docker/netem."""

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


SCHEMA_VERSION = "fleetrmw.rmw_docker_service_repair_admission_probe.v1"
DEFAULT_IMAGE = "localhost/fleetrmw/rmw-netem:jazzy"
NETEM_PROFILE = "delay 8ms 2ms"
PENDING_LIMIT = 4
PER_CLIENT_PENDING_LIMIT = 3


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
    build_base = f"/work/.tmp_fleetrmw_repair_admission_build_{suffix}"
    install_base = f"/work/.tmp_fleetrmw_repair_admission_install_{suffix}"
    log_base = f"/work/.tmp_fleetrmw_repair_admission_log_{suffix}"
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
                    "export FLEETQOX_RMW_SERVICE_REQUEST_QUEUE_LIMIT=32 && "
                    "export FLEETQOX_RMW_SERVICE_REQUEST_REPAIR_PENDING_LIMIT="
                    f"{PENDING_LIMIT} && "
                    "export FLEETQOX_RMW_SERVICE_REQUEST_REPAIR_PER_CLIENT_PENDING_LIMIT="
                    f"{PER_CLIENT_PENDING_LIMIT} && "
                    "export FLEETQOX_RMW_SERVICE_REQUEST_REPEAT_INTERVAL_MS=100 && "
                    f"tc qdisc replace dev lo root netem {NETEM_PROFILE} && "
                    f"{install_base}/rmw_fleetqox_cpp/lib/rmw_fleetqox_cpp/"
                    "fleetrmw_service_repair_admission_probe"
                ),
            )
            logs = result.stdout + result.stderr
            probe = parse_last_json(logs)
            scheduled_traces = logs.count("service repair event=scheduled")
            client_rejection_traces = logs.count(
                "service repair event=client_admission_rejected"
            )
            global_rejection_traces = logs.count(
                "service repair event=global_admission_rejected"
            )
            destroyed_traces = logs.count(
                "service repair event=client_destroyed"
            )
            ok = (
                result.returncode == 0
                and probe.get("status") == "ok"
                and int(probe.get("client_count", 0)) == 2
                and int(probe.get("requests_per_client", 0)) == 4
                and probe.get("initial_sends_ok") is True
                and int(probe.get("repair_pending_limit", 0)) == PENDING_LIMIT
                and int(probe.get("repair_per_client_pending_limit", 0))
                == PER_CLIENT_PENDING_LIMIT
                and int(probe.get("repairs_scheduled", 0)) == 4
                and int(probe.get("repair_client_admission_rejections", 0)) == 1
                and int(probe.get("repair_global_admission_rejections", 0)) == 3
                and int(probe.get("repair_pending_max_observed", 0)) == 4
                and int(probe.get("repairs_cancelled_on_destroy", 0)) == 4
                and probe.get("cleanup_ok") is True
                and scheduled_traces == 4
                and client_rejection_traces == 1
                and global_rejection_traces == 3
                and destroyed_traces == 4
            )
            runs.append(
                {
                    "iteration": iteration,
                    "status": "ok" if ok else "failed",
                    "returncode": result.returncode,
                    "netem_applied": result.returncode == 0,
                    "netem_profile": NETEM_PROFILE,
                    "scheduled_trace_count": scheduled_traces,
                    "client_rejection_trace_count": client_rejection_traces,
                    "global_rejection_trace_count": global_rejection_traces,
                    "destroyed_trace_count": destroyed_traces,
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
            "client_count": 2,
            "requests_per_client": 4,
            "repair_pending_limit": PENDING_LIMIT,
            "repair_per_client_pending_limit": PER_CLIENT_PENDING_LIMIT,
            "repairs_scheduled": sum(
                int(run["probe"].get("repairs_scheduled", 0))
                for run in runs
            ),
            "repair_client_admission_rejections": sum(
                int(
                    run["probe"].get(
                        "repair_client_admission_rejections", 0
                    )
                )
                for run in runs
            ),
            "repair_global_admission_rejections": sum(
                int(
                    run["probe"].get(
                        "repair_global_admission_rejections", 0
                    )
                )
                for run in runs
            ),
            "repairs_cancelled_on_destroy": sum(
                int(run["probe"].get("repairs_cancelled_on_destroy", 0))
                for run in runs
            ),
            "netem_applied_all": all(run["netem_applied"] for run in runs),
            "bounded_service_repair_pending_claim": status == "ok",
            "per_client_service_repair_admission_claim": status == "ok",
            "service_repair_initial_send_fail_open_claim": status == "ok",
            "service_repair_destroy_cleanup_claim": status == "ok",
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
            "docker_service_repair_admission_probe_summary.json"
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

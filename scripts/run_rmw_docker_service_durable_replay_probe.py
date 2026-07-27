"""Prove durable completed-service replay across a killed server process."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import stat
import subprocess
import sys
import time
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.run_rmw_docker_router_service_call_probe import parse_last_json


SCHEMA_VERSION = "fleetrmw.rmw_docker_service_durable_replay_probe.v1"
DEFAULT_IMAGE = "localhost/fleetrmw/rmw-netem:jazzy"
NETEM_PROFILE = "delay 8ms 2ms"


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


def wait_container(name: str) -> int:
    result = run_command(["docker", "wait", name], check=False)
    try:
        return int(result.stdout.strip())
    except ValueError:
        return 999


def container_logs(name: str) -> str:
    result = run_command(["docker", "logs", name], check=False)
    return result.stdout + result.stderr


def wait_for_status(name: str, status: str, timeout: float) -> dict[str, Any]:
    deadline = time.monotonic() + timeout
    latest: dict[str, Any] = {}
    while time.monotonic() < deadline:
        latest = parse_last_json(container_logs(name))
        if latest.get("status") == status:
            return latest
        time.sleep(0.1)
    return latest


def run_probe(*, root: Path, image: str, iterations: int) -> dict[str, Any]:
    suffix = str(os.getpid())
    build_base = f"/work/.tmp_fleetrmw_durable_replay_build_{suffix}"
    install_base = f"/work/.tmp_fleetrmw_durable_replay_install_{suffix}"
    log_base = f"/work/.tmp_fleetrmw_durable_replay_log_{suffix}"
    state_relative = Path(f".tmp_fleetrmw_durable_replay_state_{suffix}")
    state_host = root / state_relative
    state_container = f"/work/{state_relative}"
    probe_binary = (
        f"{install_base}/rmw_fleetqox_cpp/lib/rmw_fleetqox_cpp/"
        "fleetrmw_service_durable_replay_probe"
    )
    runs: list[dict[str, Any]] = []
    created_networks: list[str] = []
    created_containers: list[str] = []

    def docker_shell(command: str, *, check: bool = True) -> subprocess.CompletedProcess[str]:
        return run_command(
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
                command,
            ],
            check=check,
        )

    def start_container(
        *,
        name: str,
        network: str,
        command: str,
    ) -> str:
        result = run_command(
            [
                "docker",
                "run",
                "-d",
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
        created_containers.append(name)
        return result.stdout.strip()

    try:
        docker_shell(
            "source /opt/ros/jazzy/setup.bash && "
            f"rm -rf {build_base} {install_base} {log_base} "
            f"{state_container} && "
            f"colcon --log-base {log_base} build --base-paths ros2_ws/src "
            "--packages-select rmw_fleetqox_cpp "
            f"--build-base {build_base} --install-base {install_base} "
            "--cmake-args -DCMAKE_BUILD_TYPE=Release"
        )
        for iteration in range(iterations):
            docker_shell(
                f"rm -rf {state_container} && mkdir -p {state_container}"
            )
            network = f"fleetrmw-durable-svc-net-{suffix}-{iteration}"
            router_name = f"fleetrmw-durable-svc-router-{suffix}-{iteration}"
            server_first = f"fleetrmw-durable-svc-first-{suffix}-{iteration}"
            client_first = f"fleetrmw-durable-cli-first-{suffix}-{iteration}"
            server_replay = f"fleetrmw-durable-svc-replay-{suffix}-{iteration}"
            client_replay = f"fleetrmw-durable-cli-replay-{suffix}-{iteration}"
            run_command(["docker", "network", "create", network])
            created_networks.append(network)

            start_container(
                name=router_name,
                network=network,
                command=(
                    "source /opt/ros/jazzy/setup.bash && "
                    f"source {install_base}/setup.bash && "
                    f"tc qdisc replace dev eth0 root netem {NETEM_PROFILE} && "
                    f"{install_base}/rmw_fleetqox_cpp/lib/rmw_fleetqox_cpp/"
                    "fleetrmw_udp_router_probe "
                    "--bind 0.0.0.0:48700 "
                    "--expected-frames 0 "
                    "--expected-service-frames 4 "
                    "--expected-graph-advertisements 6 "
                    "--post-satisfaction-ms 300 "
                    "--timeout-ms 30000"
                ),
            )
            start_container(
                name=server_first,
                network=network,
                command=(
                    "source /opt/ros/jazzy/setup.bash && "
                    f"source {install_base}/setup.bash && "
                    f"tc qdisc replace dev eth0 root netem {NETEM_PROFILE} && "
                    "export RMW_IMPLEMENTATION=rmw_fleetqox_cpp && "
                    "export FLEETQOX_RMW_BIND=0.0.0.0:48701 && "
                    f"export FLEETQOX_RMW_PEERS={router_name}:48700 && "
                    "export FLEETQOX_RMW_TRACE_SERVICE=1 && "
                    "export FLEETQOX_RMW_SERVICE_RESPONSE_REPEATS=0 && "
                    "export FLEETQOX_RMW_SERVICE_REQUEST_REPAIR_RETRIES=5 && "
                    "export FLEETQOX_RMW_SERVICE_REQUEST_REPAIR_INTERVAL_MS=100 && "
                    "export FLEETQOX_RMW_SERVICE_DURABLE_REPLAY_DIR="
                    f"{state_container} && "
                    f"{probe_binary} --role server-crash"
                ),
            )
            time.sleep(0.8)
            start_container(
                name=client_first,
                network=network,
                command=(
                    "source /opt/ros/jazzy/setup.bash && "
                    f"source {install_base}/setup.bash && "
                    f"tc qdisc replace dev eth0 root netem {NETEM_PROFILE} && "
                    "export RMW_IMPLEMENTATION=rmw_fleetqox_cpp && "
                    "export FLEETQOX_RMW_BIND=0.0.0.0:48702 && "
                    f"export FLEETQOX_RMW_PEERS={router_name}:48700 && "
                    f"{probe_binary} --role client-first"
                ),
            )
            crash_ready = wait_for_status(server_first, "crash_ready", 10.0)
            state_files = sorted(state_host.glob("service-*.replay"))
            state_modes = [
                stat.S_IMODE(path.stat().st_mode) for path in state_files
            ]
            run_command(
                ["docker", "kill", "--signal", "KILL", server_first],
                check=False,
            )
            server_first_returncode = wait_container(server_first)
            client_first_returncode = wait_container(client_first)
            client_first_summary = parse_last_json(container_logs(client_first))

            start_container(
                name=server_replay,
                network=network,
                command=(
                    "source /opt/ros/jazzy/setup.bash && "
                    f"source {install_base}/setup.bash && "
                    f"tc qdisc replace dev eth0 root netem {NETEM_PROFILE} && "
                    "export RMW_IMPLEMENTATION=rmw_fleetqox_cpp && "
                    "export FLEETQOX_RMW_BIND=0.0.0.0:48701 && "
                    f"export FLEETQOX_RMW_PEERS={router_name}:48700 && "
                    "export FLEETQOX_RMW_TRACE_SERVICE=1 && "
                    "export FLEETQOX_RMW_SERVICE_DURABLE_REPLAY_DIR="
                    f"{state_container} && "
                    f"{probe_binary} --role server-replay"
                ),
            )
            time.sleep(0.8)
            start_container(
                name=client_replay,
                network=network,
                command=(
                    "source /opt/ros/jazzy/setup.bash && "
                    f"source {install_base}/setup.bash && "
                    f"tc qdisc replace dev eth0 root netem {NETEM_PROFILE} && "
                    "export RMW_IMPLEMENTATION=rmw_fleetqox_cpp && "
                    "export FLEETQOX_RMW_BIND=0.0.0.0:48702 && "
                    f"export FLEETQOX_RMW_PEERS={router_name}:48700 && "
                    f"{probe_binary} --role client-replay"
                ),
            )
            client_replay_returncode = wait_container(client_replay)
            server_replay_returncode = wait_container(server_replay)
            router_returncode = wait_container(router_name)
            client_replay_summary = parse_last_json(container_logs(client_replay))
            server_replay_summary = parse_last_json(container_logs(server_replay))
            router_summary = parse_last_json(container_logs(router_name))

            ok = (
                crash_ready.get("status") == "crash_ready"
                and crash_ready.get("application_response_sent") is True
                and int(crash_ready.get("durable_replays_persisted", 0)) >= 1
                and int(crash_ready.get("durable_replay_failures", 1)) == 0
                and server_first_returncode == 137
                and client_first_returncode == 0
                and client_first_summary.get("status") == "ok"
                and len(state_files) == 1
                and state_modes == [0o600]
                and client_replay_returncode == 0
                and client_replay_summary.get("status") == "ok"
                and client_replay_summary.get("response_matches") is True
                and server_replay_returncode == 0
                and server_replay_summary.get("status") == "ok"
                and server_replay_summary.get("request_taken") is False
                and server_replay_summary.get("application_response_sent")
                is False
                and int(
                    server_replay_summary.get("durable_replays_loaded", 0)
                )
                >= 1
                and int(server_replay_summary.get("durable_replays_sent", 0))
                >= 1
                and int(
                    server_replay_summary.get("durable_replay_failures", 1)
                )
                == 0
                and router_returncode == 0
                and router_summary.get("status") == "ok"
                and int(router_summary.get("service_frames", 0)) >= 4
                and int(router_summary.get("invalid_frames", 1)) == 0
            )
            runs.append(
                {
                    "iteration": iteration,
                    "status": "ok" if ok else "failed",
                    "netem_profile": NETEM_PROFILE,
                    "server_crash": crash_ready,
                    "server_crash_returncode": server_first_returncode,
                    "client_first": client_first_summary,
                    "client_first_returncode": client_first_returncode,
                    "server_replacement": server_replay_summary,
                    "server_replacement_returncode": server_replay_returncode,
                    "client_replay": client_replay_summary,
                    "client_replay_returncode": client_replay_returncode,
                    "router": router_summary,
                    "router_returncode": router_returncode,
                    "state_file_count": len(state_files),
                    "state_file_modes": state_modes,
                    "distinct_server_containers": server_first != server_replay,
                }
            )
            for name in (
                server_first,
                client_first,
                server_replay,
                client_replay,
                router_name,
            ):
                run_command(["docker", "rm", "-f", name], check=False)
            run_command(["docker", "network", "rm", network], check=False)
            created_networks.remove(network)

        ok_run_count = sum(run["status"] == "ok" for run in runs)
        status = "ok" if ok_run_count == iterations else "failed"
        return {
            "schema_version": SCHEMA_VERSION,
            "status": status,
            "image": image,
            "run_count": iterations,
            "ok_run_count": ok_run_count,
            "netem_profile": NETEM_PROFILE,
            "server_sigkill_count": sum(
                run["server_crash_returncode"] == 137 for run in runs
            ),
            "durable_replays_loaded": sum(
                int(
                    run["server_replacement"].get(
                        "durable_replays_loaded", 0
                    )
                )
                for run in runs
            ),
            "durable_replays_sent": sum(
                int(
                    run["server_replacement"].get(
                        "durable_replays_sent", 0
                    )
                )
                for run in runs
            ),
            "application_reexecutions": sum(
                bool(run["server_replacement"].get("request_taken"))
                for run in runs
            ),
            "client_replay_successes": sum(
                run["client_replay"].get("response_matches") is True
                for run in runs
            ),
            "durable_state_mode_0600_all": all(
                run["state_file_modes"] == [0o600] for run in runs
            ),
            "netem_applied_all": status == "ok",
            "service_completed_response_durable_replay_claim": status == "ok",
            "service_process_crash_replay_claim": status == "ok",
            "service_duplicate_application_suppression_after_restart_claim":
            status == "ok",
            "crash_persistent_completed_service_deduplication_claim":
            status == "ok",
            "full_exactly_once_service_semantics_claim": False,
            "power_loss_durability_claim": False,
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
            "runs": runs,
        }
    finally:
        for name in reversed(created_containers):
            run_command(["docker", "rm", "-f", name], check=False)
        for network in reversed(created_networks):
            run_command(["docker", "network", "rm", network], check=False)
        docker_shell(
            f"rm -rf {build_base} {install_base} {log_base} "
            f"{state_container}",
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
            "docker_service_durable_replay_probe_summary.json"
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

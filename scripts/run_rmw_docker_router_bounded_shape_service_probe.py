"""Run generated bounded ROSIDL service interoperability through FleetRMW/netem."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
import time
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.run_rmw_docker_router_service_call_probe import parse_last_json


SCHEMA_VERSION = "fleetrmw.docker_router_bounded_shape_service_probe.v1"
DEFAULT_IMAGE = "localhost/fleetrmw/rmw-netem:jazzy"
NETEM_PROFILE = "delay 8ms 2ms rate 50mbit"
SERVICE_REQUEST_REPEATS = 5
SERVICE_REQUEST_REPEAT_INTERVAL_MS = 100
DIRECTION_NAMES = {
    "server": "cpp_server_python_client",
    "client": "cpp_client_python_server",
}


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
    *, root: Path, image: str, command: str, check: bool = True
) -> subprocess.CompletedProcess[str]:
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


def run_direction(
    *,
    root: Path,
    image: str,
    install_base: str,
    iteration: int,
    cpp_mode: str,
) -> dict[str, Any]:
    python_mode = "client" if cpp_mode == "server" else "server"
    direction = DIRECTION_NAMES[cpp_mode]
    suffix = f"{os.getpid()}-{iteration}-{cpp_mode}"
    network = f"fleetrmw-bounded-net-{suffix}"
    router_name = f"fleetrmw-bounded-router-{suffix}"
    cpp_name = f"fleetrmw-bounded-cpp-{suffix}"
    python_name = f"fleetrmw-bounded-python-{suffix}"
    cpp_executable = (
        f"{install_base}/fleetrmw_interfaces/lib/fleetrmw_interfaces/"
        "fleetrmw_bounded_shape_service_probe"
    )
    common = (
        "source /opt/ros/jazzy/setup.bash && "
        f"source {install_base}/setup.bash && "
        "export RMW_IMPLEMENTATION=rmw_fleetqox_cpp && "
        "export FLEETQOX_RMW_TRACE_SERVICE=1 && "
        f"export FLEETQOX_RMW_SERVICE_REQUEST_REPEATS={SERVICE_REQUEST_REPEATS} && "
        "export FLEETQOX_RMW_SERVICE_REQUEST_REPEAT_INTERVAL_MS="
        f"{SERVICE_REQUEST_REPEAT_INTERVAL_MS} && "
    )
    netem = f"tc qdisc replace dev eth0 root netem {NETEM_PROFILE} && "

    def logs(name: str) -> str:
        result = run_command(["docker", "logs", name], check=False)
        return result.stdout + result.stderr

    try:
        run_command(["docker", "network", "create", network])
        run_command(
            [
                "docker",
                "run",
                "-d",
                "--name",
                router_name,
                "--network",
                network,
                "--entrypoint",
                "bash",
                "-v",
                f"{root}:/work",
                "-w",
                "/work",
                image,
                "-lc",
                common
                + f"{install_base}/rmw_fleetqox_cpp/lib/rmw_fleetqox_cpp/"
                "fleetrmw_udp_router_probe --bind 0.0.0.0:49800 "
                "--expected-service-frames 2 --expected-graph-advertisements 2 "
                "--post-satisfaction-ms 1200 --timeout-ms 30000",
            ]
        )
        time.sleep(0.4)
        cpp_port = 49801 if cpp_mode == "server" else 49802
        python_port = 49802 if python_mode == "client" else 49801
        run_command(
            [
                "docker",
                "run",
                "-d",
                "--name",
                cpp_name,
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
                netem
                + common
                + f"export FLEETQOX_RMW_BIND=0.0.0.0:{cpp_port} && "
                f"export FLEETQOX_RMW_PEERS={router_name}:49800 && "
                f"{cpp_executable} {cpp_mode}",
            ]
        )
        time.sleep(0.3)
        run_command(
            [
                "docker",
                "run",
                "-d",
                "--name",
                python_name,
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
                netem
                + common
                + f"export FLEETQOX_RMW_BIND=0.0.0.0:{python_port} && "
                f"export FLEETQOX_RMW_PEERS={router_name}:49800 && "
                "python3 scripts/rclpy_bounded_shape_service_endpoint.py "
                f"{python_mode}",
            ]
        )
        cpp_returncode = int(
            run_command(["docker", "wait", cpp_name]).stdout.strip()
        )
        python_returncode = int(
            run_command(["docker", "wait", python_name]).stdout.strip()
        )
        router_returncode = int(
            run_command(["docker", "wait", router_name]).stdout.strip()
        )
        cpp_logs = logs(cpp_name)
        python_logs = logs(python_name)
        router_logs = logs(router_name)
        cpp = parse_last_json(cpp_logs)
        python = parse_last_json(python_logs)
        router = parse_last_json(router_logs)
        endpoint_semantics = cpp.get("status") == "ok" and python.get("status") == "ok"
        if cpp_mode == "server":
            endpoint_semantics = (
                endpoint_semantics
                and cpp.get("request_received") is True
                and cpp.get("request_valid") is True
                and int(cpp.get("token_size", 0)) == 16
                and int(cpp.get("range_count", 0)) == 128
                and int(cpp.get("waypoint_count", 0)) == 16
                and python.get("service_available") is True
                and python.get("response_valid") is True
                and int(python.get("admitted_index_count", 0)) == 64
                and int(python.get("repaired_waypoint_count", 0)) == 16
            )
        else:
            endpoint_semantics = (
                endpoint_semantics
                and python.get("request_received") is True
                and python.get("request_valid") is True
                and int(python.get("token_size", 0)) == 16
                and int(python.get("range_count", 0)) == 128
                and int(python.get("waypoint_count", 0)) == 16
                and cpp.get("service_available") is True
                and cpp.get("response_valid") is True
                and int(cpp.get("admitted_index_count", 0)) == 64
                and int(cpp.get("repaired_waypoint_count", 0)) == 16
            )
        ok = (
            cpp_returncode == 0
            and python_returncode == 0
            and router_returncode == 0
            and endpoint_semantics
            and router.get("status") == "ok"
            and int(router.get("service_forwarded", 0)) >= 2
            and int(router.get("invalid_frames", -1)) == 0
            and "/fleetqox/bounded_shape" in set(router.get("service_names", []))
        )
        return {
            "direction": direction,
            "status": "ok" if ok else "failed",
            "netem_applied": cpp_returncode == 0 and python_returncode == 0,
            "netem_profile": NETEM_PROFILE,
            "cpp_returncode": cpp_returncode,
            "python_returncode": python_returncode,
            "router_returncode": router_returncode,
            "cpp": cpp,
            "python": python,
            "router": router,
            "cpp_logs": cpp_logs,
            "python_logs": python_logs,
            "router_logs": router_logs,
        }
    except subprocess.CalledProcessError as exc:
        return {
            "direction": direction,
            "status": "failed",
            "netem_applied": False,
            "returncode": exc.returncode,
            "stdout": exc.stdout,
            "stderr": exc.stderr,
        }
    finally:
        run_command(
            ["docker", "rm", "-f", router_name, cpp_name, python_name], check=False
        )
        run_command(["docker", "network", "rm", network], check=False)


def run_probe(*, root: Path, image: str, iterations: int) -> dict[str, Any]:
    suffix = str(os.getpid())
    build_base = f"/work/.tmp_fleetrmw_bounded_build_{suffix}"
    install_base = f"/work/.tmp_fleetrmw_bounded_install_{suffix}"
    log_base = f"/work/.tmp_fleetrmw_bounded_log_{suffix}"
    try:
        docker_shell(
            root=root,
            image=image,
            command=(
                "source /opt/ros/jazzy/setup.bash && "
                f"rm -rf {build_base} {install_base} {log_base} && "
                f"colcon --log-base {log_base} build --base-paths ros2_ws/src "
                "--packages-select fleetrmw_interfaces rmw_fleetqox_cpp "
                f"--build-base {build_base} --install-base {install_base} "
                "--cmake-args -DCMAKE_BUILD_TYPE=Release"
            ),
        )
        runs = []
        for iteration in range(iterations):
            directions = [
                run_direction(
                    root=root,
                    image=image,
                    install_base=install_base,
                    iteration=iteration,
                    cpp_mode=cpp_mode,
                )
                for cpp_mode in ("server", "client")
            ]
            runs.append(
                {
                    "iteration": iteration,
                    "status": (
                        "ok"
                        if all(row["status"] == "ok" for row in directions)
                        else "failed"
                    ),
                    "directions": directions,
                }
            )
        ok_run_count = sum(row["status"] == "ok" for row in runs)
        ok_direction_count = sum(
            direction["status"] == "ok"
            for row in runs
            for direction in row["directions"]
        )
        status = "ok" if ok_run_count == iterations else "failed"
        return {
            "schema_version": SCHEMA_VERSION,
            "status": status,
            "image": image,
            "run_count": iterations,
            "ok_run_count": ok_run_count,
            "direction_count": iterations * 2,
            "ok_direction_count": ok_direction_count,
            "netem_applied_all": all(
                direction.get("netem_applied") is True
                for row in runs
                for direction in row["directions"]
            ),
            "token_size": 16,
            "range_count": 128,
            "waypoint_count": 16,
            "admitted_index_count": 64,
            "fixed_array_claim": status == "ok",
            "bounded_primitive_sequence_claim": status == "ok",
            "bounded_nested_message_sequence_claim": status == "ok",
            "bounded_string_claim": status == "ok",
            "duration_field_claim": status == "ok",
            "bidirectional_cpp_python_bounded_service_claim": status == "ok",
            "service_request_repeat_count": SERVICE_REQUEST_REPEATS,
            "service_request_repeat_interval_ms": SERVICE_REQUEST_REPEAT_INTERVAL_MS,
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
            "docker_router_bounded_shape_service_probe_summary.json"
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
        json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(json.dumps(summary, sort_keys=True) if args.json else summary["status"])
    return 0 if summary["status"] == "ok" else 1


if __name__ == "__main__":
    raise SystemExit(main())

"""Run bidirectional C++/rclpy Path interoperability through FleetRMW and netem."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import time
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.run_rmw_docker_router_service_call_probe import parse_last_json


SCHEMA_VERSION = "fleetrmw.docker_router_cpp_python_path_probe.v2"
DEFAULT_IMAGE = "localhost/fleetrmw/rmw-netem:jazzy"
NETEM_PROFILE = "delay 8ms 2ms rate 50mbit"
MIDDLEWARE_DEFAULT_REQUEST_REPAIR_RETRIES = 5
MIDDLEWARE_DEFAULT_REQUEST_REPAIR_INTERVAL_MS = 100
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
    network = f"fleetrmw-xlang-net-{suffix}"
    router_name = f"fleetrmw-xlang-router-{suffix}"
    cpp_name = f"fleetrmw-xlang-cpp-{suffix}"
    python_name = f"fleetrmw-xlang-python-{suffix}"
    cpp_executable = (
        f"{install_base}/rmw_fleetqox_cpp/lib/rmw_fleetqox_cpp/"
        "fleetrmw_rclcpp_interprocess_probe"
    )
    common = (
        "source /opt/ros/jazzy/setup.bash && "
        f"source {install_base}/setup.bash && "
        "export RMW_IMPLEMENTATION=rmw_fleetqox_cpp && "
        "export FLEETQOX_RMW_TRACE_SERVICE=1 && "
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
                "--expected-frames 4 --expected-service-frames 3 "
                "--expected-graph-advertisements 8 "
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
                f"python3 scripts/rclpy_cpp_interprocess_endpoint.py {python_mode}",
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
        plan_payload_sizes = [
            int(value)
            for value in re.findall(
                (
                    r"service=/fleetqox/cpp_get_plan[^\n]*"
                    r"role=response[^\n]*payload=(\d+)"
                ),
                cpp_logs + python_logs,
            )
        ]
        plan_response_payload_bytes = max(plan_payload_sizes, default=0)
        endpoint_logs = cpp_logs + python_logs
        repair_scheduled_count = endpoint_logs.count(
            "fleetqox service repair event=scheduled"
        )
        repair_retry_count = endpoint_logs.count(
            "fleetqox service repair event=retry "
        )
        repair_response_cancelled_count = endpoint_logs.count(
            "fleetqox service repair event=response_received"
        )
        topics = set(router.get("forwarded_topics", []))
        required_topics = {
            "/fleetqox/cpp_pose_request",
            "/fleetqox/cpp_pose_reply",
            "/fleetqox/cpp_path_request",
            "/fleetqox/cpp_path_reply",
        }
        required_services = {
            "/fleetqox/cpp_set_bool",
            "/fleetqox/cpp_get_plan",
        }
        endpoint_semantics = (
            cpp.get("status") == "ok"
            and python.get("status") == "ok"
            and int(cpp.get("path_pose_count", 0)) == 64
            and int(python.get("path_pose_count", 0)) == 64
            and int(cpp.get("plan_pose_count", 0)) == 512
            and int(python.get("plan_pose_count", 0)) == 512
        )
        if cpp_mode == "server":
            endpoint_semantics = (
                endpoint_semantics
                and cpp.get("path_received") is True
                and cpp.get("path_valid") is True
                and python.get("path_roundtrip") is True
                and python.get("pose_roundtrip") is True
                and python.get("service_ok") is True
                and python.get("plan_service_available") is True
                and python.get("plan_service_ok") is True
                and cpp.get("plan_service_received") is True
                and cpp.get("plan_request_valid") is True
            )
        else:
            endpoint_semantics = (
                endpoint_semantics
                and python.get("path_received") is True
                and python.get("path_valid") is True
                and cpp.get("path_roundtrip") is True
                and cpp.get("pose_roundtrip") is True
                and cpp.get("service_ok") is True
                and cpp.get("plan_service_available") is True
                and cpp.get("plan_service_ok") is True
                and cpp.get("plan_response_callback_observed") is True
                and python.get("plan_service_received") is True
                and python.get("plan_request_valid") is True
                and cpp.get("path_publisher_network_flow") is True
                and cpp.get("path_subscription_network_flow") is True
            )
        ok = (
            cpp_returncode == 0
            and python_returncode == 0
            and router_returncode == 0
            and endpoint_semantics
            and router.get("status") == "ok"
            and int(router.get("forwarded_frames", 0)) >= 4
            and int(router.get("service_forwarded", 0)) >= 3
            and int(router.get("invalid_frames", -1)) == 0
            and required_topics.issubset(topics)
            and required_services.issubset(set(router.get("service_names", [])))
            and plan_response_payload_bytes > 65507
            and repair_scheduled_count >= 2
            and repair_response_cancelled_count >= 2
        )
        return {
            "direction": direction,
            "status": "ok" if ok else "failed",
            "netem_applied": cpp_returncode == 0 and python_returncode == 0,
            "netem_profile": NETEM_PROFILE,
            "plan_response_payload_bytes": plan_response_payload_bytes,
            "service_payload_exceeds_udp_datagram": (
                plan_response_payload_bytes > 65507
            ),
            "request_repairs_scheduled": repair_scheduled_count,
            "request_retries_sent": repair_retry_count,
            "request_repairs_cancelled_by_response": (
                repair_response_cancelled_count
            ),
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


def run_probe(
    *, root: Path, image: str, iterations: int
) -> dict[str, Any]:
    suffix = str(os.getpid())
    build_base = f"/work/.tmp_fleetrmw_xlang_build_{suffix}"
    install_base = f"/work/.tmp_fleetrmw_xlang_install_{suffix}"
    log_base = f"/work/.tmp_fleetrmw_xlang_log_{suffix}"
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
        plan_response_payload_sizes = [
            int(direction.get("plan_response_payload_bytes", 0))
            for row in runs
            for direction in row["directions"]
        ]
        return {
            "schema_version": SCHEMA_VERSION,
            "status": status,
            "image": image,
            "run_count": iterations,
            "ok_run_count": ok_run_count,
            "direction_count": iterations * 2,
            "ok_direction_count": ok_direction_count,
            "path_pose_count": 64,
            "plan_pose_count": 512,
            "min_plan_response_payload_bytes": min(
                plan_response_payload_sizes, default=0
            ),
            "service_payload_exceeds_udp_datagram_all": all(
                direction.get("service_payload_exceeds_udp_datagram") is True
                for row in runs
                for direction in row["directions"]
            ),
            "service_request_repair_configuration": "middleware_default",
            "service_request_repair_environment_overridden": False,
            "middleware_default_request_repair_retries": (
                MIDDLEWARE_DEFAULT_REQUEST_REPAIR_RETRIES
            ),
            "middleware_default_request_repair_interval_ms": (
                MIDDLEWARE_DEFAULT_REQUEST_REPAIR_INTERVAL_MS
            ),
            "bounded_service_discovery_repair_claim": status == "ok",
            "nonblocking_async_service_request_repair_claim": status == "ok",
            "response_cancelled_request_repair_claim": status == "ok",
            "service_discovery_repair_without_runner_override_claim": status == "ok",
            "service_exactly_once_claim": False,
            "bidirectional_cpp_python_claim": status == "ok",
            "sequence_heavy_nested_path_claim": status == "ok",
            "sequence_heavy_get_plan_service_claim": status == "ok",
            "large_sequence_service_fragmentation_claim": status == "ok",
            "netem_applied_all": all(
                direction.get("netem_applied") is True
                for row in runs
                for direction in row["directions"]
            ),
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
            "docker_router_cpp_python_path_probe_summary.json"
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

"""Run a router-mediated ROS 2 CLI service timeout probe for FleetRMW."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import shlex
import subprocess
import sys
import time
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.run_rmw_docker_router_service_call_probe import parse_last_json


SCHEMA_VERSION = "fleetrmw.rmw_router_ros2_service_timeout_probe.v1"
DEFAULT_IMAGE = "ros:jazzy-ros-base"
DEFAULT_SERVICE = "/fleetqox/router_set_bool_timeout"
DEFAULT_TYPE = "std_srvs/srv/SetBool"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--image", default=DEFAULT_IMAGE)
    parser.add_argument("--service", default=DEFAULT_SERVICE)
    parser.add_argument("--response-delay-ms", type=int, default=3500)
    parser.add_argument("--call-timeout", type=float, default=2.0)
    parser.add_argument(
        "--summary-json",
        default="results_rmw_socket/docker_router_ros2_service_timeout_probe_summary.json",
    )
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    summary = run_probe(
        root=ROOT,
        image=args.image,
        service=args.service,
        response_delay_ms=max(args.response_delay_ms, 0),
        call_timeout=max(args.call_timeout, 0.1),
    )
    output = ROOT / args.summary_json
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(summary, sort_keys=True) + "\n", encoding="utf-8")

    if args.json:
        print(json.dumps(summary, sort_keys=True))
    else:
        print("fleetrmw-router-ros2-service-timeout-probe")
        print(f"  status: {summary['status']}")
        print(f"  timed_out: {summary.get('timed_out')}")
        print(f"  server_saw_request: {summary.get('server_saw_request')}")
        print(f"  router_service_frames: {summary.get('router', {}).get('service_frames')}")
    return 0 if summary["status"] == "ok" else 1


def run_probe(
    *,
    root: Path,
    image: str,
    service: str,
    response_delay_ms: int,
    call_timeout: float,
) -> dict[str, Any]:
    suffix = str(os.getpid())
    network = f"fleetrmw-svc-timeout-net-{suffix}"
    router_name = f"fleetrmw-svc-timeout-router-{suffix}"
    service_name = f"fleetrmw-svc-timeout-server-{suffix}"
    build_base = "/work/.tmp_fleetrmw_service_timeout_router_build"
    install_base = "/work/.tmp_fleetrmw_service_timeout_router_install"
    log_base = "/work/.tmp_fleetrmw_service_timeout_router_log"
    router_port = 49650
    service_port = 49651

    def run(cmd: list[str], *, check: bool = True) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            cmd,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=check,
        )

    def docker_shell(command: str, *extra: str, check: bool = True) -> subprocess.CompletedProcess[str]:
        return run([
            "docker", "run", "--rm", *extra,
            "-v", f"{root}:/work",
            "-w", "/work",
            image,
            "bash", "-lc", command,
        ], check=check)

    try:
        docker_shell(
            "source /opt/ros/jazzy/setup.bash && "
            f"rm -rf {build_base} {install_base} {log_base} && "
            "colcon "
            f"--log-base {log_base} build --base-paths ros2_ws/src "
            "--packages-select rmw_fleetqox_cpp "
            f"--build-base {build_base} --install-base {install_base} "
            "--cmake-args -DCMAKE_BUILD_TYPE=Release"
        )
        run(["docker", "network", "create", network])
        run([
            "docker", "run", "-d",
            "--name", router_name,
            "--network", network,
            "-v", f"{root}:/work",
            "-w", "/work",
            image,
            "bash", "-lc",
            "source /opt/ros/jazzy/setup.bash && "
            f"source {install_base}/setup.bash && "
            f"{install_base}/rmw_fleetqox_cpp/lib/rmw_fleetqox_cpp/fleetrmw_udp_router_probe "
            f"--bind 0.0.0.0:{router_port} "
            "--expected-frames 0 --expected-service-frames 2 "
            "--expected-graph-advertisements 2 --post-satisfaction-ms 500 "
            "--timeout-ms 12000",
        ])
        run([
            "docker", "run", "-d",
            "--name", service_name,
            "--network", network,
            "-v", f"{root}:/work",
            "-w", "/work",
            image,
            "bash", "-lc",
            "source /opt/ros/jazzy/setup.bash && "
            f"source {install_base}/setup.bash && "
            "export RMW_IMPLEMENTATION=rmw_fleetqox_cpp && "
            f"FLEETQOX_RMW_BIND=0.0.0.0:{service_port} "
            f"FLEETQOX_RMW_PEERS={router_name}:{router_port} "
            f"{install_base}/rmw_fleetqox_cpp/lib/rmw_fleetqox_cpp/fleetrmw_rcl_service_node "
            f"--service {shlex.quote(service)} --hold-ms 10000 "
            f"--response-delay-ms {response_delay_ms}",
        ])
        time.sleep(0.8)
        client = docker_shell(
            "source /opt/ros/jazzy/setup.bash && "
            f"source {install_base}/setup.bash && "
            "export RMW_IMPLEMENTATION=rmw_fleetqox_cpp && "
            "FLEETQOX_RMW_BIND=0.0.0.0:0 "
            f"FLEETQOX_RMW_PEERS={router_name}:{router_port} "
            f"timeout {call_timeout:g} ros2 service call {shlex.quote(service)} "
            f"{DEFAULT_TYPE} '{{data: true}}'",
            "--network", network,
            check=False,
        )
        service_rc = int(run(["docker", "wait", service_name]).stdout.strip())
        router_rc = int(run(["docker", "wait", router_name]).stdout.strip())
        service_logs = run(["docker", "logs", service_name], check=False).stdout.strip()
        router_logs = run(["docker", "logs", router_name], check=False).stdout.strip()
        service_summary = parse_last_json(service_logs)
        router_summary = parse_last_json(router_logs)
        timed_out = client.returncode == 124
        server_saw_request = int(service_summary.get("request_count", 0)) >= 1
        response_found = "Response:" in client.stdout or "success=True" in client.stdout
        status = (
            timed_out
            and service_rc == 0
            and router_rc == 0
            and server_saw_request
            and not response_found
            and service_summary.get("status") == "ok"
            and int(service_summary.get("response_delay_ms", -1)) == response_delay_ms
            and router_summary.get("status") == "ok"
            and int(router_summary.get("service_frames", 0)) >= 2
            and int(router_summary.get("service_forwarded", 0)) >= 2
            and int(router_summary.get("graph_services", 0)) >= 1
            and int(router_summary.get("graph_clients", 0)) >= 1
        )
        return {
            "schema_version": SCHEMA_VERSION,
            "status": "ok" if status else "failed",
            "service": service,
            "response_delay_ms": response_delay_ms,
            "call_timeout": call_timeout,
            "timed_out": timed_out,
            "server_saw_request": server_saw_request,
            "response_found": response_found,
            "service_call_returncode": client.returncode,
            "service_returncode": service_rc,
            "router_returncode": router_rc,
            "service_call_stdout": client.stdout,
            "service_call_stderr": client.stderr,
            "service_node": service_summary,
            "router": router_summary,
            "service_logs": service_logs,
            "router_logs": router_logs,
        }
    except subprocess.CalledProcessError as exc:
        return {
            "schema_version": SCHEMA_VERSION,
            "status": "failed",
            "returncode": exc.returncode,
            "stdout": exc.stdout,
            "stderr": exc.stderr,
        }
    finally:
        run(["docker", "rm", "-f", router_name, service_name], check=False)
        run(["docker", "network", "rm", network], check=False)
        docker_shell(f"rm -rf {build_base} {install_base} {log_base}", check=False)


if __name__ == "__main__":
    raise SystemExit(main())

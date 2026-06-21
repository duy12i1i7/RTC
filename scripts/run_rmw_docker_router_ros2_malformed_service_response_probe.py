"""Run a router-mediated malformed ROS 2 service-response probe for FleetRMW."""

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


SCHEMA_VERSION = "fleetrmw.rmw_router_ros2_malformed_service_response_probe.v1"
DEFAULT_IMAGE = "ros:jazzy-ros-base"
DEFAULT_SERVICE = "/fleetqox/router_set_bool_malformed"
DEFAULT_TYPE = "std_srvs/srv/SetBool"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--image", default=DEFAULT_IMAGE)
    parser.add_argument("--service", default=DEFAULT_SERVICE)
    parser.add_argument("--call-timeout", type=float, default=6.0)
    parser.add_argument(
        "--summary-json",
        default="results_rmw_socket/docker_router_ros2_malformed_service_response_probe_summary.json",
    )
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    summary = run_probe(
        root=ROOT,
        image=args.image,
        service=args.service,
        call_timeout=max(args.call_timeout, 0.1),
    )
    output = ROOT / args.summary_json
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(summary, sort_keys=True) + "\n", encoding="utf-8")

    if args.json:
        print(json.dumps(summary, sort_keys=True))
    else:
        print("fleetrmw-router-ros2-malformed-service-response-probe")
        print(f"  status: {summary['status']}")
        print(f"  diagnostic_observed: {summary.get('diagnostic_observed')}")
        print(f"  response_found: {summary.get('response_found')}")
        print(f"  router_service_frames: {summary.get('router', {}).get('service_frames')}")
    return 0 if summary["status"] == "ok" else 1


def run_probe(
    *,
    root: Path,
    image: str,
    service: str,
    call_timeout: float,
) -> dict[str, Any]:
    suffix = str(os.getpid())
    network = f"fleetrmw-svc-malformed-net-{suffix}"
    router_name = f"fleetrmw-svc-malformed-router-{suffix}"
    service_name = f"fleetrmw-svc-malformed-server-{suffix}"
    build_base = "/work/.tmp_fleetrmw_service_malformed_router_build"
    install_base = "/work/.tmp_fleetrmw_service_malformed_router_install"
    log_base = "/work/.tmp_fleetrmw_service_malformed_router_log"
    router_port = 49660
    service_port = 49661

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
            "--timeout-ms 10000",
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
            "--malformed-response --exit-after-request",
        ])
        time.sleep(0.8)
        client = docker_shell(
            "source /opt/ros/jazzy/setup.bash && "
            f"source {install_base}/setup.bash && "
            "export RMW_IMPLEMENTATION=rmw_fleetqox_cpp && "
            "FLEETQOX_RMW_TRACE_SERVICE=1 "
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
        client_output = client.stdout + "\n" + client.stderr
        response_found = "Response:" in client.stdout or "success=True" in client.stdout
        diagnostic_markers = (
            "failed to deserialize service response",
            "failed to take response",
            "take_response_deserialize_failed",
            "RMW_RET_UNSUPPORTED",
            "rcl_take_response",
        )
        diagnostic_observed = any(marker in client_output for marker in diagnostic_markers)
        client_failed_cleanly = client.returncode not in (0, 124)
        status = (
            service_rc == 0
            and router_rc == 0
            and int(service_summary.get("request_count", 0)) >= 1
            and service_summary.get("malformed_response") is True
            and not response_found
            and diagnostic_observed
            and client_failed_cleanly
            and router_summary.get("status") == "ok"
            and int(router_summary.get("service_frames", 0)) >= 2
            and int(router_summary.get("service_forwarded", 0)) >= 2
        )
        return {
            "schema_version": SCHEMA_VERSION,
            "status": "ok" if status else "failed",
            "service": service,
            "call_timeout": call_timeout,
            "diagnostic_observed": diagnostic_observed,
            "client_failed_cleanly": client_failed_cleanly,
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

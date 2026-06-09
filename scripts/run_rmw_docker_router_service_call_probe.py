"""Run a Docker router-mediated ROS 2 service-call probe for rmw_fleetqox_cpp."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import subprocess
from typing import Any


SCHEMA_VERSION = "fleetrmw.rmw_router_service_call_probe.v1"
DEFAULT_IMAGE = "ros:jazzy-ros-base"
DEFAULT_SERVICE = "/fleetqox/set_bool"
DEFAULT_TYPE = "std_srvs/srv/SetBool"
EXPECTED_MESSAGE = "fleetqox set_bool accepted"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--image", default=DEFAULT_IMAGE)
    parser.add_argument("--service", default=DEFAULT_SERVICE)
    parser.add_argument("--summary-json", default="results_rmw_socket/docker_router_service_call_probe_summary.json")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    root = Path(__file__).resolve().parents[1]
    summary = run_probe(root=root, image=args.image, service=args.service)
    summary_path = root / args.summary_json
    summary_path.parent.mkdir(parents=True, exist_ok=True)
    summary_path.write_text(json.dumps(summary, sort_keys=True) + "\n", encoding="utf-8")

    if args.json:
        print(json.dumps(summary, sort_keys=True))
    else:
        print("fleetrmw-router-service-call-probe")
        print(f"  status: {summary['status']}")
        print(f"  response_found: {summary['response_found']}")
        print(f"  router_service_frames: {summary.get('router', {}).get('service_frames')}")
    return 0 if summary["status"] == "ok" else 1


def run_probe(*, root: Path, image: str, service: str) -> dict[str, Any]:
    suffix = str(os.getpid())
    network = f"fleetrmw-svc-net-{suffix}"
    router_name = f"fleetrmw-svc-router-{suffix}"
    service_name = f"fleetrmw-svc-server-{suffix}"
    build_base = "/work/.tmp_fleetrmw_service_router_build"
    install_base = "/work/.tmp_fleetrmw_service_router_install"
    log_base = "/work/.tmp_fleetrmw_service_router_log"

    def run(cmd: list[str], *, check: bool = True) -> subprocess.CompletedProcess[str]:
        return subprocess.run(cmd, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=check)

    def docker_shell(command: str, *extra: str, check: bool = True) -> subprocess.CompletedProcess[str]:
        return run([
            "docker", "run", *extra,
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

        router = run([
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
            "--bind 0.0.0.0:48300 "
            "--expected-frames 0 "
            "--expected-service-frames 2 "
            "--expected-graph-advertisements 2 "
            "--timeout-ms 10000",
        ])
        router_container = router.stdout.strip()

        server = run([
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
            "FLEETQOX_RMW_BIND=0.0.0.0:48301 "
            "FLEETQOX_RMW_PEERS=fleetrmw-svc-router-" + suffix + ":48300 "
            f"{install_base}/rmw_fleetqox_cpp/lib/rmw_fleetqox_cpp/fleetrmw_rcl_service_node "
            f"--service {service} --hold-ms 9000",
        ])
        service_container = server.stdout.strip()

        client = docker_shell(
            "source /opt/ros/jazzy/setup.bash && "
            f"source {install_base}/setup.bash && "
            "export RMW_IMPLEMENTATION=rmw_fleetqox_cpp && "
            "sleep 0.8 && "
            "FLEETQOX_RMW_BIND=0.0.0.0:48302 "
            "FLEETQOX_RMW_PEERS=fleetrmw-svc-router-" + suffix + ":48300 "
            f"timeout 8 ros2 service call {service} {DEFAULT_TYPE} '{{data: true}}'",
            "--network", network,
            check=False,
        )

        service_wait = run(["docker", "wait", service_container], check=False)
        router_wait = run(["docker", "wait", router_container], check=False)
        service_logs = run(["docker", "logs", service_container], check=False)
        router_logs = run(["docker", "logs", router_container], check=False)

        router_summary = parse_last_json(router_logs.stdout)
        service_summary = parse_last_json(service_logs.stdout)
        response_found = "success=True" in client.stdout and EXPECTED_MESSAGE in client.stdout
        summary = {
            "schema_version": SCHEMA_VERSION,
            "status": "pending",
            "docker_network": network,
            "service_name": service,
            "expected_type": DEFAULT_TYPE,
            "expected_message": EXPECTED_MESSAGE,
            "response_found": response_found,
            "client_returncode": client.returncode,
            "client_stdout": client.stdout,
            "client_stderr": client.stderr,
            "service_returncode": int(service_wait.stdout.strip() or "999"),
            "router_returncode": int(router_wait.stdout.strip() or "999"),
            "service_node": service_summary,
            "router": router_summary,
            "service_logs": service_logs.stdout,
            "router_logs": router_logs.stdout,
        }
        summary["status"] = "ok" if (
            client.returncode == 0 and
            summary["service_returncode"] == 0 and
            summary["router_returncode"] == 0 and
            response_found and
            service_summary.get("request_count", 0) >= 1 and
            router_summary.get("service_frames", 0) >= 2 and
            router_summary.get("service_forwarded", 0) >= 2 and
            router_summary.get("graph_services", 0) >= 1 and
            router_summary.get("graph_clients", 0) >= 1
        ) else "failed"
        return summary
    except subprocess.CalledProcessError as exc:
        return {
            "schema_version": SCHEMA_VERSION,
            "status": "failed",
            "docker_network": network,
            "returncode": exc.returncode,
            "stdout": exc.stdout,
            "stderr": exc.stderr,
        }
    finally:
        run(["docker", "rm", "-f", router_name, service_name], check=False)
        run(["docker", "network", "rm", network], check=False)
        docker_shell(f"rm -rf {build_base} {install_base} {log_base}", check=False)


def parse_last_json(output: str) -> dict[str, Any]:
    for line in reversed(output.splitlines()):
        stripped = line.strip()
        if stripped.startswith("{"):
            try:
                return json.loads(stripped)
            except json.JSONDecodeError:
                return {"status": "parse_failed", "raw": stripped}
    return {"status": "missing", "raw": output}


if __name__ == "__main__":
    raise SystemExit(main())

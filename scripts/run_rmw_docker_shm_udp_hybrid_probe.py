"""Verify FleetRMW local SHM plus remote UDP routing and application de-duplication."""

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

from scripts.run_rmw_docker_shared_memory_probe import parse_last_json


SCHEMA_VERSION = "fleetrmw.docker_shm_udp_hybrid_probe.v1"
DEFAULT_IMAGE = "localhost/fleetrmw/rmw-netem:jazzy"


def run(command: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        command,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )


def run_probe(*, root: Path, image: str, payload_size: int) -> dict[str, Any]:
    suffix = str(os.getpid())
    network = f"fleetrmw-hybrid-net-{suffix}"
    router_name = f"fleetrmw-hybrid-router-{suffix}"
    subscriber_name = f"fleetrmw-hybrid-sub-{suffix}"
    shm_name = f"/fleetrmw_hybrid_{suffix}"
    build_base = "/work/.tmp_fleetrmw_hybrid_build"
    install_base = "/work/.tmp_fleetrmw_hybrid_install"
    log_base = "/work/.tmp_fleetrmw_hybrid_log"
    endpoint_binary = (
        f"{install_base}/rmw_fleetqox_cpp/lib/rmw_fleetqox_cpp/"
        "fleetrmw_interprocess_pubsub_probe"
    )
    router_binary = (
        f"{install_base}/rmw_fleetqox_cpp/lib/rmw_fleetqox_cpp/"
        "fleetrmw_udp_router_probe"
    )
    topic = "/fleetqox/hybrid_probe"
    try:
        network_create = run(["docker", "network", "create", network])
        if network_create.returncode != 0:
            return {
                "schema_version": SCHEMA_VERSION,
                "status": "failed",
                "stage": "network_create",
                "stderr": network_create.stderr,
            }
        build = run(
            [
                "docker", "run", "--rm", "--entrypoint", "bash",
                "-v", f"{root}:/work", "-w", "/work", image, "-lc",
                "source /opt/ros/jazzy/setup.bash && "
                f"rm -rf {build_base} {install_base} {log_base} && "
                f"colcon --log-base {log_base} build --base-paths ros2_ws/src "
                "--packages-select rmw_fleetqox_cpp "
                f"--build-base {build_base} --install-base {install_base} "
                "--cmake-args -DCMAKE_BUILD_TYPE=Release",
            ]
        )
        if build.returncode != 0:
            return {
                "schema_version": SCHEMA_VERSION,
                "status": "failed",
                "stage": "build",
                "stdout": build.stdout,
                "stderr": build.stderr,
            }

        router = run(
            [
                "docker", "run", "-d", "--name", router_name,
                "--network", network, "--entrypoint", "bash",
                "-v", f"{root}:/work", "-w", "/work", image, "-lc",
                "source /opt/ros/jazzy/setup.bash && "
                f"source {install_base}/setup.bash && "
                f"{router_binary} --bind 0.0.0.0:49900 "
                "--expected-frames 1 --expected-route-advertisements 1 "
                "--expected-graph-advertisements 2 --timeout-ms 8000 "
                "--post-satisfaction-ms 500",
            ]
        )
        if router.returncode != 0:
            return {"schema_version": SCHEMA_VERSION, "status": "failed", "stage": "router_start"}
        time.sleep(0.5)

        subscriber = run(
            [
                "docker", "run", "-d", "--name", subscriber_name,
                "--network", network, "--ipc", "host", "--entrypoint", "bash",
                "-v", f"{root}:/work", "-w", "/work", image, "-lc",
                "source /opt/ros/jazzy/setup.bash && "
                f"source {install_base}/setup.bash && "
                "FLEETQOX_RMW_LOCAL_TRANSPORT=shm "
                f"FLEETQOX_RMW_SHM_NAME={shm_name} "
                "FLEETQOX_RMW_SHM_FALLBACK_UDP=0 FLEETQOX_RMW_SHM_UNLINK_OWNER=1 "
                f"FLEETQOX_RMW_BIND=0.0.0.0:49901 FLEETQOX_RMW_PEERS={router_name}:49900 "
                f"{endpoint_binary} --mode subscriber --topic {topic} --timeout-ms 8000 "
                f"--post-take-ms 800 --payload hybrid-data --payload-size {payload_size} "
                "--payload-fill h --payload-output-limit 64",
            ]
        )
        if subscriber.returncode != 0:
            return {"schema_version": SCHEMA_VERSION, "status": "failed", "stage": "subscriber_start"}
        time.sleep(1.0)

        publisher = run(
            [
                "docker", "run", "--rm", "--network", network, "--ipc", "host",
                "--entrypoint", "bash", "-v", f"{root}:/work", "-w", "/work", image, "-lc",
                "source /opt/ros/jazzy/setup.bash && "
                f"source {install_base}/setup.bash && "
                "FLEETQOX_RMW_LOCAL_TRANSPORT=shm "
                f"FLEETQOX_RMW_SHM_NAME={shm_name} FLEETQOX_RMW_SHM_FALLBACK_UDP=0 "
                f"FLEETQOX_RMW_BIND=0.0.0.0:49902 FLEETQOX_RMW_PEERS={router_name}:49900 "
                f"{endpoint_binary} --mode publisher --topic {topic} "
                f"--pre-publish-ms 200 --payload hybrid-data --payload-size {payload_size} "
                "--payload-fill h --payload-output-limit 64",
            ]
        )
        subscriber_wait = run(["docker", "wait", subscriber_name])
        router_wait = run(["docker", "wait", router_name])
        subscriber_returncode = int(subscriber_wait.stdout.strip() or -1)
        router_returncode = int(router_wait.stdout.strip() or -1)
        subscriber_logs = run(["docker", "logs", subscriber_name])
        router_logs = run(["docker", "logs", router_name])
        publisher_result = parse_last_json(publisher.stdout)
        subscriber_result = parse_last_json(subscriber_logs.stdout)
        router_result = parse_last_json(router_logs.stdout)
        ok = (
            publisher.returncode == 0
            and subscriber_returncode == 0
            and router_returncode == 0
            and publisher_result.get("status") == "ok"
            and subscriber_result.get("status") == "ok"
            and router_result.get("status") == "ok"
            and publisher_result.get("transport_mode") == "shm_udp_hybrid"
            and subscriber_result.get("transport_mode") == "shm_udp_hybrid"
            and publisher_result.get("network_flow_endpoint_count") == 1
            and subscriber_result.get("network_flow_endpoint_count") == 1
            and publisher_result.get("shared_memory_frames_sent", 0) >= 1
            and subscriber_result.get("shared_memory_frames_received", 0) >= 2
            and subscriber_result.get("duplicate_data_frames_deduped", 0) >= 1
            and subscriber_result.get("shared_memory_overwritten_frames") == 0
            and subscriber_result.get("taken") is True
            and subscriber_result.get("bytes") == payload_size
            and router_result.get("forwarded_frames", 0) >= 1
            and router_result.get("invalid_frames") == 0
        )
        return {
            "schema_version": SCHEMA_VERSION,
            "status": "ok" if ok else "failed",
            "image": image,
            "payload_size": payload_size,
            "topic": topic,
            "publisher_returncode": publisher.returncode,
            "subscriber_returncode": subscriber_returncode,
            "router_returncode": router_returncode,
            "publisher": publisher_result,
            "subscriber": subscriber_result,
            "router": router_result,
            "publisher_stderr": publisher.stderr,
            "subscriber_stderr": subscriber_logs.stderr,
            "router_stderr": router_logs.stderr,
        }
    finally:
        for container in (subscriber_name, router_name):
            subprocess.run(
                ["docker", "rm", "-f", container],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                check=False,
            )
        subprocess.run(
            ["docker", "network", "rm", network],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=False,
        )
        subprocess.run(
            [
                "docker", "run", "--rm", "--entrypoint", "bash",
                "-v", f"{root}:/work", "-w", "/work", image, "-lc",
                f"rm -rf {build_base} {install_base} {log_base}",
            ],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=False,
        )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--image", default=DEFAULT_IMAGE)
    parser.add_argument("--payload-size", type=int, default=20000)
    parser.add_argument(
        "--summary-json",
        default="results_rmw_socket/docker_shm_udp_hybrid_probe_summary.json",
    )
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    summary = run_probe(root=root, image=args.image, payload_size=max(args.payload_size, 1))
    output = root / args.summary_json
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    if args.json:
        print(json.dumps(summary, sort_keys=True))
    else:
        print(f"status={summary['status']} payload_size={summary.get('payload_size')}")
    return 0 if summary["status"] == "ok" else 1


if __name__ == "__main__":
    raise SystemExit(main())

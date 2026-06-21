"""Build and verify FleetRMW POSIX shared-memory transport across two containers."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import subprocess
import time
from typing import Any


SCHEMA_VERSION = "fleetrmw.docker_shared_memory_probe.v1"
DEFAULT_IMAGE = "localhost/fleetrmw/rmw-netem:jazzy"


def parse_last_json(output: str) -> dict[str, Any]:
    for line in reversed(output.splitlines()):
        try:
            value = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(value, dict):
            return value
    return {}


def run_probe(*, root: Path, image: str, payload_size: int) -> dict[str, Any]:
    suffix = str(os.getpid())
    subscriber_name = f"fleetrmw-shm-sub-{suffix}"
    shm_name = f"/fleetrmw_probe_{suffix}"
    build_base = "/work/.tmp_fleetrmw_shm_build"
    install_base = "/work/.tmp_fleetrmw_shm_install"
    log_base = "/work/.tmp_fleetrmw_shm_log"
    binary = (
        f"{install_base}/rmw_fleetqox_cpp/lib/rmw_fleetqox_cpp/"
        "fleetrmw_interprocess_pubsub_probe"
    )
    fallback_binary = (
        f"{install_base}/rmw_fleetqox_cpp/lib/rmw_fleetqox_cpp/"
        "fleetrmw_serialized_pubsub_probe"
    )
    common_environment = (
        "FLEETQOX_RMW_LOCAL_TRANSPORT=shm "
        f"FLEETQOX_RMW_SHM_NAME={shm_name} "
        "FLEETQOX_RMW_SHM_FALLBACK_UDP=0 "
    )
    try:
        build = subprocess.run(
            [
                "docker", "run", "--rm", "--entrypoint", "bash",
                "-v", f"{root}:/work", "-w", "/work", image, "-lc",
                "source /opt/ros/jazzy/setup.bash && "
                f"rm -rf {build_base} {install_base} {log_base} && "
                f"colcon --log-base {log_base} build --base-paths ros2_ws/src "
                "--packages-select rmw_fleetqox_cpp "
                f"--build-base {build_base} --install-base {install_base} "
                "--cmake-args -DCMAKE_BUILD_TYPE=Release",
            ],
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
        )
        if build.returncode != 0:
            return {
                "schema_version": SCHEMA_VERSION,
                "status": "failed",
                "stage": "build",
                "stdout": build.stdout,
                "stderr": build.stderr,
            }

        subscriber = subprocess.run(
            [
                "docker", "run", "-d", "--name", subscriber_name,
                "--ipc", "host", "--entrypoint", "bash",
                "-v", f"{root}:/work", "-w", "/work", image, "-lc",
                "source /opt/ros/jazzy/setup.bash && "
                f"source {install_base}/setup.bash && "
                f"{common_environment}FLEETQOX_RMW_SHM_UNLINK_OWNER=1 "
                f"{binary} --mode subscriber --timeout-ms 8000 "
                f"--payload fleetqox-shm --payload-size {payload_size} "
                "--payload-fill s --payload-output-limit 64",
            ],
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
        )
        if subscriber.returncode != 0:
            return {
                "schema_version": SCHEMA_VERSION,
                "status": "failed",
                "stage": "subscriber_start",
                "stdout": subscriber.stdout,
                "stderr": subscriber.stderr,
            }
        time.sleep(1.0)

        publisher = subprocess.run(
            [
                "docker", "run", "--rm", "--ipc", "host", "--entrypoint", "bash",
                "-v", f"{root}:/work", "-w", "/work", image, "-lc",
                "source /opt/ros/jazzy/setup.bash && "
                f"source {install_base}/setup.bash && "
                f"{common_environment}{binary} --mode publisher "
                f"--payload fleetqox-shm --payload-size {payload_size} "
                "--payload-fill s --pre-publish-ms 100 --payload-output-limit 64",
            ],
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
        )
        waited = subprocess.run(
            ["docker", "wait", subscriber_name],
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
        )
        subscriber_returncode = int(waited.stdout.strip()) if waited.stdout.strip() else -1
        subscriber_logs = subprocess.run(
            ["docker", "logs", subscriber_name],
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
        )
        publisher_result = parse_last_json(publisher.stdout)
        subscriber_result = parse_last_json(subscriber_logs.stdout)
        fallback = subprocess.run(
            [
                "docker", "run", "--rm", "--entrypoint", "bash",
                "-v", f"{root}:/work", "-w", "/work", image, "-lc",
                "source /opt/ros/jazzy/setup.bash && "
                f"source {install_base}/setup.bash && "
                "FLEETQOX_RMW_LOCAL_TRANSPORT=shm "
                "FLEETQOX_RMW_SHM_NAME=invalid_name "
                "FLEETQOX_RMW_SHM_FALLBACK_UDP=1 "
                f"{fallback_binary}",
            ],
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
        )
        fallback_result = parse_last_json(fallback.stdout)
        ok = (
            publisher.returncode == 0
            and subscriber_returncode == 0
            and publisher_result.get("status") == "ok"
            and subscriber_result.get("status") == "ok"
            and publisher_result.get("transport_mode") == "shm"
            and subscriber_result.get("transport_mode") == "shm"
            and publisher_result.get("peer_count") == 0
            and subscriber_result.get("peer_count") == 0
            and publisher_result.get("network_flow_endpoint_count") == 0
            and subscriber_result.get("network_flow_endpoint_count") == 0
            and publisher_result.get("shared_memory_frames_sent", 0) >= 1
            and subscriber_result.get("shared_memory_frames_received", 0) >= 1
            and subscriber_result.get("shared_memory_overwritten_frames") == 0
            and subscriber_result.get("taken") is True
            and subscriber_result.get("bytes") == payload_size
            and payload_size > 65507
            and fallback.returncode == 0
            and fallback_result.get("status") == "ok"
            and fallback_result.get("transport_mode") == "udp_fallback"
        )
        return {
            "schema_version": SCHEMA_VERSION,
            "status": "ok" if ok else "failed",
            "image": image,
            "ipc_mode": "host",
            "shm_name": shm_name,
            "payload_size": payload_size,
            "payload_exceeds_udp_limit": payload_size > 65507,
            "publisher_returncode": publisher.returncode,
            "subscriber_returncode": subscriber_returncode,
            "publisher": publisher_result,
            "subscriber": subscriber_result,
            "udp_fallback": fallback_result,
            "udp_fallback_returncode": fallback.returncode,
            "publisher_stderr": publisher.stderr,
            "subscriber_stderr": subscriber_logs.stderr,
            "udp_fallback_stderr": fallback.stderr,
        }
    finally:
        subprocess.run(
            ["docker", "rm", "-f", subscriber_name],
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
    parser.add_argument("--payload-size", type=int, default=100000)
    parser.add_argument(
        "--summary-json",
        default="results_rmw_socket/docker_shared_memory_probe_summary.json",
    )
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    summary = run_probe(
        root=root,
        image=args.image,
        payload_size=max(args.payload_size, 65508),
    )
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

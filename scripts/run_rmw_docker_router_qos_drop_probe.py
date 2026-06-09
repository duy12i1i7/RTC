"""Run a Docker router QoS-lifespan drop probe for rmw_fleetqox_cpp."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import subprocess
import time
from typing import Any


SCHEMA_VERSION = "fleetrmw.rmw_router_qos_drop_probe.v1"
DEFAULT_IMAGE = "ros:jazzy-ros-base"
DEFAULT_TOPIC = "/fleetqox/router_qos_lifespan_probe"
DEFAULT_PAYLOAD = "fleetqox-router-qos-expired"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--image", default=DEFAULT_IMAGE)
    parser.add_argument("--topic", default=DEFAULT_TOPIC)
    parser.add_argument("--payload", default=DEFAULT_PAYLOAD)
    parser.add_argument("--lifespan-ms", type=int, default=5)
    parser.add_argument("--forward-delay-ms", type=int, default=30)
    parser.add_argument("--summary-json", default="results_rmw_socket/docker_router_qos_drop_probe_summary.json")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    root = Path(__file__).resolve().parents[1]
    summary = run_probe(
        root=root,
        image=args.image,
        topic=args.topic,
        payload=args.payload,
        lifespan_ms=args.lifespan_ms,
        forward_delay_ms=args.forward_delay_ms,
    )
    summary_path = root / args.summary_json
    summary_path.parent.mkdir(parents=True, exist_ok=True)
    summary_path.write_text(json.dumps(summary, sort_keys=True) + "\n", encoding="utf-8")

    if args.json:
        print(json.dumps(summary, sort_keys=True))
    else:
        print("fleetrmw-router-qos-drop-probe")
        print(f"  status: {summary['status']}")
        print(f"  router_qos_dropped: {summary.get('router', {}).get('qos_dropped_frames')}")
        print(f"  subscriber_taken: {summary.get('subscriber', {}).get('taken')}")
    return 0 if summary["status"] == "ok" else 1


def run_probe(
    *,
    root: Path,
    image: str,
    topic: str,
    payload: str,
    lifespan_ms: int,
    forward_delay_ms: int,
) -> dict[str, Any]:
    suffix = str(os.getpid())
    network = f"fleetrmw-qos-net-{suffix}"
    subscriber_name = f"fleetrmw-qos-sub-{suffix}"
    router_name = f"fleetrmw-qos-router-{suffix}"
    build_base = "/work/.tmp_fleetrmw_router_qos_build"
    install_base = "/work/.tmp_fleetrmw_router_qos_install"
    log_base = "/work/.tmp_fleetrmw_router_qos_log"
    endpoint_binary = f"{install_base}/rmw_fleetqox_cpp/lib/rmw_fleetqox_cpp/fleetrmw_interprocess_pubsub_probe"
    router_binary = f"{install_base}/rmw_fleetqox_cpp/lib/rmw_fleetqox_cpp/fleetrmw_udp_router_probe"

    try:
        run(["docker", "network", "create", network])
        docker_shell(
            root,
            image,
            "source /opt/ros/jazzy/setup.bash && "
            f"rm -rf {build_base} {install_base} {log_base} && "
            "colcon "
            f"--log-base {log_base} "
            "build --base-paths ros2_ws/src --packages-select rmw_fleetqox_cpp "
            f"--build-base {build_base} --install-base {install_base} "
            "--cmake-args -DCMAKE_BUILD_TYPE=Release",
        )
        start_container(
            root=root,
            image=image,
            name=router_name,
            network=network,
            command=(
                f"source /opt/ros/jazzy/setup.bash && source {install_base}/setup.bash && "
                f"{router_binary} --bind 0.0.0.0:48320 "
                "--expected-frames 1 --expected-route-advertisements 1 "
                "--expected-graph-advertisements 2 --expected-qos-drops 1 "
                f"--forward-delay-ms {forward_delay_ms} --timeout-ms 7000"
            ),
        )
        time.sleep(0.5)
        start_container(
            root=root,
            image=image,
            name=subscriber_name,
            network=network,
            command=(
                f"source /opt/ros/jazzy/setup.bash && source {install_base}/setup.bash && "
                f"FLEETQOX_RMW_BIND=0.0.0.0:48321 FLEETQOX_RMW_PEERS={router_name}:48320 "
                f"{endpoint_binary} --mode subscriber --topic {topic} --payload {payload} "
                "--expect-taken false --timeout-ms 1500"
            ),
        )
        time.sleep(0.8)
        publisher = run(
            [
                "docker", "run", "--rm",
                "--network", network,
                "-v", f"{root}:/work",
                "-w", "/work",
                image,
                "bash", "-lc",
                (
                    f"source /opt/ros/jazzy/setup.bash && source {install_base}/setup.bash && "
                    f"FLEETQOX_RMW_BIND=0.0.0.0:0 FLEETQOX_RMW_PEERS={router_name}:48320 "
                    f"{endpoint_binary} --mode publisher --topic {topic} --payload {payload} "
                    f"--lifespan-ms {lifespan_ms}"
                ),
            ],
        )
        router_returncode = int(run(["docker", "wait", router_name]).stdout.strip())
        subscriber_returncode = int(run(["docker", "wait", subscriber_name]).stdout.strip())
        router_log = run(["docker", "logs", router_name]).stdout.strip()
        subscriber_log = run(["docker", "logs", subscriber_name]).stdout.strip()

        publisher_result = json.loads(publisher.stdout)
        router_result = json.loads(router_log)
        subscriber_result = json.loads(subscriber_log)
        status = (
            publisher.returncode == 0 and
            router_returncode == 0 and
            subscriber_returncode == 0 and
            publisher_result.get("status") == "ok" and
            router_result.get("status") == "ok" and
            subscriber_result.get("status") == "ok" and
            router_result.get("received_frames") == 1 and
            router_result.get("qos_dropped_frames") == 1 and
            router_result.get("forwarded_frames") == 0 and
            subscriber_result.get("taken") is False
        )
        return {
            "schema_version": SCHEMA_VERSION,
            "status": "ok" if status else "failed",
            "docker_network": network,
            "topic": topic,
            "payload": payload,
            "lifespan_ms": lifespan_ms,
            "forward_delay_ms": forward_delay_ms,
            "publisher_returncode": publisher.returncode,
            "router_returncode": router_returncode,
            "subscriber_returncode": subscriber_returncode,
            "publisher": publisher_result,
            "router": router_result,
            "subscriber": subscriber_result,
        }
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
        run(["docker", "rm", "-f", subscriber_name, router_name], check=False)
        run(["docker", "network", "rm", network], check=False)
        docker_shell(root, image, f"rm -rf {build_base} {install_base} {log_base}", check=False)


def run(cmd: list[str], *, check: bool = True) -> subprocess.CompletedProcess[str]:
    return subprocess.run(cmd, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=check)


def docker_shell(
  root: Path,
  image: str,
  command: str,
  *,
  check: bool = True,
) -> subprocess.CompletedProcess[str]:
    return run([
        "docker", "run", "--rm",
        "-v", f"{root}:/work",
        "-w", "/work",
        image,
        "bash", "-lc", command,
    ], check=check)


def start_container(*, root: Path, image: str, name: str, network: str, command: str) -> str:
    result = run([
        "docker", "run", "-d",
        "--name", name,
        "--network", network,
        "-v", f"{root}:/work",
        "-w", "/work",
        image,
        "bash", "-lc", command,
    ])
    return result.stdout.strip()


if __name__ == "__main__":
    raise SystemExit(main())

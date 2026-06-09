"""Run a Docker multi-container FleetRMW router probe.

The probe starts four ROS 2 containers on a private Docker network:

- a subscriber endpoint bound on UDP port 48201;
- a FleetRMW UDP router bound on UDP port 48200;
- a graph observer endpoint bound on UDP port 48202;
- an ephemeral publisher endpoint that only knows the router hostname.

The subscriber first advertises its topic route to the router through
`fleetrmw.route_advertisement.v1`.  Publisher/subscriber creation also emits
`fleetrmw.graph_advertisement.v1`, so the router can observe the remote
pub/sub graph.  The publisher then emits a serialized `fleetrmw.data_frame.v1`
through `rmw_publish_serialized_message`; the router learns the route, decodes
and forwards the frame; the subscriber takes the payload through
`rmw_take_serialized_message`.  In parallel, the router forwards graph
advertisements to the observer, and the observer validates the remote topic
through ROS 2 graph APIs without creating a local publisher or subscription
on that topic.
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import subprocess
import time
from typing import Any


SCHEMA_VERSION = "fleetrmw.rmw_multicontainer_router_probe.v1"
DEFAULT_IMAGE = "ros:jazzy-ros-base"
DEFAULT_TOPIC = "/fleetqox/multicontainer_router_probe"
DEFAULT_PAYLOAD = "fleetqox-multicontainer-router-cdr"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--image", default=DEFAULT_IMAGE)
    parser.add_argument("--topic", default=DEFAULT_TOPIC)
    parser.add_argument("--payload", default=DEFAULT_PAYLOAD)
    parser.add_argument("--summary-json", default="results_rmw_socket/docker_rmw_multicontainer_router_probe_summary.json")
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--keep-temp", action="store_true")
    args = parser.parse_args()

    root = Path(__file__).resolve().parents[1]
    summary = run_probe(
        root=root,
        image=args.image,
        topic=args.topic,
        payload=args.payload,
        keep_temp=args.keep_temp,
    )
    summary_path = root / args.summary_json
    summary_path.parent.mkdir(parents=True, exist_ok=True)
    summary_path.write_text(json.dumps(summary, sort_keys=True) + "\n", encoding="utf-8")

    if args.json:
        print(json.dumps(summary, sort_keys=True))
    else:
        print("fleetrmw-multicontainer-router-probe")
        print(f"  status: {summary['status']}")
        print(f"  router_received: {summary['router']['received_frames']}")
        print(f"  router_forwarded: {summary['router']['forwarded_frames']}")
        print(f"  subscriber_taken: {summary['subscriber']['taken']}")
        print(f"  observer_topic_found: {summary['observer']['topic_found']}")
    return 0 if summary["status"] == "ok" else 1


def run_probe(
    *,
    root: Path,
    image: str,
    topic: str,
    payload: str,
    keep_temp: bool,
) -> dict[str, Any]:
    suffix = str(os.getpid())
    network = f"fleetrmw-net-{suffix}"
    subscriber_name = f"fleetrmw-sub-{suffix}"
    observer_name = f"fleetrmw-observer-{suffix}"
    router_name = f"fleetrmw-router-{suffix}"
    tmp_build = "/work/.tmp_fleetrmw_build"
    tmp_install = "/work/.tmp_fleetrmw_install"
    tmp_log = "/work/.tmp_fleetrmw_log"
    endpoint_binary = f"{tmp_install}/rmw_fleetqox_cpp/lib/rmw_fleetqox_cpp/fleetrmw_interprocess_pubsub_probe"
    router_binary = f"{tmp_install}/rmw_fleetqox_cpp/lib/rmw_fleetqox_cpp/fleetrmw_udp_router_probe"
    observer_binary = f"{tmp_install}/rmw_fleetqox_cpp/lib/rmw_fleetqox_cpp/fleetrmw_remote_graph_probe"

    try:
        run(["docker", "network", "create", network], capture_output=True)
        docker_shell(
            root,
            image,
            "source /opt/ros/jazzy/setup.bash && "
            f"rm -rf {tmp_build} {tmp_install} {tmp_log} && "
            "colcon "
            f"--log-base {tmp_log} "
            "build --base-paths ros2_ws/src --packages-select rmw_fleetqox_cpp "
            f"--build-base {tmp_build} --install-base {tmp_install} "
            "--cmake-args -DCMAKE_BUILD_TYPE=Release",
            capture_output=True,
        )
        start_container(
            root=root,
            image=image,
            name=observer_name,
            network=network,
            command=(
                f"source /opt/ros/jazzy/setup.bash && source {tmp_install}/setup.bash && "
                "FLEETQOX_RMW_BIND=0.0.0.0:48202 "
                f"{observer_binary} "
                f"--topic {topic} --expected-publishers 1 --expected-subscribers 1 --timeout-ms 6000"
            ),
        )
        time.sleep(0.5)
        start_container(
            root=root,
            image=image,
            name=router_name,
            network=network,
            command=(
                f"source /opt/ros/jazzy/setup.bash && source {tmp_install}/setup.bash && "
                f"{router_binary} --bind 0.0.0.0:48200 "
                f"--graph-peers {observer_name}:48202 "
                "--expected-frames 1 --expected-route-advertisements 1 "
                "--expected-graph-advertisements 2 --timeout-ms 6000"
            ),
        )
        time.sleep(0.5)
        start_container(
            root=root,
            image=image,
            name=subscriber_name,
            network=network,
            command=(
                f"source /opt/ros/jazzy/setup.bash && source {tmp_install}/setup.bash && "
                f"FLEETQOX_RMW_BIND=0.0.0.0:48201 FLEETQOX_RMW_PEERS={router_name}:48200 "
                f"{endpoint_binary} "
                f"--mode subscriber --topic {topic} --payload {payload} --timeout-ms 6000"
            ),
        )

        time.sleep(1.0)
        publisher = run(
            [
                "docker", "run", "--rm",
                "--network", network,
                "-v", f"{root}:/work",
                "-w", "/work",
                image,
                "bash", "-lc",
                (
                    f"source /opt/ros/jazzy/setup.bash && source {tmp_install}/setup.bash && "
                    f"FLEETQOX_RMW_BIND=0.0.0.0:0 FLEETQOX_RMW_PEERS={router_name}:48200 "
                    f"{endpoint_binary} --mode publisher --topic {topic} --payload {payload}"
                ),
            ],
            capture_output=True,
        )
        router_returncode = int(run(["docker", "wait", router_name], capture_output=True).stdout.strip())
        subscriber_returncode = int(run(["docker", "wait", subscriber_name], capture_output=True).stdout.strip())
        observer_returncode = int(run(["docker", "wait", observer_name], capture_output=True).stdout.strip())
        router_log = run(["docker", "logs", router_name], capture_output=True).stdout.strip()
        subscriber_log = run(["docker", "logs", subscriber_name], capture_output=True).stdout.strip()
        observer_log = run(["docker", "logs", observer_name], capture_output=True).stdout.strip()

        publisher_result = json.loads(publisher.stdout)
        router_result = json.loads(router_log)
        subscriber_result = json.loads(subscriber_log)
        observer_result = json.loads(observer_log)
        status = (
            publisher.returncode == 0 and
            router_returncode == 0 and
            subscriber_returncode == 0 and
            observer_returncode == 0 and
            publisher_result.get("status") == "ok" and
            router_result.get("status") == "ok" and
            subscriber_result.get("status") == "ok" and
            observer_result.get("status") == "ok" and
            router_result.get("route_advertisements") == 1 and
            router_result.get("learned_routes") == 1 and
            router_result.get("graph_advertisements", 0) >= 2 and
            router_result.get("graph_forwarded", 0) >= 2 and
            router_result.get("graph_publishers") == 1 and
            router_result.get("graph_subscriptions") == 1 and
            observer_result.get("topic_found") is True and
            observer_result.get("publisher_count") == 1 and
            observer_result.get("subscriber_count") == 1
        )
        return {
            "schema_version": SCHEMA_VERSION,
            "status": "ok" if status else "failed",
            "docker_network": network,
            "router_container": router_name,
            "subscriber_container": subscriber_name,
            "observer_container": observer_name,
            "publisher_returncode": publisher.returncode,
            "router_returncode": router_returncode,
            "subscriber_returncode": subscriber_returncode,
            "observer_returncode": observer_returncode,
            "topic": topic,
            "payload": payload,
            "publisher": publisher_result,
            "router": router_result,
            "subscriber": subscriber_result,
            "observer": observer_result,
        }
    finally:
        cleanup(
            root=root,
            image=image,
            network=network,
            containers=[subscriber_name, observer_name, router_name],
            keep_temp=keep_temp,
        )


def start_container(*, root: Path, image: str, name: str, network: str, command: str) -> None:
    run([
        "docker", "run", "-d",
        "--name", name,
        "--network", network,
        "-v", f"{root}:/work",
        "-w", "/work",
        image,
        "bash", "-lc", command,
    ], capture_output=True)


def docker_shell(
    root: Path,
    image: str,
    command: str,
    *,
    capture_output: bool = False,
) -> subprocess.CompletedProcess[str]:
    return run([
        "docker", "run", "--rm",
        "-v", f"{root}:/work",
        "-w", "/work",
        image,
        "bash", "-lc", command,
    ], capture_output=capture_output)


def cleanup(*, root: Path, image: str, network: str, containers: list[str], keep_temp: bool) -> None:
    for container in containers:
        subprocess.run(["docker", "rm", "-f", container], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    subprocess.run(["docker", "network", "rm", network], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    if not keep_temp:
        subprocess.run(
            [
                "docker", "run", "--rm",
                "-v", f"{root}:/work",
                "-w", "/work",
                image,
                "bash", "-lc",
                "rm -rf /work/.tmp_fleetrmw_build /work/.tmp_fleetrmw_install /work/.tmp_fleetrmw_log",
            ],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )


def run(cmd: list[str], *, capture_output: bool = False) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        cmd,
        check=True,
        text=True,
        stdout=subprocess.PIPE if capture_output else None,
        stderr=subprocess.PIPE if capture_output else None,
    )


if __name__ == "__main__":
    raise SystemExit(main())

"""Run a Docker router-mediated ACK/NACK retransmission probe for rmw_fleetqox_cpp."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import subprocess
import time
from typing import Any


SCHEMA_VERSION = "fleetrmw.rmw_router_reliability_probe.v1"
DEFAULT_IMAGE = "ros:jazzy-ros-base"
DEFAULT_TOPIC = "/fleetqox/router_reliability_probe"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--image", default=DEFAULT_IMAGE)
    parser.add_argument("--topic", default=DEFAULT_TOPIC)
    parser.add_argument("--summary-json", default="results_rmw_socket/docker_router_reliability_probe_summary.json")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    root = Path(__file__).resolve().parents[1]
    summary = run_probe(root=root, image=args.image, topic=args.topic)
    summary_path = root / args.summary_json
    summary_path.parent.mkdir(parents=True, exist_ok=True)
    summary_path.write_text(json.dumps(summary, sort_keys=True) + "\n", encoding="utf-8")

    if args.json:
        print(json.dumps(summary, sort_keys=True))
    else:
        print("fleetrmw-router-reliability-probe")
        print(f"  status: {summary['status']}")
        print(f"  router_ack_forwarded: {summary.get('router', {}).get('ack_nack_forwarded')}")
        print(f"  publisher_retransmissions: {summary.get('publisher', {}).get('nack_retransmissions')}")
    return 0 if summary["status"] == "ok" else 1


def run_probe(*, root: Path, image: str, topic: str) -> dict[str, Any]:
    suffix = str(os.getpid())
    network = f"fleetrmw-rel-net-{suffix}"
    router_name = f"fleetrmw-rel-router-{suffix}"
    subscriber_name = f"fleetrmw-rel-sub-{suffix}"
    build_base = "/work/.tmp_fleetrmw_router_reliability_build"
    install_base = "/work/.tmp_fleetrmw_router_reliability_install"
    log_base = "/work/.tmp_fleetrmw_router_reliability_log"
    endpoint_binary = f"{install_base}/rmw_fleetqox_cpp/lib/rmw_fleetqox_cpp/fleetrmw_reliable_interprocess_probe"
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
                f"{router_binary} --bind 0.0.0.0:48340 "
                "--expected-frames 4 --expected-ack-nack-frames 3 "
                "--expected-route-advertisements 1 --expected-graph-advertisements 2 "
                "--drop-source-sequences 2 --timeout-ms 9000"
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
                "export RMW_IMPLEMENTATION=rmw_fleetqox_cpp && "
                f"FLEETQOX_RMW_BIND=0.0.0.0:48341 FLEETQOX_RMW_PEERS={router_name}:48340 "
                f"{endpoint_binary} --mode subscriber --topic {topic} --timeout-ms 8000"
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
                    "export RMW_IMPLEMENTATION=rmw_fleetqox_cpp && "
                    f"FLEETQOX_RMW_BIND=0.0.0.0:0 FLEETQOX_RMW_PEERS={router_name}:48340 "
                    f"{endpoint_binary} --mode publisher --topic {topic} --hold-ms 5000"
                ),
            ],
        )
        subscriber_returncode = int(run(["docker", "wait", subscriber_name]).stdout.strip())
        router_returncode = int(run(["docker", "wait", router_name]).stdout.strip())
        subscriber_log = run(["docker", "logs", subscriber_name]).stdout.strip()
        router_log = run(["docker", "logs", router_name]).stdout.strip()
        publisher_result = parse_last_json(publisher.stdout)
        subscriber_result = parse_last_json(subscriber_log)
        router_result = parse_last_json(router_log)
        subscriber_payloads = set(subscriber_result.get("payloads", []))
        status = (
            publisher.returncode == 0 and
            subscriber_returncode == 0 and
            router_returncode == 0 and
            publisher_result.get("status") == "ok" and
            subscriber_result.get("status") == "ok" and
            router_result.get("status") == "ok" and
            router_result.get("test_dropped_frames", 0) >= 1 and
            router_result.get("ack_nack_frames", 0) >= 3 and
            router_result.get("ack_nack_forwarded", 0) >= 3 and
            publisher_result.get("nack_retransmissions", 0) >= 1 and
            {"one", "two", "three"}.issubset(subscriber_payloads)
        )
        return {
            "schema_version": SCHEMA_VERSION,
            "status": "ok" if status else "failed",
            "docker_network": network,
            "topic": topic,
            "publisher_returncode": publisher.returncode,
            "subscriber_returncode": subscriber_returncode,
            "router_returncode": router_returncode,
            "publisher": publisher_result,
            "subscriber": subscriber_result,
            "router": router_result,
            "publisher_stdout": publisher.stdout,
            "publisher_stderr": publisher.stderr,
            "subscriber_logs": subscriber_log,
            "router_logs": router_log,
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
        run(["docker", "rm", "-f", router_name, subscriber_name], check=False)
        run(["docker", "network", "rm", network], check=False)
        docker_shell(root, image, f"rm -rf {build_base} {install_base} {log_base}", check=False)


def parse_last_json(output: str) -> dict[str, Any]:
    for line in reversed(output.splitlines()):
        stripped = line.strip()
        if stripped.startswith("{"):
            try:
                return json.loads(stripped)
            except json.JSONDecodeError:
                return {"status": "parse_failed", "raw": stripped}
    return {"status": "missing", "raw": output}


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

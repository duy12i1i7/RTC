"""Run a Docker telemetry-score adaptive router probe for rmw_fleetqox_cpp."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import subprocess
import time
from typing import Any


SCHEMA_VERSION = "fleetrmw.rmw_router_adaptive_score_probe.v1"
DEFAULT_IMAGE = "ros:jazzy-ros-base"
DEFAULT_TOPIC = "/fleetqox/router_adaptive_score_probe"
POST_RECOVERY_PAYLOAD = "four"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--image", default=DEFAULT_IMAGE)
    parser.add_argument("--topic", default=DEFAULT_TOPIC)
    parser.add_argument(
        "--summary-json",
        default="results_rmw_socket/docker_router_adaptive_score_probe_summary.json",
    )
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
        print("fleetrmw-router-adaptive-score-probe")
        print(f"  status: {summary['status']}")
        print(f"  score_sum: {summary.get('publisher', {}).get('adaptive_peer_score_sum')}")
        print(f"  selected_peer: {summary.get('publisher', {}).get('adaptive_selected_peer_index')}")
        print(f"  backup_received: {summary.get('backup_router', {}).get('received_frames')}")
    return 0 if summary["status"] == "ok" else 1


def run_probe(*, root: Path, image: str, topic: str) -> dict[str, Any]:
    suffix = str(os.getpid())
    network = f"fleetrmw-adapt-score-net-{suffix}"
    primary_router_name = f"fleetrmw-adapt-score-primary-{suffix}"
    backup_router_name = f"fleetrmw-adapt-score-backup-{suffix}"
    subscriber_name = f"fleetrmw-adapt-score-sub-{suffix}"
    build_base = "/work/.tmp_fleetrmw_router_adaptive_score_build"
    install_base = "/work/.tmp_fleetrmw_router_adaptive_score_install"
    log_base = "/work/.tmp_fleetrmw_router_adaptive_score_log"
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
            name=primary_router_name,
            network=network,
            command=(
                f"source /opt/ros/jazzy/setup.bash && source {install_base}/setup.bash && "
                f"{router_binary} --bind 0.0.0.0:48390 "
                "--expected-frames 3 --expected-ack-nack-frames 2 "
                "--expected-route-advertisements 1 --expected-graph-advertisements 2 "
                "--drop-source-sequences 2 --timeout-ms 10000"
            ),
        )
        start_container(
            root=root,
            image=image,
            name=backup_router_name,
            network=network,
            command=(
                f"source /opt/ros/jazzy/setup.bash && source {install_base}/setup.bash && "
                f"{router_binary} --bind 0.0.0.0:48391 "
                "--expected-frames 2 --expected-route-advertisements 1 "
                "--expected-graph-advertisements 2 --timeout-ms 10000"
            ),
        )
        time.sleep(0.6)
        start_container(
            root=root,
            image=image,
            name=subscriber_name,
            network=network,
            command=(
                f"source /opt/ros/jazzy/setup.bash && source {install_base}/setup.bash && "
                "export RMW_IMPLEMENTATION=rmw_fleetqox_cpp && "
                "FLEETQOX_RMW_BIND=0.0.0.0:48392 "
                f"FLEETQOX_RMW_PEERS={primary_router_name}:48390,{backup_router_name}:48391 "
                f"{endpoint_binary} --mode subscriber --topic {topic} --timeout-ms 9000 "
                f"--post-recovery-payload {POST_RECOVERY_PAYLOAD}"
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
                    "FLEETQOX_RMW_BIND=0.0.0.0:0 "
                    "FLEETQOX_RMW_PEER_POLICY=adaptive_score "
                    f"FLEETQOX_RMW_PEERS={primary_router_name}:48390,{backup_router_name}:48391 "
                    f"{endpoint_binary} --mode publisher --topic {topic} "
                    "--hold-ms 6500 --min-retransmissions 1 --min-ack-nack-received 2 "
                    f"--post-recovery-payload {POST_RECOVERY_PAYLOAD}"
                ),
            ],
        )
        subscriber_returncode = int(run(["docker", "wait", subscriber_name]).stdout.strip())
        primary_router_returncode = int(run(["docker", "wait", primary_router_name]).stdout.strip())
        backup_router_returncode = int(run(["docker", "wait", backup_router_name]).stdout.strip())
        subscriber_log = run(["docker", "logs", subscriber_name]).stdout.strip()
        primary_router_log = run(["docker", "logs", primary_router_name]).stdout.strip()
        backup_router_log = run(["docker", "logs", backup_router_name]).stdout.strip()
        publisher_result = parse_last_json(publisher.stdout)
        subscriber_result = parse_last_json(subscriber_log)
        primary_router_result = parse_last_json(primary_router_log)
        backup_router_result = parse_last_json(backup_router_log)
        subscriber_payloads = set(subscriber_result.get("payloads", []))
        status = (
            publisher.returncode == 0 and
            subscriber_returncode == 0 and
            primary_router_returncode == 0 and
            backup_router_returncode == 0 and
            publisher_result.get("status") == "ok" and
            subscriber_result.get("status") == "ok" and
            primary_router_result.get("status") == "ok" and
            backup_router_result.get("status") == "ok" and
            publisher_result.get("peer_policy") == "adaptive_score" and
            publisher_result.get("adaptive_failovers", 0) >= 1 and
            publisher_result.get("adaptive_selected_peer_index") == 1 and
            publisher_result.get("adaptive_unicast_frames", 0) >= 5 and
            publisher_result.get("adaptive_peer_score_sum", 0) >= 1000 and
            publisher_result.get("nack_retransmissions", 0) >= 1 and
            primary_router_result.get("received_frames", 0) == 3 and
            primary_router_result.get("test_dropped_frames", 0) >= 1 and
            backup_router_result.get("received_frames", 0) >= 2 and
            backup_router_result.get("forwarded_frames", 0) >= 2 and
            {"one", "two", "three", POST_RECOVERY_PAYLOAD}.issubset(subscriber_payloads)
        )
        return {
            "schema_version": SCHEMA_VERSION,
            "status": "ok" if status else "failed",
            "docker_network": network,
            "topic": topic,
            "publisher_returncode": publisher.returncode,
            "subscriber_returncode": subscriber_returncode,
            "primary_router_returncode": primary_router_returncode,
            "backup_router_returncode": backup_router_returncode,
            "publisher": publisher_result,
            "subscriber": subscriber_result,
            "primary_router": primary_router_result,
            "backup_router": backup_router_result,
            "publisher_stdout": publisher.stdout,
            "publisher_stderr": publisher.stderr,
            "subscriber_logs": subscriber_log,
            "primary_router_logs": primary_router_log,
            "backup_router_logs": backup_router_log,
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
        run(["docker", "rm", "-f", primary_router_name, backup_router_name, subscriber_name], check=False)
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

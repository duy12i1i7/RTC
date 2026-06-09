"""Run a Docker fleet-plan router probe for rmw_fleetqox_cpp."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from fleetqox.fleet_optimizer import (
    FleetFlowDemand,
    FleetOptimizerConfig,
    RobotQoEState,
)
from fleetqox.model import FlowClass
from fleetqox.online_fleet_planner import (
    FleetTopicDemand,
    OnlineFleetPathPlanner,
    OnlineFleetPlannerConfig,
    PathObservation,
)


SCHEMA_VERSION = "fleetrmw.rmw_router_fleet_plan_probe.v1"
DEFAULT_IMAGE = "ros:jazzy-ros-base"
DEFAULT_TOPIC = "/fleetqox/router_fleet_plan_probe"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--image", default=DEFAULT_IMAGE)
    parser.add_argument("--topic", default=DEFAULT_TOPIC)
    parser.add_argument(
        "--summary-json",
        default="results_rmw_socket/docker_router_fleet_plan_probe_summary.json",
    )
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    summary = run_probe(root=ROOT, image=args.image, topic=args.topic)
    summary_path = ROOT / args.summary_json
    summary_path.parent.mkdir(parents=True, exist_ok=True)
    summary_path.write_text(json.dumps(summary, sort_keys=True) + "\n", encoding="utf-8")

    if args.json:
        print(json.dumps(summary, sort_keys=True))
    else:
        print("fleetrmw-router-fleet-plan-probe")
        print(f"  status: {summary['status']}")
        print(f"  fleet_plan_frames: {summary.get('publisher', {}).get('fleet_plan_frames')}")
        print(f"  fleet_plan_last_paths: {summary.get('publisher', {}).get('fleet_plan_last_paths')}")
        print(f"  backup_forwarded: {summary.get('backup_router', {}).get('forwarded_frames')}")
    return 0 if summary["status"] == "ok" else 1


def run_probe(*, root: Path, image: str, topic: str) -> dict[str, Any]:
    suffix = str(os.getpid())
    network = f"fleetrmw-fleet-plan-net-{suffix}"
    primary_router_name = f"fleetrmw-fleet-plan-primary-{suffix}"
    backup_router_name = f"fleetrmw-fleet-plan-backup-{suffix}"
    subscriber_name = f"fleetrmw-fleet-plan-sub-{suffix}"
    build_base = "/work/.tmp_fleetrmw_router_fleet_plan_build"
    install_base = "/work/.tmp_fleetrmw_router_fleet_plan_install"
    log_base = "/work/.tmp_fleetrmw_router_fleet_plan_log"
    plan_dir = root / f".tmp_fleetrmw_router_fleet_plan_{suffix}"
    plan_file_host = plan_dir / "path_plan.txt"
    plan_file_container = f"/work/{plan_file_host.relative_to(root)}"
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
                f"{router_binary} --bind 0.0.0.0:48400 "
                "--expected-frames 3 --expected-ack-nack-frames 3 "
                "--expected-route-advertisements 1 --expected-graph-advertisements 2 "
                "--timeout-ms 9000"
            ),
        )
        start_container(
            root=root,
            image=image,
            name=backup_router_name,
            network=network,
            command=(
                f"source /opt/ros/jazzy/setup.bash && source {install_base}/setup.bash && "
                f"{router_binary} --bind 0.0.0.0:48401 "
                "--expected-frames 2 --expected-ack-nack-frames 2 "
                "--expected-route-advertisements 1 --expected-graph-advertisements 2 "
                "--timeout-ms 9000"
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
                "FLEETQOX_RMW_BIND=0.0.0.0:48402 "
                f"FLEETQOX_RMW_PEERS={primary_router_name}:48400,{backup_router_name}:48401 "
                f"{endpoint_binary} --mode subscriber --topic {topic} "
                "--timeout-ms 8000"
            ),
        )
        time.sleep(0.8)
        path_plan, online_plan = optimizer_path_plan_for_topic(topic)
        selected_paths = online_plan["topic_decisions"][0]["selected_paths"]
        plan_dir.mkdir(parents=True, exist_ok=True)
        initial_path_plan = f"{topic}=primary_wifi"
        plan_file_host.write_text(initial_path_plan + "\n", encoding="utf-8")
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
                    "FLEETQOX_RMW_PEER_POLICY=fleet_plan "
                    f"FLEETQOX_RMW_FLEET_PATH_PLAN_FILE='{plan_file_container}' "
                    f"FLEETQOX_RMW_PEERS=primary_wifi={primary_router_name}:48400,backup_5g={backup_router_name}:48401 "
                    f"{endpoint_binary} --mode publisher --topic {topic} "
                    "--publish-interval-ms 250 "
                    "--plan-update-after-publishes 1 "
                    f"--plan-update-text '{path_plan}' "
                    "--hold-ms 2500 --min-retransmissions 0 --min-ack-nack-received 3"
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
            publisher_result.get("peer_policy") == "fleet_plan" and
            publisher_result.get("fleet_plan_frames", 0) >= 3 and
            publisher_result.get("fleet_plan_redundant_frames", 0) >= 2 and
            publisher_result.get("fleet_plan_selected_path_count", 0) >= 5 and
            publisher_result.get("fleet_plan_last_paths") == ",".join(selected_paths) and
            primary_router_result.get("received_frames", 0) >= 3 and
            backup_router_result.get("received_frames", 0) >= 2 and
            primary_router_result.get("forwarded_frames", 0) >= 3 and
            backup_router_result.get("forwarded_frames", 0) >= 2 and
            {"one", "two", "three"}.issubset(subscriber_payloads)
        )
        return {
            "schema_version": SCHEMA_VERSION,
            "status": "ok" if status else "failed",
            "docker_network": network,
            "topic": topic,
            "initial_path_plan": initial_path_plan,
            "path_plan": path_plan,
            "path_plan_file": str(plan_file_host),
            "online_plan": online_plan,
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
        shutil.rmtree(plan_dir, ignore_errors=True)


def optimizer_path_plan_for_topic(topic: str) -> tuple[str, dict[str, Any]]:
    demand = FleetTopicDemand(
        topic,
        FleetFlowDemand(
            flow_id="robot_0000/cmd_vel",
            robot_id="robot_0000",
            flow_class=FlowClass.CONTROL,
            deadline_ms=30.0,
            payload_bytes=680,
            rate_hz=20.0,
            criticality=0.95,
            qoe_weight=0.10,
            age_ms=12.0,
            lifespan_ms=90.0,
        ),
    )
    planner = OnlineFleetPathPlanner(
        OnlineFleetPlannerConfig(
            optimizer=FleetOptimizerConfig(
                capacity_bytes_per_tick=4096,
                redundant_deadline_ms=35.0,
                redundancy_risk_threshold=1.0,
            ),
            telemetry_alpha=1.0,
            min_dwell_ticks=2,
            switch_score_margin=0.25,
        )
    )
    robot_states = [
        RobotQoEState(
            "robot_0000",
            control_delivery_ratio=0.90,
            deadline_miss_ratio=0.18,
            qoe_score=0.78,
        )
    ]
    planner.update(
        tick=0,
        observations=[
            PathObservation(
                "primary_wifi",
                latency_ms=10.0,
                jitter_ms=1.0,
                sent_frames=100,
                delivered_frames=99,
                nack_frames=1,
                bytes_sent=20_000,
                capacity_bytes=200_000,
            ),
            PathObservation(
                "backup_5g",
                latency_ms=24.0,
                jitter_ms=5.0,
                sent_frames=100,
                delivered_frames=97,
                nack_frames=3,
                deadline_miss_frames=5,
                bytes_sent=84_000,
                capacity_bytes=200_000,
            ),
        ],
        demands=[demand],
        robot_states=robot_states,
    )
    plan = planner.update(
        tick=1,
        observations=[
            PathObservation(
                "primary_wifi",
                latency_ms=58.0,
                jitter_ms=22.0,
                sent_frames=100,
                delivered_frames=82,
                nack_frames=16,
                deadline_miss_frames=24,
                bytes_sent=176_000,
                capacity_bytes=200_000,
            ),
            PathObservation(
                "backup_5g",
                latency_ms=24.0,
                jitter_ms=5.0,
                sent_frames=100,
                delivered_frames=96,
                nack_frames=3,
                deadline_miss_frames=4,
                bytes_sent=84_000,
                capacity_bytes=200_000,
            ),
        ],
        demands=[demand],
        robot_states=robot_states,
    )
    return plan.path_plan_env, plan.as_dict()


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

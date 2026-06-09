"""Run a Docker multi-robot live telemetry fleet-plan probe."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import shutil
import shlex
import subprocess
import sys
import threading
import time
from dataclasses import dataclass
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from fleetqox.fleet_optimizer import FleetFlowDemand, FleetOptimizerConfig, RobotQoEState
from fleetqox.live_path_controller import (
    LivePathPlanController,
    LivePathPlanControllerConfig,
    ROUTER_TELEMETRY_SCHEMA_VERSION,
    SUBSCRIBER_TELEMETRY_SCHEMA_VERSION,
)
from fleetqox.model import FlowClass
from fleetqox.online_fleet_planner import FleetTopicDemand, PathObservation


SCHEMA_VERSION = "fleetrmw.rmw_multi_robot_live_telemetry_plan_probe.v1"
NETEM_SCHEMA_VERSION = "fleetrmw.router_netem.v1"
DEFAULT_IMAGE = "ros:jazzy-ros-base"
DEFAULT_NETEM_DRAIN_S = 2.0
NETEM_SEED_SEMANTICS = "repetition_id_only; current tc netem in the RMW image does not support explicit RNG seed"
CONTROL_TOPIC = "/robot_0000/cmd_vel"
STATE_TOPIC = "/robot_0001/odom"
INITIAL_PATH_PLAN = f"{CONTROL_TOPIC}=primary_wifi;{STATE_TOPIC}=primary_wifi"
FINAL_PATH_PLAN = f"{CONTROL_TOPIC}=backup_5g+primary_wifi;{STATE_TOPIC}=backup_5g"
STATE_TERMINAL_GUARD_PAYLOAD = "terminal_guard"
ROUTE_WARMUP_PAYLOAD = "route_warmup"
TAIL_REPAIR_PAYLOAD = "three"
TERMINAL_GUARD_ALGORITHM = "deadline_sequence_repair_v1"
LIVE_PLAN_BUILD_DIR = ".tmp_fleetrmw_multi_live_plan_build"
LIVE_PLAN_INSTALL_DIR = ".tmp_fleetrmw_multi_live_plan_install"
LIVE_PLAN_LOG_DIR = ".tmp_fleetrmw_multi_live_plan_log"
LIVE_PLAN_BUILD_BASE = f"/work/{LIVE_PLAN_BUILD_DIR}"
LIVE_PLAN_INSTALL_BASE = f"/work/{LIVE_PLAN_INSTALL_DIR}"
LIVE_PLAN_LOG_BASE = f"/work/{LIVE_PLAN_LOG_DIR}"


@dataclass(frozen=True)
class RouterPathTelemetryProfile:
    label: str
    primary_latency_ms: float
    primary_jitter_ms: float
    primary_loss: float
    primary_nack_rate: float
    primary_deadline_miss_ratio: float
    backup_latency_ms: float
    backup_jitter_ms: float
    backup_loss: float
    backup_nack_rate: float
    backup_deadline_miss_ratio: float
    capacity_bytes: int
    primary_rate_mbit: float
    backup_rate_mbit: float
    description: str

    def as_dict(self) -> dict[str, object]:
        return {
            "label": self.label,
            "primary_latency_ms": self.primary_latency_ms,
            "primary_jitter_ms": self.primary_jitter_ms,
            "primary_loss": self.primary_loss,
            "primary_nack_rate": self.primary_nack_rate,
            "primary_deadline_miss_ratio": self.primary_deadline_miss_ratio,
            "backup_latency_ms": self.backup_latency_ms,
            "backup_jitter_ms": self.backup_jitter_ms,
            "backup_loss": self.backup_loss,
            "backup_nack_rate": self.backup_nack_rate,
            "backup_deadline_miss_ratio": self.backup_deadline_miss_ratio,
            "capacity_bytes": self.capacity_bytes,
            "primary_rate_mbit": self.primary_rate_mbit,
            "backup_rate_mbit": self.backup_rate_mbit,
            "description": self.description,
        }


@dataclass(frozen=True)
class LiveTopicSpec:
    topic: str
    robot_id: str
    flow_id: str
    flow_class: FlowClass

    @property
    def kind(self) -> str:
        return "control" if self.flow_class is FlowClass.CONTROL else "state"

    def as_dict(self) -> dict[str, object]:
        return {
            "topic": self.topic,
            "robot_id": self.robot_id,
            "flow_id": self.flow_id,
            "kind": self.kind,
        }


@dataclass(frozen=True)
class TerminalHorizon:
    algorithm: str
    repeat_count: int
    router_dwell_ms: int
    startup_settle_ms: int
    pre_publish_wait_ms: int
    post_plan_settle_ms: int
    pre_payload_warmup_count: int
    pre_payload_warmup_ack_count: int
    pre_payload_warmup_ack_timeout_ms: int
    app_repair_cycle_count: int
    tail_repair_repeat_count: int
    required_sequence: int
    proactive_data_repeats: int
    risk_score: float
    scaled_primary_loss: float
    scaled_backup_loss: float
    latency_budget_ms: float

    @property
    def wire_payloads_per_publisher(self) -> int:
        return (
            self.pre_payload_warmup_count +
            self.required_sequence - 1 +
            self.app_repair_cycle_count * 3 +
            self.tail_repair_repeat_count +
            self.repeat_count
        )

    def as_dict(self) -> dict[str, object]:
        return {
            "algorithm": self.algorithm,
            "repeat_count": self.repeat_count,
            "router_dwell_ms": self.router_dwell_ms,
            "startup_settle_ms": self.startup_settle_ms,
            "pre_publish_wait_ms": self.pre_publish_wait_ms,
            "post_plan_settle_ms": self.post_plan_settle_ms,
            "pre_payload_warmup_count": self.pre_payload_warmup_count,
            "pre_payload_warmup_ack_count": self.pre_payload_warmup_ack_count,
            "pre_payload_warmup_ack_timeout_ms": self.pre_payload_warmup_ack_timeout_ms,
            "app_repair_cycle_count": self.app_repair_cycle_count,
            "tail_repair_repeat_count": self.tail_repair_repeat_count,
            "required_sequence": self.required_sequence,
            "proactive_data_repeats": self.proactive_data_repeats,
            "risk_score": self.risk_score,
            "scaled_primary_loss": self.scaled_primary_loss,
            "scaled_backup_loss": self.scaled_backup_loss,
            "latency_budget_ms": self.latency_budget_ms,
        }


ROUTER_TELEMETRY_PROFILES = {
    "wifi": RouterPathTelemetryProfile(
        label="wifi",
        primary_latency_ms=58.0,
        primary_jitter_ms=22.0,
        primary_loss=0.18,
        primary_nack_rate=0.16,
        primary_deadline_miss_ratio=0.24,
        backup_latency_ms=24.0,
        backup_jitter_ms=5.0,
        backup_loss=0.035,
        backup_nack_rate=0.025,
        backup_deadline_miss_ratio=0.04,
        capacity_bytes=400000,
        primary_rate_mbit=20.0,
        backup_rate_mbit=35.0,
        description="shared Wi-Fi stress with a healthier 5G backup path",
    ),
    "wan": RouterPathTelemetryProfile(
        label="wan",
        primary_latency_ms=74.0,
        primary_jitter_ms=24.0,
        primary_loss=0.16,
        primary_nack_rate=0.13,
        primary_deadline_miss_ratio=0.30,
        backup_latency_ms=34.0,
        backup_jitter_ms=8.0,
        backup_loss=0.05,
        backup_nack_rate=0.04,
        backup_deadline_miss_ratio=0.08,
        capacity_bytes=320000,
        primary_rate_mbit=10.0,
        backup_rate_mbit=18.0,
        description="remote/cloud WAN profile with higher control deadline pressure",
    ),
    "roaming": RouterPathTelemetryProfile(
        label="roaming",
        primary_latency_ms=96.0,
        primary_jitter_ms=34.0,
        primary_loss=0.28,
        primary_nack_rate=0.23,
        primary_deadline_miss_ratio=0.42,
        backup_latency_ms=42.0,
        backup_jitter_ms=11.0,
        backup_loss=0.075,
        backup_nack_rate=0.06,
        backup_deadline_miss_ratio=0.12,
        capacity_bytes=240000,
        primary_rate_mbit=5.0,
        backup_rate_mbit=15.0,
        description="handoff/roaming stress profile with sharp primary-path degradation",
    ),
}


def profile_by_name(profile: str) -> RouterPathTelemetryProfile:
    try:
        return ROUTER_TELEMETRY_PROFILES[profile]
    except KeyError as exc:
        choices = ", ".join(sorted(ROUTER_TELEMETRY_PROFILES))
        raise ValueError(f"unknown router telemetry profile: {profile}; choices: {choices}") from exc


def terminal_horizon_for_profile(
    profile: RouterPathTelemetryProfile,
    *,
    robot_count: int,
    loss_scale: float,
) -> TerminalHorizon:
    scaled_primary_loss = max(0.0, min(1.0, profile.primary_loss * loss_scale))
    scaled_backup_loss = max(0.0, min(1.0, profile.backup_loss * loss_scale))
    worst_loss = max(scaled_primary_loss, scaled_backup_loss)
    worst_deadline_miss = max(
        profile.primary_deadline_miss_ratio,
        profile.backup_deadline_miss_ratio,
    )
    max_latency = max(profile.primary_latency_ms, profile.backup_latency_ms)
    max_jitter = max(profile.primary_jitter_ms, profile.backup_jitter_ms)
    robot_pressure = min(2.0, max(0, robot_count - 1) / 4.0)
    risk_score = worst_loss * 30.0 + worst_deadline_miss * 4.0 + robot_pressure
    repeat_count = 5
    proactive_data_repeats = 1
    latency_budget_ms = 2.0 * (max_latency + max_jitter)
    startup_settle_ms = 1000
    pre_publish_wait_ms = 0
    post_plan_settle_ms = 0
    router_dwell_ms = 4000
    return TerminalHorizon(
        algorithm=TERMINAL_GUARD_ALGORITHM,
        repeat_count=repeat_count,
        router_dwell_ms=router_dwell_ms,
        startup_settle_ms=startup_settle_ms,
        pre_publish_wait_ms=pre_publish_wait_ms,
        post_plan_settle_ms=post_plan_settle_ms,
        pre_payload_warmup_count=1,
        pre_payload_warmup_ack_count=1,
        pre_payload_warmup_ack_timeout_ms=2000,
        app_repair_cycle_count=2,
        tail_repair_repeat_count=5,
        required_sequence=4,
        proactive_data_repeats=proactive_data_repeats,
        risk_score=round(risk_score, 6),
        scaled_primary_loss=round(scaled_primary_loss, 6),
        scaled_backup_loss=round(scaled_backup_loss, 6),
        latency_budget_ms=round(latency_budget_ms, 6),
    )


def _ceil_int(value: float) -> int:
    integer = int(value)
    return integer if value <= integer else integer + 1


def _round_up_int(value: float, step: int) -> int:
    if step <= 0:
        return _ceil_int(value)
    return _ceil_int(value / step) * step


def live_topic_specs_for_robot_count(robot_count: int) -> list[LiveTopicSpec]:
    if robot_count <= 0:
        raise ValueError("robot_count must be positive")
    if robot_count == 1:
        return [
            LiveTopicSpec(
                topic=CONTROL_TOPIC,
                robot_id="robot_0000",
                flow_id="robot_0000/cmd_vel",
                flow_class=FlowClass.CONTROL,
            ),
            LiveTopicSpec(
                topic=STATE_TOPIC,
                robot_id="robot_0001",
                flow_id="robot_0001/odom",
                flow_class=FlowClass.STATE,
            ),
        ]
    specs: list[LiveTopicSpec] = []
    for robot_index in range(robot_count):
        robot_id = f"robot_{robot_index:04d}"
        specs.append(
            LiveTopicSpec(
                topic=f"/{robot_id}/cmd_vel",
                robot_id=robot_id,
                flow_id=f"{robot_id}/cmd_vel",
                flow_class=FlowClass.CONTROL,
            )
        )
        specs.append(
            LiveTopicSpec(
                topic=f"/{robot_id}/odom",
                robot_id=robot_id,
                flow_id=f"{robot_id}/odom",
                flow_class=FlowClass.STATE,
            )
        )
    return specs


def path_plan_for_specs(specs: list[LiveTopicSpec], *, final: bool) -> str:
    rules = []
    for spec in specs:
        if final and spec.flow_class is FlowClass.CONTROL:
            paths = "backup_5g+primary_wifi"
        elif final and spec.flow_class is FlowClass.STATE:
            paths = "backup_5g"
        else:
            paths = "primary_wifi"
        rules.append(f"{spec.topic}={paths}")
    return ";".join(rules)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--image", default=DEFAULT_IMAGE)
    parser.add_argument("--profile", choices=sorted(ROUTER_TELEMETRY_PROFILES), default="wifi")
    parser.add_argument(
        "--summary-json",
        default="results_rmw_socket/docker_multi_robot_live_telemetry_plan_probe_summary.json",
    )
    parser.add_argument("--enable-netem", action="store_true")
    parser.add_argument("--require-netem", action="store_true")
    parser.add_argument(
        "--netem-loss-scale",
        type=float,
        default=0.0,
        help="multiplier applied to profile packet loss for tc netem; default keeps smoke deterministic",
    )
    parser.add_argument(
        "--netem-drain-s",
        type=float,
        default=DEFAULT_NETEM_DRAIN_S,
        help="seconds to keep router containers alive after router exit so qdisc queues drain",
    )
    parser.add_argument(
        "--repetition-seed",
        type=int,
        default=None,
        help="recorded repetition id; current tc netem image does not expose explicit RNG seeding",
    )
    parser.add_argument("--robot-count", type=int, default=1)
    parser.add_argument(
        "--reuse-build",
        action="store_true",
        help="reuse the RMW colcon install directory when it already exists",
    )
    parser.add_argument(
        "--control-proactive-data-repeats",
        type=int,
        default=None,
        help="override control data-frame proactive repair repeats; default auto",
    )
    parser.add_argument(
        "--state-proactive-data-repeats",
        type=int,
        default=None,
        help="override state data-frame proactive repair repeats; default auto",
    )
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    summary = run_probe(
        root=ROOT,
        image=args.image,
        profile=args.profile,
        enable_netem=args.enable_netem,
        require_netem=args.require_netem,
        netem_loss_scale=args.netem_loss_scale,
        netem_drain_s=args.netem_drain_s,
        repetition_seed=args.repetition_seed,
        robot_count=args.robot_count,
        reuse_build=args.reuse_build,
        control_proactive_data_repeats=args.control_proactive_data_repeats,
        state_proactive_data_repeats=args.state_proactive_data_repeats,
    )
    summary_path = ROOT / args.summary_json
    summary_path.parent.mkdir(parents=True, exist_ok=True)
    summary_path.write_text(json.dumps(summary, sort_keys=True) + "\n", encoding="utf-8")

    if args.json:
        print(json.dumps(summary, sort_keys=True))
    else:
        print("fleetrmw-multi-robot-live-telemetry-plan-probe")
        print(f"  status: {summary['status']}")
        print(f"  initial_plan: {summary.get('initial_path_plan')}")
        print(f"  final_plan: {summary.get('controller_final_path_plan')}")
        print(f"  netem_enabled: {summary.get('netem_enabled')}")
        print(f"  subscriber_records: {summary.get('controller', {}).get('subscriber_record_count')}")
    return 0 if summary["status"] == "ok" else 1


def run_probe(
    *,
    root: Path,
    image: str,
    profile: str = "wifi",
    enable_netem: bool = False,
    require_netem: bool = False,
    netem_loss_scale: float = 0.0,
    netem_drain_s: float = DEFAULT_NETEM_DRAIN_S,
    repetition_seed: int | None = None,
    robot_count: int = 1,
    reuse_build: bool = False,
    cleanup_build: bool = True,
    control_proactive_data_repeats: int | None = None,
    state_proactive_data_repeats: int | None = None,
) -> dict[str, Any]:
    if netem_loss_scale < 0.0:
        raise ValueError("netem_loss_scale must be non-negative")
    if netem_drain_s < 0.0:
        raise ValueError("netem_drain_s must be non-negative")
    if robot_count <= 0:
        raise ValueError("robot_count must be positive")
    if control_proactive_data_repeats is not None and control_proactive_data_repeats < 0:
        raise ValueError("control_proactive_data_repeats must be non-negative")
    if state_proactive_data_repeats is not None and state_proactive_data_repeats < 0:
        raise ValueError("state_proactive_data_repeats must be non-negative")
    if robot_count != 1:
        return run_scaled_probe(
            root=root,
            image=image,
            profile=profile,
            enable_netem=enable_netem,
            require_netem=require_netem,
            netem_loss_scale=netem_loss_scale,
            netem_drain_s=netem_drain_s,
            repetition_seed=repetition_seed,
            robot_count=robot_count,
            reuse_build=reuse_build,
            cleanup_build=cleanup_build,
            control_proactive_data_repeats=control_proactive_data_repeats,
            state_proactive_data_repeats=state_proactive_data_repeats,
        )
    telemetry_profile = profile_by_name(profile)
    suffix = str(os.getpid())
    network = f"fleetrmw-multi-live-plan-net-{suffix}"
    primary_router_name = f"fleetrmw-multi-live-primary-{suffix}"
    backup_router_name = f"fleetrmw-multi-live-backup-{suffix}"
    control_subscriber_name = f"fleetrmw-multi-live-sub-control-{suffix}"
    state_subscriber_name = f"fleetrmw-multi-live-sub-state-{suffix}"
    control_publisher_name = f"fleetrmw-multi-live-pub-control-{suffix}"
    install_base = LIVE_PLAN_INSTALL_BASE
    plan_dir = root / f".tmp_fleetrmw_multi_live_plan_{suffix}"
    plan_file_host = plan_dir / "path_plan.txt"
    primary_telemetry_host = plan_dir / "primary_router_telemetry.jsonl"
    backup_telemetry_host = plan_dir / "backup_router_telemetry.jsonl"
    primary_netem_status_host = plan_dir / "primary_router_netem_status.json"
    backup_netem_status_host = plan_dir / "backup_router_netem_status.json"
    control_subscriber_telemetry_host = plan_dir / "control_subscriber_telemetry.jsonl"
    state_subscriber_telemetry_host = plan_dir / "state_subscriber_telemetry.jsonl"
    plan_file_container = f"/work/{plan_file_host.relative_to(root)}"
    primary_telemetry_container = f"/work/{primary_telemetry_host.relative_to(root)}"
    backup_telemetry_container = f"/work/{backup_telemetry_host.relative_to(root)}"
    primary_netem_status_container = f"/work/{primary_netem_status_host.relative_to(root)}"
    backup_netem_status_container = f"/work/{backup_netem_status_host.relative_to(root)}"
    control_subscriber_telemetry_container = (
        f"/work/{control_subscriber_telemetry_host.relative_to(root)}"
    )
    state_subscriber_telemetry_container = (
        f"/work/{state_subscriber_telemetry_host.relative_to(root)}"
    )
    endpoint_binary = (
        f"{install_base}/rmw_fleetqox_cpp/lib/rmw_fleetqox_cpp/"
        "fleetrmw_reliable_interprocess_probe"
    )
    router_binary = (
        f"{install_base}/rmw_fleetqox_cpp/lib/rmw_fleetqox_cpp/fleetrmw_udp_router_probe"
    )
    controller: LivePathPlanController | None = None
    controller_thread: threading.Thread | None = None
    stop_controller = threading.Event()
    failure_phase = "init"
    build_performed = False
    primary_netem = netem_config_for_path(
        telemetry_profile,
        path_id="primary_wifi",
        loss_scale=netem_loss_scale,
        repetition_seed=repetition_seed,
    )
    backup_netem = netem_config_for_path(
        telemetry_profile,
        path_id="backup_5g",
        loss_scale=netem_loss_scale,
        repetition_seed=repetition_seed,
    )
    router_exit_suffix = router_netem_drain_suffix(netem_drain_s) if enable_netem else ""
    stochastic_netem = enable_netem and netem_loss_scale > 0.0
    primary_expected_ack_nack_forwarded = 0 if stochastic_netem else (2 if enable_netem else 3)
    backup_expected_ack_nack_forwarded = 0 if stochastic_netem else (4 if enable_netem else 5)
    control_min_ack_nack_received = 0 if stochastic_netem else 3
    state_min_ack_nack_received = 0 if stochastic_netem else 2
    if control_proactive_data_repeats is None:
        control_proactive_data_repeats = 1 if stochastic_netem else 0
    if state_proactive_data_repeats is None:
        state_proactive_data_repeats = 1 if stochastic_netem else 0
    primary_expected_frames = 3 + (control_proactive_data_repeats * 3)
    backup_expected_frames = (
        5 +
        (state_proactive_data_repeats * 3) +
        (control_proactive_data_repeats * 2)
    )

    try:
        plan_dir.mkdir(parents=True, exist_ok=True)
        failure_phase = "create_docker_network"
        run(["docker", "network", "create", network])
        failure_phase = "build_rmw_package"
        build_performed = ensure_live_plan_build(root, image, clean=not reuse_build)
        failure_phase = "start_live_path_controller"
        controller = live_controller_for_probe(
            plan_file=plan_file_host,
            telemetry_files=(primary_telemetry_host, backup_telemetry_host),
            subscriber_telemetry_files=(
                control_subscriber_telemetry_host,
                state_subscriber_telemetry_host,
            ),
        )
        initial_plan = controller.poll_once().path_plan_env
        controller_thread = threading.Thread(
            target=run_controller_loop,
            args=(controller, stop_controller),
            daemon=True,
        )
        controller_thread.start()
        failure_phase = "start_primary_router"
        start_container(
            root=root,
            image=image,
            name=primary_router_name,
            network=network,
            command=(
                f"source /opt/ros/jazzy/setup.bash && source {install_base}/setup.bash && "
                + (
                    netem_shell_prefix(
                        primary_netem,
                        status_file=primary_netem_status_container,
                        require=require_netem,
                    )
                    if enable_netem
                    else ""
                )
                +
                f"{router_binary} --bind 0.0.0.0:48420 "
                "--path-id primary_wifi "
                f"--telemetry-file {primary_telemetry_container} "
                f"--telemetry-latency-ms {telemetry_profile.primary_latency_ms:g} "
                f"--telemetry-jitter-ms {telemetry_profile.primary_jitter_ms:g} "
                f"--telemetry-loss {telemetry_profile.primary_loss:g} "
                f"--telemetry-nack-rate {telemetry_profile.primary_nack_rate:g} "
                "--telemetry-deadline-miss-ratio "
                f"{telemetry_profile.primary_deadline_miss_ratio:g} "
                f"--telemetry-capacity-bytes {telemetry_profile.capacity_bytes} "
                f"--expected-frames {primary_expected_frames} --expected-ack-nack-frames 3 "
                f"--expected-ack-nack-forwarded {primary_expected_ack_nack_forwarded} "
                "--expected-route-advertisements 2 "
                "--expected-graph-advertisements 2 --timeout-ms 18000"
                f"{router_exit_suffix}"
            ),
            extra_args=("--cap-add", "NET_ADMIN") if enable_netem else (),
        )
        failure_phase = "start_backup_router"
        start_container(
            root=root,
            image=image,
            name=backup_router_name,
            network=network,
            command=(
                f"source /opt/ros/jazzy/setup.bash && source {install_base}/setup.bash && "
                + (
                    netem_shell_prefix(
                        backup_netem,
                        status_file=backup_netem_status_container,
                        require=require_netem,
                    )
                    if enable_netem
                    else ""
                )
                +
                f"{router_binary} --bind 0.0.0.0:48421 "
                "--path-id backup_5g "
                f"--telemetry-file {backup_telemetry_container} "
                f"--telemetry-latency-ms {telemetry_profile.backup_latency_ms:g} "
                f"--telemetry-jitter-ms {telemetry_profile.backup_jitter_ms:g} "
                f"--telemetry-loss {telemetry_profile.backup_loss:g} "
                f"--telemetry-nack-rate {telemetry_profile.backup_nack_rate:g} "
                "--telemetry-deadline-miss-ratio "
                f"{telemetry_profile.backup_deadline_miss_ratio:g} "
                f"--telemetry-capacity-bytes {telemetry_profile.capacity_bytes} "
                f"--expected-frames {backup_expected_frames} --expected-ack-nack-frames 5 "
                f"--expected-ack-nack-forwarded {backup_expected_ack_nack_forwarded} "
                "--expected-route-advertisements 2 "
                "--expected-graph-advertisements 2 --timeout-ms 18000"
                f"{router_exit_suffix}"
            ),
            extra_args=("--cap-add", "NET_ADMIN") if enable_netem else (),
        )
        time.sleep(0.6)
        failure_phase = "start_control_subscriber"
        start_subscriber(
            root=root,
            image=image,
            name=control_subscriber_name,
            network=network,
            install_base=install_base,
            endpoint_binary=endpoint_binary,
            topic=CONTROL_TOPIC,
            robot_id="robot_0000",
            telemetry_file=control_subscriber_telemetry_container,
            primary_router_name=primary_router_name,
            backup_router_name=backup_router_name,
        )
        failure_phase = "start_state_subscriber"
        start_subscriber(
            root=root,
            image=image,
            name=state_subscriber_name,
            network=network,
            install_base=install_base,
            endpoint_binary=endpoint_binary,
            topic=STATE_TOPIC,
            robot_id="robot_0001",
            telemetry_file=state_subscriber_telemetry_container,
            primary_router_name=primary_router_name,
            backup_router_name=backup_router_name,
        )
        time.sleep(0.8)
        failure_phase = "start_control_publisher"
        start_publisher_container(
            root=root,
            image=image,
            name=control_publisher_name,
            network=network,
            install_base=install_base,
            endpoint_binary=endpoint_binary,
            topic=CONTROL_TOPIC,
            plan_file=plan_file_container,
            primary_router_name=primary_router_name,
            backup_router_name=backup_router_name,
            min_ack_nack_received=control_min_ack_nack_received,
            proactive_data_repeats=control_proactive_data_repeats,
            publish_interval_ms=700,
        )
        final_plan_ready = wait_for_path_plan(plan_file_host, FINAL_PATH_PLAN, timeout_s=5.0)
        failure_phase = "run_state_publisher"
        state_publisher = run_publisher(
            root=root,
            image=image,
            network=network,
            install_base=install_base,
            endpoint_binary=endpoint_binary,
            topic=STATE_TOPIC,
            plan_file=plan_file_container,
            primary_router_name=primary_router_name,
            backup_router_name=backup_router_name,
            min_ack_nack_received=state_min_ack_nack_received,
            proactive_data_repeats=state_proactive_data_repeats,
            publish_interval_ms=500,
        )
        failure_phase = "wait_control_publisher"
        control_publisher_returncode = int(
            run(["docker", "wait", control_publisher_name]).stdout.strip()
        )
        failure_phase = "wait_control_subscriber"
        control_subscriber_returncode = int(
            run(["docker", "wait", control_subscriber_name]).stdout.strip()
        )
        failure_phase = "wait_state_subscriber"
        state_subscriber_returncode = int(
            run(["docker", "wait", state_subscriber_name]).stdout.strip()
        )
        failure_phase = "wait_primary_router"
        primary_router_returncode = int(run(["docker", "wait", primary_router_name]).stdout.strip())
        failure_phase = "wait_backup_router"
        backup_router_returncode = int(run(["docker", "wait", backup_router_name]).stdout.strip())
        if controller is not None:
            controller.poll_once()
        stop_controller.set()
        if controller_thread is not None:
            controller_thread.join(timeout=2.0)

        failure_phase = "collect_component_logs"
        control_publisher_log = run(["docker", "logs", control_publisher_name]).stdout.strip()
        control_subscriber_log = run(["docker", "logs", control_subscriber_name]).stdout.strip()
        state_subscriber_log = run(["docker", "logs", state_subscriber_name]).stdout.strip()
        primary_router_log = run(["docker", "logs", primary_router_name]).stdout.strip()
        backup_router_log = run(["docker", "logs", backup_router_name]).stdout.strip()
        control_publisher_result = parse_last_json(control_publisher_log)
        state_publisher_result = parse_last_json(state_publisher.stdout)
        control_subscriber_result = parse_last_json(control_subscriber_log)
        state_subscriber_result = parse_last_json(state_subscriber_log)
        primary_router_result = parse_last_json(primary_router_log)
        backup_router_result = parse_last_json(backup_router_log)
        control_subscriber_payloads = set(control_subscriber_result.get("payloads", []))
        state_subscriber_payloads = set(state_subscriber_result.get("payloads", []))
        controller_summary = controller.summary() if controller is not None else {}
        controller_final_path_plan = str(
            (controller_summary.get("last_plan") or {}).get("path_plan_env", "")
            if isinstance(controller_summary.get("last_plan"), dict)
            else ""
        )
        subscriber_telemetry = {
            "robot_0000": read_jsonl(control_subscriber_telemetry_host),
            "robot_0001": read_jsonl(state_subscriber_telemetry_host),
        }
        robot_state_ids = {
            str(state.get("robot_id", ""))
            for state in controller_summary.get("robot_states", [])
            if isinstance(state, dict)
        }
        primary_topics = set(primary_router_result.get("topics", []))
        backup_topics = set(backup_router_result.get("topics", []))
        control_delivery_ok = {"one", "two", "three"}.issubset(control_subscriber_payloads)
        state_delivery_ok = {"one", "two", "three"}.issubset(state_subscriber_payloads)
        delivery_ok = control_delivery_ok and state_delivery_ok
        control_duplicate_dedup_count = int(
            control_subscriber_result.get("duplicate_data_frames_deduped", 0)
        )
        control_duplicate_dedup_required = (not enable_netem) or netem_loss_scale <= 0.0
        control_duplicate_dedup_ok = (
            control_duplicate_dedup_count >= 1 if control_duplicate_dedup_required else True
        )
        control_duplicate_ack_required = (not enable_netem) or netem_loss_scale <= 0.0
        control_duplicate_ack_ok = (
            control_publisher_result.get("ack_nack_duplicate_received", 0) >= 1
            if control_duplicate_ack_required else True
        )
        state_duplicate_dedup_required = not stochastic_netem
        state_duplicate_dedup_ok = (
            state_subscriber_result.get("duplicate_data_frames_deduped", 0) == 0
            if state_duplicate_dedup_required else True
        )
        state_duplicate_ack_required = state_proactive_data_repeats == 0
        state_duplicate_ack_ok = (
            state_publisher_result.get("ack_nack_duplicate_received", 0) == 0
            if state_duplicate_ack_required else True
        )
        netem_status = {
            "primary_wifi": read_json(primary_netem_status_host),
            "backup_5g": read_json(backup_netem_status_host),
        }
        netem_ok = netem_status_ok(
            netem_status,
            enabled=enable_netem,
            required=require_netem,
        )
        primary_router_ok = (
            primary_router_returncode == 0 and primary_router_result.get("status") == "ok"
        )
        backup_router_ok = (
            backup_router_returncode == 0 and backup_router_result.get("status") == "ok"
        )
        if stochastic_netem and delivery_ok and netem_ok:
            primary_router_ok = primary_router_result.get("status") in {"ok", "failed"}
            backup_router_ok = backup_router_result.get("status") in {"ok", "failed"}
        status = (
            control_publisher_returncode == 0 and
            state_publisher.returncode == 0 and
            control_subscriber_returncode == 0 and
            state_subscriber_returncode == 0 and
            control_publisher_result.get("status") == "ok" and
            state_publisher_result.get("status") == "ok" and
            control_subscriber_result.get("status") == "ok" and
            state_subscriber_result.get("status") == "ok" and
            primary_router_ok and
            backup_router_ok and
            initial_plan == INITIAL_PATH_PLAN and
            final_plan_ready and
            controller_summary.get("record_count", 0) >= 6 and
            controller_summary.get("subscriber_record_count", 0) >= 6 and
            controller_final_path_plan == FINAL_PATH_PLAN and
            control_publisher_result.get("fleet_plan_frames", 0) >= 3 and
            control_publisher_result.get("fleet_plan_redundant_frames", 0) >= 1 and
            control_publisher_result.get("fleet_plan_last_paths") == "backup_5g,primary_wifi" and
            control_duplicate_ack_ok and
            state_publisher_result.get("fleet_plan_frames", 0) >= 3 and
            state_publisher_result.get("fleet_plan_redundant_frames", 0) == 0 and
            state_publisher_result.get("fleet_plan_last_paths") == "backup_5g" and
            state_duplicate_ack_ok and
            control_duplicate_dedup_ok and
            state_duplicate_dedup_ok and
            primary_router_result.get("received_frames", 0) >= 3 and
            backup_router_result.get("received_frames", 0) >= 3 and
            CONTROL_TOPIC in primary_topics and
            STATE_TOPIC in backup_topics and
            control_delivery_ok and
            state_delivery_ok and
            {"robot_0000", "robot_0001"}.issubset(robot_state_ids) and
            netem_ok
        )
        return {
            "schema_version": SCHEMA_VERSION,
            "status": "ok" if status else "failed",
            "profile": telemetry_profile.label,
            "image": image,
            "repetition_seed": repetition_seed,
            "profile_config": telemetry_profile.as_dict(),
            "netem_enabled": enable_netem,
            "netem_required": require_netem,
            "netem_loss_scale": netem_loss_scale,
            "netem_drain_s": netem_drain_s,
            "netem_seed_semantics": NETEM_SEED_SEMANTICS if enable_netem else "",
            "stochastic_netem": stochastic_netem,
            "reuse_build": reuse_build,
            "build_performed": build_performed,
            "control_duplicate_dedup_required": control_duplicate_dedup_required,
            "control_duplicate_ack_required": control_duplicate_ack_required,
            "state_duplicate_dedup_required": state_duplicate_dedup_required,
            "state_duplicate_ack_required": state_duplicate_ack_required,
            "control_proactive_data_repeats": control_proactive_data_repeats,
            "state_proactive_data_repeats": state_proactive_data_repeats,
            "netem": {
                "primary_wifi": primary_netem,
                "backup_5g": backup_netem,
            } if enable_netem else {},
            "netem_status_files": {
                "primary_wifi": str(primary_netem_status_host),
                "backup_5g": str(backup_netem_status_host),
            } if enable_netem else {},
            "netem_status": netem_status if enable_netem else {},
            "router_telemetry_schema_version": ROUTER_TELEMETRY_SCHEMA_VERSION,
            "subscriber_telemetry_schema_version": SUBSCRIBER_TELEMETRY_SCHEMA_VERSION,
            "docker_network": network,
            "topics": [CONTROL_TOPIC, STATE_TOPIC],
            "initial_path_plan": initial_plan,
            "expected_final_path_plan": FINAL_PATH_PLAN,
            "final_plan_ready": final_plan_ready,
            "controller_final_path_plan": controller_final_path_plan,
            "path_plan_file": str(plan_file_host),
            "primary_telemetry_file": str(primary_telemetry_host),
            "backup_telemetry_file": str(backup_telemetry_host),
            "subscriber_telemetry_files": {
                "robot_0000": str(control_subscriber_telemetry_host),
                "robot_0001": str(state_subscriber_telemetry_host),
            },
            "controller": controller_summary,
            "control_publisher_returncode": control_publisher_returncode,
            "state_publisher_returncode": state_publisher.returncode,
            "control_subscriber_returncode": control_subscriber_returncode,
            "state_subscriber_returncode": state_subscriber_returncode,
            "primary_router_returncode": primary_router_returncode,
            "backup_router_returncode": backup_router_returncode,
            "control_publisher": control_publisher_result,
            "state_publisher": state_publisher_result,
            "control_subscriber": control_subscriber_result,
            "state_subscriber": state_subscriber_result,
            "primary_router": primary_router_result,
            "backup_router": backup_router_result,
            "primary_telemetry": read_jsonl(primary_telemetry_host),
            "backup_telemetry": read_jsonl(backup_telemetry_host),
            "subscriber_telemetry": subscriber_telemetry,
            "control_publisher_logs": control_publisher_log,
            "state_publisher_stdout": state_publisher.stdout,
            "state_publisher_stderr": state_publisher.stderr,
            "control_subscriber_logs": control_subscriber_log,
            "state_subscriber_logs": state_subscriber_log,
            "primary_router_logs": primary_router_log,
            "backup_router_logs": backup_router_log,
        }
    except subprocess.CalledProcessError as exc:
        container_names = [
            primary_router_name,
            backup_router_name,
            control_subscriber_name,
            state_subscriber_name,
            control_publisher_name,
        ]
        failure = {
            "kind": "subprocess_error",
            "phase": failure_phase,
            "command": command_to_text(exc.cmd),
            "returncode": exc.returncode,
            "stdout_excerpt": text_tail(exc.stdout),
            "stderr_excerpt": text_tail(exc.stderr),
            "container_logs": collect_container_logs(container_names),
        }
        return {
            "schema_version": SCHEMA_VERSION,
            "status": "failed",
            "profile": telemetry_profile.label,
            "image": image,
            "repetition_seed": repetition_seed,
            "profile_config": telemetry_profile.as_dict(),
            "netem_enabled": enable_netem,
            "netem_required": require_netem,
            "netem_loss_scale": netem_loss_scale,
            "netem_drain_s": netem_drain_s,
            "netem_seed_semantics": NETEM_SEED_SEMANTICS if enable_netem else "",
            "stochastic_netem": stochastic_netem,
            "reuse_build": reuse_build,
            "build_performed": build_performed,
            "netem": {
                "primary_wifi": primary_netem,
                "backup_5g": backup_netem,
            } if enable_netem else {},
            "netem_status": {
                "primary_wifi": read_json(primary_netem_status_host),
                "backup_5g": read_json(backup_netem_status_host),
            } if enable_netem else {},
            "docker_network": network,
            "failure": failure,
            "returncode": exc.returncode,
            "stdout": exc.stdout,
            "stderr": exc.stderr,
        }
    finally:
        stop_controller.set()
        if controller_thread is not None and controller_thread.is_alive():
            controller_thread.join(timeout=2.0)
        run(
            [
                "docker",
                "rm",
                "-f",
                primary_router_name,
                backup_router_name,
                control_subscriber_name,
                state_subscriber_name,
                control_publisher_name,
            ],
            check=False,
        )
        run(["docker", "network", "rm", network], check=False)
        if cleanup_build:
            cleanup_live_plan_build(root, image)
        shutil.rmtree(plan_dir, ignore_errors=True)


def run_scaled_probe(
    *,
    root: Path,
    image: str,
    profile: str,
    enable_netem: bool,
    require_netem: bool,
    netem_loss_scale: float,
    netem_drain_s: float,
    repetition_seed: int | None,
    robot_count: int,
    reuse_build: bool,
    cleanup_build: bool,
    control_proactive_data_repeats: int | None,
    state_proactive_data_repeats: int | None,
) -> dict[str, Any]:
    telemetry_profile = profile_by_name(profile)
    topic_specs = live_topic_specs_for_robot_count(robot_count)
    control_specs = [spec for spec in topic_specs if spec.flow_class is FlowClass.CONTROL]
    state_specs = [spec for spec in topic_specs if spec.flow_class is FlowClass.STATE]
    topic_count = len(topic_specs)
    suffix = str(os.getpid())
    network = f"fleetrmw-multi-live-plan-net-{suffix}"
    primary_router_name = f"fleetrmw-multi-live-primary-{suffix}"
    backup_router_name = f"fleetrmw-multi-live-backup-{suffix}"
    install_base = LIVE_PLAN_INSTALL_BASE
    plan_dir = root / f".tmp_fleetrmw_multi_live_plan_{suffix}"
    plan_file_host = plan_dir / "path_plan.txt"
    primary_telemetry_host = plan_dir / "primary_router_telemetry.jsonl"
    backup_telemetry_host = plan_dir / "backup_router_telemetry.jsonl"
    primary_netem_status_host = plan_dir / "primary_router_netem_status.json"
    backup_netem_status_host = plan_dir / "backup_router_netem_status.json"
    subscriber_telemetry_hosts = {
        spec.topic: plan_dir / f"subscriber_{spec.robot_id}_{spec.kind}.jsonl"
        for spec in topic_specs
    }
    plan_file_container = f"/work/{plan_file_host.relative_to(root)}"
    primary_telemetry_container = f"/work/{primary_telemetry_host.relative_to(root)}"
    backup_telemetry_container = f"/work/{backup_telemetry_host.relative_to(root)}"
    primary_netem_status_container = f"/work/{primary_netem_status_host.relative_to(root)}"
    backup_netem_status_container = f"/work/{backup_netem_status_host.relative_to(root)}"
    subscriber_telemetry_containers = {
        topic: f"/work/{path.relative_to(root)}"
        for topic, path in subscriber_telemetry_hosts.items()
    }
    endpoint_binary = (
        f"{install_base}/rmw_fleetqox_cpp/lib/rmw_fleetqox_cpp/"
        "fleetrmw_reliable_interprocess_probe"
    )
    router_binary = (
        f"{install_base}/rmw_fleetqox_cpp/lib/rmw_fleetqox_cpp/fleetrmw_udp_router_probe"
    )
    initial_path_plan = path_plan_for_specs(topic_specs, final=False)
    final_path_plan = path_plan_for_specs(topic_specs, final=True)
    subscriber_names = {
        spec.topic: f"fleetrmw-multi-live-sub-{index}-{suffix}"
        for index, spec in enumerate(topic_specs)
    }
    publisher_names = {
        spec.topic: f"fleetrmw-multi-live-pub-{index}-{suffix}"
        for index, spec in enumerate(topic_specs)
    }
    all_container_names = [
        primary_router_name,
        backup_router_name,
        *subscriber_names.values(),
        *publisher_names.values(),
    ]
    controller: LivePathPlanController | None = None
    controller_thread: threading.Thread | None = None
    stop_controller = threading.Event()
    failure_phase = "init"
    build_performed = False
    primary_netem = netem_config_for_path(
        telemetry_profile,
        path_id="primary_wifi",
        loss_scale=netem_loss_scale,
        repetition_seed=repetition_seed,
    )
    backup_netem = netem_config_for_path(
        telemetry_profile,
        path_id="backup_5g",
        loss_scale=netem_loss_scale,
        repetition_seed=repetition_seed,
    )
    router_exit_suffix = router_netem_drain_suffix(netem_drain_s) if enable_netem else ""
    stochastic_netem = enable_netem and netem_loss_scale > 0.0
    primary_expected_ack_nack_forwarded = 0 if stochastic_netem else 3 * len(control_specs)
    backup_expected_ack_nack_forwarded = 0 if stochastic_netem else 5 * max(1, len(state_specs))
    control_min_ack_nack_received = 0 if stochastic_netem else 3
    state_min_ack_nack_received = 0 if stochastic_netem else 2
    terminal_horizon = terminal_horizon_for_profile(
        telemetry_profile,
        robot_count=robot_count,
        loss_scale=netem_loss_scale,
    )
    adaptive_data_repeats = terminal_horizon.proactive_data_repeats if stochastic_netem else 0
    if control_proactive_data_repeats is None:
        control_proactive_data_repeats = adaptive_data_repeats
    else:
        control_proactive_data_repeats = max(
            control_proactive_data_repeats,
            adaptive_data_repeats,
        )
    if state_proactive_data_repeats is None:
        state_proactive_data_repeats = adaptive_data_repeats
    else:
        state_proactive_data_repeats = max(
            state_proactive_data_repeats,
            adaptive_data_repeats,
        )
    control_payloads_per_publisher = 3
    state_payloads_per_publisher = 3
    terminal_guard_required_sequence = terminal_horizon.required_sequence
    control_wire_payloads_per_publisher = terminal_horizon.wire_payloads_per_publisher
    state_wire_payloads_per_publisher = terminal_horizon.wire_payloads_per_publisher
    primary_expected_frames = (
        len(control_specs) *
        terminal_guard_required_sequence *
        (1 + control_proactive_data_repeats)
    )
    backup_expected_frames = (
        len(state_specs) *
        terminal_guard_required_sequence *
        (1 + state_proactive_data_repeats) +
        len(control_specs) * 2 * (1 + control_proactive_data_repeats)
    )
    primary_expected_topic_sequences = ";".join(
        f"{spec.topic}={terminal_guard_required_sequence}"
        for spec in control_specs
    )
    primary_expected_topic_sequence_args = (
        " --expected-forwarded-topic-source-sequences "
        f"{shlex.quote(primary_expected_topic_sequences)}"
        if primary_expected_topic_sequences
        else ""
    )
    backup_expected_topic_sequences = ";".join(
        f"{spec.topic}={terminal_guard_required_sequence}"
        for spec in state_specs
    )
    backup_expected_topic_sequence_args = (
        " --expected-forwarded-topic-source-sequences "
        f"{shlex.quote(backup_expected_topic_sequences)}"
        if backup_expected_topic_sequences
        else ""
    )
    router_timeout_ms = max(26000, robot_count * 10000)

    try:
        plan_dir.mkdir(parents=True, exist_ok=True)
        failure_phase = "create_docker_network"
        run(["docker", "network", "create", network])
        failure_phase = "build_rmw_package"
        build_performed = ensure_live_plan_build(root, image, clean=not reuse_build)
        failure_phase = "start_live_path_controller"
        controller = live_controller_for_probe(
            plan_file=plan_file_host,
            telemetry_files=(primary_telemetry_host, backup_telemetry_host),
            subscriber_telemetry_files=tuple(subscriber_telemetry_hosts.values()),
            topic_specs=topic_specs,
        )
        initial_plan = controller.poll_once().path_plan_env
        controller_thread = threading.Thread(
            target=run_controller_loop,
            args=(controller, stop_controller),
            daemon=True,
        )
        controller_thread.start()
        failure_phase = "start_primary_router"
        start_container(
            root=root,
            image=image,
            name=primary_router_name,
            network=network,
            command=(
                f"source /opt/ros/jazzy/setup.bash && source {install_base}/setup.bash && "
                + (
                    netem_shell_prefix(
                        primary_netem,
                        status_file=primary_netem_status_container,
                        require=require_netem,
                    )
                    if enable_netem
                    else ""
                )
                +
                f"{router_binary} --bind 0.0.0.0:48420 "
                "--path-id primary_wifi "
                f"--telemetry-file {primary_telemetry_container} "
                f"--telemetry-latency-ms {telemetry_profile.primary_latency_ms:g} "
                f"--telemetry-jitter-ms {telemetry_profile.primary_jitter_ms:g} "
                f"--telemetry-loss {telemetry_profile.primary_loss:g} "
                f"--telemetry-nack-rate {telemetry_profile.primary_nack_rate:g} "
                "--telemetry-deadline-miss-ratio "
                f"{telemetry_profile.primary_deadline_miss_ratio:g} "
                f"--telemetry-capacity-bytes {telemetry_profile.capacity_bytes} "
                f"--expected-frames {primary_expected_frames} --expected-ack-nack-frames 0 "
                f"--expected-ack-nack-forwarded {primary_expected_ack_nack_forwarded} "
                f"--expected-route-advertisements {topic_count} "
                f"--expected-graph-advertisements {topic_count} --timeout-ms {router_timeout_ms}"
                f" --post-satisfaction-ms {terminal_horizon.router_dwell_ms}"
                f"{primary_expected_topic_sequence_args}"
                f"{router_exit_suffix}"
            ),
            extra_args=("--cap-add", "NET_ADMIN") if enable_netem else (),
        )
        failure_phase = "start_backup_router"
        start_container(
            root=root,
            image=image,
            name=backup_router_name,
            network=network,
            command=(
                f"source /opt/ros/jazzy/setup.bash && source {install_base}/setup.bash && "
                + (
                    netem_shell_prefix(
                        backup_netem,
                        status_file=backup_netem_status_container,
                        require=require_netem,
                    )
                    if enable_netem
                    else ""
                )
                +
                f"{router_binary} --bind 0.0.0.0:48421 "
                "--path-id backup_5g "
                f"--telemetry-file {backup_telemetry_container} "
                f"--telemetry-latency-ms {telemetry_profile.backup_latency_ms:g} "
                f"--telemetry-jitter-ms {telemetry_profile.backup_jitter_ms:g} "
                f"--telemetry-loss {telemetry_profile.backup_loss:g} "
                f"--telemetry-nack-rate {telemetry_profile.backup_nack_rate:g} "
                "--telemetry-deadline-miss-ratio "
                f"{telemetry_profile.backup_deadline_miss_ratio:g} "
                f"--telemetry-capacity-bytes {telemetry_profile.capacity_bytes} "
                f"--expected-frames {backup_expected_frames} --expected-ack-nack-frames 0 "
                f"--expected-ack-nack-forwarded {backup_expected_ack_nack_forwarded} "
                f"--expected-route-advertisements {topic_count} "
                f"--expected-graph-advertisements {topic_count} --timeout-ms {router_timeout_ms}"
                f" --post-satisfaction-ms {terminal_horizon.router_dwell_ms}"
                f"{backup_expected_topic_sequence_args}"
                f"{router_exit_suffix}"
            ),
            extra_args=("--cap-add", "NET_ADMIN") if enable_netem else (),
        )
        time.sleep(0.8)
        for spec in topic_specs:
            failure_phase = f"start_subscriber:{spec.topic}"
            start_subscriber(
                root=root,
                image=image,
                name=subscriber_names[spec.topic],
                network=network,
                install_base=install_base,
                endpoint_binary=endpoint_binary,
                topic=spec.topic,
                robot_id=spec.robot_id,
                telemetry_file=subscriber_telemetry_containers[spec.topic],
                primary_router_name=primary_router_name,
                backup_router_name=backup_router_name,
                timeout_ms=router_timeout_ms,
                post_recovery_payload=STATE_TERMINAL_GUARD_PAYLOAD,
            )
        time.sleep(terminal_horizon.startup_settle_ms / 1000.0)
        for spec in control_specs:
            failure_phase = f"start_control_publisher:{spec.topic}"
            start_publisher_container(
                root=root,
                image=image,
                name=publisher_names[spec.topic],
                network=network,
                install_base=install_base,
                endpoint_binary=endpoint_binary,
                topic=spec.topic,
                plan_file=plan_file_container,
                primary_router_name=primary_router_name,
                backup_router_name=backup_router_name,
                min_ack_nack_received=control_min_ack_nack_received,
                proactive_data_repeats=control_proactive_data_repeats,
                pre_publish_wait_ms=terminal_horizon.pre_publish_wait_ms,
                pre_payload_warmup_count=terminal_horizon.pre_payload_warmup_count,
                pre_payload_warmup_ack_count=terminal_horizon.pre_payload_warmup_ack_count,
                pre_payload_warmup_ack_timeout_ms=terminal_horizon.pre_payload_warmup_ack_timeout_ms,
                app_repair_cycle_count=terminal_horizon.app_repair_cycle_count,
                tail_repair_repeat_count=terminal_horizon.tail_repair_repeat_count,
                publish_interval_ms=700,
                hold_ms=4500,
                post_recovery_payload=STATE_TERMINAL_GUARD_PAYLOAD,
                post_recovery_before_hold=True,
                post_recovery_repeat_count=terminal_horizon.repeat_count,
            )
        final_plan_ready = wait_for_path_plan(plan_file_host, final_path_plan, timeout_s=6.0)
        if final_plan_ready and terminal_horizon.post_plan_settle_ms > 0:
            time.sleep(terminal_horizon.post_plan_settle_ms / 1000.0)
        for spec in state_specs:
            failure_phase = f"start_state_publisher:{spec.topic}"
            start_publisher_container(
                root=root,
                image=image,
                name=publisher_names[spec.topic],
                network=network,
                install_base=install_base,
                endpoint_binary=endpoint_binary,
                topic=spec.topic,
                plan_file=plan_file_container,
                primary_router_name=primary_router_name,
                backup_router_name=backup_router_name,
                min_ack_nack_received=state_min_ack_nack_received,
                proactive_data_repeats=state_proactive_data_repeats,
                pre_publish_wait_ms=terminal_horizon.pre_publish_wait_ms,
                pre_payload_warmup_count=terminal_horizon.pre_payload_warmup_count,
                pre_payload_warmup_ack_count=terminal_horizon.pre_payload_warmup_ack_count,
                pre_payload_warmup_ack_timeout_ms=terminal_horizon.pre_payload_warmup_ack_timeout_ms,
                app_repair_cycle_count=terminal_horizon.app_repair_cycle_count,
                tail_repair_repeat_count=terminal_horizon.tail_repair_repeat_count,
                publish_interval_ms=500,
                hold_ms=5500,
                post_recovery_payload=STATE_TERMINAL_GUARD_PAYLOAD,
                post_recovery_before_hold=True,
                post_recovery_repeat_count=terminal_horizon.repeat_count,
            )

        failure_phase = "wait_publishers"
        publisher_returncodes = {
            spec.topic: int(run(["docker", "wait", publisher_names[spec.topic]]).stdout.strip())
            for spec in topic_specs
        }
        failure_phase = "wait_subscribers"
        subscriber_returncodes = {
            spec.topic: int(run(["docker", "wait", subscriber_names[spec.topic]]).stdout.strip())
            for spec in topic_specs
        }
        failure_phase = "wait_primary_router"
        primary_router_returncode = int(run(["docker", "wait", primary_router_name]).stdout.strip())
        failure_phase = "wait_backup_router"
        backup_router_returncode = int(run(["docker", "wait", backup_router_name]).stdout.strip())
        if controller is not None:
            controller.poll_once()
        stop_controller.set()
        if controller_thread is not None:
            controller_thread.join(timeout=2.0)

        failure_phase = "collect_component_logs"
        publisher_logs = {
            spec.topic: run(["docker", "logs", publisher_names[spec.topic]]).stdout.strip()
            for spec in topic_specs
        }
        subscriber_logs = {
            spec.topic: run(["docker", "logs", subscriber_names[spec.topic]]).stdout.strip()
            for spec in topic_specs
        }
        primary_router_log = run(["docker", "logs", primary_router_name]).stdout.strip()
        backup_router_log = run(["docker", "logs", backup_router_name]).stdout.strip()
        publisher_results = {
            topic: parse_last_json(log)
            for topic, log in publisher_logs.items()
        }
        subscriber_results = {
            topic: parse_last_json(log)
            for topic, log in subscriber_logs.items()
        }
        primary_router_result = parse_last_json(primary_router_log)
        backup_router_result = parse_last_json(backup_router_log)
        controller_summary = controller.summary() if controller is not None else {}
        controller_final_path_plan = str(
            (controller_summary.get("last_plan") or {}).get("path_plan_env", "")
            if isinstance(controller_summary.get("last_plan"), dict)
            else ""
        )
        subscriber_telemetry = {
            spec.flow_id: read_jsonl(subscriber_telemetry_hosts[spec.topic])
            for spec in topic_specs
        }
        robot_state_ids = {
            str(state.get("robot_id", ""))
            for state in controller_summary.get("robot_states", [])
            if isinstance(state, dict)
        }
        primary_topics = set(primary_router_result.get("topics", []))
        backup_topics = set(backup_router_result.get("topics", []))
        delivery_by_topic = {
            spec.topic: {"one", "two", "three"}.issubset(
                set(subscriber_results[spec.topic].get("payloads", []))
            )
            for spec in topic_specs
        }
        control_delivery_ok = all(delivery_by_topic[spec.topic] for spec in control_specs)
        state_delivery_ok = all(delivery_by_topic[spec.topic] for spec in state_specs)
        delivery_ok = control_delivery_ok and state_delivery_ok
        control_publisher_result = aggregate_components(
            [publisher_results[spec.topic] for spec in control_specs],
            kind="publisher",
        )
        state_publisher_result = aggregate_components(
            [publisher_results[spec.topic] for spec in state_specs],
            kind="publisher",
        )
        control_subscriber_result = aggregate_components(
            [subscriber_results[spec.topic] for spec in control_specs],
            kind="subscriber",
        )
        state_subscriber_result = aggregate_components(
            [subscriber_results[spec.topic] for spec in state_specs],
            kind="subscriber",
        )
        netem_status = {
            "primary_wifi": read_json(primary_netem_status_host),
            "backup_5g": read_json(backup_netem_status_host),
        }
        netem_ok = netem_status_ok(
            netem_status,
            enabled=enable_netem,
            required=require_netem,
        )
        primary_router_ok = (
            primary_router_returncode == 0 and primary_router_result.get("status") == "ok"
        )
        backup_router_ok = (
            backup_router_returncode == 0 and backup_router_result.get("status") == "ok"
        )
        if stochastic_netem and delivery_ok and netem_ok:
            primary_router_ok = primary_router_result.get("status") in {"ok", "failed"}
            backup_router_ok = backup_router_result.get("status") in {"ok", "failed"}
        component_ok = (
            all(code == 0 for code in publisher_returncodes.values()) and
            all(code == 0 for code in subscriber_returncodes.values()) and
            all(result.get("status") == "ok" for result in publisher_results.values()) and
            all(result.get("status") == "ok" for result in subscriber_results.values())
        )
        expected_robot_ids = {spec.robot_id for spec in topic_specs}
        status = (
            component_ok and
            primary_router_ok and
            backup_router_ok and
            initial_plan == initial_path_plan and
            final_plan_ready and
            controller_summary.get("record_count", 0) >= topic_count and
            controller_summary.get("subscriber_record_count", 0) >= topic_count and
            controller_final_path_plan == final_path_plan and
            all(spec.topic in primary_topics or spec.flow_class is FlowClass.STATE for spec in topic_specs) and
            all(spec.topic in backup_topics for spec in state_specs) and
            control_delivery_ok and
            state_delivery_ok and
            expected_robot_ids.issubset(robot_state_ids) and
            netem_ok
        )
        return {
            "schema_version": SCHEMA_VERSION,
            "status": "ok" if status else "failed",
            "profile": telemetry_profile.label,
            "image": image,
            "repetition_seed": repetition_seed,
            "robot_count": robot_count,
            "topic_count": topic_count,
            "topic_specs": [spec.as_dict() for spec in topic_specs],
            "profile_config": telemetry_profile.as_dict(),
            "netem_enabled": enable_netem,
            "netem_required": require_netem,
            "netem_loss_scale": netem_loss_scale,
            "netem_drain_s": netem_drain_s,
            "netem_seed_semantics": NETEM_SEED_SEMANTICS if enable_netem else "",
            "stochastic_netem": stochastic_netem,
            "reuse_build": reuse_build,
            "build_performed": build_performed,
            "control_duplicate_dedup_required": False,
            "control_duplicate_ack_required": False,
            "state_duplicate_dedup_required": False,
            "state_duplicate_ack_required": False,
            "control_proactive_data_repeats": control_proactive_data_repeats,
            "state_proactive_data_repeats": state_proactive_data_repeats,
            "state_terminal_guard_payload": STATE_TERMINAL_GUARD_PAYLOAD,
            "terminal_guard_algorithm": terminal_horizon.algorithm,
            "terminal_guard_repeat_count": terminal_horizon.repeat_count,
            "terminal_guard_router_dwell_ms": terminal_horizon.router_dwell_ms,
            "terminal_guard_required_sequence": terminal_guard_required_sequence,
            "terminal_horizon": terminal_horizon.as_dict(),
            "control_payloads_per_publisher": control_payloads_per_publisher,
            "state_payloads_per_publisher": state_payloads_per_publisher,
            "control_wire_payloads_per_publisher": control_wire_payloads_per_publisher,
            "state_wire_payloads_per_publisher": state_wire_payloads_per_publisher,
            "primary_expected_forwarded_topic_source_sequences": primary_expected_topic_sequences,
            "backup_expected_forwarded_topic_source_sequences": backup_expected_topic_sequences,
            "netem": {
                "primary_wifi": primary_netem,
                "backup_5g": backup_netem,
            } if enable_netem else {},
            "netem_status_files": {
                "primary_wifi": str(primary_netem_status_host),
                "backup_5g": str(backup_netem_status_host),
            } if enable_netem else {},
            "netem_status": netem_status if enable_netem else {},
            "router_telemetry_schema_version": ROUTER_TELEMETRY_SCHEMA_VERSION,
            "subscriber_telemetry_schema_version": SUBSCRIBER_TELEMETRY_SCHEMA_VERSION,
            "docker_network": network,
            "topics": [spec.topic for spec in topic_specs],
            "initial_path_plan": initial_plan,
            "expected_initial_path_plan": initial_path_plan,
            "expected_final_path_plan": final_path_plan,
            "final_plan_ready": final_plan_ready,
            "controller_final_path_plan": controller_final_path_plan,
            "path_plan_file": str(plan_file_host),
            "primary_telemetry_file": str(primary_telemetry_host),
            "backup_telemetry_file": str(backup_telemetry_host),
            "subscriber_telemetry_files": {
                spec.flow_id: str(subscriber_telemetry_hosts[spec.topic])
                for spec in topic_specs
            },
            "controller": controller_summary,
            "control_publisher_returncode": max(
                [publisher_returncodes[spec.topic] for spec in control_specs] or [0]
            ),
            "state_publisher_returncode": max(
                [publisher_returncodes[spec.topic] for spec in state_specs] or [0]
            ),
            "control_subscriber_returncode": max(
                [subscriber_returncodes[spec.topic] for spec in control_specs] or [0]
            ),
            "state_subscriber_returncode": max(
                [subscriber_returncodes[spec.topic] for spec in state_specs] or [0]
            ),
            "primary_router_returncode": primary_router_returncode,
            "backup_router_returncode": backup_router_returncode,
            "control_publisher": control_publisher_result,
            "state_publisher": state_publisher_result,
            "control_subscriber": control_subscriber_result,
            "state_subscriber": state_subscriber_result,
            "publishers": publisher_results,
            "subscribers": subscriber_results,
            "publisher_returncodes": publisher_returncodes,
            "subscriber_returncodes": subscriber_returncodes,
            "delivery_by_topic": delivery_by_topic,
            "primary_router": primary_router_result,
            "backup_router": backup_router_result,
            "primary_telemetry": read_jsonl(primary_telemetry_host),
            "backup_telemetry": read_jsonl(backup_telemetry_host),
            "subscriber_telemetry": subscriber_telemetry,
            "publisher_logs": publisher_logs,
            "subscriber_logs": subscriber_logs,
            "primary_router_logs": primary_router_log,
            "backup_router_logs": backup_router_log,
        }
    except subprocess.CalledProcessError as exc:
        failure = {
            "kind": "subprocess_error",
            "phase": failure_phase,
            "command": command_to_text(exc.cmd),
            "returncode": exc.returncode,
            "stdout_excerpt": text_tail(exc.stdout),
            "stderr_excerpt": text_tail(exc.stderr),
            "container_logs": collect_container_logs(all_container_names),
        }
        return {
            "schema_version": SCHEMA_VERSION,
            "status": "failed",
            "profile": telemetry_profile.label,
            "image": image,
            "repetition_seed": repetition_seed,
            "robot_count": robot_count,
            "topic_count": topic_count,
            "profile_config": telemetry_profile.as_dict(),
            "netem_enabled": enable_netem,
            "netem_required": require_netem,
            "netem_loss_scale": netem_loss_scale,
            "netem_drain_s": netem_drain_s,
            "netem_seed_semantics": NETEM_SEED_SEMANTICS if enable_netem else "",
            "stochastic_netem": stochastic_netem,
            "reuse_build": reuse_build,
            "build_performed": build_performed,
            "netem": {
                "primary_wifi": primary_netem,
                "backup_5g": backup_netem,
            } if enable_netem else {},
            "netem_status": {
                "primary_wifi": read_json(primary_netem_status_host),
                "backup_5g": read_json(backup_netem_status_host),
            } if enable_netem else {},
            "docker_network": network,
            "failure": failure,
            "returncode": exc.returncode,
            "stdout": exc.stdout,
            "stderr": exc.stderr,
        }
    finally:
        stop_controller.set()
        if controller_thread is not None and controller_thread.is_alive():
            controller_thread.join(timeout=2.0)
        run(["docker", "rm", "-f", *all_container_names], check=False)
        run(["docker", "network", "rm", network], check=False)
        if cleanup_build:
            cleanup_live_plan_build(root, image)
        shutil.rmtree(plan_dir, ignore_errors=True)


def topic_demand_for_spec(spec: LiveTopicSpec) -> FleetTopicDemand:
    if spec.flow_class is FlowClass.CONTROL:
        demand = FleetFlowDemand(
            flow_id=spec.flow_id,
            robot_id=spec.robot_id,
            flow_class=FlowClass.CONTROL,
            deadline_ms=30.0,
            payload_bytes=680,
            rate_hz=20.0,
            criticality=0.95,
            qoe_weight=0.10,
            age_ms=12.0,
            lifespan_ms=90.0,
        )
    else:
        demand = FleetFlowDemand(
            flow_id=spec.flow_id,
            robot_id=spec.robot_id,
            flow_class=FlowClass.STATE,
            deadline_ms=120.0,
            payload_bytes=900,
            rate_hz=10.0,
            criticality=0.45,
            qoe_weight=0.02,
            age_ms=10.0,
            lifespan_ms=250.0,
        )
    return FleetTopicDemand(spec.topic, demand)


def aggregate_components(components: list[dict[str, Any]], *, kind: str) -> dict[str, Any]:
    if not components:
        return {"status": "missing", "component_count": 0}
    status = "ok" if all(item.get("status") == "ok" for item in components) else "failed"
    payloads: list[str] = []
    for component in components:
        component_payloads = component.get("payloads", [])
        if isinstance(component_payloads, list):
            payloads.extend(str(payload) for payload in component_payloads)
    result: dict[str, Any] = {
        "status": status,
        "component_count": len(components),
        "payloads": payloads,
        "socket_frames_sent": sum(int(component.get("socket_frames_sent", 0)) for component in components),
        "socket_frames_received": sum(
            int(component.get("socket_frames_received", 0)) for component in components
        ),
        "ack_nack_sent": sum(int(component.get("ack_nack_sent", 0)) for component in components),
        "idle_repair_ack_nack_sent": sum(
            int(component.get("idle_repair_ack_nack_sent", 0)) for component in components
        ),
        "ack_nack_received": sum(int(component.get("ack_nack_received", 0)) for component in components),
        "ack_nack_duplicate_received": sum(
            int(component.get("ack_nack_duplicate_received", 0)) for component in components
        ),
        "duplicate_data_frames_deduped": sum(
            int(component.get("duplicate_data_frames_deduped", 0)) for component in components
        ),
        "fleet_plan_frames": sum(int(component.get("fleet_plan_frames", 0)) for component in components),
        "fleet_plan_redundant_frames": sum(
            int(component.get("fleet_plan_redundant_frames", 0)) for component in components
        ),
        "fleet_plan_selected_path_count": sum(
            int(component.get("fleet_plan_selected_path_count", 0)) for component in components
        ),
    }
    if kind == "publisher":
        last_paths = [
            str(component.get("fleet_plan_last_paths", ""))
            for component in components
            if component.get("fleet_plan_last_paths")
        ]
        result["fleet_plan_last_paths"] = last_paths[-1] if last_paths else ""
    return result


def live_controller_for_probe(
    *,
    plan_file: Path,
    telemetry_files: tuple[Path, ...],
    subscriber_telemetry_files: tuple[Path, ...],
    topic_specs: list[LiveTopicSpec] | None = None,
) -> LivePathPlanController:
    topic_specs = topic_specs or live_topic_specs_for_robot_count(1)
    demands = tuple(topic_demand_for_spec(spec) for spec in topic_specs)
    robot_ids = sorted({spec.robot_id for spec in topic_specs})
    return LivePathPlanController(
        LivePathPlanControllerConfig(
            plan_file=plan_file,
            telemetry_files=telemetry_files,
            subscriber_telemetry_files=subscriber_telemetry_files,
            demands=demands,
            seed_observations=(
                PathObservation(
                    "primary_wifi",
                    latency_ms=10.0,
                    jitter_ms=1.0,
                    loss=0.01,
                    nack_rate=0.01,
                    deadline_miss_ratio=0.0,
                    bandwidth_utilization=0.10,
                ),
                PathObservation(
                    "backup_5g",
                    latency_ms=24.0,
                    jitter_ms=5.0,
                    loss=0.03,
                    nack_rate=0.03,
                    deadline_miss_ratio=0.05,
                    bandwidth_utilization=0.42,
                ),
            ),
            robot_states=(
                *(
                    RobotQoEState(
                        robot_id,
                        control_delivery_ratio=0.90 if index == 0 else 0.99,
                        deadline_miss_ratio=0.18 if index == 0 else 0.01,
                        qoe_score=0.78 if index == 0 else 0.95,
                    )
                    for index, robot_id in enumerate(robot_ids)
                ),
            ),
            optimizer=FleetOptimizerConfig(
                capacity_bytes_per_tick=max(8192, len(robot_ids) * 4096),
                redundant_deadline_ms=35.0,
                redundancy_risk_threshold=1.0,
            ),
            telemetry_alpha=1.0,
            min_dwell_ticks=0,
            switch_score_margin=0.20,
        )
    )


def start_subscriber(
    *,
    root: Path,
    image: str,
    name: str,
    network: str,
    install_base: str,
    endpoint_binary: str,
    topic: str,
    robot_id: str,
    telemetry_file: str,
    primary_router_name: str,
    backup_router_name: str,
    timeout_ms: int = 16000,
    post_recovery_payload: str = "",
    require_post_recovery_payload: bool = False,
    post_payload_wait_ms: int = 0,
) -> str:
    post_recovery_args = (
        f" --post-recovery-payload {shlex.quote(post_recovery_payload)}"
        if post_recovery_payload
        else ""
    )
    if post_recovery_payload and require_post_recovery_payload:
        post_recovery_args += " --require-post-recovery-payload"
    if post_recovery_payload and post_payload_wait_ms > 0:
        post_recovery_args += f" --post-payload-wait-ms {post_payload_wait_ms}"
    return start_container(
        root=root,
        image=image,
        name=name,
        network=network,
        command=(
            f"source /opt/ros/jazzy/setup.bash && source {install_base}/setup.bash && "
            "export RMW_IMPLEMENTATION=rmw_fleetqox_cpp && "
            "FLEETQOX_RMW_BIND=0.0.0.0:48422 "
            f"FLEETQOX_RMW_PEERS={primary_router_name}:48420,{backup_router_name}:48421 "
            f"{endpoint_binary} --mode subscriber --topic {topic} "
            f"--subscriber-telemetry-file {telemetry_file} "
            f"--robot-id {robot_id} --subscriber-deadline-ms 35 "
            f"--timeout-ms {timeout_ms}"
            f"{post_recovery_args}"
        ),
    )


def run_publisher(
    *,
    root: Path,
    image: str,
    network: str,
    install_base: str,
    endpoint_binary: str,
    topic: str,
    plan_file: str,
    primary_router_name: str,
    backup_router_name: str,
    min_ack_nack_received: int,
    proactive_data_repeats: int,
    publish_interval_ms: int,
    pre_publish_wait_ms: int = 0,
    pre_payload_warmup_count: int = 0,
    pre_payload_warmup_ack_count: int = 0,
    pre_payload_warmup_ack_timeout_ms: int = 0,
    app_repair_cycle_count: int = 0,
    tail_repair_repeat_count: int = 0,
    hold_ms: int = 2500,
    post_recovery_payload: str = "",
    post_recovery_before_hold: bool = False,
    post_recovery_repeat_count: int = 1,
) -> subprocess.CompletedProcess[str]:
    command = publisher_command(
        install_base=install_base,
        endpoint_binary=endpoint_binary,
        topic=topic,
        plan_file=plan_file,
        primary_router_name=primary_router_name,
        backup_router_name=backup_router_name,
        min_ack_nack_received=min_ack_nack_received,
        proactive_data_repeats=proactive_data_repeats,
        pre_publish_wait_ms=pre_publish_wait_ms,
        pre_payload_warmup_count=pre_payload_warmup_count,
        pre_payload_warmup_ack_count=pre_payload_warmup_ack_count,
        pre_payload_warmup_ack_timeout_ms=pre_payload_warmup_ack_timeout_ms,
        app_repair_cycle_count=app_repair_cycle_count,
        tail_repair_repeat_count=tail_repair_repeat_count,
        publish_interval_ms=publish_interval_ms,
        hold_ms=hold_ms,
        post_recovery_payload=post_recovery_payload,
        post_recovery_before_hold=post_recovery_before_hold,
        post_recovery_repeat_count=post_recovery_repeat_count,
    )
    return run(
        [
            "docker",
            "run",
            "--rm",
            "--entrypoint",
            "/bin/bash",
            "--network",
            network,
            "-v",
            f"{root}:/work",
            "-w",
            "/work",
            image,
            "-lc",
            command,
        ],
    )


def start_publisher_container(
    *,
    root: Path,
    image: str,
    name: str,
    network: str,
    install_base: str,
    endpoint_binary: str,
    topic: str,
    plan_file: str,
    primary_router_name: str,
    backup_router_name: str,
    min_ack_nack_received: int,
    proactive_data_repeats: int,
    publish_interval_ms: int,
    pre_publish_wait_ms: int = 0,
    pre_payload_warmup_count: int = 0,
    pre_payload_warmup_ack_count: int = 0,
    pre_payload_warmup_ack_timeout_ms: int = 0,
    app_repair_cycle_count: int = 0,
    tail_repair_repeat_count: int = 0,
    hold_ms: int = 2500,
    post_recovery_payload: str = "",
    post_recovery_before_hold: bool = False,
    post_recovery_repeat_count: int = 1,
) -> str:
    return start_container(
        root=root,
        image=image,
        name=name,
        network=network,
        command=publisher_command(
            install_base=install_base,
            endpoint_binary=endpoint_binary,
            topic=topic,
            plan_file=plan_file,
            primary_router_name=primary_router_name,
            backup_router_name=backup_router_name,
            min_ack_nack_received=min_ack_nack_received,
            proactive_data_repeats=proactive_data_repeats,
            pre_publish_wait_ms=pre_publish_wait_ms,
            pre_payload_warmup_count=pre_payload_warmup_count,
            pre_payload_warmup_ack_count=pre_payload_warmup_ack_count,
            pre_payload_warmup_ack_timeout_ms=pre_payload_warmup_ack_timeout_ms,
            app_repair_cycle_count=app_repair_cycle_count,
            tail_repair_repeat_count=tail_repair_repeat_count,
            publish_interval_ms=publish_interval_ms,
            hold_ms=hold_ms,
            post_recovery_payload=post_recovery_payload,
            post_recovery_before_hold=post_recovery_before_hold,
            post_recovery_repeat_count=post_recovery_repeat_count,
        ),
    )


def publisher_command(
    *,
    install_base: str,
    endpoint_binary: str,
    topic: str,
    plan_file: str,
    primary_router_name: str,
    backup_router_name: str,
    min_ack_nack_received: int,
    proactive_data_repeats: int,
    publish_interval_ms: int,
    pre_publish_wait_ms: int = 0,
    pre_payload_warmup_count: int = 0,
    pre_payload_warmup_ack_count: int = 0,
    pre_payload_warmup_ack_timeout_ms: int = 0,
    app_repair_cycle_count: int = 0,
    tail_repair_repeat_count: int = 0,
    hold_ms: int = 2500,
    post_recovery_payload: str = "",
    post_recovery_before_hold: bool = False,
    post_recovery_repeat_count: int = 1,
) -> str:
    post_recovery_args = (
        f" --post-recovery-payload {shlex.quote(post_recovery_payload)}"
        if post_recovery_payload
        else ""
    )
    if post_recovery_payload and post_recovery_before_hold:
        post_recovery_args += " --post-recovery-before-hold"
    if post_recovery_payload:
        post_recovery_args += f" --post-recovery-repeat-count {max(post_recovery_repeat_count, 1)}"
    return (
        f"source /opt/ros/jazzy/setup.bash && source {install_base}/setup.bash && "
        "export RMW_IMPLEMENTATION=rmw_fleetqox_cpp && "
        "FLEETQOX_RMW_BIND=0.0.0.0:0 "
        "FLEETQOX_RMW_PEER_POLICY=fleet_plan "
        f"FLEETQOX_RMW_PROACTIVE_DATA_REPEATS={proactive_data_repeats} "
        "FLEETQOX_RMW_PROACTIVE_DATA_REPEAT_INTERVAL_MS=10 "
        f"FLEETQOX_RMW_FLEET_PATH_PLAN_FILE='{plan_file}' "
        f"FLEETQOX_RMW_PEERS=primary_wifi={primary_router_name}:48420,"
        f"backup_5g={backup_router_name}:48421 "
        f"{endpoint_binary} --mode publisher --topic {topic} "
        f"--pre-publish-wait-ms {max(pre_publish_wait_ms, 0)} "
        f"--pre-payload-warmup-count {max(pre_payload_warmup_count, 0)} "
        f"--pre-payload-warmup-payload {ROUTE_WARMUP_PAYLOAD} "
        f"--pre-payload-warmup-ack-count {max(pre_payload_warmup_ack_count, 0)} "
        f"--pre-payload-warmup-ack-timeout-ms {max(pre_payload_warmup_ack_timeout_ms, 0)} "
        f"--app-repair-cycle-count {max(app_repair_cycle_count, 0)} "
        "--app-repair-cycle-payloads one,two,three "
        f"--tail-repair-repeat-count {max(tail_repair_repeat_count, 0)} "
        f"--tail-repair-payload {TAIL_REPAIR_PAYLOAD} "
        f"--publish-interval-ms {publish_interval_ms} --hold-ms {hold_ms} "
        f"--min-retransmissions 0 --min-ack-nack-received {min_ack_nack_received}"
        f"{post_recovery_args}"
    )


def wait_for_path_plan(path: Path, expected: str, *, timeout_s: float) -> bool:
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        if path.exists() and path.read_text(encoding="utf-8").strip() == expected:
            return True
        time.sleep(0.05)
    return path.exists() and path.read_text(encoding="utf-8").strip() == expected


def run_controller_loop(controller: LivePathPlanController, stop: threading.Event) -> None:
    while not stop.wait(0.05):
        controller.poll_once()


def parse_last_json(output: str) -> dict[str, Any]:
    for line in reversed(output.splitlines()):
        stripped = line.strip()
        if stripped.startswith("{"):
            try:
                return json.loads(stripped)
            except json.JSONDecodeError:
                return {"status": "parse_failed", "raw": stripped}
    return {"status": "missing", "raw": output}


def netem_config_for_path(
    profile: RouterPathTelemetryProfile,
    *,
    path_id: str,
    loss_scale: float,
    repetition_seed: int | None = None,
) -> dict[str, object]:
    if path_id == "primary_wifi":
        delay_ms = profile.primary_latency_ms
        jitter_ms = profile.primary_jitter_ms
        loss = profile.primary_loss
        rate_mbit = profile.primary_rate_mbit
    elif path_id == "backup_5g":
        delay_ms = profile.backup_latency_ms
        jitter_ms = profile.backup_jitter_ms
        loss = profile.backup_loss
        rate_mbit = profile.backup_rate_mbit
    else:
        raise ValueError(f"unsupported path_id for netem: {path_id}")
    return {
        "schema_version": NETEM_SCHEMA_VERSION,
        "profile": profile.label,
        "path_id": path_id,
        "device": "eth0",
        "delay_ms": delay_ms,
        "jitter_ms": jitter_ms,
        "loss_percent": min(100.0, loss * 100.0 * loss_scale),
        "loss_model": "random",
        "loss_scale": loss_scale,
        "repetition_seed": repetition_seed,
        "seed_controls_netem_rng": False,
        "rate_mbit": rate_mbit,
    }


def netem_shell_prefix(
    config: dict[str, object],
    *,
    status_file: str,
    require: bool,
) -> str:
    command = (
        "tc qdisc replace dev eth0 root netem "
        f"delay {_float_for_shell(config.get('delay_ms')):g}ms "
        f"{_float_for_shell(config.get('jitter_ms')):g}ms "
        f"loss random {_float_for_shell(config.get('loss_percent')):g}% "
        f"rate {_float_for_shell(config.get('rate_mbit')):g}mbit"
    )
    applied = dict(config, status="applied", command=command)
    failed = dict(config, status="failed", command=command)
    missing = dict(config, status="missing_tc", command=command)
    on_failure = "exit 24" if require else "true"
    return (
        "if command -v tc >/dev/null 2>&1; then "
        f"if {command}; then printf '%s\\n' "
        f"{shlex.quote(json.dumps(applied, sort_keys=True))} > {shlex.quote(status_file)}; "
        f"else printf '%s\\n' "
        f"{shlex.quote(json.dumps(failed, sort_keys=True))} > {shlex.quote(status_file)}; "
        f"{on_failure}; fi; "
        f"else printf '%s\\n' "
        f"{shlex.quote(json.dumps(missing, sort_keys=True))} > {shlex.quote(status_file)}; "
        f"{on_failure}; fi; "
    )


def netem_status_ok(
    statuses: dict[str, Any],
    *,
    enabled: bool,
    required: bool,
) -> bool:
    if not enabled or not required:
        return True
    required_paths = ("primary_wifi", "backup_5g")
    for path_id in required_paths:
        status = statuses.get(path_id)
        if not isinstance(status, dict) or status.get("status") != "applied":
            return False
    return True


def router_netem_drain_suffix(drain_s: float) -> str:
    return f"; rc=$?; sleep {drain_s:g}; exit $rc"


def read_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}
    return value if isinstance(value, dict) else {}


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    rows = []
    for line in path.read_text(encoding="utf-8").splitlines():
        try:
            value = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(value, dict):
            rows.append(value)
    return rows


def _float_for_shell(value: object) -> float:
    try:
        return float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return 0.0


def ensure_live_plan_build(root: Path, image: str, *, clean: bool) -> bool:
    if not clean and live_plan_build_ready(root):
        return False
    docker_shell(
        root,
        image,
        "source /opt/ros/jazzy/setup.bash && "
        f"rm -rf {LIVE_PLAN_BUILD_BASE} {LIVE_PLAN_INSTALL_BASE} {LIVE_PLAN_LOG_BASE} && "
        "colcon "
        f"--log-base {LIVE_PLAN_LOG_BASE} "
        "build --base-paths ros2_ws/src --packages-select rmw_fleetqox_cpp "
        f"--build-base {LIVE_PLAN_BUILD_BASE} --install-base {LIVE_PLAN_INSTALL_BASE} "
        "--cmake-args -DCMAKE_BUILD_TYPE=Release",
    )
    return True


def cleanup_live_plan_build(root: Path, image: str) -> None:
    docker_shell(
        root,
        image,
        f"rm -rf {LIVE_PLAN_BUILD_BASE} {LIVE_PLAN_INSTALL_BASE} {LIVE_PLAN_LOG_BASE}",
        check=False,
    )


def live_plan_build_ready(root: Path) -> bool:
    install = root / LIVE_PLAN_INSTALL_DIR / "rmw_fleetqox_cpp" / "lib" / "rmw_fleetqox_cpp"
    return (
        (install / "fleetrmw_reliable_interprocess_probe").exists()
        and (install / "fleetrmw_udp_router_probe").exists()
    )


def run(cmd: list[str], *, check: bool = True) -> subprocess.CompletedProcess[str]:
    return subprocess.run(cmd, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=check)


def collect_container_logs(container_names: list[str]) -> dict[str, str]:
    logs: dict[str, str] = {}
    for name in container_names:
        result = run(["docker", "logs", name], check=False)
        text = result.stdout
        if result.stderr:
            text = f"{text}\n[stderr]\n{result.stderr}"
        if text.strip():
            logs[name] = text_tail(text)
    return logs


def command_to_text(command: object) -> str:
    if isinstance(command, (list, tuple)):
        return " ".join(shlex.quote(str(part)) for part in command)
    return str(command)


def text_tail(value: object, *, max_chars: int = 2000) -> str:
    text = "" if value is None else str(value)
    text = text.strip()
    if len(text) <= max_chars:
        return text
    return text[-max_chars:]


def docker_shell(
    root: Path,
    image: str,
    command: str,
    *,
    check: bool = True,
) -> subprocess.CompletedProcess[str]:
    return run(
        [
            "docker",
            "run",
            "--rm",
            "--entrypoint",
            "/bin/bash",
            "-v",
            f"{root}:/work",
            "-w",
            "/work",
            image,
            "-lc",
            command,
        ],
        check=check,
    )


def start_container(
    *,
    root: Path,
    image: str,
    name: str,
    network: str,
    command: str,
    extra_args: tuple[str, ...] = (),
) -> str:
    result = run(
        [
            "docker",
            "run",
            "-d",
            "--name",
            name,
            "--network",
            network,
            *extra_args,
            "--entrypoint",
            "/bin/bash",
            "-v",
            f"{root}:/work",
            "-w",
            "/work",
            image,
            "-lc",
            command,
        ]
    )
    return result.stdout.strip()


if __name__ == "__main__":
    raise SystemExit(main())

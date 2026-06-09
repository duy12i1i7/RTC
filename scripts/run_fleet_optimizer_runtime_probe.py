"""Run a deterministic sidecar runtime probe with fleet optimizer actuation."""

from __future__ import annotations

import argparse
from collections import Counter
import json
from pathlib import Path
import sys
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from fleetqox.model import FlowClass
from fleetqox.sidecar_contract import validate_event
from fleetqox.sidecar_runtime import RuntimeConfig, SidecarRuntime


SCHEMA_VERSION = "fleetrmw.fleet_optimizer_runtime_probe.v1"


class MemoryUdp:
    def __init__(self) -> None:
        self.payloads: list[bytes] = []
        self.addrs: list[tuple[str, int]] = []

    def sendto(self, payload: bytes, addr: object) -> None:
        self.payloads.append(payload)
        if isinstance(addr, tuple) and len(addr) == 2:
            self.addrs.append((str(addr[0]), int(addr[1])))

    def close(self) -> None:
        pass


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--robots", type=int, default=6)
    parser.add_argument("--summary-json", default="results_fleet_optimizer/fleet_optimizer_runtime_probe_summary.json")
    parser.add_argument("--markdown", default="docs/FLEET_OPTIMIZER_RUNTIME_ACTUATION_V1.md")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    summary = run_probe(robots=args.robots)
    summary_path = ROOT / args.summary_json
    summary_path.parent.mkdir(parents=True, exist_ok=True)
    summary_path.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    markdown_path = ROOT / args.markdown
    markdown_path.parent.mkdir(parents=True, exist_ok=True)
    markdown_path.write_text(render_markdown(summary, args.summary_json), encoding="utf-8")

    if args.json:
        print(json.dumps(summary, sort_keys=True))
    else:
        print("fleet-optimizer-runtime-probe")
        print(f"  status: {summary['status']}")
        print(f"  emitted: {summary['emitted_packets']}")
        print(f"  redundant_events: {summary['event_mode_counts'].get('redundant', 0)}")
        print(f"  degraded_events: {summary['event_mode_counts'].get('degraded', 0)}")
    return 0 if summary["status"] == "ok" else 1


def run_probe(*, robots: int) -> dict[str, Any]:
    if robots <= 0:
        raise ValueError("robots must be positive")
    batch = runtime_batch(robots)
    runtime = SidecarRuntime(
        RuntimeConfig(
            policy="static_priority",
            control_lease_redundancy=1,
            control_lease_paced_redundancy=False,
            packet_format="event_json",
        )
    )
    memory_udp = MemoryUdp()
    runtime._udp.close()
    runtime._udp = memory_udp
    try:
        response = runtime.process_batch(batch)
    finally:
        runtime.close()

    emitted_events = [
        json.loads(payload.rstrip(b" ").decode("utf-8"))
        for payload in memory_udp.payloads
    ]
    for event in emitted_events:
        validate_event(event)
    first_by_event_id = {}
    for event in emitted_events:
        first_by_event_id.setdefault(int(event["event_id"]), event)
    unique_events = list(first_by_event_id.values())
    annotated = [event for event in unique_events if isinstance(event.get("fleet_optimizer"), dict)]
    event_mode_counts = Counter(str(event.get("fleet_transport_mode", "")) for event in annotated)
    event_action_counts = Counter(str(event.get("action", "")) for event in annotated)
    selected_paths = Counter(
        path
        for event in annotated
        for path in event.get("fleet_transport_paths", [])
        if isinstance(path, str)
    )
    packet_path_counts = Counter(
        str(event.get("fleet_transport_path", "default"))
        for event in emitted_events
    )
    udp_target_counts = Counter(f"{host}:{port}" for host, port in memory_udp.addrs)
    fleet_response = response.get("fleet_optimizer", {})
    redundant_events = event_mode_counts.get("redundant", 0)
    degraded_events = event_mode_counts.get("degraded", 0)
    status = (
        isinstance(fleet_response, dict)
        and fleet_response.get("schema_version") == "fleetrmw.fleet_optimizer_runtime.v1"
        and redundant_events >= robots
        and degraded_events >= 1
        and selected_paths.get("backup_5g", 0) >= robots
        and int(response["emitted"]) > len(unique_events)
        and udp_target_counts.get("127.0.0.1:19102", 0) >= robots
        and udp_target_counts.get("127.0.0.1:19101", 0) >= robots
    )
    return {
        "schema_version": SCHEMA_VERSION,
        "status": "ok" if status else "failed",
        "robots": robots,
        "accepted": response["accepted"],
        "decisions": response["decisions"],
        "emitted_packets": response["emitted"],
        "unique_event_count": len(unique_events),
        "fleet_optimizer": fleet_response,
        "event_mode_counts": dict(event_mode_counts),
        "event_action_counts": dict(event_action_counts),
        "selected_path_counts": dict(selected_paths),
        "packet_path_counts": dict(packet_path_counts),
        "udp_target_counts": dict(udp_target_counts),
        "sample_events": unique_events[: min(6, len(unique_events))],
    }


def runtime_batch(robots: int) -> dict[str, object]:
    flows = []
    for index in range(robots):
        robot_id = f"robot_{index:04d}"
        flows.extend(
            [
                flow_item(
                    robot_id=robot_id,
                    suffix="cmd_vel",
                    flow_class=FlowClass.CONTROL,
                    topic=f"/{robot_id}/cmd_vel",
                    msg_type="geometry_msgs/msg/Twist",
                    deadline_ms=30.0,
                    lifespan_ms=90.0,
                    size=680,
                    rate_hz=20.0,
                    age_ms=12.0,
                    criticality=0.95,
                ),
                flow_item(
                    robot_id=robot_id,
                    suffix="odom",
                    flow_class=FlowClass.STATE,
                    topic=f"/{robot_id}/odom",
                    msg_type="nav_msgs/msg/Odometry",
                    deadline_ms=95.0,
                    lifespan_ms=180.0,
                    size=900,
                    rate_hz=15.0,
                    age_ms=30.0,
                    criticality=0.60,
                ),
                flow_item(
                    robot_id=robot_id,
                    suffix="scan",
                    flow_class=FlowClass.PERCEPTION,
                    topic=f"/{robot_id}/scan",
                    msg_type="sensor_msgs/msg/LaserScan",
                    deadline_ms=180.0,
                    lifespan_ms=320.0,
                    size=4200,
                    rate_hz=8.0,
                    age_ms=50.0,
                    criticality=0.35,
                ),
            ]
        )
    return {
        "type": "batch",
        "scenario": "fleet_optimizer_runtime_probe",
        "timestamp_ms": 0.0,
        "tick": 1,
        "link": {
            "capacity_bytes_per_tick": 256_000,
            "loss": 0.18,
            "jitter_ms": 20.0,
            "rtt_ms": 90.0,
        },
        "flows": flows,
        "fleet_optimizer": {
            "enabled": True,
            "capacity_bytes_per_tick": max(1, robots * 2700),
            "redundant_deadline_ms": 35.0,
            "redundancy_risk_threshold": 1.0,
            "degrade_floor": 0.35,
            "path_targets": {
                "primary_wifi": {"udp_host": "127.0.0.1", "udp_port": 19101},
                "backup_5g": {"udp_host": "127.0.0.1", "udp_port": 19102},
                "low_cost_wan": {"udp_host": "127.0.0.1", "udp_port": 19103},
            },
            "paths": [
                {
                    "path_id": "primary_wifi",
                    "latency_ms": 58.0,
                    "jitter_ms": 22.0,
                    "loss": 0.18,
                    "nack_rate": 0.16,
                    "deadline_miss_ratio": 0.24,
                    "bandwidth_utilization": 0.88,
                },
                {
                    "path_id": "backup_5g",
                    "latency_ms": 24.0,
                    "jitter_ms": 5.0,
                    "loss": 0.035,
                    "nack_rate": 0.025,
                    "deadline_miss_ratio": 0.04,
                    "bandwidth_utilization": 0.42,
                },
                {
                    "path_id": "low_cost_wan",
                    "latency_ms": 115.0,
                    "jitter_ms": 35.0,
                    "loss": 0.08,
                    "nack_rate": 0.05,
                    "deadline_miss_ratio": 0.18,
                    "bandwidth_utilization": 0.36,
                },
            ],
            "robot_states": [
                {
                    "robot_id": f"robot_{index:04d}",
                    "control_delivery_ratio": 0.90 if index % 3 == 0 else 0.985,
                    "deadline_miss_ratio": 0.18 if index % 3 == 0 else 0.04,
                    "qoe_score": 0.78 if index % 4 == 0 else 0.95,
                }
                for index in range(robots)
            ],
        },
    }


def flow_item(
    *,
    robot_id: str,
    suffix: str,
    flow_class: FlowClass,
    topic: str,
    msg_type: str,
    deadline_ms: float,
    lifespan_ms: float,
    size: int,
    rate_hz: float,
    age_ms: float,
    criticality: float,
) -> dict[str, object]:
    flow_id = f"{robot_id}/{suffix}"
    return {
        "flow": {
            "flow_id": flow_id,
            "robot_id": robot_id,
            "topic": topic,
            "flow_class": flow_class.value,
            "qos": {
                "reliability": "best_effort",
                "durability": "volatile",
                "depth": 1,
                "deadline_ms": deadline_ms,
                "lifespan_ms": lifespan_ms,
                "liveliness_lease_ms": 500.0,
            },
            "qoe": {
                "operator_visible": flow_class is FlowClass.HUMAN_QOE,
                "smoothness_weight": 0.1 if flow_class is FlowClass.CONTROL else 0.0,
                "freeze_penalty": 0.0,
                "visual_confidence_weight": 0.0,
            },
            "nominal_size_bytes": size,
            "nominal_rate_hz": rate_hz,
            "causal_task_gain": criticality,
            "semantic_delta_ratio": 1.0,
            "tags": {"ros2_msg_type": msg_type},
        },
        "observation": {
            "age_ms": age_ms,
            "queue_depth": 1,
            "measured_loss": 0.0,
            "measured_rtt_ms": 20.0,
            "observed_jitter_ms": 1.0,
            "task": {
                "task_id": f"task/{robot_id}",
                "robot_id": robot_id,
                "task_criticality": criticality,
                "collision_risk": 0.2 if flow_class is FlowClass.CONTROL else 0.05,
                "operator_attention": 0.1,
                "coordination_pressure": 0.2,
            },
        },
    }


def render_markdown(summary: dict[str, Any], summary_path: str) -> str:
    lines = [
        "# Fleet Optimizer Runtime Actuation V1",
        "",
        "This artifact verifies that the fleet-level optimizer can cross the sidecar runtime boundary.",
        "",
        f"- Summary: `{summary_path}`",
        f"- Robots: `{summary['robots']}`",
        f"- Unique sidecar events: `{summary['unique_event_count']}`",
        f"- Emitted UDP packets: `{summary['emitted_packets']}`",
        "",
        "## Runtime Counts",
        "",
        f"- Fleet response: `{summary['fleet_optimizer']}`",
        f"- Event mode counts: `{summary['event_mode_counts']}`",
        f"- Event action counts: `{summary['event_action_counts']}`",
        f"- Selected path counts: `{summary['selected_path_counts']}`",
        f"- Packet path counts: `{summary['packet_path_counts']}`",
        f"- UDP target counts: `{summary['udp_target_counts']}`",
        "",
        "## Interpretation",
        "",
        "- The sidecar accepts a `fleet_optimizer` payload with multi-path telemetry and per-robot QoE state.",
        "- The runtime annotates each sidecar event with the optimizer mode and selected paths.",
        "- Redundant optimizer decisions actuate as per-path UDP transmissions in this dependency-free harness.",
        "- The current target binding is explicit UDP host/port mapping; binding to ROS 2 RMW router peers and live per-path telemetry feedback remains future C++ RMW/router work.",
        "",
    ]
    return "\n".join(lines)


if __name__ == "__main__":
    raise SystemExit(main())

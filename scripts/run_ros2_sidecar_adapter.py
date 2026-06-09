"""Build and optionally execute FleetRMW sidecar batches from ROS 2-like samples."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Iterable

from fleetqox.model import NetworkLink
from fleetqox.ros2_shim import Ros2Sample, Ros2SidecarAdapter
from fleetqox.sidecar_runtime import (
    RuntimeConfig,
    SIDECAR_POLICIES,
    SidecarRuntime,
    link_to_payload,
)
from fleetqox.transport_selector import TransportBinding, TransportBindingManager


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--input",
        type=Path,
        help="JSONL ROS 2 sample records; omitted for built-in smoke samples",
    )
    parser.add_argument(
        "--output-batch",
        type=Path,
        help="Optional JSON file for the generated sidecar batch",
    )
    parser.add_argument("--decision-log", type=Path, default=Path("results_ros2_shim/smoke_decisions.jsonl"))
    parser.add_argument("--scenario", default="ros2_shim_smoke")
    parser.add_argument("--tick", type=int, default=0)
    parser.add_argument("--timestamp-ms", type=float, default=0.0)
    parser.add_argument("--capacity-bytes-per-tick", type=int, default=588)
    parser.add_argument("--rtt-ms", type=float, default=160.0)
    parser.add_argument("--jitter-ms", type=float, default=25.0)
    parser.add_argument("--loss", type=float, default=0.03)
    parser.add_argument("--policy", choices=SIDECAR_POLICIES, default="fleetqox_semantic_contract_adaptive")
    parser.add_argument(
        "--transport-binding-summary",
        type=Path,
        help="Selector summary JSON used to attach a runtime TransportBinding.",
    )
    parser.add_argument(
        "--transport-profile",
        help="Profile label to select from a multi-profile binding summary.",
    )
    parser.add_argument(
        "--auto-transport-profile",
        action="store_true",
        help="Infer the selector profile from the configured link payload.",
    )
    parser.add_argument(
        "--adaptive-transport-profile",
        action="store_true",
        help="Infer profile through the adaptive binding estimator.",
    )
    parser.add_argument("--transport-smoothing-alpha", type=float, default=0.35)
    parser.add_argument("--transport-hysteresis-margin", type=float, default=0.06)
    parser.add_argument("--transport-min-dwell-ticks", type=int, default=2)
    parser.add_argument("--udp-host", default="127.0.0.1")
    parser.add_argument("--udp-port", type=int, default=9100)
    parser.add_argument("--include-feedback", action="store_true")
    parser.add_argument("--no-process", action="store_true", help="Only write/print the generated batch")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    link = NetworkLink(
        capacity_bytes_per_tick=args.capacity_bytes_per_tick,
        loss=args.loss,
        jitter_ms=args.jitter_ms,
        rtt_ms=args.rtt_ms,
    )
    adapter = Ros2SidecarAdapter()
    transport_binding = _read_transport_binding(
        args.transport_binding_summary,
        profile=args.transport_profile,
        link_payload=link_to_payload(link),
        auto_profile=args.auto_transport_profile,
        adaptive_profile=args.adaptive_transport_profile,
        smoothing_alpha=args.transport_smoothing_alpha,
        hysteresis_margin=args.transport_hysteresis_margin,
        min_dwell_ticks=args.transport_min_dwell_ticks,
    )
    batch = adapter.build_batch(
        _read_samples(args.input),
        scenario=args.scenario,
        link=link,
        timestamp_ms=args.timestamp_ms,
        tick=args.tick,
        include_feedback=args.include_feedback,
        transport_binding=transport_binding,
    )
    if args.output_batch:
        args.output_batch.parent.mkdir(parents=True, exist_ok=True)
        args.output_batch.write_text(json.dumps(batch, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    result: dict[str, object] = {
        "scenario": args.scenario,
        "samples": len(batch["flows"]),
        "batch": str(args.output_batch) if args.output_batch else None,
        "decision_log": str(args.decision_log) if not args.no_process else None,
        "processed": not args.no_process,
        "transport_binding": (
            transport_binding.as_payload() if transport_binding else None
        ),
    }
    if not args.no_process:
        runtime = SidecarRuntime(
            RuntimeConfig(
                udp_host=args.udp_host,
                udp_port=args.udp_port,
                policy=args.policy,
                decision_log=args.decision_log,
            )
        )
        try:
            response = runtime.process_batch(batch)
        finally:
            runtime.close()
        result["response"] = response

    if args.json:
        print(json.dumps(result, sort_keys=True))
    else:
        print(f"ros2-shim {args.scenario}")
        print(f"  samples: {result['samples']}")
        if result["batch"]:
            print(f"  batch: {result['batch']}")
        if result["transport_binding"]:
            print(
                "  transport_binding: "
                f"{result['transport_binding']['policy']}"
            )
        if result["processed"]:
            print(f"  decision_log: {result['decision_log']}")
            print(f"  response: {json.dumps(result['response'], sort_keys=True)}")


def _read_samples(path: Path | None) -> Iterable[Ros2Sample]:
    if path is None:
        return _smoke_samples()
    samples: list[Ros2Sample] = []
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            if line.strip():
                samples.append(Ros2Sample.from_payload(json.loads(line)))
    return samples


def _read_transport_binding(
    path: Path | None,
    *,
    profile: str | None,
    link_payload: dict[str, object] | None = None,
    auto_profile: bool = False,
    adaptive_profile: bool = False,
    smoothing_alpha: float = 0.35,
    hysteresis_margin: float = 0.06,
    min_dwell_ticks: int = 2,
) -> TransportBinding | None:
    if path is None:
        return None
    if adaptive_profile:
        manager = TransportBindingManager.from_summary_path(path)
        estimator = manager.adaptive_estimator(
            smoothing_alpha=smoothing_alpha,
            hysteresis_margin=hysteresis_margin,
            min_dwell_ticks=min_dwell_ticks,
        )
        return estimator.update_from_link_payload(link_payload or {}).binding
    if auto_profile:
        manager = TransportBindingManager.from_summary_path(path)
        return manager.binding_for_link_payload(link_payload or {})
    data = json.loads(path.read_text(encoding="utf-8"))
    bindings = data.get("bindings", [])
    if isinstance(bindings, list):
        for binding in bindings:
            if not isinstance(binding, dict):
                continue
            if profile is None or binding.get("profile") == profile:
                return TransportBinding.from_payload(binding)
    selections = data.get("selections", [])
    if isinstance(selections, list):
        for selection in selections:
            if not isinstance(selection, dict):
                continue
            if profile is None or selection.get("profile") == profile:
                return TransportBinding.from_selection(selection)
    if profile:
        raise ValueError(f"transport profile not found in selector summary: {profile}")
    raise ValueError(f"no transport binding found in selector summary: {path}")


def _smoke_samples() -> list[Ros2Sample]:
    samples = []
    for idx in range(4):
        robot_id = f"robot_{idx:04d}"
        samples.append(
            Ros2Sample(
                topic=f"/{robot_id}/cmd_vel",
                msg_type="geometry_msgs/msg/Twist",
                robot_id=robot_id,
                age_ms=20.0,
                collision_risk=0.8,
                coordination_pressure=0.15,
            )
        )
        samples.append(
            Ros2Sample(
                topic=f"/{robot_id}/fleet_state",
                msg_type="nav_msgs/msg/Odometry",
                robot_id=robot_id,
                age_ms=40.0,
                queue_depth=1,
            )
        )
        samples.append(
            Ros2Sample(
                topic=f"/{robot_id}/semantic_obstacles",
                msg_type="sensor_msgs/msg/LaserScan",
                robot_id=robot_id,
                age_ms=35.0,
            )
        )
    samples.append(
        Ros2Sample(
            topic="/robot_0000/front_camera/qoe",
            msg_type="sensor_msgs/msg/CompressedImage",
            robot_id="robot_0000",
            operator_visible=True,
            operator_attention=1.0,
            payload_size_bytes=9000,
            age_ms=30.0,
        )
    )
    return samples


if __name__ == "__main__":
    main()

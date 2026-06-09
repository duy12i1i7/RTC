"""Dependency-free smoke for live-bridge transport binding refresh."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from fleetqox.model import NetworkLink
from fleetqox.ros2_live_bridge import (
    BridgeTopicConfig,
    LiveBridgeConfig,
    Ros2LiveSampleBuffer,
    transport_binding_provider_for_config,
)
from fleetqox.sidecar_runtime import RuntimeConfig, SidecarRuntime


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--selector-summary",
        type=Path,
        required=True,
        help="Transport selector summary JSON with runtime bindings.",
    )
    parser.add_argument(
        "--mode",
        choices=("profile", "auto", "adaptive"),
        default="adaptive",
    )
    parser.add_argument("--profile", default="wifi")
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("results_ros2_live_bridge/live_bridge_binding_smoke_v1.json"),
    )
    parser.add_argument("--process-runtime", action="store_true")
    parser.add_argument(
        "--decision-log",
        type=Path,
        default=Path(
            "results_ros2_live_bridge/"
            "live_bridge_adaptive_binding_runtime_smoke_decisions.jsonl"
        ),
    )
    parser.add_argument("--policy", default="fleetqox_semantic_contract_adaptive")
    parser.add_argument("--udp-host", default="127.0.0.1")
    parser.add_argument("--udp-port", type=int, default=9100)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    config = _bridge_config(args.selector_summary, args.mode, args.profile)
    provider = transport_binding_provider_for_config(config)
    if provider is None:
        raise SystemExit("transport binding provider was not configured")

    buffer = Ros2LiveSampleBuffer(
        scenario="ros2_live_binding_smoke_v1",
        link=_wifi_link(),
        transport_binding_provider=provider,
        clock_ms=lambda: 0.0,
    )
    topic = config.topics[0]
    batches = []
    raw_batches = []
    for tick, link in enumerate((_wifi_link(), _roaming_link())):
        buffer.link = link
        buffer.record_sample(topic, payload_size_bytes=96, received_ms=0.0)
        batch = buffer.drain_batch(timestamp_ms=float((tick + 1) * 20))
        raw_batches.append(batch)
        batches.append(
            {
                "tick": batch["tick"],
                "link": _link_payload(link),
                "transport_binding": batch.get("transport_binding"),
                "transport_binding_estimate": batch.get(
                    "transport_binding_estimate"
                ),
            }
        )

    result = {
        "scenario": "ros2_live_binding_smoke_v1",
        "mode": args.mode,
        "selector_summary": str(args.selector_summary),
        "batches": batches,
    }
    if args.process_runtime:
        result["runtime"] = _process_runtime(
            raw_batches,
            policy=args.policy,
            decision_log=args.decision_log,
            udp_host=args.udp_host,
            udp_port=args.udp_port,
        )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True), encoding="utf-8")
    if args.json:
        print(json.dumps(result, sort_keys=True))
    else:
        print(f"live bridge binding smoke written: {args.output}")


def _bridge_config(
    selector_summary: Path,
    mode: str,
    profile: str,
) -> LiveBridgeConfig:
    binding: dict[str, object] = {
        "summary": str(selector_summary),
    }
    if mode == "profile":
        binding["profile"] = profile
    elif mode == "auto":
        binding["auto_profile"] = True
    else:
        binding.update(
            {
                "adaptive_profile": True,
                "smoothing_alpha": 1.0,
                "hysteresis_margin": 0.0,
                "min_dwell_ticks": 0,
            }
        )
    return LiveBridgeConfig.from_payload(
        {
            "scenario": "ros2_live_binding_smoke_v1",
            "transport_binding": binding,
            "topics": [
                {
                    "topic": "/robot_0000/cmd_vel",
                    "msg_type": "geometry_msgs/msg/Twist",
                    "robot_id": "robot_0000",
                }
            ],
        }
    )


def _wifi_link() -> NetworkLink:
    return NetworkLink(
        capacity_bytes_per_tick=2400,
        rtt_ms=40,
        jitter_ms=5,
        loss=0.01,
    )


def _roaming_link() -> NetworkLink:
    return NetworkLink(
        capacity_bytes_per_tick=1000,
        rtt_ms=160,
        jitter_ms=25,
        loss=0.03,
    )


def _link_payload(link: NetworkLink) -> dict[str, object]:
    return {
        "capacity_bytes_per_tick": link.capacity_bytes_per_tick,
        "rtt_ms": link.rtt_ms,
        "jitter_ms": link.jitter_ms,
        "loss": link.loss,
    }


def _process_runtime(
    batches: list[dict[str, object]],
    *,
    policy: str,
    decision_log: Path,
    udp_host: str,
    udp_port: int,
) -> dict[str, object]:
    runtime = SidecarRuntime(
        RuntimeConfig(
            udp_host=udp_host,
            udp_port=udp_port,
            policy=policy,
            decision_log=decision_log,
        )
    )
    responses = []
    try:
        for batch in batches:
            response = runtime.process_batch(batch)
            responses.append(
                {
                    "tick": response["tick"],
                    "accepted": response["accepted"],
                    "decisions": response["decisions"],
                    "emitted": response["emitted"],
                    "packet_format": response["packet_format"],
                    "transport_binding": response.get("transport_binding"),
                    "transport_binding_estimate": response.get(
                        "transport_binding_estimate"
                    ),
                }
            )
    finally:
        runtime.close()
    return {
        "policy": policy,
        "decision_log": str(decision_log),
        "responses": responses,
        "decision_log_summary": _decision_log_summary(decision_log),
    }


def _decision_log_summary(path: Path) -> dict[str, object]:
    rows = []
    if path.exists():
        rows = [
            json.loads(line)
            for line in path.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
    return {
        "rows": len(rows),
        "with_transport_binding": sum(1 for row in rows if row.get("transport_binding")),
        "with_transport_binding_estimate": sum(
            1 for row in rows if row.get("transport_binding_estimate")
        ),
        "profiles": sorted(
            {
                str(row["transport_binding"]["profile"])
                for row in rows
                if isinstance(row.get("transport_binding"), dict)
            }
        ),
    }


if __name__ == "__main__":
    main()

"""Repeat the FleetRMW generic serialized terminate/republish middle hop."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.run_ros2_relay_rmw_netem_probe import (
    DEFAULT_IMAGE,
    FLEETQOX_RMW,
    run_probe,
)


SCHEMA_VERSION = "fleetrmw.docker_fleetqox_generic_relay_probe.v1"


def probe_ok(row: dict[str, Any]) -> bool:
    publisher = row.get("publisher", {})
    return (
        row.get("status") == "ok"
        and row.get("topology") == "publisher-relay-subscriber"
        and row.get("relay_scope") == "rclcpp_generic_serialized_passthrough"
        and row.get("middle_payload_remains_serialized") is True
        and row.get("middle_application_deserialization") is False
        and row.get("middle_rmw_termination_republish") is True
        and row.get("fleetqox_direct_peer_transport") is True
        and row.get("netem_status", {}).get("direct_pub", {}).get("status")
        == "applied"
        and int(row.get("relay_payload_count", 0))
        == int(row.get("relay_expected_count", -1))
        and float(row.get("control_delivery_ratio", 0.0)) == 1.0
        and float(row.get("state_delivery_ratio", 0.0)) == 1.0
        and float(row.get("min_topic_delivery_ratio", 0.0)) == 1.0
        and isinstance(publisher, dict)
        and publisher.get("ack_wait_supported") is True
        and publisher.get("ack_wait_complete") is True
        and int(publisher.get("unacked_topic_count", -1)) == 0
    )


def run_campaign(
    *,
    root: Path,
    image: str,
    iterations: int,
    profile: str,
    netem_loss_scale: float,
    samples: int,
    robot_count: int,
    publish_interval_ms: int,
    timeout_s: float,
    publisher_linger_s: float,
) -> dict[str, Any]:
    run_count = max(iterations, 1)
    seed_cycle = (7, 13, 29)
    rows = [
        run_probe(
            root=root,
            image=image,
            rmw=FLEETQOX_RMW,
            profile=profile,
            enable_netem=True,
            require_netem=True,
            netem_loss_scale=netem_loss_scale,
            repetition_seed=seed_cycle[index % len(seed_cycle)],
            samples=samples,
            robot_count=robot_count,
            publish_interval_ms=publish_interval_ms,
            timeout_s=timeout_s,
            publisher_linger_s=publisher_linger_s,
            relay_mode="generic_serialized",
        )
        for index in range(run_count)
    ]
    ok_run_count = sum(probe_ok(row) for row in rows)
    ok = ok_run_count == run_count
    expected_per_run = robot_count * 2 * samples
    return {
        "schema_version": SCHEMA_VERSION,
        "status": "ok" if ok else "failed",
        "image": image,
        "profile": profile,
        "netem_loss_scale": netem_loss_scale,
        "samples": samples,
        "robot_count": robot_count,
        "topic_count": robot_count * 2,
        "run_count": run_count,
        "ok_run_count": ok_run_count,
        "failed_run_count": run_count - ok_run_count,
        "expected_relay_payloads_per_run": expected_per_run,
        "observed_relay_payloads": sum(
            int(row.get("relay_payload_count", 0)) for row in rows
        ),
        "expected_relay_payloads": expected_per_run * run_count,
        "fleetqox_generic_serialized_middle_relay_claim": ok,
        "fleetqox_middle_rmw_termination_republish_claim": ok,
        "fleetqox_direct_peer_topology_claim": ok,
        "fleetqox_generic_relay_repeated_netem_claim":
            ok and run_count >= 5,
        "same_hop_middle_processing_equivalence_claim": False,
        "same_hop_latency_superiority_claim": False,
        "runs": rows,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--image", default=DEFAULT_IMAGE)
    parser.add_argument("--iterations", type=int, default=5)
    parser.add_argument("--profile", default="roaming")
    parser.add_argument("--netem-loss-scale", type=float, default=0.25)
    parser.add_argument("--samples", type=int, default=5)
    parser.add_argument("--robot-count", type=int, default=8)
    parser.add_argument("--publish-interval-ms", type=int, default=50)
    parser.add_argument("--timeout-s", type=float, default=25.0)
    parser.add_argument("--publisher-linger-s", type=float, default=6.0)
    parser.add_argument(
        "--summary-json",
        default=(
            "results_rmw_socket/"
            "docker_fleetqox_generic_serialized_relay_probe_summary.json"
        ),
    )
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    summary = run_campaign(
        root=ROOT,
        image=args.image,
        iterations=max(args.iterations, 1),
        profile=args.profile,
        netem_loss_scale=max(args.netem_loss_scale, 0.0),
        samples=max(args.samples, 1),
        robot_count=max(args.robot_count, 1),
        publish_interval_ms=max(args.publish_interval_ms, 0),
        timeout_s=max(args.timeout_s, 1.0),
        publisher_linger_s=max(args.publisher_linger_s, 0.0),
    )
    output = ROOT / args.summary_json
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(summary, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    if args.json:
        print(json.dumps(summary, sort_keys=True))
    else:
        print(f"status={summary['status']}")
        print(f"runs={summary['ok_run_count']}/{summary['run_count']}")
        print(
            "relay_payloads="
            f"{summary['observed_relay_payloads']}/"
            f"{summary['expected_relay_payloads']}"
        )
    return 0 if summary["status"] == "ok" else 1


if __name__ == "__main__":
    raise SystemExit(main())

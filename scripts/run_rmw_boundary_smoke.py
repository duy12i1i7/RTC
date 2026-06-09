"""Smoke-test the minimal FleetRMW publish/take boundary."""

from __future__ import annotations

import argparse
import json

from fleetqox.model import NetworkLink
from fleetqox.rmw_boundary import FleetRmwBoundary, FleetRmwBoundaryConfig
from fleetqox.ros2_shim import Ros2Sample


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--robot-count", type=int, default=2)
    parser.add_argument("--samples-per-robot", type=int, default=3)
    parser.add_argument(
        "--skip-take",
        action="append",
        default=[],
        help="Drop a receiver-side take in robot:sequence form, for example robot_0000:2.",
    )
    parser.add_argument("--scenario", default="fleetrmw_boundary_smoke")
    parser.add_argument("--policy", default="fleetqox_semantic_contract_adaptive")
    parser.add_argument("--capacity-bytes-per-tick", type=int, default=4096)
    parser.add_argument("--rtt-ms", type=float, default=80.0)
    parser.add_argument("--jitter-ms", type=float, default=8.0)
    parser.add_argument("--loss", type=float, default=0.01)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    summary = run_smoke(
        robot_count=args.robot_count,
        samples_per_robot=args.samples_per_robot,
        skip_take=parse_skip_take(args.skip_take),
        scenario=args.scenario,
        policy=args.policy,
        link=NetworkLink(
            capacity_bytes_per_tick=args.capacity_bytes_per_tick,
            loss=args.loss,
            jitter_ms=args.jitter_ms,
            rtt_ms=args.rtt_ms,
        ),
    )
    if args.json:
        print(json.dumps(summary, sort_keys=True))
    else:
        print(f"fleetrmw-boundary-smoke {summary['scenario']}")
        print(f"  published: {summary['published']}")
        print(f"  taken: {summary['taken']}")
        print(f"  ack_nack_feedback: {summary['ack_nack_feedback']}")
        print(f"  missing_sequence_range_count: {summary['missing_sequence_range_count']}")
    return 0


def run_smoke(
    *,
    robot_count: int,
    samples_per_robot: int,
    skip_take: set[tuple[str, int]] | None = None,
    scenario: str = "fleetrmw_boundary_smoke",
    policy: str = "fleetqox_semantic_contract_adaptive",
    link: NetworkLink | None = None,
) -> dict[str, object]:
    effective_link = link or NetworkLink(capacity_bytes_per_tick=4096)
    boundary = FleetRmwBoundary(
        FleetRmwBoundaryConfig(
            scenario=scenario,
            policy=policy,
            link=effective_link,
        )
    )
    skipped = skip_take or set()
    published = []
    taken = []
    for robot_index in range(max(0, robot_count)):
        robot_id = f"robot_{robot_index:04d}"
        for sequence in range(1, max(0, samples_per_robot) + 1):
            result = boundary.publish(
                Ros2Sample(
                    topic=f"/{robot_id}/cmd_vel",
                    msg_type="geometry_msgs/msg/Twist",
                    robot_id=robot_id,
                    sequence_number=sequence,
                    source_timestamp_ns=sequence * 1_000_000,
                    age_ms=8.0,
                    collision_risk=0.8,
                    semantic_payload={
                        "msg_type": "geometry_msgs/msg/Twist",
                        "source_sequence_number": sequence,
                        "twist": {
                            "linear": {"x": 0.1 * sequence, "y": 0.0, "z": 0.0},
                            "angular": {"x": 0.0, "y": 0.0, "z": 0.1},
                        },
                    },
                ),
                timestamp_ms=float(sequence * 20),
                tick=sequence,
            )
            published.append(result)
            if (robot_id, sequence) in skipped:
                continue
            taken.append(boundary.take(result["encoded"]))
    ack_nacks = [
        item["ack_nack"]
        for item in taken
        if isinstance(item.get("ack_nack"), dict)
    ]
    gaps = [
        feedback
        for feedback in ack_nacks
        if feedback.get("nack", {}).get("missing_sequence_ranges")
    ]
    return {
        "schema_version": "fleetrmw.rmw_boundary_smoke.v1",
        "scenario": scenario,
        "policy": policy,
        "robot_count": robot_count,
        "samples_per_robot": samples_per_robot,
        "published": len(published),
        "taken": len(taken),
        "ack_nack_feedback": len(ack_nacks),
        "missing_sequence_range_count": sum(
            len(feedback.get("nack", {}).get("missing_sequence_ranges", []))
            for feedback in ack_nacks
        ),
        "streams_with_gaps": sorted(
            "/".join(str(part) for part in feedback.get("stream_key", []))
            for feedback in gaps
        ),
        "skipped_takes": sorted(f"{robot_id}:{sequence}" for robot_id, sequence in skipped),
    }


def parse_skip_take(values: list[str]) -> set[tuple[str, int]]:
    parsed: set[tuple[str, int]] = set()
    for value in values:
        robot_id, separator, sequence = value.partition(":")
        if not separator or not robot_id:
            raise ValueError(f"invalid --skip-take value: {value}")
        parsed.add((robot_id, int(sequence)))
    return parsed


if __name__ == "__main__":
    raise SystemExit(main())

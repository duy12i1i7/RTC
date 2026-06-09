"""Smoke-test FleetRMW data-frame and ACK/NACK over UDP sockets."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from fleetqox.rmw_transport_loop import (
    FleetRmwSocketLoopConfig,
    FleetRmwSocketTransportLoop,
)


SOCKET_SMOKE_SCHEMA_VERSION = "fleetrmw.rmw_socket_smoke.v1"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--robot-count", type=int, default=2)
    parser.add_argument("--samples-per-robot", type=int, default=3)
    parser.add_argument(
        "--skip-initial",
        action="append",
        default=[],
        help="Delay an initial send in robot:sequence form, for example robot_0000:2.",
    )
    parser.add_argument(
        "--skip-every",
        type=int,
        default=0,
        help="Delay every Nth initial sequence for every robot before NACK-triggered retransmit.",
    )
    parser.add_argument("--no-late-skipped", action="store_true")
    parser.add_argument("--summary-json")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    summary = run_socket_smoke(
        robot_count=args.robot_count,
        samples_per_robot=args.samples_per_robot,
        skip_initial=parse_robot_sequences(args.skip_initial),
        skip_every=args.skip_every,
        late_skipped=not args.no_late_skipped,
    )
    if args.summary_json:
        summary_path = Path(args.summary_json)
        summary_path.parent.mkdir(parents=True, exist_ok=True)
        summary_path.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n")
    if args.json:
        print(json.dumps(summary, sort_keys=True))
    else:
        print("fleetrmw-socket-smoke")
        print(f"  published: {summary['published']}")
        print(f"  taken: {summary['taken']}")
        print(f"  ack_nack_feedback: {summary['ack_nack_feedback']}")
        print(f"  missing_sequence_range_count: {summary['missing_sequence_range_count']}")
        print(f"  late_out_of_order_count: {summary['late_out_of_order_count']}")
    return 0


def run_socket_smoke(
    *,
    robot_count: int,
    samples_per_robot: int,
    skip_initial: set[tuple[str, int]] | None = None,
    skip_every: int = 0,
    late_skipped: bool = True,
) -> dict[str, object]:
    loop = FleetRmwSocketTransportLoop(
        FleetRmwSocketLoopConfig(
            robot_count=robot_count,
            samples_per_robot=samples_per_robot,
            skip_every=skip_every,
            late_skipped=late_skipped,
            timeout_s=1.0,
        )
    )
    summary = loop.run(skip_initial=skip_initial)
    loop_schema = summary.get("schema_version")
    return {
        **summary,
        "schema_version": SOCKET_SMOKE_SCHEMA_VERSION,
        "transport_loop_schema_version": loop_schema,
    }


def parse_robot_sequences(values: list[str]) -> set[tuple[str, int]]:
    parsed: set[tuple[str, int]] = set()
    for value in values:
        robot_id, separator, sequence = value.partition(":")
        if not separator or not robot_id:
            raise ValueError(f"invalid robot sequence: {value}")
        parsed.add((robot_id, int(sequence)))
    return parsed


if __name__ == "__main__":
    raise SystemExit(main())

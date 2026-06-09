"""Replay FleetQoX CSV traces through a lightweight bottleneck simulator."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from fleetqox.network_replay import (
    ReplayConfig,
    load_packet_trace,
    replay_trace,
    write_replay_jsonl,
)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("trace", type=Path)
    parser.add_argument("--data-rate-mbps", type=float, default=20.0)
    parser.add_argument("--base-delay-ms", type=float, default=5.0)
    parser.add_argument("--jitter-ms", type=float, default=0.0)
    parser.add_argument("--loss", type=float, default=0.0)
    parser.add_argument("--seed", type=int, default=7)
    parser.add_argument("--queue-policy", choices=["fifo", "class_priority"], default="fifo")
    parser.add_argument(
        "--transport-model",
        choices=["udp_like", "adaptive_reliability"],
        default="udp_like",
    )
    parser.add_argument("--retransmit-delay-ms", type=float, default=8.0)
    parser.add_argument("--output", type=Path, default=None)
    args = parser.parse_args()

    events = load_packet_trace(args.trace)
    records = replay_trace(
        events,
        ReplayConfig(
            data_rate_mbps=args.data_rate_mbps,
            base_delay_ms=args.base_delay_ms,
            jitter_ms=args.jitter_ms,
            loss=args.loss,
            seed=args.seed,
            queue_policy=args.queue_policy,
            transport_model=args.transport_model,
            retransmit_delay_ms=args.retransmit_delay_ms,
        ),
    )

    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        write_replay_jsonl(records, args.output)
        print(f"wrote {args.output}")
        return

    for record in records:
        print(json.dumps(record, sort_keys=True))


if __name__ == "__main__":
    main()

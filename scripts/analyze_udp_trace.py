"""Analyze received UDP packets from Docker/netem trace emulation."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from fleetqox.udp_metrics import analyze_udp_trace, write_metrics_jsonl


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--trace", type=Path, required=True)
    parser.add_argument("--received", type=Path, required=True)
    parser.add_argument("--output", type=Path, default=None)
    args = parser.parse_args()

    records = analyze_udp_trace(args.trace, args.received)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        write_metrics_jsonl(records, args.output)
        print(f"wrote {args.output}")
        return
    for record in records:
        print(json.dumps(record, sort_keys=True))


if __name__ == "__main__":
    main()

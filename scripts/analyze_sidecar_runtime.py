"""Analyze FleetRMW sidecar runtime UDP results."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from fleetqox.sidecar_metrics import analyze_sidecar_runtime, write_sidecar_metrics_jsonl


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--decisions", type=Path, required=True)
    parser.add_argument("--received", type=Path, required=True)
    parser.add_argument("--output", type=Path, default=None)
    args = parser.parse_args()

    records = analyze_sidecar_runtime(args.decisions, args.received)
    if args.output:
        write_sidecar_metrics_jsonl(records, args.output)
        print(f"wrote {args.output}")
        return
    for record in records:
        print(json.dumps(record, sort_keys=True))


if __name__ == "__main__":
    main()

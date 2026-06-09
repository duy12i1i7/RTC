"""Compare multiple T2E ROS 2/netem baseline summaries."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from fleetqox.comparison import (
    BaselineInput,
    compare_baselines,
    write_comparison_csv,
    write_comparison_markdown,
)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--baseline",
        action="append",
        required=True,
        help="Baseline in name:metrics.jsonl:summary.json form. Summary may be empty.",
    )
    parser.add_argument("--markdown", type=Path, default=Path("results_t2e_ros2/baseline_comparison.md"))
    parser.add_argument("--csv", type=Path, default=Path("results_t2e_ros2/baseline_comparison.csv"))
    parser.add_argument("--title", default="T2E Baseline Comparison")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    inputs = [_parse_baseline(value) for value in args.baseline]
    comparison = compare_baselines(inputs)
    write_comparison_markdown(comparison, args.markdown, title=args.title)
    write_comparison_csv(comparison, args.csv)

    record = {
        "markdown": str(args.markdown),
        "csv": str(args.csv),
        "baselines": len(comparison.get("baselines", [])),
        "rows": len(comparison.get("rows", [])),
        "deltas": len(comparison.get("deltas", [])),
    }
    if args.json:
        print(json.dumps(record, sort_keys=True))
        return
    print(f"T2E comparison written: {args.markdown}")
    print(f"T2E comparison CSV written: {args.csv}")


def _parse_baseline(value: str) -> BaselineInput:
    parts = value.split(":", 2)
    if len(parts) < 2:
        raise SystemExit("--baseline must be name:metrics.jsonl[:summary.json]")
    name, metrics = parts[0], parts[1]
    summary = parts[2] if len(parts) == 3 and parts[2] else None
    if not name:
        raise SystemExit("baseline name must be non-empty")
    return BaselineInput(name=name, metrics_path=Path(metrics), summary_path=Path(summary) if summary else None)


if __name__ == "__main__":
    main()

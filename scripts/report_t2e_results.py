"""Generate Markdown/CSV reports for T2E ROS 2/netem results."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from fleetqox.reporting import load_summary, write_markdown_report, write_summary_csv


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--metrics", type=Path, required=True)
    parser.add_argument("--summary", type=Path)
    parser.add_argument("--markdown", type=Path, default=Path("results_t2e_ros2/report.md"))
    parser.add_argument("--csv", type=Path, default=Path("results_t2e_ros2/report.csv"))
    parser.add_argument("--title", default="T2E ROS 2 / netem Report")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    summary = load_summary(args.summary, args.metrics)
    write_summary_csv(summary, args.csv)
    write_markdown_report(
        summary,
        args.markdown,
        title=args.title,
        metrics_path=args.metrics,
        summary_path=args.summary,
    )

    record = {
        "markdown": str(args.markdown),
        "csv": str(args.csv),
        "groups": len(summary.get("groups", [])),
        "ranking": len(summary.get("ranking", [])),
    }
    if args.json:
        print(json.dumps(record, sort_keys=True))
        return
    print(f"T2E report written: {args.markdown}")
    print(f"T2E CSV written: {args.csv}")


if __name__ == "__main__":
    main()

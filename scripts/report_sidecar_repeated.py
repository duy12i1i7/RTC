"""Generate repeated-run reports for FleetQoX sidecar metrics."""

from __future__ import annotations

import argparse
import glob
import json
from pathlib import Path

from fleetqox.sidecar_repeated import (
    read_sidecar_metric_records,
    summarize_repeated_sidecar_metrics,
    write_repeated_markdown_report,
    write_repeated_summary_json,
)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--metrics",
        action="append",
        required=True,
        help="Metric JSONL path or glob. Repeat for multiple evidence files.",
    )
    parser.add_argument(
        "--summary-json",
        type=Path,
        default=Path("results_sidecar_repeated/summary.json"),
    )
    parser.add_argument(
        "--markdown",
        type=Path,
        default=Path("results_sidecar_repeated/report.md"),
    )
    parser.add_argument("--title", default="Sidecar Repeated-Run Statistics")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    metric_paths = expand_metric_paths(args.metrics)
    records = read_sidecar_metric_records(metric_paths)
    summary = summarize_repeated_sidecar_metrics(records)
    write_repeated_summary_json(summary, args.summary_json)
    write_repeated_markdown_report(
        summary,
        args.markdown,
        title=args.title,
        metrics_paths=metric_paths,
    )

    result = {
        "metrics": [str(path) for path in metric_paths],
        "summary_json": str(args.summary_json),
        "markdown": str(args.markdown),
        "records": summary["records"],
        "policies": len(summary["policies"]),
        "pareto_frontier": summary["pareto_frontier"],
    }
    if args.json:
        print(json.dumps(result, sort_keys=True))
        return
    print(f"Sidecar repeated report written: {args.markdown}")
    print(f"Sidecar repeated summary written: {args.summary_json}")


def expand_metric_paths(patterns: list[str]) -> list[Path]:
    paths: list[Path] = []
    for pattern in patterns:
        matches = sorted(glob.glob(pattern, recursive=True))
        if not matches:
            matches = [pattern]
        for match in matches:
            path = Path(match)
            if path not in paths:
                paths.append(path)
    return paths


if __name__ == "__main__":
    main()

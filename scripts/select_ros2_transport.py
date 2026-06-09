"""Select ROS 2 packet-format/RMW policies from repeated-run summaries."""

from __future__ import annotations

import argparse
import glob
import json
from pathlib import Path

from fleetqox.transport_selector import (
    BUILTIN_TRANSPORT_OBJECTIVES,
    render_transport_selection_markdown,
    select_transports_from_paths,
    write_transport_selection_json,
    write_transport_selection_markdown,
)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--summary",
        action="append",
        required=True,
        help="Repeated summary JSON path or glob. Repeat for multiple profiles.",
    )
    parser.add_argument(
        "--objective",
        choices=sorted(BUILTIN_TRANSPORT_OBJECTIVES),
        default="balanced_safety_utility",
    )
    parser.add_argument(
        "--summary-json",
        type=Path,
        default=Path("results_ros2_live_bridge/transport_selector_summary.json"),
    )
    parser.add_argument(
        "--markdown",
        type=Path,
        default=Path("results_ros2_live_bridge/transport_selector_report.md"),
    )
    parser.add_argument("--title", default="ROS 2 Profile Objective Transport Selector")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    summary_paths = expand_summary_paths(args.summary)
    result = select_transports_from_paths(summary_paths, objective=args.objective)
    write_transport_selection_json(result, args.summary_json)
    write_transport_selection_markdown(result, args.markdown, title=args.title)

    if args.json:
        print(json.dumps(result, sort_keys=True))
        return
    print(f"Transport selector report written: {args.markdown}")
    print(f"Transport selector summary written: {args.summary_json}")
    for selection in result["selections"]:
        print(
            "Selected "
            f"{selection['selected_policy']} for {selection['profile']} "
            f"({args.objective}, score={selection['raw_score']:.4f})"
        )


def expand_summary_paths(patterns: list[str]) -> list[Path]:
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

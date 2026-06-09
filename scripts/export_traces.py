"""Export FleetQoX workload traces for ns-3/OMNeT++."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from fleetqox.testbed import ExperimentScenario, iter_scenarios, load_manifest
from fleetqox.trace import generate_trace_events, write_simulator_csv


DEFAULT_MANIFEST = Path("experiments/testbed_manifest.json")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--scenario", default=None)
    parser.add_argument("--output-dir", type=Path, default=Path("traces"))
    parser.add_argument("--include-non-sent", action="store_true")
    parser.add_argument(
        "--format",
        choices=["jsonl", "csv"],
        default="jsonl",
        help="jsonl keeps full events; csv emits packet rows for ns-3/OMNeT++.",
    )
    parser.add_argument(
        "--policy",
        action="append",
        dest="policies",
        help="Policy to export. Repeatable. Defaults to all T0 policies.",
    )
    args = parser.parse_args()

    manifest = load_manifest(args.manifest)
    scenarios = [
        scenario
        for scenario in iter_scenarios(manifest)
        if scenario.tier == "T0"
        and (args.scenario is None or scenario.name == args.scenario)
    ]
    if not scenarios:
        raise SystemExit("no matching T0 scenarios")

    args.output_dir.mkdir(parents=True, exist_ok=True)
    for scenario in scenarios:
        suffix = "csv" if args.format == "csv" else "jsonl"
        output = args.output_dir / f"{scenario.name}.{suffix}"
        count = export_scenario(
            scenario,
            output,
            policies=args.policies,
            include_non_sent=args.include_non_sent,
            output_format=args.format,
        )
        print(f"wrote {count} events to {output}")


def export_scenario(
    scenario: ExperimentScenario,
    output: Path,
    *,
    policies: list[str] | None,
    include_non_sent: bool,
    output_format: str,
) -> int:
    config = scenario.config
    events = generate_trace_events(
        scenario=scenario.name,
        robots=int(config["robots"]),
        seconds=int(config["seconds"]),
        seed=int(config["seed"]),
        capacity_bytes_per_second=config.get("capacity_bytes_per_second"),
        policies=policies,
        include_non_sent=include_non_sent,
    )
    if output_format == "csv":
        return write_simulator_csv(events, output)
    with output.open("w", encoding="utf-8") as handle:
        for event in events:
            handle.write(json.dumps(event, sort_keys=True) + "\n")
    return len(events)


if __name__ == "__main__":
    main()

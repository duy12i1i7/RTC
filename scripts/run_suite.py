"""Run or plan FleetQoX testbed scenarios."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from fleetqox.simulator import run_benchmark
from fleetqox.testbed import ExperimentScenario, iter_scenarios, load_manifest
from fleetqox.trace import generate_trace_events


DEFAULT_MANIFEST = Path("experiments/testbed_manifest.json")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--tier", default=None)
    parser.add_argument("--run", action="store_true")
    parser.add_argument("--output", type=Path, default=Path("results/testbed_results.jsonl"))
    parser.add_argument("--export-traces", action="store_true")
    parser.add_argument("--trace-output-dir", type=Path, default=Path("traces"))
    parser.add_argument("--include-non-sent", action="store_true")
    args = parser.parse_args()

    manifest = load_manifest(args.manifest)
    scenarios = iter_scenarios(manifest)
    if args.tier:
        scenarios = [scenario for scenario in scenarios if scenario.tier == args.tier]

    if not args.run:
        print_plan(scenarios)
        return

    args.output.parent.mkdir(parents=True, exist_ok=True)
    if args.export_traces:
        args.trace_output_dir.mkdir(parents=True, exist_ok=True)
    with args.output.open("w", encoding="utf-8") as handle:
        for scenario in scenarios:
            for record in run_scenario(scenario):
                handle.write(json.dumps(record, sort_keys=True) + "\n")
            if args.export_traces and scenario.runner == "local_python":
                trace_path = args.trace_output_dir / f"{scenario.name}.jsonl"
                count = export_trace_for_scenario(
                    scenario,
                    trace_path,
                    include_non_sent=args.include_non_sent,
                )
                handle.write(
                    json.dumps(
                        {
                            "tier": scenario.tier,
                            "experiment": scenario.experiment,
                            "scenario": scenario.name,
                            "runner": "trace_exporter",
                            "status": "ok",
                            "trace_path": str(trace_path),
                            "trace_events": count,
                        },
                        sort_keys=True,
                    )
                    + "\n"
                )
    print(f"wrote {args.output}")


def print_plan(scenarios: list[ExperimentScenario]) -> None:
    for scenario in scenarios:
        print(f"{scenario.tier}  {scenario.experiment}/{scenario.name}")
        print(f"  runner: {scenario.runner}")
        print(f"  baselines: {', '.join(scenario.baselines)}")
        print(f"  metrics: {', '.join(scenario.metrics)}")
        if scenario.runner != "local_python":
            print("  status: planned external-tool experiment")
        else:
            print("  status: runnable now with --run")


def run_scenario(scenario: ExperimentScenario) -> list[dict[str, object]]:
    if scenario.runner != "local_python":
        return [
            {
                "tier": scenario.tier,
                "experiment": scenario.experiment,
                "scenario": scenario.name,
                "runner": scenario.runner,
                "status": "planned_not_run",
            }
        ]

    config = scenario.config
    results = run_benchmark(
        robots=int(config["robots"]),
        seconds=int(config["seconds"]),
        seed=int(config["seed"]),
        capacity_bytes_per_second=config.get("capacity_bytes_per_second"),
    )
    records = []
    for result in results:
        records.append(
            {
                "tier": scenario.tier,
                "experiment": scenario.experiment,
                "scenario": scenario.name,
                "runner": scenario.runner,
                "status": "ok",
                "policy": result.name,
                "robots": result.robots,
                "ticks": result.ticks,
                "sent": result.sent,
                "dropped": result.dropped,
                "deferred": result.deferred,
                "degraded": result.degraded,
                "bytes_sent": result.bytes_sent,
                "control_deadline_miss_ratio": result.control_deadline_miss_ratio,
                "stale_state_ratio": result.stale_state_ratio,
                "qoe_delivery_ratio": result.qoe_delivery_ratio,
                "utility_score": result.utility_score,
            }
        )
    return records


def export_trace_for_scenario(
    scenario: ExperimentScenario,
    output: Path,
    *,
    include_non_sent: bool,
) -> int:
    config = scenario.config
    events = generate_trace_events(
        scenario=scenario.name,
        robots=int(config["robots"]),
        seconds=int(config["seconds"]),
        seed=int(config["seed"]),
        capacity_bytes_per_second=config.get("capacity_bytes_per_second"),
        policies=None,
        include_non_sent=include_non_sent,
    )
    with output.open("w", encoding="utf-8") as handle:
        for event in events:
            handle.write(json.dumps(event, sort_keys=True) + "\n")
    return len(events)


if __name__ == "__main__":
    main()

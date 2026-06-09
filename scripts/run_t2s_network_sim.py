"""Probe and prepare T2S ns-3/OMNeT++ network simulation experiments."""

from __future__ import annotations

import argparse
import json
import shutil
from pathlib import Path

from fleetqox.testbed import ExperimentScenario, iter_scenarios, load_manifest
from fleetqox.trace import generate_trace_events, write_simulator_csv
from fleetqox.network_replay import (
    ReplayConfig,
    load_packet_trace,
    replay_trace,
    write_replay_jsonl,
)


DEFAULT_MANIFEST = Path("experiments/testbed_manifest.json")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--scenario", default=None)
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--prepare-inputs", action="store_true")
    parser.add_argument("--replay-inputs", action="store_true")
    parser.add_argument("--input-output-dir", type=Path, default=Path("traces_t2s"))
    parser.add_argument("--replay-output-dir", type=Path, default=Path("results_t2s"))
    parser.add_argument("--data-rate-mbps", type=float, default=20.0)
    parser.add_argument("--base-delay-ms", type=float, default=5.0)
    parser.add_argument("--jitter-ms", type=float, default=0.0)
    parser.add_argument("--loss", type=float, default=0.0)
    parser.add_argument("--queue-policy", choices=["fifo", "class_priority"], default="fifo")
    args = parser.parse_args()

    manifest = load_manifest(args.manifest)
    scenarios = [
        scenario
        for scenario in iter_scenarios(manifest)
        if scenario.tier == "T2S"
        and (args.scenario is None or scenario.name == args.scenario)
    ]
    if not scenarios:
        raise SystemExit("no matching T2S scenarios")

    probe = probe_network_simulators()
    records = []
    for scenario in scenarios:
        record = record_for_scenario(scenario, probe)
        if args.prepare_inputs or args.replay_inputs:
            args.input_output_dir.mkdir(parents=True, exist_ok=True)
            trace_path, packet_count = prepare_trace_input(scenario, args.input_output_dir)
            record["prepared_trace"] = str(trace_path)
            record["packet_rows"] = packet_count
        if args.replay_inputs:
            args.replay_output_dir.mkdir(parents=True, exist_ok=True)
            replay_path = args.replay_output_dir / f"{scenario.name}.jsonl"
            replay_records = replay_prepared_trace(
                Path(record["prepared_trace"]),
                replay_path,
                ReplayConfig(
                    data_rate_mbps=args.data_rate_mbps,
                    base_delay_ms=args.base_delay_ms,
                    jitter_ms=args.jitter_ms,
                    loss=args.loss,
                    queue_policy=args.queue_policy,
                ),
            )
            record["replay_results"] = str(replay_path)
            record["replay_records"] = replay_records
        records.append(record)

    if args.json:
        for record in records:
            print(json.dumps(record, sort_keys=True))
        return
    print_human(records)


def probe_network_simulators() -> dict[str, object]:
    ns3 = shutil.which("ns3")
    opp_run = shutil.which("opp_run")
    nedtool = shutil.which("nedtool")
    return {
        "ns3": ns3,
        "opp_run": opp_run,
        "nedtool": nedtool,
        "ns3_ready": ns3 is not None,
        "omnetpp_ready": opp_run is not None and nedtool is not None,
    }


def record_for_scenario(
    scenario: ExperimentScenario,
    probe: dict[str, object],
) -> dict[str, object]:
    simulator = scenario.config.get("simulator", "")
    if str(simulator).startswith("ns-3"):
        ready = bool(probe["ns3_ready"])
        reason = "ns3 found" if ready else "ns3 command not found"
        next_step = (
            "copy external/ns3/fleetqox_trace_replay.cc into ns-3 scratch and run"
            if ready
            else "install/build ns-3 and ensure the ns3 launcher is on PATH"
        )
    elif str(simulator).startswith("omnetpp"):
        ready = bool(probe["omnetpp_ready"])
        reason = "opp_run and nedtool found" if ready else "OMNeT++ commands not found"
        next_step = (
            "create an OMNeT++/INET project from external/omnetpp"
            if ready
            else "install OMNeT++ and INET, then validate the NED template"
        )
    else:
        ready = False
        reason = "unknown simulator"
        next_step = "check T2S scenario simulator field"

    return {
        "tier": scenario.tier,
        "experiment": scenario.experiment,
        "scenario": scenario.name,
        "runner": scenario.runner,
        "simulator": simulator,
        "status": "ready" if ready else "missing_tool",
        "reason": reason,
        "next_step": next_step,
        "probe": probe,
        "config": scenario.config,
        "baselines": scenario.baselines,
        "metrics": scenario.metrics,
    }


def prepare_trace_input(
    scenario: ExperimentScenario,
    output_dir: Path,
) -> tuple[Path, int]:
    """Prepare a CSV input trace for a T2S scenario.

    T2S scenarios are network models. Their traffic source is currently mapped
    to the closest T0 warehouse workload by robot count.
    """

    robots = int(scenario.config.get("robots", 100))
    seconds = 20 if robots >= 300 else 30
    capacity = max(200_000, robots * 6_000)
    events = generate_trace_events(
        scenario=scenario.name,
        robots=robots,
        seconds=seconds,
        seed=31,
        capacity_bytes_per_second=capacity,
        policies=None,
        include_non_sent=False,
    )
    output = output_dir / f"{scenario.name}.csv"
    count = write_simulator_csv(events, output)
    return output, count


def replay_prepared_trace(
    trace_path: Path,
    output_path: Path,
    config: ReplayConfig,
) -> int:
    records = replay_trace(load_packet_trace(trace_path), config)
    write_replay_jsonl(records, output_path)
    return len(records)


def print_human(records: list[dict[str, object]]) -> None:
    for record in records:
        print(f"{record['tier']} {record['experiment']}/{record['scenario']}")
        print(f"  simulator: {record['simulator']}")
        print(f"  status: {record['status']}")
        print(f"  reason: {record['reason']}")
        if "prepared_trace" in record:
            print(f"  prepared_trace: {record['prepared_trace']} ({record['packet_rows']} packets)")
        if "replay_results" in record:
            print(f"  replay_results: {record['replay_results']} ({record['replay_records']} records)")
        print(f"  next: {record['next_step']}")


if __name__ == "__main__":
    main()

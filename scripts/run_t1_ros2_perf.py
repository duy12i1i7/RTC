"""Probe and plan T1 ROS 2 synthetic graph benchmarks.

This runner is intentionally conservative. `performance_test` CLI details can
vary by ROS distribution and package build, so this script first discovers
whether ROS 2 and the benchmark executable are available. Once a ROS 2
environment is present, this runner can be extended to execute the discovered
command templates directly.
"""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
from pathlib import Path

from fleetqox.ros2_perf import (
    build_perf_commands,
    parse_many_perf_csv,
    run_perf_command,
    write_perf_records_jsonl,
)
from fleetqox.testbed import ExperimentScenario, iter_scenarios, load_manifest


DEFAULT_MANIFEST = Path("experiments/testbed_manifest.json")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--scenario", default=None)
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--plan-commands", action="store_true")
    parser.add_argument("--results-dir", type=Path, default=Path("results_t1"))
    parser.add_argument("--parse-results", action="store_true")
    parser.add_argument("--run", action="store_true")
    parser.add_argument("--output", type=Path, default=Path("results_t1/metrics.jsonl"))
    args = parser.parse_args()

    manifest = load_manifest(args.manifest)
    scenarios = [
        scenario
        for scenario in iter_scenarios(manifest)
        if scenario.tier == "T1"
        and (args.scenario is None or scenario.name == args.scenario)
    ]
    if not scenarios:
        raise SystemExit("no matching T1 scenarios")

    probe = probe_ros2_performance_test()
    records = [
        record_for_scenario(
            scenario,
            probe,
            results_dir=args.results_dir,
            include_commands=args.plan_commands,
        )
        for scenario in scenarios
    ]
    if args.parse_results:
        records.extend(parse_result_records(args.results_dir))
    if args.run:
        run_records = run_t1_commands(scenarios, probe, args.results_dir)
        write_perf_records_jsonl(run_records, args.output)
        records.extend(run_records)

    if args.json:
        for record in records:
            print(json.dumps(record, sort_keys=True))
        return

    print_human(records)


def probe_ros2_performance_test() -> dict[str, object]:
    ros2 = shutil.which("ros2")
    if not ros2:
        return {
            "status": "missing_tool",
            "ros2": None,
            "performance_test_executable": None,
            "reason": "ros2 command not found",
        }

    package_probe = subprocess.run(
        [ros2, "pkg", "executables", "performance_test"],
        check=False,
        capture_output=True,
        text=True,
    )
    if package_probe.returncode != 0:
        return {
            "status": "missing_package",
            "ros2": ros2,
            "performance_test_executable": None,
            "reason": package_probe.stderr.strip() or package_probe.stdout.strip(),
        }

    executable = _find_perf_executable(package_probe.stdout)
    if not executable:
        return {
            "status": "missing_executable",
            "ros2": ros2,
            "performance_test_executable": None,
            "reason": package_probe.stdout.strip(),
        }

    return {
        "status": "ready",
        "ros2": ros2,
        "performance_test_executable": executable,
        "reason": "performance_test executable discovered",
    }


def record_for_scenario(
    scenario: ExperimentScenario,
    probe: dict[str, object],
    *,
    results_dir: Path,
    include_commands: bool,
) -> dict[str, object]:
    record = {
        "tier": scenario.tier,
        "experiment": scenario.experiment,
        "scenario": scenario.name,
        "runner": scenario.runner,
        "status": probe["status"],
        "reason": probe["reason"],
        "ros2": probe["ros2"],
        "performance_test_executable": probe["performance_test_executable"],
        "baselines": scenario.baselines,
        "metrics": scenario.metrics,
        "config": scenario.config,
        "next_step": _next_step(probe),
    }
    if include_commands:
        executable = _executable_command(probe)
        commands = build_perf_commands(scenario, results_dir, executable=executable)
        record["commands"] = [
            {
                "rmw": command.rmw,
                "component": command.component,
                "logfile": str(command.logfile),
                "shell": command.shell(),
            }
            for command in commands
        ]
    return record


def print_human(records: list[dict[str, object]]) -> None:
    for record in records:
        if record.get("kind") == "parsed_result":
            print(f"parsed {record['path']}")
            print(f"  latency_p99_ms: {record['latency_p99_ms']}")
            print(f"  loss_ratio: {record['loss_ratio']}")
            continue
        if record.get("kind") == "run_result":
            print(f"ran {record['scenario']}/{record['rmw']}/{record['component']}")
            print(f"  status: {record['status']} returncode={record['returncode']}")
            print(f"  logfile: {record['logfile']}")
            continue
        print(f"{record['tier']} {record['experiment']}/{record['scenario']}")
        print(f"  status: {record['status']}")
        print(f"  reason: {record['reason']}")
        print(f"  baselines: {', '.join(record['baselines'])}")
        if "commands" in record:
            print(f"  commands: {len(record['commands'])}")
            for command in record["commands"][:3]:
                print(f"    {command['shell']}")
            if len(record["commands"]) > 3:
                print("    ...")
        print(f"  next: {record['next_step']}")


def _find_perf_executable(output: str) -> str | None:
    for line in output.splitlines():
        parts = line.split()
        if len(parts) == 2 and parts[0] == "performance_test":
            if parts[1] in {"perf_test", "performance_test"}:
                return parts[1]
    return None


def _next_step(probe: dict[str, object]) -> str:
    status = probe["status"]
    if status == "ready":
        return "extend this runner with distribution-specific performance_test CLI execution"
    if status == "missing_tool":
        return "source a ROS 2 environment or install ROS 2 on a Linux test host"
    if status == "missing_package":
        return "install the ROS 2 performance_test package for the active distro"
    return "inspect `ros2 pkg executables performance_test` output"


def _executable_command(probe: dict[str, object]) -> str:
    executable = probe.get("performance_test_executable")
    if executable:
        return f"ros2 run performance_test {executable}"
    return "perf_test"


def parse_result_records(results_dir: Path) -> list[dict[str, object]]:
    paths = sorted(results_dir.glob("**/*.csv"))
    records = []
    for parsed in parse_many_perf_csv(paths):
        parsed["kind"] = "parsed_result"
        records.append(parsed)
    return records


def run_t1_commands(
    scenarios: list[ExperimentScenario],
    probe: dict[str, object],
    results_dir: Path,
) -> list[dict[str, object]]:
    if probe["status"] != "ready":
        return [
            {
                "kind": "run_result",
                "status": "skipped",
                "reason": probe["reason"],
                "returncode": None,
                "scenario": scenario.name,
                "rmw": None,
                "component": None,
                "logfile": None,
            }
            for scenario in scenarios
        ]

    executable = _executable_command(probe)
    records = []
    for scenario in scenarios:
        for command in build_perf_commands(scenario, results_dir, executable=executable):
            record = run_perf_command(command)
            record["kind"] = "run_result"
            records.append(record)
    return records


if __name__ == "__main__":
    main()

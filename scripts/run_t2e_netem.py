"""Prepare and optionally run Docker/netem T2E trace emulation."""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
from pathlib import Path

from fleetqox.testbed import ExperimentScenario, iter_scenarios, load_manifest
from fleetqox.trace import generate_trace_events, write_simulator_csv
from fleetqox.udp_metrics import analyze_udp_trace, write_metrics_jsonl


DEFAULT_MANIFEST = Path("experiments/testbed_manifest.json")
COMPOSE_FILE = Path("external/docker-netem/docker-compose.yml")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--scenario", default=None)
    parser.add_argument("--prepare-inputs", action="store_true")
    parser.add_argument("--run", action="store_true")
    parser.add_argument("--analyze", action="store_true")
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--trace-output-dir", type=Path, default=Path("traces_t2e"))
    parser.add_argument("--result-output-dir", type=Path, default=Path("results_t2e"))
    args = parser.parse_args()

    manifest = load_manifest(args.manifest)
    scenarios = [
        scenario
        for scenario in iter_scenarios(manifest)
        if scenario.tier == "T2E"
        and (args.scenario is None or scenario.name == args.scenario)
    ]
    if not scenarios:
        raise SystemExit("no matching T2E scenarios")

    probe = probe_docker()
    records = []
    for scenario in scenarios:
        record = record_for_scenario(scenario, probe)
        if args.prepare_inputs or args.run:
            args.trace_output_dir.mkdir(parents=True, exist_ok=True)
            trace_path, packets = prepare_trace_input(scenario, args.trace_output_dir)
            record["prepared_trace"] = str(trace_path)
            record["packet_rows"] = packets
        if args.run:
            if not probe["docker_ready"]:
                record["status"] = "missing_tool"
                record["reason"] = probe["reason"]
            else:
                args.result_output_dir.mkdir(parents=True, exist_ok=True)
                received_path = args.result_output_dir / f"{scenario.name}_received.jsonl"
                run_docker_netem(scenario, Path(record["prepared_trace"]), received_path)
                record["received_trace"] = str(received_path)
                record["status"] = "ran"
                if args.analyze:
                    metrics_path = args.result_output_dir / f"{scenario.name}_metrics.jsonl"
                    metrics = analyze_udp_trace(Path(record["prepared_trace"]), received_path)
                    write_metrics_jsonl(metrics, metrics_path)
                    record["metrics_path"] = str(metrics_path)
                    record["metrics_records"] = len(metrics)
        records.append(record)

    if args.json:
        for record in records:
            print(json.dumps(record, sort_keys=True))
        return
    print_human(records)


def probe_docker() -> dict[str, object]:
    docker = shutil.which("docker")
    if not docker:
        return {
            "docker": None,
            "docker_ready": False,
            "compose_ready": False,
            "reason": "docker command not found",
        }
    compose = subprocess.run(
        [docker, "compose", "version"],
        check=False,
        capture_output=True,
        text=True,
    )
    info = subprocess.run(
        [docker, "info", "--format", "{{.ServerVersion}}"],
        check=False,
        capture_output=True,
        text=True,
    )
    ready = info.returncode == 0 and bool(info.stdout.strip())
    reason = "docker daemon ready" if ready else (info.stderr.strip() or "docker daemon not available")
    return {
        "docker": docker,
        "docker_ready": ready,
        "compose_ready": compose.returncode == 0,
        "compose_version": compose.stdout.strip(),
        "server_version": info.stdout.strip(),
        "reason": reason,
    }


def record_for_scenario(
    scenario: ExperimentScenario,
    probe: dict[str, object],
) -> dict[str, object]:
    return {
        "tier": scenario.tier,
        "experiment": scenario.experiment,
        "scenario": scenario.name,
        "runner": scenario.runner,
        "status": "ready" if probe["docker_ready"] else "missing_tool",
        "reason": probe["reason"],
        "probe": probe,
        "config": scenario.config,
        "baselines": scenario.baselines,
        "metrics": scenario.metrics,
    }


def prepare_trace_input(
    scenario: ExperimentScenario,
    output_dir: Path,
) -> tuple[Path, int]:
    config = scenario.config
    robots = int(config.get("trace_robots", 50))
    seconds = int(config.get("trace_seconds", 10))
    capacity = int(config.get("capacity_bytes_per_second", max(200_000, robots * 6_000)))
    events = generate_trace_events(
        scenario=scenario.name,
        robots=robots,
        seconds=seconds,
        seed=int(config.get("seed", 41)),
        capacity_bytes_per_second=capacity,
        policies=None,
        include_non_sent=False,
    )
    max_packets = int(config.get("max_packets", 0))
    if max_packets > 0:
        events = events[:max_packets]
    output = output_dir / f"{scenario.name}.csv"
    count = write_simulator_csv(events, output)
    return output, count


def run_docker_netem(
    scenario: ExperimentScenario,
    trace_path: Path,
    received_path: Path,
) -> None:
    if not COMPOSE_FILE.exists():
        raise SystemExit(f"missing compose file: {COMPOSE_FILE}")
    cwd = Path.cwd()
    env = os.environ.copy()
    if not env.get("DOCKER_NETEM_BASE_IMAGE"):
        env["DOCKER_NETEM_BASE_IMAGE"] = _default_base_image()
    if env["DOCKER_NETEM_BASE_IMAGE"].startswith("localhost/"):
        if not env.get("DOCKER_DEFAULT_PLATFORM"):
            env["DOCKER_DEFAULT_PLATFORM"] = "linux/amd64"
    env.update(
        {
            "TRACE_FILE": _relative_to_cwd(trace_path, cwd),
            "RESULT_FILE": _relative_to_cwd(received_path, cwd),
            "NETEM_DELAY_MS": str(scenario.config.get("delay_ms", 20)),
            "NETEM_JITTER_MS": str(scenario.config.get("jitter_ms", 5)),
            "NETEM_LOSS_PERCENT": str(scenario.config.get("loss_percent", 1)),
            "NETEM_RATE_MBIT": str(scenario.config.get("rate_mbit", 20)),
            "MAX_PACKETS": str(scenario.config.get("max_packets", 0)),
            "TIME_SCALE": str(scenario.config.get("time_scale", 1.0)),
            "IDLE_TIMEOUT_S": str(scenario.config.get("idle_timeout_s", 3)),
            "MAX_RUNTIME_S": str(scenario.config.get("max_runtime_s", 120)),
        }
    )
    subprocess.run(
        [
            "docker",
            "compose",
            "-f",
            str(COMPOSE_FILE),
            "up",
            "--build",
            "--abort-on-container-exit",
            "--remove-orphans",
        ],
        cwd=cwd,
        env=env,
        check=True,
    )
    subprocess.run(
        ["docker", "compose", "-f", str(COMPOSE_FILE), "down", "--remove-orphans"],
        cwd=cwd,
        env=env,
        check=False,
    )


def print_human(records: list[dict[str, object]]) -> None:
    for record in records:
        print(f"{record['tier']} {record['experiment']}/{record['scenario']}")
        print(f"  status: {record['status']}")
        print(f"  reason: {record['reason']}")
        if "prepared_trace" in record:
            print(f"  prepared_trace: {record['prepared_trace']} ({record['packet_rows']} packets)")
        if "received_trace" in record:
            print(f"  received_trace: {record['received_trace']}")
        if "metrics_path" in record:
            print(f"  metrics: {record['metrics_path']} ({record['metrics_records']} records)")


def _relative_to_cwd(path: Path, cwd: Path) -> str:
    resolved = path.resolve()
    try:
        return str(resolved.relative_to(cwd.resolve()))
    except ValueError:
        return str(resolved)


def _default_base_image() -> str:
    local = subprocess.run(
        ["docker", "image", "inspect", "ros2-netem-publisher:latest"],
        check=False,
        capture_output=True,
        text=True,
    )
    if local.returncode == 0:
        tagged = subprocess.run(
            [
                "docker",
                "tag",
                "ros2-netem-publisher:latest",
                "localhost/fleetqox/docker-netem-base:latest",
            ],
            check=False,
            capture_output=True,
            text=True,
        )
        if tagged.returncode == 0:
            return "localhost/fleetqox/docker-netem-base:latest"
        return "ros2-netem-publisher:latest"
    return "python:3.12-slim"


if __name__ == "__main__":
    main()

"""Run ROS 2 performance_test traffic through Docker/netem."""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
from pathlib import Path

from fleetqox.ros2_netem import build_ros2_netem_plan
from fleetqox.ros2_perf import parse_perf_csv, summarize_perf_records, write_perf_records_jsonl
from fleetqox.testbed import ExperimentScenario, iter_scenarios, load_manifest


DEFAULT_MANIFEST = Path("experiments/testbed_manifest.json")
COMPOSE_FILE = Path("external/ros2-netem/docker-compose.yml")
ZENOH_COMPOSE_FILE = Path("external/ros2-netem/docker-compose.zenoh.yml")
DEFAULT_RMW = "rmw_fastrtps_cpp"
DEFAULT_MATRIX_RMWS = ["rmw_fastrtps_cpp", "rmw_cyclonedds_cpp", "rmw_zenoh_cpp"]
DEFAULT_COMPONENT = "control"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--scenario", action="append", dest="scenarios")
    parser.add_argument("--all-scenarios", action="store_true")
    parser.add_argument("--rmw", action="append", dest="rmws")
    parser.add_argument("--all-rmws", action="store_true")
    parser.add_argument("--component", action="append", dest="components")
    parser.add_argument("--components", dest="components_csv")
    parser.add_argument("--repeat", type=int, default=1)
    parser.add_argument("--run-id")
    parser.add_argument("--runtime-s", type=float)
    parser.add_argument("--rate-hz", type=float)
    parser.add_argument("--msg")
    parser.add_argument("--qos")
    parser.add_argument("--zenoh-topology", choices=["auto", "router", "peer"], default="auto")
    parser.add_argument("--results-dir", type=Path, default=Path("results_t2e_ros2"))
    parser.add_argument("--output", type=Path, default=Path("results_t2e_ros2/metrics.jsonl"))
    parser.add_argument("--summary-output", type=Path, default=Path("results_t2e_ros2/summary.json"))
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--run", action="store_true")
    parser.add_argument("--analyze", action="store_true")
    parser.add_argument("--stop-on-error", action="store_true")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    scenarios = resolve_scenarios(args.manifest, args.scenarios, all_scenarios=args.all_scenarios)
    rmws = resolve_rmws(args.rmws, all_rmws=args.all_rmws)
    components = resolve_components(args.components, args.components_csv)
    probe = probe_docker()

    plans = []
    use_run_label = args.repeat > 1 or bool(args.run_id)
    for scenario in scenarios:
        for rmw in rmws:
            for component in components:
                for repeat_index in range(args.repeat):
                    run_label = None
                    if use_run_label:
                        prefix = f"{args.run_id}_" if args.run_id else ""
                        run_label = f"{prefix}r{repeat_index + 1:03d}"
                    plans.append(
                        build_ros2_netem_plan(
                            scenario,
                            rmw=rmw,
                            component=component,
                            results_dir=args.results_dir,
                            run_label=run_label,
                            runtime_s=args.runtime_s,
                            rate_hz=args.rate_hz,
                            msg=args.msg,
                            qos=args.qos,
                            zenoh_topology=args.zenoh_topology,
                        )
                    )

    records = []
    for plan in plans:
        scenario = next(item for item in scenarios if item.name == plan.scenario)
        record = build_record(scenario, plan, probe)
        if args.dry_run:
            records.append(record)
            continue
        if args.run:
            if not probe["docker_ready"]:
                record["status"] = "skipped"
            else:
                try:
                    run_compose(plan)
                    record["status"] = "ran"
                except subprocess.CalledProcessError as exc:
                    record["status"] = "failed"
                    record["returncode"] = exc.returncode
                    record["error"] = str(exc)
                    records.append(record)
                    if args.stop_on_error:
                        raise
                    continue
            if args.analyze:
                attach_metrics(record, plan)
        elif args.analyze:
            if plan.result_log.exists():
                attach_metrics(record, plan)
                record["status"] = "analyzed"
            else:
                record["status"] = "missing_log"
        records.append(record)

    metric_records = [record["metrics"] for record in records if isinstance(record.get("metrics"), dict)]
    summary = summarize_perf_records(metric_records) if metric_records else {"groups": [], "ranking": []}
    if metric_records:
        write_perf_records_jsonl(metric_records, args.output)
        args.summary_output.parent.mkdir(parents=True, exist_ok=True)
        args.summary_output.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        for record in records:
            if isinstance(record.get("metrics"), dict):
                record["metrics_path"] = str(args.output)
                record["summary_path"] = str(args.summary_output)

    suite_record = {
        "kind": "t2e_ros2_netem_suite",
        "plans": len(plans),
        "records": records,
        "summary": summary,
        "metrics_path": str(args.output) if metric_records else None,
        "summary_path": str(args.summary_output) if metric_records else None,
    }

    if args.json:
        print(json.dumps(suite_record, sort_keys=True))
        return
    print_human(suite_record, dry_run=args.dry_run)


def resolve_scenarios(
    manifest_path: Path,
    names: list[str] | None,
    *,
    all_scenarios: bool,
) -> list[ExperimentScenario]:
    manifest = load_manifest(manifest_path)
    t2e = [scenario for scenario in iter_scenarios(manifest) if scenario.tier == "T2E"]
    if all_scenarios:
        return t2e
    selected_names = expand_csv(names) if names else ["wifi_loss_jitter"]
    scenarios = []
    missing = []
    for name in selected_names:
        scenario = next((item for item in t2e if item.name == name), None)
        if scenario:
            scenarios.append(scenario)
        else:
            missing.append(name)
    if missing:
        raise SystemExit(f"no T2E scenario named {', '.join(missing)}")
    return scenarios


def find_scenario(manifest_path: Path, name: str) -> ExperimentScenario:
    for scenario in resolve_scenarios(manifest_path, [name], all_scenarios=False):
        return scenario
    raise SystemExit(f"no T2E scenario named {name}")


def resolve_rmws(values: list[str] | None, *, all_rmws: bool) -> list[str]:
    if all_rmws:
        return DEFAULT_MATRIX_RMWS
    return expand_csv(values) if values else [DEFAULT_RMW]


def resolve_components(values: list[str] | None, csv_value: str | None) -> list[str]:
    selected = expand_csv(values)
    if csv_value:
        selected.extend(expand_csv([csv_value]))
    return selected or [DEFAULT_COMPONENT]


def expand_csv(values: list[str] | None) -> list[str]:
    if not values:
        return []
    expanded = []
    for value in values:
        expanded.extend(part.strip() for part in value.split(",") if part.strip())
    return expanded


def build_record(scenario: ExperimentScenario, plan, probe: dict[str, object]) -> dict[str, object]:
    return {
        "tier": scenario.tier,
        "experiment": scenario.experiment,
        "scenario": scenario.name,
        "rmw": plan.rmw,
        "component": plan.component,
        "run_label": plan.run_label,
        "topology": plan.topology,
        "status": "ready" if probe["docker_ready"] else "missing_tool",
        "reason": probe["reason"],
        "result_log": str(plan.result_log),
        "subscriber_command": plan.subscriber_command,
        "publisher_command": plan.publisher_command,
        "rate_hz": plan.rate_hz,
        "runtime_s": plan.runtime_s,
        "deadline_ms": plan.deadline_ms,
        "env": plan.env,
        "probe": probe,
    }


def attach_metrics(record: dict[str, object], plan) -> None:
    metrics = parse_result(plan)
    record["metrics"] = metrics


def parse_result(plan) -> dict[str, object]:
    parsed = parse_perf_csv(plan.result_log, deadline_ms=plan.deadline_ms)
    parsed.update(
        {
            "kind": "t2e_ros2_netem_result",
            "scenario": plan.scenario,
            "rmw": plan.rmw,
            "component": plan.component,
            "run_label": plan.run_label,
            "topology": plan.topology,
            "rate_hz": plan.rate_hz,
            "runtime_s": plan.runtime_s,
            "deadline_ms": plan.deadline_ms,
            "qoe_score": compute_qoe_score(parsed, plan.deadline_ms),
            "logfile": str(plan.result_log),
        }
    )
    return parsed


def compute_qoe_score(metrics: dict[str, object], deadline_ms: float) -> float:
    if metrics.get("no_samples"):
        return 0.0
    loss = float(metrics.get("loss_ratio", 0.0))
    deadline = float(metrics.get("deadline_miss_ratio", 0.0))
    latency = min(1.0, float(metrics.get("latency_p95_ms", 0.0)) / max(1.0, deadline_ms * 2.0))
    jitter = min(1.0, float(metrics.get("jitter_p95_ms", 0.0)) / max(1.0, deadline_ms))
    return max(0.0, 1.0 - 0.40 * loss - 0.35 * deadline - 0.20 * latency - 0.05 * jitter)


def probe_docker() -> dict[str, object]:
    docker = shutil.which("docker")
    if not docker:
        return {"docker_ready": False, "reason": "docker command not found", "docker": None}
    info = subprocess.run(
        [docker, "info", "--format", "{{.ServerVersion}}"],
        check=False,
        capture_output=True,
        text=True,
    )
    ready = info.returncode == 0 and bool(info.stdout.strip())
    return {
        "docker": docker,
        "docker_ready": ready,
        "server_version": info.stdout.strip(),
        "reason": "docker daemon ready" if ready else (info.stderr.strip() or "docker daemon not available"),
    }


def run_compose(plan) -> None:
    env = os.environ.copy()
    env.update(plan.env)
    compose_args = compose_files_for_plan(plan)
    try:
        subprocess.run(
            [
                "docker",
                "compose",
                *compose_args,
                "up",
                "--build",
                "--abort-on-container-exit",
                "--remove-orphans",
            ],
            check=True,
            env=env,
        )
    finally:
        subprocess.run(
            ["docker", "compose", *compose_args, "down", "--remove-orphans"],
            check=False,
            env=env,
        )


def compose_files_for_plan(plan) -> list[str]:
    args = ["-f", str(COMPOSE_FILE)]
    if plan.topology == "zenoh_router":
        args.extend(["-f", str(ZENOH_COMPOSE_FILE)])
    return args


def print_human(suite: dict[str, object], *, dry_run: bool) -> None:
    records = list(suite["records"])
    print(f"T2E ROS/netem suite")
    print(f"  plans: {suite['plans']}")
    print(f"  statuses: {status_counts(records)}")
    for record in records[:10]:
        print(
            f"  - {record['scenario']} {record['rmw']} {record['component']} "
            f"{record.get('topology') or ''} {record.get('run_label') or ''}".rstrip()
        )
        print(f"    status: {record['status']}")
        print(f"    result_log: {record['result_log']}")
        if dry_run:
            print(f"    subscriber: {record['subscriber_command']}")
            print(f"    publisher: {record['publisher_command']}")
    if len(records) > 10:
        print(f"  ... {len(records) - 10} more plans")
    if dry_run:
        print("  dry-run: compose was not executed")
    if suite.get("metrics_path"):
        print(f"  metrics: {suite['metrics_path']}")
        print(f"  summary: {suite['summary_path']}")
        ranking = list(suite["summary"].get("ranking", []))  # type: ignore[union-attr]
        if ranking:
            best = ranking[0]
            print(
                "  best: "
                f"{best['scenario']} {best['component']} {best['rmw']} "
                f"score={float(best['rank_score']):.3f} "
                f"p95={float(best['latency_p95_ms_mean']):.2f}ms "
                f"loss={float(best['loss_ratio_mean']):.3f}"
            )


def status_counts(records: list[dict[str, object]]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for record in records:
        status = str(record.get("status", "unknown"))
        counts[status] = counts.get(status, 0) + 1
    return counts


if __name__ == "__main__":
    main()

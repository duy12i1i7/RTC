"""Run repeated FleetQoX sidecar Docker/netem sweeps."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

from fleetqox.sidecar_repeated import (
    read_sidecar_metric_records,
    summarize_repeated_sidecar_metrics,
    write_repeated_markdown_report,
    write_repeated_summary_json,
)
from fleetqox.sidecar_runtime import SIDECAR_POLICIES
from scripts.run_sidecar_netem import resolve_policies


@dataclass(frozen=True)
class SidecarRepeatedRun:
    scenario: str
    seed: int
    metrics_path: Path
    profile: str | None = None


@dataclass(frozen=True)
class NetemProfile:
    label: str
    capacity_bytes_per_second: int
    delay_ms: float
    jitter_ms: float
    loss_percent: float
    rate_mbit: float
    description: str

    def as_config(self) -> dict[str, object]:
        return {
            "capacity_bytes_per_second": self.capacity_bytes_per_second,
            "delay_ms": self.delay_ms,
            "jitter_ms": self.jitter_ms,
            "loss_percent": self.loss_percent,
            "rate_mbit": self.rate_mbit,
            "description": self.description,
        }


NETEM_PROFILES = {
    "lan": NetemProfile(
        label="lan",
        capacity_bytes_per_second=180_000,
        delay_ms=3,
        jitter_ms=1,
        loss_percent=0.1,
        rate_mbit=100,
        description="low-latency wired or strong LAN baseline",
    ),
    "wifi": NetemProfile(
        label="wifi",
        capacity_bytes_per_second=120_000,
        delay_ms=20,
        jitter_ms=5,
        loss_percent=1,
        rate_mbit=20,
        description="current shared Wi-Fi-like baseline",
    ),
    "wan": NetemProfile(
        label="wan",
        capacity_bytes_per_second=90_000,
        delay_ms=60,
        jitter_ms=15,
        loss_percent=1.5,
        rate_mbit=10,
        description="cloud or remote-operator WAN path",
    ),
    "roaming": NetemProfile(
        label="roaming",
        capacity_bytes_per_second=70_000,
        delay_ms=80,
        jitter_ms=25,
        loss_percent=3,
        rate_mbit=5,
        description="capacity-drop and handoff stress profile",
    ),
}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--run", action="store_true")
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--scenario-prefix", default="sidecar_repeated_v1")
    parser.add_argument("--policy", action="append", choices=SIDECAR_POLICIES)
    parser.add_argument("--all-policies", action="store_true")
    parser.add_argument("--seeds", default="7,13,29")
    parser.add_argument("--robots", type=int, default=10)
    parser.add_argument("--seconds", type=int, default=2)
    parser.add_argument("--capacity-bytes-per-second", type=int, default=120_000)
    parser.add_argument("--delay-ms", type=float, default=20)
    parser.add_argument("--jitter-ms", type=float, default=5)
    parser.add_argument("--loss-percent", type=float, default=1)
    parser.add_argument("--rate-mbit", type=float, default=20)
    parser.add_argument(
        "--profile",
        action="append",
        choices=sorted(NETEM_PROFILES),
        help="Run one or more named netem profiles instead of the scalar netem options.",
    )
    parser.add_argument("--closed-loop-feed", action="store_true")
    parser.add_argument("--policy-label")
    parser.add_argument("--lagrangian-deadline-risk-budget", type=float)
    parser.add_argument("--lagrangian-initial-deadline-lambda", type=float)
    parser.add_argument("--lagrangian-risk-barrier-start", type=float)
    parser.add_argument("--lagrangian-risk-barrier-scale", type=float)
    parser.add_argument("--lagrangian-deadline-drop-risk", type=float)
    parser.add_argument("--output-dir", type=Path, default=Path("results_sidecar_repeated/netem"))
    parser.add_argument(
        "--summary-json",
        type=Path,
        default=Path("results_sidecar_repeated/repeated_netem_summary.json"),
    )
    parser.add_argument(
        "--markdown",
        type=Path,
        default=Path("results_sidecar_repeated/repeated_netem_report.md"),
    )
    parser.add_argument("--title", default="Sidecar Repeated Docker/netem Sweep")
    parser.add_argument(
        "--report",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Write summary JSON and Markdown after a successful --run.",
    )
    args = parser.parse_args()

    seeds = parse_ints(args.seeds, "--seeds")
    policies = resolve_policies(args.policy, args.all_policies)
    plans = build_run_plan(args.scenario_prefix, seeds, args.output_dir, args.profile)
    commands = [build_netem_command(args, policies, plan) for plan in plans]

    if args.run:
        args.output_dir.mkdir(parents=True, exist_ok=True)
        for command in commands:
            subprocess.run(command, check=True)
        summary_record = write_report_if_requested(args, plans)
    else:
        summary_record = {}

    result = {
        "mode": "run" if args.run else "plan",
        "policies": policies,
        "profiles": args.profile or ["custom"],
        "runs": len(plans),
        "commands": commands,
        "metrics": [str(plan.metrics_path) for plan in plans],
        **summary_record,
    }
    if args.json:
        print(json.dumps(result, sort_keys=True))
        return
    print_human(result)


def build_run_plan(
    scenario_prefix: str,
    seeds: list[int],
    output_dir: Path,
    profiles: list[str] | None = None,
) -> list[SidecarRepeatedRun]:
    plans = []
    if not profiles:
        for seed in seeds:
            scenario = f"{scenario_prefix}_seed_{seed}"
            plans.append(
                SidecarRepeatedRun(
                    scenario=scenario,
                    seed=seed,
                    metrics_path=output_dir / f"{scenario}_matrix_metrics.jsonl",
                )
            )
        return plans

    for profile in profiles:
        if profile not in NETEM_PROFILES:
            raise SystemExit(f"unknown --profile: {profile}")
        for seed in seeds:
            scenario = f"{scenario_prefix}_{profile}_seed_{seed}"
            plans.append(
                SidecarRepeatedRun(
                    scenario=scenario,
                    seed=seed,
                    metrics_path=output_dir / f"{scenario}_matrix_metrics.jsonl",
                    profile=profile,
                )
            )
    return plans


def build_netem_command(
    args: argparse.Namespace,
    policies: list[str],
    plan: SidecarRepeatedRun,
) -> list[str]:
    netem = netem_values_for(args, plan.profile)
    command = [
        sys.executable,
        "-m",
        "scripts.run_sidecar_netem",
        "--run",
        "--analyze",
        "--scenario",
        plan.scenario,
        "--robots",
        str(args.robots),
        "--seconds",
        str(args.seconds),
        "--seed",
        str(plan.seed),
        "--capacity-bytes-per-second",
        str(netem["capacity_bytes_per_second"]),
        "--delay-ms",
        str(netem["delay_ms"]),
        "--jitter-ms",
        str(netem["jitter_ms"]),
        "--loss-percent",
        str(netem["loss_percent"]),
        "--rate-mbit",
        str(netem["rate_mbit"]),
        "--output-dir",
        str(args.output_dir),
    ]
    for policy in policies:
        command.extend(["--policy", policy])
    if args.policy_label:
        command.extend(["--policy-label", args.policy_label])
    for option, value in lagrangian_option_values(args):
        command.extend([option, str(value)])
    if args.closed_loop_feed:
        command.append("--closed-loop-feed")
    return command


def netem_values_for(args: argparse.Namespace, profile: str | None) -> dict[str, object]:
    if profile is None:
        return {
            "capacity_bytes_per_second": args.capacity_bytes_per_second,
            "delay_ms": args.delay_ms,
            "jitter_ms": args.jitter_ms,
            "loss_percent": args.loss_percent,
            "rate_mbit": args.rate_mbit,
        }
    return NETEM_PROFILES[profile].as_config()


def write_report_if_requested(
    args: argparse.Namespace,
    plans: list[SidecarRepeatedRun],
) -> dict[str, object]:
    if not args.report:
        return {}
    metric_paths = [plan.metrics_path for plan in plans if plan.metrics_path.exists()]
    missing_metric_paths = [
        str(plan.metrics_path) for plan in plans if not plan.metrics_path.exists()
    ]
    if not metric_paths:
        return {
            "report_skipped": True,
            "missing_metrics": missing_metric_paths,
        }
    records = annotate_records_with_profiles(read_sidecar_metric_records(metric_paths), plans)
    summary = summarize_repeated_sidecar_metrics(records)
    profiles = summarize_profiles(records, plans)
    if profiles:
        summary["profiles"] = profiles
    write_repeated_summary_json(summary, args.summary_json)
    write_repeated_markdown_report(
        summary,
        args.markdown,
        title=args.title,
        metrics_paths=metric_paths,
    )
    return {
        "summary_json": str(args.summary_json),
        "markdown": str(args.markdown),
        "records": summary["records"],
        "pareto_frontier": summary["pareto_frontier"],
        "missing_metrics": missing_metric_paths,
    }


def annotate_records_with_profiles(
    records: list[dict[str, object]],
    plans: list[SidecarRepeatedRun],
) -> list[dict[str, object]]:
    profiled = [plan for plan in plans if plan.profile]
    if not profiled:
        return records
    annotated = []
    for record in records:
        scenario = str(record.get("scenario", ""))
        profile = profile_for_scenario(scenario, profiled)
        item = dict(record)
        if profile:
            item["profile"] = profile
        annotated.append(item)
    return annotated


def profile_for_scenario(scenario: str, plans: list[SidecarRepeatedRun]) -> str | None:
    matches = [
        plan
        for plan in plans
        if plan.profile and scenario.startswith(plan.scenario)
    ]
    if not matches:
        return None
    return max(matches, key=lambda plan: len(plan.scenario)).profile


def summarize_profiles(
    records: list[dict[str, object]],
    plans: list[SidecarRepeatedRun],
) -> list[dict[str, object]]:
    profile_order = []
    for plan in plans:
        if plan.profile and plan.profile not in profile_order:
            profile_order.append(plan.profile)
    summaries = []
    for profile in profile_order:
        profile_records = [
            record for record in records if record.get("profile") == profile
        ]
        if not profile_records:
            continue
        summary = summarize_repeated_sidecar_metrics(profile_records)
        summary["profile"] = profile
        summary["config"] = NETEM_PROFILES[profile].as_config()
        summaries.append(summary)
    return summaries


def parse_ints(value: str, option: str) -> list[int]:
    try:
        parsed = [int(part.strip()) for part in value.split(",") if part.strip()]
    except ValueError as exc:
        raise SystemExit(f"{option} must be a comma-separated integer list") from exc
    if not parsed or any(item < 0 for item in parsed):
        raise SystemExit(f"{option} must contain non-negative integers")
    return parsed


def lagrangian_option_values(args: argparse.Namespace) -> list[tuple[str, float]]:
    values = [
        ("--lagrangian-deadline-risk-budget", args.lagrangian_deadline_risk_budget),
        ("--lagrangian-initial-deadline-lambda", args.lagrangian_initial_deadline_lambda),
        ("--lagrangian-risk-barrier-start", args.lagrangian_risk_barrier_start),
        ("--lagrangian-risk-barrier-scale", args.lagrangian_risk_barrier_scale),
        ("--lagrangian-deadline-drop-risk", args.lagrangian_deadline_drop_risk),
    ]
    return [(option, value) for option, value in values if value is not None]


def print_human(result: dict[str, object]) -> None:
    print(f"sidecar-repeated-netem mode={result['mode']} runs={result['runs']}")
    print(f"  policies: {', '.join(result['policies'])}")
    for command in result["commands"]:
        print("  command:")
        print("    " + " ".join(str(part) for part in command))
    if "markdown" in result:
        print(f"  markdown: {result['markdown']}")
    if "summary_json" in result:
        print(f"  summary_json: {result['summary_json']}")


if __name__ == "__main__":
    main()

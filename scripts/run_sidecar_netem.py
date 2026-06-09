"""Run FleetRMW sidecar runtime through Docker/netem."""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
from pathlib import Path

from fleetqox.sidecar_metrics import analyze_sidecar_runtime, write_sidecar_metrics_jsonl
from fleetqox.sidecar_runtime import SIDECAR_POLICIES


COMPOSE_FILE = Path("external/docker-netem/docker-compose.sidecar.yml")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--run", action="store_true")
    parser.add_argument("--analyze", action="store_true")
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--scenario", default="sidecar_netem_v1")
    parser.add_argument("--policy", action="append", choices=SIDECAR_POLICIES)
    parser.add_argument("--all-policies", action="store_true")
    parser.add_argument("--robots", type=int, default=10)
    parser.add_argument("--seconds", type=int, default=2)
    parser.add_argument("--seed", type=int, default=7)
    parser.add_argument("--capacity-bytes-per-second", type=int, default=120_000)
    parser.add_argument("--delay-ms", type=float, default=20)
    parser.add_argument("--jitter-ms", type=float, default=5)
    parser.add_argument("--loss-percent", type=float, default=1)
    parser.add_argument("--rate-mbit", type=float, default=20)
    parser.add_argument("--output-dir", type=Path, default=Path("results_sidecar_netem"))
    parser.add_argument("--idle-timeout-s", type=float, default=3)
    parser.add_argument("--max-runtime-s", type=float, default=120)
    parser.add_argument("--closed-loop-feed", action="store_true")
    parser.add_argument("--policy-label")
    parser.add_argument("--lagrangian-deadline-risk-budget", type=float)
    parser.add_argument("--lagrangian-initial-deadline-lambda", type=float)
    parser.add_argument("--lagrangian-risk-barrier-start", type=float)
    parser.add_argument("--lagrangian-risk-barrier-scale", type=float)
    parser.add_argument("--lagrangian-deadline-drop-risk", type=float)
    args = parser.parse_args()

    probe = probe_docker()
    policies = resolve_policies(args.policy, args.all_policies)
    args.output_dir.mkdir(parents=True, exist_ok=True)
    matrix_metrics = args.output_dir / f"{args.scenario}_matrix_metrics.jsonl"
    record: dict[str, object] = {
        "scenario": args.scenario,
        "policies": policies,
        "status": "ready" if probe["docker_ready"] else "missing_tool",
        "reason": probe["reason"],
        "probe": probe,
        "matrix_metrics": str(matrix_metrics),
        "runs": [],
        "config": {
            "robots": args.robots,
            "seconds": args.seconds,
            "seed": args.seed,
            "capacity_bytes_per_second": args.capacity_bytes_per_second,
            "delay_ms": args.delay_ms,
            "jitter_ms": args.jitter_ms,
            "loss_percent": args.loss_percent,
            "rate_mbit": args.rate_mbit,
            "closed_loop_feed": args.closed_loop_feed,
        },
    }

    matrix_records: list[dict[str, object]] = []
    run_records: list[dict[str, object]] = []
    if args.run:
        if not probe["docker_ready"]:
            record["status"] = "missing_tool"
        else:
            for policy in policies:
                run_name = run_name_for(args.scenario, policy, len(policies) > 1)
                decisions = args.output_dir / f"{run_name}_decisions.jsonl"
                received = args.output_dir / f"{run_name}_received.jsonl"
                metrics = args.output_dir / f"{run_name}_metrics.jsonl"
                run_docker_sidecar_netem(args, policy, run_name, decisions, received)
                run_record = {
                    "policy": policy,
                    "scenario": run_name,
                    "decisions": str(decisions),
                    "received": str(received),
                    "metrics": str(metrics),
                    "status": "ran",
                }
                if args.analyze:
                    records = analyze_sidecar_runtime(decisions, received)
                    for metric in records:
                        metric["scenario"] = run_name
                    write_sidecar_metrics_jsonl(records, metrics)
                    run_record["summary"] = records
                    matrix_records.extend(records)
                run_records.append(run_record)
            record["status"] = "ran"
    elif args.analyze:
        for policy in policies:
            run_name = run_name_for(args.scenario, policy, len(policies) > 1)
            decisions = args.output_dir / f"{run_name}_decisions.jsonl"
            received = args.output_dir / f"{run_name}_received.jsonl"
            metrics = args.output_dir / f"{run_name}_metrics.jsonl"
            records = analyze_sidecar_runtime(decisions, received)
            for metric in records:
                metric["scenario"] = run_name
            write_sidecar_metrics_jsonl(records, metrics)
            matrix_records.extend(records)
            run_records.append(
                {
                    "policy": policy,
                    "scenario": run_name,
                    "decisions": str(decisions),
                    "received": str(received),
                    "metrics": str(metrics),
                    "summary": records,
                    "status": "analyzed",
                }
            )
    if matrix_records:
        write_sidecar_metrics_jsonl(matrix_records, matrix_metrics)
        record["metrics_records"] = len(matrix_records)
        record["summary"] = matrix_records
    record["runs"] = run_records

    if args.json:
        print(json.dumps(record, sort_keys=True))
        return
    print_human(record)


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


def run_docker_sidecar_netem(
    args: argparse.Namespace,
    policy: str,
    scenario: str,
    decisions: Path,
    received: Path,
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
            "DECISION_FILE": _relative_to_cwd(decisions, cwd),
            "RESULT_FILE": _relative_to_cwd(received, cwd),
            "NETEM_DELAY_MS": str(args.delay_ms),
            "NETEM_JITTER_MS": str(args.jitter_ms),
            "NETEM_LOSS_PERCENT": str(args.loss_percent),
            "NETEM_RATE_MBIT": str(args.rate_mbit),
            "IDLE_TIMEOUT_S": str(args.idle_timeout_s),
            "MAX_RUNTIME_S": str(args.max_runtime_s),
            "SIDECAR_IDLE_TIMEOUT_S": str(args.max_runtime_s),
            "SIDECAR_MAX_RUNTIME_S": str(args.max_runtime_s),
            "SIDECAR_POLICY": policy,
            "SIDECAR_SCENARIO": scenario,
            "SIDECAR_ROBOTS": str(args.robots),
            "SIDECAR_SECONDS": str(args.seconds),
            "SIDECAR_SEED": str(args.seed),
            "SIDECAR_CAPACITY_BYTES_PER_SECOND": str(args.capacity_bytes_per_second),
            "SIDECAR_LINK_RTT_MS": str(2.0 * args.delay_ms),
            "SIDECAR_LINK_JITTER_MS": str(args.jitter_ms),
            "SIDECAR_LINK_LOSS": str(args.loss_percent / 100.0),
            "SIDECAR_FEEDER_MODULE": feeder_module_for(args.closed_loop_feed),
        }
    )
    env.update(lagrangian_env_overrides(args, policy))
    subprocess.run(
        [
            "docker",
            "compose",
            "-f",
            str(COMPOSE_FILE),
            "up",
            "--build",
            "--remove-orphans",
        ],
        cwd=cwd,
        env=env,
        check=True,
    )
    subprocess.run(
        ["docker", "compose", "-f", str(COMPOSE_FILE), "down", "--remove-orphans", "--volumes"],
        cwd=cwd,
        env=env,
        check=False,
    )


def print_human(record: dict[str, object]) -> None:
    print(f"sidecar-netem {record['scenario']}")
    print(f"  status: {record['status']}")
    print(f"  reason: {record['reason']}")
    print(f"  policies: {', '.join(record['policies'])}")
    print(f"  matrix_metrics: {record['matrix_metrics']}")
    for run in record.get("runs", []):
        print(f"  run {run['policy']}:")
        print(f"    decisions: {run['decisions']}")
        print(f"    received: {run['received']}")
        print(f"    metrics: {run['metrics']}")
    if "summary" in record:
        for item in record["summary"]:
            print(
                "  "
                f"{item['policy']}: tx={item['tx']} rx={item['rx']} "
                f"loss={item['loss_ratio']:.3f} p95={item['latency_p95_ms']:.2f}ms "
                f"deadline={item['deadline_miss_ratio']:.3f}"
            )


def resolve_policies(selected: list[str] | None, all_policies: bool) -> list[str]:
    if all_policies:
        return list(SIDECAR_POLICIES)
    if selected:
        deduped = []
        for policy in selected:
            if policy not in deduped:
                deduped.append(policy)
        return deduped
    return ["fleetqox_predictive"]


def run_name_for(scenario: str, policy: str, matrix: bool) -> str:
    if matrix:
        return f"{scenario}_{policy}"
    return scenario


def feeder_module_for(closed_loop: bool) -> str:
    if closed_loop:
        return "scripts.feed_sidecar_closed_loop"
    return "scripts.feed_sidecar_synthetic"


def lagrangian_env_overrides(args: argparse.Namespace, policy: str) -> dict[str, str]:
    if policy != "fleetqox_predictive_lagrangian":
        return {}
    values = {
        "SIDECAR_POLICY_LABEL": args.policy_label,
        "SIDECAR_LAGRANGIAN_DEADLINE_RISK_BUDGET": args.lagrangian_deadline_risk_budget,
        "SIDECAR_LAGRANGIAN_INITIAL_DEADLINE_LAMBDA": args.lagrangian_initial_deadline_lambda,
        "SIDECAR_LAGRANGIAN_RISK_BARRIER_START": args.lagrangian_risk_barrier_start,
        "SIDECAR_LAGRANGIAN_RISK_BARRIER_SCALE": args.lagrangian_risk_barrier_scale,
        "SIDECAR_LAGRANGIAN_DEADLINE_DROP_RISK": args.lagrangian_deadline_drop_risk,
    }
    return {key: str(value) for key, value in values.items() if value not in {None, ""}}


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


def _relative_to_cwd(path: Path, cwd: Path) -> str:
    resolved = path.resolve()
    try:
        return str(resolved.relative_to(cwd.resolve()))
    except ValueError:
        return str(resolved)


if __name__ == "__main__":
    main()

"""Run and summarize ROS 2 N-robot QoE recovery quota live-bridge matrices."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import subprocess
import sys
from typing import Iterable, Mapping

from scripts.run_ros2_docker_live_bridge import parse_ints


SUMMARY_FIELDS = (
    "runs",
    "robot_count_mean",
    "per_robot_budget_pass_ratio",
    "per_robot_min_control_delivery_ratio_mean",
    "per_robot_max_deadline_miss_ratio_mean",
    "decision_robot_coverage_ratio_mean",
    "received_robot_coverage_ratio_mean",
    "egress_robot_coverage_ratio_mean",
    "lease_robot_coverage_ratio_mean",
    "quality_gate_robot_coverage_ratio_mean",
    "egress_monitor_robot_coverage_ratio_mean",
    "rx_mean",
    "loss_ratio_mean",
    "control_delivery_ratio_mean",
    "deadline_miss_ratio_mean",
    "latency_p95_ms_mean",
    "semantic_utility_delivered_mean",
)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--run", action="store_true", help="Run Docker live-bridge jobs before aggregating.")
    parser.add_argument("--keep-going", action="store_true", help="Continue remaining robot counts after a failed job.")
    parser.add_argument("--robot-counts", default="4", help="Comma-separated robot counts, for example 4,8,16.")
    parser.add_argument("--seeds", default="7,13,29")
    parser.add_argument("--scenario-prefix", default="ros2_live_bridge_t3_dynamic_objective_transition")
    parser.add_argument("--output-dir", type=Path, default=Path("results_ros2_live_bridge"))
    parser.add_argument("--bridge-config", default="experiments/ros2_live_bridge_tb4_binding_v1.json")
    parser.add_argument("--rmw", default="rmw_zenoh_cpp")
    parser.add_argument("--policy", default="fleetqox_semantic_contract_budgeted_deadline_first")
    parser.add_argument("--seconds", type=float, default=4.0)
    parser.add_argument("--rate-hz", type=float, default=10.0)
    parser.add_argument("--bridge-max-batches", type=int, default=80)
    parser.add_argument("--transition-segment-s", type=float, default=1.5)
    parser.add_argument("--probe-quota-scale", type=float, default=1.0)
    parser.add_argument("--probe-max-per-robot-per-tick", type=int, default=1)
    parser.add_argument("--control-lease-ack-retransmit", choices=("on", "off"), default="off")
    parser.add_argument("--egress-feedback-control-lease-ack-immediate", action="store_true")
    parser.add_argument("--egress-feedback-control-lease-ack-window-events", type=int, default=0)
    parser.add_argument("--egress-feedback-control-lease-ack-adaptive", action="store_true")
    parser.add_argument("--egress-feedback-control-lease-ack-adaptive-min-events", type=int, default=8)
    parser.add_argument("--egress-feedback-control-lease-ack-adaptive-max-events", type=int, default=48)
    parser.add_argument("--egress-feedback-control-lease-ack-adaptive-success-step", type=int, default=1)
    parser.add_argument("--egress-feedback-control-lease-ack-adaptive-failure-multiplier", type=float, default=2.0)
    parser.add_argument("--egress-feedback-control-lease-ack-adaptive-max-age-ms", type=float, default=120.0)
    parser.add_argument(
        "--egress-feedback-control-lease-ack-adaptive-no-piggyback-first",
        action="store_false",
        dest="egress_feedback_control_lease_ack_adaptive_piggyback_first",
        default=True,
    )
    parser.add_argument(
        "--binding-objective-summary",
        default="autonomy_safety:results_ros2_live_bridge/profile_objective_selector_autonomy_v1_summary.json",
    )
    parser.add_argument(
        "--binding-objective-schedule",
        default="balanced_safety_utility@0,autonomy_safety@1.5,balanced_safety_utility@3",
    )
    parser.add_argument(
        "--summary-json",
        type=Path,
        default=Path("results_ros2_live_bridge/n_robot_qoe_recovery_quota_matrix_summary.json"),
    )
    parser.add_argument(
        "--markdown",
        type=Path,
        default=Path("results_ros2_live_bridge/n_robot_qoe_recovery_quota_matrix_report.md"),
    )
    parser.add_argument("--title", default="ROS 2 N-Robot QoE Recovery Quota Matrix")
    args = parser.parse_args()

    robot_counts = positive_ints(args.robot_counts, "--robot-counts")
    seeds = positive_ints(args.seeds, "--seeds")
    plans = [
        build_matrix_plan(args, robot_count=robot_count, seeds=seeds)
        for robot_count in robot_counts
    ]
    statuses: dict[int, str] = {}
    if args.run:
        for plan in plans:
            status = run_plan(plan.command)
            statuses[plan.robot_count] = status
            if status != "ran" and not args.keep_going:
                break

    summary = aggregate_plans(plans, run_statuses=statuses)
    args.summary_json.parent.mkdir(parents=True, exist_ok=True)
    args.markdown.parent.mkdir(parents=True, exist_ok=True)
    args.summary_json.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n")
    args.markdown.write_text(render_markdown(summary, title=args.title))
    print(
        "ros2-n-robot-qoe-quota-matrix "
        f"robot_counts={','.join(str(item) for item in robot_counts)} "
        f"seeds={','.join(str(item) for item in seeds)} "
        f"summary={args.summary_json} markdown={args.markdown}"
    )
    return 0


class MatrixPlan:
    def __init__(
        self,
        *,
        robot_count: int,
        seeds: list[int],
        scenario: str,
        summary_path: Path,
        markdown_path: Path,
        command: list[str],
    ) -> None:
        self.robot_count = robot_count
        self.seeds = list(seeds)
        self.scenario = scenario
        self.summary_path = summary_path
        self.markdown_path = markdown_path
        self.command = list(command)

    def as_payload(self) -> dict[str, object]:
        return {
            "robot_count": self.robot_count,
            "seeds": self.seeds,
            "scenario": self.scenario,
            "summary_path": str(self.summary_path),
            "markdown_path": str(self.markdown_path),
            "command": self.command,
        }


def build_matrix_plan(args: argparse.Namespace, *, robot_count: int, seeds: list[int]) -> MatrixPlan:
    seed_label = seed_label_for(seeds)
    scenario = f"{args.scenario_prefix}_{robot_count}robot_qoe_recovery_quota_{seed_label}_v1"
    report_stem = f"dynamic_objective_transition_{robot_count}robot_qoe_recovery_quota_{seed_label}"
    summary_path = args.output_dir / f"{report_stem}_summary.json"
    markdown_path = args.output_dir / f"{report_stem}_report.md"
    title = f"ROS 2 Live Dynamic Objective Transition {robot_count}-Robot QoE Recovery Quota {seed_label}"
    command = [
        sys.executable,
        "-m",
        "scripts.run_ros2_docker_live_bridge",
        "--run",
        "--analyze",
        "--dynamic-objective-transition-matrix",
        "--scenario",
        scenario,
        "--bridge-config",
        str(args.bridge_config),
        "--rmw",
        str(args.rmw),
        "--policy",
        str(args.policy),
        "--seeds",
        ",".join(str(item) for item in seeds),
        "--robot-count",
        str(robot_count),
        "--transition-profile",
        "wifi",
        "--transition-profile",
        "wan",
        "--transition-profile",
        "roaming",
        "--transition-segment-s",
        str(args.transition_segment_s),
        "--seconds",
        str(args.seconds),
        "--rate-hz",
        str(args.rate_hz),
        "--bridge-max-batches",
        str(args.bridge_max_batches),
        "--binding-objective-summary",
        str(args.binding_objective_summary),
        "--binding-objective-schedule",
        str(args.binding_objective_schedule),
        "--egress-feedback",
        "--local-feedback",
        "--quality-feedback",
        "--quality-gate-identity-mode",
        "wrapper",
        "--quality-message-mode",
        "typed",
        "--projection-quality-message-mode",
        "typed",
        "--projection-quality-delivery-mode",
        "wrapper",
        "--transport-volatility-probe-quota-scale",
        str(args.probe_quota_scale),
        "--transport-volatility-probe-max-per-robot-per-tick",
        str(args.probe_max_per_robot_per_tick),
        "--control-lease-ack-retransmit",
        str(args.control_lease_ack_retransmit),
        "--egress-feedback-control-lease-ack-window-events",
        str(args.egress_feedback_control_lease_ack_window_events),
        "--egress-feedback-control-lease-ack-adaptive-min-events",
        str(args.egress_feedback_control_lease_ack_adaptive_min_events),
        "--egress-feedback-control-lease-ack-adaptive-max-events",
        str(args.egress_feedback_control_lease_ack_adaptive_max_events),
        "--egress-feedback-control-lease-ack-adaptive-success-step",
        str(args.egress_feedback_control_lease_ack_adaptive_success_step),
        "--egress-feedback-control-lease-ack-adaptive-failure-multiplier",
        str(args.egress_feedback_control_lease_ack_adaptive_failure_multiplier),
        "--egress-feedback-control-lease-ack-adaptive-max-age-ms",
        str(args.egress_feedback_control_lease_ack_adaptive_max_age_ms),
        "--transition-summary-json",
        str(summary_path),
        "--transition-markdown",
        str(markdown_path),
        "--title",
        title,
    ]
    if args.egress_feedback_control_lease_ack_immediate:
        command.append("--egress-feedback-control-lease-ack-immediate")
    if args.egress_feedback_control_lease_ack_adaptive:
        command.append("--egress-feedback-control-lease-ack-adaptive")
    if not args.egress_feedback_control_lease_ack_adaptive_piggyback_first:
        command.append("--egress-feedback-control-lease-ack-adaptive-no-piggyback-first")
    return MatrixPlan(
        robot_count=robot_count,
        seeds=seeds,
        scenario=scenario,
        summary_path=summary_path,
        markdown_path=markdown_path,
        command=command,
    )


def run_plan(command: list[str]) -> str:
    result = subprocess.run(command, check=False)
    return "ran" if result.returncode == 0 else f"failed:{result.returncode}"


def aggregate_plans(
    plans: Iterable[MatrixPlan],
    *,
    run_statuses: Mapping[int, str] | None = None,
) -> dict[str, object]:
    rows = []
    for plan in plans:
        run_status = "" if run_statuses is None else str(run_statuses.get(plan.robot_count, "not_run"))
        rows.append(aggregate_plan(plan, run_status=run_status))
    rows = sorted(rows, key=lambda row: int(row.get("robot_count", 0)))
    return {
        "schema_version": "fleetrmw.ros2_n_robot_qoe_recovery_quota_matrix.v1",
        "plans": [plan.as_payload() for plan in plans],
        "rows": rows,
        "best_robot_count": best_robot_count(rows),
    }


def aggregate_plan(plan: MatrixPlan, *, run_status: str = "") -> dict[str, object]:
    row: dict[str, object] = {
        "robot_count": plan.robot_count,
        "seeds": plan.seeds,
        "scenario": plan.scenario,
        "summary_path": str(plan.summary_path),
        "markdown_path": str(plan.markdown_path),
        "run_status": run_status,
    }
    if not plan.summary_path.exists():
        row["status"] = "missing_summary"
        return row
    summary = json.loads(plan.summary_path.read_text())
    policy = first_policy(summary)
    if policy is None:
        row["status"] = "missing_policy"
        return row
    row["status"] = "summarized"
    row["policy"] = str(policy.get("policy", ""))
    for field in SUMMARY_FIELDS:
        row[field] = number(policy.get(field, 0.0))
    row["quality_gate_robots_observed"] = list(policy.get("quality_gate_robots_observed", []))
    row["comparison_rows"] = per_seed_rows(summary)
    invalid_reasons = invalid_infrastructure_reasons(row)
    if invalid_reasons:
        row["status"] = "invalid_infrastructure"
        row["invalid_reasons"] = invalid_reasons
    return row


def per_seed_rows(summary: Mapping[str, object]) -> list[dict[str, object]]:
    rows = []
    for row in summary.get("comparison_rows", []):
        if not isinstance(row, Mapping):
            continue
        rows.append(
            {
                "seed": int(row.get("seed", 0)),
                "status": str(row.get("status", "")),
                "robot_count": number(row.get("robot_count", 0.0)),
                "rx": number(row.get("rx", 0.0)),
                "control_delivery_ratio": number(row.get("control_delivery_ratio", 0.0)),
                "deadline_miss_ratio": number(row.get("deadline_miss_ratio", 0.0)),
                "latency_p95_ms": number(row.get("latency_p95_ms", 0.0)),
                "per_robot_budget_pass": bool(row.get("per_robot_budget_pass", False)),
                "per_robot_min_control_delivery_ratio": number(
                    row.get("per_robot_min_control_delivery_ratio", 0.0)
                ),
                "per_robot_max_deadline_miss_ratio": number(
                    row.get("per_robot_max_deadline_miss_ratio", 0.0)
                ),
                "quality_gate_robot_coverage_ratio": number(
                    row.get("quality_gate_robot_coverage_ratio", 0.0)
                ),
            }
        )
    return rows


def render_markdown(summary: Mapping[str, object], *, title: str) -> str:
    rows = [row for row in summary.get("rows", []) if isinstance(row, Mapping)]
    lines = [
        f"# {title}",
        "",
        "## Summary",
        "",
        table(
            [
                "robots",
                "status",
                "runs",
                "budget",
                "quality cov",
                "ctrl",
                "deadline",
                "worst deadline",
                "p95 ms",
                "rx",
                "utility",
            ],
            [summary_table_row(row) for row in rows],
        ),
        "",
        "## Per-Seed Rows",
        "",
        table(
            [
                "robots",
                "seed",
                "pass",
                "quality cov",
                "min ctrl",
                "max deadline",
                "ctrl",
                "deadline",
                "p95 ms",
                "rx",
            ],
            [
                seed_table_row(row, seed_row)
                for row in rows
                for seed_row in row.get("comparison_rows", [])
                if isinstance(seed_row, Mapping)
            ],
        ),
        "",
        "## Notes",
        "",
        "- Budget pass and quality coverage must be read together: a run that keeps control safe by suppressing state/perception QoE is not a complete FleetRMW result.",
        "- This report is an orchestration layer over `scripts.run_ros2_docker_live_bridge`; each row links back to its own summary and Markdown artifacts.",
        "- The next RMW step should use repeated N-robot rows that keep hard budget pass high while preserving quality-gate coverage.",
        "",
    ]
    return "\n".join(lines)


def summary_table_row(row: Mapping[str, object]) -> list[str]:
    return [
        str(int(row.get("robot_count", 0))),
        str(row.get("status", "")),
        fmt(row.get("runs", 0.0)),
        fmt(row.get("per_robot_budget_pass_ratio", 0.0)),
        fmt(row.get("quality_gate_robot_coverage_ratio_mean", 0.0)),
        fmt(row.get("control_delivery_ratio_mean", 0.0)),
        fmt(row.get("deadline_miss_ratio_mean", 0.0)),
        fmt(row.get("per_robot_max_deadline_miss_ratio_mean", 0.0)),
        fmt(row.get("latency_p95_ms_mean", 0.0)),
        fmt(row.get("rx_mean", 0.0)),
        fmt(row.get("semantic_utility_delivered_mean", 0.0)),
    ]


def seed_table_row(row: Mapping[str, object], seed_row: Mapping[str, object]) -> list[str]:
    return [
        str(int(row.get("robot_count", 0))),
        str(int(seed_row.get("seed", 0))),
        "yes" if seed_row.get("per_robot_budget_pass", False) else "no",
        fmt(seed_row.get("quality_gate_robot_coverage_ratio", 0.0)),
        fmt(seed_row.get("per_robot_min_control_delivery_ratio", 0.0)),
        fmt(seed_row.get("per_robot_max_deadline_miss_ratio", 0.0)),
        fmt(seed_row.get("control_delivery_ratio", 0.0)),
        fmt(seed_row.get("deadline_miss_ratio", 0.0)),
        fmt(seed_row.get("latency_p95_ms", 0.0)),
        fmt(seed_row.get("rx", 0.0)),
    ]


def best_robot_count(rows: Iterable[Mapping[str, object]]) -> int | None:
    candidates = [
        row for row in rows
        if str(row.get("status", "")) == "summarized"
        and number(row.get("per_robot_budget_pass_ratio", 0.0)) >= 1.0
        and number(row.get("quality_gate_robot_coverage_ratio_mean", 0.0)) >= 1.0
    ]
    if not candidates:
        return None
    return max(int(row.get("robot_count", 0)) for row in candidates)


def invalid_infrastructure_reasons(row: Mapping[str, object]) -> list[str]:
    runs = number(row.get("runs", 0.0))
    if runs <= 0:
        return []
    reasons: list[str] = []
    if (
        number(row.get("rx_mean", 0.0)) <= 0.0
        and number(row.get("control_delivery_ratio_mean", 0.0)) <= 0.0
    ):
        reasons.append("no_packets_received")
    if (
        number(row.get("decision_robot_coverage_ratio_mean", 0.0)) <= 0.0
        and number(row.get("received_robot_coverage_ratio_mean", 0.0)) <= 0.0
    ):
        reasons.append("no_ros_robot_coverage")
    seed_rows = [
        seed_row for seed_row in row.get("comparison_rows", [])
        if isinstance(seed_row, Mapping)
    ]
    if seed_rows and all(number(seed_row.get("rx", 0.0)) <= 0.0 for seed_row in seed_rows):
        reasons.append("all_seed_rows_zero_rx")
    return reasons


def first_policy(summary: Mapping[str, object]) -> Mapping[str, object] | None:
    policies = summary.get("policies", [])
    if not isinstance(policies, list) or not policies:
        return None
    policy = policies[0]
    return policy if isinstance(policy, Mapping) else None


def positive_ints(raw: str, label: str) -> list[int]:
    values = parse_ints(raw, label)
    if not values or any(value <= 0 for value in values):
        raise ValueError(f"{label} must contain positive integers")
    return values


def seed_label_for(seeds: list[int]) -> str:
    if len(seeds) == 1:
        return f"seed_{seeds[0]}"
    return f"{len(seeds)}seed"


def table(headers: list[str], rows: list[list[str]]) -> str:
    lines = [
        "| " + " | ".join(headers) + " |",
        "| " + " | ".join("---" for _ in headers) + " |",
    ]
    lines.extend("| " + " | ".join(row) + " |" for row in rows)
    return "\n".join(lines)


def fmt(value: object) -> str:
    number_value = number(value)
    if abs(number_value) >= 100:
        return f"{number_value:.2f}"
    return f"{number_value:.4f}"


def number(value: object) -> float:
    try:
        return float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return 0.0


if __name__ == "__main__":
    raise SystemExit(main())

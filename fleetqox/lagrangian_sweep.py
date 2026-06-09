"""Parameter sweeps for the FleetQoX Lagrangian controller."""

from __future__ import annotations

import json
import math
from dataclasses import asdict
from pathlib import Path
from statistics import mean, stdev
from typing import Iterable

from .control_plane import (
    LagrangianAdmissionConfig,
    LagrangianRiskPredictiveAdmissionController,
    PredictiveAdmissionController,
    RiskConstrainedPredictiveAdmissionController,
)
from .fleet_scale import capacity_for_robots
from .scheduler import CausalSemanticDeadlineScheduler
from .simulator import BenchmarkResult, PolicyCallable, run_policy_benchmark_matrix


SWEEP_METRICS = [
    "utility_score",
    "control_deadline_miss_ratio",
    "qoe_delivery_ratio",
    "stale_state_ratio",
    "defer_ratio",
    "drop_ratio",
    "degraded_ratio",
    "compacted_ratio",
    "bytes_sent",
    "sent",
]

PARETO_OBJECTIVES = {
    "utility_score_mean": "max",
    "qoe_delivery_ratio_mean": "max",
    "control_deadline_miss_ratio_mean": "min",
    "stale_state_ratio_mean": "min",
    "defer_ratio_mean": "min",
    "drop_ratio_mean": "min",
}


def build_lagrangian_configs(
    *,
    deadline_risk_budgets: Iterable[float],
    initial_deadline_lambdas: Iterable[float],
    risk_barrier_starts: Iterable[float],
    risk_barrier_scales: Iterable[float],
    deadline_drop_risks: Iterable[float] = (0.45,),
) -> list[tuple[str, LagrangianAdmissionConfig]]:
    configs = []
    index = 0
    for budget in deadline_risk_budgets:
        for deadline_lambda in initial_deadline_lambdas:
            for barrier_start in risk_barrier_starts:
                for barrier_scale in risk_barrier_scales:
                    for drop_risk in deadline_drop_risks:
                        config_id = f"lag_{index:03d}"
                        configs.append(
                            (
                                config_id,
                                LagrangianAdmissionConfig(
                                    deadline_risk_budget=budget,
                                    initial_deadline_lambda=deadline_lambda,
                                    risk_barrier_start=barrier_start,
                                    risk_barrier_scale=barrier_scale,
                                    deadline_drop_risk=drop_risk,
                                ),
                            )
                        )
                        index += 1
    return configs


def run_lagrangian_sweep(
    *,
    robot_counts: Iterable[int],
    seeds: Iterable[int],
    seconds: int,
    configs: Iterable[tuple[str, LagrangianAdmissionConfig]],
    capacity_mode: str = "shared_cell",
    base_capacity: int = 180_000,
    per_robot_capacity: int = 2_800,
    knee_robots: int = 25,
    include_baselines: bool = True,
) -> list[dict[str, object]]:
    config_list = list(configs)
    records: list[dict[str, object]] = []
    for robots in robot_counts:
        capacity = capacity_for_robots(
            robots,
            mode=capacity_mode,
            base_capacity=base_capacity,
            per_robot_capacity=per_robot_capacity,
            knee_robots=knee_robots,
        )
        for seed in seeds:
            policies = _policies_for_run(config_list, include_baselines)
            results = run_policy_benchmark_matrix(
                [(candidate_id, policy) for candidate_id, policy, _ in policies],
                robots=robots,
                seconds=seconds,
                seed=seed,
                capacity_bytes_per_second=capacity,
            )
            metadata = {candidate_id: params for candidate_id, _, params in policies}
            records.extend(
                _record_from_result(
                    result,
                    seed=seed,
                    seconds=seconds,
                    capacity=capacity,
                    params=metadata[result.name],
                )
                for result in results
            )
    return records


def summarize_lagrangian_sweep(
    records: Iterable[dict[str, object]],
    *,
    control_miss_target: float = 0.05,
) -> dict[str, object]:
    rows = list(records)
    grouped: dict[str, list[dict[str, object]]] = {}
    for row in rows:
        grouped.setdefault(str(row.get("candidate_id", "")), []).append(row)

    candidates = []
    for candidate_id, group in grouped.items():
        first = group[0]
        summary: dict[str, object] = {
            "candidate_id": candidate_id,
            "policy": first.get("policy", candidate_id),
            "runs": len(group),
            "params": first.get("params", {}),
            "robots": sorted({int(row.get("robots", 0)) for row in group}),
            "seeds": sorted({int(row.get("seed", 0)) for row in group}),
        }
        for metric in SWEEP_METRICS:
            summary.update(_describe_metric(metric, [_numeric(row.get(metric, 0.0)) for row in group]))
        summary["constraint_satisfied"] = (
            _numeric(summary.get("control_deadline_miss_ratio_mean", 0.0))
            <= control_miss_target
        )
        summary["sweep_score"] = _sweep_score(summary)
        candidates.append(summary)

    frontier = pareto_frontier(candidates)
    frontier_ids = {str(row["candidate_id"]) for row in frontier}
    for candidate in candidates:
        candidate["pareto_frontier"] = str(candidate["candidate_id"]) in frontier_ids

    ranking = sorted(
        candidates,
        key=lambda row: (
            0 if row.get("constraint_satisfied") else 1,
            0 if row.get("pareto_frontier") else 1,
            -_numeric(row.get("sweep_score", 0.0)),
            str(row.get("candidate_id", "")),
        ),
    )
    return {
        "records": len(rows),
        "control_miss_target": control_miss_target,
        "candidates": candidates,
        "ranking": ranking,
        "pareto_frontier": [row["candidate_id"] for row in frontier],
        "objectives": PARETO_OBJECTIVES,
    }


def pareto_frontier(
    candidates: Iterable[dict[str, object]],
    objectives: dict[str, str] | None = None,
) -> list[dict[str, object]]:
    objective_map = objectives or PARETO_OBJECTIVES
    rows = list(candidates)
    frontier = []
    for candidate in rows:
        dominated = any(
            dominates(other, candidate, objective_map)
            for other in rows
            if other is not candidate
        )
        if not dominated:
            frontier.append(candidate)
    return sorted(
        frontier,
        key=lambda row: (
            -_numeric(row.get("sweep_score", 0.0)),
            str(row.get("candidate_id", "")),
        ),
    )


def dominates(
    left: dict[str, object],
    right: dict[str, object],
    objectives: dict[str, str] | None = None,
    *,
    tolerance: float = 1e-12,
) -> bool:
    objective_map = objectives or PARETO_OBJECTIVES
    strictly_better = False
    for metric, direction in objective_map.items():
        left_value = _numeric(left.get(metric, 0.0))
        right_value = _numeric(right.get(metric, 0.0))
        if direction == "max":
            if left_value + tolerance < right_value:
                return False
            if left_value > right_value + tolerance:
                strictly_better = True
        elif direction == "min":
            if left_value > right_value + tolerance:
                return False
            if left_value + tolerance < right_value:
                strictly_better = True
        else:
            raise ValueError(f"unknown objective direction: {direction}")
    return strictly_better


def write_lagrangian_sweep_records(records: Iterable[dict[str, object]], output: str | Path) -> None:
    Path(output).parent.mkdir(parents=True, exist_ok=True)
    with Path(output).open("w", encoding="utf-8") as handle:
        for record in records:
            handle.write(json.dumps(record, sort_keys=True) + "\n")


def write_lagrangian_sweep_summary(summary: dict[str, object], output: str | Path) -> None:
    Path(output).parent.mkdir(parents=True, exist_ok=True)
    Path(output).write_text(json.dumps(summary, indent=2, sort_keys=True), encoding="utf-8")


def write_lagrangian_sweep_markdown(
    summary: dict[str, object],
    output: str | Path,
    *,
    title: str,
    records_path: str | Path | None = None,
    summary_path: str | Path | None = None,
) -> None:
    Path(output).parent.mkdir(parents=True, exist_ok=True)
    Path(output).write_text(
        render_lagrangian_sweep_markdown(
            summary,
            title=title,
            records_path=records_path,
            summary_path=summary_path,
        ),
        encoding="utf-8",
    )


def render_lagrangian_sweep_markdown(
    summary: dict[str, object],
    *,
    title: str = "Lagrangian Parameter Sweep",
    records_path: str | Path | None = None,
    summary_path: str | Path | None = None,
) -> str:
    ranking = list(summary.get("ranking", []))
    frontier = ", ".join(f"`{name}`" for name in summary.get("pareto_frontier", [])) or "None"
    lines = [
        f"# {title}",
        "",
        "## Inputs",
        "",
    ]
    if records_path:
        lines.append(f"- Records: `{records_path}`")
    if summary_path:
        lines.append(f"- Summary: `{summary_path}`")
    lines.extend(
        [
            f"- Metric rows: `{summary.get('records', 0)}`",
            f"- Control miss target: `{_format(_numeric(summary.get('control_miss_target', 0.0)))}`",
            "",
            "## Ranking",
            "",
            _markdown_table(
                [
                    "candidate",
                    "policy",
                    "runs",
                    "target",
                    "pareto",
                    "score",
                    "utility",
                    "control miss",
                    "qoe",
                    "stale",
                    "defer",
                    "drop",
                    "compact",
                    "params",
                ],
                [_summary_table_row(row) for row in ranking],
            ),
            "",
            "## Pareto Frontier",
            "",
            f"- Non-dominated candidates: {frontier}.",
            "",
            "## Interpretation",
            "",
        ]
    )
    lines.extend(f"- {item}" for item in build_sweep_observations(summary))
    lines.append("")
    return "\n".join(lines)


def build_sweep_observations(summary: dict[str, object]) -> list[str]:
    ranking = list(summary.get("ranking", []))
    if not ranking:
        return ["No sweep candidates were available."]

    observations = []
    best = ranking[0]
    observations.append(
        "Best ranked candidate: "
        f"`{best['candidate_id']}` with score `{_format(_numeric(best['sweep_score']))}` "
        f"and control miss `{_format(_numeric(best['control_deadline_miss_ratio_mean']))}`."
    )

    lagrangian = [row for row in ranking if str(row.get("policy", "")).startswith("fleetqox_lagrangian")]
    if lagrangian:
        best_lagrangian = lagrangian[0]
        observations.append(
            "Best Lagrangian candidate: "
            f"`{best_lagrangian['candidate_id']}` with params "
            f"`{_params_short(best_lagrangian.get('params', {}))}`."
        )

    target_hits = [row for row in ranking if row.get("constraint_satisfied")]
    observations.append(
        f"`{len(target_hits)}` of `{len(ranking)}` candidates satisfy the control miss target."
    )
    drop_groups = _group_lagrangian_by_drop_risk(ranking)
    if drop_groups:
        best_drop = max(drop_groups, key=lambda row: _numeric(row["score_mean"]))
        observations.append(
            "Risk-reset threshold signal: "
            f"`deadline_drop_risk={_format(_numeric(best_drop['deadline_drop_risk']))}` "
            f"has the best mean Lagrangian score `{_format(_numeric(best_drop['score_mean']))}` "
            f"with control miss `{_format(_numeric(best_drop['control_miss_mean']))}`."
        )
    return observations


def _group_lagrangian_by_drop_risk(rows: list[dict[str, object]]) -> list[dict[str, object]]:
    groups: dict[float, list[dict[str, object]]] = {}
    for row in rows:
        params = row.get("params", {})
        if not isinstance(params, dict) or "deadline_drop_risk" not in params:
            continue
        groups.setdefault(_numeric(params["deadline_drop_risk"]), []).append(row)
    grouped = []
    for drop_risk, group in sorted(groups.items()):
        grouped.append(
            {
                "deadline_drop_risk": drop_risk,
                "score_mean": mean(_numeric(row.get("sweep_score", 0.0)) for row in group),
                "control_miss_mean": mean(
                    _numeric(row.get("control_deadline_miss_ratio_mean", 0.0))
                    for row in group
                ),
            }
        )
    return grouped


def _policies_for_run(
    configs: list[tuple[str, LagrangianAdmissionConfig]],
    include_baselines: bool,
) -> list[tuple[str, PolicyCallable, dict[str, object]]]:
    policies: list[tuple[str, PolicyCallable, dict[str, object]]] = []
    if include_baselines:
        policies.extend(
            [
                ("fleetqox_csds", CausalSemanticDeadlineScheduler().schedule, {}),
                ("fleetqox_predictive", PredictiveAdmissionController().schedule, {}),
                (
                    "fleetqox_predictive_guarded",
                    RiskConstrainedPredictiveAdmissionController().schedule,
                    {},
                ),
            ]
        )
    for config_id, config in configs:
        controller = LagrangianRiskPredictiveAdmissionController(config=config)
        policies.append(
            (
                config_id,
                controller.schedule,
                asdict(config),
            )
        )
    return policies


def _record_from_result(
    result: BenchmarkResult,
    *,
    seed: int,
    seconds: int,
    capacity: int,
    params: dict[str, object],
) -> dict[str, object]:
    events = max(1, result.sent + result.dropped + result.deferred)
    is_lagrangian = result.name.startswith("lag_")
    return {
        "kind": "lagrangian_sweep_result",
        "candidate_id": result.name,
        "policy": "fleetqox_lagrangian" if is_lagrangian else result.name,
        "params": params,
        "robots": result.robots,
        "seed": seed,
        "seconds": seconds,
        "ticks": result.ticks,
        "capacity_bytes_per_second": capacity,
        "sent": result.sent,
        "dropped": result.dropped,
        "deferred": result.deferred,
        "degraded": result.degraded,
        "compacted": result.compacted,
        "bytes_sent": result.bytes_sent,
        "control_deadline_miss_ratio": result.control_deadline_miss_ratio,
        "stale_state_ratio": result.stale_state_ratio,
        "qoe_delivery_ratio": result.qoe_delivery_ratio,
        "utility_score": result.utility_score,
        "defer_ratio": result.deferred / events,
        "drop_ratio": result.dropped / events,
        "degraded_ratio": result.degraded / events,
        "compacted_ratio": result.compacted / events,
    }


def _sweep_score(row: dict[str, object]) -> float:
    utility = _numeric(row.get("utility_score_mean", 0.0))
    qoe = _numeric(row.get("qoe_delivery_ratio_mean", 0.0))
    control_miss = _numeric(row.get("control_deadline_miss_ratio_mean", 0.0))
    stale = _numeric(row.get("stale_state_ratio_mean", 0.0))
    defer = _numeric(row.get("defer_ratio_mean", 0.0))
    drop = _numeric(row.get("drop_ratio_mean", 0.0))
    compact = _numeric(row.get("compacted_ratio_mean", 0.0))
    return utility + 2.0 * qoe + 0.4 * compact - 8.0 * control_miss - 2.0 * stale - defer - drop


def _describe_metric(metric: str, values: list[float]) -> dict[str, object]:
    values = [value for value in values if math.isfinite(value)]
    if not values:
        return {
            f"{metric}_mean": 0.0,
            f"{metric}_min": 0.0,
            f"{metric}_max": 0.0,
            f"{metric}_stdev": 0.0,
            f"{metric}_ci95": 0.0,
        }
    deviation = stdev(values) if len(values) > 1 else 0.0
    return {
        f"{metric}_mean": mean(values),
        f"{metric}_min": min(values),
        f"{metric}_max": max(values),
        f"{metric}_stdev": deviation,
        f"{metric}_ci95": 1.96 * deviation / math.sqrt(len(values)) if len(values) > 1 else 0.0,
    }


def _summary_table_row(row: dict[str, object]) -> dict[str, object]:
    return {
        "candidate": f"`{row.get('candidate_id', '')}`",
        "policy": f"`{row.get('policy', '')}`",
        "runs": row.get("runs", 0),
        "target": "yes" if row.get("constraint_satisfied") else "no",
        "pareto": "yes" if row.get("pareto_frontier") else "no",
        "score": _format(_numeric(row.get("sweep_score", 0.0))),
        "utility": _mean_ci(row, "utility_score"),
        "control miss": _mean_ci(row, "control_deadline_miss_ratio"),
        "qoe": _mean_ci(row, "qoe_delivery_ratio"),
        "stale": _mean_ci(row, "stale_state_ratio"),
        "defer": _mean_ci(row, "defer_ratio"),
        "drop": _mean_ci(row, "drop_ratio"),
        "compact": _mean_ci(row, "compacted_ratio"),
        "params": f"`{_params_short(row.get('params', {}))}`",
    }


def _mean_ci(row: dict[str, object], metric: str) -> str:
    value = _numeric(row.get(f"{metric}_mean", 0.0))
    ci95 = _numeric(row.get(f"{metric}_ci95", 0.0))
    if int(row.get("runs", 0)) <= 1:
        return _format(value)
    return f"{_format(value)} +/- {_format(ci95)}"


def _params_short(params: object) -> str:
    if not isinstance(params, dict) or not params:
        return "-"
    keys = [
        "deadline_risk_budget",
        "initial_deadline_lambda",
        "risk_barrier_start",
        "risk_barrier_scale",
        "deadline_drop_risk",
    ]
    return ", ".join(f"{key}={_format(_numeric(params.get(key, 0.0)))}" for key in keys)


def _markdown_table(columns: list[str], rows: list[dict[str, object]]) -> str:
    header = "| " + " | ".join(columns) + " |"
    separator = "| " + " | ".join("---" for _ in columns) + " |"
    body = [
        "| " + " | ".join(str(row.get(column, "")) for column in columns) + " |"
        for row in rows
    ]
    return "\n".join([header, separator, *body])


def _numeric(value: object) -> float:
    if isinstance(value, bool):
        return float(value)
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        try:
            return float(value)
        except ValueError:
            return 0.0
    return 0.0


def _format(value: float) -> str:
    if abs(value) >= 100:
        return f"{value:.1f}"
    if abs(value) >= 10:
        return f"{value:.2f}"
    return f"{value:.4f}"

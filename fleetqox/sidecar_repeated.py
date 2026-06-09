"""Repeated-run summaries for FleetQoX sidecar metrics."""

from __future__ import annotations

import json
import math
from pathlib import Path
from statistics import mean, stdev
from typing import Iterable


SUMMARY_METRICS = [
    "semantic_utility_delivered",
    "control_starvation_events",
    "deadline_miss_ratio",
    "loss_ratio",
    "control_delivery_ratio",
    "control_non_delivery_events",
    "latency_p95_ms",
    "latency_p99_ms",
    "rx",
    "tx",
    "compacted_rx",
    "intent_rx",
    "bytes_rx",
]

PARETO_OBJECTIVES = {
    "semantic_utility_delivered_mean": "max",
    "control_starvation_events_mean": "min",
    "deadline_miss_ratio_mean": "min",
    "loss_ratio_mean": "min",
    "control_delivery_ratio_mean": "max",
    "control_non_delivery_events_mean": "min",
}


def read_sidecar_metric_records(paths: Iterable[str | Path]) -> list[dict[str, object]]:
    """Read sidecar metric JSONL rows from one or more files."""

    records: list[dict[str, object]] = []
    for path in paths:
        with Path(path).open("r", encoding="utf-8") as handle:
            for line_number, line in enumerate(handle, start=1):
                if not line.strip():
                    continue
                record = json.loads(line)
                if "policy" not in record:
                    raise ValueError(f"{path}:{line_number} is missing policy")
                records.append(record)
    return records


def summarize_repeated_sidecar_metrics(
    records: Iterable[dict[str, object]],
) -> dict[str, object]:
    """Summarize repeated sidecar metric rows by policy."""

    rows = list(records)
    grouped: dict[str, list[dict[str, object]]] = {}
    for row in rows:
        grouped.setdefault(str(row.get("policy", "")), []).append(row)

    policies = []
    for policy, policy_rows in grouped.items():
        summary: dict[str, object] = {
            "policy": policy,
            "runs": len(policy_rows),
            "scenarios": sorted({str(row.get("scenario", "")) for row in policy_rows}),
        }
        for metric in SUMMARY_METRICS:
            values = [_numeric(row.get(metric, 0.0)) for row in policy_rows]
            summary.update(_describe_metric(metric, values))
        policies.append(summary)

    frontier = pareto_frontier(policies)
    frontier_names = {str(row["policy"]) for row in frontier}
    for policy in policies:
        policy["pareto_frontier"] = str(policy["policy"]) in frontier_names

    policies = sorted(
        policies,
        key=lambda row: (
            0 if row.get("pareto_frontier") else 1,
            -_numeric(row.get("semantic_utility_delivered_mean", 0.0)),
            _numeric(row.get("control_starvation_events_mean", 0.0)),
            str(row.get("policy", "")),
        ),
    )
    return {
        "records": len(rows),
        "policies": policies,
        "pareto_frontier": [row["policy"] for row in frontier],
        "objectives": PARETO_OBJECTIVES,
    }


def pareto_frontier(
    policies: Iterable[dict[str, object]],
    objectives: dict[str, str] | None = None,
) -> list[dict[str, object]]:
    """Return non-dominated policies for mixed max/min objectives."""

    objective_map = objectives or PARETO_OBJECTIVES
    rows = list(policies)
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
            -_numeric(row.get("semantic_utility_delivered_mean", 0.0)),
            _numeric(row.get("control_starvation_events_mean", 0.0)),
            str(row.get("policy", "")),
        ),
    )


def dominates(
    left: dict[str, object],
    right: dict[str, object],
    objectives: dict[str, str] | None = None,
    *,
    tolerance: float = 1e-12,
) -> bool:
    """Return true when left is at least as good as right and better once."""

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
            raise ValueError(f"unknown Pareto objective direction: {direction}")
    return strictly_better


def render_repeated_markdown_report(
    summary: dict[str, object],
    *,
    title: str = "Sidecar Repeated-Run Statistics",
    metrics_paths: Iterable[str | Path] = (),
) -> str:
    """Render a Markdown report for repeated sidecar metrics."""

    policies = list(summary.get("policies", []))
    frontier = ", ".join(f"`{name}`" for name in summary.get("pareto_frontier", []))
    if not frontier:
        frontier = "None"
    lines = [
        f"# {title}",
        "",
        "## Inputs",
        "",
        f"- Metric rows: `{summary.get('records', 0)}`",
    ]
    for path in metrics_paths:
        lines.append(f"- Metrics: `{path}`")
    lines.extend(
        [
            "",
            "## Policy Summary",
            "",
            _markdown_table(
                [
                    "policy",
                    "runs",
                    "pareto",
                    "utility",
                    "control misses",
                    "deadline miss",
                    "ctrl delivery",
                    "ctrl non-delivery",
                    "loss",
                    "p95 ms",
                    "rx",
                    "compacted rx",
                    "intent rx",
                ],
                [_summary_table_row(row) for row in policies],
            ),
            "",
        ]
    )
    profile_summaries = [
        profile
        for profile in summary.get("profiles", [])
        if isinstance(profile, dict)
    ]
    if profile_summaries:
        lines.extend(["## Profile Summaries", ""])
        for profile in profile_summaries:
            lines.extend(_profile_summary_lines(profile))
            lines.append("")
    lines.extend(
        [
            "## Pareto Frontier",
            "",
            f"- Non-dominated policies: {frontier}.",
            "",
            "## Interpretation",
            "",
        ]
    )
    lines.extend(f"- {item}" for item in build_repeated_observations(summary))
    lines.append("")
    return "\n".join(lines)


def write_repeated_summary_json(summary: dict[str, object], output: str | Path) -> None:
    Path(output).parent.mkdir(parents=True, exist_ok=True)
    Path(output).write_text(json.dumps(summary, indent=2, sort_keys=True), encoding="utf-8")


def write_repeated_markdown_report(
    summary: dict[str, object],
    output: str | Path,
    *,
    title: str,
    metrics_paths: Iterable[str | Path] = (),
) -> None:
    Path(output).parent.mkdir(parents=True, exist_ok=True)
    Path(output).write_text(
        render_repeated_markdown_report(
            summary,
            title=title,
            metrics_paths=metrics_paths,
        ),
        encoding="utf-8",
    )


def build_repeated_observations(summary: dict[str, object]) -> list[str]:
    policies = list(summary.get("policies", []))
    if not policies:
        return ["No policy metrics were available."]

    observations = []
    best_utility = max(
        policies,
        key=lambda row: _numeric(row.get("semantic_utility_delivered_mean", 0.0)),
    )
    observations.append(
        "Highest mean utility: "
        f"`{best_utility['policy']}` at "
        f"`{_format(_numeric(best_utility['semantic_utility_delivered_mean']))}`."
    )

    safe_rows = [
        row
        for row in policies
        if _numeric(row.get("control_starvation_events_mean", 0.0)) == 0.0
        and _numeric(row.get("deadline_miss_ratio_mean", 0.0)) == 0.0
        and _numeric(row.get("control_delivery_ratio_mean", 0.0)) > 0.0
    ]
    if safe_rows:
        safest = max(
            safe_rows,
            key=lambda row: _numeric(row.get("semantic_utility_delivered_mean", 0.0)),
        )
        observations.append(
            "Best zero-measured-miss policy: "
            f"`{safest['policy']}` with utility "
            f"`{_format(_numeric(safest['semantic_utility_delivered_mean']))}`."
        )

    if any(int(row.get("runs", 0)) < 3 for row in policies):
        observations.append(
            "Some policies have fewer than three runs; their confidence intervals "
            "are only a smoke-test signal, not statistical evidence."
        )

    dominated = [row for row in policies if not row.get("pareto_frontier")]
    if dominated:
        names = ", ".join(f"`{row['policy']}`" for row in dominated)
        observations.append(f"Dominated policies in the current evidence set: {names}.")

    return observations


def _profile_summary_lines(profile: dict[str, object]) -> list[str]:
    policies = list(profile.get("policies", []))
    frontier = ", ".join(f"`{name}`" for name in profile.get("pareto_frontier", []))
    if not frontier:
        frontier = "None"
    lines = [
        f"### `{profile.get('profile', 'unknown')}`",
        "",
        f"- Metric rows: `{profile.get('records', 0)}`",
    ]
    config = profile.get("config", {})
    if isinstance(config, dict) and config:
        lines.append(f"- Netem: {_format_profile_config(config)}")
    lines.extend(
        [
            "",
            _markdown_table(
                [
                    "policy",
                    "runs",
                    "pareto",
                    "utility",
                    "control misses",
                    "deadline miss",
                    "ctrl delivery",
                    "ctrl non-delivery",
                    "loss",
                    "p95 ms",
                    "rx",
                    "compacted rx",
                    "intent rx",
                ],
                [_summary_table_row(row) for row in policies],
            ),
            "",
            f"- Non-dominated policies in this profile: {frontier}.",
        ]
    )
    return lines


def _describe_metric(metric: str, values: list[float]) -> dict[str, object]:
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
        "policy": f"`{row.get('policy', '')}`",
        "runs": row.get("runs", 0),
        "pareto": "yes" if row.get("pareto_frontier") else "no",
        "utility": _mean_ci(row, "semantic_utility_delivered"),
        "control misses": _mean_ci(row, "control_starvation_events"),
        "deadline miss": _mean_ci(row, "deadline_miss_ratio"),
        "ctrl delivery": _mean_ci(row, "control_delivery_ratio"),
        "ctrl non-delivery": _mean_ci(row, "control_non_delivery_events"),
        "loss": _mean_ci(row, "loss_ratio"),
        "p95 ms": _mean_ci(row, "latency_p95_ms"),
        "rx": _mean_ci(row, "rx"),
        "compacted rx": _mean_ci(row, "compacted_rx"),
        "intent rx": _mean_ci(row, "intent_rx"),
    }


def _mean_ci(row: dict[str, object], metric: str) -> str:
    value = _numeric(row.get(f"{metric}_mean", 0.0))
    ci95 = _numeric(row.get(f"{metric}_ci95", 0.0))
    if int(row.get("runs", 0)) <= 1:
        return _format(value)
    return f"{_format(value)} +/- {_format(ci95)}"


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


def _format_profile_config(config: dict[str, object]) -> str:
    fields = [
        ("capacity_bytes_per_second", "B/s"),
        ("delay_ms", "ms delay"),
        ("jitter_ms", "ms jitter"),
        ("loss_percent", "% loss"),
        ("rate_mbit", "mbit"),
    ]
    parts = []
    for key, suffix in fields:
        if key in config:
            parts.append(f"`{_format(_numeric(config[key]))} {suffix}`")
    return ", ".join(parts) if parts else "custom"

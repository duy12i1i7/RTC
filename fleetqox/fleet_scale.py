"""Fleet-scale benchmark matrix helpers.

This module keeps the local simulator separate from ROS/netem execution while
using comparable QoS/QoE metrics. It is meant to expose scaling pain points
before the full non-DDS RMW exists.
"""

from __future__ import annotations

import csv
import json
import math
from pathlib import Path
from statistics import mean
from typing import Iterable

from .simulator import BenchmarkResult, run_benchmark


FLEET_SUMMARY_COLUMNS = [
    "robots",
    "policy",
    "runs",
    "fleet_score",
    "control_deadline_miss_ratio_mean",
    "stale_state_ratio_mean",
    "qoe_delivery_ratio_mean",
    "utility_score_mean",
    "defer_ratio_mean",
    "drop_ratio_mean",
    "degraded_ratio_mean",
    "compacted_ratio_mean",
    "bytes_sent_mean",
    "capacity_bytes_per_second_mean",
]


def capacity_for_robots(
    robots: int,
    *,
    mode: str = "shared_cell",
    base_capacity: int = 180_000,
    per_robot_capacity: int = 2_800,
    knee_robots: int = 25,
) -> int:
    """Return a synthetic shared-link capacity for a fleet size.

    `shared_cell` is intentionally sublinear after the knee to emulate a Wi-Fi
    cell, WAN bottleneck, or roaming access segment where robot demand grows
    faster than useful airtime.
    """

    if robots <= 0:
        raise ValueError("robots must be positive")
    if mode == "linear":
        return max(base_capacity, robots * per_robot_capacity)
    if mode == "fixed":
        return base_capacity
    if mode != "shared_cell":
        raise ValueError(f"unknown capacity mode: {mode}")

    below_knee = min(robots, knee_robots)
    above_knee = max(0, robots - knee_robots)
    return int(
        base_capacity
        + below_knee * per_robot_capacity
        + above_knee * per_robot_capacity * 0.35
    )


def run_fleet_scale_matrix(
    robot_counts: Iterable[int],
    seeds: Iterable[int],
    *,
    seconds: int = 30,
    capacity_mode: str = "shared_cell",
    base_capacity: int = 180_000,
    per_robot_capacity: int = 2_800,
    knee_robots: int = 25,
) -> list[dict[str, object]]:
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
            results = run_benchmark(
                robots=robots,
                seconds=seconds,
                seed=seed,
                capacity_bytes_per_second=capacity,
            )
            records.extend(
                _record_from_result(result, seed=seed, seconds=seconds, capacity=capacity)
                for result in results
            )
    return records


def summarize_fleet_scale(records: Iterable[dict[str, object]]) -> dict[str, object]:
    groups: dict[tuple[int, str], list[dict[str, object]]] = {}
    for record in records:
        key = (int(record.get("robots", 0)), str(record.get("policy", "")))
        groups.setdefault(key, []).append(record)

    rows = []
    for (robots, policy), group in sorted(groups.items()):
        row = {
            "robots": robots,
            "policy": policy,
            "runs": len(group),
            "control_deadline_miss_ratio_mean": _mean(group, "control_deadline_miss_ratio"),
            "stale_state_ratio_mean": _mean(group, "stale_state_ratio"),
            "qoe_delivery_ratio_mean": _mean(group, "qoe_delivery_ratio"),
            "utility_score_mean": _mean(group, "utility_score"),
            "defer_ratio_mean": _mean(group, "defer_ratio"),
            "drop_ratio_mean": _mean(group, "drop_ratio"),
            "degraded_ratio_mean": _mean(group, "degraded_ratio"),
            "compacted_ratio_mean": _mean(group, "compacted_ratio"),
            "bytes_sent_mean": _mean(group, "bytes_sent"),
            "capacity_bytes_per_second_mean": _mean(group, "capacity_bytes_per_second"),
        }
        row["fleet_score"] = _fleet_score(row)
        rows.append(row)

    ranking = sorted(rows, key=lambda row: (int(row["robots"]), -float(row["fleet_score"])))
    return {
        "groups": rows,
        "ranking": ranking,
        "winners": _winners_by_robot_count(ranking),
        "observations": build_fleet_scale_observations(ranking),
    }


def write_fleet_records_jsonl(records: Iterable[dict[str, object]], output: str | Path) -> None:
    Path(output).parent.mkdir(parents=True, exist_ok=True)
    with Path(output).open("w", encoding="utf-8") as handle:
        for record in records:
            handle.write(json.dumps(record, sort_keys=True) + "\n")


def write_fleet_summary_json(summary: dict[str, object], output: str | Path) -> None:
    Path(output).parent.mkdir(parents=True, exist_ok=True)
    Path(output).write_text(json.dumps(summary, indent=2, sort_keys=True), encoding="utf-8")


def write_fleet_summary_csv(summary: dict[str, object], output: str | Path) -> None:
    Path(output).parent.mkdir(parents=True, exist_ok=True)
    rows = list(summary.get("ranking", []))
    with Path(output).open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=FLEET_SUMMARY_COLUMNS)
        writer.writeheader()
        for row in rows:
            writer.writerow({column: row.get(column, "") for column in FLEET_SUMMARY_COLUMNS})


def render_fleet_scale_markdown(
    summary: dict[str, object],
    *,
    title: str = "Fleet-Scale QoS/QoE Benchmark",
    records_path: str | Path | None = None,
    summary_path: str | Path | None = None,
) -> str:
    ranking = list(summary.get("ranking", []))
    winners = list(summary.get("winners", []))
    observations = list(summary.get("observations", []))
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
            f"- Ranked rows: `{len(ranking)}`",
            "",
            "## Policy Ranking by Fleet Size",
            "",
            _markdown_table(FLEET_SUMMARY_COLUMNS, ranking),
            "",
            "## Winners",
            "",
            _markdown_table(["robots", "best_policy", "fleet_score"], winners),
            "",
            "## Research Signals",
            "",
        ]
    )
    lines.extend(f"- {item}" for item in observations)
    lines.append("")
    return "\n".join(lines)


def write_fleet_markdown(
    summary: dict[str, object],
    output: str | Path,
    *,
    title: str = "Fleet-Scale QoS/QoE Benchmark",
    records_path: str | Path | None = None,
    summary_path: str | Path | None = None,
) -> None:
    Path(output).parent.mkdir(parents=True, exist_ok=True)
    Path(output).write_text(
        render_fleet_scale_markdown(
            summary,
            title=title,
            records_path=records_path,
            summary_path=summary_path,
        ),
        encoding="utf-8",
    )


def build_fleet_scale_observations(rows: Iterable[dict[str, object]]) -> list[str]:
    row_list = list(rows)
    if not row_list:
        return ["No fleet-scale rows were available."]

    observations = []
    for robots in sorted({int(row["robots"]) for row in row_list}):
        group = [row for row in row_list if int(row["robots"]) == robots]
        best = max(group, key=lambda row: _float(row, "fleet_score"))
        observations.append(
            f"`{robots}` robots: `{best.get('policy')}` leads with fleet score "
            f"`{_format(_float(best, 'fleet_score'))}` and control miss "
            f"`{_format(_float(best, 'control_deadline_miss_ratio_mean'))}`."
        )

    predictive_rows = [
        row for row in row_list if row.get("policy") == "fleetqox_predictive"
    ]
    csds_rows = [row for row in row_list if row.get("policy") == "fleetqox_csds"]
    static_rows = [row for row in row_list if row.get("policy") == "static_priority"]
    if predictive_rows and static_rows:
        largest = max(int(row["robots"]) for row in predictive_rows)
        predictive = next(row for row in predictive_rows if int(row["robots"]) == largest)
        static = next(row for row in static_rows if int(row["robots"]) == largest)
        observations.append(
            f"At `{largest}` robots, predictive admission reduces control miss by "
            f"`{_format(_float(static, 'control_deadline_miss_ratio_mean') - _float(predictive, 'control_deadline_miss_ratio_mean'))}` "
            "versus static priority."
        )
        observations.append(
            f"At `{largest}` robots, predictive admission reduces defer ratio by "
            f"`{_format(_float(static, 'defer_ratio_mean') - _float(predictive, 'defer_ratio_mean'))}` "
            f"with semantic compaction ratio `{_format(_float(predictive, 'compacted_ratio_mean'))}`."
        )
    if predictive_rows and csds_rows:
        largest = max(int(row["robots"]) for row in predictive_rows)
        predictive = next(row for row in predictive_rows if int(row["robots"]) == largest)
        csds = next(row for row in csds_rows if int(row["robots"]) == largest)
        observations.append(
            f"At `{largest}` robots, predictive admission reduces control miss by "
            f"`{_format(_float(csds, 'control_deadline_miss_ratio_mean') - _float(predictive, 'control_deadline_miss_ratio_mean'))}` "
            "versus CSDS."
        )

    high_miss = [
        row
        for row in row_list
        if _float(row, "control_deadline_miss_ratio_mean") >= 0.3
    ]
    if high_miss:
        observations.append(
            "Control deadline miss remains the main scaling bottleneck in "
            f"`{len(high_miss)}` policy/fleet-size rows."
        )
    return observations


def _record_from_result(
    result: BenchmarkResult,
    *,
    seed: int,
    seconds: int,
    capacity: int,
) -> dict[str, object]:
    events = max(1, result.sent + result.dropped + result.deferred)
    return {
        "kind": "fleet_scale_result",
        "policy": result.name,
        "robots": result.robots,
        "seed": seed,
        "seconds": seconds,
        "ticks": result.ticks,
        "sent": result.sent,
        "dropped": result.dropped,
        "deferred": result.deferred,
        "degraded": result.degraded,
        "compacted": result.compacted,
        "bytes_sent": result.bytes_sent,
        "capacity_bytes_per_second": capacity,
        "control_deadline_miss_ratio": result.control_deadline_miss_ratio,
        "stale_state_ratio": result.stale_state_ratio,
        "qoe_delivery_ratio": result.qoe_delivery_ratio,
        "utility_score": result.utility_score,
        "defer_ratio": result.deferred / events,
        "drop_ratio": result.dropped / events,
        "degraded_ratio": result.degraded / events,
        "compacted_ratio": result.compacted / events,
    }


def _winners_by_robot_count(rows: list[dict[str, object]]) -> list[dict[str, object]]:
    winners = []
    for robots in sorted({int(row["robots"]) for row in rows}):
        best = max(
            (row for row in rows if int(row["robots"]) == robots),
            key=lambda row: _float(row, "fleet_score"),
        )
        winners.append(
            {
                "robots": robots,
                "best_policy": best.get("policy", ""),
                "fleet_score": best.get("fleet_score", 0.0),
            }
        )
    return winners


def _fleet_score(row: dict[str, object]) -> float:
    utility = _float(row, "utility_score_mean")
    qoe = _float(row, "qoe_delivery_ratio_mean")
    control_miss = _float(row, "control_deadline_miss_ratio_mean")
    stale = _float(row, "stale_state_ratio_mean")
    defer = _float(row, "defer_ratio_mean")
    drop = _float(row, "drop_ratio_mean")
    return max(0.0, utility + 2.0 * qoe - 6.0 * control_miss - 2.0 * stale - defer - drop)


def _mean(rows: list[dict[str, object]], key: str) -> float:
    values = [_float(row, key) for row in rows]
    values = [value for value in values if math.isfinite(value)]
    return mean(values) if values else 0.0


def _markdown_table(columns: list[str], rows: list[dict[str, object]]) -> str:
    header = "| " + " | ".join(columns) + " |"
    separator = "| " + " | ".join("---" for _ in columns) + " |"
    body = [
        "| " + " | ".join(_format_value(row.get(column, "")) for column in columns) + " |"
        for row in rows
    ]
    return "\n".join([header, separator, *body])


def _format_value(value: object) -> str:
    if isinstance(value, float):
        return _format(value)
    return str(value)


def _format(value: float) -> str:
    if abs(value) >= 10:
        return f"{value:.2f}"
    return f"{value:.3f}"


def _float(row: dict[str, object], key: str) -> float:
    value = row.get(key, 0.0)
    return float(value) if isinstance(value, (int, float)) else 0.0

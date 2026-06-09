"""Report generation helpers for FleetQoX benchmark results."""

from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Iterable

from .ros2_perf import read_perf_records_jsonl, summarize_perf_records


SUMMARY_COLUMNS = [
    "scenario",
    "component",
    "rmw",
    "runs",
    "rank_score",
    "qoe_score_mean",
    "latency_p95_ms_mean",
    "latency_p99_ms_mean",
    "jitter_p95_ms_mean",
    "loss_ratio_mean",
    "deadline_miss_ratio_mean",
    "throughput_mbps_mean",
    "cpu_mean",
    "memory_mean",
]


def load_summary(summary_path: str | Path | None, metrics_path: str | Path) -> dict[str, object]:
    """Load a summary JSON file or compute one from JSONL metrics."""

    if summary_path and Path(summary_path).exists():
        return json.loads(Path(summary_path).read_text(encoding="utf-8"))
    records = read_perf_records_jsonl(metrics_path)
    return summarize_perf_records(records)


def write_summary_csv(summary: dict[str, object], output: str | Path) -> None:
    rows = list(summary.get("ranking", []))
    Path(output).parent.mkdir(parents=True, exist_ok=True)
    with Path(output).open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=SUMMARY_COLUMNS)
        writer.writeheader()
        for row in rows:
            writer.writerow({column: row.get(column, "") for column in SUMMARY_COLUMNS})


def render_markdown_report(
    summary: dict[str, object],
    *,
    title: str = "T2E ROS 2 / netem Report",
    metrics_path: str | Path | None = None,
    summary_path: str | Path | None = None,
) -> str:
    ranking = list(summary.get("ranking", []))
    groups = list(summary.get("groups", []))
    lines = [
        f"# {title}",
        "",
        "## Inputs",
        "",
    ]
    if metrics_path:
        lines.append(f"- Metrics: `{metrics_path}`")
    if summary_path:
        lines.append(f"- Summary: `{summary_path}`")
    lines.extend(
        [
            f"- Groups: `{len(groups)}`",
            f"- Ranked rows: `{len(ranking)}`",
            "",
            "## Ranking",
            "",
            _markdown_table(SUMMARY_COLUMNS, ranking),
            "",
            "## Component Winners",
            "",
            _markdown_table(
                [
                    "scenario",
                    "component",
                    "best_rmw",
                    "rank_score",
                    "qoe_score_mean",
                    "latency_p95_ms_mean",
                    "loss_ratio_mean",
                    "deadline_miss_ratio_mean",
                ],
                component_winners(ranking),
            ),
            "",
            "## Observations",
            "",
        ]
    )
    observations = build_observations(ranking)
    lines.extend(f"- {item}" for item in observations)
    lines.append("")
    return "\n".join(lines)


def write_markdown_report(
    summary: dict[str, object],
    output: str | Path,
    *,
    title: str,
    metrics_path: str | Path | None = None,
    summary_path: str | Path | None = None,
) -> None:
    Path(output).parent.mkdir(parents=True, exist_ok=True)
    Path(output).write_text(
        render_markdown_report(
            summary,
            title=title,
            metrics_path=metrics_path,
            summary_path=summary_path,
        ),
        encoding="utf-8",
    )


def component_winners(ranking: Iterable[dict[str, object]]) -> list[dict[str, object]]:
    winners: dict[tuple[str, str], dict[str, object]] = {}
    for row in ranking:
        key = (str(row.get("scenario", "")), str(row.get("component", "")))
        current = winners.get(key)
        if current is None or _float(row, "rank_score") > _float(current, "rank_score"):
            winners[key] = {
                "scenario": row.get("scenario", ""),
                "component": row.get("component", ""),
                "best_rmw": row.get("rmw", ""),
                "rank_score": row.get("rank_score", 0.0),
                "qoe_score_mean": row.get("qoe_score_mean", 0.0),
                "latency_p95_ms_mean": row.get("latency_p95_ms_mean", 0.0),
                "loss_ratio_mean": row.get("loss_ratio_mean", 0.0),
                "deadline_miss_ratio_mean": row.get("deadline_miss_ratio_mean", 0.0),
            }
    return sorted(winners.values(), key=lambda item: (str(item["scenario"]), str(item["component"])))


def build_observations(ranking: Iterable[dict[str, object]]) -> list[str]:
    rows = list(ranking)
    if not rows:
        return ["No metric rows were available."]

    observations = []
    best = max(rows, key=lambda row: _float(row, "rank_score"))
    observations.append(
        "Best overall: "
        f"`{best.get('rmw')}` on `{best.get('component')}` "
        f"with rank score `{_format(_float(best, 'rank_score'))}`."
    )

    high_deadline = [
        row
        for row in rows
        if _float(row, "deadline_miss_ratio_mean") >= 0.5
    ]
    if high_deadline:
        names = ", ".join(
            f"`{row.get('component')}/{row.get('rmw')}`"
            for row in sorted(high_deadline, key=lambda item: str(item.get("rmw")))[:5]
        )
        observations.append(f"High deadline-miss regimes detected: {names}.")

    zero_loss = [
        row
        for row in rows
        if _float(row, "loss_ratio_mean") == 0.0
    ]
    if zero_loss:
        names = ", ".join(
            f"`{row.get('component')}/{row.get('rmw')}`"
            for row in zero_loss[:5]
        )
        observations.append(f"Zero-loss groups in this run: {names}.")

    return observations


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

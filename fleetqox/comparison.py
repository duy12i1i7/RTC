"""Cross-baseline comparison reports for ROS 2/netem benchmark summaries."""

from __future__ import annotations

import csv
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

from .reporting import component_winners, load_summary


BASELINE_COLUMNS = [
    "baseline",
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
]

DELTA_COLUMNS = [
    "baseline",
    "reference",
    "component",
    "rmw",
    "rank_score_delta",
    "qoe_score_delta",
    "latency_p95_ms_delta",
    "latency_p99_ms_delta",
    "jitter_p95_ms_delta",
    "loss_ratio_delta",
    "deadline_miss_ratio_delta",
    "interpretation",
]


@dataclass(frozen=True)
class BaselineInput:
    name: str
    metrics_path: Path
    summary_path: Path | None = None


def load_baseline(input_: BaselineInput) -> dict[str, object]:
    summary = load_summary(input_.summary_path, input_.metrics_path)
    return {
        "name": input_.name,
        "metrics_path": str(input_.metrics_path),
        "summary_path": str(input_.summary_path) if input_.summary_path else "",
        "summary": summary,
    }


def compare_baselines(inputs: Iterable[BaselineInput]) -> dict[str, object]:
    baselines = [load_baseline(input_) for input_ in inputs]
    rows = _baseline_rows(baselines)
    deltas = _pairwise_deltas(rows)
    return {
        "baselines": [
            {
                "name": baseline["name"],
                "metrics_path": baseline["metrics_path"],
                "summary_path": baseline["summary_path"],
            }
            for baseline in baselines
        ],
        "rows": rows,
        "deltas": deltas,
        "observations": build_comparison_observations(rows, deltas),
    }


def render_comparison_markdown(
    comparison: dict[str, object],
    *,
    title: str = "T2E Baseline Comparison",
) -> str:
    baselines = list(comparison.get("baselines", []))
    rows = list(comparison.get("rows", []))
    deltas = list(comparison.get("deltas", []))
    observations = list(comparison.get("observations", []))

    lines = [
        f"# {title}",
        "",
        "## Inputs",
        "",
    ]
    for baseline in baselines:
        lines.append(
            "- "
            f"`{baseline.get('name')}`: metrics `{baseline.get('metrics_path')}`, "
            f"summary `{baseline.get('summary_path')}`"
        )
    lines.extend(
        [
            "",
            "## Ranking Rows",
            "",
            _markdown_table(BASELINE_COLUMNS, rows),
            "",
            "## Delta vs Reference",
            "",
            _markdown_table(DELTA_COLUMNS, deltas),
            "",
            "## Observations",
            "",
        ]
    )
    lines.extend(f"- {item}" for item in observations)
    lines.append("")
    return "\n".join(lines)


def write_comparison_markdown(
    comparison: dict[str, object],
    output: str | Path,
    *,
    title: str = "T2E Baseline Comparison",
) -> None:
    Path(output).parent.mkdir(parents=True, exist_ok=True)
    Path(output).write_text(
        render_comparison_markdown(comparison, title=title),
        encoding="utf-8",
    )


def write_comparison_csv(comparison: dict[str, object], output: str | Path) -> None:
    Path(output).parent.mkdir(parents=True, exist_ok=True)
    rows = list(comparison.get("deltas", []))
    with Path(output).open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=DELTA_COLUMNS)
        writer.writeheader()
        for row in rows:
            writer.writerow({column: row.get(column, "") for column in DELTA_COLUMNS})


def build_comparison_observations(
    rows: Iterable[dict[str, object]],
    deltas: Iterable[dict[str, object]],
) -> list[str]:
    row_list = list(rows)
    delta_list = list(deltas)
    if not row_list:
        return ["No baseline rows were available."]

    observations: list[str] = []
    for baseline in sorted({str(row["baseline"]) for row in row_list}):
        winners = component_winners(
            [row for row in row_list if row.get("baseline") == baseline]
        )
        for winner in winners:
            observations.append(
                f"`{baseline}` winner for `{winner.get('component')}` is "
                f"`{winner.get('best_rmw')}` with deadline miss "
                f"`{_format(_float(winner, 'deadline_miss_ratio_mean'))}`."
            )

    severe = [
        delta
        for delta in delta_list
        if _float(delta, "deadline_miss_ratio_delta") >= 0.5
    ]
    if severe:
        names = ", ".join(
            f"`{item.get('component')}/{item.get('rmw')}`"
            for item in sorted(
                severe,
                key=lambda row: _float(row, "deadline_miss_ratio_delta"),
                reverse=True,
            )[:5]
        )
        observations.append(f"Large deadline regressions vs reference: {names}.")

    tail_tradeoffs = [
        delta
        for delta in delta_list
        if _float(delta, "loss_ratio_delta") < 0
        and _float(delta, "latency_p99_ms_delta") > 25
    ]
    if tail_tradeoffs:
        names = ", ".join(
            f"`{item.get('component')}/{item.get('rmw')}`"
            for item in tail_tradeoffs[:5]
        )
        observations.append(
            "Loss improved while p99 latency worsened for " f"{names}; this is a QoE tail-risk signal."
        )

    return observations


def _baseline_rows(baselines: list[dict[str, object]]) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for baseline in baselines:
        summary = baseline["summary"]
        assert isinstance(summary, dict)
        for row in summary.get("ranking", []):
            if not isinstance(row, dict):
                continue
            rows.append(
                {
                    "baseline": baseline["name"],
                    **{column: row.get(column, "") for column in BASELINE_COLUMNS if column != "baseline"},
                }
            )
    return rows


def _pairwise_deltas(rows: list[dict[str, object]]) -> list[dict[str, object]]:
    if not rows:
        return []
    baseline_order = []
    for row in rows:
        name = str(row.get("baseline", ""))
        if name not in baseline_order:
            baseline_order.append(name)
    if len(baseline_order) < 2:
        return []

    reference_name = baseline_order[0]
    reference = {
        (str(row.get("component")), str(row.get("rmw"))): row
        for row in rows
        if row.get("baseline") == reference_name
    }
    deltas = []
    for row in rows:
        baseline = str(row.get("baseline", ""))
        if baseline == reference_name:
            continue
        key = (str(row.get("component")), str(row.get("rmw")))
        ref = reference.get(key)
        if ref is None:
            continue
        delta = {
            "baseline": baseline,
            "reference": reference_name,
            "component": row.get("component", ""),
            "rmw": row.get("rmw", ""),
            "rank_score_delta": _float(row, "rank_score") - _float(ref, "rank_score"),
            "qoe_score_delta": _float(row, "qoe_score_mean") - _float(ref, "qoe_score_mean"),
            "latency_p95_ms_delta": _float(row, "latency_p95_ms_mean")
            - _float(ref, "latency_p95_ms_mean"),
            "latency_p99_ms_delta": _float(row, "latency_p99_ms_mean")
            - _float(ref, "latency_p99_ms_mean"),
            "jitter_p95_ms_delta": _float(row, "jitter_p95_ms_mean")
            - _float(ref, "jitter_p95_ms_mean"),
            "loss_ratio_delta": _float(row, "loss_ratio_mean") - _float(ref, "loss_ratio_mean"),
            "deadline_miss_ratio_delta": _float(row, "deadline_miss_ratio_mean")
            - _float(ref, "deadline_miss_ratio_mean"),
        }
        delta["interpretation"] = _interpret_delta(delta)
        deltas.append(delta)
    return sorted(deltas, key=lambda item: (str(item["component"]), str(item["rmw"])))


def _interpret_delta(delta: dict[str, object]) -> str:
    deadline = _float(delta, "deadline_miss_ratio_delta")
    tail = _float(delta, "latency_p99_ms_delta")
    loss = _float(delta, "loss_ratio_delta")
    score = _float(delta, "rank_score_delta")
    if deadline >= 0.5:
        return "deadline collapse"
    if loss < -0.01 and tail > 25:
        return "loss-tail tradeoff"
    if score < -0.1:
        return "QoE regression"
    if score > 0.05:
        return "QoE improvement"
    return "mixed"


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

"""Outcome-driven adaptation for Lagrangian sidecar variants."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Mapping


@dataclass(frozen=True)
class OutcomeTargets:
    deadline_miss_ratio: float = 0.002
    control_starvation_events: float = 2.0
    loss_ratio: float = 0.012
    reference_policy: str = "fleetqox_predictive"


BOUNDS = {
    "deadline_risk_budget": (0.02, 0.12),
    "initial_deadline_lambda": (0.5, 8.0),
    "risk_barrier_start": (0.45, 0.85),
    "risk_barrier_scale": (8.0, 20.0),
    "deadline_drop_risk": (0.30, 0.90),
}


def load_variant_manifest(path: str | Path) -> dict[str, dict[str, float]]:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    variants = payload.get("variants", payload)
    if not isinstance(variants, dict):
        raise ValueError("variant manifest must contain an object")
    result: dict[str, dict[str, float]] = {}
    for label, params in variants.items():
        if not isinstance(params, dict):
            raise ValueError(f"variant {label} must map to a config object")
        result[str(label)] = {str(key): float(value) for key, value in params.items()}
    return result


def adapt_from_repeated_summary(
    summary: Mapping[str, object],
    variants: Mapping[str, Mapping[str, float]],
    *,
    next_label: str,
    source_label: str | None = None,
    targets: OutcomeTargets | None = None,
) -> dict[str, object]:
    target = targets or OutcomeTargets()
    policies = {
        str(row.get("policy", "")): row
        for row in summary.get("policies", [])
        if isinstance(row, dict)
    }
    if source_label is None:
        source_label = select_source_variant(summary, variants, targets=target)
    if source_label not in variants:
        raise ValueError(f"source variant is missing from manifest: {source_label}")
    if source_label not in policies:
        raise ValueError(f"source variant is missing from summary: {source_label}")
    source_row = policies[source_label]
    reference_row = policies.get(target.reference_policy)
    next_params, adjustments = adapt_lagrangian_params(
        variants[source_label],
        source_row,
        reference_row=reference_row,
        targets=target,
    )
    command = run_command_for_variant(next_label, next_params)
    return {
        "next_label": next_label,
        "source_label": source_label,
        "targets": {
            "deadline_miss_ratio": target.deadline_miss_ratio,
            "control_starvation_events": target.control_starvation_events,
            "loss_ratio": target.loss_ratio,
            "reference_policy": target.reference_policy,
        },
        "source_metrics": _compact_metrics(source_row),
        "reference_metrics": _compact_metrics(reference_row) if reference_row else {},
        "source_params": dict(variants[source_label]),
        "next_params": next_params,
        "adjustments": adjustments,
        "run_command": command,
    }


def select_source_variant(
    summary: Mapping[str, object],
    variants: Mapping[str, Mapping[str, float]],
    *,
    targets: OutcomeTargets | None = None,
) -> str:
    target = targets or OutcomeTargets()
    candidate_rows = [
        row
        for row in summary.get("policies", [])
        if isinstance(row, dict) and str(row.get("policy", "")) in variants
    ]
    if not candidate_rows:
        raise ValueError("summary does not contain any labeled Lagrangian variants")
    pareto_rows = [row for row in candidate_rows if row.get("pareto_frontier")]
    if pareto_rows:
        candidate_rows = pareto_rows

    def score(row: dict[str, object]) -> tuple[float, str]:
        utility = _numeric(row.get("semantic_utility_delivered_mean", 0.0))
        miss = _numeric(row.get("deadline_miss_ratio_mean", 0.0))
        starvation = _numeric(row.get("control_starvation_events_mean", 0.0))
        loss = _numeric(row.get("loss_ratio_mean", 0.0))
        pareto_bonus = 1.0 if row.get("pareto_frontier") else 0.0
        risk_penalty = (
            1800.0 * max(0.0, miss - target.deadline_miss_ratio)
            + 14.0 * max(0.0, starvation - target.control_starvation_events)
            + 1000.0 * max(0.0, loss - target.loss_ratio)
        )
        return (utility + 250.0 * pareto_bonus - risk_penalty, str(row.get("policy", "")))

    return max(candidate_rows, key=score)["policy"]


def adapt_lagrangian_params(
    params: Mapping[str, float],
    source_row: Mapping[str, object],
    *,
    reference_row: Mapping[str, object] | None,
    targets: OutcomeTargets,
) -> tuple[dict[str, float], dict[str, float]]:
    current = dict(params)
    miss = _numeric(source_row.get("deadline_miss_ratio_mean", 0.0))
    starvation = _numeric(source_row.get("control_starvation_events_mean", 0.0))
    loss = _numeric(source_row.get("loss_ratio_mean", 0.0))
    utility = _numeric(source_row.get("semantic_utility_delivered_mean", 0.0))
    reference_utility = _numeric(reference_row.get("semantic_utility_delivered_mean", 0.0)) if reference_row else utility
    utility_gap = max(0.0, reference_utility - utility) / max(1.0, reference_utility)

    deadline_pressure = max(0.0, miss - targets.deadline_miss_ratio) / max(
        0.0005,
        targets.deadline_miss_ratio,
    )
    starvation_pressure = max(0.0, starvation - targets.control_starvation_events) / max(
        1.0,
        targets.control_starvation_events,
    )
    loss_pressure = max(0.0, loss - targets.loss_ratio) / max(0.002, targets.loss_ratio)
    risk_pressure = deadline_pressure + starvation_pressure + 0.5 * loss_pressure

    next_params = dict(current)
    adjustments: dict[str, float] = {}
    if risk_pressure > 0.0:
        adjustments = {
            "initial_deadline_lambda": min(1.2, 0.25 + 0.25 * risk_pressure),
            "risk_barrier_start": -min(0.08, 0.02 + 0.015 * risk_pressure),
            "risk_barrier_scale": min(4.0, 0.5 + 0.45 * risk_pressure),
            "deadline_drop_risk": -min(0.08, 0.02 + 0.012 * risk_pressure),
            "deadline_risk_budget": -min(0.02, 0.004 + 0.003 * risk_pressure),
        }
    else:
        relax = min(0.06, 0.012 + 0.05 * utility_gap)
        adjustments = {
            "initial_deadline_lambda": -min(0.5, 0.1 + 0.5 * utility_gap),
            "risk_barrier_start": relax,
            "risk_barrier_scale": -min(2.0, 0.4 + 2.0 * utility_gap),
            "deadline_drop_risk": relax,
            "deadline_risk_budget": min(0.02, 0.004 + 0.02 * utility_gap),
        }

    for key, delta in adjustments.items():
        next_params[key] = _bounded(key, _numeric(next_params.get(key, 0.0)) + delta)
    return next_params, adjustments


def render_adaptation_markdown(adaptation: Mapping[str, object], *, title: str) -> str:
    lines = [
        f"# {title}",
        "",
        "## Source",
        "",
        f"- Source variant: `{adaptation['source_label']}`",
        f"- Next variant: `{adaptation['next_label']}`",
        "",
        "## Metrics",
        "",
        _markdown_table(
            ["item", "utility", "control misses", "deadline miss", "loss", "p95 ms"],
            [
                {"item": "source", **_metric_row(adaptation.get("source_metrics", {}))},
                {"item": "reference", **_metric_row(adaptation.get("reference_metrics", {}))},
            ],
        ),
        "",
        "## Next Parameters",
        "",
        _markdown_table(
            ["parameter", "source", "delta", "next"],
            _param_rows(
                adaptation.get("source_params", {}),
                adaptation.get("adjustments", {}),
                adaptation.get("next_params", {}),
            ),
        ),
        "",
        "## Run Command",
        "",
        "```bash",
        " ".join(str(part) for part in adaptation["run_command"]),
        "```",
        "",
        "## Interpretation",
        "",
        "- This is an outcome-driven trust-region update: measured deadline and starvation excess tighten the Lagrangian risk gate; safe low-utility results loosen it.",
        "- The generated variant should be validated through Docker/netem before changing controller defaults.",
        "",
    ]
    return "\n".join(lines)


def write_adaptation_json(adaptation: Mapping[str, object], output: str | Path) -> None:
    Path(output).parent.mkdir(parents=True, exist_ok=True)
    Path(output).write_text(json.dumps(adaptation, indent=2, sort_keys=True), encoding="utf-8")


def write_adaptation_markdown(
    adaptation: Mapping[str, object],
    output: str | Path,
    *,
    title: str,
) -> None:
    Path(output).parent.mkdir(parents=True, exist_ok=True)
    Path(output).write_text(
        render_adaptation_markdown(adaptation, title=title),
        encoding="utf-8",
    )


def run_command_for_variant(label: str, params: Mapping[str, float]) -> list[str]:
    return [
        "python3",
        "-m",
        "scripts.run_sidecar_repeated_netem",
        "--run",
        "--scenario-prefix",
        f"sidecar_{label}_v1",
        "--policy",
        "fleetqox_predictive_lagrangian",
        "--policy-label",
        label,
        "--lagrangian-deadline-risk-budget",
        _format_cli(params["deadline_risk_budget"]),
        "--lagrangian-initial-deadline-lambda",
        _format_cli(params["initial_deadline_lambda"]),
        "--lagrangian-risk-barrier-start",
        _format_cli(params["risk_barrier_start"]),
        "--lagrangian-risk-barrier-scale",
        _format_cli(params["risk_barrier_scale"]),
        "--lagrangian-deadline-drop-risk",
        _format_cli(params["deadline_drop_risk"]),
        "--seeds",
        "7,13",
        "--closed-loop-feed",
    ]


def _compact_metrics(row: Mapping[str, object] | None) -> dict[str, float]:
    if not row:
        return {}
    return {
        "semantic_utility_delivered_mean": _numeric(row.get("semantic_utility_delivered_mean", 0.0)),
        "control_starvation_events_mean": _numeric(row.get("control_starvation_events_mean", 0.0)),
        "deadline_miss_ratio_mean": _numeric(row.get("deadline_miss_ratio_mean", 0.0)),
        "loss_ratio_mean": _numeric(row.get("loss_ratio_mean", 0.0)),
        "latency_p95_ms_mean": _numeric(row.get("latency_p95_ms_mean", 0.0)),
    }


def _metric_row(metrics: object) -> dict[str, str]:
    if not isinstance(metrics, dict):
        metrics = {}
    return {
        "utility": _format(_numeric(metrics.get("semantic_utility_delivered_mean", 0.0))),
        "control misses": _format(_numeric(metrics.get("control_starvation_events_mean", 0.0))),
        "deadline miss": _format(_numeric(metrics.get("deadline_miss_ratio_mean", 0.0))),
        "loss": _format(_numeric(metrics.get("loss_ratio_mean", 0.0))),
        "p95 ms": _format(_numeric(metrics.get("latency_p95_ms_mean", 0.0))),
    }


def _param_rows(
    source: object,
    adjustments: object,
    next_params: object,
) -> list[dict[str, str]]:
    source_map = source if isinstance(source, dict) else {}
    adjustment_map = adjustments if isinstance(adjustments, dict) else {}
    next_map = next_params if isinstance(next_params, dict) else {}
    rows = []
    for key in BOUNDS:
        rows.append(
            {
                "parameter": f"`{key}`",
                "source": _format(_numeric(source_map.get(key, 0.0))),
                "delta": _format(_numeric(adjustment_map.get(key, 0.0))),
                "next": _format(_numeric(next_map.get(key, 0.0))),
            }
        )
    return rows


def _markdown_table(columns: list[str], rows: Iterable[Mapping[str, object]]) -> str:
    header = "| " + " | ".join(columns) + " |"
    separator = "| " + " | ".join("---" for _ in columns) + " |"
    body = [
        "| " + " | ".join(str(row.get(column, "")) for column in columns) + " |"
        for row in rows
    ]
    return "\n".join([header, separator, *body])


def _bounded(key: str, value: float) -> float:
    lower, upper = BOUNDS[key]
    return max(lower, min(upper, value))


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


def _format_cli(value: float) -> str:
    return f"{value:.6g}"

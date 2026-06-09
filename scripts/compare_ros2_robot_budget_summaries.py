"""Compare ROS 2 dynamic-objective per-robot budget summaries."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Mapping


SUMMARY_FIELDS = [
    "per_robot_budget_pass_ratio",
    "per_robot_min_control_delivery_ratio_mean",
    "per_robot_max_deadline_miss_ratio_mean",
    "per_robot_rx_jain_index_mean",
    "per_robot_control_delivery_jain_index_mean",
    "per_robot_deadline_success_jain_index_mean",
    "per_robot_latency_p95_spread_ms_mean",
    "rx_mean",
    "loss_ratio_mean",
    "control_delivery_ratio_mean",
    "deadline_miss_ratio_mean",
    "latency_p95_ms_mean",
    "semantic_utility_delivered_mean",
]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--summary",
        action="append",
        default=[],
        metavar="LABEL:PATH",
        help="Summary JSON to compare. The first entry is the baseline.",
    )
    parser.add_argument(
        "--summary-json",
        type=Path,
        default=Path("results_ros2_live_bridge/robot_budget_policy_compare_summary.json"),
    )
    parser.add_argument(
        "--markdown",
        type=Path,
        default=Path("results_ros2_live_bridge/robot_budget_policy_compare_report.md"),
    )
    parser.add_argument("--title", default="ROS 2 Robot Budget Policy Comparison")
    args = parser.parse_args()

    result = compare_summary_specs(args.summary)
    args.summary_json.parent.mkdir(parents=True, exist_ok=True)
    args.markdown.parent.mkdir(parents=True, exist_ok=True)
    args.summary_json.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    args.markdown.write_text(render_markdown(result, title=args.title))
    print(
        "ros2-robot-budget-compare "
        f"summaries={len(result['policies'])} "
        f"summary={args.summary_json} markdown={args.markdown}"
    )
    return 0


def compare_summary_specs(specs: list[str]) -> dict[str, object]:
    if len(specs) < 2:
        raise ValueError("at least two --summary LABEL:PATH entries are required")
    loaded = [_load_labeled_summary(spec) for spec in specs]
    baseline = loaded[0]
    policies = []
    for item in loaded:
        policy = item["policy"]
        deltas = {
            field: _number(policy.get(field, 0.0))
            - _number(baseline["policy"].get(field, 0.0))
            for field in SUMMARY_FIELDS
        }
        policies.append(
            {
                "label": item["label"],
                "path": item["path"],
                "policy": str(policy.get("policy", "")),
                "runs": int(policy.get("runs", 0)),
                "metrics": {
                    field: _number(policy.get(field, 0.0))
                    for field in SUMMARY_FIELDS
                },
                "delta_vs_baseline": deltas,
                "per_seed": _per_seed_rows(item["summary"]),
            }
        )
    return {
        "schema_version": "fleetrmw.ros2_robot_budget_policy_compare.v1",
        "baseline_label": loaded[0]["label"],
        "policies": policies,
    }


def render_markdown(result: Mapping[str, object], *, title: str) -> str:
    policies = [
        item for item in result.get("policies", [])
        if isinstance(item, Mapping)
    ]
    lines = [
        f"# {title}",
        "",
        f"- Baseline: `{result.get('baseline_label', '')}`",
        "",
        "## Policy Summary",
        "",
        _table(
            [
                "label",
                "budget pass",
                "min ctrl",
                "max deadline",
                "ctrl delivery",
                "deadline miss",
                "p95 ms",
                "utility",
                "delta min ctrl",
                "delta deadline miss",
                "delta p95",
                "delta utility",
            ],
            [_summary_row(item) for item in policies],
        ),
        "",
        "## Per-Seed Budget Rows",
        "",
        _table(
            [
                "label",
                "seed",
                "pass",
                "min ctrl",
                "max deadline",
                "worst ctrl",
                "rx",
                "ctrl delivery",
                "deadline miss",
                "p95 ms",
            ],
            [
                _seed_row(item, row)
                for item in policies
                for row in item.get("per_seed", [])
                if isinstance(row, Mapping)
            ],
        ),
        "",
        "## Interpretation",
        "",
        "A higher budget pass ratio and minimum per-robot control delivery are",
        "better.  Lower maximum per-robot deadline miss, aggregate deadline miss,",
        "and p95 latency are better.  This report deliberately keeps utility in",
        "the table because a controller that improves worst-robot SLOs by dropping",
        "too much useful traffic is not a complete FleetRMW solution.",
        "",
    ]
    return "\n".join(lines)


def _load_labeled_summary(spec: str) -> dict[str, object]:
    if ":" not in spec:
        raise ValueError(f"summary spec must be LABEL:PATH, got {spec!r}")
    label, raw_path = spec.split(":", 1)
    path = Path(raw_path)
    summary = json.loads(path.read_text())
    policies = summary.get("policies", [])
    if not isinstance(policies, list) or not policies:
        raise ValueError(f"{path} does not contain policy summaries")
    policy = policies[0]
    if not isinstance(policy, Mapping):
        raise ValueError(f"{path} first policy summary is not an object")
    return {
        "label": label,
        "path": str(path),
        "summary": summary,
        "policy": policy,
    }


def _per_seed_rows(summary: Mapping[str, object]) -> list[dict[str, object]]:
    rows = []
    for row in summary.get("comparison_rows", []):
        if not isinstance(row, Mapping):
            continue
        rows.append(
            {
                "seed": int(row.get("seed", 0)),
                "per_robot_budget_pass": bool(row.get("per_robot_budget_pass", False)),
                "per_robot_min_control_delivery_ratio": _number(
                    row.get("per_robot_min_control_delivery_ratio", 0.0)
                ),
                "per_robot_max_deadline_miss_ratio": _number(
                    row.get("per_robot_max_deadline_miss_ratio", 0.0)
                ),
                "per_robot_worst_control_delivery_robot": str(
                    row.get("per_robot_worst_control_delivery_robot", "")
                ),
                "rx": _number(row.get("rx", 0.0)),
                "control_delivery_ratio": _number(row.get("control_delivery_ratio", 0.0)),
                "deadline_miss_ratio": _number(row.get("deadline_miss_ratio", 0.0)),
                "latency_p95_ms": _number(row.get("latency_p95_ms", 0.0)),
            }
        )
    return rows


def _summary_row(item: Mapping[str, object]) -> list[str]:
    metrics = item.get("metrics", {})
    deltas = item.get("delta_vs_baseline", {})
    metric_map = metrics if isinstance(metrics, Mapping) else {}
    delta_map = deltas if isinstance(deltas, Mapping) else {}
    return [
        str(item.get("label", "")),
        _fmt(metric_map.get("per_robot_budget_pass_ratio", 0.0)),
        _fmt(metric_map.get("per_robot_min_control_delivery_ratio_mean", 0.0)),
        _fmt(metric_map.get("per_robot_max_deadline_miss_ratio_mean", 0.0)),
        _fmt(metric_map.get("control_delivery_ratio_mean", 0.0)),
        _fmt(metric_map.get("deadline_miss_ratio_mean", 0.0)),
        _fmt(metric_map.get("latency_p95_ms_mean", 0.0)),
        _fmt(metric_map.get("semantic_utility_delivered_mean", 0.0)),
        _signed(delta_map.get("per_robot_min_control_delivery_ratio_mean", 0.0)),
        _signed(delta_map.get("deadline_miss_ratio_mean", 0.0)),
        _signed(delta_map.get("latency_p95_ms_mean", 0.0)),
        _signed(delta_map.get("semantic_utility_delivered_mean", 0.0)),
    ]


def _seed_row(item: Mapping[str, object], row: Mapping[str, object]) -> list[str]:
    return [
        str(item.get("label", "")),
        str(row.get("seed", "")),
        "yes" if row.get("per_robot_budget_pass") else "no",
        _fmt(row.get("per_robot_min_control_delivery_ratio", 0.0)),
        _fmt(row.get("per_robot_max_deadline_miss_ratio", 0.0)),
        str(row.get("per_robot_worst_control_delivery_robot", "")),
        _fmt(row.get("rx", 0.0)),
        _fmt(row.get("control_delivery_ratio", 0.0)),
        _fmt(row.get("deadline_miss_ratio", 0.0)),
        _fmt(row.get("latency_p95_ms", 0.0)),
    ]


def _table(headers: list[str], rows: list[list[str]]) -> str:
    lines = [
        "| " + " | ".join(headers) + " |",
        "| " + " | ".join("---" for _ in headers) + " |",
    ]
    lines.extend("| " + " | ".join(row) + " |" for row in rows)
    return "\n".join(lines)


def _fmt(value: object) -> str:
    return f"{_number(value):.4f}"


def _signed(value: object) -> str:
    return f"{_number(value):+.4f}"


def _number(value: object) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


if __name__ == "__main__":
    raise SystemExit(main())

"""Compare FleetRMW router data plane with Fast DDS, Cyclone DDS, and Zenoh."""

from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
import statistics
import sys
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.run_rmw_docker_router_matched_multi_topic_probe import (
    DEFAULT_IMAGE,
    cleanup_reusable_build,
    run_probe as run_fleetrmw,
)
from scripts.run_ros2_direct_rmw_netem_probe import run_probe as run_direct


SCHEMA_VERSION = "fleetrmw.large_scale_rmw_comparison.v2"
DEFAULT_RMWS = "rmw_fastrtps_cpp,rmw_cyclonedds_cpp,rmw_zenoh_cpp"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--image", default=DEFAULT_IMAGE)
    parser.add_argument("--robot-counts", default="8,16,32")
    parser.add_argument("--seeds", default="7,13,29")
    parser.add_argument("--rmws", default=DEFAULT_RMWS)
    parser.add_argument("--profile", default="roaming")
    parser.add_argument("--netem-loss-scale", type=float, default=0.25)
    parser.add_argument("--samples", type=int, default=5)
    parser.add_argument("--publish-interval-ms", type=int, default=50)
    parser.add_argument("--timeout-s", type=float, default=25.0)
    parser.add_argument(
        "--summary-json",
        default="results_rmw_socket/large_scale_rmw_comparison_summary.json",
    )
    parser.add_argument(
        "--markdown",
        default="results_rmw_socket/large_scale_rmw_comparison_report.md",
    )
    parser.add_argument(
        "--resume-summary",
        type=Path,
        help="reuse completed rows and rerun only harness/lifecycle failures",
    )
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    summary = run_comparison(
        root=ROOT,
        image=args.image,
        robot_counts=parse_csv_int(args.robot_counts),
        seeds=parse_csv_int(args.seeds, minimum=0),
        rmws=parse_csv(args.rmws),
        profile=args.profile,
        netem_loss_scale=max(args.netem_loss_scale, 0.0),
        samples=max(args.samples, 1),
        publish_interval_ms=max(args.publish_interval_ms, 0),
        timeout_s=max(args.timeout_s, 1.0),
        prior_rows=load_prior_rows(args.resume_summary),
    )
    summary_path = ROOT / args.summary_json
    report_path = ROOT / args.markdown
    summary_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.parent.mkdir(parents=True, exist_ok=True)
    summary_path.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    report_path.write_text(render_markdown(summary), encoding="utf-8")
    if args.json:
        print(json.dumps(summary, sort_keys=True))
    else:
        print("fleetrmw-large-scale-rmw-comparison")
        print(f"  status: {summary['status']}")
        print(f"  ok/skipped/failed: {summary['ok_run_count']}/{summary['skipped_run_count']}/{summary['failed_run_count']}")
        print(f"  summary: {args.summary_json}")
    return 0 if summary["status"] in {"ok", "partial"} else 1


def run_comparison(
    *,
    root: Path,
    image: str,
    robot_counts: list[int],
    seeds: list[int],
    rmws: list[str],
    profile: str,
    netem_loss_scale: float,
    samples: int,
    publish_interval_ms: int,
    timeout_s: float,
    prior_rows: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    cleanup_reusable_build(root=root, image=image)
    rows: list[dict[str, Any]] = []
    prior_index = {
        (row.get("system"), row.get("robot_count"), row.get("seed")): row
        for row in (prior_rows or [])
        if row.get("system") and int(row.get("robot_count", 0)) > 0
    }
    try:
        for robot_count in robot_counts:
            for seed in seeds:
                fleet_key = ("rmw_fleetqox_cpp_router", robot_count, seed)
                prior_fleet = prior_index.get(fleet_key)
                if prior_fleet is not None and not row_needs_infrastructure_rerun(prior_fleet):
                    rows.append(prior_fleet)
                    print(f"reuse {fleet_key}", file=sys.stderr, flush=True)
                else:
                    print(f"run {fleet_key}", file=sys.stderr, flush=True)
                    fleet = run_fleetrmw(
                        root=root,
                        image=image,
                        profile=profile,
                        netem_loss_scale=netem_loss_scale,
                        repetition_seed=seed,
                        samples=samples,
                        robot_count=robot_count,
                        publish_interval_ms=publish_interval_ms,
                        timeout_s=timeout_s,
                        reuse_build=True,
                    )
                    rows.append(normalize_row(fleet, system="rmw_fleetqox_cpp_router"))
                for rmw in rmws:
                    direct_key = (rmw, robot_count, seed)
                    prior_direct = prior_index.get(direct_key)
                    if prior_direct is not None and not row_needs_infrastructure_rerun(prior_direct):
                        rows.append(prior_direct)
                        print(f"reuse {direct_key}", file=sys.stderr, flush=True)
                        continue
                    print(f"run {direct_key}", file=sys.stderr, flush=True)
                    direct = run_direct(
                        root=root,
                        image=image,
                        rmw=rmw,
                        profile=profile,
                        enable_netem=True,
                        require_netem=True,
                        netem_loss_scale=netem_loss_scale,
                        repetition_seed=seed,
                        samples=samples,
                        robot_count=robot_count,
                        publish_interval_ms=publish_interval_ms,
                        timeout_s=timeout_s,
                        publisher_linger_s=6.0,
                    )
                    rows.append(normalize_row(direct, system=rmw))
    finally:
        cleanup_reusable_build(root=root, image=image)
    aggregates = aggregate(rows)
    ok = sum(1 for row in rows if row["status"] == "ok")
    skipped = sum(1 for row in rows if row["status"] == "skipped")
    failed = len(rows) - ok - skipped
    status = "ok" if rows and failed == 0 and skipped == 0 else "partial"
    if rows and ok == 0:
        status = "failed"
    return {
        "schema_version": SCHEMA_VERSION,
        "status": status,
        "image": image,
        "robot_counts": robot_counts,
        "seeds": seeds,
        "systems": ["rmw_fleetqox_cpp_router", *rmws],
        "profile": profile,
        "netem_loss_scale": netem_loss_scale,
        "samples": samples,
        "publish_interval_ms": publish_interval_ms,
        "comparison_design": "split_scope_topology_caveated",
        "direct_claim_allowed": False,
        "claim_scopes": {
            "direct_rmw_delivery_latency": {
                "systems": rmws,
                "topology": "publisher-subscriber",
                "allowed": True,
                "claim": "compare direct ROS 2 RMW delivery and latency",
            },
            "fleet_router_repair_value": {
                "systems": ["rmw_fleetqox_cpp_router"],
                "topology": "publisher-router-subscriber",
                "allowed": True,
                "claim": "measure FleetRMW router reliability and fleet-control value",
            },
            "cross_scope_superiority": {
                "systems": ["rmw_fleetqox_cpp_router", *rmws],
                "topology": "mixed",
                "allowed": False,
                "claim": "no direct superiority claim until hop count is equivalent",
            },
        },
        "topology_note": (
            "FleetRMW uses publisher-router-subscriber; DDS/Zenoh rows use direct "
            "publisher-subscriber. Workload, topics, samples, profile, source-side netem, "
            "and ROS QoS RELIABLE match. FleetRMW enables RTT-derived ACK-timeout "
            "retransmission in addition to gap NACK repair."
        ),
        "run_count": len(rows),
        "ok_run_count": ok,
        "skipped_run_count": skipped,
        "failed_run_count": failed,
        "aggregates": aggregates,
        "runs": rows,
    }


def normalize_row(result: dict[str, Any], *, system: str) -> dict[str, Any]:
    return {
        "system": system,
        "status": result.get("status", "failed"),
        "reason": result.get("reason", ""),
        "profile": result.get("profile", ""),
        "robot_count": int(result.get("robot_count", 0)),
        "topic_count": int(result.get("topic_count", 0)),
        "seed": result.get("repetition_seed"),
        "control_delivery_ratio": number(result.get("control_delivery_ratio")),
        "state_delivery_ratio": number(result.get("state_delivery_ratio")),
        "min_topic_delivery_ratio": number(result.get("min_topic_delivery_ratio")),
        "control_latency_ms_p95": number(result.get("control_latency_ms_p95")),
        "state_latency_ms_p95": number(result.get("state_latency_ms_p95")),
        "reliability_mode": result.get(
            "reliability_mode",
            "ros2_reliable_qos" if system != "rmw_fleetqox_cpp_router" else "gap_nack_only",
        ),
        "reliable_ack_timeout_ms": int(result.get("reliable_ack_timeout_ms", 0)),
        "topology": result.get(
            "topology",
            "publisher-router-subscriber"
            if system == "rmw_fleetqox_cpp_router" else "publisher-subscriber",
        ),
        "result": result,
    }


def row_needs_infrastructure_rerun(row: dict[str, Any]) -> bool:
    if row.get("status") == "ok":
        return False
    result = row.get("result")
    if not isinstance(result, dict):
        return True
    if result.get("reason") == "harness_exception":
        return True
    expected_control = int(result.get("control_expected_count", 0))
    expected_state = int(result.get("state_expected_count", 0))
    delivered = (
        expected_control > 0
        and expected_state > 0
        and int(result.get("control_payload_count", 0)) >= expected_control
        and int(result.get("state_payload_count", 0)) >= expected_state
    )
    process_failed = any(
        int(result.get(key, 0) or 0) != 0
        for key in ("publisher_returncode", "subscriber_returncode", "router_returncode")
    )
    return delivered and process_failed


def load_prior_rows(path: Path | None) -> list[dict[str, Any]]:
    if path is None:
        return []
    payload = json.loads(path.read_text(encoding="utf-8"))
    rows = payload.get("runs", []) if isinstance(payload, dict) else []
    return [row for row in rows if isinstance(row, dict)]


def aggregate(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    keys = sorted({(row["system"], row["robot_count"]) for row in rows})
    result = []
    for system, robot_count in keys:
        selected = [row for row in rows if row["system"] == system and row["robot_count"] == robot_count]
        passed = [row for row in selected if row["status"] == "ok"]
        measured = [
            row for row in selected
            if row["status"] != "skipped" and row["topic_count"] > 0
        ]
        success_low, success_high = wilson_interval(len(passed), len(selected))
        control_delivery = metric_summary(
            measured, "control_delivery_ratio", lower_bound=0.0, upper_bound=1.0
        )
        state_delivery = metric_summary(
            measured, "state_delivery_ratio", lower_bound=0.0, upper_bound=1.0
        )
        min_topic_delivery = metric_summary(
            measured, "min_topic_delivery_ratio", lower_bound=0.0, upper_bound=1.0
        )
        control_latency = metric_summary(
            passed, "control_latency_ms_p95", lower_bound=0.0
        )
        state_latency = metric_summary(
            passed, "state_latency_ms_p95", lower_bound=0.0
        )
        result.append({
            "system": system,
            "robot_count": robot_count,
            "run_count": len(selected),
            "ok_run_count": len(passed),
            "measured_run_count": len(measured),
            "success_rate_mean": len(passed) / len(selected) if selected else 0.0,
            "success_rate_ci95_low": success_low,
            "success_rate_ci95_high": success_high,
            "control_delivery_ratio_mean": control_delivery["mean"],
            "control_delivery_ratio_ci95_low": control_delivery["ci95_low"],
            "control_delivery_ratio_ci95_high": control_delivery["ci95_high"],
            "state_delivery_ratio_mean": state_delivery["mean"],
            "state_delivery_ratio_ci95_low": state_delivery["ci95_low"],
            "state_delivery_ratio_ci95_high": state_delivery["ci95_high"],
            "min_topic_delivery_ratio_mean": min_topic_delivery["mean"],
            "min_topic_delivery_ratio_ci95_low": min_topic_delivery["ci95_low"],
            "min_topic_delivery_ratio_ci95_high": min_topic_delivery["ci95_high"],
            "control_latency_ms_p95_mean": control_latency["mean"],
            "control_latency_ms_p95_ci95_low": control_latency["ci95_low"],
            "control_latency_ms_p95_ci95_high": control_latency["ci95_high"],
            "state_latency_ms_p95_mean": state_latency["mean"],
            "state_latency_ms_p95_ci95_low": state_latency["ci95_low"],
            "state_latency_ms_p95_ci95_high": state_latency["ci95_high"],
            "reliability_modes": sorted({str(row["reliability_mode"]) for row in selected}),
        })
    return result


def render_markdown(summary: dict[str, Any]) -> str:
    lines = [
        "# Large-Scale ROS 2 RMW Comparison",
        "",
        summary["topology_note"],
        "",
        f"Comparison design: `{summary.get('comparison_design', 'legacy')}`; "
        f"cross-scope superiority allowed: `{str(summary.get('direct_claim_allowed', False)).lower()}`.",
        "",
        "| system | robots | reliability | runs OK | success rate [95% CI] | control delivery [95% CI] | state delivery [95% CI] | min-topic delivery [95% CI] | control p95 ms [95% CI] | state p95 ms [95% CI] |",
        "|---|---:|---|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for row in summary["aggregates"]:
        lines.append(
            f"| {row['system']} | {row['robot_count']} | "
            f"{','.join(row['reliability_modes'])} | {row['ok_run_count']}/{row['run_count']} | "
            f"{format_ci(row, 'success_rate', 3)} | "
            f"{format_ci(row, 'control_delivery_ratio', 4)} | "
            f"{format_ci(row, 'state_delivery_ratio', 4)} | "
            f"{format_ci(row, 'min_topic_delivery_ratio', 4)} | "
            f"{format_ci(row, 'control_latency_ms_p95', 3)} | "
            f"{format_ci(row, 'state_latency_ms_p95', 3)} |"
        )
    lines.extend([
        "",
        "Allowed scope 1: compare Fast DDS, Cyclone DDS, and Zenoh as direct-RMW delivery/latency baselines.",
        "Allowed scope 2: report FleetRMW router/reliability/fleet-control value on its own topology.",
        "Disallowed scope: claim FleetRMW superiority over direct DDS/Zenoh from this mixed-hop table.",
        "",
    ])
    return "\n".join(lines)


def mean(rows: list[dict[str, Any]], key: str) -> float:
    return statistics.fmean(row[key] for row in rows) if rows else 0.0


def metric_summary(
    rows: list[dict[str, Any]],
    key: str,
    *,
    lower_bound: float | None = None,
    upper_bound: float | None = None,
) -> dict[str, float | int]:
    values = [float(row[key]) for row in rows]
    if not values:
        return {"count": 0, "mean": 0.0, "ci95_low": 0.0, "ci95_high": 0.0}
    average = statistics.fmean(values)
    if len(values) == 1:
        low = high = average
    else:
        critical = {1: 12.706, 2: 4.303, 3: 3.182, 4: 2.776, 5: 2.571}.get(
            len(values) - 1,
            1.96,
        )
        margin = critical * statistics.stdev(values) / math.sqrt(len(values))
        low, high = average - margin, average + margin
    if lower_bound is not None:
        low = max(lower_bound, low)
    if upper_bound is not None:
        high = min(upper_bound, high)
    return {"count": len(values), "mean": average, "ci95_low": low, "ci95_high": high}


def wilson_interval(successes: int, total: int) -> tuple[float, float]:
    if total <= 0:
        return 0.0, 0.0
    z = 1.96
    proportion = successes / total
    denominator = 1.0 + z * z / total
    center = (proportion + z * z / (2.0 * total)) / denominator
    margin = z * math.sqrt(
        proportion * (1.0 - proportion) / total + z * z / (4.0 * total * total)
    ) / denominator
    return max(0.0, center - margin), min(1.0, center + margin)


def format_ci(row: dict[str, Any], prefix: str, precision: int) -> str:
    return (
        f"{row[f'{prefix}_mean']:.{precision}f} "
        f"[{row[f'{prefix}_ci95_low']:.{precision}f}, "
        f"{row[f'{prefix}_ci95_high']:.{precision}f}]"
    )


def number(value: object) -> float:
    try:
        return float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return 0.0


def parse_csv(value: str) -> list[str]:
    result = [item.strip() for item in value.split(",") if item.strip()]
    if not result:
        raise SystemExit("expected at least one comma-separated value")
    return list(dict.fromkeys(result))


def parse_csv_int(value: str, minimum: int = 1) -> list[int]:
    result = [int(item) for item in parse_csv(value)]
    if any(item < minimum for item in result):
        raise SystemExit(f"values must be >= {minimum}")
    return result


if __name__ == "__main__":
    raise SystemExit(main())

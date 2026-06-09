"""Compare FleetRMW-native live evidence with ROS 2 live-bridge baselines."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import Iterable

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


SCHEMA_VERSION = "fleetrmw.live_baseline_comparison.v1"
DEFAULT_FLEETRMW_SUMMARY = Path(
    "results_rmw_socket/docker_multi_robot_live_stochastic_netem_ablation_summary.json"
)
DEFAULT_FLEETRMW_MATCHED_SUMMARY = Path(
    "results_rmw_socket/docker_multi_robot_live_telemetry_matrix_4robot_summary.json"
)
DEFAULT_ROS2_SUMMARIES = {
    "wifi": Path("results_ros2_live_bridge/ros2_live_bridge_t3_repeated_packet_wifi_3seed_v1_summary.json"),
    "wan": Path("results_ros2_live_bridge/ros2_live_bridge_t3_repeated_packet_wan_3seed_v1_summary.json"),
    "roaming": Path(
        "results_ros2_live_bridge/ros2_live_bridge_t3_repeated_packet_roaming_3seed_v1_summary.json"
    ),
}
DEFAULT_DIRECT_SUMMARIES = [
    Path("results_rmw_socket/ros2_direct_rmw_netem_matrix_4robot_summary.json"),
    Path("results_rmw_socket/ros2_direct_rmw_netem_matrix_summary.json"),
]
DEFAULT_DIRECT_SMOKE_SUMMARIES = [
    Path("results_rmw_socket/ros2_direct_rmw_netem_matrix_smoke_summary.json"),
    Path("results_rmw_socket/ros2_direct_rmw_netem_matrix_fastrtps_wifi_smoke_summary.json"),
]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--fleetrmw-summary", type=Path, default=DEFAULT_FLEETRMW_SUMMARY)
    parser.add_argument(
        "--fleetrmw-matched-summary",
        type=Path,
        default=DEFAULT_FLEETRMW_MATCHED_SUMMARY,
        help="FleetRMW matched robot-count telemetry matrix summary.",
    )
    parser.add_argument(
        "--ros2-summary",
        action="append",
        help="ROS 2 live-bridge summary as profile:path. Defaults to wifi/wan/roaming summaries when present.",
    )
    parser.add_argument(
        "--direct-summary",
        action="append",
        type=Path,
        help="Direct ROS 2 RMW netem matrix summary. Defaults to the full matrix when present, otherwise smoke summaries.",
    )
    parser.add_argument(
        "--summary-json",
        type=Path,
        default=Path("results_rmw_socket/fleetrmw_live_baseline_comparison_summary.json"),
    )
    parser.add_argument(
        "--markdown",
        type=Path,
        default=Path("results_rmw_socket/fleetrmw_live_baseline_comparison_report.md"),
    )
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    ros2_inputs = parse_ros2_summary_args(args.ros2_summary)
    direct_inputs = parse_direct_summary_args(args.direct_summary)
    comparison = build_comparison(
        fleetrmw_summary_path=args.fleetrmw_summary,
        fleetrmw_matched_summary_path=args.fleetrmw_matched_summary,
        ros2_summary_paths=ros2_inputs,
        direct_summary_paths=direct_inputs,
    )
    write_json(comparison, args.summary_json)
    write_markdown(render_markdown(comparison), args.markdown)

    result = {
        "schema_version": comparison["schema_version"],
        "status": comparison["status"],
        "fleetrmw_rows": len(comparison["fleetrmw_mode_rows"]),
        "fleetrmw_matched_rows": len(comparison["fleetrmw_matched_rows"]),
        "ros2_rows": len(comparison["ros2_policy_rows"]),
        "direct_rows": len(comparison["direct_rmw_rows"]),
        "summary": str(args.summary_json),
        "markdown": str(args.markdown),
    }
    if args.json:
        print(json.dumps(result, sort_keys=True))
    else:
        print("fleetrmw-live-baseline-comparison")
        print(f"  status: {result['status']}")
        print(f"  fleetrmw rows: {result['fleetrmw_rows']}")
        print(f"  ros2 rows: {result['ros2_rows']}")
        print(f"  summary: {args.summary_json}")
    return 0 if comparison["status"] == "ok" else 1


def build_comparison(
    *,
    fleetrmw_summary_path: Path,
    fleetrmw_matched_summary_path: Path | None,
    ros2_summary_paths: dict[str, Path],
    direct_summary_paths: list[Path] | None = None,
) -> dict[str, object]:
    fleetrmw = read_json(fleetrmw_summary_path)
    fleetrmw_matched = (
        read_json(fleetrmw_matched_summary_path)
        if fleetrmw_matched_summary_path is not None and fleetrmw_matched_summary_path.exists()
        else {}
    )
    ros2_summaries = {
        profile: read_json(path)
        for profile, path in ros2_summary_paths.items()
        if path.exists()
    }
    direct_paths = list(direct_summary_paths or [])
    direct_summaries = [
        (path, read_json(path))
        for path in direct_paths
        if path.exists()
    ]
    fleetrmw_mode_rows = fleet_mode_rows(fleetrmw, source=fleetrmw_summary_path)
    fleetrmw_profile_rows = fleet_profile_rows(fleetrmw, source=fleetrmw_summary_path)
    fleetrmw_matched_rows = (
        fleet_matched_rows(fleetrmw_matched, source=fleetrmw_matched_summary_path)
        if fleetrmw_matched and fleetrmw_matched_summary_path is not None
        else []
    )
    ros2_policy_rows = []
    for profile, summary in sorted(ros2_summaries.items()):
        ros2_policy_rows.extend(ros2_rows_for_summary(summary, profile=profile, source=ros2_summary_paths[profile]))
    direct_rmw_rows = []
    for path, summary_data in direct_summaries:
        direct_rmw_rows.extend(direct_rows_for_summary(summary_data, source=path))
    summary = summarize_comparison(
        fleetrmw_mode_rows=fleetrmw_mode_rows,
        fleetrmw_profile_rows=fleetrmw_profile_rows,
        fleetrmw_matched_rows=fleetrmw_matched_rows,
        ros2_policy_rows=ros2_policy_rows,
        direct_rmw_rows=direct_rmw_rows,
    )
    return {
        "schema_version": SCHEMA_VERSION,
        "status": "ok" if fleetrmw_mode_rows and ros2_policy_rows else "partial",
        "inputs": {
            "fleetrmw_summary": str(fleetrmw_summary_path),
            "fleetrmw_matched_summary": str(fleetrmw_matched_summary_path)
            if fleetrmw_matched_summary_path is not None
            else "",
            "ros2_summaries": {
                profile: str(path)
                for profile, path in sorted(ros2_summary_paths.items())
            },
            "direct_summaries": [str(path) for path in direct_paths],
        },
        "comparability_contract": {
            "fleetrmw_native": "live ROS 2 rmw_fleetqox_cpp publisher-router-subscriber topology under tc netem",
            "fleetrmw_matched": "4-robot FleetRMW router/redundancy telemetry matrix under the same named profiles/seeds as the direct ROS 2 RMW 4-robot matrix",
            "ros2_live_bridge": "live ROS 2 sidecar/egress packet-format RMW matrix under named netem profiles",
            "direct_claim_allowed": False,
            "reason": "the 4-robot workload/profile/seed envelope is now matched, but topology and metric semantics still differ between direct single-path RMW rows and FleetRMW router/redundancy rows",
        },
        "fleetrmw_mode_rows": fleetrmw_mode_rows,
        "fleetrmw_profile_rows": fleetrmw_profile_rows,
        "fleetrmw_matched_rows": fleetrmw_matched_rows,
        "ros2_policy_rows": ros2_policy_rows,
        "direct_rmw_rows": direct_rmw_rows,
        "summary": summary,
    }


def fleet_mode_rows(data: dict[str, object], *, source: Path) -> list[dict[str, object]]:
    summary_ranking = _dict(data.get("summary")).get("ranking", [])
    mode_rows = (
        [row for row in summary_ranking if isinstance(row, dict)]
        if isinstance(summary_ranking, list) and summary_ranking
        else [row for row in data.get("mode_results", []) if isinstance(row, dict)]
    )
    rows = []
    for row in mode_rows:
        if not isinstance(row, dict):
            continue
        run_count = int(row.get("run_count", 0))
        ok_count = int(row.get("ok_run_count", 0))
        rows.append(
            {
                "evidence_family": "fleetrmw_native",
                "comparability": "native_router_topology",
                "profile": "all",
                "policy": f"rmw_fleetqox_cpp/{row.get('mode', '')}",
                "mode": row.get("mode", ""),
                "runs": run_count,
                "ok_runs": ok_count,
                "success_ratio": _ratio(ok_count, run_count),
                "delivery_metric": _ratio(ok_count, run_count),
                "delivery_metric_name": "row_success_ratio",
                "latency_metric_ms": _float(row.get("ok_control_delivery_latency_ms_mean"))
                + _float(row.get("ok_state_delivery_latency_ms_mean")),
                "latency_metric_name": "control_mean_plus_state_mean_ms",
                "control_latency_ms_mean": _float(row.get("ok_control_delivery_latency_ms_mean")),
                "state_latency_ms_mean": _float(row.get("ok_state_delivery_latency_ms_mean")),
                "max_all_profiles_ok_loss_scale": row.get("max_all_profiles_ok_loss_scale"),
                "repair_cost_frames_mean": _float(row.get("repair_cost_frames_mean")),
                "failure_kind_counts": _dict(row.get("failure_kind_counts")),
                "source": str(source),
            }
        )
    return rows


def fleet_profile_rows(data: dict[str, object], *, source: Path) -> list[dict[str, object]]:
    rows = []
    for item in data.get("sweeps", []):
        if not isinstance(item, dict):
            continue
        mode = str(item.get("mode", ""))
        sweep = _dict(item.get("sweep"))
        runs = [row for row in sweep.get("runs", []) if isinstance(row, dict)]
        by_profile: dict[str, list[dict[str, object]]] = {}
        for run in runs:
            by_profile.setdefault(str(run.get("profile", "")), []).append(run)
        for profile, group in sorted(by_profile.items()):
            run_count = len(group)
            ok_count = sum(1 for row in group if row.get("status") == "ok")
            rows.append(
                {
                    "evidence_family": "fleetrmw_native",
                    "comparability": "native_router_topology",
                    "profile": profile,
                    "policy": f"rmw_fleetqox_cpp/{mode}",
                    "mode": mode,
                    "runs": run_count,
                    "ok_runs": ok_count,
                    "success_ratio": _ratio(ok_count, run_count),
                    "delivery_metric": _ratio(ok_count, run_count),
                    "delivery_metric_name": "row_success_ratio",
                    "latency_metric_ms": _mean_metric(group, "control_delivery_latency_ms_mean", ok_only=True)
                    + _mean_metric(group, "state_delivery_latency_ms_mean", ok_only=True),
                    "latency_metric_name": "control_mean_plus_state_mean_ms",
                    "control_latency_ms_mean": _mean_metric(
                        group,
                        "control_delivery_latency_ms_mean",
                        ok_only=True,
                    ),
                    "state_latency_ms_mean": _mean_metric(
                        group,
                        "state_delivery_latency_ms_mean",
                        ok_only=True,
                    ),
                    "failure_kind_counts": _failure_kind_counts(group),
                    "max_ok_loss_scale": _max_ok_loss_scale(group),
                    "source": str(source),
                }
            )
    return rows


def fleet_matched_rows(data: dict[str, object], *, source: Path) -> list[dict[str, object]]:
    rows = []
    for row in data.get("runs", []):
        if not isinstance(row, dict):
            continue
        robot_count = int(row.get("robot_count", data.get("robot_count", 1)))
        control_expected = robot_count * int(row.get("control_payloads_per_publisher", 3))
        state_expected = robot_count * int(row.get("state_payloads_per_publisher", 3))
        control_delivery_ratio = min(1.0, _ratio(int(row.get("control_payload_count", 0)), control_expected))
        state_delivery_ratio = min(1.0, _ratio(int(row.get("state_payload_count", 0)), state_expected))
        terminal_horizon = _dict(row.get("terminal_horizon"))
        rows.append(
            {
                "evidence_family": "fleetrmw_native_matched",
                "comparability": "fleet_router_redundancy_4robot",
                "profile": str(row.get("profile", "")),
                "policy": "rmw_fleetqox_cpp/fleet_router_terminal_horizon",
                "status": str(row.get("status", "")),
                "runs": 1,
                "ok_runs": 1 if row.get("status") == "ok" else 0,
                "success_ratio": 1.0 if row.get("status") == "ok" else 0.0,
                "delivery_metric": min(control_delivery_ratio, state_delivery_ratio),
                "delivery_metric_name": "min_control_state_payload_ratio",
                "latency_metric_ms": _float(row.get("control_delivery_latency_ms_mean"))
                + _float(row.get("state_delivery_latency_ms_mean")),
                "latency_metric_name": "control_mean_plus_state_mean_ms",
                "control_delivery_ratio": control_delivery_ratio,
                "state_delivery_ratio": state_delivery_ratio,
                "control_latency_ms_mean": _float(row.get("control_delivery_latency_ms_mean")),
                "state_latency_ms_mean": _float(row.get("state_delivery_latency_ms_mean")),
                "control_payload_count": int(row.get("control_payload_count", 0)),
                "state_payload_count": int(row.get("state_payload_count", 0)),
                "control_expected_count": control_expected,
                "state_expected_count": state_expected,
                "robot_count": robot_count,
                "topic_count": int(row.get("topic_count", 0)),
                "state_terminal_guard_payload": str(row.get("state_terminal_guard_payload", "")),
                "terminal_guard_algorithm": str(row.get("terminal_guard_algorithm", "")),
                "terminal_guard_repeat_count": int(row.get("terminal_guard_repeat_count", 1)),
                "terminal_guard_router_dwell_ms": int(row.get("terminal_guard_router_dwell_ms", 0)),
                "terminal_guard_startup_settle_ms": int(
                    row.get(
                        "terminal_guard_startup_settle_ms",
                        terminal_horizon.get("startup_settle_ms", 0),
                    )
                ),
                "terminal_guard_pre_publish_wait_ms": int(
                    row.get(
                        "terminal_guard_pre_publish_wait_ms",
                        terminal_horizon.get("pre_publish_wait_ms", 0),
                    )
                ),
                "terminal_guard_app_repair_cycle_count": int(
                    row.get(
                        "terminal_guard_app_repair_cycle_count",
                        terminal_horizon.get("app_repair_cycle_count", 0),
                    )
                ),
                "terminal_guard_warmup_ack_count": int(
                    row.get(
                        "terminal_guard_warmup_ack_count",
                        terminal_horizon.get("pre_payload_warmup_ack_count", 0),
                    )
                ),
                "terminal_guard_warmup_ack_timeout_ms": int(
                    row.get(
                        "terminal_guard_warmup_ack_timeout_ms",
                        terminal_horizon.get("pre_payload_warmup_ack_timeout_ms", 0),
                    )
                ),
                "terminal_guard_required_sequence": int(row.get("terminal_guard_required_sequence", 0)),
                "terminal_horizon": terminal_horizon,
                "control_wire_payloads_per_publisher": int(
                    row.get("control_wire_payloads_per_publisher", row.get("control_payloads_per_publisher", 3))
                ),
                "state_wire_payloads_per_publisher": int(
                    row.get("state_wire_payloads_per_publisher", row.get("state_payloads_per_publisher", 3))
                ),
                "primary_expected_forwarded_topic_source_sequences": str(
                    row.get("primary_expected_forwarded_topic_source_sequences", "")
                ),
                "backup_expected_forwarded_topic_source_sequences": str(
                    row.get("backup_expected_forwarded_topic_source_sequences", "")
                ),
                "netem_applied": _all_netem_applied(_dict(row.get("netem_status"))),
                "source": str(source),
            }
        )
    return rows


def ros2_rows_for_summary(
    data: dict[str, object],
    *,
    profile: str,
    source: Path,
) -> list[dict[str, object]]:
    rows = []
    for row in data.get("policies", []):
        if not isinstance(row, dict):
            continue
        policy = str(row.get("policy", ""))
        rows.append(
            {
                "evidence_family": "ros2_live_bridge",
                "comparability": "indirect_named_profile",
                "profile": profile,
                "policy": policy,
                "packet_format": row.get("packet_format", policy.split("/", 1)[0] if "/" in policy else ""),
                "rmw": row.get("rmw", policy.split("/", 1)[1] if "/" in policy else ""),
                "runs": int(row.get("runs", 0)),
                "ok_runs": int(row.get("runs", 0)),
                "success_ratio": _float(row.get("control_delivery_ratio_mean")),
                "delivery_metric": _float(row.get("control_delivery_ratio_mean")),
                "delivery_metric_name": "control_delivery_ratio_mean",
                "latency_metric_ms": _float(row.get("latency_p95_ms_mean")),
                "latency_metric_name": "latency_p95_ms_mean",
                "latency_p95_ms_mean": _float(row.get("latency_p95_ms_mean")),
                "latency_p99_ms_mean": _float(row.get("latency_p99_ms_mean")),
                "loss_ratio_mean": _float(row.get("loss_ratio_mean")),
                "deadline_miss_ratio_mean": _float(row.get("deadline_miss_ratio_mean")),
                "semantic_utility_delivered_mean": _float(
                    row.get("semantic_utility_delivered_mean")
                ),
                "pareto_frontier": bool(row.get("pareto_frontier", False)),
                "source": str(source),
            }
        )
    return rows


def direct_rows_for_summary(data: dict[str, object], *, source: Path) -> list[dict[str, object]]:
    rows = []
    for row in data.get("runs", []):
        if not isinstance(row, dict):
            continue
        rows.append(
            {
                "evidence_family": "ros2_direct_rmw",
                "comparability": "direct_single_path_pubsub",
                "profile": str(row.get("profile", "")),
                "policy": str(row.get("rmw", "")),
                "rmw": str(row.get("rmw", "")),
                "status": str(row.get("status", "")),
                "reason": str(row.get("reason", "")),
                "runs": 1,
                "ok_runs": 1 if row.get("status") == "ok" else 0,
                "skipped_runs": 1 if row.get("status") == "skipped" else 0,
                "failed_runs": 1 if row.get("status") not in {"ok", "skipped"} else 0,
                "success_ratio": 1.0 if row.get("status") == "ok" else 0.0,
                "delivery_metric": min(
                    _float(row.get("control_delivery_ratio")),
                    _float(row.get("state_delivery_ratio")),
                ),
                "delivery_metric_name": "min_control_state_delivery_ratio",
                "latency_metric_ms": _float(row.get("control_latency_ms_p95"))
                + _float(row.get("state_latency_ms_p95")),
                "latency_metric_name": "control_p95_plus_state_p95_ms",
                "control_delivery_ratio": _float(row.get("control_delivery_ratio")),
                "state_delivery_ratio": _float(row.get("state_delivery_ratio")),
                "control_latency_ms_p95": _float(row.get("control_latency_ms_p95")),
                "state_latency_ms_p95": _float(row.get("state_latency_ms_p95")),
                "netem_applied": bool(row.get("netem_applied", False)),
                "source": str(source),
            }
        )
    return rows


def summarize_comparison(
    *,
    fleetrmw_mode_rows: list[dict[str, object]],
    fleetrmw_profile_rows: list[dict[str, object]],
    fleetrmw_matched_rows: list[dict[str, object]],
    ros2_policy_rows: list[dict[str, object]],
    direct_rmw_rows: list[dict[str, object]] | None = None,
) -> dict[str, object]:
    direct_rows = list(direct_rmw_rows or [])
    fleet_best = min(
        fleetrmw_mode_rows,
        key=lambda row: (
            -_float(row.get("success_ratio")),
            _float(row.get("latency_metric_ms")),
            _float(row.get("repair_cost_frames_mean")),
        ),
        default={},
    )
    ros2_winners = []
    for profile in sorted({str(row.get("profile", "")) for row in ros2_policy_rows}):
        group = [row for row in ros2_policy_rows if row.get("profile") == profile]
        if not group:
            continue
        winner = min(
            group,
            key=lambda row: (
                not bool(row.get("pareto_frontier", False)),
                -_float(row.get("semantic_utility_delivered_mean")),
                -_float(row.get("delivery_metric")),
                _float(row.get("latency_metric_ms")),
            ),
        )
        ros2_winners.append(winner)
    return {
        "fleetrmw_best_policy": fleet_best.get("policy", ""),
        "fleetrmw_best_success_ratio": fleet_best.get("success_ratio", 0.0),
        "fleetrmw_best_latency_metric_ms": fleet_best.get("latency_metric_ms", 0.0),
        "ros2_profile_winners": ros2_winners,
        "direct_rmw_rows": direct_rows,
        "fleetrmw_profiles": summarize_profile_best(fleetrmw_profile_rows),
        "fleetrmw_matched_profiles": summarize_matched_profiles(fleetrmw_matched_rows),
        "research_gaps": research_gaps(
            fleetrmw_mode_rows,
            ros2_policy_rows,
            direct_rows,
            fleetrmw_matched_rows,
        ),
    }


def summarize_profile_best(rows: list[dict[str, object]]) -> list[dict[str, object]]:
    winners = []
    for profile in sorted({str(row.get("profile", "")) for row in rows}):
        group = [row for row in rows if row.get("profile") == profile]
        if not group:
            continue
        winners.append(
            min(
                group,
                key=lambda row: (
                    -_float(row.get("success_ratio")),
                    _float(row.get("latency_metric_ms")),
                    _float(row.get("repair_cost_frames_mean")),
                ),
            )
        )
    return winners


def summarize_matched_profiles(rows: list[dict[str, object]]) -> list[dict[str, object]]:
    summaries = []
    for profile in sorted({str(row.get("profile", "")) for row in rows}):
        group = [row for row in rows if row.get("profile") == profile]
        if not group:
            continue
        run_count = len(group)
        ok_count = sum(1 for row in group if row.get("status") == "ok")
        summaries.append(
            {
                "profile": profile,
                "policy": "rmw_fleetqox_cpp/fleet_router_terminal_horizon",
                "runs": run_count,
                "ok_runs": ok_count,
                "success_ratio": _ratio(ok_count, run_count),
                "delivery_metric": sum(_float(row.get("delivery_metric")) for row in group) / run_count,
                "control_latency_ms_mean": _mean_metric(
                    group,
                    "control_latency_ms_mean",
                    ok_only=True,
                ),
                "state_latency_ms_mean": _mean_metric(
                    group,
                    "state_latency_ms_mean",
                    ok_only=True,
                ),
                "latency_metric_ms": _mean_metric(group, "latency_metric_ms", ok_only=True),
                "netem_applied_runs": sum(1 for row in group if row.get("netem_applied")),
                "robot_count": max(int(row.get("robot_count", 0)) for row in group),
                "terminal_guard_algorithm": next(
                    (
                        str(row.get("terminal_guard_algorithm", ""))
                        for row in group
                        if row.get("terminal_guard_algorithm")
                    ),
                    "",
                ),
                "terminal_guard_repeat_count_mean": _mean_metric(
                    group,
                    "terminal_guard_repeat_count",
                    ok_only=False,
                ),
                "terminal_guard_router_dwell_ms_mean": _mean_metric(
                    group,
                    "terminal_guard_router_dwell_ms",
                    ok_only=False,
                ),
                "terminal_guard_startup_settle_ms_mean": _mean_metric(
                    group,
                    "terminal_guard_startup_settle_ms",
                    ok_only=False,
                ),
                "terminal_guard_pre_publish_wait_ms_mean": _mean_metric(
                    group,
                    "terminal_guard_pre_publish_wait_ms",
                    ok_only=False,
                ),
                "terminal_guard_app_repair_cycle_count_mean": _mean_metric(
                    group,
                    "terminal_guard_app_repair_cycle_count",
                    ok_only=False,
                ),
                "terminal_guard_warmup_ack_count_mean": _mean_metric(
                    group,
                    "terminal_guard_warmup_ack_count",
                    ok_only=False,
                ),
                "terminal_guard_warmup_ack_timeout_ms_mean": _mean_metric(
                    group,
                    "terminal_guard_warmup_ack_timeout_ms",
                    ok_only=False,
                ),
                "state_terminal_guard_payload": next(
                    (
                        str(row.get("state_terminal_guard_payload", ""))
                        for row in group
                        if row.get("state_terminal_guard_payload")
                    ),
                    "",
                ),
                "source": str(group[0].get("source", "")),
            }
        )
    return summaries


def research_gaps(
    fleetrmw_mode_rows: list[dict[str, object]],
    ros2_policy_rows: list[dict[str, object]],
    direct_rmw_rows: list[dict[str, object]] | None = None,
    fleetrmw_matched_rows: list[dict[str, object]] | None = None,
) -> list[str]:
    gaps = [
        "Direct DDS/Zenoh baselines are still needed under the same FleetRMW publisher-router-subscriber topology.",
        "Metric definitions differ: FleetRMW rows use row success and control/state delivery telemetry; ROS 2 live-bridge rows use sidecar control-delivery and p95/p99 latency.",
        "The next paper-grade claim must run the same profiles, seeds, loss scales, topics, and robot counts across rmw_fleetqox_cpp, Fast DDS, Cyclone DDS, and Zenoh.",
    ]
    if fleetrmw_mode_rows and ros2_policy_rows:
        gaps.append(
            "This report is valid as a baseline map and research-gap register, not as a direct superiority benchmark."
        )
    if direct_rmw_rows:
        gaps.append(
            "Direct ROS 2 RMW seed rows now exist, but they are still single-path pub/sub rows rather than matched FleetRMW router/redundancy rows."
        )
    if fleetrmw_matched_rows:
        gaps.append(
            "FleetRMW 4-robot router/redundancy rows now share the direct RMW 4-robot profile/seed envelope; the remaining gap is equalizing topology semantics and QoE metrics across middleware families."
        )
    return gaps


def parse_ros2_summary_args(values: list[str] | None) -> dict[str, Path]:
    if not values:
        return {
            profile: path
            for profile, path in DEFAULT_ROS2_SUMMARIES.items()
            if path.exists()
        }
    parsed: dict[str, Path] = {}
    for value in values:
        if ":" not in value:
            path = Path(value)
            parsed[infer_profile_from_path(path)] = path
            continue
        profile, path = value.split(":", 1)
        if not profile:
            raise SystemExit("--ros2-summary profile must be non-empty")
        parsed[profile] = Path(path)
    return parsed


def parse_direct_summary_args(values: list[Path] | None) -> list[Path]:
    if values:
        return values
    full_paths = [path for path in DEFAULT_DIRECT_SUMMARIES if path.exists()]
    if full_paths:
        return [full_paths[0]]
    return [path for path in DEFAULT_DIRECT_SMOKE_SUMMARIES if path.exists()]


def infer_profile_from_path(path: Path) -> str:
    text = path.name
    for profile in ("wifi", "wan", "roaming"):
        if profile in text:
            return profile
    return path.stem


def render_markdown(comparison: dict[str, object]) -> str:
    summary = _dict(comparison.get("summary"))
    contract = _dict(comparison.get("comparability_contract"))
    lines = [
        "# FleetRMW Live Baseline Comparison V1",
        "",
        f"- Status: `{comparison.get('status')}`",
        f"- Schema: `{comparison.get('schema_version')}`",
        f"- Direct claim allowed: `{contract.get('direct_claim_allowed')}`",
        f"- Reason: `{contract.get('reason')}`",
        f"- FleetRMW best policy: `{summary.get('fleetrmw_best_policy', '')}`",
        "",
        "## FleetRMW Native Modes",
        "",
        "| policy | ok/runs | success | latency metric ms | control mean ms | state mean ms | loss boundary | repair cost | failures |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---|",
    ]
    for row in comparison.get("fleetrmw_mode_rows", []):
        if not isinstance(row, dict):
            continue
        lines.append(
            "| "
            f"{row.get('policy')} | "
            f"{int(row.get('ok_runs', 0))}/{int(row.get('runs', 0))} | "
            f"{_format(row.get('success_ratio'))} | "
            f"{_format(row.get('latency_metric_ms'))} | "
            f"{_format(row.get('control_latency_ms_mean'))} | "
            f"{_format(row.get('state_latency_ms_mean'))} | "
            f"{_format_nullable(row.get('max_all_profiles_ok_loss_scale'))} | "
            f"{_format(row.get('repair_cost_frames_mean'))} | "
            f"{format_counts(_dict(row.get('failure_kind_counts')))} |"
        )
    matched_profiles = [
        row for row in summary.get("fleetrmw_matched_profiles", [])
        if isinstance(row, dict)
    ]
    if matched_profiles:
        lines.extend(
            [
                "",
                "## FleetRMW Matched 4-Robot Profile Rows",
                "",
                "| profile | policy | ok/runs | success | delivery | control mean ms | state mean ms | netem applied | horizon | guard |",
                "|---|---|---:|---:|---:|---:|---:|---:|---|---|",
            ]
        )
        for row in matched_profiles:
            horizon = (
                f"{row.get('terminal_guard_algorithm', '') or '-'} "
                f"r={_format(row.get('terminal_guard_repeat_count_mean'))} "
                f"a={_format(row.get('terminal_guard_app_repair_cycle_count_mean'))} "
                f"w={_format(row.get('terminal_guard_warmup_ack_count_mean'))}/"
                f"{_format(row.get('terminal_guard_warmup_ack_timeout_ms_mean'))}ms "
                f"d={_format(row.get('terminal_guard_router_dwell_ms_mean'))}ms "
                f"s={_format(row.get('terminal_guard_startup_settle_ms_mean'))}ms "
                f"p={_format(row.get('terminal_guard_pre_publish_wait_ms_mean'))}ms"
            )
            lines.append(
                "| "
                f"{row.get('profile')} | "
                f"{row.get('policy')} | "
                f"{int(row.get('ok_runs', 0))}/{int(row.get('runs', 0))} | "
                f"{_format(row.get('success_ratio'))} | "
                f"{_format(row.get('delivery_metric'))} | "
                f"{_format(row.get('control_latency_ms_mean'))} | "
                f"{_format(row.get('state_latency_ms_mean'))} | "
                f"{int(row.get('netem_applied_runs', 0))}/{int(row.get('runs', 0))} | "
                f"{horizon} | "
                f"{row.get('state_terminal_guard_payload', '') or '-'} |"
            )
    lines.extend(
        [
            "",
            "## ROS 2 Live-Bridge Profile Winners",
            "",
            "| profile | policy | runs | control delivery | p95 ms | p99 ms | loss | utility | pareto |",
            "|---|---|---:|---:|---:|---:|---:|---:|---:|",
        ]
    )
    for row in summary.get("ros2_profile_winners", []):
        if not isinstance(row, dict):
            continue
        lines.append(
            "| "
            f"{row.get('profile')} | "
            f"{row.get('policy')} | "
            f"{int(row.get('runs', 0))} | "
            f"{_format(row.get('delivery_metric'))} | "
            f"{_format(row.get('latency_p95_ms_mean'))} | "
            f"{_format(row.get('latency_p99_ms_mean'))} | "
            f"{_format(row.get('loss_ratio_mean'))} | "
            f"{_format(row.get('semantic_utility_delivered_mean'))} | "
            f"{bool(row.get('pareto_frontier', False))} |"
        )
    lines.extend(
        [
            "",
            "## FleetRMW Profile Winners",
            "",
            "| profile | policy | ok/runs | success | latency metric ms | max OK loss scale | failures |",
            "|---|---|---:|---:|---:|---:|---|",
        ]
    )
    for row in summary.get("fleetrmw_profiles", []):
        if not isinstance(row, dict):
            continue
        lines.append(
            "| "
            f"{row.get('profile')} | "
            f"{row.get('policy')} | "
            f"{int(row.get('ok_runs', 0))}/{int(row.get('runs', 0))} | "
            f"{_format(row.get('success_ratio'))} | "
            f"{_format(row.get('latency_metric_ms'))} | "
            f"{_format_nullable(row.get('max_ok_loss_scale'))} | "
            f"{format_counts(_dict(row.get('failure_kind_counts')))} |"
        )
    direct_rows = [row for row in summary.get("direct_rmw_rows", []) if isinstance(row, dict)]
    if direct_rows:
        lines.extend(
            [
                "",
                "## Direct ROS 2 RMW Seed Rows",
                "",
                "| source | rmw | profile | status | delivery min | control p95 ms | state p95 ms | netem applied | reason |",
                "|---|---|---|---|---:|---:|---:|---:|---|",
            ]
        )
        for row in direct_rows:
            lines.append(
                "| "
                f"{Path(str(row.get('source', ''))).name} | "
                f"{row.get('rmw')} | "
                f"{row.get('profile')} | "
                f"{row.get('status')} | "
                f"{_format(row.get('delivery_metric'))} | "
                f"{_format(row.get('control_latency_ms_p95'))} | "
                f"{_format(row.get('state_latency_ms_p95'))} | "
                f"{bool(row.get('netem_applied', False))} | "
                f"{row.get('reason', '') or '-'} |"
            )
    lines.extend(
        [
            "",
            "## Research Gaps",
            "",
        ]
    )
    lines.extend(f"- {gap}" for gap in summary.get("research_gaps", []))
    lines.append("")
    return "\n".join(lines)


def write_json(data: dict[str, object], output: Path) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def write_markdown(markdown: str, output: Path) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(markdown, encoding="utf-8")


def read_json(path: Path) -> dict[str, object]:
    with path.open("r", encoding="utf-8") as handle:
        data = json.load(handle)
    if not isinstance(data, dict):
        raise ValueError(f"{path} did not contain a JSON object")
    return data


def _failure_kind_counts(rows: Iterable[dict[str, object]]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for row in rows:
        if row.get("status") == "ok":
            continue
        kind = str(row.get("failure_kind", "unknown_failed"))
        counts[kind] = counts.get(kind, 0) + 1
    return counts


def _max_ok_loss_scale(rows: Iterable[dict[str, object]]) -> float | None:
    loss_scales = [
        _float(row.get("loss_scale"))
        for row in rows
        if row.get("status") == "ok"
    ]
    return max(loss_scales) if loss_scales else None


def _mean_metric(rows: Iterable[dict[str, object]], key: str, *, ok_only: bool) -> float:
    values = []
    for row in rows:
        if ok_only and row.get("status") != "ok":
            continue
        values.append(_float(row.get(key)))
    return sum(values) / len(values) if values else 0.0


def format_counts(counts: dict[str, object]) -> str:
    if not counts:
        return "-"
    return ",".join(f"{key}:{int(_float(value))}" for key, value in sorted(counts.items()))


def _dict(value: object) -> dict[str, object]:
    return value if isinstance(value, dict) else {}


def _all_netem_applied(statuses: dict[str, object]) -> bool:
    if not statuses:
        return False
    return all(_dict(value).get("status") == "applied" for value in statuses.values())


def _float(value: object) -> float:
    try:
        return float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return 0.0


def _ratio(numerator: int, denominator: int) -> float:
    return numerator / denominator if denominator else 0.0


def _format(value: object) -> str:
    return f"{_float(value):.3f}"


def _format_nullable(value: object) -> str:
    if value is None or value == "":
        return "-"
    return _format(value)


if __name__ == "__main__":
    raise SystemExit(main())

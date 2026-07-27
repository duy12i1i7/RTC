"""Compare FleetRMW and ROS 2 baselines with a publisher-middle-subscriber hop count."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.run_large_scale_rmw_comparison import (  # noqa: E402
    DEFAULT_RMWS,
    aggregate,
    format_ci,
    load_prior_rows,
    normalize_row,
    parse_csv,
    parse_csv_int,
    row_needs_infrastructure_rerun,
)
from scripts.run_rmw_docker_router_matched_multi_topic_probe import (  # noqa: E402
    DEFAULT_IMAGE,
    cleanup_reusable_build,
    run_probe as run_fleetrmw,
)
from scripts.run_ros2_relay_rmw_netem_probe import run_probe as run_relay  # noqa: E402


SCHEMA_VERSION = "fleetrmw.same_hop_rmw_comparison.v2"


def should_reuse_prior_row(
    row: dict[str, Any] | None,
    *,
    rerun_failed_rows: bool,
) -> bool:
    return (
        row is not None
        and not (rerun_failed_rows and row.get("status") == "failed")
        and not row_needs_infrastructure_rerun(row)
    )


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
    rerun_failed_rows: bool = False,
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
                if should_reuse_prior_row(
                    prior_fleet,
                    rerun_failed_rows=rerun_failed_rows,
                ):
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
                    rows.append(
                        normalize_row(fleet, system="rmw_fleetqox_cpp_router")
                    )
                for rmw in rmws:
                    key = (rmw, robot_count, seed)
                    prior = prior_index.get(key)
                    if should_reuse_prior_row(
                        prior,
                        rerun_failed_rows=rerun_failed_rows,
                    ):
                        rows.append(prior)
                        print(f"reuse {key}", file=sys.stderr, flush=True)
                        continue
                    print(f"run {key}", file=sys.stderr, flush=True)
                    baseline = run_relay(
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
                        relay_mode="generic_serialized",
                    )
                    rows.append(normalize_row(baseline, system=rmw))
    finally:
        cleanup_reusable_build(root=root, image=image)

    aggregates = aggregate(rows)
    ok_count = sum(row["status"] == "ok" for row in rows)
    skipped_count = sum(row["status"] == "skipped" for row in rows)
    failed_count = len(rows) - ok_count - skipped_count
    relay_results = [
        row.get("result", {})
        for row in rows
        if row.get("system") != "rmw_fleetqox_cpp_router"
        and isinstance(row.get("result"), dict)
    ]
    relay_expected_count = sum(
        int(result.get("relay_expected_count", 0)) for result in relay_results
    )
    relay_payload_count = sum(
        int(result.get("relay_payload_count", 0)) for result in relay_results
    )
    serialized_relay_result_count = sum(
        result.get("relay_scope") == "rclcpp_generic_serialized_passthrough"
        and result.get("middle_payload_remains_serialized") is True
        and result.get("middle_application_deserialization") is False
        for result in relay_results
    )
    expected_relay_result_count = sum(
        row.get("system") != "rmw_fleetqox_cpp_router" for row in rows
    )
    serialized_relay_contract_ok = (
        expected_relay_result_count > 0
        and len(relay_results) == expected_relay_result_count
        and serialized_relay_result_count == expected_relay_result_count
    )
    publisher_results = [
        result.get("publisher", {})
        for row in rows
        if isinstance(row.get("result"), dict)
        for result in [row["result"]]
        if isinstance(result.get("publisher"), dict)
    ]
    publisher_ack_wait_supported_count = sum(
        publisher.get("ack_wait_supported") is True
        for publisher in publisher_results
    )
    publisher_ack_wait_complete_count = sum(
        publisher.get("ack_wait_complete") is True
        and int(publisher.get("unacked_topic_count", -1)) == 0
        for publisher in publisher_results
    )
    publisher_ack_horizon_contract_ok = (
        len(publisher_results) == len(rows)
        and publisher_ack_wait_supported_count == len(rows)
        and publisher_ack_wait_complete_count == len(rows)
    )
    status = "ok" if rows and failed_count == 0 and skipped_count == 0 else "partial"
    if status == "ok" and (
        not serialized_relay_contract_ok or
        not publisher_ack_horizon_contract_ok
    ):
        status = "partial"
    if rows and ok_count == 0:
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
        "comparison_design": "matched_one_middle_hop_caveated",
        "hop_count_matched": True,
        "source_netem_profile_matched": True,
        "reliable_qos_matched": True,
        "publisher_reliability_horizon_s": 6.0,
        "publisher_reliability_horizon_mode":
            "bounded_wait_for_all_acked",
        "prior_row_count": len(prior_rows or []),
        "rerun_failed_rows": rerun_failed_rows,
        "publisher_ack_wait_supported_count":
            publisher_ack_wait_supported_count,
        "publisher_ack_wait_complete_count":
            publisher_ack_wait_complete_count,
        "publisher_ack_horizon_contract_ok":
            publisher_ack_horizon_contract_ok,
        "relay_scope": "rclcpp_generic_serialized_passthrough",
        "relay_expected_count": relay_expected_count,
        "relay_payload_count": relay_payload_count,
        "serialized_relay_result_count": serialized_relay_result_count,
        "serialized_relay_contract_ok": serialized_relay_contract_ok,
        "middle_payload_serialization_state_matched":
            serialized_relay_contract_ok,
        "middle_application_deserialization":
            False if serialized_relay_contract_ok else None,
        "middle_hop_processing_equivalent": False,
        "direct_claim_allowed": False,
        "delivery_reliability_comparison_allowed": True,
        "latency_superiority_claim_allowed": False,
        "topology_note": (
            "Every row uses publisher-middle-subscriber and applies the same source-side "
            "netem profile with ROS QoS RELIABLE and a six-second publisher horizon. "
            "FleetRMW's middle is a raw FleetRMW router; DDS/Zenoh use a common "
            "rclcpp generic serialized-message relay with no application-message "
            "deserialization. Hop count and opaque serialized payload handling are matched, "
            "but transport-envelope termination/republish still differs from raw frame "
            "forwarding, so delivery/reliability comparison is allowed and broad latency "
            "or architectural superiority remains disallowed."
        ),
        "claim_scopes": {
            "matched_hop_delivery_reliability": {
                "allowed": True,
                "topology": "publisher-middle-subscriber",
            },
            "latency_superiority": {
                "allowed": False,
                "reason": (
                    "raw FleetRMW frame forwarding versus generic serialized "
                    "RMW termination/republish"
                ),
            },
            "architectural_superiority": {
                "allowed": False,
                "reason": "middle implementation semantics differ",
            },
        },
        "run_count": len(rows),
        "ok_run_count": ok_count,
        "skipped_run_count": skipped_count,
        "failed_run_count": failed_count,
        "aggregates": aggregates,
        "runs": rows,
    }


def render_markdown(summary: dict[str, Any]) -> str:
    lines = [
        "# Same-Hop ROS 2 RMW Comparison",
        "",
        summary["topology_note"],
        "",
        "| system | robots | reliability | runs OK | success rate [95% CI] | control delivery [95% CI] | state delivery [95% CI] | min-topic delivery [95% CI] | control p95 ms [95% CI] | state p95 ms [95% CI] |",
        "|---|---:|---|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for row in summary["aggregates"]:
        lines.append(
            f"| {row['system']} | {row['robot_count']} | "
            f"{','.join(row['reliability_modes'])} | "
            f"{row['ok_run_count']}/{row['run_count']} | "
            f"{format_ci(row, 'success_rate', 3)} | "
            f"{format_ci(row, 'control_delivery_ratio', 4)} | "
            f"{format_ci(row, 'state_delivery_ratio', 4)} | "
            f"{format_ci(row, 'min_topic_delivery_ratio', 4)} | "
            f"{format_ci(row, 'control_latency_ms_p95', 3)} | "
            f"{format_ci(row, 'state_latency_ms_p95', 3)} |"
        )
    lines.extend(
        [
            "",
            "Allowed: compare delivery and reliability under the matched one-middle-hop envelope.",
            "Disallowed: infer latency or architectural superiority because FleetRMW forwards raw frames while baseline relays terminate and republish opaque serialized ROS messages through an RMW endpoint.",
            "",
        ]
    )
    return "\n".join(lines)


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
        default="results_rmw_socket/same_hop_rmw_comparison_summary.json",
    )
    parser.add_argument(
        "--markdown",
        default="results_rmw_socket/same_hop_rmw_comparison_report.md",
    )
    parser.add_argument("--resume-summary", type=Path)
    parser.add_argument(
        "--rerun-failed",
        action="store_true",
        help=(
            "rerun measured failed rows from --resume-summary after an "
            "implementation change; failures are retained by default"
        ),
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
        rerun_failed_rows=args.rerun_failed,
    )
    summary_path = ROOT / args.summary_json
    markdown_path = ROOT / args.markdown
    summary_path.parent.mkdir(parents=True, exist_ok=True)
    markdown_path.parent.mkdir(parents=True, exist_ok=True)
    summary_path.write_text(
        json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    markdown_path.write_text(render_markdown(summary), encoding="utf-8")
    if args.json:
        print(json.dumps(summary, sort_keys=True))
    else:
        print(
            f"status={summary['status']} ok={summary['ok_run_count']}/"
            f"{summary['run_count']}"
        )
    return 0 if summary["status"] in {"ok", "partial"} else 1


if __name__ == "__main__":
    raise SystemExit(main())

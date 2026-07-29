"""Compare FleetRMW and ROS 2 baselines with a publisher-middle-subscriber hop count."""

from __future__ import annotations

import argparse
import json
import math
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
    normalize_row,
    parse_csv,
    parse_csv_int,
    row_needs_infrastructure_rerun,
)
from scripts.run_rmw_docker_router_matched_multi_topic_probe import (  # noqa: E402
    DEFAULT_IMAGE,
    cleanup_reusable_build,
)
from scripts.run_ros2_relay_rmw_netem_probe import (  # noqa: E402
    FLEETQOX_RMW,
    run_probe as run_relay,
)


SCHEMA_VERSION = "fleetrmw.same_hop_rmw_comparison.v4"


def should_reuse_prior_row(
    row: dict[str, Any] | None,
    *,
    rerun_failed_rows: bool,
    image: str,
    profile: str,
    netem_loss_scale: float,
    samples: int,
    payload_bytes: int,
    publish_interval_ms: int,
) -> bool:
    return (
        row is not None
        and prior_row_matches_configuration(
            row,
            image=image,
            profile=profile,
            netem_loss_scale=netem_loss_scale,
            samples=samples,
            payload_bytes=payload_bytes,
            publish_interval_ms=publish_interval_ms,
        )
        and not (rerun_failed_rows and row.get("status") == "failed")
        and not row_needs_infrastructure_rerun(row)
    )


def load_same_hop_prior_rows(path: Path | None) -> list[dict[str, Any]]:
    if path is None:
        return []
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        return []
    configuration = {
        key: payload.get(key)
        for key in (
            "image",
            "profile",
            "netem_loss_scale",
            "samples",
            "payload_bytes",
            "publish_interval_ms",
            "timeout_s",
        )
    }
    rows = payload.get("runs", [])
    if not isinstance(rows, list):
        return []
    annotated: list[dict[str, Any]] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        copied = dict(row)
        copied["_resume_summary_configuration"] = configuration
        annotated.append(copied)
    return annotated


def prior_row_matches_configuration(
    row: dict[str, Any],
    *,
    image: str,
    profile: str,
    netem_loss_scale: float,
    samples: int,
    payload_bytes: int,
    publish_interval_ms: int,
) -> bool:
    result = row.get("result")
    if not isinstance(result, dict):
        return False
    summary = row.get("_resume_summary_configuration")
    if not isinstance(summary, dict):
        summary = {}

    def recorded(key: str, row_key: str | None = None) -> Any:
        value = result.get(key)
        if value is not None:
            return value
        if row_key is not None:
            value = row.get(row_key)
            if value is not None:
                return value
        return summary.get(key)

    try:
        recorded_loss_scale = float(recorded("netem_loss_scale"))
        recorded_samples = int(recorded("samples"))
        recorded_payload_bytes = int(recorded("payload_bytes") or 0)
        recorded_publish_interval_ms = int(recorded("publish_interval_ms"))
        recorded_publisher_linger_s = float(
            result.get("publisher_linger_s", -1.0)
        )
    except (TypeError, ValueError):
        return False
    return (
        recorded("image") == image
        and recorded("profile", "profile") == profile
        and math.isclose(
            recorded_loss_scale,
            netem_loss_scale,
            rel_tol=0.0,
            abs_tol=1e-12,
        )
        and recorded_samples == samples
        and recorded_payload_bytes == payload_bytes
        and recorded_publish_interval_ms == publish_interval_ms
        and result.get("relay_mode") == "generic_serialized"
        and result.get("relay_scope")
        == "rclcpp_generic_serialized_passthrough"
        and result.get("netem_enabled") is True
        and result.get("netem_required") is True
        and math.isclose(
            recorded_publisher_linger_s,
            6.0,
            rel_tol=0.0,
            abs_tol=1e-12,
        )
    )


def clean_reused_row(row: dict[str, Any]) -> dict[str, Any]:
    return {
        key: value
        for key, value in row.items()
        if key != "_resume_summary_configuration"
    }


def middle_termination_republish_evidence(
    result: dict[str, Any],
) -> str | None:
    """Return the auditable evidence source for the generic RMW middle contract."""
    if result.get("middle_rmw_termination_republish") is True:
        return "explicit_runner_field"
    relay = result.get("relay")
    if not isinstance(relay, dict):
        return None
    if (
        result.get("relay_scope") == "rclcpp_generic_serialized_passthrough"
        and result.get("middle_payload_remains_serialized") is True
        and result.get("middle_application_deserialization") is False
        and relay.get("schema_version")
        == "fleetrmw.generic_serialized_relay_probe.v1"
        and relay.get("relay_scope")
        == "rclcpp_generic_serialized_passthrough"
        and relay.get("generic_subscription") is True
        and relay.get("generic_publisher") is True
        and relay.get("application_deserialization") is False
    ):
        return "strict_generic_relay_contract"
    return None


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
    payload_bytes: int = 0,
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
    reused_row_count = 0
    executed_row_count = 0
    resume_configuration_mismatch_count = 0
    try:
        for robot_count in robot_counts:
            for seed in seeds:
                fleet_key = (FLEETQOX_RMW, robot_count, seed)
                prior_fleet = prior_index.get(fleet_key)
                if should_reuse_prior_row(
                    prior_fleet,
                    rerun_failed_rows=rerun_failed_rows,
                    image=image,
                    profile=profile,
                    netem_loss_scale=netem_loss_scale,
                    samples=samples,
                    payload_bytes=payload_bytes,
                    publish_interval_ms=publish_interval_ms,
                ):
                    rows.append(clean_reused_row(prior_fleet))
                    reused_row_count += 1
                    print(f"reuse {fleet_key}", file=sys.stderr, flush=True)
                else:
                    if prior_fleet is not None and not prior_row_matches_configuration(
                        prior_fleet,
                        image=image,
                        profile=profile,
                        netem_loss_scale=netem_loss_scale,
                        samples=samples,
                        payload_bytes=payload_bytes,
                        publish_interval_ms=publish_interval_ms,
                    ):
                        resume_configuration_mismatch_count += 1
                    print(f"run {fleet_key}", file=sys.stderr, flush=True)
                    fleet = run_relay(
                        root=root,
                        image=image,
                        rmw=FLEETQOX_RMW,
                        profile=profile,
                        enable_netem=True,
                        require_netem=True,
                        netem_loss_scale=netem_loss_scale,
                        repetition_seed=seed,
                        samples=samples,
                        robot_count=robot_count,
                        payload_bytes=payload_bytes,
                        publish_interval_ms=publish_interval_ms,
                        timeout_s=timeout_s,
                        publisher_linger_s=6.0,
                        relay_mode="generic_serialized",
                    )
                    rows.append(normalize_row(fleet, system=FLEETQOX_RMW))
                    executed_row_count += 1
                for rmw in rmws:
                    key = (rmw, robot_count, seed)
                    prior = prior_index.get(key)
                    if should_reuse_prior_row(
                        prior,
                        rerun_failed_rows=rerun_failed_rows,
                        image=image,
                        profile=profile,
                        netem_loss_scale=netem_loss_scale,
                        samples=samples,
                        payload_bytes=payload_bytes,
                        publish_interval_ms=publish_interval_ms,
                    ):
                        rows.append(clean_reused_row(prior))
                        reused_row_count += 1
                        print(f"reuse {key}", file=sys.stderr, flush=True)
                        continue
                    if prior is not None and not prior_row_matches_configuration(
                        prior,
                        image=image,
                        profile=profile,
                        netem_loss_scale=netem_loss_scale,
                        samples=samples,
                        payload_bytes=payload_bytes,
                        publish_interval_ms=publish_interval_ms,
                    ):
                        resume_configuration_mismatch_count += 1
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
                        payload_bytes=payload_bytes,
                        publish_interval_ms=publish_interval_ms,
                        timeout_s=timeout_s,
                        publisher_linger_s=6.0,
                        relay_mode="generic_serialized",
                    )
                    rows.append(normalize_row(baseline, system=rmw))
                    executed_row_count += 1
    finally:
        cleanup_reusable_build(root=root, image=image)

    aggregates = aggregate(rows)
    ok_count = sum(row["status"] == "ok" for row in rows)
    skipped_count = sum(row["status"] == "skipped" for row in rows)
    failed_count = len(rows) - ok_count - skipped_count
    relay_results = [
        row.get("result", {})
        for row in rows
        if isinstance(row.get("result"), dict)
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
    expected_relay_result_count = len(rows)
    serialized_relay_contract_ok = (
        expected_relay_result_count > 0
        and len(relay_results) == expected_relay_result_count
        and serialized_relay_result_count == expected_relay_result_count
    )
    middle_termination_evidence = [
        middle_termination_republish_evidence(result)
        for result in relay_results
    ]
    middle_termination_republish_result_count = sum(
        evidence is not None for evidence in middle_termination_evidence
    )
    middle_termination_republish_explicit_result_count = (
        middle_termination_evidence.count("explicit_runner_field")
    )
    middle_termination_republish_derived_result_count = (
        middle_termination_evidence.count("strict_generic_relay_contract")
    )
    middle_termination_republish_contract_ok = (
        len(relay_results) == len(rows)
        and middle_termination_republish_result_count == len(rows)
    )
    middle_processing_equivalent = (
        serialized_relay_contract_ok
        and middle_termination_republish_contract_ok
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
    payload_size_contract_ok = (
        len(relay_results) == len(rows)
        and (
            payload_bytes == 0
            or all(
                result.get("payload_size_contract_ok") is True
                for result in relay_results
            )
        )
    )
    status = "ok" if rows and failed_count == 0 and skipped_count == 0 else "partial"
    if status == "ok" and (
        not serialized_relay_contract_ok or
        not middle_termination_republish_contract_ok or
        not publisher_ack_horizon_contract_ok or
        not payload_size_contract_ok
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
        "systems": [FLEETQOX_RMW, *rmws],
        "profile": profile,
        "netem_loss_scale": netem_loss_scale,
        "samples": samples,
        "payload_bytes": payload_bytes,
        "payload_size_contract_ok": payload_size_contract_ok,
        "publish_interval_ms": publish_interval_ms,
        "timeout_s": timeout_s,
        "comparison_design": "matched_generic_serialized_rmw_middle",
        "hop_count_matched": True,
        "source_netem_profile_matched": True,
        "reliable_qos_matched": True,
        "publisher_reliability_horizon_s": 6.0,
        "publisher_reliability_horizon_mode":
            "bounded_wait_for_all_acked",
        "prior_row_count": len(prior_rows or []),
        "reused_row_count": reused_row_count,
        "executed_row_count": executed_row_count,
        "resume_configuration_mismatch_count":
            resume_configuration_mismatch_count,
        "resume_configuration_match_contract_ok":
            reused_row_count + executed_row_count == len(rows),
        "resume_configuration_validation_enabled": True,
        "resume_configuration_fields": [
            "image",
            "profile",
            "netem_loss_scale",
            "samples",
            "payload_bytes",
            "publish_interval_ms",
            "relay_mode",
            "relay_scope",
            "netem_enabled",
            "netem_required",
            "publisher_linger_s",
        ],
        "resume_configuration_mismatch_policy":
            "execute_current_configuration",
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
        "middle_rmw_termination_republish_result_count":
            middle_termination_republish_result_count,
        "middle_rmw_termination_republish_explicit_result_count":
            middle_termination_republish_explicit_result_count,
        "middle_rmw_termination_republish_derived_result_count":
            middle_termination_republish_derived_result_count,
        "middle_rmw_termination_republish_contract_ok":
            middle_termination_republish_contract_ok,
        "middle_hop_processing_equivalent": middle_processing_equivalent,
        "direct_claim_allowed": False,
        "delivery_reliability_comparison_allowed": True,
        "latency_comparison_allowed": middle_processing_equivalent,
        "latency_superiority_claim_allowed": False,
        "topology_note": (
            "Every row uses publisher-middle-subscriber and applies the same source-side "
            "netem profile with ROS QoS RELIABLE and a six-second publisher horizon. "
            "FleetRMW, Fast DDS, Cyclone DDS, and Zenoh all use the same rclcpp generic "
            "serialized-message relay with no application-message deserialization. Every "
            "middle terminates an RMW subscription and republishes through an RMW publisher. "
            "Hop count, opaque payload state, and middle application processing are matched, "
            "so delivery/reliability and scoped latency distributions are comparable. Broad "
            "latency or architectural superiority remains disallowed without larger "
            "pre-registered repetition and sensitivity campaigns."
        ),
        "claim_scopes": {
            "matched_hop_delivery_reliability": {
                "allowed": True,
                "topology": "publisher-middle-subscriber",
            },
            "latency_superiority": {
                "allowed": False,
                "reason": (
                    "three repetitions per cell do not establish broad "
                    "production superiority"
                ),
            },
            "architectural_superiority": {
                "allowed": False,
                "reason": "matched middle processing does not imply architectural superiority",
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
        control_latency = (
            format_ci(row, "control_latency_ms_p95", 3)
            if row["ok_run_count"] > 0
            else "n/a"
        )
        state_latency = (
            format_ci(row, "state_latency_ms_p95", 3)
            if row["ok_run_count"] > 0
            else "n/a"
        )
        lines.append(
            f"| {row['system']} | {row['robot_count']} | "
            f"{','.join(row['reliability_modes'])} | "
            f"{row['ok_run_count']}/{row['run_count']} | "
            f"{format_ci(row, 'success_rate', 3)} | "
            f"{format_ci(row, 'control_delivery_ratio', 4)} | "
            f"{format_ci(row, 'state_delivery_ratio', 4)} | "
            f"{format_ci(row, 'min_topic_delivery_ratio', 4)} | "
            f"{control_latency} | "
            f"{state_latency} |"
        )
    lines.extend(
        [
            "",
            "Allowed: compare delivery and reliability under the matched one-middle-hop envelope.",
            "Allowed: compare scoped latency distributions because every system terminates and republishes opaque serialized ROS messages through the same generic relay.",
            "Disallowed: infer broad latency or architectural superiority without larger pre-registered repetition and sensitivity campaigns.",
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
    parser.add_argument(
        "--payload-bytes",
        type=int,
        default=0,
        help="exact UTF-8 message data size; zero preserves the metadata-only payload",
    )
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
        payload_bytes=max(args.payload_bytes, 0),
        publish_interval_ms=max(args.publish_interval_ms, 0),
        timeout_s=max(args.timeout_s, 1.0),
        prior_rows=load_same_hop_prior_rows(args.resume_summary),
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

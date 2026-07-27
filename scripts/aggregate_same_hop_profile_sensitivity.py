"""Aggregate configuration-matched same-hop RMW network-profile summaries."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
SCHEMA_VERSION = "fleetrmw.same_hop_profile_sensitivity.v1"
EXPECTED_PROFILES = ("wifi", "wan", "roaming")
EXPECTED_SYSTEMS = (
    "rmw_fleetqox_cpp",
    "rmw_fastrtps_cpp",
    "rmw_cyclonedds_cpp",
    "rmw_zenoh_cpp",
)


def load_summary(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"{path}: summary must be a JSON object")
    return payload


def aggregate_summaries(
    summaries: list[tuple[Path, dict[str, Any]]],
) -> dict[str, Any]:
    if len(summaries) != len(EXPECTED_PROFILES):
        raise ValueError("exactly wifi, wan, and roaming summaries are required")
    by_profile = {str(summary.get("profile")): (path, summary) for path, summary in summaries}
    if set(by_profile) != set(EXPECTED_PROFILES):
        raise ValueError("profiles must be exactly wifi, wan, and roaming")

    reference: dict[str, Any] | None = None
    rows: list[dict[str, Any]] = []
    aggregates: list[dict[str, Any]] = []
    source_artifacts: list[dict[str, Any]] = []
    for profile in EXPECTED_PROFILES:
        path, summary = by_profile[profile]
        if summary.get("schema_version") != "fleetrmw.same_hop_rmw_comparison.v4":
            raise ValueError(f"{path}: unsupported same-hop schema")
        if summary.get("status") != "ok":
            raise ValueError(f"{path}: source status is not ok")
        if summary.get("robot_counts") != [16]:
            raise ValueError(f"{path}: expected only the 16-robot cell")
        if tuple(summary.get("systems", ())) != EXPECTED_SYSTEMS:
            raise ValueError(f"{path}: system set or order differs")
        if summary.get("run_count") != 12 or summary.get("ok_run_count") != 12:
            raise ValueError(f"{path}: expected 12/12 rows")
        if not all(
            summary.get(key) is True
            for key in (
                "serialized_relay_contract_ok",
                "middle_rmw_termination_republish_contract_ok",
                "publisher_ack_horizon_contract_ok",
                "middle_hop_processing_equivalent",
                "latency_comparison_allowed",
                "resume_configuration_validation_enabled",
            )
        ):
            raise ValueError(f"{path}: required common-middle contract is false")
        configuration = {
            key: summary.get(key)
            for key in (
                "image",
                "netem_loss_scale",
                "samples",
                "publish_interval_ms",
                "timeout_s",
                "publisher_reliability_horizon_s",
                "relay_scope",
            )
        }
        if reference is None:
            reference = configuration
        elif configuration != reference:
            raise ValueError(f"{path}: non-profile configuration differs")
        source_rows = summary.get("runs")
        if not isinstance(source_rows, list) or len(source_rows) != 12:
            raise ValueError(f"{path}: missing source rows")
        if any(row.get("profile") != profile for row in source_rows):
            raise ValueError(f"{path}: row profile does not match summary profile")
        rows.extend(source_rows)
        for aggregate in summary.get("aggregates", []):
            aggregates.append({"profile": profile, **aggregate})
        source_artifacts.append(
            {
                "path": str(path),
                "profile": profile,
                "run_count": summary["run_count"],
                "reused_row_count": summary.get("reused_row_count", 0),
                "executed_row_count": summary.get("executed_row_count", 0),
                "relay_expected_count": summary.get("relay_expected_count", 0),
                "relay_payload_count": summary.get("relay_payload_count", 0),
            }
        )

    assert reference is not None
    run_count = len(rows)
    ok_run_count = sum(row.get("status") == "ok" for row in rows)
    relay_expected_count = sum(
        int(summary.get("relay_expected_count", 0))
        for _, summary in summaries
    )
    relay_payload_count = sum(
        int(summary.get("relay_payload_count", 0))
        for _, summary in summaries
    )
    reused_row_count = sum(
        int(summary.get("reused_row_count", 0))
        for _, summary in summaries
    )
    executed_row_count = sum(
        int(summary.get("executed_row_count", 0))
        for _, summary in summaries
    )
    contract_ok = (
        run_count == 36
        and ok_run_count == run_count
        and relay_expected_count == 5760
        and relay_payload_count == relay_expected_count
        and reused_row_count == 12
        and executed_row_count == 24
        and len(aggregates) == 12
    )
    return {
        "schema_version": SCHEMA_VERSION,
        "status": "ok" if contract_ok else "failed",
        "profiles": list(EXPECTED_PROFILES),
        "profile_count": len(EXPECTED_PROFILES),
        "systems": list(EXPECTED_SYSTEMS),
        "robot_count": 16,
        **reference,
        "run_count": run_count,
        "ok_run_count": ok_run_count,
        "failed_run_count": run_count - ok_run_count,
        "reused_row_count": reused_row_count,
        "executed_row_count": executed_row_count,
        "relay_expected_count": relay_expected_count,
        "relay_payload_count": relay_payload_count,
        "network_profile_contract_ok": contract_ok,
        "common_middle_contract_ok": contract_ok,
        "profile_sensitivity_comparison_allowed": contract_ok,
        "latency_distribution_comparison_allowed": contract_ok,
        "latency_superiority_claim_allowed": False,
        "cross_rmw_superiority_claim_allowed": False,
        "claim_boundary": (
            "Compare delivery/reliability and scoped latency distributions across "
            "the three tested profiles at 16 robots. Do not infer broad RMW, "
            "latency, architectural, or production superiority."
        ),
        "source_artifacts": source_artifacts,
        "aggregates": aggregates,
        "runs": rows,
    }


def render_markdown(summary: dict[str, Any]) -> str:
    lines = [
        "# Same-Hop RMW Profile Sensitivity",
        "",
        summary["claim_boundary"],
        "",
        "| profile | system | runs OK | control delivery mean | state delivery mean | control p95 ms mean | state p95 ms mean |",
        "|---|---|---:|---:|---:|---:|---:|",
    ]
    for row in summary["aggregates"]:
        lines.append(
            f"| {row['profile']} | {row['system']} | "
            f"{row['ok_run_count']}/{row['run_count']} | "
            f"{row['control_delivery_ratio_mean']:.4f} | "
            f"{row['state_delivery_ratio_mean']:.4f} | "
            f"{row['control_latency_ms_p95_mean']:.3f} | "
            f"{row['state_latency_ms_p95_mean']:.3f} |"
        )
    lines.extend(
        [
            "",
            f"Relay payloads: {summary['relay_payload_count']}/{summary['relay_expected_count']}.",
            f"Rows: {summary['ok_run_count']}/{summary['run_count']} OK; "
            f"{summary['executed_row_count']} fresh and {summary['reused_row_count']} reused.",
            "",
        ]
    )
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("summaries", nargs=3, type=Path)
    parser.add_argument(
        "--summary-json",
        type=Path,
        default=Path(
            "results_rmw_socket/"
            "same_hop_profile_sensitivity_16robot_3profile_3seed_summary.json"
        ),
    )
    parser.add_argument(
        "--markdown",
        type=Path,
        default=Path(
            "results_rmw_socket/"
            "same_hop_profile_sensitivity_16robot_3profile_3seed_report.md"
        ),
    )
    args = parser.parse_args()
    summary = aggregate_summaries(
        [(path, load_summary(ROOT / path)) for path in args.summaries]
    )
    summary_path = ROOT / args.summary_json
    markdown_path = ROOT / args.markdown
    summary_path.parent.mkdir(parents=True, exist_ok=True)
    markdown_path.parent.mkdir(parents=True, exist_ok=True)
    summary_path.write_text(
        json.dumps(summary, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    markdown_path.write_text(render_markdown(summary), encoding="utf-8")
    print(
        f"status={summary['status']} ok={summary['ok_run_count']}/"
        f"{summary['run_count']} relay={summary['relay_payload_count']}/"
        f"{summary['relay_expected_count']}"
    )
    return 0 if summary["status"] == "ok" else 1


if __name__ == "__main__":
    raise SystemExit(main())

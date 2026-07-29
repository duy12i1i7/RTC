"""Aggregate configuration-matched same-hop RMW network-profile summaries."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
SCHEMA_VERSION = "fleetrmw.same_hop_profile_sensitivity.v2"
EXPECTED_PROFILES = ("wifi", "wan", "roaming")
EXPECTED_SYSTEMS = (
    "rmw_fleetqox_cpp",
    "rmw_fastrtps_cpp",
    "rmw_cyclonedds_cpp",
    "rmw_zenoh_cpp",
)
EXPECTED_SEEDS = (7, 13, 29)


def load_summary(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"{path}: summary must be a JSON object")
    return payload


def aggregate_summaries(
    summaries: list[tuple[Path, dict[str, Any]]],
    *,
    expected_robot_counts: tuple[int, ...] = (16,),
) -> dict[str, Any]:
    if not summaries:
        raise ValueError("at least one source summary is required")
    if (
        not expected_robot_counts
        or any(count <= 0 for count in expected_robot_counts)
        or len(set(expected_robot_counts)) != len(expected_robot_counts)
    ):
        raise ValueError("expected robot counts must be positive and unique")
    expected_robot_set = set(expected_robot_counts)

    reference: dict[str, Any] | None = None
    rows: list[dict[str, Any]] = []
    aggregates: list[dict[str, Any]] = []
    source_artifacts: list[dict[str, Any]] = []
    row_keys: set[tuple[str, str, int, int]] = set()
    aggregate_keys: set[tuple[str, str, int]] = set()
    covered_robots_by_profile = {
        profile: set() for profile in EXPECTED_PROFILES
    }
    for path, summary in sorted(
        summaries,
        key=lambda item: (str(item[1].get("profile")), str(item[0])),
    ):
        profile = str(summary.get("profile"))
        if profile not in EXPECTED_PROFILES:
            raise ValueError(f"{path}: unexpected profile {profile!r}")
        if summary.get("schema_version") != "fleetrmw.same_hop_rmw_comparison.v4":
            raise ValueError(f"{path}: unsupported same-hop schema")
        if summary.get("status") != "ok":
            raise ValueError(f"{path}: source status is not ok")
        source_robot_counts = summary.get("robot_counts")
        if (
            not isinstance(source_robot_counts, list)
            or not source_robot_counts
            or any(int(count) not in expected_robot_set for count in source_robot_counts)
            or len({int(count) for count in source_robot_counts})
            != len(source_robot_counts)
        ):
            raise ValueError(f"{path}: robot-count coverage is outside the campaign")
        source_robot_set = {int(count) for count in source_robot_counts}
        if covered_robots_by_profile[profile] & source_robot_set:
            raise ValueError(f"{path}: duplicate profile/robot source coverage")
        covered_robots_by_profile[profile].update(source_robot_set)
        if tuple(summary.get("systems", ())) != EXPECTED_SYSTEMS:
            raise ValueError(f"{path}: system set or order differs")
        expected_source_runs = (
            len(source_robot_set) * len(EXPECTED_SEEDS) * len(EXPECTED_SYSTEMS)
        )
        if (
            summary.get("run_count") != expected_source_runs
            or summary.get("ok_run_count") != expected_source_runs
        ):
            raise ValueError(f"{path}: source row count does not match its robot cells")
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
        if not isinstance(source_rows, list) or len(source_rows) != expected_source_runs:
            raise ValueError(f"{path}: missing source rows")
        if any(row.get("profile") != profile for row in source_rows):
            raise ValueError(f"{path}: row profile does not match summary profile")
        for row in source_rows:
            try:
                key = (
                    profile,
                    str(row["system"]),
                    int(row["robot_count"]),
                    int(row["seed"]),
                )
            except (KeyError, TypeError, ValueError) as exc:
                raise ValueError(f"{path}: malformed row identity") from exc
            if (
                key[1] not in EXPECTED_SYSTEMS
                or key[2] not in source_robot_set
                or key[3] not in EXPECTED_SEEDS
            ):
                raise ValueError(f"{path}: row identity is outside source coverage")
            if key in row_keys:
                raise ValueError(f"{path}: duplicate profile/system/robot/seed row")
            row_keys.add(key)
            rows.append(row)
        for aggregate in summary.get("aggregates", []):
            try:
                aggregate_key = (
                    profile,
                    str(aggregate["system"]),
                    int(aggregate["robot_count"]),
                )
            except (KeyError, TypeError, ValueError) as exc:
                raise ValueError(f"{path}: malformed aggregate identity") from exc
            if (
                aggregate_key[1] not in EXPECTED_SYSTEMS
                or aggregate_key[2] not in source_robot_set
            ):
                raise ValueError(
                    f"{path}: aggregate identity is outside source coverage"
                )
            if aggregate_key in aggregate_keys:
                raise ValueError(f"{path}: duplicate profile/system/robot aggregate")
            aggregate_keys.add(aggregate_key)
            aggregates.append({"profile": profile, **aggregate})
        source_artifacts.append(
            {
                "path": str(path),
                "profile": profile,
                "robot_counts": sorted(source_robot_set),
                "run_count": summary["run_count"],
                "reused_row_count": summary.get("reused_row_count", 0),
                "executed_row_count": summary.get("executed_row_count", 0),
                "relay_expected_count": summary.get("relay_expected_count", 0),
                "relay_payload_count": summary.get("relay_payload_count", 0),
            }
        )

    assert reference is not None
    if any(
        covered_robots_by_profile[profile] != expected_robot_set
        for profile in EXPECTED_PROFILES
    ):
        raise ValueError("every profile must cover every requested robot count")
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
    expected_run_count = (
        len(EXPECTED_PROFILES)
        * len(expected_robot_counts)
        * len(EXPECTED_SEEDS)
        * len(EXPECTED_SYSTEMS)
    )
    expected_relay_count = (
        len(EXPECTED_PROFILES)
        * sum(expected_robot_counts)
        * 2
        * int(reference["samples"])
        * len(EXPECTED_SEEDS)
        * len(EXPECTED_SYSTEMS)
    )
    expected_row_keys = {
        (profile, system, robot_count, seed)
        for profile in EXPECTED_PROFILES
        for system in EXPECTED_SYSTEMS
        for robot_count in expected_robot_counts
        for seed in EXPECTED_SEEDS
    }
    expected_aggregate_keys = {
        (profile, system, robot_count)
        for profile in EXPECTED_PROFILES
        for system in EXPECTED_SYSTEMS
        for robot_count in expected_robot_counts
    }
    contract_ok = (
        run_count == expected_run_count
        and ok_run_count == run_count
        and relay_expected_count == expected_relay_count
        and relay_payload_count == relay_expected_count
        and reused_row_count + executed_row_count == run_count
        and len(aggregates)
        == len(EXPECTED_PROFILES) * len(expected_robot_counts) * len(EXPECTED_SYSTEMS)
        and row_keys == expected_row_keys
        and aggregate_keys == expected_aggregate_keys
    )
    return {
        "schema_version": SCHEMA_VERSION,
        "status": "ok" if contract_ok else "failed",
        "profiles": list(EXPECTED_PROFILES),
        "profile_count": len(EXPECTED_PROFILES),
        "systems": list(EXPECTED_SYSTEMS),
        "robot_counts": list(expected_robot_counts),
        "robot_count": (
            expected_robot_counts[0]
            if len(expected_robot_counts) == 1
            else None
        ),
        **reference,
        "run_count": run_count,
        "ok_run_count": ok_run_count,
        "failed_run_count": run_count - ok_run_count,
        "reused_row_count": reused_row_count,
        "executed_row_count": executed_row_count,
        "relay_expected_count": relay_expected_count,
        "relay_payload_count": relay_payload_count,
        "network_profile_contract_ok": contract_ok,
        "profile_robot_scale_coverage_contract_ok": contract_ok,
        "common_middle_contract_ok": contract_ok,
        "profile_sensitivity_comparison_allowed": contract_ok,
        "latency_distribution_comparison_allowed": contract_ok,
        "latency_superiority_claim_allowed": False,
        "cross_rmw_superiority_claim_allowed": False,
        "claim_boundary": (
            "Compare delivery/reliability and scoped latency distributions across "
            f"the three tested profiles at robot counts "
            f"{','.join(str(count) for count in expected_robot_counts)}. "
            "Do not infer broad RMW, latency, architectural, or production "
            "superiority."
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
        "| profile | robots | system | runs OK | control delivery mean | state delivery mean | control p95 ms mean | state p95 ms mean |",
        "|---|---:|---|---:|---:|---:|---:|---:|",
    ]
    for row in summary["aggregates"]:
        lines.append(
            f"| {row['profile']} | {row['robot_count']} | {row['system']} | "
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
    parser.add_argument("summaries", nargs="+", type=Path)
    parser.add_argument("--robot-counts", default="8,16,32")
    parser.add_argument(
        "--summary-json",
        type=Path,
        default=Path(
            "results_rmw_socket/"
            "same_hop_profile_scale_sensitivity_8_16_32_3profile_3seed_summary.json"
        ),
    )
    parser.add_argument(
        "--markdown",
        type=Path,
        default=Path(
            "results_rmw_socket/"
            "same_hop_profile_scale_sensitivity_8_16_32_3profile_3seed_report.md"
        ),
    )
    args = parser.parse_args()
    robot_counts = tuple(
        int(value.strip())
        for value in args.robot_counts.split(",")
        if value.strip()
    )
    summary = aggregate_summaries(
        [(path, load_summary(ROOT / path)) for path in args.summaries],
        expected_robot_counts=robot_counts,
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

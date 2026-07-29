"""Aggregate exact-payload same-hop offered-load sensitivity summaries."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
SCHEMA_VERSION = "fleetrmw.same_hop_offered_load_sensitivity.v1"
SOURCE_SCHEMA_VERSION = "fleetrmw.same_hop_rmw_comparison.v4"
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


def payload_offered_mbit_s(
    *,
    payload_bytes: int,
    robot_count: int,
    publish_interval_ms: int,
) -> float:
    if payload_bytes <= 0 or robot_count <= 0 or publish_interval_ms <= 0:
        raise ValueError("offered-load inputs must be positive")
    topic_count = robot_count * 2
    return (
        payload_bytes
        * topic_count
        * 8.0
        / (publish_interval_ms / 1000.0)
        / 1_000_000.0
    )


def aggregate_summaries(
    summaries: list[tuple[Path, dict[str, Any]]],
    *,
    expected_publish_interval_ms: tuple[int, ...] = (50, 500, 2000),
    expected_payload_bytes: int = 32768,
    expected_robot_count: int = 16,
) -> dict[str, Any]:
    if (
        not expected_publish_interval_ms
        or any(interval <= 0 for interval in expected_publish_interval_ms)
        or len(set(expected_publish_interval_ms))
        != len(expected_publish_interval_ms)
    ):
        raise ValueError("expected publish intervals must be positive and unique")
    if expected_payload_bytes <= 0 or expected_robot_count <= 0:
        raise ValueError("payload bytes and robot count must be positive")
    if len(summaries) != len(expected_publish_interval_ms):
        raise ValueError("exactly one source summary per publish interval is required")

    expected_interval_set = set(expected_publish_interval_ms)
    reference: dict[str, Any] | None = None
    rows: list[dict[str, Any]] = []
    aggregates: list[dict[str, Any]] = []
    source_artifacts: list[dict[str, Any]] = []
    covered_intervals: set[int] = set()
    row_keys: set[tuple[int, str, int]] = set()
    aggregate_keys: set[tuple[int, str]] = set()

    for path, summary in sorted(
        summaries,
        key=lambda item: int(item[1].get("publish_interval_ms", 0)),
    ):
        if summary.get("schema_version") != SOURCE_SCHEMA_VERSION:
            raise ValueError(f"{path}: unsupported same-hop schema")
        if summary.get("status") not in {"ok", "partial", "failed"}:
            raise ValueError(f"{path}: source status is not measured")
        try:
            publish_interval_ms = int(summary["publish_interval_ms"])
            payload_bytes = int(summary["payload_bytes"])
        except (KeyError, TypeError, ValueError) as exc:
            raise ValueError(f"{path}: source schedule is malformed") from exc
        if publish_interval_ms not in expected_interval_set:
            raise ValueError(f"{path}: publish interval is outside the campaign")
        if publish_interval_ms in covered_intervals:
            raise ValueError(f"{path}: duplicate publish-interval source")
        covered_intervals.add(publish_interval_ms)
        if payload_bytes != expected_payload_bytes:
            raise ValueError(f"{path}: payload size differs")
        if summary.get("robot_counts") != [expected_robot_count]:
            raise ValueError(f"{path}: robot-count coverage differs")
        if tuple(summary.get("seeds", ())) != EXPECTED_SEEDS:
            raise ValueError(f"{path}: seed coverage differs")
        if tuple(summary.get("systems", ())) != EXPECTED_SYSTEMS:
            raise ValueError(f"{path}: system set or order differs")
        expected_source_runs = len(EXPECTED_SEEDS) * len(EXPECTED_SYSTEMS)
        if (
            summary.get("run_count") != expected_source_runs
            or int(summary.get("skipped_run_count", 0)) != 0
            or int(summary.get("ok_run_count", 0))
            + int(summary.get("failed_run_count", 0))
            != expected_source_runs
        ):
            raise ValueError(f"{path}: source measured-row coverage differs")
        if not all(
            summary.get(key) is True
            for key in (
                "payload_size_contract_ok",
                "serialized_relay_contract_ok",
                "middle_rmw_termination_republish_contract_ok",
                "middle_hop_processing_equivalent",
                "latency_comparison_allowed",
                "resume_configuration_validation_enabled",
            )
        ):
            raise ValueError(f"{path}: required same-hop contract is false")

        configuration = {
            key: summary.get(key)
            for key in (
                "image",
                "profile",
                "netem_loss_scale",
                "samples",
                "payload_bytes",
                "timeout_s",
                "publisher_reliability_horizon_s",
                "relay_scope",
            )
        }
        if reference is None:
            reference = configuration
        elif configuration != reference:
            raise ValueError(f"{path}: non-interval configuration differs")

        source_rows = summary.get("runs")
        if not isinstance(source_rows, list) or len(source_rows) != expected_source_runs:
            raise ValueError(f"{path}: source rows are missing")
        for row in source_rows:
            result = row.get("result")
            if not isinstance(result, dict):
                raise ValueError(f"{path}: row result is missing")
            try:
                key = (
                    publish_interval_ms,
                    str(row["system"]),
                    int(row["seed"]),
                )
                result_interval_ms = int(result["publish_interval_ms"])
                result_payload_bytes = int(result["payload_bytes"])
                payload_size_min = int(result["payload_size_min_bytes"])
                payload_size_max = int(result["payload_size_max_bytes"])
            except (KeyError, TypeError, ValueError) as exc:
                raise ValueError(f"{path}: malformed row schedule evidence") from exc
            if (
                key[1] not in EXPECTED_SYSTEMS
                or key[2] not in EXPECTED_SEEDS
                or int(row.get("robot_count", 0)) != expected_robot_count
                or result_interval_ms != publish_interval_ms
                or result_payload_bytes != expected_payload_bytes
                or payload_size_min != expected_payload_bytes
                or payload_size_max != expected_payload_bytes
                or result.get("payload_size_contract_ok") is not True
                or row.get("status") not in {"ok", "failed"}
            ):
                raise ValueError(f"{path}: row is outside exact schedule coverage")
            if key in row_keys:
                raise ValueError(f"{path}: duplicate interval/system/seed row")
            row_keys.add(key)
            rows.append({"publish_interval_ms": publish_interval_ms, **row})

        source_aggregates = summary.get("aggregates")
        if not isinstance(source_aggregates, list):
            raise ValueError(f"{path}: source aggregates are missing")
        for aggregate in source_aggregates:
            try:
                key = (publish_interval_ms, str(aggregate["system"]))
            except (KeyError, TypeError, ValueError) as exc:
                raise ValueError(f"{path}: malformed aggregate identity") from exc
            if (
                key[1] not in EXPECTED_SYSTEMS
                or int(aggregate.get("robot_count", 0)) != expected_robot_count
            ):
                raise ValueError(f"{path}: aggregate is outside campaign coverage")
            if key in aggregate_keys:
                raise ValueError(f"{path}: duplicate interval/system aggregate")
            aggregate_keys.add(key)
            aggregates.append(
                {
                    "publish_interval_ms": publish_interval_ms,
                    "payload_offered_mbit_s": payload_offered_mbit_s(
                        payload_bytes=expected_payload_bytes,
                        robot_count=expected_robot_count,
                        publish_interval_ms=publish_interval_ms,
                    ),
                    **aggregate,
                }
            )

        source_artifacts.append(
            {
                "path": str(path),
                "publish_interval_ms": publish_interval_ms,
                "payload_offered_mbit_s": payload_offered_mbit_s(
                    payload_bytes=expected_payload_bytes,
                    robot_count=expected_robot_count,
                    publish_interval_ms=publish_interval_ms,
                ),
                "run_count": summary["run_count"],
                "reused_row_count": int(summary.get("reused_row_count", 0)),
                "executed_row_count": int(summary.get("executed_row_count", 0)),
                "relay_expected_count": int(
                    summary.get("relay_expected_count", 0)
                ),
                "relay_payload_count": int(
                    summary.get("relay_payload_count", 0)
                ),
            }
        )

    assert reference is not None
    expected_row_keys = {
        (interval, system, seed)
        for interval in expected_publish_interval_ms
        for system in EXPECTED_SYSTEMS
        for seed in EXPECTED_SEEDS
    }
    expected_aggregate_keys = {
        (interval, system)
        for interval in expected_publish_interval_ms
        for system in EXPECTED_SYSTEMS
    }
    expected_run_count = len(expected_row_keys)
    expected_relay_count = (
        len(expected_publish_interval_ms)
        * expected_robot_count
        * 2
        * int(reference["samples"])
        * len(EXPECTED_SEEDS)
        * len(EXPECTED_SYSTEMS)
    )
    ok_run_count = sum(row.get("status") == "ok" for row in rows)
    failed_run_count = sum(row.get("status") == "failed" for row in rows)
    relay_expected_count = sum(
        source["relay_expected_count"] for source in source_artifacts
    )
    relay_payload_count = sum(
        source["relay_payload_count"] for source in source_artifacts
    )
    reused_row_count = sum(
        source["reused_row_count"] for source in source_artifacts
    )
    executed_row_count = sum(
        source["executed_row_count"] for source in source_artifacts
    )
    contract_ok = (
        covered_intervals == expected_interval_set
        and row_keys == expected_row_keys
        and aggregate_keys == expected_aggregate_keys
        and len(rows) == expected_run_count
        and ok_run_count + failed_run_count == expected_run_count
        and relay_expected_count == expected_relay_count
        and reused_row_count + executed_row_count == expected_run_count
    )
    successful_cell_keys = {
        (int(row["publish_interval_ms"]), str(row["system"]))
        for row in rows
        if row.get("status") == "ok"
    }
    fully_successful_intervals = [
        interval
        for interval in expected_publish_interval_ms
        if all(
            (interval, system) in successful_cell_keys
            and sum(
                row.get("status") == "ok"
                and int(row["publish_interval_ms"]) == interval
                and row["system"] == system
                for row in rows
            )
            == len(EXPECTED_SEEDS)
            for system in EXPECTED_SYSTEMS
        )
    ]
    latency_distribution_comparison_allowed = (
        contract_ok and successful_cell_keys == expected_aggregate_keys
    )
    return {
        "schema_version": SCHEMA_VERSION,
        "status": (
            "ok"
            if contract_ok and failed_run_count == 0
            else "partial"
            if contract_ok
            else "failed"
        ),
        "publish_interval_ms": list(expected_publish_interval_ms),
        "payload_offered_mbit_s": [
            payload_offered_mbit_s(
                payload_bytes=expected_payload_bytes,
                robot_count=expected_robot_count,
                publish_interval_ms=interval,
            )
            for interval in expected_publish_interval_ms
        ],
        "payload_offered_rate_scope":
            "source_publisher_application_payload_only_excludes_ros_wire_and_relay_hop",
        "fully_successful_publish_interval_ms": fully_successful_intervals,
        "minimum_fully_successful_publish_interval_ms": (
            min(fully_successful_intervals)
            if fully_successful_intervals
            else None
        ),
        "payload_bytes": expected_payload_bytes,
        "robot_count": expected_robot_count,
        "seeds": list(EXPECTED_SEEDS),
        "systems": list(EXPECTED_SYSTEMS),
        **reference,
        "run_count": len(rows),
        "ok_run_count": ok_run_count,
        "failed_run_count": failed_run_count,
        "skipped_run_count": 0,
        "reused_row_count": reused_row_count,
        "executed_row_count": executed_row_count,
        "relay_expected_count": relay_expected_count,
        "relay_payload_count": relay_payload_count,
        "exact_payload_size_contract_ok": contract_ok,
        "complete_measurement_matrix_contract_ok": contract_ok,
        "common_middle_contract_ok": contract_ok,
        "offered_load_sensitivity_comparison_allowed": contract_ok,
        "latency_distribution_comparison_allowed":
            latency_distribution_comparison_allowed,
        "latency_superiority_claim_allowed": False,
        "cross_rmw_superiority_claim_allowed": False,
        "claim_boundary": (
            f"Compare delivery/reliability across exact {expected_payload_bytes}-byte "
            "payloads at "
            f"{expected_robot_count} robots while changing only the batch interval "
            f"over {','.join(str(value) for value in expected_publish_interval_ms)} "
            "ms. Source-publisher payload offered-load rates exclude ROS/wire "
            "overhead and the relay hop. Failed rows "
            "remain measured outcomes; latency comparison requires a successful run "
            "in every interval/system cell. Do not infer broad RMW, latency, "
            "architectural, or production superiority."
        ),
        "source_artifacts": source_artifacts,
        "aggregates": aggregates,
        "runs": rows,
    }


def render_markdown(summary: dict[str, Any]) -> str:
    lines = [
        "# Same-Hop ROS 2 RMW Offered-Load Sensitivity",
        "",
        summary["claim_boundary"],
        "",
        "| interval ms | payload offered Mbit/s | system | runs OK | control delivery mean | state delivery mean | control p95 ms mean | state p95 ms mean |",
        "|---:|---:|---|---:|---:|---:|---:|---:|",
    ]
    for row in summary["aggregates"]:
        control_latency = (
            f"{row['control_latency_ms_p95_mean']:.3f}"
            if row["ok_run_count"] > 0
            else "n/a"
        )
        state_latency = (
            f"{row['state_latency_ms_p95_mean']:.3f}"
            if row["ok_run_count"] > 0
            else "n/a"
        )
        lines.append(
            f"| {row['publish_interval_ms']} | "
            f"{row['payload_offered_mbit_s']:.3f} | {row['system']} | "
            f"{row['ok_run_count']}/{row['run_count']} | "
            f"{row['control_delivery_ratio_mean']:.4f} | "
            f"{row['state_delivery_ratio_mean']:.4f} | "
            f"{control_latency} | {state_latency} |"
        )
    lines.append("")
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("summaries", nargs="+", type=Path)
    parser.add_argument("--publish-interval-ms", default="50,500,2000")
    parser.add_argument("--payload-bytes", type=int, default=32768)
    parser.add_argument("--robot-count", type=int, default=16)
    parser.add_argument(
        "--summary-json",
        type=Path,
        default=Path(
            "results_rmw_socket/"
            "same_hop_offered_load_sensitivity_32768b_16robot_3interval_3seed_summary.json"
        ),
    )
    parser.add_argument(
        "--markdown",
        type=Path,
        default=Path(
            "results_rmw_socket/"
            "same_hop_offered_load_sensitivity_32768b_16robot_3interval_3seed_report.md"
        ),
    )
    args = parser.parse_args()
    expected_publish_interval_ms = tuple(
        int(value.strip())
        for value in args.publish_interval_ms.split(",")
        if value.strip()
    )
    summary = aggregate_summaries(
        [(path, load_summary(ROOT / path)) for path in args.summaries],
        expected_publish_interval_ms=expected_publish_interval_ms,
        expected_payload_bytes=args.payload_bytes,
        expected_robot_count=args.robot_count,
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
        f"{summary['relay_expected_count']} fully_successful_intervals="
        f"{summary['fully_successful_publish_interval_ms']}"
    )
    return 0 if summary["status"] in {"ok", "partial"} else 1


if __name__ == "__main__":
    raise SystemExit(main())

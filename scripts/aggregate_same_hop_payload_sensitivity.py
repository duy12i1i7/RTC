"""Aggregate exact-payload same-hop RMW sensitivity summaries."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
SCHEMA_VERSION = "fleetrmw.same_hop_payload_sensitivity.v1"
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


def aggregate_summaries(
    summaries: list[tuple[Path, dict[str, Any]]],
    *,
    expected_payload_bytes: tuple[int, ...] = (256, 4096, 32768),
    expected_robot_count: int = 16,
) -> dict[str, Any]:
    if (
        not expected_payload_bytes
        or any(size <= 0 for size in expected_payload_bytes)
        or len(set(expected_payload_bytes)) != len(expected_payload_bytes)
    ):
        raise ValueError("expected payload sizes must be positive and unique")
    if expected_robot_count <= 0:
        raise ValueError("expected robot count must be positive")
    if len(summaries) != len(expected_payload_bytes):
        raise ValueError("exactly one source summary per payload size is required")

    expected_payload_set = set(expected_payload_bytes)
    reference: dict[str, Any] | None = None
    rows: list[dict[str, Any]] = []
    aggregates: list[dict[str, Any]] = []
    source_artifacts: list[dict[str, Any]] = []
    covered_payloads: set[int] = set()
    row_keys: set[tuple[int, str, int]] = set()
    aggregate_keys: set[tuple[int, str]] = set()

    for path, summary in sorted(
        summaries,
        key=lambda item: int(item[1].get("payload_bytes", 0)),
    ):
        if summary.get("schema_version") != SOURCE_SCHEMA_VERSION:
            raise ValueError(f"{path}: unsupported same-hop schema")
        if summary.get("status") not in {"ok", "partial", "failed"}:
            raise ValueError(f"{path}: source status is not measured")
        try:
            payload_bytes = int(summary["payload_bytes"])
        except (KeyError, TypeError, ValueError) as exc:
            raise ValueError(f"{path}: missing exact payload size") from exc
        if payload_bytes not in expected_payload_set:
            raise ValueError(f"{path}: payload size is outside the campaign")
        if payload_bytes in covered_payloads:
            raise ValueError(f"{path}: duplicate payload-size source")
        covered_payloads.add(payload_bytes)
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
                "publish_interval_ms",
                "timeout_s",
                "publisher_reliability_horizon_s",
                "relay_scope",
            )
        }
        if reference is None:
            reference = configuration
        elif configuration != reference:
            raise ValueError(f"{path}: non-payload configuration differs")

        source_rows = summary.get("runs")
        if not isinstance(source_rows, list) or len(source_rows) != expected_source_runs:
            raise ValueError(f"{path}: missing source rows")
        for row in source_rows:
            result = row.get("result")
            if not isinstance(result, dict):
                raise ValueError(f"{path}: row result is missing")
            try:
                key = (
                    payload_bytes,
                    str(row["system"]),
                    int(row["seed"]),
                )
                result_payload_bytes = int(result["payload_bytes"])
                payload_size_min = int(result["payload_size_min_bytes"])
                payload_size_max = int(result["payload_size_max_bytes"])
            except (KeyError, TypeError, ValueError) as exc:
                raise ValueError(f"{path}: malformed row payload evidence") from exc
            if (
                key[1] not in EXPECTED_SYSTEMS
                or key[2] not in EXPECTED_SEEDS
                or int(row.get("robot_count", 0)) != expected_robot_count
                or result_payload_bytes != payload_bytes
                or payload_size_min != payload_bytes
                or payload_size_max != payload_bytes
                or result.get("payload_size_contract_ok") is not True
                or row.get("status") not in {"ok", "failed"}
            ):
                raise ValueError(f"{path}: row is outside exact-payload coverage")
            if key in row_keys:
                raise ValueError(f"{path}: duplicate payload/system/seed row")
            row_keys.add(key)
            rows.append({"payload_bytes": payload_bytes, **row})

        source_aggregates = summary.get("aggregates")
        if not isinstance(source_aggregates, list):
            raise ValueError(f"{path}: source aggregates are missing")
        for aggregate in source_aggregates:
            try:
                key = (payload_bytes, str(aggregate["system"]))
            except (KeyError, TypeError, ValueError) as exc:
                raise ValueError(f"{path}: malformed aggregate identity") from exc
            if (
                key[1] not in EXPECTED_SYSTEMS
                or int(aggregate.get("robot_count", 0)) != expected_robot_count
            ):
                raise ValueError(f"{path}: aggregate is outside campaign coverage")
            if key in aggregate_keys:
                raise ValueError(f"{path}: duplicate payload/system aggregate")
            aggregate_keys.add(key)
            aggregates.append({"payload_bytes": payload_bytes, **aggregate})

        source_artifacts.append(
            {
                "path": str(path),
                "payload_bytes": payload_bytes,
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
        (payload_bytes, system, seed)
        for payload_bytes in expected_payload_bytes
        for system in EXPECTED_SYSTEMS
        for seed in EXPECTED_SEEDS
    }
    expected_aggregate_keys = {
        (payload_bytes, system)
        for payload_bytes in expected_payload_bytes
        for system in EXPECTED_SYSTEMS
    }
    expected_run_count = len(expected_row_keys)
    expected_relay_count = (
        len(expected_payload_bytes)
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
        covered_payloads == expected_payload_set
        and row_keys == expected_row_keys
        and aggregate_keys == expected_aggregate_keys
        and len(rows) == expected_run_count
        and ok_run_count + failed_run_count == expected_run_count
        and relay_expected_count == expected_relay_count
        and reused_row_count + executed_row_count == expected_run_count
    )
    successful_cell_keys = {
        (int(row["payload_bytes"]), str(row["system"]))
        for row in rows
        if row.get("status") == "ok"
    }
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
        "payload_bytes": list(expected_payload_bytes),
        "payload_size_count": len(expected_payload_bytes),
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
        "common_middle_contract_ok": contract_ok,
        "complete_measurement_matrix_contract_ok": contract_ok,
        "payload_sensitivity_comparison_allowed": contract_ok,
        "latency_distribution_comparison_allowed":
            latency_distribution_comparison_allowed,
        "latency_superiority_claim_allowed": False,
        "cross_rmw_superiority_claim_allowed": False,
        "claim_boundary": (
            "Compare delivery/reliability and scoped latency distributions across "
            f"exact {','.join(str(size) for size in expected_payload_bytes)}-byte "
            f"payloads at {expected_robot_count} robots under the matched profile. "
            "Failed delivery rows are measured outcomes, not omitted cells; latency "
            "comparison is allowed only when every payload/system cell has at least "
            "one successful run. "
            "Do not infer broad RMW, latency, architectural, or production "
            "superiority."
        ),
        "source_artifacts": source_artifacts,
        "aggregates": aggregates,
        "runs": rows,
    }


def render_markdown(summary: dict[str, Any]) -> str:
    lines = [
        "# Same-Hop ROS 2 RMW Payload Sensitivity",
        "",
        summary["claim_boundary"],
        "",
        "| payload bytes | system | runs OK | control delivery mean | state delivery mean | control p95 ms mean | state p95 ms mean |",
        "|---:|---|---:|---:|---:|---:|---:|",
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
            f"| {row['payload_bytes']} | {row['system']} | "
            f"{row['ok_run_count']}/{row['run_count']} | "
            f"{row['control_delivery_ratio_mean']:.4f} | "
            f"{row['state_delivery_ratio_mean']:.4f} | "
            f"{control_latency} | "
            f"{state_latency} |"
        )
    lines.append("")
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("summaries", nargs="+", type=Path)
    parser.add_argument("--payload-bytes", default="256,4096,32768")
    parser.add_argument("--robot-count", type=int, default=16)
    parser.add_argument(
        "--summary-json",
        type=Path,
        default=Path(
            "results_rmw_socket/"
            "same_hop_payload_sensitivity_16robot_3size_3seed_summary.json"
        ),
    )
    parser.add_argument(
        "--markdown",
        type=Path,
        default=Path(
            "results_rmw_socket/"
            "same_hop_payload_sensitivity_16robot_3size_3seed_report.md"
        ),
    )
    args = parser.parse_args()
    expected_payload_bytes = tuple(
        int(value.strip())
        for value in args.payload_bytes.split(",")
        if value.strip()
    )
    summary = aggregate_summaries(
        [(path, load_summary(ROOT / path)) for path in args.summaries],
        expected_payload_bytes=expected_payload_bytes,
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
        f"{summary['relay_expected_count']}"
    )
    return 0 if summary["status"] in {"ok", "partial"} else 1


if __name__ == "__main__":
    raise SystemExit(main())

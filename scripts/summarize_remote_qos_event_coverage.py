"""Aggregate repeated Docker/netem evidence for all Jazzy RMW event types."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
SCHEMA_VERSION = "fleetrmw.remote_qos_event_coverage.v1"

EVENT_TYPES = [
    "RMW_EVENT_LIVELINESS_CHANGED",
    "RMW_EVENT_REQUESTED_DEADLINE_MISSED",
    "RMW_EVENT_REQUESTED_QOS_INCOMPATIBLE",
    "RMW_EVENT_MESSAGE_LOST",
    "RMW_EVENT_SUBSCRIPTION_INCOMPATIBLE_TYPE",
    "RMW_EVENT_SUBSCRIPTION_MATCHED",
    "RMW_EVENT_LIVELINESS_LOST",
    "RMW_EVENT_OFFERED_DEADLINE_MISSED",
    "RMW_EVENT_OFFERED_QOS_INCOMPATIBLE",
    "RMW_EVENT_PUBLISHER_INCOMPATIBLE_TYPE",
    "RMW_EVENT_PUBLICATION_MATCHED",
]

SOURCE_FILES = {
    "remote_graph": "docker_remote_event_probe_summary.json",
    "remote_liveliness": "docker_remote_manual_liveliness_probe_summary.json",
    "remote_deadline": "docker_remote_deadline_event_probe_summary.json",
    "remote_message_lost": "docker_message_lost_interprocess_probe_summary.json",
}

EVENT_SOURCES = {
    "RMW_EVENT_PUBLICATION_MATCHED": "remote_graph",
    "RMW_EVENT_SUBSCRIPTION_MATCHED": "remote_graph",
    "RMW_EVENT_OFFERED_QOS_INCOMPATIBLE": "remote_graph",
    "RMW_EVENT_REQUESTED_QOS_INCOMPATIBLE": "remote_graph",
    "RMW_EVENT_PUBLISHER_INCOMPATIBLE_TYPE": "remote_graph",
    "RMW_EVENT_SUBSCRIPTION_INCOMPATIBLE_TYPE": "remote_graph",
    "RMW_EVENT_LIVELINESS_CHANGED": "remote_graph",
    "RMW_EVENT_LIVELINESS_LOST": "remote_liveliness",
    "RMW_EVENT_OFFERED_DEADLINE_MISSED": "remote_deadline",
    "RMW_EVENT_REQUESTED_DEADLINE_MISSED": "remote_deadline",
    "RMW_EVENT_MESSAGE_LOST": "remote_message_lost",
}


def load_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return value if isinstance(value, dict) else {}


def repeated_ok(data: dict[str, Any], minimum_runs: int = 5) -> bool:
    run_count = int(data.get("run_count", 0))
    return (
        data.get("status") == "ok"
        and run_count >= minimum_runs
        and int(data.get("ok_run_count", 0)) == run_count
        and data.get("netem_applied") is True
        and len(data.get("runs", [])) == run_count
    )


def remote_graph_ok(data: dict[str, Any]) -> bool:
    if not repeated_ok(data) or data.get("real_udp_multicontainer") is not True:
        return False
    if not all(
        data.get(key) is True
        for key in (
            "remote_matched_event_production",
            "remote_qos_event_production",
            "remote_type_event_production",
            "remote_liveliness_event_production",
        )
    ):
        return False
    for run in data.get("runs", []):
        observer = run.get("observer", {})
        if run.get("status") != "ok" or not all(
            observer.get(key) is True
            for key in ("matched_ok", "qos_ok", "type_ok", "liveliness_ok")
        ):
            return False
        if any(
            int(observer.get(key, 0)) < minimum
            for key, minimum in (
                ("publication_callback_events", 2),
                ("subscription_callback_events", 2),
                ("liveliness_callback_events", 2),
            )
        ):
            return False
    return True


def remote_liveliness_ok(data: dict[str, Any]) -> bool:
    if not repeated_ok(data) or data.get("real_udp_multicontainer") is not True:
        return False
    if data.get("remote_publisher_liveliness_lost_event_claim") is not True:
        return False
    for run in data.get("runs", []):
        advertiser = run.get("advertiser", {})
        if (
            run.get("status") != "ok"
            or advertiser.get("remote_publisher_liveliness_lost_event_claim") is not True
            or advertiser.get("initial_lost_not_ready") is not True
            or advertiser.get("first_lost_taken") is not True
            or advertiser.get("second_lost_taken") is not True
            or advertiser.get("lost_event_cleared") is not True
            or int(advertiser.get("lost_callback_events", 0)) != 2
        ):
            return False
    return True


def remote_deadline_ok(data: dict[str, Any]) -> bool:
    if not repeated_ok(data) or data.get("real_udp_multicontainer") is not True:
        return False
    if not all(
        data.get(key) is True
        for key in (
            "remote_offered_deadline_missed_event_claim",
            "remote_requested_deadline_missed_event_claim",
            "remote_deadline_missed_event_repeated_claim",
        )
    ):
        return False
    for run in data.get("runs", []):
        for endpoint in (run.get("advertiser", {}), run.get("observer", {})):
            if (
                endpoint.get("status") != "ok"
                or endpoint.get("initial_not_ready") is not True
                or endpoint.get("cleared_not_ready") is not True
                or int(endpoint.get("callback_events", 0)) < 1
                or int(endpoint.get("total_count", 0)) < 1
            ):
                return False
    return True


def remote_message_lost_ok(data: dict[str, Any]) -> bool:
    if not repeated_ok(data):
        return False
    if not all(
        data.get(key) is True
        for key in (
            "remote_message_lost_waitable_claim",
            "repeated_remote_message_lost_claim",
        )
    ):
        return False
    for run in data.get("runs", []):
        subscriber = run.get("subscriber", {})
        if (
            run.get("status") != "ok"
            or subscriber.get("message_lost_wait_ready") is not True
            or subscriber.get("message_lost_taken") is not True
            or int(subscriber.get("message_lost_callback_events", 0)) != 1
            or int(subscriber.get("message_lost_total_count", 0)) != 1
        ):
            return False
    return True


VALIDATORS = {
    "remote_graph": remote_graph_ok,
    "remote_liveliness": remote_liveliness_ok,
    "remote_deadline": remote_deadline_ok,
    "remote_message_lost": remote_message_lost_ok,
}


def summarize(results_dir: Path) -> dict[str, Any]:
    sources: dict[str, dict[str, Any]] = {}
    source_ok: dict[str, bool] = {}
    for source, filename in SOURCE_FILES.items():
        path = results_dir / filename
        data = load_json(path)
        ok = VALIDATORS[source](data)
        source_ok[source] = ok
        sources[source] = {
            "path": str(path),
            "schema_version": data.get("schema_version"),
            "status": data.get("status", "missing"),
            "run_count": int(data.get("run_count", 0)),
            "ok_run_count": int(data.get("ok_run_count", 0)),
            "coverage_valid": ok,
        }

    event_coverage = {
        event_type: {
            "source": EVENT_SOURCES[event_type],
            "covered": source_ok.get(EVENT_SOURCES[event_type], False),
        }
        for event_type in EVENT_TYPES
    }
    all_covered = all(row["covered"] for row in event_coverage.values())
    execution_count = sum(source["run_count"] for source in sources.values())
    return {
        "schema_version": SCHEMA_VERSION,
        "status": "ok" if all_covered else "failed",
        "remote_event_coverage_scope": "one repeated real UDP/netem multi-container production path per non-invalid Jazzy RMW event type",
        "event_type_count": len(EVENT_TYPES),
        "event_types_covered": EVENT_TYPES if all_covered else [
            event_type
            for event_type, row in event_coverage.items()
            if row["covered"]
        ],
        "event_coverage": event_coverage,
        "source_artifact_count": len(sources),
        "source_artifacts": sources,
        "component_execution_count": execution_count,
        "minimum_repeated_runs_per_source": min(
            (source["run_count"] for source in sources.values()), default=0
        ),
        "real_udp_multicontainer": all_covered,
        "netem_applied": all_covered,
        "remote_all_jazzy_event_types_path_claim": all_covered,
        "remote_event_wait_take_callback_coverage_claim": all_covered,
        "full_dds_event_semantics_covered": False,
        "remote_event_coverage_boundary": "does not claim every DDS resource-limit, deprecated liveliness, or vendor-specific event semantic",
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--results-dir", default="results_rmw_socket")
    parser.add_argument(
        "--summary-json",
        default="results_rmw_socket/remote_qos_event_coverage_summary.json",
    )
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    results_dir = Path(args.results_dir)
    if not results_dir.is_absolute():
        results_dir = ROOT / results_dir
    summary = summarize(results_dir)
    output = Path(args.summary_json)
    if not output.is_absolute():
        output = ROOT / output
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(summary, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    if args.json:
        print(json.dumps(summary, sort_keys=True))
    else:
        print(f"status={summary['status']}")
        print(
            f"events={len(summary['event_types_covered'])}/{summary['event_type_count']}"
        )
    return 0 if summary["status"] == "ok" else 1


if __name__ == "__main__":
    raise SystemExit(main())

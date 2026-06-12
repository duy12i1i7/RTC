"""Run repeated lossy scheduled ACK/NACK repair rows for FleetRMW."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

try:
    from scripts.run_rmw_docker_router_scheduled_reliability_probe import (
        DEFAULT_IMAGE,
        DEFAULT_TOPIC,
        NETEM_PROFILES,
        run_probe,
    )
except ModuleNotFoundError:
    from run_rmw_docker_router_scheduled_reliability_probe import (
        DEFAULT_IMAGE,
        DEFAULT_TOPIC,
        NETEM_PROFILES,
        run_probe,
    )


SCHEMA_VERSION = (
    "fleetrmw.rmw_router_scheduled_reliability_repeated_loss_matrix.v1"
)
DEFAULT_PROFILES = "wifi,roaming"
DEFAULT_REPETITIONS = "7,13"
DEFAULT_LOSS_PERCENTS = "0.02"
SEED_SEMANTICS = (
    "repetition_id_only; current tc netem in the RMW image does not expose "
    "explicit deterministic RNG seeding"
)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--image", default=DEFAULT_IMAGE)
    parser.add_argument("--profiles", default=DEFAULT_PROFILES)
    parser.add_argument("--repetitions", default=DEFAULT_REPETITIONS)
    parser.add_argument("--loss-percents", default=DEFAULT_LOSS_PERCENTS)
    parser.add_argument("--topic-prefix", default=DEFAULT_TOPIC)
    parser.add_argument(
        "--fail-on-row-failure",
        action="store_true",
        help="return non-zero when stochastic loss causes any row to fail",
    )
    parser.add_argument(
        "--summary-json",
        default=(
            "results_rmw_socket/"
            "docker_router_scheduled_reliability_repeated_loss_matrix_summary.json"
        ),
    )
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    profiles = parse_profiles(args.profiles)
    repetitions = parse_ints(args.repetitions)
    loss_percents = parse_floats(args.loss_percents)
    root = Path(__file__).resolve().parents[1]
    rows: list[dict[str, Any]] = []
    for loss_percent in loss_percents:
        loss_token = str(loss_percent).replace(".", "_")
        for repetition_id in repetitions:
            for profile in profiles:
                topic = (
                    f"{args.topic_prefix.rstrip('/')}/{profile}/"
                    f"rep-{repetition_id}/loss-{loss_token}"
                )
                result = run_probe(
                    root=root,
                    image=args.image,
                    topic=topic,
                    netem_profile=profile,
                    netem_loss_percent=loss_percent,
                )
                rows.append(
                    row_from_result(
                        profile=profile,
                        repetition_id=repetition_id,
                        loss_percent=loss_percent,
                        result=result,
                    )
                )

    ok_rows = [row for row in rows if row["evidence_ok"]]
    status = "failed"
    if rows:
        status = "ok" if len(ok_rows) == len(rows) else "partial"
        if not ok_rows:
            status = "failed"
    summary = {
        "schema_version": SCHEMA_VERSION,
        "status": status,
        "image": args.image,
        "profiles": profiles,
        "repetitions": repetitions,
        "loss_percents": loss_percents,
        "seed_semantics": SEED_SEMANTICS,
        "run_count": len(rows),
        "ok_run_count": len(ok_rows),
        "failed_run_count": len(rows) - len(ok_rows),
        "total_test_dropped_frames": sum(
            int(row["router_test_dropped_frames"]) for row in rows
        ),
        "total_ack_nack_forwarded": sum(
            int(row["router_ack_nack_forwarded"]) for row in rows
        ),
        "total_scheduler_forwarded_frames": sum(
            int(row["router_scheduler_forwarded_frames"]) for row in rows
        ),
        "total_nack_retransmissions": sum(
            int(row["publisher_nack_retransmissions"]) for row in rows
        ),
        "rows": rows,
    }
    output = root / args.summary_json
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(summary, sort_keys=True) + "\n", encoding="utf-8")

    if args.json:
        print(json.dumps(summary, sort_keys=True))
    else:
        print("fleetrmw-router-scheduled-reliability-repeated-loss-matrix")
        print(f"  status: {status}")
        print(f"  ok/runs: {len(ok_rows)}/{len(rows)}")
        print(
            "  total_nack_retransmissions: "
            f"{summary['total_nack_retransmissions']}"
        )
        print(
            "  total_scheduler_forwarded_frames: "
            f"{summary['total_scheduler_forwarded_frames']}"
        )
    if args.fail_on_row_failure and status != "ok":
        return 1
    return 0 if status in ("ok", "partial") else 1


def row_from_result(
    *,
    profile: str,
    repetition_id: int,
    loss_percent: float,
    result: dict[str, Any],
) -> dict[str, Any]:
    publisher = result.get("publisher", {})
    subscriber = result.get("subscriber", {})
    router = result.get("router", {})
    payloads = list(subscriber.get("payloads", []))
    netem_qdisc = str(result.get("netem_qdisc", ""))
    qdisc_ok = "netem" in netem_qdisc
    if loss_percent > 0.0:
        qdisc_ok = qdisc_ok and "loss" in netem_qdisc
    evidence_ok = (
        result.get("status") == "ok"
        and qdisc_ok
        and int(router.get("test_dropped_frames", 0)) >= 1
        and int(router.get("ack_nack_forwarded", 0)) >= 3
        and int(router.get("scheduler_queued_frames", 0)) >= 3
        and int(router.get("scheduler_forwarded_frames", 0)) >= 3
        and int(publisher.get("nack_retransmissions", 0)) >= 1
        and {"one", "two", "three"}.issubset(payloads)
    )
    return {
        "profile": profile,
        "repetition_id": repetition_id,
        "loss_percent": loss_percent,
        "status": result.get("status", "failed"),
        "evidence_ok": evidence_ok,
        "topic": result.get("topic"),
        "netem_qdisc": netem_qdisc,
        "publisher_ack_nack_received": int(
            publisher.get("ack_nack_received", 0)
        ),
        "publisher_nack_retransmissions": int(
            publisher.get("nack_retransmissions", 0)
        ),
        "subscriber_ack_nack_sent": int(subscriber.get("ack_nack_sent", 0)),
        "subscriber_payloads": payloads,
        "router_test_dropped_frames": int(
            router.get("test_dropped_frames", 0)
        ),
        "router_ack_nack_forwarded": int(
            router.get("ack_nack_forwarded", 0)
        ),
        "router_scheduler_queued_frames": int(
            router.get("scheduler_queued_frames", 0)
        ),
        "router_scheduler_forwarded_frames": int(
            router.get("scheduler_forwarded_frames", 0)
        ),
        "router_scheduler_deadline_misses": int(
            router.get("scheduler_deadline_misses", 0)
        ),
        "result": result,
    }


def parse_profiles(value: str) -> list[str]:
    profiles = [item.strip() for item in value.split(",") if item.strip()]
    if not profiles:
        raise ValueError("at least one netem profile is required")
    unknown = [
        profile
        for profile in profiles
        if profile == "none" or profile not in NETEM_PROFILES
    ]
    if unknown:
        raise ValueError(f"unknown or non-netem profiles: {','.join(unknown)}")
    return profiles


def parse_ints(value: str) -> list[int]:
    result = [int(item.strip()) for item in value.split(",") if item.strip()]
    if not result:
        raise ValueError("at least one repetition id is required")
    return result


def parse_floats(value: str) -> list[float]:
    result = [
        max(0.0, float(item.strip()))
        for item in value.split(",")
        if item.strip()
    ]
    if not result:
        raise ValueError("at least one loss percent is required")
    return result


if __name__ == "__main__":
    raise SystemExit(main())

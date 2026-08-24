"""Prove per-frame/reader round-robin scheduling of contended fragment repair."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.run_ros2_relay_rmw_netem_probe import (  # noqa: E402
    DEFAULT_FLEETQOX_FRAGMENT_SEND_QUEUE_LIMIT,
    DEFAULT_IMAGE,
    FLEETQOX_RMW,
    run_probe as run_relay,
)


SCHEMA_VERSION = "fleetrmw.fragment_repair_round_robin.v1"
DEFAULT_DROP_INDEXES = "2,3,4,5,6,7,8,9"


def summarize_probe(
    result: dict[str, Any],
    *,
    samples: int,
    payload_bytes: int,
    fragment_chunk_bytes: int,
    pacing_us: int,
    repair_queue_limit: int,
    dropped_fragment_indexes: str,
) -> dict[str, Any]:
    publisher = result.get("publisher")
    metrics = (
        publisher.get("fleetqox_transport_metrics")
        if isinstance(publisher, dict)
        else None
    )
    drop_count = len(
        {
            int(value.strip())
            for value in dropped_fragment_indexes.split(",")
            if value.strip()
        }
    )
    expected_frames = samples * 2
    expected_test_drops = expected_frames * drop_count
    contract_ok = (
        result.get("status") == "ok"
        and result.get("rmw") == FLEETQOX_RMW
        and result.get("netem_enabled") is True
        and result.get("netem_required") is True
        and float(result.get("netem_loss_scale", -1.0)) == 0.0
        and int(result.get("samples", 0)) == samples
        and int(result.get("robot_count", 0)) == 1
        and int(result.get("payload_bytes", 0)) == payload_bytes
        and int(
            result.get("fleetqox_loss_resilient_fragment_chunk_bytes", 0)
        )
        == fragment_chunk_bytes
        and int(result.get("fleetqox_udp_send_pacing_us", 0)) == pacing_us
        and int(result.get("fleetqox_reliable_max_retransmissions", -1)) == 0
        and result.get("fleetqox_fragment_async_send") is True
        and int(result.get("fleetqox_fragment_repair_queue_limit", 0))
        == repair_queue_limit
        and result.get("fleetqox_publisher_test_drop_fragment_indexes")
        == dropped_fragment_indexes
        and int(result.get("relay_expected_count", -1)) == expected_frames
        and int(result.get("relay_payload_count", -1)) == expected_frames
        and int(result.get("publisher_returncode", -1)) == 0
        and int(result.get("relay_returncode", -1)) == 0
        and int(result.get("subscriber_returncode", -1)) == 0
        and isinstance(publisher, dict)
        and publisher.get("ack_wait_complete") is True
        and int(publisher.get("unacked_topic_count", -1)) == 0
        and isinstance(metrics, dict)
        and metrics.get("available") is True
        and int(metrics.get("test_dropped_fragments", -1))
        == expected_test_drops
        and int(metrics.get("fragment_nacks_received", 0)) >= expected_frames
        and int(metrics.get("fragments_selectively_retransmitted", 0))
        >= expected_test_drops
        and 0 < int(metrics.get("fragment_repair_queue_high_water", 0))
        <= repair_queue_limit
        and int(metrics.get("fragment_repair_round_robin_rotations", 0)) > 0
        and int(metrics.get("fragment_repair_frame_switches", 0)) > 0
        and int(metrics.get("fragment_repair_max_active_frames", 0)) >= 2
        and int(
            metrics.get(
                "fragment_repair_max_consecutive_same_frame_while_contended",
                -1,
            )
        )
        == 1
        and int(metrics.get("fragment_repair_queue_deferrals", -1)) == 0
        and int(metrics.get("fragment_send_queue_rejections", -1)) == 0
        and int(metrics.get("fragment_send_failures", -1)) == 0
    )
    return {
        "schema_version": SCHEMA_VERSION,
        "status": "ok" if contract_ok else "failed",
        "samples": samples,
        "expected_frames": expected_frames,
        "payload_bytes": payload_bytes,
        "fragment_chunk_bytes": fragment_chunk_bytes,
        "pacing_us": pacing_us,
        "repair_queue_limit": repair_queue_limit,
        "dropped_fragment_indexes": dropped_fragment_indexes,
        "expected_test_drops": expected_test_drops,
        "transport_contract_ok": contract_ok,
        "per_frame_reader_fragment_repair_round_robin_claim": contract_ok,
        "bounded_fragment_repair_queue_claim": contract_ok,
        "docker_fragment_repair_round_robin_probe_claim": contract_ok,
        "fleet_scale_selective_fragment_repair_claim": False,
        "production_large_sample_reliability_claim": False,
        "claim_boundary": (
            "One publisher emits eight exact 32768-byte frames and drops "
            "eight configured fragments from each. Under 5000-us pacing, the "
            "bounded repair queue must have at least two active frame/reader "
            "scopes, rotate and switch scopes, send at most one consecutive "
            "fragment per scope while contended, deliver and acknowledge all "
            "frames, and report no queue deferral/rejection/send failure. This "
            "is deterministic queue fairness evidence, not a fleet-scale or "
            "production reliability claim."
        ),
        "result": result,
    }


def run_probe(
    *,
    root: Path,
    image: str,
    samples: int,
    payload_bytes: int,
    fragment_chunk_bytes: int,
    pacing_us: int,
    repair_queue_limit: int,
    dropped_fragment_indexes: str,
) -> dict[str, Any]:
    result = run_relay(
        root=root,
        image=image,
        rmw=FLEETQOX_RMW,
        profile="roaming",
        enable_netem=True,
        require_netem=True,
        netem_loss_scale=0.0,
        repetition_seed=7,
        samples=samples,
        robot_count=1,
        payload_bytes=payload_bytes,
        publish_interval_ms=0,
        timeout_s=45.0,
        publisher_linger_s=15.0,
        relay_mode="generic_serialized",
        fleetqox_loss_resilient_fragment_chunk_bytes=fragment_chunk_bytes,
        fleetqox_reliable_max_retransmissions=0,
        fleetqox_udp_send_pacing_us=pacing_us,
        fleetqox_fragment_nack_interval_ms=100,
        fleetqox_fragment_nack_max_requests=10,
        fleetqox_fragment_nack_max_indexes_per_request=8,
        fleetqox_fragment_tail_guard_ms=1000,
        fleetqox_fragment_async_send=True,
        fleetqox_fragment_send_queue_limit=(
            DEFAULT_FLEETQOX_FRAGMENT_SEND_QUEUE_LIMIT
        ),
        fleetqox_fragment_repair_queue_limit=repair_queue_limit,
        fleetqox_publisher_test_drop_fragment_indexes=(
            dropped_fragment_indexes
        ),
    )
    return summarize_probe(
        result,
        samples=samples,
        payload_bytes=payload_bytes,
        fragment_chunk_bytes=fragment_chunk_bytes,
        pacing_us=pacing_us,
        repair_queue_limit=repair_queue_limit,
        dropped_fragment_indexes=dropped_fragment_indexes,
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--image", default=DEFAULT_IMAGE)
    parser.add_argument("--samples", type=int, default=4)
    parser.add_argument("--payload-bytes", type=int, default=32768)
    parser.add_argument("--fragment-chunk-bytes", type=int, default=1024)
    parser.add_argument("--pacing-us", type=int, default=5000)
    parser.add_argument("--fragment-repair-queue-limit", type=int, default=256)
    parser.add_argument("--dropped-fragment-indexes", default=DEFAULT_DROP_INDEXES)
    parser.add_argument(
        "--summary-json",
        type=Path,
        default=Path(
            "results_rmw_socket/"
            "docker_fragment_repair_round_robin_probe_summary.json"
        ),
    )
    args = parser.parse_args()
    summary = run_probe(
        root=ROOT,
        image=args.image,
        samples=max(args.samples, 2),
        payload_bytes=max(args.payload_bytes, 1),
        fragment_chunk_bytes=max(min(args.fragment_chunk_bytes, 60000), 1),
        pacing_us=max(min(args.pacing_us, 100000), 1),
        repair_queue_limit=max(
            min(args.fragment_repair_queue_limit, 262144), 1
        ),
        dropped_fragment_indexes=args.dropped_fragment_indexes,
    )
    path = ROOT / args.summary_json
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(summary, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(
        f"status={summary['status']} "
        "round_robin="
        f"{summary['per_frame_reader_fragment_repair_round_robin_claim']}"
    )
    return 0 if summary["status"] == "ok" else 1


if __name__ == "__main__":
    raise SystemExit(main())

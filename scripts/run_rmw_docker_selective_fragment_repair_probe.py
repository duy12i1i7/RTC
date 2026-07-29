"""Prove fragment-selective FleetRMW repair without whole-sample retries."""

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
    DEFAULT_FLEETQOX_FRAGMENT_HISTORY_LIMIT,
    DEFAULT_FLEETQOX_FRAGMENT_SEND_QUEUE_LIMIT,
    DEFAULT_FLEETQOX_LOSS_RESILIENT_FRAGMENT_CHUNK_BYTES,
    DEFAULT_IMAGE,
    FLEETQOX_RMW,
    run_probe as run_relay,
)


SCHEMA_VERSION = "fleetrmw.selective_fragment_repair.v1"


def summarize_probe(
    result: dict[str, Any],
    *,
    payload_bytes: int,
    fragment_chunk_bytes: int,
    dropped_fragment_indexes: str,
    queue_limit: int,
) -> dict[str, Any]:
    publisher = result.get("publisher")
    relay = result.get("relay")
    publisher_metrics = (
        publisher.get("fleetqox_transport_metrics")
        if isinstance(publisher, dict) else None
    )
    relay_metrics = (
        relay.get("fleetqox_transport_metrics")
        if isinstance(relay, dict) else None
    )
    expected_frames = int(result.get("relay_expected_count", 0))
    configured_drop_count = len(
        {
            int(value.strip())
            for value in dropped_fragment_indexes.split(",")
            if value.strip()
        }
    )
    expected_test_drops = expected_frames * configured_drop_count
    transport_contract_ok = (
        result.get("status") == "ok"
        and result.get("rmw") == FLEETQOX_RMW
        and result.get("netem_enabled") is True
        and result.get("netem_required") is True
        and float(result.get("netem_loss_scale", -1.0)) == 0.0
        and int(result.get("robot_count", 0)) == 1
        and int(result.get("samples", 0)) == 1
        and int(result.get("payload_bytes", 0)) == payload_bytes
        and result.get("payload_size_contract_ok") is True
        and int(result.get("payload_size_min_bytes", 0)) == payload_bytes
        and int(result.get("payload_size_max_bytes", 0)) == payload_bytes
        and int(
            result.get("fleetqox_loss_resilient_fragment_chunk_bytes", 0)
        ) == fragment_chunk_bytes
        and int(result.get("fleetqox_reliable_max_retransmissions", -1)) == 0
        and result.get("fleetqox_fragment_async_send") is True
        and int(result.get("fleetqox_fragment_send_queue_limit", 0))
        == queue_limit
        and result.get("fleetqox_publisher_test_drop_fragment_indexes")
        == dropped_fragment_indexes
        and int(result.get("relay_payload_count", 0)) == expected_frames
        and expected_frames == 2
        and float(result.get("control_delivery_ratio", 0.0)) == 1.0
        and float(result.get("state_delivery_ratio", 0.0)) == 1.0
        and int(result.get("publisher_returncode", -1)) == 0
        and int(result.get("relay_returncode", -1)) == 0
        and int(result.get("subscriber_returncode", -1)) == 0
        and isinstance(publisher, dict)
        and publisher.get("ack_wait_supported") is True
        and publisher.get("ack_wait_complete") is True
        and int(publisher.get("unacked_topic_count", -1)) == 0
        and isinstance(publisher_metrics, dict)
        and publisher_metrics.get("available") is True
        and int(publisher_metrics.get("test_dropped_fragments", -1))
        == expected_test_drops
        and int(publisher_metrics.get("fragment_nacks_received", 0))
        >= expected_test_drops
        and int(
            publisher_metrics.get("fragments_selectively_retransmitted", -1)
        ) == expected_test_drops
        and int(
            publisher_metrics.get("reliable_timeout_retransmissions", -1)
        ) == 0
        and int(publisher_metrics.get("fragment_send_queue_rejections", -1))
        == 0
        and int(publisher_metrics.get("fragment_send_failures", -1)) == 0
        and 0 < int(
            publisher_metrics.get("fragment_send_queue_high_water", 0)
        ) <= queue_limit
        and isinstance(relay_metrics, dict)
        and relay_metrics.get("available") is True
        and int(relay_metrics.get("fragment_nacks_sent", 0))
        >= expected_test_drops
    )
    return {
        "schema_version": SCHEMA_VERSION,
        "status": "ok" if transport_contract_ok else "failed",
        "payload_bytes": payload_bytes,
        "fragment_chunk_bytes": fragment_chunk_bytes,
        "dropped_fragment_indexes": dropped_fragment_indexes,
        "expected_test_drops": expected_test_drops,
        "fragment_send_queue_limit": queue_limit,
        "whole_sample_max_retransmissions": 0,
        "transport_contract_ok": transport_contract_ok,
        "fragment_specific_nack_selective_retransmission_claim":
            transport_contract_ok,
        "docker_selective_fragment_repair_without_whole_sample_retry_claim":
            transport_contract_ok,
        "bounded_async_fragment_send_queue_claim": transport_contract_ok,
        "fleet_scale_selective_fragment_repair_claim": False,
        "production_large_sample_reliability_claim": False,
        "claim_boundary": (
            "Deterministically drops one configured 1024-byte fragment from "
            "each of two exact 32768-byte samples, disables whole-sample "
            "timeout retransmission, and requires fragment NACK counters, "
            "exactly two selective retransmissions, bounded async-queue "
            "metrics, complete delivery/ACK, and clean process teardown. "
            "This does not prove 16-robot/high-rate, secure-fragment, "
            "arbitrary-size, or production reliability."
        ),
        "result": result,
    }


def run_probe(
    *,
    root: Path,
    image: str,
    payload_bytes: int,
    fragment_chunk_bytes: int,
    dropped_fragment_indexes: str,
    queue_limit: int,
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
        samples=1,
        robot_count=1,
        payload_bytes=payload_bytes,
        publish_interval_ms=0,
        timeout_s=15.0,
        publisher_linger_s=3.0,
        relay_mode="generic_serialized",
        fleetqox_loss_resilient_fragment_chunk_bytes=fragment_chunk_bytes,
        fleetqox_reliable_max_retransmissions=0,
        fleetqox_udp_send_pacing_us=1600,
        fleetqox_fragment_nack_interval_ms=250,
        fleetqox_fragment_nack_max_requests=6,
        fleetqox_fragment_history_limit=DEFAULT_FLEETQOX_FRAGMENT_HISTORY_LIMIT,
        fleetqox_fragment_async_send=True,
        fleetqox_fragment_send_queue_limit=queue_limit,
        fleetqox_publisher_test_drop_fragment_indexes=dropped_fragment_indexes,
    )
    return summarize_probe(
        result,
        payload_bytes=payload_bytes,
        fragment_chunk_bytes=fragment_chunk_bytes,
        dropped_fragment_indexes=dropped_fragment_indexes,
        queue_limit=queue_limit,
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--image", default=DEFAULT_IMAGE)
    parser.add_argument("--payload-bytes", type=int, default=32768)
    parser.add_argument(
        "--fragment-chunk-bytes",
        type=int,
        default=DEFAULT_FLEETQOX_LOSS_RESILIENT_FRAGMENT_CHUNK_BYTES,
    )
    parser.add_argument("--dropped-fragment-indexes", default="2")
    parser.add_argument(
        "--fragment-send-queue-limit",
        type=int,
        default=DEFAULT_FLEETQOX_FRAGMENT_SEND_QUEUE_LIMIT,
    )
    parser.add_argument(
        "--summary-json",
        type=Path,
        default=Path(
            "results_rmw_socket/"
            "docker_selective_fragment_repair_probe_summary.json"
        ),
    )
    args = parser.parse_args()
    summary = run_probe(
        root=ROOT,
        image=args.image,
        payload_bytes=max(args.payload_bytes, 1),
        fragment_chunk_bytes=max(min(args.fragment_chunk_bytes, 60000), 1),
        dropped_fragment_indexes=args.dropped_fragment_indexes,
        queue_limit=max(min(args.fragment_send_queue_limit, 262144), 1),
    )
    summary_path = ROOT / args.summary_json
    summary_path.parent.mkdir(parents=True, exist_ok=True)
    summary_path.write_text(
        json.dumps(summary, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(
        f"status={summary['status']} "
        "selective="
        f"{summary['fragment_specific_nack_selective_retransmission_claim']} "
        f"whole_retries={summary['whole_sample_max_retransmissions']}"
    )
    return 0 if summary["status"] == "ok" else 1


if __name__ == "__main__":
    raise SystemExit(main())

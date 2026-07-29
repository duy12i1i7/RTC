"""Run repeated FleetRMW large-sample fragment repair through a matched relay."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.run_large_scale_rmw_comparison import parse_csv_int  # noqa: E402
from scripts.run_ros2_relay_rmw_netem_probe import (  # noqa: E402
    DEFAULT_FLEETQOX_FRAGMENT_HISTORY_LIMIT,
    DEFAULT_FLEETQOX_FRAGMENT_ASSEMBLY_TTL_MS,
    DEFAULT_FLEETQOX_FRAGMENT_NACK_INTERVAL_MS,
    DEFAULT_FLEETQOX_FRAGMENT_NACK_MAX_INDEXES_PER_REQUEST,
    DEFAULT_FLEETQOX_FRAGMENT_NACK_MAX_REQUESTS,
    DEFAULT_FLEETQOX_LOSS_RESILIENT_FRAGMENT_CHUNK_BYTES,
    DEFAULT_FLEETQOX_RELIABLE_MAX_RETRANSMISSIONS,
    DEFAULT_IMAGE,
    FLEETQOX_RMW,
    run_probe as run_relay,
)


SCHEMA_VERSION = "fleetrmw.loss_resilient_large_sample_fragment.v1"


def summarize_campaign(
    rows: list[dict[str, Any]],
    *,
    image: str,
    profile: str,
    netem_loss_scale: float,
    seeds: list[int],
    samples: int,
    robot_count: int,
    payload_bytes: int,
    publish_interval_ms: int,
    timeout_s: float,
    fragment_chunk_bytes: int,
    max_retransmissions: int,
) -> dict[str, Any]:
    expected_per_run = robot_count * 2 * samples
    expected_run_count = len(seeds)
    row_contracts = []
    for row in rows:
        result = row.get("result")
        contract_ok = (
            isinstance(result, dict)
            and row.get("seed") in seeds
            and result.get("status") == "ok"
            and result.get("rmw") == FLEETQOX_RMW
            and result.get("profile") == profile
            and result.get("netem_enabled") is True
            and result.get("netem_required") is True
            and float(result.get("netem_loss_scale", -1.0)) == netem_loss_scale
            and int(result.get("samples", 0)) == samples
            and int(result.get("robot_count", 0)) == robot_count
            and int(result.get("payload_bytes", 0)) == payload_bytes
            and result.get("payload_size_contract_ok") is True
            and int(result.get("payload_size_min_bytes", 0)) == payload_bytes
            and int(result.get("payload_size_max_bytes", 0)) == payload_bytes
            and int(result.get("publish_interval_ms", -1))
            == publish_interval_ms
            and int(result.get("relay_expected_count", -1)) == expected_per_run
            and int(result.get("relay_payload_count", -1)) == expected_per_run
            and float(result.get("control_delivery_ratio", 0.0)) == 1.0
            and float(result.get("state_delivery_ratio", 0.0)) == 1.0
            and int(
                result.get(
                    "fleetqox_loss_resilient_fragment_chunk_bytes",
                    0,
                )
            )
            == fragment_chunk_bytes
            and int(
                result.get("fleetqox_reliable_max_retransmissions", 0)
            )
            == max_retransmissions
            and int(result.get("fleetqox_fragment_nack_interval_ms", 0))
            == DEFAULT_FLEETQOX_FRAGMENT_NACK_INTERVAL_MS
            and int(result.get("fleetqox_fragment_nack_max_requests", 0))
            == DEFAULT_FLEETQOX_FRAGMENT_NACK_MAX_REQUESTS
            and int(
                result.get(
                    "fleetqox_fragment_nack_max_indexes_per_request",
                    0,
                )
            )
            == DEFAULT_FLEETQOX_FRAGMENT_NACK_MAX_INDEXES_PER_REQUEST
            and int(result.get("fleetqox_fragment_history_limit", 0))
            == DEFAULT_FLEETQOX_FRAGMENT_HISTORY_LIMIT
            and int(result.get("fleetqox_fragment_assembly_ttl_ms", 0))
            == DEFAULT_FLEETQOX_FRAGMENT_ASSEMBLY_TTL_MS
            and isinstance(result.get("publisher"), dict)
            and result["publisher"].get("ack_wait_supported") is True
            and result["publisher"].get("ack_wait_complete") is True
            and int(result["publisher"].get("unacked_topic_count", -1)) == 0
        )
        row_contracts.append(contract_ok)
    unique_seed_count = len(
        {
            int(row["seed"])
            for row in rows
            if isinstance(row.get("seed"), int)
        }
    )
    contract_ok = (
        len(rows) == expected_run_count
        and unique_seed_count == expected_run_count
        and len(row_contracts) == expected_run_count
        and all(row_contracts)
    )
    relay_expected_count = expected_per_run * expected_run_count
    relay_payload_count = sum(
        int(row.get("result", {}).get("relay_payload_count", 0))
        for row in rows
        if isinstance(row.get("result"), dict)
    )
    return {
        "schema_version": SCHEMA_VERSION,
        "status": "ok" if contract_ok else "failed",
        "image": image,
        "rmw": FLEETQOX_RMW,
        "profile": profile,
        "netem_loss_scale": netem_loss_scale,
        "seeds": seeds,
        "samples": samples,
        "robot_count": robot_count,
        "payload_bytes": payload_bytes,
        "publish_interval_ms": publish_interval_ms,
        "timeout_s": timeout_s,
        "fragment_chunk_bytes": fragment_chunk_bytes,
        "max_retransmissions": max_retransmissions,
        "fragment_nack_interval_ms":
            DEFAULT_FLEETQOX_FRAGMENT_NACK_INTERVAL_MS,
        "fragment_nack_max_requests":
            DEFAULT_FLEETQOX_FRAGMENT_NACK_MAX_REQUESTS,
        "fragment_nack_max_indexes_per_request":
            DEFAULT_FLEETQOX_FRAGMENT_NACK_MAX_INDEXES_PER_REQUEST,
        "fragment_history_limit": DEFAULT_FLEETQOX_FRAGMENT_HISTORY_LIMIT,
        "fragment_assembly_ttl_ms":
            DEFAULT_FLEETQOX_FRAGMENT_ASSEMBLY_TTL_MS,
        "run_count": len(rows),
        "ok_run_count": sum(row_contracts),
        "failed_run_count": len(rows) - sum(row_contracts),
        "relay_expected_count": relay_expected_count,
        "relay_payload_count": relay_payload_count,
        "exact_payload_size_contract_ok": contract_ok,
        "loss_resilient_fragment_configuration_contract_ok": contract_ok,
        "publisher_ack_horizon_contract_ok": contract_ok,
        "loss_resilient_large_sample_fragment_repair_claim": contract_ok,
        "production_large_sample_reliability_claim": False,
        "claim_boundary": (
            f"Proves {payload_bytes}-byte FleetRMW samples across two RMW hops "
            f"at {robot_count} robot, {len(seeds)} seeds, profile {profile}, "
            f"and loss scale {netem_loss_scale} with {fragment_chunk_bytes}-byte "
            "stable fragments accumulated across timeout retransmission. It does "
            "not prove high-rate, arbitrary-size, secure-fragment, fleet-scale, "
            "or production reliability."
        ),
        "runs": rows,
    }


def run_campaign(
    *,
    root: Path,
    image: str,
    profile: str,
    netem_loss_scale: float,
    seeds: list[int],
    samples: int,
    robot_count: int,
    payload_bytes: int,
    publish_interval_ms: int,
    timeout_s: float,
    fragment_chunk_bytes: int,
    max_retransmissions: int,
) -> dict[str, Any]:
    rows = []
    for seed in seeds:
        print(f"run seed={seed}", file=sys.stderr, flush=True)
        result = run_relay(
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
            fleetqox_loss_resilient_fragment_chunk_bytes=fragment_chunk_bytes,
            fleetqox_reliable_max_retransmissions=max_retransmissions,
            fleetqox_udp_send_pacing_us=0,
        )
        rows.append({"seed": seed, "status": result.get("status"), "result": result})
    return summarize_campaign(
        rows,
        image=image,
        profile=profile,
        netem_loss_scale=netem_loss_scale,
        seeds=seeds,
        samples=samples,
        robot_count=robot_count,
        payload_bytes=payload_bytes,
        publish_interval_ms=publish_interval_ms,
        timeout_s=timeout_s,
        fragment_chunk_bytes=fragment_chunk_bytes,
        max_retransmissions=max_retransmissions,
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--image", default=DEFAULT_IMAGE)
    parser.add_argument("--profile", default="roaming")
    parser.add_argument("--netem-loss-scale", type=float, default=0.25)
    parser.add_argument("--seeds", default="7,13,29,37,43")
    parser.add_argument("--samples", type=int, default=3)
    parser.add_argument("--robot-count", type=int, default=1)
    parser.add_argument("--payload-bytes", type=int, default=32768)
    parser.add_argument("--publish-interval-ms", type=int, default=2000)
    parser.add_argument("--timeout-s", type=float, default=25.0)
    parser.add_argument(
        "--fragment-chunk-bytes",
        type=int,
        default=DEFAULT_FLEETQOX_LOSS_RESILIENT_FRAGMENT_CHUNK_BYTES,
    )
    parser.add_argument(
        "--max-retransmissions",
        type=int,
        default=DEFAULT_FLEETQOX_RELIABLE_MAX_RETRANSMISSIONS,
    )
    parser.add_argument(
        "--summary-json",
        type=Path,
        default=Path(
            "results_rmw_socket/"
            "docker_loss_resilient_large_sample_fragment_5run_summary.json"
        ),
    )
    args = parser.parse_args()
    summary = run_campaign(
        root=ROOT,
        image=args.image,
        profile=args.profile,
        netem_loss_scale=max(args.netem_loss_scale, 0.0),
        seeds=parse_csv_int(args.seeds, minimum=0),
        samples=max(args.samples, 1),
        robot_count=max(args.robot_count, 1),
        payload_bytes=max(args.payload_bytes, 1),
        publish_interval_ms=max(args.publish_interval_ms, 1),
        timeout_s=max(args.timeout_s, 1.0),
        fragment_chunk_bytes=max(min(args.fragment_chunk_bytes, 60000), 1),
        max_retransmissions=max(min(args.max_retransmissions, 100), 1),
    )
    summary_path = ROOT / args.summary_json
    summary_path.parent.mkdir(parents=True, exist_ok=True)
    summary_path.write_text(
        json.dumps(summary, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(
        f"status={summary['status']} ok={summary['ok_run_count']}/"
        f"{summary['run_count']} relay={summary['relay_payload_count']}/"
        f"{summary['relay_expected_count']}"
    )
    return 0 if summary["status"] == "ok" else 1


if __name__ == "__main__":
    raise SystemExit(main())

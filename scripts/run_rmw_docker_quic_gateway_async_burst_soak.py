"""Run repeated async QUIC gateway burst probes and aggregate soak telemetry."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.run_rmw_docker_quic_gateway_netem_publish_probe import (
    run_probe as run_netem_probe,
)
from scripts.run_rmw_docker_quic_gateway_publish_probe import DEFAULT_IMAGE, run_probe


SCHEMA_VERSION = "fleetrmw.docker_quic_gateway_async_burst_soak.v1"


def _probe_int(row: dict[str, Any], key: str) -> int:
    try:
        return int(row.get("probe", {}).get(key, 0))
    except (TypeError, ValueError):
        return 0


def aggregate(rows: list[dict[str, Any]], *, netem: bool) -> dict[str, Any]:
    ok_rows = [row for row in rows if row.get("status") == "ok"]
    total_frames = sum(_probe_int(row, "quic_gateway_frames_sent") for row in rows)
    total_bytes = sum(_probe_int(row, "quic_gateway_bytes_sent") for row in rows)
    total_enqueued = sum(_probe_int(row, "quic_gateway_frames_enqueued") for row in rows)
    total_failed = sum(_probe_int(row, "quic_gateway_frames_failed") for row in rows)
    total_dropped = sum(_probe_int(row, "quic_gateway_frames_dropped") for row in rows)
    total_server_body_bytes = sum(int(row.get("server_body_total_bytes", 0) or 0) for row in rows)
    qlog_total_bytes = sum(int(row.get("qlog_total_bytes", 0) or 0) for row in rows)
    netem_sent_packets = sum(
        int(row.get("netem", {}).get("counters_after", {}).get("sent_packets", 0) or 0)
        for row in rows
    )
    rtt_samples = sum(
        int(
            row.get("path_telemetry", {})
            .get("rtt_raw", {})
            .get("latest", {})
            .get("sample_count", 0)
            or 0
        )
        for row in rows
    )
    return {
        "schema_version": SCHEMA_VERSION,
        "status": "ok" if len(ok_rows) == len(rows) and rows else "failed",
        "mode": "netem_async_burst" if netem else "local_async_burst",
        "run_count": len(rows),
        "ok_run_count": len(ok_rows),
        "total_quic_gateway_frames_sent": total_frames,
        "total_quic_gateway_frames_enqueued": total_enqueued,
        "total_quic_gateway_bytes_sent": total_bytes,
        "total_server_body_bytes": total_server_body_bytes,
        "total_quic_gateway_frames_failed": total_failed,
        "total_quic_gateway_frames_dropped": total_dropped,
        "qlog_total_bytes": qlog_total_bytes,
        "netem_sent_packets": netem_sent_packets if netem else None,
        "rtt_sample_count": rtt_samples if netem else None,
        "server_payload_bytes_match": total_bytes == total_server_body_bytes and total_bytes > 0,
        "subprocess_backed": True,
        "production_quic_backend": False,
        "full_bidirectional_quic_backend": False,
        "rows": rows,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--image", default=DEFAULT_IMAGE)
    parser.add_argument("--iterations", type=int, default=2)
    parser.add_argument("--base-port", type=int, default=4451)
    parser.add_argument("--netem", action="store_true")
    parser.add_argument("--delay-ms", type=int, default=20)
    parser.add_argument("--jitter-ms", type=int, default=5)
    parser.add_argument("--loss-percent", type=float, default=0.0)
    parser.add_argument(
        "--summary-json",
        default="results_rmw_socket/docker_quic_gateway_async_burst_soak_summary.json",
    )
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    rows: list[dict[str, Any]] = []
    iterations = max(args.iterations, 1)
    for index in range(iterations):
        port = args.base_port + index
        if args.netem:
            row = run_netem_probe(
                root=ROOT,
                image=args.image,
                port=port,
                delay_ms=max(args.delay_ms, 0),
                jitter_ms=max(args.jitter_ms, 0),
                loss_percent=max(args.loss_percent, 0.0),
                async_gateway=True,
                schema_version="fleetrmw.docker_quic_gateway_netem_async_burst_probe.v1",
                probe_executable="fleetrmw_quic_gateway_burst_publish_probe",
            )
        else:
            row = run_probe(
                root=ROOT,
                image=args.image,
                port=port,
                async_gateway=True,
                schema_version="fleetrmw.docker_quic_gateway_async_burst_probe.v1",
                probe_executable="fleetrmw_quic_gateway_burst_publish_probe",
            )
        row["iteration"] = index
        rows.append(row)

    summary = aggregate(rows, netem=args.netem)
    output = ROOT / args.summary_json
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    if args.json:
        print(json.dumps(summary, sort_keys=True))
    else:
        print(
            f"status={summary['status']} ok_runs={summary['ok_run_count']}/"
            f"{summary['run_count']} frames={summary['total_quic_gateway_frames_sent']}"
        )
    return 0 if summary["status"] == "ok" else 1


if __name__ == "__main__":
    raise SystemExit(main())

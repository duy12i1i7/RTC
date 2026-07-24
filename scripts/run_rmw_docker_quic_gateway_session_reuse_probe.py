"""Verify QUIC gateway session-reuse file plumbing with ngtcp2/GnuTLS."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import shutil
import sys
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.run_rmw_docker_quic_gateway_publish_probe import (
    DEFAULT_IMAGE,
    parse_quic_session_reuse_telemetry,
    run_probe,
)


SCHEMA_VERSION = "fleetrmw.docker_quic_gateway_session_reuse_probe.v1"


def file_status(path: Path) -> dict[str, Any]:
    return {
        "exists": path.exists(),
        "size_bytes": path.stat().st_size if path.exists() else 0,
    }


def run_session_reuse_probe(*, root: Path, image: str, port: int) -> dict[str, Any]:
    tmp = root / f".tmp_fleetrmw_quic_gateway_session_reuse_{os.getpid()}"
    tmp.mkdir(parents=True, exist_ok=True)
    session_file = tmp / "gtlsclient-session.bin"
    tp_file = tmp / "gtlsclient-transport-params.bin"
    token_file = tmp / "gtlsclient-token.bin"
    try:
        row = run_probe(
            root=root,
            image=image,
            port=port,
            schema_version="fleetrmw.docker_quic_gateway_session_reuse_inner_probe.v1",
            probe_executable="fleetrmw_quic_gateway_burst_publish_probe",
            extra_env={
                "FLEETQOX_RMW_QUIC_SESSION_FILE": f"/work/{session_file.relative_to(root)}",
                "FLEETQOX_RMW_QUIC_TP_FILE": f"/work/{tp_file.relative_to(root)}",
                "FLEETQOX_RMW_QUIC_TOKEN_FILE": f"/work/{token_file.relative_to(root)}",
            },
        )
        probe = row.get("probe", {})
        frames_sent = int(probe.get("quic_gateway_frames_sent", 0) or 0)
        session_status = file_status(session_file)
        tp_status = file_status(tp_file)
        token_status = file_status(token_file)
        session_files_persisted = (
            session_status["exists"]
            and session_status["size_bytes"] > 0
            and tp_status["exists"]
            and tp_status["size_bytes"] > 0
        )
        telemetry = parse_quic_session_reuse_telemetry(
            str(row.get("client_log_excerpt", "")),
            str(row.get("server_log_excerpt", "")),
        )
        for key in tuple(telemetry):
            if key in row:
                telemetry[key] = row[key]
        configured_for_multiple_uploads = frames_sent > 1 and session_files_persisted
        ok = (
            row.get("status") == "ok"
            and configured_for_multiple_uploads
            and row.get("server_payload_matches_rmw_frame_bytes") is True
        )
        return {
            "schema_version": SCHEMA_VERSION,
            "status": "ok" if ok else "failed",
            "session_reuse_file_configured": True,
            "session_files_persisted": session_files_persisted,
            "session_file_reused_by_multiple_uploads": configured_for_multiple_uploads,
            **telemetry,
            "session_resumption_attempted_observed": telemetry[
                "session_resumption_attempted_observed"
            ],
            "session_resumption_observed": telemetry["session_resumption_observed"],
            "zero_rtt_packet_observed": telemetry["zero_rtt_packet_observed"],
            "zero_rtt_accepted_observed": telemetry["zero_rtt_accepted_observed"],
            "zero_rtt_claim": telemetry["zero_rtt_accepted_observed"],
            "subprocess_backed": True,
            "production_quic_backend": False,
            "full_bidirectional_quic_backend": False,
            "quic_gateway_frames_sent": frames_sent,
            "session_file": session_status,
            "transport_parameters_file": tp_status,
            "token_file": token_status,
            "inner_probe": row,
        }
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--image", default=DEFAULT_IMAGE)
    parser.add_argument("--port", type=int, default=4462)
    parser.add_argument(
        "--summary-json",
        default="results_rmw_socket/docker_quic_gateway_session_reuse_probe_summary.json",
    )
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    summary = run_session_reuse_probe(root=ROOT, image=args.image, port=args.port)
    output = ROOT / args.summary_json
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    if args.json:
        print(json.dumps(summary, sort_keys=True))
    else:
        print(
            f"status={summary['status']} frames={summary['quic_gateway_frames_sent']} "
            f"session_file={summary['session_file']['size_bytes']}B"
        )
    return 0 if summary["status"] == "ok" else 1


if __name__ == "__main__":
    raise SystemExit(main())

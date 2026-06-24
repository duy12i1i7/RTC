"""Verify async QUIC gateway burst rmw_publish across Docker netem."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.run_rmw_docker_quic_gateway_netem_publish_probe import DEFAULT_IMAGE, run_probe


SCHEMA_VERSION = "fleetrmw.docker_quic_gateway_netem_async_burst_probe.v1"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--image", default=DEFAULT_IMAGE)
    parser.add_argument("--port", type=int, default=4450)
    parser.add_argument("--delay-ms", type=int, default=20)
    parser.add_argument("--jitter-ms", type=int, default=5)
    parser.add_argument("--loss-percent", type=float, default=0.0)
    parser.add_argument(
        "--summary-json",
        default="results_rmw_socket/docker_quic_gateway_netem_async_burst_probe_summary.json",
    )
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    summary = run_probe(
        root=ROOT,
        image=args.image,
        port=args.port,
        delay_ms=max(args.delay_ms, 0),
        jitter_ms=max(args.jitter_ms, 0),
        loss_percent=max(args.loss_percent, 0.0),
        async_gateway=True,
        schema_version=SCHEMA_VERSION,
        probe_executable="fleetrmw_quic_gateway_burst_publish_probe",
    )
    output = ROOT / args.summary_json
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    if args.json:
        print(json.dumps(summary, sort_keys=True))
    else:
        print(f"status={summary['status']} transport={summary.get('transport')}")
    return 0 if summary["status"] == "ok" else 1


if __name__ == "__main__":
    raise SystemExit(main())

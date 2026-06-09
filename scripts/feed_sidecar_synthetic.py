"""Feed synthetic ROS-like flow observations into the sidecar runtime."""

from __future__ import annotations

import argparse
import json

from fleetqox.sidecar_runtime import generate_synthetic_batches, send_batches


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--scenario", default="sidecar_synthetic")
    parser.add_argument("--robots", type=int, default=10)
    parser.add_argument("--seconds", type=int, default=2)
    parser.add_argument("--seed", type=int, default=7)
    parser.add_argument("--capacity-bytes-per-second", type=int, default=None)
    parser.add_argument("--link-rtt-ms", type=float, default=None)
    parser.add_argument("--link-jitter-ms", type=float, default=None)
    parser.add_argument("--link-loss", type=float, default=None)
    parser.add_argument("--max-ticks", type=int, default=None)
    parser.add_argument("--no-stop", action="store_true")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    batches = generate_synthetic_batches(
        scenario=args.scenario,
        robots=args.robots,
        seconds=args.seconds,
        seed=args.seed,
        capacity_bytes_per_second=args.capacity_bytes_per_second,
        link_rtt_ms=args.link_rtt_ms,
        link_jitter_ms=args.link_jitter_ms,
        link_loss=args.link_loss,
        max_ticks=args.max_ticks,
    )
    responses = send_batches(
        host=args.host,
        port=args.port,
        batches=batches,
        stop_after=not args.no_stop,
    )
    emitted = sum(int(response.get("emitted", 0)) for response in responses)
    accepted = sum(int(response.get("accepted", 0)) for response in responses)
    result = {
        "batches": len(batches),
        "accepted": accepted,
        "emitted": emitted,
        "responses": len(responses),
    }
    if args.json:
        print(json.dumps(result, sort_keys=True))
        return
    print(f"sent {len(batches)} batches, accepted {accepted} flows, emitted {emitted} UDP packets")


if __name__ == "__main__":
    main()

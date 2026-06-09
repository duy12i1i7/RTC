"""Feed synthetic observations into sidecar runtime with action feedback."""

from __future__ import annotations

import argparse
import json
import socket
from collections import Counter

from fleetqox.sidecar_runtime import SyntheticBatchStream


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--scenario", default="sidecar_closed_loop")
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

    result = feed_closed_loop(
        host=args.host,
        port=args.port,
        scenario=args.scenario,
        robots=args.robots,
        seconds=args.seconds,
        seed=args.seed,
        capacity_bytes_per_second=args.capacity_bytes_per_second,
        link_rtt_ms=args.link_rtt_ms,
        link_jitter_ms=args.link_jitter_ms,
        link_loss=args.link_loss,
        max_ticks=args.max_ticks,
        stop_after=not args.no_stop,
    )
    if args.json:
        print(json.dumps(result, sort_keys=True))
        return
    print(
        f"sent {result['batches']} closed-loop batches, "
        f"accepted {result['accepted']} flows, emitted {result['emitted']} UDP packets, "
        f"status {result['status']}"
    )


def feed_closed_loop(
    *,
    host: str,
    port: int,
    scenario: str,
    robots: int,
    seconds: int,
    seed: int,
    capacity_bytes_per_second: int | None,
    link_rtt_ms: float | None = None,
    link_jitter_ms: float | None = None,
    link_loss: float | None = None,
    max_ticks: int | None = None,
    stop_after: bool = True,
) -> dict[str, object]:
    stream = SyntheticBatchStream(
        scenario=scenario,
        robots=robots,
        seconds=seconds,
        seed=seed,
        capacity_bytes_per_second=capacity_bytes_per_second,
        link_rtt_ms=link_rtt_ms,
        link_jitter_ms=link_jitter_ms,
        link_loss=link_loss,
        max_ticks=max_ticks,
        include_feedback=True,
    )
    responses = 0
    accepted = 0
    emitted = 0
    action_counts: Counter[str] = Counter()
    termination_reason = "completed"

    with socket.create_connection((host, port), timeout=10.0) as conn:
        conn_file = conn.makefile("rwb")
        for batch in stream:
            conn_file.write((json.dumps(batch, sort_keys=True) + "\n").encode("utf-8"))
            conn_file.flush()
            response, reason = read_json_response(conn_file)
            if response is None:
                termination_reason = reason
                break
            stream.apply_feedback(response)
            responses += 1
            accepted += int(response.get("accepted", 0))
            emitted += int(response.get("emitted", 0))
            counts = response.get("action_counts", {})
            if isinstance(counts, dict):
                action_counts.update({str(key): int(value) for key, value in counts.items()})
        if stop_after and termination_reason == "completed":
            conn_file.write(b'{"type":"stop"}\n')
            conn_file.flush()
            response, reason = read_json_response(conn_file)
            if response is None:
                termination_reason = reason
            else:
                responses += 1

    return {
        "mode": "closed_loop",
        "status": "completed" if termination_reason == "completed" else "partial",
        "termination_reason": termination_reason,
        "batches": stream.ticks,
        "accepted": accepted,
        "emitted": emitted,
        "responses": responses,
        "action_counts": dict(sorted(action_counts.items())),
    }


def read_json_response(conn_file) -> tuple[dict[str, object] | None, str]:
    try:
        line = conn_file.readline()
    except (TimeoutError, socket.timeout):
        return None, "response_timeout"
    if not line:
        return None, "connection_closed"
    return json.loads(line.decode("utf-8")), "completed"


if __name__ == "__main__":
    main()

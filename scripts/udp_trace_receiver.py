"""UDP receiver for Docker/netem trace emulation."""

from __future__ import annotations

import argparse
import json
import socket
import time
from pathlib import Path

from fleetqox.rmw_frame import decode_data_frame, sidecar_event_from_data_frame


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument("--port", type=int, default=9100)
    parser.add_argument("--idle-timeout-s", type=float, default=3.0)
    parser.add_argument("--max-runtime-s", type=float, default=120.0)
    args = parser.parse_args()

    args.output.parent.mkdir(parents=True, exist_ok=True)
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.bind((args.host, args.port))
    sock.settimeout(0.25)

    started = time.monotonic()
    last_packet = started
    count = 0
    with args.output.open("w", encoding="utf-8") as handle:
        while True:
            now = time.monotonic()
            if now - started > args.max_runtime_s:
                break
            if count and now - last_packet > args.idle_timeout_s:
                break
            try:
                data, _ = sock.recvfrom(2_000_000)
            except socket.timeout:
                continue
            recv_ns = time.monotonic_ns()
            last_packet = time.monotonic()
            packet = _decode(data)
            if packet is None:
                continue
            send_ns = int(packet["send_monotonic_ns"])
            packet["recv_monotonic_ns"] = recv_ns
            packet["latency_ms"] = (recv_ns - send_ns) / 1_000_000.0
            handle.write(json.dumps(packet, sort_keys=True) + "\n")
            count += 1
    print(f"received {count} packets")


def _decode(data: bytes) -> dict[str, object] | None:
    frame = decode_data_frame(data)
    if frame is not None:
        packet = sidecar_event_from_data_frame(frame)
    else:
        text = data.rstrip(b" ").decode("utf-8", errors="replace")
        try:
            packet = json.loads(text)
        except json.JSONDecodeError:
            return None
    if "send_monotonic_ns" not in packet:
        return None
    return {
        "event_id": int(packet["event_id"]),
        "timestamp_ms": float(packet["timestamp_ms"]),
        "policy": str(packet["policy"]),
        "flow_id": str(packet["flow_id"]),
        "flow_class": str(packet["flow_class"]),
        "src": str(packet["src"]),
        "dst": str(packet["dst"]),
        "bytes": int(float(packet["bytes"])),
        "deadline_ms": float(packet["deadline_ms"]),
        "semantic_utility": float(packet["semantic_utility"]),
        "send_monotonic_ns": int(packet["send_monotonic_ns"]),
    }


if __name__ == "__main__":
    main()

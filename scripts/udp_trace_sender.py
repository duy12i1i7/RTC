"""UDP sender for Docker/netem trace emulation."""

from __future__ import annotations

import argparse
import csv
import json
import socket
import time
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--trace", type=Path, required=True)
    parser.add_argument("--host", required=True)
    parser.add_argument("--port", type=int, default=9100)
    parser.add_argument("--time-scale", type=float, default=1.0)
    parser.add_argument("--max-packets", type=int, default=0)
    args = parser.parse_args()

    if args.time_scale <= 0:
        raise SystemExit("--time-scale must be positive")

    rows = _load_rows(args.trace, args.max_packets)
    address = (args.host, args.port)
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    start = time.monotonic_ns()

    sent = 0
    for row in rows:
        target_ns = start + int(float(row["timestamp_ms"]) / args.time_scale * 1_000_000)
        _sleep_until(target_ns)
        row["send_monotonic_ns"] = time.monotonic_ns()
        payload = _payload(row)
        sock.sendto(payload, address)
        sent += 1
    print(f"sent {sent} packets")


def _load_rows(trace: Path, max_packets: int) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    with trace.open("r", newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        for row in reader:
            rows.append(dict(row))
            if max_packets and len(rows) >= max_packets:
                break
    return rows


def _payload(row: dict[str, object]) -> bytes:
    target_size = max(1, int(float(row["bytes"])))
    body = json.dumps(row, sort_keys=True, separators=(",", ":")).encode("utf-8")
    if len(body) >= target_size:
        return body
    return body + b" " * (target_size - len(body))


def _sleep_until(target_ns: int) -> None:
    while True:
        now = time.monotonic_ns()
        remaining = target_ns - now
        if remaining <= 0:
            return
        time.sleep(min(remaining / 1_000_000_000.0, 0.01))


if __name__ == "__main__":
    main()

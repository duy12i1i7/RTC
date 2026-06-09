"""Run the FleetQoX deterministic benchmark."""

from __future__ import annotations

import argparse

from fleetqox.simulator import format_results, run_benchmark


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--robots", type=int, default=100)
    parser.add_argument("--seconds", type=int, default=60)
    parser.add_argument("--seed", type=int, default=7)
    parser.add_argument("--capacity-bytes-per-second", type=int, default=None)
    args = parser.parse_args()

    if args.robots <= 0:
        raise SystemExit("--robots must be positive")
    if args.seconds <= 0:
        raise SystemExit("--seconds must be positive")

    results = run_benchmark(
        robots=args.robots,
        seconds=args.seconds,
        seed=args.seed,
        capacity_bytes_per_second=args.capacity_bytes_per_second,
    )
    print(format_results(results))


if __name__ == "__main__":
    main()

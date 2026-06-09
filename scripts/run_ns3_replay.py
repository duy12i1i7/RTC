"""Run the FleetQoX ns-3 trace replay in an external ns-3 workspace."""

from __future__ import annotations

import argparse
import shutil
import subprocess
from pathlib import Path


REPLAY_SOURCE = Path("external/ns3/fleetqox_trace_replay.cc")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--ns3-workspace", type=Path, default=None)
    parser.add_argument("--trace", type=Path, required=True)
    parser.add_argument("--data-rate", default="54Mbps")
    parser.add_argument("--delay", default="2ms")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    workspace = args.ns3_workspace or _workspace_from_env()
    if workspace is None:
        raise SystemExit("provide --ns3-workspace or set NS3_WORKSPACE")
    workspace = workspace.resolve()
    if not workspace.exists():
        raise SystemExit(f"ns-3 workspace does not exist: {workspace}")
    ns3 = workspace / "ns3"
    if not ns3.exists():
        raise SystemExit(f"ns3 launcher not found at {ns3}")
    if not REPLAY_SOURCE.exists():
        raise SystemExit(f"missing replay source: {REPLAY_SOURCE}")
    if not args.trace.exists():
        raise SystemExit(f"trace file does not exist: {args.trace}")

    scratch = workspace / "scratch"
    scratch.mkdir(exist_ok=True)
    target = scratch / "fleetqox_trace_replay.cc"
    shutil.copyfile(REPLAY_SOURCE, target)

    command = [
        str(ns3),
        "run",
        (
            "scratch/fleetqox_trace_replay "
            f"--trace={args.trace.resolve()} "
            f"--dataRate={args.data_rate} "
            f"--delay={args.delay}"
        ),
    ]
    print(" ".join(command))
    if args.dry_run:
        return
    subprocess.run(command, cwd=workspace, check=True)


def _workspace_from_env() -> Path | None:
    import os

    value = os.environ.get("NS3_WORKSPACE")
    return Path(value) if value else None


if __name__ == "__main__":
    main()

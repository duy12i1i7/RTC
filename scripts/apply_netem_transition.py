"""Apply a timed tc/netem profile transition schedule."""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path

from scripts.run_sidecar_repeated_netem import NETEM_PROFILES


@dataclass(frozen=True)
class NetemTransition:
    profile: str
    at_s: float

    def as_payload(self) -> dict[str, object]:
        return {
            "profile": self.profile,
            "at_s": self.at_s,
            "config": NETEM_PROFILES[self.profile].as_config(),
        }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dev", default="eth0")
    parser.add_argument("--schedule", required=True)
    parser.add_argument("--log", type=Path)
    parser.add_argument("--start-delay-s", type=float, default=0.0)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    transitions = parse_transition_schedule(args.schedule)
    records = apply_transition_schedule(
        transitions,
        dev=args.dev,
        log=args.log,
        start_delay_s=args.start_delay_s,
        dry_run=args.dry_run,
    )
    result = {
        "dev": args.dev,
        "schedule": [transition.as_payload() for transition in transitions],
        "records": records,
        "status": "ok",
    }
    if args.json:
        print(json.dumps(result, sort_keys=True))
    else:
        print(f"netem transition schedule applied: {len(records)} steps")


def parse_transition_schedule(value: str) -> list[NetemTransition]:
    transitions = []
    for index, raw_part in enumerate(value.split(",")):
        part = raw_part.strip()
        if not part:
            continue
        if "@" in part:
            profile, at_s = part.split("@", 1)
        elif ":" in part:
            profile, at_s = part.split(":", 1)
        else:
            profile, at_s = part, str(index)
        profile = profile.strip()
        if profile not in NETEM_PROFILES:
            choices = ", ".join(sorted(NETEM_PROFILES))
            raise SystemExit(f"unknown netem transition profile: {profile}; choices: {choices}")
        try:
            offset = float(at_s)
        except ValueError as exc:
            raise SystemExit(f"invalid transition offset for {profile}: {at_s}") from exc
        if offset < 0:
            raise SystemExit("transition offsets must be non-negative")
        transitions.append(NetemTransition(profile=profile, at_s=offset))
    if not transitions:
        raise SystemExit("--schedule must contain at least one profile")
    transitions.sort(key=lambda item: item.at_s)
    return transitions


def apply_transition_schedule(
    transitions: list[NetemTransition],
    *,
    dev: str,
    log: Path | None = None,
    start_delay_s: float = 0.0,
    dry_run: bool = False,
) -> list[dict[str, object]]:
    records = []
    delay_s = max(0.0, float(start_delay_s))
    if delay_s > 0.0:
        time.sleep(delay_s)
    started = time.monotonic()
    for transition in transitions:
        sleep_s = transition.at_s - (time.monotonic() - started)
        if sleep_s > 0:
            time.sleep(sleep_s)
        command = tc_command_for_transition(transition, dev=dev)
        status = "dry_run"
        returncode = 0
        stderr = ""
        if not dry_run:
            if shutil.which("tc") is None:
                status = "missing_tc"
                returncode = 127
                stderr = "tc command not found"
            else:
                completed = subprocess.run(
                    command,
                    check=False,
                    capture_output=True,
                    text=True,
                )
                returncode = completed.returncode
                stderr = completed.stderr.strip()
                status = "applied" if completed.returncode == 0 else "failed"
        record = {
            "profile": transition.profile,
            "scheduled_at_s": transition.at_s,
            "elapsed_s": max(0.0, time.monotonic() - started),
            "config": NETEM_PROFILES[transition.profile].as_config(),
            "command": command,
            "status": status,
            "returncode": returncode,
            "start_delay_s": delay_s,
            **({"stderr": stderr} if stderr else {}),
        }
        records.append(record)
        if log:
            log.parent.mkdir(parents=True, exist_ok=True)
            with log.open("a", encoding="utf-8") as handle:
                handle.write(json.dumps(record, sort_keys=True) + "\n")
        if returncode != 0 and not dry_run:
            raise SystemExit(f"failed to apply netem profile {transition.profile}: {stderr}")
    return records


def tc_command_for_transition(
    transition: NetemTransition,
    *,
    dev: str,
) -> list[str]:
    config = NETEM_PROFILES[transition.profile].as_config()
    return [
        "tc",
        "qdisc",
        "replace",
        "dev",
        dev,
        "root",
        "netem",
        "delay",
        f"{config['delay_ms']}ms",
        f"{config['jitter_ms']}ms",
        "loss",
        f"{config['loss_percent']}%",
        "rate",
        f"{config['rate_mbit']}mbit",
    ]


if __name__ == "__main__":
    main()

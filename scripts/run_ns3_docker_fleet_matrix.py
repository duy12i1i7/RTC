"""Run a repeatable FleetQoX trace matrix in native ns-3 inside Docker."""

from __future__ import annotations

import argparse
from collections import defaultdict
import json
from pathlib import Path
import shlex
import subprocess
import sys
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from fleetqox.trace import generate_trace_events, write_simulator_csv


SCHEMA_VERSION = "fleetqox.ns3_docker_fleet_matrix.v1"
DEFAULT_IMAGE = "localhost/fleetrmw/rmw-netem:jazzy"
POLICIES = ("fifo", "static_priority", "fleetqox_predictive_guarded")
PROFILES = {
    "wifi": {"data_rate": "54Mbps", "delay": "2ms", "error_rate": 0.01},
    "wan": {"data_rate": "20Mbps", "delay": "30ms", "error_rate": 0.02},
    "roaming": {"data_rate": "6Mbps", "delay": "15ms", "error_rate": 0.08},
}


def parse_csv_summary(stdout: str) -> list[dict[str, Any]]:
    lines = [line.strip() for line in stdout.splitlines() if line.strip()]
    try:
        header_index = lines.index(
            "policy,tx,rx,bytes,deadline_miss_ratio,p50_ms,p99_ms,utility"
        )
    except ValueError:
        return []
    rows = []
    for line in lines[header_index + 1 :]:
        cells = line.split(",")
        if len(cells) != 8:
            continue
        rows.append(
            {
                "policy": cells[0],
                "tx": int(cells[1]),
                "rx": int(cells[2]),
                "bytes": int(cells[3]),
                "deadline_miss_ratio": float(cells[4]),
                "p50_ms": float(cells[5]),
                "p99_ms": float(cells[6]),
                "utility": float(cells[7]),
            }
        )
    return rows


def docker_run(image: str, command: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [
            "docker", "run", "--rm", "--entrypoint", "bash",
            "-v", f"{ROOT}:/work", "-w", "/work", image, "-lc", command,
        ],
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )


def run_matrix(
    *,
    image: str,
    output_dir: Path,
    robot_counts: list[int],
    seeds: list[int],
    seconds: int,
) -> dict[str, Any]:
    output_dir.mkdir(parents=True, exist_ok=True)
    binary = output_dir / ".fleetqox_ns3_replay"
    compile_command = (
        "g++ -std=c++17 external/ns3/fleetqox_trace_replay.cc "
        f"-o {shlex.quote(str(binary))} "
        "$(pkg-config --cflags --libs ns3-applications ns3-bridge ns3-core ns3-csma "
        "ns3-internet ns3-network ns3-wifi ns3-mobility) && "
        "pkg-config --modversion ns3-core"
    )
    compiled = docker_run(image, compile_command)
    if compiled.returncode != 0:
        return {
            "schema_version": SCHEMA_VERSION,
            "status": "failed",
            "stage": "compile",
            "stdout": compiled.stdout,
            "stderr": compiled.stderr,
        }
    ns3_version = compiled.stdout.strip().splitlines()[-1]
    rows: list[dict[str, Any]] = []
    trace_metadata: list[dict[str, Any]] = []
    try:
        for robots in robot_counts:
            for seed in seeds:
                trace_path = output_dir / f"trace_{robots}robot_seed{seed}.csv"
                events = generate_trace_events(
                    scenario=f"ns3_csma_{robots}robot",
                    robots=robots,
                    seconds=seconds,
                    seed=seed,
                    capacity_bytes_per_second=max(200_000, robots * 6_000),
                    policies=POLICIES,
                    include_non_sent=False,
                )
                packet_rows = write_simulator_csv(events, trace_path)
                trace_metadata.append(
                    {
                        "robots": robots,
                        "seed": seed,
                        "trace": str(trace_path),
                        "packet_rows": packet_rows,
                    }
                )
                for profile_name, profile in PROFILES.items():
                    command = (
                        f"{shlex.quote(str(binary))} "
                        f"--trace={shlex.quote(str(trace_path))} "
                        f"--dataRate={profile['data_rate']} "
                        f"--delay={profile['delay']} "
                        f"--errorRate={profile['error_rate']} "
                        f"--seed={seed} --run={seed}"
                    )
                    completed = docker_run(image, command)
                    policy_rows = parse_csv_summary(completed.stdout)
                    seen = {item["policy"] for item in policy_rows}
                    valid = (
                        completed.returncode == 0
                        and seen == set(POLICIES)
                        and all(
                            item["tx"] > 0
                            and 0 <= item["rx"] <= item["tx"]
                            and 0.0 <= item["deadline_miss_ratio"] <= 1.0
                            for item in policy_rows
                        )
                    )
                    rows.append(
                        {
                            "robots": robots,
                            "seed": seed,
                            "profile": profile_name,
                            "profile_config": profile,
                            "status": "ok" if valid else "failed",
                            "returncode": completed.returncode,
                            "policies": policy_rows,
                            "stdout": completed.stdout,
                            "stderr": completed.stderr,
                        }
                    )
    finally:
        binary.unlink(missing_ok=True)

    grouped: dict[tuple[int, str, str], list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        for policy in row["policies"]:
            grouped[(row["robots"], row["profile"], policy["policy"])].append(policy)
    aggregates = []
    for (robots, profile, policy), samples in sorted(grouped.items()):
        total_tx = sum(item["tx"] for item in samples)
        total_rx = sum(item["rx"] for item in samples)
        aggregates.append(
            {
                "robots": robots,
                "profile": profile,
                "policy": policy,
                "repetitions": len(samples),
                "tx": total_tx,
                "rx": total_rx,
                "delivery_ratio": total_rx / total_tx if total_tx else 0.0,
                "mean_deadline_miss_ratio": sum(
                    item["deadline_miss_ratio"] for item in samples
                ) / len(samples),
                "mean_p99_ms": sum(item["p99_ms"] for item in samples) / len(samples),
                "mean_utility": sum(item["utility"] for item in samples) / len(samples),
            }
        )
    ok = len(rows) == len(robot_counts) * len(seeds) * len(PROFILES) and all(
        row["status"] == "ok" for row in rows
    )
    return {
        "schema_version": SCHEMA_VERSION,
        "status": "ok" if ok else "failed",
        "simulator": "ns-3",
        "ns3_version": ns3_version,
        "topology": "shared_csma_with_independent_receive_error_model",
        "high_fidelity_wireless_claim_allowed": False,
        "robot_counts": robot_counts,
        "seeds": seeds,
        "seconds": seconds,
        "policies": list(POLICIES),
        "profiles": PROFILES,
        "traces": trace_metadata,
        "rows": rows,
        "aggregates": aggregates,
    }


def parse_int_list(value: str) -> list[int]:
    values = [int(item.strip()) for item in value.split(",") if item.strip()]
    if not values or any(item <= 0 for item in values):
        raise argparse.ArgumentTypeError("expected comma-separated positive integers")
    return values


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--image", default=DEFAULT_IMAGE)
    parser.add_argument("--robot-counts", type=parse_int_list, default=[8, 16, 32])
    parser.add_argument("--seeds", type=parse_int_list, default=[7, 13, 29])
    parser.add_argument("--seconds", type=int, default=3)
    parser.add_argument("--output-dir", type=Path, default=Path("results_ns3/fleet_matrix_v1"))
    parser.add_argument(
        "--summary-json",
        type=Path,
        default=Path("results_ns3/ns3_docker_fleet_matrix_v1_summary.json"),
    )
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    summary = run_matrix(
        image=args.image,
        output_dir=args.output_dir,
        robot_counts=args.robot_counts,
        seeds=args.seeds,
        seconds=max(args.seconds, 1),
    )
    args.summary_json.parent.mkdir(parents=True, exist_ok=True)
    args.summary_json.write_text(
        json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    if args.json:
        print(json.dumps(summary, sort_keys=True))
    else:
        print(f"status={summary['status']} rows={len(summary.get('rows', []))}")
    return 0 if summary["status"] == "ok" else 1


if __name__ == "__main__":
    raise SystemExit(main())

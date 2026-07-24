"""Repeat terminal repair-policy MESSAGE_LOST paths across Docker/netem peers."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.run_rmw_docker_message_lost_interprocess_probe import (
    DEFAULT_IMAGE,
    docker_shell,
    run,
    run_iteration,
)


SCHEMA_VERSION = "fleetrmw.docker_message_lost_terminal_repair_probe.v1"
TERMINAL_REPAIR_MODES = (
    "budget_exhaustion",
    "attempt_limit",
    "admission_rejection",
)


def run_probe(*, image: str, iterations: int) -> dict[str, Any]:
    iterations_per_scenario = max(iterations, 1)
    expected_run_count = iterations_per_scenario * len(TERMINAL_REPAIR_MODES)
    suffix = str(os.getpid())
    network = f"fq-loss-terminal-net-{suffix}"
    subnet_octet = 20 + (os.getpid() % 200)
    subnet = f"10.232.{subnet_octet}.0/24"
    publisher_ip = f"10.232.{subnet_octet}.11"
    subscriber_ip = f"10.232.{subnet_octet}.12"
    build = "/work/.tmp_fq_loss_terminal_build"
    install = "/work/.tmp_fq_loss_terminal_install"
    log = "/work/.tmp_fq_loss_terminal_log"
    binary = (
        f"{install}/rmw_fleetqox_cpp/lib/rmw_fleetqox_cpp/"
        "fleetrmw_message_lost_interprocess_probe"
    )
    rows: list[dict[str, Any]] = []
    try:
        run(["docker", "network", "create", "--subnet", subnet, network])
        docker_shell(
            image=image,
            command=(
                "source /opt/ros/jazzy/setup.bash && "
                f"rm -rf {build} {install} {log} && "
                f"colcon --log-base {log} build --base-paths ros2_ws/src "
                "--packages-select rmw_fleetqox_cpp "
                f"--build-base {build} --install-base {install} "
                "--cmake-args -DCMAKE_BUILD_TYPE=Release >/dev/null"
            ),
        )
        for index in range(iterations_per_scenario):
            for mode in TERMINAL_REPAIR_MODES:
                rows.append(
                    run_iteration(
                        image=image,
                        network=network,
                        suffix=f"{suffix}-{mode}-{index}",
                        subscriber_ip=subscriber_ip,
                        publisher_ip=publisher_ip,
                        install=install,
                        binary=binary,
                        topic=f"/fleetqox/message_lost_terminal_{mode}_{suffix}_{index}",
                        terminal_repair_mode=mode,
                    )
                )
    except subprocess.CalledProcessError as error:
        rows.append(
            {
                "status": "failed",
                "returncode": error.returncode,
                "stdout": error.stdout,
                "stderr": error.stderr,
            }
        )
    finally:
        containers = run(
            ["docker", "ps", "-aq", "--filter", f"network={network}"],
            check=False,
        ).stdout.split()
        if containers:
            run(["docker", "rm", "-f", *containers], check=False)
        run(["docker", "network", "rm", network], check=False)
        docker_shell(
            image=image,
            command=f"rm -rf {build} {install} {log}",
            check=False,
        )

    scenario_summaries: dict[str, dict[str, int | bool]] = {}
    for mode in TERMINAL_REPAIR_MODES:
        scenario_rows = [row for row in rows if row.get("terminal_repair_mode") == mode]
        ok_count = sum(row.get("status") == "ok" for row in scenario_rows)
        scenario_summaries[mode] = {
            "run_count": len(scenario_rows),
            "ok_run_count": ok_count,
            "claim": (
                len(scenario_rows) == iterations_per_scenario
                and ok_count == iterations_per_scenario
            ),
        }
    ok_run_count = sum(row.get("status") == "ok" for row in rows)
    ok = len(rows) == expected_run_count and ok_run_count == expected_run_count
    duplicate_notice_deduplication = ok and all(
        int(row.get("subscriber", {}).get("unrecoverable_loss_notices_received", 0))
        >= (1 if row.get("terminal_repair_mode") == "attempt_limit" else 2)
        and row.get("subscriber", {}).get("unrecoverable_loss_samples_reported") == 1
        for row in rows
    )
    teardown_clean = ok and all(
        row.get("publisher_returncode") == 0
        and row.get("subscriber_returncode") == 0
        and row.get("publisher_stderr") == ""
        and row.get("subscriber_stderr") == ""
        for row in rows
    )
    return {
        "schema_version": SCHEMA_VERSION,
        "status": "ok" if ok and duplicate_notice_deduplication and teardown_clean else "failed",
        "image": image,
        "netem": "delay 8ms 2ms on publisher and subscriber",
        "netem_applied": ok,
        "scenario_count": len(TERMINAL_REPAIR_MODES),
        "iterations_per_scenario": iterations_per_scenario,
        "run_count": expected_run_count,
        "ok_run_count": ok_run_count,
        "scenario_summaries": scenario_summaries,
        "repair_budget_terminal_loss_notice_claim": scenario_summaries[
            "budget_exhaustion"
        ]["claim"],
        "repair_attempt_limit_terminal_loss_notice_claim": scenario_summaries[
            "attempt_limit"
        ]["claim"],
        "repair_admission_terminal_loss_notice_claim": scenario_summaries[
            "admission_rejection"
        ]["claim"],
        "terminal_repair_duplicate_notice_deduplication_claim": (
            duplicate_notice_deduplication
        ),
        "terminal_repair_clean_teardown_claim": teardown_clean,
        "terminal_repair_controls_repeated_claim": (
            ok and iterations_per_scenario >= 5
        ),
        "runs": rows,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--image", default=DEFAULT_IMAGE)
    parser.add_argument("--iterations", type=int, default=1)
    parser.add_argument(
        "--summary-json",
        default=(
            "results_rmw_socket/"
            "docker_message_lost_terminal_repair_probe_summary.json"
        ),
    )
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    summary = run_probe(image=args.image, iterations=args.iterations)
    output = ROOT / args.summary_json
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(summary, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    if args.json:
        print(json.dumps(summary, sort_keys=True))
    else:
        print(f"status={summary['status']}")
    return 0 if summary["status"] == "ok" else 1


if __name__ == "__main__":
    raise SystemExit(main())

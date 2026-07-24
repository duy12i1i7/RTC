"""Run subscriber-targeted reliable MESSAGE_LOST across two Docker/netem peers."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import subprocess
import time
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
SCHEMA_VERSION = "fleetrmw.docker_message_lost_interprocess_probe.v1"
DEFAULT_IMAGE = "localhost/fleetrmw/rmw-netem:jazzy"
TERMINAL_REPAIR_SCENARIOS: dict[str, dict[str, Any]] = {
    "history_exhaustion": {
        "publisher_depth": 1,
        "expected_dropped_frames": 1,
        "publisher_environment": "",
    },
    "budget_exhaustion": {
        "publisher_depth": 16,
        "expected_dropped_frames": 1,
        "publisher_environment": (
            "export FLEETQOX_RMW_REPAIR_RETRANSMISSION_BUDGET=0 && "
        ),
    },
    "attempt_limit": {
        "publisher_depth": 16,
        "expected_dropped_frames": 2,
        "publisher_environment": (
            "export FLEETQOX_RMW_REPAIR_MAX_ATTEMPTS_PER_SEQUENCE=1 && "
            "export FLEETQOX_RMW_DROP_SOURCE_SEQUENCE_SEND_COUNT=2 && "
        ),
    },
    "admission_rejection": {
        "publisher_depth": 16,
        "expected_dropped_frames": 1,
        "publisher_environment": (
            "export FLEETQOX_RMW_REPAIR_ADMISSION_STRICT=1 && "
        ),
    },
}


def run(
    command: list[str], *, check: bool = True
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        command,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=check,
    )


def parse_last_json(output: str) -> dict[str, Any]:
    for line in reversed(output.splitlines()):
        line = line.strip()
        if not line.startswith("{"):
            continue
        try:
            value = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(value, dict):
            return value
    return {"status": "missing", "raw": output}


def docker_shell(
    *, image: str, command: str, check: bool = True
) -> subprocess.CompletedProcess[str]:
    return run(
        [
            "docker",
            "run",
            "--rm",
            "--entrypoint",
            "bash",
            "-v",
            f"{ROOT}:/work",
            "-w",
            "/work",
            image,
            "-lc",
            command,
        ],
        check=check,
    )


def create_subscriber(
    *,
    image: str,
    network: str,
    name: str,
    subscriber_ip: str,
    publisher_ip: str,
    install: str,
    binary: str,
    topic: str,
    terminal_repair_mode: str,
    publisher_depth: int,
) -> None:
    command = (
        "tc qdisc replace dev eth0 root netem delay 8ms 2ms && "
        f"source /opt/ros/jazzy/setup.bash && source {install}/setup.bash && "
        "export RMW_IMPLEMENTATION=rmw_fleetqox_cpp && "
        f"export FLEETQOX_RMW_BIND=0.0.0.0:48452 && "
        f"export FLEETQOX_RMW_PEERS={publisher_ip}:48451 && "
        f"{binary} --mode subscriber --topic {topic} --timeout-ms 6000 "
        f"--terminal-repair-mode {terminal_repair_mode} "
        f"--publisher-depth {publisher_depth}"
    )
    run(
        [
            "docker",
            "create",
            "--name",
            name,
            "--network",
            network,
            "--ip",
            subscriber_ip,
            "--cap-add",
            "NET_ADMIN",
            "--entrypoint",
            "bash",
            "-v",
            f"{ROOT}:/work",
            "-w",
            "/work",
            image,
            "-lc",
            command,
        ]
    )


def run_iteration(
    *,
    image: str,
    network: str,
    suffix: str,
    subscriber_ip: str,
    publisher_ip: str,
    install: str,
    binary: str,
    topic: str,
    terminal_repair_mode: str = "history_exhaustion",
) -> dict[str, Any]:
    scenario = TERMINAL_REPAIR_SCENARIOS[terminal_repair_mode]
    publisher_depth = int(scenario["publisher_depth"])
    subscriber_name = f"fq-loss-sub-{suffix}"
    publisher_name = f"fq-loss-pub-{suffix}"
    create_subscriber(
        image=image,
        network=network,
        name=subscriber_name,
        subscriber_ip=subscriber_ip,
        publisher_ip=publisher_ip,
        install=install,
        binary=binary,
        topic=topic,
        terminal_repair_mode=terminal_repair_mode,
        publisher_depth=publisher_depth,
    )
    publisher_command = (
        "tc qdisc replace dev eth0 root netem delay 8ms 2ms && "
        f"source /opt/ros/jazzy/setup.bash && source {install}/setup.bash && "
        "export RMW_IMPLEMENTATION=rmw_fleetqox_cpp && "
        "export FLEETQOX_RMW_BIND=0.0.0.0:48451 && "
        f"export FLEETQOX_RMW_PEERS={subscriber_ip}:48452 && "
        "export FLEETQOX_RMW_DROP_SOURCE_SEQUENCES=3 && "
        f"{scenario['publisher_environment']}"
        f"{binary} --mode publisher --topic {topic} --timeout-ms 5000 "
        "--pre-publish-wait-ms 800 --publish-interval-ms 40 "
        f"--terminal-repair-mode {terminal_repair_mode} "
        f"--publisher-depth {publisher_depth}"
    )
    run(
        [
            "docker",
            "create",
            "--name",
            publisher_name,
            "--network",
            network,
            "--ip",
            publisher_ip,
            "--cap-add",
            "NET_ADMIN",
            "--entrypoint",
            "bash",
            "-v",
            f"{ROOT}:/work",
            "-w",
            "/work",
            image,
            "-lc",
            publisher_command,
        ]
    )
    run(["docker", "start", subscriber_name])
    time.sleep(0.2)
    publisher = run(["docker", "start", "-a", publisher_name], check=False)
    publisher_inspect = run(
        ["docker", "inspect", "-f", "{{.State.ExitCode}}", publisher_name],
        check=False,
    )
    publisher_returncode = (
        int(publisher_inspect.stdout.strip())
        if publisher_inspect.stdout.strip().isdigit()
        else -1
    )
    wait = run(["docker", "wait", subscriber_name], check=False)
    logs = run(["docker", "logs", subscriber_name], check=False)
    subscriber_returncode = int(wait.stdout.strip()) if wait.stdout.strip().isdigit() else -1
    publisher_result = parse_last_json(publisher.stdout)
    subscriber_result = parse_last_json(logs.stdout)
    payloads = set(subscriber_result.get("payloads", []))
    minimum_notice_count = 1 if terminal_repair_mode == "attempt_limit" else 2
    terminal_control_ok = {
        "history_exhaustion": (
            publisher_result.get("nack_retransmissions") == 0
            and publisher_result.get("repair_budget_exhausted") == 0
            and publisher_result.get("repair_sequence_attempt_limit_exhausted") == 0
            and publisher_result.get("repair_not_admitted") == 0
        ),
        "budget_exhaustion": (
            publisher_result.get("nack_retransmissions") == 0
            and int(publisher_result.get("repair_budget_exhausted", 0)) >= 1
            and publisher_result.get("repair_sequence_attempt_limit_exhausted") == 0
            and publisher_result.get("repair_not_admitted") == 0
        ),
        "attempt_limit": (
            publisher_result.get("nack_retransmissions") == 1
            and publisher_result.get("repair_budget_exhausted") == 0
            and int(
                publisher_result.get("repair_sequence_attempt_limit_exhausted", 0)
            )
            >= 1
            and publisher_result.get("repair_not_admitted") == 0
        ),
        "admission_rejection": (
            publisher_result.get("nack_retransmissions") == 0
            and publisher_result.get("repair_budget_exhausted") == 0
            and publisher_result.get("repair_sequence_attempt_limit_exhausted") == 0
            and int(publisher_result.get("repair_not_admitted", 0)) >= 1
        ),
    }[terminal_repair_mode]
    ok = (
        publisher_returncode == 0
        and subscriber_returncode == 0
        and publisher_result.get("status") == "ok"
        and subscriber_result.get("status") == "ok"
        and publisher_result.get("terminal_repair_mode") == terminal_repair_mode
        and subscriber_result.get("terminal_repair_mode") == terminal_repair_mode
        and publisher_result.get("publisher_depth") == publisher_depth
        and terminal_control_ok
        and publisher_result.get("test_dropped_frames")
        == scenario["expected_dropped_frames"]
        and int(publisher_result.get("unrecoverable_loss_notices_sent", 0))
        >= minimum_notice_count
        and subscriber_result.get("message_lost_wait_ready") is True
        and subscriber_result.get("message_lost_taken") is True
        and subscriber_result.get("message_lost_total_count") == 1
        and subscriber_result.get("message_lost_total_count_change") == 1
        and subscriber_result.get("message_lost_callback_events") == 1
        and int(subscriber_result.get("unrecoverable_loss_notices_received", 0))
        >= minimum_notice_count
        and subscriber_result.get("unrecoverable_loss_samples_reported") == 1
        and payloads == {"remote-one", "remote-two", "remote-four"}
    )
    run(["docker", "rm", "-f", subscriber_name, publisher_name], check=False)
    return {
        "status": "ok" if ok else "failed",
        "terminal_repair_mode": terminal_repair_mode,
        "publisher_returncode": publisher_returncode,
        "subscriber_returncode": subscriber_returncode,
        "publisher": publisher_result,
        "subscriber": subscriber_result,
        "publisher_stdout": publisher.stdout,
        "publisher_stderr": publisher.stderr,
        "subscriber_logs": logs.stdout,
        "subscriber_stderr": logs.stderr,
    }


def run_probe(*, image: str, iterations: int) -> dict[str, Any]:
    run_count = max(iterations, 1)
    suffix = str(os.getpid())
    network = f"fq-loss-net-{suffix}"
    subnet_octet = 20 + (os.getpid() % 200)
    subnet = f"10.231.{subnet_octet}.0/24"
    publisher_ip = f"10.231.{subnet_octet}.11"
    subscriber_ip = f"10.231.{subnet_octet}.12"
    build = "/work/.tmp_fq_loss_remote_build"
    install = "/work/.tmp_fq_loss_remote_install"
    log = "/work/.tmp_fq_loss_remote_log"
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
        for index in range(run_count):
            rows.append(
                run_iteration(
                    image=image,
                    network=network,
                    suffix=f"{suffix}-{index}",
                    subscriber_ip=subscriber_ip,
                    publisher_ip=publisher_ip,
                    install=install,
                    binary=binary,
                    topic=f"/fleetqox/message_lost_remote_{suffix}_{index}",
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
    ok_count = sum(row.get("status") == "ok" for row in rows)
    ok = len(rows) == run_count and ok_count == run_count
    return {
        "schema_version": SCHEMA_VERSION,
        "status": "ok" if ok else "failed",
        "image": image,
        "netem": "delay 8ms 2ms on publisher and subscriber",
        "netem_applied": ok,
        "run_count": run_count,
        "ok_run_count": ok_count,
        "remote_unrecoverable_loss_notice_claim": ok,
        "remote_message_lost_waitable_claim": ok,
        "duplicate_unrecoverable_loss_notice_deduplication_claim": ok,
        "repeated_remote_message_lost_claim": ok and run_count >= 5,
        "runs": rows,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--image", default=DEFAULT_IMAGE)
    parser.add_argument("--iterations", type=int, default=1)
    parser.add_argument(
        "--summary-json",
        default="results_rmw_socket/docker_message_lost_interprocess_probe_summary.json",
    )
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    summary = run_probe(image=args.image, iterations=args.iterations)
    output = ROOT / args.summary_json
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    if args.json:
        print(json.dumps(summary, sort_keys=True))
    else:
        print(f"status={summary['status']}")
    return 0 if summary["status"] == "ok" else 1


if __name__ == "__main__":
    raise SystemExit(main())

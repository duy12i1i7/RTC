#!/usr/bin/env python3
"""Prove two-reader rmw_publisher_wait_for_all_acked over UDP/router/netem."""

from __future__ import annotations

import argparse
import ipaddress
import json
import os
from pathlib import Path
import subprocess
import time
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
SCHEMA_VERSION = "fleetrmw.docker_remote_wait_for_all_acked_probe.v1"
PROBE_SCHEMA_VERSION = "fleetrmw.remote_wait_for_all_acked_probe.v1"
DEFAULT_IMAGE = "localhost/fleetrmw/rmw-netem:jazzy"


def run_command(command: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        command,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )


def json_rows(output: str) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for line in output.splitlines():
        line = line.strip()
        if not line.startswith("{"):
            continue
        try:
            value = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(value, dict):
            rows.append(value)
    return rows


def last_json(output: str) -> dict[str, Any]:
    rows = json_rows(output)
    return rows[-1] if rows else {}


def wait_for_ready(container: str, *, mode: str, timeout_s: float = 8.0) -> bool:
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        logs = run_command(["docker", "logs", container]).stdout
        if (
            f'"mode":"{mode}"' in logs
            and '"phase":"ready"' in logs
            and '"initialized":true' in logs
        ):
            return True
        state = run_command(
            ["docker", "inspect", "-f", "{{.State.Running}}", container]
        )
        if state.returncode != 0 or state.stdout.strip() != "true":
            return False
        time.sleep(0.1)
    return False


def start_container(
    *,
    root: Path,
    image: str,
    name: str,
    network: str,
    ip_address: str,
    command: str,
) -> subprocess.CompletedProcess[str]:
    return run_command(
        [
            "docker",
            "run",
            "-d",
            "--name",
            name,
            "--network",
            network,
            "--ip",
            ip_address,
            "--cap-add",
            "NET_ADMIN",
            "--entrypoint",
            "bash",
            "-v",
            f"{root}:/work",
            "-w",
            "/work",
            image,
            "-lc",
            command,
        ]
    )


def wait_container(container: str) -> int:
    waited = run_command(["docker", "wait", container])
    if waited.returncode != 0 or not waited.stdout.strip():
        return -1
    try:
        return int(waited.stdout.strip())
    except ValueError:
        return -1


def publisher_ok(probe: dict[str, Any]) -> bool:
    return (
        probe.get("schema_version") == PROBE_SCHEMA_VERSION
        and probe.get("mode") == "publisher"
        and probe.get("status") == "ok"
        and probe.get("remote_two_reader_ack_snapshot_claim") is True
        and probe.get("matched_subscription_count") == 2
        and probe.get("empty_wait_ok") is True
        and probe.get("published") is True
        and probe.get("partial_ack_timeout") is True
        and int(probe.get("partial_wait_elapsed_ms", 0)) >= 150
        and probe.get("partial_expected_ack_count") == 2
        and probe.get("partial_observed_ack_count") == 1
        and probe.get("all_acked_wait_ok") is True
        and probe.get("completed_expected_ack_count") == 2
        and probe.get("completed_observed_ack_count") == 2
        and probe.get("zero_timeout_after_ack_ok") is True
        and probe.get("clean_teardown") is True
    )


def subscriber_ok(probe: dict[str, Any], index: int) -> bool:
    return (
        probe.get("schema_version") == PROBE_SCHEMA_VERSION
        and probe.get("mode") == "subscriber"
        and probe.get("subscriber_index") == index
        and probe.get("status") == "ok"
        and probe.get("sample_taken") is True
        and probe.get("payload_ok") is True
        and probe.get("clean_teardown") is True
    )


def run_case(
    *,
    root: Path,
    image: str,
    install: str,
    network: str,
    addresses: dict[str, str],
    index: int,
) -> dict[str, Any]:
    suffix = f"{os.getpid()}-{index}"
    router = f"fleetrmw-remote-acked-router-{suffix}"
    publisher = f"fleetrmw-remote-acked-publisher-{suffix}"
    subscriber_one = f"fleetrmw-remote-acked-sub1-{suffix}"
    subscriber_two = f"fleetrmw-remote-acked-sub2-{suffix}"
    names = [publisher, subscriber_one, subscriber_two, router]
    endpoint_binary = (
        f"{install}/rmw_fleetqox_cpp/lib/rmw_fleetqox_cpp/"
        "fleetrmw_remote_wait_for_all_acked_probe"
    )
    router_binary = (
        f"{install}/rmw_fleetqox_cpp/lib/rmw_fleetqox_cpp/"
        "fleetrmw_udp_router_probe"
    )
    source = f"source /opt/ros/jazzy/setup.bash && source {install}/setup.bash && "
    netem = "tc qdisc replace dev eth0 root netem delay 5ms 1ms && "
    common = "export RMW_IMPLEMENTATION=rmw_fleetqox_cpp && "
    starts: dict[str, int] = {}
    ready = {"publisher": False, "subscriber_one": False, "subscriber_two": False}
    returncodes = {name: -1 for name in names}
    logs = {name: "" for name in names}
    try:
        router_start = start_container(
            root=root,
            image=image,
            name=router,
            network=network,
            ip_address=addresses["router"],
            command=(
                source
                + netem
                + f"{router_binary} --bind 0.0.0.0:48830 "
                + "--graph-peers "
                + f"{addresses['publisher']}:48831,"
                + f"{addresses['subscriber_one']}:48832,"
                + f"{addresses['subscriber_two']}:48833 "
                "--expected-frames 1 --expected-ack-nack-frames 2 "
                "--expected-ack-nack-forwarded 2 --expected-route-advertisements 1 "
                "--expected-graph-advertisements 3 --timeout-ms 8000"
            ),
        )
        starts[router] = router_start.returncode
        time.sleep(0.3)
        publisher_start = start_container(
            root=root,
            image=image,
            name=publisher,
            network=network,
            ip_address=addresses["publisher"],
            command=(
                source
                + netem
                + common
                + "FLEETQOX_RMW_GRAPH_RENEW_INTERVAL_MS=100 "
                + "FLEETQOX_RMW_BIND=0.0.0.0:48831 "
                + f"FLEETQOX_RMW_PEERS={addresses['router']}:48830 "
                + f"{endpoint_binary} --mode publisher"
            ),
        )
        starts[publisher] = publisher_start.returncode
        ready["publisher"] = publisher_start.returncode == 0 and wait_for_ready(
            publisher, mode="publisher"
        )
        if ready["publisher"]:
            subscriber_one_start = start_container(
                root=root,
                image=image,
                name=subscriber_one,
                network=network,
                ip_address=addresses["subscriber_one"],
                command=(
                    source
                    + netem
                    + common
                    + "FLEETQOX_RMW_GRAPH_RENEW_INTERVAL_MS=100 "
                    + "FLEETQOX_RMW_BIND=0.0.0.0:48832 "
                    + f"FLEETQOX_RMW_PEERS={addresses['router']}:48830 "
                    + f"{endpoint_binary} --mode subscriber --subscriber-index 1 --hold-ms 700"
                ),
            )
            starts[subscriber_one] = subscriber_one_start.returncode
            subscriber_two_start = start_container(
                root=root,
                image=image,
                name=subscriber_two,
                network=network,
                ip_address=addresses["subscriber_two"],
                command=(
                    source
                    + netem
                    + common
                    + "FLEETQOX_RMW_GRAPH_RENEW_INTERVAL_MS=100 "
                    + "FLEETQOX_RMW_TEST_ACK_DELAY_SUBSCRIPTION_SUFFIX=-1 "
                    + "FLEETQOX_RMW_TEST_ACK_DELAY_MS=450 "
                    + "FLEETQOX_RMW_BIND=0.0.0.0:48833 "
                    + f"FLEETQOX_RMW_PEERS={addresses['router']}:48830 "
                    + f"{endpoint_binary} --mode subscriber --subscriber-index 2 --hold-ms 700"
                ),
            )
            starts[subscriber_two] = subscriber_two_start.returncode
            ready["subscriber_one"] = (
                subscriber_one_start.returncode == 0
                and wait_for_ready(subscriber_one, mode="subscriber")
            )
            ready["subscriber_two"] = (
                subscriber_two_start.returncode == 0
                and wait_for_ready(subscriber_two, mode="subscriber")
            )
        for name in names:
            if starts.get(name) == 0:
                returncodes[name] = wait_container(name)
        for name in names:
            logs[name] = run_command(["docker", "logs", name]).stdout
    finally:
        for name in names:
            run_command(["docker", "rm", "-f", name])

    publisher_probe = last_json(logs[publisher])
    subscriber_one_probe = last_json(logs[subscriber_one])
    subscriber_two_probe = last_json(logs[subscriber_two])
    router_probe = last_json(logs[router])
    ok = (
        all(ready.values())
        and all(returncodes[name] == 0 for name in names)
        and publisher_ok(publisher_probe)
        and subscriber_ok(subscriber_one_probe, 1)
        and subscriber_ok(subscriber_two_probe, 2)
        and router_probe.get("status") == "ok"
        and int(router_probe.get("ack_nack_frames", 0)) >= 2
        and int(router_probe.get("ack_nack_forwarded", 0)) >= 2
    )
    return {
        "index": index,
        "status": "ok" if ok else "failed",
        "ready": ready,
        "returncodes": returncodes,
        "publisher": publisher_probe,
        "subscriber_one": subscriber_one_probe,
        "subscriber_two": subscriber_two_probe,
        "router": router_probe,
        "logs": logs if not ok else {},
    }


def run_probe(
    *, root: Path, image: str, iterations: int, keep_temp: bool
) -> dict[str, Any]:
    run_count = max(iterations, 1)
    build_root = "/work/.tmp_fleetrmw_remote_wait_for_all_acked"
    install = f"{build_root}/install"
    build_command = (
        "source /opt/ros/jazzy/setup.bash && "
        f"rm -rf {build_root} && "
        f"colcon --log-base {build_root}/log build --base-paths ros2_ws/src "
        "--packages-select rmw_fleetqox_cpp "
        f"--build-base {build_root}/build --install-base {install} "
        "--cmake-args -DCMAKE_BUILD_TYPE=Release"
    )
    build = run_command(
        [
            "docker",
            "run",
            "--rm",
            "--entrypoint",
            "bash",
            "-v",
            f"{root}:/work",
            "-w",
            "/work",
            image,
            "-lc",
            build_command,
        ]
    )
    network = f"fleetrmw-remote-acked-net-{os.getpid()}"
    network_result = run_command(["docker", "network", "create", network])
    subnet_result = run_command(
        [
            "docker",
            "network",
            "inspect",
            "-f",
            "{{(index .IPAM.Config 0).Subnet}}",
            network,
        ]
    )
    addresses: dict[str, str] = {}
    if subnet_result.returncode == 0 and subnet_result.stdout.strip():
        subnet = ipaddress.ip_network(subnet_result.stdout.strip(), strict=False)
        addresses = {
            "router": str(subnet.network_address + 10),
            "publisher": str(subnet.network_address + 11),
            "subscriber_one": str(subnet.network_address + 12),
            "subscriber_two": str(subnet.network_address + 13),
        }
    runs: list[dict[str, Any]] = []
    try:
        if (
            build.returncode == 0
            and network_result.returncode == 0
            and len(addresses) == 4
        ):
            for index in range(1, run_count + 1):
                runs.append(
                    run_case(
                        root=root,
                        image=image,
                        install=install,
                        network=network,
                        addresses=addresses,
                        index=index,
                    )
                )
    finally:
        run_command(["docker", "network", "rm", network])
        if not keep_temp:
            run_command(
                [
                    "docker",
                    "run",
                    "--rm",
                    "--entrypoint",
                    "bash",
                    "-v",
                    f"{root}:/work",
                    image,
                    "-lc",
                    f"rm -rf {build_root}",
                ]
            )

    successful_runs = sum(run.get("status") == "ok" for run in runs)
    status = (
        "ok"
        if build.returncode == 0
        and network_result.returncode == 0
        and subnet_result.returncode == 0
        and len(runs) == run_count
        and successful_runs == run_count
        else "failed"
    )
    return {
        "schema_version": SCHEMA_VERSION,
        "status": status,
        "run_count": run_count,
        "successful_runs": successful_runs,
        "failed_run_count": run_count - successful_runs,
        "container_count_per_run": 4,
        "real_udp_router": True,
        "netem": "delay 5ms 1ms on router, publisher, and both subscribers",
        "delayed_ack_ms": 450,
        "remote_two_reader_ack_snapshot_claim": status == "ok",
        "partial_ack_never_misreported_complete": status == "ok",
        "all_remote_subscribers_acknowledged": status == "ok",
        "clean_teardown": status == "ok"
        and all(
            run.get("publisher", {}).get("clean_teardown") is True
            and run.get("subscriber_one", {}).get("clean_teardown") is True
            and run.get("subscriber_two", {}).get("clean_teardown") is True
            for run in runs
        ),
        "build_returncode": build.returncode,
        "build_stderr": build.stderr[-4000:],
        "network_create_returncode": network_result.returncode,
        "network_subnet": subnet_result.stdout.strip(),
        "endpoint_addresses": addresses,
        "runs": runs,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--image", default=DEFAULT_IMAGE)
    parser.add_argument("--iterations", type=int, default=5)
    parser.add_argument(
        "--summary-json",
        default="results_rmw_socket/docker_remote_wait_for_all_acked_probe_summary.json",
    )
    parser.add_argument("--keep-temp", action="store_true")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    summary = run_probe(
        root=ROOT,
        image=args.image,
        iterations=args.iterations,
        keep_temp=args.keep_temp,
    )
    summary_path = ROOT / args.summary_json
    summary_path.parent.mkdir(parents=True, exist_ok=True)
    summary_path.write_text(json.dumps(summary, sort_keys=True) + "\n", encoding="utf-8")
    if args.json:
        print(json.dumps(summary, sort_keys=True))
    else:
        print("fleetrmw-remote-wait-for-all-acked-probe")
        print(f"  status: {summary['status']}")
        print(f"  successful_runs: {summary['successful_runs']}/{summary['run_count']}")
        print(
            "  remote_two_reader_ack_snapshot_claim: "
            f"{summary['remote_two_reader_ack_snapshot_claim']}"
        )
    return 0 if summary["status"] == "ok" else 1


if __name__ == "__main__":
    raise SystemExit(main())

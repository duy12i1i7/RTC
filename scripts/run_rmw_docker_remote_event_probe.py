"""Build and run FleetRMW remote graph event probes in separate Docker containers."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import subprocess
import time
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
SCHEMA_VERSION = "fleetrmw.docker_remote_event_probe.v1"
DEFAULT_IMAGE = "localhost/fleetrmw/rmw-netem:jazzy"


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


def observer_ok(probe: dict[str, Any], *, expect_expiry: bool) -> bool:
    return (
        probe.get("status") == "ok"
        and probe.get("expect_expiry") is expect_expiry
        and probe.get("matched_ok") is True
        and probe.get("qos_ok") is True
        and probe.get("type_ok") is True
        and probe.get("liveliness_ok") is True
        and probe.get("graph_guard_ok") is True
        and probe.get("remote_graph_guard_add_ready") is True
        and probe.get("remote_graph_guard_renewal_suppressed") is True
        and probe.get("remote_graph_guard_disconnect_ready") is True
        and probe.get("renewal_deduplicated") is True
        and probe.get("publication_connect_current_count") == 1
        and probe.get("publication_disconnect_current_count") == 0
        and probe.get("subscription_connect_current_count") == 1
        and probe.get("subscription_disconnect_current_count") == 0
        and probe.get("offered_total_count") == 1
        and probe.get("requested_total_count") == 1
        and probe.get("offered_durability_total_count") == 1
        and probe.get("requested_durability_total_count") == 1
        and probe.get("offered_deadline_total_count") == 1
        and probe.get("requested_deadline_total_count") == 1
        and probe.get("publisher_type_total_count") == 1
        and probe.get("subscription_type_total_count") == 1
        and probe.get("liveliness_connect_alive_count") == 1
        and probe.get("liveliness_disconnect_alive_count") == 0
        and int(probe.get("advertisements_received", 0)) >= 33
        and probe.get("endpoint_adds") == 11
        and int(probe.get("endpoint_renewals", 0)) >= 11
        and probe.get("endpoint_count_after") == 0
        and (
            probe.get("endpoint_expiries", 0) >= 11
            and probe.get("endpoint_removes") == 0
            if expect_expiry
            else probe.get("endpoint_removes", 0) >= 11
            and probe.get("endpoint_expiries") == 0
        )
    )


def run_command(
    command: list[str],
    *,
    check: bool = False,
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        command,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=check,
    )


def wait_for_ready(container: str, timeout_s: float = 8.0) -> bool:
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        logs = run_command(["docker", "logs", container]).stdout
        if '"phase":"ready"' in logs and '"initialized":true' in logs:
            return True
        state = run_command(["docker", "inspect", "-f", "{{.State.Running}}", container])
        if state.returncode != 0 or state.stdout.strip() != "true":
            return False
        time.sleep(0.1)
    return False


def build_probe(root: Path, image: str, build_root: str) -> subprocess.CompletedProcess[str]:
    install = f"{build_root}/install"
    command = (
        "source /opt/ros/jazzy/setup.bash && "
        f"rm -rf {build_root} && "
        f"colcon --log-base {build_root}/log build --base-paths ros2_ws/src "
        "--packages-select rmw_fleetqox_cpp "
        f"--build-base {build_root}/build --install-base {install} "
        "--cmake-args -DCMAKE_BUILD_TYPE=Release"
    )
    return run_command(
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
            command,
        ]
    )


def run_case(
    *,
    root: Path,
    image: str,
    install: str,
    network: str,
    index: int,
    expect_expiry: bool,
) -> dict[str, Any]:
    observer = f"fleetrmw-remote-event-observer-{os.getpid()}-{index}"
    advertiser = f"fleetrmw-remote-event-advertiser-{os.getpid()}-{index}"
    binary = f"{install}/rmw_fleetqox_cpp/lib/rmw_fleetqox_cpp/fleetrmw_remote_event_probe"
    observer_args = "--mode observer --timeout-ms 9500"
    if expect_expiry:
        observer_args += " --expect-expiry"
    observer_command = (
        f"source /opt/ros/jazzy/setup.bash && source {install}/setup.bash && "
        "tc qdisc replace dev eth0 root netem delay 5ms 1ms && "
        f"FLEETQOX_RMW_BIND=0.0.0.0:48410 {binary} {observer_args}"
    )
    start = run_command(
        [
            "docker",
            "run",
            "-d",
            "--name",
            observer,
            "--network",
            network,
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
            observer_command,
        ]
    )
    ready = start.returncode == 0 and wait_for_ready(observer)
    advertiser_result = subprocess.CompletedProcess([], 1, "", "observer_not_ready")
    observer_returncode = -1
    observer_stdout = ""
    try:
        if ready:
            crash_arg = " --crash-without-remove" if expect_expiry else ""
            advertiser_command = (
                f"source /opt/ros/jazzy/setup.bash && source {install}/setup.bash && "
                "tc qdisc replace dev eth0 root netem delay 5ms 1ms && "
                "FLEETQOX_RMW_BIND=0.0.0.0:48411 "
                f"FLEETQOX_RMW_PEERS={observer}:48410 "
                f"{binary} --mode advertiser --hold-ms 2200{crash_arg}"
            )
            advertiser_result = run_command(
                [
                    "docker",
                    "run",
                    "--rm",
                    "--name",
                    advertiser,
                    "--network",
                    network,
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
                    advertiser_command,
                ]
            )
            wait_result = run_command(["docker", "wait", observer])
            if wait_result.returncode == 0 and wait_result.stdout.strip():
                observer_returncode = int(wait_result.stdout.strip())
        observer_stdout = run_command(["docker", "logs", observer]).stdout
    finally:
        run_command(["docker", "rm", "-f", observer])

    observer_rows = json_rows(observer_stdout)
    advertiser_rows = json_rows(advertiser_result.stdout)
    observer_probe = observer_rows[-1] if observer_rows else {}
    advertiser_probe = advertiser_rows[-1] if advertiser_rows else {}
    ok = (
        ready
        and advertiser_result.returncode == 0
        and observer_returncode == 0
        and advertiser_probe.get("status") == "ok"
        and observer_ok(observer_probe, expect_expiry=expect_expiry)
    )
    return {
        "index": index,
        "status": "ok" if ok else "failed",
        "expect_expiry": expect_expiry,
        "observer_ready": ready,
        "observer_returncode": observer_returncode,
        "advertiser_returncode": advertiser_result.returncode,
        "observer": observer_probe,
        "advertiser": advertiser_probe,
        "observer_stdout": observer_stdout,
        "advertiser_stdout": advertiser_result.stdout,
        "advertiser_stderr": advertiser_result.stderr,
    }


def run_probe(
    *,
    root: Path,
    image: str,
    iterations: int,
    keep_temp: bool,
) -> dict[str, Any]:
    run_count = max(iterations, 2)
    build_root = "/work/.tmp_fleetrmw_remote_event"
    install = f"{build_root}/install"
    network = f"fleetrmw-remote-event-net-{os.getpid()}"
    build = build_probe(root, image, build_root)
    if build.returncode != 0:
        return {
            "schema_version": SCHEMA_VERSION,
            "status": "failed",
            "image": image,
            "run_count": run_count,
            "ok_run_count": 0,
            "build_returncode": build.returncode,
            "build_stdout": build.stdout,
            "build_stderr": build.stderr,
            "runs": [],
        }

    network_result = run_command(["docker", "network", "create", network])
    runs: list[dict[str, Any]] = []
    try:
        if network_result.returncode == 0:
            for index in range(run_count):
                runs.append(
                    run_case(
                        root=root,
                        image=image,
                        install=install,
                        network=network,
                        index=index + 1,
                        expect_expiry=index % 2 == 1,
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
                    "-w",
                    "/work",
                    image,
                    "-lc",
                    f"rm -rf {build_root}",
                ]
            )

    ok_run_count = sum(run.get("status") == "ok" for run in runs)
    expiry_count = sum(run.get("expect_expiry") is True for run in runs)
    explicit_remove_count = len(runs) - expiry_count
    ok = (
        len(runs) == run_count
        and ok_run_count == run_count
        and expiry_count > 0
        and explicit_remove_count > 0
    )
    return {
        "schema_version": SCHEMA_VERSION,
        "status": "ok" if ok else "failed",
        "image": image,
        "run_count": run_count,
        "ok_run_count": ok_run_count,
        "explicit_remove_run_count": explicit_remove_count,
        "lease_expiry_run_count": expiry_count,
        "build_returncode": build.returncode,
        "remote_matched_event_production": ok,
        "remote_qos_event_production": ok,
        "remote_qos_policy_matrix": ["reliability", "durability", "deadline"],
        "remote_type_event_production": ok,
        "remote_liveliness_event_production": ok,
        "remote_graph_guard_notification": ok,
        "remote_graph_guard_renewal_suppression": ok,
        "renewal_deduplication": ok,
        "real_udp_multicontainer": ok,
        "netem_applied": ok,
        "netem": "delay 5ms 1ms on observer and advertiser",
        "runs": runs,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--image", default=DEFAULT_IMAGE)
    parser.add_argument("--iterations", type=int, default=5)
    parser.add_argument("--keep-temp", action="store_true")
    parser.add_argument(
        "--summary-json",
        default="results_rmw_socket/docker_remote_event_probe_summary.json",
    )
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    summary = run_probe(
        root=ROOT,
        image=args.image,
        iterations=args.iterations,
        keep_temp=args.keep_temp,
    )
    output = ROOT / args.summary_json
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    if args.json:
        print(json.dumps(summary, sort_keys=True))
    else:
        print(f"status={summary['status']}")
        print(f"runs={summary.get('ok_run_count', 0)}/{summary.get('run_count', 0)}")
    return 0 if summary["status"] == "ok" else 1


if __name__ == "__main__":
    raise SystemExit(main())

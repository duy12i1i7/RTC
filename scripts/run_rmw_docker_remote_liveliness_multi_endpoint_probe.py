"""Repeat remote MANUAL_BY_TOPIC multi-endpoint/churn semantics under Docker/netem."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import subprocess
import time
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
SCHEMA_VERSION = "fleetrmw.docker_remote_liveliness_multi_endpoint_probe.v1"
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


def observer_ok(probe: dict[str, Any]) -> bool:
    return (
        probe.get("status") == "ok"
        and probe.get("multi_endpoint_independent_state_claim") is True
        and probe.get("alive_remove_and_not_alive_remove_claim") is True
        and probe.get("endpoint_churn_recreate_claim") is True
        and probe.get("liveliness_expiry_preserves_matching_claim") is True
        and probe.get("publishers_during_single_endpoint_expiry") == 2
        and probe.get("publishers_after_churn") == 0
        and int(probe.get("assertions_received", 0)) >= 9
        and probe.get("manual_liveliness_expiries") == 2
        and probe.get("manual_liveliness_reassertions") == 1
        and int(probe.get("callback_events", 0)) >= 9
        and probe.get("clean_teardown") is True
    )


def run_case(
    *,
    root: Path,
    image: str,
    install: str,
    network: str,
    index: int,
) -> dict[str, Any]:
    observer = f"fleetrmw-remote-live-multi-observer-{os.getpid()}-{index}"
    advertiser = f"fleetrmw-remote-live-multi-advertiser-{os.getpid()}-{index}"
    binary = (
        f"{install}/rmw_fleetqox_cpp/lib/rmw_fleetqox_cpp/"
        "fleetrmw_remote_liveliness_multi_endpoint_probe"
    )
    common_env = (
        "FLEETQOX_RMW_GRAPH_RENEW_INTERVAL_MS=100 "
        "FLEETQOX_RMW_QOS_DEADLINE_MONITOR_MS=10 "
    )
    observer_command = (
        f"source /opt/ros/jazzy/setup.bash && source {install}/setup.bash && "
        "tc qdisc replace dev eth0 root netem delay 5ms 1ms && "
        f"{common_env}FLEETQOX_RMW_BIND=0.0.0.0:48520 "
        f"{binary} --mode observer"
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
            advertiser_command = (
                f"source /opt/ros/jazzy/setup.bash && source {install}/setup.bash && "
                "tc qdisc replace dev eth0 root netem delay 5ms 1ms && "
                f"{common_env}FLEETQOX_RMW_BIND=0.0.0.0:48521 "
                f"FLEETQOX_RMW_PEERS={observer}:48520 "
                f"{binary} --mode advertiser"
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
            waited = run_command(["docker", "wait", observer])
            if waited.returncode == 0 and waited.stdout.strip():
                observer_returncode = int(waited.stdout.strip())
        observer_stdout = run_command(["docker", "logs", observer]).stdout
    finally:
        run_command(["docker", "rm", "-f", observer])

    observer_rows = json_rows(observer_stdout)
    advertiser_rows = json_rows(advertiser_result.stdout)
    observer_probe = observer_rows[-1] if observer_rows else {}
    advertiser_probe = advertiser_rows[-1] if advertiser_rows else {}
    ok = (
        ready
        and observer_returncode == 0
        and advertiser_result.returncode == 0
        and observer_ok(observer_probe)
        and advertiser_probe.get("status") == "ok"
        and advertiser_probe.get("keepalive_ok") is True
        and advertiser_probe.get("publisher_two_reasserted") is True
        and advertiser_probe.get("endpoint_recreated") is True
        and advertiser_probe.get("clean_teardown") is True
    )
    return {
        "index": index,
        "status": "ok" if ok else "failed",
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
    run_count = max(iterations, 1)
    build_root = "/work/.tmp_fleetrmw_remote_liveliness_multi"
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
    network = f"fleetrmw-remote-live-multi-net-{os.getpid()}"
    network_result = run_command(["docker", "network", "create", network])
    runs: list[dict[str, Any]] = []
    try:
        if build.returncode == 0 and network_result.returncode == 0:
            for index in range(1, run_count + 1):
                runs.append(
                    run_case(
                        root=root,
                        image=image,
                        install=install,
                        network=network,
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

    ok_run_count = sum(run.get("status") == "ok" for run in runs)
    ok = (
        build.returncode == 0
        and network_result.returncode == 0
        and len(runs) == run_count
        and ok_run_count == run_count
    )
    last_observer = runs[-1].get("observer", {}) if runs else {}
    return {
        "schema_version": SCHEMA_VERSION,
        "status": "ok" if ok else "failed",
        "image": image,
        "run_count": run_count,
        "ok_run_count": ok_run_count,
        "real_udp_multicontainer": True,
        "netem_applied": ok,
        "netem": "delay 5ms 1ms on observer and advertiser",
        "liveliness_policy": "MANUAL_BY_TOPIC",
        "liveliness_lease_ms": 500,
        "graph_renew_interval_ms": 100,
        "remote_liveliness_multi_endpoint_independence_claim": ok,
        "remote_liveliness_alive_not_alive_remove_claim": ok,
        "remote_liveliness_endpoint_churn_recreate_claim": ok,
        "remote_liveliness_expiry_preserves_matching_claim": ok,
        "remote_liveliness_multi_endpoint_repeated_claim": ok and run_count >= 5,
        "publishers_during_single_endpoint_expiry": last_observer.get(
            "publishers_during_single_endpoint_expiry"
        ),
        "publishers_after_churn": last_observer.get("publishers_after_churn"),
        "assertions_received": last_observer.get("assertions_received"),
        "manual_liveliness_expiries": last_observer.get("manual_liveliness_expiries"),
        "manual_liveliness_reassertions": last_observer.get(
            "manual_liveliness_reassertions"
        ),
        "clean_teardown": all(
            run.get("observer", {}).get("clean_teardown") is True
            and run.get("advertiser", {}).get("clean_teardown") is True
            for run in runs
        ),
        "build_returncode": build.returncode,
        "build_stdout": build.stdout,
        "build_stderr": build.stderr,
        "runs": runs,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--image", default=DEFAULT_IMAGE)
    parser.add_argument("--iterations", type=int, default=1)
    parser.add_argument("--keep-temp", action="store_true")
    parser.add_argument(
        "--summary-json",
        default=(
            "results_rmw_socket/"
            "docker_remote_liveliness_multi_endpoint_probe_summary.json"
        ),
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
    output.write_text(
        json.dumps(summary, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    if args.json:
        print(json.dumps(summary, sort_keys=True))
    else:
        print(f"status={summary['status']}")
        print(f"runs={summary.get('ok_run_count', 0)}/{summary.get('run_count', 0)}")
    return 0 if summary["status"] == "ok" else 1


if __name__ == "__main__":
    raise SystemExit(main())

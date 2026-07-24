"""Build and repeat FleetRMW BEST_AVAILABLE endpoint QoS adaptation."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import subprocess
import sys
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.run_rmw_docker_shared_memory_probe import parse_last_json


SCHEMA_VERSION = "fleetrmw.docker_qos_best_available_probe.v1"
DEFAULT_IMAGE = "localhost/fleetrmw/rmw-netem:jazzy"


def parse_json_rows(stdout: str) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for line in stdout.splitlines():
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


def probe_ok(probe: dict[str, Any]) -> bool:
    return (
        probe.get("status") == "ok"
        and probe.get("best_publisher_manual_selection_claim") is True
        and probe.get("best_subscription_automatic_selection_claim") is True
        and probe.get("zero_endpoint_best_available_defaults_claim") is True
        and probe.get("mixed_publishers_automatic_max_lease_claim") is True
        and probe.get("best_available_policy_frozen_after_create_claim") is True
        and probe.get("publisher_selected_lease_ms") == 200
        and probe.get("subscription_selected_lease_ms") == 300
        and probe.get("mixed_selected_lease_ms") == 500
        and probe.get("zero_publisher_liveliness_policy") == 1
        and probe.get("zero_subscription_liveliness_policy") == 1
        and probe.get("zero_publisher_lease_sec") == 0
        and probe.get("zero_publisher_lease_nsec") == 0
        and probe.get("zero_subscription_lease_sec") == 0
        and probe.get("zero_subscription_lease_nsec") == 0
        and probe.get("scenario_count") == 4
        and probe.get("clean_teardown") is True
    )


def run_probe(*, image: str, iterations: int) -> dict[str, Any]:
    run_count = max(iterations, 1)
    command = (
        "source /opt/ros/jazzy/setup.bash && "
        "rm -rf /tmp/fq-best-build /tmp/fq-best-install /tmp/fq-best-log && "
        "colcon --log-base /tmp/fq-best-log build --base-paths ros2_ws/src "
        "--packages-select rmw_fleetqox_cpp --build-base /tmp/fq-best-build "
        "--install-base /tmp/fq-best-install --cmake-args -DCMAKE_BUILD_TYPE=Release "
        ">/dev/null && source /tmp/fq-best-install/setup.bash && "
        f"for i in $(seq 1 {run_count}); do "
        "/tmp/fq-best-install/rmw_fleetqox_cpp/lib/rmw_fleetqox_cpp/"
        "fleetrmw_qos_best_available_probe || exit $?; done"
    )
    completed = subprocess.run(
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
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    rows = parse_json_rows(completed.stdout)
    probe = rows[-1] if rows else parse_last_json(completed.stdout)
    ok_run_count = sum(probe_ok(row) for row in rows)
    ok = (
        completed.returncode == 0
        and len(rows) == run_count
        and ok_run_count == run_count
    )
    metric_keys = (
        "best_publisher_manual_selection_claim",
        "best_subscription_automatic_selection_claim",
        "zero_endpoint_best_available_defaults_claim",
        "mixed_publishers_automatic_max_lease_claim",
        "best_available_policy_frozen_after_create_claim",
        "publisher_selected_lease_ms",
        "subscription_selected_lease_ms",
        "mixed_selected_lease_ms",
        "zero_publisher_liveliness_policy",
        "zero_subscription_liveliness_policy",
        "scenario_count",
        "clean_teardown",
    )
    summary: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "status": "ok" if ok else "failed",
        "image": image,
        "returncode": completed.returncode,
        "run_count": run_count,
        "ok_run_count": ok_run_count,
        "qos_best_available_endpoint_adaptation_claim": ok,
        "qos_best_available_endpoint_adaptation_repeated_claim": ok and run_count >= 5,
        "probe": probe,
        "runs": rows,
        "stdout": completed.stdout,
        "stderr": completed.stderr,
    }
    summary.update({key: probe.get(key) for key in metric_keys})
    return summary


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--image", default=DEFAULT_IMAGE)
    parser.add_argument("--iterations", type=int, default=1)
    parser.add_argument(
        "--summary-json",
        default="results_rmw_socket/docker_qos_best_available_probe_summary.json",
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
        print(f"runs={summary.get('ok_run_count', 0)}/{summary.get('run_count', 0)}")
    return 0 if summary["status"] == "ok" else 1


if __name__ == "__main__":
    raise SystemExit(main())

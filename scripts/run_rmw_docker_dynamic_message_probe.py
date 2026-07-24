"""Build and repeat FleetRMW dynamic serialization/take coverage in Docker."""

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

from scripts.run_rmw_docker_allocation_probe import DEFAULT_IMAGE, parse_json_rows


SCHEMA_VERSION = "fleetrmw.docker_dynamic_message_probe.v1"


def row_ok(row: dict[str, Any]) -> bool:
    return (
        row.get("status") == "ok"
        and row.get("serialization_library")
        == "rosidl_dynamic_typesupport_fastrtps"
        and int(row.get("serialized_bytes", 0)) > 0
        and row.get("taken") is True
        and row.get("value_ok") is True
        and row.get("taken_with_info") is True
        and row.get("message_info_ok") is True
        and row.get("dynamic_take_feature_reported") is True
        and row.get("message_info_sequence_features_reported") is True
        and row.get("dynamic_serialization_support_claim") is True
        and row.get("dynamic_message_take_claim") is True
    )


def run_probe(*, root: Path, image: str, iterations: int = 1) -> dict[str, Any]:
    run_count = max(iterations, 1)
    command = (
        "source /opt/ros/jazzy/setup.bash && set -eo pipefail && "
        "rm -rf /tmp/fq-dynamic-build /tmp/fq-dynamic-install /tmp/fq-dynamic-log && "
        "colcon --log-base /tmp/fq-dynamic-log build --base-paths ros2_ws/src "
        "--packages-select rmw_fleetqox_cpp --build-base /tmp/fq-dynamic-build "
        "--install-base /tmp/fq-dynamic-install --cmake-args -DCMAKE_BUILD_TYPE=Release "
        ">/dev/null && source /tmp/fq-dynamic-install/setup.bash && "
        f"for i in $(seq 1 {run_count}); do "
        "/tmp/fq-dynamic-install/rmw_fleetqox_cpp/lib/rmw_fleetqox_cpp/"
        "fleetrmw_dynamic_message_probe || exit $?; done"
    )
    completed = subprocess.run(
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
        ],
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    rows = [
        row
        for row in parse_json_rows(completed.stdout)
        if row.get("schema_version") == "fleetrmw.dynamic_message_probe.v1"
    ]
    ok_run_count = sum(1 for row in rows if row_ok(row))
    ok = (
        completed.returncode == 0
        and len(rows) == run_count
        and ok_run_count == run_count
    )
    return {
        "schema_version": SCHEMA_VERSION,
        "status": "ok" if ok else "failed",
        "image": image,
        "returncode": completed.returncode,
        "run_count": run_count,
        "ok_run_count": ok_run_count,
        "serialization_library": "rosidl_dynamic_typesupport_fastrtps",
        "dynamic_serialization_support_claim": ok,
        "dynamic_serialization_support_repeated_claim": ok and run_count >= 5,
        "dynamic_message_take_claim": ok,
        "dynamic_message_take_with_info_claim": ok,
        "message_info_sequence_features_claim": ok,
        "dds_independent_core_transport_claim": True,
        "dynamic_serialization_plugin_scope": (
            "optional_rosidl_dynamic_typesupport_fastrtps_plugin"
        ),
        "runs": rows,
        "stdout": completed.stdout,
        "stderr": completed.stderr,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--image", default=DEFAULT_IMAGE)
    parser.add_argument("--iterations", type=int, default=1)
    parser.add_argument(
        "--summary-json",
        default="results_rmw_socket/docker_dynamic_message_probe_summary.json",
    )
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    summary = run_probe(root=ROOT, image=args.image, iterations=args.iterations)
    output = ROOT / args.summary_json
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n")
    if args.json:
        print(json.dumps(summary, sort_keys=True))
    else:
        print(
            f"status={summary['status']} ok_runs={summary['ok_run_count']}/"
            f"{summary['run_count']}"
        )
    return 0 if summary["status"] == "ok" else 1


if __name__ == "__main__":
    raise SystemExit(main())

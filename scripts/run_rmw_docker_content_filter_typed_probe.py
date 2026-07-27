"""Build and repeat typed ROSIDL field-reflection content-filter coverage."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import subprocess
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
SCHEMA_VERSION = "fleetrmw.docker_content_filter_typed_probe.v1"
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


def probe_ok(row: dict[str, Any]) -> bool:
    return (
        row.get("status") == "ok"
        and row.get("cpp_nested_scalar_reflection") is True
        and row.get("c_nested_scalar_reflection") is True
        and row.get("cpp_array_index_and_length_reflection") is True
        and row.get("malformed_typed_payload_fail_closed") is True
        and row.get("content_filter_introspection_cpp_nested_fields_claim") is True
        and row.get("content_filter_introspection_c_nested_fields_claim") is True
        and row.get("content_filter_introspection_cpp_array_fields_claim") is True
        and row.get("content_filter_malformed_typed_payload_fail_closed_claim") is True
        and row.get("clean_teardown") is True
        and int(row.get("cpp_evaluated", 0)) == 5
        and int(row.get("cpp_matched", 0)) == 2
        and int(row.get("cpp_dropped", 0)) == 3
        and int(row.get("c_evaluated", 0)) == 4
        and int(row.get("c_matched", 0)) == 2
        and int(row.get("c_dropped", 0)) == 2
        and int(row.get("array_evaluated", 0)) == 4
        and int(row.get("array_matched", 0)) == 1
        and int(row.get("array_dropped", 0)) == 3
        and int(row.get("typed_reflections", 0)) == 12
    )


def run_probe(*, root: Path, image: str, iterations: int) -> dict[str, Any]:
    run_count = max(iterations, 1)
    command = (
        "source /opt/ros/jazzy/setup.bash && "
        "rm -rf /tmp/fq-content-filter-typed-build "
        "/tmp/fq-content-filter-typed-install /tmp/fq-content-filter-typed-log && "
        "colcon --log-base /tmp/fq-content-filter-typed-log build "
        "--base-paths ros2_ws/src --packages-select rmw_fleetqox_cpp "
        "--build-base /tmp/fq-content-filter-typed-build "
        "--install-base /tmp/fq-content-filter-typed-install "
        "--cmake-args -DCMAKE_BUILD_TYPE=Release >/dev/null && "
        "source /tmp/fq-content-filter-typed-install/setup.bash && "
        f"for i in $(seq 1 {run_count}); do "
        "/tmp/fq-content-filter-typed-install/rmw_fleetqox_cpp/lib/"
        "rmw_fleetqox_cpp/fleetrmw_content_filter_typed_probe || exit $?; done"
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
        if row.get("schema_version") == "fleetrmw.content_filter_typed_probe.v1"
    ]
    ok_run_count = sum(probe_ok(row) for row in rows)
    ok = (
        completed.returncode == 0
        and len(rows) == run_count
        and ok_run_count == run_count
    )
    last = rows[-1] if rows else {}
    return {
        "schema_version": SCHEMA_VERSION,
        "status": "ok" if ok else "failed",
        "image": image,
        "returncode": completed.returncode,
        "run_count": run_count,
        "ok_run_count": ok_run_count,
        "content_filter_typed_reflection_scope": (
            "ROSIDL introspection C/C++ nested scalar fields plus C++ "
            "sequence length/index and nested sequence-message fields"
        ),
        "content_filter_introspection_cpp_nested_fields_claim": ok,
        "content_filter_introspection_c_nested_fields_claim": ok,
        "content_filter_introspection_cpp_array_fields_claim": ok,
        "content_filter_malformed_typed_payload_fail_closed_claim": ok,
        "content_filter_typed_reflection_repeated_claim": ok and run_count >= 5,
        "cpp_evaluated": last.get("cpp_evaluated"),
        "cpp_matched": last.get("cpp_matched"),
        "cpp_dropped": last.get("cpp_dropped"),
        "c_evaluated": last.get("c_evaluated"),
        "c_matched": last.get("c_matched"),
        "c_dropped": last.get("c_dropped"),
        "array_evaluated": last.get("array_evaluated"),
        "array_matched": last.get("array_matched"),
        "array_dropped": last.get("array_dropped"),
        "typed_reflections": last.get("typed_reflections"),
        "clean_teardown": all(row.get("clean_teardown") is True for row in rows),
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
        default="results_rmw_socket/docker_content_filter_typed_probe_summary.json",
    )
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    summary = run_probe(root=ROOT, image=args.image, iterations=args.iterations)
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
        print(f"runs={summary['ok_run_count']}/{summary['run_count']}")
    return 0 if summary["status"] == "ok" else 1


if __name__ == "__main__":
    raise SystemExit(main())

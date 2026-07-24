"""Build and run the FleetRMW content-filter ABI and enforcement probe."""

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


SCHEMA_VERSION = "fleetrmw.docker_content_filter_probe.v1"
DEFAULT_IMAGE = "localhost/fleetrmw/rmw-netem:jazzy"


def parse_json_rows(stdout: str) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for line in stdout.splitlines():
        line = line.strip()
        if not line.startswith("{"):
            continue
        try:
            data = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(data, dict):
            rows.append(data)
    return rows


def content_filter_probe_ok(probe: dict[str, Any]) -> bool:
    return (
        probe.get("status") == "ok"
        and probe.get("expression_ok") is True
        and probe.get("parameters_ok") is True
        and probe.get("std_expression_ok") is True
        and probe.get("std_parameters_ok") is True
        and probe.get("content_filter_enabled_after_set") is True
        and probe.get("content_filter_enabled_after_std_set") is True
        and probe.get("content_filter_enabled_after_disable") is False
        and probe.get("content_filter_enforcement") is True
        and probe.get("raw_content_filter_enforcement") is True
        and probe.get("std_msgs_content_filter_enforcement") is True
        and probe.get("disabled_content_filter_bypass") is True
        and int(probe.get("content_filters_set_delta", 0)) == 3
        and int(probe.get("content_filters_got_delta", 0)) == 3
        and int(probe.get("raw_content_filters_evaluated_delta", 0)) == 3
        and int(probe.get("raw_content_filters_matched_delta", 0)) == 1
        and int(probe.get("raw_content_filters_dropped_delta", 0)) == 2
        and int(probe.get("std_msgs_content_filters_evaluated_delta", 0)) == 4
        and int(probe.get("std_msgs_content_filters_matched_delta", 0)) == 1
        and int(probe.get("std_msgs_content_filters_dropped_delta", 0)) == 3
        and int(probe.get("disabled_content_filters_evaluated_delta", 0)) == 0
        and int(probe.get("disabled_content_filters_matched_delta", 0)) == 0
        and int(probe.get("disabled_content_filters_dropped_delta", 0)) == 0
        and int(probe.get("content_filters_evaluated_delta", 0)) == 7
        and int(probe.get("content_filters_matched_delta", 0)) == 2
        and int(probe.get("content_filters_dropped_delta", 0)) == 5
    )


def run_probe(*, root: Path, image: str, iterations: int = 1) -> dict[str, Any]:
    run_count = max(iterations, 1)
    command = (
        "source /opt/ros/jazzy/setup.bash && "
        "rm -rf /tmp/fq-content-filter-build /tmp/fq-content-filter-install "
        "/tmp/fq-content-filter-log && "
        "colcon --log-base /tmp/fq-content-filter-log build --base-paths ros2_ws/src "
        "--packages-select rmw_fleetqox_cpp --build-base /tmp/fq-content-filter-build "
        "--install-base /tmp/fq-content-filter-install --cmake-args -DCMAKE_BUILD_TYPE=Release "
        ">/dev/null && source /tmp/fq-content-filter-install/setup.bash && "
        f"for i in $(seq 1 {run_count}); do "
        "/tmp/fq-content-filter-install/rmw_fleetqox_cpp/lib/rmw_fleetqox_cpp/"
        "fleetrmw_content_filter_probe || exit $?; done"
    )
    completed = subprocess.run(
        [
            "docker", "run", "--rm", "--entrypoint", "bash",
            "-v", f"{root}:/work", "-w", "/work", image, "-lc", command,
        ],
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    rows = parse_json_rows(completed.stdout)
    probe = rows[-1] if rows else parse_last_json(completed.stdout)
    ok_run_count = sum(1 for row in rows if content_filter_probe_ok(row))
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
        "content_filter_set_get_abi_supported": ok,
        "filter_enforcement": ok,
        "content_filter_enforcement_scope": "key_value_payload_and_std_msgs_string_text",
        "raw_content_filter_enforcement": probe.get("raw_content_filter_enforcement"),
        "std_msgs_content_filter_enforcement": probe.get(
            "std_msgs_content_filter_enforcement"
        ),
        "disabled_content_filter_bypass": probe.get("disabled_content_filter_bypass"),
        "content_filters_set_delta": probe.get("content_filters_set_delta"),
        "content_filters_got_delta": probe.get("content_filters_got_delta"),
        "raw_content_filters_evaluated_delta": probe.get(
            "raw_content_filters_evaluated_delta"
        ),
        "raw_content_filters_matched_delta": probe.get(
            "raw_content_filters_matched_delta"
        ),
        "raw_content_filters_dropped_delta": probe.get(
            "raw_content_filters_dropped_delta"
        ),
        "std_msgs_content_filters_evaluated_delta": probe.get(
            "std_msgs_content_filters_evaluated_delta"
        ),
        "std_msgs_content_filters_matched_delta": probe.get(
            "std_msgs_content_filters_matched_delta"
        ),
        "std_msgs_content_filters_dropped_delta": probe.get(
            "std_msgs_content_filters_dropped_delta"
        ),
        "disabled_content_filters_evaluated_delta": probe.get(
            "disabled_content_filters_evaluated_delta"
        ),
        "disabled_content_filters_matched_delta": probe.get(
            "disabled_content_filters_matched_delta"
        ),
        "disabled_content_filters_dropped_delta": probe.get(
            "disabled_content_filters_dropped_delta"
        ),
        "content_filters_evaluated_delta": probe.get("content_filters_evaluated_delta"),
        "content_filters_matched_delta": probe.get("content_filters_matched_delta"),
        "content_filters_dropped_delta": probe.get("content_filters_dropped_delta"),
        "content_filter_repeated_enforcement_claim": ok and run_count >= 5,
        "probe": probe,
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
        default="results_rmw_socket/docker_content_filter_probe_summary.json",
    )
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    summary = run_probe(root=ROOT, image=args.image, iterations=args.iterations)
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

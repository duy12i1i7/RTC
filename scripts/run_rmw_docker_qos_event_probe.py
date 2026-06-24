"""Build and run the FleetRMW no-op QoS event ABI probe."""

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


SCHEMA_VERSION = "fleetrmw.docker_qos_event_probe.v1"
DEFAULT_IMAGE = "localhost/fleetrmw/rmw-netem:jazzy"


def run_probe(*, root: Path, image: str) -> dict[str, Any]:
    command = (
        "source /opt/ros/jazzy/setup.bash && "
        "rm -rf /tmp/fq-qos-event-build /tmp/fq-qos-event-install /tmp/fq-qos-event-log && "
        "colcon --log-base /tmp/fq-qos-event-log build --base-paths ros2_ws/src "
        "--packages-select rmw_fleetqox_cpp --build-base /tmp/fq-qos-event-build "
        "--install-base /tmp/fq-qos-event-install --cmake-args -DCMAKE_BUILD_TYPE=Release "
        ">/dev/null && source /tmp/fq-qos-event-install/setup.bash && "
        "/tmp/fq-qos-event-install/rmw_fleetqox_cpp/lib/rmw_fleetqox_cpp/"
        "fleetrmw_qos_event_probe"
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
    probe = parse_last_json(completed.stdout)
    ok = (
        completed.returncode == 0
        and probe.get("status") == "ok"
        and probe.get("event_object_abi_ok") is True
        and probe.get("event_production") is False
    )
    return {
        "schema_version": SCHEMA_VERSION,
        "status": "ok" if ok else "failed",
        "image": image,
        "returncode": completed.returncode,
        "qos_event_object_abi_supported": ok,
        "event_production": False,
        "probe": probe,
        "stdout": completed.stdout,
        "stderr": completed.stderr,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--image", default=DEFAULT_IMAGE)
    parser.add_argument(
        "--summary-json",
        default="results_rmw_socket/docker_qos_event_probe_summary.json",
    )
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    summary = run_probe(root=ROOT, image=args.image)
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

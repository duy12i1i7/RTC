"""Prove later fragment-repair rounds are not re-quiesced by useful progress."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import shutil
import sys
import time
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.run_rmw_docker_authenticated_fragment_assembly_probe import (  # noqa: E402
    ensure_rmw_build,
)
from scripts.run_ros2_direct_rmw_netem_probe import (  # noqa: E402
    parse_last_json,
    run,
    wait_for_container_path,
)
from scripts.run_ros2_relay_rmw_netem_probe import (  # noqa: E402
    DEFAULT_IMAGE,
    SERIALIZED_RELAY_INSTALL,
)


SCHEMA_VERSION = "fleetrmw.progressive_fragment_repair.v1"
RECEIVER_SCHEMA_VERSION = "fleetrmw.progressive_fragment_repair_receiver.v1"
INJECTOR_SCHEMA_VERSION = "fleetrmw.progressive_fragment_repair_injector.v1"


RECEIVER_SCRIPT = r'''
import ctypes
import json
import os
import time

import rclpy
from rclpy.node import Node
from rclpy.qos import QoSProfile, ReliabilityPolicy
from std_msgs.msg import String


rclpy.init()
node = Node("fleetrmw_progressive_fragment_repair_receiver")
subscription = node.create_subscription(
    String,
    "/fleetqox/progressive_fragment_repair",
    lambda _message: None,
    QoSProfile(depth=10, reliability=ReliabilityPolicy.RELIABLE),
)
with open(os.environ["FLEETQOX_PROBE_READY_FILE"], "w", encoding="utf-8") as stream:
    stream.write("ready\n")

deadline = time.monotonic() + 1.6
while time.monotonic() < deadline:
    rclpy.spin_once(node, timeout_sec=0.02)

library = ctypes.CDLL("librmw_fleetqox_cpp.so")
names = (
    "fragment_active_assemblies",
    "fragment_active_missing_indexes",
    "fragment_nack_exhausted_assemblies",
    "fragment_nacks_sent",
    "fragment_nack_indexes_requested",
    "fragment_progressive_nacks_sent",
)
metrics = {}
for name in names:
    symbol = getattr(library, f"rmw_fleetqox_cpp_socket_{name}")
    symbol.restype = ctypes.c_uint64
    metrics[name] = int(symbol())

expected = {
    "fragment_active_assemblies": 1,
    "fragment_active_missing_indexes": 12,
    "fragment_nack_exhausted_assemblies": 1,
    "fragment_nacks_sent": 2,
    "fragment_nack_indexes_requested": 16,
    "fragment_progressive_nacks_sent": 1,
}
status = "ok" if metrics == expected else "failed"
print(json.dumps({
    "schema_version": "fleetrmw.progressive_fragment_repair_receiver.v1",
    "status": status,
    "metrics": metrics,
    "expected": expected,
}, sort_keys=True))
node.destroy_subscription(subscription)
node.destroy_node()
rclpy.shutdown()
raise SystemExit(0 if status == "ok" else 1)
'''


INJECTOR_SCRIPT = r'''
import json
import socket
import sys
import time


def expand_ranges(text):
    indexes = []
    for token in text.split(","):
        if "-" in token:
            first, last = (int(value) for value in token.split("-", 1))
            indexes.extend(range(first, last + 1))
        else:
            indexes.append(int(token))
    return indexes


target = (sys.argv[1], 49812)
sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
sock.bind(("0.0.0.0", 49811))
sock.settimeout(0.02)
prefix = "FLEETQOX_REPAIR_FRAGMENT_NACK_V1|"
fragment_prefix = "FLEETQOX_REPAIR_FRAGMENT_V1|progressive|"

def send_fragment(index):
    sock.sendto(f"{fragment_prefix}{index}|20|20|x".encode(), target)


send_fragment(0)
send_fragment(19)
requests = []
first_deadline = time.monotonic() + 0.8
while time.monotonic() < first_deadline and not requests:
    try:
        payload, _source = sock.recvfrom(65535)
    except socket.timeout:
        continue
    text = payload.decode("utf-8", errors="replace")
    if not text.startswith(prefix):
        continue
    fields = text[len(prefix):].split("|", 2)
    if len(fields) == 3:
        requests.append({
            "fragment_id": fields[0],
            "fragment_count": int(fields[1]),
            "indexes": fields[2],
        })

first_nack_at = time.monotonic()
progress_indexes = expand_ranges(requests[0]["indexes"])[:6] if requests else []
progress_sent = 0
progress_sent_at_second_nack = None
second_nack_elapsed_ms = None
for index in progress_indexes:
    send_fragment(index)
    progress_sent += 1
    interval_deadline = time.monotonic() + 0.075
    while time.monotonic() < interval_deadline:
        try:
            payload, _source = sock.recvfrom(65535)
        except socket.timeout:
            continue
        text = payload.decode("utf-8", errors="replace")
        if not text.startswith(prefix):
            continue
        fields = text[len(prefix):].split("|", 2)
        if len(fields) != 3:
            continue
        requests.append({
            "fragment_id": fields[0],
            "fragment_count": int(fields[1]),
            "indexes": fields[2],
        })
        if second_nack_elapsed_ms is None:
            second_nack_elapsed_ms = (time.monotonic() - first_nack_at) * 1000.0
            progress_sent_at_second_nack = progress_sent

late_deadline = time.monotonic() + 0.5
while time.monotonic() < late_deadline and len(requests) < 2:
    try:
        payload, _source = sock.recvfrom(65535)
    except socket.timeout:
        continue
    text = payload.decode("utf-8", errors="replace")
    if not text.startswith(prefix):
        continue
    fields = text[len(prefix):].split("|", 2)
    if len(fields) == 3:
        requests.append({
            "fragment_id": fields[0],
            "fragment_count": int(fields[1]),
            "indexes": fields[2],
        })
        second_nack_elapsed_ms = (time.monotonic() - first_nack_at) * 1000.0
        progress_sent_at_second_nack = progress_sent
sock.close()

request_indexes = [expand_ranges(row["indexes"]) for row in requests]
status = "ok" if (
    len(requests) == 2
    and all(row["fragment_id"] == "progressive" for row in requests)
    and all(row["fragment_count"] == 20 for row in requests)
    and request_indexes[0] == list(range(1, 9))
    and len(request_indexes[1]) == 8
    and second_nack_elapsed_ms is not None
    and 225.0 <= second_nack_elapsed_ms < 425.0
    and progress_sent_at_second_nack is not None
    and progress_sent_at_second_nack < len(progress_indexes)
) else "failed"
print(json.dumps({
    "schema_version": "fleetrmw.progressive_fragment_repair_injector.v1",
    "status": status,
    "progress_indexes": progress_indexes,
    "progress_sent_at_second_nack": progress_sent_at_second_nack,
    "second_nack_elapsed_ms": second_nack_elapsed_ms,
    "requests": requests,
}, sort_keys=True))
raise SystemExit(0 if status == "ok" else 1)
'''


def summarize_probe(
    receiver: dict[str, Any] | None,
    injector: dict[str, Any] | None,
    *,
    receiver_returncode: int,
    injector_returncode: int,
) -> dict[str, Any]:
    receiver_ok = (
        receiver_returncode == 0
        and isinstance(receiver, dict)
        and receiver.get("schema_version") == RECEIVER_SCHEMA_VERSION
        and receiver.get("status") == "ok"
        and receiver.get("metrics") == receiver.get("expected")
    )
    elapsed_ms = (
        float(injector.get("second_nack_elapsed_ms", 0.0))
        if isinstance(injector, dict) else 0.0
    )
    injector_ok = (
        injector_returncode == 0
        and isinstance(injector, dict)
        and injector.get("schema_version") == INJECTOR_SCHEMA_VERSION
        and injector.get("status") == "ok"
        and 225.0 <= elapsed_ms < 425.0
        and int(injector.get("progress_sent_at_second_nack", 99)) < 6
        and isinstance(injector.get("requests"), list)
        and len(injector["requests"]) == 2
    )
    contract_ok = receiver_ok and injector_ok
    return {
        "schema_version": SCHEMA_VERSION,
        "status": "ok" if contract_ok else "failed",
        "receiver_returncode": receiver_returncode,
        "injector_returncode": injector_returncode,
        "initial_nack_quiescence_claim": contract_ok,
        "progressive_multi_round_repair_claim": contract_ok,
        "bounded_repair_backoff_claim": contract_ok,
        "fleet_scale_selective_fragment_repair_claim": False,
        "production_large_sample_reliability_claim": False,
        "receiver": receiver,
        "injector": injector,
    }


def run_probe(*, root: Path, image: str) -> dict[str, Any]:
    suffix = f"{os.getpid()}-{time.time_ns() % 1_000_000_000}"
    network = f"fq-progress-net-{suffix}"
    receiver_name = f"fq-progress-r-{suffix}"
    injector_name = f"fq-progress-i-{suffix}"
    work_dir = root / f".tmp_fleetrmw_progressive_fragment_{suffix}"
    receiver_script = work_dir / "receiver.py"
    injector_script = work_dir / "injector.py"
    ready_path = "/tmp/fleetrmw_progressive_fragment_ready"
    receiver_returncode = injector_returncode = -1
    receiver_result: dict[str, Any] | None = None
    injector_result: dict[str, Any] | None = None
    receiver_logs_text = ""

    try:
        work_dir.mkdir(parents=True, exist_ok=True)
        receiver_script.write_text(RECEIVER_SCRIPT, encoding="utf-8")
        injector_script.write_text(INJECTOR_SCRIPT, encoding="utf-8")
        ensure_rmw_build(root=root, image=image)
        run(["docker", "network", "create", network])
        run([
            "docker", "run", "-d", "--name", injector_name,
            "--network", network, "--entrypoint", "bash",
            "-v", f"{root}:/work", "-w", "/work", image, "-lc", "sleep 20",
        ])
        receiver_command = (
            "source /opt/ros/jazzy/setup.bash && "
            f"source /work/{SERIALIZED_RELAY_INSTALL}/setup.bash && "
            "export RMW_IMPLEMENTATION=rmw_fleetqox_cpp && "
            "export FLEETQOX_RMW_BIND=0.0.0.0:49812 && "
            f"export FLEETQOX_RMW_PEERS={injector_name}:49811 && "
            "export FLEETQOX_RMW_FRAGMENT_NACK_INTERVAL_MS=100 && "
            "export FLEETQOX_RMW_FRAGMENT_NACK_MAX_REQUESTS=2 && "
            "export FLEETQOX_RMW_FRAGMENT_NACK_MAX_INDEXES_PER_REQUEST=8 && "
            "export FLEETQOX_RMW_FRAGMENT_TAIL_GUARD_MS=400 && "
            "export FLEETQOX_RMW_FRAGMENT_ASSEMBLY_LIMIT=8 && "
            "export FLEETQOX_RMW_FRAGMENT_MAX_ASSEMBLY_BYTES=4096 && "
            f"export FLEETQOX_PROBE_READY_FILE={ready_path} && "
            f"python3 /work/{receiver_script.relative_to(root)}"
        )
        run([
            "docker", "run", "-d", "--name", receiver_name,
            "--network", network, "--entrypoint", "bash",
            "-v", f"{root}:/work", "-w", "/work", image, "-lc", receiver_command,
        ])
        wait_for_container_path(receiver_name, ready_path, timeout_s=12.0)
        injector = run([
            "docker", "exec", injector_name, "python3",
            f"/work/{injector_script.relative_to(root)}", receiver_name,
        ], check=False)
        injector_returncode = injector.returncode
        injector_result = parse_last_json(injector.stdout)
        receiver_returncode = int(run(["docker", "wait", receiver_name]).stdout.strip())
        receiver_logs = run(["docker", "logs", receiver_name], check=False)
        receiver_logs_text = receiver_logs.stdout + receiver_logs.stderr
        receiver_result = parse_last_json(receiver_logs.stdout)
    finally:
        for container in (receiver_name, injector_name):
            run(["docker", "rm", "-f", container], check=False)
        run(["docker", "network", "rm", network], check=False)
        shutil.rmtree(work_dir, ignore_errors=True)

    summary = summarize_probe(
        receiver_result,
        injector_result,
        receiver_returncode=receiver_returncode,
        injector_returncode=injector_returncode,
    )
    summary["receiver_logs"] = receiver_logs_text
    return summary


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--image", default=DEFAULT_IMAGE)
    parser.add_argument(
        "--summary-json",
        type=Path,
        default=Path(
            "results_rmw_socket/docker_progressive_fragment_repair_probe_summary.json"
        ),
    )
    args = parser.parse_args()
    summary = run_probe(root=ROOT, image=args.image)
    path = ROOT / args.summary_json
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(
        f"status={summary['status']} "
        f"progressive={summary['progressive_multi_round_repair_claim']}"
    )
    return 0 if summary["status"] == "ok" else 1


if __name__ == "__main__":
    raise SystemExit(main())

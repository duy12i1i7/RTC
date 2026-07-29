"""Prove bounded fragment admission after FleetRMW UDP AEAD authentication."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.run_rmw_docker_udp_aead_probe import TEST_KEY_HEX  # noqa: E402
from scripts.run_ros2_direct_rmw_netem_probe import (  # noqa: E402
    parse_last_json,
    run,
    wait_for_container_path,
)
from scripts.run_ros2_relay_rmw_netem_probe import (  # noqa: E402
    DEFAULT_IMAGE,
    SERIALIZED_RELAY_BUILD,
    SERIALIZED_RELAY_INSTALL,
    SERIALIZED_RELAY_LOG,
)


SCHEMA_VERSION = "fleetrmw.authenticated_fragment_assembly_admission.v1"
RECEIVER_SCHEMA_VERSION = (
    "fleetrmw.authenticated_fragment_assembly_admission_receiver.v1"
)
PUBLISHER_SCHEMA_VERSION = (
    "fleetrmw.authenticated_fragment_assembly_admission_publisher.v1"
)
TOPIC = "/fleetqox/authenticated_fragment_assembly_admission"
PARTIAL_SAMPLE_COUNT = 6

RECEIVER_SCRIPT = r'''
import ctypes
import json
import os
import time

import rclpy
from rclpy.node import Node
from rclpy.qos import QoSProfile, ReliabilityPolicy
from std_msgs.msg import String


taken = 0


def receive(_message):
    global taken
    taken += 1


rclpy.init()
node = Node("fleetrmw_authenticated_fragment_admission_receiver")
subscription = node.create_subscription(
    String,
    "__TOPIC__",
    receive,
    QoSProfile(depth=10, reliability=ReliabilityPolicy.RELIABLE),
)
ready_path = os.environ["FLEETQOX_PROBE_READY_FILE"]
done_path = os.environ["FLEETQOX_PROBE_DONE_FILE"]
with open(ready_path, "w", encoding="utf-8") as stream:
    stream.write("ready\n")

deadline = time.monotonic() + 15.0
done_seen_at = None
while time.monotonic() < deadline:
    rclpy.spin_once(node, timeout_sec=0.05)
    if os.path.exists(done_path):
        if done_seen_at is None:
            done_seen_at = time.monotonic()
        if time.monotonic() - done_seen_at >= 0.75:
            break

library = ctypes.CDLL("librmw_fleetqox_cpp.so")
socket_names = (
    "fragment_active_assemblies",
    "fragment_active_missing_indexes",
    "fragment_assembly_evictions",
)
metrics = {}
for name in socket_names:
    symbol = getattr(library, f"rmw_fleetqox_cpp_socket_{name}")
    symbol.restype = ctypes.c_uint64
    metrics[name] = int(symbol())
for name in (
    "udp_aead_decrypted_frames",
    "udp_aead_authentication_failures",
    "udp_aead_unprotected_drops",
):
    symbol = getattr(library, f"rmw_fleetqox_cpp_{name}")
    symbol.restype = ctypes.c_uint64
    metrics[name] = int(symbol())
enabled = library.rmw_fleetqox_cpp_udp_aead_enabled
enabled.restype = ctypes.c_bool
metrics["udp_aead_enabled"] = bool(enabled())
metrics["taken"] = taken
metrics["done_seen"] = done_seen_at is not None

assembly_limit = int(os.environ["FLEETQOX_RMW_FRAGMENT_ASSEMBLY_LIMIT"])
partial_sample_count = int(os.environ["FLEETQOX_PROBE_PARTIAL_SAMPLE_COUNT"])
expected = {
    "fragment_active_assemblies": assembly_limit,
    "fragment_active_missing_indexes": assembly_limit,
    "fragment_assembly_evictions": partial_sample_count - assembly_limit,
    "udp_aead_authentication_failures": 0,
    "udp_aead_unprotected_drops": 2,
    "udp_aead_enabled": True,
    "taken": 0,
    "done_seen": True,
}
status = "ok" if (
    all(metrics.get(key) == value for key, value in expected.items())
    and metrics["udp_aead_decrypted_frames"] > 0
) else "failed"
print(json.dumps({
    "schema_version":
        "fleetrmw.authenticated_fragment_assembly_admission_receiver.v1",
    "status": status,
    "metrics": metrics,
    "expected": expected,
}, sort_keys=True))
node.destroy_subscription(subscription)
node.destroy_node()
rclpy.shutdown()
raise SystemExit(0 if status == "ok" else 1)
'''.replace("__TOPIC__", TOPIC)

PUBLISHER_SCRIPT = r'''
import ctypes
import json
import os
import socket
import time

import rclpy
from rclpy.node import Node
from rclpy.qos import QoSProfile, ReliabilityPolicy
from std_msgs.msg import String


rclpy.init()
node = Node("fleetrmw_authenticated_fragment_admission_publisher")
publisher = node.create_publisher(
    String,
    "__TOPIC__",
    QoSProfile(depth=10, reliability=ReliabilityPolicy.RELIABLE),
)
deadline = time.monotonic() + 8.0
while time.monotonic() < deadline and publisher.get_subscription_count() == 0:
    rclpy.spin_once(node, timeout_sec=0.05)
matched = publisher.get_subscription_count() > 0

published = 0
if matched:
    for index in range(__PARTIAL_SAMPLE_COUNT__):
        publisher.publish(String(data=f"{index:02d}|" + ("x" * 4096)))
        published += 1
        rclpy.spin_once(node, timeout_sec=0.02)
deadline = time.monotonic() + 0.75
while time.monotonic() < deadline:
    rclpy.spin_once(node, timeout_sec=0.05)

library = ctypes.CDLL("librmw_fleetqox_cpp.so")
metrics = {}
for name in ("test_dropped_fragments",):
    symbol = getattr(library, f"rmw_fleetqox_cpp_socket_{name}")
    symbol.restype = ctypes.c_uint64
    metrics[name] = int(symbol())
for name in (
    "udp_aead_encrypted_frames",
    "udp_aead_authentication_failures",
):
    symbol = getattr(library, f"rmw_fleetqox_cpp_{name}")
    symbol.restype = ctypes.c_uint64
    metrics[name] = int(symbol())
metrics["matched"] = matched
metrics["published"] = published

node.destroy_publisher(publisher)
node.destroy_node()
rclpy.shutdown()

target_host = os.environ["FLEETQOX_NEGATIVE_CONTROL_TARGET"]
raw = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
raw.sendto(
    b"FLEETQOX_REPAIR_FRAGMENT_V1|unprotected|0|2|8|abcd",
    (target_host, 49812),
)
raw.sendto(
    b"FLEETQOX_FRAGMENT_V1|unprotected-outer|0|2|8|abcd",
    (target_host, 49812),
)
raw.close()
metrics["unprotected_negative_control_count"] = 2

status = "ok" if (
    metrics["matched"]
    and metrics["published"] == __PARTIAL_SAMPLE_COUNT__
    and metrics["test_dropped_fragments"] == __PARTIAL_SAMPLE_COUNT__
    and metrics["udp_aead_encrypted_frames"] > 0
    and metrics["udp_aead_authentication_failures"] == 0
) else "failed"
print(json.dumps({
    "schema_version":
        "fleetrmw.authenticated_fragment_assembly_admission_publisher.v1",
    "status": status,
    "metrics": metrics,
}, sort_keys=True))
with open(os.environ["FLEETQOX_PROBE_DONE_FILE"], "w", encoding="utf-8") as stream:
    stream.write("done\n")
raise SystemExit(0 if status == "ok" else 1)
'''.replace("__TOPIC__", TOPIC).replace(
    "__PARTIAL_SAMPLE_COUNT__", str(PARTIAL_SAMPLE_COUNT)
)


def summarize_probe(
    receiver: dict[str, Any] | None,
    publisher: dict[str, Any] | None,
    *,
    receiver_returncode: int,
    publisher_returncode: int,
    assembly_limit: int,
    max_assembly_bytes: int,
    receiver_stderr: str = "",
    publisher_stderr: str = "",
) -> dict[str, Any]:
    receiver_metrics = (
        receiver.get("metrics") if isinstance(receiver, dict) else None
    )
    publisher_metrics = (
        publisher.get("metrics") if isinstance(publisher, dict) else None
    )
    receiver_ok = (
        receiver_returncode == 0
        and isinstance(receiver, dict)
        and receiver.get("status") == "ok"
        and receiver.get("schema_version") == RECEIVER_SCHEMA_VERSION
        and isinstance(receiver_metrics, dict)
        and int(receiver_metrics.get("fragment_active_assemblies", -1))
        == assembly_limit
        and int(receiver_metrics.get("fragment_active_missing_indexes", -1))
        == assembly_limit
        and int(receiver_metrics.get("fragment_assembly_evictions", -1))
        == PARTIAL_SAMPLE_COUNT - assembly_limit
        and receiver_metrics.get("udp_aead_enabled") is True
        and int(receiver_metrics.get("udp_aead_decrypted_frames", 0)) > 0
        and int(
            receiver_metrics.get("udp_aead_authentication_failures", -1)
        ) == 0
        and int(receiver_metrics.get("udp_aead_unprotected_drops", -1)) == 2
        and int(receiver_metrics.get("taken", -1)) == 0
        and receiver_metrics.get("done_seen") is True
    )
    publisher_ok = (
        publisher_returncode == 0
        and isinstance(publisher, dict)
        and publisher.get("status") == "ok"
        and publisher.get("schema_version") == PUBLISHER_SCHEMA_VERSION
        and isinstance(publisher_metrics, dict)
        and publisher_metrics.get("matched") is True
        and int(publisher_metrics.get("published", -1))
        == PARTIAL_SAMPLE_COUNT
        and int(publisher_metrics.get("test_dropped_fragments", -1))
        == PARTIAL_SAMPLE_COUNT
        and int(publisher_metrics.get("udp_aead_encrypted_frames", 0)) > 0
        and int(
            publisher_metrics.get("udp_aead_authentication_failures", -1)
        ) == 0
        and int(
            publisher_metrics.get("unprotected_negative_control_count", -1)
        ) == 2
    )
    contract_ok = receiver_ok and publisher_ok
    return {
        "schema_version": SCHEMA_VERSION,
        "status": "ok" if contract_ok else "failed",
        "assembly_limit": assembly_limit,
        "max_assembly_bytes": max_assembly_bytes,
        "authenticated_partial_sample_count": PARTIAL_SAMPLE_COUNT,
        "receiver_returncode": receiver_returncode,
        "publisher_returncode": publisher_returncode,
        "udp_aead_cipher": "AES-256-GCM",
        "udp_aead_key_management": "pre_shared_test_key",
        "authenticated_fragment_assembly_admission_claim": contract_ok,
        "docker_authenticated_fragment_resource_bound_claim": contract_ok,
        "udp_unprotected_fragment_fail_closed_claim": receiver_ok,
        "peer_identity_authentication_claim": False,
        "production_fragment_security_claim": False,
        "receiver": receiver,
        "publisher": publisher,
        "receiver_stderr": receiver_stderr,
        "publisher_stderr": publisher_stderr,
    }


def ensure_rmw_build(*, root: Path, image: str) -> None:
    install = root / SERIALIZED_RELAY_INSTALL
    setup = install / "setup.bash"
    library = install / "rmw_fleetqox_cpp" / "lib" / "librmw_fleetqox_cpp.so"
    source_root = root / "ros2_ws" / "src" / "rmw_fleetqox_cpp"
    inputs = (
        list(source_root.glob("src/*.cpp"))
        + list(source_root.glob("include/**/*.hpp"))
        + [source_root / "CMakeLists.txt", source_root / "package.xml"]
    )
    if (
        setup.exists()
        and library.exists()
        and all(
            not path.exists() or path.stat().st_mtime <= library.stat().st_mtime
            for path in inputs
        )
    ):
        return
    completed = run([
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
        "source /opt/ros/jazzy/setup.bash && "
        f"colcon --log-base /work/{SERIALIZED_RELAY_LOG} "
        "build --base-paths ros2_ws/src "
        "--packages-select fleetrmw_interfaces rmw_fleetqox_cpp "
        f"--build-base /work/{SERIALIZED_RELAY_BUILD} "
        f"--install-base /work/{SERIALIZED_RELAY_INSTALL} "
        "--cmake-args -DCMAKE_BUILD_TYPE=Release",
    ], check=False)
    if completed.returncode != 0 or not setup.exists() or not library.exists():
        raise RuntimeError(
            "FleetRMW reusable Docker build failed: "
            f"{completed.stderr[-2000:]}"
        )


def run_probe(
    *,
    root: Path,
    image: str,
    assembly_limit: int,
    max_assembly_bytes: int,
) -> dict[str, Any]:
    suffix = f"{os.getpid()}-{time.time_ns()}"
    network = f"fleetrmw-auth-fragment-net-{suffix}"
    receiver_name = f"fleetrmw-auth-fragment-receiver-{suffix}"
    publisher_name = f"fleetrmw-auth-fragment-publisher-{suffix}"
    work_dir = root / f".tmp_fleetrmw_authenticated_fragment_{suffix}"
    receiver_script = work_dir / "receiver.py"
    publisher_script = work_dir / "publisher.py"
    ready_path = "/tmp/fleetrmw_authenticated_fragment_ready"
    done_path = f"/work/{work_dir.relative_to(root)}/publisher_done"
    receiver_returncode = -1
    publisher_returncode = -1
    receiver_result: dict[str, Any] | None = None
    publisher_result: dict[str, Any] | None = None
    receiver_stderr = ""
    publisher_stderr = ""

    try:
        work_dir.mkdir(parents=True, exist_ok=True)
        receiver_script.write_text(RECEIVER_SCRIPT, encoding="utf-8")
        publisher_script.write_text(PUBLISHER_SCRIPT, encoding="utf-8")
        ensure_rmw_build(root=root, image=image)
        run(["docker", "network", "create", network])
        common_environment = [
            "-e",
            "RMW_IMPLEMENTATION=rmw_fleetqox_cpp",
            "-e",
            f"FLEETQOX_RMW_UDP_AEAD_KEY_HEX={TEST_KEY_HEX}",
            "-e",
            "FLEETQOX_RMW_UDP_AEAD_REQUIRE=1",
            "-e",
            "FLEETQOX_RMW_LOSS_RESILIENT_FRAGMENT_CHUNK_BYTES=1024",
            "-e",
            "FLEETQOX_RMW_FRAGMENT_NACK_MAX_REQUESTS=0",
            "-e",
            "FLEETQOX_RMW_RELIABLE_MAX_RETRANSMISSIONS=0",
            "-e",
            "FLEETQOX_RMW_FRAGMENT_ASYNC_SEND=0",
            "-e",
            "FLEETQOX_RMW_UDP_SEND_PACING_US=500",
            "-e",
            f"FLEETQOX_PROBE_DONE_FILE={done_path}",
            "-e",
            f"FLEETQOX_PROBE_PARTIAL_SAMPLE_COUNT={PARTIAL_SAMPLE_COUNT}",
        ]
        run([
            "docker",
            "run",
            "-d",
            "--name",
            publisher_name,
            "--network",
            network,
            "--entrypoint",
            "bash",
            "-v",
            f"{root}:/work",
            "-w",
            "/work",
            *common_environment,
            "-e",
            "FLEETQOX_RMW_BIND=0.0.0.0:49811",
            "-e",
            f"FLEETQOX_RMW_PEERS={receiver_name}:49812",
            "-e",
            "FLEETQOX_RMW_TEST_DROP_FRAGMENT_INDEXES=1",
            "-e",
            f"FLEETQOX_NEGATIVE_CONTROL_TARGET={receiver_name}",
            image,
            "-lc",
            "sleep 30",
        ])
        receiver_command = (
            "source /opt/ros/jazzy/setup.bash && "
            f"source /work/{SERIALIZED_RELAY_INSTALL}/setup.bash && "
            f"python3 /work/{receiver_script.relative_to(root)}"
        )
        run([
            "docker",
            "run",
            "-d",
            "--name",
            receiver_name,
            "--network",
            network,
            "--entrypoint",
            "bash",
            "-v",
            f"{root}:/work",
            "-w",
            "/work",
            *common_environment,
            "-e",
            "FLEETQOX_RMW_BIND=0.0.0.0:49812",
            "-e",
            f"FLEETQOX_RMW_PEERS={publisher_name}:49811",
            "-e",
            f"FLEETQOX_RMW_FRAGMENT_ASSEMBLY_LIMIT={assembly_limit}",
            "-e",
            f"FLEETQOX_RMW_FRAGMENT_MAX_ASSEMBLY_BYTES={max_assembly_bytes}",
            "-e",
            f"FLEETQOX_PROBE_READY_FILE={ready_path}",
            image,
            "-lc",
            receiver_command,
        ])
        wait_for_container_path(receiver_name, ready_path, timeout_s=12.0)
        publisher = run([
            "docker",
            "exec",
            publisher_name,
            "bash",
            "-lc",
            "source /opt/ros/jazzy/setup.bash && "
            f"source /work/{SERIALIZED_RELAY_INSTALL}/setup.bash && "
            f"python3 /work/{publisher_script.relative_to(root)}",
        ], check=False)
        publisher_returncode = publisher.returncode
        publisher_result = parse_last_json(publisher.stdout)
        publisher_stderr = publisher.stderr
        receiver_returncode = int(
            run(["docker", "wait", receiver_name]).stdout.strip()
        )
        receiver_logs = run(["docker", "logs", receiver_name], check=False)
        receiver_result = parse_last_json(receiver_logs.stdout)
        receiver_stderr = receiver_logs.stderr
    finally:
        for container in (receiver_name, publisher_name):
            run(["docker", "rm", "-f", container], check=False)
        run(["docker", "network", "rm", network], check=False)
        shutil.rmtree(work_dir, ignore_errors=True)

    return summarize_probe(
        receiver_result,
        publisher_result,
        receiver_returncode=receiver_returncode,
        publisher_returncode=publisher_returncode,
        assembly_limit=assembly_limit,
        max_assembly_bytes=max_assembly_bytes,
        receiver_stderr=receiver_stderr,
        publisher_stderr=publisher_stderr,
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--image", default=DEFAULT_IMAGE)
    parser.add_argument("--assembly-limit", type=int, default=4)
    parser.add_argument("--max-assembly-bytes", type=int, default=16384)
    parser.add_argument(
        "--summary-json",
        type=Path,
        default=Path(
            "results_rmw_socket/"
            "docker_authenticated_fragment_assembly_probe_summary.json"
        ),
    )
    args = parser.parse_args()
    assembly_limit = max(min(args.assembly_limit, PARTIAL_SAMPLE_COUNT - 1), 1)
    summary = run_probe(
        root=ROOT,
        image=args.image,
        assembly_limit=assembly_limit,
        max_assembly_bytes=max(
            min(args.max_assembly_bytes, 256 * 1024 * 1024),
            8192,
        ),
    )
    path = ROOT / args.summary_json
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(summary, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(
        f"status={summary['status']} "
        "authenticated_bound="
        f"{summary['authenticated_fragment_assembly_admission_claim']} "
        "unprotected_fail_closed="
        f"{summary['udp_unprotected_fragment_fail_closed_claim']}"
    )
    return 0 if summary["status"] == "ok" else 1


if __name__ == "__main__":
    raise SystemExit(main())

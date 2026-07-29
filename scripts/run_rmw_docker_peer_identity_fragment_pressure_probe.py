"""Prove unauthorized X.509 peers cannot consume fragment reassembly state."""

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
    PARTIAL_SAMPLE_COUNT,
    TEST_KEY_HEX,
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


SCHEMA_VERSION = "fleetrmw.peer_identity_fragment_pressure.v1"
RECEIVER_SCHEMA_VERSION = "fleetrmw.peer_identity_fragment_pressure_receiver.v1"
PUBLISHER_SCHEMA_VERSION = "fleetrmw.peer_identity_fragment_pressure_publisher.v1"
TOPIC = "/fleetqox/peer_identity_fragment_pressure"
ATTACKER_SAMPLE_COUNT = 6

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


library = None


def metrics():
    global library
    if library is None:
        library = ctypes.CDLL("librmw_fleetqox_cpp.so")
    result = {}
    for name in (
        "fragment_active_assemblies",
        "fragment_active_missing_indexes",
        "fragment_assembly_evictions",
    ):
        symbol = getattr(library, f"rmw_fleetqox_cpp_socket_{name}")
        symbol.restype = ctypes.c_uint64
        result[name] = int(symbol())
    for name in (
        "udp_aead_decrypted_frames",
        "udp_aead_authentication_failures",
        "udp_peer_auth_verified_frames",
        "udp_peer_auth_failures",
        "udp_peer_auth_chain_failures",
        "udp_peer_auth_signature_failures",
        "udp_peer_auth_identity_denied",
    ):
        symbol = getattr(library, f"rmw_fleetqox_cpp_{name}")
        symbol.restype = ctypes.c_uint64
        result[name] = int(symbol())
    enabled = library.rmw_fleetqox_cpp_udp_peer_auth_enabled
    enabled.restype = ctypes.c_bool
    result["udp_peer_auth_enabled"] = bool(enabled())
    identity = library.rmw_fleetqox_cpp_udp_peer_auth_last_identity
    identity.restype = ctypes.c_char_p
    value = identity()
    result["udp_peer_auth_last_identity"] = (
        value.decode("utf-8") if value else ""
    )
    result["taken"] = taken
    return result


def spin_until_file(path, timeout_s):
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline and not os.path.exists(path):
        rclpy.spin_once(node, timeout_sec=0.05)
    if not os.path.exists(path):
        return False
    settle = time.monotonic() + 0.75
    while time.monotonic() < settle:
        rclpy.spin_once(node, timeout_sec=0.05)
    return True


rclpy.init(args=[
    "--ros-args",
    "--enclave",
    os.environ["FLEETQOX_RMW_PROBE_ENCLAVE"],
])
node = Node("fleetrmw_peer_identity_fragment_pressure_receiver")
subscription = node.create_subscription(
    String,
    "__TOPIC__",
    receive,
    QoSProfile(depth=10, reliability=ReliabilityPolicy.RELIABLE),
)
with open(os.environ["FLEETQOX_PROBE_READY_FILE"], "w", encoding="utf-8") as stream:
    stream.write("ready\n")

allowed_done = spin_until_file(
    os.environ["FLEETQOX_ALLOWED_DONE_FILE"], 15.0
)
baseline = metrics()
with open(
    os.environ["FLEETQOX_BASELINE_READY_FILE"], "w", encoding="utf-8"
) as stream:
    stream.write("ready\n")
attacker_done = spin_until_file(
    os.environ["FLEETQOX_ATTACKER_DONE_FILE"], 15.0
)
final = metrics()

assembly_limit = int(os.environ["FLEETQOX_RMW_FRAGMENT_ASSEMBLY_LIMIT"])
expected_state = {
    "fragment_active_assemblies": assembly_limit,
    "fragment_active_missing_indexes": assembly_limit,
    "fragment_assembly_evictions":
        int(os.environ["FLEETQOX_ALLOWED_SAMPLE_COUNT"]) - assembly_limit,
}
state_unchanged = all(
    baseline.get(key) == value and final.get(key) == value
    for key, value in expected_state.items()
)
identity_denied_delta = (
    final["udp_peer_auth_identity_denied"]
    - baseline["udp_peer_auth_identity_denied"]
)
peer_auth_failure_delta = (
    final["udp_peer_auth_failures"] - baseline["udp_peer_auth_failures"]
)
status = "ok" if (
    allowed_done
    and attacker_done
    and state_unchanged
    and baseline["udp_peer_auth_enabled"]
    and baseline["udp_peer_auth_verified_frames"] > 0
    and baseline["udp_peer_auth_identity_denied"] == 0
    and baseline["udp_peer_auth_chain_failures"] == 0
    and baseline["udp_peer_auth_signature_failures"] == 0
    and baseline["udp_peer_auth_last_identity"] == "/fleetqox/allowed"
    and baseline["udp_aead_decrypted_frames"] > 0
    and baseline["udp_aead_authentication_failures"] == 0
    and identity_denied_delta > 0
    and peer_auth_failure_delta >= identity_denied_delta
    and final["udp_peer_auth_chain_failures"] == 0
    and final["udp_peer_auth_signature_failures"] == 0
    and final["udp_peer_auth_last_identity"] == "/fleetqox/allowed"
    and final["udp_aead_authentication_failures"] == 0
    and final["taken"] == 0
) else "failed"
print(json.dumps({
    "schema_version": "fleetrmw.peer_identity_fragment_pressure_receiver.v1",
    "status": status,
    "allowed_done": allowed_done,
    "attacker_done": attacker_done,
    "expected_state": expected_state,
    "state_unchanged": state_unchanged,
    "identity_denied_delta": identity_denied_delta,
    "peer_auth_failure_delta": peer_auth_failure_delta,
    "baseline": baseline,
    "final": final,
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
import time

import rclpy
from rclpy.node import Node
from rclpy.qos import QoSProfile, ReliabilityPolicy
from std_msgs.msg import String


role = os.environ["FLEETQOX_PROBE_ROLE"]
sample_count = int(os.environ["FLEETQOX_PROBE_SAMPLE_COUNT"])
expected_drops = int(os.environ["FLEETQOX_PROBE_EXPECTED_DROPS"])
rclpy.init(args=[
    "--ros-args",
    "--enclave",
    os.environ["FLEETQOX_RMW_PROBE_ENCLAVE"],
])
node = Node(f"fleetrmw_peer_identity_pressure_{role}")
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
    for index in range(sample_count):
        publisher.publish(
            String(data=f"{role}|{index:02d}|" + (role[0] * 4096))
        )
        published += 1
        rclpy.spin_once(node, timeout_sec=0.02)
deadline = time.monotonic() + 0.75
while time.monotonic() < deadline:
    rclpy.spin_once(node, timeout_sec=0.05)

library = ctypes.CDLL("librmw_fleetqox_cpp.so")
metrics = {"matched": matched, "published": published}
for name in ("test_dropped_fragments",):
    symbol = getattr(library, f"rmw_fleetqox_cpp_socket_{name}")
    symbol.restype = ctypes.c_uint64
    metrics[name] = int(symbol())
for name in (
    "udp_aead_encrypted_frames",
    "udp_peer_auth_signed_frames",
    "udp_peer_auth_failures",
):
    symbol = getattr(library, f"rmw_fleetqox_cpp_{name}")
    symbol.restype = ctypes.c_uint64
    metrics[name] = int(symbol())

status = "ok" if (
    matched
    and published == sample_count
    and metrics["test_dropped_fragments"] == expected_drops
    and metrics["udp_aead_encrypted_frames"] > 0
    and metrics["udp_peer_auth_signed_frames"] > 0
    and metrics["udp_peer_auth_failures"] == 0
) else "failed"
print(json.dumps({
    "schema_version": "fleetrmw.peer_identity_fragment_pressure_publisher.v1",
    "status": status,
    "role": role,
    "metrics": metrics,
}, sort_keys=True))
node.destroy_publisher(publisher)
node.destroy_node()
rclpy.shutdown()
with open(os.environ["FLEETQOX_PROBE_DONE_FILE"], "w", encoding="utf-8") as stream:
    stream.write("done\n")
raise SystemExit(0 if status == "ok" else 1)
'''.replace("__TOPIC__", TOPIC)


def summarize_probe(
    receiver: dict[str, Any] | None,
    allowed: dict[str, Any] | None,
    attacker: dict[str, Any] | None,
    *,
    receiver_returncode: int,
    allowed_returncode: int,
    attacker_returncode: int,
    assembly_limit: int,
) -> dict[str, Any]:
    baseline = receiver.get("baseline") if isinstance(receiver, dict) else None
    final = receiver.get("final") if isinstance(receiver, dict) else None
    expected = (
        receiver.get("expected_state") if isinstance(receiver, dict) else None
    )
    receiver_ok = (
        receiver_returncode == 0
        and isinstance(receiver, dict)
        and receiver.get("schema_version") == RECEIVER_SCHEMA_VERSION
        and receiver.get("status") == "ok"
        and receiver.get("state_unchanged") is True
        and isinstance(baseline, dict)
        and isinstance(final, dict)
        and isinstance(expected, dict)
        and int(expected.get("fragment_active_assemblies", -1))
        == assembly_limit
        and int(receiver.get("identity_denied_delta", 0)) > 0
        and int(final.get("udp_peer_auth_identity_denied", 0))
        > int(baseline.get("udp_peer_auth_identity_denied", -1))
    )

    def publisher_ok(row: dict[str, Any] | None, role: str, rc: int) -> bool:
        metrics = row.get("metrics") if isinstance(row, dict) else None
        expected_drops = PARTIAL_SAMPLE_COUNT if role == "allowed" else 0
        expected_samples = (
            PARTIAL_SAMPLE_COUNT
            if role == "allowed"
            else ATTACKER_SAMPLE_COUNT
        )
        return (
            rc == 0
            and isinstance(row, dict)
            and row.get("schema_version") == PUBLISHER_SCHEMA_VERSION
            and row.get("status") == "ok"
            and row.get("role") == role
            and isinstance(metrics, dict)
            and metrics.get("matched") is True
            and int(metrics.get("published", -1)) == expected_samples
            and int(metrics.get("test_dropped_fragments", -1))
            == expected_drops
            and int(metrics.get("udp_peer_auth_signed_frames", 0)) > 0
        )

    allowed_ok = publisher_ok(allowed, "allowed", allowed_returncode)
    attacker_ok = publisher_ok(attacker, "attacker", attacker_returncode)
    contract_ok = receiver_ok and allowed_ok and attacker_ok
    return {
        "schema_version": SCHEMA_VERSION,
        "status": "ok" if contract_ok else "failed",
        "assembly_limit": assembly_limit,
        "allowed_partial_sample_count": PARTIAL_SAMPLE_COUNT,
        "attacker_sample_count": ATTACKER_SAMPLE_COUNT,
        "receiver_returncode": receiver_returncode,
        "allowed_returncode": allowed_returncode,
        "attacker_returncode": attacker_returncode,
        "peer_auth_scheme": "SROS2 X.509 CA + SHA-256 certificate signature",
        "payload_protection": "AES-256-GCM PSK",
        "peer_identity_fragment_pressure_isolation_claim": contract_ok,
        "unauthorized_identity_pre_reassembly_rejection_claim": contract_ok,
        "authorized_fragment_resource_bound_preserved_claim": contract_ok,
        "production_fragment_security_claim": False,
        "receiver": receiver,
        "allowed_publisher": allowed,
        "attacker_publisher": attacker,
    }


def identity_environment(
    *,
    enclave_dir: str,
    identity: str,
    allowed_identity: str,
) -> list[str]:
    return [
        "-e",
        f"FLEETQOX_RMW_PROBE_ENCLAVE={identity}",
        "-e",
        f"FLEETQOX_RMW_SROS2_IDENTITY_CERT_FILE={enclave_dir}/cert.pem",
        "-e",
        f"FLEETQOX_RMW_SROS2_IDENTITY_KEY_FILE={enclave_dir}/key.pem",
        "-e",
        (
            "FLEETQOX_RMW_SROS2_IDENTITY_CA_FILE="
            f"{enclave_dir}/identity_ca.cert.pem"
        ),
        "-e",
        "FLEETQOX_RMW_UDP_PEER_AUTH_REQUIRE=1",
        "-e",
        f"FLEETQOX_RMW_UDP_PEER_IDENTITIES={allowed_identity}",
    ]


def run_probe(
    *,
    root: Path,
    image: str,
    assembly_limit: int,
    max_assembly_bytes: int,
) -> dict[str, Any]:
    suffix = f"{os.getpid()}-{time.time_ns()}"
    network = f"fleetrmw-peer-fragment-net-{suffix}"
    receiver_name = f"fleetrmw-peer-fragment-receiver-{suffix}"
    allowed_name = f"fleetrmw-peer-fragment-allowed-{suffix}"
    attacker_name = f"fleetrmw-peer-fragment-attacker-{suffix}"
    work_dir = root / f".tmp_fleetrmw_peer_fragment_{suffix}"
    receiver_script = work_dir / "receiver.py"
    publisher_script = work_dir / "publisher.py"
    keystore = work_dir / "keystore"
    ready_path = "/tmp/fleetrmw_peer_fragment_ready"
    allowed_done = f"/work/{work_dir.relative_to(root)}/allowed_done"
    baseline_ready = f"/work/{work_dir.relative_to(root)}/baseline_ready"
    attacker_done = f"/work/{work_dir.relative_to(root)}/attacker_done"
    receiver_result: dict[str, Any] | None = None
    allowed_result: dict[str, Any] | None = None
    attacker_result: dict[str, Any] | None = None
    receiver_returncode = allowed_returncode = attacker_returncode = -1

    try:
        work_dir.mkdir(parents=True, exist_ok=True)
        receiver_script.write_text(RECEIVER_SCRIPT, encoding="utf-8")
        publisher_script.write_text(PUBLISHER_SCRIPT, encoding="utf-8")
        ensure_rmw_build(root=root, image=image)
        keystore_relative = keystore.relative_to(root)
        credentials = run([
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
            f"ros2 security create_keystore /work/{keystore_relative} "
            ">/dev/null && "
            "for identity in allowed receiver attacker; do "
            f"ros2 security create_enclave /work/{keystore_relative} "
            '"/fleetqox/${identity}" >/dev/null; '
            "done",
        ], check=False)
        if credentials.returncode != 0:
            raise RuntimeError(
                "failed to create peer identity credentials: "
                f"{credentials.stderr[-2000:]}"
            )
        run(["docker", "network", "create", network])
        base = f"/work/{keystore_relative}/enclaves/fleetqox"
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
        ]

        def start_sleeper(
            name: str,
            *,
            port: int,
            peers: str,
            identity: str,
            allowed_identity: str,
            role: str,
            sample_count: int,
            expected_drops: int,
            done_file: str,
        ) -> None:
            command = [
                "docker",
                "run",
                "-d",
                "--name",
                name,
                "--network",
                network,
                "--entrypoint",
                "bash",
                "-v",
                f"{root}:/work",
                "-w",
                "/work",
                *common_environment,
                *identity_environment(
                    enclave_dir=f"{base}/{identity.rsplit('/', 1)[-1]}",
                    identity=identity,
                    allowed_identity=allowed_identity,
                ),
                "-e",
                f"FLEETQOX_RMW_BIND=0.0.0.0:{port}",
                "-e",
                f"FLEETQOX_RMW_PEERS={peers}",
                "-e",
                f"FLEETQOX_PROBE_ROLE={role}",
                "-e",
                f"FLEETQOX_PROBE_SAMPLE_COUNT={sample_count}",
                "-e",
                f"FLEETQOX_PROBE_EXPECTED_DROPS={expected_drops}",
                "-e",
                f"FLEETQOX_PROBE_DONE_FILE={done_file}",
            ]
            if expected_drops:
                command.extend([
                    "-e",
                    "FLEETQOX_RMW_TEST_DROP_FRAGMENT_INDEXES=1",
                ])
            command.extend([image, "-lc", "sleep 40"])
            run(command)

        start_sleeper(
            allowed_name,
            port=49811,
            peers=f"{receiver_name}:49812",
            identity="/fleetqox/allowed",
            allowed_identity="/fleetqox/receiver",
            role="allowed",
            sample_count=PARTIAL_SAMPLE_COUNT,
            expected_drops=PARTIAL_SAMPLE_COUNT,
            done_file=allowed_done,
        )
        start_sleeper(
            attacker_name,
            port=49813,
            peers=f"{receiver_name}:49812",
            identity="/fleetqox/attacker",
            allowed_identity="/fleetqox/receiver",
            role="attacker",
            sample_count=ATTACKER_SAMPLE_COUNT,
            expected_drops=0,
            done_file=attacker_done,
        )
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
            *identity_environment(
                enclave_dir=f"{base}/receiver",
                identity="/fleetqox/receiver",
                allowed_identity="/fleetqox/allowed",
            ),
            "-e",
            "FLEETQOX_RMW_BIND=0.0.0.0:49812",
            "-e",
            (
                "FLEETQOX_RMW_PEERS="
                f"{allowed_name}:49811,{attacker_name}:49813"
            ),
            "-e",
            f"FLEETQOX_RMW_FRAGMENT_ASSEMBLY_LIMIT={assembly_limit}",
            "-e",
            f"FLEETQOX_RMW_FRAGMENT_MAX_ASSEMBLY_BYTES={max_assembly_bytes}",
            "-e",
            f"FLEETQOX_PROBE_READY_FILE={ready_path}",
            "-e",
            f"FLEETQOX_ALLOWED_DONE_FILE={allowed_done}",
            "-e",
            f"FLEETQOX_BASELINE_READY_FILE={baseline_ready}",
            "-e",
            f"FLEETQOX_ATTACKER_DONE_FILE={attacker_done}",
            "-e",
            f"FLEETQOX_ALLOWED_SAMPLE_COUNT={PARTIAL_SAMPLE_COUNT}",
            image,
            "-lc",
            receiver_command,
        ])
        try:
            wait_for_container_path(receiver_name, ready_path, timeout_s=12.0)
        except Exception as exc:
            logs = run(["docker", "logs", receiver_name], check=False)
            raise RuntimeError(
                "peer-identity receiver did not become ready: "
                f"stdout={logs.stdout[-4000:]!r} "
                f"stderr={logs.stderr[-4000:]!r}"
            ) from exc
        allowed_process = run([
            "docker",
            "exec",
            allowed_name,
            "bash",
            "-lc",
            "source /opt/ros/jazzy/setup.bash && "
            f"source /work/{SERIALIZED_RELAY_INSTALL}/setup.bash && "
            f"python3 /work/{publisher_script.relative_to(root)}",
        ], check=False)
        allowed_returncode = allowed_process.returncode
        allowed_result = parse_last_json(allowed_process.stdout)
        wait_for_container_path(
            receiver_name, baseline_ready, timeout_s=12.0
        )
        attacker_process = run([
            "docker",
            "exec",
            attacker_name,
            "bash",
            "-lc",
            "source /opt/ros/jazzy/setup.bash && "
            f"source /work/{SERIALIZED_RELAY_INSTALL}/setup.bash && "
            f"python3 /work/{publisher_script.relative_to(root)}",
        ], check=False)
        attacker_returncode = attacker_process.returncode
        attacker_result = parse_last_json(attacker_process.stdout)
        receiver_returncode = int(
            run(["docker", "wait", receiver_name]).stdout.strip()
        )
        receiver_logs = run(["docker", "logs", receiver_name], check=False)
        receiver_result = parse_last_json(receiver_logs.stdout)
    finally:
        for container in (receiver_name, allowed_name, attacker_name):
            run(["docker", "rm", "-f", container], check=False)
        run(["docker", "network", "rm", network], check=False)
        shutil.rmtree(work_dir, ignore_errors=True)

    return summarize_probe(
        receiver_result,
        allowed_result,
        attacker_result,
        receiver_returncode=receiver_returncode,
        allowed_returncode=allowed_returncode,
        attacker_returncode=attacker_returncode,
        assembly_limit=assembly_limit,
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
            "docker_peer_identity_fragment_pressure_probe_summary.json"
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
        "identity_pressure_isolated="
        f"{summary['peer_identity_fragment_pressure_isolation_claim']}"
    )
    return 0 if summary["status"] == "ok" else 1


if __name__ == "__main__":
    raise SystemExit(main())

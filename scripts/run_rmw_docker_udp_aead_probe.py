"""Build and repeat the FleetRMW UDP AES-256-GCM data-plane probe in Docker."""

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


SCHEMA_VERSION = "fleetrmw.docker_udp_aead_probe.v1"
TEST_KEY_HEX = "7f" * 32


def valid_row(row: dict[str, Any]) -> bool:
    return (
        row.get("status") == "ok"
        and row.get("probe_mode") == "valid"
        and row.get("udp_aead_enabled") is True
        and int(row.get("publish_returncode", -1)) == 0
        and row.get("taken") is True
        and row.get("payload_ok") is True
        and int(row.get("encrypted_frames_delta", 0)) >= 1
        and int(row.get("decrypted_frames_delta", 0)) >= 1
        and int(row.get("authentication_failures_delta", -1)) == 0
        and row.get("udp_aead_authenticated_encryption_claim") is True
        and row.get("udp_authenticated_psk_session_key_derivation_claim") is True
        and int(row.get("session_key_reuses_delta", 0)) >= 1
    )


def tamper_row_ok(row: dict[str, Any]) -> bool:
    return (
        row.get("status") == "ok"
        and row.get("probe_mode") == "tamper"
        and row.get("udp_aead_enabled") is True
        and int(row.get("publish_returncode", -1)) == 0
        and row.get("taken") is False
        and int(row.get("encrypted_frames_delta", 0)) >= 1
        and int(row.get("decrypted_frames_delta", -1)) == 0
        and int(row.get("authentication_failures_delta", 0)) >= 1
        and row.get("udp_aead_tamper_fail_closed_claim") is True
    )


def rotation_row_ok(row: dict[str, Any]) -> bool:
    return (
        row.get("status") == "ok"
        and row.get("probe_mode") == "rotation"
        and row.get("udp_aead_enabled") is True
        and int(row.get("publish_returncode", -1)) == 0
        and row.get("taken") is True
        and row.get("payload_ok") is True
        and int(row.get("session_keys_derived_delta", 0)) >= 2
        and int(row.get("session_key_rotations_delta", 0)) >= 1
        and row.get("udp_session_key_rotation_claim") is True
    )


def run_probe(*, root: Path, image: str, iterations: int = 1) -> dict[str, Any]:
    run_count = max(iterations, 1)
    command = (
        "source /opt/ros/jazzy/setup.bash && set -eo pipefail && "
        "rm -rf /tmp/fq-aead-build /tmp/fq-aead-install /tmp/fq-aead-log && "
        "colcon --log-base /tmp/fq-aead-log build --base-paths ros2_ws/src "
        "--packages-select rmw_fleetqox_cpp --build-base /tmp/fq-aead-build "
        "--install-base /tmp/fq-aead-install --cmake-args -DCMAKE_BUILD_TYPE=Release "
        ">/dev/null && source /tmp/fq-aead-install/setup.bash && "
        f"export FLEETQOX_RMW_UDP_AEAD_KEY_HEX={TEST_KEY_HEX} && "
        "export FLEETQOX_RMW_UDP_AEAD_REQUIRE=1 && "
        f"for i in $(seq 1 {run_count}); do "
        "/tmp/fq-aead-install/rmw_fleetqox_cpp/lib/rmw_fleetqox_cpp/"
        "fleetrmw_udp_aead_probe || exit $?; done && "
        "export FLEETQOX_RMW_UDP_SESSION_KEY_ROTATE_FRAMES=1 && "
        "/tmp/fq-aead-install/rmw_fleetqox_cpp/lib/rmw_fleetqox_cpp/"
        "fleetrmw_udp_aead_probe && "
        "unset FLEETQOX_RMW_UDP_SESSION_KEY_ROTATE_FRAMES && "
        "export FLEETQOX_RMW_UDP_AEAD_TAMPER_OUTBOUND_ONCE=1 && "
        "/tmp/fq-aead-install/rmw_fleetqox_cpp/lib/rmw_fleetqox_cpp/"
        "fleetrmw_udp_aead_probe && "
        "unset FLEETQOX_RMW_UDP_AEAD_TAMPER_OUTBOUND_ONCE "
        "FLEETQOX_RMW_UDP_AEAD_KEY_HEX && "
        "set +e; /tmp/fq-aead-install/rmw_fleetqox_cpp/lib/rmw_fleetqox_cpp/"
        "fleetrmw_udp_aead_probe >/tmp/fq-aead-missing-key.out 2>&1; "
        "missing_key_rc=$?; set -e; test $missing_key_rc -ne 0 && "
        "grep -q 'create_endpoint_failed' /tmp/fq-aead-missing-key.out && "
        "echo strict_missing_key_fail_closed=1"
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
    all_rows = parse_json_rows(completed.stdout)
    rows = [row for row in all_rows if row.get("probe_mode") == "valid"]
    tamper_rows = [row for row in all_rows if row.get("probe_mode") == "tamper"]
    rotation_rows = [row for row in all_rows if row.get("probe_mode") == "rotation"]
    ok_run_count = sum(1 for row in rows if valid_row(row))
    tamper_control = tamper_rows[-1] if tamper_rows else {}
    tamper_control_ok = tamper_row_ok(tamper_control)
    rotation_control = rotation_rows[-1] if rotation_rows else {}
    rotation_control_ok = rotation_row_ok(rotation_control)
    strict_missing_key_fail_closed = (
        "strict_missing_key_fail_closed=1" in completed.stdout
    )
    ok = (
        completed.returncode == 0
        and len(rows) == run_count
        and ok_run_count == run_count
        and len(tamper_rows) == 1
        and tamper_control_ok
        and len(rotation_rows) == 1
        and rotation_control_ok
        and strict_missing_key_fail_closed
    )
    probe = rows[-1] if rows else {}
    return {
        "schema_version": SCHEMA_VERSION,
        "status": "ok" if ok else "failed",
        "image": image,
        "returncode": completed.returncode,
        "run_count": run_count,
        "ok_run_count": ok_run_count,
        "udp_aead_cipher": "AES-256-GCM",
        "udp_aead_key_management": "pre_shared_test_key",
        "udp_aead_authenticated_encryption_claim": ok,
        "udp_aead_repeated_authenticated_encryption_claim": ok and run_count >= 5,
        "udp_aead_tamper_fail_closed_claim": tamper_control_ok,
        "udp_authenticated_psk_session_key_derivation_claim": (
            ok_run_count == run_count
        ),
        "udp_session_key_rotation_claim": rotation_control_ok,
        "session_key_establishment_claim": (
            ok_run_count == run_count and rotation_control_ok
        ),
        "forward_secrecy_claim": False,
        "asymmetric_session_key_exchange_claim": False,
        "udp_aead_strict_missing_key_fail_closed_claim": (
            strict_missing_key_fail_closed
        ),
        "encrypted_frames_delta": probe.get("encrypted_frames_delta"),
        "decrypted_frames_delta": probe.get("decrypted_frames_delta"),
        "authentication_failures_delta": tamper_control.get(
            "authentication_failures_delta"
        ),
        "session_keys_derived_delta": rotation_control.get(
            "session_keys_derived_delta"
        ),
        "session_key_rotations_delta": rotation_control.get(
            "session_key_rotations_delta"
        ),
        "sros2_peer_identity_authentication_claim": False,
        "dds_security_interoperability_claim": False,
        "production_security_hardening_claim": False,
        "security_scope": "fleetqox_udp_payload_aes_256_gcm_psk",
        "probe": probe,
        "runs": rows,
        "tamper_control": tamper_control,
        "rotation_control": rotation_control,
        "stdout": completed.stdout,
        "stderr": completed.stderr,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--image", default=DEFAULT_IMAGE)
    parser.add_argument("--iterations", type=int, default=1)
    parser.add_argument(
        "--summary-json",
        default="results_rmw_socket/docker_udp_aead_probe_summary.json",
    )
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    root = ROOT
    summary = run_probe(root=root, image=args.image, iterations=args.iterations)
    output = root / args.summary_json
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n")
    if args.json:
        print(json.dumps(summary, sort_keys=True))
    else:
        print(
            f"status={summary['status']} ok_runs={summary['ok_run_count']}/"
            f"{summary['run_count']} tamper={summary['udp_aead_tamper_fail_closed_claim']}"
        )
    return 0 if summary["status"] == "ok" else 1


if __name__ == "__main__":
    raise SystemExit(main())

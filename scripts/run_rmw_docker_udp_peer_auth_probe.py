"""Build and exercise certificate-authenticated FleetRMW UDP AEAD peers in Docker."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import shlex
import subprocess
import sys
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.run_rmw_docker_allocation_probe import DEFAULT_IMAGE, parse_json_rows


SCHEMA_VERSION = "fleetrmw.docker_udp_peer_auth_probe.v1"
TEST_KEY_HEX = "4b" * 32


def _subscriber_rows(rows: list[dict[str, Any]], topic_prefix: str) -> list[dict[str, Any]]:
    return [
        row
        for row in rows
        if row.get("mode") == "subscriber"
        and str(row.get("topic", "")).startswith(topic_prefix)
    ]


def _publisher_rows(rows: list[dict[str, Any]], topic_prefix: str) -> list[dict[str, Any]]:
    return [
        row
        for row in rows
        if row.get("mode") == "publisher"
        and str(row.get("topic", "")).startswith(topic_prefix)
    ]


def run_probe(*, root: Path, image: str, iterations: int = 1) -> dict[str, Any]:
    run_count = max(iterations, 1)
    executable = (
        "/tmp/fq-peer-auth-install/rmw_fleetqox_cpp/lib/"
        "rmw_fleetqox_cpp/fleetrmw_interprocess_pubsub_probe"
    )
    crl_python = (
        "from datetime import datetime, timedelta, timezone; "
        "from pathlib import Path; "
        "from cryptography import x509; "
        "from cryptography.hazmat.primitives import hashes, serialization; "
        "root=Path('/tmp/fq-peer-auth-keystore'); "
        "ca=x509.load_pem_x509_certificate("
        "(root/'public/identity_ca.cert.pem').read_bytes()); "
        "key=serialization.load_pem_private_key("
        "(root/'private/identity_ca.key.pem').read_bytes(),password=None); "
        "peer=x509.load_pem_x509_certificate("
        "(root/'enclaves/fleetqox/peer_c/cert.pem').read_bytes()); "
        "now=datetime.now(timezone.utc); "
        "revoked=x509.RevokedCertificateBuilder().serial_number("
        "peer.serial_number).revocation_date(now).build(); "
        "crl=x509.CertificateRevocationListBuilder().issuer_name("
        "ca.subject).last_update(now).next_update(now+timedelta(days=1))."
        "add_revoked_certificate(revoked).sign(key,hashes.SHA256()); "
        "Path('/tmp/fq-peer-auth-revoked.crl.pem').write_bytes("
        "crl.public_bytes(serialization.Encoding.PEM))"
    )
    command = f"""
source /opt/ros/jazzy/setup.bash
set -eo pipefail
rm -rf /tmp/fq-peer-auth-build /tmp/fq-peer-auth-install /tmp/fq-peer-auth-log \
  /tmp/fq-peer-auth-keystore /tmp/fq-peer-auth-untrusted-keystore \
  /tmp/fq-peer-auth-*.json
colcon --log-base /tmp/fq-peer-auth-log build --base-paths ros2_ws/src \
  --packages-select rmw_fleetqox_cpp --build-base /tmp/fq-peer-auth-build \
  --install-base /tmp/fq-peer-auth-install --cmake-args -DCMAKE_BUILD_TYPE=Release \
  >/dev/null
source /tmp/fq-peer-auth-install/setup.bash
ros2 security create_keystore /tmp/fq-peer-auth-keystore >/dev/null
ros2 security create_enclave /tmp/fq-peer-auth-keystore /fleetqox/peer_a >/dev/null
ros2 security create_enclave /tmp/fq-peer-auth-keystore /fleetqox/peer_b >/dev/null
ros2 security create_enclave /tmp/fq-peer-auth-keystore /fleetqox/peer_c >/dev/null
ros2 security create_keystore /tmp/fq-peer-auth-untrusted-keystore >/dev/null
ros2 security create_enclave \
  /tmp/fq-peer-auth-untrusted-keystore /fleetqox/peer_d >/dev/null
python3 -c {shlex.quote(crl_python)}

run_pair() {{
  case_name="$1"
  port_base="$2"
  publisher_keystore="$3"
  publisher_name="$4"
  subscriber_allow="$5"
  tamper_signature="$6"
  expect_taken="$7"
  subscriber_crl="$8"
  topic="/fleetqox/udp_peer_auth/${{case_name}}"
  subscriber_dir="/tmp/fq-peer-auth-keystore/enclaves/fleetqox/peer_b"
  publisher_dir="${{publisher_keystore}}/enclaves/fleetqox/${{publisher_name}}"
  set +e
  env \
    RMW_IMPLEMENTATION=rmw_fleetqox_cpp \
    FLEETQOX_RMW_PROBE_ENCLAVE=/fleetqox/peer_b \
    FLEETQOX_RMW_SROS2_IDENTITY_CERT_FILE="${{subscriber_dir}}/cert.pem" \
    FLEETQOX_RMW_SROS2_IDENTITY_KEY_FILE="${{subscriber_dir}}/key.pem" \
    FLEETQOX_RMW_SROS2_IDENTITY_CA_FILE="${{subscriber_dir}}/identity_ca.cert.pem" \
    FLEETQOX_RMW_UDP_AEAD_KEY_HEX={TEST_KEY_HEX} \
    FLEETQOX_RMW_UDP_AEAD_REQUIRE=1 \
    FLEETQOX_RMW_UDP_PEER_AUTH_REQUIRE=1 \
    FLEETQOX_RMW_UDP_PEER_IDENTITIES="${{subscriber_allow}}" \
    FLEETQOX_RMW_SROS2_IDENTITY_CRL_FILE="${{subscriber_crl}}" \
    FLEETQOX_RMW_BIND="127.0.0.1:$((port_base + 1))" \
    FLEETQOX_RMW_PEERS="127.0.0.1:${{port_base}}" \
    {executable} --mode subscriber --topic "${{topic}}" \
      --payload fleetqox-peer-authenticated-aead --timeout-ms 2500 \
      --expect-taken "${{expect_taken}}" \
      >"/tmp/fq-peer-auth-${{case_name}}-subscriber.json" 2>&1 &
  subscriber_pid=$!
  sleep 0.25
  env \
    RMW_IMPLEMENTATION=rmw_fleetqox_cpp \
    FLEETQOX_RMW_PROBE_ENCLAVE="/fleetqox/${{publisher_name}}" \
    FLEETQOX_RMW_SROS2_IDENTITY_CERT_FILE="${{publisher_dir}}/cert.pem" \
    FLEETQOX_RMW_SROS2_IDENTITY_KEY_FILE="${{publisher_dir}}/key.pem" \
    FLEETQOX_RMW_SROS2_IDENTITY_CA_FILE="${{publisher_dir}}/identity_ca.cert.pem" \
    FLEETQOX_RMW_UDP_AEAD_KEY_HEX={TEST_KEY_HEX} \
    FLEETQOX_RMW_UDP_AEAD_REQUIRE=1 \
    FLEETQOX_RMW_UDP_PEER_AUTH_REQUIRE=1 \
    FLEETQOX_RMW_UDP_PEER_IDENTITIES=/fleetqox/peer_b \
    FLEETQOX_RMW_UDP_PEER_AUTH_TAMPER_OUTBOUND_ONCE="${{tamper_signature}}" \
    FLEETQOX_RMW_BIND="127.0.0.1:${{port_base}}" \
    FLEETQOX_RMW_PEERS="127.0.0.1:$((port_base + 1))" \
    {executable} --mode publisher --topic "${{topic}}" \
      --payload fleetqox-peer-authenticated-aead --pre-publish-ms 100 \
      >"/tmp/fq-peer-auth-${{case_name}}-publisher.json" 2>&1
  publisher_rc=$?
  wait "${{subscriber_pid}}"
  subscriber_rc=$?
  set -e
  cat "/tmp/fq-peer-auth-${{case_name}}-publisher.json"
  cat "/tmp/fq-peer-auth-${{case_name}}-subscriber.json"
  test "${{publisher_rc}}" -eq 0
  test "${{subscriber_rc}}" -eq 0
}}

for i in $(seq 1 {run_count}); do
  run_pair "valid_${{i}}" "$((50200 + i * 4))" \
    /tmp/fq-peer-auth-keystore peer_a /fleetqox/peer_a 0 true ""
done
run_pair unauthorized 50300 \
  /tmp/fq-peer-auth-keystore peer_c /fleetqox/peer_a 0 false ""
run_pair signature_tamper 50310 \
  /tmp/fq-peer-auth-keystore peer_a /fleetqox/peer_a 1 false ""
run_pair untrusted_certificate 50320 \
  /tmp/fq-peer-auth-untrusted-keystore peer_d /fleetqox/peer_d 0 false ""
run_pair revoked_certificate 50330 \
  /tmp/fq-peer-auth-keystore peer_c /fleetqox/peer_c 0 false \
  /tmp/fq-peer-auth-revoked.crl.pem
"""
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
    rows = parse_json_rows(completed.stdout)
    valid_subscribers = _subscriber_rows(rows, "/fleetqox/udp_peer_auth/valid_")
    valid_publishers = _publisher_rows(rows, "/fleetqox/udp_peer_auth/valid_")
    valid_pairs = 0
    for subscriber in valid_subscribers:
        suffix = str(subscriber.get("topic", "")).rsplit("/", 1)[-1]
        publisher = next(
            (
                row
                for row in valid_publishers
                if str(row.get("topic", "")).endswith("/" + suffix)
            ),
            {},
        )
        if (
            subscriber.get("status") == "ok"
            and subscriber.get("taken") is True
            and subscriber.get("payload") == "fleetqox-peer-authenticated-aead"
            and subscriber.get("udp_peer_auth_enabled") is True
            and int(subscriber.get("udp_peer_auth_verified_frames", 0)) >= 1
            and subscriber.get("udp_peer_auth_last_identity") == "/fleetqox/peer_a"
            and publisher.get("status") == "ok"
            and publisher.get("udp_peer_auth_enabled") is True
            and int(publisher.get("udp_peer_auth_signed_frames", 0)) >= 1
        ):
            valid_pairs += 1

    unauthorized = next(
        iter(_subscriber_rows(rows, "/fleetqox/udp_peer_auth/unauthorized")), {}
    )
    signature_tamper = next(
        iter(_subscriber_rows(rows, "/fleetqox/udp_peer_auth/signature_tamper")), {}
    )
    untrusted = next(
        iter(
            _subscriber_rows(
                rows, "/fleetqox/udp_peer_auth/untrusted_certificate"
            )
        ),
        {},
    )
    revoked = next(
        iter(
            _subscriber_rows(rows, "/fleetqox/udp_peer_auth/revoked_certificate")
        ),
        {},
    )
    unauthorized_ok = (
        unauthorized.get("status") == "ok"
        and unauthorized.get("taken") is False
        and int(unauthorized.get("udp_peer_auth_identity_denied", 0)) >= 1
    )
    signature_tamper_ok = (
        signature_tamper.get("status") == "ok"
        and signature_tamper.get("taken") is False
        and int(signature_tamper.get("udp_peer_auth_signature_failures", 0)) >= 1
    )
    untrusted_ok = (
        untrusted.get("status") == "ok"
        and untrusted.get("taken") is False
        and int(untrusted.get("udp_peer_auth_chain_failures", 0)) >= 1
    )
    revoked_ok = (
        revoked.get("status") == "ok"
        and revoked.get("taken") is False
        and revoked.get("udp_peer_auth_crl_enabled") is True
        and int(revoked.get("udp_peer_auth_revoked_certificate_drops", 0)) >= 1
    )
    valid_ok = (
        len(valid_subscribers) == run_count
        and len(valid_publishers) == run_count
        and valid_pairs == run_count
    )
    ok = (
        completed.returncode == 0
        and valid_ok
        and unauthorized_ok
        and signature_tamper_ok
        and untrusted_ok
        and revoked_ok
    )
    return {
        "schema_version": SCHEMA_VERSION,
        "status": "ok" if ok else "failed",
        "image": image,
        "returncode": completed.returncode,
        "run_count": run_count,
        "ok_run_count": valid_pairs,
        "peer_auth_scheme": "SROS2 X.509 CA + SHA-256 certificate signature",
        "payload_protection": "AES-256-GCM PSK",
        "sros2_peer_identity_authentication_claim": valid_ok,
        "sros2_peer_identity_repeated_authentication_claim": (
            valid_ok and run_count >= 5
        ),
        "udp_peer_identity_allowlist_fail_closed_claim": unauthorized_ok,
        "udp_peer_signature_tamper_fail_closed_claim": signature_tamper_ok,
        "udp_peer_untrusted_certificate_fail_closed_claim": untrusted_ok,
        "udp_certificate_authenticated_aead_claim": ok,
        "session_key_establishment_claim": False,
        "certificate_revocation_claim": revoked_ok,
        "dds_security_interoperability_claim": False,
        "production_security_hardening_claim": False,
        "security_scope": "fleetqox_udp_certificate_signed_aead_psk",
        "valid_subscribers": valid_subscribers,
        "valid_publishers": valid_publishers,
        "unauthorized_identity_control": unauthorized,
        "signature_tamper_control": signature_tamper,
        "untrusted_certificate_control": untrusted,
        "revoked_certificate_control": revoked,
        "stdout": completed.stdout,
        "stderr": completed.stderr,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--image", default=DEFAULT_IMAGE)
    parser.add_argument("--iterations", type=int, default=1)
    parser.add_argument(
        "--summary-json",
        default="results_rmw_socket/docker_udp_peer_auth_probe_summary.json",
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
            f"status={summary['status']} peers={summary['ok_run_count']}/"
            f"{summary['run_count']} controls="
            f"{summary['udp_peer_identity_allowlist_fail_closed_claim']}/"
            f"{summary['udp_peer_signature_tamper_fail_closed_claim']}/"
            f"{summary['udp_peer_untrusted_certificate_fail_closed_claim']}/"
            f"{summary['certificate_revocation_claim']}"
        )
    return 0 if summary["status"] == "ok" else 1


if __name__ == "__main__":
    raise SystemExit(main())

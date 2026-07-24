"""Run a Docker stress/soak/security campaign across FleetRMW boundary probes.

This runner aggregates existing Docker probes into one campaign artifact.  A
short/default run is only a smoke/repeat boundary; the long-campaign claim stays
false unless an explicit long profile meets the configured runtime threshold.
"""

from __future__ import annotations

import argparse
import json
import time
from pathlib import Path
import sys
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.run_rmw_docker_allocation_probe import (  # noqa: E402
    DEFAULT_IMAGE,
    run_probe as run_allocation_probe,
)
from scripts.run_rmw_docker_content_filter_probe import (  # noqa: E402
    run_probe as run_content_filter_probe,
)
from scripts.run_rmw_docker_dynamic_message_probe import (  # noqa: E402
    run_probe as run_dynamic_message_probe,
)
from scripts.run_rmw_docker_qos_event_probe import (  # noqa: E402
    run_probe as run_qos_event_probe,
)
from scripts.run_rmw_docker_quic_gateway_async_burst_soak import (  # noqa: E402
    aggregate as aggregate_quic_gateway_soak,
)
from scripts.run_rmw_docker_quic_gateway_netem_publish_probe import (  # noqa: E402
    run_probe as run_quic_netem_probe,
)
from scripts.run_rmw_docker_quic_gateway_publish_probe import (  # noqa: E402
    run_probe as run_quic_publish_probe,
)
from scripts.run_rmw_docker_security_options_probe import (  # noqa: E402
    run_probe as run_security_options_probe,
)
from scripts.run_rmw_docker_security_policy_probe import (  # noqa: E402
    DEFAULT_POLICY as DEFAULT_SECURITY_POLICY,
    run_probe as run_security_policy_probe,
)
from scripts.run_rmw_docker_sros2_permissions_probe import (  # noqa: E402
    run_probe as run_sros2_permissions_probe,
)
from scripts.run_rmw_docker_udp_aead_probe import (  # noqa: E402
    run_probe as run_udp_aead_probe,
)
from scripts.run_rmw_docker_udp_peer_auth_probe import (  # noqa: E402
    run_probe as run_udp_peer_auth_probe,
)


SCHEMA_VERSION = "fleetrmw.docker_stress_security_campaign.v1"
ALL_COMPONENTS = (
    "security_options",
    "security_policy",
    "sros2_permissions",
    "udp_aead",
    "udp_peer_auth",
    "dynamic_message",
    "allocation",
    "qos_event",
    "content_filter",
    "quic_gateway_async_burst_soak",
)
PROFILE_DEFAULTS = {
    "smoke": {
        "abi_iterations": 1,
        "security_iterations": 1,
        "quic_iterations": 1,
        "long_min_runtime_s": 3600.0,
    },
    "repeated": {
        "abi_iterations": 5,
        "security_iterations": 5,
        "quic_iterations": 3,
        "long_min_runtime_s": 3600.0,
    },
    "long": {
        "abi_iterations": 20,
        "security_iterations": 20,
        "quic_iterations": 30,
        "long_min_runtime_s": 3600.0,
    },
}


def as_int(value: Any) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def component_run_count(summary: dict[str, Any]) -> int:
    return max(as_int(summary.get("run_count")), len(summary.get("runs", [])), len(summary.get("rows", [])))


def component_ok_run_count(summary: dict[str, Any]) -> int:
    if "ok_run_count" in summary:
        return as_int(summary.get("ok_run_count"))
    rows = summary.get("rows") or summary.get("runs") or []
    if isinstance(rows, list):
        return sum(1 for row in rows if isinstance(row, dict) and row.get("status") == "ok")
    return int(summary.get("status") == "ok")


def component_row(name: str, summary: dict[str, Any]) -> dict[str, Any]:
    run_count = component_run_count(summary)
    ok_run_count = component_ok_run_count(summary)
    return {
        "component": name,
        "schema_version": summary.get("schema_version"),
        "status": "ok" if summary.get("status") == "ok" else "failed",
        "run_count": run_count,
        "ok_run_count": ok_run_count,
        "failed_run_count": max(run_count - ok_run_count, 0),
        "stress_component_ok": summary.get("status") == "ok" and ok_run_count == run_count,
        "summary": summary,
    }


def aggregate_campaign(
    components: list[dict[str, Any]],
    *,
    profile: str,
    elapsed_s: float,
    long_min_runtime_s: float,
    quic_netem: bool,
) -> dict[str, Any]:
    component_count = len(components)
    ok_components = [
        row for row in components
        if row.get("status") == "ok" and row.get("stress_component_ok") is True
    ]
    total_runs = sum(as_int(row.get("run_count")) for row in components)
    total_ok_runs = sum(as_int(row.get("ok_run_count")) for row in components)
    quic = next(
        (
            row.get("summary", {})
            for row in components
            if row.get("component") == "quic_gateway_async_burst_soak"
        ),
        {},
    )
    security = next(
        (
            row.get("summary", {})
            for row in components
            if row.get("component") == "security_options"
        ),
        {},
    )
    security_policy = next(
        (
            row.get("summary", {})
            for row in components
            if row.get("component") == "security_policy"
        ),
        {},
    )
    sros2_permissions = next(
        (
            row.get("summary", {})
            for row in components
            if row.get("component") == "sros2_permissions"
        ),
        {},
    )
    udp_aead = next(
        (
            row.get("summary", {})
            for row in components
            if row.get("component") == "udp_aead"
        ),
        {},
    )
    udp_peer_auth = next(
        (
            row.get("summary", {})
            for row in components
            if row.get("component") == "udp_peer_auth"
        ),
        {},
    )
    dynamic_message = next(
        (
            row.get("summary", {})
            for row in components
            if row.get("component") == "dynamic_message"
        ),
        {},
    )
    abi_components = [
        row for row in components
        if row.get("component") in {
            "allocation",
            "qos_event",
            "content_filter",
            "security_options",
            "security_policy",
            "sros2_permissions",
            "udp_aead",
            "udp_peer_auth",
            "dynamic_message",
        }
    ]
    repeated_abi_ok = bool(abi_components) and all(
        row.get("stress_component_ok") is True and as_int(row.get("run_count")) >= 5
        for row in abi_components
    )
    repeated_quic_ok = (
        not quic
        or (
            quic.get("status") == "ok"
            and as_int(quic.get("run_count")) >= 3
            and as_int(quic.get("total_quic_gateway_frames_failed")) == 0
            and as_int(quic.get("total_quic_gateway_frames_dropped")) == 0
        )
    )
    campaign_ok = component_count > 0 and len(ok_components) == component_count
    long_claim = (
        campaign_ok
        and profile == "long"
        and elapsed_s >= long_min_runtime_s
        and total_runs >= 70
    )
    return {
        "schema_version": SCHEMA_VERSION,
        "status": "ok" if campaign_ok else "failed",
        "campaign_profile": profile,
        "component_count": component_count,
        "ok_component_count": len(ok_components),
        "failed_component_count": component_count - len(ok_components),
        "total_component_runs": total_runs,
        "total_component_ok_runs": total_ok_runs,
        "total_component_failed_runs": max(total_runs - total_ok_runs, 0),
        "elapsed_s": round(elapsed_s, 3),
        "long_min_runtime_s": long_min_runtime_s,
        "quic_netem": quic_netem,
        "stress_security_smoke_claim": campaign_ok,
        "stress_security_repeated_claim": campaign_ok and repeated_abi_ok and repeated_quic_ok,
        "long_stress_security_campaign_claim": long_claim,
        "long_stress_security_campaign_blocker": (
            ""
            if long_claim
            else "profile_or_runtime_threshold_not_met"
        ),
        "security_policy_enforcement_executed": bool(
            sros2_permissions.get("security_policy_enforcement_executed")
            or security.get("security_policy_enforcement_executed")
        ),
        "security_hardening_blocker": (
            "forward_secret_key_exchange_and_transport_hardening_not_implemented"
            if udp_peer_auth.get("sros2_peer_identity_authentication_claim")
            else sros2_permissions.get(
                "security_policy_enforcement_gap_reason",
                security.get("security_hardening_blocker", ""),
            )
        ),
        "fleetqox_security_policy_enforcement_claim": bool(
            security_policy.get("fleetqox_security_policy_enforcement_claim")
        ),
        "security_policy_repeated_enforcement_claim": bool(
            security_policy.get("security_policy_repeated_enforcement_claim")
        ),
        "sros2_cli_generated_artifacts": bool(
            sros2_permissions.get("sros2_cli_generated_artifacts")
        ),
        "signed_permissions_verified_preflight": bool(
            sros2_permissions.get("signed_permissions_verified_preflight")
        ),
        "permissions_xsd_validated": bool(
            sros2_permissions.get("permissions_xsd_validated")
        ),
        "sros2_permissions_xml_publish_enforcement_claim": bool(
            sros2_permissions.get("sros2_permissions_xml_publish_enforcement_claim")
        ),
        "sros2_permissions_xml_subscribe_enforcement_claim": bool(
            sros2_permissions.get(
                "sros2_permissions_xml_subscribe_enforcement_claim"
            )
        ),
        "sros2_permissions_xml_pubsub_enforcement_claim": bool(
            sros2_permissions.get("sros2_permissions_xml_pubsub_enforcement_claim")
        ),
        "sros2_permissions_xml_repeated_enforcement_claim": bool(
            sros2_permissions.get("sros2_permissions_xml_repeated_enforcement_claim")
        ),
        "sros2_permissions_xml_subscribe_repeated_enforcement_claim": bool(
            sros2_permissions.get(
                "sros2_permissions_xml_subscribe_repeated_enforcement_claim"
            )
        ),
        "malformed_permissions_fail_closed_claim": bool(
            sros2_permissions.get("malformed_permissions_fail_closed_claim")
        ),
        "runtime_sros2_permissions_signature_validation_claim": bool(
            sros2_permissions.get(
                "runtime_sros2_permissions_signature_validation_claim"
            )
        ),
        "tampered_signed_permissions_fail_closed_claim": bool(
            sros2_permissions.get(
                "tampered_signed_permissions_fail_closed_claim"
            )
        ),
        "sros2_service_request_reply_authorization_claim": bool(
            sros2_permissions.get(
                "sros2_service_request_reply_authorization_claim"
            )
        ),
        "sros2_service_repeated_authorization_claim": bool(
            sros2_permissions.get("sros2_service_repeated_authorization_claim")
        ),
        "sros2_action_authorization_claim": bool(
            sros2_permissions.get("sros2_action_authorization_claim")
        ),
        "sros2_action_repeated_authorization_claim": bool(
            sros2_permissions.get("sros2_action_repeated_authorization_claim")
        ),
        "sros2_action_allowed_end_to_end_claim": bool(
            sros2_permissions.get("sros2_action_allowed_end_to_end_claim")
        ),
        "sros2_action_call_denied_fail_closed_claim": bool(
            sros2_permissions.get(
                "sros2_action_call_denied_fail_closed_claim"
            )
        ),
        "sros2_action_execute_denied_fail_closed_claim": bool(
            sros2_permissions.get(
                "sros2_action_execute_denied_fail_closed_claim"
            )
        ),
        "sros2_action_call_execute_decision_matrix_claim": bool(
            sros2_permissions.get(
                "sros2_action_call_execute_decision_matrix_claim"
            )
        ),
        "governance_xml_enforcement_claim": bool(
            sros2_permissions.get("governance_xml_enforcement_claim")
        ),
        "sros2_governance_access_control_claim": bool(
            sros2_permissions.get("sros2_governance_access_control_claim")
        ),
        "sros2_governance_repeated_access_control_claim": bool(
            sros2_permissions.get(
                "sros2_governance_repeated_access_control_claim"
            )
        ),
        "sros2_governance_runtime_signature_validation_claim": bool(
            sros2_permissions.get(
                "sros2_governance_runtime_signature_validation_claim"
            )
        ),
        "sros2_governance_transport_protection_fail_closed_claim": bool(
            sros2_permissions.get(
                "sros2_governance_transport_protection_fail_closed_claim"
            )
        ),
        "sros2_tampered_signed_governance_fail_closed_claim": bool(
            sros2_permissions.get(
                "sros2_tampered_signed_governance_fail_closed_claim"
            )
        ),
        "sros2_local_identity_credentials_validation_claim": bool(
            sros2_permissions.get(
                "sros2_local_identity_credentials_validation_claim"
            )
        ),
        "sros2_local_identity_credentials_repeated_validation_claim": bool(
            sros2_permissions.get(
                "sros2_local_identity_credentials_repeated_validation_claim"
            )
        ),
        "sros2_tampered_identity_certificate_fail_closed_claim": bool(
            sros2_permissions.get(
                "sros2_tampered_identity_certificate_fail_closed_claim"
            )
        ),
        "sros2_identity_private_key_mismatch_fail_closed_claim": bool(
            sros2_permissions.get(
                "sros2_identity_private_key_mismatch_fail_closed_claim"
            )
        ),
        "sros2_identity_enclave_mismatch_fail_closed_claim": bool(
            sros2_permissions.get(
                "sros2_identity_enclave_mismatch_fail_closed_claim"
            )
        ),
        "sros2_peer_identity_authentication_claim": bool(
            udp_peer_auth.get("sros2_peer_identity_authentication_claim")
        ),
        "sros2_peer_identity_repeated_authentication_claim": bool(
            udp_peer_auth.get("sros2_peer_identity_repeated_authentication_claim")
        ),
        "udp_peer_identity_allowlist_fail_closed_claim": bool(
            udp_peer_auth.get("udp_peer_identity_allowlist_fail_closed_claim")
        ),
        "udp_peer_signature_tamper_fail_closed_claim": bool(
            udp_peer_auth.get("udp_peer_signature_tamper_fail_closed_claim")
        ),
        "udp_peer_untrusted_certificate_fail_closed_claim": bool(
            udp_peer_auth.get("udp_peer_untrusted_certificate_fail_closed_claim")
        ),
        "udp_certificate_authenticated_aead_claim": bool(
            udp_peer_auth.get("udp_certificate_authenticated_aead_claim")
        ),
        "udp_authenticated_psk_session_key_derivation_claim": bool(
            udp_aead.get("udp_authenticated_psk_session_key_derivation_claim")
        ),
        "udp_session_key_rotation_claim": bool(
            udp_aead.get("udp_session_key_rotation_claim")
        ),
        "session_key_establishment_claim": bool(
            udp_aead.get("session_key_establishment_claim")
        ),
        "forward_secrecy_claim": False,
        "asymmetric_session_key_exchange_claim": False,
        "dynamic_serialization_support_claim": bool(
            dynamic_message.get("dynamic_serialization_support_claim")
        ),
        "dynamic_serialization_support_repeated_claim": bool(
            dynamic_message.get("dynamic_serialization_support_repeated_claim")
        ),
        "dynamic_message_take_claim": bool(
            dynamic_message.get("dynamic_message_take_claim")
        ),
        "dynamic_message_take_with_info_claim": bool(
            dynamic_message.get("dynamic_message_take_with_info_claim")
        ),
        "message_info_sequence_features_claim": bool(
            dynamic_message.get("message_info_sequence_features_claim")
        ),
        "certificate_revocation_claim": bool(
            udp_peer_auth.get("certificate_revocation_claim")
        ),
        "udp_aead_authenticated_encryption_claim": bool(
            udp_aead.get("udp_aead_authenticated_encryption_claim")
        ),
        "udp_aead_repeated_authenticated_encryption_claim": bool(
            udp_aead.get("udp_aead_repeated_authenticated_encryption_claim")
        ),
        "udp_aead_tamper_fail_closed_claim": bool(
            udp_aead.get("udp_aead_tamper_fail_closed_claim")
        ),
        "udp_aead_strict_missing_key_fail_closed_claim": bool(
            udp_aead.get("udp_aead_strict_missing_key_fail_closed_claim")
        ),
        "dds_security_interoperability_claim": False,
        "governance_transport_security_claim": False,
        "sros2_policy_enforcement_claim": False,
        "production_security_hardening_claim": False,
        "quic_soak_run_count": as_int(quic.get("run_count")),
        "quic_soak_ok_run_count": as_int(quic.get("ok_run_count")),
        "quic_soak_total_frames_sent": as_int(quic.get("total_quic_gateway_frames_sent")),
        "quic_soak_total_frames_failed": as_int(quic.get("total_quic_gateway_frames_failed")),
        "quic_soak_total_frames_dropped": as_int(quic.get("total_quic_gateway_frames_dropped")),
        "quic_soak_total_bytes_sent": as_int(quic.get("total_quic_gateway_bytes_sent")),
        "quic_soak_qlog_total_bytes": as_int(quic.get("qlog_total_bytes")),
        "production_quic_backend": False,
        "full_bidirectional_quic_backend": False,
        "components": components,
        "rows": [
            {
                key: value
                for key, value in row.items()
                if key != "summary"
            }
            for row in components
        ],
    }


def run_quic_soak_component(
    *,
    root: Path,
    image: str,
    iterations: int,
    base_port: int,
    netem: bool,
    delay_ms: int,
    jitter_ms: int,
    loss_percent: float,
) -> dict[str, Any]:
    rows: list[dict[str, Any]] = []
    for index in range(max(iterations, 1)):
        port = base_port + index
        if netem:
            row = run_quic_netem_probe(
                root=root,
                image=image,
                port=port,
                delay_ms=max(delay_ms, 0),
                jitter_ms=max(jitter_ms, 0),
                loss_percent=max(loss_percent, 0.0),
                async_gateway=True,
                schema_version="fleetrmw.docker_quic_gateway_netem_async_burst_probe.v1",
                probe_executable="fleetrmw_quic_gateway_burst_publish_probe",
            )
        else:
            row = run_quic_publish_probe(
                root=root,
                image=image,
                port=port,
                async_gateway=True,
                schema_version="fleetrmw.docker_quic_gateway_async_burst_probe.v1",
                probe_executable="fleetrmw_quic_gateway_burst_publish_probe",
            )
        row["iteration"] = index
        rows.append(row)
    return aggregate_quic_gateway_soak(rows, netem=netem)


def run_campaign(
    *,
    root: Path,
    image: str,
    profile: str,
    components: list[str],
    abi_iterations: int,
    security_iterations: int,
    quic_iterations: int,
    base_port: int,
    quic_netem: bool,
    delay_ms: int,
    jitter_ms: int,
    loss_percent: float,
    long_min_runtime_s: float,
) -> dict[str, Any]:
    started = time.monotonic()
    rows: list[dict[str, Any]] = []
    round_count = 0
    while True:
        for component in components:
            if component == "security_options":
                summary = run_security_options_probe(
                    root=root,
                    image=image,
                    iterations=security_iterations,
                )
            elif component == "security_policy":
                summary = run_security_policy_probe(
                    root=root,
                    image=image,
                    policy=DEFAULT_SECURITY_POLICY,
                    iterations=security_iterations,
                )
            elif component == "sros2_permissions":
                summary = run_sros2_permissions_probe(
                    root=root,
                    image=image,
                    iterations=security_iterations,
                )
            elif component == "udp_aead":
                summary = run_udp_aead_probe(
                    root=root,
                    image=image,
                    iterations=security_iterations,
                )
            elif component == "udp_peer_auth":
                summary = run_udp_peer_auth_probe(
                    root=root,
                    image=image,
                    iterations=security_iterations,
                )
            elif component == "dynamic_message":
                summary = run_dynamic_message_probe(
                    root=root,
                    image=image,
                    iterations=abi_iterations,
                )
            elif component == "allocation":
                summary = run_allocation_probe(
                    root=root, image=image, iterations=abi_iterations
                )
            elif component == "qos_event":
                summary = run_qos_event_probe(
                    root=root, image=image, iterations=abi_iterations
                )
            elif component == "content_filter":
                summary = run_content_filter_probe(
                    root=root, image=image, iterations=abi_iterations
                )
            elif component == "quic_gateway_async_burst_soak":
                summary = run_quic_soak_component(
                    root=root,
                    image=image,
                    iterations=quic_iterations,
                    base_port=base_port + round_count * quic_iterations,
                    netem=quic_netem,
                    delay_ms=delay_ms,
                    jitter_ms=jitter_ms,
                    loss_percent=loss_percent,
                )
            else:
                summary = {
                    "schema_version": SCHEMA_VERSION,
                    "status": "failed",
                    "reason": f"unknown_component:{component}",
                }
            row = component_row(component, summary)
            row["campaign_round"] = round_count + 1
            rows.append(row)
        round_count += 1
        elapsed_s = time.monotonic() - started
        round_ok = all(
            row.get("stress_component_ok") is True
            for row in rows[-len(components) :]
        ) if components else False
        if profile != "long" or not round_ok or elapsed_s >= long_min_runtime_s:
            break
    elapsed_s = time.monotonic() - started
    summary = aggregate_campaign(
        rows,
        profile=profile,
        elapsed_s=elapsed_s,
        long_min_runtime_s=long_min_runtime_s,
        quic_netem=quic_netem,
    )
    summary["campaign_round_count"] = round_count
    summary["active_soak_until_runtime_threshold"] = profile == "long"
    return summary


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--image", default=DEFAULT_IMAGE)
    parser.add_argument("--profile", choices=sorted(PROFILE_DEFAULTS), default="smoke")
    parser.add_argument(
        "--component",
        action="append",
        choices=ALL_COMPONENTS,
        help="component to run; may be repeated; defaults to the full smoke set",
    )
    parser.add_argument("--abi-iterations", type=int)
    parser.add_argument("--security-iterations", type=int)
    parser.add_argument("--quic-iterations", type=int)
    parser.add_argument("--base-port", type=int, default=4890)
    parser.add_argument("--quic-netem", action="store_true")
    parser.add_argument("--delay-ms", type=int, default=20)
    parser.add_argument("--jitter-ms", type=int, default=5)
    parser.add_argument("--loss-percent", type=float, default=0.0)
    parser.add_argument("--long-min-runtime-s", type=float)
    parser.add_argument(
        "--summary-json",
        default="results_rmw_socket/docker_stress_security_campaign_summary.json",
    )
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    defaults = PROFILE_DEFAULTS[args.profile]
    selected_components = args.component or list(ALL_COMPONENTS)
    summary = run_campaign(
        root=ROOT,
        image=args.image,
        profile=args.profile,
        components=selected_components,
        abi_iterations=max(args.abi_iterations or defaults["abi_iterations"], 1),
        security_iterations=max(
            args.security_iterations or defaults["security_iterations"],
            1,
        ),
        quic_iterations=max(args.quic_iterations or defaults["quic_iterations"], 1),
        base_port=args.base_port,
        quic_netem=args.quic_netem,
        delay_ms=args.delay_ms,
        jitter_ms=args.jitter_ms,
        loss_percent=args.loss_percent,
        long_min_runtime_s=float(
            args.long_min_runtime_s
            if args.long_min_runtime_s is not None
            else defaults["long_min_runtime_s"]
        ),
    )
    output = ROOT / args.summary_json
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    if args.json:
        print(json.dumps(summary, sort_keys=True))
    else:
        print(
            f"status={summary['status']} profile={summary['campaign_profile']} "
            f"components={summary['ok_component_count']}/{summary['component_count']} "
            f"runs={summary['total_component_ok_runs']}/{summary['total_component_runs']} "
            f"long={summary['long_stress_security_campaign_claim']}"
        )
    return 0 if summary["status"] == "ok" else 1


if __name__ == "__main__":
    raise SystemExit(main())

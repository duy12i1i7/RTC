"""Pinned fail-closed adapter for aioquic server-side mutual TLS.

aioquic 0.9.25 and current upstream 1.3.0 expose CertificateRequest handling
only through private TLS state. Keep that dependency isolated, fingerprinted,
and exact-version gated until aioquic provides a public server client-auth API.
"""

from __future__ import annotations

import inspect
from typing import Any, Callable


SUPPORTED_AIOQUIC_VERSION = "0.9.25"
ADAPTER_MODE = "pinned_aioquic_0_9_25_private_server_client_auth"
PRIVATE_HOOK_FINGERPRINT = (
    "QuicConnection._initialize(self,peer_cid)|"
    "Context._server_handle_certificate(self,input_buf,output_buf)|"
    "Context._server_handle_certificate_verify(self,input_buf,output_buf)"
)


def _parameter_names(callable_object: Any) -> tuple[str, ...]:
    return tuple(inspect.signature(callable_object).parameters)


def aioquic_mtls_compatibility_report() -> dict[str, Any]:
    import aioquic
    from aioquic.quic.connection import QuicConnection
    from aioquic.tls import Context

    checks = {
        "quic_initialize_signature": _parameter_names(QuicConnection._initialize)
        == ("self", "peer_cid"),
        "server_certificate_handler_signature": _parameter_names(
            Context._server_handle_certificate
        )
        == ("self", "input_buf", "output_buf"),
        "server_certificate_verify_handler_signature": _parameter_names(
            Context._server_handle_certificate_verify
        )
        == ("self", "input_buf", "output_buf"),
    }
    version = str(getattr(aioquic, "__version__", "unknown"))
    return {
        "adapter_mode": ADAPTER_MODE,
        "runtime_version": version,
        "supported_version": SUPPORTED_AIOQUIC_VERSION,
        "exact_version_match": version == SUPPORTED_AIOQUIC_VERSION,
        "private_hook_fingerprint": PRIVATE_HOOK_FINGERPRINT,
        "structural_checks": checks,
        "compatible": version == SUPPORTED_AIOQUIC_VERSION and all(checks.values()),
        "public_server_client_auth_api": False,
        "production_supported": False,
    }


def require_aioquic_mtls_compatibility() -> dict[str, Any]:
    report = aioquic_mtls_compatibility_report()
    if not report["compatible"]:
        raise RuntimeError(
            "unsupported aioquic mutual-TLS runtime; exact 0.9.25 private-hook "
            f"fingerprint required, observed {report!r}"
        )
    return report


def install_aioquic_mtls_adapter(
    quic_connection: Any,
    *,
    client_ca: str,
    revoked_client_serials: frozenset[int],
    on_missing_certificate: Callable[[], None],
    on_untrusted_certificate: Callable[[], None],
    on_revoked_certificate: Callable[[], None],
    on_authenticated_certificate: Callable[[Any], None],
) -> dict[str, Any]:
    """Install the exact-version adapter before the first QUIC Initial packet."""

    from aioquic.tls import Alert, AlertBadCertificate, verify_certificate

    report = require_aioquic_mtls_compatibility()
    original_initialize = getattr(quic_connection, "_initialize", None)
    if original_initialize is None or _parameter_names(original_initialize) != (
        "peer_cid",
    ):
        raise RuntimeError(
            "aioquic connection lacks the pinned bound TLS initializer signature"
        )

    def initialize_with_client_auth(peer_cid: bytes) -> None:
        original_initialize(peer_cid)
        tls_context = getattr(quic_connection, "tls", None)
        if tls_context is None:
            raise RuntimeError("aioquic TLS context was not initialized")
        original_handle_certificate = getattr(
            tls_context, "_server_handle_certificate", None
        )
        original_handle_verify = getattr(
            tls_context, "_server_handle_certificate_verify", None
        )
        if (
            original_handle_certificate is None
            or _parameter_names(original_handle_certificate)
            != ("input_buf", "output_buf")
            or original_handle_verify is None
            or _parameter_names(original_handle_verify)
            != ("input_buf", "output_buf")
            or not hasattr(tls_context, "_request_client_certificate")
        ):
            raise RuntimeError(
                "aioquic TLS context does not match the pinned client-auth hooks"
            )
        tls_context._request_client_certificate = True

        def handle_certificate(input_buf: Any, output_buf: Any) -> None:
            original_handle_certificate(input_buf, output_buf)
            if getattr(tls_context, "_peer_certificate", None) is None:
                on_missing_certificate()
                raise AlertBadCertificate("client certificate is required")

        def handle_certificate_verify(input_buf: Any, output_buf: Any) -> None:
            # First require proof that the peer holds the certificate private key.
            original_handle_verify(input_buf, output_buf)
            try:
                verify_certificate(
                    certificate=tls_context._peer_certificate,
                    chain=tls_context._peer_certificate_chain,
                    cafile=client_ca,
                )
            except Alert:
                on_untrusted_certificate()
                raise
            certificate = tls_context._peer_certificate
            if certificate.serial_number in revoked_client_serials:
                on_revoked_certificate()
                raise AlertBadCertificate("client certificate is revoked")
            on_authenticated_certificate(certificate)

        tls_context._server_handle_certificate = handle_certificate
        tls_context._server_handle_certificate_verify = handle_certificate_verify

    quic_connection._initialize = initialize_with_client_auth
    return report

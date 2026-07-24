"""Exact-version adapter for native QUIC path observations.

aioquic does not expose recovery RTT and packet-loss counters through a stable
public API.  Keep the private dependency isolated and fail closed on any
runtime or signature drift, just like the server-side mutual-TLS adapter.
"""

from __future__ import annotations

import inspect
import math
from typing import Any, Callable


SUPPORTED_AIOQUIC_VERSION = "0.9.25"
ADAPTER_MODE = "pinned_aioquic_0_9_25_private_recovery_observer"
PRIVATE_HOOK_FINGERPRINT = (
    "QuicPacketRecovery.on_packet_sent(self,*,packet,space)|"
    "QuicPacketRecovery._on_packets_lost(self,*,now,packets,space)|"
    "QuicConnection._loss"
)


def _parameter_names(callable_object: Any) -> tuple[str, ...]:
    return tuple(inspect.signature(callable_object).parameters)


def aioquic_path_observer_compatibility_report() -> dict[str, Any]:
    import aioquic
    from aioquic.quic.recovery import QuicPacketRecovery

    checks = {
        "packet_sent_signature": _parameter_names(
            QuicPacketRecovery.on_packet_sent
        )
        == ("self", "packet", "space"),
        "packets_lost_signature": _parameter_names(
            QuicPacketRecovery._on_packets_lost
        )
        == ("self", "now", "packets", "space"),
        "rtt_state_declared": all(
            name in inspect.getsource(QuicPacketRecovery.__init__)
            for name in (
                "_rtt_initialized",
                "_rtt_smoothed",
                "_rtt_variance",
            )
        ),
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
        "public_path_metrics_api": False,
        "production_supported": False,
    }


def require_aioquic_path_observer_compatibility() -> dict[str, Any]:
    report = aioquic_path_observer_compatibility_report()
    if not report["compatible"]:
        raise RuntimeError(
            "unsupported aioquic path-observer runtime; exact 0.9.25 "
            f"private-hook fingerprint required, observed {report!r}"
        )
    return report


class AioquicPathObserver:
    """Per-connection counters and recovery estimates from pinned aioquic."""

    def __init__(self, recovery: Any) -> None:
        self._recovery = recovery
        self._original_on_packet_sent: Callable[..., Any] = recovery.on_packet_sent
        self._original_on_packets_lost: Callable[..., Any] = (
            recovery._on_packets_lost
        )
        self._packets_sent = 0
        self._packets_lost = 0
        self._closed = False

        def on_packet_sent(*, packet: Any, space: Any) -> Any:
            if bool(getattr(packet, "in_flight", False)):
                self._packets_sent += 1
            return self._original_on_packet_sent(packet=packet, space=space)

        def on_packets_lost(*, now: float, packets: Any, space: Any) -> Any:
            packet_tuple = tuple(packets)
            self._packets_lost += sum(
                bool(getattr(packet, "in_flight", False)) for packet in packet_tuple
            )
            return self._original_on_packets_lost(
                now=now, packets=packet_tuple, space=space
            )

        recovery.on_packet_sent = on_packet_sent
        recovery._on_packets_lost = on_packets_lost

    def snapshot(self) -> dict[str, Any]:
        initialized = bool(getattr(self._recovery, "_rtt_initialized", False))
        smoothed_rtt = float(getattr(self._recovery, "_rtt_smoothed", 0.0))
        rtt_variance = float(getattr(self._recovery, "_rtt_variance", 0.0))
        values_finite = math.isfinite(smoothed_rtt) and math.isfinite(rtt_variance)
        initialized = initialized and values_finite and smoothed_rtt > 0.0
        return {
            "schema_version": "fleetrmw.aioquic_path_observation.v1",
            "source": "quic_session_native",
            "rtt_initialized": initialized,
            "measured_rtt_ms": max(0.0, smoothed_rtt * 1000.0),
            # aioquic's recovery estimator is an RTT-variation proxy, not an
            # application inter-arrival jitter measurement.
            "measured_jitter_ms": max(0.0, rtt_variance * 1000.0),
            "jitter_measurement_kind": "quic_recovery_rtt_variance_proxy",
            "packets_sent": self._packets_sent,
            "packets_lost": self._packets_lost,
            "measured_loss": (
                min(1.0, self._packets_lost / self._packets_sent)
                if self._packets_sent > 0
                else 0.0
            ),
            "private_runtime_adapter": True,
            "production_supported": False,
        }

    def close(self) -> None:
        if self._closed:
            return
        self._recovery.on_packet_sent = self._original_on_packet_sent
        self._recovery._on_packets_lost = self._original_on_packets_lost
        self._closed = True


def install_aioquic_path_observer(quic_connection: Any) -> AioquicPathObserver:
    """Install a per-connection observer before packet processing starts."""

    require_aioquic_path_observer_compatibility()
    recovery = getattr(quic_connection, "_loss", None)
    if recovery is None:
        raise RuntimeError("aioquic connection lacks the pinned _loss recovery state")
    if (
        _parameter_names(recovery.on_packet_sent) != ("packet", "space")
        or _parameter_names(recovery._on_packets_lost)
        != ("now", "packets", "space")
        or not all(
            hasattr(recovery, name)
            for name in ("_rtt_initialized", "_rtt_smoothed", "_rtt_variance")
        )
    ):
        raise RuntimeError("aioquic recovery instance does not match the pinned hooks")
    return AioquicPathObserver(recovery)

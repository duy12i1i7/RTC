import sys
from types import ModuleType, SimpleNamespace
import unittest
from unittest.mock import patch

from fleetqox.aioquic_path_observer import (
    aioquic_path_observer_compatibility_report,
    install_aioquic_path_observer,
    require_aioquic_path_observer_compatibility,
)


class FakeRecovery:
    def __init__(self) -> None:
        self._rtt_initialized = True
        self._rtt_smoothed = 0.080
        self._rtt_variance = 0.012
        self.sent_calls = 0
        self.lost_calls = 0

    def on_packet_sent(self, *, packet, space):
        self.sent_calls += 1

    def _on_packets_lost(self, *, now, packets, space):
        self.lost_calls += len(tuple(packets))


def fake_aioquic_modules(version: str) -> dict[str, ModuleType]:
    aioquic = ModuleType("aioquic")
    aioquic.__version__ = version
    quic = ModuleType("aioquic.quic")
    recovery = ModuleType("aioquic.quic.recovery")
    recovery.QuicPacketRecovery = FakeRecovery
    return {
        "aioquic": aioquic,
        "aioquic.quic": quic,
        "aioquic.quic.recovery": recovery,
    }


class AioquicPathObserverTest(unittest.TestCase):
    def test_exact_supported_version_and_fingerprint_pass(self) -> None:
        with patch.dict(sys.modules, fake_aioquic_modules("0.9.25")):
            report = require_aioquic_path_observer_compatibility()
        self.assertTrue(report["compatible"])
        self.assertTrue(report["exact_version_match"])
        self.assertFalse(report["public_path_metrics_api"])
        self.assertFalse(report["production_supported"])

    def test_future_version_fails_closed(self) -> None:
        with patch.dict(sys.modules, fake_aioquic_modules("1.3.0")):
            report = aioquic_path_observer_compatibility_report()
            self.assertFalse(report["compatible"])
            with self.assertRaisesRegex(RuntimeError, "exact 0.9.25"):
                require_aioquic_path_observer_compatibility()

    def test_observer_counts_packets_and_exposes_recovery_estimates(self) -> None:
        connection = SimpleNamespace(_loss=FakeRecovery())
        with patch.dict(sys.modules, fake_aioquic_modules("0.9.25")):
            observer = install_aioquic_path_observer(connection)
            in_flight = SimpleNamespace(in_flight=True)
            not_in_flight = SimpleNamespace(in_flight=False)
            connection._loss.on_packet_sent(packet=in_flight, space=object())
            connection._loss.on_packet_sent(packet=not_in_flight, space=object())
            connection._loss._on_packets_lost(
                now=1.0,
                packets=(in_flight, not_in_flight),
                space=object(),
            )
            snapshot = observer.snapshot()
            self.assertEqual(snapshot["packets_sent"], 1)
            self.assertEqual(snapshot["packets_lost"], 1)
            self.assertEqual(snapshot["measured_loss"], 1.0)
            self.assertEqual(snapshot["measured_rtt_ms"], 80.0)
            self.assertEqual(snapshot["measured_jitter_ms"], 12.0)
            self.assertEqual(
                snapshot["jitter_measurement_kind"],
                "quic_recovery_rtt_variance_proxy",
            )
            self.assertTrue(snapshot["rtt_initialized"])
            observer.close()
            connection._loss.on_packet_sent(packet=in_flight, space=object())
            self.assertEqual(connection._loss.sent_calls, 3)


if __name__ == "__main__":
    unittest.main()

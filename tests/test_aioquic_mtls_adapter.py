from pathlib import Path
import sys
from types import ModuleType
import unittest
from unittest.mock import patch

from fleetqox.aioquic_mtls_adapter import (
    aioquic_mtls_compatibility_report,
    require_aioquic_mtls_compatibility,
)


ROOT = Path(__file__).resolve().parents[1]


def fake_aioquic_modules(version: str) -> dict[str, ModuleType]:
    aioquic = ModuleType("aioquic")
    aioquic.__version__ = version
    quic = ModuleType("aioquic.quic")
    connection = ModuleType("aioquic.quic.connection")
    tls = ModuleType("aioquic.tls")

    class QuicConnection:
        def _initialize(self, peer_cid):
            pass

    class Context:
        def _server_handle_certificate(self, input_buf, output_buf):
            pass

        def _server_handle_certificate_verify(self, input_buf, output_buf):
            pass

    connection.QuicConnection = QuicConnection
    tls.Context = Context
    return {
        "aioquic": aioquic,
        "aioquic.quic": quic,
        "aioquic.quic.connection": connection,
        "aioquic.tls": tls,
    }


class AioquicMutualTlsAdapterTest(unittest.TestCase):
    def test_exact_supported_version_and_fingerprint_pass(self) -> None:
        with patch.dict(sys.modules, fake_aioquic_modules("0.9.25")):
            report = require_aioquic_mtls_compatibility()
        self.assertTrue(report["compatible"])
        self.assertTrue(report["exact_version_match"])
        self.assertFalse(report["public_server_client_auth_api"])
        self.assertFalse(report["production_supported"])

    def test_future_version_fails_closed_even_with_same_private_signatures(self) -> None:
        with patch.dict(sys.modules, fake_aioquic_modules("1.3.0")):
            report = aioquic_mtls_compatibility_report()
            self.assertFalse(report["compatible"])
            self.assertFalse(report["exact_version_match"])
            with self.assertRaisesRegex(RuntimeError, "exact 0.9.25"):
                require_aioquic_mtls_compatibility()

    def test_dockerfile_pins_the_debian_aioquic_package(self) -> None:
        dockerfile = (ROOT / "external" / "rmw-netem" / "Dockerfile").read_text()
        self.assertIn("AIOQUIC_DEB_VERSION=0.9.25-3build2", dockerfile)
        self.assertIn("python3-aioquic=${AIOQUIC_DEB_VERSION}", dockerfile)


if __name__ == "__main__":
    unittest.main()

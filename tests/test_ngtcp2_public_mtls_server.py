from __future__ import annotations

import json
from pathlib import Path
import subprocess
import unittest

from scripts.run_rmw_docker_ngtcp2_public_mtls_server_probe import (
    ROOT,
    SCHEMA_VERSION,
    negative_client_was_rejected,
)


class Ngtcp2PublicMutualTlsServerTest(unittest.TestCase):
    def test_public_api_server_sources_are_pinned_and_auditable(self) -> None:
        dockerfile = (
            ROOT / "external/ngtcp2-public-mtls/Dockerfile"
        ).read_text(encoding="utf-8")
        patch = (
            ROOT / "external/ngtcp2-public-mtls/public-mtls.patch"
        ).read_text(encoding="utf-8")
        self.assertIn("a4ba3f20d70d4a4d79674cee1093c55b4c1d78ed", dockerfile)
        self.assertIn("gnutls_certificate_set_x509_trust_file", patch)
        self.assertIn("gnutls_certificate_set_x509_crl_file", patch)
        self.assertIn("gnutls_certificate_verify_peers3", patch)
        self.assertIn("gnutls_x509_crt_check_key_purpose", patch)
        self.assertIn("GNUTLS_SAN_URI", patch)
        self.assertIn("gnutls_record_set_max_early_data_size(session_, 0)", patch)
        self.assertNotIn("aioquic", patch.lower())

    def test_runner_preserves_stateful_production_boundary(self) -> None:
        runner = (
            ROOT / "scripts/run_rmw_docker_ngtcp2_public_mtls_server_probe.py"
        ).read_text(encoding="utf-8")
        self.assertIn(SCHEMA_VERSION, runner)
        self.assertIn('"stateful_gateway_backend_integrated": False', runner)
        self.assertIn('"production_quic_backend_claim": False', runner)
        self.assertIn('"single_connection_six_h3_streams_claim": ok', runner)

    def test_protocol_rejection_does_not_depend_on_example_exit_code(self) -> None:
        rejected = subprocess.CompletedProcess(
            [],
            0,
            "",
            "CONNECTION_CLOSE error_code=CRYPTO_ERROR(0x12a)",
        )
        successful = subprocess.CompletedProcess(
            [],
            0,
            "",
            "response headers started\n[:status: 200]\nCONNECTION_CLOSE",
        )
        self.assertTrue(negative_client_was_rejected(rejected))
        self.assertFalse(negative_client_was_rejected(successful))
        self.assertFalse(negative_client_was_rejected(None))

    def test_canonical_artifact_passes_five_runs(self) -> None:
        artifact = (
            ROOT
            / "results_rmw_socket/docker_ngtcp2_public_mtls_server_summary.json"
        )
        if not artifact.exists():
            self.skipTest("canonical public mTLS artifact has not been generated")
        summary = json.loads(artifact.read_text(encoding="utf-8"))
        self.assertEqual(summary["schema_version"], SCHEMA_VERSION)
        self.assertEqual(summary["status"], "ok")
        self.assertEqual(summary["run_count"], 5)
        self.assertEqual(summary["ok_run_count"], 5)
        self.assertTrue(summary["public_api_mtls_server_claim"])
        self.assertTrue(summary["public_api_crl_revocation_claim"])
        self.assertTrue(summary["public_api_uri_san_binding_claim"])
        self.assertFalse(summary["aioquic_private_server_hook_required"])
        self.assertFalse(summary["production_quic_backend_claim"])


if __name__ == "__main__":
    unittest.main()

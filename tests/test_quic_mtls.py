import copy
import json
from pathlib import Path
import unittest

from scripts.run_rmw_docker_quic_mtls_probe import client_ok, service_ok


ROOT = Path(__file__).resolve().parents[1]
ARTIFACT = ROOT / "results_rmw_socket" / "docker_quic_mtls_probe_summary.json"


class QuicMutualTlsTest(unittest.TestCase):
    def test_validators_reject_unauthenticated_state_mutation(self) -> None:
        summary = json.loads(ARTIFACT.read_text(encoding="utf-8"))
        run = summary["runs"][0]
        self.assertTrue(
            client_ok(
                run["valid_client"],
                expect_success=True,
                certificate_configured=True,
            )
        )
        self.assertTrue(
            client_ok(
                run["missing_certificate_client"],
                expect_success=False,
                certificate_configured=False,
            )
        )
        self.assertTrue(
            client_ok(
                run["untrusted_certificate_client"],
                expect_success=False,
                certificate_configured=True,
            )
        )
        self.assertTrue(
            client_ok(
                run["trusted_impersonator_client"],
                expect_success=False,
                certificate_configured=True,
                expect_authorization_failure=True,
            )
        )
        self.assertTrue(
            client_ok(
                run["revoked_certificate_client"],
                expect_success=False,
                certificate_configured=True,
            )
        )
        self.assertTrue(service_ok(run["service"]))

        unauthorized_request = copy.deepcopy(run["service"])
        unauthorized_request["metrics"]["requests_total"] = 2
        unauthorized_request["metrics"]["post_requests"] = 2
        self.assertFalse(service_ok(unauthorized_request))

    def test_canonical_docker_netem_artifact_passes_five_runs(self) -> None:
        self.assertTrue(ARTIFACT.is_file())
        summary = json.loads(ARTIFACT.read_text(encoding="utf-8"))
        self.assertEqual(summary["status"], "ok")
        self.assertEqual(summary["run_count"], 5)
        self.assertEqual(summary["successful_runs"], 5)
        self.assertEqual(summary["container_count_per_run"], 6)
        self.assertTrue(summary["real_quic_v1_h3"])
        self.assertTrue(summary["server_certificate_verification_required"])
        self.assertTrue(summary["client_certificate_verification_required"])
        self.assertTrue(summary["valid_client_certificate_accepted_claim"])
        self.assertTrue(summary["missing_client_certificate_fail_closed_claim"])
        self.assertTrue(summary["untrusted_client_certificate_fail_closed_claim"])
        self.assertTrue(summary["mutual_tls_client_authentication_claim"])
        self.assertTrue(summary["client_certificate_publisher_identity_binding_claim"])
        self.assertTrue(
            summary["client_certificate_uri_san_publisher_identity_binding_claim"]
        )
        self.assertTrue(
            summary["trusted_certificate_publisher_impersonation_fail_closed_claim"]
        )
        self.assertTrue(summary["unauthorized_identity_state_isolation_claim"])
        self.assertTrue(summary["revoked_client_certificate_fail_closed_claim"])
        self.assertTrue(summary["aioquic_exact_version_pin_claim"])
        self.assertTrue(summary["aioquic_private_hook_fingerprint_claim"])
        self.assertTrue(summary["aioquic_private_adapter_fail_closed_claim"])
        self.assertFalse(summary["aioquic_public_server_client_auth_api_claim"])
        self.assertFalse(summary["production_quic_backend_claim"])
        self.assertFalse(summary["production_readiness"])
        for run in summary["runs"]:
            self.assertEqual(run["status"], "ok")
            self.assertTrue(run["netem_configured_all_containers"])
            self.assertGreaterEqual(run["service_qlog_file_count"], 1)
            self.assertGreaterEqual(run["valid_qlog_file_count"], 1)
            self.assertGreaterEqual(run["missing_qlog_file_count"], 1)
            self.assertGreaterEqual(run["untrusted_qlog_file_count"], 1)
            self.assertGreaterEqual(run["impersonator_qlog_file_count"], 1)
            self.assertGreaterEqual(run["revoked_qlog_file_count"], 1)
            self.assertGreater(run["qlog_total_bytes"], 0)
            self.assertTrue(service_ok(run["service"]))

    def test_client_credentials_and_server_auth_are_wired(self) -> None:
        service = (ROOT / "scripts" / "fleetrmw_quic_gateway_service.py").read_text()
        transport = (
            ROOT
            / "ros2_ws"
            / "src"
            / "rmw_fleetqox_cpp"
            / "src"
            / "quic_gateway_transport.cpp"
        ).read_text()
        client = (
            ROOT
            / "ros2_ws"
            / "src"
            / "rmw_fleetqox_cpp"
            / "src"
            / "inprocess_quic_client.cpp"
        ).read_text()
        cmake = (
            ROOT / "ros2_ws" / "src" / "rmw_fleetqox_cpp" / "CMakeLists.txt"
        ).read_text()
        adapter = (ROOT / "fleetqox" / "aioquic_mtls_adapter.py").read_text()
        dockerfile = (ROOT / "external" / "rmw-netem" / "Dockerfile").read_text()
        self.assertIn("install_aioquic_mtls_adapter", service)
        self.assertIn("SUPPORTED_AIOQUIC_VERSION = \"0.9.25\"", adapter)
        self.assertIn("_request_client_certificate = True", adapter)
        self.assertIn("verify_certificate(", adapter)
        self.assertIn("original_handle_verify(input_buf, output_buf)", adapter)
        self.assertIn("python3-aioquic=${AIOQUIC_DEB_VERSION}", dockerfile)
        self.assertIn("not self.client_authenticated", service)
        self.assertIn("publisher_identity_mismatch", service)
        self.assertIn("--publisher-identity-uri-prefix", service)
        self.assertIn("x509.UniformResourceIdentifier", service)
        self.assertIn("load_revoked_client_serials", service)
        self.assertIn("client certificate is revoked", adapter)
        self.assertIn("FLEETQOX_RMW_QUIC_CLIENT_CERT_FILE", transport)
        self.assertIn("FLEETQOX_RMW_QUIC_CLIENT_KEY_FILE", transport)
        self.assertIn("gnutls_certificate_set_x509_key_file", client)
        self.assertIn("fleetrmw_quic_mtls_probe", cmake)


if __name__ == "__main__":
    unittest.main()

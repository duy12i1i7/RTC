import copy
import json
from pathlib import Path
import unittest

from scripts.run_rmw_docker_quic_stateful_gateway_probe import probe_ok, service_ok
from scripts.run_rmw_docker_quic_stateful_rmw_probe import (
    endpoint_ok,
    service_ok as rmw_service_ok,
)


ROOT = Path(__file__).resolve().parents[1]
ARTIFACT = (
    ROOT
    / "results_rmw_socket"
    / "docker_quic_stateful_gateway_probe_summary.json"
)
RMW_ARTIFACT = (
    ROOT / "results_rmw_socket" / "docker_quic_stateful_rmw_probe_summary.json"
)


class QuicStatefulGatewayTest(unittest.TestCase):
    def test_validators_require_exact_replay_and_transport_sessions(self) -> None:
        summary = json.loads(ARTIFACT.read_text(encoding="utf-8"))
        run = summary["runs"][0]
        self.assertTrue(probe_ok(run["probe"]))
        self.assertTrue(service_ok(run["service"]))

        partial_probe = copy.deepcopy(run["probe"])
        partial_probe["beta_received_count"] = 2
        self.assertFalse(probe_ok(partial_probe))

        partial_service = copy.deepcopy(run["service"])
        partial_service["transport_metrics"]["h3_sessions_negotiated"] = 2
        self.assertFalse(service_ok(partial_service))

    def test_canonical_docker_netem_artifact_passes_five_runs(self) -> None:
        self.assertTrue(ARTIFACT.is_file())
        summary = json.loads(ARTIFACT.read_text(encoding="utf-8"))
        self.assertEqual(summary["status"], "ok")
        self.assertEqual(summary["run_count"], 5)
        self.assertEqual(summary["successful_runs"], 5)
        self.assertTrue(summary["real_quic_v1_h3"])
        self.assertTrue(summary["tls_peer_verification_required"])
        self.assertTrue(summary["stateful_fleetqox_quic_gateway_service_claim"])
        self.assertTrue(summary["bounded_topic_history_claim"])
        self.assertTrue(summary["publisher_sequence_deduplication_claim"])
        self.assertTrue(summary["independent_consumer_cursor_replay_claim"])
        self.assertTrue(summary["invalid_frame_http_status_fail_closed_claim"])
        self.assertFalse(summary["production_quic_backend_claim"])
        self.assertFalse(summary["production_readiness"])
        for run in summary["runs"]:
            self.assertEqual(run["status"], "ok")
            self.assertTrue(probe_ok(run["probe"]))
            self.assertTrue(service_ok(run["service"]))
            self.assertTrue(run["netem_configured_both_containers"])
            self.assertGreaterEqual(run["service_qlog_file_count"], 1)
            self.assertGreaterEqual(run["client_qlog_file_count"], 3)
            self.assertGreater(run["service_qlog_bytes"], 0)
            self.assertGreater(run["client_qlog_bytes"], 0)

    def test_service_and_probe_are_wired_into_the_package(self) -> None:
        service = (ROOT / "scripts" / "fleetrmw_quic_gateway_service.py").read_text()
        probe = (
            ROOT
            / "ros2_ws"
            / "src"
            / "rmw_fleetqox_cpp"
            / "src"
            / "quic_stateful_gateway_probe.cpp"
        ).read_text()
        dockerfile = (ROOT / "external" / "rmw-netem" / "Dockerfile").read_text()
        self.assertIn("from aioquic.asyncio import QuicConnectionProtocol, serve", service)
        self.assertIn("ServiceTelemetry", service)
        self.assertIn("fleetrmw.quic_stateful_gateway_probe.v1", probe)
        self.assertIn("HTTP/3 response status 400", probe)
        self.assertIn("python3-aioquic", dockerfile)

    def test_public_rmw_validators_reject_partial_delivery(self) -> None:
        summary = json.loads(RMW_ARTIFACT.read_text(encoding="utf-8"))
        run = summary["runs"][0]
        self.assertTrue(endpoint_ok(run["publisher"], "publisher"))
        self.assertTrue(endpoint_ok(run["subscriber"], "subscriber"))
        self.assertTrue(rmw_service_ok(run["service"]))
        partial = copy.deepcopy(run["subscriber"])
        partial["completed_count"] = 2
        self.assertFalse(endpoint_ok(partial, "subscriber"))

    def test_public_rmw_canonical_artifact_passes_five_runs(self) -> None:
        summary = json.loads(RMW_ARTIFACT.read_text(encoding="utf-8"))
        self.assertEqual(summary["status"], "ok")
        self.assertEqual(summary["run_count"], 5)
        self.assertEqual(summary["successful_runs"], 5)
        self.assertEqual(summary["container_count_per_run"], 3)
        self.assertTrue(summary["real_quic_v1_h3"])
        self.assertTrue(summary["tls_peer_verification_required"])
        self.assertTrue(summary["stateful_gateway_interprocess_rmw_publish_take_claim"])
        self.assertTrue(summary["rmw_publish_path_integrated_claim"])
        self.assertTrue(summary["rmw_take_path_integrated_claim"])
        self.assertTrue(summary["persistent_session_reuse_both_endpoints_claim"])
        self.assertFalse(summary["production_quic_backend_claim"])
        self.assertFalse(summary["production_readiness"])
        for run in summary["runs"]:
            self.assertEqual(run["status"], "ok")
            self.assertTrue(endpoint_ok(run["publisher"], "publisher"))
            self.assertTrue(endpoint_ok(run["subscriber"], "subscriber"))
            self.assertTrue(rmw_service_ok(run["service"]))
            self.assertTrue(run["netem_configured_all_containers"])
            self.assertGreaterEqual(run["service_qlog_file_count"], 1)
            self.assertEqual(run["publisher_qlog_file_count"], 1)
            self.assertEqual(run["subscriber_qlog_file_count"], 1)
            self.assertGreater(run["qlog_total_bytes"], 0)


if __name__ == "__main__":
    unittest.main()

from __future__ import annotations

import json
import unittest

from scripts.run_rmw_docker_ngtcp2_public_stateful_gateway_probe import (
    BACKEND_SCHEMA_VERSION,
    ROOT,
    SCHEMA_VERSION,
    backend_ok,
    probe_ok,
)


class Ngtcp2PublicStatefulGatewayTest(unittest.TestCase):
    def test_pinned_server_patch_forwards_bounded_identity_aware_requests(self) -> None:
        patch = (
            ROOT / "external/ngtcp2-public-mtls/stateful-backend.patch"
        ).read_text(encoding="utf-8")
        self.assertIn("FLEETQOX_STATE_BACKEND_SOCKET", patch)
        self.assertIn("FLEETQOX_STATE_BACKEND_MAX_BODY_BYTES", patch)
        self.assertIn("FLEETQOX_GNUTLS_REQUIRED_CLIENT_URI_SAN", patch)
        self.assertIn("FLEETQOX_PUBLIC_MTLS_IDENTITY", patch)
        self.assertIn("SO_RCVTIMEO", patch)
        self.assertIn("request_body_too_large", patch)
        self.assertNotIn("aioquic", patch.lower())

    def test_runner_preserves_remaining_production_boundary(self) -> None:
        runner = (
            ROOT
            / "scripts/run_rmw_docker_ngtcp2_public_stateful_gateway_probe.py"
        ).read_text(encoding="utf-8")
        self.assertIn(SCHEMA_VERSION, runner)
        self.assertIn(BACKEND_SCHEMA_VERSION, runner)
        self.assertIn('"aioquic_server_runtime_used": False', runner)
        self.assertIn('"native_public_path_metrics_integrated": False', runner)
        self.assertIn('"production_quic_backend_claim": False', runner)

    def test_predicates_cover_state_and_transport_evidence(self) -> None:
        probe = {
            "schema_version": "fleetrmw.quic_stateful_gateway_probe.v1",
            "status": "ok",
            "stateful_gateway_roundtrip_claim": True,
            "per_consumer_replay_claim": True,
            "invalid_frame_http_status_fail_closed_claim": True,
            "alpha_connections_created": 1,
            "alpha_handshakes_completed": 1,
            "alpha_streams_opened": 7,
            "alpha_connection_reuse_count": 6,
            "beta_connections_created": 1,
            "beta_handshakes_completed": 1,
            "beta_streams_opened": 3,
            "beta_connection_reuse_count": 2,
        }
        backend = {
            "schema_version": BACKEND_SCHEMA_VERSION,
            "status": "stopped",
            "clean_teardown": True,
            "metrics": {
                "identity_rejections": 1,
                "protocol_rejections": 0,
                "require_client_identity": True,
                "accept_public_path_observations": False,
                "public_path_telemetry_requests": 4,
                "public_path_observation_updates": 0,
                "public_path_missing_rtt_samples": 0,
                "public_path_loss_semantics": (
                    "raw_ngtcp2_stream_packet_loss_count_not_loss_ratio"
                ),
                "public_path_rttvar_semantics": (
                    "ngtcp2_rttvar_mean_deviation_used_as_jitter_proxy"
                ),
                "last_public_path_telemetry": {
                    "rtt_initialized": True,
                    "smoothed_rtt_us": 20_000,
                },
                "state": {
                    "requests_total": 11,
                    "post_requests": 5,
                    "get_requests": 6,
                    "accepted_frames": 3,
                    "duplicate_frames": 1,
                    "invalid_frames": 1,
                    "dequeued_frames": 6,
                    "retained_frames": 3,
                    "consumer_count": 2,
                },
            },
        }
        self.assertTrue(probe_ok(probe))
        self.assertTrue(backend_ok(backend))

    def test_canonical_artifact_passes_five_runs(self) -> None:
        artifact = (
            ROOT
            / "results_rmw_socket/"
            "docker_ngtcp2_public_stateful_gateway_summary.json"
        )
        if not artifact.exists():
            self.skipTest("canonical public stateful artifact has not been generated")
        summary = json.loads(artifact.read_text(encoding="utf-8"))
        self.assertEqual(summary["schema_version"], SCHEMA_VERSION)
        self.assertEqual(summary["status"], "ok")
        self.assertEqual(summary["run_count"], 5)
        self.assertEqual(summary["ok_run_count"], 5)
        self.assertTrue(
            summary["public_api_stateful_gateway_backend_integrated_claim"]
        )
        self.assertTrue(summary["public_api_stateful_identity_binding_claim"])
        self.assertFalse(summary["aioquic_server_runtime_used"])
        self.assertFalse(summary["native_public_path_metrics_integrated"])
        self.assertFalse(summary["production_quic_backend_claim"])


if __name__ == "__main__":
    unittest.main()

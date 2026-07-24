from __future__ import annotations

import json
import unittest

from scripts.run_rmw_docker_ngtcp2_public_path_admission_probe import (
    BACKEND_SCHEMA_VERSION,
    ROOT,
    SCHEMA_VERSION,
    backend_phase_ok,
)


class Ngtcp2PublicPathAdmissionTest(unittest.TestCase):
    def test_patch_uses_only_public_ngtcp2_path_metric_apis(self) -> None:
        patch = (
            ROOT / "external/ngtcp2-public-mtls/stateful-backend.patch"
        ).read_text(encoding="utf-8")
        self.assertIn("ngtcp2_conn_get_conn_stat", patch)
        self.assertIn("ngtcp2_conn_get_stream_loss_count", patch)
        self.assertIn("FLEETQOX_PUBLIC_PATH_TELEMETRY", patch)
        self.assertNotIn("aioquic", patch.lower())

    def test_backend_predicate_distinguishes_disabled_and_enabled(self) -> None:
        def summary(enabled: bool) -> dict[str, object]:
            count = 1 if enabled else 0
            return {
                "schema_version": BACKEND_SCHEMA_VERSION,
                "status": "stopped",
                "clean_teardown": True,
                "metrics": {
                    "accept_public_path_observations": enabled,
                    "identity_rejections": 0,
                    "protocol_rejections": 0,
                    "public_path_telemetry_requests": 1,
                    "public_path_observation_updates": count,
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
                        "accepted_frames": count,
                        "requests_total": 2 if enabled else 1,
                        "post_requests": 1,
                        "get_requests": count,
                        "dequeued_frames": count,
                        "retained_frames": count,
                        "observation_requests": 0,
                        "admission": {
                            "observation_updates": count,
                            "observation_updates_by_source": (
                                {"ngtcp2_public_api": 1} if enabled else {}
                            ),
                            "observation_score_uses": count,
                            "rejected_by_reason": (
                                {}
                                if enabled
                                else {"qox_score_below_threshold": 1}
                            ),
                        },
                    },
                },
            }

        self.assertTrue(backend_phase_ok(summary(False), enabled=False))
        self.assertTrue(backend_phase_ok(summary(True), enabled=True))
        self.assertFalse(backend_phase_ok(summary(False), enabled=True))

    def test_runner_preserves_production_boundary(self) -> None:
        runner = (
            ROOT
            / "scripts/run_rmw_docker_ngtcp2_public_path_admission_probe.py"
        ).read_text(encoding="utf-8")
        self.assertIn(SCHEMA_VERSION, runner)
        self.assertIn('"external_observation_api_requests": 0', runner)
        self.assertIn('"production_quic_backend_claim": False', runner)

    def test_canonical_artifact_passes_five_runs(self) -> None:
        artifact = (
            ROOT
            / "results_rmw_socket/"
            "docker_ngtcp2_public_path_admission_summary.json"
        )
        if not artifact.exists():
            self.skipTest("canonical public path-admission artifact is absent")
        summary = json.loads(artifact.read_text(encoding="utf-8"))
        self.assertEqual(summary["schema_version"], SCHEMA_VERSION)
        self.assertEqual(summary["status"], "ok")
        self.assertEqual(summary["run_count"], 5)
        self.assertEqual(summary["ok_run_count"], 5)
        self.assertTrue(summary["public_ngtcp2_api_path_metrics_claim"])
        self.assertTrue(summary["public_path_metrics_admission_contrast_claim"])
        self.assertEqual(summary["external_observation_api_requests"], 0)
        self.assertTrue(summary["raw_stream_loss_count_not_ratio_claim"])
        self.assertFalse(summary["production_quic_backend_claim"])


if __name__ == "__main__":
    unittest.main()

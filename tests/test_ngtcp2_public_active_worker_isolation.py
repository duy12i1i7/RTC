from __future__ import annotations

import json
import unittest

from scripts.run_rmw_docker_ngtcp2_public_active_worker_isolation_probe import (
    ROOT,
    SCHEMA_VERSION,
)


class Ngtcp2PublicActiveWorkerIsolationTest(unittest.TestCase):
    def test_patch_tracks_active_identity_and_runnable_identity_sets(
        self,
    ) -> None:
        patch = (
            ROOT
            / "external/ngtcp2-public-mtls/active-worker-isolation.patch"
        ).read_text(encoding="utf-8")
        self.assertIn(
            "FLEETQOX_STATE_BACKEND_PER_IDENTITY_ACTIVE_LIMIT",
            patch,
        )
        self.assertIn("backend_identity_active_counts_", patch)
        self.assertIn("backend_ready_identity_set_", patch)
        self.assertIn("schedule_backend_identity_locked", patch)
        self.assertIn(
            "active >= backend_per_identity_active_limit_",
            patch,
        )
        self.assertIn(
            "backend_stopping_ || !backend_ready_identities_.empty()",
            patch,
        )
        self.assertIn("FLEETQOX_STATE_BACKEND_ACTIVE", patch)
        self.assertIn("FLEETQOX_STATE_BACKEND_RELEASED", patch)
        self.assertNotIn("aioquic", patch.lower())

    def test_default_active_limit_preserves_worker_pool_concurrency(self) -> None:
        patch = (
            ROOT
            / "external/ngtcp2-public-mtls/active-worker-isolation.patch"
        ).read_text(encoding="utf-8")
        self.assertIn(
            '"FLEETQOX_STATE_BACKEND_PER_IDENTITY_ACTIVE_LIMIT"',
            patch,
        )
        self.assertIn(
            "worker_count, FLEETQOX_BACKEND_MAX_WORKERS",
            patch,
        )
        self.assertIn("      worker_count);", patch)

    def test_dockerfile_applies_active_isolation_after_identity_patch(
        self,
    ) -> None:
        dockerfile = (
            ROOT / "external/ngtcp2-public-mtls/Dockerfile"
        ).read_text(encoding="utf-8")
        identity = dockerfile.index("identity-fairness.patch")
        active = dockerfile.index("active-worker-isolation.patch")
        self.assertLess(identity, active)

    def test_runner_has_matched_limit_control_and_production_boundary(
        self,
    ) -> None:
        runner = (
            ROOT
            / "scripts/"
            "run_rmw_docker_ngtcp2_public_active_worker_isolation_probe.py"
        ).read_text(encoding="utf-8")
        self.assertIn(SCHEMA_VERSION, runner)
        self.assertIn("active_limit=1", runner)
        self.assertIn("active_limit=2", runner)
        self.assertIn("matched_active_limit_contrast", runner)
        self.assertIn("victim_b_completed_while_both_a_clients_open", runner)
        self.assertIn('"production_quic_backend_claim": False', runner)

    def test_canonical_artifact_passes_five_runs(self) -> None:
        artifact = (
            ROOT
            / "results_rmw_socket/"
            "docker_ngtcp2_public_active_worker_isolation_summary.json"
        )
        if not artifact.exists():
            self.skipTest("canonical active-worker artifact has not been generated")
        summary = json.loads(artifact.read_text(encoding="utf-8"))
        self.assertEqual(summary["schema_version"], SCHEMA_VERSION)
        self.assertEqual(summary["status"], "ok")
        self.assertEqual(summary["run_count"], 5)
        self.assertEqual(summary["ok_run_count"], 5)
        self.assertTrue(summary["per_identity_active_worker_limit_claim"])
        self.assertTrue(
            summary["active_worker_cross_publisher_isolation_claim"]
        )
        self.assertTrue(summary["matched_active_limit_contrast_claim"])
        self.assertFalse(summary["production_quic_backend_claim"])


if __name__ == "__main__":
    unittest.main()

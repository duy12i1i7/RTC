from __future__ import annotations

import json
import unittest

from scripts.run_rmw_docker_ngtcp2_public_identity_fairness_probe import (
    ROOT,
    SCHEMA_VERSION,
)


class Ngtcp2PublicIdentityFairnessTest(unittest.TestCase):
    def test_patch_derives_bounded_identity_from_verified_peer_certificate(
        self,
    ) -> None:
        patch = (
            ROOT / "external/ngtcp2-public-mtls/identity-fairness.patch"
        ).read_text(encoding="utf-8")
        self.assertIn("gnutls_certificate_get_peers", patch)
        self.assertIn("gnutls_x509_crt_get_subject_alt_name", patch)
        self.assertIn("GNUTLS_SAN_URI", patch)
        self.assertIn("FLEETQOX_GNUTLS_CLIENT_URI_PREFIX", patch)
        self.assertIn("fleetqox_valid_client_identity", patch)
        self.assertIn("identity.size() <= 256", patch)
        self.assertIn("tls_session_.get_native_handle()", patch)
        self.assertNotIn("aioquic", patch.lower())

    def test_patch_has_per_identity_limit_and_round_robin_scheduler(self) -> None:
        patch = (
            ROOT / "external/ngtcp2-public-mtls/identity-fairness.patch"
        ).read_text(encoding="utf-8")
        self.assertIn(
            "FLEETQOX_STATE_BACKEND_PER_IDENTITY_QUEUE_CAPACITY",
            patch,
        )
        self.assertIn("backend_identity_tasks_", patch)
        self.assertIn("backend_ready_identities_", patch)
        self.assertIn("IdentityQueueFull", patch)
        self.assertIn("FLEETQOX_STATE_BACKEND_IDENTITY_QUEUE_FULL", patch)
        self.assertIn("send_status_response(httpconn, 429)", patch)
        pop = patch.index("backend_ready_identities_.pop_front()")
        rotate = patch.index("backend_ready_identities_.push_back(std::move(identity))")
        self.assertLess(pop, rotate)

    def test_dockerfile_applies_fairness_after_async_patch(self) -> None:
        dockerfile = (
            ROOT / "external/ngtcp2-public-mtls/Dockerfile"
        ).read_text(encoding="utf-8")
        asynchronous = dockerfile.index("async-backend.patch")
        fairness = dockerfile.index("identity-fairness.patch")
        self.assertLess(asynchronous, fairness)

    def test_runner_covers_two_identities_order_and_negative_control(self) -> None:
        runner = (
            ROOT
            / "scripts/run_rmw_docker_ngtcp2_public_identity_fairness_probe.py"
        ).read_text(encoding="utf-8")
        self.assertIn(SCHEMA_VERSION, runner)
        self.assertIn("fairness-publisher-a", runner)
        self.assertIn("fairness-publisher-b", runner)
        self.assertIn("spiffe://other/publishers/fairness-outsider", runner)
        self.assertIn('forwarded_consumer_ids[0] == "queue-a1"', runner)
        self.assertIn(
            '== {"queue-a2", "queue-a3", "victim-b"}',
            runner,
        )
        self.assertIn('forwarded_consumer_ids.index("victim-b")', runner)
        self.assertIn("publisher_a_overload_http_429", runner)
        self.assertIn("publisher_b_overtook_queued_publisher_a", runner)
        self.assertIn('"production_quic_backend_claim": False', runner)

    def test_canonical_artifact_passes_five_runs(self) -> None:
        artifact = (
            ROOT
            / "results_rmw_socket/"
            "docker_ngtcp2_public_identity_fairness_summary.json"
        )
        if not artifact.exists():
            self.skipTest("canonical public fairness artifact has not been generated")
        summary = json.loads(artifact.read_text(encoding="utf-8"))
        self.assertEqual(summary["schema_version"], SCHEMA_VERSION)
        self.assertEqual(summary["status"], "ok")
        self.assertEqual(summary["run_count"], 5)
        self.assertEqual(summary["ok_run_count"], 5)
        self.assertTrue(
            summary["per_connection_certificate_uri_san_identity_claim"]
        )
        self.assertTrue(summary["out_of_prefix_identity_fail_closed_claim"])
        self.assertTrue(summary["round_robin_backend_queue_fairness_claim"])
        self.assertTrue(summary["cross_publisher_overload_isolation_claim"])
        self.assertFalse(summary["production_quic_backend_claim"])


if __name__ == "__main__":
    unittest.main()

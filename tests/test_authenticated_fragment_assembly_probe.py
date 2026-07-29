from __future__ import annotations

import unittest

from scripts.run_rmw_docker_authenticated_fragment_assembly_probe import (
    PUBLISHER_SCHEMA_VERSION,
    RECEIVER_SCHEMA_VERSION,
    summarize_probe,
)


class AuthenticatedFragmentAssemblyAdmissionProbeTests(unittest.TestCase):
    def test_summary_requires_aead_and_exact_resource_bound(self) -> None:
        receiver = {
            "schema_version": RECEIVER_SCHEMA_VERSION,
            "status": "ok",
            "metrics": {
                "fragment_active_assemblies": 4,
                "fragment_active_missing_indexes": 4,
                "fragment_assembly_evictions": 2,
                "udp_aead_enabled": True,
                "udp_aead_decrypted_frames": 24,
                "udp_aead_authentication_failures": 0,
                "udp_aead_unprotected_drops": 2,
                "taken": 0,
                "done_seen": True,
            },
        }
        publisher = {
            "schema_version": PUBLISHER_SCHEMA_VERSION,
            "status": "ok",
            "metrics": {
                "matched": True,
                "published": 6,
                "test_dropped_fragments": 6,
                "udp_aead_encrypted_frames": 24,
                "udp_aead_authentication_failures": 0,
                "unprotected_negative_control_count": 2,
            },
        }
        summary = summarize_probe(
            receiver,
            publisher,
            receiver_returncode=0,
            publisher_returncode=0,
            assembly_limit=4,
            max_assembly_bytes=16384,
        )
        self.assertEqual(summary["status"], "ok")
        self.assertTrue(
            summary["authenticated_fragment_assembly_admission_claim"]
        )
        self.assertTrue(
            summary["docker_authenticated_fragment_resource_bound_claim"]
        )
        self.assertTrue(
            summary["udp_unprotected_fragment_fail_closed_claim"]
        )
        self.assertFalse(summary["peer_identity_authentication_claim"])
        self.assertFalse(summary["production_fragment_security_claim"])

        receiver["metrics"]["udp_aead_unprotected_drops"] = 0
        failed = summarize_probe(
            receiver,
            publisher,
            receiver_returncode=0,
            publisher_returncode=0,
            assembly_limit=4,
            max_assembly_bytes=16384,
        )
        self.assertEqual(failed["status"], "failed")


if __name__ == "__main__":
    unittest.main()

from __future__ import annotations

import unittest

from scripts.run_rmw_docker_peer_identity_fragment_pressure_probe import (
    PUBLISHER_SCHEMA_VERSION,
    RECEIVER_SCHEMA_VERSION,
    RUN_SCHEMA_VERSION,
    summarize_campaign,
    summarize_probe,
)


class PeerIdentityFragmentPressureProbeTests(unittest.TestCase):
    def test_summary_requires_identity_rejection_without_state_growth(
        self,
    ) -> None:
        state = {
            "fragment_active_assemblies": 4,
            "fragment_active_missing_indexes": 4,
            "fragment_assembly_evictions": 2,
        }
        baseline = {
            **state,
            "udp_peer_auth_identity_denied": 0,
        }
        final = {
            **state,
            "udp_peer_auth_identity_denied": 24,
        }
        receiver = {
            "schema_version": RECEIVER_SCHEMA_VERSION,
            "status": "ok",
            "state_unchanged": True,
            "identity_denied_delta": 24,
            "expected_state": state,
            "baseline": baseline,
            "final": final,
        }

        def publisher(role: str, drops: int) -> dict[str, object]:
            return {
                "schema_version": PUBLISHER_SCHEMA_VERSION,
                "status": "ok",
                "role": role,
                "metrics": {
                    "matched": True,
                    "published": 6,
                    "test_dropped_fragments": drops,
                    "udp_peer_auth_signed_frames": 30,
                },
            }

        summary = summarize_probe(
            receiver,
            publisher("allowed", 6),
            publisher("attacker", 0),
            receiver_returncode=0,
            allowed_returncode=0,
            attacker_returncode=0,
            assembly_limit=4,
        )
        self.assertEqual(summary["status"], "ok")
        self.assertTrue(
            summary["peer_identity_fragment_pressure_isolation_claim"]
        )
        self.assertTrue(
            summary["unauthorized_identity_pre_reassembly_rejection_claim"]
        )
        self.assertFalse(summary["production_fragment_security_claim"])

        receiver["state_unchanged"] = False
        failed = summarize_probe(
            receiver,
            publisher("allowed", 6),
            publisher("attacker", 0),
            receiver_returncode=0,
            allowed_returncode=0,
            attacker_returncode=0,
            assembly_limit=4,
        )
        self.assertEqual(failed["status"], "failed")

    def test_campaign_requires_all_five_independent_runs(self) -> None:
        run = {
            "schema_version": RUN_SCHEMA_VERSION,
            "status": "ok",
            "peer_identity_fragment_pressure_isolation_claim": True,
            "unauthorized_identity_pre_reassembly_rejection_claim": True,
            "authorized_fragment_resource_bound_preserved_claim": True,
            "receiver": {"identity_denied_delta": 96},
        }
        summary = summarize_campaign([run] * 5, requested_run_count=5)
        self.assertEqual(summary["status"], "ok")
        self.assertEqual(summary["ok_run_count"], 5)
        self.assertEqual(summary["identity_denied_total"], 480)
        self.assertTrue(
            summary["repeated_peer_identity_fragment_pressure_claim"]
        )
        self.assertFalse(
            summary["long_duration_peer_identity_fragment_soak_claim"]
        )

        failed = summarize_campaign([run] * 4, requested_run_count=5)
        self.assertEqual(failed["status"], "failed")


if __name__ == "__main__":
    unittest.main()

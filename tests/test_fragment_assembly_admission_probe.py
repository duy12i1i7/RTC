from __future__ import annotations

import unittest

from scripts.run_rmw_docker_fragment_assembly_admission_probe import (
    summarize_probe,
)


class FragmentAssemblyAdmissionProbeTests(unittest.TestCase):
    def test_summary_requires_exact_bounded_resource_contract(self) -> None:
        receiver = {
            "schema_version":
                "fleetrmw.fragment_assembly_admission_receiver.v1",
            "status": "ok",
            "metrics": {
                "fragment_active_assemblies": 4,
                "fragment_active_missing_indexes": 4,
                "fragment_assembly_evictions": 2,
                "fragment_assembly_oversize_drops": 1,
                "fragment_assembly_metadata_mismatch_drops": 1,
            },
        }
        summary = summarize_probe(
            receiver,
            receiver_returncode=0,
            injector_returncode=0,
            assembly_limit=4,
            max_assembly_bytes=4096,
        )
        self.assertEqual(summary["status"], "ok")
        self.assertTrue(
            summary["bounded_fragment_assembly_admission_claim"]
        )
        self.assertFalse(summary["production_fragment_security_claim"])

        receiver["metrics"]["fragment_active_assemblies"] = 5
        failed = summarize_probe(
            receiver,
            receiver_returncode=0,
            injector_returncode=0,
            assembly_limit=4,
            max_assembly_bytes=4096,
        )
        self.assertEqual(failed["status"], "failed")


if __name__ == "__main__":
    unittest.main()

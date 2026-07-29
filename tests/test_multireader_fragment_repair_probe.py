from __future__ import annotations

import unittest

from scripts.run_rmw_docker_multireader_fragment_repair_probe import (
    INJECTOR_SCHEMA_VERSION,
    PUBLISHER_SCHEMA_VERSION,
    summarize_probe,
)


class MultiReaderFragmentRepairProbeTests(unittest.TestCase):
    def test_summary_requires_two_isolated_readers_and_denied_source(
        self,
    ) -> None:
        metrics = {
            "fragment_repair_source_denials": 1,
            "fragments_selectively_retransmitted": 2,
        }
        publisher = {
            "schema_version": PUBLISHER_SCHEMA_VERSION,
            "status": "ok",
            "metrics": metrics,
            "expected": dict(metrics),
        }
        injector = {
            "schema_version": INJECTOR_SCHEMA_VERSION,
            "status": "ok",
            "requested": True,
            "repair_seen_by_port": {
                "49821": 1,
                "49822": 1,
                "49823": 0,
            },
        }
        summary = summarize_probe(
            publisher,
            injector,
            publisher_returncode=0,
            injector_returncode=0,
        )
        self.assertEqual(summary["status"], "ok")
        self.assertTrue(
            summary["multi_reader_fragment_repair_isolation_claim"]
        )
        self.assertTrue(
            summary[
                "unauthorized_fragment_repair_source_fail_closed_claim"
            ]
        )

        injector["repair_seen_by_port"]["49822"] = 0
        failed = summarize_probe(
            publisher,
            injector,
            publisher_returncode=0,
            injector_returncode=1,
        )
        self.assertEqual(failed["status"], "failed")


if __name__ == "__main__":
    unittest.main()

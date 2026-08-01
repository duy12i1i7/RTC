from copy import deepcopy
from pathlib import Path
import unittest

from scripts.generate_unified_benchmark_report import classify_path
from scripts.run_rmw_docker_loss_resilient_fragment_campaign import (
    summarize_campaign,
)


def result(seed: int) -> dict:
    return {
        "status": "ok",
        "rmw": "rmw_fleetqox_cpp",
        "profile": "roaming",
        "netem_enabled": True,
        "netem_required": True,
        "netem_loss_scale": 0.25,
        "samples": 3,
        "robot_count": 1,
        "payload_bytes": 32768,
        "payload_size_contract_ok": True,
        "payload_size_min_bytes": 32768,
        "payload_size_max_bytes": 32768,
        "publish_interval_ms": 2000,
        "relay_expected_count": 6,
        "relay_payload_count": 6,
        "control_delivery_ratio": 1.0,
        "state_delivery_ratio": 1.0,
        "fleetqox_loss_resilient_fragment_chunk_bytes": 1024,
        "fleetqox_reliable_max_retransmissions": 6,
        "fleetqox_fragment_nack_interval_ms": 50,
        "fleetqox_fragment_nack_max_requests": 6,
        "fleetqox_fragment_nack_max_indexes_per_request": 8,
        "fleetqox_fragment_history_limit": 1024,
        "fleetqox_fragment_assembly_ttl_ms": 60000,
        "fleetqox_fragment_whole_fallback_grace_ms": 1000,
        "fleetqox_fragment_tail_guard_ms": 1000,
        "fleetqox_udp_datagram_budget_bytes": 1472,
        "publisher": {
            "ack_wait_supported": True,
            "ack_wait_complete": True,
            "unacked_topic_count": 0,
        },
        "repetition_seed": seed,
    }


def summary(rows):
    return summarize_campaign(
        rows,
        image="image",
        profile="roaming",
        netem_loss_scale=0.25,
        seeds=[7, 13, 29, 37, 43],
        samples=3,
        robot_count=1,
        payload_bytes=32768,
        publish_interval_ms=2000,
        timeout_s=25.0,
        fragment_chunk_bytes=1024,
        max_retransmissions=6,
    )


class LossResilientFragmentCampaignTest(unittest.TestCase):
    def test_accepts_complete_five_seed_campaign(self):
        rows = [
            {"seed": seed, "status": "ok", "result": result(seed)}
            for seed in (7, 13, 29, 37, 43)
        ]
        campaign = summary(rows)
        self.assertEqual(campaign["status"], "ok")
        self.assertEqual(campaign["ok_run_count"], 5)
        self.assertEqual(campaign["relay_payload_count"], 30)
        self.assertTrue(
            campaign["loss_resilient_large_sample_fragment_repair_claim"]
        )
        self.assertFalse(campaign["production_large_sample_reliability_claim"])
        self.assertEqual(
            classify_path(Path("campaign_summary.json"), campaign),
            "transport/udp",
        )

    def test_rejects_missing_fragment_configuration_evidence(self):
        rows = [
            {"seed": seed, "status": "ok", "result": result(seed)}
            for seed in (7, 13, 29, 37, 43)
        ]
        mismatched = deepcopy(rows)
        mismatched[2]["result"][
            "fleetqox_loss_resilient_fragment_chunk_bytes"
        ] = 0
        campaign = summary(mismatched)
        self.assertEqual(campaign["status"], "failed")
        self.assertEqual(campaign["ok_run_count"], 4)


if __name__ == "__main__":
    unittest.main()

from copy import deepcopy
from pathlib import Path
import unittest

from scripts.generate_unified_benchmark_report import classify_path
from scripts.run_rmw_docker_selective_fragment_repair_probe import (
    summarize_probe,
)


def relay_result() -> dict:
    return {
        "status": "ok",
        "rmw": "rmw_fleetqox_cpp",
        "netem_enabled": True,
        "netem_required": True,
        "netem_loss_scale": 0.0,
        "robot_count": 1,
        "samples": 1,
        "payload_bytes": 32768,
        "payload_size_contract_ok": True,
        "payload_size_min_bytes": 32768,
        "payload_size_max_bytes": 32768,
        "fleetqox_loss_resilient_fragment_chunk_bytes": 1024,
        "fleetqox_reliable_max_retransmissions": 0,
        "fleetqox_fragment_async_send": True,
        "fleetqox_fragment_send_queue_limit": 32768,
        "fleetqox_publisher_test_drop_fragment_indexes": "2",
        "relay_expected_count": 2,
        "relay_payload_count": 2,
        "control_delivery_ratio": 1.0,
        "state_delivery_ratio": 1.0,
        "publisher_returncode": 0,
        "relay_returncode": 0,
        "subscriber_returncode": 0,
        "publisher": {
            "ack_wait_supported": True,
            "ack_wait_complete": True,
            "unacked_topic_count": 0,
            "fleetqox_transport_metrics": {
                "available": True,
                "test_dropped_fragments": 2,
                "fragment_nacks_received": 2,
                "fragments_selectively_retransmitted": 2,
                "reliable_timeout_retransmissions": 0,
                "fragment_send_queue_rejections": 0,
                "fragment_send_failures": 0,
                "fragment_send_queue_high_water": 65,
            },
        },
        "relay": {
            "fleetqox_transport_metrics": {
                "available": True,
                "fragment_nacks_sent": 2,
            },
        },
    }


def summary(result: dict) -> dict:
    return summarize_probe(
        result,
        payload_bytes=32768,
        fragment_chunk_bytes=1024,
        dropped_fragment_indexes="2",
        queue_limit=32768,
    )


class SelectiveFragmentRepairProbeTest(unittest.TestCase):
    def test_accepts_selective_repair_without_whole_sample_retry(self):
        probe = summary(relay_result())
        self.assertEqual(probe["status"], "ok")
        self.assertTrue(
            probe["fragment_specific_nack_selective_retransmission_claim"]
        )
        self.assertTrue(
            probe[
                "docker_selective_fragment_repair_without_whole_sample_retry_claim"
            ]
        )
        self.assertTrue(probe["bounded_async_fragment_send_queue_claim"])
        self.assertFalse(probe["fleet_scale_selective_fragment_repair_claim"])
        self.assertFalse(probe["production_large_sample_reliability_claim"])
        self.assertEqual(
            classify_path(Path("selective_fragment_repair_summary.json"), probe),
            "transport/udp",
        )

    def test_rejects_whole_sample_retry_or_queue_failure(self):
        invalid = deepcopy(relay_result())
        invalid["fleetqox_reliable_max_retransmissions"] = 1
        invalid["publisher"]["fleetqox_transport_metrics"][
            "fragment_send_queue_rejections"
        ] = 1
        self.assertEqual(summary(invalid)["status"], "failed")


if __name__ == "__main__":
    unittest.main()

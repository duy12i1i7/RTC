from __future__ import annotations

import unittest
from pathlib import Path

from scripts.generate_unified_benchmark_report import classify_path
from scripts.run_rmw_docker_initial_fragment_round_robin_probe import (
    summarize_probe,
)


def result() -> dict:
    return {
        "status": "ok",
        "rmw": "rmw_fleetqox_cpp",
        "netem_enabled": True,
        "netem_required": True,
        "netem_loss_scale": 0.0,
        "samples": 4,
        "robot_count": 1,
        "payload_bytes": 32768,
        "fleetqox_loss_resilient_fragment_chunk_bytes": 1024,
        "fleetqox_udp_send_pacing_us": 1600,
        "fleetqox_udp_datagram_budget_bytes": 1472,
        "fleetqox_reliable_max_retransmissions": 1,
        "fleetqox_fragment_whole_fallback_grace_ms": 5000,
        "fleetqox_fragment_async_send": True,
        "relay_expected_count": 8,
        "relay_payload_count": 8,
        "publisher_returncode": 0,
        "relay_returncode": 0,
        "subscriber_returncode": 0,
        "publisher": {
            "ack_wait_complete": True,
            "unacked_topic_count": 0,
            "fleetqox_transport_metrics": {
                "available": True,
                "fragment_initial_round_robin_rotations": 400,
                "fragment_initial_frame_switches": 300,
                "fragment_initial_max_consecutive_same_frame_while_contended":
                    1,
                "fragment_initial_max_active_frames": 8,
                "fragment_async_send_completions": 8,
                "fragment_initial_pending_timeout_suppressions": 8,
                "fragment_whole_fallback_grace_deferrals": 8,
                "reliable_timeout_retransmissions": 0,
                "fragment_send_queue_high_water": 256,
                "fragment_send_queue_rejections": 0,
                "fragment_send_failures": 0,
                "udp_datagram_size_high_water": 1120,
                "fragment_effective_chunk_bytes_min": 1024,
                "fragment_effective_chunk_bytes_max": 1024,
                "fragment_chunk_budget_reductions": 0,
                "udp_datagram_budget_failures": 0,
                "fragment_completion_markers_sent": 8,
                "fragment_completion_marker_failures": 0,
            },
        },
        "relay": {
            "fleetqox_transport_metrics": {
                "fragment_completion_markers_received": 8,
                "fragment_completion_marker_orphans": 0,
                "fragment_completion_marker_failures": 0,
            },
        },
    }


class InitialFragmentRoundRobinProbeTests(unittest.TestCase):
    def test_summary_requires_exact_contended_fairness(self) -> None:
        row = result()
        summary = summarize_probe(
            row,
            samples=4,
            payload_bytes=32768,
            fragment_chunk_bytes=1024,
            pacing_us=1600,
        )
        self.assertEqual(summary["status"], "ok")
        self.assertTrue(
            summary["round_robin_initial_fragment_scheduling_claim"]
        )
        self.assertTrue(summary["async_fragment_ack_timeout_after_drain_claim"])
        self.assertTrue(summary["fragment_sender_completion_marker_claim"])
        self.assertTrue(summary["mtu_aware_udp_datagram_budget_claim"])
        self.assertFalse(summary["fleet_scale_selective_fragment_repair_claim"])
        self.assertEqual(
            classify_path(
                Path(
                    "loss_resilient_round_robin_unseen_fallback_"
                    "32768_16robot_seed7_summary.json"
                ),
                summary,
            ),
            "transport/udp",
        )

        row["publisher"]["fleetqox_transport_metrics"][
            "fragment_initial_max_consecutive_same_frame_while_contended"
        ] = 2
        failed = summarize_probe(
            row,
            samples=4,
            payload_bytes=32768,
            fragment_chunk_bytes=1024,
            pacing_us=1600,
        )
        self.assertEqual(failed["status"], "failed")

    def test_summary_proves_requested_chunk_reduction_to_wire_budget(self) -> None:
        row = result()
        row["fleetqox_loss_resilient_fragment_chunk_bytes"] = 4096
        metrics = row["publisher"]["fleetqox_transport_metrics"]
        metrics["fragment_effective_chunk_bytes_min"] = 1368
        metrics["fragment_effective_chunk_bytes_max"] = 1368
        metrics["fragment_chunk_budget_reductions"] = 8
        summary = summarize_probe(
            row,
            samples=4,
            payload_bytes=32768,
            fragment_chunk_bytes=4096,
            pacing_us=1600,
        )
        self.assertEqual(summary["status"], "ok")
        self.assertTrue(summary["mtu_aware_udp_datagram_budget_claim"])

    def test_summary_accepts_retransmission_markers_but_requires_one_per_completion(
        self,
    ) -> None:
        row = result()
        metrics = row["publisher"]["fleetqox_transport_metrics"]
        relay_metrics = row["relay"]["fleetqox_transport_metrics"]
        metrics["fragment_async_send_completions"] = 9
        metrics["fragment_completion_markers_sent"] = 9
        relay_metrics["fragment_completion_markers_received"] = 9
        summary = summarize_probe(
            row,
            samples=4,
            payload_bytes=32768,
            fragment_chunk_bytes=1024,
            pacing_us=1600,
        )
        self.assertEqual(summary["status"], "ok")

        metrics["fragment_completion_markers_sent"] = 8
        failed = summarize_probe(
            row,
            samples=4,
            payload_bytes=32768,
            fragment_chunk_bytes=1024,
            pacing_us=1600,
        )
        self.assertEqual(failed["status"], "failed")


if __name__ == "__main__":
    unittest.main()

from __future__ import annotations

import unittest

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
                "fragment_send_queue_high_water": 256,
                "fragment_send_queue_rejections": 0,
                "fragment_send_failures": 0,
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
        self.assertFalse(summary["fleet_scale_selective_fragment_repair_claim"])

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


if __name__ == "__main__":
    unittest.main()

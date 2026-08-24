import importlib.util
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
RUNNER = ROOT / "scripts" / "run_rmw_docker_fragment_repair_round_robin_probe.py"


def load_runner():
    spec = importlib.util.spec_from_file_location("fragment_repair_rr", RUNNER)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class FragmentRepairRoundRobinProbeTest(unittest.TestCase):
    def test_summary_requires_contended_single_fragment_rotation(self):
        module = load_runner()
        samples = 4
        expected_frames = samples * 2
        metrics = {
            "available": True,
            "test_dropped_fragments": expected_frames * 8,
            "fragment_nacks_received": expected_frames,
            "fragments_selectively_retransmitted": expected_frames * 8,
            "fragment_repair_queue_high_water": 42,
            "fragment_repair_round_robin_rotations": 73,
            "fragment_repair_frame_switches": 79,
            "fragment_repair_max_active_frames": 6,
            "fragment_repair_max_consecutive_same_frame_while_contended": 1,
            "fragment_repair_queue_deferrals": 0,
            "fragment_send_queue_rejections": 0,
            "fragment_send_failures": 0,
        }
        result = {
            "status": "ok",
            "rmw": module.FLEETQOX_RMW,
            "netem_enabled": True,
            "netem_required": True,
            "netem_loss_scale": 0.0,
            "samples": samples,
            "robot_count": 1,
            "payload_bytes": 32768,
            "fleetqox_loss_resilient_fragment_chunk_bytes": 1024,
            "fleetqox_udp_send_pacing_us": 5000,
            "fleetqox_reliable_max_retransmissions": 0,
            "fleetqox_fragment_async_send": True,
            "fleetqox_fragment_repair_queue_limit": 256,
            "fleetqox_publisher_test_drop_fragment_indexes": (
                module.DEFAULT_DROP_INDEXES
            ),
            "relay_expected_count": expected_frames,
            "relay_payload_count": expected_frames,
            "publisher_returncode": 0,
            "relay_returncode": 0,
            "subscriber_returncode": 0,
            "publisher": {
                "ack_wait_complete": True,
                "unacked_topic_count": 0,
                "fleetqox_transport_metrics": metrics,
            },
        }
        summary = module.summarize_probe(
            result,
            samples=samples,
            payload_bytes=32768,
            fragment_chunk_bytes=1024,
            pacing_us=5000,
            repair_queue_limit=256,
            dropped_fragment_indexes=module.DEFAULT_DROP_INDEXES,
        )
        self.assertEqual(summary["status"], "ok")
        self.assertTrue(
            summary["per_frame_reader_fragment_repair_round_robin_claim"]
        )
        self.assertFalse(summary["fleet_scale_selective_fragment_repair_claim"])

        metrics[
            "fragment_repair_max_consecutive_same_frame_while_contended"
        ] = 2
        unfair = module.summarize_probe(
            result,
            samples=samples,
            payload_bytes=32768,
            fragment_chunk_bytes=1024,
            pacing_us=5000,
            repair_queue_limit=256,
            dropped_fragment_indexes=module.DEFAULT_DROP_INDEXES,
        )
        self.assertEqual(unfair["status"], "failed")

    def test_runtime_uses_per_scope_repair_queues(self):
        source = (
            ROOT / "ros2_ws" / "src" / "rmw_fleetqox_cpp" / "src" / "rmw_pubsub.cpp"
        ).read_text()
        self.assertIn("fragment_repair_send_queues_", source)
        self.assertIn("fragment_repair_send_order_", source)
        self.assertIn("fragment_repair_frame_queue_key", source)
        self.assertIn("fragment_repair_round_robin_rotations_", source)


if __name__ == "__main__":
    unittest.main()

import importlib.util
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
RUNNER = ROOT / "scripts" / "run_rmw_docker_progressive_fragment_repair_probe.py"


def load_runner():
    spec = importlib.util.spec_from_file_location("progressive_fragment_repair", RUNNER)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class ProgressiveFragmentRepairProbeTest(unittest.TestCase):
    def test_summary_requires_second_round_during_progress(self):
        module = load_runner()
        metrics = {
            "fragment_active_assemblies": 1,
            "fragment_active_missing_indexes": 12,
            "fragment_nack_exhausted_assemblies": 1,
            "fragment_nacks_sent": 2,
            "fragment_nack_indexes_requested": 16,
            "fragment_progressive_nacks_sent": 1,
        }
        receiver = {
            "schema_version": module.RECEIVER_SCHEMA_VERSION,
            "status": "ok",
            "metrics": metrics,
            "expected": dict(metrics),
        }
        injector = {
            "schema_version": module.INJECTOR_SCHEMA_VERSION,
            "status": "ok",
            "second_nack_elapsed_ms": 305.0,
            "progress_sent_at_second_nack": 3,
            "requests": [{}, {}],
        }
        summary = module.summarize_probe(
            receiver,
            injector,
            receiver_returncode=0,
            injector_returncode=0,
        )
        self.assertEqual(summary["status"], "ok")
        self.assertTrue(summary["progressive_multi_round_repair_claim"])
        self.assertFalse(summary["fleet_scale_selective_fragment_repair_claim"])

        injector["progress_sent_at_second_nack"] = 6
        late = module.summarize_probe(
            receiver,
            injector,
            receiver_returncode=0,
            injector_returncode=0,
        )
        self.assertEqual(late["status"], "failed")

    def test_runtime_only_requires_quiescence_before_initial_nack(self):
        source = (
            ROOT / "ros2_ws" / "src" / "rmw_fleetqox_cpp" / "src" / "rmw_pubsub.cpp"
        ).read_text()
        self.assertIn("assembly.nack_count == 0", source)
        self.assertIn("initial_quiescence_pending", source)
        self.assertIn("bounded_progress_grace_pending", source)
        self.assertIn("retry_interval_ns + interval_ns", source)
        self.assertIn("assembly.last_update_ns > assembly.last_nack_ns", source)
        self.assertIn("fragment_progressive_nacks_sent_", source)


if __name__ == "__main__":
    unittest.main()

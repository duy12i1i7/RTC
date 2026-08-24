import importlib.util
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
RUNNER = ROOT / "scripts" / "run_rmw_docker_fragment_tail_progress_probe.py"


def load_runner():
    spec = importlib.util.spec_from_file_location("fragment_tail_progress", RUNNER)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class FragmentTailProgressProbeTest(unittest.TestCase):
    def test_summary_requires_nack_while_duplicates_are_still_arriving(self):
        module = load_runner()
        metrics = {
            "fragment_active_assemblies": 1,
            "fragment_active_missing_indexes": 2,
            "fragment_nack_exhausted_assemblies": 1,
            "fragment_nacks_sent": 1,
            "fragment_nack_indexes_requested": 2,
            "fragment_duplicate_no_progress_drops": 20,
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
            "duplicate_count": module.DUPLICATE_COUNT,
            "first_nack_elapsed_ms": 430.0,
            "nack_during_duplicate_stream": True,
            "requests": [{
                "fragment_id": "tail-progress",
                "fragment_count": 4,
                "indexes": "2-3",
            }],
        }
        summary = module.summarize_probe(
            receiver,
            injector,
            receiver_returncode=0,
            injector_returncode=0,
        )
        self.assertEqual(summary["status"], "ok")
        self.assertTrue(summary["duplicate_fragment_no_progress_claim"])
        self.assertTrue(summary["tail_repair_bounded_under_duplicate_pressure_claim"])
        self.assertFalse(summary["production_large_sample_reliability_claim"])

        injector["first_nack_elapsed_ms"] = 950.0
        late = module.summarize_probe(
            receiver,
            injector,
            receiver_returncode=0,
            injector_returncode=0,
        )
        self.assertEqual(late["status"], "failed")

    def test_runtime_updates_progress_only_for_new_fragments(self):
        source = (
            ROOT / "ros2_ws" / "src" / "rmw_fleetqox_cpp" / "src" / "rmw_pubsub.cpp"
        ).read_text()
        block_start = source.index("if (!assembly.received[fragment_index])")
        block_end = source.index(
            "if (assembly.received_count != assembly.fragment_count)",
            block_start,
        )
        progress_block = source[block_start:block_end]
        self.assertIn("assembly.last_update_ns = now_ns", progress_block)
        preceding = source[source.rfind("if (source != nullptr)", 0, block_start):block_start]
        self.assertNotIn("assembly.last_update_ns = now_ns", preceding)


if __name__ == "__main__":
    unittest.main()

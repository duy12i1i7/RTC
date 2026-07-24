import copy
import json
from pathlib import Path
import unittest

from scripts.run_rmw_docker_quic_feedback_batch_probe import probe_ok, service_ok


ROOT = Path(__file__).resolve().parents[1]
ARTIFACT = (
    ROOT
    / "results_rmw_socket"
    / "docker_quic_feedback_batch_probe_summary.json"
)


class QuicFeedbackBatchTest(unittest.TestCase):
    def test_validators_reject_unaccounted_batch_priority(self) -> None:
        summary = json.loads(ARTIFACT.read_text(encoding="utf-8"))
        run = summary["runs"][0]
        self.assertTrue(probe_ok(run["probe"]))
        self.assertTrue(service_ok(run["service"]))
        mutated = copy.deepcopy(run["service"])
        mutated["metrics"]["batch_rejected_frames"] = 1
        self.assertFalse(service_ok(mutated))
        mutated = copy.deepcopy(run["service"])
        mutated["metrics"]["admission"]["repair_decisions"][0][
            "publisher_id"
        ] = "repair-low"
        self.assertFalse(service_ok(mutated))

    def test_canonical_docker_netem_artifact_passes_five_runs(self) -> None:
        summary = json.loads(ARTIFACT.read_text(encoding="utf-8"))
        self.assertEqual(summary["status"], "ok")
        self.assertEqual(summary["run_count"], 5)
        self.assertEqual(summary["successful_runs"], 5)
        self.assertEqual(summary["container_count_per_run"], 2)
        self.assertTrue(summary["real_quic_v1_h3"])
        self.assertTrue(summary["tls_peer_verification_required"])
        self.assertTrue(summary["closed_loop_observation_wire_claim"])
        self.assertTrue(summary["observation_adjusted_admission_score_claim"])
        self.assertTrue(summary["score_prioritized_batch_admission_claim"])
        self.assertTrue(summary["competing_repair_batch_capacity_claim"])
        self.assertTrue(summary["batch_admission_state_isolation_claim"])
        self.assertFalse(summary["production_quic_backend_claim"])
        self.assertFalse(summary["production_readiness"])
        for run in summary["runs"]:
            self.assertEqual(run["status"], "ok")
            self.assertTrue(run["netem_configured_both_containers"])
            self.assertGreaterEqual(run["service_qlog_file_count"], 1)
            self.assertEqual(run["client_qlog_file_count"], 3)
            self.assertGreater(run["qlog_total_bytes"], 0)
            self.assertTrue(probe_ok(run["probe"]))
            self.assertTrue(service_ok(run["service"]))

    def test_observation_batch_and_cpp_probe_are_wired(self) -> None:
        state = (ROOT / "fleetqox" / "quic_gateway_state.py").read_text()
        probe = (
            ROOT
            / "ros2_ws"
            / "src"
            / "rmw_fleetqox_cpp"
            / "src"
            / "quic_feedback_batch_probe.cpp"
        ).read_text()
        cmake = (
            ROOT / "ros2_ws" / "src" / "rmw_fleetqox_cpp" / "CMakeLists.txt"
        ).read_text()
        self.assertIn("def update_observation", state)
        self.assertIn("def effective_admission_score", state)
        self.assertIn("def publish_batch", state)
        self.assertIn("closed_loop_observation_wire_claim", probe)
        self.assertIn("fleetrmw_quic_feedback_batch_probe", cmake)
        capabilities = json.loads(
            (
                ROOT
                / "ros2_ws"
                / "src"
                / "rmw_fleetqox_cpp"
                / "capabilities.json"
            ).read_text()
        )
        self.assertTrue(
            capabilities["supported"][
                "stateful_quic_gateway_observation_adjusted_admission_score"
            ]
        )
        self.assertTrue(
            capabilities["supported"][
                "stateful_quic_gateway_score_prioritized_frame_batch"
            ]
        )
        self.assertTrue(
            capabilities["claim_boundaries"][
                "quic_gateway_competing_repair_batch_capacity_claim"
            ]
        )


if __name__ == "__main__":
    unittest.main()

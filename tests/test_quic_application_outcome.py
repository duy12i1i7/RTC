import copy
import json
from pathlib import Path
import unittest

from scripts.run_rmw_docker_quic_application_outcome_probe import (
    probe_ok,
    service_ok,
)


ROOT = Path(__file__).resolve().parents[1]
ARTIFACT = (
    ROOT
    / "results_rmw_socket"
    / "docker_quic_application_outcome_probe_summary.json"
)


class QuicApplicationOutcomeTest(unittest.TestCase):
    def test_canonical_authenticated_outcome_passes_five_runs(self) -> None:
        summary = json.loads(ARTIFACT.read_text(encoding="utf-8"))
        self.assertEqual(summary["status"], "ok")
        self.assertEqual(summary["run_count"], 5)
        self.assertEqual(summary["successful_runs"], 5)
        self.assertEqual(summary["container_count_per_run"], 2)
        self.assertTrue(summary["real_quic_v1_h3"])
        self.assertTrue(summary["mutual_tls_client_authentication_required"])
        self.assertTrue(summary["publisher_identity_binding_required"])
        self.assertFalse(summary["external_observation_api_used"])
        for claim in (
            "authenticated_application_outcome_feedback_claim",
            "application_outcome_known_frame_binding_claim",
            "application_outcome_publisher_identity_binding_claim",
            "application_outcome_replay_idempotence_claim",
            "application_outcome_malformed_fail_closed_claim",
            "application_outcome_qoe_debt_claim",
            "application_task_outcome_failure_pressure_claim",
            "application_outcome_admission_effect_claim",
        ):
            self.assertTrue(summary[claim])
        self.assertEqual(
            summary["application_outcome_qoe_debt_kind"],
            "ewma_authenticated_delivery_deadline_latency_task_pressure",
        )
        self.assertFalse(summary["production_quic_backend_claim"])
        self.assertFalse(summary["production_readiness"])
        for run in summary["runs"]:
            self.assertEqual(run["status"], "ok")
            self.assertTrue(run["netem_configured_both_containers"])
            self.assertGreater(run["qlog_file_count"], 0)
            self.assertGreater(run["qlog_total_bytes"], 0)
            self.assertTrue(probe_ok(run["probe"]))
            self.assertTrue(service_ok(run["service"]))

    def test_validators_reject_unproven_identity_state_and_provenance(self) -> None:
        run = json.loads(ARTIFACT.read_text(encoding="utf-8"))["runs"][0]
        mutated = copy.deepcopy(run["probe"])
        mutated["impersonation_rejected"] = False
        self.assertFalse(probe_ok(mutated))

        mutated = copy.deepcopy(run["service"])
        mutated["metrics"]["application_outcome_unknown_frames"] = 0
        self.assertFalse(service_ok(mutated))
        mutated = copy.deepcopy(run["service"])
        mutated["metrics"]["application_task_outcome_failures"] = 0
        self.assertFalse(service_ok(mutated))
        mutated = copy.deepcopy(run["service"])
        mutated["metrics"]["admission"][
            "active_observations_by_qoe_debt_source"
        ] = {"publisher_metadata": 1}
        self.assertFalse(service_ok(mutated))
        mutated = copy.deepcopy(run["service"])
        mutated["transport_metrics"][
            "application_outcome_identity_authorization_rejected"
        ] = 0
        self.assertFalse(service_ok(mutated))
        mutated = copy.deepcopy(run["service"])
        mutated["transport_metrics"]["malformed_h3_requests_rejected"] = 1
        self.assertFalse(service_ok(mutated))

    def test_service_probe_and_manifest_expose_fail_closed_boundary(self) -> None:
        state = (ROOT / "fleetqox" / "quic_gateway_state.py").read_text()
        service = (ROOT / "scripts" / "fleetrmw_quic_gateway_service.py").read_text()
        probe = (
            ROOT
            / "ros2_ws"
            / "src"
            / "rmw_fleetqox_cpp"
            / "src"
            / "quic_application_outcome_probe.cpp"
        ).read_text()
        cmake = (
            ROOT / "ros2_ws" / "src" / "rmw_fleetqox_cpp" / "CMakeLists.txt"
        ).read_text()
        capabilities = json.loads((
            ROOT
            / "ros2_ws"
            / "src"
            / "rmw_fleetqox_cpp"
            / "capabilities.json"
        ).read_text())
        self.assertIn('qoe_debt_source="gateway_derived_outcome"', state)
        self.assertIn("application outcome QoE debt requires mutual TLS", service)
        self.assertIn("completed_request_streams", service)
        self.assertIn("impersonation_rejected", probe)
        self.assertIn("fleetrmw_quic_application_outcome_probe", cmake)
        self.assertTrue(capabilities["supported"][
            "stateful_quic_gateway_authenticated_application_outcome"
        ])
        self.assertTrue(capabilities["supported"][
            "stateful_quic_gateway_application_task_outcome_pressure"
        ])
        self.assertTrue(capabilities["claim_boundaries"][
            "quic_gateway_application_outcome_qoe_debt_claim"
        ])
        self.assertTrue(capabilities["claim_boundaries"][
            "quic_gateway_application_task_outcome_pressure_claim"
        ])


if __name__ == "__main__":
    unittest.main()

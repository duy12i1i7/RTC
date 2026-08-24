import copy
import json
from pathlib import Path
import unittest

from scripts.run_rmw_docker_quic_native_qoe_debt_probe import (
    native_qoe_service_ok,
)


ROOT = Path(__file__).resolve().parents[1]
ARTIFACT = (
    ROOT
    / "results_rmw_socket"
    / "docker_quic_native_qoe_debt_probe_summary.json"
)


class QuicNativeQoeDebtTest(unittest.TestCase):
    @unittest.skipUnless(ARTIFACT.is_file(), "external Docker evidence artifact absent")
    def test_validators_reject_publisher_or_unproven_debt(self) -> None:
        summary = json.loads(ARTIFACT.read_text(encoding="utf-8"))
        run = summary["runs"][0]
        self.assertTrue(
            native_qoe_service_ok(run["path_only"]["service"], derived_qoe=False)
        )
        self.assertTrue(
            native_qoe_service_ok(run["derived_qoe"]["service"], derived_qoe=True)
        )

        mutated = copy.deepcopy(run["derived_qoe"]["service"])
        mutated["metrics"]["admission"][
            "active_observations_by_qoe_debt_source"
        ] = {"publisher_metadata": 1}
        self.assertFalse(native_qoe_service_ok(mutated, derived_qoe=True))
        mutated = copy.deepcopy(run["derived_qoe"]["service"])
        mutated["transport_metrics"]["native_qoe_debt_updates"] = 0
        self.assertFalse(native_qoe_service_ok(mutated, derived_qoe=True))
        mutated = copy.deepcopy(run["derived_qoe"]["service"])
        mutated["transport_metrics"]["native_qoe_latest_debt"] = 0.0
        self.assertFalse(native_qoe_service_ok(mutated, derived_qoe=True))

    @unittest.skipUnless(ARTIFACT.is_file(), "external Docker evidence artifact absent")
    def test_canonical_authenticated_native_qoe_contrast_passes_five_runs(
        self,
    ) -> None:
        summary = json.loads(ARTIFACT.read_text(encoding="utf-8"))
        self.assertEqual(summary["status"], "ok")
        self.assertEqual(summary["run_count"], 5)
        self.assertEqual(summary["successful_runs"], 5)
        self.assertEqual(summary["container_count_per_run"], 4)
        self.assertTrue(summary["real_quic_v1_h3"])
        self.assertTrue(summary["mutual_tls_client_authentication_required"])
        self.assertTrue(summary["publisher_identity_binding_required"])
        self.assertFalse(summary["external_observation_api_used"])
        self.assertEqual(summary["publisher_frame_qoe_debt"], 0.0)
        self.assertTrue(summary["authenticated_native_qoe_debt_derivation_claim"])
        self.assertTrue(summary["native_qoe_debt_admission_effect_claim"])
        self.assertTrue(summary["native_qoe_debt_provenance_claim"])
        self.assertTrue(summary["path_only_contrast_claim"])
        self.assertEqual(
            summary["native_qoe_debt_kind"],
            "ewma_authenticated_quic_path_pressure_proxy",
        )
        self.assertFalse(summary["application_outcome_qoe_debt_claim"])
        self.assertFalse(summary["aioquic_public_path_metrics_api_claim"])
        self.assertFalse(summary["production_readiness"])
        for run in summary["runs"]:
            self.assertEqual(run["status"], "ok")
            self.assertEqual(run["path_only"]["probe"]["frame_qoe_debt"], 0.0)
            self.assertEqual(run["derived_qoe"]["probe"]["frame_qoe_debt"], 0.0)
            self.assertTrue(
                native_qoe_service_ok(
                    run["path_only"]["service"], derived_qoe=False
                )
            )
            self.assertTrue(
                native_qoe_service_ok(
                    run["derived_qoe"]["service"], derived_qoe=True
                )
            )

    def test_policy_service_and_probe_enforce_provenance(self) -> None:
        state = (ROOT / "fleetqox" / "quic_gateway_state.py").read_text()
        service = (ROOT / "scripts" / "fleetrmw_quic_gateway_service.py").read_text()
        probe = (
            ROOT
            / "ros2_ws"
            / "src"
            / "rmw_fleetqox_cpp"
            / "src"
            / "quic_native_path_observation_probe.cpp"
        ).read_text()
        self.assertIn('qoe_debt_source = "gateway_derived_path"', state)
        self.assertIn("native QoE debt requires mutual TLS client auth", service)
        self.assertIn("frame_qoe_debt", probe)


if __name__ == "__main__":
    unittest.main()

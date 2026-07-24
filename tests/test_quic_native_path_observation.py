import copy
import json
from pathlib import Path
import unittest

from scripts.run_rmw_docker_quic_native_path_observation_probe import (
    probe_ok,
    service_ok,
)


ROOT = Path(__file__).resolve().parents[1]
ARTIFACT = (
    ROOT
    / "results_rmw_socket"
    / "docker_quic_native_path_observation_probe_summary.json"
)


class QuicNativePathObservationTest(unittest.TestCase):
    def test_validators_reject_external_or_unmeasured_observation(self) -> None:
        summary = json.loads(ARTIFACT.read_text(encoding="utf-8"))
        native = summary["runs"][0]["native"]
        self.assertTrue(probe_ok(native["probe"], expect_success=True))
        self.assertTrue(service_ok(native["service"], native=True))

        mutated = copy.deepcopy(native["service"])
        mutated["metrics"]["observation_requests"] = 1
        self.assertFalse(service_ok(mutated, native=True))
        mutated = copy.deepcopy(native["service"])
        mutated["metrics"]["admission"]["observation_updates_by_source"] = {
            "external_api": 1
        }
        self.assertFalse(service_ok(mutated, native=True))
        mutated = copy.deepcopy(native["service"])
        mutated["transport_metrics"]["native_path_latest_rtt_ms"] = 0.0
        self.assertFalse(service_ok(mutated, native=True))

    def test_canonical_mtls_docker_netem_contrast_passes_five_runs(self) -> None:
        summary = json.loads(ARTIFACT.read_text(encoding="utf-8"))
        self.assertEqual(summary["status"], "ok")
        self.assertEqual(summary["run_count"], 5)
        self.assertEqual(summary["successful_runs"], 5)
        self.assertEqual(summary["container_count_per_run"], 4)
        self.assertTrue(summary["real_quic_v1_h3"])
        self.assertTrue(summary["mutual_tls_client_authentication_required"])
        self.assertTrue(summary["publisher_identity_binding_required"])
        self.assertFalse(summary["external_observation_api_used"])
        self.assertTrue(summary["native_quic_path_observation_claim"])
        self.assertTrue(summary["native_rtt_admission_effect_claim"])
        self.assertTrue(summary["baseline_contrast_claim"])
        self.assertTrue(summary["aioquic_exact_version_pin_claim"])
        self.assertTrue(
            summary["aioquic_private_path_observer_fingerprint_claim"]
        )
        self.assertFalse(summary["aioquic_public_path_metrics_api_claim"])
        self.assertEqual(
            summary["jitter_measurement_kind"],
            "quic_recovery_rtt_variance_proxy",
        )
        self.assertFalse(summary["production_readiness"])
        for run in summary["runs"]:
            self.assertEqual(run["status"], "ok")
            self.assertTrue(service_ok(run["baseline"]["service"], native=False))
            self.assertTrue(service_ok(run["native"]["service"], native=True))
            self.assertTrue(
                probe_ok(run["baseline"]["probe"], expect_success=False)
            )
            self.assertTrue(probe_ok(run["native"]["probe"], expect_success=True))

    def test_adapter_service_and_cpp_probe_are_wired(self) -> None:
        service = (ROOT / "scripts" / "fleetrmw_quic_gateway_service.py").read_text()
        adapter = (ROOT / "fleetqox" / "aioquic_path_observer.py").read_text()
        probe = (
            ROOT
            / "ros2_ws"
            / "src"
            / "rmw_fleetqox_cpp"
            / "src"
            / "quic_native_path_observation_probe.cpp"
        ).read_text()
        self.assertIn("install_aioquic_path_observer", service)
        self.assertIn("update_native_path_observation", service)
        self.assertIn('source="quic_session_native"', (ROOT / "fleetqox" / "quic_gateway_state.py").read_text())
        self.assertIn("private_recovery_observer", adapter)
        self.assertIn("external_observation_request_sent", probe)


if __name__ == "__main__":
    unittest.main()

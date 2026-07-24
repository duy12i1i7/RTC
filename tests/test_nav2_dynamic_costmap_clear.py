import copy
import json
from pathlib import Path
import unittest

from scripts.run_rmw_docker_nav2_dynamic_costmap_clear_probe import (
    params_yaml,
    probe_node_py,
    runtime_evidence_ok,
)


ROOT = Path(__file__).resolve().parents[1]
ARTIFACT = (
    ROOT
    / "results_rmw_socket"
    / "docker_nav2_dynamic_costmap_clear_summary.json"
)
CAPABILITIES = (
    ROOT / "ros2_ws" / "src" / "rmw_fleetqox_cpp" / "capabilities.json"
)


def valid_client() -> dict:
    return {
        "status": "ok",
        "lifecycle_configure_response": True,
        "lifecycle_activate_response": True,
        "dynamic_obstacle_marked": True,
        "clear_service_requested": True,
        "clear_service_response": True,
        "costmap_cleared_after_service": True,
        "max_cost_before_clear": 254,
        "occupied_cells_before_clear": 3,
        "max_cost_after_clear": 0,
        "occupied_cells_after_clear": 0,
        "scan_messages_published": 100,
        "tf_messages_published": 100,
    }


def valid_router() -> dict:
    return {
        "status": "ok",
        "graph_advertisements": 3,
        "service_frames": 6,
        "invalid_frames": 0,
    }


class Nav2DynamicCostmapClearTest(unittest.TestCase):
    def test_probe_uses_real_obstacle_layer_laser_scan_and_clear_service(
        self,
    ) -> None:
        parameters = params_yaml()
        probe = probe_node_py()
        self.assertIn("nav2_costmap_2d::ObstacleLayer", parameters)
        self.assertIn('data_type: "LaserScan"', parameters)
        self.assertIn("marking: true", parameters)
        self.assertIn("clearing: false", parameters)
        self.assertIn("ClearEntireCostmap", probe)
        self.assertIn("/local_costmap/clear_entirely_costmap", probe)
        self.assertIn("Transition.TRANSITION_CONFIGURE", probe)
        self.assertIn("Transition.TRANSITION_ACTIVATE", probe)

    def test_validator_requires_mark_clear_and_router_transport(self) -> None:
        client = valid_client()
        router = valid_router()
        self.assertTrue(
            runtime_evidence_ok(client, router, docker_returncode=0)
        )
        for key, value in (
            ("dynamic_obstacle_marked", False),
            ("clear_service_response", False),
            ("occupied_cells_before_clear", 0),
            ("max_cost_after_clear", 1),
            ("occupied_cells_after_clear", 1),
        ):
            mutated = copy.deepcopy(client)
            mutated[key] = value
            self.assertFalse(
                runtime_evidence_ok(mutated, router, docker_returncode=0),
                key,
            )
        mutated_router = copy.deepcopy(router)
        mutated_router["service_frames"] = 5
        self.assertFalse(
            runtime_evidence_ok(client, mutated_router, docker_returncode=0)
        )
        mutated_router = copy.deepcopy(router)
        mutated_router["invalid_frames"] = 1
        self.assertFalse(
            runtime_evidence_ok(client, mutated_router, docker_returncode=0)
        )

    def test_capability_manifest_preserves_production_boundaries(self) -> None:
        capabilities = json.loads(CAPABILITIES.read_text(encoding="utf-8"))
        supported = capabilities["supported"]
        claims = capabilities["claim_boundaries"]
        self.assertTrue(supported["nav2_dynamic_laser_scan_obstacle_layer"])
        self.assertTrue(supported["nav2_clear_entire_costmap_service"])
        self.assertTrue(supported["docker_nav2_dynamic_costmap_clear"])
        self.assertTrue(claims["docker_nav2_dynamic_costmap_clear"])
        self.assertTrue(claims["nav2_dynamic_costmap_mark_clear_claim"])
        self.assertFalse(claims["full_dynamic_obstacle_navigation_claim"])
        self.assertFalse(
            claims["production_costmap_recovery_policy_claim"]
        )
        self.assertFalse(capabilities["production_ready"])

    @unittest.skipUnless(ARTIFACT.exists(), "canonical Docker artifact absent")
    def test_canonical_docker_netem_artifact(self) -> None:
        summary = json.loads(ARTIFACT.read_text(encoding="utf-8"))
        self.assertEqual(
            summary["schema_version"],
            "fleetrmw.docker_nav2_dynamic_costmap_clear_probe.v1",
        )
        self.assertEqual(summary["status"], "ok")
        self.assertTrue(summary["dynamic_costmap_mark_clear_claim"])
        self.assertEqual(summary["max_cost_before_clear"], 254)
        self.assertGreater(summary["occupied_cells_before_clear"], 0)
        self.assertEqual(summary["max_cost_after_clear"], 0)
        self.assertEqual(summary["occupied_cells_after_clear"], 0)
        self.assertEqual(summary["fleetqox_router_invalid_frames"], 0)
        self.assertFalse(summary["full_dynamic_obstacle_navigation_claim"])
        self.assertFalse(
            summary["production_costmap_recovery_policy_claim"]
        )


if __name__ == "__main__":
    unittest.main()

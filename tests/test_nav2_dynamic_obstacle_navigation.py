import copy
import json
from pathlib import Path
import unittest

from scripts.run_rmw_docker_nav2_dynamic_obstacle_navigation_probe import (
    dynamic_nav2_params_yaml,
    runtime_evidence_ok,
    scenario_node_py,
)


ROOT = Path(__file__).resolve().parents[1]
ARTIFACT = (
    ROOT
    / "results_rmw_socket"
    / "docker_nav2_dynamic_obstacle_navigation_summary.json"
)
CAPABILITIES = (
    ROOT / "ros2_ws" / "src" / "rmw_fleetqox_cpp" / "capabilities.json"
)
ROUTER_SOURCE = (
    ROOT
    / "ros2_ws"
    / "src"
    / "rmw_fleetqox_cpp"
    / "src"
    / "udp_router_probe.cpp"
)


def valid_scenario() -> dict:
    return {
        "status": "ok",
        "lifecycle_configure_ok": True,
        "lifecycle_activate_ok": True,
        "negative_control_ok": True,
        "persistent_obstacle_remarked_after_clear": True,
        "persistent_no_progress_after_clear": True,
        "negative_terminal_safe": True,
        "recovery_case_ok": True,
        "recovery_obstacle_marked": True,
        "recovery_robot_stopped": True,
        "recovery_clear_response": True,
        "recovery_resumed_after_clear": True,
        "recovery_result_status": 4,
        "recovery_goal_succeeded": True,
        "clear_call_count": 3,
        "max_cost_observed": 254,
        "scan_messages_published": 100,
    }


def valid_router() -> dict:
    return {
        "status": "ok",
        "service_frames": 100,
        "invalid_frames": 0,
        "unrecoverable_loss_notice_frames": 2,
        "unrecoverable_loss_notice_forwarded": 2,
    }


class Nav2DynamicObstacleNavigationTest(unittest.TestCase):
    def test_scenario_uses_real_nav2_action_costmap_and_bounded_policy(
        self,
    ) -> None:
        parameters = dynamic_nav2_params_yaml("/tmp/tree.xml")
        scenario = scenario_node_py()
        self.assertIn("nav2_costmap_2d::ObstacleLayer", parameters)
        self.assertIn("nav2_costmap_2d::InflationLayer", parameters)
        self.assertIn("failure_tolerance: 5.0", parameters)
        self.assertIn("default_server_timeout: 1000", parameters)
        self.assertIn("NavigateToPose", scenario)
        self.assertIn("/local_costmap/clear_entirely_local_costmap", scenario)
        self.assertIn("persistent_obstacle_remarked_after_clear", scenario)
        self.assertIn("recovery_resumed_after_clear", scenario)

    def test_validator_rejects_missing_negative_recovery_or_router_gate(
        self,
    ) -> None:
        scenario = valid_scenario()
        router = valid_router()
        self.assertTrue(
            runtime_evidence_ok(scenario, router, docker_returncode=0)
        )
        for key, value in (
            ("negative_control_ok", False),
            ("persistent_obstacle_remarked_after_clear", False),
            ("recovery_robot_stopped", False),
            ("recovery_clear_response", False),
            ("recovery_resumed_after_clear", False),
            ("recovery_goal_succeeded", False),
            ("clear_call_count", 4),
        ):
            mutated = copy.deepcopy(scenario)
            mutated[key] = value
            self.assertFalse(
                runtime_evidence_ok(mutated, router, docker_returncode=0),
                key,
            )
        mutated_router = copy.deepcopy(router)
        mutated_router["invalid_frames"] = 1
        self.assertFalse(
            runtime_evidence_ok(scenario, mutated_router, docker_returncode=0)
        )
        for key in (
            "unrecoverable_loss_notice_frames",
            "unrecoverable_loss_notice_forwarded",
        ):
            mutated_router = copy.deepcopy(router)
            mutated_router[key] = 0
            self.assertFalse(
                runtime_evidence_ok(
                    scenario,
                    mutated_router,
                    docker_returncode=0,
                ),
                key,
            )

    def test_router_recognizes_and_routes_terminal_loss_notices(self) -> None:
        source = ROUTER_SOURCE.read_text(encoding="utf-8")
        decode_position = source.index(
            "decode_unrecoverable_loss_notice(encoded_frame)"
        )
        invalid_position = source.index("++invalid;", decode_position)
        self.assertLess(decode_position, invalid_position)
        self.assertIn(
            '\\"unrecoverable_loss_notice_frames\\":',
            source,
        )
        self.assertIn(
            '\\"unrecoverable_loss_notice_forwarded\\":',
            source,
        )
        self.assertIn("route.topic == loss_notice->topic", source)
        self.assertIn("route.domain_id == loss_notice->domain_id", source)

    def test_capability_manifest_keeps_broad_claims_scoped(self) -> None:
        capabilities = json.loads(CAPABILITIES.read_text(encoding="utf-8"))
        supported = capabilities["supported"]
        claims = capabilities["claim_boundaries"]
        self.assertTrue(
            supported["udp_router_unrecoverable_loss_notice_passthrough"]
        )
        self.assertTrue(
            supported["nav2_dynamic_obstacle_stop_clear_resume"]
        )
        self.assertTrue(
            supported["docker_nav2_dynamic_obstacle_navigation"]
        )
        self.assertTrue(
            claims["udp_router_unrecoverable_loss_notice_forwarding_claim"]
        )
        self.assertTrue(
            claims["navigate_to_pose_dynamic_obstacle_clear_resume_claim"]
        )
        self.assertTrue(
            claims["persistent_obstacle_negative_control_claim"]
        )
        self.assertFalse(claims["dynamic_obstacle_detour_avoidance_claim"])
        self.assertFalse(
            claims["production_costmap_recovery_policy_claim"]
        )
        self.assertFalse(capabilities["production_ready"])

    @unittest.skipUnless(ARTIFACT.exists(), "canonical Docker artifact absent")
    def test_canonical_docker_netem_artifact(self) -> None:
        summary = json.loads(ARTIFACT.read_text(encoding="utf-8"))
        self.assertEqual(
            summary["schema_version"],
            "fleetrmw.docker_nav2_dynamic_obstacle_navigation_probe.v1",
        )
        self.assertEqual(summary["status"], "ok")
        self.assertTrue(summary["persistent_obstacle_negative_control_claim"])
        self.assertTrue(
            summary["navigate_to_pose_dynamic_obstacle_clear_resume_claim"]
        )
        self.assertEqual(summary["negative_result_status"], 5)
        self.assertEqual(summary["recovery_result_status"], 4)
        self.assertTrue(summary["recovery_goal_succeeded"])
        self.assertEqual(summary["fleetqox_router_invalid_frames"], 0)
        self.assertGreater(
            summary["unrecoverable_loss_notice_forwarded"],
            0,
        )
        self.assertFalse(summary["dynamic_obstacle_detour_avoidance_claim"])
        self.assertFalse(
            summary["production_costmap_recovery_policy_claim"]
        )


if __name__ == "__main__":
    unittest.main()

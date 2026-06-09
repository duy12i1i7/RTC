import unittest

from scripts.run_ros2_local_controller_lease import (
    robot_ids_for_args as lease_robot_ids_for_args,
    topic_for_robot as lease_topic_for_robot,
)
from scripts.run_ros2_projection_quality_gate import (
    robot_ids_for_args as gate_robot_ids_for_args,
    topic_for_robot as gate_topic_for_robot,
)
from scripts.run_ros2_string_monitor import expand_topics_for_robots


class Ros2NamespaceExpansionTest(unittest.TestCase):
    def test_robot_ids_preserve_single_robot_base_id(self) -> None:
        self.assertEqual(lease_robot_ids_for_args("tb4_a", 1), ["tb4_a"])
        self.assertEqual(gate_robot_ids_for_args("tb4_a", 1), ["tb4_a"])

    def test_robot_ids_expand_to_stable_fleet_names(self) -> None:
        self.assertEqual(
            lease_robot_ids_for_args("robot_0000", 3),
            ["robot_0000", "robot_0001", "robot_0002"],
        )
        self.assertEqual(
            gate_robot_ids_for_args("robot_0000", 2),
            ["robot_0000", "robot_0001"],
        )

    def test_local_controller_topic_expansion_supports_format_token(self) -> None:
        topic = lease_topic_for_robot(
            "/fleetrmw/{robot_id}/local_cmd_vel",
            default_template="/fleetrmw/{robot_id}/local_cmd_vel",
            base_robot_id="robot_0000",
            robot_id="robot_0002",
        )

        self.assertEqual(topic, "/fleetrmw/robot_0002/local_cmd_vel")

    def test_quality_gate_topic_expansion_replaces_base_namespace(self) -> None:
        topic = gate_topic_for_robot(
            "/fleetrmw/robot_0000/accepted_scan",
            default_template="/fleetrmw/{robot_id}/accepted_scan",
            base_robot_id="robot_0000",
            robot_id="robot_0001",
        )

        self.assertEqual(topic, "/fleetrmw/robot_0001/accepted_scan")

    def test_monitor_expands_and_deduplicates_topic_lists(self) -> None:
        topics = expand_topics_for_robots(
            [
                "/fleetrmw/robot_0000/control_lease",
                "/fleetrmw/{robot_id}/control_lease",
            ],
            "robot_0000",
            2,
        )

        self.assertEqual(
            topics,
            [
                "/fleetrmw/robot_0000/control_lease",
                "/fleetrmw/robot_0001/control_lease",
            ],
        )


if __name__ == "__main__":
    unittest.main()

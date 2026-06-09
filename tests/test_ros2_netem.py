import unittest
import json

from fleetqox.ros2_netem import build_ros2_netem_plan
from fleetqox.testbed import iter_scenarios, load_manifest


class Ros2NetemTest(unittest.TestCase):
    def test_build_ros2_netem_plan(self) -> None:
        manifest = load_manifest("experiments/testbed_manifest.json")
        scenario = next(item for item in iter_scenarios(manifest) if item.tier == "T2E")

        plan = build_ros2_netem_plan(scenario, rmw="rmw_fastrtps_cpp")

        self.assertIn("ros2 run performance_test perf_test", plan.publisher_command)
        self.assertIn("--num-pub-threads 1", plan.publisher_command)
        self.assertIn("--num-sub-threads 1", plan.subscriber_command)
        self.assertIn("--logfile", plan.subscriber_command)
        self.assertNotIn("--logfile", plan.publisher_command)
        self.assertEqual(plan.topology, "dds_bridge")
        self.assertEqual(plan.env["RMW_IMPLEMENTATION"], "rmw_fastrtps_cpp")
        self.assertIn("NETEM_DELAY_MS", plan.env)

    def test_build_ros2_netem_plan_with_overrides_and_run_label(self) -> None:
        manifest = load_manifest("experiments/testbed_manifest.json")
        scenario = next(item for item in iter_scenarios(manifest) if item.tier == "T2E")

        plan = build_ros2_netem_plan(
            scenario,
            rmw="rmw_cyclonedds_cpp",
            component="state",
            run_label="r002",
            runtime_s=5,
            rate_hz=25,
        )

        self.assertEqual(plan.run_label, "r002")
        self.assertEqual(plan.rate_hz, 25)
        self.assertEqual(plan.runtime_s, 5)
        self.assertIn("state/r002.csv", str(plan.result_log))
        self.assertIn("--rate 25", plan.subscriber_command)
        self.assertIn("--max-runtime 5", plan.publisher_command)

    def test_zenoh_plan_uses_router_topology_by_default(self) -> None:
        manifest = load_manifest("experiments/testbed_manifest.json")
        scenario = next(item for item in iter_scenarios(manifest) if item.tier == "T2E")

        plan = build_ros2_netem_plan(scenario, rmw="rmw_zenoh_cpp")

        self.assertEqual(plan.topology, "zenoh_router")
        self.assertEqual(
            plan.env["ZENOH_SESSION_CONFIG_URI"],
            "/work/external/ros2-netem/zenoh/session-router.json5",
        )

    def test_zenoh_plan_can_use_peer_topology(self) -> None:
        manifest = load_manifest("experiments/testbed_manifest.json")
        scenario = next(item for item in iter_scenarios(manifest) if item.tier == "T2E")

        plan = build_ros2_netem_plan(scenario, rmw="rmw_zenoh_cpp", zenoh_topology="peer")

        self.assertEqual(plan.topology, "zenoh_peer")
        self.assertNotIn("ZENOH_SESSION_CONFIG_URI", plan.env)

    def test_apex_metadata_is_string_only(self) -> None:
        manifest = load_manifest("experiments/testbed_manifest.json")
        scenario = next(item for item in iter_scenarios(manifest) if item.tier == "T2E")

        plan = build_ros2_netem_plan(scenario, rmw="rmw_fastrtps_cpp", runtime_s=5)
        metadata = json.loads(plan.env["APEX_PERFORMANCE_TEST_SUB"])

        self.assertNotIn("run_label", metadata)
        self.assertTrue(all(isinstance(value, str) for value in metadata.values()))


if __name__ == "__main__":
    unittest.main()

import unittest

from fleetqox.ros2_netem import build_ros2_netem_plan
from fleetqox.testbed import iter_scenarios, load_manifest
from scripts.run_t2e_ros2_netem import compose_files_for_plan, expand_csv, resolve_components, resolve_rmws


class T2ERunnerTest(unittest.TestCase):
    def test_expand_csv(self) -> None:
        self.assertEqual(expand_csv(["a,b", "c"]), ["a", "b", "c"])

    def test_resolve_rmws(self) -> None:
        self.assertEqual(resolve_rmws(["rmw_a,rmw_b"], all_rmws=False), ["rmw_a", "rmw_b"])
        self.assertIn("rmw_zenoh_cpp", resolve_rmws(None, all_rmws=True))

    def test_resolve_components(self) -> None:
        self.assertEqual(resolve_components(["control"], "state,sensor"), ["control", "state", "sensor"])

    def test_compose_files_include_zenoh_overlay_for_router_topology(self) -> None:
        manifest = load_manifest("experiments/testbed_manifest.json")
        scenario = next(item for item in iter_scenarios(manifest) if item.tier == "T2E")
        plan = build_ros2_netem_plan(scenario, rmw="rmw_zenoh_cpp")

        compose_args = compose_files_for_plan(plan)

        self.assertIn("external/ros2-netem/docker-compose.zenoh.yml", compose_args)


if __name__ == "__main__":
    unittest.main()

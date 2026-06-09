import unittest

from fleetqox.fleet_scale import (
    capacity_for_robots,
    run_fleet_scale_matrix,
    summarize_fleet_scale,
)
from fleetqox.simulator import run_benchmark


class FleetScaleTest(unittest.TestCase):
    def test_shared_cell_capacity_is_sublinear_after_knee(self) -> None:
        at_knee = capacity_for_robots(25)
        larger = capacity_for_robots(50)

        self.assertGreater(larger, at_knee)
        self.assertLess(larger - at_knee, at_knee)

    def test_matrix_summary_groups_by_robot_and_policy(self) -> None:
        policies = len(run_benchmark(robots=5, seconds=1, seed=7))
        records = run_fleet_scale_matrix([5], [7, 13], seconds=1)
        summary = summarize_fleet_scale(records)

        self.assertEqual(len(records), policies * 2)
        self.assertEqual(len(summary["ranking"]), policies)
        self.assertEqual(summary["winners"][0]["robots"], 5)

    def test_qoe_delivery_ratio_is_bounded(self) -> None:
        results = run_benchmark(robots=20, seconds=2, seed=7)

        self.assertTrue(all(0.0 <= result.qoe_delivery_ratio <= 1.0 for result in results))
        self.assertTrue(any(result.name == "fleetqox_predictive" for result in results))


if __name__ == "__main__":
    unittest.main()

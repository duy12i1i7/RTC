import unittest

from fleetqox.testbed import iter_scenarios, load_manifest


class TestbedManifestTest(unittest.TestCase):
    def test_manifest_loads_and_contains_all_tiers(self) -> None:
        manifest = load_manifest("experiments/testbed_manifest.json")
        scenarios = iter_scenarios(manifest)
        tiers = {scenario.tier for scenario in scenarios}

        self.assertEqual({"T0", "T1", "T2E", "T2S", "T3", "T4"}, tiers)
        self.assertGreaterEqual(len(scenarios), 10)

    def test_t0_is_runnable_locally(self) -> None:
        manifest = load_manifest("experiments/testbed_manifest.json")
        t0 = [scenario for scenario in iter_scenarios(manifest) if scenario.tier == "T0"]

        self.assertTrue(t0)
        self.assertTrue(all(scenario.runner == "local_python" for scenario in t0))


if __name__ == "__main__":
    unittest.main()

import unittest
from pathlib import Path

from scripts.run_sidecar_netem import (
    _relative_to_cwd,
    feeder_module_for,
    lagrangian_env_overrides,
    resolve_policies,
    run_name_for,
)


class SidecarNetemRunnerTest(unittest.TestCase):
    def test_relative_to_cwd(self) -> None:
        cwd = Path("/tmp/project")
        path = cwd / "results" / "x.jsonl"

        self.assertEqual(_relative_to_cwd(path, cwd), "results/x.jsonl")

    def test_resolve_policies(self) -> None:
        self.assertEqual(resolve_policies(None, False), ["fleetqox_predictive"])
        self.assertEqual(
            resolve_policies(["fifo", "fifo", "fleetqox_csds"], False),
            ["fifo", "fleetqox_csds"],
        )
        self.assertIn("static_priority", resolve_policies(None, True))
        self.assertIn("fleetqox_predictive_profiled", resolve_policies(None, True))
        self.assertIn("fleetqox_predictive_contextual", resolve_policies(None, True))
        self.assertIn("fleetqox_predictive_intent", resolve_policies(None, True))
        self.assertIn("fleetqox_semantic_contract", resolve_policies(None, True))
        self.assertIn("fleetqox_semantic_contract_lossaware", resolve_policies(None, True))
        self.assertIn("fleetqox_semantic_contract_adaptive", resolve_policies(None, True))

    def test_run_name_for_matrix(self) -> None:
        self.assertEqual(run_name_for("s", "fifo", False), "s")
        self.assertEqual(run_name_for("s", "fifo", True), "s_fifo")

    def test_feeder_module_for_closed_loop(self) -> None:
        self.assertEqual(feeder_module_for(False), "scripts.feed_sidecar_synthetic")
        self.assertEqual(feeder_module_for(True), "scripts.feed_sidecar_closed_loop")

    def test_lagrangian_env_overrides_only_for_lagrangian_policy(self) -> None:
        args = type(
            "Args",
            (),
            {
                "policy_label": "lag_015",
                "lagrangian_deadline_risk_budget": 0.08,
                "lagrangian_initial_deadline_lambda": 1.8,
                "lagrangian_risk_barrier_start": 0.7,
                "lagrangian_risk_barrier_scale": 12.0,
                "lagrangian_deadline_drop_risk": 0.45,
            },
        )()

        self.assertEqual(lagrangian_env_overrides(args, "fleetqox_csds"), {})
        env = lagrangian_env_overrides(args, "fleetqox_predictive_lagrangian")
        self.assertEqual(env["SIDECAR_POLICY_LABEL"], "lag_015")
        self.assertEqual(env["SIDECAR_LAGRANGIAN_DEADLINE_DROP_RISK"], "0.45")


if __name__ == "__main__":
    unittest.main()

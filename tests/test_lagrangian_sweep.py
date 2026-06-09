import unittest

from fleetqox.lagrangian_sweep import (
    build_lagrangian_configs,
    dominates,
    render_lagrangian_sweep_markdown,
    summarize_lagrangian_sweep,
)
from scripts.run_lagrangian_sweep import parse_floats, parse_ints


class LagrangianSweepTest(unittest.TestCase):
    def test_build_lagrangian_configs_creates_cartesian_grid(self) -> None:
        configs = build_lagrangian_configs(
            deadline_risk_budgets=[0.04, 0.08],
            initial_deadline_lambdas=[1.8],
            risk_barrier_starts=[0.62, 0.70],
            risk_barrier_scales=[12.0],
        )

        self.assertEqual(len(configs), 4)
        self.assertEqual(configs[0][0], "lag_000")
        self.assertEqual(configs[-1][1].risk_barrier_start, 0.70)

    def test_summarize_sweep_ranks_constraint_hits(self) -> None:
        records = [
            _record("safe", "fleetqox_lagrangian", 5.0, 0.01, 0.7),
            _record("unsafe", "fleetqox_lagrangian", 6.0, 0.20, 0.8),
            _record("baseline", "fleetqox_predictive", 4.5, 0.02, 0.7),
        ]

        summary = summarize_lagrangian_sweep(records, control_miss_target=0.05)

        self.assertEqual(summary["ranking"][0]["candidate_id"], "safe")
        self.assertTrue(summary["ranking"][0]["constraint_satisfied"])
        self.assertFalse(
            next(row for row in summary["ranking"] if row["candidate_id"] == "unsafe")[
                "constraint_satisfied"
            ]
        )

    def test_dominates_respects_qoe_and_deadline_objectives(self) -> None:
        left = {
            "utility_score_mean": 5.0,
            "qoe_delivery_ratio_mean": 0.8,
            "control_deadline_miss_ratio_mean": 0.01,
            "stale_state_ratio_mean": 0.0,
            "defer_ratio_mean": 0.1,
            "drop_ratio_mean": 0.0,
        }
        right = {
            "utility_score_mean": 4.0,
            "qoe_delivery_ratio_mean": 0.8,
            "control_deadline_miss_ratio_mean": 0.02,
            "stale_state_ratio_mean": 0.0,
            "defer_ratio_mean": 0.1,
            "drop_ratio_mean": 0.0,
        }

        self.assertTrue(dominates(left, right))
        self.assertFalse(dominates(right, left))

    def test_render_markdown(self) -> None:
        summary = summarize_lagrangian_sweep(
            [_record("safe", "fleetqox_lagrangian", 5.0, 0.01, 0.7)]
        )

        report = render_lagrangian_sweep_markdown(summary, title="Sweep")

        self.assertIn("# Sweep", report)
        self.assertIn("Pareto Frontier", report)

    def test_cli_parsers(self) -> None:
        self.assertEqual(parse_ints("10,25", "--robots"), [10, 25])
        self.assertEqual(parse_floats("0.04, 0.08", "--x"), [0.04, 0.08])


def _record(
    candidate_id: str,
    policy: str,
    utility: float,
    control_miss: float,
    qoe: float,
) -> dict[str, object]:
    return {
        "candidate_id": candidate_id,
        "policy": policy,
        "params": {},
        "robots": 10,
        "seed": 7,
        "utility_score": utility,
        "control_deadline_miss_ratio": control_miss,
        "qoe_delivery_ratio": qoe,
        "stale_state_ratio": 0.0,
        "defer_ratio": 0.1,
        "drop_ratio": 0.0,
        "degraded_ratio": 0.0,
        "compacted_ratio": 0.2,
        "bytes_sent": 100,
        "sent": 10,
    }


if __name__ == "__main__":
    unittest.main()

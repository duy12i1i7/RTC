import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from fleetqox.lagrangian_adaptation import (
    OutcomeTargets,
    adapt_from_repeated_summary,
    load_variant_manifest,
    select_source_variant,
)


class LagrangianAdaptationTest(unittest.TestCase):
    def test_select_source_variant_prefers_pareto_lagrangian(self) -> None:
        summary = _summary()
        variants = {"lag_012": _params(), "lag_015": _params(risk_barrier_start=0.7)}

        source = select_source_variant(summary, variants)

        self.assertEqual(source, "lag_012")

    def test_adapt_from_repeated_summary_tightens_when_miss_exceeds_target(self) -> None:
        adaptation = adapt_from_repeated_summary(
            _summary(),
            {"lag_012": _params()},
            next_label="lag_adapt_001",
            targets=OutcomeTargets(deadline_miss_ratio=0.002, control_starvation_events=2),
        )

        self.assertEqual(adaptation["source_label"], "lag_012")
        self.assertGreater(
            adaptation["next_params"]["initial_deadline_lambda"],
            adaptation["source_params"]["initial_deadline_lambda"],
        )
        self.assertLess(
            adaptation["next_params"]["deadline_drop_risk"],
            adaptation["source_params"]["deadline_drop_risk"],
        )
        self.assertIn("--policy-label", adaptation["run_command"])

    def test_adapt_from_repeated_summary_can_force_source_label(self) -> None:
        summary = _summary()
        summary["policies"].append(
            {
                "policy": "lag_safe",
                "semantic_utility_delivered_mean": 6400.0,
                "control_starvation_events_mean": 0.0,
                "deadline_miss_ratio_mean": 0.0,
                "loss_ratio_mean": 0.009,
                "latency_p95_ms_mean": 27.2,
                "pareto_frontier": True,
            }
        )

        adaptation = adapt_from_repeated_summary(
            summary,
            {"lag_012": _params(), "lag_safe": _params()},
            source_label="lag_safe",
            next_label="lag_relaxed",
            targets=OutcomeTargets(deadline_miss_ratio=0.002, control_starvation_events=2),
        )

        self.assertEqual(adaptation["source_label"], "lag_safe")
        self.assertGreater(
            adaptation["next_params"]["deadline_drop_risk"],
            adaptation["source_params"]["deadline_drop_risk"],
        )

    def test_load_variant_manifest(self) -> None:
        with TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "variants.json"
            path.write_text(json.dumps({"variants": {"lag": _params()}}), encoding="utf-8")

            variants = load_variant_manifest(path)

        self.assertEqual(variants["lag"]["deadline_risk_budget"], 0.08)


def _summary() -> dict[str, object]:
    return {
        "policies": [
            {
                "policy": "fleetqox_predictive",
                "semantic_utility_delivered_mean": 8400.0,
                "control_starvation_events_mean": 5.0,
                "deadline_miss_ratio_mean": 0.003,
                "loss_ratio_mean": 0.011,
                "latency_p95_ms_mean": 27.3,
                "pareto_frontier": True,
            },
            {
                "policy": "lag_012",
                "semantic_utility_delivered_mean": 7200.0,
                "control_starvation_events_mean": 6.5,
                "deadline_miss_ratio_mean": 0.0053,
                "loss_ratio_mean": 0.008,
                "latency_p95_ms_mean": 27.2,
                "pareto_frontier": True,
            },
            {
                "policy": "lag_015",
                "semantic_utility_delivered_mean": 7480.0,
                "control_starvation_events_mean": 5.0,
                "deadline_miss_ratio_mean": 0.004,
                "loss_ratio_mean": 0.010,
                "latency_p95_ms_mean": 27.2,
                "pareto_frontier": False,
            },
        ]
    }


def _params(
    *,
    risk_barrier_start: float = 0.62,
) -> dict[str, float]:
    return {
        "deadline_risk_budget": 0.08,
        "initial_deadline_lambda": 1.8,
        "risk_barrier_start": risk_barrier_start,
        "risk_barrier_scale": 12.0,
        "deadline_drop_risk": 0.45,
    }


if __name__ == "__main__":
    unittest.main()

# Lagrangian Outcome Adaptation V1

## Source

- Source variant: `lag_012`
- Next variant: `lag_adapt_001`

## Metrics

| item | utility | control misses | deadline miss | loss | p95 ms |
| --- | --- | --- | --- | --- | --- |
| source | 7203.2 | 6.5000 | 0.0053 | 0.0081 | 27.25 |
| reference | 8383.9 | 5.0000 | 0.0036 | 0.0113 | 27.30 |

## Next Parameters

| parameter | source | delta | next |
| --- | --- | --- | --- |
| `deadline_risk_budget` | 0.0800 | -0.0157 | 0.0643 |
| `initial_deadline_lambda` | 1.8000 | 1.2000 | 3.0000 |
| `risk_barrier_start` | 0.6200 | -0.0787 | 0.5413 |
| `risk_barrier_scale` | 12.00 | 2.2618 | 14.26 |
| `deadline_drop_risk` | 0.4500 | -0.0670 | 0.3830 |

## Run Command

```bash
python3 -m scripts.run_sidecar_repeated_netem --run --scenario-prefix sidecar_lag_adapt_001_v1 --policy fleetqox_predictive_lagrangian --policy-label lag_adapt_001 --lagrangian-deadline-risk-budget 0.0642548 --lagrangian-initial-deadline-lambda 3 --lagrangian-risk-barrier-start 0.541274 --lagrangian-risk-barrier-scale 14.2618 --lagrangian-deadline-drop-risk 0.383019 --seeds 7,13 --closed-loop-feed
```

## Interpretation

- This is an outcome-driven trust-region update: measured deadline and starvation excess tighten the Lagrangian risk gate; safe low-utility results loosen it.
- The generated variant should be validated through Docker/netem before changing controller defaults.

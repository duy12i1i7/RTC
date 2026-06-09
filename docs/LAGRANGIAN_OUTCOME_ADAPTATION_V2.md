# Lagrangian Outcome Adaptation V2

## Source

- Source variant: `lag_adapt_001`
- Next variant: `lag_adapt_002`

## Metrics

| item | utility | control misses | deadline miss | loss | p95 ms |
| --- | --- | --- | --- | --- | --- |
| source | 6429.2 | 0.0000 | 0.0000 | 0.0090 | 27.25 |
| reference | 8383.9 | 5.0000 | 0.0036 | 0.0113 | 27.30 |

## Next Parameters

| parameter | source | delta | next |
| --- | --- | --- | --- |
| `deadline_risk_budget` | 0.0643 | 0.0087 | 0.0729 |
| `initial_deadline_lambda` | 3.0000 | -0.2166 | 2.7834 |
| `risk_barrier_start` | 0.5413 | 0.0237 | 0.5649 |
| `risk_barrier_scale` | 14.26 | -0.8663 | 13.40 |
| `deadline_drop_risk` | 0.3830 | 0.0237 | 0.4067 |

## Run Command

```bash
python3 -m scripts.run_sidecar_repeated_netem --run --scenario-prefix sidecar_lag_adapt_002_v1 --policy fleetqox_predictive_lagrangian --policy-label lag_adapt_002 --lagrangian-deadline-risk-budget 0.0729177 --lagrangian-initial-deadline-lambda 2.78343 --lagrangian-risk-barrier-start 0.564931 --lagrangian-risk-barrier-scale 13.3955 --lagrangian-deadline-drop-risk 0.406676 --seeds 7,13 --closed-loop-feed
```

## Interpretation

- This is an outcome-driven trust-region update: measured deadline and starvation excess tighten the Lagrangian risk gate; safe low-utility results loosen it.
- The generated variant should be validated through Docker/netem before changing controller defaults.

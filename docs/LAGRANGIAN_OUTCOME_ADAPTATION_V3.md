# Lagrangian Outcome Adaptation V3

## Source

- Source variant: `lag_adapt_002`
- Next variant: `lag_adapt_003`

## Metrics

| item | utility | control misses | deadline miss | loss | p95 ms |
| --- | --- | --- | --- | --- | --- |
| source | 6729.7 | 0.0000 | 0.0000 | 0.0093 | 27.26 |
| reference | 8503.2 | 7.4000 | 0.0052 | 0.0121 | 27.38 |

## Next Parameters

| parameter | source | delta | next |
| --- | --- | --- | --- |
| `deadline_risk_budget` | 0.0729 | 0.0082 | 0.0811 |
| `initial_deadline_lambda` | 2.7834 | -0.2043 | 2.5791 |
| `risk_barrier_start` | 0.5649 | 0.0224 | 0.5874 |
| `risk_barrier_scale` | 13.40 | -0.8171 | 12.58 |
| `deadline_drop_risk` | 0.4067 | 0.0224 | 0.4291 |

## Run Command

```bash
python3 -m scripts.run_sidecar_repeated_netem --run --scenario-prefix sidecar_lag_adapt_003_v1 --policy fleetqox_predictive_lagrangian --policy-label lag_adapt_003 --lagrangian-deadline-risk-budget 0.0810891 --lagrangian-initial-deadline-lambda 2.57914 --lagrangian-risk-barrier-start 0.58736 --lagrangian-risk-barrier-scale 12.5784 --lagrangian-deadline-drop-risk 0.429105 --seeds 7,13 --closed-loop-feed
```

## Interpretation

- This is an outcome-driven trust-region update: measured deadline and starvation excess tighten the Lagrangian risk gate; safe low-utility results loosen it.
- The generated variant should be validated through Docker/netem before changing controller defaults.

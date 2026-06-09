# Sidecar Lagrangian lag_012 Netem V1

## Inputs

- Metric rows: `2`
- Metrics: `results_sidecar_repeated/lag_variants_v1/sidecar_lag012_v1_seed_7_matrix_metrics.jsonl`
- Metrics: `results_sidecar_repeated/lag_variants_v1/sidecar_lag012_v1_seed_13_matrix_metrics.jsonl`

## Policy Summary

| policy | runs | pareto | utility | control misses | deadline miss | loss | p95 ms | rx | compacted rx |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `lag_012` | 2 | yes | 7203.2 +/- 470.3 | 6.5000 +/- 2.9400 | 0.0053 +/- 0.0025 | 0.0081 +/- 0.0017 | 27.25 +/- 0.2837 | 1221.5 +/- 16.66 | 963.0 +/- 49.00 |

## Pareto Frontier

- Non-dominated policies: `lag_012`.

## Interpretation

- Highest mean utility: `lag_012` at `7203.2`.
- Some policies have fewer than three runs; their confidence intervals are only a smoke-test signal, not statistical evidence.

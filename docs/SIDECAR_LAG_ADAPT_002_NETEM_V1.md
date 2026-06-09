# Sidecar Lagrangian lag_adapt_002 Netem V1

## Inputs

- Metric rows: `2`
- Metrics: `results_sidecar_repeated/lag_adaptation_v2/sidecar_lag_adapt_002_v1_seed_7_matrix_metrics.jsonl`
- Metrics: `results_sidecar_repeated/lag_adaptation_v2/sidecar_lag_adapt_002_v1_seed_13_matrix_metrics.jsonl`

## Policy Summary

| policy | runs | pareto | utility | control misses | deadline miss | loss | p95 ms | rx | compacted rx |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `lag_adapt_002` | 2 | yes | 6562.7 +/- 449.9 | 0.0000 +/- 0.0000 | 0.0000 +/- 0.0000 | 0.0080 +/- 0.0017 | 27.21 +/- 0.0053 | 1120.0 +/- 1.9600 | 874.5 +/- 32.34 |

## Pareto Frontier

- Non-dominated policies: `lag_adapt_002`.

## Interpretation

- Highest mean utility: `lag_adapt_002` at `6562.7`.
- Best zero-measured-miss policy: `lag_adapt_002` with utility `6562.7`.
- Some policies have fewer than three runs; their confidence intervals are only a smoke-test signal, not statistical evidence.

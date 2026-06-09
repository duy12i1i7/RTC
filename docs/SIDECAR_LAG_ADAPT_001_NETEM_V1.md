# Sidecar Lagrangian lag_adapt_001 Netem V1

## Inputs

- Metric rows: `2`
- Metrics: `results_sidecar_repeated/lag_adaptation_v1/sidecar_lag_adapt_001_v1_seed_7_matrix_metrics.jsonl`
- Metrics: `results_sidecar_repeated/lag_adaptation_v1/sidecar_lag_adapt_001_v1_seed_13_matrix_metrics.jsonl`

## Policy Summary

| policy | runs | pareto | utility | control misses | deadline miss | loss | p95 ms | rx | compacted rx |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `lag_adapt_001` | 2 | yes | 6429.2 +/- 431.6 | 0.0000 +/- 0.0000 | 0.0000 +/- 0.0000 | 0.0090 +/- 0.0053 | 27.25 +/- 0.0880 | 1099.0 +/- 3.9200 | 852.5 +/- 34.30 |

## Pareto Frontier

- Non-dominated policies: `lag_adapt_001`.

## Interpretation

- Highest mean utility: `lag_adapt_001` at `6429.2`.
- Best zero-measured-miss policy: `lag_adapt_001` with utility `6429.2`.
- Some policies have fewer than three runs; their confidence intervals are only a smoke-test signal, not statistical evidence.

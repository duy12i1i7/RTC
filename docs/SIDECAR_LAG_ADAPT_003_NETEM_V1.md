# Sidecar lag_adapt_003 Netem V1

## Inputs

- Metric rows: `2`
- Metrics: `results_sidecar_repeated/lag_adaptation_v3/sidecar_lag_adapt_003_v1_seed_7_matrix_metrics.jsonl`
- Metrics: `results_sidecar_repeated/lag_adaptation_v3/sidecar_lag_adapt_003_v1_seed_13_matrix_metrics.jsonl`

## Policy Summary

| policy | runs | pareto | utility | control misses | deadline miss | loss | p95 ms | rx | compacted rx |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `lag_adapt_003` | 2 | yes | 6739.4 +/- 478.2 | 0.0000 +/- 0.0000 | 0.0000 +/- 0.0000 | 0.0095 +/- 0.0050 | 27.31 +/- 0.0188 | 1149.0 +/- 0.0000 | 905.0 +/- 29.40 |

## Pareto Frontier

- Non-dominated policies: `lag_adapt_003`.

## Interpretation

- Highest mean utility: `lag_adapt_003` at `6739.4`.
- Best zero-measured-miss policy: `lag_adapt_003` with utility `6739.4`.
- Some policies have fewer than three runs; their confidence intervals are only a smoke-test signal, not statistical evidence.

# Sidecar lag_adapt_003 Extra Netem Seeds

## Inputs

- Metric rows: `3`
- Metrics: `results_sidecar_repeated/lag_adaptation_v3/sidecar_lag_adapt_003_v1_seed_29_matrix_metrics.jsonl`
- Metrics: `results_sidecar_repeated/lag_adaptation_v3/sidecar_lag_adapt_003_v1_seed_41_matrix_metrics.jsonl`
- Metrics: `results_sidecar_repeated/lag_adaptation_v3/sidecar_lag_adapt_003_v1_seed_53_matrix_metrics.jsonl`

## Policy Summary

| policy | runs | pareto | utility | control misses | deadline miss | loss | p95 ms | rx | compacted rx |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `lag_adapt_003` | 3 | yes | 7005.8 +/- 443.3 | 0.0000 +/- 0.0000 | 0.0000 +/- 0.0000 | 0.0103 +/- 0.0021 | 27.28 +/- 0.2738 | 1187.3 +/- 23.53 | 966.3 +/- 39.37 |

## Pareto Frontier

- Non-dominated policies: `lag_adapt_003`.

## Interpretation

- Highest mean utility: `lag_adapt_003` at `7005.8`.
- Best zero-measured-miss policy: `lag_adapt_003` with utility `7005.8`.

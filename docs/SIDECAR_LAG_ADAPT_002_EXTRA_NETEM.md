# Sidecar lag_adapt_002 Extra Netem Seeds

## Inputs

- Metric rows: `12`
- Metrics: `results_sidecar_repeated/lag_adaptation_v2/sidecar_lag_adapt_002_v1_seed_29_matrix_metrics.jsonl`
- Metrics: `results_sidecar_repeated/lag_adaptation_v2/sidecar_lag_adapt_002_v1_seed_41_matrix_metrics.jsonl`
- Metrics: `results_sidecar_repeated/lag_adaptation_v2/sidecar_lag_adapt_002_v1_seed_53_matrix_metrics.jsonl`

## Policy Summary

| policy | runs | pareto | utility | control misses | deadline miss | loss | p95 ms | rx | compacted rx |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `fleetqox_predictive` | 3 | yes | 8582.8 +/- 373.8 | 9.0000 +/- 1.1316 | 0.0063 +/- 0.0008 | 0.0127 +/- 0.0039 | 27.43 +/- 0.1925 | 1427.7 +/- 6.2324 | 1248.7 +/- 13.12 |
| `fleetqox_csds` | 3 | yes | 7968.9 +/- 449.2 | 6.0000 +/- 5.8800 | 0.0045 +/- 0.0045 | 0.0078 +/- 0.0036 | 27.09 +/- 0.1826 | 1316.0 +/- 8.1601 | 0.0000 +/- 0.0000 |
| `lag_adapt_002` | 3 | yes | 6841.0 +/- 418.4 | 0.0000 +/- 0.0000 | 0.0000 +/- 0.0000 | 0.0102 +/- 0.0027 | 27.29 +/- 0.2179 | 1160.7 +/- 24.33 | 940.7 +/- 26.88 |
| `fleetqox_predictive_guarded` | 3 | yes | 6807.2 +/- 253.9 | 0.0000 +/- 0.0000 | 0.0000 +/- 0.0000 | 0.0078 +/- 0.0017 | 27.19 +/- 0.1841 | 1149.0 +/- 13.05 | 951.3 +/- 8.6428 |

## Pareto Frontier

- Non-dominated policies: `fleetqox_predictive`, `fleetqox_csds`, `lag_adapt_002`, `fleetqox_predictive_guarded`.

## Interpretation

- Highest mean utility: `fleetqox_predictive` at `8582.8`.
- Best zero-measured-miss policy: `lag_adapt_002` with utility `6841.0`.

# Sidecar lag_adapt_002 5-Seed Netem

## Inputs

- Metric rows: `20`
- Metrics: `results_sidecar_repeated/risk_reset_v1/sidecar_risk_reset_v1_seed_13_fleetqox_csds_metrics.jsonl`
- Metrics: `results_sidecar_repeated/risk_reset_v1/sidecar_risk_reset_v1_seed_7_fleetqox_csds_metrics.jsonl`
- Metrics: `results_sidecar_repeated/risk_reset_v1/sidecar_risk_reset_v1_seed_13_fleetqox_predictive_metrics.jsonl`
- Metrics: `results_sidecar_repeated/risk_reset_v1/sidecar_risk_reset_v1_seed_7_fleetqox_predictive_metrics.jsonl`
- Metrics: `results_sidecar_repeated/risk_reset_v1/sidecar_risk_reset_v1_seed_13_fleetqox_predictive_guarded_metrics.jsonl`
- Metrics: `results_sidecar_repeated/risk_reset_v1/sidecar_risk_reset_v1_seed_7_fleetqox_predictive_guarded_metrics.jsonl`
- Metrics: `results_sidecar_repeated/lag_adaptation_v2/sidecar_lag_adapt_002_v1_seed_7_matrix_metrics.jsonl`
- Metrics: `results_sidecar_repeated/lag_adaptation_v2/sidecar_lag_adapt_002_v1_seed_13_matrix_metrics.jsonl`
- Metrics: `results_sidecar_repeated/lag_adaptation_v2/sidecar_lag_adapt_002_v1_seed_29_matrix_metrics.jsonl`
- Metrics: `results_sidecar_repeated/lag_adaptation_v2/sidecar_lag_adapt_002_v1_seed_41_matrix_metrics.jsonl`
- Metrics: `results_sidecar_repeated/lag_adaptation_v2/sidecar_lag_adapt_002_v1_seed_53_matrix_metrics.jsonl`

## Policy Summary

| policy | runs | pareto | utility | control misses | deadline miss | loss | p95 ms | rx | compacted rx |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `fleetqox_predictive` | 5 | yes | 8503.2 +/- 284.1 | 7.4000 +/- 3.6981 | 0.0052 +/- 0.0026 | 0.0121 +/- 0.0026 | 27.38 +/- 0.1229 | 1415.2 +/- 16.67 | 1224.4 +/- 34.05 |
| `fleetqox_csds` | 5 | yes | 7892.4 +/- 313.8 | 5.6000 +/- 4.4952 | 0.0043 +/- 0.0034 | 0.0081 +/- 0.0020 | 27.11 +/- 0.1512 | 1306.6 +/- 13.77 | 0.0000 +/- 0.0000 |
| `lag_adapt_002` | 5 | yes | 6729.7 +/- 301.0 | 0.0000 +/- 0.0000 | 0.0000 +/- 0.0000 | 0.0093 +/- 0.0019 | 27.26 +/- 0.1248 | 1144.4 +/- 23.65 | 914.2 +/- 36.48 |
| `fleetqox_predictive_guarded` | 5 | yes | 6713.5 +/- 216.7 | 0.0000 +/- 0.0000 | 0.0000 +/- 0.0000 | 0.0084 +/- 0.0012 | 27.28 +/- 0.2413 | 1134.4 +/- 18.99 | 921.0 +/- 39.50 |

## Pareto Frontier

- Non-dominated policies: `fleetqox_predictive`, `fleetqox_csds`, `lag_adapt_002`, `fleetqox_predictive_guarded`.

## Interpretation

- Highest mean utility: `fleetqox_predictive` at `8503.2`.
- Best zero-measured-miss policy: `lag_adapt_002` with utility `6729.7`.

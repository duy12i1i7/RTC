# Sidecar Lagrangian Outcome Adaptation Netem V2

## Inputs

- Metric rows: `14`
- Metrics: `results_sidecar_repeated/risk_reset_v1/sidecar_risk_reset_v1_seed_13_fleetqox_csds_metrics.jsonl`
- Metrics: `results_sidecar_repeated/risk_reset_v1/sidecar_risk_reset_v1_seed_7_fleetqox_csds_metrics.jsonl`
- Metrics: `results_sidecar_repeated/risk_reset_v1/sidecar_risk_reset_v1_seed_13_fleetqox_predictive_metrics.jsonl`
- Metrics: `results_sidecar_repeated/risk_reset_v1/sidecar_risk_reset_v1_seed_7_fleetqox_predictive_metrics.jsonl`
- Metrics: `results_sidecar_repeated/risk_reset_v1/sidecar_risk_reset_v1_seed_13_fleetqox_predictive_guarded_metrics.jsonl`
- Metrics: `results_sidecar_repeated/risk_reset_v1/sidecar_risk_reset_v1_seed_7_fleetqox_predictive_guarded_metrics.jsonl`
- Metrics: `results_sidecar_repeated/lag_variants_v1/sidecar_lag012_v1_seed_13_matrix_metrics.jsonl`
- Metrics: `results_sidecar_repeated/lag_variants_v1/sidecar_lag012_v1_seed_7_matrix_metrics.jsonl`
- Metrics: `results_sidecar_repeated/lag_variants_v1/sidecar_lag015_v1_seed_13_matrix_metrics.jsonl`
- Metrics: `results_sidecar_repeated/lag_variants_v1/sidecar_lag015_v1_seed_7_matrix_metrics.jsonl`
- Metrics: `results_sidecar_repeated/lag_adaptation_v1/sidecar_lag_adapt_001_v1_seed_13_matrix_metrics.jsonl`
- Metrics: `results_sidecar_repeated/lag_adaptation_v1/sidecar_lag_adapt_001_v1_seed_7_matrix_metrics.jsonl`
- Metrics: `results_sidecar_repeated/lag_adaptation_v2/sidecar_lag_adapt_002_v1_seed_13_matrix_metrics.jsonl`
- Metrics: `results_sidecar_repeated/lag_adaptation_v2/sidecar_lag_adapt_002_v1_seed_7_matrix_metrics.jsonl`

## Policy Summary

| policy | runs | pareto | utility | control misses | deadline miss | loss | p95 ms | rx | compacted rx |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `fleetqox_predictive` | 2 | yes | 8383.9 +/- 544.6 | 5.0000 +/- 9.8000 | 0.0036 +/- 0.0071 | 0.0113 +/- 0.0043 | 27.30 +/- 0.0536 | 1396.5 +/- 20.58 | 1188.0 +/- 50.96 |
| `fleetqox_csds` | 2 | yes | 7777.6 +/- 543.0 | 5.0000 +/- 9.8000 | 0.0038 +/- 0.0075 | 0.0084 +/- 0.0016 | 27.16 +/- 0.3423 | 1292.5 +/- 20.58 | 0.0000 +/- 0.0000 |
| `lag_012` | 2 | yes | 7203.2 +/- 470.3 | 6.5000 +/- 2.9400 | 0.0053 +/- 0.0025 | 0.0081 +/- 0.0017 | 27.25 +/- 0.2837 | 1221.5 +/- 16.66 | 963.0 +/- 49.00 |
| `fleetqox_predictive_guarded` | 2 | yes | 6572.9 +/- 386.9 | 0.0000 +/- 0.0000 | 0.0000 +/- 0.0000 | 0.0093 +/- 0.0008 | 27.42 +/- 0.5991 | 1112.5 +/- 4.9000 | 875.5 +/- 46.06 |
| `lag_adapt_002` | 2 | yes | 6562.7 +/- 449.9 | 0.0000 +/- 0.0000 | 0.0000 +/- 0.0000 | 0.0080 +/- 0.0017 | 27.21 +/- 0.0053 | 1120.0 +/- 1.9600 | 874.5 +/- 32.34 |
| `lag_015` | 2 | no | 7483.9 +/- 542.0 | 5.0000 +/- 9.8000 | 0.0040 +/- 0.0078 | 0.0098 +/- 0.0038 | 27.27 +/- 0.2343 | 1264.5 +/- 2.9400 | 1016.5 +/- 20.58 |
| `lag_adapt_001` | 2 | no | 6429.2 +/- 431.6 | 0.0000 +/- 0.0000 | 0.0000 +/- 0.0000 | 0.0090 +/- 0.0053 | 27.25 +/- 0.0880 | 1099.0 +/- 3.9200 | 852.5 +/- 34.30 |

## Pareto Frontier

- Non-dominated policies: `fleetqox_predictive`, `fleetqox_csds`, `lag_012`, `fleetqox_predictive_guarded`, `lag_adapt_002`.

## Interpretation

- Highest mean utility: `fleetqox_predictive` at `8383.9`.
- Best zero-measured-miss policy: `fleetqox_predictive_guarded` with utility `6572.9`.
- Some policies have fewer than three runs; their confidence intervals are only a smoke-test signal, not statistical evidence.
- Dominated policies in the current evidence set: `lag_015`, `lag_adapt_001`.

# Sidecar Risk-Reset Netem V1

## Inputs

- Metric rows: `8`
- Metrics: `results_sidecar_repeated/risk_reset_v1/sidecar_risk_reset_v1_seed_7_matrix_metrics.jsonl`
- Metrics: `results_sidecar_repeated/risk_reset_v1/sidecar_risk_reset_v1_seed_13_matrix_metrics.jsonl`

## Policy Summary

| policy | runs | pareto | utility | control misses | deadline miss | loss | p95 ms | rx | compacted rx |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `fleetqox_predictive` | 2 | yes | 8383.9 +/- 544.6 | 5.0000 +/- 9.8000 | 0.0036 +/- 0.0071 | 0.0113 +/- 0.0043 | 27.30 +/- 0.0536 | 1396.5 +/- 20.58 | 1188.0 +/- 50.96 |
| `fleetqox_csds` | 2 | yes | 7777.6 +/- 543.0 | 5.0000 +/- 9.8000 | 0.0038 +/- 0.0075 | 0.0084 +/- 0.0016 | 27.16 +/- 0.3423 | 1292.5 +/- 20.58 | 0.0000 +/- 0.0000 |
| `fleetqox_predictive_guarded` | 2 | yes | 6572.9 +/- 386.9 | 0.0000 +/- 0.0000 | 0.0000 +/- 0.0000 | 0.0093 +/- 0.0008 | 27.42 +/- 0.5991 | 1112.5 +/- 4.9000 | 875.5 +/- 46.06 |
| `fleetqox_predictive_lagrangian` | 2 | no | 7470.8 +/- 493.5 | 5.0000 +/- 9.8000 | 0.0040 +/- 0.0077 | 0.0114 +/- 0.0023 | 27.54 +/- 0.5332 | 1262.5 +/- 4.9000 | 1015.0 +/- 23.52 |

## Pareto Frontier

- Non-dominated policies: `fleetqox_predictive`, `fleetqox_csds`, `fleetqox_predictive_guarded`.

## Interpretation

- Highest mean utility: `fleetqox_predictive` at `8383.9`.
- Best zero-measured-miss policy: `fleetqox_predictive_guarded` with utility `6572.9`.
- Some policies have fewer than three runs; their confidence intervals are only a smoke-test signal, not statistical evidence.
- Dominated policies in the current evidence set: `fleetqox_predictive_lagrangian`.

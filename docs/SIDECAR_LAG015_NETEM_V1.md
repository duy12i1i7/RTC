# Sidecar Lagrangian lag_015 Netem V1

## Inputs

- Metric rows: `2`
- Metrics: `results_sidecar_repeated/lag_variants_v1/sidecar_lag015_v1_seed_7_matrix_metrics.jsonl`
- Metrics: `results_sidecar_repeated/lag_variants_v1/sidecar_lag015_v1_seed_13_matrix_metrics.jsonl`

## Policy Summary

| policy | runs | pareto | utility | control misses | deadline miss | loss | p95 ms | rx | compacted rx |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `lag_015` | 2 | yes | 7483.9 +/- 542.0 | 5.0000 +/- 9.8000 | 0.0040 +/- 0.0078 | 0.0098 +/- 0.0038 | 27.27 +/- 0.2343 | 1264.5 +/- 2.9400 | 1016.5 +/- 20.58 |

## Pareto Frontier

- Non-dominated policies: `lag_015`.

## Interpretation

- Highest mean utility: `lag_015` at `7483.9`.
- Some policies have fewer than three runs; their confidence intervals are only a smoke-test signal, not statistical evidence.

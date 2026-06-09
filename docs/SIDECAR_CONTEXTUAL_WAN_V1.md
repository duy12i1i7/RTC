# Sidecar Contextual WAN V1

## Inputs

- Metric rows: `4`
- Metrics: `results_sidecar_repeated/contextual_wan_v1/sidecar_contextual_wan_v1_wan_seed_7_matrix_metrics.jsonl`

## Policy Summary

| policy | runs | pareto | utility | control misses | deadline miss | ctrl delivery | ctrl non-delivery | loss | p95 ms | rx | compacted rx |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `fleetqox_predictive_guarded` | 1 | yes | 2613.5 | 0.0000 | 0.0122 | 0.0000 | 944.0 | 0.0040 | 78.11 | 492.0 | 284.0 |
| `fleetqox_predictive_contextual` | 1 | yes | 1090.4 | 0.0000 | 0.0114 | 0.0000 | 944.0 | 0.0150 | 77.92 | 263.0 | 62.00 |
| `fleetqox_predictive_profiled` | 1 | yes | 1070.5 | 0.0000 | 0.0077 | 0.0000 | 944.0 | 0.0038 | 78.23 | 261.0 | 57.00 |
| `lag_adapt_003` | 1 | no | 1604.0 | 0.0000 | 0.0146 | 0.0000 | 944.0 | 0.0058 | 77.98 | 342.0 | 137.0 |

## Pareto Frontier

- Non-dominated policies: `fleetqox_predictive_guarded`, `fleetqox_predictive_contextual`, `fleetqox_predictive_profiled`.

## Interpretation

- Highest mean utility: `fleetqox_predictive_guarded` at `2613.5`.
- Some policies have fewer than three runs; their confidence intervals are only a smoke-test signal, not statistical evidence.
- Dominated policies in the current evidence set: `lag_adapt_003`.

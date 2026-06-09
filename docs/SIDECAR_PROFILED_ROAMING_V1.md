# Sidecar Profiled Roaming V1

## Inputs

- Metric rows: `3`
- Metrics: `results_sidecar_repeated/profiled_roaming_v1/sidecar_profiled_roaming_v1_roaming_seed_7_matrix_metrics.jsonl`

## Policy Summary

| policy | runs | pareto | utility | control misses | deadline miss | loss | p95 ms | rx | compacted rx |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `fleetqox_predictive_guarded` | 1 | yes | 2378.9 | 0.0000 | 0.3107 | 0.0516 | 110.3 | 441.0 | 275.0 |
| `lag_adapt_003` | 1 | yes | 1249.9 | 0.0000 | 0.0601 | 0.0139 | 109.3 | 283.0 | 86.00 |
| `fleetqox_predictive_profiled` | 1 | yes | 660.2 | 0.0000 | 0.0052 | 0.0352 | 108.1 | 192.0 | 0.0000 |

## Profile Summaries

### `roaming`

- Metric rows: `3`
- Netem: `70000.0 B/s`, `80.00 ms delay`, `25.00 ms jitter`, `3.0000 % loss`, `5.0000 mbit`

| policy | runs | pareto | utility | control misses | deadline miss | loss | p95 ms | rx | compacted rx |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `fleetqox_predictive_guarded` | 1 | yes | 2378.9 | 0.0000 | 0.3107 | 0.0516 | 110.3 | 441.0 | 275.0 |
| `lag_adapt_003` | 1 | yes | 1249.9 | 0.0000 | 0.0601 | 0.0139 | 109.3 | 283.0 | 86.00 |
| `fleetqox_predictive_profiled` | 1 | yes | 660.2 | 0.0000 | 0.0052 | 0.0352 | 108.1 | 192.0 | 0.0000 |

- Non-dominated policies in this profile: `fleetqox_predictive_guarded`, `lag_adapt_003`, `fleetqox_predictive_profiled`.

## Pareto Frontier

- Non-dominated policies: `fleetqox_predictive_guarded`, `lag_adapt_003`, `fleetqox_predictive_profiled`.

## Interpretation

- Highest mean utility: `fleetqox_predictive_guarded` at `2378.9`.
- Some policies have fewer than three runs; their confidence intervals are only a smoke-test signal, not statistical evidence.

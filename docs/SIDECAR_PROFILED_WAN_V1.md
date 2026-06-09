# Sidecar Profiled WAN V1

## Inputs

- Metric rows: `3`
- Metrics: `results_sidecar_repeated/profiled_wan_v1/sidecar_profiled_wan_v1_wan_seed_7_matrix_metrics.jsonl`

## Policy Summary

| policy | runs | pareto | utility | control misses | deadline miss | loss | p95 ms | rx | compacted rx |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `fleetqox_predictive_guarded` | 1 | yes | 2583.8 | 0.0000 | 0.0123 | 0.0162 | 78.65 | 486.0 | 280.0 |
| `lag_adapt_003` | 1 | yes | 1588.5 | 0.0000 | 0.0147 | 0.0116 | 79.81 | 340.0 | 135.0 |
| `fleetqox_predictive_profiled` | 1 | yes | 1068.2 | 0.0000 | 0.0077 | 0.0076 | 78.34 | 260.0 | 58.00 |

## Profile Summaries

### `wan`

- Metric rows: `3`
- Netem: `90000.0 B/s`, `60.00 ms delay`, `15.00 ms jitter`, `1.5000 % loss`, `10.00 mbit`

| policy | runs | pareto | utility | control misses | deadline miss | loss | p95 ms | rx | compacted rx |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `fleetqox_predictive_guarded` | 1 | yes | 2583.8 | 0.0000 | 0.0123 | 0.0162 | 78.65 | 486.0 | 280.0 |
| `lag_adapt_003` | 1 | yes | 1588.5 | 0.0000 | 0.0147 | 0.0116 | 79.81 | 340.0 | 135.0 |
| `fleetqox_predictive_profiled` | 1 | yes | 1068.2 | 0.0000 | 0.0077 | 0.0076 | 78.34 | 260.0 | 58.00 |

- Non-dominated policies in this profile: `fleetqox_predictive_guarded`, `lag_adapt_003`, `fleetqox_predictive_profiled`.

## Pareto Frontier

- Non-dominated policies: `fleetqox_predictive_guarded`, `lag_adapt_003`, `fleetqox_predictive_profiled`.

## Interpretation

- Highest mean utility: `fleetqox_predictive_guarded` at `2583.8`.
- Some policies have fewer than three runs; their confidence intervals are only a smoke-test signal, not statistical evidence.

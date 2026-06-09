# Sidecar Profile Timeout Fix V1

## Inputs

- Metric rows: `1`
- Metrics: `results_sidecar_repeated/profile_timeout_fix_v1/sidecar_profile_timeout_fix_v1_wan_seed_7_matrix_metrics.jsonl`

## Policy Summary

| policy | runs | pareto | utility | control misses | deadline miss | loss | p95 ms | rx | compacted rx |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `lag_adapt_003` | 1 | yes | 6758.3 | 703.0 | 0.6442 | 0.0126 | 79.10 | 1099.0 | 919.0 |

## Profile Summaries

### `wan`

- Metric rows: `1`
- Netem: `90000.0 B/s`, `60.00 ms delay`, `15.00 ms jitter`, `1.5000 % loss`, `10.00 mbit`

| policy | runs | pareto | utility | control misses | deadline miss | loss | p95 ms | rx | compacted rx |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `lag_adapt_003` | 1 | yes | 6758.3 | 703.0 | 0.6442 | 0.0126 | 79.10 | 1099.0 | 919.0 |

- Non-dominated policies in this profile: `lag_adapt_003`.

## Pareto Frontier

- Non-dominated policies: `lag_adapt_003`.

## Interpretation

- Highest mean utility: `lag_adapt_003` at `6758.3`.
- Some policies have fewer than three runs; their confidence intervals are only a smoke-test signal, not statistical evidence.

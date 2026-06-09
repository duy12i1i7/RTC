# Sidecar Semantic Contract Loss-Aware Compare WAN V1

## Inputs

- Metric rows: `15`
- Metrics: `results_sidecar_repeated/semantic_contract_lossaware_compare_wan_v1/sidecar_semantic_contract_lossaware_compare_wan_v1_wan_seed_7_matrix_metrics.jsonl`
- Metrics: `results_sidecar_repeated/semantic_contract_lossaware_compare_wan_v1/sidecar_semantic_contract_lossaware_compare_wan_v1_wan_seed_13_matrix_metrics.jsonl`
- Metrics: `results_sidecar_repeated/semantic_contract_lossaware_compare_wan_v1/sidecar_semantic_contract_lossaware_compare_wan_v1_wan_seed_29_matrix_metrics.jsonl`
- Metrics: `results_sidecar_repeated/semantic_contract_lossaware_compare_wan_v1/sidecar_semantic_contract_lossaware_compare_wan_v1_wan_seed_41_matrix_metrics.jsonl`
- Metrics: `results_sidecar_repeated/semantic_contract_lossaware_compare_wan_v1/sidecar_semantic_contract_lossaware_compare_wan_v1_wan_seed_53_matrix_metrics.jsonl`

## Policy Summary

| policy | runs | pareto | utility | control misses | deadline miss | ctrl delivery | ctrl non-delivery | loss | p95 ms | rx | compacted rx | intent rx |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `fleetqox_semantic_contract` | 5 | yes | 7496.3 +/- 226.9 | 24.80 +/- 29.99 | 0.0230 +/- 0.0294 | 0.9742 +/- 0.0244 | 0.2000 +/- 0.3920 | 0.0252 +/- 0.0211 | 134.2 +/- 103.8 | 1270.2 +/- 32.00 | 177.4 +/- 15.49 | 925.8 +/- 21.47 |
| `fleetqox_semantic_contract_lossaware` | 5 | yes | 7455.5 +/- 334.1 | 9.6000 +/- 0.4801 | 0.0084 +/- 0.0007 | 0.9836 +/- 0.0027 | 0.2000 +/- 0.3920 | 0.0153 +/- 0.0024 | 80.81 +/- 0.3140 | 1236.2 +/- 14.79 | 180.0 +/- 15.03 | 934.8 +/- 5.4175 |
| `fleetqox_predictive_intent` | 5 | yes | 7072.1 +/- 318.6 | 9.6000 +/- 0.4801 | 0.0093 +/- 0.0009 | 0.9851 +/- 0.0008 | 0.0000 +/- 0.0000 | 0.0157 +/- 0.0011 | 81.80 +/- 0.4828 | 1207.0 +/- 8.4303 | 75.00 +/- 11.38 | 936.2 +/- 5.4529 |

## Profile Summaries

### `wan`

- Metric rows: `15`
- Netem: `90000.0 B/s`, `60.00 ms delay`, `15.00 ms jitter`, `1.5000 % loss`, `10.00 mbit`

| policy | runs | pareto | utility | control misses | deadline miss | ctrl delivery | ctrl non-delivery | loss | p95 ms | rx | compacted rx | intent rx |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `fleetqox_semantic_contract` | 5 | yes | 7496.3 +/- 226.9 | 24.80 +/- 29.99 | 0.0230 +/- 0.0294 | 0.9742 +/- 0.0244 | 0.2000 +/- 0.3920 | 0.0252 +/- 0.0211 | 134.2 +/- 103.8 | 1270.2 +/- 32.00 | 177.4 +/- 15.49 | 925.8 +/- 21.47 |
| `fleetqox_semantic_contract_lossaware` | 5 | yes | 7455.5 +/- 334.1 | 9.6000 +/- 0.4801 | 0.0084 +/- 0.0007 | 0.9836 +/- 0.0027 | 0.2000 +/- 0.3920 | 0.0153 +/- 0.0024 | 80.81 +/- 0.3140 | 1236.2 +/- 14.79 | 180.0 +/- 15.03 | 934.8 +/- 5.4175 |
| `fleetqox_predictive_intent` | 5 | yes | 7072.1 +/- 318.6 | 9.6000 +/- 0.4801 | 0.0093 +/- 0.0009 | 0.9851 +/- 0.0008 | 0.0000 +/- 0.0000 | 0.0157 +/- 0.0011 | 81.80 +/- 0.4828 | 1207.0 +/- 8.4303 | 75.00 +/- 11.38 | 936.2 +/- 5.4529 |

- Non-dominated policies in this profile: `fleetqox_semantic_contract`, `fleetqox_semantic_contract_lossaware`, `fleetqox_predictive_intent`.

## Pareto Frontier

- Non-dominated policies: `fleetqox_semantic_contract`, `fleetqox_semantic_contract_lossaware`, `fleetqox_predictive_intent`.

## Interpretation

- Highest mean utility: `fleetqox_semantic_contract` at `7496.3`.
- `fleetqox_semantic_contract_lossaware` is the stronger operating point for
  WAN stability: it keeps utility close to the semantic baseline while reducing
  loss, deadline miss, and p95 latency, and it remains ahead of
  `fleetqox_predictive_intent` on utility and receive count.

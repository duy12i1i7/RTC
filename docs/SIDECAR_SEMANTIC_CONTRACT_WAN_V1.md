# Sidecar Semantic Contract WAN V1

## Inputs

- Metric rows: `15`
- Metrics: `results_sidecar_repeated/semantic_contract_wan_v1/sidecar_semantic_contract_wan_v1_wan_seed_7_matrix_metrics.jsonl`
- Metrics: `results_sidecar_repeated/semantic_contract_wan_v1/sidecar_semantic_contract_wan_v1_wan_seed_13_matrix_metrics.jsonl`
- Metrics: `results_sidecar_repeated/semantic_contract_wan_v1/sidecar_semantic_contract_wan_v1_wan_seed_29_matrix_metrics.jsonl`
- Metrics: `results_sidecar_repeated/semantic_contract_wan_v1/sidecar_semantic_contract_wan_v1_wan_seed_41_matrix_metrics.jsonl`
- Metrics: `results_sidecar_repeated/semantic_contract_wan_v1/sidecar_semantic_contract_wan_v1_wan_seed_53_matrix_metrics.jsonl`

## Policy Summary

| policy | runs | pareto | utility | control misses | deadline miss | ctrl delivery | ctrl non-delivery | loss | p95 ms | rx | compacted rx | intent rx |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `fleetqox_semantic_contract` | 5 | yes | 7560.6 +/- 320.4 | 9.6000 +/- 0.4801 | 0.0081 +/- 0.0007 | 0.9815 +/- 0.0039 | 0.2000 +/- 0.3920 | 0.0178 +/- 0.0033 | 80.82 +/- 0.3314 | 1279.8 +/- 17.62 | 179.0 +/- 17.32 | 932.8 +/- 8.1852 |
| `fleetqox_predictive_intent` | 5 | yes | 7076.0 +/- 305.8 | 9.4000 +/- 0.4801 | 0.0091 +/- 0.0009 | 0.9853 +/- 0.0040 | 0.0000 +/- 0.0000 | 0.0148 +/- 0.0036 | 81.80 +/- 0.3774 | 1208.0 +/- 9.9363 | 75.20 +/- 11.65 | 936.4 +/- 8.4212 |
| `fleetqox_predictive_profiled` | 5 | yes | 1144.3 +/- 76.89 | 0.0000 +/- 0.0000 | 0.0051 +/- 0.0028 | 0.0000 +/- 0.0000 | 950.4 +/- 5.6331 | 0.0198 +/- 0.0076 | 78.98 +/- 0.6347 | 269.6 +/- 11.13 | 72.80 +/- 11.96 | 0.0000 +/- 0.0000 |

## Profile Summaries

### `wan`

- Metric rows: `15`
- Netem: `90000.0 B/s`, `60.00 ms delay`, `15.00 ms jitter`, `1.5000 % loss`, `10.00 mbit`

| policy | runs | pareto | utility | control misses | deadline miss | ctrl delivery | ctrl non-delivery | loss | p95 ms | rx | compacted rx | intent rx |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `fleetqox_semantic_contract` | 5 | yes | 7560.6 +/- 320.4 | 9.6000 +/- 0.4801 | 0.0081 +/- 0.0007 | 0.9815 +/- 0.0039 | 0.2000 +/- 0.3920 | 0.0178 +/- 0.0033 | 80.82 +/- 0.3314 | 1279.8 +/- 17.62 | 179.0 +/- 17.32 | 932.8 +/- 8.1852 |
| `fleetqox_predictive_intent` | 5 | yes | 7076.0 +/- 305.8 | 9.4000 +/- 0.4801 | 0.0091 +/- 0.0009 | 0.9853 +/- 0.0040 | 0.0000 +/- 0.0000 | 0.0148 +/- 0.0036 | 81.80 +/- 0.3774 | 1208.0 +/- 9.9363 | 75.20 +/- 11.65 | 936.4 +/- 8.4212 |
| `fleetqox_predictive_profiled` | 5 | yes | 1144.3 +/- 76.89 | 0.0000 +/- 0.0000 | 0.0051 +/- 0.0028 | 0.0000 +/- 0.0000 | 950.4 +/- 5.6331 | 0.0198 +/- 0.0076 | 78.98 +/- 0.6347 | 269.6 +/- 11.13 | 72.80 +/- 11.96 | 0.0000 +/- 0.0000 |

- Non-dominated policies in this profile: `fleetqox_semantic_contract`, `fleetqox_predictive_intent`, `fleetqox_predictive_profiled`.

## Pareto Frontier

- Non-dominated policies: `fleetqox_semantic_contract`, `fleetqox_predictive_intent`, `fleetqox_predictive_profiled`.

## Interpretation

- Highest mean utility: `fleetqox_semantic_contract` at `7560.6`.

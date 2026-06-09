# Sidecar Semantic Contract Loss-Aware WAN V1

> Superseded by `SIDECAR_SEMANTIC_CONTRACT_LOSSAWARE_COMPARE_WAN_V1.md`.
> This earlier smoke was generated before the loss-aware scheduler was split
> into the explicit `fleetqox_semantic_contract_lossaware` policy name.

## Inputs

- Metric rows: `10`
- Metrics: `results_sidecar_repeated/semantic_contract_lossaware_wan_v1/sidecar_semantic_contract_lossaware_wan_v1_wan_seed_7_matrix_metrics.jsonl`
- Metrics: `results_sidecar_repeated/semantic_contract_lossaware_wan_v1/sidecar_semantic_contract_lossaware_wan_v1_wan_seed_13_matrix_metrics.jsonl`
- Metrics: `results_sidecar_repeated/semantic_contract_lossaware_wan_v1/sidecar_semantic_contract_lossaware_wan_v1_wan_seed_29_matrix_metrics.jsonl`
- Metrics: `results_sidecar_repeated/semantic_contract_lossaware_wan_v1/sidecar_semantic_contract_lossaware_wan_v1_wan_seed_41_matrix_metrics.jsonl`
- Metrics: `results_sidecar_repeated/semantic_contract_lossaware_wan_v1/sidecar_semantic_contract_lossaware_wan_v1_wan_seed_53_matrix_metrics.jsonl`

## Policy Summary

| policy | runs | pareto | utility | control misses | deadline miss | ctrl delivery | ctrl non-delivery | loss | p95 ms | rx | compacted rx | intent rx |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `fleetqox_semantic_contract` | 5 | yes | 7439.7 +/- 316.4 | 11.20 +/- 3.3607 | 0.0102 +/- 0.0037 | 0.9827 +/- 0.0047 | 0.2000 +/- 0.3920 | 0.0169 +/- 0.0030 | 80.70 +/- 0.3510 | 1234.2 +/- 17.91 | 179.0 +/- 15.54 | 934.0 +/- 8.1523 |
| `fleetqox_predictive_intent` | 5 | yes | 7089.5 +/- 314.8 | 9.6000 +/- 0.4801 | 0.0096 +/- 0.0012 | 0.9872 +/- 0.0020 | 0.0000 +/- 0.0000 | 0.0132 +/- 0.0024 | 81.81 +/- 0.3972 | 1210.0 +/- 9.5418 | 74.80 +/- 11.38 | 938.2 +/- 6.3026 |

## Profile Summaries

### `wan`

- Metric rows: `10`
- Netem: `90000.0 B/s`, `60.00 ms delay`, `15.00 ms jitter`, `1.5000 % loss`, `10.00 mbit`

| policy | runs | pareto | utility | control misses | deadline miss | ctrl delivery | ctrl non-delivery | loss | p95 ms | rx | compacted rx | intent rx |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `fleetqox_semantic_contract` | 5 | yes | 7439.7 +/- 316.4 | 11.20 +/- 3.3607 | 0.0102 +/- 0.0037 | 0.9827 +/- 0.0047 | 0.2000 +/- 0.3920 | 0.0169 +/- 0.0030 | 80.70 +/- 0.3510 | 1234.2 +/- 17.91 | 179.0 +/- 15.54 | 934.0 +/- 8.1523 |
| `fleetqox_predictive_intent` | 5 | yes | 7089.5 +/- 314.8 | 9.6000 +/- 0.4801 | 0.0096 +/- 0.0012 | 0.9872 +/- 0.0020 | 0.0000 +/- 0.0000 | 0.0132 +/- 0.0024 | 81.81 +/- 0.3972 | 1210.0 +/- 9.5418 | 74.80 +/- 11.38 | 938.2 +/- 6.3026 |

- Non-dominated policies in this profile: `fleetqox_semantic_contract`, `fleetqox_predictive_intent`.

## Pareto Frontier

- Non-dominated policies: `fleetqox_semantic_contract`, `fleetqox_predictive_intent`.

## Interpretation

- Highest mean utility: `fleetqox_semantic_contract` at `7439.7`.

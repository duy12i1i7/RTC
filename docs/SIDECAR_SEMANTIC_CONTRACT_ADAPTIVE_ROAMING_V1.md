# Sidecar Semantic Contract Adaptive Roaming V1

## Inputs

- Metric rows: `20`
- Metrics: `results_sidecar_repeated/semantic_contract_adaptive_roaming_v1/sidecar_semantic_contract_adaptive_roaming_v1_roaming_seed_7_matrix_metrics.jsonl`
- Metrics: `results_sidecar_repeated/semantic_contract_adaptive_roaming_v1/sidecar_semantic_contract_adaptive_roaming_v1_roaming_seed_13_matrix_metrics.jsonl`
- Metrics: `results_sidecar_repeated/semantic_contract_adaptive_roaming_v1/sidecar_semantic_contract_adaptive_roaming_v1_roaming_seed_29_matrix_metrics.jsonl`
- Metrics: `results_sidecar_repeated/semantic_contract_adaptive_roaming_v1/sidecar_semantic_contract_adaptive_roaming_v1_roaming_seed_41_matrix_metrics.jsonl`
- Metrics: `results_sidecar_repeated/semantic_contract_adaptive_roaming_v1/sidecar_semantic_contract_adaptive_roaming_v1_roaming_seed_53_matrix_metrics.jsonl`

## Policy Summary

| policy | runs | pareto | utility | control misses | deadline miss | ctrl delivery | ctrl non-delivery | loss | p95 ms | rx | compacted rx | intent rx |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `fleetqox_semantic_contract` | 5 | yes | 6332.3 +/- 304.7 | 0.0000 +/- 0.0000 | 0.0004 +/- 0.0004 | 0.9646 +/- 0.0051 | 1.0000 +/- 0.8765 | 0.0344 +/- 0.0037 | 117.5 +/- 0.6744 | 1073.0 +/- 2.6296 | 0.0000 +/- 0.0000 | 916.8 +/- 6.8852 |
| `fleetqox_semantic_contract_adaptive` | 5 | yes | 5973.8 +/- 315.4 | 0.0000 +/- 0.0000 | 0.0002 +/- 0.0004 | 0.9686 +/- 0.0033 | 1.0000 +/- 0.8765 | 0.0304 +/- 0.0044 | 117.2 +/- 0.4755 | 957.0 +/- 7.7908 | 0.0000 +/- 0.0000 | 920.6 +/- 7.6816 |
| `fleetqox_semantic_contract_lossaware` | 5 | no | 5946.3 +/- 285.4 | 17.40 +/- 34.10 | 0.0184 +/- 0.0356 | 0.9649 +/- 0.0074 | 1.0000 +/- 0.8765 | 0.0340 +/- 0.0074 | 237.1 +/- 238.5 | 953.4 +/- 6.3086 | 0.0000 +/- 0.0000 | 917.0 +/- 4.3386 |
| `fleetqox_predictive_intent` | 5 | no | 603.5 +/- 29.88 | 0.0000 +/- 0.0000 | 0.0098 +/- 0.0038 | 0.0000 +/- 0.0000 | 950.4 +/- 5.6331 | 0.0339 +/- 0.0190 | 108.9 +/- 1.5324 | 183.0 +/- 7.4635 | 0.0000 +/- 0.0000 | 0.0000 +/- 0.0000 |

## Profile Summaries

### `roaming`

- Metric rows: `20`
- Netem: `70000.0 B/s`, `80.00 ms delay`, `25.00 ms jitter`, `3.0000 % loss`, `5.0000 mbit`

| policy | runs | pareto | utility | control misses | deadline miss | ctrl delivery | ctrl non-delivery | loss | p95 ms | rx | compacted rx | intent rx |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `fleetqox_semantic_contract` | 5 | yes | 6332.3 +/- 304.7 | 0.0000 +/- 0.0000 | 0.0004 +/- 0.0004 | 0.9646 +/- 0.0051 | 1.0000 +/- 0.8765 | 0.0344 +/- 0.0037 | 117.5 +/- 0.6744 | 1073.0 +/- 2.6296 | 0.0000 +/- 0.0000 | 916.8 +/- 6.8852 |
| `fleetqox_semantic_contract_adaptive` | 5 | yes | 5973.8 +/- 315.4 | 0.0000 +/- 0.0000 | 0.0002 +/- 0.0004 | 0.9686 +/- 0.0033 | 1.0000 +/- 0.8765 | 0.0304 +/- 0.0044 | 117.2 +/- 0.4755 | 957.0 +/- 7.7908 | 0.0000 +/- 0.0000 | 920.6 +/- 7.6816 |
| `fleetqox_semantic_contract_lossaware` | 5 | no | 5946.3 +/- 285.4 | 17.40 +/- 34.10 | 0.0184 +/- 0.0356 | 0.9649 +/- 0.0074 | 1.0000 +/- 0.8765 | 0.0340 +/- 0.0074 | 237.1 +/- 238.5 | 953.4 +/- 6.3086 | 0.0000 +/- 0.0000 | 917.0 +/- 4.3386 |
| `fleetqox_predictive_intent` | 5 | no | 603.5 +/- 29.88 | 0.0000 +/- 0.0000 | 0.0098 +/- 0.0038 | 0.0000 +/- 0.0000 | 950.4 +/- 5.6331 | 0.0339 +/- 0.0190 | 108.9 +/- 1.5324 | 183.0 +/- 7.4635 | 0.0000 +/- 0.0000 | 0.0000 +/- 0.0000 |

- Non-dominated policies in this profile: `fleetqox_semantic_contract`, `fleetqox_semantic_contract_adaptive`.

## Pareto Frontier

- Non-dominated policies: `fleetqox_semantic_contract`, `fleetqox_semantic_contract_adaptive`.

## Interpretation

- Highest mean utility: `fleetqox_semantic_contract` at `6332.3`.
- Dominated policies in the current evidence set: `fleetqox_semantic_contract_lossaware`, `fleetqox_predictive_intent`.

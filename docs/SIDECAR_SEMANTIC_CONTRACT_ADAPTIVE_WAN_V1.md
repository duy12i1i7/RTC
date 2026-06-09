# Sidecar Semantic Contract Adaptive WAN V1

## Inputs

- Metric rows: `20`
- Metrics: `results_sidecar_repeated/semantic_contract_adaptive_wan_v1/sidecar_semantic_contract_adaptive_wan_v1_wan_seed_7_matrix_metrics.jsonl`
- Metrics: `results_sidecar_repeated/semantic_contract_adaptive_wan_v1/sidecar_semantic_contract_adaptive_wan_v1_wan_seed_13_matrix_metrics.jsonl`
- Metrics: `results_sidecar_repeated/semantic_contract_adaptive_wan_v1/sidecar_semantic_contract_adaptive_wan_v1_wan_seed_29_matrix_metrics.jsonl`
- Metrics: `results_sidecar_repeated/semantic_contract_adaptive_wan_v1/sidecar_semantic_contract_adaptive_wan_v1_wan_seed_41_matrix_metrics.jsonl`
- Metrics: `results_sidecar_repeated/semantic_contract_adaptive_wan_v1/sidecar_semantic_contract_adaptive_wan_v1_wan_seed_53_matrix_metrics.jsonl`

## Policy Summary

| policy | runs | pareto | utility | control misses | deadline miss | ctrl delivery | ctrl non-delivery | loss | p95 ms | rx | compacted rx | intent rx |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `fleetqox_semantic_contract_adaptive` | 5 | yes | 7597.5 +/- 310.5 | 9.6000 +/- 0.4801 | 0.0081 +/- 0.0007 | 0.9855 +/- 0.0015 | 0.2000 +/- 0.3920 | 0.0130 +/- 0.0017 | 82.53 +/- 0.4538 | 1286.0 +/- 16.87 | 181.8 +/- 16.38 | 936.6 +/- 4.9039 |
| `fleetqox_predictive_intent` | 5 | yes | 7089.2 +/- 320.9 | 9.6000 +/- 0.4801 | 0.0093 +/- 0.0010 | 0.9867 +/- 0.0035 | 0.0000 +/- 0.0000 | 0.0135 +/- 0.0031 | 82.21 +/- 0.8439 | 1209.6 +/- 6.4591 | 74.80 +/- 11.65 | 937.8 +/- 7.7016 |
| `fleetqox_semantic_contract` | 5 | no | 7496.4 +/- 319.4 | 23.80 +/- 28.03 | 0.0226 +/- 0.0286 | 0.9712 +/- 0.0252 | 0.2000 +/- 0.3920 | 0.0248 +/- 0.0204 | 116.2 +/- 68.58 | 1270.4 +/- 20.77 | 178.2 +/- 14.69 | 923.0 +/- 23.46 |
| `fleetqox_semantic_contract_lossaware` | 5 | no | 7364.5 +/- 449.7 | 25.60 +/- 31.07 | 0.0243 +/- 0.0305 | 0.9706 +/- 0.0257 | 0.2000 +/- 0.3920 | 0.0269 +/- 0.0214 | 126.2 +/- 88.47 | 1221.6 +/- 31.51 | 178.4 +/- 15.71 | 922.4 +/- 22.80 |

## Profile Summaries

### `wan`

- Metric rows: `20`
- Netem: `90000.0 B/s`, `60.00 ms delay`, `15.00 ms jitter`, `1.5000 % loss`, `10.00 mbit`

| policy | runs | pareto | utility | control misses | deadline miss | ctrl delivery | ctrl non-delivery | loss | p95 ms | rx | compacted rx | intent rx |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `fleetqox_semantic_contract_adaptive` | 5 | yes | 7597.5 +/- 310.5 | 9.6000 +/- 0.4801 | 0.0081 +/- 0.0007 | 0.9855 +/- 0.0015 | 0.2000 +/- 0.3920 | 0.0130 +/- 0.0017 | 82.53 +/- 0.4538 | 1286.0 +/- 16.87 | 181.8 +/- 16.38 | 936.6 +/- 4.9039 |
| `fleetqox_predictive_intent` | 5 | yes | 7089.2 +/- 320.9 | 9.6000 +/- 0.4801 | 0.0093 +/- 0.0010 | 0.9867 +/- 0.0035 | 0.0000 +/- 0.0000 | 0.0135 +/- 0.0031 | 82.21 +/- 0.8439 | 1209.6 +/- 6.4591 | 74.80 +/- 11.65 | 937.8 +/- 7.7016 |
| `fleetqox_semantic_contract` | 5 | no | 7496.4 +/- 319.4 | 23.80 +/- 28.03 | 0.0226 +/- 0.0286 | 0.9712 +/- 0.0252 | 0.2000 +/- 0.3920 | 0.0248 +/- 0.0204 | 116.2 +/- 68.58 | 1270.4 +/- 20.77 | 178.2 +/- 14.69 | 923.0 +/- 23.46 |
| `fleetqox_semantic_contract_lossaware` | 5 | no | 7364.5 +/- 449.7 | 25.60 +/- 31.07 | 0.0243 +/- 0.0305 | 0.9706 +/- 0.0257 | 0.2000 +/- 0.3920 | 0.0269 +/- 0.0214 | 126.2 +/- 88.47 | 1221.6 +/- 31.51 | 178.4 +/- 15.71 | 922.4 +/- 22.80 |

- Non-dominated policies in this profile: `fleetqox_semantic_contract_adaptive`, `fleetqox_predictive_intent`.

## Pareto Frontier

- Non-dominated policies: `fleetqox_semantic_contract_adaptive`, `fleetqox_predictive_intent`.

## Interpretation

- Highest mean utility: `fleetqox_semantic_contract_adaptive` at `7597.5`.
- Dominated policies in the current evidence set: `fleetqox_semantic_contract`, `fleetqox_semantic_contract_lossaware`.

## Adaptive Trace Check

The adaptive policy did not behave as a static alias for either semantic
variant. Across the five WAN runs, decision reasons show `5137` tail-shield
decisions and `2705` utility-variant decisions. The selector therefore acted as
a hedge: it kept the high-utility semantic plan when the preview remained safe,
but switched to the loss-shadowed plan on batches where the contract score made
tail exposure expensive.

The important signal is the outlier suppression. In this run, the fixed
`fleetqox_semantic_contract` baseline hit high-loss/high-latency outliers
(`116.2 ms` mean p95 and `0.0226` deadline miss). The adaptive selector kept
the utility level higher (`7597.5` versus `7496.4`) while reducing loss
(`0.0130` versus `0.0248`) and deadline miss (`0.0081` versus `0.0226`). Its
p95 is slightly higher than `fleetqox_predictive_intent` in this WAN sweep, but
with much higher delivered semantic utility and receive count.

# Sidecar Control Intent WAN V1

## Inputs

- Metric rows: `5`
- Metrics: `results_sidecar_repeated/intent_wan_v1/sidecar_intent_wan_v1_wan_seed_7_matrix_metrics.jsonl`

## Policy Summary

| policy | runs | pareto | utility | control misses | deadline miss | ctrl delivery | ctrl non-delivery | loss | p95 ms | rx | compacted rx | intent rx |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `fleetqox_predictive_intent` | 1 | yes | 7303.8 | 10.00 | 0.0101 | 0.9862 | 0.0000 | 0.0157 | 81.38 | 1192.0 | 62.00 | 931.0 |
| `fleetqox_predictive_guarded` | 1 | yes | 2603.6 | 0.0000 | 0.0143 | 0.0000 | 944.0 | 0.0081 | 78.03 | 490.0 | 283.0 | 0.0000 |
| `fleetqox_predictive_contextual` | 1 | yes | 1089.8 | 0.0000 | 0.0076 | 0.0000 | 944.0 | 0.0150 | 78.49 | 263.0 | 62.00 | 0.0000 |
| `lag_adapt_003` | 1 | no | 1588.1 | 0.0000 | 0.0177 | 0.0000 | 944.0 | 0.0145 | 78.75 | 339.0 | 136.0 | 0.0000 |
| `fleetqox_predictive_profiled` | 1 | no | 1062.9 | 0.0000 | 0.0078 | 0.0000 | 944.0 | 0.0153 | 78.28 | 258.0 | 58.00 | 0.0000 |

## Pareto Frontier

- Non-dominated policies: `fleetqox_predictive_intent`, `fleetqox_predictive_guarded`, `fleetqox_predictive_contextual`.

## Interpretation

- Highest mean utility: `fleetqox_predictive_intent` at `7303.8`.
- Some policies have fewer than three runs; their confidence intervals are only a smoke-test signal, not statistical evidence.
- Dominated policies in the current evidence set: `lag_adapt_003`, `fleetqox_predictive_profiled`.

## Key Finding

This run exposes why packet-deadline metrics alone are not enough for robot
control. The guarded, fixed Lagrangian, profiled, and contextual policies all
show zero `control misses`, but they do it by dropping all `944` control
decisions. Their `ctrl delivery` is `0.0000`.

`fleetqox_predictive_intent` changes the communication semantics instead of
only tuning admission. When a 45 ms control sample is infeasible over the WAN
path, the sidecar emits a compact `send_intent` packet with `wire_mode` set to
`control_intent` and a path-aware horizon deadline. In this smoke it delivers
`931` intent packets, reaches `0.9862` control delivery, and raises delivered
utility to `7303.8`.

The tradeoff is explicit: intent traffic raises offered load and still has `10`
control deadline misses in this one-seed WAN run. The next step is not to hide
that cost; it is to add horizon sizing, intent rate control, and multi-seed
WAN/roaming validation.

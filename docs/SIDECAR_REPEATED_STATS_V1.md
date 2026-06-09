# Sidecar Repeated-Run Statistics V1

## Inputs

- Metric rows: `9`
- Metrics: `results_sidecar_netem_closed_loop/sidecar_netem_closed_loop_v1_matrix_metrics.jsonl`
- Metrics: `results_sidecar_netem_lagrangian_v3_matrix/sidecar_netem_lagrangian_v3_matrix_matrix_metrics.jsonl`

## Policy Summary

| policy | runs | pareto | utility | control misses | deadline miss | loss | p95 ms | rx | compacted rx |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `fleetqox_predictive` | 2 | yes | 8680.5 +/- 68.82 | 10.00 +/- 0.0000 | 0.0072 +/- 0.0001 | 0.0110 +/- 0.0077 | 27.30 +/- 0.0387 | 1389.5 +/- 10.78 | 1165.5 +/- 6.8600 |
| `fleetqox_csds` | 2 | yes | 8036.5 +/- 37.44 | 5.0000 +/- 7.8400 | 0.0039 +/- 0.0061 | 0.0120 +/- 0.0038 | 26.89 +/- 0.1820 | 1278.5 +/- 4.9000 | 0.0000 +/- 0.0000 |
| `static_priority` | 1 | yes | 7625.6 | 1.0000 | 0.0008 | 0.0109 | 27.90 | 1177.0 | 0.0000 |
| `fleetqox_predictive_lagrangian` | 1 | yes | 7516.0 | 10.00 | 0.0081 | 0.0097 | 27.24 | 1228.0 | 976.0 |
| `fleetqox_predictive_guarded` | 2 | yes | 6741.8 +/- 13.24 | 0.0000 +/- 0.0000 | 0.0000 +/- 0.0000 | 0.0125 +/- 0.0017 | 27.36 +/- 0.0822 | 1106.0 +/- 1.9600 | 847.5 +/- 2.9400 |
| `fifo` | 1 | no | 6335.8 | 2.0000 | 0.0020 | 0.0149 | 27.06 | 990.0 | 0.0000 |

## Pareto Frontier

- Non-dominated policies: `fleetqox_predictive`, `fleetqox_csds`, `static_priority`, `fleetqox_predictive_lagrangian`, `fleetqox_predictive_guarded`.

## Interpretation

- Highest mean utility: `fleetqox_predictive` at `8680.5`.
- Best zero-measured-miss policy: `fleetqox_predictive_guarded` with utility `6741.8`.
- Some policies have fewer than three runs; their confidence intervals are only a smoke-test signal, not statistical evidence.
- Dominated policies in the current evidence set: `fifo`.

## Next Sweep Command

When Docker is available, run a real repeated closed-loop sweep with:

```bash
python3 -m scripts.run_sidecar_repeated_netem \
  --run \
  --scenario-prefix sidecar_repeated_v1 \
  --all-policies \
  --seeds 7,13,29,41,53 \
  --closed-loop-feed \
  --markdown docs/SIDECAR_REPEATED_STATS_V1.md \
  --summary-json results_sidecar_repeated/repeated_netem_summary.json
```

This will replace this smoke aggregation with seed-level evidence from the same
runner and metric schema.

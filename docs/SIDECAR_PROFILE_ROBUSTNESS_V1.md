# Sidecar Profile Robustness V1

## Inputs

- Metric rows: `12`
- Metrics: `results_sidecar_repeated/profile_robustness_v1/sidecar_profile_robustness_v1_lan_seed_7_matrix_metrics.jsonl`
- Metrics: `results_sidecar_repeated/profile_robustness_v1/sidecar_profile_robustness_v1_wan_seed_7_matrix_metrics.jsonl`
- Metrics: `results_sidecar_repeated/profile_robustness_v1/sidecar_profile_robustness_v1_roaming_seed_7_matrix_metrics.jsonl`

## Policy Summary

| policy | runs | pareto | utility | control misses | deadline miss | loss | p95 ms | rx | compacted rx |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `fleetqox_predictive` | 3 | yes | 8386.7 +/- 675.7 | 610.0 +/- 597.9 | 0.5074 +/- 0.5002 | 0.0155 +/- 0.0171 | 67.39 +/- 64.57 | 1338.0 +/- 113.3 | 1134.7 +/- 54.51 |
| `fleetqox_csds` | 3 | yes | 7373.9 +/- 1432.7 | 566.0 +/- 556.2 | 0.5658 +/- 0.5599 | 0.0138 +/- 0.0131 | 65.42 +/- 62.17 | 1160.7 +/- 245.6 | 0.0000 +/- 0.0000 |
| `lag_adapt_003` | 3 | yes | 6799.4 +/- 424.0 | 461.7 +/- 452.5 | 0.4615 +/- 0.4554 | 0.0139 +/- 0.0159 | 66.96 +/- 64.17 | 1109.0 +/- 88.36 | 879.7 +/- 44.25 |
| `fleetqox_predictive_guarded` | 3 | yes | 6558.7 +/- 388.6 | 407.7 +/- 399.5 | 0.4487 +/- 0.4512 | 0.0169 +/- 0.0154 | 68.30 +/- 66.47 | 1068.3 +/- 66.27 | 853.3 +/- 63.11 |

## Profile Summaries

### `lan`

- Metric rows: `4`
- Netem: `180000.0 B/s`, `3.0000 ms delay`, `1.0000 ms jitter`, `0.1000 % loss`, `100.0 mbit`

| policy | runs | pareto | utility | control misses | deadline miss | loss | p95 ms | rx | compacted rx |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `fleetqox_predictive` | 1 | yes | 9041.5 | 0.0000 | 0.0000 | 0.0000 | 5.0600 | 1450.0 | 1089.0 |
| `fleetqox_csds` | 1 | no | 8704.5 | 0.0000 | 0.0000 | 0.0014 | 5.0324 | 1389.0 | 0.0000 |
| `lag_adapt_003` | 1 | no | 7194.3 | 0.0000 | 0.0000 | 0.0000 | 5.0015 | 1192.0 | 839.0 |
| `fleetqox_predictive_guarded` | 1 | no | 6930.2 | 0.0000 | 0.0000 | 0.0026 | 4.9712 | 1131.0 | 789.0 |

- Non-dominated policies in this profile: `fleetqox_predictive`.

### `wan`

- Metric rows: `4`
- Netem: `90000.0 B/s`, `60.00 ms delay`, `15.00 ms jitter`, `1.5000 % loss`, `10.00 mbit`

| policy | runs | pareto | utility | control misses | deadline miss | loss | p95 ms | rx | compacted rx |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `fleetqox_predictive` | 1 | yes | 8246.2 | 925.0 | 0.7131 | 0.0166 | 80.09 | 1307.0 | 1185.0 |
| `fleetqox_csds` | 1 | yes | 7232.7 | 885.0 | 0.7799 | 0.0156 | 78.76 | 1136.0 | 0.0000 |
| `lag_adapt_003` | 1 | yes | 6755.0 | 701.0 | 0.6448 | 0.0135 | 79.56 | 1098.0 | 917.0 |
| `fleetqox_predictive_guarded` | 1 | yes | 6493.1 | 611.0 | 0.5836 | 0.0185 | 78.93 | 1059.0 | 888.0 |

- Non-dominated policies in this profile: `fleetqox_predictive`, `fleetqox_csds`, `lag_adapt_003`, `fleetqox_predictive_guarded`.

### `roaming`

- Metric rows: `4`
- Netem: `70000.0 B/s`, `80.00 ms delay`, `25.00 ms jitter`, `3.0000 % loss`, `5.0000 mbit`

| policy | runs | pareto | utility | control misses | deadline miss | loss | p95 ms | rx | compacted rx |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `fleetqox_predictive` | 1 | yes | 7872.3 | 905.0 | 0.8091 | 0.0301 | 117.0 | 1257.0 | 1130.0 |
| `lag_adapt_003` | 1 | yes | 6448.9 | 684.0 | 0.7396 | 0.0281 | 116.3 | 1037.0 | 883.0 |
| `fleetqox_predictive_guarded` | 1 | yes | 6252.9 | 612.0 | 0.7626 | 0.0296 | 121.0 | 1015.0 | 883.0 |
| `fleetqox_csds` | 1 | yes | 6184.3 | 813.0 | 0.9175 | 0.0245 | 112.5 | 957.0 | 0.0000 |

- Non-dominated policies in this profile: `fleetqox_predictive`, `lag_adapt_003`, `fleetqox_predictive_guarded`, `fleetqox_csds`.

## Pareto Frontier

- Non-dominated policies: `fleetqox_predictive`, `fleetqox_csds`, `lag_adapt_003`, `fleetqox_predictive_guarded`.

## Interpretation

- Highest mean utility: `fleetqox_predictive` at `8386.7`.
- No policy keeps zero measured miss across all three profiles in this smoke.

## Research Interpretation

- The LAN profile is not the hard case. All policies keep zero measured deadline
  miss; `fleetqox_predictive` dominates because it delivers much higher utility
  without needing the safety gate.
- The WAN and roaming profiles are infeasible for the current single-profile
  controller settings. Every policy shows large deadline miss, including guarded
  predictive and `lag_adapt_003`.
- `lag_adapt_003` still has value under WAN/roaming because it lowers deadline
  miss versus unguarded predictive while retaining more utility than guarded
  predictive in this one-seed smoke. It does not preserve the Wi-Fi zero-miss
  envelope once base latency and jitter exceed the control deadline slack.
- This invalidates a one-configuration claim. The next research step should be a
  profile-aware or context-aware controller that changes deadline budgets,
  admission aggressiveness, and perhaps control deadlines based on observed path
  RTT/jitter/capacity, rather than using one global Lagrangian parameter set.
- The stress run also exposed a harness issue: closed-loop feeder responses can
  timeout when the sidecar reaches max runtime first. `scripts/feed_sidecar_closed_loop.py`
  now treats that as a partial run with `termination_reason=response_timeout`
  instead of crashing, so impaired profiles still produce usable metrics.

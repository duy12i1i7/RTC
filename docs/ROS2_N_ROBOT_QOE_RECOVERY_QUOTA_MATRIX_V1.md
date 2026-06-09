# ROS 2 N-Robot QoE Recovery Quota Matrix V1

## Purpose

This milestone turns the four-robot QoE recovery smoke into a repeatable
N-robot matrix runner.  The goal is to stop treating a single Docker realization
as evidence and instead produce aggregate reports over robot counts and workload
seeds.  The first full matrix exposed the `8`-robot hard-SLO frontier: `4`
robots passed the hard/QoE gates over three seeds, while `8` robots ran to
completion but missed the hard per-robot budget.  The latest hardening audit
closes that `8`-robot frontier by combining source-sequence ACK/NACK with a
liveliness-backed retransmission horizon.

The matrix keeps the same live ROS 2 path:

- `rclpy` publisher emits command, odom, and scan topics for each robot
  namespace;
- live bridge forwards ROS 2 samples into the FleetQoX sidecar;
- sidecar runs the hard-SLO volatility guard plus fleet-quota QoE recovery;
- egress reconstructs typed local command and qualified state/perception
  projections;
- local controller, projection quality gate, and monitor all subscribe across
  the robot namespace set.

## New Runner

Implemented:

- `scripts/run_ros2_n_robot_qoe_quota_matrix.py`
  - wraps `scripts.run_ros2_docker_live_bridge`;
  - expands `--robot-counts` and `--seeds`;
  - runs one dynamic-objective transition matrix per robot count;
  - writes per-count live-bridge summaries and reports;
  - aggregates all rows into one JSON and Markdown report;
  - marks the largest robot count that satisfies both hard per-robot budget and
    quality-gate robot coverage.
- `tests/test_ros2_n_robot_qoe_quota_matrix.py`
  - verifies command construction;
  - verifies summary aggregation;
  - verifies missing-summary handling and positive-count validation.

## Reproduction

Run the current repeated matrix:

```bash
python3 -m scripts.run_ros2_n_robot_qoe_quota_matrix \
  --run \
  --keep-going \
  --robot-counts 4,8 \
  --seeds 7,13,29 \
  --seconds 4 \
  --rate-hz 10 \
  --bridge-max-batches 80 \
  --transition-segment-s 1.5 \
  --summary-json results_ros2_live_bridge/n_robot_qoe_recovery_quota_matrix_summary.json \
  --markdown results_ros2_live_bridge/n_robot_qoe_recovery_quota_matrix_report.md
```

The runner can later be extended without changing the underlying live bridge:

```bash
python3 -m scripts.run_ros2_n_robot_qoe_quota_matrix \
  --run \
  --keep-going \
  --robot-counts 4,8,16 \
  --seeds 7,13,29
```

## Artifacts

- `results_ros2_live_bridge/n_robot_qoe_recovery_quota_matrix_summary.json`
- `results_ros2_live_bridge/n_robot_qoe_recovery_quota_matrix_report.md`
- `results_ros2_live_bridge/dynamic_objective_transition_4robot_qoe_recovery_quota_3seed_summary.json`
- `results_ros2_live_bridge/dynamic_objective_transition_4robot_qoe_recovery_quota_3seed_report.md`
- `results_ros2_live_bridge/dynamic_objective_transition_8robot_qoe_recovery_quota_3seed_summary.json`
- `results_ros2_live_bridge/dynamic_objective_transition_8robot_qoe_recovery_quota_3seed_report.md`
- `results_ros2_live_bridge/n_robot_qoe_recovery_quota_8robot_liveliness_horizon_3seed_aggregate_summary.json`
- `results_ros2_live_bridge/n_robot_qoe_recovery_quota_8robot_liveliness_horizon_3seed_aggregate_report.md`
- `results_ros2_live_bridge/ros2_live_bridge_t3_dynamic_objective_transition_4robot_qoe_recovery_quota_3seed_v1_seed_7_quality_gate_decisions.jsonl`
- `results_ros2_live_bridge/ros2_live_bridge_t3_dynamic_objective_transition_4robot_qoe_recovery_quota_3seed_v1_seed_13_quality_gate_decisions.jsonl`
- `results_ros2_live_bridge/ros2_live_bridge_t3_dynamic_objective_transition_4robot_qoe_recovery_quota_3seed_v1_seed_29_quality_gate_decisions.jsonl`
- `results_ros2_live_bridge/ros2_live_bridge_t3_dynamic_objective_transition_8robot_qoe_recovery_quota_3seed_v1_seed_7_quality_gate_decisions.jsonl`
- `results_ros2_live_bridge/ros2_live_bridge_t3_dynamic_objective_transition_8robot_qoe_recovery_quota_3seed_v1_seed_13_quality_gate_decisions.jsonl`
- `results_ros2_live_bridge/ros2_live_bridge_t3_dynamic_objective_transition_8robot_qoe_recovery_quota_3seed_v1_seed_29_quality_gate_decisions.jsonl`

## Matrix Result

The original aggregate report marked `4` as the best passing robot count and
kept the first `8`-robot row as a useful negative scale result, not a runner
failure.  The latest accepted `8`-robot regression row now passes after the
liveliness ACK-horizon mechanism.

| robot count | runs | control delivery | loss | deadline miss | p95 ms | hard budget pass | min robot control | worst robot deadline | quality coverage |
| ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| `4` | `3/3` | `0.9957` | `0.0109` | `0.0773` | `422.22` | `1.0000` | `0.9825` | `0.1209` | `1.0000` |
| `8` original quota row | `3/3` | `0.7859` | `0.1960` | `0.1280` | `1387.09` | `0.0000` | `0.6164` | `0.1725` | `0.9583` |
| `8` liveliness ACK horizon | `3/3` | `0.9902` | `0.0311` | `0.1296` | `1085.30` | `1.0000` | `0.9804` | `0.1659` | `1.0000` |

The original `8`-robot run still observed all robot IDs in sidecar decisions,
receiver packets, egress publications, lease decisions, and monitor logs.  The
collapse was therefore not namespace discovery or local-service wiring.  It was
a transport recovery boundary in the admission/lease/control envelope.

## Four-Robot Pass Row

The repeated four-robot run completed all seeds:

| metric | value |
| --- | ---: |
| runs | `3/3` |
| robot count | `4` |
| RX mean | `91.3333` |
| loss mean | `0.0109` |
| control delivery mean | `0.9957` |
| deadline miss mean | `0.0773` |
| p95 latency mean | `422.22 ms` |
| semantic utility mean | `646.41` |
| hard per-robot budget pass | `1.0000` |
| min per-robot control delivery mean | `0.9825` |
| worst-robot deadline miss mean | `0.1209` |
| quality-gate robot coverage | `1.0000` |
| decision/receiver/egress/lease/monitor coverage | `1.0000` |

Per-seed rows:

| seed | RX | control | deadline miss | p95 ms | budget pass | quality coverage | worst deadline |
| --- | ---: | ---: | ---: | ---: | --- | ---: | ---: |
| `7` | `84` | `0.9870` | `0.0833` | `391.79` | yes | `1.0000` | `0.0952` |
| `13` | `104` | `1.0000` | `0.0673` | `554.86` | yes | `1.0000` | `0.0769` |
| `29` | `86` | `1.0000` | `0.0814` | `320.01` | yes | `1.0000` | `0.1905` |

## Eight-Robot Scale Row

The original runner completed all three `8`-robot seeds, but no seed passed the
hard per-robot budget:

| seed | RX | control | deadline miss | p95 ms | budget pass | quality coverage | min robot control | worst deadline |
| --- | ---: | ---: | ---: | ---: | --- | ---: | ---: | ---: |
| `7` | `115` | `0.9615` | `0.1304` | `1170.21` | no | `1.0000` | `0.8462` | `0.1538` |
| `13` | `108` | `0.6078` | `0.1389` | `1699.30` | no | `1.0000` | `0.4737` | `0.1818` |
| `29` | `122` | `0.7883` | `0.1148` | `1291.77` | no | `0.8750` | `0.5294` | `0.1818` |

Two signals matter most:

- the receive/fairness path still sees the fleet (`received`, `egress`,
  `lease`, and `monitor` robot coverage are all `1.0000`);
- the worst robot loses the hard service floor at `8` robots
  (`min_control_delivery` mean `0.6164`, with seed `13` falling to `0.4737`).

The current liveliness ACK-horizon audit reruns the `8`-robot row over the same
seed set and passes all three seeds:

| seed | RX | control | deadline miss | p95 ms | budget pass | quality coverage | min robot control | worst deadline |
| --- | ---: | ---: | ---: | ---: | --- | ---: | ---: | ---: |
| `7` | `138` | `1.0000` | `0.1087` | `1441.50` | yes | `1.0000` | `1.0000` | `0.1176` |
| `13` | `122` | `1.0000` | `0.1721` | `999.61` | yes | `1.0000` | `1.0000` | `0.2222` |
| `29` | `148` | `0.9706` | `0.1081` | `814.80` | yes | `1.0000` | `0.9412` | `0.1579` |

## Interpretation

This is the first repeated ROS 2 evidence that the fleet-quota QoE recovery lane
scales beyond two robots without giving back the hard per-robot budget.  The
original `8`-robot failure prevented an overclaim and showed that a sublinear
QoE probe quota was not enough by itself: the transport path also needed
source-sequence repair and enough sender-side recovery memory for late feedback.

The current conclusion is sharper than before: bounded state/perception QoE
recovery can coexist with hard control budgets in the current ROS 2 sidecar
bridge at `8` robots when ACK/NACK recovery is source-sequence aware,
backpressured, and retained for a liveliness-derived horizon.

## Follow-Up Mechanism

Implemented after the `8`-robot negative row:

- `RobotBudgetConfig.n_aware_control_floor_enabled`;
- a post-policy N-aware command service allocator inside
  `RobotBudgetAwareAdmissionController`;
- paced control-lease redundancy in `SidecarRuntime`, where the first control
  lease packet is sent immediately and redundant lease copies are queued for a
  later batch instead of being emitted as a same-burst duplicate;
- policy enablement for
  `fleetqox_semantic_contract_budgeted_deadline_first` and
  `fleetqox_semantic_contract_budgeted_action_deadline_first`;
- unit coverage proving that, for an eight-robot candidate set, the allocator
  reclaims non-control capacity and admits one minimal command representation
  per robot when the byte budget can fit those commands.
- unit coverage proving that deadline-first control-lease redundancy is paced
  through the runtime retransmission queue.
- adaptive ACK-only control-lease feedback in the egress bridge, with
  backpressure-driven ACK window expansion on feedback failure and slow
  contraction after success.

This started as a code-level mechanism, and the live benchmark now confirms the
direction.  The latest `8`-robot liveliness-horizon row passes all three seeds
and should become the regression artifact for future transport-boundary work.

One attempted `8`-robot/seed-`13` paced smoke is intentionally not counted as
algorithm evidence: the Zenoh router exited before ROS 2 nodes initialized, so
the aggregate marks it `invalid_infrastructure` with zero received packets.

## Latest Hardening Audit

The follow-up implementation has now been exercised against the `8`-robot live
bridge path.  The useful result is a sharper failure boundary, not a solved
scale claim.

Testbed hardening added during this audit:

- Zenoh router readiness is guarded by a healthcheck and `service_healthy`
  dependencies in the Docker compose path.
- The netem transition schedule is delayed until the live publisher window
  starts, so early Wi-Fi/WAN/roaming impairment is no longer accidentally
  applied during ROS 2 discovery/bootstrap.
- control-lease terminal replay keeps a short per-robot event history instead
  of replaying only one final lease.
- local lease ingestion rejects duplicate and stale lease IDs, so delayed
  retransmits cannot extend or replace a newer command lease.
- egress feedback can carry observed control-lease event IDs back to the
  sidecar.
- ACK-driven retransmission exists as an experimental runtime path.  It is still
  disabled by default for generic runs, but the persistent-feedback audit below
  shows it is the strongest current `8`-robot direction.
- egress, local-controller, and projection-quality feedback producers can reuse
  a persistent sidecar TCP client instead of opening a new TCP connection per
  feedback flush.
- egress also has an ACK-only immediate feedback option for control leases.  It
  is kept as an experimental negative-control mechanism because the live run
  below shows that ACKs can become their own congestion source.
- egress can coalesce ACK-only feedback into a bounded event window.  The first
  fixed-window audit uses `8` unique control-lease ACK events per flush.
- egress now also exposes an adaptive ACK pacer through Docker and the N-robot
  matrix runner.  Unlike the fixed window, it preserves pending ACKs after a
  feedback send failure, grows the event window under feedback backpressure, and
  shrinks it only after successful ACK delivery.  The current implementation is
  piggyback-first: normal robot feedback clears matching pending ACK-only
  records, and ACK-only batches are a fallback for stale pending ACKs or emergency
  backlog.
- transition-uncertainty redundancy and paced retransmit fairness are covered
  by unit tests, but are not yet sufficient as live `8`-robot evidence.

Measured artifacts:

| run | status | control delivery | loss | p95 ms | min robot control | quality coverage | interpretation |
| --- | --- | ---: | ---: | ---: | ---: | ---: | --- |
| `n_robot_qoe_recovery_quota_8robot_terminal_replay_3seed_summary.json` | `2/3` budget pass | `0.9752` mean | not aggregated in runner row | `703.89` mean | `0.9556` mean | `1.0000` | terminal replay helped two seeds but seed `29` still fell to `0.8667` min control |
| `n_robot_qoe_recovery_quota_8robot_ack_window_seed29_summary.json` | pass | `1.0000` | `0.0000` observed in the single run | `831.50` | `1.0000` | `0.8750` | batch ACK event IDs can recover one hard case |
| `n_robot_qoe_recovery_quota_8robot_ack_window_3seed_summary.json` | fail | `0.8526` mean | not aggregated in runner row | `1621.00` mean | `0.7130` mean | `1.0000` | same ACK idea is unstable over repeated seeds |
| `n_robot_qoe_recovery_quota_8robot_persistent_ack_seed29_summary.json` | pass | `0.9908` | `0.0213` | `640.10` | `0.9231` | `1.0000` | persistent feedback removes the connection-storm failure for seed `29` |
| `n_robot_qoe_recovery_quota_8robot_persistent_ack_3seed_summary.json` | `2/3` budget pass | `0.9647` mean | `0.0418` mean | `1359.86` mean | `0.8997` mean | `1.0000` | previous repeated `8`-robot best before ACK/NACK horizon; seed `13` still falls to `0.8421` min control |
| `n_robot_qoe_recovery_quota_8robot_persistent_ack_immediate_3seed_summary.json` | fail | `0.5936` mean | `0.4296` mean | `6747.10` mean | `0.4091` mean | `1.0000` | immediate ACK-only feedback is too chatty and becomes a control-plane bottleneck |
| `n_robot_qoe_recovery_quota_8robot_paced_ack8_seed13_summary.json` | pass | `0.9779` | `0.0581` | `1791.31` | not aggregated in runner row | `1.0000` | fixed ACK coalescing can recover the previously failing seed `13` |
| `n_robot_qoe_recovery_quota_8robot_paced_ack8_3seed_summary.json` | `1/3` budget pass | `0.8983` mean | `0.1084` mean | `2006.53` mean | `0.8346` mean | `1.0000` | fixed ACK coalescing is not stable across seeds |
| `n_robot_qoe_recovery_quota_8robot_adaptive_ack_timebounded_seed13_summary.json` | pass | `0.9694` | `0.1085` | `1933.72` | not aggregated in runner row | `1.0000` | time-bounded adaptive ACK-only can recover seed `13` alone |
| `n_robot_qoe_recovery_quota_8robot_adaptive_ack_timebounded_3seed_summary.json` | fail | `0.8723` mean | `0.1196` mean | `2213.17` mean | `0.7679` mean | `1.0000` | ACK-only fallback is still too much extra feedback load over repeated seeds |
| `n_robot_qoe_recovery_quota_8robot_adaptive_ack_piggyback_3seed_summary.json` | `2/3` budget pass | `0.9689` mean | `0.0358` mean | `1651.42` mean | `0.9500` mean | `1.0000` | previous piggyback-first control-floor row; seed `13` still fails at `0.8500` min control |
| `n_robot_qoe_recovery_quota_8robot_egress_acknack_seed13_aggregate_summary.json` | fail | `0.9444` | `0.0663` | `2012.22` | `0.8889` | `1.0000` | source ACK/NACK is connected, but fixed sender history expires too early for late NACK repair |
| `n_robot_qoe_recovery_quota_8robot_liveliness_horizon_seed13_aggregate_summary.json` | pass | `0.9830` | `0.0253` | `1731.48` | `0.9545` | `1.0000` | liveliness-backed history recovers the formerly failing seed `13` |
| `n_robot_qoe_recovery_quota_8robot_liveliness_horizon_3seed_aggregate_summary.json` | `3/3` budget pass | `0.9902` mean | `0.0311` mean | `1085.30` mean | `0.9804` mean | `1.0000` | current accepted `8`-robot hard-SLO bridge result |
| `n_robot_qoe_recovery_quota_8robot_aligned_temporal_guard_seed29_summary.json` | fail | `0.8235` | `0.1786` | `1812.28` | `0.6818` | `1.0000` | transition guard plus temporal pacing still overloads the burst window |
| `n_robot_qoe_recovery_quota_8robot_aligned_baseline_8s_seed29_summary.json` | fail | `0.8913` | `0.1127` | `1566.24` | `0.8261` | `1.0000` | longer observation improves coverage but still misses hard per-robot control |

The first ACK experiment that flushed feedback immediately is deliberately
excluded from the table as a negative engineering artifact: it created too many
short TCP feedback connections, reduced RX to `57`, and dropped control
delivery to `0.5476`.  It is useful only because it shows that feedback cadence
and transport are part of the control problem.

The strongest current conclusion is:

- the `8`-robot repeated row is now the accepted sidecar-scale hard-SLO
  regression gate;
- router readiness and netem/publisher timeline issues have been separated from
  the algorithmic failure;
- sidecar-level UDP redundancy and ACK eagerness are not sufficient by
  themselves;
- useful ACK/NACK needs source sequence, pacing/backpressure, and a sender-side
  recovery horizon long enough for late feedback under roaming;
- the next credible hard-real-time mechanism is not another ACK parameter row,
  but moving the same source/liveliness/recovery contract into the FleetRMW
  publish/take path.

## Next Gap

- Extend the minimal UDP socket-backed FleetRMW write/read boundary into a
  persistent retransmission loop so lease reliability is coupled to source
  sequence, effective lifespan, liveliness lease, and ROS QoS semantics, not
  inferred after a Python sidecar bridge.
- Keep the liveliness-horizon `8`-robot row as a regression gate while adding
  `16` robots and longer transition segments.
- Add bounded deficit round-robin or virtual-deadline ranking only after the
  transport-boundary path preserves the `8`-robot hard budget; allocator changes
  alone did not solve the tail robot.
- Add DDS/Zenoh-tuned baseline rows that do not use FleetQoX admission.
- Add confidence intervals over at least five seeds after the runner is stable.
- Connect the same matrix to ns-3/OMNeT++ scale tests for larger fleets.
- Move the proven sidecar boundary into minimal `rmw_fleetqox_cpp` pub/sub.

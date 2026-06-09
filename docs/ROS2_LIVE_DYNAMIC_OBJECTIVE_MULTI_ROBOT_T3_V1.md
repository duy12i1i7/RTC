# ROS 2 Live Dynamic Objective Multi-Robot T3 V1

## Purpose

This milestone extends the ROS 2 live dynamic-objective transition harness from
one robot namespace to multiple robot namespaces in one Docker bridge session.
It keeps the same FleetRMW/FleetQoX control-plane question:

- the ROS 2 bridge remains live while `tc netem` changes Wi-Fi -> WAN ->
  roaming at `0s`, `2s`, and `4s`;
- the active QoS/QoE objective changes `balanced_safety_utility@0` ->
  `autonomy_safety@2` -> `balanced_safety_utility@4`;
- the sidecar decision path refreshes `fleetrmw.transport_binding.v1` on every
  batch;
- the test publisher emits the same command/state/perception workload under
  separate robot namespaces.

The new evidence target is not only "can one bridge session adapt objective and
profile?".  It is "can the same ROS-backed bridge/sidecar/egress path preserve
objective-adaptive binding while handling more than one robot namespace?".

The follow-up local-services run extends that target to robot-local consumers:
the local control lease adapter, projection quality gate, and ROS monitor now
subscribe/publish across the same robot namespace set and report per-robot
coverage.

The per-robot budget follow-up makes the evidence stricter.  Instead of asking
only whether both robot IDs are present, the runner now measures per-robot
control delivery, deadline miss, latency spread, semantic utility, and Jain
fairness.  This turns multi-robot coverage into an explicit per-robot QoS/SLO
budget check.

## New Code

- `scripts/run_ros2_test_publisher.py`
  - Adds `--robot-count`.
  - Publishes `/robot_0000/...`, `/robot_0001/...`, and later namespaces from
    the same ROS 2 test publisher node.
  - Reports `robot_count` and total `published_messages` at shutdown.
- `scripts/run_ros2_docker_live_bridge.py`
  - Adds `--robot-count`.
  - Expands bridge topic configs by replacing the `robot_0000` namespace token
    with `robot_0001`, `robot_0002`, and so on.
  - Writes generated transition configs with `robot_count`.
  - Aggregates robot coverage from sidecar decisions, receiver packets, egress
    publications, local lease decisions, projection gate decisions, and monitor
    observations.
  - Adds robot-count columns to transition summary JSON and Markdown reports.
  - Adds per-robot budget thresholds and report columns for budget pass rate,
    Jain fairness, minimum control delivery, maximum deadline miss, latency p95
    spread, and worst robot IDs.
- `scripts/run_ros2_n_robot_qoe_quota_matrix.py`
  - Wraps the dynamic-objective live bridge runner across `robot-count x seed`
    rows.
  - Writes one summary/report per robot count and a matrix-level aggregate
    summary/report.
  - Marks the largest robot count that satisfies both hard per-robot budget and
    quality-gate robot coverage.
- `fleetqox/sidecar_metrics.py`
  - Adds `fleetrmw.per_robot_qos.v1` analysis over sidecar decisions and
    receiver logs.
  - Computes per-robot delivery/deadline/latency/utility metrics and a
    `fleetrmw.per_robot_qos_budget.v1` pass/fail report.
- `fleetqox/sidecar_runtime.py`
  - Adds batch-level fleet quota for volatility-guard QoE probes.
  - Defaults the quota to `ceil(scale * sqrt(active_robot_count))`, with an
    additional per-robot cap per tick so N-robot probe traffic does not grow
    linearly with fleet size.
  - Adds an uncertainty recovery lane: if the volatility guard would defer
    non-control traffic that already has semantic payload, the sidecar can admit
    a bounded `semantic_delta`/`degraded` probe instead of only waiting for a
    high-confidence stable estimate.
- `scripts/run_ros2_local_controller_lease.py`
  - Adds `--robot-count`.
  - Creates one lease state, subscription pair, safe-command publisher, and
    counter bucket per robot namespace in one ROS 2 node.
- `scripts/run_ros2_projection_quality_gate.py`
  - Adds `--robot-count`.
  - Creates one gate, pending identity queues, accepted odom/scan publishers,
    and counter bucket per robot namespace.
- `scripts/run_ros2_string_monitor.py`
  - Adds `--robot-id` and `--robot-count`.
  - Expands every configured monitor topic across robot namespaces.
- `external/ros2-live-bridge/docker-compose.yml`
  - Passes `ROS2_TEST_ROBOT_COUNT` into the ROS 2 test publisher, local
    controller, projection gate, and monitor.

## Reproduction

Run the two-robot dynamic-objective smoke:

```bash
python3 -m scripts.run_ros2_docker_live_bridge \
  --run \
  --analyze \
  --dynamic-objective-transition-matrix \
  --scenario ros2_live_bridge_t3_dynamic_objective_transition_2robot_smoke_v1 \
  --bridge-config experiments/ros2_live_bridge_tb4_binding_v1.json \
  --rmw rmw_zenoh_cpp \
  --seeds 7 \
  --robot-count 2 \
  --transition-profile wifi \
  --transition-profile wan \
  --transition-profile roaming \
  --transition-segment-s 2 \
  --seconds 6 \
  --rate-hz 12 \
  --bridge-max-batches 120 \
  --binding-objective-summary autonomy_safety:results_ros2_live_bridge/profile_objective_selector_autonomy_v1_summary.json \
  --binding-objective-schedule balanced_safety_utility@0,autonomy_safety@2,balanced_safety_utility@4 \
  --transition-summary-json results_ros2_live_bridge/dynamic_objective_transition_2robot_smoke_summary.json \
  --transition-markdown results_ros2_live_bridge/dynamic_objective_transition_2robot_smoke_report.md \
  --title "ROS 2 Live Dynamic Objective Transition 2-Robot Smoke T3 V1"
```

Run the repeated two-robot matrix:

```bash
python3 -m scripts.run_ros2_docker_live_bridge \
  --run \
  --analyze \
  --dynamic-objective-transition-matrix \
  --scenario ros2_live_bridge_t3_dynamic_objective_transition_2robot_3seed_v1 \
  --bridge-config experiments/ros2_live_bridge_tb4_binding_v1.json \
  --rmw rmw_zenoh_cpp \
  --seeds 7,13,29 \
  --robot-count 2 \
  --transition-profile wifi \
  --transition-profile wan \
  --transition-profile roaming \
  --transition-segment-s 2 \
  --seconds 6 \
  --rate-hz 12 \
  --bridge-max-batches 120 \
  --binding-objective-summary autonomy_safety:results_ros2_live_bridge/profile_objective_selector_autonomy_v1_summary.json \
  --binding-objective-schedule balanced_safety_utility@0,autonomy_safety@2,balanced_safety_utility@4 \
  --transition-summary-json results_ros2_live_bridge/dynamic_objective_transition_2robot_3seed_summary.json \
  --transition-markdown results_ros2_live_bridge/dynamic_objective_transition_2robot_3seed_report.md \
  --title "ROS 2 Live Dynamic Objective Transition 2-Robot 3-Seed T3 V1"
```

Run the repeated two-robot matrix with namespace-aware local services:

```bash
python3 -m scripts.run_ros2_docker_live_bridge \
  --run \
  --analyze \
  --dynamic-objective-transition-matrix \
  --scenario ros2_live_bridge_t3_dynamic_objective_transition_2robot_local_services_3seed_v1 \
  --bridge-config experiments/ros2_live_bridge_tb4_binding_v1.json \
  --rmw rmw_zenoh_cpp \
  --seeds 7,13,29 \
  --robot-count 2 \
  --transition-profile wifi \
  --transition-profile wan \
  --transition-profile roaming \
  --transition-segment-s 2 \
  --seconds 6 \
  --rate-hz 12 \
  --bridge-max-batches 120 \
  --binding-objective-summary autonomy_safety:results_ros2_live_bridge/profile_objective_selector_autonomy_v1_summary.json \
  --binding-objective-schedule balanced_safety_utility@0,autonomy_safety@2,balanced_safety_utility@4 \
  --transition-summary-json results_ros2_live_bridge/dynamic_objective_transition_2robot_local_services_3seed_summary.json \
  --transition-markdown results_ros2_live_bridge/dynamic_objective_transition_2robot_local_services_3seed_report.md \
  --title "ROS 2 Live Dynamic Objective Transition 2-Robot Local Services 3-Seed T3 V1"
```

Run the repeated two-robot matrix with per-robot QoS budget reporting:

```bash
python3 -m scripts.run_ros2_docker_live_bridge \
  --run \
  --analyze \
  --dynamic-objective-transition-matrix \
  --scenario ros2_live_bridge_t3_dynamic_objective_transition_2robot_fair_budget_3seed_v1 \
  --bridge-config experiments/ros2_live_bridge_tb4_binding_v1.json \
  --rmw rmw_zenoh_cpp \
  --seeds 7,13,29 \
  --robot-count 2 \
  --transition-profile wifi \
  --transition-profile wan \
  --transition-profile roaming \
  --transition-segment-s 2 \
  --seconds 6 \
  --rate-hz 12 \
  --bridge-max-batches 120 \
  --binding-objective-summary autonomy_safety:results_ros2_live_bridge/profile_objective_selector_autonomy_v1_summary.json \
  --binding-objective-schedule balanced_safety_utility@0,autonomy_safety@2,balanced_safety_utility@4 \
  --transition-summary-json results_ros2_live_bridge/dynamic_objective_transition_2robot_fair_budget_3seed_summary.json \
  --transition-markdown results_ros2_live_bridge/dynamic_objective_transition_2robot_fair_budget_3seed_report.md \
  --title "ROS 2 Live Dynamic Objective Transition 2-Robot Fair Budget 3-Seed T3 V1"
```

Run the same matrix with the budget-aware sidecar policy:

```bash
python3 -m scripts.run_ros2_docker_live_bridge \
  --run \
  --analyze \
  --dynamic-objective-transition-matrix \
  --scenario ros2_live_bridge_t3_dynamic_objective_transition_2robot_budgeted_3seed_v1 \
  --bridge-config experiments/ros2_live_bridge_tb4_binding_v1.json \
  --rmw rmw_zenoh_cpp \
  --policy fleetqox_semantic_contract_budgeted \
  --seeds 7,13,29 \
  --robot-count 2 \
  --transition-profile wifi \
  --transition-profile wan \
  --transition-profile roaming \
  --transition-segment-s 2 \
  --seconds 6 \
  --rate-hz 12 \
  --bridge-max-batches 120 \
  --binding-objective-summary autonomy_safety:results_ros2_live_bridge/profile_objective_selector_autonomy_v1_summary.json \
  --binding-objective-schedule balanced_safety_utility@0,autonomy_safety@2,balanced_safety_utility@4 \
  --transition-summary-json results_ros2_live_bridge/dynamic_objective_transition_2robot_budgeted_3seed_summary.json \
  --transition-markdown results_ros2_live_bridge/dynamic_objective_transition_2robot_budgeted_3seed_report.md \
  --title "ROS 2 Live Dynamic Objective Transition 2-Robot Budgeted 3-Seed T3 V1"
```

## Artifacts

- `results_ros2_live_bridge/ros2_live_bridge_t3_dynamic_objective_transition_2robot_smoke_v1_bridge_transition_config.json`
- `results_ros2_live_bridge/dynamic_objective_transition_2robot_smoke_summary.json`
- `results_ros2_live_bridge/dynamic_objective_transition_2robot_smoke_report.md`
- `results_ros2_live_bridge/ros2_live_bridge_t3_dynamic_objective_transition_2robot_3seed_v1_seed_7_metrics.jsonl`
- `results_ros2_live_bridge/ros2_live_bridge_t3_dynamic_objective_transition_2robot_3seed_v1_seed_13_metrics.jsonl`
- `results_ros2_live_bridge/ros2_live_bridge_t3_dynamic_objective_transition_2robot_3seed_v1_seed_29_metrics.jsonl`
- `results_ros2_live_bridge/dynamic_objective_transition_2robot_3seed_summary.json`
- `results_ros2_live_bridge/dynamic_objective_transition_2robot_3seed_report.md`
- `results_ros2_live_bridge/dynamic_objective_transition_2robot_local_services_smoke_summary.json`
- `results_ros2_live_bridge/dynamic_objective_transition_2robot_local_services_smoke_report.md`
- `results_ros2_live_bridge/dynamic_objective_transition_2robot_local_services_3seed_summary.json`
- `results_ros2_live_bridge/dynamic_objective_transition_2robot_local_services_3seed_report.md`
- `results_ros2_live_bridge/ros2_live_bridge_t3_dynamic_objective_transition_2robot_local_services_3seed_v1_seed_7_lease_decisions.jsonl`
- `results_ros2_live_bridge/ros2_live_bridge_t3_dynamic_objective_transition_2robot_local_services_3seed_v1_seed_7_quality_gate_decisions.jsonl`
- `results_ros2_live_bridge/ros2_live_bridge_t3_dynamic_objective_transition_2robot_local_services_3seed_v1_seed_13_lease_decisions.jsonl`
- `results_ros2_live_bridge/ros2_live_bridge_t3_dynamic_objective_transition_2robot_local_services_3seed_v1_seed_13_quality_gate_decisions.jsonl`
- `results_ros2_live_bridge/ros2_live_bridge_t3_dynamic_objective_transition_2robot_local_services_3seed_v1_seed_29_lease_decisions.jsonl`
- `results_ros2_live_bridge/ros2_live_bridge_t3_dynamic_objective_transition_2robot_local_services_3seed_v1_seed_29_quality_gate_decisions.jsonl`
- `results_ros2_live_bridge/dynamic_objective_transition_2robot_fair_budget_3seed_summary.json`
- `results_ros2_live_bridge/dynamic_objective_transition_2robot_fair_budget_3seed_report.md`
- `results_ros2_live_bridge/ros2_live_bridge_t3_dynamic_objective_transition_2robot_fair_budget_3seed_v1_seed_7_metrics.jsonl`
- `results_ros2_live_bridge/ros2_live_bridge_t3_dynamic_objective_transition_2robot_fair_budget_3seed_v1_seed_13_metrics.jsonl`
- `results_ros2_live_bridge/ros2_live_bridge_t3_dynamic_objective_transition_2robot_fair_budget_3seed_v1_seed_29_metrics.jsonl`
- `results_ros2_live_bridge/dynamic_objective_transition_2robot_budgeted_3seed_summary.json`
- `results_ros2_live_bridge/dynamic_objective_transition_2robot_budgeted_3seed_report.md`
- `results_ros2_live_bridge/dynamic_objective_transition_2robot_budgeted_floor_3seed_summary.json`
- `results_ros2_live_bridge/dynamic_objective_transition_2robot_budgeted_floor_3seed_report.md`
- `results_ros2_live_bridge/dynamic_objective_transition_2robot_budgeted_tailrisk_3seed_summary.json`
- `results_ros2_live_bridge/dynamic_objective_transition_2robot_budgeted_tailrisk_3seed_report.md`
- `results_ros2_live_bridge/robot_budget_policy_compare_summary.json`
- `results_ros2_live_bridge/robot_budget_policy_compare_report.md`
- `results_ros2_live_bridge/dynamic_objective_transition_4robot_qoe_recovery_quota_smoke_summary.json`
- `results_ros2_live_bridge/dynamic_objective_transition_4robot_qoe_recovery_quota_smoke_report.md`
- `results_ros2_live_bridge/ros2_live_bridge_t3_dynamic_objective_transition_4robot_qoe_recovery_quota_smoke_v1_quality_gate_decisions.jsonl`
- `results_ros2_live_bridge/dynamic_objective_transition_4robot_qoe_recovery_quota_3seed_summary.json`
- `results_ros2_live_bridge/dynamic_objective_transition_4robot_qoe_recovery_quota_3seed_report.md`
- `results_ros2_live_bridge/dynamic_objective_transition_8robot_qoe_recovery_quota_3seed_summary.json`
- `results_ros2_live_bridge/dynamic_objective_transition_8robot_qoe_recovery_quota_3seed_report.md`
- `results_ros2_live_bridge/n_robot_qoe_recovery_quota_matrix_summary.json`
- `results_ros2_live_bridge/n_robot_qoe_recovery_quota_matrix_report.md`

## Result

### Topic Expansion

The generated bridge config expands the three base TurtleBot-style topics to
six live subscriptions:

| robot | topics |
| --- | --- |
| `robot_0000` | `/cmd_vel`, `/odom`, `/scan` |
| `robot_0001` | `/cmd_vel`, `/odom`, `/scan` |

The publisher also emits camera payloads for both robots.  The current bridge
config intentionally subscribes to command/state/scan topics only, matching the
existing binding workload.

### Two-Robot Smoke

The smoke run completed `1/1` seed.  The bridge subscribed to six ROS 2 topics,
the publisher reported `robot_count=2` and `552` published messages, and both
robot IDs appeared in the decision, receiver, and egress logs.

| metric | value |
| --- | ---: |
| rx packets | `186` |
| loss | `0.0792` |
| control delivery | `0.9103` |
| deadline miss | `0.2527` |
| p95 latency | `156.73 ms` |
| profile switches | `2` |
| objective switches | `2` |
| policy switches | `2` |
| decision robots observed | `2` |
| received robots observed | `2` |
| egress robots observed | `2` |

### Two-Robot Three-Seed Matrix

The repeated Docker run completed `3/3` seeds with status `ran`.  Every seed
observed both robot IDs in sidecar decisions, receiver packets, and egress
publications.  Every seed also matched both scheduled profile switches and both
scheduled objective switches.

Mean dynamic binding result:

| policy | runs | robots | rx | loss | control delivery | deadline miss | p95 ms | utility |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| `dynamic_objective/rmw_zenoh_cpp` | `3` | `2.0` | `159.33` | `0.0637` | `0.9432` | `0.2472` | `121.69` | `844.71` |

Mean transition evidence:

| metric | value |
| --- | ---: |
| decision robots observed/run | `2.0` |
| received robots observed/run | `2.0` |
| egress robots observed/run | `2.0` |
| profile switches/run | `2.0` |
| matched profile switches/run | `2.0` |
| profile switch mean absolute latency | `0.2761 s` |
| objective switches/run | `2.0` |
| matched objective switches/run | `2.0` |
| objective switch mean absolute latency | `0.0797 s` |
| objective flapping/run | `0.0` |
| policy switches/run | `2.0` |
| decision rows with binding estimate/run | `191.0` |

Per-seed rows:

| seed | rx | loss | control delivery | p95 ms | decision robots | received robots | egress robots |
| ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| `7` | `196` | `0.0622` | `0.9241` | `122.42` | `2` | `2` | `2` |
| `13` | `127` | `0.0797` | `0.9057` | `120.93` | `2` | `2` | `2` |
| `29` | `155` | `0.0491` | `1.0000` | `121.72` | `2` | `2` | `2` |

Observed binding coverage:

| dimension | values |
| --- | --- |
| robots | `robot_0000`, `robot_0001` |
| profiles | `wifi`, `wan`, `roaming` |
| objectives | `balanced_safety_utility`, `autonomy_safety` |
| packet formats | `data_frame`, `event_json` |

### Two-Robot Local Services Three-Seed Matrix

The namespace-aware local-services run completed `3/3` seeds.  In every seed,
all six robot coverage points observed both robots:

- sidecar decisions;
- UDP receiver packets;
- egress ROS publications;
- local control lease decisions;
- projection quality gate decisions;
- ROS monitor observations.

Mean dynamic binding and local-service result:

| policy | runs | robots | rx | loss | control delivery | deadline miss | p95 ms | utility |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| `dynamic_objective/rmw_zenoh_cpp` | `3` | `2.0` | `148.67` | `0.0542` | `0.9524` | `0.2661` | `131.93` | `790.50` |

Mean robot coverage:

| coverage point | robots/run | observed robots |
| --- | ---: | --- |
| sidecar decisions | `2.0` | `robot_0000`, `robot_0001` |
| UDP receiver | `2.0` | `robot_0000`, `robot_0001` |
| egress publications | `2.0` | `robot_0000`, `robot_0001` |
| local leases | `2.0` | `robot_0000`, `robot_0001` |
| projection gate | `2.0` | `robot_0000`, `robot_0001` |
| monitor | `2.0` | `robot_0000`, `robot_0001` |

Per-seed local-service coverage:

| seed | rx | loss | control delivery | p95 ms | lease robots | gate robots | monitor robots |
| ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| `7` | `124` | `0.0677` | `0.9200` | `132.96` | `2` | `2` | `2` |
| `13` | `153` | `0.0497` | `0.9667` | `123.25` | `2` | `2` | `2` |
| `29` | `169` | `0.0452` | `0.9706` | `139.58` | `2` | `2` | `2` |

### Two-Robot Per-Robot QoS Budget Three-Seed Matrix

The per-robot budget run completed `3/3` seeds.  It used the same
Wi-Fi/WAN/roaming transition and objective schedule as the local-services
matrix, but added explicit budget gates:

- minimum per-robot control delivery: `0.90`;
- maximum per-robot deadline miss: `0.35`;
- minimum RX Jain fairness: `0.90`;
- minimum control-delivery Jain fairness: `0.95`;
- minimum deadline-success Jain fairness: `0.95`.

Mean result:

| policy | runs | robots | robot budget pass | rx fairness | ctrl fairness | deadline fairness | min ctrl delivery | max deadline miss | p95 spread ms |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| `dynamic_objective/rmw_zenoh_cpp` | `3` | `2.0` | `0.3333` | `1.0000` | `0.9984` | `0.9997` | `0.8950` | `0.3036` | `7.09` |

Fleet-level means still look acceptable: rx `154.33`, loss `0.0692`,
control delivery `0.9328`, deadline miss `0.2920`, p95 latency `128.42 ms`,
and delivered utility `818.53`.  The stricter per-robot budget exposes the
missing control-boundary mechanism: two of the three seeds fail because the
worst robot falls below the `0.90` control-delivery SLO even though aggregate
control delivery remains above `0.90`.

Per-seed per-robot budget rows:

| seed | pass | rx fairness | ctrl fairness | deadline fairness | min ctrl delivery | max deadline miss | p95 spread ms | worst ctrl | worst deadline |
| ---: | --- | ---: | ---: | ---: | ---: | ---: | ---: | --- | --- |
| `7` | yes | `0.9999` | `0.9986` | `0.9997` | `0.9286` | `0.3000` | `2.03` | `robot_0000` | `robot_0001` |
| `13` | no | `0.9999` | `0.9982` | `0.9999` | `0.8846` | `0.3235` | `7.23` | `robot_0001` | `robot_0001` |
| `29` | no | `1.0000` | `0.9982` | `0.9994` | `0.8718` | `0.2872` | `12.00` | `robot_0001` | `robot_0001` |

### Two-Robot Budget-Aware Policy Three-Seed Matrix

The budget-aware sidecar sequence now has three validation points:

- `budgeted`: virtual queues are wired into the live sidecar path, but
  predicted-decision pressure alone does not solve the per-robot SLO;
- `budgeted_floor`: a minimum control-service floor is available, but it does
  not activate when the base semantic contract already sends control intent;
- `tailrisk`: network-tail-risk pressure plus semantic shaping activates under
  WAN/roaming and solves the short two-robot per-robot budget matrix.

Policy comparison:

| policy | budget pass | min ctrl | max deadline | ctrl delivery | deadline miss | p95 ms | utility |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| baseline | `0.3333` | `0.8950` | `0.3036` | `0.9328` | `0.2920` | `128.42` | `818.53` |
| budgeted | `0.3333` | `0.8974` | `0.2783` | `0.9101` | `0.2507` | `120.56` | `806.17` |
| budgeted_floor | `0.3333` | `0.8992` | `0.2650` | `0.9330` | `0.2506` | `122.99` | `751.44` |
| tailrisk | `1.0000` | `0.9222` | `0.3239` | `0.9422` | `0.2931` | `132.73` | `767.96` |

Per-seed tail-risk rows:

| seed | pass | min ctrl delivery | max deadline miss | worst ctrl | rx | ctrl delivery | deadline miss | p95 ms |
| ---: | --- | ---: | ---: | --- | ---: | ---: | ---: | ---: |
| `7` | yes | `0.9333` | `0.3284` | `robot_0000` | `143` | `0.9500` | `0.2937` | `129.49` |
| `13` | yes | `0.9167` | `0.3214` | `robot_0000` | `109` | `0.9184` | `0.2936` | `145.22` |
| `29` | yes | `0.9167` | `0.3218` | `robot_0000` | `178` | `0.9583` | `0.2921` | `123.47` |

Decision-log evidence:

| seed | robot_budget active | pressure_shaping | control floor |
| ---: | ---: | ---: | ---: |
| `7` | `114` | `25` | `0` |
| `13` | `84` | `28` | `0` |
| `29` | `130` | `29` | `0` |

The result is a real SLO win with an explicit trade-off.  Tail-risk pressure
raises budget pass from `0.3333` to `1.0000` and raises mean minimum per-robot
control delivery from `0.8950` to `0.9222`.  It also increases p95 latency and
exposes a large per-robot p95 spread in seed `13`, so the next problem is
closed-loop QoE/latency optimization, not another proof that pressure can be
wired into the sidecar.

### Multi-Source Deadline Ownership Reanalysis

The multi-source feedback branch exposed a measurement bug in the original
deadline accounting.  `control_intent` and `supervisory_intent` packets are ROS
2 control leases, not raw actuator commands.  Since the local lease window
starts at robot receive time, their WAN transit time should not be counted as
egress deadline miss.  The corrected analyzer keeps control delivery and
latency evidence at egress, but assigns command freshness/deadline evidence to
the local-controller feedback source.

Reanalyzing the existing one-seed
`feedback_multisource_arbitrated_v2_deadlinefirst_smoke_v1` log with that rule
turns the run into a hard-budget pass:

| metric | value |
| --- | ---: |
| rx packets | `175` |
| loss | `0.0691` |
| aggregate control delivery | `0.9500` |
| aggregate deadline miss | `0.2971` |
| p95 latency | `284.66 ms` |
| utility | `953.89` |
| minimum per-robot control delivery | `0.9000` |
| maximum per-robot deadline miss | `0.3483` |
| RX Jain | `0.9997` |
| control-delivery Jain | `0.9972` |
| deadline-success Jain | `0.9946` |

The reanalysis artifact is
`results_ros2_live_bridge/control_lease_deadline_ownership_reanalysis_v1.json`.
The action-deadline branch remains a useful but not-yet-passing variant after
the same correction: RX `178`, utility `1010.71`, minimum control delivery
`0.9767`, but worst-robot deadline miss `0.3820`.

The corrected live path was then rerun as
`feedback_deadline_ownership_smoke_v1`.  That smoke applies all three feedback
sources in one ROS 2 bridge session (`146` applied records, `1` failed quality
flush), observes both robot IDs through decisions, receiver, egress, lease,
quality gate, and monitor logs, and passes the hard per-robot budget with
minimum control delivery `0.9091`, maximum deadline miss `0.2319`, RX Jain
`0.9991`, control Jain `0.9990`, and deadline-success Jain `0.9996`.

The repeated follow-up separates hard-SLO enforcement from QoE recovery.  A
deadline-ownership 3-seed run with redundant control leases improves control
delivery to `0.9932` but still fails one hard budget dimension (`robot_budget`
`0.0000`) because non-control telemetry can become late during startup and
profile transitions.  Adding the transport-volatility guard defers non-control
packets while the binding estimate is low-confidence or newly changed.  The
3-seed scenario
`ros2_live_bridge_t3_dynamic_objective_transition_2robot_feedback_deadline_ownership_volatility_guard_3seed_v1`
passes all seeds: mean RX `70.3333`, loss `0.0128`, control delivery `0.9872`,
deadline miss `0.0000`, p95 `241.78 ms`, minimum per-robot control delivery
`0.9872`, worst-robot deadline miss `0.0000`, and all control/deadline fairness
indices `1.0000` except RX Jain `0.99995`.  The cost is deliberate: quality
gate robot coverage drops to `0.0000`, so this run should be treated as the
hard-SLO safe envelope for the next QoE recovery step.

The QoE recovery step adds a bounded low-cost probe inside that safe envelope.
The sidecar can now let only `semantic_delta`/`degraded` state, perception, or
human-QoE packets through the volatility guard, rate-limited per robot/class
and gated by binding-estimator confidence, margin, dwell, and predicted slack.
The default stable-probe run
`ros2_live_bridge_t3_dynamic_objective_transition_2robot_feedback_deadline_ownership_qoe_stable_probe_3seed_v1`
also passes all seeds: mean RX `77.6667`, loss `0.0127`, control delivery
`0.9870`, deadline miss `0.0171`, p95 `293.40 ms`, semantic utility `564.22`,
minimum per-robot control delivery `0.9738`, worst-robot deadline miss
`0.0264`, and quality-gate robot coverage `2.0000`.  Its accepted quality-gate
samples are conservative downsampled scan projections (`2` per seed, one per
robot).  An earlier aggressive probe admitted more QoE samples, including
semantic odometry, but raised non-control deadline miss; the stable probe is
therefore the current safe default, not the final QoE optimum.

The four-robot follow-up makes the QoE recovery lane scale-aware instead of
robot-count linear.  The runtime now selects recovery probes at batch level with
a fleet quota of `ceil(scale * sqrt(active_robot_count))` and a per-robot cap of
one probe per tick.  It also admits low-cost semantic probes during uncertain
binding epochs instead of requiring the estimator to be stable before any QoE
evidence can be collected.  In the ROS 2 live smoke
`ros2_live_bridge_t3_dynamic_objective_transition_4robot_qoe_recovery_quota_smoke_v1`,
the bridge subscribes to `12` live ROS 2 topics and the quality gate observes
all four robot namespaces.  The run completes `1/1` seed with RX `101`, loss
`0.0098`, control delivery `1.0000`, deadline miss `0.0891`, p95 `422.02 ms`,
semantic utility `719.68`, budget pass `1.0000`, worst-robot deadline miss
`0.1154`, and quality-gate robot coverage ratio `1.0000`.  The quality gate
accepts `9` qualified projections across all four robots (`6` odom, `3` scan).
This is not a final performance claim because it is still a one-seed smoke and
p95 rises when QoE probes are admitted.  It does close the previous structural
gap: state/perception QoE can be recovered through the actual ROS 2 qualified
projection path for more than two robots while preserving the hard per-robot
budget envelope.

The repeated matrix runner then reruns the same four-robot scenario over seeds
`7,13,29`.  The 3-seed run
`ros2_live_bridge_t3_dynamic_objective_transition_4robot_qoe_recovery_quota_3seed_v1`
completes all seeds with hard per-robot budget pass `1.0000` and quality-gate
robot coverage ratio `1.0000`.  Mean RX is `91.3333`, loss `0.0109`, control
delivery `0.9957`, deadline miss `0.0773`, p95 `422.22 ms`, semantic utility
`646.41`, minimum per-robot control delivery `0.9825`, and worst-robot deadline
miss `0.1209`.  Per-seed p95 still varies widely (`320.01 ms` to
`554.86 ms`), so this promotes the claim from one-smoke structural feasibility
to repeated short-run evidence, not to final fleet-scale dominance.

The first larger-N row is intentionally kept as a negative result.  The same
matrix over `8` robots and seeds `7,13,29` completes `3/3` runs, subscribes to
`24` live ROS 2 topics, and keeps robot coverage at `1.0000` for sidecar
decisions, receiver packets, egress publications, lease decisions, and monitor
observations.  However, it fails every hard per-robot budget row: mean control
delivery drops to `0.7859`, loss rises to `0.1960`, p95 rises to
`1387.09 ms`, mean minimum per-robot control delivery falls to `0.6164`, and
quality-gate coverage falls to `0.9583` because seed `29` misses one robot at
the projection gate.  The current aggregate matrix therefore marks `4` as the
best passing robot count.

## Interpretation

This is the first ROS-backed multi-robot evidence for FleetRMW's dynamic
profile/objective binding path.  It shows that the same bridge session can
carry two robot namespaces, update binding decisions per batch, switch packet
format at the sidecar data-plane boundary, and preserve robot coverage through
receiver and egress logs while the network profile and objective both change.

The local-services follow-up closes the previous bridge-only limitation for the
two-robot case: local controller leases, projection quality gates, and monitor
topics are now namespace-aware and all observe both robot IDs over repeated
seeds.  This makes the claim end-to-end for a short two-robot local-control
path, not only for sidecar transport.

The per-robot budget follow-up changes the claim again.  It shows that high
Jain fairness can coexist with an SLO failure when both robots degrade
similarly but the worst robot dips below the absolute control-delivery budget.
For fleet control, relative fairness is therefore not enough; the control plane
must enforce absolute per-robot safety/QoE budgets while still optimizing fleet
utility.

The tail-risk follow-up is the first ROS-backed evidence that FleetRMW can turn
LAN/WAN/Wi-Fi/roaming path conditions into robot-specific SLO pressure and
semantic shaping decisions.  It solves the short two-robot budget matrix, while
also showing why the research cannot stop at open-loop path estimates: QoE and
tail latency need feedback from the actual receiver, egress, local lease, and
quality-gate outcomes.

The volatility-guard follow-up makes that gap sharper: hard deadline and
control budgets can be made robust over repeated ROS 2 live runs, but only by
temporarily suppressing state/perception traffic during uncertain binding
epochs.  The stable-probe follow-up shows that a small amount of perception QoE
can be restored without losing the hard per-robot budget, but it also shows the
new frontier: recovering richer state/perception utility without reintroducing
startup/profile-transition tail debt.

The four-robot quota matrix narrows that frontier again.  The missing mechanism
was not another static threshold; it was fleet-level probe admission plus a
repeatable N-robot benchmark wrapper.  Probe traffic now has an explicit
scaling law and robot-level rotation, so the middleware can collect QoE evidence
under uncertainty without opening a per-robot linear burst.

The eight-robot row exposes the next frontier.  The namespace expansion and
local service wiring hold, but the hard service floor does not.  A scalable
FleetRMW control plane therefore needs an explicit N-aware command service
allocator: every robot must receive bounded command progress first, and only the
remaining transition budget can be spent on QoE probes, late state/perception,
or utility recovery.

That allocator now exists in the sidecar controller as an optional post-policy
floor.  It is enabled for the deadline-first policy branches used by this
matrix, and unit coverage verifies the eight-robot case where non-control
capacity must be reclaimed so every robot receives one minimal command
representation.  The live `8`-robot row above remains the pre-allocator
negative artifact until the Docker matrix is rerun.

The runtime also now supports paced control-lease redundancy.  The previous
redundant lease path emitted duplicate control packets immediately; the paced
path sends the primary lease now and queues redundant copies for later batches.
This targets the measured `8`-robot failure mode where every control decision
can be admitted but only a subset reaches the receiver/local lease path.  A
post-change Docker rerun was attempted, but it is not counted because the Zenoh
router exited before ROS 2 nodes initialized; the aggregate marks that artifact
`invalid_infrastructure`.

The sidecar now has the feedback boundary for that next step: a
`robot_feedback` TCP message updates the active budget controller's virtual
queues when `fleetqox_semantic_contract_budgeted` is running. Unit tests verify
that a feedback message changes the following scheduling round. The sidecar TCP
server now handles concurrent bridge and feedback clients, and the ROS 2 egress
bridge can aggregate receiver-side outcomes into feedback windows.

Live producer smoke:

| scenario | seed | feedback sent | feedback failed | budget pass | control delivery | p95 ms |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| `feedback_core_window_smoke_v1` | `7` | `28` | `0` | `0.0` | `0.9024` | `293.18` |
| `feedback_damped_smoke_v1` | `7` | `22` | `2` | `0.0` | `0.9412` | `399.36` |
| `feedback_qoe_smoke_v1` | `7` | `24` | `1` | `0.0` | `0.8987` | `302.53` |
| `feedback_control_first_qoe_smoke_v1` | `7` | `26` | `1` | `0.0` | `0.9136` | `309.82` |
| `feedback_deadline_first_policy_smoke_v1` | `7` | `18` | `3` | `0.0` | `0.9846` | `302.45` |
| `feedback_multisource_smoke_v1` | `7` | `177` | `4` | `0.0` | `0.9012` | `320.51` |
| `feedback_multisource_arbitrated_v2_smoke_v1` | `7` | `139` | `2` | `0.0` | `0.9722` | `299.45` |
| `feedback_multisource_arbitrated_v2_deadlinefirst_smoke_v1` | `7` | `205` | `0` | `0.0` | `0.9500` | `284.66` |
| `feedback_action_deadline_first_v2_smoke_v1` | `7` | `208` | `0` | `0.0` | `0.9885` | `293.55` |
| `feedback_deadline_ownership_smoke_v1` | `7` | `146` | `1` | `1.0` | `0.9394` | `262.47` |

The damped producer uses sample-count-aware learning, caps deadline-risk
feedback, and excludes perception-only misses from the core deadline feedback
signal. It reduces overreaction in the decision log: `pressure_shaping` drops
from `74` to `42`, `drop` from `32` to `22`, and `defer` from `38` to `18`.
That is enough to recover aggregate control delivery from `0.9024` to `0.9412`,
but not enough to promote feedback to the benchmark path: budget pass remains
`0.0`, deadline miss rises from `0.5723` to `0.6405`, and p95 rises to
`399.36 ms`.

The QoE feedback follow-up adds latency fields to each feedback window and keeps
latency debt separate from service debt.  Critical-flow gain and control-floor
rescue still use control/deadline pressure, while non-critical shaping uses total
pressure including latency.  That improves deadline miss to `0.5097` and pulls
p95 back down to `302.53 ms` versus the damped feedback smoke, but it also lowers
worst-robot control delivery to `0.8718`.  The stable benchmark therefore
remains the tail-risk three-seed run; feedback now needs a lexicographic
control-first objective, not just additive latency pressure.

The control-first follow-up gates latency pressure by control-delivery headroom.
It recovers aggregate control delivery to `0.9136`, worst-robot control delivery
to `0.9024`, RX to `163`, and utility to `906.17`, but budget pass is still
`0.0` because worst-robot deadline miss is `0.7125`.  The active feedback gap is
now narrower: the controller needs a deadline-first inner loop inside the
control-first envelope.

The deadline-first inner loop is intentionally a separate experimental policy,
`fleetqox_semantic_contract_budgeted_deadline_first`, not a replacement for the
stable budgeted policy.  It adds deadline debt as extra non-critical shaping
pressure.  In the policy smoke, aggregate control delivery reaches `0.9846`,
worst-robot control delivery reaches `0.9697`, RX is `144`, loss is `0.0649`,
and utility is `797.30`; budget pass still remains `0.0` because worst-robot
deadline miss is `0.5694`.  Tail-risk remains the hard-SLO benchmark, while this
policy is a high-control/high-utility feedback branch that still needs lower
deadline miss and p95.

The multi-source feedback smoke keeps the stable
`fleetqox_semantic_contract_budgeted` policy and enables all current producers:
egress feedback from received samples, local-controller feedback from command
delivery decisions, and projection-quality feedback from publish/drop outcomes.
The run applies `24` egress, `60` local-controller, and `93` quality-gate
records.  RX and utility improve to `166` and `912.44`, but budget pass stays
`0.0`; worst-robot control delivery drops to `0.8049`, worst-robot deadline miss
is `0.6000`, and p95 is `320.51 ms`.  That makes the result a boundary
validation, not a benchmark upgrade: the system can now close the loop from
multiple ROS-side outcomes, but it still needs principled arbitration across
feedback sources.

The arbitration follow-up makes feedback partial and source-aware.  Missing
dimensions no longer imply success: a projection-quality record can update
QoE/latency debt without crediting control, local-controller records use
robot-side responsibility weights, and egress records remain the strongest
receiver-visible evidence.  A conservative first pass over-corrected and reduced
RX to `97` with control `0.8491`; it is kept only as a negative result.  The v2
pass recovers control and keeps the stable budgeted policy: RX is `139`, control
delivery is `0.9722`, loss is `0.0608`, p95 is `299.45 ms`, and utility is
`786.54`.  The same arbitration under the deadline-first policy is the current
best multi-source QoE branch: RX is `175`, utility is `953.89`, control delivery
is `0.9500`, and p95 is `284.66 ms`.  It still fails budget pass because
worst-robot deadline miss is `0.6517`.  A deadline-debt firewall knob was tested
but left disabled by default because its smoke worsened p95 and worst-robot
deadline miss.  A control horizon-lift knob was also tested; it reduced RX to
`90` and is disabled by default.

Action-aware deadline attribution extends that path below robot-level feedback.
Egress feedback windows now report deadline miss ratios by
`flow_class:wire_mode`, and the budget wrapper stores per-transform deadline
debt.  The experimental `fleetqox_semantic_contract_budgeted_action_deadline_first`
policy keeps this signal available for targeted transform changes.  Its v2 smoke
improves the multi-source utility/control branch: RX is `178`, utility is
`1010.71`, aggregate control delivery is `0.9885`, loss is `0.0481`, and p95 is
`293.55 ms`.  Budget pass remains `0.0` because worst-robot deadline miss is
`0.6629`.  Lowering the action threshold enough to trigger horizon lifts is a
negative result: RX falls to `145` and p95 rises to `378.50 ms`.

The RMW field in `TransportBinding` also remains target metadata in this path:
the running ROS 2 process uses `rmw_zenoh_cpp` for the whole session.  The
packet-format portion is already executable in the sidecar; the native
`rmw_fleetqox_cpp` milestone is where per-flow/per-fleet transport binding can
become a true middleware boundary.

## Next Gap

The next research gap is not another fixed tuning sweep.  It is a scaling,
fairness, and control-boundary problem:

- scale the namespace-aware controller/gate path beyond two robots;
- rerun the measured `8`-robot collapse with the N-aware command service
  allocator and paced control-lease redundancy enabled before attempting `16`
  robots;
- extend the current `4/8` QoE quota matrix to longer segments and confidence
  intervals once the `8`-robot row reaches hard budget pass;
- refine the deadline-first feedback policy so it lowers worst-robot deadline
  miss below budget without sacrificing the control and utility gains;
- use the new action-aware attribution signal to prevent `control_intent`,
  state, and perception deadline misses before they become receiver-visible tail
  latency;
- make pressure shaping latency- and QoE-aware so budget pass does not require
  large p95 spread in unlucky seeds;
- stress the same path with longer dwell windows, more robots, asymmetric robot
  priorities, and mixed objectives;
- move the binding decision from sidecar metadata into `rmw_fleetqox_cpp`.

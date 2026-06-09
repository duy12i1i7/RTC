# ROS 2 Live Dynamic Objective Binding T3 V1

## Purpose

This milestone adds runtime QoS/QoE objective changes to the ROS 2 live
transport-binding path.  The previous transition matrix changed only the
network profile: Wi-Fi -> WAN -> roaming.  This run changes both the network
profile and the active transport objective inside one bridge session:

- `0s`: `balanced_safety_utility`;
- `2s`: `autonomy_safety`;
- `4s`: `balanced_safety_utility`.

The implementation keeps the ROS 2 live bridge, sidecar, egress bridge, local
controller, projection quality gate, UDP receiver, and `tc netem` schedule
unchanged.  The new behavior is in the binding control plane: a bridge config
can now carry multiple objective selector summaries and an
`objective_schedule`.  Each bridge batch resolves the current network profile
and the current objective before attaching `fleetrmw.transport_binding.v1`.

The latest measured run repeats this dynamic-objective transition over seeds
`7,13,29`, using the same Wi-Fi -> WAN -> roaming schedule and the same
balanced -> autonomy -> balanced objective schedule.

A follow-up milestone extends the same schedule to a two-robot namespace
workload and records robot coverage through sidecar decisions, receiver
packets, egress publications, local lease decisions, projection gate decisions,
and monitor observations.  See
`docs/ROS2_LIVE_DYNAMIC_OBJECTIVE_MULTI_ROBOT_T3_V1.md`.

## New Code

- `fleetqox/transport_selector.py`
  - `TransportBindingManager` can resolve a binding by `(profile, objective)`.
  - Adaptive profile estimation can keep its profile state while selecting the
    binding for the currently active objective.
- `fleetqox/ros2_live_bridge.py`
  - Adds `LiveBindingContext` with tick, timestamp, and elapsed time.
  - Adds `objective_summaries` and `objective_schedule` to
    `LiveTransportBindingConfig`.
  - Keeps backward compatibility with old one-argument binding providers.
- `scripts/run_ros2_docker_live_bridge.py`
  - Adds `--binding-objective-summary objective:path`.
  - Adds `--binding-objective-schedule objective@seconds,...`.
  - Extends transition summaries with observed objectives, objective switches,
    and policy switches.

## Reproduction

Generate the autonomy selector:

```bash
python3 -m scripts.select_ros2_transport \
  --summary results_ros2_live_bridge/ros2_live_bridge_t3_repeated_packet_wifi_3seed_v1_summary.json \
  --summary results_ros2_live_bridge/ros2_live_bridge_t3_repeated_packet_wan_3seed_v1_summary.json \
  --summary results_ros2_live_bridge/ros2_live_bridge_t3_repeated_packet_roaming_3seed_v1_summary.json \
  --objective autonomy_safety \
  --summary-json results_ros2_live_bridge/profile_objective_selector_autonomy_v1_summary.json \
  --markdown results_ros2_live_bridge/profile_objective_selector_autonomy_v1_report.md
```

Run the one-seed dynamic-objective live transition smoke:

```bash
python3 -m scripts.run_ros2_docker_live_bridge \
  --run \
  --analyze \
  --scenario ros2_live_bridge_t3_dynamic_objective_transition_smoke_v1 \
  --bridge-config experiments/ros2_live_bridge_tb4_binding_v1.json \
  --rmw rmw_zenoh_cpp \
  --transition-profile wifi \
  --transition-profile wan \
  --transition-profile roaming \
  --transition-segment-s 2 \
  --seconds 6 \
  --rate-hz 20 \
  --bridge-max-batches 120 \
  --binding-objective-summary autonomy_safety:results_ros2_live_bridge/profile_objective_selector_autonomy_v1_summary.json \
  --binding-objective-schedule balanced_safety_utility@0,autonomy_safety@2,balanced_safety_utility@4 \
  --json
```

Run the repeated dynamic-objective live transition matrix:

```bash
python3 -m scripts.run_ros2_docker_live_bridge \
  --run \
  --analyze \
  --dynamic-objective-transition-matrix \
  --scenario ros2_live_bridge_t3_dynamic_objective_transition_3seed_v1 \
  --bridge-config experiments/ros2_live_bridge_tb4_binding_v1.json \
  --rmw rmw_zenoh_cpp \
  --seeds 7,13,29 \
  --transition-profile wifi \
  --transition-profile wan \
  --transition-profile roaming \
  --transition-segment-s 2 \
  --seconds 6 \
  --rate-hz 20 \
  --bridge-max-batches 120 \
  --binding-objective-summary autonomy_safety:results_ros2_live_bridge/profile_objective_selector_autonomy_v1_summary.json \
  --binding-objective-schedule balanced_safety_utility@0,autonomy_safety@2,balanced_safety_utility@4 \
  --transition-summary-json results_ros2_live_bridge/dynamic_objective_transition_3seed_summary.json \
  --transition-markdown results_ros2_live_bridge/dynamic_objective_transition_3seed_report.md \
  --title "ROS 2 Live Dynamic Objective Transition 3-Seed T3 V1"
```

## Artifacts

- `results_ros2_live_bridge/profile_objective_selector_autonomy_v1_summary.json`
- `results_ros2_live_bridge/profile_objective_selector_autonomy_v1_report.md`
- `results_ros2_live_bridge/ros2_live_bridge_t3_dynamic_objective_transition_smoke_v1_bridge_transition_config.json`
- `results_ros2_live_bridge/ros2_live_bridge_t3_dynamic_objective_transition_smoke_v1_decisions.jsonl`
- `results_ros2_live_bridge/ros2_live_bridge_t3_dynamic_objective_transition_smoke_v1_metrics.jsonl`
- `results_ros2_live_bridge/dynamic_objective_transition_3seed_summary.json`
- `results_ros2_live_bridge/dynamic_objective_transition_3seed_report.md`
- `results_ros2_live_bridge/ros2_live_bridge_t3_dynamic_objective_transition_3seed_v1_seed_7_metrics.jsonl`
- `results_ros2_live_bridge/ros2_live_bridge_t3_dynamic_objective_transition_3seed_v1_seed_13_metrics.jsonl`
- `results_ros2_live_bridge/ros2_live_bridge_t3_dynamic_objective_transition_3seed_v1_seed_29_metrics.jsonl`

## Result

### Three-Seed Matrix

The repeated Docker run completed `3/3` seeds with status `ran`.  Every run
matched both scheduled profile switches and both scheduled objective switches.
No unmatched switch/flapping was measured in the profile or objective switch
streams.

Mean dynamic binding result:

| policy | runs | rx | loss | control delivery | deadline miss | p95 ms | utility |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| `dynamic_objective/rmw_zenoh_cpp` | `3` | `97.33` | `0.0642` | `0.9612` | `0.2400` | `115.50` | `518.28` |

Mean transition evidence:

| metric | value |
| --- | ---: |
| profile switches/run | `2.0` |
| matched profile switches/run | `2.0` |
| profile switch mean absolute latency | `0.1644 s` |
| profile flapping/run | `0.0` |
| objective switches/run | `2.0` |
| matched objective switches/run | `2.0` |
| objective switch mean absolute latency | `0.0468 s` |
| objective flapping/run | `0.0` |
| policy switches/run | `2.0` |
| decision rows with binding estimate/run | `117.0` |

Per-seed transition rows:

| seed | rx | loss | control delivery | p95 ms | matched profile | profile abs s | matched objective | objective abs s | policy switches |
| ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| `7` | `105` | `0.0948` | `0.9535` | `115.31` | `2` | `0.1605` | `2` | `0.0406` | `2` |
| `13` | `82` | `0.0353` | `1.0000` | `117.32` | `2` | `0.1624` | `2` | `0.0695` | `2` |
| `29` | `105` | `0.0625` | `0.9302` | `113.88` | `2` | `0.1704` | `2` | `0.0303` | `2` |

Observed binding coverage:

| dimension | values |
| --- | --- |
| profiles | `wifi`, `wan`, `roaming` |
| objectives | `balanced_safety_utility`, `autonomy_safety` |
| packet formats | `data_frame`, `event_json` |

### One-Seed Smoke

The Docker run completed with status `ran`.  The netem schedule applied all
three profiles: Wi-Fi, WAN, and roaming.  The decision log recorded
`135/135` rows with `transport_binding` and `transport_binding_estimate`.

Observed transition evidence:

| metric | value |
| --- | ---: |
| profile switches | `2` |
| objective switches | `2` |
| policy switches | `2` |
| observed objectives | `autonomy_safety`, `balanced_safety_utility` |
| observed packet formats | `data_frame`, `event_json` |
| observed profiles | `wifi`, `wan`, `roaming` |

Objective/policy switch points:

| tick | elapsed s | profile | objective | policy |
| ---: | ---: | --- | --- | --- |
| `16` | `2.1000` | `wan` | `balanced_safety_utility -> autonomy_safety` | `data_frame/rmw_zenoh_cpp -> data_frame/rmw_cyclonedds_cpp` |
| `31` | `4.0008` | `wan` | `autonomy_safety -> balanced_safety_utility` | `data_frame/rmw_cyclonedds_cpp -> event_json/rmw_zenoh_cpp` |

Profile switch points:

| tick | elapsed s | switch |
| ---: | ---: | --- |
| `16` | `2.1000` | `wifi -> wan` |
| `33` | `4.2589` | `wan -> roaming` |

Run metrics:

| tx | rx | loss | control delivery | deadline miss | p95 ms | utility |
| ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| `121` | `114` | `0.0579` | `0.8889` | `0.2193` | `151.07` | `595.16` |

## Interpretation

This is the first ROS-backed evidence that FleetRMW binding is not only
profile-adaptive but also objective-adaptive during one live session.  At the
WAN transition, the active objective changes from balanced safety/utility to
autonomy safety, and the binding changes to the autonomy-selected WAN operating
point.  At `4s`, the objective returns to balanced and the binding returns to
the balanced WAN operating point before the profile estimator moves to roaming.

The current sidecar can immediately act on packet-format changes.  The `rmw`
field in the binding remains a target binding because a running ROS 2 process
still has a fixed `RMW_IMPLEMENTATION`.  This is not a contradiction; it marks
the next boundary shift.  The sidecar stage proves objective-aware control
plane behavior, while `rmw_fleetqox_cpp` is the path where RMW selection and
transport binding can become a native middleware decision.

The repeated result is now stronger than a smoke: objective-adaptive binding is
measured over multiple ROS-backed seeds, with explicit profile/objective switch
matching and flapping counters.  It is still not a fleet-scale dominance claim.
The two-robot follow-up closes the first short local-control scale gap, but not
the fleet-scale control gap.  The remaining evidence gap is longer dwell
windows, more than two robot namespaces, explicit per-robot fairness/deadline
budgets, more objective schedules, and eventually moving the same decision into
`rmw_fleetqox_cpp` so the RMW field is an executable middleware boundary rather
than target metadata.

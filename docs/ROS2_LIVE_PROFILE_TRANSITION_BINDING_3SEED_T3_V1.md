# ROS 2 Live Profile Transition Binding 3-Seed T3 V1

## Purpose

This milestone repeats the ROS 2 live Wi-Fi/WAN/roaming transition binding
matrix over three workload seeds.  It keeps the same Docker T3 topology,
`rmw_zenoh_cpp`, ROS 2 publisher, live bridge, sidecar runtime, egress bridge,
local controller, projection quality gate, UDP receiver, and timed `tc netem`
schedule while comparing four transport-binding modes:

- `adaptive`: online telemetry estimator with smoothing, hysteresis, and
  minimum dwell;
- `static_wifi`: binding locked to Wi-Fi's measured packet/RMW choice;
- `static_wan`: binding locked to WAN's measured packet/RMW choice;
- `static_roaming`: binding locked to roaming's measured packet/RMW choice.

The goal is to move the transition claim beyond a one-seed smoke: adaptive
must not only receive packets, it must switch at the scheduled profile changes,
avoid flapping, and improve the control-plane objectives under the same
non-stationary ROS 2 workload.

## Reproduction

```bash
python3 -m scripts.run_ros2_docker_live_bridge \
  --run \
  --analyze \
  --scenario ros2_live_bridge_t3_profile_transition_binding_matrix_3seed_v1 \
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
  --transition-binding-matrix \
  --transition-summary-json results_ros2_live_bridge/profile_transition_binding_matrix_3seed_summary.json \
  --transition-markdown results_ros2_live_bridge/profile_transition_binding_matrix_3seed_report.md \
  --title "ROS 2 Live Transition Binding Matrix 3-Seed T3 V1" \
  --json
```

## Artifacts

- `results_ros2_live_bridge/profile_transition_binding_matrix_3seed_summary.json`
- `results_ros2_live_bridge/profile_transition_binding_matrix_3seed_report.md`
- `results_ros2_live_bridge/ros2_live_bridge_t3_profile_transition_binding_matrix_3seed_v1_seed_7_*`
- `results_ros2_live_bridge/ros2_live_bridge_t3_profile_transition_binding_matrix_3seed_v1_seed_13_*`
- `results_ros2_live_bridge/ros2_live_bridge_t3_profile_transition_binding_matrix_3seed_v1_seed_29_*`

## Result

All `12/12` Docker runs completed with status `ran`: three seeds times
adaptive, static Wi-Fi, static WAN, and static roaming.  Every run applied the
same profile schedule:

| profile | at s | RTT ms | jitter ms | loss |
| --- | ---: | ---: | ---: | ---: |
| `wifi` | `0` | `40` | `5` | `0.010` |
| `wan` | `2` | `120` | `15` | `0.015` |
| `roaming` | `4` | `160` | `25` | `0.030` |

Policy means with 95% confidence intervals:

| policy | runs | loss | control delivery | deadline miss | p95 ms | utility |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| `adaptive` | `3` | `0.0605 +/- 0.0374` | `0.9654 +/- 0.0206` | `0.1991 +/- 0.0349` | `117.83 +/- 1.59` | `517.7 +/- 73.8` |
| `static_wifi` | `3` | `0.0965 +/- 0.0651` | `0.8995 +/- 0.0843` | `0.2131 +/- 0.0199` | `124.22 +/- 11.02` | `519.7 +/- 23.5` |
| `static_wan` | `3` | `0.0786 +/- 0.0585` | `0.9217 +/- 0.0491` | `0.2214 +/- 0.0519` | `117.85 +/- 1.90` | `530.0 +/- 81.9` |
| `static_roaming` | `3` | `0.0600 +/- 0.0077` | `0.9593 +/- 0.0083` | `0.2358 +/- 0.0331` | `124.89 +/- 15.17` | `527.1 +/- 105.3` |

Best observed policy by mean objective:

- control delivery: `adaptive`;
- deadline miss ratio: `adaptive`;
- p95 latency: `adaptive`;
- loss ratio: `static_roaming`;
- semantic utility: `static_wan`.

Adaptive-vs-static deltas use a positive sign when adaptive is better:

| baseline | control delivery | loss | deadline miss | p95 ms | semantic utility |
| --- | ---: | ---: | ---: | ---: | ---: |
| `static_wifi` | `+0.0659` | `+0.0360` | `+0.0140` | `+6.39` | `-2.05` |
| `static_wan` | `+0.0436` | `+0.0181` | `+0.0224` | `+0.03` | `-12.33` |
| `static_roaming` | `+0.0061` | `-0.0005` | `+0.0367` | `+7.07` | `-9.44` |

Switch evidence:

| policy | matched switches/run | missing switches/run | abs switch latency s | max abs switch latency s | flaps/run |
| --- | ---: | ---: | ---: | ---: | ---: |
| `adaptive` | `2.0` | `0.0` | `0.1805` | `0.3335` | `0.0` |
| `static_wifi` | `0.0` | `2.0` | `0.0` | `0.0` | `0.0` |
| `static_wan` | `0.0` | `2.0` | `0.0` | `0.0` | `0.0` |
| `static_roaming` | `0.0` | `2.0` | `0.0` | `0.0` | `0.0` |

## Interpretation

Adaptive binding is now a repeated ROS-backed operating point, not just a
configuration toggle.  It tracks the Wi-Fi -> WAN -> roaming transition in all
three seeds, matches both scheduled switches per run, and shows zero measured
flapping.  Under the current objective vector it also has the best mean control
delivery, deadline miss ratio, and p95 latency.

The result is still not universal dominance.  Static roaming is slightly better
on mean loss, and static WAN is better on mean delivered semantic utility.  That
is useful research signal: a fleet middleware should not hard-code "adaptive is
always best"; it should expose a measurable multi-objective control plane that
can trade control continuity, tail latency, loss, and semantic utility.

The remaining evidence gap is scale and objective diversity.  This run is three
short seeds, one robot workload, one RMW, and one fixed objective vector.  The
next research-grade step is to keep the same transition mechanism while adding
longer dwell windows, more robots, more objective schedules, and eventually a
true `rmw_fleetqox_cpp` boundary.

## Follow-Up Dynamic Objective Matrix

`ROS2_LIVE_DYNAMIC_OBJECTIVE_BINDING_T3_V1` implements and repeats objective
changes during the same ROS 2 live profile-transition session.  It switches the
binding objective from `balanced_safety_utility` to `autonomy_safety` during
the WAN segment and then back to balanced over seeds `7,13,29`, recording
matched `2.0` objective switches/run, `2.0` policy switches/run, mean absolute
objective switch latency `0.0468 s`, and zero measured objective flapping.
That narrows this document's "objective dynamics" gap to longer runs, more
robots, more objective schedules, and the future RMW boundary.

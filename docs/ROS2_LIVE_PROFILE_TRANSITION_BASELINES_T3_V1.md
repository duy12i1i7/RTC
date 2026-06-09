# ROS 2 Live Profile Transition Baselines T3 V1

## Purpose

This milestone turns the live Wi-Fi/WAN/roaming transition test into a
controlled baseline comparison.  The workload, Docker compose topology, ROS 2
publisher, live bridge, sidecar runtime, egress bridge, local controller lease,
quality gate, UDP receiver, and `tc netem` schedule are held constant while the
transport binding mode changes:

- `adaptive`: online profile estimator, smoothed telemetry, hysteresis, and
  minimum dwell;
- `static_wifi`: selector binding locked to the measured Wi-Fi profile;
- `static_wan`: selector binding locked to the measured WAN profile;
- `static_roaming`: selector binding locked to the measured roaming profile.

This is the first ROS-backed evidence that the adaptive binding control plane is
not just an engineering toggle.  It can be evaluated against static deployment
choices under the same non-stationary network.

## New Code

- `scripts/run_ros2_docker_live_bridge.py`
  - Adds `--transition-binding-matrix`.
  - Adds `--transition-binding-profile` to choose static baseline profiles.
  - Generates per-run transition bridge configs for adaptive and static binding
    baselines.
  - Writes `transition_binding_comparison` rows, policy summaries, best-policy
    labels, and adaptive-vs-static deltas.
  - Writes a transition binding JSON summary and Markdown report.

## Reproduction

```bash
python3 -m scripts.run_ros2_docker_live_bridge \
  --run \
  --analyze \
  --scenario ros2_live_bridge_t3_profile_transition_binding_matrix_v1 \
  --bridge-config experiments/ros2_live_bridge_tb4_binding_v1.json \
  --rmw rmw_zenoh_cpp \
  --transition-profile wifi \
  --transition-profile wan \
  --transition-profile roaming \
  --transition-segment-s 2 \
  --seconds 6 \
  --rate-hz 20 \
  --bridge-max-batches 120 \
  --transition-binding-matrix \
  --title "ROS 2 Live Transition Binding Matrix T3 V1" \
  --json
```

## Artifacts

- `results_ros2_live_bridge/profile_transition_binding_matrix_summary.json`
- `results_ros2_live_bridge/profile_transition_binding_matrix_report.md`
- `results_ros2_live_bridge/ros2_live_bridge_t3_profile_transition_binding_matrix_v1_adaptive_*`
- `results_ros2_live_bridge/ros2_live_bridge_t3_profile_transition_binding_matrix_v1_static_wifi_*`
- `results_ros2_live_bridge/ros2_live_bridge_t3_profile_transition_binding_matrix_v1_static_wan_*`
- `results_ros2_live_bridge/ros2_live_bridge_t3_profile_transition_binding_matrix_v1_static_roaming_*`

## Result

All four runs completed with Docker status `ran`.  Every run applied the same
netem transition schedule:

| profile | at s | RTT ms | jitter ms | loss |
| --- | ---: | ---: | ---: | ---: |
| `wifi` | `0` | `40` | `5` | `0.010` |
| `wan` | `2` | `120` | `15` | `0.015` |
| `roaming` | `4` | `160` | `25` | `0.030` |

Policy comparison:

| policy | tx | rx | loss | control delivery | deadline miss | p95 ms | switches |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| `adaptive` | `125` | `118` | `0.0560` | `0.9787` | `0.2373` | `137.94` | `2` |
| `static_wifi` | `91` | `87` | `0.0440` | `0.9429` | `0.2414` | `116.05` | `0` |
| `static_wan` | `91` | `86` | `0.0549` | `0.9706` | `0.2093` | `117.59` | `0` |
| `static_roaming` | `103` | `95` | `0.0777` | `0.9500` | `0.2105` | `115.18` | `0` |

Adaptive binding switched twice:

- tick `16`: `wifi/data_frame/rmw_zenoh_cpp` to
  `wan/event_json/rmw_zenoh_cpp`;
- tick `33`: `wan/event_json/rmw_zenoh_cpp` to
  `roaming/event_json/rmw_zenoh_cpp`.

Adaptive-vs-static deltas use a positive sign when adaptive is better:

| baseline | control delivery | loss | deadline miss | p95 ms | semantic utility |
| --- | ---: | ---: | ---: | ---: | ---: |
| `static_wifi` | `+0.0359` | `-0.0120` | `+0.0041` | `-21.89` | `+163.51` |
| `static_wan` | `+0.0081` | `-0.0011` | `-0.0280` | `-20.35` | `+169.18` |
| `static_roaming` | `+0.0287` | `+0.0217` | `-0.0268` | `-22.76` | `+122.22` |

Best observed policy in this one-seed smoke:

- control delivery: `adaptive`;
- semantic utility: `adaptive`;
- loss ratio: `static_wifi`;
- deadline miss ratio: `static_wan`;
- p95 latency: `static_roaming`.

## Interpretation

The adaptive policy is not a blanket latency optimizer in this short smoke.  It
chooses the profile-dependent binding that maximizes delivered utility and
control continuity, and that creates a trade-off: more admitted/delivered work
also increases p95 latency compared with the static baselines.

That trade-off is useful research evidence.  Static baselines look good on one
metric because they remain narrow: static Wi-Fi keeps the data-frame path,
static WAN/roaming keep event JSON, and none of them attempt to track the
network state.  Adaptive is the only run that observes all three profiles,
switches packet format, and delivers the highest control delivery and semantic
utility under the same profile transition.

The next research-grade step is repeated evaluation over seeds, longer
segments, and objective changes.  This baseline matrix is the harness needed to
make that claim measurable instead of rhetorical.

## Follow-Up Three-Seed Matrix

`ROS2_LIVE_PROFILE_TRANSITION_BINDING_3SEED_T3_V1` repeats this same
adaptive-vs-static transition matrix over seeds `7,13,29` and writes:

- `results_ros2_live_bridge/profile_transition_binding_matrix_3seed_summary.json`
- `results_ros2_live_bridge/profile_transition_binding_matrix_3seed_report.md`

In that repeated short matrix, adaptive binding matches both scheduled switches
per run, measures mean absolute switch latency `0.1805 s`, and has zero
measured flapping.  It becomes the best mean policy for control delivery,
deadline miss, and p95 latency, while static roaming remains slightly better on
loss and static WAN remains better on semantic utility.  The result narrows the
research gap from "repeat the smoke" to "scale the repeated transition test
across robots, longer dwell windows, dynamic objectives, and the future
`rmw_fleetqox_cpp` boundary."

## Verification

```bash
python3 -m unittest tests.test_ros2_docker_live_bridge_metadata
# Ran 22 tests - OK
```

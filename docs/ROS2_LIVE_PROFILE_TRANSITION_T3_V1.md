# ROS 2 Live Profile Transition T3 V1

## Purpose

This milestone tests live continuous binding under a non-stationary network
inside the Docker T3 ROS 2 harness.

Unlike the dependency-free binding smoke, this run keeps the ROS 2 live bridge,
publisher, sidecar, egress bridge, local controller lease, projection quality
gate, monitor, and UDP receiver running in one compose session while the sidecar
container applies a timed `tc netem` schedule:

```text
0s  -> wifi
2s  -> wan
4s  -> roaming
```

The bridge receives the same transition schedule as `link_schedule`, so the
adaptive estimator sees telemetry aligned with the network impairment being
applied by Docker.

## New Code

- `scripts/apply_netem_transition.py`
  - Parses schedules such as `wifi@0,wan@2,roaming@4`.
  - Applies `tc qdisc replace ... netem` per scheduled profile.
  - Logs each applied profile with command, elapsed time, and status.
- `external/ros2-live-bridge/docker-compose.yml`
  - Runs the transition applier in the sidecar container when
    `NETEM_TRANSITION_SCHEDULE` is set.
- `scripts/run_ros2_docker_live_bridge.py`
  - Adds `--transition-profile`, `--transition-segment-s`, and
    `--transition-schedule`.
  - Generates a per-run bridge config with `link_schedule`.
  - Summarizes binding profile switches from the sidecar decision log.
- `fleetqox/ros2_live_bridge.py`
  - Adds `LiveLinkScheduleEntry` and `ScheduledLiveLinkProvider`.

## Reproduction

```bash
python3 -m scripts.run_ros2_docker_live_bridge \
  --run \
  --analyze \
  --scenario ros2_live_bridge_t3_profile_transition_v1 \
  --bridge-config experiments/ros2_live_bridge_tb4_binding_v1.json \
  --transition-profile wifi \
  --transition-profile wan \
  --transition-profile roaming \
  --transition-segment-s 2 \
  --seconds 6 \
  --rate-hz 20 \
  --bridge-max-batches 120 \
  --json
```

## Artifacts

- `results_ros2_live_bridge/ros2_live_bridge_t3_profile_transition_v1_bridge_transition_config.json`
- `results_ros2_live_bridge/ros2_live_bridge_t3_profile_transition_v1_netem_transition.jsonl`
- `results_ros2_live_bridge/ros2_live_bridge_t3_profile_transition_v1_decisions.jsonl`
- `results_ros2_live_bridge/ros2_live_bridge_t3_profile_transition_v1_received.jsonl`
- `results_ros2_live_bridge/ros2_live_bridge_t3_profile_transition_v1_metrics.jsonl`
- `results_ros2_live_bridge/ros2_live_bridge_t3_profile_transition_v1_quality_gate_decisions.jsonl`

## Result

Netem transition log:

| profile | scheduled s | applied elapsed s | status |
| --- | ---: | ---: | --- |
| `wifi` | `0.0` | `0.016` | `applied` |
| `wan` | `2.0` | `2.015` | `applied` |
| `roaming` | `4.0` | `4.031` | `applied` |

Binding transition summary:

| switch | tick | from | to |
| ---: | ---: | --- | --- |
| 1 | `14` | `wifi` / `data_frame/rmw_zenoh_cpp` | `wan` / `event_json/rmw_zenoh_cpp` |
| 2 | `28` | `wan` / `event_json/rmw_zenoh_cpp` | `roaming` / `event_json/rmw_zenoh_cpp` |

Decision-log coverage:

- decision rows: `87`
- rows with `transport_binding`: `87/87`
- rows with `transport_binding_estimate`: `87/87`
- profiles observed by binding: `wifi`, `wan`, `roaming`
- packet formats observed: `data_frame`, `event_json`

End-to-end ROS 2 path:

- sidecar packets transmitted: `80`
- UDP packets received: `72`
- measured loss ratio: `0.1000`
- p95 latency: `132.64 ms`
- p99 latency: `216.19 ms`
- control delivery ratio: `0.8966`
- control non-delivery events: `0`
- egress publications: `144`
- projection quality gate accepts: `40`
- decision-to-gate contract matches: `46/46`
- decision-to-gate source matches: `46/46`

## Interpretation

This run proves the profile-transition mechanism end to end:

```text
tc netem transition
-> bridge link_schedule
-> adaptive binding estimator
-> per-batch TransportBinding
-> sidecar packet-format selection
-> ROS 2 egress/quality-gate path
```

It is still a one-seed, short T3 smoke, not a statistical claim. The run does
show that the binding switch is not a static profile lookup: the estimator
tracks Wi-Fi, moves to WAN after the first transition, then moves to roaming
after the second transition while preserving estimator metadata in every
decision row.

## Follow-On Baseline Matrix

The static-baseline follow-on is now implemented in
`docs/ROS2_LIVE_PROFILE_TRANSITION_BASELINES_T3_V1.md`.

It reuses the same Wi-Fi/WAN/roaming transition workload and compares:

- adaptive binding;
- static Wi-Fi binding;
- static WAN binding;
- static roaming binding.

The first one-seed Docker T3 matrix completed `4/4` runs.  Adaptive delivered
the highest control delivery (`0.9787`) and semantic utility (`630.45`) while
switching Wi-Fi -> WAN -> roaming.  Static baselines still won some raw latency
or loss metrics, so the result is a measured trade-off, not a blanket claim.

## Next Step

The next research-grade step is repeated transition evaluation:

- multiple seeds;
- longer segments;
- objective changes during the run;
- switch-latency and flapping metrics;
- confidence intervals over the adaptive-vs-static baseline matrix;
- RMW matrix once transition behavior is stable.

## Verification

```bash
python3 -m unittest tests.test_ros2_live_bridge tests.test_ros2_docker_live_bridge_metadata
# Ran 28 tests - OK

python3 -m unittest discover -s tests
# Ran 227 tests - OK
```

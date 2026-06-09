# ROS 2 Live Continuous Binding V1

## Purpose

This milestone connects the profile/objective-aware transport selector to the
live ROS 2 bridge loop.

Before this point, selector output could be attached to a dependency-free ROS 2
shim batch and consumed by the sidecar runtime.  The live bridge still used one
static data-plane mode for a run.  V1 closes that gap: every live bridge batch
can refresh its `TransportBinding` from the current `NetworkLink`, so the
sidecar receives a measured packet-format/RMW policy with each batch.

The design keeps the ROS 2 application model intact:

```text
rclpy callback
-> Ros2LiveSampleBuffer
-> adaptive TransportBinding provider
-> Ros2SidecarAdapter batch
-> SidecarRuntime packet-format selection
-> event_json or fleetrmw.data_frame.v1 UDP emission
```

## New Code

- `fleetqox/ros2_live_bridge.py`
  - Adds `LiveTransportBindingConfig`.
  - Parses `transport_binding` from bridge config JSON.
  - Creates static, auto-profile, or adaptive binding providers from selector
    summary artifacts.
  - Refreshes binding payloads on each `drain_batch()`.
  - Emits adaptive profile estimate metadata beside the binding.
- `fleetqox/ros2_shim.py`
  - Keeps `transport_binding_estimate` in the sidecar batch.
- `fleetqox/sidecar_runtime.py`
  - Logs `transport_binding_estimate` on each decision/packet event.
  - Echoes the estimate in the batch response for live bridge observability.
- `scripts/smoke_ros2_live_bridge_binding.py`
  - Dependency-free smoke for static, auto, and adaptive live binding.
- `experiments/ros2_live_bridge_tb4_binding_v1.json`
  - TurtleBot-style live bridge config using adaptive binding.

## Config

The live bridge config now accepts:

```json
{
  "transport_binding": {
    "summary": "results_ros2_live_bridge/profile_objective_selector_balanced_v1_summary.json",
    "adaptive_profile": true,
    "smoothing_alpha": 0.35,
    "hysteresis_margin": 0.06,
    "min_dwell_ticks": 2
  }
}
```

Supported modes:

- `profile`: fixed selector profile such as `wifi`, `wan`, or `roaming`.
- `auto_profile`: rule-based link classification without estimator state.
- `adaptive_profile`: smoothed link telemetry, profile prototype scoring,
  hysteresis, and minimum dwell before switching.

## Reproduction

Dependency-free smoke:

```bash
python3 -m scripts.smoke_ros2_live_bridge_binding \
  --selector-summary results_ros2_live_bridge/profile_objective_selector_balanced_v1_summary.json \
  --mode adaptive \
  --process-runtime \
  --output results_ros2_live_bridge/live_bridge_adaptive_binding_runtime_smoke_v1.json \
  --json
```

Live ROS 2 bridge config:

```bash
python3 -m scripts.run_ros2_live_bridge \
  --config experiments/ros2_live_bridge_tb4_binding_v1.json
```

The second command still requires a sourced ROS 2 environment, or the Docker T3
runner that provides one inside Linux containers.

## Smoke Result

Artifact:

- `results_ros2_live_bridge/live_bridge_adaptive_binding_runtime_smoke_v1.json`
- `results_ros2_live_bridge/live_bridge_adaptive_binding_runtime_smoke_decisions.jsonl`

Observed adaptive binding refresh:

| tick | link | active profile | selected policy | confidence | margin |
| ---: | --- | --- | --- | ---: | ---: |
| 0 | `120000 B/s`, `40 ms` RTT, `5 ms` jitter, `1%` loss | `wifi` | `data_frame/rmw_zenoh_cpp` | `0.4215` | `0.0517` |
| 1 | `50000 B/s`, `160 ms` RTT, `25 ms` jitter, `3%` loss | `roaming` | `event_json/rmw_zenoh_cpp` | `0.5206` | `0.1928` |

Runtime sidecar result:

- decision log rows: `2`
- rows with `transport_binding`: `2/2`
- rows with `transport_binding_estimate`: `2/2`
- response packet formats: tick `0` -> `data_frame`, tick `1` -> `event_json`

This is intentionally not a dominance claim.  It proves the continuous binding
loop: selector summary -> adaptive estimator -> live bridge batch -> sidecar
runtime packet-format choice.

## Current Scope

Implemented:

- live bridge config can carry measured selector summaries;
- adaptive estimator state is maintained across batches;
- every batch can carry both `transport_binding` and
  `transport_binding_estimate`;
- sidecar decision logs preserve the binding and estimator state;
- packet format is selected per batch from the binding.

Still outside this milestone:

- switching a running ROS 2 process to a different RMW implementation per batch;
- repeated or long-duration Docker T3 baseline matrices with confidence
  intervals;
- objective-weight optimization from observed QoS/QoE outcomes;
- moving the binding decision into `rmw_fleetqox_cpp`.

`ROS2_LIVE_PROFILE_TRANSITION_T3_V1.md` adds the first short Docker T3
Wi-Fi/WAN/roaming transition run for this binding loop.
`ROS2_LIVE_PROFILE_TRANSITION_BASELINES_T3_V1.md` adds the first adaptive vs
static binding matrix under that same transition workload.

## Verification

```bash
python3 -m unittest tests.test_ros2_live_bridge tests.test_sidecar_runtime tests.test_ros2_shim
# Ran 38 tests - OK, skipped 12

python3 -m unittest discover -s tests
# Ran 227 tests - OK
```

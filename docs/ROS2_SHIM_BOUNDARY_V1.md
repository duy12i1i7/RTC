# ROS 2 Shim Boundary V1

## Purpose

This milestone moves FleetRMW closer to a real ROS 2 integration without
requiring a ROS 2 installation in the local test environment.

The new boundary is dependency-free:

```text
ROS 2 topic/sample metadata
-> Ros2SidecarAdapter
-> optional TransportBinding
-> FleetQoX FlowSpec + FlowObservation
-> SidecarRuntime policy
-> FleetRMW sidecar trace + UDP packet emission
-> FleetRmwProjectedSample contract at egress
```

The important design choice is that the adapter only translates ROS 2-facing
facts into FleetQoX contracts. It does not make scheduling decisions and it does
not depend on DDS, Zenoh, CycloneDDS, Fast DDS, or `rclpy`.

## New Code

- `fleetqox/ros2_shim.py`
  - `Ros2Sample`: one live/replayed ROS 2 sample observation.
  - `Ros2QoS`: dependency-free ROS 2 QoS subset.
  - `Ros2TopicRule`: explicit override for topic families.
  - `Ros2SidecarAdapter`: converts samples to sidecar batches.
- `fleetqox/rmw_contract.py`
  - `FleetRmwProjectedSample`: post-admission sample plus identity and delivery
    contract.
  - `FleetRmwSampleIdentity`: stable projection identity, contract ID, source
    sample ID, and canonical signature.
  - `FleetRmwDeliveryContract`: action, wire mode, timing, fidelity, lossiness,
    and task context.
- `scripts/run_ros2_sidecar_adapter.py`
  - Builds a sidecar batch from JSONL sample records or built-in smoke samples.
  - Optionally processes that batch through `SidecarRuntime`.
  - Can attach a selector-produced `TransportBinding` summary/profile to the
    generated batch.
- `tests/test_ros2_shim.py`
  - Verifies topic inference, QoS defaults, override rules, and runtime handoff.

## Mapping Model

The adapter infers semantic class from topic and message metadata:

| ROS 2 signal | FleetQoX class | Default contract |
| --- | --- | --- |
| `/cmd_vel`, twist commands | `control` | reliable, depth 1, 45 ms deadline, 90 ms lifespan |
| emergency/safety topics | `safety` | reliable, depth 1, 30 ms deadline |
| coordination/intent topics | `coordination` | reliable, depth 2, 80 ms deadline |
| state/odom/tf/battery | `state` | reliable, depth 3, 120 ms deadline |
| scan/lidar/obstacle/costmap/image | `perception` | best-effort, depth 1, semantic delta enabled |
| front camera/QoE topics | `human_qoe` | best-effort, operator-visible QoE profile |
| debug/log/trace | `debug` | best-effort, low task gain |

Topic rules can override the inferred class, logical flow name, size, rate,
semantic delta ratio, redundancy, and operator visibility.

## Smoke Evidence

Command:

```bash
python3 -m scripts.run_ros2_sidecar_adapter \
  --scenario ros2_shim_smoke_v1 \
  --output-batch results_ros2_shim/smoke_batch.json \
  --decision-log results_ros2_shim/smoke_decisions.jsonl \
  --json
```

Result:

```json
{"accepted": 13, "decisions": 13, "emitted": 7, "status": "ok"}
```

The smoke uses a roaming-like link (`160 ms` RTT, `25 ms` jitter, `3%` loss,
`588` bytes/tick). The adaptive semantic-contract runtime emits
`send_supervisory_intent` for `/robot_*/cmd_vel`, confirming that the ROS
2-facing sample path reaches the same supervisory intent machinery as the
Docker/netem experiments.

Runtime binding smoke:

```bash
python3 -m scripts.run_ros2_sidecar_adapter \
  --scenario ros2_shim_transport_binding_runtime_smoke_v1 \
  --decision-log results_ros2_shim/transport_binding_runtime_smoke_decisions.jsonl \
  --transport-binding-summary results_ros2_live_bridge/profile_objective_selector_balanced_v1_summary.json \
  --transport-profile wifi \
  --json
```

Result:

```json
{"accepted": 13, "decisions": 13, "emitted": 7, "packet_format": "data_frame", "status": "ok"}
```

All `13/13` decision-log rows carry the Wi-Fi balanced binding
`data_frame/rmw_zenoh_cpp`, so the ROS 2 shim boundary can now pass the
profile/objective-aware transport decision into the sidecar runtime.

Auto-profile binding smoke:

```bash
python3 -m scripts.run_ros2_sidecar_adapter \
  --scenario ros2_shim_transport_binding_auto_profile_smoke_v1 \
  --decision-log results_ros2_shim/transport_binding_auto_profile_smoke_decisions.jsonl \
  --transport-binding-summary results_ros2_live_bridge/profile_objective_selector_balanced_v1_summary.json \
  --auto-transport-profile \
  --json
```

The default smoke link is roaming-like, so the manager infers `roaming` and
selects `event_json/rmw_zenoh_cpp`.

Adaptive-profile binding smoke:

```bash
python3 -m scripts.run_ros2_sidecar_adapter \
  --scenario ros2_shim_transport_binding_adaptive_profile_smoke_v1 \
  --decision-log results_ros2_shim/transport_binding_adaptive_profile_smoke_decisions.jsonl \
  --transport-binding-summary results_ros2_live_bridge/profile_objective_selector_balanced_v1_summary.json \
  --adaptive-transport-profile \
  --json
```

This exercises the same runtime binding path through the smoothing/hysteresis
estimator interface.

## Why This Matters

Before this boundary, the sidecar accepted synthetic `FlowSpec` batches. That
was enough for algorithmic evidence, but weak as a middleware story.

With this adapter, the same FleetRMW policy can now be driven by:

- synthetic workload generation;
- JSONL traces from rosbag/performance tools;
- a future live `rclpy`/`rclcpp` shim that observes ROS 2 topics and QoS;
- later RMW replacement work that bypasses DDS for selected flows.

`RMW_SAMPLE_CONTRACT_V1.md` extends this ingress boundary to the post-admission
side.  It defines the dependency-free contract that egress, wrapper messages,
and a future RMW sample metadata path must share.  `Ros2SidecarAdapter` now also
generates a deterministic `contract_id` for each sample when one is not supplied
by the caller.  It also derives `source_sample_id` from semantic payload
metadata such as `header.stamp` when available.  For headerless samples such as
`cmd_vel`, it can derive the same source identity from RMW-facing metadata:
publisher GID, publication sequence number, and source timestamp.  It falls
back to `contract_id` only when the source sample has no explicit or derived
identity.

The Docker T3 `ros2_live_bridge_t3_source_metadata_v2` run confirmed live
callback propagation for sequence number plus source/received timestamps on
`66/66` sidecar packet decisions.  The follow-up
`ros2_live_bridge_t3_rmw_metadata_v2` matrix confirmed that source and received
timestamps are portable across Fast DDS, CycloneDDS, and Zenoh RMW in this
bridge, while sequence number is absent for CycloneDDS and publisher GID is not
exposed through the observed `rclpy` callback metadata for any tested RMW.
Those fields remain optional at the shim boundary.

This preserves the original ROS mindset while creating a clean insertion point
for non-DDS data-plane experiments.

## Follow-Up

`ROS2_LIVE_BRIDGE_V1.md` builds on this boundary with a thin `rclpy` ingress
bridge.  The live bridge subscribes configured ROS 2 topics, converts callbacks
to this same `Ros2Sample` schema, and sends sidecar batches to
`SidecarRuntime` over TCP.

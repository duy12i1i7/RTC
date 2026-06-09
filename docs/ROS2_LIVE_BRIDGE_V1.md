# ROS 2 Live Bridge V1

## Purpose

This milestone adds the first live ROS 2 ingress path for FleetRMW.  The bridge
does not replace an RMW yet.  It observes selected ROS 2 topics, converts each
callback into the dependency-free `Ros2Sample` schema, coalesces callbacks into
20 ms sidecar batches, and sends those batches to a running FleetRMW sidecar
over newline-delimited TCP JSON.

```text
rclpy subscriptions
-> serialized size + topic/QoS metadata
-> Ros2LiveSampleBuffer
-> Ros2SidecarAdapter
-> SidecarRuntime TCP API
-> semantic/adaptive policy
```

## New Code

- `fleetqox/ros2_live_bridge.py`
  - `BridgeTopicConfig` and `LiveBridgeConfig` parse live subscription config.
  - `Ros2LiveSampleBuffer` coalesces callbacks and computes sample age/depth.
  - `LiveTransportBindingConfig` optionally refreshes selector-produced
    transport bindings and adaptive profile estimates per batch.
  - `SidecarTcpClient` sends batches to `serve_tcp`.
- `scripts/run_ros2_live_bridge.py`
  - Lazy-imports `rclpy`, `rosidl_runtime_py`, and ROS serializers only when run.
  - Subscribes the configured topics and feeds the sidecar.
- `experiments/ros2_live_bridge_tb4_v1.json`
  - TurtleBot/Fleet-style starter config for `/cmd_vel`, odom, scan, and camera.
- `tests/test_ros2_live_bridge.py`
  - Covers config parsing, callback coalescing, and TCP handoff to a real
    `SidecarRuntime` server without requiring ROS 2.

## How To Run

Terminal 1, start the FleetRMW sidecar runtime:

```bash
python3 -m scripts.run_sidecar_runtime \
  --listen-host 127.0.0.1 \
  --listen-port 8765 \
  --udp-host 127.0.0.1 \
  --udp-port 9100 \
  --policy fleetqox_semantic_contract_adaptive \
  --decision-log results_ros2_live_bridge/tb4_decisions.jsonl
```

Terminal 2, in a sourced ROS 2 environment:

```bash
python3 -m scripts.run_ros2_live_bridge \
  --config experiments/ros2_live_bridge_tb4_v1.json
```

Adaptive transport binding config:

```bash
python3 -m scripts.run_ros2_live_bridge \
  --config experiments/ros2_live_bridge_tb4_binding_v1.json
```

The bridge will subscribe the configured topics, estimate serialized payload
size from each message, and feed non-empty batches to the sidecar every `20 ms`.

## Current Scope

This is a live ingress bridge, not yet a full non-DDS RMW.  It proves that the
FleetRMW control plane can be driven by real ROS 2 topic callbacks while keeping
the data-plane experiment independent:

- the ROS application can keep using normal publishers/subscribers;
- the bridge observes and translates selected flows into semantic contracts;
- the sidecar decides which representation should cross the constrained link;
- the sidecar still emits the selected packet representation through its
  existing UDP test data plane.

## Egress Status

The first egress reinjection path is now implemented in
`ROS2_EGRESS_BRIDGE_V1.md`.  After the sidecar selects `native`, `degraded`,
`control_intent`, or `supervisory_intent`, the Docker T3 harness decodes the
sidecar UDP packet and republishes a ROS 2 `std_msgs/String` envelope.  For
`geometry_msgs/Twist` control samples, the same egress path can also publish a
typed local command on `/fleetrmw/<robot>/local_cmd_vel`.

The remaining technical gap is general typed reconstruction: odometry,
perception, degraded state, and controller-specific leases still need explicit
message/type semantics.

The first Dockerized ROS 2 T3 smoke is recorded in
`ROS2_DOCKER_LIVE_BRIDGE_T3.md`. It confirms that live `rclpy` callbacks inside
Linux containers can feed the adaptive sidecar, produce supervisory intent
packets, and observe the resulting egress publications on ROS 2 topics without
installing ROS 2 natively on macOS.

`ROS2_LIVE_CONTINUOUS_BINDING_V1.md` records the follow-up binding milestone.
It connects selector summaries and the adaptive binding estimator to the live
bridge loop, so each batch can carry both the selected packet-format/RMW binding
and the profile-estimator state used to choose it.

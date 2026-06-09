# Architecture

## Long-Term Target

```text
ROS 2 application code
  rclcpp / rclpy
  rcl
  rmw_fleetqox_cpp
  FleetQoX Core
    Graph Manager
    Capability Graph
    QoX Runtime
    Causal Semantic Deadline Scheduler
    Admission Control
    Transport Multiplexer
  SHM / UDP / QUIC / WebRTC / TCP bulk
```

## Local And Fleet Graphs

Inside each robot, normal ROS 2 topics remain available:

```text
/cmd_vel
/odom
/tf
/scan
/camera/front/image
/diagnostics
```

Across the fleet, FleetRMW exposes a compressed capability graph:

```yaml
robot_042:
  capabilities:
    - navigate
    - dock
    - stream_front_view
  active_task: delivery
  pose_freshness_ms: 48
  collision_risk: medium
  operator_attention: false
  network_health: constrained
```

This avoids exposing every internal endpoint to every remote participant.

## Communication Planes

FleetRMW separates flows by semantics:

- safety-critical plane;
- control plane;
- coordination plane;
- state/diagnostics plane;
- perception-semantic plane;
- human-QoE plane;
- debug/bulk plane.

Each plane has independent admission, queueing, degradation, and reliability
rules.

## Scheduler Inputs

For each flow:

- flow class;
- deadline;
- lifespan;
- current age;
- message size;
- estimated bandwidth cost;
- causal task gain;
- task risk;
- operator QoE sensitivity;
- redundancy;
- current network health.

## Scheduler Decision

For each tick, the scheduler may:

- send now;
- send degraded;
- defer;
- drop stale sample;
- deny by admission control.

The scheduler is allowed to degrade video/perception/debug, but it must reserve
capacity for control and state flows.

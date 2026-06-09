# Testbed Survey

This document records the testing strategy for FleetRMW/FleetQoX. The goal is
to avoid a weak toy benchmark and build a layered experimental program that can
be executed progressively without requiring a full physical robot fleet.

## What Must Be Tested

FleetRMW claims are not single-metric claims. The testbed must cover:

- ROS graph/discovery scalability;
- pub/sub latency, jitter, and p99/p999 tail behavior;
- deadline miss and stale data ratio;
- bandwidth pressure from perception/video/debug traffic;
- operator-facing QoE under congestion;
- task/fleet success under network degradation;
- CPU and memory overhead;
- behavior under Wi-Fi, routed LAN, WAN, NAT-like, and lossy links.

## Tool Categories

### ROS 2 Microbenchmarking

Use this layer to isolate middleware behavior without robot physics.

- `performance_test`: measures latency, throughput, CPU, message size, QoS, and
  RMW differences through ROS 2 `rclcpp` pub/sub.
- `ros2_tracing`: low-overhead tracepoints for callback, executor, publish,
  take, and OS-level timing analysis.
- RobotPerf: vendor-neutral ROS 2 benchmarking suite, useful for aligning with
  robotics benchmarking conventions.
- Isaac ROS Benchmark: useful later if GPU/perception graphs are involved.

### Network Emulation

Use this layer to create controlled bad networks.

- `tc netem`: delay, jitter, packet loss, reordering, duplication, corruption,
  and rate limits at Linux qdisc level.
- Mininet: virtual hosts/switches/links with real Linux network stacks.
- Mininet-WiFi: virtual stations/APs, Wi-Fi mobility, SDN wireless experiments.
- Containernet: Mininet fork where Docker containers can act as emulated hosts.
- CORE/EMANE: higher-fidelity mobile ad-hoc/radio network emulation.
- ns-3: discrete-event network simulation for Wi-Fi/LTE/5G/mesh fidelity.
- Pumba: container-level chaos/network emulation for Docker workloads.

### Discrete-Event Network Simulation

Use this layer when network fidelity matters more than running unmodified ROS 2
binaries.

- ns-3: packet-level/discrete-event simulator for internet systems, with models
  for Wi-Fi, LTE, 5G NR through 5G-LENA, mesh, mobility, routing, and protocol
  studies.
- OMNeT++ + INET: modular network simulation environment for wired, wireless,
  mobile, ad hoc, sensor, Internet stack, routing, DiffServ, MPLS, mobility,
  emulation, and TSN/traffic-shaping studies.

This layer is essential for claims about Wi-Fi contention, roaming, mesh
behavior, 5G scheduling, and TSN-like traffic classes.

### Robot And Fleet Simulation

Use this layer to connect communication metrics to robot behavior.

- Gazebo Sim + `ros_gz`: practical ROS 2 simulation baseline.
- Webots + `webots_ros2`: simpler robot simulation with ROS 2 integration.
- Isaac Sim + ROS 2 bridge: high-fidelity sensors and multi-robot navigation,
  but heavier hardware requirements.
- CoppeliaSim ROS 2 interface: flexible multi-robot scene scripting.
- Open-RMF demos: task dispatching, fleet adapters, building maps, and fleet
  coordination scenarios.
- Nav2 multi-robot bringup/TurtleBot3-style workloads: canonical ROS 2 mobile
  robot workload for namespacing, navigation, and action traffic.

## Recommended Stack For This Project

The most useful practical stack, given limited hardware, is:

```text
T0  FleetQoX analytical simulator
T1  ROS 2 performance_test + ros2_tracing
T2E Docker/Containernet + tc netem + FastDDS/CycloneDDS/Zenoh baselines
T2S ns-3 / OMNeT++ trace-driven network simulation
T3  Gazebo Sim + Nav2 multi-robot workload
T4  Open-RMF demos + synthetic robot/fleet adapters
T5  Later: real TurtleBot/AMR or HIL
```

This stack can separate causes:

- if T1 fails, the middleware path is weak;
- if T2E fails, the ROS/network integration behavior is weak;
- if T2S fails, the network-science claim is weak;
- if T3 fails, robot autonomy/workload interaction is weak;
- if T4 fails, fleet/task coordination is weak.

## Why Not Use Only Gazebo?

Full robot simulation is convincing but poor for root-cause isolation. If p99
latency is bad in Gazebo, the cause may be physics, CPU saturation, ROS graph
scale, network emulation, simulator bridge overhead, or the scheduler. The
layered testbed makes each component measurable.

## Why Not Use Only ns-3 Or OMNeT++?

ns-3 and OMNeT++ are excellent for network realism, especially Wi-Fi, LTE/5G,
mesh, mobility, queueing, and traffic-shaping studies. They do not run normal
ROS 2 applications as directly as Linux container/network namespace emulation.
Therefore the strongest plan is not to choose one family, but to use both:

- emulation to test real ROS 2 binaries and RMW behavior;
- discrete-event simulation to test the network model and scaling assumptions.

## Immediate Recommendation

Build the benchmark suite around reproducible manifests:

- one manifest for scenarios;
- one runner for synthetic FleetQoX simulator;
- one planned runner for ROS 2 `performance_test`;
- one planned runner for network emulation;
- one planned runner for Gazebo/Nav2/RMF scenarios;
- one common metrics schema.

The current repository now implements the first of these and defines the rest
as executable plans.

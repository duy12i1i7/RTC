# Research Plan

## Problem Statement

Large robot fleets built on ROS 2 need communication that remains useful under
wireless congestion, roaming, partial connectivity, and mixed workloads
including control, state, perception, operator video, diagnostics, and bulk
logging.

DDS-based ROS 2 communication is endpoint-centric. It provides per-topic QoS,
but it does not know task value, operator experience, fleet risk, or semantic
freshness. Existing bridges and routers improve connectivity, but they still
mostly route messages rather than deciding which information is worth network
resources.

## Research Gap

Existing work covers important pieces:

- DDS/RMW benchmarking and tuning;
- ROS 2 tracing, executor, and response-time analysis;
- Zenoh, DDS Router, Robofleet, FogROS2, and Open-RMF;
- utility-aware multi-robot communication;
- semantic communication and Age/Value of Information.

The missing system is a ROS-native communication runtime that jointly provides:

```text
fleet-scale graph virtualization
+ causal/task-aware information valuation
+ adaptive QoS/QoE/QoT scheduling
+ freshness-first reliability
+ runtime admission control
+ compatibility with ROS 2 programming model
```

## Proposed Contribution

FleetRMW is a ROS 2-native non-DDS middleware direction. FleetQoX is the
control-plane model and scheduler that can be validated before implementing the
full RMW.

Primary contributions:

1. Causal Capability Graph

   A fleet-level graph that hides raw ROS endpoint explosion and exposes
   robot capabilities, task state, freshness, risk, and operator demand.

2. QoX Flow Model

   A model that extends topic QoS into QoS + QoE + QoT + semantic freshness.

3. Causal Semantic Deadline Scheduler

   A scheduler that prioritizes flows by estimated task utility, risk
   reduction, age urgency, operator impact, bandwidth cost, and redundancy.

4. Freshness-First Reliability

   A reliability model that drops stale data deliberately and retransmits only
   samples that are still useful.

5. Runtime Admission Control

   A safety shield that reserves bandwidth and deadline budget for
   control/state/coordination flows before permitting debug/video/bulk traffic.

## Research Hypotheses

Compared with DDS native, Zenoh bridge, DDS Router, and static-priority fleet
bridges, FleetRMW/FleetQoX should:

- reduce p99 command latency under mixed video/debug load;
- reduce stale state ratio;
- reduce bandwidth for perception/fleet state using semantic deltas;
- improve operator QoE under congestion;
- reduce graph/discovery overhead by exposing capability graphs rather than raw
  endpoint graphs;
- improve task success under packet loss and bandwidth contention.

## Evaluation Plan

Phase 1: deterministic simulator

- 10, 50, 100, 300 robot workloads;
- mixed control/state/perception/operator/debug flows;
- constrained links with loss/jitter/capacity changes;
- compare FIFO, static priority, and Causal Semantic Deadline Scheduler.

Phase 2: ROS 2 bridge prototype

- observe ROS graph;
- classify flows;
- bridge selected topics over QUIC/Zenoh/WebRTC;
- keep DDS local.

Phase 3: non-DDS RMW

- implement pub/sub and graph cache;
- implement services;
- let actions work through topics/services;
- add QoX-aware data plane.

Phase 4: robot benchmark

- Nav2 multi-robot simulation;
- Wi-Fi/4G emulation with `tc/netem`;
- operator teleop scenario;
- large-scale graph/discovery benchmark.

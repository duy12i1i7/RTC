# Network Simulator Plan

## Why Add ns-3 And OMNeT++?

FleetRMW is a communication research project, so Linux emulation alone is not
enough. Tools such as `tc netem`, Mininet, and Containernet can run real ROS 2
processes, but they approximate the network as delays, loss, bandwidth limits,
and virtual links. They do not model wireless contention, roaming, MAC behavior,
interference, 5G scheduling, or multi-hop mesh effects with enough fidelity.

Network simulators should therefore become a first-class part of the testbed.

## Simulator vs Emulator

```text
Emulator:
  runs real ROS 2 binaries
  uses Linux network stack
  good for integration and reproducibility
  weaker PHY/MAC fidelity

Discrete-event simulator:
  runs modeled traffic and modeled network protocols
  good for Wi-Fi/5G/mesh/TSN/roaming fidelity
  harder to run unmodified ROS 2 applications
```

FleetRMW needs both.

## Where ns-3 Fits

ns-3 should be used for high-fidelity network experiments:

- Wi-Fi 5/6/6E/7-like contention scenarios where models exist;
- LTE/5G NR using 5G-LENA;
- mesh/ad-hoc routing;
- mobility and roaming;
- packet-level delay/loss/jitter distributions;
- sensitivity analysis across channel, mobility, and load.

Best use:

```text
ROS/FleetQoX traffic model
  -> ns-3 application traffic generators
  -> Wi-Fi/LTE/5G/mesh network
  -> per-flow traces
  -> FleetQoX scheduler evaluation
```

ns-3 is stronger for scientific communication-network claims than for direct
ROS integration.

## Where OMNeT++ / INET Fits

OMNeT++ with INET should be used for:

- modular protocol experiments;
- wired/wireless/mobile network scenarios;
- TSN and traffic shaping studies;
- visual and inspectable protocol modeling;
- rapid experimentation with routing/queueing variants.

INET supports wired, wireless, mobile, ad hoc, sensor, Internet stack, routing,
DiffServ, MPLS, mobility, emulation, and TSN-related components. This makes it
well-suited for FleetRMW control-plane ideas that need custom scheduling,
traffic classes, admission control, and network-policy validation.

Best use:

```text
FleetQoX policy trace
  -> OMNeT++/INET traffic classes
  -> queueing / shaping / TSN / Wi-Fi model
  -> QoS/QoE/QoT result comparison
```

## Proposed New Tier

Add a dedicated tier:

```text
T2S: Discrete-event network simulation
  built-in replay: lightweight queueing sanity check
  ns-3: Wi-Fi, LTE/5G, mesh, mobility
  OMNeT++/INET: protocol design, TSN, shaping, routing, custom queues
```

This sits between:

- T2E: real ROS 2 network emulation;
- T3: robot simulator.

## Co-Simulation Strategy

There are three levels of coupling.

### Level A: Trace-Driven Simulation

Run ROS 2 synthetic/fleet workloads, export per-flow traces:

```json
{"time": 0.10, "flow": "robot_17/state", "size": 320, "deadline_ms": 120}
```

Feed those traces into ns-3 or OMNeT++ as application traffic.

This is the lowest-risk and most reproducible first approach.

Implemented now:

```bash
python3 -m scripts.export_traces --scenario warehouse_100_constrained --format csv
python3 -m scripts.replay_trace traces/warehouse_100_constrained.csv
```

The built-in replay is a sanity check, not a substitute for ns-3 or OMNeT++.
It validates trace quality and metric calculation before running heavier
simulators.

### Level B: Policy-In-The-Loop

Run the FleetQoX scheduler as a library or offline policy in the network
simulator. At each scheduling epoch, the simulator asks FleetQoX which packets
or flows should be admitted/degraded/dropped.

This tests the algorithm under high-fidelity network dynamics.

### Level C: Live Co-Simulation

Connect ROS 2 runtime to a network simulator through sockets/TAP/FdNetDevice or
external interfaces. This is powerful but fragile and should not be the first
milestone.

## What To Measure In T2S

- per-flow delay distribution;
- p99/p999 deadline miss;
- queue occupancy;
- airtime utilization;
- retransmission count;
- handover interruption;
- fairness across robots;
- control-plane starvation events;
- QoE stream freeze/stutter;
- task-state update freshness.

## Why This Is Important For Novelty

If FleetRMW only beats baselines under `tc netem`, reviewers can argue that the
network model is too simple. If it also beats baselines in ns-3/OMNeT++ under
Wi-Fi contention, 5G scheduler variation, mesh routing, and TSN shaping, the
claim becomes much stronger.

The final research story should therefore combine:

```text
T1/T2E: real ROS 2 binaries
T2S: high-fidelity network science
T3/T4: robot and fleet task impact
```

## First Implementation Target

Start with trace-driven ns-3/OMNeT++ because it does not require a full RMW.

1. Export FleetQoX workload traces from T0/T1. Done for T0.
2. Define common trace schema. Done.
3. Write ns-3 importer for UDP-like per-flow traffic. Starter added under
   `external/ns3`.
4. Write OMNeT++/INET importer for application traffic classes. Template added
   under `external/omnetpp`; the C++ app must be validated against the selected
   INET version.
5. Compare FIFO/static-priority/FleetQoX policies under identical network
   scenarios.

The current ns-3 runner expects an external ns-3 workspace:

```bash
export NS3_WORKSPACE=/path/to/ns-3
python3 -m scripts.run_ns3_replay --trace traces/warehouse_100_constrained.csv
```

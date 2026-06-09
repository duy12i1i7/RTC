# Experimental Methodology

## Evaluation Philosophy

FleetRMW must not be evaluated as "one more transport". It must be evaluated as
a communication system for robot fleets. Therefore each experiment must include:

- a baseline;
- a controlled impairment or scale factor;
- a communication metric;
- a robot/fleet metric;
- an operator/QoE metric when human-visible streams are present.

## Baselines

Minimum baselines:

- Fast DDS simple discovery;
- Cyclone DDS;
- Fast DDS Discovery Server;
- Zenoh RMW;
- Zenoh ROS 2 bridge;
- DDS Router;
- static priority bridge;
- FIFO/no-admission-control bridge.

The early local prototype compares only FIFO, static priority, and FleetQoX
CSDS. Later ROS 2 experiments must add the middleware baselines above.

## Metrics

### Network And Middleware

- discovery convergence time;
- discovery bytes;
- graph churn rate;
- p50/p95/p99/p999 latency;
- jitter;
- packet loss;
- retransmission rate when observable;
- throughput and goodput;
- per-flow deadline miss ratio;
- stale sample ratio;
- CPU and memory.

### Fleet And Robot

- task completion time;
- task success/failure;
- navigation recovery count;
- conflict resolution delay;
- coordination update age;
- localization/state freshness;
- control interruption count.

### QoE

- video freeze count;
- frame staleness;
- command-to-visual response latency;
- teleop correction count;
- operator-visible stream availability;
- smoothness score.

## Experiment Tiers

### T0: Analytical FleetQoX Simulator

Purpose: prove scheduling ideas and metric definitions quickly.

Inputs:

- robot count;
- capacity;
- loss/jitter patterns;
- flow mix;
- task risk distribution.

Outputs:

- deadline miss;
- stale ratio;
- QoE delivery ratio;
- utility score;
- bytes sent;
- degradation count.

### T1: ROS 2 Synthetic Graph

Purpose: test real ROS 2 message passing without robot physics.

Tools:

- `performance_test`;
- `ros2_tracing`;
- `ros2 topic info --verbose`;
- `ros2 daemon stop`;
- RMW switching via `RMW_IMPLEMENTATION`.

Variables:

- RMW;
- message size;
- publishers/subscribers;
- QoS;
- processes vs composition;
- domain IDs;
- discovery mode.

### T2E: Network Emulation

Purpose: test real ROS 2 traffic under controlled bad networks.

Tools:

- `tc netem`;
- Docker network namespaces;
- Containernet/Mininet-WiFi;
- Pumba for container chaos.
- ROS 2 `performance_test` in publisher/subscriber containers.

Variables:

- delay;
- jitter;
- loss;
- bandwidth;
- roaming-like capacity drops;
- multicast allowed/blocked;
- routed LAN vs same subnet;
- NAT-like topology.

Two T2E paths are maintained:

- trace UDP emulation, which validates Linux/socket/netem behavior without ROS;
- ROS 2 `performance_test` emulation, which validates real RMW behavior under
  the same impairment classes.

### T2S: Discrete-Event Network Simulation

Purpose: test FleetRMW/FleetQoX under network models that are more realistic
than `tc netem`.

Tools:

- built-in FleetQoX trace replay for quick queueing sanity checks;
- ns-3;
- ns-3 5G-LENA;
- OMNeT++;
- INET.

Variables:

- Wi-Fi contention;
- channel model/path loss;
- AP association and roaming;
- multi-hop mesh routing;
- LTE/5G scheduling;
- TSN/traffic shaping;
- traffic class mapping;
- mobility model.

Integration modes:

- trace-driven workload import;
- policy-in-the-loop FleetQoX scheduler;
- later, live co-simulation.

The built-in trace replay should be treated as a pre-flight check. It is useful
for verifying trace schemas, deadline accounting, and policy comparisons, but
publishable network claims should rely on ns-3/OMNeT++ or real emulation.

### T3: Multi-Robot Autonomy Simulation

Purpose: connect communication quality to robot behavior.

Tools:

- Gazebo Sim;
- Nav2;
- TurtleBot3/TurtleBot4-like multi-robot setup;
- rosbag2/MCAP;
- RViz/Foxglove for visual inspection.

Variables:

- robot count;
- mission density;
- obstacle density;
- video/debug load;
- simulated AP zones;
- operator teleop events.

### T4: Fleet Task Simulation

Purpose: test task allocation and coordination under communication limits.

Tools:

- Open-RMF demos;
- RMF task dispatch;
- synthetic fleet adapters;
- network emulation around adapters/robots.

Variables:

- fleet size;
- task arrival rate;
- map topology;
- conflict zones;
- elevators/doors if needed;
- adapter latency/loss.

### T5: HIL And Physical Robots

Purpose: validate against reality after the software evidence is strong.

Candidates:

- 2-5 TurtleBot/TurtleBot4 robots;
- one real robot plus N simulated robots;
- Raspberry Pi/Jetson nodes with real Wi-Fi roaming;
- bridge laptop running FleetRMW sidecar.

## Acceptance Gates

Do not move from one tier to the next until:

- the experiment is reproducible from a manifest;
- the result is captured in a structured file;
- repeated runs report mean, variance, and confidence intervals when the claim
  compares algorithms rather than only checking tool wiring;
- at least two baselines are included;
- failure modes are visible, not hidden;
- metrics show either improvement or a clear reason for redesign.

## Minimum Publishable Benchmark

A convincing first paper-quality benchmark should include:

- T1: ROS 2 synthetic graph with 3 RMW baselines;
- T2E: network emulation with loss/jitter/bandwidth sweeps;
- T2S: at least one ns-3 or OMNeT++ discrete-event network study;
- T3: 20-50 robot Nav2 simulation or lightweight robot graph equivalent;
- T4: at least one Open-RMF-style task/fleet scenario;
- full traces for at least representative runs;
- p99/p999 and stale-data metrics, not only averages.
- Pareto-frontier analysis over utility, deadline miss, loss, and QoE risk.

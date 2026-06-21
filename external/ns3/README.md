# ns-3 Trace Replay Harness

This folder contains a starter ns-3 replay program for FleetQoX packet traces.

It is intentionally trace-driven:

```text
FleetQoX T0/T1 workload
  -> CSV packet trace
  -> ns-3 topology and channel model
  -> per-policy delay/deadline/utility statistics
```

## Generate Input

From the repository root:

```bash
python3 -m scripts.export_traces \
  --scenario warehouse_100_constrained \
  --format csv \
  --output-dir traces
```

## Use With ns-3

Copy or symlink `fleetqox_trace_replay.cc` into an ns-3 workspace under
`scratch/`, then run:

```bash
./ns3 run "scratch/fleetqox_trace_replay \
  --trace=/absolute/path/to/traces/warehouse_100_constrained.csv \
  --dataRate=54Mbps \
  --delay=2ms"
```

The replay program supports both a CSMA shared medium and a single-AP 802.11g
infrastructure topology with stationary or constant-velocity stations.

## Reproducible Docker Matrix

The FleetRMW Docker image includes ns-3 3.41 and its development libraries.
Run the repeated matrix without an external ns-3 workspace:

```bash
python3 scripts/run_ns3_docker_fleet_matrix.py \
  --robot-counts 8,16,32 --seeds 7,13,29 --seconds 3
```

The runner adds an independent receive packet error model and fixes ns-3
seed/run per repetition. The current CSMA topology is not a high-fidelity
wireless model; the summary carries this claim boundary explicitly.

Run the native Wi-Fi/mobility matrix with:

```bash
python3 scripts/run_ns3_docker_wifi_mobility_matrix.py \
  --robot-counts 8,16,32 --seeds 7,13,29 --seconds 3
```

The recorded campaign passes `27/27` rows. It uses one infrastructure AP and
three station speed/spacing/PHY-rate profiles. The generated summary permits
Wi-Fi and mobility-model claims and forbids roaming handoff claims.

Run the measured dual-AP roaming matrix with:

```bash
python3 scripts/run_ns3_docker_wifi_roaming_matrix.py \
  --robot-counts 8,16,32 --seeds 7,13,29 --seconds 3
```

This gate requires direct association/disassociation trace events, at least
one AP1-to-AP2 handoff per endpoint, stable station IP addresses over bridged
backhaul, and positive receive counts. The recorded campaign passes `27/27`
rows and `585/585` required handoffs. The range-limited 802.11g model supports
a scoped handoff claim, not a general high-fidelity wireless claim.

## Next Extensions

- map `flow_class` to access categories or queue disciplines;
- add richer propagation/interference and Wi-Fi access-category models;
- add 5G-LENA private 5G scenarios;
- emit JSONL results instead of console summaries;
- import multiple policies and run comparative sweeps.

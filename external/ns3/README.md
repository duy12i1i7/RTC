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

The starter topology is a CSMA shared medium. It is deliberately simple so the
trace importer and metrics can be validated before replacing the channel with
Wi-Fi, mesh, LTE/5G-LENA, or custom queueing.

## Next Extensions

- replace CSMA with Wi-Fi AP/station topology;
- map `flow_class` to access categories or queue disciplines;
- add mobility and roaming;
- add 5G-LENA private 5G scenarios;
- emit JSONL results instead of console summaries;
- import multiple policies and run comparative sweeps.

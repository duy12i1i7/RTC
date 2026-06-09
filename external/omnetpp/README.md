# OMNeT++ / INET Trace Replay Starter

This folder contains a starter layout for replaying FleetQoX packet traces in
OMNeT++ with INET.

The ns-3 harness is the first concrete replay target. The OMNeT++ files here
define the intended project shape and the NED/INI structure that should be
validated against the installed OMNeT++ and INET versions.

## Generate Input

```bash
python3 -m scripts.export_traces \
  --scenario warehouse_100_constrained \
  --format csv \
  --output-dir traces
```

## Intended Experiment

```text
CSV trace
  -> TraceDrivenUdpApp instances
  -> INET hosts/switch/AP/TSN/mesh topology
  -> scalar/vector results
```

## Suggested Next Steps

1. Create an OMNeT++ project and add INET.
2. Copy `FleetQoxTraceReplay.ned`, `TraceDrivenUdpApp.ned`, and `omnetpp.ini`.
3. Implement `TraceDrivenUdpApp.cc` against the installed INET API.
4. Map `flow_class` to INET traffic classes / queues.
5. Add Wi-Fi, TSN, and mesh variants.

OMNeT++/INET APIs and NED module names can vary by version. Keep this folder as
the project template, then validate and pin versions in the external simulator
workspace.

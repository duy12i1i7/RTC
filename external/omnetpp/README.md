# OMNeT++ / INET Trace Replay Runtime

This directory is a runnable FleetQoX trace-replay project, not a template.
It pins OMNeT++ 6.4.0 and INET 4.7.0 by commit in `Dockerfile`, builds a
headless runtime, and implements `TraceDrivenUdpApp` against the INET UDP API.

Each FleetQoX endpoint is an INET `StandardHost`. The controller, fleet router,
operator UI, and `robot[]` hosts use a routed two-hop PPP star. Every app
reads the same CSV cache, sends rows matching its endpoint through `UdpSocket`,
and records policy-level transmission, reception, deadline, latency, byte, and
semantic-utility metrics.

## Build and smoke parity

From the repository root:

```bash
docker build \
  -t localhost/fleetqox/omnetpp-inet:6.4.0-4.7.0 \
  external/omnetpp

python3 scripts/run_omnetpp_docker_parity.py \
  --skip-image-build \
  --robot-counts 8 \
  --seeds 7 \
  --seconds 1 \
  --summary-json results_omnetpp/omnetpp_ns3_docker_parity_smoke_summary.json
```

The full default matrix uses 8/16/32 robots, seeds 7/13/29, three matched link
profiles, and three policies. The runner generates each trace once, runs that
same file in native ns-3 and OMNeT++/INET Docker runtimes, and evaluates the
declared metric bounds in its JSON artifact.

## Claim boundary

Successful execution proves a real OMNeT++/INET UDP replay path. A successful
parity matrix proves only the runner's bounded, matched routed-P2P scope. The
`TsnMixedFleet` and `MeshDegraded` configs remain named extension points;
802.1Qbv/Qav TSN, MANET mobility/routing, and wireless fidelity are not claimed
until those models have dedicated runtime evidence.

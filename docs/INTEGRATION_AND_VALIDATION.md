# Integration and Validation

## Validation ladder

FleetRMW uses a tiered evidence model:

| Tier | Environment | Purpose |
|---|---|---|
| T0 | Analytical/Python simulation | Scheduling, admission, and metric sanity |
| T1 | ROS 2 synthetic graph | Real RMW ABI and message/service/action behavior |
| T2E | Docker/tc-netem | Real processes and controlled delay/loss/rate/topology |
| T2S | ns-3 and OMNeT++/INET | Discrete-event contention, mobility, and parity |
| T3 | Nav2 multi-robot simulation | Communication effects on navigation behavior |
| T4 | Open-RMF fleet workload | Dispatch, bidding, coordination, and fleet failures |
| T5 | HIL/physical robots | Reality check for hosts, Wi-Fi, timing, and operations |

## Baseline comparison

The primary middleware baselines are:

- Fast DDS;
- Cyclone DDS;
- Zenoh RMW;
- FleetRMW.

The common-middle harness keeps the application topology, serialized relay
role, sample count, payload, profile, and seed aligned. Rows with different
middle processing, failed processes, missing payloads, or incompatible resume
provenance must be marked non-comparable.

No current result supports a universal latency or superiority claim.

## Docker/tc-netem

The Docker runners cover:

- Wi-Fi, WAN, and roaming profiles;
- delay, jitter, loss, bandwidth, and queue effects;
- 8/16/32 robot scales;
- exact payload and offered-load sensitivity;
- graph/discovery, typed and serialized traffic, service/action traffic;
- fragment loss/repair/admission/fairness;
- QUIC/mTLS and failure behavior;
- stress/security campaigns.

Every publishable row should record image, RMW, profile, seed, payload, timing,
topology, process return codes, delivery, latency, and transport telemetry.

## Nav2

Implemented evidence includes action workloads, `NavigateToPose` paths,
planner/static obstacle recovery, selected dynamic-obstacle recovery slices,
and router QoX actuation.

Still required:

- sustained planner/controller/costmap execution;
- dynamic obstacle churn over long runs;
- full recovery-tree behavior and terminal outcomes;
- multi-robot contention with realistic sensors/state/control;
- multi-host and HIL execution.

The capability manifest therefore keeps full dynamic-obstacle navigation and
production costmap recovery policy false.

## Open-RMF

Implemented evidence includes bounded fleet action workloads, dispatch-related
interfaces, task admission, outcome reporting, and large fleet windows.

Still required:

- representative bidding and dispatch traffic;
- fleet-state and adapter churn;
- doors/lifts/conflict-zone interactions where relevant;
- process/network failures during active tasks;
- multiple fleet adapters and hosts;
- task-level success, delay, and recovery metrics.

## ns-3 and OMNeT++/INET

The repository contains trace-driven runners and parity matrices. This proves
tool integration and bounded agreement for the selected abstractions.

It does not yet prove high-fidelity wireless equivalence. Completion requires:

- calibrated Wi-Fi contention/path-loss/roaming models;
- mobility and AP association;
- mesh/TSN scope where claimed;
- matching workload/seed/schema across simulators;
- sensitivity analysis and documented model limitations.

## Stress, soak, and physical validation

Short repeated campaigns are useful gates but are not long soak. Release
qualification needs:

- sanitizer campaigns;
- hours-to-days data-plane and credential churn;
- bounded CPU/RSS/queue/state trends;
- process kill/restart, partition, recovery, and clock behavior;
- at least one real Wi-Fi/multi-host testbed;
- HIL and a small physical fleet.

## Acceptance discipline

A tier can support the next tier only when its runner, manifest, structured
result, failure diagnostics, and claim boundary are reproducible. Simulation
does not replace real emulation; emulation does not replace HIL; one physical
demo does not replace repeated controlled evidence.

# Architecture

## Design objective

FleetRMW preserves the ROS 2 application model while replacing DDS-dependent
endpoint delivery with a native middleware that can make fleet-level decisions.
FleetQoX is the control plane that supplies those decisions.

The implementation deliberately separates:

- ROS 2 ABI semantics;
- sample identity and wire contracts;
- reliability and repair;
- fleet admission/scheduling/path control;
- physical transports;
- evidence and operational telemetry.

## Layer model

```text
┌─────────────────────────────────────────────────────────────┐
│ ROS 2 applications: rclcpp, rclpy, Nav2, RMF, fleet nodes  │
├─────────────────────────────────────────────────────────────┤
│ rmw_fleetqox_cpp                                            │
│ lifecycle · graph · wait · pub/sub · service/action · QoS   │
├─────────────────────────────────────────────────────────────┤
│ FleetRMW contracts                                          │
│ endpoint/sample identity · sequence · time · QoX · fidelity │
├─────────────────────────────────────────────────────────────┤
│ Reliability                                                  │
│ ACK/NACK · history · fragments · repair · loss termination  │
├─────────────────────────────────────────────────────────────┤
│ FleetQoX control                                             │
│ admission · priority · robot budgets · path/repair planning │
├─────────────────────────────────────────────────────────────┤
│ Transport selection                                         │
│ shared memory · UDP · QUIC/mTLS · explicit fallback         │
├─────────────────────────────────────────────────────────────┤
│ Docker/netem · ns-3 · OMNeT++ · multi-host · HIL           │
└─────────────────────────────────────────────────────────────┘
```

## ROS 2 RMW boundary

`ros2_ws/src/rmw_fleetqox_cpp` owns the ROS 2-facing ABI. Its main state is
partitioned by entity ownership and guarded registries:

- contexts and nodes;
- publishers/subscriptions;
- clients/services;
- wait sets and guard conditions;
- local and leased remote graph endpoints;
- QoS/event state;
- reliable writer/reader state;
- transport state.

The package supports introspection C and C++ serialization rather than copying
native message object memory onto the wire. Optional ABI surfaces must either
perform real work or return a controlled unsupported/error result.

## Identity and sample contract

Every FleetRMW data sample can carry:

- domain, topic, and ROS type;
- publisher/endpoint identity;
- source sequence;
- source and receive timestamps;
- flow/task/QoX metadata;
- admission and path provenance;
- fidelity/degradation information.

Identity is required for deduplication, ACK/NACK, source-scoped repair, graph
events, task outcomes, and auditability. See
[Data Frame](FLEETRMW_DATA_FRAME_V1.md),
[Sample Envelope](FLEETRMW_SAMPLE_ENVELOPE_V1.md), and
[Sample Contract](RMW_SAMPLE_CONTRACT_V1.md).

## Reliability path

### Small samples

Reliable writers retain bounded history. Readers observe source sequences and
return subscriber-identified ACK/NACK feedback. Writer timeout and repair
budgets are bounded; unrecoverable loss becomes an explicit terminal notice.

### Large samples

Large payloads follow this path:

1. Derive a stable frame identity.
2. Select an effective chunk size within the configured UDP wire budget,
   including protection overhead.
3. Queue initial fragments per frame in round-robin order.
4. Emit an authenticated sender-completion marker after physical drain.
5. Retain bounded writer fragment history.
6. Assemble unique fragments under bounded count/byte/TTL limits.
7. Request observed holes and guarded trailing indexes.
8. Queue selective repair per `(fragment, reader target)` in round-robin order.
9. Coalesce pending/recent repairs and apply bounded progress-aware backoff.
10. Complete, deduplicate, ACK, or report terminal loss.

The transport exports queue, history, assembly, NACK, repair, duplicate,
fairness, admission, and failure telemetry.

## FleetQoX control plane

For each flow, FleetQoX can use:

- flow class and semantic contract;
- deadline, lifespan, age, and size;
- task risk and causal gain;
- robot virtual budget;
- operator QoE sensitivity;
- network profile and live telemetry;
- available paths and repair capacity;
- application/task outcomes.

Decisions include:

- admit/send now;
- select one or more paths;
- reserve repair capacity;
- degrade representation;
- defer;
- drop stale data;
- reject with an observable reason.

Fleet planning is not allowed to silently bypass RMW semantics. Plans are
versioned/observable and actuated through the router/RMW data plane.

## Communication planes

Flows are grouped by semantics rather than only topic name:

- safety/control;
- coordination/task state;
- localization/state;
- perception-semantic;
- operator QoE/teleoperation;
- diagnostics;
- debug/bulk.

Each plane can have independent admission, reliability, repair, degradation,
and path rules while sharing a fleet-level capacity budget.

## Graph model

Local ROS 2 endpoints remain visible through normal graph APIs. Remote graph
state is advertised over FleetRMW control frames and expires by lease. The
long-term target is a compressed fleet capability graph so every robot does not
need every internal endpoint of every other robot.

The current implementation includes local and remote endpoint tracking, QoS and
type matching, guard wakeups, explicit remove, renewal deduplication, and lease
expiry. Full vendor/DDS-equivalent remote event semantics remain incomplete.

## Transport model

### Shared memory

Used for local large payloads with bounded slots and explicit initialization
failure. Hybrid mode can deliver locally over SHM and remotely over UDP while
deduplicating at the application boundary.

### UDP

The primary research data plane for native framing, graph/control traffic,
ACK/NACK, fragmentation, repair, and netem evidence. UDP is not presented as a
QUIC substitute.

### QUIC

Used for real encrypted session-oriented paths, mTLS identity, full-duplex
traffic, admission, outcomes, and gateway state/failover. Research probes cover
many slices; production PKI and distributed cluster semantics remain open.

## State and resource bounds

Production-oriented middleware cannot hide unbounded maps or queues. FleetRMW
therefore exposes limits for:

- wait-set entities;
- service request/response/replay state;
- writer and fragment history;
- fragment assemblies and total assembly bytes;
- initial and repair send queues;
- repair requests per reader;
- completed-frame tombstones;
- gateway and outcome state.

Limits must have observable rejection/eviction/exhaustion behavior. A bounded
probe does not by itself prove the chosen limit is sufficient for production.

## Concurrency and teardown

Transport receive and fragment sender threads operate independently of ROS
application executors. Registries use explicit locks, and callback-owner
teardown waits for in-flight callback notifications before freeing entities.

Memory safety under typed large-message stress remains an active release
blocker and must be qualified under sanitizers before the architecture can be
called production-safe.

## Observability

Evidence is emitted as structured JSON with schema versions and explicit claim
booleans. Important telemetry includes:

- delivery, latency, freshness, and task/QoE outcomes;
- process return codes and benchmark provenance;
- queue/state high-water and admission outcomes;
- ACK/NACK, retries, repairs, coalescing, and terminal loss;
- graph/event transitions;
- QUIC identity/session/failover state;
- CPU/RSS and long-run trends where available.

The capability manifest is the final machine-readable boundary between
implemented behavior, partial behavior, unsupported behavior, and production
claims.

# Experimental Results

## Scope

This document is the concise evidence snapshot for the current repository. It
records what has been demonstrated, what failed, and which claims remain open.
Historical milestone-by-milestone reports were removed from the working tree;
they remain available through Git history.

The normative claim boundary is
`ros2_ws/src/rmw_fleetqox_cpp/capabilities.json`.

## Verification snapshot

| Evidence | Current result | Boundary |
|---|---:|---|
| Clean-source suite | 690 discovered: 637 pass, 53 external-artifact skips | Does not replace ROS/Docker execution |
| Supported capabilities | 510 | Scoped capability entries |
| Claim boundaries | 607 true / 46 false | `production_ready=false` |
| Callback teardown stress | 20/20 processes | 160 publisher + 160 subscription cases |
| Deterministic repair fairness | 8/8 frames | One fragment per active repair scope while contended |
| Best retained 16-robot 32-KiB frontier | 155/160 | Single seed; negative fleet-scale result |
| Stress/security campaign | 80/80 component runs, 1680/1680 probes | Bounded campaign, not production soak |

## RMW core

The C++ ROS 2 Jazzy package has executable probes for:

- lifecycle and owner validation;
- local/remote graph, lease expiry, guard wakeup, and domain isolation;
- serialized and typed pub/sub using introspection C/C++;
- wait sets and externally owned rcl timer guards;
- services, actions, bounded service state, repair, replay, priority, weighted
  fairness, and deadline scheduling;
- QoS events, content filters, dynamic messages, loan lifecycle, reusable
  allocation scratch, take sequence, and scoped all-acknowledged behavior;
- shared-memory, UDP, and QUIC paths.

The exported-symbol audit and probes demonstrate broad ABI coverage. Full
DDS/vendor semantics, deep preallocation, and zero-copy remain unclaimed.

## Large-sample reliability

### Deterministic controls that pass

- Exact 32768-byte selective repair with whole-sample timeout retry disabled.
- MTU-aware wire budgeting: a requested 4096-byte chunk is reduced to a
  protected effective payload that keeps the datagram within 1472 bytes.
- Bounded fragment assembly count/bytes/TTL and fail-closed metadata collision
  and oversize handling.
- Authenticated fragment admission and unauthorized identity pressure
  isolation.
- Source-scoped two-reader repair and untargeted-source denial.
- A 513-assembly NACK sweep with a 512-index hard budget and rotating cursor.
- Initial-fragment round robin with maximum one consecutive frame while
  contended.
- Duplicate fragments do not refresh assembly progress or postpone trailing
  repair.
- Later repair rounds use exponential backoff plus bounded progress grace.
- Per-frame/reader repair queues rotate one fragment per active scope while
  contended.

Representative runners:

```text
scripts/run_rmw_docker_selective_fragment_repair_probe.py
scripts/run_rmw_docker_fragment_assembly_admission_probe.py
scripts/run_rmw_docker_authenticated_fragment_assembly_probe.py
scripts/run_rmw_docker_multireader_fragment_repair_probe.py
scripts/run_rmw_docker_fragment_nack_fairness_probe.py
scripts/run_rmw_docker_initial_fragment_round_robin_probe.py
scripts/run_rmw_docker_fragment_tail_progress_probe.py
scripts/run_rmw_docker_progressive_fragment_repair_probe.py
scripts/run_rmw_docker_fragment_repair_round_robin_probe.py
```

### Fleet frontier that does not pass

The retained 16-robot, 32-KiB, roaming-loss, seed-7 progression includes:

| Revision/operating point | Delivery | Relevant observation |
|---|---:|---|
| MTU/pacing row | 152/160 | Negative baseline for later fixes |
| Duplicate/no-progress fix | 155/160 | Best retained row; four publisher topics unacknowledged |
| Immediate progressive repair | 151/160 | Excess repair pressure |
| Bounded progress grace | 152/160 | Deferrals and admission wait reduced |
| Per-frame/reader repair round robin | 152/160 | Selective sends 10499→6932; deferrals 698→29 |
| Repair round robin, 3.0-ms pacing | 148/160 | Slower drain increased duplicate NACK/repair |
| Repair round robin, 500-ms NACK | 151/160 | Lower pressure, no delivery improvement |

The fair repair row reaches 59 active repair scopes, 5736 rotations, and a
maximum contended consecutive service of one. Delivery remaining incomplete
after repair pressure falls shows that FIFO starvation was not the only
bottleneck. Whole-frame observation, late burst/horizon convergence, and
memory safety require further work.

The correct current claims are:

```text
fleet_scale_selective_fragment_repair_claim=false
production_large_sample_reliability_claim=false
same_hop_32768_fully_successful_schedule_claim=false
```

## Memory safety

The callback-owner quiescence gate passes 20 fresh processes with eight
publisher and eight subscription cases per process, totaling 320 cases.

However, two long lossy 32-KiB runs ended in the subscriber with:

```text
free(): invalid next size (fast)
```

Six subsequent short selective-repair processes passed, so this is intermittent
and not yet localized. The typed `std_msgs/String` probe now accepts large
payload/iteration settings for ASan/UBSan stress. A fresh ROS 2 Jazzy Docker
build instrumented with AddressSanitizer and UndefinedBehaviorSanitizer passed
both 500/500 and 5,000/5,000 same-process typed 32-KiB publish/take iterations,
including clean finalization, with no sanitizer report. This is useful negative
evidence but does not exercise the original lossy inter-process fragment path.
Until that path is reproduced, fixed, and protected by a repeated sanitizer
gate, memory safety remains a release blocker.

## QoS, services, and actions

Passing scoped evidence includes:

- local and selected remote matched, deadline, incompatibility, liveliness,
  and message-lost event behavior;
- wait/take/callback/clear event lifecycle;
- bounded request/response/replay state;
- per-client service admission and fairness;
- asynchronous service repair and cancelled-job cleanup;
- bounded durable service replay after process replacement;
- action frame/QoS paths and large status/service payload fragmentation.

Open boundaries include full remote graph/event production, full non-deadline
QoS event semantics, full DDS content-filter dialect, full DDS writer-history
all-acknowledged behavior, and power-loss/exactly-once semantics.

## QUIC and gateway state

Scoped evidence covers:

- real QUIC publish/take paths;
- in-process full-duplex and session reuse;
- concurrent streams;
- mTLS identity and admission;
- public ngtcp2 gateway patches/probes;
- task/application outcomes;
- durable outcome/admission state and bounded failover;
- PostgreSQL-backed state/replication/quorum experiments.

The following remain false: production QUIC backend, public active-session
revocation/online certificate rotation, complete forward-secret asymmetric
establishment, consensus/split-brain/regional recovery, production rejoin and
failback, and zero-RTT.

## FleetQoX control

The repository demonstrates:

- causal-semantic deadline scheduling;
- predictive/guarded/profile-aware/Lagrangian admission variants;
- outcome-driven adaptation;
- robot virtual budgets;
- local control leases and projection-quality gates;
- fleet path and repair plans;
- live telemetry-to-router/RMW plan actuation;
- task-outcome submission and durable gateway feedback.

These results establish a functioning research control plane. They do not yet
establish a globally optimal or production-safe controller.

## Nav2 and Open-RMF

Docker probes cover action wiring, selected `NavigateToPose` execution,
planner/static-obstacle repair, bounded dynamic-obstacle recovery slices,
router QoX actuation, fleet task/action workloads, and admission windows up to
4096 tasks.

The capability manifest correctly keeps full dynamic-obstacle navigation and
production costmap recovery policy false. A full planner/controller/costmap
campaign and representative multi-host RMF bidding/dispatch/failure workload
remain open.

## Baseline comparison

The same-hop common-middle comparison includes FleetRMW, Fast DDS, Cyclone DDS,
and Zenoh. A repaired comparison bundle preserves 36/36 passing rows across the
profile/scale matrix, with baseline relays delivering the expected 5040/5040
samples in the cited campaign.

This supports runner/tooling parity for those rows. It does not support:

- universal cross-RMW superiority;
- latency superiority;
- payload-latency distribution superiority;
- comparison of failed/incomplete 32-KiB rows as if they succeeded.

The common-middle runner and report generator are:

```text
scripts/run_same_hop_rmw_comparison.py
scripts/generate_unified_benchmark_report.py
```

## ns-3 and OMNeT++/INET

Trace-driven ns-3 and OMNeT++/INET runners execute matched input matrices and
bounded parity checks. The OMNeT++ environment targets the repository's pinned
6.4/INET 4.7 setup.

This proves integration and selected trace parity, not high-fidelity wireless
or TSN/mesh equivalence. Model calibration, mobility/association, contention,
mesh, and TSN scope remain completion work.

## Stress and security

The consolidated campaign reports 80/80 component executions and 1680/1680
probe checks over approximately 3793 seconds for its configured bounded run.
Other deterministic controls cover AEAD, mTLS, SROS2-derived identity,
unauthorized fragment pressure, CRL refresh slices, failover, and resource
limits.

The campaign is not a long-duration production soak. Multi-attacker credential
rotation, active-session revocation, PKI operations, distributed gateway
failure semantics, and independent security review remain open.

## Evidence rules

- Deterministic probes establish contracts, not broad performance claims.
- One stochastic seed establishes a frontier observation, not reliability.
- Failed rows remain visible.
- Every comparative claim requires aligned application middle, payload,
  profile, topology, seed, and process health.
- Security and simulator claims are no broader than their tested threat/model
  boundary.
- `production_ready=false` remains authoritative.

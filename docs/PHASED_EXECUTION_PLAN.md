# FleetRMW / FleetQoX Phased Execution Plan

## Purpose

This document is the operational execution plan for taking the current FleetRMW/FleetQoX research prototype from its present checkpoint to a reproducible research release candidate and then toward production-oriented qualification.

The plan is intentionally dependency-ordered. Work should not advance to later phases merely because code exists; each phase has explicit exit gates. If evidence changes the diagnosis, this plan should be revised before continuing.

## Canonical project objective

FleetRMW/FleetQoX aims to provide a ROS 2-native, non-DDS middleware and fleet control plane for large robot fleets. The system should make task-aware admission, scheduling, degradation, path selection, reliability, repair, and resource-budget decisions while preserving ROS 2 semantics and exposing bounded, testable, reproducible behavior.

The final target includes:

- ROS 2-native RMW behavior on FleetRMW transports;
- fleet-scale reliable communication under bounded resource budgets;
- task-aware QoS/QoE/QoT control;
- shared memory, UDP, and production-qualified QUIC/mTLS paths;
- representative Nav2 and Open-RMF workloads;
- fair comparison with Fast DDS, Cyclone DDS, and Zenoh;
- Docker/netem, simulation, multi-host, HIL, and physical validation;
- reproducible packaging, CI, release evidence, security and operations documentation.

`ros2_ws/src/rmw_fleetqox_cpp/capabilities.json` remains the authoritative capability/claim boundary. `production_ready=false` remains authoritative until the production qualification gates pass.

## Handoff protocol for AI-assisted execution

Every implementation agent must return a structured handoff containing:

1. commit SHA or patch/diff;
2. files changed;
3. root cause or design conclusion;
4. commands executed;
5. exact test results including failures/skips;
6. generated result artifact paths and key metrics;
7. capability/claim changes, if any;
8. known remaining risks;
9. explicit recommendation: `PASS`, `PARTIAL`, or `BLOCKED` for the current step.

Do not mark a phase complete from prose alone. Phase completion requires evidence satisfying the exit gate.

---

# Phase 0 — Stabilization Freeze and Reproduction Harness

## Goal

Stop feature expansion and make the two current release blockers reproducible and observable:

- intermittent subscriber heap corruption on lossy large typed samples;
- incomplete 32-KiB fleet-scale convergence.

## Step 0.1 — Freeze scope and establish baseline

### Work

- Record the exact main SHA, capability counts, test counts, and known negative claims.
- Run the clean Python/unit suite.
- Build the ROS 2 Jazzy packages from a clean tree.
- Build the canonical Docker/netem image.
- Run a minimal representative set of currently passing fragment, callback-teardown, and typed-message gates.
- Do not change algorithms in this step.

### Exit gate

A baseline manifest exists that records all commands, versions, pass/fail/skip counts, image identity, and current negative reliability/memory-safety claims.

## Step 0.2 — Build exact lossy inter-process sanitizer reproducer

### Work

Create a sanitizer-enabled Docker gate that exercises the original failure path as closely as possible:

publisher process -> FleetRMW UDP/router/netem -> fragmentation -> loss -> NACK/selective repair -> reassembly -> typed 32-KiB String take/deserialization -> subscriber lifecycle/finalization.

Requirements:

- ASan and UBSan instrument the actual loaded RMW library and probe binaries;
- separate publisher/subscriber processes;
- deterministic seed/profile controls;
- configurable iteration count and payload size;
- capture sanitizer stderr, process return codes, fragment/reassembly telemetry, and finalization state;
- runner must preserve a failing artifact bundle.

### Exit gate

Either:

- the existing heap corruption is reproduced with actionable sanitizer output; or
- a statistically meaningful repeated campaign is completed without reproduction, with enough telemetry to narrow the suspected path and justify the next diagnostic change.

## Step 0.3 — Localize and fix memory corruption

### Work

Use the reproducer to identify the root cause. Audit especially:

- typed String deserialize/take ownership;
- fragment reassembly buffer lifetime;
- move/copy of payload vectors and serialized buffers;
- callback and entity teardown concurrency;
- loan/allocation scratch interaction;
- late repair arrival after subscription shutdown;
- queue/registry synchronization.

Fix the root cause rather than suppressing the crash.

### Exit gate

- ASan clean;
- UBSan clean;
- repeated lossy inter-process 32-KiB campaign passes;
- callback teardown regressions remain green;
- typed/serialized/service/action regressions remain green;
- a permanent Docker regression gate is added.

---

# Phase 1 — Large-Sample Reliability Convergence

## Goal

Make 32-KiB reliable delivery converge at fleet scale without unbounded queues, retries, or repair amplification.

## Step 1.1 — Instrument complete frame lifecycle

### Work

Add structured per-frame timing/transition telemetry for:

- initial enqueue;
- first/last initial fragment send;
- sender completion marker;
- receiver first fragment;
- hole/trailing-index observation;
- NACK generation;
- selective-repair enqueue/send;
- assembly completion;
- application take;
- ACK generation/reception;
- writer-history retirement;
- terminal expiry/loss.

Correlate by publisher/source sequence/frame id/reader target.

### Exit gate

For every missing sample in the 16-robot 32-KiB frontier, the system can state exactly which lifecycle state failed to progress and why.

## Step 1.2 — Fix late-burst / horizon convergence

### Work

Use Step 1.1 evidence to correct the actual bottleneck. Likely areas include:

- completion-marker timing;
- trailing-fragment discovery;
- assembly TTL;
- writer-history horizon;
- NACK cadence/backoff;
- ACK baseline and out-of-order convergence;
- terminal loss timing;
- admission interaction during late repair bursts.

Do not tune pacing blindly. Every algorithm change must be tied to an observed failed state transition.

### Exit gate

A fixed 16-robot, 32-KiB, roaming-loss seed reaches complete delivery and ACK convergence with bounded state.

## Step 1.3 — Close the 8/16/32 multi-seed acceptance matrix

### Work

Run at least three fixed seeds per required profile for 8, 16, and 32 robots with exact 32-KiB payload provenance.

Record:

- delivery and ACK convergence;
- completion time;
- CPU/RSS;
- initial/repair queue high-water marks;
- assembly/history high-water marks;
- NACK/retransmission/selective-repair counts;
- deferrals/rejections;
- hidden retry detection;
- process health.

### Exit gate

All required rows pass with versioned bounds. Only then may the fleet-scale large-sample claim be changed to true.

---

# Phase 2 — Research Release Candidate Scope Closure

## Goal

Turn the broad research prototype into a defensible, reproducible Research RC without allowing optional semantics to delay the release indefinitely.

## Step 2.1 — Freeze RMW semantic scope

### Work

Review every remaining partial/unsupported RMW boundary and classify it as either:

- required for Research RC;
- deliberate non-goal for Research RC;
- deferred production qualification item.

Prioritize real gaps in remote events, message-lost/liveliness semantics, content-filter behavior, all-acknowledged semantics, dynamic-message concurrency, and allocation behavior.

Zero-copy does not become required merely because it is desirable.

### Exit gate

Every capability is either implemented with evidence or explicitly scoped with documentation and manifest alignment. No placeholder success path remains.

## Step 2.2 — Consolidate benchmark and evidence schema

### Work

- Freeze one benchmark manifest/schema.
- Freeze named profiles, payloads, offered loads, seeds, topology and image versions.
- Ensure failed/non-comparable rows remain visible.
- Ensure Fast DDS, Cyclone DDS, Zenoh and FleetRMW common-middle comparisons use aligned provenance.
- Add confidence intervals/effect sizes where comparative claims are made.

### Exit gate

One canonical report can be generated from a clean evidence bundle and every human claim maps to a machine-readable boundary.

## Step 2.3 — Clean-build CI and packaging

### Work

Add/complete CI that verifies at minimum:

- formatting/static checks appropriate to the repo;
- JSON/schema validity;
- Python/unit suite;
- ROS 2 Jazzy colcon build;
- selected deterministic C++/Docker gates where CI infrastructure permits;
- capability/document consistency checks.

Complete clean install/package instructions for the Research RC.

### Exit gate

A fresh clone can build, test, install, and generate the scoped research report using documented commands.

## Step 2.4 — Research RC freeze

### Work

- freeze version and manifests;
- regenerate evidence;
- run final release matrix;
- produce unified report;
- update README/status/roadmap;
- create release tag only after gates pass.

### Exit gate

Research RC is reproducible by someone other than the original author, with no unsupported production claim.

---

# Phase 3 — QUIC, PKI, and Security Hardening

## Goal

Move from scoped security probes to a production-oriented secure transport boundary.

## Step 3.1 — Public maintained QUIC backend only

Remove private or brittle runtime-hook dependencies from required production paths. Make the maintained public backend the default tested path.

### Exit gate

Required QUIC functionality works without private API dependence and passes regression/netem tests.

## Step 3.2 — Certificate and CA lifecycle

Implement and test:

- server certificate rotation;
- client certificate rotation;
- CA rotation;
- active-session expiry/revocation;
- rollback/fail-closed behavior;
- in-flight reliable-data behavior during credential change.

### Exit gate

Rotation/revocation is proven under active sessions with explicit fail-closed semantics.

## Step 3.3 — Session security and threat-model closure

Complete forward-secret asymmetric establishment, replay-window documentation, identity binding, and policy enforcement needed by the production threat model.

### Exit gate

Every production security claim maps to a fail-closed test and documented threat assumption.

## Step 3.4 — Gateway clustering and failure semantics

Implement/qualify:

- leader election/consensus;
- split-brain fencing;
- stale-writer rejection;
- rejoin/failback;
- regional recovery;
- observability/runbooks.

### Exit gate

Repeated failure campaigns prove bounded, deterministic recovery behavior.

## Step 3.5 — Long security/resource soak

Run credential churn, malformed input, multi-attacker/resource-pressure, process failure, and long-duration secure fragment/gateway workloads.

### Exit gate

CPU/RSS/state remain bounded, no memory-safety failures occur, and the security operations guide is complete enough for review.

---

# Phase 4 — Full Autonomy and Multi-Host Validation

## Goal

Demonstrate that FleetRMW/FleetQoX behaves correctly under representative autonomy workloads, not only communication probes.

## Step 4.1 — Sustained Nav2 workload

Run real planner/controller/costmap loops with dynamic obstacles, recovery behavior, realistic state/control/perception traffic, and task outcomes.

### Exit gate

Repeated sustained Nav2 campaigns meet defined task success, deadline, recovery, and communication-resource bounds.

## Step 4.2 — Representative Open-RMF workload

Exercise bidding, dispatch, fleet state, adapter churn, conflicts/doors/lifts where applicable, process/network failures, and multiple active tasks.

### Exit gate

Multi-host RMF workloads produce repeatable task-level success/delay/recovery evidence.

## Step 4.3 — Multi-host network testbed

Move key campaigns off single-host Docker topology and onto at least one real multi-host network/emulation environment.

### Exit gate

The main reliability, security and autonomy claims survive multi-host execution with recorded host/network provenance.

---

# Phase 5 — HIL and Physical Fleet Qualification

## Goal

Validate timing, Wi-Fi behavior, host effects, operations and recovery outside pure simulation/emulation.

## Step 5.1 — HIL

Connect representative robot computers/controllers/sensors or equivalent hardware to the middleware and network stack.

### Exit gate

No new correctness/memory/resource blockers appear under HIL, and timing/resource deltas are characterized.

## Step 5.2 — Small physical multi-robot campaign

Run a small real fleet under controlled tasks, impairment/failure scenarios, roaming or Wi-Fi changes where practical, and operator/task outcomes.

### Exit gate

Physical evidence is consistent with the scoped claims and discrepancies from simulation/emulation are documented.

---

# Phase 6 — Production-Oriented Release Qualification

## Goal

Convert the Research RC plus hardened transport/autonomy evidence into an operationally defensible production-oriented candidate.

## Step 6.1 — Long soak and failure campaign

Run hours-to-days campaigns covering:

- large-sample reliable traffic;
- service/action load;
- credential churn;
- gateway/process restart;
- partitions/recovery;
- multi-host autonomy workloads;
- CPU/RSS/queue/state trend monitoring.

### Exit gate

No unexplained crash, leak, unbounded state growth, or silent reliability failure remains.

## Step 6.2 — Operations and lifecycle

Complete:

- install;
- upgrade;
- rollback;
- configuration/version compatibility;
- PKI operations;
- monitoring/alerting;
- backup/recovery;
- incident/failure runbooks.

### Exit gate

A new operator can deploy, upgrade, roll back, rotate credentials, diagnose common failures and recover the system using documented procedures.

## Step 6.3 — Independent review and final claim audit

Perform security/code/benchmark claim review and reconcile every claim with evidence and capability manifest.

### Exit gate

`production_ready` may change only if all mandatory production gates pass and no known blocker contradicts the claim.

---

# Current execution checkpoint

As of the plan creation checkpoint, execution starts at **Phase 0, Step 0.1**. Feature expansion should remain frozen until Phase 0 and Phase 1 are closed.

## Replanning rule

After every step, compare the handoff evidence to the current diagnosis:

- if the exit gate passes, advance;
- if partially passes, revise the next step around the newly isolated blocker;
- if the evidence falsifies the current architecture assumption, update this plan before coding further;
- never flip a broad capability claim from a single deterministic probe or stochastic seed.

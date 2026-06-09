# ROS 2 Profile Objective Selector V1

## Purpose

The repeated packet-format/RMW experiments showed that the best ROS 2
communication policy is not a fixed DDS/RMW configuration.  It depends on:

- network profile: Wi-Fi, WAN, roaming, or later LAN/Internet profiles;
- packet representation: legacy `event_json` versus
  `fleetrmw.data_frame.v1`;
- concrete RMW/data plane: Fast DDS, CycloneDDS, Zenoh RMW today, and future
  FleetRMW planes later;
- active QoS/QoE objective: shared-autonomy safety/utility is not the same
  decision problem as teleoperation latency.

`fleetqox.transport_selector` is the first explicit control-plane component for
this decision.  It turns repeated-run evidence into a reproducible
profile/objective-aware transport choice.

## Implementation

Implemented files:

- `fleetqox/transport_selector.py`
- `scripts/select_ros2_transport.py`
- `tests/test_transport_selector.py`

The selector:

- loads repeated-run summary JSON files produced by
  `scripts.run_ros2_docker_live_bridge`;
- ranks each `packet_format/rmw` candidate per profile;
- normalizes metrics over the candidate set so heterogeneous units can be
  compared without hardcoded absolute scaling;
- supports mixed max/min objectives;
- applies hard eligibility constraints such as minimum control delivery;
- relaxes constraints only when every candidate violates at least one hard
  constraint, and records that relaxation explicitly;
- emits JSON and Markdown artifacts with rankings, selected policy, raw score,
  normalized metric contributions, and constraint violations.

The runtime binding path:

- serializes the selected policy as `fleetrmw.transport_binding.v1`;
- provides `ProfileObservation`, `classify_network_profile`, and
  `TransportBindingManager` for rule-based online profile inference from link
  capacity, RTT, jitter, and loss;
- adds `AdaptiveTransportBindingEstimator`, which smooths link telemetry,
  scores measured profile prototypes, and applies hysteresis/min-dwell before
  switching bindings;
- lets `Ros2SidecarAdapter.build_batch` attach the binding to a ROS 2 shim
  batch;
- lets `Ros2LiveSampleBuffer` refresh the binding and adaptive profile estimate
  on each live bridge batch;
- lets a live bridge config carry multiple objective selector summaries and an
  `objective_schedule`, so the active QoS/QoE objective can change during one
  bridge session;
- lets `SidecarRuntime.process_batch` select per-batch `packet_format` from
  the binding and log the binding plus estimator state on every sidecar
  decision/packet event;
- lets the Docker transition reporter attach `fleetrmw.per_robot_qos.v1` and
  `fleetrmw.per_robot_qos_budget.v1` summaries to multi-robot transition runs,
  so objective selection can be evaluated against robot-level SLOs instead of
  only aggregate fleet means;
- exposes `fleetqox_semantic_contract_budgeted`, a per-robot virtual-queue
  wrapper that turns budget violations into future admission pressure while
  reusing the semantic-contract data-plane logic;
- keeps the RMW field explicit for future process-level or RMW-level binding,
  even though a running ROS 2 process still cannot switch RMW implementation on
  a per-batch basis.

## Objective Presets

### `balanced_safety_utility`

Shared-autonomy objective.  It preserves semantic utility and control delivery
while keeping starvation, deadline miss, loss, and p95 latency in the objective
vector.

Hard constraints:

- `control_delivery_ratio_mean >= 0.90`
- `control_non_delivery_events_mean <= 0`

### `teleop_latency`

Latency-first objective for remote supervision or teleoperation.  It gives most
weight to p95/p99 latency while still enforcing control delivery.

Hard constraints:

- `control_delivery_ratio_mean >= 0.90`
- `control_non_delivery_events_mean <= 0`

### Other presets

- `autonomy_safety`: stronger control-delivery and starvation bias.
- `throughput_utility`: telemetry/semantic-throughput bias.

## Reproduction

Balanced selector:

```bash
python3 -m scripts.select_ros2_transport \
  --summary results_ros2_live_bridge/ros2_live_bridge_t3_repeated_packet_wifi_3seed_v1_summary.json \
  --summary results_ros2_live_bridge/ros2_live_bridge_t3_repeated_packet_wan_3seed_v1_summary.json \
  --summary results_ros2_live_bridge/ros2_live_bridge_t3_repeated_packet_roaming_3seed_v1_summary.json \
  --objective balanced_safety_utility \
  --summary-json results_ros2_live_bridge/profile_objective_selector_balanced_v1_summary.json \
  --markdown results_ros2_live_bridge/profile_objective_selector_balanced_v1_report.md
```

Teleoperation-latency selector:

```bash
python3 -m scripts.select_ros2_transport \
  --summary results_ros2_live_bridge/ros2_live_bridge_t3_repeated_packet_wifi_3seed_v1_summary.json \
  --summary results_ros2_live_bridge/ros2_live_bridge_t3_repeated_packet_wan_3seed_v1_summary.json \
  --summary results_ros2_live_bridge/ros2_live_bridge_t3_repeated_packet_roaming_3seed_v1_summary.json \
  --objective teleop_latency \
  --summary-json results_ros2_live_bridge/profile_objective_selector_teleop_v1_summary.json \
  --markdown results_ros2_live_bridge/profile_objective_selector_teleop_v1_report.md
```

Autonomy-safety selector:

```bash
python3 -m scripts.select_ros2_transport \
  --summary results_ros2_live_bridge/ros2_live_bridge_t3_repeated_packet_wifi_3seed_v1_summary.json \
  --summary results_ros2_live_bridge/ros2_live_bridge_t3_repeated_packet_wan_3seed_v1_summary.json \
  --summary results_ros2_live_bridge/ros2_live_bridge_t3_repeated_packet_roaming_3seed_v1_summary.json \
  --objective autonomy_safety \
  --summary-json results_ros2_live_bridge/profile_objective_selector_autonomy_v1_summary.json \
  --markdown results_ros2_live_bridge/profile_objective_selector_autonomy_v1_report.md
```

Runtime binding smoke:

```bash
python3 -m scripts.run_ros2_sidecar_adapter \
  --scenario ros2_shim_transport_binding_runtime_smoke_v1 \
  --decision-log results_ros2_shim/transport_binding_runtime_smoke_decisions.jsonl \
  --transport-binding-summary results_ros2_live_bridge/profile_objective_selector_balanced_v1_summary.json \
  --transport-profile wifi \
  --json
```

Auto-profile binding smoke:

```bash
python3 -m scripts.run_ros2_sidecar_adapter \
  --scenario ros2_shim_transport_binding_auto_profile_smoke_v1 \
  --decision-log results_ros2_shim/transport_binding_auto_profile_smoke_decisions.jsonl \
  --transport-binding-summary results_ros2_live_bridge/profile_objective_selector_balanced_v1_summary.json \
  --auto-transport-profile \
  --json
```

Adaptive-profile binding smoke:

```bash
python3 -m scripts.run_ros2_sidecar_adapter \
  --scenario ros2_shim_transport_binding_adaptive_profile_smoke_v1 \
  --decision-log results_ros2_shim/transport_binding_adaptive_profile_smoke_decisions.jsonl \
  --transport-binding-summary results_ros2_live_bridge/profile_objective_selector_balanced_v1_summary.json \
  --adaptive-transport-profile \
  --json
```

Live continuous binding smoke:

```bash
python3 -m scripts.smoke_ros2_live_bridge_binding \
  --selector-summary results_ros2_live_bridge/profile_objective_selector_balanced_v1_summary.json \
  --mode adaptive \
  --process-runtime \
  --output results_ros2_live_bridge/live_bridge_adaptive_binding_runtime_smoke_v1.json \
  --json
```

## Results

### Balanced Safety/Utility

| Profile | Selected policy | Score | Utility | Ctrl delivery | Deadline miss | Loss | p95 ms |
| --- | --- | --- | --- | --- | --- | --- | --- |
| Wi-Fi | `data_frame/rmw_zenoh_cpp` | `1.0000` | `458.18` | `1.0000` | `0.0000` | `0.0173` | `38.27` |
| WAN | `event_json/rmw_zenoh_cpp` | `0.8259` | `342.49` | `1.0000` | `0.0425` | `0.0365` | `111.19` |
| Roaming | `event_json/rmw_zenoh_cpp` | `0.8498` | `248.51` | `0.9667` | `0.2365` | `0.0645` | `162.60` |

### Teleoperation Latency

| Profile | Selected policy | Score | Utility | Ctrl delivery | Deadline miss | Loss | p95 ms |
| --- | --- | --- | --- | --- | --- | --- | --- |
| Wi-Fi | `data_frame/rmw_zenoh_cpp` | `1.0000` | `458.18` | `1.0000` | `0.0000` | `0.0173` | `38.27` |
| WAN | `event_json/rmw_zenoh_cpp` | `0.9567` | `342.49` | `1.0000` | `0.0425` | `0.0365` | `111.19` |
| Roaming | `event_json/rmw_cyclonedds_cpp` | `0.8557` | `242.17` | `1.0000` | `0.2750` | `0.0578` | `169.44` |

The important result is not that one RMW always wins.  The important result is
that the selected operating point changes when the objective changes.  In the
roaming profile, `event_json/rmw_zenoh_cpp` is best for the balanced objective,
while `event_json/rmw_cyclonedds_cpp` narrowly wins the latency-first objective
because it combines feasible control delivery with acceptable latency.  The
absolute lowest p95 candidate, `data_frame/rmw_zenoh_cpp`, remains eligible but
does not dominate once control delivery and p99/deadline terms are included.

## Research Meaning

This moves the project beyond a fixed engineering recipe such as "use Zenoh" or
"replace JSON with a binary frame".  The current evidence supports a stronger
FleetRMW claim:

Fleet communication should expose a profile-aware and objective-aware
transport-selection control plane.  The control plane chooses the data-plane
binding from measured QoS/QoE/QoT evidence rather than treating RMW selection,
packet format, and QoS policy as static deployment parameters.

## Current Limitation

The selector can now export a runtime `TransportBinding`, the shim/sidecar path
can consume that binding for per-batch packet-format selection, the live bridge
refreshes an adaptive binding provider for each batch, and Docker T3 now
compares adaptive binding against static Wi-Fi/WAN/roaming baselines under the
same non-stationary ROS 2 workload. The adaptive-vs-static transition matrix
has been repeated over three short seeds and now reports switch latency,
missing switches, and flapping. The live bridge also has a one-seed
dynamic-objective smoke and a three-seed dynamic-objective matrix where the
active objective changes during the same session. The first two-robot,
three-seed dynamic-objective matrix now shows robot namespace coverage in
sidecar decisions, receiver packets, and egress publications. The two-robot
local-services matrix now also shows robot coverage in local lease decisions,
projection gate decisions, and monitor observations. The per-robot budget
matrix then shows the remaining algorithmic gap: RX/control/deadline Jain
fairness can be high while the worst robot still misses an absolute control
delivery SLO. The remaining limitations are fleet scale, objective diversity,
dwell-window length, budget enforcement, and RMW boundary depth: the
multi-robot evidence is still short, two-robot, and `rmw_zenoh_cpp`-only. A
running ROS 2 process still cannot switch RMW implementation per batch.

## Next Step

The next implementation step is scale-oriented objective-adaptive ROS-backed
continuous binding:

- extend the repeated Docker T3 transition matrix to longer dwell windows and
  more than two robots with per-robot budget enforcement;
- add more objective schedules and more abrupt/overlapping objective changes;
- quantify QoE under transition moments: switch latency, flapping rate,
  p95/p99 latency, loss, control delivery, non-delivery, and semantic utility;
- promote per-robot budget violations into the objective/admission loop instead
  of treating them as a post-run report, starting with
  `fleetqox_semantic_contract_budgeted`;
- RMW roadmap later moves the same decision into `rmw_fleetqox_cpp`.

## Verification

```bash
python3 -m unittest tests.test_transport_selector
# Ran 10 tests - OK

python3 -m unittest discover -s tests
# Ran 227 tests - OK
```

Runtime smoke result:

- `accepted=13`
- `decisions=13`
- `emitted=7`
- `packet_format=data_frame`
- decision log rows with `transport_binding`: `13/13`

Auto-profile smoke result:

- inferred profile: `roaming`
- selected binding: `event_json/rmw_zenoh_cpp`
- `accepted=13`
- `decisions=13`
- `emitted=7`
- `packet_format=event_json`

Adaptive-profile smoke result:

- inferred profile: `roaming`
- selected binding: `event_json/rmw_zenoh_cpp`
- `accepted=13`
- `decisions=13`
- `emitted=7`
- `packet_format=event_json`

Live continuous binding smoke result:

- tick `0`: profile `wifi`, policy `data_frame/rmw_zenoh_cpp`,
  packet format `data_frame`
- tick `1`: profile `roaming`, policy `event_json/rmw_zenoh_cpp`,
  packet format `event_json`
- both ticks include `transport_binding_estimate` with profile scores,
  confidence, margin, and dwell state
- sidecar runtime decision log rows with `transport_binding_estimate`: `2/2`

Docker T3 profile-transition result:

- netem transitions applied: `3/3` (`wifi`, `wan`, `roaming`)
- decision log rows with `transport_binding`: `87/87`
- decision log rows with `transport_binding_estimate`: `87/87`
- binding switches: tick `14` Wi-Fi -> WAN, tick `28` WAN -> roaming
- packet formats observed: `data_frame`, `event_json`

Docker T3 adaptive-vs-static transition matrix result:

- runs completed: `4/4`;
- adaptive binding switches: tick `16` Wi-Fi -> WAN, tick `33` WAN -> roaming;
- adaptive control delivery: `0.9787`;
- adaptive semantic utility: `630.45`;
- best static loss: `static_wifi` at `0.0440`;
- best static deadline miss ratio: `static_wan` at `0.2093`;
- best static p95 latency: `static_roaming` at `115.18 ms`;
- result interpretation: adaptive wins control delivery and delivered utility
  in this smoke, but repeated seeds are required before claiming statistical
  dominance across latency/loss/deadline metrics.

Docker T3 adaptive-vs-static transition matrix 3-seed result:

- runs completed: `12/12` over seeds `7,13,29`;
- adaptive matched `2.0` scheduled switches/run, missing switches `0.0`, mean
  absolute switch latency `0.1805 s`, and flapping `0.0`;
- adaptive is best by mean control delivery (`0.9654`), deadline miss ratio
  (`0.1991`), and p95 latency (`117.83 ms`);
- static roaming remains slightly better on mean loss (`0.0600`), and static
  WAN remains better on mean semantic utility (`530.0`);
- result interpretation: adaptive binding is now a repeated ROS-backed
  objective-specific control-plane operating point, but not a universal winner
  across every raw metric.

Docker T3 dynamic-objective binding smoke result:

- objective schedule: `balanced_safety_utility@0`,
  `autonomy_safety@2`, `balanced_safety_utility@4`;
- runs completed: `1/1`;
- decision rows with transport binding and estimator metadata: `135/135`;
- profile switches: `2`;
- objective switches: `2`;
- policy switches: `2`;
- observed packet formats: `data_frame`, `event_json`;
- at `2.1000 s`, the WAN/autonomy segment switches to
  `data_frame/rmw_cyclonedds_cpp`;
- at `4.0008 s`, the objective returns to balanced and switches to
  `event_json/rmw_zenoh_cpp`;
- result interpretation: packet-format binding can already change inside the
  sidecar path; RMW changes remain target metadata until the control plane is
  moved into a true RMW boundary.

Docker T3 dynamic-objective binding 3-seed result:

- runs completed: `3/3` over seeds `7,13,29`;
- mean rx `97.33`, loss `0.0642`, control delivery `0.9612`, deadline miss
  `0.2400`, p95 latency `115.50 ms`, and delivered utility `518.28`;
- matched profile switches/run: `2.0`, mean absolute profile switch latency
  `0.1644 s`, flapping `0.0`;
- matched objective switches/run: `2.0`, mean absolute objective switch
  latency `0.0468 s`, objective flapping `0.0`;
- policy switches/run: `2.0`;
- observed profiles: `wifi`, `wan`, `roaming`;
- observed objectives: `balanced_safety_utility`, `autonomy_safety`;
- observed packet formats: `data_frame`, `event_json`.

Docker T3 dynamic-objective binding two-robot 3-seed result:

- runs completed: `3/3` over seeds `7,13,29`;
- configured robot count: `2`;
- decision robots observed/run: `2.0`;
- received robots observed/run: `2.0`;
- egress robots observed/run: `2.0`;
- observed robots: `robot_0000`, `robot_0001`;
- mean rx `159.33`, loss `0.0637`, control delivery `0.9432`, deadline miss
  `0.2472`, p95 latency `121.69 ms`, and delivered utility `844.71`;
- matched profile switches/run: `2.0`, matched objective switches/run: `2.0`;
- result interpretation: objective/profile binding survives a multi-robot ROS
  namespace workload at bridge/sidecar/receiver/egress level.

Docker T3 dynamic-objective binding two-robot local-services 3-seed result:

- runs completed: `3/3` over seeds `7,13,29`;
- configured robot count: `2`;
- decision, receiver, egress, lease, projection gate, and monitor robot
  coverage all measured `2.0` robots/run;
- observed robots: `robot_0000`, `robot_0001`;
- mean rx `148.67`, loss `0.0542`, control delivery `0.9524`, deadline miss
  `0.2661`, p95 latency `131.93 ms`, and delivered utility `790.50`;
- matched profile switches/run: `2.0`, matched objective switches/run: `2.0`;
- result interpretation: the two-robot claim is now end-to-end for the short
  local-control path, including local lease and projection quality consumers.
  The remaining gap is scaling this to larger fleets and enforcing explicit
  per-robot fairness/deadline constraints.

Docker T3 dynamic-objective binding two-robot per-robot budget 3-seed result:

- runs completed: `3/3` over seeds `7,13,29`;
- configured robot count: `2`;
- robot budget pass ratio: `0.3333`;
- mean RX Jain fairness: `1.0000`;
- mean control-delivery Jain fairness: `0.9984`;
- mean deadline-success Jain fairness: `0.9997`;
- mean minimum per-robot control delivery: `0.8950`;
- mean maximum per-robot deadline miss: `0.3036`;
- mean p95 latency spread between robots: `7.09 ms`;
- seeds `13` and `29` fail because the worst robot's control delivery is
  `0.8846` and `0.8718`, below the `0.90` SLO;
- result interpretation: aggregate fleet control delivery is not a sufficient
  objective for fleet middleware. The selector needs a budget-aware admission
  term that can protect the worst robot, not just improve the mean robot.

Per-robot budget-aware controller smoke result:

- scenario: two robots contend for one control packet slot per tick;
- predictive baseline delivery: `robot_0000=1.0000`, `robot_0001=0.0000`,
  Jain `0.5000`;
- budget-aware wrapper delivery: `robot_0000=0.5000`, `robot_0001=0.5000`,
  Jain `1.0000`;
- artifact: `results_robot_budget/robot_budget_controller_smoke_report.md`;
- result interpretation: virtual queues convert robot SLO debt into future
  scheduling pressure. The next evidence step is ROS 2 Docker validation under
  the live profile/objective transition workload.

ROS 2 Docker budgeted-policy comparison:

- baseline budget pass ratio: `0.3333`;
- budgeted pass ratio: `0.3333`;
- budgeted-floor pass ratio: `0.3333`;
- tail-risk pass ratio: `1.0000`;
- mean minimum per-robot control delivery: `0.8950 -> 0.9222` with tail-risk
  pressure;
- aggregate control delivery: `0.9328 -> 0.9422` with tail-risk pressure;
- p95 latency: `128.42 ms -> 132.73 ms` with tail-risk pressure;
- utility: `818.53 -> 767.96` with tail-risk pressure;
- artifact: `results_ros2_live_bridge/robot_budget_policy_compare_report.md`;
- result interpretation: the first budgeted wrapper is wired into the ROS 2
  sidecar path and moves deadline/tail-latency in the right direction but does
  not enforce the per-robot budget. The tail-risk version adds
  network-tail-risk pressure and pressure-aware semantic shaping, raising budget
  pass to `1.0000` for the short two-robot T3 matrix. The remaining gap is
  receiver/local-controller feedback and QoE-aware shaping to reduce p95 spread
  without losing the SLO win.

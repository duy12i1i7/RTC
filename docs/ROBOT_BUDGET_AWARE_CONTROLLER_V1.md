# Robot Budget-Aware Controller V1

## Purpose

The two-robot ROS 2 per-robot budget run exposed a real control-plane gap:
aggregate control delivery can remain above `0.90` while one robot falls below
the per-robot SLO.  Jain fairness was also near `1.0`, which means relative
fairness alone is not a sufficient safety/QoE objective.

This milestone adds the first budget-enforcing mechanism:
`RobotBudgetAwareAdmissionController`.  It wraps an existing admission policy
and keeps per-robot virtual queues for:

- control-delivery shortfall;
- predicted deadline-risk excess.

The controller converts those queues into future scheduling pressure.  A robot
that misses its SLO gets more task value on its critical flows in subsequent
batches.  The base policy still chooses packet transforms and byte admission,
so this mechanism can wrap predictive, Lagrangian, semantic-contract, or future
RMW-native policies.

## Implementation

Implemented files:

- `fleetqox/control_plane.py`
  - Adds `RobotBudgetConfig`.
  - Adds `_RobotBudgetState`.
  - Adds `RobotBudgetAwareAdmissionController`.
  - Adds network-tail-risk pressure, control-service floor rescue, and
    pressure-aware semantic shaping for non-critical robot traffic.
- `fleetqox/sidecar_runtime.py`
  - Adds sidecar policy name `fleetqox_semantic_contract_budgeted`.
  - Adds a `robot_feedback` TCP message type so observed receiver/controller
    outcomes can update the active budget controller.
  - Adds batch-level volatility-probe quota and low-cost semantic recovery
    probes so state/perception QoE can be restored without opening linear
    per-robot bursts during unstable Wi-Fi/WAN/roaming epochs.
- `scripts/report_robot_budget_controller.py`
  - Generates a deterministic two-robot control contention smoke report.
- `tests/test_control_plane.py`
  - Verifies that a robot with prior control deficit is promoted in the next
    scheduling round.
  - Verifies that WAN/roaming tail risk can create robot pressure even when the
    base policy already sends control intent, and that the wrapper then shapes
    non-critical traffic for that robot.

## Algorithm

For each robot `r`, the controller maintains virtual queues:

```text
Q_control[r]  <- decay * Q_control[r]  + lr_control  * max(0, target_delivery - observed_delivery)
Q_deadline[r] <- decay * Q_deadline[r] + lr_deadline * max(0, observed_deadline_risk - target_risk)
pressure[r]  <- clamp(Q_control[r] + Q_deadline[r], 0, max_pressure)
```

On the next batch, `pressure[r]` is injected into critical flows for that robot:

- increase `causal_task_gain`;
- reduce effective redundancy;
- raise task criticality/collision/coordination context within `[0,1]`;
- annotate the decision reason with the active robot-budget queues.

The live ROS 2 result showed that this predicted-decision loop alone is not
enough: the base semantic contract can send every control intent while the
receiver/local-controller path still misses a per-robot budget. The controller
therefore now also adds a transport-derived tail-risk term:

```text
tail_ms          <- RTT/2 + jitter_tail + loss_tail + serialization
network_risk     <- sigmoid((tail_ms - source_deadline_slack) / temperature)
Q_deadline[r]    <- Q_deadline[r] + lr_deadline * max(0, max(predicted_risk, network_risk) - target_risk)
```

When pressure is active, the wrapper applies two actions before the final
decision list is emitted:

- control-service floor rescue: if a control/safety flow for the pressured
  robot was not admitted, reclaim non-control capacity and send the smallest
  feasible control representation;
- pressure-aware semantic shaping: compact or degrade the pressured robot's
  state/perception/Human-QoE/debug/bulk flows so control service can survive
  WAN/roaming tails.

The controller also exposes an observed-feedback update surface:

```json
{
  "type": "robot_feedback",
  "feedback": [
    {
      "robot_id": "robot_0000",
      "control_delivery_ratio": 0.91,
      "deadline_miss_ratio": 0.32
    }
  ]
}
```

When the active sidecar policy is `fleetqox_semantic_contract_budgeted`, this
message updates the same robot virtual queues used by scheduler-side pressure.
The sidecar TCP server accepts concurrent bridge and feedback clients, so the
ROS 2 egress bridge can send feedback while the live bridge keeps its batch
connection open.

The first live producer is the egress bridge. With `--egress-feedback`, it
aggregates receiver-side packet outcomes into per-robot windows and sends
control/deadline ratios back to the sidecar. A one-seed Docker smoke
(`ros2_live_bridge_t3_dynamic_objective_transition_2robot_feedback_core_window_smoke_v1`)
confirmed the wiring with `28` feedback records applied and `0` feedback
connection failures. That smoke is not a performance win yet: budget pass
remained `0.0`, aggregate control delivery was `0.9024`, and p95 latency was
`293.18 ms`.

The feedback law now applies sample-count-aware damping before it updates the
robot virtual queues.  Egress feedback windows include control/deadline sample
counts, the controller scales the external feedback learning rate against a
reference window, caps observed deadline risk, and ignores perception-only
deadline misses in the core deadline feedback signal.  The follow-up smoke
(`ros2_live_bridge_t3_dynamic_objective_transition_2robot_feedback_damped_smoke_v1`)
reduced overreaction in the decision log: `pressure_shaping` fell from `74` to
`42`, `drop` from `32` to `22`, and `defer` from `38` to `18`.  Aggregate
control delivery improved from `0.9024` to `0.9412`, and the worst-robot control
delivery improved from `0.8537` to `0.9118`.

This is still not the benchmark policy.  The damped smoke keeps budget pass at
`0.0`, raises deadline miss from `0.5723` to `0.6405`, and raises p95 latency
from `293.18 ms` to `399.36 ms`.  The conclusion is that feedback transport is
real and no longer catastrophically overreacts, but the feedback objective now
needs explicit QoE/latency-aware pressure shaping before it can replace the
tail-risk benchmark.

The next iteration adds that QoE feedback boundary.  Egress windows now report
`mean_latency_ms`, `tail_latency_ms`, `mean_deadline_ms`,
`latency_deadline_ratio`, and `latency_sample_count`.  The controller converts
tail-latency excess into a separate `latency_deficit`: service pressure for
critical-flow gain still comes only from control/deadline debt, while total
pressure for non-critical shaping includes latency debt.  In the one-seed smoke
(`ros2_live_bridge_t3_dynamic_objective_transition_2robot_feedback_qoe_smoke_v1`)
deadline miss improved to `0.5097`, p95 improved versus the damped feedback run
to `302.53 ms`, and utility reached `851.69`.  It is still not benchmark-ready:
budget pass remains `0.0`, worst-robot control delivery is only `0.8718`, and
p95 is still worse than the original core-window feedback smoke.  The result
validates the latency feedback path and exposes the next control problem:
QoE/tail pressure must be lexicographic with the control SLO, not merely another
additive pressure term.

The control-first follow-up gates `latency_pressure` by control-delivery
headroom.  Latency debt is still stored, but it contributes to total shaping
pressure only when the robot's control-delivery EWMA is above the configured
control SLO by a small margin.  The smoke
(`ros2_live_bridge_t3_dynamic_objective_transition_2robot_feedback_control_first_qoe_smoke_v1`)
recovers the control side of the budget: aggregate control delivery improves to
`0.9136`, worst-robot control delivery improves to `0.9024`, RX rises to `163`,
loss falls to `0.0686`, and delivered utility rises to `906.17`.  Budget pass is
still `0.0` because worst-robot deadline miss rises to `0.7125`.  The current
failure has therefore moved from "QoE feedback can break control SLO" to
"control-first feedback still needs a deadline-first inner loop."

That inner loop is exposed as an experimental sidecar policy,
`fleetqox_semantic_contract_budgeted_deadline_first`, rather than changing the
stable `fleetqox_semantic_contract_budgeted` default.  It adds deadline debt as
extra non-critical shaping pressure, while leaving critical service pressure
unchanged.  In
`ros2_live_bridge_t3_dynamic_objective_transition_2robot_feedback_deadline_first_policy_smoke_v1`,
aggregate control delivery reaches `0.9846`, worst-robot control delivery
reaches `0.9697`, RX is `144`, loss is `0.0649`, and utility is `797.30`.  It
still fails budget pass because worst-robot deadline miss is `0.5694`, and p95
latency is `302.45 ms`.  The result defines a useful trade-off branch, not a new
best benchmark: the tail-risk three-seed path remains the hard-SLO reference.

The next closed-loop step adds robot-side and projection-side producers without
changing the stable budgeted policy.  The local controller lease adapter now
reports command-delivery outcomes, and the projection quality gate reports
publish/drop QoE risk for qualified odometry, scan, and state projections.  In
`ros2_live_bridge_t3_dynamic_objective_transition_2robot_feedback_multisource_smoke_v1`,
the sidecar receives egress, local-controller, and quality-gate feedback in the
same ROS 2 live bridge run.  RX rises to `166`, utility reaches `912.44`, and
feedback delivery itself works (`24` egress, `60` local-controller, and `93`
quality-gate records applied), but budget pass remains `0.0`: worst-robot
control delivery falls to `0.8049`, worst-robot deadline miss is `0.6000`, and
p95 latency is `320.51 ms`.  This validates the multi-source feedback boundary
while showing that the next research problem is feedback arbitration and credit
assignment, not simply adding more feedback signals.

The source-aware arbitration follow-up changes the feedback semantics rather
than adding another scalar gain.  Feedback records are now partial updates:
egress feedback owns receiver-visible delivery/latency evidence and
state/safety/coordination deadline evidence, local-controller feedback credits
or debits command application with a separate robot-side responsibility weight,
and projection-quality feedback updates only QoE/latency debt.  The first
conservative pass was a negative result
(`feedback_multisource_arbitrated_smoke_v1`): RX fell to `97`, control delivery
to `0.8491`, and utility to `535.84`.  The calibrated v2 pass recovered the hard
control side: `feedback_multisource_arbitrated_v2_smoke_v1` reached
worst-robot control delivery `0.9722`, aggregate control delivery `0.9722`, loss
`0.0608`, p95 `299.45 ms`, and utility `786.54`, but still failed budget pass
because worst-robot deadline miss rose to `0.6857`.

Combining source-aware arbitration v2 with the experimental deadline-first
policy gives the strongest multi-source QoE branch so far:
`feedback_multisource_arbitrated_v2_deadlinefirst_smoke_v1` reaches RX `175`,
utility `953.89`, aggregate control delivery `0.9500`, and p95 `284.66 ms`.
It still fails the hard budget because worst-robot control delivery is exactly
`0.9000` and worst-robot deadline miss is `0.6517`.  A stronger deadline-debt
firewall and a control horizon-lift mechanism were also tested and left disabled
by default: the firewall improved control and loss but worsened worst-robot
deadline miss and p95, while horizon lift reduced RX to `90` and still failed
budget pass.  Tail-risk remains the hard-SLO reference.

The next attribution step pushes egress feedback below the robot aggregate into
`flow_class:wire_mode` deadline buckets.  The egress bridge now reports
`deadline_miss_by_transform`, and the budget wrapper stores per-transform
deadline debt such as `control:control_intent`.  A new experimental policy,
`fleetqox_semantic_contract_budgeted_action_deadline_first`, uses that debt as
the guard signal for future targeted transform changes.  In
`feedback_action_deadline_first_v2_smoke_v1`, the attribution path raises RX to
`178`, utility to `1010.71`, aggregate control delivery to `0.9885`, and loss
falls to `0.0481`; budget pass is still `0.0` because worst-robot deadline miss
is `0.6629` and p95 is `293.55 ms`.  Lowering the action threshold enough to
force horizon lifts is a negative result (`feedback_action_deadline_first_v3`):
RX falls to `145` and p95 rises to `378.50 ms`.  The useful contribution is the
action-level credit assignment; the remaining gap is preventing the attributed
miss before it becomes receiver-visible tail latency.

The control-lease deadline ownership fix resolves a hidden measurement error in
that branch.  `send_intent` and `send_supervisory_intent` re-enter ROS 2 as
`/fleetrmw/<robot>/control_lease`, and the robot-side lease starts validity at
local receive time.  Therefore WAN/egress latency of the lease packet is not the
same SLO as local command freshness.  The analyzer and egress feedback window
now keep control-lease delivery and latency evidence but do not turn a late
control lease packet into egress deadline debt; local-controller feedback owns
control application deadline debt and carries the lease `action`/`wire_mode`.
Reanalyzing the existing `feedback_multisource_arbitrated_v2_deadlinefirst`
run with this ownership rule changes it from a hard-budget failure to a pass:
RX `175`, aggregate control delivery `0.9500`, p95 `284.66 ms`, utility
`953.89`, minimum per-robot control delivery `0.9000`, worst-robot deadline
miss `0.3483`, RX Jain `0.9997`, control Jain `0.9972`, and deadline-success
Jain `0.9946`.

A fresh ROS 2 Docker smoke with the corrected live path,
`ros2_live_bridge_t3_dynamic_objective_transition_2robot_feedback_deadline_ownership_smoke_v1`,
also passes the hard budget.  It applies egress, local-controller, and
projection-quality feedback in one run (`146` records applied, `1` failed
flush), observes both robot IDs through decisions/receiver/egress/lease/gate/
monitor logs, and records RX `134`, aggregate control delivery `0.9394`,
aggregate deadline miss `0.2164`, p95 `262.47 ms`, minimum per-robot control
delivery `0.9091`, worst-robot deadline miss `0.2319`, RX Jain `0.9991`,
control Jain `0.9990`, and deadline-success Jain `0.9996`.

The repeated live path is now hardened with two additional mechanisms:
redundant control-lease datagrams with `event_id` de-duplication, and a
transport-volatility guard that defers non-control packets while the
transport-binding estimate is low-confidence or newly changed.  The repeated
3-seed run
`ros2_live_bridge_t3_dynamic_objective_transition_2robot_feedback_deadline_ownership_volatility_guard_3seed_v1`
passes all seeds: budget pass `1.0000`, mean RX `70.3333`, loss `0.0128`,
control delivery `0.9872`, deadline miss `0.0000`, p95 `241.78 ms`, minimum
per-robot control delivery `0.9872`, worst-robot deadline miss `0.0000`, RX
Jain `0.99995`, control Jain `1.0000`, and deadline-success Jain `1.0000`.
This is a hard-SLO safe mode, not a QoE-optimal mode: quality-gate robot
coverage is `0.0000`, so state/perception projection is intentionally
sacrificed when binding confidence is not high enough.

The follow-up QoE recovery path adds a bounded low-cost probe inside that same
transport-volatility guard.  A non-control packet can bypass the guard only if
it is already a `semantic_delta` or `degraded` representation, belongs to a
managed QoE class, has enough predicted slack, and the binding estimator has
enough confidence, margin, and dwell.  The probe is rate-limited per
`robot_id:flow_class`, so it restores consumer-visible projection coverage
without reopening native telemetry during unstable profile transitions.
`semantic_delta` odometry is also classified as `semantic_projection` at the
qualified projection boundary, rather than as a rejected degraded projection.

In the current stable 3-seed run
`ros2_live_bridge_t3_dynamic_objective_transition_2robot_feedback_deadline_ownership_qoe_stable_probe_3seed_v1`,
the hard budget still passes on all seeds.  Mean RX is `77.6667`, loss
`0.0127`, control delivery `0.9870`, deadline miss `0.0171`, p95 `293.40 ms`,
semantic utility `564.22`, worst-robot deadline miss `0.0264`, and
quality-gate robot coverage is restored to `2.0000`.  This is deliberately
conservative: it recovers one accepted downsampled scan projection per robot
per seed, while a more aggressive probe admits more state/perception samples at
the cost of higher non-control deadline miss.

This is intentionally a wrapper.  It does not duplicate semantic-contract
candidate generation, Lagrangian risk scoring, or packet-format decisions.
Those remain owned by the base policy.

## Reproduction

```bash
python3 -m scripts.report_robot_budget_controller \
  --ticks 12 \
  --summary-json results_robot_budget/robot_budget_controller_smoke_summary.json \
  --markdown results_robot_budget/robot_budget_controller_smoke_report.md
```

## Result

The smoke keeps two robots contending for one control packet slot per tick.
The baseline has no per-robot SLO memory, so stable tie-breaking starves
`robot_0001`.  The budget-aware wrapper accumulates SLO debt for the starved
robot and alternates future service.

| policy | robot_0000 delivery | robot_0001 delivery | min delivery | Jain |
| --- | ---: | ---: | ---: | ---: |
| `predictive_baseline` | `1.0000` | `0.0000` | `0.0000` | `0.5000` |
| `robot_budget_aware` | `0.5000` | `0.5000` | `0.5000` | `1.0000` |

Artifacts:

- `results_robot_budget/robot_budget_controller_smoke_summary.json`
- `results_robot_budget/robot_budget_controller_smoke_report.md`

## ROS 2 Docker Validation

The first ROS 2 live validation ran the sidecar policy
`fleetqox_semantic_contract_budgeted` through the same two-robot
Wi-Fi/WAN/roaming dynamic-objective transition workload used by the per-robot
budget baseline:

```bash
python3 -m scripts.run_ros2_docker_live_bridge \
  --run \
  --analyze \
  --dynamic-objective-transition-matrix \
  --scenario ros2_live_bridge_t3_dynamic_objective_transition_2robot_budgeted_3seed_v1 \
  --bridge-config experiments/ros2_live_bridge_tb4_binding_v1.json \
  --rmw rmw_zenoh_cpp \
  --policy fleetqox_semantic_contract_budgeted \
  --seeds 7,13,29 \
  --robot-count 2 \
  --transition-profile wifi \
  --transition-profile wan \
  --transition-profile roaming \
  --transition-segment-s 2 \
  --seconds 6 \
  --rate-hz 12 \
  --bridge-max-batches 120 \
  --binding-objective-summary autonomy_safety:results_ros2_live_bridge/profile_objective_selector_autonomy_v1_summary.json \
  --binding-objective-schedule balanced_safety_utility@0,autonomy_safety@2,balanced_safety_utility@4 \
  --transition-summary-json results_ros2_live_bridge/dynamic_objective_transition_2robot_budgeted_3seed_summary.json \
  --transition-markdown results_ros2_live_bridge/dynamic_objective_transition_2robot_budgeted_3seed_report.md \
  --title "ROS 2 Live Dynamic Objective Transition 2-Robot Budgeted 3-Seed T3 V1"
```

Comparison artifact:

```bash
python3 -m scripts.compare_ros2_robot_budget_summaries \
  --summary baseline:results_ros2_live_bridge/dynamic_objective_transition_2robot_fair_budget_3seed_summary.json \
  --summary budgeted:results_ros2_live_bridge/dynamic_objective_transition_2robot_budgeted_3seed_summary.json \
  --summary budgeted_floor:results_ros2_live_bridge/dynamic_objective_transition_2robot_budgeted_floor_3seed_summary.json \
  --summary tailrisk:results_ros2_live_bridge/dynamic_objective_transition_2robot_budgeted_tailrisk_3seed_summary.json \
  --summary-json results_ros2_live_bridge/robot_budget_policy_compare_summary.json \
  --markdown results_ros2_live_bridge/robot_budget_policy_compare_report.md \
  --title "ROS 2 Robot Budget Policy Comparison T3 V1"
```

Live comparison:

| policy | budget pass | min ctrl | max deadline | ctrl delivery | deadline miss | p95 ms | utility |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| baseline | `0.3333` | `0.8950` | `0.3036` | `0.9328` | `0.2920` | `128.42` | `818.53` |
| budgeted | `0.3333` | `0.8974` | `0.2783` | `0.9101` | `0.2507` | `120.56` | `806.17` |
| budgeted_floor | `0.3333` | `0.8992` | `0.2650` | `0.9330` | `0.2506` | `122.99` | `751.44` |
| tailrisk | `1.0000` | `0.9222` | `0.3239` | `0.9422` | `0.2931` | `132.73` | `767.96` |

The result is now a solved per-robot budget pass for this short T3 workload, but
not a solved latency/QoE claim. The tail-risk version improves budget pass from
`0.3333` to `1.0000`, raises mean minimum per-robot control delivery from
`0.8950` to `0.9222`, and raises aggregate control delivery from `0.9328` to
`0.9422`. The cost is higher p95 latency (`128.42 ms` to `132.73 ms`), larger
latency spread in seed `13`, and lower utility (`818.53` to `767.96`).

Decision logs confirm the new mechanism is active in the ROS 2 path. Across
seeds `7`, `13`, and `29`, respectively, the sidecar recorded `114`, `84`, and
`130` decisions with `robot_budget=active`, plus `25`, `28`, and `29`
`pressure_shaping` decisions. The earlier `budgeted_floor` run had zero
`control floor` activations because the base semantic contract already sent
control intent; the missing pressure source was network-tail risk, not another
capacity reclaim rule.

The later ROS 2 path separates hard-SLO ownership from QoE recovery. Redundant
control leases, event de-duplication, local-controller deadline ownership, and
the volatility guard define the hard envelope. QoE recovery then runs only as a
bounded non-control lane. The current four-robot smoke
`ros2_live_bridge_t3_dynamic_objective_transition_4robot_qoe_recovery_quota_smoke_v1`
uses a fleet quota `ceil(scale * sqrt(active_robot_count))` plus one probe per
robot per tick. It keeps budget pass `1.0000`, control delivery `1.0000`, and
worst-robot deadline miss `0.1154`, while restoring quality-gate robot coverage
to `1.0000` for `4/4` robots with `9` accepted qualified projections. The cost
is visible p95 growth to `422.02 ms`, so the mechanism is a scale-safe recovery
boundary, not the final QoE optimizer.

The smoke has now been promoted to a repeated four-robot row through
`scripts.run_ros2_n_robot_qoe_quota_matrix`.  Over seeds `7,13,29`, the same
QoE quota path keeps hard budget pass `1.0000` and quality-gate robot coverage
`1.0000`.  Mean control delivery is `0.9957`, mean deadline miss is `0.0773`,
mean p95 is `422.22 ms`, mean minimum per-robot control delivery is `0.9825`,
and mean worst-robot deadline miss is `0.1209`.  This makes the controller
evidence repeated for `4` robots, but also confirms the remaining optimization
gap: p95 varies from `320.01 ms` to `554.86 ms` across seeds.

The first `8`-robot row is a measured scale failure.  The same runner completes
all `3/3` seeds and keeps robot coverage at `1.0000` for sidecar decisions,
receiver packets, egress publications, local leases, and monitor observations.
However, hard budget pass falls to `0.0000`, mean control delivery falls to
`0.7859`, p95 rises to `1387.09 ms`, and mean minimum per-robot control
delivery falls to `0.6164`.  The failure is therefore not a missing namespace or
ROS wiring issue.  It is a controller/service-allocation issue: the current
virtual-queue pressure and QoE probe quota do not guarantee bounded command
progress for every robot as N grows.

The next controller step is now implemented as an optional N-aware command
service floor.  When enabled, the wrapper scans the current tick after the base
policy runs.  If the active robot count is at or above the configured threshold
and a robot has control candidates but no sent command representation, the
allocator chooses the smallest feasible control transform, reclaims
non-critical capacity, and emits the decision with
`robot_budget=n_aware_control_floor`.  This floor is proactive: it does not wait
for that robot to accumulate service pressure from a previous miss.  The
deadline-first and action-deadline sidecar policies enable it because those are
the branches used by the current ROS 2 QoE quota matrix.

The follow-up inspection showed a second scale failure mode: in the `8`-robot
seed-`13` live path, the sidecar can already admit every control decision
(`control_tx_ratio=1.0`) while only a fraction are received.  The runtime now
therefore supports paced control-lease redundancy.  Instead of sending duplicate
lease packets back-to-back in the same burst, it sends the primary immediately
and queues redundant copies for later batches, giving the lease path time
diversity without adding more decision-level events.

## Research Meaning

This is the first algorithmic step from "measure per-robot SLO violations" to
"feed per-robot SLO debt back into admission".  The mechanism is not a
seed-specific parameter patch: it is a primal-dual virtual-queue controller over
robot-level constraints.

The novelty path for FleetRMW is now sharper:

- fleet-level objective chooses the transport/semantic representation;
- robot-level virtual queues enforce worst-robot SLO pressure;
- network-tail risk turns LAN/WAN/Wi-Fi/roaming conditions into budget pressure
  before the receiver-side SLO has already failed;
- pressure-aware semantic shaping gives up non-critical robot traffic first;
- local robot-side lease and projection gates validate authority and quality
  before ROS consumers or controllers use reconstructed messages.

## Next Gap

The local smoke proves control-loop behavior in a deterministic setting, the
ROS 2 Docker run proves that tail-risk pressure and semantic shaping can enforce
the per-robot budget in a live two-robot bridge, and the damped feedback smoke
proves that receiver-side feedback can be closed without collapsing the
scheduler. The remaining gap is closed-loop optimality:

- update pressure from observed per-robot receiver, egress, lease, and quality
  gate outcomes through the new `robot_feedback` protocol, not only
  scheduler-side predictions and link-tail estimates;
- extend the control-first feedback law with a deadline-first inner loop so the
  controller protects both hard SLOs before optimizing residual QoE;
- make the pressure shaper latency-aware without letting QoE pressure suppress
  worst-robot control delivery or push deadline miss above budget;
- improve state/perception QoE beyond the stable-probe minimum without letting
  startup/profile-transition tail debt push worst-robot deadline miss above the
  hard budget;
- re-run the `8`-robot QoE quota row with the new N-aware command service
  allocator and paced control-lease redundancy enabled, then compare against the
  current negative row;
- if tail robots still fall below budget, add bounded deficit round-robin or
  virtual-deadline ranking on top of the current proactive floor;
- once `8` robots reach hard budget pass, extend to `16` robots, longer
  segments, asymmetric robot priorities, and confidence intervals;
- move the mechanism from sidecar policy into the future `rmw_fleetqox_cpp`
  boundary where per-flow packet format, reliability, and admission decisions
  become native middleware behavior.

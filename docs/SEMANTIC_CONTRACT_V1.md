# Semantic Contract V1

## Purpose

This artifact turns `control_intent` from a WAN-specific patch into a general
feasibility-aware semantic communication layer.

The previous controller logic was still close to tuning: classify the link,
select a profile, then adjust admission pressure. That is not enough when the
original ROS sample is physically infeasible on the path. A 45 ms control sample
cannot be made valid on a 120 ms RTT WAN path by changing a Lagrange multiplier.

The new layer makes this explicit:

```text
ROS flow -> semantic contract -> transform candidates -> feasibility certificate
```

## Implementation

| component | path |
| --- | --- |
| Contract model | `fleetqox/semantic_contract.py` |
| Intent controller integration | `fleetqox/control_plane.py` |
| First-class contract scheduler | `fleetqox/control_plane.py` |
| Runtime effective deadline | `fleetqox/sidecar_runtime.py` |
| Contract tests | `tests/test_semantic_contract.py` |

Policy name:

```text
fleetqox_semantic_contract
fleetqox_semantic_contract_lossaware
fleetqox_semantic_contract_adaptive
```

## Core Types

`FlowContract` captures:

- source ROS-like deadline and lifespan;
- flow class;
- allowed semantic transforms;
- minimum delivery target;
- maximum tolerated deadline risk.

`SemanticTransform` captures one deliverable representation:

- `raw`: normal ROS sample;
- `semantic_delta`: compact state/control/coordination representation;
- `degraded`: reduced QoE/perception/debug representation;
- `control_intent`: path-aware command horizon for infeasible control samples;
- `supervisory_intent`: longer goal/constraint lease for paths where even the
  short control-intent lifespan is physically infeasible.

`FeasibilityCertificate` records why a transform is or is not feasible:

- allocated bytes;
- estimated path tail time;
- predicted arrival age;
- slack after wire time;
- deadline risk;
- reason.

For `semantic_delta`, `degraded`, `control_intent`, and
`supervisory_intent`, the certificate uses semantic age from the moment the
representation is synthesized, not the age of the raw sample that triggered the
transform. This is deliberate: these are new bounded representations of the
latest local state, not claims that an old raw sample is still fresh. Raw
delivery still preserves source age.

The intent feasibility gate is also transform-specific: raw control keeps the
strict control risk budget, while `control_intent` is feasible if it arrives
inside its horizon/lifespan. The risk value is still reported so the scheduler
can rank intent candidates, but it does not use the raw-control risk threshold.
For `supervisory_intent`, the lifespan is also transformed: the packet is no
longer a next-tick velocity sample, but a local-controller lease with a longer
validity horizon.

## Control-Intent Rule

`fleetqox_predictive_intent` no longer asks whether the link is labeled WAN or
roaming before sending intent. It asks:

```text
is raw control infeasible?
does control_intent improve the feasibility certificate?
does it remain inside lifespan?
```

If yes, the controller rewrites the dropped control decision into:

```text
action    = send_intent
wire_mode = control_intent
deadline  = path-aware horizon deadline
```

This is the first step toward a general transform algebra. Network profiles
still matter as observations, but they no longer define the mechanism.

## Why This Is Not Tuning

The key change is the decision unit. The system is no longer only selecting
parameters for packet admission. It is selecting among semantically valid
representations of the same ROS-level flow.

For WAN-infeasible control, the system does not claim that the original 45 ms
sample was delivered. It delivers a different representation: a compact control
intent with a longer validity horizon bounded by the original lifespan. The
metric layer separately reports control delivery, intent delivery, and deadline
miss, so a policy cannot win by dropping all control messages.

## Scheduler Model

The scheduler lifts this from an intent fallback into the main control-plane
decision:

```text
for every flow:
  generate all semantic transform candidates
  certify each candidate under the current service curve
  solve one constrained scheduling problem over certified candidates
```

That makes `raw`, `semantic_delta`, `degraded`, `control_intent`,
`supervisory_intent`, and future representations first-class actions in one
optimizer instead of special cases around an existing admission controller.

## Scheduler Integration

`fleetqox_semantic_contract` implements that first scheduler integration. For
each flow, it generates certified transform candidates, filters infeasible
ones, then admits candidates directly under `NetworkLink.capacity_bytes_per_tick`.
Each flow can contribute at most one selected transform, and the chosen
transform consumes its real byte budget.

The scheduler no longer does:

```text
base scheduler drops control -> wrapper rewrites drop to send_intent
```

It now does:

```text
raw / semantic_delta / degraded / control_intent / supervisory_intent candidates
-> feasibility certificates
-> capacity-aware semantic candidate selection
```

## Supervisory Intent Lease

The roaming preflight exposed a gap that packet compaction cannot solve: if the
network path is longer than the original `/cmd_vel` lifespan, neither raw
control nor short `control_intent` is physically meaningful. The new
`supervisory_intent` transform changes the control representation to a compact
goal/constraint lease. It has lower semantic value than direct control, but it
lets the local robot controller continue with bounded intent instead of losing
all control delivery.

In the offline roaming preflight with `160 ms` RTT, `25 ms` jitter, `3%` loss,
and `70 KB/s`, previous policies delivered zero control packets. The semantic
contract now emits `send_supervisory_intent` packets for control on every seed
checked, while the adaptive selector chooses the tail-shield variant for nearly
all roaming decisions.

The follow-up five-seed Docker/tc-netem roaming sweep confirms that this is not
only an offline artifact. Under `80 ms` one-way delay, `25 ms` jitter, `3%`
loss, and `70 KB/s`, `fleetqox_predictive_intent` still delivered no control
intent packets (`0.0000` control delivery; `950.4` mean non-delivery events).
The semantic-contract family delivered supervisory control instead:
`fleetqox_semantic_contract` reached `0.9646 +/- 0.0051` control delivery and
`0.0004 +/- 0.0004` deadline miss, while
`fleetqox_semantic_contract_adaptive` reached `0.9686 +/- 0.0033` control
delivery and `0.0002 +/- 0.0004` deadline miss. The adaptive policy used
`4747` `send_supervisory_intent` transmissions and selected tail-shield for
`7842` traced decisions.

The roaming result is a Pareto result, not a single-metric dominance claim. The
fixed semantic contract has higher delivered utility (`6332.3 +/- 304.7`) by
spending more bytes (`77.4 KB` mean received bytes). The adaptive selector gives
up about `5.7%` utility (`5973.8 +/- 315.4`) while reducing received bytes to
`55.0 KB`, lowering mean loss from `0.0344` to `0.0304`, and suppressing the
loss-aware variant's tail outlier (`237.1 ms` mean p95 and `0.0184` deadline
miss) down to `117.2 ms` mean p95 and `0.0002` deadline miss.

In a five-seed Docker/tc-netem WAN sweep (`60 ms` delay, `15 ms` jitter,
`1.5%` loss, `90 KB/s`), the policy reached the highest mean utility
(`7560.6 +/- 320.4`) and receive count (`1279.8 +/- 17.62`) among the compared
policies. It also reduced measured deadline miss versus the older
`fleetqox_predictive_intent` wrapper (`0.0081 +/- 0.0007` versus
`0.0091 +/- 0.0009`). The tradeoff is slightly lower control delivery and
higher loss, so the result is a Pareto improvement signal rather than a
universal dominance claim.

## Loss-Aware Variant

`fleetqox_semantic_contract_lossaware` adds a packet-level loss shadow price on
top of the same semantic contract scheduler. It does not change the contract
algebra. It changes candidate scoring and admission under lossy/scarce paths:

```text
semantic score
- deadline risk price
- loss shadow price(packet cost, flow class, transform kind, path loss)
```

It also caps non-control packet admissions when loss/scarcity pressure is high.
Safety and control flows do not count against that cap, so the variant should
shape opportunistic semantic traffic without starving `control_intent`.

In the five-seed WAN comparison, the loss-aware variant kept most semantic
utility (`7455.5 +/- 334.1`) while reducing the baseline semantic scheduler's
mean loss (`0.0153` versus `0.0252`), deadline miss (`0.0084` versus `0.0230`),
and p95 latency (`80.81 ms` versus `134.2 ms`). It also beat the older
`fleetqox_predictive_intent` wrapper on utility, receive count, deadline miss,
loss, and p95 latency, with slightly lower control delivery.

## Adaptive Variant Selector

`fleetqox_semantic_contract_adaptive` is the next step after the fixed
loss-aware variant. It keeps the ROS/FleetRMW contract algebra unchanged, but it
does not force the operator to choose one scheduler mode ahead of time. Instead,
it runs two semantic-contract controllers in shadow mode on each batch:

```text
utility variant      = semantic contract without packet loss shadow
tail_shield variant  = semantic contract with packet loss shadow and non-control cap
```

The selector then evaluates both candidate schedules with contract-derived
budgets:

```text
maximize semantic utility
subject to:
  deadline risk <= active flow contract risk budget
  safety/control non-delivery <= active min-delivery budget
  loss exposure is priced by observed path instability
```

This makes the adaptive policy a small primal-dual control loop over semantic
representations rather than another set of WAN constants. On stable links it can
select the high-utility semantic scheduler. On lossy/high-jitter paths it can
switch to the tail shield when the utility regret is bounded and the lower
packet exposure is expected to protect deadline/QoE tail behavior.

In the five-seed WAN adaptive sweep, this selector became the highest-utility
policy (`7597.5 +/- 310.5`) while suppressing the fixed semantic scheduler's
tail outliers: deadline miss fell from `0.0226` to `0.0081`, loss fell from
`0.0248` to `0.0130`, and p95 latency fell from `116.2 ms` to `82.53 ms`.
Trace reasons confirm that the selector used both variants (`5137` tail-shield
decisions and `2705` utility decisions), so the result is not just a renamed
fixed policy.

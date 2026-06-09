# Sidecar Lagrangian V1

## Purpose

This artifact introduces `fleetqox_predictive_lagrangian`, the first soft
risk-constrained FleetQoX controller.

The earlier `fleetqox_predictive_guarded` policy used a hard safety gate: if a
control sample had too little deadline slack, it was dropped. That eliminated
deadline misses, but it also lost too much semantic utility. The Lagrangian
controller replaces that binary gate with an online dual penalty:

```text
score(action) =
  semantic_value
  + predictive_priority
  - lambda_deadline * deadline_risk
  - lambda_qoe * qoe_risk
  - high_risk_barrier
```

The policy updates `lambda_deadline` and `lambda_qoe` online from estimated
admitted risk. It also treats native, compacted, and degraded transmissions as
separate candidate actions.

## Implementation

| component | path |
| --- | --- |
| Controller | `fleetqox/control_plane.py` |
| Runtime policy binding | `fleetqox/sidecar_runtime.py` |
| Simulator binding | `fleetqox/simulator.py` |
| Trace binding | `fleetqox/trace.py` |

Policy name:

```text
fleetqox_predictive_lagrangian
```

## Commands

Single-policy tuning run:

```bash
env DOCKER_NETEM_BASE_IMAGE=localhost/fleetqox/docker-netem-base:latest \
    DOCKER_DEFAULT_PLATFORM=linux/amd64 \
    python3 -m scripts.run_sidecar_netem \
      --run \
      --analyze \
      --scenario sidecar_netem_lagrangian_v3 \
      --policy fleetqox_predictive_lagrangian \
      --closed-loop-feed \
      --robots 10 \
      --seconds 2 \
      --seed 7 \
      --capacity-bytes-per-second 120000 \
      --delay-ms 20 \
      --jitter-ms 5 \
      --loss-percent 1 \
      --rate-mbit 20 \
      --output-dir results_sidecar_netem_lagrangian_v3
```

Comparative matrix:

```bash
env DOCKER_NETEM_BASE_IMAGE=localhost/fleetqox/docker-netem-base:latest \
    DOCKER_DEFAULT_PLATFORM=linux/amd64 \
    python3 -m scripts.run_sidecar_netem \
      --run \
      --analyze \
      --scenario sidecar_netem_lagrangian_v3_matrix \
      --policy fleetqox_csds \
      --policy fleetqox_predictive \
      --policy fleetqox_predictive_guarded \
      --policy fleetqox_predictive_lagrangian \
      --closed-loop-feed \
      --robots 10 \
      --seconds 2 \
      --seed 7 \
      --capacity-bytes-per-second 120000 \
      --delay-ms 20 \
      --jitter-ms 5 \
      --loss-percent 1 \
      --rate-mbit 20 \
      --output-dir results_sidecar_netem_lagrangian_v3_matrix
```

## Results

Single-policy tuning run:

| policy | tx | rx | loss | deadline miss | control misses | compacted rx | p95 ms | p99 ms | utility |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| `fleetqox_predictive_lagrangian` | 1240 | 1224 | 0.013 | 0.002 | 3 | 971 | 27.62 | 43.33 | 7482.29 |

Comparative closed-loop matrix:

| policy | tx | rx | loss | deadline miss | control misses | compacted rx | p95 ms | p99 ms | utility |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| `fleetqox_csds` | 1294 | 1281 | 0.010 | 0.001 | 1 | 0 | 26.80 | 27.73 | 8055.59 |
| `fleetqox_predictive` | 1405 | 1395 | 0.007 | 0.007 | 10 | 1169 | 27.28 | 29.10 | 8715.61 |
| `fleetqox_predictive_guarded` | 1120 | 1105 | 0.013 | 0.000 | 0 | 846 | 27.40 | 28.80 | 6735.08 |
| `fleetqox_predictive_lagrangian` | 1240 | 1228 | 0.010 | 0.008 | 10 | 976 | 27.24 | 45.08 | 7516.04 |

## Interpretation

- The Lagrangian policy successfully adds a new action-selection mechanism: it
  chooses between native, compacted, degraded, defer, and drop using risk-aware
  score density.
- In the tuning run, it lands in the intended middle region: higher utility than
  guarded predictive and fewer control misses than unguarded predictive.
- In the comparative matrix, Docker/netem variance is large enough that the same
  controller still shows control misses similar to unguarded predictive.
- This means the system contribution is now present, but the evaluation is not
  yet statistically strong enough to claim dominance from a single run.

## Research Gap Exposed

The next research step is not another hand-tuned threshold. The gap is a
statistical closed-loop optimizer:

```text
learn lambda_deadline and lambda_qoe over repeated episodes
minimize regret against deadline/QoE budgets
report confidence intervals over seeds and netem realizations
```

Concretely, the next implementation should add:

- repeated-run Docker/netem sweeps;
- mean/p95/confidence-interval reporting;
- controller parameter sweeps for `risk_barrier_start`, `risk_barrier_scale`,
  and `deadline_risk_budget`;
- automatic selection of a Pareto frontier over utility and control misses.

The first version of that reporting layer is implemented in
`docs/SIDECAR_REPEATED_STATS_V1.md` and
`scripts/report_sidecar_repeated.py`.

## Follow-Up: Risk Reset

The offline sweep in `docs/LAGRANGIAN_SWEEP_V1.md` found why the first
Lagrangian controller was unstable: unadmitted high-risk control samples could
be deferred repeatedly until they crossed the deadline. The controller now uses
`deadline_drop_risk=0.45` by default and labels that path as `lagrangian risk
reset`, so stale risky samples are consumed/reset instead of accumulating
deadline debt.

## Follow-Up: Labeled Netem Variants

`docs/SIDECAR_LAGRANGIAN_VARIANTS_NETEM_V1.md` adds Docker/netem evidence for
labeled Lagrangian configurations. `lag_012` is now a non-dominated operating
point in the two-seed smoke matrix, but it still trails predictive on utility
and guarded predictive on zero-miss safety. The next controller should therefore
adapt multipliers from observed delivery/miss feedback across windows instead
of relying only on pre-send risk estimates.

## Follow-Up: Outcome Adaptation

`docs/LAGRANGIAN_OUTCOME_ADAPTATION_V1.md`,
`docs/LAGRANGIAN_OUTCOME_ADAPTATION_V2.md`, and
`docs/SIDECAR_LAGRANGIAN_OUTCOME_ADAPTATION_NETEM_V2.md` implement the first
measured outer loop. The adapter tightens the risk gate when observed deadline
miss/starvation exceed targets, then relaxes from a zero-miss point to recover
utility. In the current two-seed netem smoke matrix, `lag_adapt_002` reaches
zero measured miss with lower loss and slightly higher receive count than
guarded predictive, while staying close on utility.

## Follow-Up: Five-Seed Validation

`docs/SIDECAR_LAG_ADAPT_002_5SEED_NETEM.md` extends `lag_adapt_002` to five
Docker/netem seeds. The adapted controller keeps zero measured control
starvation and zero measured deadline miss across the matrix. It also lands
slightly above guarded predictive on mean utility (`6729.7` versus `6713.5`)
and receive count (`1144.4` versus `1134.4`), while guarded predictive keeps a
slightly lower loss ratio (`0.0084` versus `0.0093`). The correct claim is
therefore Pareto improvement, not absolute dominance.

The next controller step is to test whether another bounded outcome update can
recover more utility without crossing the zero-miss safety boundary, then check
that candidate across more than one impairment profile.

## Follow-Up: Outcome Adaptation V3

`docs/LAGRANGIAN_OUTCOME_ADAPTATION_V3.md` and
`docs/SIDECAR_LAGRANGIAN_OUTCOME_ADAPTATION_NETEM_V3_5SEED.md` validate that
next bounded update. `lag_adapt_003` relaxes from `lag_adapt_002` by increasing
the risk budget and deadline drop threshold while lowering the deadline
multiplier. Across five Docker/netem seeds it keeps zero measured control
starvation and deadline miss, raises mean utility to `6899.2`, and raises mean
receive count to `1172.0`.

This is the best adapted operating point in the current profile. It is not a
default yet because it increases loss versus guarded predictive and
`lag_adapt_002`; the next validation must check whether it stays safe across
multiple impairment profiles, not only the current `20ms +- 5ms`, `1%` loss,
`20mbit` profile.

## Follow-Up: Profile Robustness

`docs/SIDECAR_PROFILE_ROBUSTNESS_V1.md` runs a one-seed smoke across LAN, WAN,
and roaming profiles. The result narrows the claim: `lag_adapt_003` is a good
Wi-Fi-profile operating point, but it is not a universal controller. In WAN and
roaming conditions, all current policies miss control deadlines heavily because
the base RTT/jitter profile consumes the control slack before admission can
help.

The next algorithmic step should therefore be profile-aware Lagrangian control:
estimate path RTT, jitter, loss, and capacity online; classify the path regime;
then adapt deadline budgets, risk multipliers, compaction pressure, and perhaps
flow deadlines before the sidecar starts accumulating deadline debt.

## Follow-Up: Profile-Aware Lagrangian

`docs/SIDECAR_PROFILE_AWARE_LAGRANGIAN_V1.md` implements the first version of
that profile-aware controller as `fleetqox_predictive_profiled`. The sidecar
now receives the Docker/netem link observation through `NetworkLink`, classifies
the path as LAN, Wi-Fi, WAN, or roaming, and routes decisions to a separate
Lagrangian controller for that regime.

The first one-seed WAN/roaming smoke confirms the mechanism but also exposes the
next algorithmic gap. In WAN, `fleetqox_predictive_profiled` lowers deadline
miss to `0.008`, compared with `0.012` for guarded predictive and `0.015` for
fixed `lag_adapt_003`. In roaming, it lowers deadline miss to `0.005`, compared
with `0.060` for fixed `lag_adapt_003` and `0.311` for guarded predictive.
However, it does so by dropping/admitting very conservatively: WAN utility falls
to `1068.2`, and roaming utility falls to `660.2`.

The next controller should therefore stop treating each profile envelope as a
hand-picked operating point. It should learn how aggressively each link regime
can relax its risk budget, drop threshold, compaction pressure, and deadline
multiplier while keeping measured deadline miss and operator QoE inside target
budgets.

## Follow-Up: Control Intent

`docs/SIDECAR_INTENT_WAN_V1.md` adds the missing metric and semantic layer. The
previous WAN policies looked safe because they dropped all `944` control
decisions; their packet deadline miss was low, but their control delivery ratio
was `0.0000`. The metric layer now reports `control_delivery_ratio`,
`control_non_delivery_events`, and intent packet counts.

`fleetqox_predictive_intent` wraps the contextual profile controller with a
control-intent fallback: if a control sample's original deadline is infeasible
over the observed WAN path, it sends a compact `control_intent` horizon packet
instead of dropping the sample. In the one-seed WAN smoke, that raises control
delivery to `0.9862` and delivered utility to `7303.8`, with `931` received
intent packets. It still has `10` control misses, so the next algorithmic step
is horizon sizing and intent rate control, not claiming final dominance.

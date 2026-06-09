# Sidecar Profile-Aware Lagrangian V1

## Purpose

`fleetqox_predictive_profiled` is the first profile-aware FleetQoX controller.
It keeps the ROS-side sidecar/RMW-shim contract unchanged, but stops assuming
that one Lagrangian parameter set can work for every IP path.

The previous profile robustness smoke showed why this is needed:

- `lag_adapt_003` is a good Wi-Fi-profile operating point.
- The same fixed parameters are not robust under WAN/roaming latency.
- Docker `tc netem` delay/loss must also be reflected in the scheduler-visible
  `NetworkLink`; otherwise the controller is tuning against the wrong network.

## Implementation

| component | path |
| --- | --- |
| Profile classifier and controller | `fleetqox/control_plane.py` |
| Runtime policy binding | `fleetqox/sidecar_runtime.py` |
| Feeder link-profile overrides | `scripts/feed_sidecar_synthetic.py`, `scripts/feed_sidecar_closed_loop.py` |
| Docker/netem link observation plumbing | `scripts/run_sidecar_netem.py`, `external/docker-netem/docker-compose.sidecar.yml` |
| Repeated profile runner/reporting | `scripts/run_sidecar_repeated_netem.py`, `fleetqox/sidecar_repeated.py` |

Policy name:

```text
fleetqox_predictive_profiled
```

The controller classifies the path from scheduler-visible `NetworkLink`:

```text
LAN      low RTT/jitter/loss, high capacity
Wi-Fi    default loss/jitter regime
WAN      high RTT/jitter or lower capacity
Roaming  severe delay/jitter/loss/capacity pressure
```

Each regime owns a separate Lagrangian controller and dual state. This is
deliberate: if WAN repeatedly violates deadlines, its multiplier should not
pollute the LAN controller, and a LAN controller should not stay conservative
because a previous roaming episode was bad.

## Testbed Correction

Before this step, Docker `tc netem` affected the actual UDP path but not the
`NetworkLink` payload seen by the sidecar. The feeder now passes:

```text
SIDECAR_LINK_RTT_MS    = 2 * NETEM_DELAY_MS
SIDECAR_LINK_JITTER_MS = NETEM_JITTER_MS
SIDECAR_LINK_LOSS      = NETEM_LOSS_PERCENT / 100
```

When explicit link overrides are present, the synthetic stream no longer adds
its legacy random RTT/jitter/loss bursts. This keeps a named WAN profile from
being accidentally classified as roaming at tick 0.

## Commands

WAN smoke:

```bash
env DOCKER_NETEM_BASE_IMAGE=localhost/fleetqox/docker-netem-base:latest \
    DOCKER_DEFAULT_PLATFORM=linux/amd64 \
    python3 -m scripts.run_sidecar_repeated_netem \
      --run \
      --scenario-prefix sidecar_profiled_wan_v1 \
      --profile wan \
      --policy fleetqox_predictive_guarded \
      --policy fleetqox_predictive_lagrangian \
      --policy fleetqox_predictive_profiled \
      --policy-label lag_adapt_003 \
      --lagrangian-deadline-risk-budget 0.0810891 \
      --lagrangian-initial-deadline-lambda 2.57914 \
      --lagrangian-risk-barrier-start 0.58736 \
      --lagrangian-risk-barrier-scale 12.5784 \
      --lagrangian-deadline-drop-risk 0.429105 \
      --seeds 7 \
      --closed-loop-feed
```

Roaming smoke uses the same command with `--profile roaming`.

## Results

One-seed WAN smoke:

| policy | rx | loss | deadline miss | p95 ms | utility |
| --- | ---: | ---: | ---: | ---: | ---: |
| `fleetqox_predictive_guarded` | 486 | 0.016 | 0.012 | 78.65 | 2583.8 |
| `lag_adapt_003` | 340 | 0.012 | 0.015 | 79.81 | 1588.5 |
| `fleetqox_predictive_profiled` | 260 | 0.008 | 0.008 | 78.34 | 1068.2 |

One-seed roaming smoke:

| policy | rx | loss | deadline miss | p95 ms | utility |
| --- | ---: | ---: | ---: | ---: | ---: |
| `fleetqox_predictive_guarded` | 441 | 0.052 | 0.311 | 110.3 | 2378.9 |
| `lag_adapt_003` | 283 | 0.014 | 0.060 | 109.3 | 1249.9 |
| `fleetqox_predictive_profiled` | 192 | 0.035 | 0.005 | 108.1 | 660.2 |

## Interpretation

- The profile-aware controller sharply reduces deadline miss under WAN/roaming
  once the sidecar receives the correct link observation.
- This is achieved by aggressive admission/drop behavior, not by magic
  transport improvement. Utility and receive count drop substantially.
- Under WAN, profiled is the best measured deadline/safety point in the smoke:
  `0.008` deadline miss versus `0.012` guarded and `0.015` fixed `lag_adapt_003`.
- Under roaming, profiled nearly restores the deadline envelope: `0.005`
  deadline miss versus `0.060` fixed `lag_adapt_003` and `0.311` guarded.
- This is still one-seed evidence. The next benchmark must run multiple seeds
  and tune the WAN/roaming profile parameters to recover utility without giving
  back the deadline protection.

## Research Implication

The system contribution is now clearer: FleetRMW should not expose only static
QoS knobs or a single global scheduler. It should run a path-aware control plane:

```text
estimate IP path regime -> choose risk envelope -> schedule semantic actions
-> observe deadline/QoE outcomes -> adapt the regime-specific dual state
```

The next algorithmic target is a context-bandit or constrained online optimizer
over these profile-specific Lagrangian envelopes, with regret measured against
deadline miss, delivered utility, and operator QoE.

## Follow-Up Direction

The first contextual envelope selector is implemented as
`fleetqox_predictive_contextual`, but the WAN smoke in
`docs/SIDECAR_INTENT_WAN_V1.md` shows a more fundamental metric issue: low
deadline miss can be achieved by dropping all control samples. The follow-up
policy, `fleetqox_predictive_intent`, therefore adds a semantic `control_intent`
wire mode for WAN-infeasible control samples and evaluates control delivery
directly.

# Sidecar Netem Matrix V2

## Purpose

This artifact extends `SIDECAR_NETEM_MATRIX_V1` with a fifth policy:

- `fleetqox_predictive_guarded`.

The guarded policy keeps the FleetQoX predictive admission path but adds a
deadline-risk guard for safety/control flows. Before admission, it estimates a
tail wire-time budget from RTT, jitter, and loss. A control sample is dropped
instead of transmitted when its remaining deadline slack is already below that
tail estimate. The released capacity is then reallocated to the remaining
candidate flows.

## Command

```bash
env DOCKER_NETEM_BASE_IMAGE=localhost/fleetqox/docker-netem-base:latest \
    DOCKER_DEFAULT_PLATFORM=linux/amd64 \
    python3 -m scripts.run_sidecar_netem \
      --run \
      --analyze \
      --scenario sidecar_netem_matrix_v4 \
      --all-policies \
      --robots 10 \
      --seconds 2 \
      --seed 7 \
      --capacity-bytes-per-second 120000 \
      --delay-ms 20 \
      --jitter-ms 5 \
      --loss-percent 1 \
      --rate-mbit 20 \
      --output-dir results_sidecar_netem_matrix_v4
```

The explicit local base image avoids Docker Hub pull-rate limits.

## Artifacts

| artifact | path |
| --- | --- |
| Matrix metrics | `results_sidecar_netem_matrix_v4/sidecar_netem_matrix_v4_matrix_metrics.jsonl` |
| Guarded decisions | `results_sidecar_netem_matrix_v4/sidecar_netem_matrix_v4_fleetqox_predictive_guarded_decisions.jsonl` |
| Guarded received | `results_sidecar_netem_matrix_v4/sidecar_netem_matrix_v4_fleetqox_predictive_guarded_received.jsonl` |
| Guarded metrics | `results_sidecar_netem_matrix_v4/sidecar_netem_matrix_v4_fleetqox_predictive_guarded_metrics.jsonl` |

## Results

| policy | tx | rx | loss | deadline miss | control misses | compacted rx | p95 ms | p99 ms | utility |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| `fifo` | 64 | 64 | 0.000 | 0.016 | 1 | 0 | 30.23 | 46.21 | 306.43 |
| `static_priority` | 75 | 74 | 0.013 | 0.014 | 1 | 0 | 42.37 | 45.83 | 375.30 |
| `fleetqox_csds` | 98 | 97 | 0.010 | 0.010 | 1 | 0 | 42.82 | 46.61 | 448.81 |
| `fleetqox_predictive` | 120 | 119 | 0.008 | 0.084 | 10 | 76 | 57.66 | 58.35 | 545.20 |
| `fleetqox_predictive_guarded` | 90 | 90 | 0.000 | 0.000 | 0 | 42 | 55.93 | 60.36 | 348.52 |

## Interpretation

- Unguarded predictive still gives the highest delivered utility and receive
  count, but it has the worst control deadline misses in this run.
- Guarded predictive eliminates measured deadline misses and packet loss, while
  still using semantic compaction.
- Guarded predictive is too conservative on utility: `348.52` is better than
  FIFO but below static priority, CSDS, and unguarded predictive.
- CSDS remains the best balanced hand-written baseline in this specific run:
  high utility, low deadline miss, and moderate receive count.

The result is useful because it splits the research problem cleanly:

```text
Predictive admission solves value density and semantic compaction.
Deadline-risk guarding solves control misses.
The missing contribution is a soft constrained optimizer that combines both
without collapsing delivered utility.
```

## Testbed Limitation

The current sidecar feeder is open-loop: it pre-generates observation ages
without feeding policy decisions back into future sample ages. That is acceptable
for comparing socket/netem behavior, but it can over-penalize policies that drop
control samples because later observations continue aging in the pre-generated
trace.

The next testbed improvement should be a closed-loop sidecar feeder:

```text
sidecar response -> per-flow action feedback -> next observation age update
```

That will make guarded admission measurements more faithful.

This follow-up is implemented in `docs/SIDECAR_CLOSED_LOOP_V1.md`. In the
closed-loop matrix, guarded predictive no longer collapses to very low
throughput: it delivers `1107` packets with zero measured deadline miss.

## Next Algorithmic Step

The next controller should replace hard guarded drops with a constrained
utility optimizer:

```text
maximize semantic utility
subject to Pr(control latency > deadline) <= epsilon
           and QoE freeze risk <= beta
```

A practical version can start with:

- tail-latency/CVaR risk estimates per flow class;
- Lagrange multipliers for deadline and QoE budgets;
- semantic compaction as an action with value loss, not only a byte reduction;
- closed-loop feedback from delivered/missed packets into the next admission
  window.

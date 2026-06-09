# Sidecar Closed-Loop Netem V1

## Purpose

This artifact fixes the main limitation in the previous sidecar-netem matrix:
the synthetic feeder was open-loop. It pre-generated observation ages and did
not let sidecar decisions affect future samples.

Closed-loop feeding changes the testbed path to:

```text
synthetic flow state
  -> TCP sidecar batch with include_feedback=true
  -> sidecar policy decision
  -> per-flow action feedback
  -> next observation age update
  -> UDP emission over Docker/tc-netem
  -> receiver metrics
```

For `send`, `send_degraded`, `send_compacted`, and `drop`, the feeder consumes
the current sample and resets that flow's age. For `defer`, age continues to
accumulate. This matches the simulator's age model more closely and makes
deadline-risk policies easier to evaluate fairly.

## Command

```bash
env DOCKER_NETEM_BASE_IMAGE=localhost/fleetqox/docker-netem-base:latest \
    DOCKER_DEFAULT_PLATFORM=linux/amd64 \
    python3 -m scripts.run_sidecar_netem \
      --run \
      --analyze \
      --scenario sidecar_netem_closed_loop_v1 \
      --all-policies \
      --closed-loop-feed \
      --robots 10 \
      --seconds 2 \
      --seed 7 \
      --capacity-bytes-per-second 120000 \
      --delay-ms 20 \
      --jitter-ms 5 \
      --loss-percent 1 \
      --rate-mbit 20 \
      --output-dir results_sidecar_netem_closed_loop
```

## Artifacts

| artifact | path |
| --- | --- |
| Matrix metrics | `results_sidecar_netem_closed_loop/sidecar_netem_closed_loop_v1_matrix_metrics.jsonl` |
| FIFO decisions | `results_sidecar_netem_closed_loop/sidecar_netem_closed_loop_v1_fifo_decisions.jsonl` |
| Static priority decisions | `results_sidecar_netem_closed_loop/sidecar_netem_closed_loop_v1_static_priority_decisions.jsonl` |
| CSDS decisions | `results_sidecar_netem_closed_loop/sidecar_netem_closed_loop_v1_fleetqox_csds_decisions.jsonl` |
| Predictive decisions | `results_sidecar_netem_closed_loop/sidecar_netem_closed_loop_v1_fleetqox_predictive_decisions.jsonl` |
| Guarded predictive decisions | `results_sidecar_netem_closed_loop/sidecar_netem_closed_loop_v1_fleetqox_predictive_guarded_decisions.jsonl` |

## Results

| policy | tx | rx | loss | deadline miss | control misses | compacted rx | p95 ms | p99 ms | utility |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| `fifo` | 1005 | 990 | 0.015 | 0.002 | 2 | 0 | 27.06 | 28.40 | 6335.82 |
| `static_priority` | 1190 | 1177 | 0.011 | 0.001 | 1 | 0 | 27.90 | 29.48 | 7625.57 |
| `fleetqox_csds` | 1294 | 1276 | 0.014 | 0.007 | 9 | 0 | 26.99 | 28.85 | 8017.39 |
| `fleetqox_predictive` | 1405 | 1384 | 0.015 | 0.007 | 10 | 1162 | 27.31 | 29.52 | 8645.39 |
| `fleetqox_predictive_guarded` | 1120 | 1107 | 0.012 | 0.000 | 0 | 849 | 27.32 | 28.43 | 6748.60 |

## Interpretation

- Closed-loop feeding removes the artificial age accumulation seen in the
  open-loop matrix. Throughput is now in the expected 1000+ packet range for
  this 2-second workload.
- Unguarded predictive remains the best utility policy: it delivers `8645.39`
  semantic utility and the highest receive count.
- Guarded predictive now has a meaningful operating point: it eliminates
  measured deadline misses and control misses while still delivering `1107`
  packets and `849` compacted samples.
- Guarded predictive is no longer collapsed, but it still loses too much utility
  versus unguarded predictive and CSDS. The next algorithmic contribution should
  be a soft risk-constrained optimizer, not a binary guard.

## Research Signal

Closed-loop evaluation strengthens the FleetQoX research story:

```text
Semantic predictive admission maximizes delivered value.
Risk guarding protects control deadlines.
Closed-loop feedback makes the tradeoff measurable.
The missing novelty is an online constrained optimizer that moves along the
utility/deadline frontier instead of choosing one extreme.
```

The next prototype should use closed-loop feedback to learn/update:

- per-class tail-latency risk;
- per-flow value loss under semantic compaction;
- deadline and QoE Lagrange multipliers;
- admission thresholds that adapt to measured miss/loss outcomes.

The first implementation of this direction is documented in
`docs/SIDECAR_LAGRANGIAN_V1.md`.

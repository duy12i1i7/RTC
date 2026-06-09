# Sidecar Netem Matrix V1

## Purpose

This artifact compares the same live FleetRMW sidecar path across four
policies:

- `fifo`;
- `static_priority`;
- `fleetqox_csds`;
- `fleetqox_predictive`.

The path is:

```text
synthetic ROS-like flow observations
  -> TCP sidecar API inside Docker
  -> selected runtime policy
  -> UDP emission from sidecar container
  -> tc netem impairment
  -> receiver container
  -> sidecar runtime metrics
```

This is the first comparative network-emulated runtime matrix for FleetQoX. It
does not yet use ROS 2 `rmw` symbols, but it does validate the middleware policy
boundary under real sockets, Docker network namespaces, and Linux `tc netem`.

## Command

```bash
python3 -m scripts.run_sidecar_netem \
  --run \
  --analyze \
  --scenario sidecar_netem_matrix_v1 \
  --all-policies \
  --robots 10 \
  --seconds 2 \
  --seed 7 \
  --capacity-bytes-per-second 120000 \
  --delay-ms 20 \
  --jitter-ms 5 \
  --loss-percent 1 \
  --rate-mbit 20 \
  --output-dir results_sidecar_netem_matrix
```

The runner executes policies sequentially and writes per-policy logs plus one
combined matrix file.

## Artifacts

| artifact | path |
| --- | --- |
| Matrix metrics | `results_sidecar_netem_matrix/sidecar_netem_matrix_v1_matrix_metrics.jsonl` |
| FIFO decisions | `results_sidecar_netem_matrix/sidecar_netem_matrix_v1_fifo_decisions.jsonl` |
| FIFO received | `results_sidecar_netem_matrix/sidecar_netem_matrix_v1_fifo_received.jsonl` |
| Static priority decisions | `results_sidecar_netem_matrix/sidecar_netem_matrix_v1_static_priority_decisions.jsonl` |
| Static priority received | `results_sidecar_netem_matrix/sidecar_netem_matrix_v1_static_priority_received.jsonl` |
| CSDS decisions | `results_sidecar_netem_matrix/sidecar_netem_matrix_v1_fleetqox_csds_decisions.jsonl` |
| CSDS received | `results_sidecar_netem_matrix/sidecar_netem_matrix_v1_fleetqox_csds_received.jsonl` |
| Predictive decisions | `results_sidecar_netem_matrix/sidecar_netem_matrix_v1_fleetqox_predictive_decisions.jsonl` |
| Predictive received | `results_sidecar_netem_matrix/sidecar_netem_matrix_v1_fleetqox_predictive_received.jsonl` |

## Results

| policy | tx | rx | loss | deadline miss | control misses | compacted rx | p95 ms | p99 ms | utility |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| `fifo` | 64 | 64 | 0.000 | 0.031 | 2 | 0 | 27.86 | 50.77 | 306.43 |
| `static_priority` | 75 | 74 | 0.013 | 0.108 | 8 | 0 | 56.26 | 59.43 | 381.43 |
| `fleetqox_csds` | 98 | 95 | 0.031 | 0.011 | 1 | 0 | 43.76 | 47.97 | 439.18 |
| `fleetqox_predictive` | 120 | 120 | 0.000 | 0.083 | 10 | 77 | 52.45 | 53.39 | 549.89 |

## Interpretation

- FIFO has low p95 only because it admits far fewer packets; it delivers the
  lowest semantic utility.
- Static class priority improves delivered utility over FIFO but is worst on
  deadline miss in this run.
- CSDS has the strongest deadline protection in this matrix: lowest deadline
  miss ratio and only one control miss, but it sacrifices delivered utility and
  loses three packets.
- FleetQoX predictive delivers the highest utility, highest receive count, zero
  measured loss, and visible semantic compaction. It is not yet the best
  deadline policy in the live netem matrix.

The important research signal is therefore not "predictive wins every scalar
metric." The stronger and more useful signal is:

```text
Semantic predictive admission can deliver substantially more useful fleet
information through the same impaired network, but the next algorithmic step
must make that admission deadline-risk constrained rather than utility-only.
```

## Research Gap Exposed

This matrix exposes a sharper gap than the local simulator:

1. Throughput/utility optimization and deadline protection diverge under real
   socket scheduling and netem delay.
2. Semantic compaction increases delivered value, but by admitting more packets
   it can still increase the count of control packets that cross their deadline.
3. Per-flow QoS is not enough; the policy needs fleet-level, class-level risk
   budgets that trade utility, freshness, and deadline violation probability.
4. A publishable FleetRMW result should optimize a constrained multi-objective
   function, not just rank packets by local urgency.

## Next Algorithmic Direction

The next prototype should add risk-constrained predictive admission:

```text
maximize delivered semantic utility and operator QoE
subject to per-class deadline miss budgets,
           control starvation budgets,
           link-capacity uncertainty,
           and semantic freshness constraints.
```

Concretely, this suggests a controller that combines:

- online link-capacity prediction;
- per-class deadline-risk estimation, preferably tail/CVaR-like rather than
  average-latency based;
- semantic compaction as an action with explicit cost and fidelity loss;
- a control-barrier or Lyapunov-style safety layer that rejects utility-improving
  transmissions when they would violate the control deadline budget.

That is the next step from engineering prototype toward a research contribution.

## Follow-up

`docs/SIDECAR_NETEM_MATRIX_V2.md` adds the first risk-guarded predictive
variant. It validates that deadline-risk gating can eliminate measured control
misses, but also shows that hard gating loses too much utility without a softer
constrained optimizer.

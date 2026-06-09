# Sidecar Netem V1

## Purpose

This artifact validates the first network-emulated FleetRMW sidecar path:

```text
synthetic ROS-like flow observations
  -> TCP sidecar API inside Docker
  -> FleetQoX predictive admission
  -> UDP emission from sidecar container
  -> tc netem impairment
  -> receiver container
  -> sidecar runtime metrics
```

This is the first step where FleetQoX predictive admission runs as a live
process across Docker network namespaces with Linux `tc netem`.

## Command

```bash
python3 -m scripts.run_sidecar_netem \
  --run \
  --analyze \
  --scenario sidecar_netem_v1 \
  --robots 10 \
  --seconds 2 \
  --seed 7 \
  --capacity-bytes-per-second 120000 \
  --delay-ms 20 \
  --jitter-ms 5 \
  --loss-percent 1 \
  --rate-mbit 20 \
  --output-dir results_sidecar_netem
```

The runner uses `external/docker-netem/docker-compose.sidecar.yml`. When Docker
Hub pull limits block `python:3.12-slim`, it can reuse the local
`ros2-netem-publisher:latest` image as `localhost/fleetqox/docker-netem-base`.

## Artifacts

| artifact | path |
| --- | --- |
| Sidecar decisions | `results_sidecar_netem/sidecar_netem_v1_decisions.jsonl` |
| UDP receive log | `results_sidecar_netem/sidecar_netem_v1_received.jsonl` |
| Metrics | `results_sidecar_netem/sidecar_netem_v1_metrics.jsonl` |

## Results

| metric | value |
| --- | --- |
| accepted flow observations | `1555` |
| emitted UDP packets | `120` |
| received UDP packets | `118` |
| loss ratio | `0.0167` |
| deadline miss ratio | `0.0847` |
| control starvation events | `10` |
| compacted tx/rx | `77 / 76` |
| p50 latency ms | `25.29` |
| p95 latency ms | `51.70` |
| p99 latency ms | `52.90` |

## Interpretation

- The sidecar runtime now works through Docker network namespaces and `tc netem`.
- The result is no longer just trace replay; packets are emitted by a live
  sidecar process.
- `send_compacted` remains visible after network traversal.
- Deadline misses appear under the configured `20ms +- 5ms` delay, `1%` loss,
  and `20mbit` rate profile. This is expected because control deadline is
  `45ms` and early ticks include high simulated link RTT/loss pressure.

## Next Step

The comparative sidecar-netem matrix has now been added in
`docs/SIDECAR_NETEM_MATRIX_V1.md`. The next engineering step is to tighten the
policy objective: predictive admission currently maximizes delivered semantic
utility, but the live matrix shows it also needs explicit deadline-risk budgets
to dominate CSDS on control misses.

# Sidecar Replay V1

## Purpose

This artifact validates that FleetQoX decisions can leave the local simulator as
a sidecar/RMW-shim trace contract and be replayed by a transport-level model.

The goal is not yet to implement the final RMW. The goal is to prove this
boundary:

```text
ROS-like flow observation -> FleetQoX decision -> sidecar trace -> transport replay
```

## Commands

```bash
python3 -m scripts.export_traces \
  --scenario warehouse_50_constrained \
  --format csv \
  --policy fleetqox_predictive \
  --output-dir traces_sidecar

python3 -m scripts.replay_trace traces_sidecar/warehouse_50_constrained.csv \
  --data-rate-mbps 20 \
  --base-delay-ms 5 \
  --jitter-ms 10 \
  --loss 0.03 \
  --queue-policy class_priority \
  --transport-model udp_like \
  --output results_sidecar/warehouse_50_predictive_udp_like.jsonl

python3 -m scripts.replay_trace traces_sidecar/warehouse_50_constrained.csv \
  --data-rate-mbps 20 \
  --base-delay-ms 5 \
  --jitter-ms 10 \
  --loss 0.03 \
  --queue-policy class_priority \
  --transport-model adaptive_reliability \
  --output results_sidecar/warehouse_50_predictive_adaptive_reliability.jsonl
```

## Artifacts

| artifact | path |
| --- | --- |
| Sidecar packet CSV | `traces_sidecar/warehouse_50_constrained.csv` |
| UDP-like replay | `results_sidecar/warehouse_50_predictive_udp_like.jsonl` |
| Adaptive reliability replay | `results_sidecar/warehouse_50_predictive_adaptive_reliability.jsonl` |

## Results

| model | tx | rx | lost | retransmissions | p95 latency ms | p99 latency ms | deadline miss | compacted rx |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| udp_like | 93689 | 90877 | 2812 | 0 | 15.40 | 16.30 | 0.000 | 87092 |
| adaptive_reliability | 93689 | 91106 | 2583 | 238 | 15.45 | 16.41 | 0.000 | 87308 |

## Interpretation

- The predictive sidecar emits `send_compacted` events as first-class packets.
- The replay sees semantic delta bytes through `wire_mode=semantic_delta`.
- Adaptive reliability recovers additional packets with modest p99 latency
  increase in this profile.
- This is now a concrete boundary for the next implementation step: a ROS 2
  sidecar can emit the same contract while real transports carry the bytes.

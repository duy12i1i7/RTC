# Sidecar Runtime V1

## Purpose

This artifact validates the first runtime boundary for FleetRMW:

```text
synthetic ROS-like flow observations
  -> TCP local sidecar API
  -> FleetQoX predictive admission
  -> sidecar decision log
  -> UDP packet emission
  -> UDP receiver metrics
```

This is still a skeleton, not a ROS 2 RMW implementation. The important step is
that decisions are now made by a live process and packets are emitted through a
real socket path. The runtime now supports the same pluggable policy family used
by the sidecar-netem matrix: FIFO, static priority, CSDS, and FleetQoX
predictive admission.

## Commands

Terminal 1:

```bash
python3 -m scripts.udp_trace_receiver \
  --output results_sidecar_runtime/runtime_v1_received.jsonl \
  --host 127.0.0.1 \
  --port 9201 \
  --idle-timeout-s 2 \
  --max-runtime-s 30
```

Terminal 2:

```bash
python3 -m scripts.run_sidecar_runtime \
  --listen-host 127.0.0.1 \
  --listen-port 8765 \
  --udp-host 127.0.0.1 \
  --udp-port 9201 \
  --policy fleetqox_predictive \
  --decision-log results_sidecar_runtime/runtime_v1_decisions.jsonl \
  --idle-timeout-s 20 \
  --max-runtime-s 30
```

Terminal 3:

```bash
python3 -m scripts.feed_sidecar_synthetic \
  --host 127.0.0.1 \
  --port 8765 \
  --scenario runtime_v1_smoke \
  --robots 10 \
  --seconds 2 \
  --seed 7 \
  --capacity-bytes-per-second 120000 \
  --json

python3 -m scripts.analyze_sidecar_runtime \
  --decisions results_sidecar_runtime/runtime_v1_decisions.jsonl \
  --received results_sidecar_runtime/runtime_v1_received.jsonl \
  --output results_sidecar_runtime/runtime_v1_metrics.jsonl
```

## Artifacts

| artifact | path |
| --- | --- |
| Runtime decision log | `results_sidecar_runtime/runtime_v1_decisions.jsonl` |
| Runtime UDP receive log | `results_sidecar_runtime/runtime_v1_received.jsonl` |
| Runtime metrics | `results_sidecar_runtime/runtime_v1_metrics.jsonl` |

## Results

| metric | value |
| --- | --- |
| accepted flow observations | `1555` |
| emitted UDP packets | `120` |
| received UDP packets | `120` |
| loss ratio | `0.000` |
| deadline miss ratio | `0.000` |
| compacted tx/rx | `77 / 77` |
| p95 latency ms | `0.070` |
| p99 latency ms | `0.125` |

## Interpretation

- The sidecar runtime can make live predictive decisions from ROS-like flow
  observations.
- The decision log uses the same `fleetrmw.sidecar.trace.v1` contract as the
  offline trace exporter.
- `send_compacted` control packets are emitted over UDP as real datagrams.
- The same runtime can be run with FIFO, static priority, CSDS, or predictive
  admission, which enables the Docker/netem comparison matrix.
- The next validation step is to connect this sidecar boundary closer to ROS 2
  `rmw` execution and compare it against static trace replay and ROS 2 RMW
  baselines.

# Docker / netem Trace Emulation

This harness runs FleetQoX packet traces through real Linux UDP sockets inside
Docker containers. It applies `tc netem` to the sender interface so that traces
experience delay, jitter, loss, and rate limits in the Linux network stack.

It is not a replacement for ns-3/OMNeT++. It is the T2E integration layer:

```text
CSV packet trace
  -> UDP sender container
  -> tc netem
  -> Docker bridge network
  -> UDP receiver container
  -> received JSONL
  -> analyzer metrics
```

## Generate Input

```bash
python3 -m scripts.export_traces \
  --scenario warehouse_50_constrained \
  --format csv \
  --output-dir traces
```

## Run Through Docker/netem

```bash
TRACE_FILE=traces/warehouse_50_constrained.csv \
RESULT_FILE=results_t2e/received.jsonl \
NETEM_DELAY_MS=20 \
NETEM_JITTER_MS=5 \
NETEM_LOSS_PERCENT=1 \
NETEM_RATE_MBIT=20 \
docker compose -f external/docker-netem/docker-compose.yml up --build --abort-on-container-exit
```

Then analyze:

```bash
python3 -m scripts.analyze_udp_trace \
  --trace traces/warehouse_50_constrained.csv \
  --received results_t2e/received.jsonl
```

## Run Live Sidecar Through Docker/netem

```bash
python3 -m scripts.run_sidecar_netem \
  --run \
  --analyze \
  --scenario sidecar_netem_v1 \
  --robots 10 \
  --seconds 2 \
  --delay-ms 20 \
  --jitter-ms 5 \
  --loss-percent 1 \
  --rate-mbit 20
```

This path uses `docker-compose.sidecar.yml`:

```text
synthetic feeder -> TCP sidecar -> UDP over tc netem -> receiver
```

To compare runtime policies under the same impairment profile:

```bash
python3 -m scripts.run_sidecar_netem \
  --run \
  --analyze \
  --scenario sidecar_netem_matrix_v1 \
  --all-policies \
  --robots 10 \
  --seconds 2 \
  --delay-ms 20 \
  --jitter-ms 5 \
  --loss-percent 1 \
  --rate-mbit 20 \
  --output-dir results_sidecar_netem_matrix
```

The matrix currently runs:

- `fifo`;
- `static_priority`;
- `fleetqox_csds`;
- `fleetqox_predictive`;
- `fleetqox_predictive_guarded`;
- `fleetqox_predictive_lagrangian`.

The combined metrics file is
`results_sidecar_netem_matrix/sidecar_netem_matrix_v1_matrix_metrics.jsonl`.

To run the same sidecar path with closed-loop age feedback:

```bash
python3 -m scripts.run_sidecar_netem \
  --run \
  --analyze \
  --scenario sidecar_netem_closed_loop_v1 \
  --all-policies \
  --closed-loop-feed \
  --robots 10 \
  --seconds 2 \
  --delay-ms 20 \
  --jitter-ms 5 \
  --loss-percent 1 \
  --rate-mbit 20 \
  --output-dir results_sidecar_netem_closed_loop
```

Closed-loop feeding sends `include_feedback=true` batches to the sidecar and
uses returned per-flow actions to update the next observation age.

To run a labeled Lagrangian variant without editing code:

```bash
python3 -m scripts.run_sidecar_repeated_netem \
  --run \
  --scenario-prefix sidecar_lag012_v1 \
  --policy fleetqox_predictive_lagrangian \
  --policy-label lag_012 \
  --lagrangian-deadline-risk-budget 0.08 \
  --lagrangian-initial-deadline-lambda 1.8 \
  --lagrangian-risk-barrier-start 0.62 \
  --lagrangian-risk-barrier-scale 12.0 \
  --lagrangian-deadline-drop-risk 0.45 \
  --seeds 7,13 \
  --closed-loop-feed \
  --output-dir results_sidecar_repeated/lag_variants_v1
```

The sidecar compose file forwards `SIDECAR_POLICY_LABEL` and
`SIDECAR_LAGRANGIAN_*` environment variables into the runtime container, so
variant labels appear directly in metric JSONL rows.

## Notes

- The sender service needs `NET_ADMIN` to apply `tc netem`.
- Docker Desktop may require elevated network capabilities or may not support
  all qdisc behavior identically to native Linux.
- Use this layer to test real socket and container behavior. Use ns-3/OMNeT++
  for higher-fidelity wireless/5G/mesh claims.

# RMW Multi-Robot Live Stochastic Netem Matrix V1

This artifact is the stochastic-loss companion to the deterministic live netem
matrix.

- Script: `scripts/run_rmw_docker_multi_robot_live_stochastic_netem_matrix.py`
- Summary:
  `results_rmw_socket/docker_multi_robot_live_stochastic_netem_matrix_summary.json`
- Report:
  `results_rmw_socket/docker_multi_robot_live_stochastic_netem_matrix_report.md`
- Schema: `fleetrmw.rmw_multi_robot_live_stochastic_netem_matrix.v1`
- Default loss scale: `0.1`

## Meaning

The deterministic netem matrix validates that real qdisc delay, jitter, and rate
shaping are wired into the ROS 2/RMW live path. This stochastic matrix turns on
random packet loss through:

```text
loss random <profile_loss * netem_loss_scale>%
```

It preserves the same topology, pass conditions, and telemetry as
`RMW_MULTI_ROBOT_LIVE_NETEM_MATRIX_V1`, with one stochastic-loss exception:
control de-duplication is reported but not required. Under random loss, one
redundant copy can be dropped while the other still delivers the sample, so
zero de-duplication does not imply double delivery or lost delivery.

## Seed Semantics

The `--seeds` values are repetition identifiers recorded in the summary. The
current `tc netem` build in `localhost/fleetrmw/rmw-netem:jazzy` rejects a
`seed` argument, so packet-loss RNG cannot be forced from this runner. Treat
multi-seed results as repeated stochastic trials, not deterministic replay.

## Example

```bash
python3 scripts/run_rmw_docker_multi_robot_live_stochastic_netem_matrix.py \
  --image localhost/fleetrmw/rmw-netem:jazzy \
  --profiles wifi,wan,roaming \
  --seeds 7 \
  --require-netem \
  --netem-loss-scale 0.1 \
  --netem-drain-s 2.0
```

The next research step is to increase repetitions and loss scales until the
current ACK/NACK retransmission boundary exposes its failure envelope. The
dedicated sweep runner for that is
`scripts/run_rmw_docker_multi_robot_live_stochastic_netem_sweep.py`.

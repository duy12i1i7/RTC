# RMW Multi-Robot Live Stochastic Netem Sweep V1

This artifact sweeps stochastic `tc netem` packet-loss multipliers over the
live ROS 2/RMW multi-robot path to expose the current reliability envelope.

- Script: `scripts/run_rmw_docker_multi_robot_live_stochastic_netem_sweep.py`
- Summary:
  `results_rmw_socket/docker_multi_robot_live_stochastic_netem_sweep_summary.json`
- Report:
  `results_rmw_socket/docker_multi_robot_live_stochastic_netem_sweep_report.md`
- Schema: `fleetrmw.rmw_multi_robot_live_stochastic_netem_sweep.v1`
- Default loss scales: `0.1`, `0.25`, `0.5`
- Optional build reuse: `--reuse-build`

## Scope

Each loss scale runs the stochastic netem matrix over the selected profiles and
repetition IDs. A row still uses the real Docker RMW topology:

- RMW publisher/router/subscriber containers;
- `primary_wifi` and `backup_5g` qdisc shaping;
- host-side QoS/QoE path-plan controller;
- redundant control and unicast state routing.

With `--reuse-build`, the runner builds `rmw_fleetqox_cpp` once for the whole
sweep, reuses the install directory across loss-scale/profile/seed rows, and
cleans the build/install/log directories at the end. The sweep summary records
`reuse_build` and campaign-level `build_performed`; each row also records
whether its probe reused the cached install or performed its own build.

The sweep records:

- per-run pass/fail;
- per-run `failure_kind`, separating harness, qdisc, component, telemetry, and
  delivery failures;
- qdisc application status;
- mean control/state delivery latency;
- control redundant frame count;
- duplicate data-frame de-duplication;
- first failed loss scale by profile;
- maximum tested loss scale where every profile had an OK run.

## Status Semantics

`ok` means all rows passed. `partial` means the runner completed and at least
one tested operating point failed. `failed` means no row passed.

This is intentional: a `partial` sweep is useful research evidence because it
identifies the failure boundary.

Failure kinds are intentionally coarse:

- `harness_exception`: a Docker/colcon/subprocess command failed before a full
  component snapshot was available;
- `netem_not_applied`: the row required qdisc shaping, but at least one router
  path did not apply `tc netem`;
- `component_failed`: a publisher, subscriber, or router process returned a
  non-zero code or emitted a failed JSON status;
- `delivery_failed`: the live RMW path completed, but the subscriber did not
  receive all required control/state payloads;
- `telemetry_missing`: delivery evidence was insufficient because router or
  subscriber telemetry was incomplete;
- `contract_evidence_failed`: delivery completed, but a deterministic
  duplicate-ACK or de-duplication evidence requirement was not met;
- `harness_exception_missing_diagnostics`: an older/partial row had no
  component snapshot and no exception tail.

Exception rows carry `failure_phase`, `failure_returncode`, stdout/stderr
excerpts, and container-log excerpts so infrastructure faults do not masquerade
as algorithmic delivery failures.

Control duplicate de-duplication and duplicate ACK reception are reported
metrics, not stochastic-loss pass requirements. A random drop can remove one
redundant copy or one ACK duplicate while the other path still delivers the
command sample. For positive stochastic loss scales, publisher
`min_ack_nack_received` and router `expected_ack_nack_forwarded` evidence
thresholds are likewise recorded rather than used as pass gates; end-to-end
payload delivery, telemetry completeness, component liveness, and qdisc
application remain required.

State traffic uses a small proactive repair repeat in positive stochastic
netem rows. This addresses terminal sample loss, where pure gap-based NACK
cannot fire because no later frame arrives to reveal the missing sequence. The
RMW subscriber de-duplicates repeated frames before application delivery, and
the sweep reports `state_duplicate_data_frames_deduped` and state duplicate ACK
counts as the cost of this repair.

## Seed Semantics

The `--seeds` values are repetition IDs. The current
`localhost/fleetrmw/rmw-netem:jazzy` image's `tc netem` rejects explicit RNG
seeding, so repeated rows are stochastic trials rather than deterministic
packet-loss replay.

## Example

```bash
python3 scripts/run_rmw_docker_multi_robot_live_stochastic_netem_sweep.py \
  --image localhost/fleetrmw/rmw-netem:jazzy \
  --profiles wifi,wan,roaming \
  --seeds 7,13,29 \
  --loss-scales 0.1,0.25,0.5 \
  --require-netem \
  --netem-drain-s 2.0 \
  --reuse-build
```

The next step after this sweep is to either raise loss until failures appear,
or widen the same sweep across more robots and baseline RMWs.

# RMW Multi-Robot Live Stochastic Netem Ablation V1

This artifact compares proactive repair policies over the same live ROS 2/RMW
multi-robot stochastic netem sweep.

- Script: `scripts/run_rmw_docker_multi_robot_live_stochastic_netem_ablation.py`
- Summary:
  `results_rmw_socket/docker_multi_robot_live_stochastic_netem_ablation_summary.json`
- Report:
  `results_rmw_socket/docker_multi_robot_live_stochastic_netem_ablation_report.md`
- Schema: `fleetrmw.rmw_multi_robot_live_stochastic_netem_ablation.v1`
- Default modes: `none`, `state_only`, `control_state`
- Optional build reuse: `--reuse-build`

## Purpose

The stochastic netem sweep exposes a reliability envelope for one repair
configuration. The ablation makes the evidence comparative by holding the
topology, topics, profiles, seeds, and loss scales constant while changing only
the proactive data-frame repeat policy.

This is the minimum controlled experiment needed before claiming that proactive
repair improves fleet-scale QoS/QoE rather than merely passing one tuned row.

## Modes

- `none`: no proactive data-frame repeats. Delivery can only recover when a
  later frame reveals a gap and triggers ACK/NACK feedback.
- `state_only`: repeat state frames once while leaving urgent control on
  gap-triggered ACK/NACK only.
- `control_state`: repeat both urgent control and state frames once under
  stochastic loss.
- `auto`: optional mode that delegates repeat counts to the probe default.

The key research question is whether terminal-loss repair improves delivery
resilience enough to justify duplicate-frame and duplicate-ACK overhead.

## Metrics

Each mode records:

- pass/fail and `failure_kind` for every profile/seed/loss row;
- qdisc application evidence;
- maximum tested loss scale where every profile has an OK row;
- first failed loss scale by profile;
- mean OK-run control/state delivery latency;
- duplicate data frames de-duplicated at the subscriber;
- duplicate ACKs received by the publisher;
- repair cost, computed from duplicate data-frame and duplicate-ACK evidence.

The report ranks modes by:

1. delivery success ratio;
2. strongest all-profile loss boundary;
3. lower OK-run control/state latency;
4. lower repair overhead.

## Status Semantics

`ok` means the ablation completed and at least one mode produced a successful
row. Individual mode sweeps can still be `partial`; that is expected when an
ablation intentionally pushes weaker repair policies past their boundary.

`failed` means no mode produced a successful row, or the campaign could not
produce usable evidence.

## Example

```bash
python3 scripts/run_rmw_docker_multi_robot_live_stochastic_netem_ablation.py \
  --image localhost/fleetrmw/rmw-netem:jazzy \
  --profiles wifi,wan,roaming \
  --seeds 7,13,29 \
  --loss-scales 0.1,0.25,0.5 \
  --modes none,state_only,control_state \
  --require-netem \
  --netem-drain-s 2.0 \
  --reuse-build
```

For a quick smoke:

```bash
python3 scripts/run_rmw_docker_multi_robot_live_stochastic_netem_ablation.py \
  --image localhost/fleetrmw/rmw-netem:jazzy \
  --profiles wifi \
  --seeds 7 \
  --loss-scales 0.25 \
  --modes none,control_state \
  --require-netem \
  --netem-drain-s 2.0 \
  --reuse-build \
  --summary-json results_rmw_socket/docker_multi_robot_live_stochastic_netem_ablation_smoke_summary.json \
  --markdown results_rmw_socket/docker_multi_robot_live_stochastic_netem_ablation_smoke_report.md \
  --json
```

## Interpretation

This ablation turns the current repair policy into a falsifiable systems claim:
if `control_state` only matches `none`, proactive repair is not justified; if it
extends the all-profile loss boundary with tolerable duplicate overhead, it
becomes a concrete FleetRMW contribution. The next research step is to add
baseline RMW rows under the same profiles and then widen the fleet scale.

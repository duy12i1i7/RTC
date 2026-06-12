# RMW Multi-Robot QoS Scheduler V1

## Purpose

This milestone moves FleetRMW deadline scheduling from two-topic and
single-action probes to a concurrent fleet-shaped ROS 2 workload. Each robot
publishes a control flow and a state flow through `rmw_fleetqox_cpp`; matching
subscribers receive them through one shared router.

The experiment compares:

- FIFO forwarding with no scheduler window;
- an online deadline-gated scheduler over the same ordered publication
  workload.

The scheduler has two phases. Frames with a deadline at or below the configured
urgent threshold are forwarded immediately. Non-urgent frames are held briefly,
sorted by absolute deadline, and drained with pacing so a bulk/state burst does
not destroy downstream QoE under a shaped link.

## Fleet Identity

`rmw_pubsub.cpp` now reads `FLEETQOX_RMW_ROBOT_ID` when constructing each
`fleetrmw.data_frame.v1`. The default remains `local`, preserving existing
single-host behavior.

This closes an important fleet observability gap: `DataFrame.robot_id` is now a
real scheduling and telemetry dimension rather than a constant placeholder.

## Router Telemetry

`fleetrmw_udp_router_probe` now reports:

- `scheduler_queued_frames`;
- `scheduler_urgent_frames`;
- `scheduler_paced_frames`;
- `scheduler_drain_pacing_ms`;
- `scheduler_forwarded_frames`;
- `scheduler_deadline_misses`;
- mean and maximum scheduler queue wait;
- per-robot forwarded and deadline-miss counts;
- Jain fairness over per-robot deadline successes.

Deadline misses are evaluated against the publisher's monotonic source
timestamp plus the deadline learned from its graph advertisement. The endpoint
probe also reports `take_age_ms`, so the matrix can compare end-to-end receive
age, not just router ordering.

## Docker Matrix

`scripts/run_rmw_docker_router_multi_robot_qos_matrix.py` builds one FleetRMW
workspace and executes two rows. The default workload contains four robots and
eight flows:

- `/fleetqox/robot_N/control`, deadline `5000 ms`;
- `/fleetqox/robot_N/state`, deadline `20000 ms`.

The publishers intentionally emit control then state for each robot. Therefore
the FIFO row preserves the interleaved arrival order, while the scheduler row
must forward every urgent control flow before draining held state flows.

The row is accepted only when:

- all eight real RMW publishers succeed;
- all eight real RMW subscribers take the expected payload;
- the router forwards exactly eight logical frames;
- the deadline row forwards urgent control immediately and queues state;
- every robot receives two frames with zero deadline misses;
- deadline-success Jain fairness is `1.0`;
- the deadline order improves over FIFO.

`scripts/run_rmw_docker_router_multi_robot_qos_netem_matrix.py` repeats the
same contract under real `tc netem` Wi-Fi, WAN, and roaming profiles. This row
uses generated payloads inside the probe binary, avoiding shell argument-size
limits while still sending large state/bulk payloads over the RMW data plane.

## Current Evidence

Latest Docker/netem gate:

```bash
python3 scripts/run_rmw_docker_router_multi_robot_qos_netem_matrix.py \
  --image localhost/fleetrmw/rmw-netem:jazzy \
  --robot-count 8 \
  --summary-json results_rmw_socket/docker_router_multi_robot_qos_netem_matrix_summary.json
```

Observed result:

| profile | FIFO control p95 ms | scheduler control p95 ms | raw delta ms | adaptive policy | adaptive delta ms | scheduler state p95 ms | deadline miss | fairness |
|---|---:|---:|---:|---|---:|---:|---:|---:|
| Wi-Fi | 36.070 | 34.900 | +1.169 | deadline-gated holdback | +1.169 | 1096.360 | 0 | 1.0 |
| WAN | 94.874 | 93.991 | +0.883 | deadline-gated holdback | +0.883 | 1162.050 | 0 | 1.0 |
| roaming | 158.036 | 159.904 | -1.868 | FIFO | +0.000 | 1210.220 | 0 | 1.0 |

The matrix status is `ok`: every profile applied real `tc netem`, every
scheduler row forwarded `8` urgent control frames and queued `8` state frames,
all `16/16` subscribers received their payloads, deadline misses were zero, and
per-robot deadline-success fairness was `1.0`.

Raw deadline-gated holdback is not universally better for control p95. The
netem wrapper therefore now records a first adaptive-admission decision: choose
`deadline_gated_holdback` only when the scheduler row is evidence-valid, control
p95 is not worse than FIFO, and state p95 remains inside the state deadline.
In this run the adaptive selector chose holdback for Wi-Fi and WAN, FIFO for
roaming, reported `adaptive_worse_profile_count=0`, and raised mean control
p95 reduction from `+0.061 ms` raw to `+0.684 ms` admitted. That is the key
contract: raw holdback is a candidate, while the admitted policy is prevented
from carrying losing rows forward.

## Live Router Admission

The follow-on live router gate moves the decision into
`fleetrmw_udp_router_probe` with
`--scheduler-admission-policy slo_service_epoch`. For each non-urgent frame,
the router estimates link service time from the encoded frame size and measured
link capacity, normalizes it by the urgent control deadline, smooths that
service-ratio signal with EWMA, and applies separate enter/exit thresholds plus
a minimum epoch length before changing holdback mode. The policy is therefore
expressed in SLO-normalized link cost rather than profile names, and it avoids
per-frame flip-flopping.

Latest live gate:

```bash
python3 scripts/run_rmw_docker_router_multi_robot_qos_live_adaptive_matrix.py \
  --image localhost/fleetrmw/rmw-netem:jazzy \
  --robot-count 8 \
  --summary-json results_rmw_socket/docker_router_multi_robot_qos_live_adaptive_matrix_summary.json
```

Observed result:

| profile | live policy | FIFO control p95 ms | adaptive control p95 ms | delta ms | queued | bypassed | epoch samples | switches | EWMA ratio | deadline miss | fairness |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| Wi-Fi | FIFO | 36.173 | 34.060 | +2.113 | 0 | 8 | 8 | 0 | 0.0161 | 0 | 1.0 |
| WAN | deadline-gated holdback | 105.090 | 104.014 | +1.076 | 8 | 0 | 8 | 1 | 0.0322 | 0 | 1.0 |
| roaming | deadline-gated holdback | 144.013 | 132.138 | +11.875 | 8 | 0 | 8 | 1 | 0.0644 | 0 | 1.0 |

The live matrix status is `ok`: it exercised both admission branches
(`queued_profile_count=2`, `bypassed_profile_count=1`), preserved zero deadline
misses and per-robot fairness `1.0`, and kept mean control p95 reduction
positive at `5.021 ms`. WAN and roaming each switched into holdback once;
Wi-Fi stayed in bypass mode because its EWMA service ratio remained below the
enter threshold.

## Repeated-Loss Smoke

`scripts/run_rmw_docker_router_multi_robot_qos_live_adaptive_repeated_loss_matrix.py`
wraps the same live admission policy over repetition IDs and explicit
`tc netem` loss percentages. Seed values are recorded as repetition IDs because
the current RMW Docker image does not expose deterministic `tc netem` RNG
seeding.

Latest smoke:

```bash
python3 scripts/run_rmw_docker_router_multi_robot_qos_live_adaptive_repeated_loss_matrix.py \
  --image localhost/fleetrmw/rmw-netem:jazzy \
  --profiles wifi,roaming \
  --repetitions 7 \
  --loss-percents 0.02 \
  --robot-count 8 \
  --summary-json results_rmw_socket/docker_router_multi_robot_qos_live_adaptive_repeated_loss_matrix_summary.json
```

Observed result:

| profile | loss % | policy | FIFO control p95 ms | adaptive control p95 ms | delta ms | queued | bypassed | epoch samples | switches |
|---|---:|---|---:|---:|---:|---:|---:|---:|---:|
| Wi-Fi | 0.02 | FIFO | 34.144 | 33.012 | +1.132 | 0 | 8 | 8 | 0 |
| roaming | 0.02 | deadline-gated holdback | 157.947 | 146.006 | +11.941 | 8 | 0 | 8 | 1 |

The repeated-loss smoke status is `ok`: `2/2` rows passed, both admission
branches were exercised, qdisc showed `loss 0.02%`, and mean control p95
reduction was `6.536 ms`.

## Scheduled ACK/NACK Repair

`scripts/run_rmw_docker_router_scheduled_reliability_probe.py` verifies that
ACK/NACK repair still works when the data path is routed through a scheduler
window. The router intentionally drops source sequence `2` on first arrival,
queues scheduled data frames with `--scheduler-window-ms 150`, forwards
ACK/NACK feedback, and then forwards the publisher's retransmission through the
same scheduled data path.

Latest probe:

```bash
python3 scripts/run_rmw_docker_router_scheduled_reliability_probe.py \
  --image localhost/fleetrmw/rmw-netem:jazzy \
  --summary-json results_rmw_socket/docker_router_scheduled_reliability_probe_summary.json
```

Observed result:

- status `ok`;
- router `test_dropped_frames=1`;
- router `ack_nack_forwarded=3`;
- router `scheduler_queued_frames=4`;
- router `scheduler_forwarded_frames=4`;
- publisher `nack_retransmissions=2`;
- subscriber recovered payloads `one`, `three`, `two`.

## Repeated-Loss Scheduled Repair

`scripts/run_rmw_docker_router_scheduled_reliability_repeated_loss_matrix.py`
extends the scheduled repair probe across netem profiles, repetition IDs, and
explicit loss percentages. Each row requires qdisc evidence, the intentional
source-sequence drop, forwarded ACK/NACK feedback, scheduler queue/forward
counters, publisher retransmission, and recovery of all three payloads.

Latest smoke:

```bash
python3 scripts/run_rmw_docker_router_scheduled_reliability_repeated_loss_matrix.py \
  --image localhost/fleetrmw/rmw-netem:jazzy \
  --profiles wifi,roaming \
  --repetitions 7 \
  --loss-percents 0.02 \
  --summary-json results_rmw_socket/docker_router_scheduled_reliability_repeated_loss_matrix_summary.json
```

Both rows pass. Each profile records one intentional router drop, two publisher
retransmissions, four queued and forwarded scheduler frames, zero scheduler
deadline misses, and subscriber recovery of `one`, `three`, `two`. Across the
matrix the router forwards `12` ACK/NACK frames and the publisher performs `4`
NACK-driven retransmissions.

The first netem run exposed a testbed lifecycle error: router forwarding
counters reached their terminal condition while the final repaired packet was
still queued in the kernel qdisc. The probe now derives a post-satisfaction
drain horizon for netem rows. This preserves the original delivery criteria
while preventing container teardown from discarding already-forwarded packets.

## Concurrent Multi-Robot Scheduled Repair

`scripts/run_rmw_docker_router_multi_robot_scheduled_reliability_probe.py`
runs independent ROS 2 publisher/subscriber pairs concurrently through one
scheduled router. Source sequence `2` is dropped once per publisher identity,
so ACK/NACK routing, retransmit history, scheduling, and payload recovery are
validated independently for every robot rather than inferred from aggregate
counters.

Latest smoke:

```bash
python3 scripts/run_rmw_docker_router_multi_robot_scheduled_reliability_probe.py \
  --image localhost/fleetrmw/rmw-netem:jazzy \
  --robot-count 4 \
  --netem-profile roaming \
  --netem-loss-percent 0.02 \
  --summary-json results_rmw_socket/docker_router_multi_robot_scheduled_reliability_probe_summary.json
```

The roaming row (`95 +/- 20 ms`, `5 Mbit`, `loss 0.02%`) passes `4/4` robots.
The router receives `20` data frames, deliberately drops `4`, queues and
forwards `16`, forwards `32` ACK/NACK frames, and records zero scheduler
deadline misses. Every robot receives four scheduled frames, recovers
`one`, `three`, `two`, and performs two NACK-driven retransmissions. Per-robot
deadline-success Jain fairness is `1.0`.

## Remaining Gap

This is concurrent live-netem evidence for reliable control-like topics, not
yet a fleet-scale mixed-workload claim. The next step is to integrate repaired
reliability with simultaneous action/control/state traffic and measure its
cross-class QoS/QoE tradeoff.

## Mixed Workload Closure

The first mixed-workload slice is now complete in
`scripts/run_rmw_docker_router_mixed_action_control_state_probe.py`. Two robots
each run one control and one state repair flow while a real ROS 2 action runs a
successful goal and a canceled goal through the same router under roaming
netem (`95 +/- 20 ms`, `5 Mbit`, `loss 0.02%`). The router applies topic-scoped
sequence loss only to `/fleetqox/mixed/`, schedules all `/fleetqox/` data, and
records both urgent and queued branches.

The row passes with `4/4` reliable flows, successful action completion, `4`
intentional drops, `46` forwarded ACK/NACK frames, `17` urgent frames, `8`
queued frames, and `25` scheduled forwards. Deadline telemetry now separates
fresh and repair samples: fresh misses are `0`; four sequence-`2` control
repairs miss their original deadline by about `167-196 ms`. This is the
measured boundary between hard real-time QoS and post-loss delivery QoE.

`scripts/run_rmw_docker_router_proactive_deadline_diversity_probe.py` then
protects the hard-deadline side proactively. A deadline-critical publisher
uses `adaptive_qos` over a roaming primary and Wi-Fi backup. The repeated-loss
wrapper passes `2/2` rows: every sequence is on time, primary sequence `2` is
dropped in both rows, maximum latency is `63.688 ms`, six frames are sent
redundantly, and no NACK retransmission is required.

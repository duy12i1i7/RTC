# FleetRMW Completion Backlog

This backlog records the remaining work needed to turn the current
FleetRMW/FleetQoX research prototype into a complete, defensible ROS 2 RMW
project. It is ordered by dependency and regression value.

## Current Baseline

- The Python/dependency-free suite passes locally and on the `udy` runner:
  `428` unit tests.
- The ROS 2 sidecar path has repeated four-robot and eight-robot hard-SLO
  evidence with source-sequence ACK/NACK, liveliness-backed retransmit horizon,
  QoE quota recovery, and typed projection feedback.
- `rmw_fleetqox_cpp` has a working ROS 2 RMW skeleton with serialized and typed
  pub/sub, introspection-C message serialization, ROS CLI topic pub/echo,
  topic/node/service graph discovery, SetBool request/response, queue
  QoS/lifespan checks, stale service request/response drops, ACK/NACK
  retransmission, C-level service no-response/malformed-response error checks,
  a dependency-light action-frame contract, router-mediated reliability,
  multi-hop routing, path diversity, adaptive routing, and live fleet-plan
  routing probes.
- The strongest native stochastic netem evidence is the `control_state` repair
  mode: all `27/27` mode rows pass across Wi-Fi, WAN, roaming, seeds
  `7,13,29`, and loss scales `0.1,0.25,0.5`.
- The matched four-robot FleetRMW router/redundancy matrix passes `9/9` rows,
  but direct DDS/Zenoh rows remain single-path, so the comparison map still has
  `direct_claim_allowed=false`.

## P0: Make The RMW ABI Complete Enough For Real ROS 2 Workloads

- Expand C++ type-support-backed serialization/deserialization beyond the
  current introspection-C CLI matrix.
- Add regression coverage for more ROS message shapes: bounded/unbounded
  sequences, nested arrays, time/duration-heavy messages, and common Nav2/RMF
  message families.
- Complete service timeout, cancellation, stale request/response, and error
  semantics instead of only proving the successful SetBool path.
- Implement action transport on top of pub/sub plus service reliability:
  goal, result, feedback, cancel, and status.
- Add lifecycle/Nav2 action smoke tests that use `rmw_fleetqox_cpp` as the
  selected RMW.
- Replace or deliberately scope optional ABI stubs for events, dynamic
  messages, content-filtered topics, loaned messages, network-flow endpoints,
  and callbacks.

## P1: Move The Sidecar Hard-SLO Contract Fully Into FleetRMW

- Preserve publisher identity, source sequence, source timestamp, effective
  wire lifespan, source lifespan, liveliness lease, and recovery horizon at the
  C++ publish/take boundary.
- Keep ACK/NACK backpressured and source-sequence based; urgent out-of-band
  NACK remains a negative-control path unless new evidence justifies it.
- Run the eight-robot liveliness ACK-horizon ROS 2 bridge as the regression
  gate while transferring semantics into `rmw_fleetqox_cpp`.
- Add larger live rows such as `16` robots and longer profile-transition
  segments after the eight-robot gate remains stable.

## P2: Equalize Baselines For A Paper-Grade Claim

- Make the comparison topology and metrics equivalent across
  `rmw_fleetqox_cpp`, Fast DDS, Cyclone DDS, and Zenoh.
- Either run DDS/Zenoh through comparable router/repair semantics, or expose
  equivalent terminal-horizon, ACK/NACK, route-control, QoE, and robot-SLO
  metrics on the direct-RMW side.
- Keep the current baseline report as a gap register until
  `direct_claim_allowed=true` is defensible.
- Preserve qdisc evidence, profile/seed parity, robot/topic count parity, and
  per-topic delivery metrics in every baseline row.

## P3: Scale The Network-Aware QoS/QoE Plane

- Run the current N-topic controller-scale workload through live Docker
  router/subscriber probes with real `tc netem` shaping.
- Record duplicate/de-duplication, QoE feedback, robot-level SLO debt, path
  plan churn, and controller decision latency at larger N.
- Add repeatable ns-3 and OMNeT++ matrices from the existing trace/export
  pipeline.
- Tie simulator, Docker/netem, and network-simulator outputs into one
  reproducible report path.

## P4: Extend The Data Plane

- Add same-host shared-memory transport for local high-rate flows.
- Add UDP/QUIC LAN and QUIC WAN transports with explicit path telemetry.
- Add WebRTC/SVC or equivalent video/operator-observation path semantics.
- Add low-priority bulk-data path and per-plane admission control.
- Make transport selection choose between these planes using measured QoS/QoE,
  not just named packet-format/RMW candidates.

## P5: Production Hardening

- Define supported ROS 2 distributions and Docker images.
- Add CI-friendly test tiers: unit, local socket, Docker ROS smoke,
  Docker/netem matrix, and long benchmark.
- Add failure triage fields for every runner so partial rows are comparable.
- Add documentation for installation, environment variables, runner
  prerequisites, and benchmark reproduction.
- Audit memory ownership, allocator usage, thread shutdown, socket lifecycle,
  graph lease cleanup, and long-running process behavior in `rmw_fleetqox_cpp`.

## Next Work Slice

The first P0 service-freshness/error slice is complete:
`fleetrmw_service_qos_probe` now verifies stale request and response frames are
dropped before application delivery, verifies unknown-response targets fail
without sending a frame, and the Docker probe passes on `udy`.

The first P0 message-shape expansion is also complete: the ROS CLI message
matrix now includes `builtin_interfaces/msg/Time` and
`builtin_interfaces/msg/Duration` in addition to String, Twist, LaserScan, and
Odometry. The next expansion adds `geometry_msgs/msg/PoseStamped` and
`nav_msgs/msg/Path`, proving nested headers/poses and dynamic sequences of
nested messages; the Docker matrix passes `8/8` cases on `udy`.

The first P0 action-frame contract is also complete:
`fleetrmw.action_frame.v1` now round-trips goal, feedback, status, result, and
cancel roles with lifespan checks and service-schema rejection, and the Docker
action-frame probe passes on `udy`.

The first P0 router-mediated action transport slice is also complete:
`fleetrmw_udp_router_probe` now learns `action_server` and `action_client`
graph routes, forwards `goal/cancel` to action servers, forwards
`feedback/status/result` to action clients, and
`run_rmw_docker_router_action_frame_probe.py` passes on `udy` with
`action_frames=5`, `action_forwarded=5`, `graph_action_servers=1`, and
`graph_action_clients=1`.

The first real action API smoke is also complete:
`run_rmw_docker_rclpy_action_probe.py` runs a same-process
`rclpy.action.ActionServer` and `ActionClient` with
`tf2_msgs/action/LookupTransform` over `rmw_fleetqox_cpp`; the Docker probe
passes on `udy` with server discovery, accepted goal, execute callback, and
GetResult response status `4` (`SUCCEEDED`).

The first router-mediated real action operation smoke is also complete:
`run_rmw_docker_router_rclpy_action_probe.py` runs the `rclpy.action` server and
client in separate Docker containers that peer only with
`fleetrmw_udp_router_probe`; the Docker probe passes on `udy` with accepted
success and cancel goals, feedback callbacks for both goals, status samples,
GetResult status `4` (`SUCCEEDED`) for the first goal, cancel result status `5`
(`CANCELED`) for the second, and router `service_frames=10` /
`service_forwarded=10`. The probe also verifies
`ActionClient.server_is_ready()` before send and after result. This closes the
hidden action graph availability gap and the first real feedback/status/cancel
coverage gap.

The first real action observation-QoS slice is complete:
`run_rmw_docker_router_rclpy_action_qos_probe.py` compares a fresh row
(`1 ms` router delay, `100 ms` lifespan) with an expired row (`30 ms` delay,
`5 ms` lifespan). The fresh row delivers feedback/status; the expired row
drops `2` feedback and `7` status frames by topic while preserving successful
and canceled action results. A third deadline row scopes a three-frame burst to
the action topic prefix and forwards feedback deadline `5 ms` before status
deadline `100 ms`.

The first fleet-identity and multi-robot deadline-scheduling slice is complete:
publishers now populate `DataFrame.robot_id` from
`FLEETQOX_RMW_ROBOT_ID`, router telemetry records queue wait, deadline misses,
per-robot delivery, and deadline-success Jain fairness, and
`run_rmw_docker_router_multi_robot_qos_matrix.py` compares FIFO with
online deadline-gated scheduling over real control/state publishers and
subscribers. The scheduler forwards urgent control immediately, holds
non-urgent state briefly, and paces the drain to avoid bulk bursts under
roaming-rate netem. The Wi-Fi/WAN/roaming netem gate passes with `8` robots
and `16` flows: all rows have zero deadline misses and fairness `1.0`.
The first adaptive admission evidence is now recorded in
`run_rmw_docker_router_multi_robot_qos_netem_matrix.py`: the paired-row selector
chooses FIFO when holdback hurts control p95 and chooses
`deadline_gated_holdback` only for admitted profiles. The latest raw/admitted
run selected holdback for Wi-Fi/WAN, FIFO for roaming, kept
`adaptive_worse_profile_count=0`, and raised mean control p95 reduction from
`+0.061 ms` raw to `+0.684 ms` admitted. The follow-on live router admission
slice is also complete:
`fleetrmw_udp_router_probe` now supports
`--scheduler-admission-policy slo_service_epoch`, estimates each non-urgent
frame's SLO-normalized link service cost, smooths the signal with EWMA, and
uses enter/exit thresholds plus a minimum epoch length before switching
holdback mode. The latest live Wi-Fi/WAN/roaming gate exercised both branches
(`queued_profile_count=2`, `bypassed_profile_count=1`), preserved zero deadline
misses and fairness `1.0`, recorded `8` epoch samples per profile, switched
once into holdback for WAN and roaming, and kept mean control p95 reduction
positive at `5.021 ms`.

The first repeated-loss live adaptive smoke is complete:
`run_rmw_docker_router_multi_robot_qos_live_adaptive_repeated_loss_matrix.py`
runs the same `slo_service_epoch` policy over repetition IDs and explicit
`tc netem` loss percentages. The latest Wi-Fi/roaming smoke with `8` robots,
`16` flows, repetition `7`, and `loss 0.02%` passes `2/2` rows, exercises both
branches (`bypassed_run_count=1`, `queued_run_count=1`), and records mean
control p95 reduction `6.536 ms`. The runner also supports `partial` status for
true stochastic delivery loss, making it a gap register for the next ACK/NACK
repair integration rather than hiding loss-induced failures.

The first scheduled ACK/NACK repair slice is complete:
`run_rmw_docker_router_scheduled_reliability_probe.py` runs
`fleetrmw_reliable_interprocess_probe` through `fleetrmw_udp_router_probe` with
`--scheduler-window-ms 150`, deliberately drops source sequence `2`, forwards
`3` ACK/NACK frames, and verifies publisher retransmission through the
scheduled data path. The latest Docker probe passes with router
`scheduler_queued_frames=4`, `scheduler_forwarded_frames=4`,
`test_dropped_frames=1`, publisher `nack_retransmissions=2`, and subscriber
payload recovery `one`, `three`, `two`.

The first repeated-loss scheduled repair smoke is complete:
`run_rmw_docker_router_scheduled_reliability_repeated_loss_matrix.py` runs the
same repair contract under Wi-Fi and roaming qdiscs with `loss 0.02%`. The
latest repetition-`7` artifact passes `2/2` rows, applies qdisc in both rows,
records `2` intentional drops, `12` forwarded ACK/NACK frames, `8` scheduled
forwards, `4` publisher retransmissions, zero scheduler deadline misses, and
full payload recovery. The probe also keeps the router alive for a derived
post-satisfaction drain horizon so a netem-delayed repaired packet is not lost
when the container reaches its internal counter target.

The first concurrent multi-robot scheduled repair slice is complete:
`run_rmw_docker_router_multi_robot_scheduled_reliability_probe.py` launches
four independent ROS 2 publisher/subscriber pairs through one router under the
roaming qdisc (`95 +/- 20 ms`, `5 Mbit`, `loss 0.02%`). The latest artifact
passes `4/4` robots, drops source sequence `2` independently for all four
publisher identities, forwards `32` ACK/NACK frames and `16` scheduled data
frames, performs `8` retransmissions, recovers every payload set, has zero
scheduler deadline misses, and records Jain fairness `1.0`.

The first real mixed action/control/state slice is complete:
`run_rmw_docker_router_mixed_action_control_state_probe.py` executes a real
`rclpy.action` success/cancel lifecycle together with four repaired
control/state flows for two robots on one roaming-profile router. The latest
artifact passes action and `4/4` data flows, exercises urgent and queued
scheduling, scopes four deterministic drops to `/fleetqox/mixed/`, and
forwards `46` ACK/NACK frames. New deadline telemetry distinguishes fresh from
repair traffic: fresh deadline misses are `0`; four repaired control samples
arrive after their original deadline. This closes mixed integration but opens
the hard-real-time gap that reactive repair alone cannot solve.

The first proactive hard-deadline protection slice is complete:
`run_rmw_docker_router_proactive_deadline_diversity_probe.py` sends critical
control data through a roaming primary and Wi-Fi backup using `adaptive_qos`.
Subscriber telemetry requires sequences `1,2,3` to arrive within `100 ms`.
The repeated-loss matrix passes `2/2` rows with a real primary sequence-`2`
drop in both rows, maximum latency `63.688 ms`, `6` proactive redundant sends,
and `0` NACK retransmissions.

The first concurrent proactive fleet slice is complete:
`run_rmw_docker_router_multi_robot_proactive_deadline_diversity_probe.py`
protects four robots concurrently over the same roaming/Wi-Fi pair. Its
two-row repeated-loss matrix passes `2/2`: all eight robot-runs deliver
sequences `1,2,3` within `100 ms`, maximum latency is `56.163 ms`, minimum Jain
fairness is `1.0`, and NACK retransmissions remain `0`. The measured cost is
`24` protected source frames expanded to `48` path transmissions, exposing the
next optimization target: preserve the deadline floor with less than full
`2x` redundancy.

The first redundancy-budget/failure-domain allocator slice is complete in
`fleetqox/fleet_optimizer.py`. `PathTelemetry` now identifies failure domains,
and redundant decisions select paths from distinct domains. A dedicated
redundancy byte budget is consumed only by extra path copies; when it is
exhausted or total capacity cannot afford duplication, critical flows fall
back to the best unicast path instead of being dropped. The deterministic
four-robot probe protects the two robots with fairness debt, sends the other
two by unicast, drops no flow, and reduces path transmissions from `8` to `6`
(`25%`) while avoiding correlated Wi-Fi path pairs.

The first live budgeted fleet-plan actuation slice is complete:
`run_rmw_docker_router_multi_robot_budgeted_fleet_plan_probe.py` carries path
failure domains through online telemetry smoothing, gives the two
fairness-debt robots redundant 5G/Wi-Fi plans, and gives the other two robots
5G unicast plans. The real four-publisher/four-subscriber RMW run under
roaming/Wi-Fi netem passes `4/4` robots, keeps all samples below the `100 ms`
deadline with maximum latency `56.577 ms` and Jain fairness `1.0`, observes the
intentional primary-path sequence-`2` drops, performs zero retransmissions,
and executes exactly `18` path transmissions instead of the full-redundancy
baseline of `24` (`25%` reduction).

The first active-publisher epoch transition is also complete:
`run_rmw_docker_router_multi_robot_budgeted_fleet_plan_epoch_probe.py` starts
all four topics with blanket dual-path protection, then changes the shared
fleet plan to a two-robot redundancy budget after the first source frame while
the publishers remain alive. The C++ RMW reloads the plan per frame: robots
`0000/0001` record three redundant frames each, while robots `0002/0003`
record one redundant frame followed by two unicast frames. The run passes
`4/4`, maximum latency is `63.405 ms`, fairness is `1.0`, retransmissions are
zero, and path transmissions fall from `24` to `20` in the same session.

The first subscriber-QoE-driven closed-loop budget epoch is complete:
`run_rmw_docker_router_multi_robot_qoe_feedback_budget_probe.py` starts robot
`0000/0001` on the roaming path and robot `0002/0003` on the backup path,
waits for one subscriber-visible sample from every robot, and invokes the live
controller with no seeded `RobotQoEState`. Measured first-epoch QoE is
`0.56-0.63` for the roaming robots versus `0.87-0.90` for the backup-path
robots, so the optimizer assigns its two-copy budget to `0000/0001`. The C++
RMW reloads that plan for frames `2/3`. The run passes `4/4`, keeps all samples
within the `250 ms` diagnostic SLO, records maximum latency `222.266 ms` and
Jain fairness `1.0`, masks both intentional sequence-`2` primary drops with no
retransmission, and reduces path transmissions from `24` to `16` (`33.3%`).
The independent two-run netem matrix also passes `2/2`: both rows select
`robot_0000/0001`, keep fairness `1.0`, observe maximum latency `210.977 ms`,
perform zero retransmissions, and use `32` total path transmissions instead of
`48` under blanket redundancy.

The first measured-QoE protection-migration slice is complete:
`run_rmw_docker_router_multi_robot_qoe_protection_migration_probe.py` keeps the
same four ROS 2 publishers alive across two feedback epochs. Epoch 1 measures
QoE `0.60-0.62` on robot `0000/0001` versus `0.88-0.90` on `0002/0003` and
protects the first pair. The harness then reverses the live router qdiscs;
epoch 2 measures QoE `0.93` on `0000/0001` versus `0.79-0.83` on `0002/0003`
and migrates the two-copy budget to the second pair before frame `3`. The run
passes `4/4`, maximum latency is `201.596 ms`, fairness is `1.0`, path
transmissions remain `16` versus `24`, and retransmissions remain zero.

The first uncertainty-aware fleet-size migration matrix is also complete:
`run_rmw_docker_router_qoe_protection_migration_scale_matrix.py` repeats the
same two-epoch live-qdisc experiment with `4`, `8`, and `16` concurrent ROS 2
robots. All `3/3` rows pass. The controller moves protection from the first
half of each fleet to the second half, producing expected protected-set churn
of `28` robot memberships and `14` budget migrations across the matrix. A
publisher readiness barrier and per-epoch event gate remove the fixed
multi-second sampling timer, while a sequential QoE stopping rule waits until
confidence bounds separate the protected and unprotected halves. In the main
`4/8/16` run, all QoE epochs stop at `3` samples per robot and keep `5`
post-migration confirmation frames. Maximum telemetry-to-plan convergence is
`486.958 ms`; maximum controller actuation is `56.761 ms`, including a
conservative `50 ms` bind-mount visibility guard. The separate Docker qdisc
transition takes at most `222.912 ms`. Maximum delivery latency is
`127.958 ms`, minimum Jain fairness is `1.0`, retransmissions remain zero, and
aggregate path transmissions are `420` versus `616` under blanket redundancy
(`31.8%` reduction).

The first repeated stochastic sequential-migration matrix is complete:
`run_rmw_docker_router_qoe_protection_migration_sequential_repeated_matrix.py`
runs `6` rows (`4/8/16` robots times repetition IDs `7,13`) at `0.02%` netem
loss. All `6/6` rows pass and all `12/12` QoE epochs stop by confidence
separation. Maximum telemetry-to-plan convergence is `465.783 ms`, maximum
delivery latency is `125.835 ms`, minimum Jain fairness is `1.0`,
retransmissions remain zero, and aggregate path transmissions are `840` versus
`1232` under full redundancy (`31.8%` reduction). The prior `4/8` repeated run
included one epoch that expanded from `3` to `4` samples; the current `4/8/16`
matrix stopped every epoch at `3` samples under this netem draw.

The first harsh-loss sequential-migration boundary is also recorded. The same
runner now reports row-level `failure_mode` and aggregate
`failure_mode_counts`, tightens `evidence_ok` so a row is not counted OK unless
all sequential QoE epochs reach confidence separation, and tolerates lossy
feedback windows by sampling until the confidence rule separates or reaches its
cap. The `8/16` robot matrix at `0.2%`, `0.5%`, and `1.0%` netem loss completes
`5/6` rows OK: `0.2%` and `0.5%` pass for both fleet sizes, `16` robots also
passes at `1.0%`, and the `8`-robot `1.0%` row fails as
`confidence_not_separated`. This converts the next hard problem from
"did the bridge hang?" into a policy question: when telemetry confidence is not
separable under high loss, the controller must either keep sampling, fall back
to a conservative protection plan, or trigger an explicit repair/safe-mode
decision.

The first confidence-fallback actuation slice is complete. `LivePathPlanController`
now exposes a conservative fallback that selects a protected set from the union
of previous protected robots and current low-QoE candidates, creates synthetic
high-debt robot states for that set, temporarily expands the redundancy budget
for the fallback epoch, and writes the resulting `fleet_plan` to the C++ RMW
publishers. The Docker smoke forces two non-separated QoE epochs with a high
separation margin; both epochs apply fallback, protect all four robots, pass
`4/4` deliveries, keep retransmissions at zero, and use `20/24` full-redundancy
path transmissions. The companion one-row matrix smoke intentionally remains a
strict-evidence failure while reporting `failure_mode=confidence_fallback_applied`,
so fallback safety evidence is not confused with confident migration evidence.
The first harsh fallback matrix is also recorded over `8/16` robots and
`0.2/0.5/1.0%` loss. It passes `3/6` rows under strict confidence. One
`16`-robot row applies fallback and delivers all robots but remains strict-failed
because confidence did not separate; one `16`-robot row applies fallback twice
but still ends at `15/16` robot delivery with tail latency above `1.5 s`; one
`8`-robot row reaches confidence but loses one robot delivery. This confirms
that fallback is now observable but not yet sufficient: the next algorithmic
work is a recovery-window/repair policy after fallback and a feedback-timeout
safe mode for larger fleets.

The first post-fallback recovery-window slice is complete. The budgeted
fleet-plan probe can now release a configurable number of recovery frames after
fallback and reports `fallback_recovery` separately from strict migration
success. The forced four-robot smoke applies fallback in both epochs, then
delivers recovery sequences `3,4,5` on time to `4/4` robots. The harsh recovery
matrix over `8/16` robots and `0.2/0.5/1.0%` loss passes `4/6` strict rows, but
all `6/6` rows pass the recovery window; the two strict-failed rows are
classified as `confidence_fallback_recovered_window`. This closes the first
observability gap after fallback. It does not yet implement targeted replay of
specific missing source sequences; it proves the controller can enter and audit
a bounded recovery state.

The next P0 service-error slice is complete at the RMW C layer:
`fleetrmw_service_error_probe` verifies no-response takes do not fabricate a
reply, malformed response payloads return a controlled error with
`taken=false`, invalid service frames are rejected, and the Docker probe passes
on `udy`.

The first caller-visible P0 service-timeout slice is complete:
`run_rmw_docker_ros2_service_timeout_probe.py` verifies a real
`ros2 service call` sends a request through FleetRMW, the server sees it, the
response is intentionally delayed, and the CLI times out with no fabricated
response.

The router-mediated caller-visible timeout slice is also complete:
`run_rmw_docker_router_ros2_service_timeout_probe.py` runs the service, router,
and ROS CLI caller in separate containers. The caller times out after `2 s`
with return code `124`, the server sees one request and delays `3500 ms`, no
response appears at the caller, and the router records and forwards both
service frames. Standard ROS 2 services have no cancellation operation;
cancellation remains an action semantic and is already covered by the rclpy
action cancel lifecycle.

Next continue P0 in this order:

1. Add caller-visible malformed-service-response diagnostics beyond timeout.
2. Convert post-fallback recovery from extra confirmation frames into targeted
   repair/replay of specific missing source sequences, then rerun the harsh
   recovery matrix.
3. Decide whether `32` robots should be run as one huge container batch or as a
   batched fleet test to avoid Docker resource artifacts.
4. Expand serialization regression coverage and add Nav2/RMF action smoke tests.

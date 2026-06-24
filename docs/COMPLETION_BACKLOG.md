# FleetRMW Completion Backlog

This backlog records the remaining work needed to turn the current
FleetRMW/FleetQoX research prototype into a complete, defensible ROS 2 RMW
project. It is ordered by dependency and regression value.

## Current Baseline

- The Python/dependency-free suite passes locally on the `udy` runner:
  `450` unit tests.
- The ROS 2 sidecar path has repeated four-robot and eight-robot hard-SLO
  evidence with source-sequence ACK/NACK, liveliness-backed retransmit horizon,
  QoE quota recovery, and typed projection feedback.
- `rmw_fleetqox_cpp` has a working ROS 2 RMW skeleton with serialized and typed
  pub/sub, introspection-C/C++ message serialization, standalone
  `rmw_serialize`/`rmw_deserialize`, ROS CLI topic pub/echo,
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
- The repeated `8/16/32` actuated-repair v3 frontier passes `27/27` rows over
  repetition IDs `7,13,29`; all `9/9` groups are monotonic. Every row proves
  dual-path forced loss, admitted NACK repair, deferred rejection, and healthy
  unaffected robots. The maximum observed latency is `397.314 ms` under the
  `400 ms` diagnostic deadline.
- The Nav2/RMF workload now combines local fallback actions with upstream APIs.
  `nav2_msgs/action/NavigateToPose` passes success/cancel and RMF
  `SubmitTask`/`CancelTask` pass nested service serialization through
  `rmw_fleetqox_cpp`. A four-way concurrent batch also passes for both upstream
  APIs. The official Nav2 C++ lifecycle manager drives a lifecycle companion
  through configure/activate/deactivate/cleanup; the router accounts for
  `82/82` service frames with zero invalid frames. The
  ROS CLI message matrix covers `13/13` message shapes.
- A standalone `rosidl_typesupport_cpp` Docker regression round-trips C++
  `std_msgs/String` and nested `geometry_msgs/PoseStamped` through
  `rmw_serialize`/`rmw_deserialize` (40 and 129 serialized bytes).
- A two-container `rclcpp` regression routes nested `PoseStamped` request/reply
  and a C++ `SetBool` service through the FleetRMW router. Both endpoints pass,
  the router forwards `2/2` service frames, and invalid frames remain zero.
- The same C++ regression validates publisher/subscription UDP network-flow
  endpoint metadata and observes real on-new-request/on-new-response callbacks;
  these ABI surfaces are no longer placeholder successes.
- The repeated large-scale RMW comparison spans FleetRMW router, Fast DDS,
  Cyclone DDS, and Zenoh at `8/16/32` robots over repetition IDs `7,13,29`.
  FleetRMW, Cyclone, and Zenoh pass `9/9`; Fast DDS passes `7/9`. The report
  includes 95% confidence intervals. The v2 artifact separates direct-RMW
  delivery/latency from FleetRMW router value and machine-enforces
  `direct_claim_allowed=false` for cross-scope superiority.
- Native ns-3 3.41 now runs in the project Docker image. The first repeated
  T2S matrix passes `27/27` rows at `8/16/32` robots over Wi-Fi/WAN/roaming
  parameter envelopes and seeds `7,13,29`, using identical traces for FIFO,
  static priority, and guarded FleetQoX. Its artifact machine-disallows a
  high-fidelity wireless claim because topology is shared CSMA with an
  independent receive error model.
- The follow-on native Wi-Fi/mobility matrix also passes `27/27` rows at
  `8/16/32` robots and seeds `7,13,29`. It uses one 802.11g infrastructure AP,
  moving stations, three PHY-rate/spacing/speed profiles, and requires a
  positive receive count in every policy row. Wi-Fi and mobility model claims
  are allowed; this single-AP artifact itself disallows roaming handoff.
  Guarded FleetQoX has the highest utility in `8/27`
  rows, static priority in `16/27`, and FIFO in `3/27`, so no general policy
  superiority claim is allowed from this campaign.
- The dedicated dual-AP roaming campaign passes `27/27` rows and observes
  `585/585` required endpoint handoffs over `8/16/32` robots, three handoff
  profiles, and seeds `7,13,29`. Association/disassociation events come from
  `StaWifiMac` traces, every policy row receives packets, and bridged backhaul
  preserves station IP addresses across handoff. Its scoped roaming claim is
  allowed, while `high_fidelity_wireless_simulator_claim` remains false. The
  utility winner is static priority in `20/27` rows, FleetQoX guarded in `5/27`,
  and FIFO in `2/27`; general policy superiority remains disallowed.

## P0: Make The RMW ABI Complete Enough For Real ROS 2 Workloads

- Expand the now-working introspection-C++ path beyond Nav2 manager,
  String/PoseStamped standalone, and C++ interprocess Pose/SetBool probes into
  sequence-heavy services and cross-language C/C++ matrices.
- Add regression coverage for more ROS message shapes: bounded/unbounded
  sequences, nested arrays, time/duration-heavy messages, and common Nav2/RMF
  message families.
- Complete service timeout, cancellation, stale request/response, and error
  semantics instead of only proving the successful SetBool path.
- Harden action transport on top of pub/sub plus service reliability:
  goal, result, feedback, cancel, status, deadlines, and larger concurrent
  action/client counts.
- Extend the proven upstream Nav2 lifecycle-manager transport from the
  companion node to real planner/controller components and larger repeated
  client counts.
- Replace or deliberately scope the remaining optional ABI stubs for QoS
  events, dynamic messages, and content-filtered topics.

The middleware-owned loaned-message ABI slice is complete for introspection C
and C++. Docker verifies publisher borrow/publish, publisher borrow/return,
subscription take/return, endpoint capability flags, and both type-support
paths. Subscription take still deserializes into the loaned object, so the
machine-readable zero-copy claim remains false.

The publisher/subscription allocation ABI slice is complete as a no-op
middleware allocation lifecycle. `rmw_init_*_allocation` and
`rmw_fini_*_allocation` now set/check the FleetRMW identifier, keep `data=null`,
and Docker verifies that serialized publish/take accepts allocation pointers.
The machine-readable deep-preallocation claim remains false.

The QoS event ABI slice is complete as a no-op event-object surface.
Publisher/subscription event init/fini, `rmw_event_type_is_supported`,
callback setters, and `rmw_take_event` returning OK with `taken=false` are
covered by Docker. Event production and event readiness remain unsupported and
machine-readable.

The bounded standalone serialization-size slice is complete:
`rmw_get_serialized_message_size` recursively computes exact sizes for
statically bounded introspection C/C++ messages with overflow checks. The
Docker probe exercises both introspection C and C++, predicting and serializing
nested `geometry_msgs/Pose` at exactly `80` bytes in both paths. Artificial
bounds for unbounded fields remain explicitly
unsupported and machine-readable.

The optional ABI scope is now machine-readable in the installed
`rmw_fleetqox_cpp/capabilities.json`. It records supported and partial surfaces,
lists every controlled `RMW_RET_UNSUPPORTED` family, and explicitly sets
`production_ready=false`; future implementation work must update this manifest
and its CI assertion.

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

- Keep the completed split-scope report as the paper claim boundary: direct
  DDS/Zenoh delivery/latency is one scope and FleetRMW router/repair value is
  another; cross-scope superiority remains forbidden.
- Optionally add a same-hop relay experiment later, but do not mix its claims
  into the current split-scope evidence.
- Preserve qdisc evidence, profile/seed parity, robot/topic count parity, and
  per-topic delivery metrics in every baseline row.

## P3: Scale The Network-Aware QoS/QoE Plane

- Run the current N-topic controller-scale workload through live Docker
  router/subscriber probes with real `tc netem` shaping.
- Record duplicate/de-duplication, QoE feedback, robot-level SLO debt, path
  plan churn, and controller decision latency at larger N.
- Extend the completed dual-AP ns-3 handoff matrix with richer propagation,
  interference, and access-category models, and add an OMNeT++/INET matrix
  from the same trace/export pipeline.
- Tie simulator, Docker/netem, and network-simulator outputs into one
  reproducible report path.

## P4: Extend The Data Plane

- The first same-host POSIX shared-memory transport slice is complete. A
  process-shared 64-slot ring uses sequence numbers, process-shared
  mutex/condition synchronization, overwrite telemetry, configurable segment
  names, owner cleanup, and explicit UDP fallback. The two-container Docker
  gate transfers `100000` payload bytes (above the UDP limit), observes zero
  overwrites and zero network-flow endpoints in SHM mode, then fault-injects
  SHM initialization and passes through `udp_fallback`.
- The first hybrid SHM-local plus UDP-remote gate is complete. One publication
  reaches the subscriber directly through SHM and again through the UDP
  router; the router forwards one valid frame, the subscriber takes one
  payload, records `duplicate_data_frames_deduped=1`, and has zero SHM
  overwrites. QUIC remains separate.
- The first real QUIC/TLS dependency gate is complete at the transport
  boundary: Docker now carries ngtcp2/GnuTLS tooling, and
  `run_rmw_docker_quic_tls_probe.py` verifies a QUIC v1 TLS handshake, ALPN
  `h3`, qlog emission, and payload download through `gtlsserver`/`gtlsclient`.
  This is not an integrated RMW QUIC backend claim.
- The follow-on QUIC/FleetRMW frame gate sends a real
  `fleetrmw.data_frame.v1` through the same QUIC/TLS/H3 path and requires the
  downloaded bytes to decode with `fleetrmw_frame_probe`. This proves the
  FleetRMW wire format can survive the real QUIC path, still not RMW
  publish/take integration.
- The Docker/netem QUIC frame gate extends that proof across two containers on
  a Docker network. The client container applies `tc netem` to `eth0`, fetches
  the FleetRMW frame over ngtcp2/GnuTLS QUIC/TLS/H3, and the received bytes are
  decoded by the C++ frame probe. The same gate now records qdisc snapshots
  before and after the transfer and requires ngtcp2 path telemetry from client
  and server logs, including packet-log counts, RTT samples, congestion-window
  samples where emitted, QUIC v1 negotiation, and ECN-capable evidence.
- The first publish-side QUIC gateway slice is complete. `rmw_publish` can be
  configured with `FLEETQOX_RMW_REMOTE_TRANSPORT=quic_gateway` and
  `FLEETQOX_RMW_QUIC_GATEWAY=host:port`; it writes the encoded FleetRMW frame
  to ngtcp2/GnuTLS `gtlsclient --data` and POSTs it over QUIC/TLS/H3. The
  Docker gate verifies QUIC v1, ALPN `h3`, qlog emission, `rmw_publish` success,
  and that `gtlsserver` received a body/content-length matching the RMW frame
  bytes. The async worker variants add bounded enqueue/drain and burst telemetry
  so `rmw_publish` can return after queueing while the worker completes real
  QUIC/TLS/H3 uploads. The two-container Docker/netem variant repeats the same
  `rmw_publish` upload through a Docker network after applying `tc netem` on the
  client, records qdisc before/after counters, and requires parsed ngtcp2 path
  telemetry; the async-burst netem variant extends that proof to multiple
  queued uploads and aggregate server body-byte validation under the same netem
  path. This remains subprocess-backed and publish-side only.
- Add the integrated UDP/QUIC LAN and QUIC WAN RMW transports with explicit
  path telemetry.
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
observability gap after fallback.

The targeted-repair attribution slice now joins that audit to the RMW
source-sequence ACK/NACK ledger. The probe reports per-robot missing/late
sequences, idle repair requests, NACK retransmissions, unresolved robots, and
repair path overhead. A forced four-robot smoke observes source sequence `5`
repaired after one idle request and six retransmissions; it is correctly
classified `repaired_late` because latency reaches `1603.340 ms`, while the
subsequent three-frame recovery window passes `4/4`. A separate one-row matrix
smoke has no loss event, remains strict-failed because confidence was
intentionally prevented from separating, but reports `qoe_recovered_run_count=1`
and zero repair overhead. Source-sequence replay is therefore present and
measurable; this result motivated the controller-directed repair slice below.

The first controller-directed repair slice is now complete. The Python
controller writes a separate live repair-plan file, the C++ RMW applies it only
to ACK/NACK retransmissions, and a per-publisher repair budget is exposed with
separate path/frame/budget metrics. A deterministic two-robot sequence drop
uses dual-path repair for every retransmission. At a `250 ms` SLO, repaired
latency remains about `299 ms` and is classified late; at a `400 ms` SLO, both
affected robots are `repaired_on_time` and the repair summary qualifies `4/4`
robots. A zero-budget run leaves both sequence gaps unresolved and sets
`qoe_recovery_ok=false`. The remaining gap is no longer repair-path actuation;
it is fleet-wide, per-sequence urgency/admission.

Repeated-NACK coalescing and per-sequence attempt limits are also complete.
With a `50 ms` coalescing interval, retransmissions fall from `8` to `4`
without changing the `4/4` repair-qualified result. A one-attempt cap reduces
the deterministic run to `2` retransmissions and `4` repair path sends while
remaining `repaired_on_time`; duplicate and over-limit requests are reported
separately instead of consuming the global publisher budget.

Adaptive fleet-wide repair admission is now complete for the deterministic
four-robot boundary. `FleetRepairScheduler` ranks per-sequence gaps using
remaining-deadline pressure, criticality, QoE debt, expected path success and
latency, previous attempts, and byte cost. It evaluates unicast and
failure-domain-diverse repair alternatives under one shared capacity using a
multi-choice knapsack with Pareto pruning. The generated
`topic=paths|sequences=N|attempts=M` policy is enforced by C++ publishers in
strict mode. With `2800` available bytes, both affected robots recover on time
using only `1400` bytes and two backup-path transmissions. With `700` bytes,
only higher-debt `robot_0000` is admitted; `robot_0001` is explicitly deferred,
repair-qualified coverage is `3/4`, and the rejected publisher reports `33`
non-admitted repair requests. This proves shared admission and priority under
scarcity without hiding the lost QoE behind the later recovery window.

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

Caller-visible malformed-service-response diagnostics are now complete. The
router-mediated probe sends a validly addressed `fleetrmw.service_frame.v1`
whose serialized response body is intentionally invalid. The router forwards
both frames, the server records one request and exits normally, while
`ros2 service call` exits with code `1`, prints no response, and reports
`failed to deserialize service response` through the RMW/rcl error chain.

The repeated `8/16/32` fleet repair-capacity frontier is now complete under
actuated-repair v3 semantics. The runner gives repair candidates a separate
topic prefix, drops sequence `2` once on both router paths, and classifies
admitted, deferred, and unaffected robots separately. The repetition
`7,13,29` artifact passes `27/27` rows and all `9/9` robot/capacity groups are
monotonic. Audit finds zero counter anomalies: admitted count, NACK
retransmissions, repair frames, and repair path overhead agree exactly, while
every deferred robot reports an unresolved sequence-`2` gap and
`repair_not_admitted`. Capacity fractions `0.25/0.5/1.0` produce repair
coverage `0.25/0.5/1.0` and live QoE-qualified coverage `0.625/0.75/1.0` at all
three fleet sizes. The maximum observed latency is `397.314 ms`, below the
`400 ms` deadline. With only three repetitions, some Student-t intervals for
the mean extend slightly above `400 ms`; this remains a statistical precision
limit, not an observed deadline failure.

The upstream Nav2/RMF action/service and lifecycle-manager expansion is complete. The
`fleetrmw_interfaces` package now defines `NavigateFleet.action` and
`DispatchFleetTask.action`, and
`run_rmw_docker_router_nav2_rmf_action_workload.py` retains those local
fallbacks while also running upstream `nav2_msgs/action/NavigateToPose` and RMF
`SubmitTask`/`CancelTask`. Success, feedback, cancel, result, submit, and cancel
all pass through the FleetRMW router. The v5 batch additionally completes four
simultaneous upstream navigation goals and four RMF submissions. The official
`nav2_lifecycle_manager` C++ node issues `STARTUP` and `RESET`; the companion
reaches `active` and returns to `unconfigured`. The router forwards `82/82`
service frames with zero invalid frames, proving introspection-C++ service
dispatch, guard-condition/client wait readiness, concurrent action handling,
nested RMF serialization, and lifecycle transition transport. This does not
yet instantiate the full Nav2
planner/controller plugin stack. The ROS CLI message matrix remains `13/13`.

The repeated large-scale DDS/Zenoh comparison is complete as a gap register.
`run_large_scale_rmw_comparison.py` runs the same multi-topic envelope across
FleetRMW router, Fast DDS, Cyclone DDS, and Zenoh for `8/16/32` robots over
repetition IDs `7,13,29`. Netem is applied after discovery, every publisher
uses the same six-second reliability horizon, and Zenoh uses its required
router/session configuration. FleetRMW, Cyclone, and Zenoh pass `9/9`; Fast
DDS passes `7/9`, with one state-delivery failure at `8` and one at `16`
robots. FleetRMW's earlier 16-robot miss is closed, and its retransmit worker
now joins cleanly instead of racing static teardown. Because FleetRMW uses a
router hop while DDS/Zenoh rows are direct, the report keeps the topology
caveat explicit and does not claim superiority.
The v2 artifact formalizes that boundary with allowed direct-RMW and
Fleet-router scopes plus a disallowed cross-scope superiority claim;
`direct_claim_allowed=false` is machine-readable.

Next continue P0/P2 in this order:

1. Apply the proven lifecycle transition path to real Nav2 planner/controller
   components and larger repeated client counts while retaining local actions
   as CI-light fallbacks.
2. Preserve the completed split-scope benchmark boundary; add same-hop relay
   rows only as a separate future experiment.
3. Broaden native C++ type-support regression coverage and close or explicitly
   scope the remaining optional RMW ABI surfaces before production-ready status.
4. Increase frontier repetitions so the `32`-robot latency-mean confidence
   interval can be estimated more tightly around the `400 ms` boundary.

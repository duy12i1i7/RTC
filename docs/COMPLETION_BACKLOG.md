# FleetRMW Completion Backlog

This backlog records the remaining work needed to turn the current
FleetRMW/FleetQoX research prototype into a complete, defensible ROS 2 RMW
project. It is ordered by dependency and regression value.

## Current Baseline

- The full repository suite passes in the pinned ROS 2 Jazzy Docker image:
  `622/622` unit/contract tests. The unified report currently indexes `323`
  retained artifacts (`264` ok, `16` partial, `39` historical failed, and `4`
  unknown); its overall `partial` status deliberately includes old debug,
  negative-control, superseded, and failed runs rather than hiding them.
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
  `82/82` service frames with zero invalid frames. Real upstream
  `planner_server`/`controller_server` probes configure Navfn/DWB plugins and
  activate both lifecycle nodes to `active [3]` with repeated dynamic `/tf`
  forwarded through the same FleetRMW router. A planner runtime probe also
  forwards repeated `/map` plus `/tf`, sends upstream `ComputePathToPose`, and
  receives a successful Navfn path. A controller runtime probe forwards
  repeated `/map`, `/tf`, and `/odom`, sends upstream `FollowPath`, and
  receives a successful DWB result. A full-stack CI-light probe starts
  `bt_navigator`, executes a minimal `ComputePathToPose -> FollowPath`
  behavior tree through upstream `NavigateToPose`, and succeeds at the current
  pose. The ROS CLI message matrix covers `13/13` message shapes.
- A standalone `rosidl_typesupport_cpp` Docker regression round-trips C++
  `std_msgs/String` and nested `geometry_msgs/PoseStamped` through
  `rmw_serialize`/`rmw_deserialize` (40 and 129 serialized bytes).
- The `rclcpp` regression now routes nested `PoseStamped`, a dynamic 64-pose
  `nav_msgs/Path`, `SetBool`, and `nav_msgs/GetPlan` through the FleetRMW
  router. GetPlan checks nested start/goal/tolerance requests and returns a
  512-pose Path; its 73,181-byte serialized response exceeds the 65,507-byte
  UDP datagram boundary and proves service-frame fragmentation/reassembly. A separate
  bidirectional C++/rclpy Docker/netem matrix passes `5/5` runs and `10/10`
  direction rows with exact nested Path validation and zero invalid frames.
  Its service leg explicitly uses five 100 ms request repeats: early requests
  may be rejected until the reciprocal client graph converges, then endpoint
  deduplication preserves one callback and response replay completes the call.
- The same C++ regression validates publisher/subscription UDP network-flow
  endpoint metadata and observes real on-new-request/on-new-response callbacks;
  these ABI surfaces are no longer placeholder successes.
- The current repeated split-scope RMW comparison spans FleetRMW router, Fast
  DDS, Cyclone DDS, and Zenoh at `8/16/32` robots over repetition IDs
  `7,13,29`; all four pass `9/9`. Its v2 artifact still machine-enforces
  `direct_claim_allowed=false` because FleetRMW has a router hop while the
  baseline application paths are direct. A separate matched-hop study now
  gives every row publisher-middle-subscriber topology: Cyclone and Zenoh pass
  `9/9`, FleetRMW `8/9`, and Fast DDS `6/9` (`32/36` overall). It permits only
  delivery/reliability comparison. Its historical 36-row artifact used a
  typed rclpy relay. The current harness instead uses a common `rclcpp` generic
  serialized relay with no application deserialization plus bounded
  `wait_for_all_acked` publisher horizons. A fresh full-scale run passes
  `35/36`: all three baselines pass `9/9` and relay `5040/5040` payloads;
  FleetRMW passes `8/9` with one retained `319/320` row. FleetRMW raw-frame
  forwarding and baseline RMW endpoint termination/republish are still not
  latency-equivalent middle processing.
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
- OMNeT++ 6.4.0 and INET 4.7.0 are pinned by commit in a headless ARM64 Docker
  image. The implemented INET `UdpSocket` trace replay and matching ns-3
  routed-P2P path pass `27/27` runtime pairs and `27/27` bounded-parity cases at
  `8/16/32` robots and three seeds (`72,213` packet rows). Scoped runtime and
  parity claims are true. Dedicated 802.1Qbv/Qav TSN, mobile mesh/MANET, and
  high-fidelity wireless parity remain explicitly unsupported rather than
  being inferred from this wired P2P matrix.

## P0: Make The RMW ABI Complete Enough For Real ROS 2 Workloads

- Expand the now-working introspection-C++ path beyond the completed
  bidirectional C++/rclpy `PoseStamped`/64-pose `Path`/`SetBool`/512-pose
  `GetPlan` router matrix and generated bounded `FleetShape` service into
  additional common Nav2/RMF service families and a broader generated C/C++
  compatibility corpus.
- The bounded-shape regression is complete for bounded strings, fixed arrays,
  bounded primitive sequences, bounded nested PoseStamped sequences, Duration,
  and bounded response sequences at their declared maxima. Unbounded nested
  message sequences, headers, signed time, dynamic byte/float arrays, and fixed
  covariance arrays are covered by the Path/CLI/Nav2 matrix. This is broad
  shape coverage, not an exhaustive ROSIDL corpus.
- Service no-response/timeout, stale request/response lifespan, malformed
  response propagation, and successful SetBool/GetPlan/FleetShape paths are
  complete. Discovery-window repair is now a nonblocking middleware worker:
  the request call sends once and returns, bounded retries use the same
  sequence, matching responses cancel pending work, client teardown clears it,
  and the Docker/netem runners require no retry environment override. The
  pending repair pool now has global/per-client admission bounds; a 5/5 gate
  reaches exact limits 4/3, keeps all eight initial sends, records one
  per-client plus three global repair rejections, and cancels all four admitted
  jobs at teardown. Standard
  ROS 2 services have no cancellation operation; action cancellation is covered
  separately. Request/response queues, pending-response state, dedupe history,
  and response replay are now bounded and configurable; a limit-four Docker
  gate proves capacity rejection remains repairable and delivers 10/10 unique
  requests/responses in 5/5 runs. A second 5/5 noisy/quiet-client gate proves
  optional per-client pending isolation: the noisy client cannot consume the
  quiet client's two first-wave slots; round-robin dequeue alternates clients
  while preserving each client's FIFO order, and all deferred requests are
  later delivered. Optional priority metadata, strict priority dequeue, and
  local enqueue-time aging are covered by a separate 5/5 Docker gate; legacy
  frames default to priority zero. Optional weight metadata defaults to one;
  an opt-in smooth weighted round-robin scheduler preserves per-client FIFO,
  including reordered wire arrival, reaches an exact 3:1 saturated dequeue
  split, and bounds the tested
  lower-weight client's wait to four dequeues in a separate 5/5 Docker/netem
  gate. An opt-in EDF scheduler now carries relative request deadlines, orders
  them from server-local enqueue time, and gives no-deadline requests a
  configurable synthetic aging deadline; its 5/5 end-to-end gate proves
  20 ms before 200 ms and the aging escape path. Completed responses now have
  opt-in crash-persistent dedupe/replay: a mode-0600 atomic-fsync ledger is
  loaded by a replacement process, and a 5/5 Docker/netem SIGKILL gate proves
  no duplicate application delivery after persistence. Remaining service work
  is the pre-persistence crash ambiguity window and application-transactional
  exactly-once semantics; host power-loss durability is also unclaimed.
- Harden action transport on top of pub/sub plus service reliability:
  goal, result, feedback, cancel, status, deadlines, and larger concurrent
  action/client counts.
- Extend the proven upstream Nav2 lifecycle-manager transport from the
  companion node to real planner/controller components and larger repeated
  client counts.
- Replace or deliberately scope the remaining optional ABI stubs for full
  liveliness coverage, full DDS message-lost/resource-limit semantics,
  complete DDS/vendor-specific semantics beyond the proven 11/11 remote event
  path coverage, the full QoS/type compatibility matrix, dynamic type
  discovery and non-FastRTPS dynamic serialization plugins,
  and the full DDS content-filter expression dialect.

The middleware-owned loaned-message ABI slice is complete for introspection C
and C++. Docker verifies publisher borrow/publish, publisher borrow/return,
subscription take/return, endpoint capability flags, and both type-support
paths. Subscription take still deserializes into the loaned object, so the
machine-readable zero-copy claim remains false.

The publisher/subscription allocation ABI now owns a real, type-support-bound
payload scratch buffer. `rmw_init_*_allocation` reserves 64 KiB by default
(or a larger bounded introspection size), typed and serialized publish/take
validate the handle kind/type and reuse the vector under a per-allocation
mutex, and fini releases it. Docker verifies `5/5` fresh processes, eight
publish/take pairs per process, exact use counts, unchanged capacity, zero
payload-scratch growths, and fail-closed uninitialized handles. The
machine-readable deep-preallocation claim remains false because frame encoding,
reliability history, transport queues, and application-message deserialization
still allocate.

The required `rmw_take_sequence` symbol and behavior slice is now complete.
FleetRMW validates all arguments before mutation, leaves both output sequences
unchanged when no message is available, reports partial sequence sizes, and
serializes all take operations per subscription so concurrently requested
sequences remain consecutive in queue order. Docker passes this contract
`5/5`; an `nm -D` audit against `librmw_fastrtps_cpp.so` from the same Jazzy
image reports `95/95` baseline `rmw_*` symbols present in FleetRMW, including
`rmw_take_sequence`. This is exported-symbol parity, not behavioral parity for
every optional RMW family.

The previous unconditional-success `rmw_publisher_wait_for_all_acked` stub has
also been replaced. `fleetrmw.ack_nack.v1` now optionally carries
`subscriber_id`; reliable ledger entries snapshot compatible local/remote graph
endpoint IDs and retain a pending set per write. The API waits only for writes
that existed when the call began, removes readers that are no longer matched,
honors zero/finite timeouts, and wakes on ACK arrival. A delayed-second-reader
Docker control passes `5/5`: the first wait times out with `1/2` ACKs and the
completion wait returns OK with `2/2`. Full DDS writer-history/resource-limit
semantics remain explicitly unclaimed. A second `5/5` gate now repeats the
same boundary over four containers (router, publisher, and two subscribers)
with `5 ms +/- 1 ms` netem on every hop and a 450 ms delayed second ACK. The
router observes one DATA plus both subscriber ACKs, the publisher never reports
the partial `1/2` state as complete, and every process tears down cleanly.

The security-options lifecycle ABI slice is complete as a repeated Docker
boundary. Docker now verifies default security options, custom enclave
configuration, `rmw_init_options_copy` preservation/deep-copy behavior, context
init copy, shutdown, and fini across `5/5` repeated runs. The first opt-in
FleetQoX policy slice is also complete: `FLEETQOX_RMW_SECURITY_POLICY` supports
publish allow/deny rules and Docker verifies allowed delivery plus denied
publish rejection across `5/5` repeated runs. A scoped SROS2 path is now also
complete: Docker uses `ros2 security` to generate enclave credentials,
`permissions.xml`, and `permissions.p7s`; verifies the signed payload against
the permissions CA; validates it against the SROS2 DDS permissions XSD; and
passes the signed policy and permissions CA to FleetRMW. The RMW verifies the
S/MIME signature and certificate chain at runtime before parsing, then enforces
grant selection by enclave, validity, domain `id`/`id_range`, ordered publish
and subscribe allow/deny topic rules, `*`/`?` wildcards, and the grant default action across
`5/5` runs. Invalid XML and a byte-tampered signed policy are denied
fail-closed. The generated SROS2 service `request`/`reply` permissions are also
mapped onto `rq...Request` and `rr...Reply` and enforced on real RMW SetBool
request/response send/receive paths, with allow, explicit-deny, and default-deny
controls. Generated Action `call`/`execute` rules are likewise enforced on a
real rclpy `tf2_msgs/action/LookupTransform` path: the allowed goal/result and
feedback path succeeds, explicit call denial returns an RMW error, execute-side
denial drops the request before callback dispatch, and the full matrix repeats
`5/5`. Signed Governance is now parsed and CA-verified too: domain/topic
read-write access-control switches are enforced `5/5`, while the stock SROS2
ENCRYPT/SIGN profile and a tampered governance signature are denied
fail-closed. FleetRMW now additionally verifies the local identity certificate
chain, private-key correspondence, and certificate-CN/enclave equality before
`rmw_init`, repeated `5/5`; tampered certificate, mismatched key, and mismatched
enclave controls fail closed. Remote peer authentication, keystore secrecy,
and production key management remain gaps, but the UDP data path now has an
opt-in AES-256-GCM PSK envelope with unique nonces, replay tracking, strict-key
mode, and tamper fail-closed evidence repeated `5/5`. DDS-Security peer
certificate exchange/interoperability, revocation, and production
hardening remain explicit gaps; therefore the broad
`sros2_policy_enforcement_claim` remains false.

The QoS event ABI slice now includes scoped deadline event production.
Docker verifies publisher/subscription event init/fini,
`rmw_event_type_is_supported`, callback setters, initial
`rmw_take_event(taken=false)`, and offered/requested deadline-missed events
after a publish/receive gap exceeds the configured deadline. The produced
statuses have positive total/change counts, callbacks receive pending event
counts, timer-driven idle misses after the first sample become ready through
`rmw_wait`, and a second take clears the change counts/readiness. The deadline
event object/waitable Docker artifact passes `5/5` repeated runs. A second
matrix executes seven event-production probes per round and covers all eleven
non-invalid Jazzy event types. It passes `5/5` rounds (`35/35` components),
including ready-before-take and initial/cleared-not-ready controls, so full
Jazzy QoS-event waitability is now supported. Remaining gaps are full
liveliness production semantics, full DDS message-lost/resource-limit
semantics, complete DDS/vendor-specific semantics beyond the repeated 11/11
remote event paths, and the full QoS/type compatibility matrix.

The independent `rmw_qos_profile_check_compatible` ABI now follows the ROS 2
Jazzy compatibility rules across reliability, durability, deadline,
liveliness kind, and liveliness lease duration. The Docker QoS v2 probe covers
an OK profile pair; aggregated reliability plus durability errors; absent and
misordered deadlines; automatic/manual liveliness; lease-duration ordering;
and WARNING output for an unresolved publisher policy. This closes profile
checking for the policies in that API, but does not imply remote QoS event
production or the remaining DDS-specific compatibility event matrix.

Deadline-incompatible event production now covers both a slower offered
deadline and an absent/default offered deadline against a finite requested
deadline. Offered and requested event directions each pass wait/take/callback,
`RMW_QOS_POLICY_DEADLINE`, and unmatched negative controls across `5/5` Docker
runs (`4` scenarios per run).

BEST_AVAILABLE endpoint creation now uses the Jazzy `rmw_dds_common` selection
helpers over FleetRMW publisher/subscription graph queries. Docker repeats four
scenarios `5/5`: manual publisher selection at `200 ms`, automatic subscription
selection at `300 ms`, zero-endpoint AUTOMATIC/default values, and mixed
automatic/manual publisher selection at the maximum `500 ms` lease. Actual QoS
is reported after create and remains frozen after discovery churn.

The matched-event slice covers local compatible endpoint matching. Docker
verifies `RMW_EVENT_PUBLICATION_MATCHED` and
`RMW_EVENT_SUBSCRIPTION_MATCHED` support for local same-process compatible
endpoint create/destroy: callbacks fire, `rmw_wait` reports readiness while the
matched status is unread, `rmw_take_event` reports connect and disconnect
status changes, and a second take clears the changes. The implementation now
avoids counting same-topic endpoints with incompatible type, reliability, or
durability as matched. The local Docker artifact passes `5/5` repeated runs.

The incompatible-QoS slice now covers local same-process reliability,
durability, and deadline mismatches. Docker verifies that a best-effort
publisher discovered by a reliable subscription reports
`RMW_QOS_POLICY_RELIABILITY`, a volatile publisher discovered by a
transient-local subscription reports `RMW_QOS_POLICY_DURABILITY`, and an
offered deadline longer than the requested deadline reports
`RMW_QOS_POLICY_DEADLINE`; in all cases offered/requested
`RMW_EVENT_*_QOS_INCOMPATIBLE` callbacks fire, `rmw_wait` reports readiness,
`rmw_take_event` reports `total_count_change=1`, and the incompatible endpoint
is not counted as matched. The local Docker artifact passes `5/5` repeated
runs. A separate `5/5` Docker artifact covers liveliness kind plus slow/missing
offered lease in both event directions, with `RMW_QOS_POLICY_LIVELINESS`,
cleared readiness after take, and a faster-offered compatible control. The
remaining gap is the full DDS QoS compatibility matrix beyond these policies
and broader unresolved/system-default combinations.

The incompatible-type slice now covers local same-topic type mismatches.
Docker verifies that publisher-side and subscription-side
`RMW_EVENT_*_INCOMPATIBLE_TYPE` events are supported, callbacks fire,
`rmw_wait` reports readiness while unread, and `rmw_take_event` reports
`total_count_change=1` before clearing readiness. The local Docker artifact
passes `5/5` repeated runs. The remaining type gap is the full ROS/DDS
compatibility matrix beyond exact type-name mismatch.

The message-lost slice now covers both local subscription queue overwrite under
`KEEP_LAST` and real `BEST_EFFORT` source-sequence gaps. Docker verifies that a
depth-`1` subscription drops the older queued payload, then independently drops
source sequence `3` from a four-sample best-effort stream and reports exactly
one `RMW_EVENT_MESSAGE_LOST` through callback, `rmw_wait`, and
`rmw_take_event`. A mixed reliable/best-effort control drops the same sequence,
repairs it within the configurable grace interval, delivers all four payloads,
and reports zero false loss events. Best-effort readers no longer emit ACK/NACK
or enter reliable writer ACK snapshots. The Docker artifact passes `5/5`
repeated runs. A fourth control uses a reliable writer with `KEEP_LAST depth=1`:
the dropped sample is evicted before its NACK arrives, the writer sends exactly
one subscriber-targeted unrecoverable-loss notice, and the reader reports one
loss while retaining the other three payloads. A two-container Docker/netem
probe repeats the same remote writer-history-exhaustion path `20/20`; immediate
and idle NACKs produce duplicate targeted notices, but the reader idempotently
reports exactly one lost sample/event through callback, `rmw_wait`, and
`rmw_take_event`. A second two-container campaign keeps the dropped sample in
writer depth-`16` history and proves terminal repair budget `0`, max-attempt `1`,
and strict-admission rejection `5/5` each (`15/15` total). Every branch produces
its distinct counter and one targeted loss event, duplicate budget/admission
notices remain idempotent, and both processes tear down cleanly. The remaining
gap is full DDS message-lost/resource-limit semantics beyond these scoped paths.

The liveliness-event slice now covers local same-process finite lease
transitions. Docker verifies that a matching publisher first makes the
subscription `RMW_EVENT_LIVELINESS_CHANGED` status alive, a lease timeout
produces publisher `RMW_EVENT_LIVELINESS_LOST` plus subscription not-alive
change, callbacks fire, `rmw_wait` reports unread status readiness, and
`rmw_publisher_assert_liveliness` reasserts the publisher as alive. That manual
timeout/reassert artifact passes `5/5`. A second `5/5` artifact verifies that an
AUTOMATIC publisher left idle for six `20 ms` lease intervals remains alive
without lost wait readiness, callback, event total, or subscription not-alive
transition. A third `5/5` artifact uses two UDP/netem containers to verify
remote MANUAL_BY_TOPIC semantics: `100 ms` graph renewal does not assert the
independent `200 ms` liveliness lease, idle expiry leaves the publisher matched,
and both explicit assertion and serialized publish send a wire assertion that
reasserts the endpoint. Each run receives ten assertions and records exactly
two expiries plus two reassertions with clean teardown. Remaining gaps are
reduced further by a second two-container `5/5` artifact: two simultaneous
manual publishers maintain independent state, removal is correct from both
alive and not-alive states, expiry does not alter matching, and a third endpoint
is recreated after the aggregate returns to zero. Local liveliness kind and
slow/missing lease incompatibility event production also passes a separate
`5/5` seven-scenario Docker artifact. A further local `5/5` scale artifact
drives 64 MANUAL_BY_TOPIC publishers through exact 64/0, 32/32, reasserted
64/0, expired 0/64, and removed 0/0 aggregate states while keeping half the
publishers alive independently. Its SYSTEM_DEFAULT control leaves 16 idle
publishers alive across six finite lease periods. The remote scale gap is now
closed by a two-container UDP/netem artifact passing `5/5`: 64 remote publishers produce
exact half-expiry, 32-endpoint reassert, all-expiry, removal, match and unmatch
deltas; each run records exactly 96 expiries and 32 reassertions while all 64
endpoints remain matched during expiry. The remaining liveliness gap is limited
to deprecated participant-wide DDS semantics, so the generic full-DDS claim
remains false. A separate `5/5` control closes the ROS 2 non-deprecated policy
surface: SYSTEM_DEFAULT, AUTOMATIC, MANUAL_BY_TOPIC, and BEST_AVAILABLE with a
default/non-expiring lease still emit exact alive/remove lifecycle events and
never time out; UNKNOWN and deprecated MANUAL_BY_NODE inputs fail closed for
both publisher and subscription creation.

The remote graph event slice is now active on the real UDP receive path rather
than only in graph-query state. A per-endpoint lease registry combines local
and remote compatible endpoints for publication/subscription matched counts,
produces offered/requested reliability/durability/deadline-incompatible and exact
publisher/subscription type-incompatible events when remote advertisements are
discovered, and reports finite-liveliness publisher add/disconnect transitions
to local subscriptions. Repeated `add` advertisements only renew the lease and
do not duplicate event totals. The two-container Docker/netem artifact passes `5/5`:
three runs disconnect all eleven remote endpoints through explicit `remove`,
two kill the advertiser without cleanup and expire all eleven through the
five-second graph lease, and every run proves matched, QoS, type, liveliness,
callback, renewal-deduplication, and empty-registry postconditions. The remote
MANUAL_BY_TOPIC publisher now additionally takes two exact
`RMW_EVENT_LIVELINESS_LOST` transitions with callback and cleared-readiness
controls in every `5/5` run. Together with remote deadline-missed (`5/5`) and
message-lost (`20/20`) artifacts, the aggregate
`remote_qos_event_coverage_summary.json` validates a repeated real UDP/netem
multi-container path for all `11` non-invalid Jazzy RMW event types over `35`
source executions. The broad full-DDS claim remains false because this path
coverage does not imply every DDS resource-limit, deprecated liveliness, or
vendor-specific event semantic.

Remote deadline-missed production is now separately active on the real data
path. In two UDP/netem containers, one serialized sample establishes the local
publisher and remote subscriber deadline anchors; both offered and requested
deadline-missed events then pass callback, `rmw_wait`, `rmw_take_event`, and
cleared-readiness checks across `5/5` runs with clean teardown.
The same `5/5` runs now prove automatic graph-guard readiness on remote add and
explicit-remove/lease-expiry disconnect, while four unchanged renewal rounds
per endpoint produce no spurious guard wakeup.

The content-filter ABI slice now includes scoped data-plane enforcement.
Docker verifies that `rmw_subscription_set_content_filter` stores expression
parameters, marks the subscription CFT-enabled,
`rmw_subscription_get_content_filter` returns the same values, and
`robot_id = %0 AND sequence > %1` drops non-matching raw key-value payloads
while delivering only the matching payload. The Docker probe also reconfigures
the same subscription with `!=`, `>=`, and `<=` predicates and verifies one
matching `std_msgs/String`-style serialized text payload against three
non-matches, then disables the filter with an empty expression and verifies a
payload bypass without increasing filter counters. The Docker artifact passes
`5/5` repeated runs. A second `5/5` artifact adds real data-plane precedence
and parentheses for `AND`, `OR`, and `NOT`, plus parameterized `LIKE`,
`BETWEEN`, `IN`/`NOT IN`, `IS NULL`, and `IS NOT NULL`. It evaluates eleven
payloads per run with exact four-match/seven-drop outcomes and keeps missing
fields under negation at SQL `unknown`; malformed syntax and a missing parameter
reference fail closed without replacing the active filter. The remaining gap
is typed-field reflection and the full DDS SQL content-filter dialect, not
basic dynamic key-value/std_msgs text enforcement.

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
- Keep the completed same-hop relay experiment separate from split-scope
  evidence. It supports delivery/reliability comparison only; increase
  repetitions and equalize middle-hop processing before any latency claim.
- Preserve qdisc evidence, profile/seed parity, robot/topic count parity, and
  per-topic delivery metrics in every baseline row.

## P3: Scale The Network-Aware QoS/QoE Plane

- Run the current N-topic controller-scale workload through live Docker
  router/subscriber probes with real `tc netem` shaping.
- Record duplicate/de-duplication, QoE feedback, robot-level SLO debt, path
  plan churn, and controller decision latency at larger N.
- Extend the completed dual-AP ns-3 handoff matrix with richer propagation,
  interference, and access-category models, and run the prepared OMNeT++/INET
  templates in a pinned external simulator workspace.
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
  QUIC/TLS/H3 uploads. Session/tp/token file plumbing now maps FleetRMW env
  vars to ngtcp2/GnuTLS `gtlsclient` options and has a Docker burst probe that
  verifies session artifacts persist across multiple uploads. The probes also
  parse log-level session/0-RTT telemetry, keeping `zero_rtt_packet_observed`
  separate from `zero_rtt_accepted_observed`; accepted 0-RTT, explicit session
  resumption remain unclaimed. The legacy subprocess path is retained as a
  compatibility and telemetry fallback. A newer optional in-process backend
  links ngtcp2/GnuTLS/nghttp3 directly and is covered by
  `docker_quic_inprocess_rmw_bidirectional_probe_summary.json`: under loopback
  netem it completes 128 `rmw_publish` POSTs plus one on-demand
  `rmw_take_serialized_message` GET on one QUIC v1/H3 connection, one verified
  TLS handshake, 129 bidirectional streams, 128 connection reuses, and zero
  reconnects. In artifact v3, the final `rmw_publish` and
  `rmw_take_serialized_message` are independent calls from two threads and
  rendezvous before the event loop drives either response; it records one
  concurrent RMW API pair, two simultaneous calls, and two simultaneous H3
  streams. A second positive case verifies the explicit paired transport API,
  and the negative control rejects an unrelated CA. The ngtcp2 qlog callback
  is now wired into the in-process client lifecycle; the gate records three
  non-empty client qlogs plus three non-empty server qlogs and reports their
  byte totals in the JSON artifact. This closes
  the scoped in-process multi-threaded publish/take and integrated-qlog slices.
  The stateful aioquic FleetQoX gateway slice is now implemented and passes a
  `5/5` two-container Docker/netem gate. It validates FleetRMW frames, keeps
  bounded per-domain/topic history, deduplicates publisher sequence numbers,
  replays independently to two consumers over persistent verified-TLS client
  sessions, exports qlogs, and fails closed on HTTP 400. Clustered durability,
  accepted 0-RTT/resumption, predictive fleet admission/QoE integration, and production
  hardening remain open. A follow-on `5/5` three-container gate now proves the
  public RMW path as well: one process publishes three typed strings through
  `rmw_publish`, a separate process retrieves all three in order through
  `rmw_take`, and both reuse verified-TLS H3 sessions with qlog evidence. The
  gateway now also has a `5/5` six-container mutual-TLS netem gate: one client
  authenticated by the configured client CA writes a frame, while missing
  client credentials and an unrelated client CA both fail closed before any
  additional gateway request/state mutation. A certificate signed by the
  trusted client CA but carrying the wrong publisher URI SAN is separately rejected
  with HTTP/3 403 before state mutation. A second CA-trusted certificate with
  the correct publisher URI SAN is rejected during TLS because its serial is in a
  current, CA-signed CRL validated at service startup. Client certificate/key loading and an
  opt-in SPIFFE-style URI-SAN-to-`publisher_id` binding are integrated into the in-process
  GnuTLS/gateway path. The current aioquic server requires a private TLS hook
  for CertificateRequest and chain verification; upstream 1.3.0 still exposes
  no public server client-auth switch. The adapter is now isolated, exact-pins
  runtime 0.9.25 / Debian package 0.9.25-3build2, fingerprints its private
  signatures, proves client private-key possession before authentication, and
  fails startup on drift. A pinned build of the official ngtcp2 `v0.12.1`
  server now closes the separate public-API mTLS transport edge: its `5/5`
  Docker/netem artifact gets six H3 responses over one valid session and
  rejects missing, unrelated-CA, wrong-URI, and revoked clients with TLS
  `CRYPTO_ERROR`. It uses public GnuTLS APIs for CA, CRL, client-auth EKU, and
  exact URI-SAN verification and disables server early data. A follow-on
  `5/5` gate now places the shared `FleetQoxGatewayState` engine behind that
  edge through a bounded local protocol. Each round proves three accepted
  frames, one duplicate, six ordered two-consumer takes, invalid-frame 400,
  authenticated publisher-impersonation 403 without state mutation, and
  seven-/three-stream session reuse. The stateful server process uses neither
  aioquic nor its private TLS hook. A further matched `5/5` Docker/netem
  contrast now carries public-ngtcp2 smoothed RTT, RTT variation, congestion,
  PTO, and raw stream-loss-count telemetry through backend protocol v2. It
  proves the same score-zero frame changes from HTTP 429 to accepted/taken
  HTTP 200 only when `ngtcp2_public_api` observations are enabled, with zero
  external observation-API requests. The loss count is deliberately not
  treated as a ratio because the public API provides no denominator.
  A third public-edge `5/5` Docker/netem gate moves backend Unix-socket I/O off
  the libev thread into a configurable bounded worker pool and queue.
  Completions return through `ev_async`; saturation returns HTTP 503. Each
  round proves a fast mTLS/H3 request completes while a delayed request is
  still in flight, proves `1 worker + queue 1` overload behavior, and forces
  one handler to expire before its backend completion. The stale result is
  generation-fenced and dropped, after which a fresh connection remains
  healthy. The delay proxy is test-only and forwards to the real state engine.
  A fourth `5/5` public-edge gate now derives each connection's publisher
  identity from its verified URI SAN, rejects an out-of-prefix CA-trusted
  certificate before backend access, and applies a bounded per-identity
  pending queue with round-robin identity scheduling. Publisher A receives
  HTTP 429 after filling its two pending slots while publisher B is admitted
  and overtakes A's remaining queued request in every round. This closes
  scoped pending-queue cross-publisher fairness. A fifth matched `5/5` gate
  closes configurable active-worker isolation: with two workers and a
  per-identity active limit of one, publisher B completes while both delayed
  publisher-A clients remain open and A never reaches active count two. The
  limit-two control lets A occupy both workers and makes B wait about ten
  times longer. The default limit remains equal to worker count so existing
  work-conserving behavior is unchanged unless isolation is configured.
  A sixth `5/5` public-edge Docker/netem gate now reloads the configured client
  CRL through public GnuTLS APIs before each new TLS peer verification. The
  same server process first accepts the stateful client, rejects it with
  `CRYPTO_ERROR` after an atomic CRL replacement revokes its serial, accepts it
  again after the original CRL is restored, and rejects a malformed CRL
  fail-closed. Backend accounting remains exactly two valid requests in every
  round. This closes online CRL refresh for new connections only; it does not
  evict established sessions or rotate the client CA or server certificate.
  Weighted QoS-aware classes, active-session revocation, online CA/server
  certificate rotation, cluster-wide fairness/state, and production operations
  remain work. The
  gateway's first scoped fleet-admission slice is now complete as a separate
  `5/5` two-container netem artifact. A startup-validated JSON policy assigns
  control/bulk/state traffic classes, publisher allowlists, per-stream frame
  quotas, and one shared three-frame fleet quota. The probe admits and replays
  two control plus one bulk frame, then distinguishes stream-quota 429,
  fleet-quota 429, and publisher-policy 403 while rejected frames leave no
  topic state. A one-second monotonic epoch then replenishes capacity and the
  previously rejected state frame is admitted/replayed; current-epoch and
  cumulative counters remain separate. Dynamic measured QoS/QoE admission,
  repair coupling, and clustered capacity coordination remain open. The
  next scoped coupling slice is now complete: optional C++ data-frame fields
  carry traffic class, deadline/age, QoE debt, criticality, repair intent, and
  prior attempts into the gateway. A `5/5` two-container netem artifact proves
  score-threshold rejection/admission, then invokes the existing fleet repair
  scheduler when normal quota is full: private 5G admits one urgent repair and
  the shared 1024-byte repair budget defers the next. Both accepted frames
  replay over H3 with qlogs. A follow-on `5/5` netem gate now accepts versioned
  external observations with TTL, incorporates debt/loss/RTT/jitter into the
  admission score, and sorts competing two-frame batches before admission. It
  proves an observation-raised frame wins the only normal slot and an urgent
  repair wins the shared 1024-byte capacity before a lower-score repair is
  deferred. A second `5/5` mTLS/netem contrast now closes scoped gateway-native
  path feedback without any observation-API request: baseline rejects the same
  frame, while native smoothed RTT, RTT-variation proxy, and recovery loss
  accounting raise its score and admit it. Source accounting remains explicit,
  and the private aioquic recovery hooks are exact-version/signature gated. A
  third `5/5` mTLS/netem contrast keeps publisher debt at zero and proves an
  opt-in, provenance-tagged `gateway_derived_path` EWMA can change admission;
  startup requires native observation, client auth, and certificate publisher
  binding. A fourth `5/5` mTLS/netem gate closes the scoped application-outcome
  slice: reports must reference a known accepted frame and match the
  certificate URI-SAN publisher identity; impersonation, unknown frames, and
  malformed values fail closed, duplicate reports are idempotent, and a failed
  task delivery/deadline report with consistent task kind/status/success fields
  derives `gateway_derived_outcome` EWMA debt that includes task pressure and
  changes the next admission result. A fifth `5/5` mTLS/netem gate persists
  the authenticated outcome key and post-outcome admission snapshot atomically,
  then proves a replacement gateway restores the debt, suppresses a replay
  without double application, and admits/replays the low-criticality frame.
  A sixth `5/5` gate repeats this over networked PostgreSQL 16 with synchronous
  commits and fenced writer tokens `1->2`; all outcome/admission semantics and
  credential-scrubbing controls pass, while database-process failover remains
  explicitly false. A real concurrency-8 Nav2/RMF workload separately maps
  terminal Nav2 success/cancel results and an RMF submit response to the same
  strict schema, keeping result delivery separate from task success. It does
  not itself post those documents. A chained `5/5` Docker/netem gate consumes
  the exact output, seeds three known frames, and submits all three through an
  mTLS/URI-SAN-bound H3 client with outcome-session reuse; all 15 task outcomes
  are accepted and each run records exactly one canceled-task failure. A
  follow-on `5/5` gate now maps and submits those results before ROS teardown:
  the H3 submitter PID equals the client PID, `rclpy` and the node remain
  active, one verified mTLS handshake carries six streams with five reuses,
  and netem runs on both client and gateway. Repeating service requests and
  responses twice repaired a reproduced RMF batch response loss; all five
  canonical rounds then completed with zero nonzero container exits. The
  remaining gaps are nonblocking backend I/O on the new stateful public-API
  ngtcp2 server, globally optimal joint
  multi-demand scheduling, and clustered replicated capacity state. A separate `5/5`
  active/passive gate now persists retained frames,
  dedup keys, and consumer cursors with SQLite WAL `synchronous=FULL` and
  recovers them across three sequential aioquic instances per run. It proves
  duplicate suppression after A-to-B failover and cursor continuation after
  B-to-C failover. A follow-on `5/5` gate atomically commits frame plus
  admission/repair snapshot, restores exhausted quota and repair capacity on a
  replacement, and rejects policy-fingerprint drift. Legacy retained frames
  without policy state fail closed. A third `5/5` Docker/netem gate now adds a
  renewable single-writer lease, monotonic fence token, concurrent-standby
  startup rejection, and manual takeover that preserves admission/repair state.
  Frame/admission and consumer-cursor writes recheck the fence inside their
  SQLite write transactions; unit controls prove an expired writer cannot
  commit either path. A fourth `5/5` gate keeps B alive and waiting before A
  stops; B then acquires token 2 and serves restored state without being
  relaunched, with 203--208 ms stop-to-ready takeover. Timeout remains
  fail-closed. This closes automatic shared-file standby takeover only:
  active/active consensus, quorum leader election, replicated/distributed
  storage, and cross-node partition tolerance remain open. A subsequent `5/5`
  Docker/netem gate now runs the gateways against PostgreSQL 16 over the Docker
  network instead of a shared SQLite file. It validates synchronous commits,
  transactional admission state, advisory-lock lease serialization, monotonic
  fencing, pre-started standby takeover, and restored repair-budget rejection.
  The next durability blocker is now the database tier itself: add replicated
  PostgreSQL primary/standby failover (or a consensus-backed store), force
  primary loss during traffic, and prove no stale acknowledgement or split
  brain. A new `5/5` gate now covers the first half: synchronous PostgreSQL
  streaming replication, primary process kill, fail-closed active exit, manual
  replica promotion, multi-host gateway reconnect, token 2, and recovery of all
  seeded acknowledged frame/admission state in 3.129--3.154 s. The remaining
  blocker is automatic, quorum-backed database leadership plus explicit
  partition/split-brain and failback testing; `pg_ctl promote` is currently
  invoked by the experiment runner, so this is controlled HA evidence rather
  than production orchestration. A follow-on `5/5` campaign now adds a
  three-member etcd Raft DCS, two controllers, and a Docker-socket fence agent.
  It keeps a network-isolated primary process live while 2/3 DCS members are
  down, proves both controllers are denied, then restores quorum and elects
  exactly one TTL-lease winner. The agent validates the winner and lease with a
  linearizable mTLS DCS read, hard-fences the allowlisted primary, and only then
  permits automatic promotion. The fence HTTPS endpoint requires a CA-verified
  client certificate, binds CN to controller ID, rejects no-cert clients, and
  rejects an authenticated forged lease. The gateway resumes with all seeded
  state in 9.934--10.478 s. It then rebuilds the fenced primary from a fresh
  physical basebackup and dedicated slot, requires synchronous read-only
  streaming, positive flush/replay WAL, and the seeded frame/admission rows,
  thereby restoring Docker-scoped redundancy. Two automatic failback policy
  controllers now reject an intentionally asynchronous replica and preserve
  both database roles. Once synchronous zero-gap replication is restored under
  1/3 etcd, they also fail closed without quorum. At 2/3 quorum, exactly one
  failback lease winner is authorized through an mTLS switchover agent to
  gracefully stop the current primary before promotion. Gateway C resumes all
  state with fence token 3 over QUIC/H3 in 1.699--3.449 s. The former primary
  is then re-created as a synchronous read-only standby, restoring redundancy
  after failback. DCS client/peer, controller/fence, and failback/switchover
  paths require CA-verified mutual TLS. Remaining HA work is hardware/cloud
  fencing, certificate rotation/revocation, broader asymmetric/control-plane
  partition matrices, production orchestration, multi-region recovery, and
  operational hardening. The
  two-container Docker/netem
  variant repeats the same `rmw_publish` upload through a Docker network after
  applying `tc netem` on the client, records qdisc before/after counters, and
  requires parsed ngtcp2 path telemetry; the async-burst netem variant extends
  that proof to multiple queued uploads and aggregate server body-byte
  validation under the same netem path. A repeated async-burst soak runner now
  wraps the netem gateway probe over `10/10` iterations and aggregates `40`
  sent/enqueued frames, zero drops/failures, total bytes, qlog bytes, `208`
  qdisc packets, and `160` RTT samples. The first QUIC gateway take/download slice adds a
  shared-transport `gtlsclient --download` path: a Docker server hosts a
  `fleetrmw.data_frame.v1`, the C++ probe fetches it over QUIC/TLS/H3 GET,
  verifies byte-for-byte integrity, decodes the frame, and records received
  frame/byte counters. A follow-on opt-in RMW take smoke sets
  `FLEETQOX_RMW_QUIC_GATEWAY_TAKE_ON_DEMAND=1` and proves
  `rmw_take_serialized_message` can fill an empty subscription queue from the
  same QUIC GET path. A repeated RMW-take session-file probe then runs five
  QUIC GET takes with shared ngtcp2/GnuTLS session/tp/token files and verifies
  all downloads plus persisted files. A same-server bidirectional boundary
  probe now runs RMW publish POST followed by opt-in RMW take GET against one
  `gtlsserver` while sharing session/tp/token files across both client
  invocations for `5/5` repeated publish+take pairs. This remains
  subprocess-backed legacy boundary and is not a
  0-RTT/session-resumption claim, production QUIC backend, or final
  long stress/security campaign. A disable-early-data control now reruns this
  boundary with `FLEETQOX_RMW_QUIC_DISABLE_EARLY_DATA=1` and verifies the
  parser reports zero 0-RTT packets.
- Add a Docker stress/security campaign runner that aggregates security-options,
  FleetQoX security-policy, SROS2 permissions XML, UDP AEAD/peer auth,
  allocation, QoS event,
  content-filter, and QUIC async-burst soak probes into one summary artifact.
  The repeated profile now passes `48/48` component runs. The long profile now
  actively repeats complete workload rounds until the configured runtime
  threshold. The default one-hour netem run is now complete: eight rounds,
  `3793.205 s`, `80/80` component executions, and `1680/1680` probe runs with
  no failure, setting the long stress/security claim true.
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
- Keep the unified benchmark report current. The first aggregator now reads
  existing summary JSON artifacts plus `capabilities.json`, normalizes status,
  run counts, key metrics, and claim-boundary guards, then emits JSON/Markdown
  without rerunning benchmarks. The all-artifact history status includes
  retained failed/debug/negative-control runs; current capability-manifest
  status and explicit true/false claim counts are separate fields.
- Add documentation for installation, environment variables, runner
  prerequisites, and benchmark reproduction.
- Audit memory ownership, allocator usage, thread shutdown, socket lifecycle,
  graph lease cleanup, and long-running process behavior in `rmw_fleetqox_cpp`.

## Next Work Slice

The first P0 service-freshness/error slice is complete:
`fleetrmw_service_qos_probe` now verifies stale request and response frames are
dropped before application delivery, verifies unknown-response targets fail
without sending a frame, and verifies stable/distinct client endpoint GIDs plus
exact request `writer_guid`/sequence identity. The Docker probe passes on `udy`.
It also verifies that service availability requires exact type and compatible
request/response QoS. The remote graph lease smoke verifies QoS changes on
renewal immediately change matching and stale-descriptor removal still removes
by endpoint identity. Request ingestion independently enforces the same client
endpoint ID/type/QoS match, so bypassing discovery cannot enqueue an
incompatible request.

Graph guard conditions are now event-driven rather than probe-driven. Local
and remote endpoint mutations trigger live node graph guards only in the
affected ROS domain, unchanged lease renewals are deduplicated, and a dedicated
lease monitor triggers the same domain-scoped guard when a remote endpoint
expires. The native Docker CTest suite verifies local wait behavior and remote
add/renew/change/remove/expiry behavior.

ROS domain isolation is now implemented across the FleetRMW wire and graph
paths. `domain_id` is encoded in data, ACK/NACK, route, graph, service, and
action frames; missing v1 fields decode as domain `0`. Graph records and queries,
pub/sub and QoS-event matching, service availability/request delivery,
reliability feedback, and router route learning all filter by domain. The
Docker domain probe uses contexts `31` and `32` and passes graph guard/count,
data, service, and leased remote-graph positive/negative controls. RMW-produced
data frames now also include `type_name`, and the same probe proves a
same-topic/same-domain subscription with a different type receives no sample.

The wait/lifecycle contract slice is now complete for the implemented entity
families. `rmw_wait` enforces `max_conditions` for native subscription,
service, client, and event entries (with zero unbounded), rejects null array
entries, validates every waitable against the active wait-set context, and
exits when that context is shut down. `rcl`-owned timer guard conditions are
externally polled and excluded from capacity because Jazzy adds them to the RMW
guard array while omitting timers from the value passed to
`rmw_create_wait_set`; the Docker wait probe covers both boundaries. Publisher, subscription,
service, client, and service-availability operations reject a non-owner node
without mutating the entity. Docker proves bounded/unbounded, null,
same-domain cross-context, shutdown, and wrong-owner controls, then uses the
same entities successfully. `rmw_context_fini` now also frees and zeroes the
context after nested finalization errors, matching Jazzy best-effort cleanup.

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
nested RMF serialization, and lifecycle transition transport. A follow-on real
Nav2 planner/controller lifecycle probes now install/run upstream
`planner_server` and `controller_server`, configure
`nav2_navfn_planner::NavfnPlanner` and `dwb_core::DWBLocalPlanner` through the
FleetRMW router, publish repeated dynamic `/tf` (`map->odom`,
`odom->base_link`) over the same router, and verify both nodes reach
`active [3]`. A subsequent planner runtime probe publishes repeated
`nav_msgs/msg/OccupancyGrid` `/map` plus `/tf`, sends upstream
`nav2_msgs/action/ComputePathToPose`, and receives a successful Navfn path with
`error_code=0`. A companion controller runtime probe publishes repeated
`/map`, `/tf`, and `/odom`, sends upstream `nav2_msgs/action/FollowPath`, and
receives a successful DWB result with `error_code=0`. These artifacts
are followed by a full-stack CI-light Nav2 probe that starts `planner_server`,
`controller_server`, and `bt_navigator`, activates all three, publishes
repeated `/map`, `/tf`, and `/odom`, sends upstream
`nav2_msgs/action/NavigateToPose` through a minimal
`ComputePathToPose -> FollowPath` behavior tree, and receives `error_code=0`.
That same-pose pipeline is repeated twice with fresh Docker processes. A
moving-base probe now sends a short `x=0.6` goal while a fake base receives
Nav2 `/cmd_vel`, publishes dynamic `/odom` and `/tf` through FleetRMW, records
four command messages, moves about `0.406 m`, and still receives
`error_code=0`. An extended moving-base probe raises the goal to `x=1.2`,
still receives `error_code=0`, forwards `/cmd_vel`, and records about
`0.956 m` of fake-base motion. A direct upstream `behavior_server` probe activates
`nav2_behaviors::Spin`, sends `/spin`, forwards `/cmd_vel`, records eight
command messages, rotates the fake base about `0.616 rad`, and receives
`spin_error_code=0`. A NavigateToPose recovery-tree probe now starts
`planner_server`, `behavior_server`, and `bt_navigator`, runs a `RecoveryNode`
where `ComputePathToPose` intentionally fails with `MissingPlanner`, then
executes `Spin`; the top-level goal aborts as expected with
`navigate_to_pose_error_code=201`, but `/spin`, `/cmd_vel`, and fake-base
rotation prove the BT fallback branch. A recovered-success probe then executes
`Spin` before a short successful `ComputePathToPose -> FollowPath`
`NavigateToPose` goal, with `/spin`, `/cmd_vel`, `/map`, `/odom`, and `/tf`
forwarded through FleetRMW and `navigate_to_pose_error_code=0`; a repeated
wrapper runs the same recovered-success path twice with fresh Docker processes
and forwards `144` lifecycle/action service frames in aggregate. A long
moving-base wrapper repeats the unobstructed `x=1.2` Nav2 BT pipeline three
times with fresh Docker processes, requiring repeated success, aggregate
`/cmd_vel`, aggregate fake-base movement, and repeated FleetRMW action/service
traffic; this closes the scoped long-navigation smoke boundary. A concurrency-8
upstream Nav2/RMF action/service rerun also passes with `106/106` expected
service frames. That clean-build rerun additionally maps real Nav2 success and
cancel terminal results plus a successful RMF submit response into three
versioned application-outcome documents; all are delivered, while the canceled
goal correctly has `task_succeeded=false`. Gateway submission remains false in
this workload artifact, but a chained `5/5` mTLS/netem artifact submits those
exact documents with one reused outcome session and verifies three task updates
plus one failure per run. The separate live-process artifact repeats the full
workload `5/5`; every round submits from the same active ROS client PID over
one mTLS/H3 connection, records one canceled-task failure, and uses duplicate
service request/response transmissions to close the observed RMF response-loss
case. The next QUIC boundary is therefore the production server backend, not
task-result integration. A concurrency-16 rerun passes with `154/154` expected
service frames. A concurrency-32 rerun also passes with `250/250` expected
service frames, and a concurrency-64 rerun passes with `442/442` expected
service frames. A concurrency-128 rerun passes with `826/826` expected service
frames, a concurrency-256 rerun passes with `1594/1594` expected service
frames, a concurrency-512 rerun passes with `3130/3130` expected service
frames, a concurrency-1024 rerun passes with `6202/6202` expected service
frames, and a concurrency-2048 rerun passes with `12346/12346` expected service
frames after FleetRMW UDP large-frame fragmentation/reassembly and router
fragment passthrough for oversized action status/service bursts. The
concurrency-4096 single-batch Docker rerun now also passes. It retains one
unwindowed 4096-goal batch and spins the client executor during an automatic
`0.5 ms` inter-send interval; all `4096/4096` `NavigateToPose` goals complete,
all `4096/4096` RMF task submissions return, lifecycle startup/reset succeeds,
and the router forwards `98704` service frames with zero invalid frames. This
is a transport/workload request-burst claim, not proof of 4096 long-running
robot motions at once. The follow-on total-4096 admission-controlled rerun
remains a positive control with an 8-goal action window and `106088` forwarded
service frames. A
planner-level static-obstacle repair probe now blocks
`ComputePathToPose` with an occupancy-grid wall (`error_code=208`), then clears
the map and replans successfully with `14` path poses, so the scoped
planner/static-map `obstacle_field_recovery_claim` is closed. A follow-on
full-stack `NavigateToPose` obstacle retry probe starts planner, controller, and
BT navigator, aborts a blocked `x=0.8` goal with `error_code=208`, then retries
after a clear map and succeeds with `error_code=0`, `62/58` service frames, and
about `0.610 m` of fake-base motion. This closes the scoped
retry-after-clear full-stack obstacle claim. A same-goal `NavigateToPose`
obstacle recovery probe then keeps one goal active, observes a planner failure,
executes a real `Wait` recovery action, publishes a clear map during that same
goal, and succeeds with `error_code=0`, `1989/72` service frames, and about
`0.610 m` of fake-base motion; this closes the scoped same-goal external
static-map repair claim. A real `nav2_costmap_2d::ObstacleLayer` probe now
marks three lethal cells from dynamic `LaserScan` traffic, calls
`/local_costmap/clear_entirely_costmap`, and observes an empty costmap through
FleetRMW plus loopback netem; six service frames pass with zero invalid frames.
The scoped dynamic mark/clear gap is closed. A follow-on moving
`NavigateToPose` gate adds an inflation layer and bounded five-second failure
tolerance. Its persistent-obstacle control re-marks after clear, makes no
material progress, and cancels safely; its positive case removes the obstacle,
clears once, resumes the same goal, and succeeds near `x=0.96 m`. The router now
forwards terminal unrecoverable-loss notices by topic/domain and records zero
invalid frames. Its v2 world-frame circular-obstacle case then passes the
still-present obstacle in two independent Docker/netem runs with
`17.3-17.7 cm` lateral excursion, `11.9-12.7 cm` obstacle-edge clearance, and
status `4`. The scoped local-controller detour gap is closed. Version 3 then
disables LaserScan, inserts a persistent occupied wall into the global map
after a fourth goal starts moving, and uses two-Hz periodic planning. Two final
independent Docker/netem runs each publish `36` post-update paths; path
excursion reaches `0.826 m`, robot excursion is `0.545-0.547 m`, the robot
passes the wall, and the action succeeds with status `4`. The scoped global
dynamic-map replanning gap is closed. Arbitrary obstacle fields, production
recovery policy, upstream request counts beyond 4096, and sustained 4096-robot
physical navigation remain open.
The ROS CLI message
matrix remains `13/13`.

The repeated large-scale DDS/Zenoh comparison is complete as a gap register.
`run_large_scale_rmw_comparison.py` runs the same multi-topic envelope across
FleetRMW router, Fast DDS, Cyclone DDS, and Zenoh for `8/16/32` robots over
repetition IDs `7,13,29`. Netem is applied after discovery, every publisher
uses the same six-second reliability horizon, and Zenoh uses its required
router/session configuration. The current-image rerun passes all `36/36`
system/scale/seed rows. Because FleetRMW uses a router hop while DDS/Zenoh rows
are direct, the report keeps the topology caveat explicit and does not claim
superiority.
The v2 artifact formalizes that boundary with allowed direct-RMW and
Fleet-router scopes plus a disallowed cross-scope superiority claim;
`direct_claim_allowed=false` is machine-readable.

`run_same_hop_rmw_comparison.py` closes the hop-count gap as a separate study.
Its historical v1 artifact used one common typed rclpy `std_msgs/String` relay
for Fast DDS, Cyclone DDS, and Zenoh, while FleetRMW retained its raw-frame
router. Under the same roaming profile, loss scale `0.25`, five samples/topic,
six-second reliability horizon, and seeds `7,13,29`, that study records `32/36`
passing rows: Cyclone/Zenoh `9/9`, FleetRMW `8/9`, and Fast DDS `6/9`. Relay
delivery is `5030/5040`; failures are retained as measured loss, not
infrastructure reruns.

The v2 harness replaces that typed middle with a C++ `rclcpp`
generic-subscription/generic-publisher relay. The relay republishes
`rclcpp::SerializedMessage` directly, reports serialized byte/count evidence,
and explicitly reports `application_deserialization=false`. A fresh full
`8/16/32`-robot, seed `7/13/29` Docker/netem matrix passes `35/36`. Fast DDS,
Cyclone DDS, and Zenoh pass `9/9` each and relay `5040/5040` payloads. FleetRMW
passes `8/9`; its retained 32-robot seed-29 row delivers `319/320`. All 36
publishers report supported/completed ACK waits and zero unacked topics. The
machine-readable contract sets hop/profile/RELIABLE and serialized-payload
state matching true. It does not claim byte-identical serialization across
RMWs. Delivery/reliability comparison remains allowed, while latency
superiority, full middle-hop equivalence, and broad cross-RMW superiority
remain false because raw FleetRMW frame forwarding still differs from RMW
endpoint termination/republish.

The full-scale run exposed a separate FleetRMW initial-sequence reliability
bug: a reader that first observed sequence 2 could cumulatively acknowledge
sequence 1 even when sequence 1 was dropped. ACK feedback now carries the
lowest observed sequence and bounds cumulative acknowledgement to that floor.
A deterministic Docker regression drops sequence 2 for NACK repair, then
drops sequence 1 for timeout repair; both phases receive `one/two/three`.

Next continue P0/P2 in this order:

1. Extend the completed moving-goal stop/clear/resume, persistent local detour,
   and global dynamic-map replan paths with arbitrary/multiple obstacle fields,
   repeated longer-duration controls, and an explicit production-policy
   boundary. Then push beyond the proven unwindowed total-4096 upstream request
   workload without presenting request completion as simultaneous physical
   navigation.
2. Preserve both completed comparison contracts, increase beyond the current
   five samples and three independent repetitions, and investigate the one
   retained FleetRMW `319/320` delivery row. Match transport-envelope middle
   semantics before any latency-superiority claim.
3. Broaden native C++ type-support regression coverage and close or explicitly
   scope the remaining optional RMW ABI surfaces before production-ready status.
4. Increase frontier repetitions so the `32`-robot latency-mean confidence
   interval can be estimated more tightly around the `400 ms` boundary.

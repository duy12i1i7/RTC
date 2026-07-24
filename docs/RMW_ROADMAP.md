# RMW Roadmap

## Why Not Start With Full RMW Immediately?

A ROS 2 RMW implementation must support node creation, publishers,
subscriptions, wait sets, graph introspection, type support, QoS, services,
events, and more. Building that first would hide the research question inside
months of glue code.

The research risk is the communication semantics. Therefore the first milestone
is a standalone FleetQoX runtime and simulator.

## Milestone 0: FleetQoX Simulator

Implemented in this repository:

- QoX flow model;
- Causal Semantic Deadline Scheduler;
- static baselines;
- deterministic fleet benchmark.

## Milestone 1: ROS 2 Sidecar Bridge

Keep normal DDS local. Add a ROS 2 node that:

- observes local topics;
- classifies flows;
- bridges selected data over FleetQoX transport;
- emits capability graph updates;
- enforces admission control.

This proves value without touching RMW internals.

Implemented sub-milestones:

- dependency-free `Ros2Sample`/QoS shim boundary;
- live `rclpy` ingress bridge into the sidecar;
- robot-local command lease for typed `cmd_vel`;
- qualified odometry/laser-scan wrappers with a consumer-side quality gate;
- dependency-free `FleetRmwProjectedSample` contract that separates sample
  identity, admission provenance, fidelity, and qualified delivery metadata from
  the ROS 2 egress adapter.
- end-to-end `contract_id` propagation from ROS 2 shim batch to sidecar event,
  projection quality, qualified wrapper, and quality-gate log.
- source-derived `source_sample_id` propagation, using ROS header stamp
  metadata or RMW-facing publisher GID/sequence metadata when available, and
  falling back to `contract_id` otherwise.
- native `FleetRmwSampleEnvelope` propagation through shim batches and sidecar
  events, so publisher identity and source sequence can be owned by FleetRMW
  instead of inferred from `rclpy` callback metadata.
- dependency-free `fleetrmw.data_frame.v1` codec that narrows sidecar packet
  events into transport frames with contract, route, timing, sample envelope,
  and payload fields.
- profile/objective-aware transport selector that ranks measured packet-format
  and RMW candidates from repeated ROS 2 live-bridge evidence under
  safety/utility, teleop-latency, autonomy-safety, or throughput objectives.
- runtime `TransportBinding` payload from selector summary to ROS 2 shim batch
  and sidecar runtime packet-format selection.
- rule-based `TransportBindingManager` that infers Wi-Fi/WAN/roaming from link
  telemetry and selects the corresponding measured binding.
- adaptive binding estimator with telemetry smoothing, measured profile
  prototype scoring, hysteresis, and minimum dwell before profile switching.
- live continuous binding in `Ros2LiveSampleBuffer`, where the bridge refreshes
  `TransportBinding` and adaptive profile estimates on each batch before the
  sidecar chooses packet framing.
- Docker T3 profile-transition harness that applies timed Wi-Fi/WAN/roaming
  `tc netem` changes during one ROS 2 live bridge run and records adaptive
  binding switches in the sidecar decision log.
- Docker T3 adaptive-vs-static transition binding matrix that compares adaptive
  binding against static Wi-Fi, static WAN, and static roaming bindings under
  the same live ROS 2 transition workload.
- Three-seed Docker T3 adaptive-vs-static transition binding matrix that
  quantifies switch latency, missing switches, and flapping while comparing the
  same adaptive/static bindings over seeds `7,13,29`.
- Three-seed Docker T3 dynamic-objective binding matrix that changes the
  active QoS/QoE objective during live ROS 2 transition runs, then records
  matched profile switches, matched objective switches, policy switches,
  switch latency, and flapping in the sidecar decision log.
- Two-robot, three-seed Docker T3 dynamic-objective binding matrix that expands
  the same live transition session across `robot_0000` and `robot_0001`, then
  records robot coverage in sidecar decisions, receiver packets, and egress
  publications.
- Two-robot, three-seed Docker T3 local-services dynamic-objective matrix that
  makes the local controller, projection quality gate, and monitor
  namespace-aware and records both robot IDs through lease decisions, gate
  decisions, and monitor observations.
- Two-robot, three-seed Docker T3 per-robot QoS budget matrix that computes
  `fleetrmw.per_robot_qos.v1` from sidecar decision/receiver logs, reports
  Jain fairness plus absolute per-robot delivery/deadline budgets, and exposes
  robot-level SLO failures that aggregate fleet means hide.
- Per-robot budget-aware admission wrapper that keeps virtual queues for
  control-delivery shortfall and deadline-risk excess, then injects robot SLO
  pressure into future critical-flow scheduling. The wrapper is exposed as
  `fleetqox_semantic_contract_budgeted` for the sidecar path.
- ROS 2 Docker validation of `fleetqox_semantic_contract_budgeted` under the
  two-robot dynamic-objective transition matrix. The first version lowers
  deadline miss and p95 latency versus the baseline but does not improve the
  budget pass ratio.
- Tail-risk budget validation for `fleetqox_semantic_contract_budgeted` that
  adds network-tail-risk pressure and pressure-aware semantic shaping. In the
  short two-robot Wi-Fi/WAN/roaming matrix it raises budget pass from `0.3333`
  to `1.0000` and mean minimum per-robot control delivery from `0.8950` to
  `0.9222`, while exposing the next QoE gap through higher p95 latency and a
  large seed-`13` latency spread.
- Sidecar `robot_feedback` protocol for feeding observed per-robot
  delivery/deadline outcomes into the active budget-aware controller. Unit
  coverage verifies that feedback changes the next scheduling round.
- ROS 2 egress feedback producer and multi-client sidecar TCP server. A one-seed
  Docker smoke applies `28` feedback records with `0` feedback connection
  failures, proving the live feedback path is connected. The feedback law is
  still too aggressive for benchmark use: the smoke fails the per-robot budget
  and raises p95 latency to `293.18 ms`.
- Damped egress feedback for the same live path. The controller now scales
  external feedback by feedback-window sample count, caps deadline-risk feedback,
  and excludes perception-only deadline misses from the core robot-budget
  feedback signal. A one-seed Docker smoke improves aggregate control delivery
  from `0.9024` to `0.9412` and reduces pressure overreaction
  (`pressure_shaping` `74` to `42`, `drop` `32` to `22`, `defer` `38` to `18`).
  It is still not benchmark-ready because budget pass remains `0.0` and p95
  rises to `399.36 ms`.
- QoE/latency-aware egress feedback boundary. Feedback windows now include
  mean/tail latency, mean deadline, latency/deadline ratio, and latency sample
  count. The controller stores that signal as `latency_deficit` so critical
  service pressure remains control/deadline-driven, while non-critical shaping
  can respond to p95/tail debt. A one-seed Docker smoke improves deadline miss
  to `0.5097` and p95 to `302.53 ms` versus the damped feedback run, but budget
  pass remains `0.0` and worst-robot control delivery falls to `0.8718`.
- Control-first QoE feedback gate. Latency debt now contributes to shaping
  pressure only when a robot has control-delivery headroom above the SLO. A
  one-seed Docker smoke recovers aggregate control delivery to `0.9136`,
  worst-robot control delivery to `0.9024`, RX to `163`, and utility to
  `906.17`. Budget pass remains `0.0` because worst-robot deadline miss is
  `0.7125`, so deadline-first feedback is the remaining hard-SLO gap.
- Experimental deadline-first policy,
  `fleetqox_semantic_contract_budgeted_deadline_first`. It adds deadline debt as
  extra non-critical shaping pressure without changing critical service pressure.
  A one-seed Docker smoke reaches aggregate control delivery `0.9846`,
  worst-robot control delivery `0.9697`, RX `144`, loss `0.0649`, and utility
  `797.30`. Budget pass remains `0.0` because worst-robot deadline miss is
  `0.5694`, so tail-risk remains the hard-SLO benchmark.
- Multi-source ROS-side feedback producers. The ROS 2 live bridge can now send
  egress, local-controller, and projection-quality feedback to the sidecar in
  the same run. The one-seed smoke applies `177` total records (`24` egress,
  `60` local-controller, `93` quality-gate), raises RX to `166`, and raises
  utility to `912.44`, but budget pass remains `0.0`; worst-robot control
  delivery falls to `0.8049`, worst-robot deadline miss is `0.6000`, and p95 is
  `320.51 ms`. This makes multi-source arbitration and credit assignment the
  next hard control-plane gap.
- Source-aware feedback arbitration. The budget controller now treats feedback
  as partial, source-responsibility-weighted evidence instead of implicit
  full-state credit. Egress updates receiver-visible delivery/latency debt and
  non-control deadline debt, local-controller feedback updates command
  application evidence with separate success/failure weights, and
  projection-gate feedback updates only QoE/latency debt. The best measured
  multi-source branch at that point combines arbitration v2 with the
  deadline-first policy:
  RX `175`, utility `953.89`, control delivery `0.9500`, and p95 `284.66 ms`.
  Under the corrected control-lease ownership rule, the same existing log
  passes the hard per-robot budget: minimum control delivery `0.9000`,
  worst-robot deadline miss `0.3483`, RX Jain `0.9997`, control Jain `0.9972`,
  and deadline-success Jain `0.9946`. A fresh ROS 2 smoke of the corrected live
  path also passes: RX `134`, control delivery `0.9394`, deadline miss
  `0.2164`, p95 `262.47 ms`, minimum control delivery `0.9091`, and
  worst-robot deadline miss `0.2319`. The repeated 3-seed hard-SLO path now
  passes after adding redundant control-lease transmission, `event_id`
  de-duplication, deadline feasibility filtering, and a transport-volatility
  guard for low-confidence binding epochs: budget pass `1.0000`, mean RX
  `70.3333`, control delivery `0.9872`, deadline miss `0.0000`, p95
  `241.78 ms`, and worst-robot deadline miss `0.0000`. This is the safe
  envelope; quality-gate coverage is `0.0000`, so QoE restoration remains open.
- Bounded QoE recovery inside the volatility guard. The sidecar now admits only
  low-cost `semantic_delta`/`degraded` state, perception, or human-QoE probes
  when the binding estimator has enough confidence, margin, dwell, and
  predicted slack, with a per-robot/class period limit. `semantic_delta`
  odometry is classified as `semantic_projection` at the qualified projection
  boundary. The current 3-seed stable-probe run keeps budget pass `1.0000` and
  restores quality-gate robot coverage to `2.0000` with RX `77.6667`, control
  delivery `0.9870`, deadline miss `0.0171`, p95 `293.40 ms`, and worst-robot
  deadline miss `0.0264`. This is a minimal safe QoE recovery point; richer
  state/perception recovery still needs a better utility optimizer.
- Fleet-quota QoE recovery for the ROS 2 live bridge. The volatility guard now
  selects QoE probes at batch level with a sublinear quota
  `ceil(scale * sqrt(active_robot_count))`, a per-robot cap, and robot-rotation
  ranking. It can also pass low-cost semantic probes during uncertain binding
  epochs instead of waiting for the estimator to become stable before collecting
  QoE evidence. A four-robot ROS 2 live smoke with `rmw_zenoh_cpp` observes all
  four robots through sidecar decisions, receiver packets, egress publications,
  local lease decisions, quality-gate decisions, and monitor logs. It keeps hard
  budget pass `1.0000`, control delivery `1.0000`, worst-robot deadline miss
  `0.1154`, and quality-gate robot coverage ratio `1.0000`, with `9` accepted
  qualified projections. This closes the structural N-robot QoE recovery gap
  for the sidecar path; repeated longer N-robot matrices are still needed before
  claiming statistical dominance.
- N-robot QoE recovery matrix runner. `scripts/run_ros2_n_robot_qoe_quota_matrix.py`
  now wraps the live bridge over `robot-count x seed` rows and writes an
  aggregate JSON/Markdown report. The first repeated row reruns the four-robot
  QoE quota scenario over seeds `7,13,29`: all `3/3` seeds run, hard budget pass
  is `1.0000`, quality-gate robot coverage ratio is `1.0000`, control delivery
  is `0.9957`, worst-robot deadline miss is `0.1209`, and p95 is
  `422.22 ms`. The same runner now also records the first `8`-robot scale row
  over seeds `7,13,29`: all runs complete and robot coverage remains `1.0000`
  through decisions, receiver, egress, lease, and monitor logs, but hard budget
  pass falls to `0.0000`, control delivery to `0.7859`, p95 rises to
  `1387.09 ms`, and minimum per-robot control delivery falls to `0.6164`. This
  upgrades the four-robot evidence from a one-seed smoke to a repeatable
  short-run matrix and identifies `8` robots as the current hard-SLO scale
  frontier.
- N-aware command service allocator. `RobotBudgetAwareAdmissionController` now
  has an optional post-policy control floor that activates when the active robot
  count crosses a configured threshold. If a robot has control candidates but no
  command representation admitted in the current tick, the allocator picks the
  smallest feasible command transform, reclaims non-control capacity when
  possible, and records `robot_budget=n_aware_control_floor`. It is enabled for
  the deadline-first and action-deadline policy branches used by the current ROS
  2 QoE quota experiments. Unit coverage verifies the intended eight-robot
  behavior. Docker reruns show that allocator pressure is necessary but not
  sufficient: tail robots still fall below the hard control service floor when
  transition loss and retransmit bursts coincide.
- Paced control-lease redundancy. The sidecar runtime can now pace redundant
  control-lease packets across batches instead of emitting all duplicates in
  the same UDP burst. Deadline-first policy branches enable the pacing by
  default while still respecting explicit redundancy overrides. Unit coverage
  verifies the retransmission queue, transition-uncertainty guard, adaptive
  lease redundancy, terminal replay history, and stale/duplicate lease
  rejection. The Docker path was also hardened so Zenoh readiness is checked
  before ROS 2 nodes start, and timed netem transitions now begin after the
  publisher window rather than during discovery/bootstrap.
- Eight-robot hardening audit. The `8`-robot live-bridge experiments separated
  infrastructure failure from algorithmic failure and rejected several tempting
  transport shortcuts. Terminal replay, fixed ACK windows, persistent feedback
  clients, and piggyback-first adaptive ACK can recover selected runs, but they
  do not close all repeated seeds. Immediate or urgent ACK/NACK feedback is a
  negative control: it overloads the sidecar feedback path and collapses control
  delivery. The winning mechanism is source-sequence ACK/NACK plus sender-side
  recovery memory derived from the transport contract. Control and supervisory
  intents now use an effective wire lifespan, events preserve raw
  `source_lifespan_ms`, and the ACK/NACK retransmit ledger is retained for a
  bounded horizon computed from deadline, measured RTT/jitter, and ROS
  `liveliness_lease_ms`. The repeated `8`-robot Wi-Fi/WAN/roaming row over
  seeds `7,13,29` now passes hard budget `3/3`, with mean control delivery
  `0.9902`, mean minimum per-robot control delivery `0.9804`, loss `0.0311`,
  p95 `1085.30 ms`, and quality-gate coverage `1.0000`. This converts
  `8` robots from an open hard-SLO frontier into the regression gate for the
  next transport/RMW boundary.
- Source-sequence ACK/NACK primitive. `fleetqox/rmw_ack.py` defines
  `fleetrmw.ack_nack.v1`, stable `fack1-*` IDs, per-stream gap detection, compact
  missing sequence ranges, and duplicate/out-of-order state. The sidecar ACK
  tracker can now clear retransmit state via legacy event IDs or source-aware
  ACKs using `source_sample_id` /
  `(robot_id, source_topic, source_sequence_number)`, and it consumes NACK
  missing ranges by requesting retransmission of matching tracked control-lease
  events. This is the concrete bridge from the Python sidecar feedback path
  toward a true RMW publish/take ACK/NACK loop.
- Minimal FleetRMW publish/take boundary. `fleetqox/rmw_boundary.py` now exposes
  an in-memory `FleetRmwBoundary` that assigns native publisher identity and
  source sequence, emits `fleetrmw.data_frame.v1`, takes frames back into a
  local sample view, and produces `fleetrmw.ack_nack.v1` from the receiver-side
  source stream. `scripts/run_rmw_boundary_smoke.py` proves the loop over a
  multi-robot command workload and can intentionally skip a take to produce a
  NACK gap. This is still not a C++ RMW ABI implementation, but it is the first
  executable publish/take contract for replacing DDS at the communication
  boundary.
- Socket-backed FleetRMW boundary smoke. `fleetqox/rmw_socket.py` wraps the same
  publish/take contract with UDP sockets: a talker sends
  `fleetrmw.data_frame.v1`, a listener takes it, and `fleetrmw.ack_nack.v1`
  returns to the talker source socket. `fleetqox/rmw_transport_loop.py` keeps
  one talker/listener pair alive across many source streams and handles
  NACK-triggered retransmission from the talker ledger. `scripts/run_rmw_socket_smoke.py`
  proves the loop with a delayed source sequence: `6` frames published, `6`
  taken, `6` ACK/NACK records, one NACK-triggered retransmission, one missing
  range, and one late out-of-order repair. This is the first transport-backed
  executable contract below the sidecar path. The same smoke can run
  deterministic multi-gap patterns;
  `results_rmw_socket/socket_smoke_skip_every2_summary.json` uses `3` robots x
  `5` samples with `--skip-every 2`, takes all `15` frames, and performs `6`
  NACK-driven retransmissions.
- C++ FleetRMW transport-boundary reference. `ros2_ws/src/rmw_fleetqox_cpp`
  now contains a C++ package with `fleetrmw.data_frame.v1` encode/decode,
  receiver-side ACK/NACK gap detection, and the
  `fleetrmw_transport_loop_smoke` UDP executable. The smoke artifact
  `results_rmw_socket/cpp_transport_smoke_summary.json` mirrors the Python
  socket loop: `15` frames published, `15` taken, `15` ACK/NACK records, `6`
  retransmissions, and `6` repaired missing ranges. This is not yet the ROS 2
  RMW ABI; it is the C++ executable reference the ABI layer must preserve. The
  package also builds the first `librmw_fleetqox_cpp` lifecycle skeleton,
  exporting `rmw_get_implementation_identifier()`,
  `rmw_get_serialization_format()`, init-options, context
  init/shutdown/fini, and create/destroy node symbols. It builds under Docker
  `ros:jazzy-ros-base` through `colcon` alongside `fleetrmw_interfaces`. The
  Docker artifacts
  `results_rmw_socket/docker_cpp_transport_smoke_summary.json` and
  `results_rmw_socket/docker_cpp_frame_probe_summary.json` prove both the C++
  UDP smoke and Python-to-C++ data-frame decode in a ROS 2 container. The
  lifecycle artifact `results_rmw_socket/docker_rmw_lifecycle_probe_summary.json`
  proves `rmw_init_options_init -> rmw_init -> rmw_create_node ->
  rmw_destroy_node -> rmw_shutdown -> rmw_context_fini ->
  rmw_init_options_fini` with status `ok`. The serialized pub/sub artifact
  `results_rmw_socket/docker_rmw_serialized_pubsub_probe_summary.json` proves
  publisher/subscription handle allocation, serialized publish/take through
  `fleetrmw.data_frame.v1`, matched-endpoint counts, and destroy paths over a
  UDP loopback socket path with `socket_frames_sent=1` and
  `socket_frames_received=1`.
  The wait artifact `results_rmw_socket/docker_rmw_wait_probe_summary.json`
  now proves graph registration automatically triggers the node graph guard;
  remote graph lease CTest additionally proves renewal deduplication and
  automatic expiry notification, alongside `rmw_wait` readiness for a local
  serialized subscription. The graph artifact
  `results_rmw_socket/docker_rmw_graph_probe_summary.json` proves
  `rmw_get_node_names`, `rmw_get_topic_names_and_types`,
  `rmw_count_publishers`, and `rmw_count_subscribers` for the in-process graph.
  The domain artifact
  `results_rmw_socket/docker_rmw_domain_isolation_probe_summary.json` extends
  this boundary to contexts `31` and `32`: graph guard wakeups, graph records,
  serialized data, service discovery/request delivery, ACK/NACK identity, and
  router routes are domain-scoped, while legacy v1 frames without `domain_id`
  decode into domain `0`.
  The inter-process artifact
  `results_rmw_socket/docker_rmw_interprocess_pubsub_probe_summary.json`
  proves an env-configured publisher process can send a serialized
  `fleetrmw.data_frame.v1` payload to a subscriber process bound at
  `127.0.0.1:48101`, with publisher `peer_count=1`,
  `socket_frames_sent=1`, subscriber `socket_frames_received=1`, and `taken=true`.
  The multi-container router artifact
  `results_rmw_socket/docker_rmw_multicontainer_router_probe_summary.json`
  proves the same path across four Docker containers on a private network:
  subscriber first sends `fleetrmw.route_advertisement.v1`, router learns one
  route, and publisher -> router -> subscriber then carries the data frame by
  container hostname. Publisher/subscriber creation also emits
  `fleetrmw.graph_advertisement.v1`; the router forwards those advertisements
  to a graph-only observer peer, and the observer applies them into the RMW graph
  cache without creating a local publisher or subscription on the observed
  topic. The router reports one learned route, at least one route
  advertisement, at least the initial two graph advertisements,
  `graph_peer_count=1`, `received_frames=1`, and `forwarded_frames=1`; lease
  renewals may increase advertisement occurrence counters without duplicating
  the observer's endpoint records. The
  subscriber reports `socket_frames_received=1` and `taken=true`; the observer
  reports `topic_found=true`, `publisher_count=1`, `subscriber_count=1`, and
  a positive graph-frame receive count. The remote graph lease artifact
  `results_rmw_socket/docker_rmw_remote_graph_lease_probe_summary.json` proves a
  remote publisher advertisement with a short lease is visible before expiry and
  removed from graph queries afterward. The typed pub/sub artifact
  `results_rmw_socket/docker_rmw_typed_pubsub_probe_summary.json` proves
  `rmw_publish`/`rmw_take` can carry a fixed-size FleetRMW type-erased message
  through the same data-frame socket path. The introspection C artifacts
  `results_rmw_socket/docker_rmw_std_msgs_string_probe_summary.json` and
  `results_rmw_socket/docker_rmw_geometry_twist_probe_summary.json` prove real
  ROS message structs can now pass through `rmw_publish`/`rmw_take` over the
  FleetRMW data-frame socket path: `std_msgs/msg/String` covers ROS C strings,
  and `geometry_msgs/msg/Twist` covers nested primitive fields for `cmd_vel`.
  The first `rcl` artifact
  `results_rmw_socket/docker_rcl_string_probe_summary.json` proves a real
  `rcl` node, publisher, and subscription can publish and take
  `std_msgs/msg/String` through `rmw_fleetqox_cpp`. The first ROS CLI graph
  artifact `results_rmw_socket/docker_ros2_topic_list_probe_summary.json` proves
  `ros2 topic list --no-daemon --spin-time 2 -t` can observe a FleetRMW `rcl`
  talker topic and its `std_msgs/msg/String` type. The ROS CLI endpoint-info
  artifact `results_rmw_socket/docker_ros2_topic_info_probe_summary.json` proves
  `ros2 topic info --no-daemon --spin-time 2 --verbose` can observe a remote
  FleetRMW publisher endpoint with node metadata, endpoint GID, and QoS profile;
  this is backed by endpoint-rich `fleetrmw.graph_advertisement.v1` frames and
  throttled publisher graph lease renewal for late-joining observers. The node
  graph artifact `results_rmw_socket/docker_ros2_node_info_probe_summary.json`
  proves `ros2 node list --no-daemon` discovers the remote FleetRMW talker and
  `ros2 node info --no-daemon` reports its publisher topic/type through
  by-node graph APIs. The first
  ROS CLI pub/echo
  artifact `results_rmw_socket/docker_ros2_pub_echo_probe_summary.json` proves
  `ros2 topic pub` can send a `std_msgs/msg/String` that
  `ros2 topic echo --once` receives through `rmw_fleetqox_cpp`. The ROS CLI
  message-matrix artifact
  `results_rmw_socket/docker_ros2_cli_message_matrix_summary.json` extends this
  to `std_msgs/msg/String`, `builtin_interfaces/msg/Time`,
  `builtin_interfaces/msg/Duration`, `geometry_msgs/msg/Twist`,
  `geometry_msgs/msg/PoseStamped`, `sensor_msgs/msg/LaserScan`,
  `sensor_msgs/msg/PointCloud2`, `nav_msgs/msg/Odometry`,
  `nav_msgs/msg/Path`, `trajectory_msgs/msg/JointTrajectory`,
  `diagnostic_msgs/msg/DiagnosticArray`,
  `fleetrmw_interfaces/msg/SampleIdentity`, and
  `fleetrmw_interfaces/msg/ProjectionQuality`, covering signed/unsigned
  time fields, nested messages, fixed arrays, dynamic primitive sequences,
  dynamic sequences of nested pose messages, binary blobs, trajectories,
  diagnostics, and FleetRMW quality metadata. The RMW now
  dispatches
  generic `rosidl_typesupport_c` maps into introspection-C handles and exposes
  service/client handle lifecycle and service graph support for node startup
  paths such as type-description services. The ROS CLI service-graph artifact
  `results_rmw_socket/docker_ros2_service_graph_probe_summary.json` proves
  `ros2 service list --no-daemon --spin-time 2 -t` discovers
  `/fleetqox/set_bool [std_srvs/srv/SetBool]` from a late-joining observer and
  `ros2 node info --no-daemon` reports the service server through by-node graph
  APIs. The service-call artifact
  `results_rmw_socket/docker_ros2_service_call_probe_summary.json` proves
  `ros2 service call /fleetqox/set_bool std_srvs/srv/SetBool "{data: true}"`
  receives `success=True` through `fleetrmw.service_frame.v1` request/response
  frames over the same non-DDS RMW transport. The router-mediated artifact
  `results_rmw_socket/docker_router_service_call_probe_summary.json` proves the
  same service call when server and client peer only with
  `fleetrmw_udp_router_probe`; the router learns service/client routes from
  graph advertisements and forwards the request/response frames. The QoS
  service freshness artifact
  `results_rmw_socket/docker_rmw_service_qos_probe_summary.json` proves stale
  request and response service frames are counted as expired and skipped before
  `rmw_take_request` / `rmw_take_response` delivery; it also proves stable and
  distinct client endpoint GIDs and exact agreement between
  `rmw_get_gid_for_client` and request `writer_guid`. It also proves that
  `rmw_service_server_is_available` accepts a matching endpoint while filtering
  same-name type and response-QoS mismatches; remote renewal updates cached
  service QoS. Direct mismatch sends are also rejected before the service
  queue, proving enforcement beyond the discovery API. The service error artifact
  `results_rmw_socket/docker_rmw_service_error_probe_summary.json` proves empty
  response queues do not fabricate responses, malformed response payloads return
  controlled errors with `taken=false`, and invalid service frames are rejected
  without creating a response. The ROS CLI service-timeout artifact
  `results_rmw_socket/docker_ros2_service_timeout_probe_summary.json` proves a
  real `ros2 service call` sends a request through FleetRMW, the server sees it,
  the response is intentionally delayed, and the CLI exits with timeout code
  `124` without printing a success response. The router-mediated malformed
  response artifact
  `results_rmw_socket/docker_router_ros2_malformed_service_response_probe_summary.json`
  proves that a correctly routed but invalid serialized response makes the CLI
  exit with code `1`, prints no response, and surfaces the RMW/rcl deserialize
  diagnostic instead of timing out. The action-frame contract
  artifact `results_rmw_socket/docker_rmw_action_frame_probe_summary.json`
  proves `fleetrmw.action_frame.v1` round-trips goal, feedback, status, result,
  and cancel roles with lifespan checks and rejects service-frame schema input.
  The router-mediated action artifact
  `results_rmw_socket/docker_rmw_router_action_frame_probe_summary.json` proves
  `fleetrmw_udp_router_probe` learns `action_server` and `action_client` graph
  routes, forwards `goal/cancel` toward the server, and forwards
  `feedback/status/result` toward the client.
  The first real action API artifact
  `results_rmw_socket/docker_rmw_rclpy_action_probe_summary.json` proves a
  same-process `rclpy.action.ActionServer` and `ActionClient` can discover a
  `tf2_msgs/action/LookupTransform` server, accept a goal, execute it, and
  receive a GetResult response through `rmw_fleetqox_cpp`.
  The router-mediated real action artifact
  `results_rmw_socket/docker_rmw_router_rclpy_action_probe_summary.json` proves
  the same action client/server operation completes across separate Docker
  containers that peer only with `fleetrmw_udp_router_probe`; the router
  observes ten action service frames and forwards all ten. The client observes
  `ActionClient.server_is_ready()` before send and after result, feedback for
  both success and cancel goals, status samples through `CANCELING` and
  `CANCELED`, success status `4`, and canceled status `5`.
  The action QoS artifact
  `results_rmw_socket/docker_rmw_router_rclpy_action_qos_probe_summary.json`
  proves graph-advertised lifespan admission on real feedback and status: a
  fresh row delivers both streams, while an expired row drops two feedback and
  seven status frames without breaking goal/cancel/result completion. Its
  deadline row scopes a three-frame burst to the action topic prefix and
  forwards feedback deadline `5 ms` before status deadline `100 ms`.
  The QoS
  artifact `results_rmw_socket/docker_rmw_qos_probe_summary.json` proves the
  first measured queue QoS subset: `KEEP_LAST depth=1` keeps only the newest
  serialized sample, and subscription `lifespan` drops an expired frame before
  delivery. The router QoS artifact
  `results_rmw_socket/docker_router_qos_drop_probe_summary.json` proves the
  same `lifespan` contract at the fleet data plane: the UDP router learns
  publisher QoS from graph advertisements, applies a controlled forwarding
  delay, and drops the expired data frame instead of delivering stale control
  state. The router priority artifact
  `results_rmw_socket/docker_router_qos_priority_probe_summary.json` moves the
  data plane from filtering to scheduling: within a short scheduler window,
  the router snapshots publisher deadline QoS learned from graph
  advertisements and forwards a later-arriving critical topic before an
  earlier-arriving bulk topic. The companion matrix artifact
  `results_rmw_socket/docker_router_qos_priority_matrix_summary.json` compares
  the same workload against FIFO routing and records the order change from
  `bulk -> critical` to `critical -> bulk`. It also handles the waitable
  pointer form used by
  `rclpy` executors, where `rmw_wait` receives subscription implementation data
  instead of the full `rmw_subscription_t *`. Optional RMW ABI stubs cover loader-resolved
  surfaces such as loaned messages, events, network-flow endpoints, and callbacks.
  Dynamic serialization support plus dynamic take/with-info now load the optional
  `rosidl_dynamic_typesupport_fastrtps` plugin at runtime;
  unsupported surfaces return controlled `RMW_RET_UNSUPPORTED` instead of
  unresolved loader symbols. Broader service QoS semantics, sequence/C++
  type-support coverage, and real `rcl_action` APIs are still open ABI work.
- ROS 2 egress ACK/NACK piggyback. The live egress bridge now tracks received
  source sequences with `RmwAckNackTracker` and attaches `fleetrmw.ack_nack.v1`
  records to regular feedback windows. This means the same gap signal generated
  by the minimal boundary can reach the sidecar runtime in the current Docker
  bridge path before a C++ RMW exists. The first seed-`13` audit with fixed
  retransmit memory was negative, but the follow-up liveliness-horizon design
  passes the repeated `8`-robot matrix: hard budget `3/3`, mean minimum
  per-robot control delivery `0.9804`, p95 `1085.30 ms`, and quality coverage
  `1.0000`. The mechanism is now ready to move from sidecar-owned runtime state
  into FleetRMW-owned publish/take metadata.
- Action-aware deadline attribution. Egress feedback now carries
  `deadline_miss_by_transform`, and the budget wrapper stores per-transform
  deadline debt for network-owned deadline classes. Control-lease deadline debt
  is now owned by local-controller feedback because lease validity starts at
  robot receive time, not original sender time. The experimental
  action-deadline policy reaches RX `178`, utility `1010.71`, control delivery
  `0.9885`, and loss `0.0481`; after correcting control-lease ownership it
  still misses the hard budget because worst-robot deadline miss is `0.3820`.
  The next gap is preventing non-control tail debt while preserving the
  multi-source budget pass found by the deadline-first branch.

The cross-RMW metadata matrix is now measured in Docker T3.  Fast DDS,
CycloneDDS, and Zenoh RMW all expose source and received timestamps through the
current `rclpy` bridge.  Fast DDS and Zenoh RMW expose sequence numbers;
CycloneDDS does not in this path.  None of the three expose publisher GID
through the observed callback surface.  The remaining Milestone 1 gap is now
narrower: preserve the egress-piggybacked NACK-aware retransmission path as an
`8`-robot regression gate, improve state/perception QoE beyond the current quota
matrix while preserving the hard-SLO volatility guard, and expand the C++
identifier seed into true `rmw_fleetqox_cpp` ABI entry points.

## Milestone 2: Minimal `rmw_fleetqox_cpp`

Implemented first:

- context/init/shutdown/fini;
- node create/destroy;
- publisher/subscription create/destroy;
- serialized publish/take through `fleetrmw.data_frame.v1` over a UDP loopback
  socket transport;
- minimal type-erased typed publish/take through `rmw_publish` and `rmw_take`
  for fixed-size FleetRMW probe messages;
- introspection C typed publish/take for ROS C message structs, including
  verified `std_msgs/msg/String` and `geometry_msgs/msg/Twist`;
- env-configured inter-process serialized publish/take with
  `FLEETQOX_RMW_BIND` and `FLEETQOX_RMW_PEERS`;
- Docker multi-container route discovery, where publisher, router, and
  subscriber run in separate containers, subscriber advertises its topic route,
  and the router forwards `fleetrmw.data_frame.v1` by learned route table;
- router-level remote pub/sub graph advertisement with
  `fleetrmw.graph_advertisement.v1`, graph-only router peers, and remote
  application into RMW graph query APIs for topic names/types plus
  publisher/subscriber counts;
- lease refresh and expiry for learned router routes and remote graph
  endpoints;
- matched publisher/subscription counting;
- domain-scoped graph guard condition and wait-set readiness for local
  serialized subscriptions and remote graph mutations/expiry;
- wait-set capacity, zero-as-unbounded, null-entry, active same-context, and
  shutdown validation, plus exact owner-node validation for pub/sub/service/
  client lifecycle and service availability;
- minimal in-process graph cache for node names, topic names/types, publisher
  counts, and subscriber counts;
- first single-process `rcl` publisher/subscription probe for
  `std_msgs/msg/String`;
- generic `rosidl_typesupport_c` dispatch into introspection-C handles;
- first ROS CLI graph smoke where `ros2 topic list --no-daemon --spin-time 2 -t`
  observes `/fleetqox/rcl_graph_talker [std_msgs/msg/String]`;
- first ROS CLI pub/echo smoke where `ros2 topic pub` sends and
  `ros2 topic echo --once` receives `std_msgs/msg/String`;
- endpoint-info and node-info graph APIs where `ros2 topic info --verbose` sees
  remote publisher GID/QoS metadata and `ros2 node info` reports publisher
  names/types by node;
- service/client graph support where `ros2 service list -t` discovers
  `/fleetqox/set_bool [std_srvs/srv/SetBool]`, `ros2 node info` reports the
  service server, graph advertisements renew for late-joining observers, and
  `rmw_service_server_is_available` reads graph service counts;
- first service request/response path where `ros2 service call` sends
  `std_srvs/srv/SetBool` and receives the response through
  `fleetrmw.service_frame.v1`;
- first service QoS freshness subset where `fleetrmw.service_frame.v1` carries
  request/response lifespan metadata from client/service QoS and the RMW drops
  stale RPC frames before service/client delivery;
- first service error subset where empty response queues return `taken=false`,
  malformed response payloads return a controlled error without delivery, and
  invalid service frames are rejected before a client-visible response appears;
- first ROS CLI service-timeout subset where a delayed `rcl` service response
  causes `ros2 service call` to time out after sending the request and before
  receiving any fabricated response;
- dependency-light action-frame contract where `fleetrmw.action_frame.v1`
  carries goal, feedback, status, result, and cancel role payloads with source
  timestamp, lifespan, endpoint id, goal id, and serialized payload metadata;
- router-mediated action-frame transport where `action_server` and
  `action_client` endpoints are learned from graph advertisements and the
  router forwards `goal/cancel/feedback/status/result` role frames;
- same-process real `rclpy.action` smoke where a
  `tf2_msgs/action/LookupTransform` client/server pair completes server
  discovery, SendGoal, execution, and GetResult over `rmw_fleetqox_cpp`;
- router-mediated real `rclpy.action` operation where the client and server run
  in separate containers and exchange SendGoal, CancelGoal, GetResult,
  feedback, and status only through `fleetrmw_udp_router_probe`;
- real action observation lifespan admission plus scoped deadline ordering,
  while action command/result services remain complete;
- router-mediated service request/response where service/client endpoints are
  learned from graph advertisements and the router forwards both RPC frames;
- first measured QoS subset for local subscription queues: `KEEP_LAST` depth
  trimming and `lifespan` expiry for serialized data frames;
- first RMW-owned ACK/NACK retransmission loop where subscriptions emit
  `fleetrmw.ack_nack.v1`, publishers retain a source-sequence ledger, and a
  dropped serialized frame is recovered by NACK-triggered retransmission;
- router-mediated ACK/NACK reliability where the router learns publisher
  source routes from data frames, forwards subscriber ACK/NACK feedback back to
  the publisher, and recovers a router-dropped sequence by retransmission;
- multi-hop router ACK/NACK reliability where a dropped sequence near the
  subscriber side is recovered across `publisher -> router A -> router B ->
  subscriber`, with NACK feedback relayed back through both routers before the
  publisher retransmits;
- dual-router path diversity where the publisher and subscriber both use a
  primary and backup router, the primary path drops a source sequence, the
  backup path delivers it, and the publisher completes without NACK-triggered
  retransmission;
- NACK-driven adaptive failover where publisher data starts as single-path
  unicast on the primary router, a missing source sequence rotates the selected
  peer, and retransmission recovers through the backup router;
- telemetry-score adaptive routing where a missing source sequence penalizes
  the active peer, retransmission uses the lower-score peer, and a post-recovery
  publish stays on that lower-risk path;
- deadline-triggered `adaptive_qos` routing where urgent ROS deadline QoS
  selects redundant router paths and recovers a primary-path drop without
  retransmission;
- offline fleet-level telemetry-scored QoS/QoE optimization where path
  loss/latency/jitter/NACK/deadline/utilization telemetry, per-robot QoE debt,
  ROS-like flow class/deadline/criticality, and fleet capacity jointly select
  unicast, redundant, degraded, or deferred routing;
- sidecar runtime `fleet_optimizer` actuation where optimizer decisions cross
  the batch boundary, annotate sidecar events, degrade or defer flows under
  fleet capacity pressure, and turn selected path choices into per-path UDP
  target transmissions in the dependency-free runtime probe;
- online fleet path-plan control where measured per-path observations are
  smoothed, guarded against flapping, and converted into topic-level
  `FLEETQOX_RMW_FLEET_PATH_PLAN` rules;
- C++ `rmw_fleetqox_cpp` fleet-plan routing where path-labeled peers in
  `FLEETQOX_RMW_PEERS` and a `FLEETQOX_RMW_FLEET_PATH_PLAN` or
  `FLEETQOX_RMW_FLEET_PATH_PLAN_FILE` topic map route data frames through
  selected Docker router peers such as `backup_5g` and `primary_wifi`, including
  a live probe where the publisher starts primary-only, updates the plan file
  after the first publish, and reloads a redundant backup-plus-primary plan for
  later frames;
- router-telemetry closed-loop control where `fleetrmw_udp_router_probe` writes
  `fleetrmw.router_path_telemetry.v1` JSONL records, `LivePathPlanController`
  tails those files, runs the online planner, and rewrites the RMW plan file
  during the same publisher session;
- subscriber-visible delivery telemetry where `rmw_take` metadata exposes
  source sequence/timestamp and take timestamp, the subscriber probe writes
  `fleetrmw.subscriber_delivery_telemetry.v1`, and the live controller converts
  those records into robot QoE state for the optimizer;
- multi-robot live telemetry planning where two ROS topics share one
  `FLEETQOX_RMW_FLEET_PATH_PLAN_FILE`, router/subscriber telemetry updates the
  host controller, and the resulting RMW rules diverge by flow class:
  redundant `backup_5g+primary_wifi` for `/robot_0000/cmd_vel` and unicast
  `backup_5g` for `/robot_0001/odom`, with redundant-path duplicate frames
  counted and de-duplicated before application delivery;
- multi-robot live telemetry profile matrix where the same Docker RMW
  publisher/router/subscriber path is repeated over `wifi`, `wan`, and
  `roaming` router-telemetry profiles, producing JSON/Markdown reports for
  router records, subscriber records, redundant frames, de-duplication, and
  delivery latency;
- multi-robot live netem matrix where the same ROS 2/RMW
  publisher/router/subscriber path runs with Docker `NET_ADMIN` router
  containers that apply `tc qdisc` delay, jitter, rate, and optional stochastic
  loss on their `eth0` links, producing per-path `fleetrmw.router_netem.v1`
  status records so packet-shaping evidence is auditable;
- matched four-robot live netem telemetry matrix where
  `deadline_sequence_repair_v1` gates application release on route-warmup
  ACK/readiness, repeats semantic application samples for route repair, emits
  idle missing-range ACK/NACK feedback from subscribers, and finishes with a
  terminal guard horizon. The stored artifact
  `results_rmw_socket/docker_multi_robot_live_telemetry_matrix_4robot_summary.json`
  passes Wi-Fi, WAN, and roaming rows over seeds `7,13,29` with qdisc applied
  in all `9/9` runs;
- controller-level live plan scale probing where the same online planner runs
  over N robots and 2N ROS-style topics, reporting decision latency,
  final rule count, path-plan byte size, and redundant/unicast mode shape before
  committing the workload to Docker/netem/ns-3/OMNeT++ runs;
- router-level `lifespan` admission where the data-plane router learns
  publisher QoS from graph advertisements and drops expired frames before
  forwarding;
- service-level `lifespan` admission where stale
  `fleetrmw.service_frame.v1` request and response frames are counted as
  expired and skipped before `rmw_take_request` / `rmw_take_response` delivery;
- service-level error handling where empty response queues report `taken=false`,
  malformed response payloads are popped with `RMW_RET_UNSUPPORTED` and
  `taken=false`, and invalid service frames are rejected without queueing a
  response;
- ROS CLI service-timeout handling where `ros2 service call` sends a request,
  the service node observes it, response delay exceeds the client timeout, and
  the CLI exits with timeout code `124` without a success response;
- action-frame role contract where `fleetrmw_action_frame_probe` round-trips
  goal, feedback, status, result, and cancel frames, verifies action lifespan
  boundaries, and rejects service-frame schema input before real `rcl_action`
  APIs are wired in;
- router-mediated action-frame transport where `fleetrmw_action_router_probe`
  sends the five minimal roles through `fleetrmw_udp_router_probe`, yielding
  server-visible `goal/cancel` and client-visible `feedback/status/result`;
- real `rclpy.action` goal/result smoke where
  `run_rmw_docker_rclpy_action_probe.py` uses
  `tf2_msgs/action/LookupTransform` and verifies server discovery, accepted
  goal, execute callback, and GetResult status `SUCCEEDED`;
- router-mediated real `rclpy.action` lifecycle smoke where
  `run_rmw_docker_router_rclpy_action_probe.py` separates the client and server
  into different Docker containers and verifies availability, success and
  cancel goals, feedback callbacks, status samples, `SUCCEEDED` and `CANCELED`
  results, and ten forwarded action service frames;
- opt-in router deadline scheduler window where the data plane snapshots
  learned deadline QoS and prioritizes earlier-deadline frames in a burst;
- publisher-provided fleet identity plus per-robot deadline-success and queue
  telemetry, with a real multi-robot control/state FIFO comparison;
- online deadline-gated scheduling with paced non-urgent drain under
  Wi-Fi/WAN/roaming `tc netem`;
- first adaptive admission evidence for deadline-gated holdback, where the
  Wi-Fi/WAN/roaming netem wrapper chooses FIFO when holdback hurts control p95
  and chooses `deadline_gated_holdback` only for admitted profiles, preserving
  zero deadline misses and per-robot fairness `1.0`;
- live router admission with `slo_service_epoch`, where the router estimates
  each non-urgent frame's SLO-normalized link service cost, smooths it with
  EWMA, and uses enter/exit thresholds plus epoch dwell before deciding inside
  the running scheduler whether to queue or bypass holdback;
- first repeated-loss smoke for live adaptive admission, where Wi-Fi/roaming
  run under explicit `tc netem loss 0.02%`, both admission branches execute,
  and stochastic row failure is surfaced as `partial` evidence instead of being
  hidden;
- scheduled ACK/NACK repair where a router scheduler window, an intentional
  source-sequence drop, forwarded ACK/NACK feedback, and publisher
  retransmission recover the missing payload through the scheduled data path;
- repeated-loss scheduled ACK/NACK repair under Wi-Fi and roaming qdiscs, with
  `2/2` first-smoke rows recovering all payloads and a post-satisfaction drain
  horizon that prevents terminal router counters from racing kernel netem
  delivery;
- concurrent four-robot scheduled ACK/NACK repair under a roaming qdisc, with
  independent per-publisher drops, full payload recovery, `8`
  retransmissions, zero scheduler deadline misses, and fairness `1.0`;
- real mixed action/control/state operation on one roaming-profile router,
  where action success/cancel and `4/4` repaired data flows pass, fresh
  deadline misses remain zero, and late repair misses are separately
  attributable by topic, robot, sequence, and lateness;
- proactive deadline diversity where `adaptive_qos` duplicates critical
  control samples over roaming and Wi-Fi paths; the repeated-loss matrix passes
  `2/2`, keeps every sample below `100 ms`, and requires no retransmission;
- concurrent four-robot proactive diversity, repeated `2/2`, with all per-robot
  samples on time, fairness `1.0`, maximum latency `56.163 ms`, and measured
  `2x` path-transmission overhead;
- failure-domain-aware redundancy budgeting in the fleet optimizer: a
  four-robot deterministic probe protects the two fairness-debt robots, keeps
  two flows unicast, drops none, and cuts path transmissions from `8` to `6`;
- live budgeted fleet-plan actuation across four concurrent ROS 2 robots: the
  optimizer's failure-domain-diverse decisions reach the C++ RMW publisher,
  all samples meet the `100 ms` deadline with fairness `1.0`, and measured
  path transmissions fall from `24` to `18` with zero retransmissions;
- active-publisher fleet-plan epoch transition: after frame `1`, two robots
  move from redundant to unicast transmission without restarting their ROS 2
  publishers; the run keeps `4/4` deadlines and reduces the session from `24`
  to `20` path transmissions;
- subscriber-QoE-driven closed-loop budgeting: the controller waits for live
  delivery telemetry from every robot, derives robot debt without seeded
  state, protects the measured lower-QoE pair, keeps `4/4` diagnostic
  deadlines, and reduces path transmissions from `24` to `16`; its first
  repeated netem matrix passes `2/2` with zero retransmissions;
- measured-QoE protection migration across two live qdisc epochs: redundancy
  moves from robot `0000/0001` to `0002/0003` without restarting publishers,
  while preserving `4/4` diagnostic deadlines and `16/24` transmissions;
- live protection-migration scaling at `4`, `8`, and `16` robots: all rows move the
  redundancy budget to the expected lower-QoE half, keep fairness `1.0`, avoid
  retransmissions, and reduce aggregate transmissions from `616` to `420`;
  event-triggered publisher barriers and sequential confidence stopping remove
  the fixed sampling timer, telemetry-to-plan convergence stays below
  `486.958 ms`, and controller actuation stays below `56.761 ms` including
  plan visibility settling;
- repeated sequential-QoE protection migration: `6/6` rows across `4/8/16`
  robots and repetition IDs `7,13` pass, all `12/12` QoE epochs stop by
  confidence separation, maximum convergence is `465.783 ms`, and aggregate
  transmissions fall from `1232` to `840`;
- harsh-loss sequential-QoE protection migration: the `8/16` robot matrix at
  `0.2%`, `0.5%`, and `1.0%` loss completes `5/6` rows OK, with explicit
  `failure_mode_counts={ok:5, confidence_not_separated:1}`. The remaining
  failure is not a router timeout; it is the first measured policy boundary
  where telemetry confidence does not separate before the sample cap under high
  loss and tail latency;
- confidence-fallback actuation: when sequential QoE does not separate, the
  controller can now protect the union of previous and candidate low-QoE robots,
  temporarily expand fallback redundancy budget, and write that plan to live
  C++ RMW publishers. A forced four-robot Docker/RMW smoke applies fallback in
  both epochs, protects all four robots, passes `4/4`, keeps zero
  retransmissions, and uses `20/24` full-redundancy transmissions. A companion
  matrix smoke preserves strict confidence accounting by reporting
  `failure_mode=confidence_fallback_applied` instead of counting fallback as a
  confident migration success. The first harsh fallback matrix passes `3/6`
  strict rows and exposes the next boundary: fallback can actuate and sometimes
  preserve delivery, but high tail loss still needs recovery-window repair and
  feedback-timeout safe mode at `8/16` robots;
- post-fallback recovery-window accounting: after fallback, the Docker/RMW probe
  can release explicit recovery frames and audit those frames separately from
  strict confidence success. A forced four-robot smoke recovers `4/4` robots
  over three recovery frames, and the harsh `8/16` robot matrix passes `4/6`
  strict rows while all `6/6` rows pass the recovery window;
- targeted source-sequence repair attribution: the probe now joins subscriber
  telemetry with publisher NACK retransmissions and idle repair requests,
  classifies each robot as `ok`, `repaired_on_time`, `repaired_late`, `late`,
  or `unresolved`, and reports repair path overhead separately from planned
  traffic. A forced smoke observes one late repaired sequence followed by a
  `4/4` healthy recovery window; a second matrix smoke reports strict
  confidence `0/1` but QoE recovery `1/1`;
- controller-directed repair routing and admission: the live controller writes
  a separate repair plan, C++ publishers reload it only for NACK
  retransmissions, and a per-publisher budget bounds replay. Deterministic
  sequence drops prove dual-path repair, distinguish a `250 ms`
  `repaired_late` boundary from a `400 ms` `repaired_on_time` result, and
  produce unresolved gaps when the budget is zero;
- per-sequence repair storm control: a configurable coalescing interval and
  attempt cap reduce deterministic repair from `8` retransmissions/`16` path
  sends to `2` retransmissions/`4` path sends while preserving `4/4`
  repair-deadline success;
- adaptive fleet-wide per-sequence repair admission: a multi-choice knapsack
  with Pareto pruning ranks repair alternatives by deadline pressure,
  criticality, QoE debt, path success/latency, attempt debt, and byte cost. A
  strict sequence-specific policy is enforced across publishers under one
  shared capacity. The sufficient-capacity smoke repairs both forced gaps on
  time with `2` unicast backup transmissions; the `700`-byte smoke admits only
  higher-debt `robot_0000`, reports the other repair as explicitly deferred,
  and produces the expected `3/4` repair-qualified result;
- repeated `8/16/32` actuated-repair capacity frontier: the v3 artifact passes
  `27/27` rows and all `9/9` groups. It drops sequence `2` once on both paths,
  requires admitted NACK repair plus explicit deferred rejection, produces
  live QoE coverage `0.625/0.75/1.0` as capacity rises, and keeps every observed
  latency below the `400 ms` deadline with a maximum of `397.314 ms`;
- upstream Nav2/RMF workload: local `NavigateFleet`/`DispatchFleetTask`
  fallbacks and upstream `NavigateToPose` all exercise success/cancel paths;
  RMF `SubmitTask`/`CancelTask` services additionally prove nested upstream
  task serialization. A four-way concurrent batch passes for both upstream
  APIs. The upstream Nav2 C++ lifecycle manager drives all four primary
  transitions on a companion node, with `82/82` service frames forwarded by
  the router and zero invalid frames. Follow-on real Nav2 planner/controller
  probes configure upstream `planner_server` and `controller_server` with
  `NavfnPlanner` and DWB plugins through FleetRMW lifecycle services, then
  publish repeated dynamic `/tf` through the router and activate both nodes to
  `active [3]`. The planner runtime probe adds repeated `/map` plus `/tf`,
  sends upstream `ComputePathToPose`, and receives a successful Navfn path;
  the controller runtime probe adds repeated `/map`, `/tf`, and `/odom`, sends
  upstream `FollowPath`, and receives a successful DWB result. The current
  full-stack CI-light probe then starts `bt_navigator`, executes a minimal
  `ComputePathToPose -> FollowPath` behavior tree through upstream
  `NavigateToPose`, and succeeds at the current pose. A repeated wrapper
  executes that same-pose pipeline twice with fresh Docker processes. A
  moving-base probe sends a short `x=0.6` goal while a fake base receives
  `/cmd_vel`, publishes dynamic `/odom` and `/tf`, and records about
  `0.406 m` of motion. An extended moving-base probe raises the goal to
  `x=1.2`, still receives `error_code=0`, forwards `/cmd_vel`, and records
  about `0.956 m` of fake-base motion. A direct `nav2_behaviors::Spin` probe starts upstream
  `behavior_server`, activates it over FleetRMW lifecycle services, sends
  `/spin`, forwards `/cmd_vel`, and rotates the fake base about `0.616 rad`.
  A NavigateToPose recovery-tree probe then executes a `RecoveryNode` where an
  intentional `MissingPlanner` compute-path failure triggers `Spin`; the
  top-level goal aborts as expected after retry, but `/spin`, `/cmd_vel`, and
  fake-base rotation prove the fallback branch. A recovered-success probe then
  executes `Spin` before a short successful `ComputePathToPose -> FollowPath`
  `NavigateToPose` goal, with `/spin`, `/cmd_vel`, `/map`, `/odom`, and `/tf`
  forwarded through FleetRMW and `navigate_to_pose_error_code=0`; a repeated
  wrapper runs the same recovered-success path twice with fresh Docker
  processes and forwards `144` lifecycle/action service frames in aggregate. A
  long moving-base wrapper repeats the unobstructed `x=1.2` BT path three times
  with fresh Docker processes and aggregates `/cmd_vel`, fake-base movement,
  and FleetRMW action/service traffic. A concurrency-8 upstream Nav2/RMF
  action/service rerun also passes with `106/106` expected service frames.
  A concurrency-16 rerun keeps the same upstream Nav2/RMF flags true and
  forwards `154/154` expected service frames. A concurrency-32 rerun also
  forwards `250/250` expected service frames, and a concurrency-64 rerun
  forwards `442/442` expected service frames. A concurrency-128 rerun forwards
  `826/826` expected service frames, a concurrency-256 rerun forwards
  `1594/1594` expected service frames, a concurrency-512 rerun forwards
  `3130/3130` expected service frames, a concurrency-1024 rerun forwards
  `6202/6202` expected service frames, and a concurrency-2048 rerun forwards
  `12346/12346` expected service frames after FleetRMW UDP large-frame
  fragmentation/reassembly and router fragment passthrough. The
  concurrency-4096 Docker rerun now passes as a single unwindowed 4096-goal
  batch after adding automatic `0.5 ms` inter-send executor-spin pacing:
  `4096/4096` action goals and `4096/4096` RMF submissions complete, lifecycle
  startup/reset succeeds, and the router forwards `98704` service frames with
  zero invalid frames. The claim is scoped to an unwindowed request workload
  with UDP socket/pacing and duplicate-safe service-frame tuning, not 4096
  simultaneously long-running robot motions. The separate total-4096
  admission-controlled 8-goal-window run remains a positive control with
  `106088` forwarded service frames. A planner-level static-obstacle
  repair
  probe now blocks `ComputePathToPose` with an occupancy-grid wall, then clears
  the map and replans successfully. A full-stack `NavigateToPose`
  retry-after-clear probe then starts planner, controller, and BT navigator,
  aborts a blocked `x=0.8` goal, publishes a clear map, and succeeds on retry
  while moving the fake base. A same-goal `NavigateToPose` obstacle recovery
  probe then keeps one goal active, runs a real `Wait` recovery action after
  planner failure, receives a clear-map repair during that same goal, and
  succeeds while moving the fake base. Dynamic obstacle avoidance, production
  costmap-clearing policy, upstream request counts beyond 4096, and sustained
  4096-robot physical navigation remain future work;
- repeated large-scale baseline gap register: `run_large_scale_rmw_comparison.py`
  compares FleetRMW router, Fast DDS, Cyclone DDS, and Zenoh at `8/16/32`
  robots over repetition IDs `7,13,29`, with data-plane-only netem, an equal
  publisher reliability horizon, Zenoh router bootstrap, resumable
  infrastructure-only retries, and 95% confidence intervals. The current-image
  split-scope run passes `36/36`; its topology caveat remains. A separate
  same-hop relay study passes `32/36` and allows delivery/reliability comparison
  only because raw FleetRMW forwarding and baseline rclpy
  deserialize-republish are not latency-equivalent. Both reports forbid broad
  mixed-semantics superiority claims;
- router-mediated ROS CLI service timeout: separate client/server containers
  exchange request/response through FleetRMW, the caller times out cleanly
  without a fabricated response, and the router accounts for both frames;
- router-mediated caller-visible malformed service response: a validly routed
  response with an invalid serialized body reaches `rmw_take_response`, causes
  `ros2 service call` to exit with code `1`, and preserves the concrete
  deserialize diagnostic through rcl without fabricating a response;
- waitable subscription registry so `rmw_wait` supports both full
  `rmw_subscription_t *` handles and implementation-data pointers used by
  `rclpy`;
- optional RMW ABI surfaces and deliberately scoped unsupported surfaces
  including loaned messages, type-support-bound publisher/subscription payload
  scratch reuse repeated `5/5`, ordered/partial/empty `rmw_take_sequence`
  semantics with concurrent
  same-subscription queue-order preservation repeated `5/5`, and an exported
  symbol audit with no missing symbol against the Fast DDS Jazzy RMW baseline;
  `rmw_publisher_wait_for_all_acked` now tracks subscriber-identified ACKs for
  the reliable-write matched-endpoint snapshot, and a delayed-second-ACK
  timeout/completion control repeats `5/5` in Docker. A separate four-container
  UDP/router/netem gate repeats the same `1/2` timeout then `2/2` completion
  behavior across two remote subscriber processes and verifies both ACKs at
  the router;
  QoS event objects/callback setters with timer-driven deadline-missed
  production after the first sample plus next-publish/receive production after
  a deadline gap, local publication/subscription matched event production on
  same-process compatible endpoint create/destroy, local reliability-,
  durability-, deadline-, and liveliness-incompatible QoS event production, local
  incompatible-type event production for same-topic type mismatches, local
  message-lost event production for `KEEP_LAST` queue overwrite and
  `BEST_EFFORT` source-sequence gaps with first-sample baselining plus
  repair/reorder grace suppression, plus subscriber-targeted unrecoverable
  notices when a reliable sample has left writer history. That reliable remote
  path passes `20/20` across two Docker/netem UDP peers, including idempotent
  duplicate-notice handling and callback/`rmw_wait`/`rmw_take_event` readiness.
  A second two-peer campaign retains the sample in writer history and proves
  terminal repair-budget, max-attempt, and admission-rejection notification
  `5/5` each (`15/15` total), including distinct counters and clean teardown;
  local manual liveliness lost/changed event production for finite lease timeout
  and reassert, and `rmw_wait` readiness while the status is unread. AUTOMATIC
  liveliness is renewed by the RMW while a publisher exists; a separate `5/5`
  Docker control leaves the publisher idle for six lease intervals and observes
  no false lost event or not-alive transition. A two-container UDP/netem control
  also repeats remote MANUAL_BY_TOPIC behavior `5/5`: periodic graph renewal
  leaves an idle publisher matched without renewing its independent liveliness
  lease, while explicit assertion and serialized publish each send a wire
  assertion and restore the endpoint to alive. Every implemented QoS event
  family is repeated `5/5` in Docker. A second remote `5/5` artifact verifies
  exact aggregate liveliness and matching transitions across two simultaneous
  manual publishers plus remove/recreate churn of a third endpoint. A local
  seven-scenario artifact also passes `5/5` for offered/requested liveliness
  kind and slow/missing lease incompatibility events plus a compatible control.
  The separate
  `rmw_qos_profile_check_compatible` ABI follows Jazzy rules for reliability,
  durability, deadline, liveliness kind, and liveliness lease duration; its v2
  probe covers OK, aggregated ERROR reasons, and unresolved-policy WARNING.
  BEST_AVAILABLE creation now delegates to `rmw_dds_common` over FleetRMW graph
  queries; a four-scenario `5/5` artifact covers publisher/subscription,
  zero-endpoint, mixed-endpoint, actual-QoS, and frozen-after-create behavior.
  Content-filter
  set/get plus key-value/std_msgs text payload enforcement repeated `5/5`; and
  security-options lifecycle/deep-copy/context-copy coverage repeated `5/5` in
  Docker; plus an opt-in FleetQoX publish allow/deny security policy repeated
  `5/5` in Docker; plus SROS2-generated signed DDS permissions with CA
  verification both as preflight and inside FleetRMW, XSD validation, scoped
  publish/subscribe authorization, and malformed/tampered-policy fail-closed controls
  repeated `5/5` in Docker. SROS2 service request/reply rules are mapped to the
  actual RMW SetBool request/response send/receive paths and cover allowed,
  explicit-denied, and default-denied flows. Generated Action call/execute
  rules also cover an allowed rclpy LookupTransform goal/result/feedback path,
  explicit call fail-closed, and execute-side request drop before callback,
  repeated `5/5`. Signed Governance domain/topic read-write access-control is
  likewise enforced `5/5`; stock ENCRYPT/SIGN requirements and a tampered
  governance signature fail closed without claiming transport crypto. Local
  identity certificate-chain, key, and enclave-CN validation also passes `5/5`
  with tampered-cert, wrong-key, and wrong-enclave fail-closed controls. An
  opt-in AES-256-GCM PSK envelope protects UDP payloads and rejects tampering
  before queue delivery across `5/5`. Remote SROS2 X.509 identities are also
  certificate-authenticated `5/5`, with allowlist, signature-tamper, and
  untrusted-CA and CRL-revocation controls failing closed; DDS-Security
  interoperability and forward-secret asymmetric key exchange remain
  unclaimed. HKDF-SHA256 PSK session derivation/reuse/rotation is covered. A
  stress/security campaign runner now aggregates these ABI/security components
  with QUIC async-burst soak into one artifact; the repeated profile passes
  `48/48` component runs. The long runner actively repeats full workload
  rounds until the threshold instead of merely checking one short round; its
  one-hour netem campaign passed eight rounds over `3793.205 s`, with `80/80`
  component executions and `1680/1680` probe runs. Remote graph event state is
  now connected to the real UDP advertisement path: matched,
  reliability/durability/deadline-QoS, exact type, and finite-liveliness graph lifecycle events pass `5/5`
  two-container runs with renewal deduplication, explicit remove, and killed-peer
  lease expiry. Dynamic type discovery and additional serialization plugins,
  network-flow endpoints, and callbacks remain scoped. A `5/5` aggregate matrix
  now verifies `rmw_wait`/`rmw_take_event` readiness for all eleven non-invalid
  Jazzy event types (`35/35` component executions). Remote MANUAL_BY_TOPIC idle
  timeout, explicit/publish reassertion, and graph/liveliness lease independence
  now pass a separate `5/5` two-container UDP/netem probe. Independent state,
  alive/not-alive removal, and endpoint recreation also pass a second `5/5`
  remote probe. A local scale/control artifact additionally passes `5/5` with
  exact 64-publisher MANUAL_BY_TOPIC aggregate transitions and 16 idle
  SYSTEM_DEFAULT publishers remaining alive for six finite lease periods.
  A two-container UDP/netem scale artifact also passes `5/5` with 64 remote
  publishers, exact half-expiry/reassert/all-expiry/removal and matched deltas,
  96 expiries, 32 reassertions, and matching preserved through expiry.
  Default/non-expiring leases now retain alive/remove lifecycle events for all
  non-deprecated Jazzy policies, and UNKNOWN/deprecated endpoint inputs fail
  closed across another `5/5` control. Deprecated participant-wide DDS
  liveliness semantics,
  full DDS message-lost/resource-limit semantics, all remaining remote optional event
  families, the full
  remote QoS/type event compatibility matrix, the full DDS
  SQL-like content-filter dialect, forward-secret SROS2/DDS key exchange,
  complete PKI lifecycle automation and production transport hardening,
  and production security hardening remain outside the implemented subset. The broad SROS2
  policy claim stays false despite the scoped signed permissions and Governance
  authorization path.
- standalone `rmw_serialize`/`rmw_deserialize` backed by the native
  introspection-C codec, with an explicit `fleetrmw.introspection_c.v1`
  format identifier and a passing String round-trip probe.
- installed machine-readable capability manifest with
  `production_ready=false`, explicit supported/partial surfaces, and a complete
  list of controlled unsupported optional ABI families.
- unified benchmark report aggregator that reads existing summary JSON
  artifacts plus `capabilities.json`, normalizes status, run counts, selected
  key metrics, and claim-boundary guards, then emits JSON/Markdown without
  rerunning benchmarks. Retained historical/debug/negative-control artifacts
  contribute to the all-history status, while current manifest health and
  explicit true/false claim counts are reported independently.
- standalone generic C++ type-support regression for `std_msgs/String` and
  nested `geometry_msgs/PoseStamped`, both round-tripped through
  `rmw_serialize`/`rmw_deserialize` in Docker. Bounded standalone size
  calculation is also implemented for introspection C/C++; nested
  `geometry_msgs/Pose` predicts and serializes to the same `80` bytes through
  both runtime paths while
  artificial bounds for unbounded fields remain explicitly unsupported.
- two-container `rclcpp` data-plane regression for nested PoseStamped
  pub/sub and SetBool service request/response through the router, with zero
  invalid frames, real UDP network-flow metadata, and observed request/response
  callbacks.

Next implement:

- increase repetitions around the completed actuated-repair v3 frontier so
  the `32`-robot latency-mean interval is tighter at the `400 ms` boundary;
- sequence-heavy C++ service and cross-language type-support matrices beyond
  the proven Nav2 manager, standalone, and interprocess C++ paths;
- preserve the completed split-scope DDS/Zenoh/FleetRMW contract and the
  separate `32/36` same-hop study; increase samples/repetitions and make middle
  processing semantically equivalent before allowing latency superiority;
- preserve the completed ns-3/OMNeT++ matched routed-P2P matrix (`27/27`
  runtime and bounded-parity cases, OMNeT++ 6.4.0/INET 4.7.0) while adding
  separate dedicated TSN and mobile-mesh models. The ns-3 CSMA, single-AP
  Wi-Fi/mobility, and dual-AP handoff matrices are also complete at `27/27`;
  full cross-simulator TSN/mesh/wireless parity remains a distinct evidence
  target and is not implied by the completed P2P matrix.

Target: C++ type-support coverage, caller-visible service cancellation/error
semantics, multi-container real `rcl_action` transport, live optimizer actuation, and measured
network-aware QoS/QoE at fleet scale.

## Milestone 3: Services And Actions

Services and initial ROS 2 actions are now possible over the prototype RMW:
SetBool services, service timeout/error cases, same-process `rclpy.action`,
router-mediated success/cancel, action QoS observation, and the local
Nav2/RMF-compatible action workload all have Docker artifacts. The remaining
work is breadth and concurrency rather than first viability.

Target:

- lifecycle demos;
- dynamic obstacle / production costmap-clearing Nav2 NavigateToPose scenarios
  beyond the static-map retry-after-clear and same-goal external-repair probes,
  plus larger repeated upstream client counts;
- robot state/control workloads.

## Milestone 4: Fleet Data Plane

Add:

- SHM same-host: first local-only POSIX ring and UDP-fallback gate complete;
- hybrid SHM-local plus UDP-remote peers: first router/de-dup gate complete;
- QUIC/TLS dependency gate: first ngtcp2/GnuTLS QUIC v1 + ALPN `h3` payload
  probe complete; this proves the backend dependency and handshake path, not
  the integrated RMW transport;
- QUIC/FleetRMW frame gate: first `fleetrmw.data_frame.v1` transfer through
  ngtcp2/GnuTLS QUIC/TLS/H3 and C++ decode complete; this is still pre-RMW
  publish/take integration;
- Docker/netem QUIC frame gate: first two-container ngtcp2/GnuTLS
  QUIC/TLS/H3 transfer of `fleetrmw.data_frame.v1` under verified `tc netem`
  complete, with qdisc before/after counters and parsed ngtcp2 path telemetry;
- publish-side QUIC gateway: first `rmw_publish` path through
  ngtcp2/GnuTLS `gtlsclient --data` complete, with server-side body byte-count
  verification, async enqueue/drain and burst telemetry, plus two-container
  Docker/netem single-publish and async-burst variants with qdisc counters and
  parsed ngtcp2 telemetry. Session/tp/token file plumbing maps FleetRMW env
  vars to ngtcp2/GnuTLS `gtlsclient` options and has a Docker burst probe for
  persisted session artifacts. The QUIC runners now parse file-read/missing and
  0-RTT log telemetry, keeping packet-level 0-RTT attempts separate from
  accepted 0-RTT/session-resumption evidence, which remains unclaimed. A
  repeated async-burst soak runner now passes `10/10` Docker/netem
  iterations and aggregates `40` sent/enqueued frames, bytes, qlog size, zero
  drops/failures, `208` qdisc packets, and `160` RTT samples. A first gateway take/download slice now fetches a
  hosted `fleetrmw.data_frame.v1` through `gtlsclient --download`, verifies
  byte-for-byte integrity, and decodes it in C++. A follow-on opt-in
  `rmw_take_serialized_message` smoke fills an empty subscription queue from
  the same QUIC GET path when
  `FLEETQOX_RMW_QUIC_GATEWAY_TAKE_ON_DEMAND=1`; a repeated RMW-take session-file
  probe shares ngtcp2/GnuTLS session/tp/token files across five GET downloads.
  A same-server bidirectional boundary probe also runs RMW publish POST followed
  by opt-in RMW take GET while sharing session/tp/token files across `5/5`
  repeated publish+take pairs. A disable-early-data control now verifies that
  the 0-RTT telemetry parser reports no 0-RTT packets when early data is
  disabled. This is
  subprocess-backed smoke/repeat evidence and not accepted 0-RTT/session
  resumption proof. The follow-on in-process ngtcp2/GnuTLS/nghttp3 backend is
  now integrated into both RMW paths: its Docker/netem artifact proves 128
  publishes and one take over one connection, one verified TLS handshake,
  129 bidirectional streams, 128 same-connection reuses, zero reconnects,
  three native client qlogs plus three server qlogs, and untrusted-CA
  rejection. The final publish and take
  are independent public RMW calls launched from two threads; a bounded
  rendezvous opens POST and GET before either response is driven and records
  one concurrent API pair, two simultaneous calls, and two simultaneous H3
  streams. A second verified connection exercises the explicit paired API. A
  stateful aioquic FleetQoX gateway now passes `5/5` two-container Docker/netem
  runs with validated FleetRMW frames, bounded per-domain/topic history,
  publisher-sequence deduplication, independent replay cursors for two
  consumers, persistent verified-TLS client sessions, qlogs, and HTTP 400
  fail-closed propagation. A second `5/5` three-container gate exercises public
  `rmw_publish` in one process and ordered public `rmw_take` in another, with
  both endpoints reusing verified-TLS H3 sessions and exporting qlogs.
  A third `5/5` six-container netem gate requires a client certificate at the
  stateful gateway: the trusted in-process GnuTLS client writes one frame,
  while missing credentials and an unrelated client CA are rejected without
  mutating gateway state. A certificate from the trusted CA but with a
  SPIFFE-style publisher URI SAN that does not match the frame's `publisher_id`
  is also rejected with HTTP/3 403
  before state mutation. This is scoped mTLS and publisher-binding evidence.
  A CA-trusted certificate with the correct publisher identity is separately
  rejected when its serial appears in a current CRL; the gateway verifies the
  CRL issuer, signature, and validity window at startup.
  The aioquic compatibility layer still uses a private TLS hook because
  upstream 1.3.0 has no public server client-auth switch. It now exact-pins
  version 0.9.25, fingerprints private signatures, verifies CertificateVerify
  before authentication, and fails closed on drift; stable upstream client-auth
  integration, broader fleet identity policy,
  online revocation and rotation remain open.
  A separate pinned official ngtcp2/GnuTLS public-API server now carries the
  shared state engine and public path telemetry. Its backend protocol v2
  forwards authenticated identity, method/path/body, smoothed RTT, RTT
  variation, congestion state, PTO count, and raw stream-loss count. The
  stateful and path-admission artifacts each pass `5/5` Docker/netem rounds.
  A further `5/5` gate removes blocking Unix-socket work from the libev thread:
  a bounded configurable worker pool returns completions through `ev_async`,
  queue saturation returns HTTP 503, and generation fencing drops stale
  handler completions. Slow/fast, overload, and expired-handler phases all
  continue through the real state engine behind a test-only delay proxy.
  The next `5/5` gate derives a separate publisher identity for each verified
  connection from its peer-certificate URI SAN, rejects an out-of-prefix
  identity before backend access, caps each identity's pending queue, and
  round-robins ready identities. An overloaded publisher receives HTTP 429
  while an independent publisher is admitted and overtakes the first
  publisher's remaining queued request. This closes scoped multi-publisher
  pending-queue fairness. A matched `5/5` two-worker follow-on adds an optional
  per-identity active limit. Limit one keeps noisy publisher A at one active
  backend call and lets publisher B finish while both A clients remain open;
  the limit-two control lets A occupy both workers and delays B. The default
  limit is the worker count, preserving work-conserving behavior unless
  operators opt into isolation. The next `5/5` Docker/netem gate enables an
  opt-in public-GnuTLS client-CRL reload before each new TLS connection is
  verified. It atomically revokes and restores the same client while retaining
  the same server PID/start time, observes `CRYPTO_ERROR` only during
  revocation, and rejects a malformed replacement CRL fail-closed. This is
  online revocation refresh for new connections, not eviction/reverification
  of established sessions or online client-CA/server-certificate rotation.
  Weighted QoS-aware scheduling remains outside the claim.
  Active/active replicated durability, standardized task-result
  instrumentation, a stable public QUIC path-metrics API, accepted
  0-RTT/resumption,
  and production hardening remain open, so production readiness is still false;
- stateful QUIC fleet admission: a `5/5` two-container netem gate now loads a
  fail-closed JSON policy with publisher allowlists, control/bulk/state traffic
  classes, per-stream quotas, and a shared fleet quota. It admits and replays
  exactly three frames, returns distinct 403/429 controls for publisher,
  stream, and fleet rejection, and proves rejected frames do not create topic
  state. A monotonic one-second epoch replenishes capacity and admits/replays
  the previously rejected state frame while preserving cumulative telemetry.
  This is a deterministic quota slice; the follow-on feedback/batch gate below
  adds scoped QoS/QoE adaptation and repair scheduling, while cluster-wide
  admission remains open;
- QUIC QoS/QoE repair coupling: optional C++ v1 frame metadata now carries
  traffic class, deadline/age, QoE debt, criticality, repair intent, and prior
  attempts. A `5/5` Docker/netem gate proves score-based reject/admit and calls
  `FleetRepairScheduler` after normal quota exhaustion; private 5G admits one
  urgent repair while shared capacity defers the next, and admitted frames
  replay over H3. A follow-on `5/5` Docker/netem gate accepts versioned external
  debt/loss/RTT/jitter observations with TTL and score-sorts two-frame batches.
  The observed publisher wins a one-frame normal quota, then an urgent repair
  wins 622/1024 shared bytes before a lower-score repair is deferred. This is
  externally fed, deterministic sequential batch admission. A separate `5/5`
  mTLS/netem contrast performs zero observation-API requests and proves native
  smoothed RTT, RTT-variation proxy, and recovery loss accounting can change the
  admission outcome for the same frame. The private aioquic recovery adapter is
  exact-version/signature gated and source-accounted as `quic_session_native`.
  A third `5/5` contrast keeps publisher debt at zero and proves an opt-in EWMA
  debt derived from authenticated loss and RTT/deadline pressures can change
  admission, with provenance `gateway_derived_path` and mandatory mTLS identity
  binding. A fourth `5/5` gate binds versioned application outcomes to both a
  known accepted frame and the mTLS URI-SAN publisher identity. Unknown,
  malformed, impersonated, and replayed reports are handled fail closed or
  idempotently; failed delivery/deadline/latency derives
  `gateway_derived_outcome` EWMA debt and changes the next admission result.
  A fifth `5/5` mTLS/netem gate commits the authenticated outcome key and
  post-outcome admission snapshot atomically to SQLite WAL. A replacement
  gateway restores both, makes cross-gateway replay idempotent without applying
  debt twice, and still admits/replays the low-criticality frame. A sixth
  `5/5` gate repeats that outcome path over networked PostgreSQL 16 with
  `synchronous_commit=on` and writer fence tokens `1->2`; this proves gateway
  replacement, not database-process failover. A stable public path API, global
  joint optimization, standardized task-result instrumentation, and
  cluster-wide replicated scheduler state remain open;
- QUIC active/passive durability: optional SQLite WAL state with
  `synchronous=FULL` persists retained frames, bounded dedup keys, and consumer
  cursors. A `5/5` Docker/netem gate performs A-to-B-to-C sequential gateway
  replacement against a fresh shared database per run, proving frame recovery,
  duplicate suppression, and cursor resume over verified H3. A second `5/5`
  gate persists quota, cumulative counters, repair bytes/count, decisions, and
  live observation source state. Frame plus post-admission snapshot commit in
  one SQLite transaction; replacement rejects the next repair under restored
  capacity, while a changed policy fingerprint fails startup. A third `5/5`
  gate adds a renewable single-writer lease, monotonic fence token,
  concurrent-standby rejection, and manual takeover with restored admission
  state. Frame/admission and cursor writes verify the fence inside their SQLite
  transactions. A fourth `5/5` gate proves a pre-started standby waits, then
  automatically acquires token 2 and serves restored admission state after the
  active exits (203--208 ms stop-to-ready). Active/active consensus, quorum
  leader election, multi-node replication, partition tolerance, and distributed
  storage remain open. A fifth `5/5` gate moves the same transaction, lease,
  fence, and recovery invariants to PostgreSQL 16 over a Docker network. Each
  run has one fresh database process plus two pre-started gateways; PostgreSQL
  `synchronous_commit=on`, advisory transaction locking, and lease-row
  `FOR UPDATE` checks are required by the validator. B takes token 2 and serves
  restored admission state 429--715 ms after A is stopped. This removes shared
  host-file coupling between gateways, but database-process failover,
  replication/quorum, partition tolerance, and active/active operation remain
  open at that stage. A sixth `5/5` gate starts a synchronous PostgreSQL
  streaming replica, confirms its flush/replay WAL positions after the seeded
  commits, kills the primary, observes A exit after lease-store loss, manually
  promotes the replica, and proves B reconnects to the promoted read-write host
  with token 2 and restored admission state. End-to-end recovery takes
  3.129--3.154 s. Controlled database-process failover and seeded-state
  continuity are now covered; automatic database leader election, quorum DCS,
  split-brain/partition testing, regional DR, and production HA remain open;
  a seventh `5/5` gate introduces a three-member etcd Raft DCS and two
  controllers and a Docker-socket fence agent. With 2/3 etcd members down, the
  runner applies 100% egress loss to the still-running PostgreSQL primary.
  Promotion stays fail-closed, both controllers record DCS denial, the active
  gateway exits, and the replica remains in recovery. Restoring 2/3 quorum
  yields exactly one TTL-lease winner. The agent validates controller identity
  and lease ID with a linearizable mTLS etcd lookup, hard-fences only the
  allowlisted primary, and the controller invokes `pg_promote` only after
  confirmation. B takes token 2 with restored state in 9.934--10.478 s. The
  fence endpoint requires a CA-verified client certificate, binds certificate
  CN to controller ID, rejects no-cert clients, and rejects an authenticated
  forged lease while the primary is live. This
  closes scoped quorum-gated promotion, DCS-authorized Docker STONITH, and one
  live-primary partition/fence sequence. The fenced primary is subsequently
  rebuilt by physical basebackup with a dedicated replication slot and must
  reappear as a synchronous read-only standby containing the seeded state,
  restoring Docker-scoped redundancy in every run. The same gate then starts
  two automatic failback policy controllers. Both reject an intentionally
  asynchronous replica; after `streaming|sync` and zero replay gap are restored
  under 1/3 etcd, both also reject failback without quorum. Restoring 2/3 yields
  one failback-lease winner. An mTLS agent binds controller CN to the live DCS
  lease and gracefully stops the current primary before the winner promotes the
  original role. Gateway C resumes seeded state with fence token 3 over QUIC/H3
  in 1.699--3.449 s, and the former primary is rebuilt as a final synchronous
  read-only standby. This closes scoped automatic policy/DCS failback and
  post-failback Docker redundancy. etcd client and peer links require
  CA-verified mutual TLS, as do the fencing and switchover links. Hardware/cloud
  fencing, certificate rotation/revocation, broader partition matrices,
  production orchestration, and regional production HA remain open;
- integrated UDP/QUIC LAN;
- integrated QUIC WAN;
- WebRTC/SVC video path;
- low-priority bulk path;
- per-plane admission control.

## Milestone 5: Full Benchmark

Compare against:

- Fast DDS;
- Cyclone DDS;
- Fast DDS Discovery Server;
- Zenoh RMW;
- Zenoh ROS 2 bridge;
- DDS Router;
- Robofleet-style priority bridge.

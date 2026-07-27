# rmw_fleetqox_cpp

This package is the first C++ transport-boundary reference for FleetRMW.  It is
not yet a complete ROS 2 RMW implementation.  The current scope is deliberately
smaller:

The installed `share/rmw_fleetqox_cpp/capabilities.json` is the normative,
machine-readable capability boundary. It intentionally reports
`production_ready=false` and lists supported, partial, and unsupported ABI
surfaces; prose and benchmark claims must not exceed that manifest.

- encode and decode `fleetrmw.data_frame.v1`;
- observe source sequences at a receiver;
- emit `fleetrmw.ack_nack.v1`;
- run a UDP loopback smoke that retransmits missing source sequences;
- decode Python-generated FleetRMW data frames with `fleetrmw_frame_probe`;
- export the first RMW lifecycle symbols:
  `rmw_get_implementation_identifier()`, `rmw_get_serialization_format()`,
  init options, context init/shutdown/fini, and create/destroy node;
- export publisher/subscription handles and serialized publish/take through
  `fleetrmw.data_frame.v1` frames over a UDP loopback socket transport;
- export a minimal type-erased typed publish/take path for fixed-size FleetRMW
  probe messages through `rmw_publish` and `rmw_take`;
- serialize and deserialize ROS messages with introspection C/C++ type support for
  scalar primitives, strings, nested messages, and basic arrays, currently
  verified with `std_msgs/msg/String` and `geometry_msgs/msg/Twist`;
- expose standalone `rmw_serialize`/`rmw_deserialize` through the same codec
  and identify it as `fleetrmw.introspection_c.v1` rather than DDS CDR;
- register as a ROS 2 RMW implementation for introspection C/C++ messages and pass
  the first `rcl` publish/take probe with a real `std_msgs/msg/String`;
- dispatch `rosidl_typesupport_c` handles to introspection C handles when ROS 2
  client libraries provide the generic C type-support map;
- dispatch `rosidl_typesupport_cpp` handles to introspection C++ handles and
  preserve the same FleetRMW wire encoding across C and C++ layouts;
- pass the first ROS CLI graph smoke where `ros2 topic list --no-daemon -t`
  observes a FleetRMW `rcl` talker topic and its `std_msgs/msg/String` type;
- pass the first ROS CLI endpoint-info smoke where
  `ros2 topic info --no-daemon --verbose` observes a remote FleetRMW publisher
  endpoint with node metadata, GID, and QoS profile;
- pass the first ROS CLI node graph smoke where `ros2 node list` discovers a
  remote FleetRMW node and `ros2 node info` reports its publisher topic/type
  through by-node graph APIs;
- pass the first ROS CLI pub/sub smoke where `ros2 topic pub` sends a
  `std_msgs/msg/String` and `ros2 topic echo --once` receives it through
  `rmw_fleetqox_cpp`;
- pass a ROS CLI message matrix covering `std_msgs/msg/String`,
  `builtin_interfaces/msg/Time`, `builtin_interfaces/msg/Duration`,
  `geometry_msgs/msg/Twist`, `geometry_msgs/msg/PoseStamped`,
  `sensor_msgs/msg/LaserScan`, `sensor_msgs/msg/PointCloud2`,
  `nav_msgs/msg/Odometry`, `nav_msgs/msg/Path`,
  `trajectory_msgs/msg/JointTrajectory`,
  `diagnostic_msgs/msg/DiagnosticArray`,
  `fleetrmw_interfaces/msg/SampleIdentity`, and
  `fleetrmw_interfaces/msg/ProjectionQuality`, exercising signed/unsigned time
  fields, nested messages, fixed arrays, dynamic primitive sequences, dynamic
  sequences of nested messages, binary blobs, and FleetRMW quality metadata
  through the introspection-C serializer;
- export controlled failures for remaining optional RMW surfaces while the
  implemented loaned-message, QoS-event, dynamic-message, allocation,
  `rmw_take_sequence`, and all-acknowledged slices execute real behavior;
- expose UDP/IPv4 network-flow metadata and invoke on-new-message/request/
  response callbacks outside internal transport locks;
- produce publication/subscription matched,
  reliability/durability/deadline-incompatible QoS, exact type-incompatible,
  and finite-liveliness changed events from both local
  endpoints and UDP-learned remote graph endpoints; remote `add` renewals are
  deduplicated, explicit `remove` updates current counts immediately, and a
  killed peer disconnects through graph-lease expiry, proven by a `5/5`
  two-container Docker artifact;
- produce offered and requested deadline-missed events across two UDP/netem
  containers after a real serialized sample establishes each deadline anchor;
  wait/take/callback and cleared-readiness controls pass `5/5`;
- produce publisher-side `RMW_EVENT_LIVELINESS_LOST` twice per remote
  MANUAL_BY_TOPIC run and aggregate the remote graph, deadline, liveliness,
  and message-lost artifacts into repeated callback/wait/take coverage for all
  `11` non-invalid Jazzy RMW event types;
- keep local AUTOMATIC publishers alive while they exist even when application
  traffic is idle, with a `5/5` Docker control spanning six finite lease
  intervals and observing no false lost event;
- carry remote MANUAL_BY_TOPIC assertion state over graph-control
  `liveliness_assert` frames sent by both explicit assertion and publish; a
  two-container UDP/netem artifact passes `5/5`, including idle timeout while
  the endpoint remains matched and independence from periodic graph renewal;
- isolate remote liveliness by endpoint across simultaneous publishers, with a
  second `5/5` Docker/netem artifact covering kept-alive versus expired state,
  removal from alive/not-alive state, exact aggregate counts, and endpoint
  remove/recreate churn;
- exercise local liveliness at scale with 64 MANUAL_BY_TOPIC publishers and
  exact half-expiry/reassert/full-expiry/removal aggregate transitions, plus a
  16-publisher SYSTEM_DEFAULT idle-renewal control, repeated `5/5` in Docker;
- repeat the 64-publisher MANUAL_BY_TOPIC transition matrix across two real UDP
  containers with netem; all `5/5` runs preserve matching during expiry and
  record exact aggregate match/liveliness deltas, 96 expiries, and 32
  reassertions;
- preserve alive/remove events for default, non-expiring leases across
  SYSTEM_DEFAULT, AUTOMATIC, MANUAL_BY_TOPIC, and BEST_AVAILABLE while rejecting
  UNKNOWN and deprecated MANUAL_BY_NODE endpoint policies; six scenarios pass
  `5/5` in Docker;
- produce local offered/requested incompatible-QoS events for liveliness kind,
  slower offered lease, and missing offered lease while suppressing matching;
  seven incompatible/compatible scenarios repeat `5/5` in Docker;
- produce local offered/requested deadline-incompatible events for both a
  slower offered deadline and an absent offered deadline; all four directions
  suppress matching and repeat `5/5` in Docker;
- resolve BEST_AVAILABLE policies at endpoint creation with the Jazzy
  `rmw_dds_common` selector and FleetRMW graph queries; a `5/5` Docker artifact
  covers publisher/subscription selection, zero/mixed endpoint sets,
  `rmw_*_get_actual_qos`, and frozen policy after churn;
- parse and enforce a fail-closed SQL-like content-filter subset with
  `AND/OR/NOT`, parentheses, comparisons, `LIKE`, `BETWEEN`, `IN/NOT IN`, and
  `IS NULL`/`IS NOT NULL`; missing fields remain SQL `unknown` under negation,
  and parameterized data-plane plus invalid-expression controls repeat `5/5`
  in Docker. Direct ROSIDL introspection C/C++ reflection exposes nested scalar
  paths plus C++ sequence index/length and nested sequence-message paths without
  constructing an application message; its typed data-plane probe also repeats
  `5/5`, while the full DDS dialect remains scoped;
- expose waitable unread status for every non-invalid Jazzy `rmw_event_type_t`,
  proven by a `5/5` aggregate Docker matrix over seven production probes and
  `35/35` component executions;
- export service/client handle lifecycle, service/client graph registration,
  service/client graph advertisements, by-node service/client graph queries, and
  service availability from graph state;
- carry `ROS_DOMAIN_ID` in data, ACK/NACK, route, graph, service, and action
  frames; isolate local/leased graph queries, pub/sub delivery, service
  availability/request delivery, QoS matching, reliability feedback, and router
  routes by domain, and reject nonempty data-frame type mismatches before the
  subscription queue;
- automatically trigger graph guards only for live nodes in the affected domain
  on local/remote endpoint add, remove, descriptor/QoS change, and remote lease
  expiry while suppressing unchanged advertisement renewals;
- enforce the Jazzy wait-set contract for native-entity `max_conditions`,
  zero-as-unbounded, and externally polled timer guards (which Jazzy omits from
  the capacity supplied to RMW),
  non-null entries, active/same-context waitables, and shutdown detection;
- reject publisher/subscription/service/client destruction by any node other
  than the exact node that created the entity, and apply the same owner check
  to service-server availability queries;
- pass the first ROS CLI service call smoke where `ros2 service call` sends a
  `std_srvs/srv/SetBool` request and receives the response through
  `fleetrmw.service_frame.v1` over `rmw_fleetqox_cpp`;
- carry service request/response lifespan metadata in
  `fleetrmw.service_frame.v1` and drop stale RPC frames before service/client
  delivery;
- pass a deterministic service QoS/GID probe where a stale request and a stale
  response are counted as expired and are not delivered by `rmw_take_request`
  or `rmw_take_response`; it also proves stable request identity and type/QoS-
  aware `rmw_service_server_is_available` matching plus data-plane rejection
  when an incompatible client sends without waiting for availability;
- pass a service error probe where empty response queues report `taken=false`,
  malformed response payloads return a controlled error without delivery, and
  invalid service frames are rejected;
- pass a ROS CLI service timeout probe where `ros2 service call` sends a real
  request through FleetRMW, the service intentionally delays the response, and
  the client times out without receiving a fabricated response;
- pass a router-mediated malformed-response probe where the service emits a
  correctly addressed frame with an invalid serialized body, the router
  forwards it, and `ros2 service call` exits with a concrete deserialize error
  and no fabricated `Response`;
- define a dependency-light `fleetrmw.action_frame.v1` contract for goal,
  feedback, status, result, and cancel role payloads, and pass an action-frame
  probe that round-trips those roles with lifespan checks as the low-level
  frame contract under the real `rclpy.action` probes;
- route `fleetrmw.action_frame.v1` traffic through `fleetrmw_udp_router_probe`
  after learning `action_server` and `action_client` graph advertisements,
  with `goal/cancel` delivered to the server and `feedback/status/result`
  delivered to the client;
- pass a same-process real `rclpy.action` smoke where
  `tf2_msgs/action/LookupTransform` server discovery, SendGoal, execute, and
  GetResult complete over `rmw_fleetqox_cpp`;
- pass a router-mediated real `rclpy.action` operation smoke where the action
  client and server run in separate Docker containers, peer only with
  `fleetrmw_udp_router_probe`, and complete success and cancel goals with
  feedback, status, `SUCCEEDED`/`CANCELED` results, and
  `ActionClient.server_is_ready()` true before send and after result;
- pass a router-mediated real-action lifespan matrix where fresh
  feedback/status is delivered and expired observation traffic is dropped by
  topic without breaking goal/cancel/result completion, then verify scoped
  deadline ordering places feedback before status in an action burst;
- support env-configured inter-process UDP peers with
  `FLEETQOX_RMW_BIND=host:port` and `FLEETQOX_RMW_PEERS=host:port,...`;
- support local-only inter-process POSIX shared memory with
  `FLEETQOX_RMW_LOCAL_TRANSPORT=shm` and
  `FLEETQOX_RMW_SHM_NAME=/segment_name`. The fixed ring carries payloads up to
  256 KiB, records overwrite telemetry, and requires a shared IPC namespace
  across containers. `FLEETQOX_RMW_SHM_FALLBACK_UDP=1` permits explicit UDP
  fallback; SHM mode reports an empty network-flow endpoint list rather than a
  false UDP data path. When UDP peers are configured, mode
  `shm_udp_hybrid` writes local traffic to SHM and remote traffic to UDP;
  received UDP frames are bridged into the local ring and existing source
  sequence de-duplication prevents double application delivery;
- support path-labeled inter-process peers with
  `FLEETQOX_RMW_PEERS=primary_wifi=host:port,backup_5g=host:port` plus
  `FLEETQOX_RMW_PEER_POLICY=fleet_plan` and
  either `FLEETQOX_RMW_FLEET_PATH_PLAN=/topic=backup_5g+primary_wifi` or
  `FLEETQOX_RMW_FLEET_PATH_PLAN_FILE=/path/to/plan.txt`;
- route NACK retransmissions through a separately reloadable repair policy with
  `FLEETQOX_RMW_REPAIR_PATH_PLAN`,
  `FLEETQOX_RMW_REPAIR_PATH_PLAN_FILE`, and a per-publisher
  `FLEETQOX_RMW_REPAIR_RETRANSMISSION_BUDGET`; expose repair-plan frames,
  selected paths, budget exhaustion, and last repair paths separately from
  normal fleet-plan traffic; coalesce duplicate repair requests with
  `FLEETQOX_RMW_REPAIR_MIN_INTERVAL_MS` and bound each source sequence with
  `FLEETQOX_RMW_REPAIR_MAX_ATTEMPTS_PER_SEQUENCE`; accept sequence-scoped
  controller policies in the form
  `topic=path_a+path_b|sequences=2,5|attempts=1`, and enforce them with
  `FLEETQOX_RMW_REPAIR_ADMISSION_STRICT=1`, exposing rejected requests through
  `repair_not_admitted`;
- resolve Docker/container hostnames and route frames through
  `fleetrmw_udp_router_probe` after subscriber route advertisements;
- let `fleetrmw_udp_router_probe` write per-path JSONL telemetry records with
  `--path-id` and `--telemetry-file`, enabling a host-side live controller to
  update `FLEETQOX_RMW_FLEET_PATH_PLAN_FILE` during an active publisher run;
- expose last-taken source sequence/timestamp metadata from `rmw_take` and let
  `fleetrmw_reliable_interprocess_probe` write subscriber delivery telemetry
  with latency/deadline/robot-ID fields;
- expose duplicate/out-of-order data-frame and ACK/NACK counters so redundant
  fleet-plan delivery can prove de-duplication before application `take`;
- support middleware-owned loaned messages for introspection C/C++ publishers
  and subscriptions, including borrow/publish, borrow/return, take/return, and
  outstanding-loan cleanup on endpoint destruction. Subscription take
  currently deserializes into the middleware-owned object, so this does not
  claim zero-copy;
- route service request/response frames through `fleetrmw_udp_router_probe` by
  learning service/client endpoints from graph advertisements, so a client and
  server can peer only with the router and still complete a `SetBool` service
  call;
- enforce the first measured QoS subset on subscription queues: `KEEP_LAST`
  depth trimming and `lifespan` expiry for serialized publish/take frames;
- keep a sender-side retransmit ledger for serialized topic frames, emit
  `fleetrmw.ack_nack.v1` feedback from subscriptions, and retransmit missing
  source sequences when a NACK references a retained frame;
- emit idle missing-range ACK/NACK feedback when a subscriber already knows a
  source-sequence gap but no newer frame arrives to trigger feedback naturally;
- forward `fleetrmw.ack_nack.v1` through `fleetrmw_udp_router_probe` by
  learning publisher routes from data frames, so a subscriber NACK can travel
  back through the router and trigger publisher retransmission;
- let `fleetrmw_udp_router_probe` learn publisher `lifespan` QoS from graph
  advertisements and drop expired data frames before forwarding them across a
  simulated delayed router hop;
- expose an opt-in router scheduler window that snapshots learned publisher
  deadline QoS and forwards earlier-deadline data frames before later-deadline
  frames within the same burst;
- preserve fleet identity through `FLEETQOX_RMW_ROBOT_ID` and report
  per-robot scheduler forwarding, deadline misses, queue wait, and
  deadline-success Jain fairness;
- expose an online deadline-gated scheduler path where urgent deadline flows
  bypass the holdback queue and non-urgent flows are paced during drain;
- advertise publisher/subscription graph changes with
  `fleetrmw.graph_advertisement.v1`, forward them to graph-only router peers,
  and apply remote graph advertisements back into RMW graph query state;
- attach endpoint GID and QoS metadata to graph advertisements, expose them
  through `rmw_get_publishers_info_by_topic` and
  `rmw_get_subscriptions_info_by_topic`, and renew publisher graph leases so
  late-joining CLI/observer processes can discover active publishers;
- refresh and expire learned router routes plus remote graph endpoints by
  advertisement lease;
- export automatically notified graph guard conditions and wait-set readiness
  for local serialized subscriptions and remote graph add/remove/lease-expiry;
- pass a two-context Docker probe over domains `31` and `32` proving graph-count,
  graph-guard, data-plane, service-availability/request, and leased remote-graph
  isolation with a positive same-domain control;
- export a minimal in-process graph cache for node names, topic names/types,
  publisher counts, and subscriber counts.
- pass a matched four-robot Docker netem matrix over Wi-Fi, WAN, and roaming
  seeds `7,13,29` using `deadline_sequence_repair_v1`, which combines
  route-warmup ACK gating, semantic application repair cycles, idle
  missing-range ACK/NACK feedback, and terminal guard repeats.

The executable target is:

```bash
ros2 run rmw_fleetqox_cpp fleetrmw_transport_loop_smoke \
  --robot-count 3 \
  --samples-per-robot 5 \
  --skip-every 2 \
  --json
```

Expected smoke behavior:

- `15` frames published;
- `15` frames taken;
- `6` NACK-driven retransmissions;
- `6` missing sequence ranges repaired.

Current verification:

- local unit suite: `python3 -m unittest discover tests` -> `513` tests pass;
- Docker ROS Jazzy build:
  `colcon build --base-paths ros2_ws/src --packages-select fleetrmw_interfaces rmw_fleetqox_cpp`;
- Docker artifacts:
  `results_rmw_socket/docker_cpp_transport_smoke_summary.json` and
  `results_rmw_socket/docker_cpp_frame_probe_summary.json`;
- lifecycle ABI artifact:
  `results_rmw_socket/docker_rmw_lifecycle_probe_summary.json`;
- serialized pub/sub ABI artifact:
  `results_rmw_socket/docker_rmw_serialized_pubsub_probe_summary.json`;
- QoS depth/lifespan plus full profile-compatibility ABI artifact (schema v2):
  `results_rmw_socket/docker_rmw_qos_probe_summary.json`;
- ordered/partial/concurrent `rmw_take_sequence` plus Fast DDS Jazzy exported
  symbol audit (`5/5`):
  `results_rmw_socket/docker_rmw_take_sequence_probe_summary.json`;
- subscriber-identified, multi-reader `rmw_publisher_wait_for_all_acked`
  timeout/completion artifact (`5/5`):
  `results_rmw_socket/docker_rmw_wait_for_all_acked_probe_summary.json`;
- four-container remote UDP/router/netem `rmw_publisher_wait_for_all_acked`
  timeout/completion artifact (`5/5`):
  `results_rmw_socket/docker_remote_wait_for_all_acked_probe_summary.json`;
- service QoS ABI artifact:
  `results_rmw_socket/docker_rmw_service_qos_probe_summary.json`;
  the same artifact verifies stable, distinct client endpoint GIDs and exact
  equality between the sending client's GID and the request writer GUID, then
  accepts a matching service while rejecting same-name type/QoS mismatches;
- service error ABI artifact:
  `results_rmw_socket/docker_rmw_service_error_probe_summary.json`;
- ROS CLI service-timeout artifact:
  `results_rmw_socket/docker_ros2_service_timeout_probe_summary.json`;
- router-mediated malformed-service-response artifact:
  `results_rmw_socket/docker_router_ros2_malformed_service_response_probe_summary.json`;
- action-frame contract artifact:
  `results_rmw_socket/docker_rmw_action_frame_probe_summary.json`;
- router-mediated action-frame artifact:
  `results_rmw_socket/docker_rmw_router_action_frame_probe_summary.json`;
- real `rclpy.action` smoke artifact:
  `results_rmw_socket/docker_rmw_rclpy_action_probe_summary.json`;
- router-mediated real `rclpy.action` smoke artifact:
  `results_rmw_socket/docker_rmw_router_rclpy_action_probe_summary.json`;
- router-mediated real `rclpy.action` QoS artifact:
  `results_rmw_socket/docker_rmw_router_rclpy_action_qos_probe_summary.json`;
- ACK/NACK reliability ABI artifact:
  `results_rmw_socket/docker_rmw_reliability_probe_summary.json`;
- router-mediated ACK/NACK reliability artifact:
  `results_rmw_socket/docker_router_reliability_probe_summary.json`;
- router-scheduled ACK/NACK reliability artifact:
  `results_rmw_socket/docker_router_scheduled_reliability_probe_summary.json`;
- repeated-loss router-scheduled ACK/NACK reliability artifact:
  `results_rmw_socket/docker_router_scheduled_reliability_repeated_loss_matrix_summary.json`;
- concurrent multi-robot router-scheduled ACK/NACK reliability artifact:
  `results_rmw_socket/docker_router_multi_robot_scheduled_reliability_probe_summary.json`;
- mixed real-action/control/state reliability artifact:
  `results_rmw_socket/docker_router_mixed_action_control_state_probe_summary.json`;
- proactive hard-deadline path-diversity artifact:
  `results_rmw_socket/docker_router_proactive_deadline_diversity_probe_summary.json`;
- repeated proactive hard-deadline diversity artifact:
  `results_rmw_socket/docker_router_proactive_deadline_diversity_repeated_loss_matrix_summary.json`;
- concurrent proactive hard-deadline diversity artifact:
  `results_rmw_socket/docker_router_multi_robot_proactive_deadline_diversity_probe_summary.json`;
- repeated concurrent proactive diversity artifact:
  `results_rmw_socket/docker_router_multi_robot_proactive_deadline_diversity_repeated_loss_matrix_summary.json`;
- fleet redundancy-budget/failure-domain allocator artifact:
  `results_rmw_socket/fleet_optimizer_redundancy_budget_probe_summary.json`;
- multi-hop router ACK/NACK reliability artifact:
  `results_rmw_socket/docker_router_multihop_reliability_probe_summary.json`;
- dual-router path-diversity reliability artifact:
  `results_rmw_socket/docker_router_path_diversity_probe_summary.json`;
- NACK-driven adaptive failover artifact:
  `results_rmw_socket/docker_router_adaptive_failover_probe_summary.json`;
- telemetry-score adaptive routing artifact:
  `results_rmw_socket/docker_router_adaptive_score_probe_summary.json`;
- QoS-deadline adaptive routing artifact:
  `results_rmw_socket/docker_router_adaptive_qos_probe_summary.json`;
- online-planner/file-backed fleet-plan path-ID routing artifact:
  `results_rmw_socket/docker_router_fleet_plan_probe_summary.json`;
- router-telemetry live fleet-plan control artifact:
  `results_rmw_socket/docker_router_live_telemetry_plan_probe_summary.json`;
- multi-robot live telemetry fleet-plan artifact:
  `results_rmw_socket/docker_multi_robot_live_telemetry_plan_probe_summary.json`;
- multi-robot live telemetry profile matrix artifact:
  `results_rmw_socket/docker_multi_robot_live_telemetry_matrix_summary.json`;
- matched four-robot Docker netem telemetry matrix artifact:
  `results_rmw_socket/docker_multi_robot_live_telemetry_matrix_4robot_summary.json`;
- controller-level live plan scale artifact:
  `results_rmw_socket/live_plan_scale_probe_summary.json`;
- type-erased typed pub/sub ABI artifact:
  `results_rmw_socket/docker_rmw_typed_pubsub_probe_summary.json`;
- introspection C ROS message artifacts:
  `results_rmw_socket/docker_rmw_std_msgs_string_probe_summary.json` and
  `results_rmw_socket/docker_rmw_geometry_twist_probe_summary.json`;
- first `rcl` artifact:
  `results_rmw_socket/docker_rcl_string_probe_summary.json`, with an empty
  probe stderr log after optional RMW ABI stubs are exported;
- first ROS CLI graph artifact:
  `results_rmw_socket/docker_ros2_topic_list_probe_summary.json`;
- first ROS CLI endpoint-info artifact:
  `results_rmw_socket/docker_ros2_topic_info_probe_summary.json`;
- first ROS CLI node-info artifact:
  `results_rmw_socket/docker_ros2_node_info_probe_summary.json`;
- first ROS CLI service-graph artifact:
  `results_rmw_socket/docker_ros2_service_graph_probe_summary.json`;
- first ROS CLI service-call artifact:
  `results_rmw_socket/docker_ros2_service_call_probe_summary.json`;
- router-mediated ROS CLI service-call artifact:
  `results_rmw_socket/docker_router_service_call_probe_summary.json`;
- router QoS drop artifact:
  `results_rmw_socket/docker_router_qos_drop_probe_summary.json`;
- router QoS priority artifact:
  `results_rmw_socket/docker_router_qos_priority_probe_summary.json`;
- router QoS priority matrix artifact:
  `results_rmw_socket/docker_router_qos_priority_matrix_summary.json`;
- multi-robot router QoS scheduler artifact:
  `results_rmw_socket/docker_router_multi_robot_qos_matrix_summary.json`;
- Wi-Fi/WAN/roaming adaptive multi-robot QoS artifact:
  `results_rmw_socket/docker_router_multi_robot_qos_netem_matrix_summary.json`;
- live router adaptive multi-robot QoS artifact:
  `results_rmw_socket/docker_router_multi_robot_qos_live_adaptive_matrix_summary.json`;
- live router adaptive repeated-loss QoS artifact:
  `results_rmw_socket/docker_router_multi_robot_qos_live_adaptive_repeated_loss_matrix_summary.json`;
- first ROS CLI pub/echo artifact:
  `results_rmw_socket/docker_ros2_pub_echo_probe_summary.json`;
- ROS CLI multi-message matrix artifact:
  `results_rmw_socket/docker_ros2_cli_message_matrix_summary.json`;
- standalone C++ type-support, bounded serialized-size, and unbounded-scope artifact:
  `results_rmw_socket/docker_cpp_typesupport_probe_summary.json`;
- router-mediated C++ interprocess pub/sub/service artifact:
  `results_rmw_socket/docker_router_rclcpp_interprocess_probe_summary.json`;
- Nav2/RMF-compatible action workload artifact:
  `results_rmw_socket/docker_router_upstream_nav2_rmf_workload_v5_lifecycle_manager_concurrency4_summary.json`;
- `8/16/32` repair capacity-frontier artifact:
  `results_rmw_socket/docker_fleet_repair_capacity_frontier_8_16_32_seed7_summary.json`;
- current three-seed large-scale split-scope RMW comparison artifact:
  `results_rmw_socket/large_scale_rmw_comparison_8_16_32_3seed_20260713_summary.json`;
- matched-hop RMW comparison artifact, with delivery/reliability-only claim
  scope:
  `results_rmw_socket/same_hop_rmw_comparison_8_16_32_3seed_v1_summary.json`;
- current generic-serialized matched-hop four-system Docker/netem smoke:
  `results_rmw_socket/same_hop_generic_serialized_smoke_summary.json`;
- FleetRMW direct-peer generic serialized terminate/republish `5/5` gate:
  `results_rmw_socket/docker_fleetqox_generic_serialized_relay_probe_summary.json`;
- full `8/16/32`-robot, three-seed generic-serialized matched-hop matrix:
  `results_rmw_socket/same_hop_rmw_comparison_8_16_32_3seed_v2_summary.json`;
- deterministic middle-sequence NACK and initial-sequence timeout-repair
  regression:
  `results_rmw_socket/docker_rmw_initial_sequence_reliability_probe_summary.json`;
- in-process QUIC RMW bidirectional, independent-thread publish/take,
  concurrent POST/GET stream-pair, and native client-qlog artifact:
  `results_rmw_socket/docker_quic_inprocess_rmw_bidirectional_probe_summary.json`;
- stateful FleetQoX QUIC v1/H3 gateway, bounded history, publisher-sequence
  deduplication, independent consumer replay, HTTP-status fail-closed, and
  two-container netem `5/5` artifact:
  `results_rmw_socket/docker_quic_stateful_gateway_probe_summary.json`;
- three-container stateful gateway public `rmw_publish` to separate-process
  public `rmw_take`, ordered typed payload, persistent endpoint-session, and
  netem `5/5` artifact:
  `results_rmw_socket/docker_quic_stateful_rmw_probe_summary.json`;
- six-container stateful gateway mutual-TLS client authentication, trusted
  client positive path, missing-certificate and unrelated-client-CA
  fail-closed controls, trusted-CA/wrong-publisher-URI-SAN HTTP/3 403 control,
  signed-CRL revoked-client TLS control, unauthorized state isolation, qlogs,
  and netem `5/5` artifact:
  `results_rmw_socket/docker_quic_mtls_probe_summary.json`;
- stateful QUIC gateway JSON admission policy, per-stream traffic-class quota,
  shared fleet quota, publisher allowlist, rejected-frame state isolation,
  monotonic epoch replenishment, qlogs, and two-container netem `5/5` artifact:
  `results_rmw_socket/docker_quic_admission_probe_summary.json`;
- C++ FleetRMW frame QoS/QoE/repair metadata, admission score, quota-overflow
  fleet repair-scheduler coupling, repair-capacity defer control, H3 replay,
  qlogs, and two-container netem `5/5` artifact:
  `results_rmw_socket/docker_quic_qox_repair_probe_summary.json`;
- wait/guard plus capacity/context/owner negative-control ABI artifact:
  `results_rmw_socket/docker_rmw_wait_probe_summary.json`;
- graph ABI artifact:
  `results_rmw_socket/docker_rmw_graph_probe_summary.json`.
- remote graph lease artifact:
  `results_rmw_socket/docker_rmw_remote_graph_lease_probe_summary.json`.
- inter-process serialized pub/sub artifact:
  `results_rmw_socket/docker_rmw_interprocess_pubsub_probe_summary.json`.
- multi-container router/remote-graph artifact:
  `results_rmw_socket/docker_rmw_multicontainer_router_probe_summary.json`.

The next step is expanding from the current introspection-C CLI and upstream
Nav2 introspection-C++ coverage,
service request/response path, measured queue and service QoS/error subsets,
minimal action-frame contract, router-mediated action-frame transport, real
`rclpy.action` success/cancel smokes, a Nav2/RMF-compatible action workload,
router QoS scheduling, adaptive multi-robot QoS netem evidence, live multi-epoch
router adaptive admission, repeated-loss scheduled ACK/NACK repair, strict
fleet-wide repair admission, and the first `8/16/32` capacity-frontier plus
RMW-comparison artifacts toward production-grade coverage. The remaining gap is
not another per-publisher tuning pass; it is repeated multi-seed fleet
statistics, a dedicated cross-language C/C++ matrix, real Nav2 planner/controller
components, a full-scale rerun of the generic-serialized DDS/Zenoh relay
topology, tighter middle-processing semantics for any latency claim, and
reduction of the observed `32`-robot tail latency.

# rmw_fleetqox_cpp

This package is the first C++ transport-boundary reference for FleetRMW.  It is
not yet a complete ROS 2 RMW implementation.  The current scope is deliberately
smaller:

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
- serialize and deserialize ROS messages with introspection C type support for
  scalar primitives, strings, nested messages, and basic arrays, currently
  verified with `std_msgs/msg/String` and `geometry_msgs/msg/Twist`;
- register as a ROS 2 RMW implementation for introspection C messages and pass
  the first `rcl` publish/take probe with a real `std_msgs/msg/String`;
- dispatch `rosidl_typesupport_c` handles to introspection C handles when ROS 2
  client libraries provide the generic C type-support map;
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
  `sensor_msgs/msg/LaserScan`, `nav_msgs/msg/Odometry`, and
  `nav_msgs/msg/Path`, exercising signed/unsigned time fields, nested messages,
  fixed arrays, dynamic primitive sequences, and dynamic sequences of nested
  messages through the introspection-C serializer;
- export explicit ABI stubs for optional or not-yet-supported RMW surfaces
  such as loaned messages, events, dynamic messages, network-flow endpoints,
  and callbacks, so `rcl` loader resolution is clean
  while unsupported features fail with controlled `RMW_RET_UNSUPPORTED`;
- export service/client handle lifecycle, service/client graph registration,
  service/client graph advertisements, by-node service/client graph queries, and
  service availability from graph state;
- pass the first ROS CLI service call smoke where `ros2 service call` sends a
  `std_srvs/srv/SetBool` request and receives the response through
  `fleetrmw.service_frame.v1` over `rmw_fleetqox_cpp`;
- carry service request/response lifespan metadata in
  `fleetrmw.service_frame.v1` and drop stale RPC frames before service/client
  delivery;
- pass a deterministic service QoS probe where a stale request and a stale
  response are counted as expired and are not delivered by `rmw_take_request`
  or `rmw_take_response`;
- pass a service error probe where empty response queues report `taken=false`,
  malformed response payloads return a controlled error without delivery, and
  invalid service frames are rejected;
- pass a ROS CLI service timeout probe where `ros2 service call` sends a real
  request through FleetRMW, the service intentionally delays the response, and
  the client times out without receiving a fabricated response;
- define a dependency-light `fleetrmw.action_frame.v1` contract for goal,
  feedback, status, result, and cancel role payloads, and pass an action-frame
  probe that round-trips those roles with lifespan checks before real
  `rcl_action` APIs are wired in;
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
- support path-labeled inter-process peers with
  `FLEETQOX_RMW_PEERS=primary_wifi=host:port,backup_5g=host:port` plus
  `FLEETQOX_RMW_PEER_POLICY=fleet_plan` and
  either `FLEETQOX_RMW_FLEET_PATH_PLAN=/topic=backup_5g+primary_wifi` or
  `FLEETQOX_RMW_FLEET_PATH_PLAN_FILE=/path/to/plan.txt`;
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
- export graph guard condition and wait-set readiness for local serialized
  subscriptions;
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

- local unit suite: `python3 -m unittest discover tests` -> `414` tests pass;
- Docker ROS Jazzy build:
  `colcon build --base-paths ros2_ws/src --packages-select fleetrmw_interfaces rmw_fleetqox_cpp`;
- Docker artifacts:
  `results_rmw_socket/docker_cpp_transport_smoke_summary.json` and
  `results_rmw_socket/docker_cpp_frame_probe_summary.json`;
- lifecycle ABI artifact:
  `results_rmw_socket/docker_rmw_lifecycle_probe_summary.json`;
- serialized pub/sub ABI artifact:
  `results_rmw_socket/docker_rmw_serialized_pubsub_probe_summary.json`;
- QoS ABI artifact:
  `results_rmw_socket/docker_rmw_qos_probe_summary.json`;
- service QoS ABI artifact:
  `results_rmw_socket/docker_rmw_service_qos_probe_summary.json`;
- service error ABI artifact:
  `results_rmw_socket/docker_rmw_service_error_probe_summary.json`;
- ROS CLI service-timeout artifact:
  `results_rmw_socket/docker_ros2_service_timeout_probe_summary.json`;
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
- wait/guard ABI artifact:
  `results_rmw_socket/docker_rmw_wait_probe_summary.json`;
- graph ABI artifact:
  `results_rmw_socket/docker_rmw_graph_probe_summary.json`.
- remote graph lease artifact:
  `results_rmw_socket/docker_rmw_remote_graph_lease_probe_summary.json`.
- inter-process serialized pub/sub artifact:
  `results_rmw_socket/docker_rmw_interprocess_pubsub_probe_summary.json`.
- multi-container router/remote-graph artifact:
  `results_rmw_socket/docker_rmw_multicontainer_router_probe_summary.json`.

The next step is expanding from the current introspection-C CLI coverage,
service request/response path, measured queue and service QoS/error subsets,
minimal action-frame contract, router-mediated action-frame transport, first
same-process real `rclpy.action` smoke, router-mediated real `rclpy.action`
operation smoke, router QoS scheduler, adaptive multi-robot QoS netem evidence,
live multi-epoch router adaptive admission, first repeated-loss scheduler
smoke, repeated-loss scheduled ACK/NACK repair, and first ACK/NACK
retransmission loops
through one-hop and multi-hop router paths plus dual-router path diversity
toward concurrent ACK/NACK-repaired mixed action/control/state scheduling,
C++ type-support-backed serialization,
broader caller-visible service cancellation/error semantics, and deeper
telemetry-scored network-aware QoS/QoE scheduling beyond the current
NACK-scored path memory and deadline-triggered redundancy modes.

# FleetRMW Minimal Boundary V1

## Purpose

The project has crossed the point where ACK tuning inside the Python sidecar is
the main research mechanism.  The `8`-robot live bridge now passes the repeated
Wi-Fi/WAN/roaming hard control floor after source-sequence ACK/NACK is combined
with a liveliness-backed retransmission horizon.  The next layer must move
source identity, frame ownership, liveliness recovery, and ACK/NACK semantics
toward the RMW boundary.

This document records the first dependency-free publish/take boundary for that
step.  It is not a full ROS 2 RMW implementation.  It is an executable contract
for what `rmw_fleetqox_cpp` must preserve.

## Implemented Code

Implemented in `fleetqox/rmw_boundary.py`:

- `FleetRmwBoundary.publish(...)`
  - accepts a `Ros2Sample` or mapping;
  - assigns native FleetRMW publisher identity and source sequence when missing;
  - builds a `FleetRmwSampleEnvelope`;
  - applies the existing FleetQoX admission policy;
  - emits `fleetrmw.data_frame.v1` bytes.
- `FleetRmwBoundary.take(...)`
  - decodes `fleetrmw.data_frame.v1`;
  - reconstructs the local sample view;
  - feeds the received record into `RmwAckNackTracker`;
  - emits `fleetrmw.ack_nack.v1` feedback.
- `scripts/run_rmw_boundary_smoke.py`
  - generates multi-robot command samples;
  - publishes and takes data frames in memory;
  - can intentionally skip receiver-side takes to create sequence gaps.
- `fleetqox/rmw_socket.py`
  - sends `fleetrmw.data_frame.v1` bytes over UDP;
  - takes frames at a listener boundary;
  - returns `fleetrmw.ack_nack.v1` feedback to the talker source socket.
- `fleetqox/rmw_transport_loop.py`
  - keeps one socket talker/listener pair alive across many source streams;
  - applies deterministic initial loss patterns;
  - consumes ACK/NACK feedback and retransmits missing source sequences from the
    talker ledger.
- `scripts/run_rmw_socket_smoke.py`
  - runs the same publish/take/ACK-NACK loop over local UDP sockets;
  - can delay an initial sequence and send it late to produce a real socket
    NACK gap plus out-of-order repair.
- `ros2_ws/src/rmw_fleetqox_cpp`
  - provides the first C++ transport-boundary reference package;
  - builds a dependency-light `fleetrmw_transport_loop_smoke` executable;
  - builds a `fleetrmw_frame_probe` executable that decodes Python-generated
    `fleetrmw.data_frame.v1` bytes;
  - builds the initial `librmw_fleetqox_cpp` RMW lifecycle skeleton;
  - exports identifier, init options, context init/shutdown/fini, and
    create/destroy node symbols;
  - exports publisher/subscription handles plus serialized publish/take through
    `fleetrmw.data_frame.v1` frames over a UDP loopback socket transport;
  - supports env-configured local peer delivery through
    `FLEETQOX_RMW_BIND=host:port` and `FLEETQOX_RMW_PEERS=host:port,...`;
  - exports graph guard condition, guard trigger, wait-set create/destroy, and
    `rmw_wait` readiness for local serialized subscriptions;
  - exports a minimal in-process graph cache for node names, topic names/types,
    publisher counts, and subscriber counts;
  - builds a `fleetrmw_lifecycle_probe` executable for the ABI lifecycle path;
  - builds a `fleetrmw_serialized_pubsub_probe` executable for serialized
    publish/take ownership;
  - builds a `fleetrmw_typed_pubsub_probe` executable for minimal type-erased
    typed publish/take ownership through `rmw_publish` and `rmw_take`;
  - builds `fleetrmw_std_msgs_string_probe` and `fleetrmw_geometry_twist_probe`
    executables that verify ROS introspection C message structs through
    `rmw_publish` and `rmw_take`;
  - registers as an introspection-C ROS 2 RMW implementation and builds
    `fleetrmw_rcl_string_probe`, proving a real `rcl` publisher/subscription
    can publish and take `std_msgs/msg/String` through `rmw_fleetqox_cpp`;
  - dispatches generic `rosidl_typesupport_c` handles to introspection-C handles
    when ROS 2 client libraries provide a type-support map instead of the final
    introspection handle;
  - builds `fleetrmw_rcl_graph_talker` and
    `scripts/run_rmw_docker_ros2_topic_list_probe.py`, proving
    `ros2 topic list --no-daemon --spin-time 2 -t` can observe a FleetRMW
    `rcl` talker topic and the `std_msgs/msg/String` type;
  - includes `scripts/run_rmw_docker_ros2_pub_echo_probe.py`, proving
    `ros2 topic pub` and `ros2 topic echo --once` can exchange a
    `std_msgs/msg/String` through `rmw_fleetqox_cpp`;
  - includes `scripts/run_rmw_docker_ros2_cli_message_matrix.py`, proving ROS
    CLI pub/echo works for `std_msgs/msg/String`, `geometry_msgs/msg/Twist`,
    `sensor_msgs/msg/LaserScan`, and `nav_msgs/msg/Odometry` through the same
    introspection-C serialization path;
  - exports service/client handle lifecycle plus service/client graph
    registration, remote graph advertisements, by-node service/client graph
    queries, and graph-derived service availability;
  - sends service requests and responses as `fleetrmw.service_frame.v1` frames,
    reusing the introspection-C serializer for request/response message bodies;
  - exports explicit optional-surface ABI stubs for loaned messages, services,
    events, dynamic messages, network-flow endpoints, callbacks,
    and serialization-support hooks, keeping `rcl` loader symbol resolution
    clean while unsupported APIs return controlled `RMW_RET_UNSUPPORTED`;
  - builds a `fleetrmw_wait_probe` executable for graph guard and wait-set
    readiness;
  - builds a `fleetrmw_graph_probe` executable for node/topic graph queries;
  - builds a `fleetrmw_interprocess_pubsub_probe` executable for two-process
    serialized publish/take over the same data-frame socket path;
  - builds a `fleetrmw_udp_router_probe` executable that learns subscriber
    routes from `fleetrmw.route_advertisement.v1`, then decodes and forwards
    `fleetrmw.data_frame.v1`;
  - routes `fleetrmw.service_frame.v1` request/response frames by learning
    service/client endpoint routes from graph advertisements;
  - enforces a first measured QoS subset for serialized data frames:
    `KEEP_LAST` subscription queue depth and `lifespan` expiry;
  - owns a first RMW ACK/NACK retransmission loop: subscriptions observe source
    sequence gaps, emit `fleetrmw.ack_nack.v1`, publishers retain encoded
    frames in a source-sequence ledger, and a NACK can trigger retransmission;
  - forwards `fleetrmw.ack_nack.v1` through the UDP router by learning publisher
    routes from data frames, allowing a subscriber NACK to recover a
    router-dropped data frame;
  - lets the UDP router learn publisher `lifespan` QoS from graph
    advertisements and reject expired data frames before forwarding over a
    delayed hop;
  - exposes an opt-in UDP router scheduler window that snapshots learned
    publisher deadline QoS and forwards earlier-deadline frames first within a
    short burst;
  - advertises publisher/subscription graph changes with
    `fleetrmw.graph_advertisement.v1`, forwards them to graph-only router
    peers, and applies received remote advertisements into RMW graph query
    state;
  - includes endpoint id, endpoint GID, and QoS profile metadata in
    `fleetrmw.graph_advertisement.v1`, exposes local/remote endpoint snapshots
    through `rmw_get_publishers_info_by_topic` and
    `rmw_get_subscriptions_info_by_topic`, and renews publisher graph leases so
    late-joining observer processes can discover active publishers;
  - includes `scripts/run_rmw_docker_ros2_topic_info_probe.py`, proving
    `ros2 topic info --no-daemon --verbose` can observe a remote FleetRMW
    publisher endpoint with node name, node namespace, GID, and QoS profile;
  - implements publisher/subscriber names-and-types by node and includes
    `scripts/run_rmw_docker_ros2_node_info_probe.py`, proving
    `ros2 node list --no-daemon` discovers a remote FleetRMW node and
    `ros2 node info --no-daemon` reports its publisher topic/type;
  - builds `fleetrmw_rcl_service_node` and includes
    `scripts/run_rmw_docker_ros2_service_graph_probe.py`, proving a late-joining
    `ros2 service list --no-daemon --spin-time 2 -t` observer sees
    `/fleetqox/set_bool [std_srvs/srv/SetBool]` and
    `ros2 node info --no-daemon` reports the same service server through by-node
    graph APIs;
  - builds a `fleetrmw_remote_graph_probe` executable that observes remote graph
    advertisements without creating a local publisher/subscription on the
    target topic;
  - builds a `fleetrmw_remote_graph_lease_probe` executable that verifies remote
    graph endpoints are removed from graph queries after lease expiry;
  - includes `scripts/run_rmw_docker_multicontainer_router_probe.py` to build
    the package and verify publisher-router-subscriber-observer delivery and
    graph synchronization across four Docker containers;
  - mirrors the data-frame, ACK/NACK, and NACK-driven retransmit behavior before
    implementing full networked publish/take/wait/graph RMW ABI entry points.

The boundary schemas are:

```text
fleetrmw.rmw_publish.v1
fleetrmw.rmw_take.v1
fleetrmw.rmw_boundary_smoke.v1
fleetrmw.rmw_socket_publish.v1
fleetrmw.rmw_socket_take.v1
fleetrmw.rmw_socket_feedback.v1
fleetrmw.rmw_socket_smoke.v1
fleetrmw.rmw_transport_loop.v1
fleetrmw.route_advertisement.v1
fleetrmw.graph_advertisement.v1
fleetrmw.rmw_udp_router_probe.v1
fleetrmw.rmw_typed_pubsub_probe.v1
fleetrmw.rmw_std_msgs_string_probe.v1
fleetrmw.rmw_geometry_twist_probe.v1
fleetrmw.rmw_qos_probe.v1
fleetrmw.rmw_docker_qos_probe.v1
fleetrmw.rmw_reliability_probe.v1
fleetrmw.rmw_docker_reliability_probe.v1
fleetrmw.rmw_reliable_interprocess_probe.v1
fleetrmw.rmw_router_reliability_probe.v1
fleetrmw.rmw_router_multihop_reliability_probe.v1
fleetrmw.rmw_router_path_diversity_probe.v1
fleetrmw.rmw_router_adaptive_failover_probe.v1
fleetrmw.rmw_router_adaptive_score_probe.v1
fleetrmw.rmw_router_adaptive_qos_probe.v1
fleetrmw.rmw_router_fleet_plan_probe.v1
fleetrmw.fleet_optimizer_summary.v1
fleetrmw.fleet_optimizer_decision.v1
fleetrmw.fleet_optimizer_runtime.v1
fleetrmw.fleet_optimizer_probe.v1
fleetrmw.fleet_optimizer_runtime_probe.v1
fleetrmw.online_fleet_path_plan.v1
fleetrmw.online_fleet_path_plan_probe.v1
fleetrmw.router_path_telemetry.v1
fleetrmw.subscriber_delivery_telemetry.v1
fleetrmw.live_path_plan_controller.v1
fleetrmw.rmw_router_live_telemetry_plan_probe.v1
fleetrmw.rmw_router_qos_drop_probe.v1
fleetrmw.rmw_router_qos_priority_probe.v1
fleetrmw.rmw_router_qos_priority_matrix.v1
fleetrmw.router_netem.v1
fleetrmw.rmw_multi_robot_live_netem_matrix.v1
fleetrmw.rmw_multi_robot_live_stochastic_netem_matrix.v1
fleetrmw.rmw_multi_robot_live_stochastic_netem_sweep.v1
fleetrmw.rcl_string_probe.v1
fleetrmw.rcl_graph_talker.v1
fleetrmw.rmw_ros2_topic_list_probe.v1
fleetrmw.rmw_ros2_topic_info_probe.v1
fleetrmw.rmw_ros2_node_info_probe.v1
fleetrmw.rmw_ros2_pub_echo_probe.v1
fleetrmw.rmw_ros2_cli_message_matrix.v1
fleetrmw.rmw_remote_graph_probe.v1
fleetrmw.rmw_remote_graph_lease_probe.v1
fleetrmw.rmw_multicontainer_router_probe.v1
```

## Smoke Evidence

Command:

```bash
python3 -m scripts.run_rmw_boundary_smoke \
  --robot-count 2 \
  --samples-per-robot 3 \
  --skip-take robot_0000:2 \
  --json
```

Observed summary:

```json
{
  "published": 6,
  "taken": 5,
  "ack_nack_feedback": 5,
  "missing_sequence_range_count": 1,
  "skipped_takes": ["robot_0000:2"]
}
```

The skipped take produces one receiver-visible missing sequence range for
`robot_0000`.  A late arrival of sequence `2` is also covered by unit tests and
closes the gap while marking the sample as out-of-order.

Socket command:

```bash
python3 -m scripts.run_rmw_socket_smoke \
  --robot-count 2 \
  --samples-per-robot 3 \
  --skip-initial robot_0000:2 \
  --json
```

Observed socket summary:

```json
{
  "published": 6,
  "taken": 6,
  "retransmitted": 1,
  "ack_nack_feedback": 6,
  "missing_sequence_range_count": 1,
  "late_out_of_order_count": 1,
  "initial_skips": ["robot_0000:2"]
}
```

The socket smoke also supports deterministic multi-gap patterns.  The artifact
`results_rmw_socket/socket_smoke_skip_every2_summary.json` uses
`--robot-count 3 --samples-per-robot 5 --skip-every 2`, publishes and takes `15`
frames, triggers `6` NACK-driven retransmissions, and repairs `6` missing
sequence ranges.

The C++ reference package has the same smoke artifact at
`results_rmw_socket/cpp_transport_smoke_summary.json`: `15` frames published,
`15` taken, `6` ACK/NACK-driven retransmissions, and `6` missing sequence ranges
repaired. Unit tests also compile and load the identifier symbols, confirming
`rmw_get_implementation_identifier()` returns `rmw_fleetqox_cpp` and
`rmw_get_serialization_format()` returns `cdr`.

The C++ package was also built inside Docker with `ros:jazzy-ros-base` through
`colcon` alongside `fleetrmw_interfaces`.  The Docker ROS build/run artifact
`results_rmw_socket/docker_cpp_transport_smoke_summary.json` repeats the `3`
robot x `5` sample smoke with `15` frames published, `15` taken, `15` ACK/NACK
records, `6` retransmissions, and `6` repaired missing ranges.  The
cross-runtime frame-probe artifact
`results_rmw_socket/docker_cpp_frame_probe_summary.json` confirms that the C++
decoder now accepts a `fleetrmw.data_frame.v1` packet emitted by the Python
`FleetRmwBoundary`: status `decoded`, robot `robot_0005`, topic
`/robot_0005/cmd_vel`, and source sequence `42`.

The first lifecycle ABI artifact
`results_rmw_socket/docker_rmw_lifecycle_probe_summary.json` goes one step past
identifier export.  In Docker ROS Jazzy, `fleetrmw_lifecycle_probe` executes
`rmw_init_options_init`, `rmw_init`, `rmw_create_node`, `rmw_destroy_node`,
`rmw_shutdown`, `rmw_context_fini`, and `rmw_init_options_fini`, reporting
status `ok`, implementation `rmw_fleetqox_cpp`, node
`/fleetqox/fleetqox_lifecycle_probe`, instance ID `42`, and actual domain ID
`0`.

The first serialized pub/sub ABI artifact
`results_rmw_socket/docker_rmw_serialized_pubsub_probe_summary.json` then proves
publisher/subscription handle allocation plus FleetRMW data-frame byte
ownership:
`rmw_create_publisher`, `rmw_create_subscription`,
`rmw_publish_serialized_message`, `rmw_take_serialized_message`,
matched-endpoint counting, and destroy paths all run in Docker ROS Jazzy.  The
probe publishes `18` bytes on `/fleetqox/serialized_probe`, takes the same `18`
bytes from a decoded `fleetrmw.data_frame.v1`, and reports
`data_frame_wrapped=true`, schema `fleetrmw.data_frame.v1`, and payload
`fleetrmw-cdr-bytes`.  The same probe now verifies the local transport boundary
is socket-backed, with `socket_backed=true`, `socket_frames_sent=1`, and
`socket_frames_received=1`.

The type-erased typed pub/sub artifact
`results_rmw_socket/docker_rmw_typed_pubsub_probe_summary.json` extends that
same path to `rmw_publish` and `rmw_take` for a fixed-size FleetRMW probe
message.  The probe reports status `ok`, `typed_message_size=40`,
`data_frame_wrapped=true`, `socket_backed=true`, `socket_frames_sent=1`,
`socket_frames_received=1`, and recovers sequence `7`, linear velocity `0.42`,
angular velocity `-0.13`, and label `typed-probe`.

The ROS introspection C typed artifacts move beyond the fixed-size internal
probe.  `results_rmw_socket/docker_rmw_std_msgs_string_probe_summary.json`
publishes and takes a real `std_msgs/msg/String` C struct through
`rmw_publish`/`rmw_take`, reporting status `ok`, `socket_frames_sent=1`,
`socket_frames_received=1`, and payload
`fleetqox std_msgs/String over introspection C`.  The command-oriented artifact
`results_rmw_socket/docker_rmw_geometry_twist_probe_summary.json` publishes and
takes a real `geometry_msgs/msg/Twist`, proving nested primitive fields:
`linear_x=0.7`, `linear_y=-0.2`, and `angular_z=0.33`.

The first `rcl` artifact `results_rmw_socket/docker_rcl_string_probe_summary.json`
proves the same path through ROS 2's client-library layer instead of direct RMW
calls.  In Docker ROS Jazzy, `fleetrmw_rcl_string_probe` sets
`RMW_IMPLEMENTATION=rmw_fleetqox_cpp`, creates one `rcl` node, publisher, and
subscription, publishes a real `std_msgs/msg/String`, and takes the payload
`fleetqox rcl std_msgs/String`.  The current full Docker suite additionally
asserts the probe's stderr is empty, which confirms the optional RMW ABI stubs
eliminate the earlier loader-level missing-symbol noise.

The first ROS CLI graph artifact
`results_rmw_socket/docker_ros2_topic_list_probe_summary.json` moves from an
in-process `rcl` probe to ROS 2 tooling.  The runner starts
`ros2 topic list --no-daemon --spin-time 2 -t` as an observer, then starts
`fleetrmw_rcl_graph_talker` as a real `rcl` application publisher.  The CLI
returns `0`, stderr is empty, and stdout includes
`/fleetqox/rcl_graph_talker [std_msgs/msg/String]` along with ROS-created
`/parameter_events` and `/rosout` topics.  This required two extra RMW
surfaces: resolving `rosidl_typesupport_c` maps into introspection-C handles,
and allowing ROS node startup to create type-description service handles even
before full service/action coverage is complete.

The first ROS CLI pub/echo artifact
`results_rmw_socket/docker_ros2_pub_echo_probe_summary.json` proves CLI data
delivery through the same RMW.  The runner starts
`ros2 topic echo --no-daemon --once --timeout 8 /fleetqox/cli_echo
std_msgs/msg/String`, then starts `ros2 topic pub --times 3 --rate 5` with
`FLEETQOX_RMW_PEERS` pointing at the echo process.  The echo CLI returns `0`,
stderr is empty, and stdout contains `data: fleetqox cli echo`.  This exposed
and fixed an important wait-set compatibility issue: `rclpy` passes the RMW
subscription implementation-data pointer into `rmw_wait`, while the earlier
local probe passed the full `rmw_subscription_t *`.  `rmw_wait` now resolves
readiness through a registered waitable-subscription lookup that supports both
forms.

The wait-set artifact `results_rmw_socket/docker_rmw_wait_probe_summary.json`
adds the next `rcl`-facing primitive: graph guard retrieval/trigger and
`rmw_wait` readiness.  The Docker probe triggers the node graph guard, publishes
one serialized message to a local subscription, and reports status `ok` with
`graph_guard_ready=true`, `subscription_ready=true`, and `publish_ret=0`.

The graph artifact `results_rmw_socket/docker_rmw_graph_probe_summary.json`
adds a minimal ROS graph cache.  The Docker probe creates one node, one
publisher, and one subscription, then validates `rmw_get_node_names`,
`rmw_get_topic_names_and_types`, `rmw_count_publishers`, and
`rmw_count_subscribers`: status `ok`, node count `1`, topic count `1`,
publisher count `1`, and subscriber count `1`.

The inter-process artifact
`results_rmw_socket/docker_rmw_interprocess_pubsub_probe_summary.json` proves
the same serialized RMW data path can cross process boundaries without DDS.  A
subscriber process binds `FLEETQOX_RMW_BIND=127.0.0.1:48101`, a publisher
process sends with `FLEETQOX_RMW_PEERS=127.0.0.1:48101`, and the subscriber
takes the `fleetqox-interprocess-cdr` payload from
`/fleetqox/interprocess_probe`.  The publisher reports `peer_count=1` and
`socket_frames_sent=1`; the subscriber reports `socket_frames_received=1`,
`taken=true`, and `25` received bytes.

The multi-container router artifact
`results_rmw_socket/docker_rmw_multicontainer_router_probe_summary.json` moves
that proof onto a private Docker network with four containers.  The subscriber
container binds `0.0.0.0:48201` and advertises its topic route to the router
with `fleetrmw.route_advertisement.v1`; the publisher container sends only to
the router hostname; the router container binds `0.0.0.0:48200`, learns the
subscriber route, and forwards the data frame before the subscriber takes the
`fleetqox-multicontainer-router-cdr` payload from
`/fleetqox/multicontainer_router_probe`.  Publisher/subscriber creation also
emits `fleetrmw.graph_advertisement.v1`, and the router forwards those graph
advertisements to a graph-only observer peer.  The router reports
`route_advertisements=1`, `learned_routes=1`, `graph_advertisements=2`,
`graph_forwarded=2`, `graph_peer_count=1`, `graph_publishers=1`,
`graph_subscriptions=1`, `received_frames=1`, `forwarded_frames=1`, and
`invalid_frames=0`; the subscriber reports `socket_frames_received=1`,
`taken=true`, and `34` received bytes.  The observer does not create a local
publisher or subscription on the topic, but its RMW graph queries report
`topic_found=true`, `publisher_count=1`, `subscriber_count=1`,
`node_count=3`, and type `rmw_fleetqox_cpp_interprocess_probe`.

The ROS CLI endpoint-info artifact
`results_rmw_socket/docker_ros2_topic_info_probe_summary.json` verifies the
same remote graph path through standard ROS 2 CLI endpoint APIs.  A FleetRMW
`rcl` talker publishes `/fleetqox/rcl_graph_talker`; a late-joining
`ros2 topic info --no-daemon --spin-time 2 --verbose` observer discovers the
publisher through renewed graph advertisements and reports `Publisher count: 1`,
node name `fleetqox_rcl_graph_talker`, namespace `/fleetqox`, a non-empty GID,
and the RELIABLE/KEEP_LAST/VOLATILE QoS profile.

The ROS CLI message-matrix artifact
`results_rmw_socket/docker_ros2_cli_message_matrix_summary.json` verifies
`4/4` CLI pub/echo cases over `rmw_fleetqox_cpp`: `std_msgs/msg/String`,
`geometry_msgs/msg/Twist`, `sensor_msgs/msg/LaserScan`, and
`nav_msgs/msg/Odometry`.  This covers ROS strings, nested messages, fixed
covariance arrays, and dynamic float sequences (`ranges`/`intensities`) through
the current introspection-C serializer.

The ROS CLI node-info artifact
`results_rmw_socket/docker_ros2_node_info_probe_summary.json` verifies by-node
graph queries through standard ROS 2 CLI tooling.  A late-joining
`ros2 node list --no-daemon --spin-time 2` observer discovers
`/fleetqox/fleetqox_rcl_graph_talker`, and
`ros2 node info --no-daemon --spin-time 2 /fleetqox/fleetqox_rcl_graph_talker`
reports publisher `/fleetqox/rcl_graph_talker: std_msgs/msg/String`.

The ROS CLI service-graph artifact
`results_rmw_socket/docker_ros2_service_graph_probe_summary.json` verifies the
service side of the same graph path.  A FleetRMW `rcl` service node creates
`/fleetqox/set_bool` with type `std_srvs/srv/SetBool`; a late-joining
`ros2 service list --no-daemon --spin-time 2 -t` observer discovers the service
through renewed service graph advertisements, and `ros2 node info --no-daemon`
reports it under `Service Servers`.

The ROS CLI service-call artifact
`results_rmw_socket/docker_ros2_service_call_probe_summary.json` verifies the
first RPC path.  A FleetRMW `rcl` SetBool server binds one UDP endpoint, a
`ros2 service call /fleetqox/set_bool std_srvs/srv/SetBool "{data: true}"`
client binds another, and request/response frames cross the non-DDS
`rmw_fleetqox_cpp` transport.  The CLI receives
`success=True, message='fleetqox set_bool accepted'`, while the server reports
`request_count=1`.

The router-mediated service-call artifact
`results_rmw_socket/docker_router_service_call_probe_summary.json` verifies the
fleet routing version of the same RPC path.  The SetBool server and ROS CLI
client each peer only with `fleetrmw_udp_router_probe`; the router learns
service/client endpoints from graph advertisements, forwards two service frames,
and the client still receives `success=True`.

The remote graph lease artifact
`results_rmw_socket/docker_rmw_remote_graph_lease_probe_summary.json` verifies
that remote graph state is not permanent.  It injects a remote publisher
advertisement with a `30 ms` lease, observes `publisher_count_before=1` and
`topic_found_before=true`, waits past the lease, then observes
`publisher_count_after=0`, `topic_found_after=false`, and `node_count_after=1`.

The first live seed-`13` egress-piggyback ACK/NACK audit was a negative result:
`n_robot_qoe_recovery_quota_8robot_egress_acknack_seed13_aggregate_summary.json`
still fails the hard budget with minimum per-robot control delivery `0.8889`,
loss `0.0663`, and p95 `2012.22 ms`.  The boundary mechanism is connected, but
the fixed retransmit memory was too short for late source-sequence NACK repair.
The follow-up liveliness-horizon row closes that gap:
`n_robot_qoe_recovery_quota_8robot_liveliness_horizon_3seed_aggregate_summary.json`
passes seeds `7,13,29` with hard budget `3/3`, control delivery `0.9902`,
minimum per-robot control delivery `0.9804`, loss `0.0311`, p95 `1085.30 ms`,
and quality coverage `1.0000`.

## Why This Matters

The previous bridge could clear retransmit state with source-aware ACKs, but
the source identity was still produced by the ROS 2 sidecar/egress path.  The
new boundary makes the RMW-facing ownership explicit:

```text
ROS-like sample
-> native publisher_id + source_sequence_number
-> FleetRMW sample envelope
-> data_frame
-> take
-> source-sequence ACK/NACK
```

That is the minimal loop needed before replacing DDS.  It separates the
research question from ROS 2 C++ glue: the system can now test whether native
source-sequence feedback, liveliness-backed retransmission memory, and gap-aware
lease replay can outperform sidecar event-ID feedback before implementing full
node/graph/wait-set support.

## Remaining Gap

The boundary is still not a complete ROS 2 RMW ABI implementation.  It now owns
the first lifecycle symbols, publisher/subscription handles, and serialized
byte ownership needed by `rcl`.  It also has a first wait-set/guard-condition
skeleton, minimal graph cache, and remote graph-advertisement synchronization
into graph query APIs.  It also owns a minimal type-erased typed publish/take
path for fixed-size probe messages, a first ROS introspection C typed path for
String/Twist-like messages, a first `rcl` publish/take probe, first
`ros2 topic list`, `ros2 topic pub/echo`, `ros2 topic info`, `ros2 node info`,
and `ros2 service list` CLI smokes, generic C type-support dispatch,
service/client graph support, and explicit unsupported-feature ABI stubs. It
now owns a first `std_srvs/srv/SetBool` service request/response path, a
measured local QoS subset, router-level QoS admission/scheduling probes, and a
first RMW-owned ACK/NACK retransmission loop including one-router and multi-hop
router recovery probes, plus a first dual-router path-diversity smoke where a
backup path masks a primary-path drop without publisher retransmission. It does
also owns a first NACK-driven adaptive failover mode where publisher data starts
on the primary router and moves retransmission traffic to the backup router
after a missing source sequence is reported. The first `adaptive_qos` mode ties
ROS deadline QoS to transport behavior: urgent deadline topics use redundant
router paths, while relaxed topics can remain adaptive unicast/failover. It does
also has a first telemetry-score memory: a NACK penalizes the active peer, the
next retransmission moves to the lower-score peer, and the next post-recovery
publish follows that lower-risk path. It also now owns an offline fleet-level
QoS/QoE path optimizer that scores path loss, latency, jitter, NACK rate,
deadline misses, utilization, per-robot QoE debt, flow class, deadlines,
criticality, and fleet capacity, then chooses unicast, redundant, degraded, or
deferred routing. That optimizer now crosses the sidecar runtime boundary as a
`fleet_optimizer` batch payload, annotates events with
`fleetrmw.fleet_optimizer_decision.v1`, degrades/defer flows under capacity
pressure, and actuates selected path choices as per-path UDP target
transmissions in the dependency-free sidecar runtime probe. The C++ RMW socket
transport now also has a first `fleet_plan` mode: path-labeled peers in
`FLEETQOX_RMW_PEERS`, `FLEETQOX_RMW_FLEET_PATH_PLAN`, and
`FLEETQOX_RMW_FLEET_PATH_PLAN_FILE` bind selected path IDs to live Docker
router peers. It also has an online Python path-plan controller that turns
per-path observations into guarded topic route plans, and the Docker RMW probe
now updates that file after the first publish so the same publisher process
reloads a new redundant path plan for later data frames. The router path now
also emits `fleetrmw.router_path_telemetry.v1` JSONL records, and a live
controller tails those files to rewrite the RMW plan file during the same
publisher session. The subscriber path now writes
`fleetrmw.subscriber_delivery_telemetry.v1` from `rmw_take` source sequence and
timestamp metadata, and the controller converts those records into robot QoE
state. The live RMW probe now covers two robots/topics with divergent
control-vs-state path rules, and the controller-scale probe covers N robots and
2N topics without Docker. Redundant-path duplicate data frames are counted and
de-duplicated before application delivery. A multi-robot profile matrix now
repeats the Docker RMW path over `wifi`, `wan`, and `roaming`
router-telemetry profiles. It does not yet own actions, full sequence/C++
type-support coverage, full service QoS semantics, or scaled end-to-end
`tc netem` QoE/robot-SLO telemetry over many topics and robots.
The dependency-free Python boundary and the C++ socket reference now prove the
same frame/ACK contract, including Docker ROS build coverage.  The Python
sidecar runtime can consume
`fleetrmw.ack_nack.v1` NACK gaps for tracked control-lease retransmission, and
the ROS 2 egress bridge can piggyback those ACK/NACK records in regular
feedback windows.  The live proof now exists for `8` robots; the remaining gap
is moving ownership of the same metadata out of the sidecar bridge and into a
minimal RMW ABI layer:

1. keep the C++ section-aware data-frame decoder aligned with the Python frame
   schema as new envelope fields are added;
2. carry source sequence, effective lifespan, source lifespan, liveliness lease,
   ACK/NACK recovery horizon, and fleet optimizer decisions through
   telemetry-scored multi-path RMW/router paths;
3. bind the current live profile matrix to real `tc netem` shaping and then run
   the N-topic controller-scale workload through live router/subscriber loops,
   including duplicate/de-duplication and richer robot-SLO outcomes, so
   `FLEETQOX_RMW_FLEET_PATH_PLAN_FILE` is driven by end-to-end fleet health;
4. expand from the current ROS CLI topic/service graph, pub/echo, and SetBool
   service-call smokes to richer messages, sequence/C++ type-support coverage,
   action transport APIs, and measured service QoS semantics.

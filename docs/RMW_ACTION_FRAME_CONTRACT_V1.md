# RMW Action Frame Contract V1

## Purpose

This milestone adds the first dependency-light action-frame contract for
`rmw_fleetqox_cpp`. It does not implement ROS 2 `rcl_action` APIs yet. It locks
the transport shape that the later action implementation must preserve across
the already-tested topic and service paths.

Actions combine request/response semantics with streaming topics. The project
needs a frame contract for goal, feedback, status, result, and cancel traffic
before wiring those roles into real `rcl_action` goal handles and waitables.

## Implemented Code

- `ros2_ws/src/rmw_fleetqox_cpp/include/rmw_fleetqox_cpp/data_frame.hpp`
  - defines `fleetrmw.action_frame.v1`;
  - adds `ActionFrame` with role, action name, type name, endpoint id, goal id,
    sequence id, source timestamp, lifespan, and serialized payload.
- `ros2_ws/src/rmw_fleetqox_cpp/src/data_frame.cpp`
  - encodes and decodes action frames with the same FleetRMW frame magic and
    hex serialized payload convention used by data and service frames;
  - rejects other schema versions, including `fleetrmw.service_frame.v1`;
  - treats missing lifespan as infinite for forward compatibility;
  - exposes `action_frame_expired(...)` for later queue admission logic.
- `ros2_ws/src/rmw_fleetqox_cpp/src/action_frame_probe.cpp`
  - round-trips all five minimal action roles: `goal`, `feedback`, `status`,
    `result`, and `cancel`;
  - verifies freshness boundaries and service-schema rejection;
  - emits `fleetrmw.rmw_action_frame_probe.v1`.
- `ros2_ws/src/rmw_fleetqox_cpp/src/udp_router_probe.cpp`
  - learns `action_server` and `action_client` graph advertisements;
  - forwards `goal` and `cancel` frames toward action servers by action name;
  - forwards `feedback`, `status`, and `result` frames toward action clients by
    endpoint id or action name;
  - reports `expected_action_frames`, `action_frames`, `action_forwarded`,
    `graph_action_servers`, and `graph_action_clients`.
- `ros2_ws/src/rmw_fleetqox_cpp/src/action_router_probe.cpp`
  - advertises one action server and one action client;
  - sends all five action roles through `fleetrmw_udp_router_probe`;
  - verifies server-visible `goal/cancel` and client-visible
    `feedback/status/result` delivery;
  - emits `fleetrmw.rmw_action_router_probe.v1`.
- `scripts/run_rmw_docker_action_frame_probe.py`
  - builds `fleetrmw_interfaces` and `rmw_fleetqox_cpp` inside
    `ros:jazzy-ros-base`;
  - runs `fleetrmw_action_frame_probe`;
  - writes a JSON summary under `results_rmw_socket/`.
- `scripts/run_rmw_docker_router_action_frame_probe.py`
  - builds the same package set in Docker;
  - starts `fleetrmw_udp_router_probe`;
  - runs `fleetrmw_action_router_probe` over loopback UDP;
  - writes a JSON summary under `results_rmw_socket/`.
- `scripts/run_rmw_docker_rclpy_action_probe.py`
  - builds the same package set in Docker;
  - runs a real `rclpy.action.ActionServer` and `ActionClient` using
    `tf2_msgs/action/LookupTransform` with `RMW_IMPLEMENTATION=rmw_fleetqox_cpp`;
  - verifies server discovery, goal acceptance, execution, and GetResult
    response delivery;
  - writes a JSON summary under `results_rmw_socket/`.
- `scripts/run_rmw_docker_router_rclpy_action_probe.py`
  - runs the same `rclpy.action` client and server in separate Docker
    containers;
  - makes both containers peer only with `fleetrmw_udp_router_probe`;
  - verifies router-mediated action server availability, SendGoal, and GetResult
    service-frame delivery.

## Frame Fields

The V1 action frame carries:

```text
schema_version = fleetrmw.action_frame.v1
kind = action_frame
role = goal | feedback | status | result | cancel
action_name
type_name
endpoint_id
goal_id
sequence_id
source_timestamp_ns
lifespan_ns
serialized_payload
```

The `serialized_payload` field is optional and uses the same
`encoding=hex`, `size`, and `data` object shape as existing FleetRMW data and
service frames.

## Evidence

Package-level regression:

```bash
python3 -m unittest tests.test_rmw_fleetqox_cpp_package
```

Docker ROS Jazzy probe:

```bash
python3 -m scripts.run_rmw_docker_action_frame_probe \
  --json \
  --summary-json results_rmw_socket/docker_rmw_action_frame_probe_codex_check_summary.json
```

Router-mediated Docker probe:

```bash
python3 scripts/run_rmw_docker_router_action_frame_probe.py \
  --json \
  --summary-json results_rmw_socket/docker_rmw_router_action_frame_probe_summary.json
```

Real `rclpy.action` Docker smoke:

```bash
python3 scripts/run_rmw_docker_rclpy_action_probe.py \
  --json \
  --summary-json results_rmw_socket/docker_rmw_rclpy_action_probe_summary.json
```

Router-mediated real `rclpy.action` Docker smoke:

```bash
python3 scripts/run_rmw_docker_router_rclpy_action_probe.py \
  --json \
  --summary-json results_rmw_socket/docker_rmw_router_rclpy_action_probe_summary.json
```

Remote `udy` result:

```json
{
  "status": "ok",
  "probe": {
    "status": "ok",
    "action_name": "/fleetqox/navigate_to_pose",
    "type_name": "nav2_msgs/action/NavigateToPose",
    "role_count": 5,
    "lifespan_ns": 5000000,
    "not_expired": true,
    "expired": true,
    "rejects_service_schema": true,
    "roles": ["goal", "feedback", "status", "result", "cancel"]
  },
  "probe_returncode": 0,
  "docker_returncode": 0,
  "probe_stderr": "",
  "docker_stderr": ""
}
```

Remote `udy` full unit result:

```text
Ran 414 tests in 9.736s
OK
```

The probe contract requires:

```json
{
  "status": "ok",
  "probe": {
    "status": "ok",
    "roles": ["goal", "feedback", "status", "result", "cancel"],
    "not_expired": true,
    "expired": true,
    "rejects_service_schema": true
  }
}
```

The router-mediated probe additionally requires:

```json
{
  "status": "ok",
  "probe": {
    "status": "ok",
    "server_received_roles": ["goal", "cancel"],
    "client_received_roles": ["feedback", "status", "result"]
  },
  "router": {
    "status": "ok",
    "expected_action_frames": 5,
    "action_frames": 5,
    "action_forwarded": 5,
    "graph_action_servers": 1,
    "graph_action_clients": 1
  }
}
```

The real `rclpy.action` smoke additionally requires:

```json
{
  "status": "ok",
  "probe": {
    "status": "ok",
    "action_type": "tf2_msgs/action/LookupTransform",
    "available": true,
    "goal_accepted": true,
    "events": ["execute"],
    "result_done": true,
    "result_status": 4,
    "result_frame": "map",
    "result_child_frame": "base_link",
    "result_error": 0
  }
}
```

The router-mediated `rclpy.action` smoke additionally requires:

```json
{
  "status": "ok",
  "client": {
    "status": "ok",
    "available_before_send": true,
    "available_after_result": true,
    "success_goal_accepted": true,
    "success_result_status": 4,
    "feedback_callbacks": ["success", "cancel"],
    "cancel_goal_accepted": true,
    "cancel_goals_canceling": 1,
    "cancel_result_status": 5,
    "status_observed": true,
    "graph_before_send": {
      "status_publishers": 1,
      "feedback_publishers": 1,
      "status_subscribers": 2,
      "feedback_subscribers": 1
    }
  },
  "server": {
    "status": "ok",
    "feedback_published": 2,
    "cancel_callbacks": 1,
    "events": [
      "execute:map",
      "execute:cancel_map",
      "cancel_callback",
      "cancel_requested"
    ]
  },
  "router": {
    "status": "ok",
    "service_frames": 10,
    "service_forwarded": 10
  }
}
```

## Remaining Gap

This closes the frame contract, proves router-mediated action-frame transport
for the minimal action roles, proves a same-process real `rclpy.action`
goal/result path over FleetRMW services/topics, and proves router-mediated
real `rclpy.action` availability, feedback, status, cancel, and result across
separate containers. The action availability fix depends on periodic pub/sub
graph renewal and graph-backed matched counts. The extended probe also proves
feedback/status topic routing and SendGoal/CancelGoal/GetResult service routing
through the same FleetRMW router. `docs/RMW_ACTION_QOS_V1.md` additionally
proves lifespan-based admission for real feedback/status traffic.
Remaining action work:

- add deadline-aware scheduling and latency/deadline telemetry for concurrent
  action and robot data flows;
- add Nav2/RMF action smoke tests using `RMW_IMPLEMENTATION=rmw_fleetqox_cpp`.

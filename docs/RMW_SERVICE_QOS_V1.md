# RMW Service QoS V1

## Purpose

This milestone adds deterministic service request/response freshness and client
identity coverage to `rmw_fleetqox_cpp`. The previous service evidence proved successful
`std_srvs/srv/SetBool` request/response delivery through
`fleetrmw.service_frame.v1`, including router-mediated forwarding. It did not
prove that stale request or response frames are filtered before application
delivery.

Service freshness matters before action transport because ROS 2 actions are
built from services plus topics. A stale goal/cancel/result frame must not be
accepted merely because it remains in an RMW queue.

## Implemented Code

- `ros2_ws/src/rmw_fleetqox_cpp/src/service_qos_probe.cpp`
  - creates one `rmw_service_t` and one `rmw_client_t` for
    `/fleetqox/service_qos_probe`;
  - sets request and response QoS lifespan to `5 ms`;
  - sends one request, waits past lifespan, and verifies
    `rmw_take_request(...)` returns `taken=false`;
  - sends one fresh request, takes it, sends a response, waits past lifespan,
    and verifies `rmw_take_response(...)` returns `taken=false`;
  - attempts `rmw_send_response(...)` with an unknown request id and verifies
    the RMW returns an error without sending a service frame;
  - calls `rmw_get_gid_for_client(...)` repeatedly, verifies the GID is stable
    and nonzero, verifies a second client has a distinct GID, and verifies the
    fresh request's `writer_guid` and sequence number exactly match the sending
    client;
  - verifies `rmw_service_server_is_available(...)` accepts a matching server,
    rejects a same-name/different-type server, and rejects a same-type server
    whose best-effort response publisher cannot satisfy a reliable client;
  - sends requests anyway for both mismatch cases and verifies neither request
    reaches the service queue, so matching is enforced on the data plane as
    well as the discovery API;
  - verifies `rmw_fleetqox_cpp_service_expired_frames_dropped()` increases by
    at least `2`.
- `scripts/run_rmw_docker_service_qos_probe.py`
  - builds `fleetrmw_interfaces` and `rmw_fleetqox_cpp` inside
    `ros:jazzy-ros-base`;
  - runs `fleetrmw_service_qos_probe`;
  - writes a JSON summary under `results_rmw_socket/`.
- `ros2_ws/src/rmw_fleetqox_cpp/src/rmw_stubs.cpp`
  - now clears and skips expired service frames while draining request and
    response queues, matching the existing pub/sub `lifespan` drop behavior.
  - returns the client's deterministic endpoint GID from
    `rmw_get_gid_for_client(...)`, rather than deriving identity from the client
    handle's process-local pointer value.
- `ros2_ws/src/rmw_fleetqox_cpp/src/rmw_graph.cpp`
  - stores service/client QoS in local and leased remote graph endpoints;
  - requires service name, exact type, and compatible request/response QoS for
    availability, and updates cached service QoS on remote renewal.
- `ros2_ws/src/rmw_fleetqox_cpp/src/rmw_stubs.cpp`
  - accepts a request frame only when its client endpoint ID is present in the
    local/remote graph with the exact service type and compatible two-way QoS;
  - accepts a response frame only when its addressed client, service name, and
    type all agree.

## Bug Fixed

The probes exposed two real ABI/path bugs. First, expired request/response
frames were counted as dropped, but the frame object was still deserialized and
returned to the caller. The fixed queue loops reset the frame and continue
after a freshness drop, so only a non-expired frame can be delivered.
Second, `rmw_get_gid_for_client(...)` returned a pointer-derived value while
`rmw_take_request(...)` constructed `writer_guid` from the endpoint ID. Both
APIs now expose the same deterministic endpoint identity.
Third, service availability previously counted every same-name server even if
its type or QoS could not match the client. Availability now evaluates the
actual endpoint descriptors in both local and leased remote graph caches.
Fourth, availability and destroy calls previously accepted any FleetRMW node.
Service/client data now records the exact creator node; a wrong-owner query or
destroy returns `RMW_RET_INVALID_ARGUMENT`, leaves the entity intact, and the
probe subsequently completes the normal request/response and cleanup path.

## Evidence

Package-level regression:

```bash
python3 -m unittest tests.test_rmw_fleetqox_cpp_package
```

Remote `udy` result:

```text
Ran 9 tests in 5.138s
OK
```

Docker ROS Jazzy probe:

```bash
python3 -m scripts.run_rmw_docker_service_qos_probe \
  --json \
  --summary-json results_rmw_socket/docker_rmw_service_qos_probe_codex_check_summary.json
```

Remote `udy` result:

```json
{
  "status": "ok",
  "probe": {
    "status": "ok",
    "lifespan_ns": 5000000,
    "stale_request_frame_received": true,
    "stale_request_taken": false,
    "fresh_request_taken": true,
    "stale_response_frame_received": true,
    "stale_response_taken": false,
    "unknown_response_error": true,
    "unknown_response_sent_delta": 0,
    "client_gid_stable": true,
    "client_gids_distinct": true,
    "client_gid_nonzero": true,
    "request_writer_gid_matches_client": true,
    "request_sequence_matches": true,
    "service_availability_matching_ok": true,
    "service_availability_type_filter_ok": true,
    "service_availability_qos_filter_ok": true,
    "service_request_type_filter_ok": true,
    "service_request_qos_filter_ok": true,
    "expired_frames_dropped_delta": 2,
    "cleanup_ok": true
  }
}
```

## Remaining Gap

This closes stale request/response delivery for the current SetBool service
path. C-level no-response and malformed-response handling is covered in
`docs/RMW_SERVICE_ERROR_V1.md`, and the first ROS CLI timeout smoke is covered in
`docs/RMW_SERVICE_TIMEOUT_V1.md`. The service/action work is not complete yet.
Remaining service work:

- cancellation/error propagation through caller-visible APIs;
- richer service QoS interaction beyond lifespan freshness and discovery-time
  type/QoS compatibility;
- action transport built on top of the now-tested service and topic paths.

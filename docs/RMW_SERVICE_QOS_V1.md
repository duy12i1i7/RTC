# RMW Service QoS V1

## Purpose

This milestone adds deterministic service request/response freshness coverage to
`rmw_fleetqox_cpp`. The previous service evidence proved successful
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

## Bug Fixed

The first probe run exposed a real service queue bug: expired request/response
frames were counted as dropped, but the frame object was still deserialized and
returned to the caller. The fixed queue loops reset the frame and continue
after a freshness drop, so only a non-expired frame can be delivered.

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
- richer service QoS interaction beyond lifespan freshness;
- action transport built on top of the now-tested service and topic paths.

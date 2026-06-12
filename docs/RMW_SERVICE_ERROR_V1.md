# RMW Service Error V1

## Purpose

This milestone adds deterministic C-level service error coverage to
`rmw_fleetqox_cpp`. The previous service probes covered successful SetBool RPCs,
router forwarding, and stale request/response freshness. This slice verifies
that the RMW does not fabricate responses when none exist and does not deliver a
malformed response payload to application code.

This is still below the ROS CLI timeout surface. It locks the RMW queue behavior
that later `rcl`, `rclpy`, and action clients must rely on.

## Implemented Code

- `ros2_ws/src/rmw_fleetqox_cpp/src/service_error_probe.cpp`
  - creates one service/client pair for `/fleetqox/service_error_probe`;
  - verifies `rmw_take_response(...)` returns `RMW_RET_OK` with `taken=false`
    when no response exists;
  - injects a routed `fleetrmw.service_frame.v1` response with malformed
    serialized payload bytes;
  - verifies `rmw_take_response(...)` returns `RMW_RET_UNSUPPORTED` with
    `taken=false`, then verifies the malformed frame was popped and a later take
    still reports `taken=false`;
  - injects a non-FleetRMW service frame string and verifies it is rejected and
    does not create a client-visible response.
- `ros2_ws/src/rmw_fleetqox_cpp/src/rmw_stubs.cpp`
  - exposes probe-only endpoint-id helpers for live service/client handles so
    tests can target the actual internal route without guessing endpoint names.
- `scripts/run_rmw_docker_service_error_probe.py`
  - builds `fleetrmw_interfaces` and `rmw_fleetqox_cpp` inside
    `ros:jazzy-ros-base`;
  - runs `fleetrmw_service_error_probe`;
  - writes a JSON summary under `results_rmw_socket/`.

## Evidence

Package-level regression:

```bash
python3 -m unittest tests.test_rmw_fleetqox_cpp_package
```

Remote `udy` result:

```text
Ran 10 tests in 7.128s
OK
```

Full unit regression:

```bash
python3 -m unittest discover tests
```

Remote `udy` result:

```text
Ran 414 tests in 9.543s
OK
```

Docker ROS Jazzy probe:

```bash
python3 -m scripts.run_rmw_docker_service_error_probe \
  --json \
  --summary-json results_rmw_socket/docker_rmw_service_error_probe_codex_check_summary.json
```

Remote `udy` result:

```json
{
  "status": "ok",
  "probe": {
    "status": "ok",
    "empty_response_taken": false,
    "malformed_frame_handled": true,
    "malformed_response_error": true,
    "malformed_response_taken": false,
    "post_malformed_response_taken": false,
    "invalid_frame_rejected": true,
    "after_invalid_response_taken": false,
    "cleanup_ok": true
  },
  "probe_returncode": 0,
  "docker_returncode": 0,
  "probe_stderr": "",
  "docker_stderr": ""
}
```

## Remaining Gap

This closes the C-level no-response and malformed-response delivery semantics.
The first ROS CLI timeout smoke is covered separately in
`docs/RMW_SERVICE_TIMEOUT_V1.md`. Remaining service work:

- cancellation/error propagation through `rcl` and action clients;
- richer service QoS interaction beyond lifespan freshness.

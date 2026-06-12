# RMW Service Timeout V1

## Purpose

This milestone adds the first caller-visible ROS CLI service timeout smoke for
`rmw_fleetqox_cpp`. The lower-level service probes already prove successful
request/response delivery, stale-frame drops, no-response `taken=false`, and
malformed-response rejection. This slice verifies that a real `ros2 service call`
can make a request through FleetRMW and time out without receiving a fabricated
response when the service intentionally delays its reply.

## Implemented Code

- `ros2_ws/src/rmw_fleetqox_cpp/src/rcl_service_node.cpp`
  - adds `--response-delay-ms`;
  - delays after `rcl_take_request(...)` and before `rcl_send_response(...)`;
  - records `response_delay_ms` in the node JSON summary.
- `scripts/run_rmw_docker_ros2_service_timeout_probe.py`
  - builds `fleetrmw_interfaces` and `rmw_fleetqox_cpp` inside
    `ros:jazzy-ros-base`;
  - starts `fleetrmw_rcl_service_node` with a delayed response;
  - runs `ros2 service call` under a shorter shell `timeout`;
  - verifies the server saw the request, the client did not print a success
    response, and the service-call process returned timeout code `124`.

## Evidence

Package-level regression:

```bash
python3 -m unittest tests.test_rmw_fleetqox_cpp_package
```

Remote `udy` result:

```text
Ran 10 tests in 6.805s
OK
```

Full unit regression:

```bash
python3 -m unittest discover tests
```

Remote `udy` result:

```text
Ran 414 tests in 9.419s
OK
```

Docker ROS Jazzy probe:

```bash
python3 -m scripts.run_rmw_docker_ros2_service_timeout_probe \
  --json \
  --summary-json results_rmw_socket/docker_ros2_service_timeout_probe_codex_check_summary.json
```

Remote `udy` result:

```json
{
  "status": "ok",
  "timed_out": true,
  "service_call_returncode": 124,
  "server_saw_request": true,
  "response_found": false,
  "response_delay_ms": 3500,
  "call_timeout": 2.0,
  "service_node": {
    "status": "ok",
    "request_count": 1,
    "response_delay_ms": 3500
  }
}
```

The CLI process writes a cleanup warning on SIGTERM because the shell `timeout`
kills the waiting `ros2 service call`. The runner records that stderr and still
requires the server-side evidence above.

## Router-Mediated Evidence

`run_rmw_docker_router_ros2_service_timeout_probe.py` extends the same caller
semantics across a real FleetRMW router and separate service/client
containers. The latest run passes: the CLI returns timeout code `124` after
`2 s`, the server records one request and delays its response by `3500 ms`, no
response is printed by the caller, and the router records and forwards both
service frames (`2/2`).

## Remaining Gap

This closes ROS CLI-visible timeout behavior both locally and through the
router. ROS 2 services do not define a standard cancellation API; cancellation
belongs to actions and is covered by the action probes. Remaining service work:

- richer service QoS interaction beyond lifespan freshness;
- explicit caller-visible malformed-response diagnostics beyond timeout.

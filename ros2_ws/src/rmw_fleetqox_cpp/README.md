# rmw_fleetqox_cpp

`rmw_fleetqox_cpp` is the ROS 2 Jazzy RMW package for FleetRMW. It preserves
the ROS 2 client-library boundary while using FleetRMW's non-DDS data plane and
FleetQoX control decisions.

This package is an advanced research prototype, not a production RMW. The
installed [`capabilities.json`](capabilities.json) is the normative,
machine-readable claim boundary and deliberately reports
`production_ready=false`.

## Implemented surface

The package currently includes real, scoped implementations of:

- context, node, graph, guard-condition, and wait-set lifecycle;
- typed and serialized publish/take with ROSIDL introspection C/C++;
- local and remote graph discovery and endpoint metadata;
- QoS matching, queues, deadlines, liveliness, and event wait/take/callbacks;
- services and the ROS 2 action protocol built over service/topic primitives;
- dynamic-message, content-filter, loan, allocation-scratch,
  `take_sequence`, and bounded all-acknowledged slices;
- UDP, POSIX shared memory, hybrid routing, fragment reliability, ACK/NACK,
  selective repair, admission, and telemetry;
- FleetQoX path, repair, priority, budget, and outcome control inputs;
- QUIC/mTLS gateway and failover research paths.

Claims remain deliberately narrower than the code surface. In particular,
full DDS-equivalent semantics, complete large-fleet reliability, production
certificate/cluster operations, zero-copy, and production readiness are not
claimed.

## Build

Use a ROS 2 Jazzy environment from the repository root:

```bash
source /opt/ros/jazzy/setup.bash
colcon build \
  --base-paths ros2_ws/src \
  --packages-select fleetrmw_interfaces rmw_fleetqox_cpp
source install/setup.bash
```

Select the implementation with:

```bash
export RMW_IMPLEMENTATION=rmw_fleetqox_cpp
```

For a pinned build/test environment, use
[`external/rmw-netem/Dockerfile`](../../../external/rmw-netem/Dockerfile).

## Runtime configuration

The most important configuration families are:

- `FLEETQOX_RMW_BIND` and `FLEETQOX_RMW_PEERS` for UDP endpoints;
- `FLEETQOX_RMW_LOCAL_TRANSPORT`, `FLEETQOX_RMW_SHM_NAME`, and
  `FLEETQOX_RMW_SHM_FALLBACK_UDP` for local/hybrid delivery;
- `FLEETQOX_RMW_FLEET_PATH_PLAN*` and
  `FLEETQOX_RMW_REPAIR_PATH_PLAN*` for controller-selected paths;
- `FLEETQOX_RMW_REPAIR_*` for bounded repair policy;
- `FLEETQOX_RMW_QUIC_*` for the experimental QUIC gateway;
- `FLEETQOX_PROBE_PAYLOAD_BYTES` and `FLEETQOX_PROBE_ITERATIONS` for
  large-string memory-safety probing.

The runners under [`scripts/`](../../../scripts) are the executable reference
for exact combinations. Avoid treating environment-variable presence as proof
that the corresponding broad production claim is complete.

## Verification

Run repository contract tests:

```bash
python3 -m unittest discover -s tests
```

Transport, ABI, security, and concurrency changes must also pass the relevant
Docker probes. Current priority gates are selective fragment repair,
per-frame/reader repair fairness, callback teardown, large-string ASan/UBSan,
and multi-seed 16/32-robot netem matrices.

## Project documentation

The root [`README.md`](../../../README.md) gives the project goal, current
progress, remaining work, and estimates. Detailed material is consolidated in:

- [`docs/ARCHITECTURE.md`](../../../docs/ARCHITECTURE.md);
- [`docs/RMW_MINIMAL_BOUNDARY_V1.md`](../../../docs/RMW_MINIMAL_BOUNDARY_V1.md);
- [`docs/INTEGRATION_AND_VALIDATION.md`](../../../docs/INTEGRATION_AND_VALIDATION.md);
- [`docs/EXPERIMENTAL_RESULTS_V1.md`](../../../docs/EXPERIMENTAL_RESULTS_V1.md);
- [`docs/STATUS_AND_ROADMAP.md`](../../../docs/STATUS_AND_ROADMAP.md);
- [`docs/DEVELOPMENT.md`](../../../docs/DEVELOPMENT.md).

Protocol-specific contracts remain in `docs/`; benchmark output belongs in
ignored `results_*`/`traces_*` directories or in an immutable release bundle.

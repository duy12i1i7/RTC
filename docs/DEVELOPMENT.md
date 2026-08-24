# Development and Reproducibility

## Repository policy

Tracked files are source, configuration, specifications, tests, and runners.
Generated artifacts are deliberately ignored:

- `build/`, `install/`, `log/`;
- `.tmp_*` build/install/log trees;
- `results_*` and `traces_*`;
- Python and pytest caches;
- local virtual environments and OS metadata.

Do not commit generated benchmark output. A canonical release may publish an
external immutable evidence bundle referenced by version and checksum.

## Python tests

```bash
python3 -m unittest discover -s tests
```

These tests cover algorithms, contracts, schemas, runner composition, report
logic, and many source/ABI boundaries. They do not replace a ROS 2/Docker run.
Tests that inspect canonical Docker evidence use explicit artifact-presence
guards. They skip in a clean checkout and execute after the corresponding
ignored `results_*` bundle has been regenerated or restored.

## ROS 2 build

Use ROS 2 Jazzy:

```bash
source /opt/ros/jazzy/setup.bash
colcon build \
  --base-paths ros2_ws/src \
  --packages-select fleetrmw_interfaces rmw_fleetqox_cpp
```

Then:

```bash
source install/setup.bash
export RMW_IMPLEMENTATION=rmw_fleetqox_cpp
```

## Docker image

```bash
docker build \
  -t localhost/fleetrmw/rmw-netem:jazzy \
  -f external/rmw-netem/Dockerfile .
```

Docker/netem gates may require `NET_ADMIN` inside a container. The runners
create isolated networks and should clean them up even after a failed process.

## Representative gates

```bash
python3 scripts/run_rmw_docker_selective_fragment_repair_probe.py
python3 scripts/run_rmw_docker_fragment_nack_fairness_probe.py
python3 scripts/run_rmw_docker_fragment_repair_round_robin_probe.py
python3 scripts/run_rmw_docker_callback_teardown_probe.py --iterations 5
python3 scripts/run_same_hop_rmw_comparison.py --help
python3 scripts/generate_unified_benchmark_report.py --help
```

## Sanitizers

Memory safety is a release blocker. Build the RMW with at least:

```text
-fsanitize=address -fno-omit-frame-pointer
-fsanitize=undefined
```

The typed `std_msgs/String` probe accepts:

```text
FLEETQOX_PROBE_PAYLOAD_BYTES
FLEETQOX_PROBE_ITERATIONS
```

Use it for repeated large-string publish/take/fini testing. A sanitizer run is
valid only when the instrumented library and executable are actually loaded and
the sanitizer runtime is active.

## Capability discipline

When adding a capability:

1. Implement the real behavior.
2. Add a deterministic unit/contract test.
3. Add a Docker/netem or integration probe when the claim crosses a process or
   network boundary.
4. Record structured telemetry and failure reasons.
5. Update `capabilities.json` with the narrowest justified claim.
6. Update the root README/status only after the evidence passes.

Never turn a partial or failed result into a broad true claim.

## Benchmark discipline

- Pin image and dependency versions.
- Record seed, profile, topology, payload, offered load, and exact arguments.
- Require clean process return codes.
- Keep failed rows; mark them failed rather than silently dropping them.
- Use multi-seed statistics for comparative claims.
- Separate deterministic contract gates from stochastic performance evidence.
- Compare the same application middle whenever claiming RMW differences.

## Cleaning the workspace

The following paths are disposable and can be regenerated:

```text
.pytest_cache/
__pycache__/
.tmp_*/
build/
install/
log/
results_*/
traces_*/
```

Before committing, run:

```bash
git status --short
git diff --check
python3 -m unittest discover -s tests
```

Docker gates must also be rerun when C++ transport, ABI, security, or runner
behavior changes.

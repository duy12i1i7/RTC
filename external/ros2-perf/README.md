# ROS 2 performance_test Harness

This harness builds Apex.AI `performance_test` with the ROS 2 plugin on top of
ROS 2 Jazzy. It is the first concrete T1 runner target.

The official `performance_test` documentation describes `perf_test`, ROS 2
plugin builds with `-DPERFORMANCE_TEST_PLUGIN=ROS2`, the ROS 2 executor
communication plugins, and CSV/JSON logging through `--logfile`.

## Build

```bash
docker compose -f external/ros2-perf/docker-compose.yml build
```

## Print Command Plan

```bash
T1_ARGS="--plan-commands" \
docker compose -f external/ros2-perf/docker-compose.yml run --rm ros2-perf
```

## Run Smoke Benchmark

```bash
docker compose -f external/ros2-perf/docker-compose.yml run --rm ros2-perf
```

The default runs only `small_messages_many_endpoints` and writes:

```text
results_t1/metrics.jsonl
```

Run all T1 scenarios:

```bash
T1_ARGS="--run --output results_t1/metrics.jsonl" \
docker compose -f external/ros2-perf/docker-compose.yml run --rm ros2-perf
```

## Run Manually Inside Container

```bash
docker compose -f external/ros2-perf/docker-compose.yml run --rm ros2-perf bash
source /opt/ros/jazzy/setup.bash
source /opt/performance_test_ws/install/setup.bash
python3 -m scripts.run_t1_ros2_perf --plan-commands
```

Then run selected `perf_test` commands from the plan.

## Notes

- `rmw_fastrtps_cpp` is available in the base ROS image.
- `rmw_cyclonedds_cpp` is installed explicitly.
- `rmw_zenoh_cpp` is attempted but may depend on the package availability in
  the active ROS apt snapshot.
- Use host networking for discovery/transport tests. For isolated tests, create
  explicit Docker networks and add `tc netem` at the container interface.

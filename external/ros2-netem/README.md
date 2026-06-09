# ROS 2 / performance_test over Docker netem

This is the T2E-ROS harness. It runs real ROS 2 `performance_test` traffic in
two containers and applies `tc netem` to the publisher container.

```text
subscriber container
  ros2 run performance_test perf_test --num-sub-threads 1 --num-pub-threads 0 --logfile ...

publisher container
  tc netem delay/loss/rate
  ros2 run performance_test perf_test --num-sub-threads 0 --num-pub-threads 1

zenoh-router container, only for rmw_zenoh_cpp
  ros2 run rmw_zenoh_cpp rmw_zenohd
```

## Plan

```bash
python3 -m scripts.run_t2e_ros2_netem --dry-run
```

## Run

```bash
python3 -m scripts.run_t2e_ros2_netem \
  --scenario wifi_loss_jitter \
  --rmw rmw_fastrtps_cpp \
  --run --analyze
```

Matrix baseline example:

```bash
python3 -m scripts.run_t2e_ros2_netem \
  --all-rmws \
  --components control,state \
  --repeat 3 \
  --runtime-s 30 \
  --run-id baseline_v1 \
  --run --analyze
```

The runner writes subscriber logs, parsed JSONL metrics, and summary rankings
under `results_t2e_ros2/`.

Generate Markdown/CSV reports:

```bash
python3 -m scripts.report_t2e_results \
  --metrics results_t2e_ros2/baseline_wifi_v1_metrics.jsonl \
  --summary results_t2e_ros2/baseline_wifi_v1_summary.json \
  --markdown results_t2e_ros2/baseline_wifi_v1_report.md \
  --csv results_t2e_ros2/baseline_wifi_v1_report.csv
```

`rmw_zenoh_cpp` defaults to `zenoh_router` topology. The runner adds
`docker-compose.zenoh.yml`, starts `rmw_zenohd`, and sets
`ZENOH_SESSION_CONFIG_URI=/work/external/ros2-netem/zenoh/session-router.json5`
for the publisher and subscriber. That session config uses Zenoh `client` mode
so both endpoints communicate through the router container.

Peer-mode debugging is still available:

```bash
python3 -m scripts.run_t2e_ros2_netem \
  --rmw rmw_zenoh_cpp \
  --zenoh-topology peer \
  --run --analyze
```

## Notes

- This requires Docker daemon and container `NET_ADMIN`.
- Metadata values passed through `APEX_PERFORMANCE_TEST` are kept string-only;
  current `performance_test` builds can crash on null or numeric metadata.
- The current compose file uses a Docker bridge network, not host networking,
  so multicast behavior may differ from a physical LAN.
- Use this as the first real ROS 2/netem integration; later variants should add
  explicit Discovery Server, static peers, Zenoh router, and multicast-blocked
  topologies.

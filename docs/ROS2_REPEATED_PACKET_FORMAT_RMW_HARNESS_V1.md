# ROS 2 Repeated Packet-Format/RMW Harness V1

## Purpose

`ROS2_PACKET_FORMAT_RMW_MATRIX_V1` proved that both packet formats can run
across Fast DDS, CycloneDDS, and Zenoh RMW once.  This milestone adds the
missing repeated-run harness so the same comparison can be expanded across
publisher workload seeds and named network profiles.

The point is to avoid treating one Docker/netem realization as an algorithmic
claim.  FleetRMW now has a ROS-backed path for collecting repeated evidence
before moving the frame boundary closer to `rmw_fleetrmw_cpp`.

## What Changed

The live bridge runner now supports:

- `--seeds`, a comma-separated list of deterministic publisher workload seeds;
- `--profile`, using the existing named netem profiles: `lan`, `wifi`, `wan`,
  and `roaming`;
- repeated scenario naming such as
  `scenario_wifi_seed_7_data_frame_rmw_fastrtps_cpp`;
- seed propagation into the ROS 2 test publisher through `ROS2_TEST_SEED`;
- repeated summary JSON and Markdown output grouped by `packet_format/RMW`;
- repeated summaries that only aggregate successful `status=ran` records with
  real analyzer metrics, while failed or missing-tool records remain visible in
  status counts for debugging;
- profile-specific repeated summaries using the same confidence-interval and
  Pareto reporting code as the sidecar Docker/netem harness.

The ROS 2 publisher now uses the seed to choose a deterministic phase and small
speed offset for the generated `cmd_vel`, odometry, scan, and compressed image
payload sequence.

## Plan Command

Plan a two-seed Wi-Fi matrix without running Docker:

```bash
python3 -m scripts.run_ros2_docker_live_bridge \
  --all-rmws \
  --packet-format-matrix \
  --seeds 7,13 \
  --profile wifi \
  --scenario ros2_live_bridge_t3_repeated_packet_v1
```

This expands to:

```text
2 seeds x 1 profile x 2 packet formats x 3 RMWs = 12 live-bridge records
```

## Full Run Command

```bash
python3 -m scripts.run_ros2_docker_live_bridge \
  --run \
  --analyze \
  --all-rmws \
  --packet-format-matrix \
  --seeds 7,13,29 \
  --profile wifi \
  --scenario ros2_live_bridge_t3_repeated_packet_wifi_3seed_v1 \
  --policy fleetqox_semantic_contract_adaptive \
  --bridge-config experiments/ros2_live_bridge_tb4_typed_projection_v1.json \
  --seconds 2 \
  --rate-hz 20 \
  --bridge-max-batches 20 \
  --quality-gate-identity-mode wrapper \
  --quality-message-mode typed \
  --projection-quality-message-mode typed \
  --projection-quality-delivery-mode wrapper \
  --projection-quality-payload-mode compact \
  --repeated-summary-json results_ros2_live_bridge/ros2_live_bridge_t3_repeated_packet_wifi_3seed_v1_summary.json \
  --repeated-markdown results_ros2_live_bridge/ros2_live_bridge_t3_repeated_packet_wifi_3seed_v1_report.md
```

Additional `--profile wan` or `--profile roaming` options can be appended to
turn the run into a multi-profile matrix.

## Smoke Result

The first live repeated smoke intentionally used only Fast DDS, one Wi-Fi seed,
and both packet formats.  Its purpose was to validate the harness and report
path.

```text
scenario: ros2_live_bridge_t3_repeated_packet_smoke_v1
profile: wifi
seed: 7
rmw: rmw_fastrtps_cpp
status_counts: 2 ran
```

| packet-format/RMW | runs | rx | loss | control delivery | p95 latency | deadline miss |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| `event_json/rmw_fastrtps_cpp` | 1 | 80.0 | 0.0000 | 1.0000 | 47.49 ms | 0.0000 |
| `data_frame/rmw_fastrtps_cpp` | 1 | 74.0 | 0.0263 | 1.0000 | 42.04 ms | 0.0000 |

Artifacts:

- `results_ros2_live_bridge/ros2_live_bridge_t3_repeated_packet_smoke_v1_summary.json`
- `results_ros2_live_bridge/ros2_live_bridge_t3_repeated_packet_smoke_v1_report.md`

## Full Wi-Fi Matrix Result

The first full Wi-Fi matrix then ran all combinations of three workload seeds,
two packet formats, and three RMW implementations:

```text
scenario: ros2_live_bridge_t3_repeated_packet_wifi_3seed_v1
profile: wifi
seeds: 7, 13, 29
statuses: 18 ran / 18 planned
invalid egress packets: 0 in all 18 runs
pareto frontier: data_frame/rmw_zenoh_cpp
```

| packet-format/RMW | runs | utility | ctrl delivery | loss | p95 ms | rx | pareto |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| `data_frame/rmw_zenoh_cpp` | 3 | 458.2 +/- 6.05 | 1.0000 +/- 0.0000 | 0.0173 +/- 0.0224 | 38.27 +/- 11.54 | 75.33 +/- 1.31 | yes |
| `event_json/rmw_cyclonedds_cpp` | 3 | 456.8 +/- 24.69 | 0.9482 +/- 0.0596 | 0.0176 +/- 0.0093 | 62.69 +/- 2.74 | 75.33 +/- 3.97 | no |
| `data_frame/rmw_cyclonedds_cpp` | 3 | 455.6 +/- 13.86 | 0.9658 +/- 0.0336 | 0.0257 +/- 0.0252 | 56.69 +/- 3.10 | 75.33 +/- 2.36 | no |
| `data_frame/rmw_fastrtps_cpp` | 3 | 444.4 +/- 49.49 | 0.9833 +/- 0.0327 | 0.0308 +/- 0.0071 | 59.08 +/- 4.28 | 73.33 +/- 8.19 | no |
| `event_json/rmw_fastrtps_cpp` | 3 | 443.0 +/- 26.91 | 0.9658 +/- 0.0336 | 0.0351 +/- 0.0172 | 60.56 +/- 1.81 | 73.33 +/- 4.71 | no |
| `event_json/rmw_zenoh_cpp` | 3 | 430.8 +/- 14.77 | 0.9269 +/- 0.0373 | 0.0273 +/- 0.0010 | 53.47 +/- 5.56 | 71.33 +/- 2.61 | no |

Detailed interpretation is captured in
`docs/ROS2_REPEATED_PACKET_FORMAT_RMW_WIFI_3SEED_V1.md`.

## Full WAN Matrix Result

The same matrix then ran under the named WAN profile:

```text
scenario: ros2_live_bridge_t3_repeated_packet_wan_3seed_v1
profile: wan
seeds: 7, 13, 29
statuses: 18 ran / 18 planned
invalid egress packets: 0 in all 18 runs
pareto frontier:
  event_json/rmw_zenoh_cpp
  data_frame/rmw_zenoh_cpp
  event_json/rmw_fastrtps_cpp
  data_frame/rmw_cyclonedds_cpp
  event_json/rmw_cyclonedds_cpp
```

| packet-format/RMW | runs | utility | ctrl delivery | loss | p95 ms | rx | pareto |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| `event_json/rmw_zenoh_cpp` | 3 | 342.5 +/- 103.65 | 1.0000 +/- 0.0000 | 0.0365 +/- 0.0175 | 111.19 +/- 31.22 | 58.00 +/- 17.68 | yes |
| `data_frame/rmw_zenoh_cpp` | 3 | 318.8 +/- 41.61 | 0.9778 +/- 0.0436 | 0.0537 +/- 0.0261 | 115.65 +/- 50.34 | 54.33 +/- 7.28 | yes |
| `event_json/rmw_fastrtps_cpp` | 3 | 315.9 +/- 47.52 | 0.9778 +/- 0.0436 | 0.0472 +/- 0.0381 | 159.33 +/- 20.63 | 53.33 +/- 7.53 | yes |
| `data_frame/rmw_cyclonedds_cpp` | 3 | 284.6 +/- 25.79 | 1.0000 +/- 0.0000 | 0.0271 +/- 0.0363 | 131.51 +/- 44.57 | 48.33 +/- 3.97 | yes |
| `event_json/rmw_cyclonedds_cpp` | 3 | 276.9 +/- 100.60 | 1.0000 +/- 0.0000 | 0.0548 +/- 0.0229 | 125.05 +/- 22.83 | 47.67 +/- 16.95 | yes |
| `data_frame/rmw_fastrtps_cpp` | 3 | 269.4 +/- 49.28 | 1.0000 +/- 0.0000 | 0.0328 +/- 0.0186 | 132.74 +/- 45.91 | 46.33 +/- 8.79 | no |

Detailed interpretation is captured in
`docs/ROS2_REPEATED_PACKET_FORMAT_RMW_WAN_3SEED_V1.md`.

## Full Roaming Matrix Result

The same matrix then ran under the named roaming stress profile:

```text
scenario: ros2_live_bridge_t3_repeated_packet_roaming_3seed_v1
profile: roaming
seeds: 7, 13, 29
statuses: 18 ran / 18 planned
invalid egress packets: 0 in all 18 runs
pareto frontier:
  event_json/rmw_zenoh_cpp
  data_frame/rmw_cyclonedds_cpp
  event_json/rmw_cyclonedds_cpp
  data_frame/rmw_fastrtps_cpp
  event_json/rmw_fastrtps_cpp
```

| packet-format/RMW | runs | utility | ctrl delivery | loss | p95 ms | rx | pareto |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| `event_json/rmw_zenoh_cpp` | 3 | 248.5 +/- 19.08 | 0.9667 +/- 0.0653 | 0.0645 +/- 0.0389 | 162.60 +/- 59.90 | 42.00 +/- 3.39 | yes |
| `data_frame/rmw_cyclonedds_cpp` | 3 | 242.8 +/- 90.76 | 0.9188 +/- 0.0944 | 0.0487 +/- 0.0168 | 199.81 +/- 17.02 | 41.67 +/- 14.73 | yes |
| `event_json/rmw_cyclonedds_cpp` | 3 | 242.2 +/- 60.99 | 1.0000 +/- 0.0000 | 0.0578 +/- 0.0495 | 169.44 +/- 52.04 | 41.33 +/- 9.89 | yes |
| `data_frame/rmw_fastrtps_cpp` | 3 | 160.6 +/- 93.57 | 0.8102 +/- 0.1409 | 0.0955 +/- 0.0324 | 217.62 +/- 15.05 | 27.33 +/- 16.10 | yes |
| `event_json/rmw_fastrtps_cpp` | 3 | 138.6 +/- 72.84 | 0.9630 +/- 0.0726 | 0.0554 +/- 0.0772 | 227.12 +/- 12.12 | 24.33 +/- 12.41 | yes |
| `data_frame/rmw_zenoh_cpp` | 3 | 240.0 +/- 75.66 | 0.9048 +/- 0.1867 | 0.0805 +/- 0.0611 | 158.59 +/- 71.73 | 41.00 +/- 12.75 | no |

Detailed interpretation is captured in
`docs/ROS2_REPEATED_PACKET_FORMAT_RMW_ROAMING_3SEED_V1.md`.

## Interpretation

The smoke result is harness evidence, not a packet-format performance result.
With only one seed and one RMW, it correctly marks the result as a smoke-test
signal.  The full Wi-Fi matrix is stronger: in the current three-seed evidence
set, `data_frame/rmw_zenoh_cpp` is the only non-dominated packet-format/RMW
combination.  The WAN matrix is more profile-sensitive: five combinations stay
on the Pareto frontier, with `event_json/rmw_zenoh_cpp` highest on utility and
`data_frame/rmw_cyclonedds_cpp` best on mean loss.
The roaming matrix keeps five combinations on the reporter's frontier but
drops `data_frame/rmw_zenoh_cpp` from that objective set, even though it has the
lowest reported mean p95 latency.

The important outcome is that repeated ROS 2 Docker T3 runs now produce:

- per-run packet-format/RMW metrics;
- profile annotation;
- confidence-interval-ready repeated summaries;
- Markdown reports with Pareto/frontier context;
- the same typed egress, lease, quality-gate, and source-identity checks used
  in the earlier one-shot matrix.

The completed Wi-Fi/WAN/roaming sequence shows that packet format and RMW are
runtime control decisions, not fixed migration switches.

If Docker or the ROS 2 logs are unavailable, the runner reports the failed
record statuses but does not write a repeated performance report.  This keeps
environment failures from appearing as all-zero algorithmic measurements.

## Verification

```text
python3 -m unittest discover -s tests
Ran 202 tests - OK

docker compose -f external/ros2-live-bridge/docker-compose.yml config --quiet
OK

docker compose -f external/ros2-live-bridge/docker-compose.yml \
  -f external/ros2-live-bridge/docker-compose.zenoh.yml config --quiet
OK
```

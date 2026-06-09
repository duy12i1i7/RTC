# ROS 2 Packet Format RMW Matrix V1

## Purpose

This milestone expands the packet-format comparison from one Fast DDS run to
the full Docker T3 RMW matrix:

```text
packet_format in {event_json, data_frame}
RMW in {Fast DDS, CycloneDDS, Zenoh RMW}
```

The objective is transition evidence for the FleetRMW data-plane boundary.  If
`fleetrmw.data_frame.v1` is going to replace sidecar event JSON, it must remain
decodable and identity-preserving across the RMWs that ROS 2 applications may
already use.

## Command

```bash
python3 -m scripts.run_ros2_docker_live_bridge \
  --run \
  --analyze \
  --all-rmws \
  --packet-format-matrix \
  --scenario ros2_live_bridge_t3_packet_format_rmw_matrix_v1 \
  --policy fleetqox_semantic_contract_adaptive \
  --bridge-config experiments/ros2_live_bridge_tb4_typed_projection_v1.json \
  --seconds 2 \
  --rate-hz 20 \
  --bridge-max-batches 20 \
  --delay-ms 20 \
  --jitter-ms 5 \
  --loss-percent 0.5 \
  --rate-mbit 20 \
  --quality-gate-identity-mode wrapper \
  --quality-message-mode typed \
  --projection-quality-message-mode typed \
  --projection-quality-delivery-mode wrapper \
  --projection-quality-payload-mode compact \
  --json
```

## Result

```text
scenario: ros2_live_bridge_t3_packet_format_rmw_matrix_v1
status_counts: 6 ran
```

| packet format | RMW | tx | rx | loss | control delivery | p95 latency | gate accept | contract match | source match |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| `event_json` | `rmw_fastrtps_cpp` | 68 | 67 | 0.0147 | 0.9412 | 59.04 ms | 35/35 | 35/35 | 35/35 |
| `event_json` | `rmw_cyclonedds_cpp` | 80 | 78 | 0.0250 | 0.9500 | 50.72 ms | 38/39 | 39/39 | 39/39 |
| `event_json` | `rmw_zenoh_cpp` | 77 | 77 | 0.0000 | 1.0000 | 32.60 ms | 38/38 | 38/38 | 38/38 |
| `data_frame` | `rmw_fastrtps_cpp` | 72 | 72 | 0.0000 | 1.0000 | 58.77 ms | 36/36 | 36/36 | 36/36 |
| `data_frame` | `rmw_cyclonedds_cpp` | 76 | 75 | 0.0132 | 0.9474 | 58.17 ms | 37/38 | 38/38 | 38/38 |
| `data_frame` | `rmw_zenoh_cpp` | 78 | 78 | 0.0000 | 1.0000 | 34.98 ms | 39/39 | 39/39 | 39/39 |

All six runs completed with `0` invalid egress packets.  The two
`drop_projection` cases above were quality-gate decisions, not decode failures;
their `contract_id` and `source_sample_id` still matched the sidecar decision
identity.

## Metadata Matrix

| packet format | RMW | sidecar packets | publisher_gid | sequence_number | source_timestamp_ns | received_timestamp_ns |
| --- | --- | ---: | ---: | ---: | ---: | ---: |
| `event_json` | `rmw_fastrtps_cpp` | 68 | 0 | 68 | 68 | 68 |
| `event_json` | `rmw_cyclonedds_cpp` | 80 | 0 | 0 | 80 | 80 |
| `event_json` | `rmw_zenoh_cpp` | 77 | 0 | 77 | 77 | 77 |
| `data_frame` | `rmw_fastrtps_cpp` | 72 | 0 | 72 | 72 | 72 |
| `data_frame` | `rmw_cyclonedds_cpp` | 76 | 0 | 0 | 76 | 76 |
| `data_frame` | `rmw_zenoh_cpp` | 78 | 0 | 78 | 78 | 78 |

The callback metadata pattern is consistent with earlier matrix runs:

- source and receive timestamps are present across all RMWs;
- Fast DDS and Zenoh RMW expose sequence numbers in this `rclpy` path;
- CycloneDDS does not expose sequence numbers here;
- publisher GID remains absent through the observed `rclpy` callback surface.

## Interpretation

The main result is not universal performance dominance.  This is a single
Docker/netem realization, and the tx/rx counts vary by RMW start timing and
discovery behavior.

The stronger result is architectural:

- `fleetrmw.data_frame.v1` is portable across the current Fast DDS,
  CycloneDDS, and Zenoh Docker T3 matrix;
- the same egress bridge can decode legacy JSON and data-frame packets;
- typed ROS egress and qualified wrapper delivery remain unchanged;
- quality-gate identity remains intact across both packet formats;
- packet format is now separated from RMW callback metadata availability.

That is enough evidence to move the project direction from "sidecar frame
codec" toward a minimal RMW-facing publish/take boundary.  The first repeated
Wi-Fi evidence identifies `data_frame/rmw_zenoh_cpp` as the non-dominated
operating point in `ROS2_REPEATED_PACKET_FORMAT_RMW_WIFI_3SEED_V1`.  The WAN
matrix in `ROS2_REPEATED_PACKET_FORMAT_RMW_WAN_3SEED_V1` changes the frontier:
`event_json/rmw_zenoh_cpp` has the highest mean utility, while
`data_frame/rmw_cyclonedds_cpp` has the lowest mean loss.  The next evaluation
step is a measured profile-aware/objective-aware selector before making general
latency or dominance claims.

`ROS2_REPEATED_PACKET_FORMAT_RMW_HARNESS_V1` adds that repeated-run harness and
validates it with a one-seed Fast DDS smoke plus three-seed Wi-Fi, WAN, and
roaming matrices.  In the roaming matrix,
`ROS2_REPEATED_PACKET_FORMAT_RMW_ROAMING_3SEED_V1`,
`event_json/rmw_zenoh_cpp` has the highest utility while
`data_frame/rmw_zenoh_cpp` has the lowest mean p95 latency but is not on the
reporter's current safety/utility Pareto frontier.

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

# ROS 2 RMW Data Frame Matrix V1

## Purpose

This milestone validates that `fleetrmw.data_frame.v1` can replace the legacy
sidecar JSON UDP payload in the live ROS 2 Docker T3 harness across multiple
RMW implementations.

The goal is narrower than a full RMW replacement: keep ROS 2 applications and
topics unchanged, but prove that the sidecar-to-egress data-plane object is now
a FleetRMW frame rather than a research log record.

## Command

```bash
python3 -m scripts.run_ros2_docker_live_bridge \
  --run \
  --analyze \
  --all-rmws \
  --packet-format data_frame \
  --scenario ros2_live_bridge_t3_data_frame_rmw_matrix_v1 \
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

The matrix covers:

- `rmw_fastrtps_cpp`;
- `rmw_cyclonedds_cpp`;
- `rmw_zenoh_cpp` with the in-compose Zenoh router.

## Result

```text
scenario: ros2_live_bridge_t3_data_frame_rmw_matrix_v1
packet_format: data_frame
status_counts: 3 ran
```

| RMW | tx | rx | loss | control delivery | p95 latency | gate accept | contract match | source match |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| `rmw_fastrtps_cpp` | 78 | 78 | 0.0000 | 1.0000 | 44.98 ms | 39/39 | 39/39 | 39/39 |
| `rmw_cyclonedds_cpp` | 73 | 72 | 0.0137 | 1.0000 | 37.50 ms | 36/36 | 36/36 | 36/36 |
| `rmw_zenoh_cpp` | 70 | 69 | 0.0143 | 1.0000 | 30.90 ms | 34/34 | 34/34 | 34/34 |

All three RMWs delivered frame-mode packets to egress with `0` invalid decoded
packets.  The quality gate accepted every qualified wrapper sample that reached
it, and every accepted gate decision matched the corresponding sidecar
`contract_id` and `source_sample_id`.

## Metadata Matrix

| RMW | sidecar packets | publisher_gid | sequence_number | source_timestamp_ns | received_timestamp_ns |
| --- | ---: | ---: | ---: | ---: | ---: |
| `rmw_fastrtps_cpp` | 78 | 0 | 78 | 78 | 78 |
| `rmw_cyclonedds_cpp` | 73 | 0 | 0 | 73 | 73 |
| `rmw_zenoh_cpp` | 70 | 0 | 70 | 70 | 70 |

This reproduces the earlier callback-metadata portability result under
frame-mode transport:

- timestamps remain portable across all three RMWs;
- sequence number remains absent for CycloneDDS in this `rclpy` path;
- publisher GID is still not exposed through the observed callback surface.

## Interpretation

This is the first evidence that `fleetrmw.data_frame.v1` is not just a local
codec.  It can carry the live sidecar packet path across ROS 2 RMW backends
while preserving:

- sidecar admission decisions;
- source and contract identity;
- typed qualified odometry/scan wrappers;
- control-intent delivery;
- latency metrics through the UDP trace receiver.

The remaining gap is no longer "can the frame path work in ROS 2 Docker T3?"
It can.  The next gap is to compare frame-mode versus legacy JSON mode under
the same repeated seeds/profiles, then move the frame boundary closer to a
minimal `rmw_fleetrmw_cpp` publish/take path.

`ROS2_PACKET_FORMAT_COMPARE_V1` starts that comparison on Fast DDS and confirms
that `event_json` and `data_frame` both preserve packet delivery, quality-gate
identity, and typed ROS-facing behavior in the current T3 harness.

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

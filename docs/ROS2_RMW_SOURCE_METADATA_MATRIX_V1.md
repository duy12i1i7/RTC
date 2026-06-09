# ROS 2 RMW Source Metadata Matrix V1

## Purpose

This milestone checks whether the current live ROS 2 bridge can obtain
portable source-sample identity material from `rclpy` callback metadata across
multiple RMW implementations.

The question is not only whether a topic can be received.  FleetRMW needs a
source identity path that can survive admission, transport shaping, wrapper
delivery, and projection-quality gates.  If the identity material changes by
RMW, the future `rmw_fleetrmw` design cannot rely on one DDS-specific field.

## Testbed

The Docker T3 live bridge now supports a metadata matrix runner:

```bash
python3 -m scripts.run_ros2_docker_live_bridge \
  --run \
  --analyze \
  --all-rmws \
  --scenario ros2_live_bridge_t3_rmw_metadata_v2 \
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

The default matrix currently covers:

- `rmw_fastrtps_cpp`;
- `rmw_cyclonedds_cpp`;
- `rmw_zenoh_cpp`.

Zenoh RMW requires an in-compose router, so the matrix adds
`external/ros2-live-bridge/docker-compose.zenoh.yml` when the selected RMW is
`rmw_zenoh_cpp`.

## Result

```text
scenario: ros2_live_bridge_t3_rmw_metadata_v2
```

| RMW | sidecar packets | records with metadata | publisher_gid | sequence_number | source_timestamp_ns | received_timestamp_ns | qualified gate | loss | control delivery | p95 latency |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| `rmw_fastrtps_cpp` | 76 | 76 | 0 | 76 | 76 | 76 | 38/38 accept | 0.0000 | 1.0000 | 68.22 ms |
| `rmw_cyclonedds_cpp` | 80 | 80 | 0 | 0 | 80 | 80 | 40/40 accept | 0.0125 | 0.9500 | 51.93 ms |
| `rmw_zenoh_cpp` | 73 | 73 | 0 | 73 | 73 | 73 | 36/36 accept | 0.0137 | 1.0000 | 59.76 ms |

Per-topic metadata was present on all emitted decision packets for each RMW.
The important portability result is field-level:

- `source_timestamp_ns` was available through all three RMWs;
- `received_timestamp_ns` was available through all three RMWs;
- `sequence_number` was available through Fast DDS and Zenoh RMW, but absent
  through CycloneDDS in this `rclpy` path;
- `publisher_gid` was absent through all three RMWs in this container setup.

## Interpretation

This result changes the source-identity contract from an assumption into a
measured constraint.

The current live bridge can derive robust `source_sample_id`s from:

1. explicit caller-provided `source_sample_id`;
2. semantic ROS payload metadata, especially `header.stamp` and `frame_id`;
3. RMW-facing callback metadata when present;
4. timestamp-based fallback when header and sequence metadata are unavailable;
5. generated `contract_id` as the final fallback.

It should not require `publisher_gid` from `rclpy`.  In this testbed, no tested
RMW exposed that field to the Python callback path.

It should not require `sequence_number` either.  CycloneDDS delivered callback
timestamps but no publication sequence number through the observed
`MessageInfo` surface.

The later `ros2_live_bridge_t3_data_frame_rmw_matrix_v1` run reproduced the
same metadata portability shape after replacing legacy sidecar JSON with
`fleetrmw.data_frame.v1` on the sidecar-to-egress path.

## Design Consequence For FleetRMW

For a sidecar bridge, source identity must be treated as opportunistic
metadata: preserve every field that exists, but keep the contract valid when
some fields are absent.

For a real `rmw_fleetrmw` implementation, source identity should be native
data-plane metadata, not inferred from `rclpy`:

- every publisher endpoint should have a FleetRMW publisher identity;
- every published sample should carry a monotonic source sequence number;
- source and receive timestamps should be explicit fields in the FleetRMW
  sample envelope;
- projection and admission IDs should remain separate from source sample IDs.

That makes the future RMW more deterministic than the current ROS 2 Python
callback bridge while preserving the same ROS programming model.

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

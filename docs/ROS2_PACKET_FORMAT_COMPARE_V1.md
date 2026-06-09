# ROS 2 Packet Format Compare V1

## Purpose

This milestone compares the legacy sidecar JSON UDP payload with the new
`fleetrmw.data_frame.v1` packet format inside the same Dockerized ROS 2 T3
harness.

The purpose is not to claim that the new frame is already faster in general.
The purpose is to prove that FleetRMW can switch the sidecar-to-egress data
plane from a research log record to a native middleware frame without changing
the ROS-facing application behavior, typed projections, qualified wrappers, or
quality-gate identity checks.

## Command

```bash
python3 -m scripts.run_ros2_docker_live_bridge \
  --run \
  --analyze \
  --packet-format-matrix \
  --scenario ros2_live_bridge_t3_packet_format_compare_v1 \
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

The runner expands `--packet-format-matrix` into:

- `event_json`, the previous padded sidecar event JSON packet;
- `data_frame`, the magic-prefixed `fleetrmw.data_frame.v1` packet.

## Result

```text
scenario: ros2_live_bridge_t3_packet_format_compare_v1
rmw: rmw_fastrtps_cpp
status_counts: 2 ran
```

| packet format | tx | rx | loss | control delivery | p95 latency | gate accept | contract match | source match |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| `event_json` | 80 | 80 | 0.0000 | 1.0000 | 50.02 ms | 40/40 | 40/40 | 40/40 |
| `data_frame` | 80 | 80 | 0.0000 | 1.0000 | 40.87 ms | 40/40 | 40/40 | 40/40 |

Both packet formats produced:

- `0` invalid egress packets;
- `201` monitored ROS 2 messages;
- `40/40` quality-gate accepts for qualified state/perception wrappers;
- complete decision-to-gate `contract_id` matches;
- complete decision-to-gate `source_sample_id` matches.

The one-run p95 latency was lower for `data_frame`, but this is only a smoke
signal.  The stronger conclusion is functional equivalence at the ROS-facing
boundary with the native frame already preserving every identity and quality
contract checked by the T3 harness.

## Metadata Matrix

| packet format | sidecar packets | publisher_gid | sequence_number | source_timestamp_ns | received_timestamp_ns |
| --- | ---: | ---: | ---: | ---: | ---: |
| `event_json` | 80 | 0 | 80 | 80 | 80 |
| `data_frame` | 80 | 0 | 80 | 80 | 80 |

The metadata result is intentionally identical for this Fast DDS comparison:
packet format is now separated from ROS callback metadata extraction.  That
separation matters for the RMW direction because FleetRMW can keep improving
the data-plane frame without depending on how each upstream RMW exposes
`rclpy` callback metadata.

## Interpretation

This closes the immediate transition risk for the frame codec:

- legacy JSON remains the default compatibility path;
- `fleetrmw.data_frame.v1` is opt-in and decodable by the same egress bridge;
- UDP trace metrics work for both formats because the frame carries
  `send_monotonic_ns`;
- typed ROS egress behavior is unchanged;
- qualified wrapper identity is unchanged;
- the runner can now generate packet-format comparison rows automatically.

`ROS2_PACKET_FORMAT_RMW_MATRIX_V1` extends this smoke to the Cartesian matrix:

```text
packet_format in {event_json, data_frame}
RMW in {Fast DDS, CycloneDDS, Zenoh RMW}
seed/profile in repeated Docker/netem runs
```

The RMW dimension now runs, and the repeated Wi-Fi/WAN evidence shows why the
matrix matters.  `ROS2_REPEATED_PACKET_FORMAT_RMW_WIFI_3SEED_V1` has a single
non-dominated point, `data_frame/rmw_zenoh_cpp`; in
`ROS2_REPEATED_PACKET_FORMAT_RMW_WAN_3SEED_V1`, five combinations remain on the
Pareto frontier.  `ROS2_REPEATED_PACKET_FORMAT_RMW_ROAMING_3SEED_V1` changes
the frontier again and shows that latency-sensitive and safety/utility
objective vectors may select different packet-format/RMW pairs.  The remaining
gap is a runtime selector before moving from a sidecar frame boundary to a
minimal `rmw_fleetrmw_cpp` publish/take prototype.

`ROS2_REPEATED_PACKET_FORMAT_RMW_HARNESS_V1` documents that repeated-run layer.

## Verification

```text
python3 -m unittest discover -s tests
Ran 202 tests - OK
```

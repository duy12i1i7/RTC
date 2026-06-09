# ROS 2 Repeated Packet-Format/RMW WAN 3-Seed V1

## Purpose

This run repeats the ROS-backed packet-format/RMW matrix under the named WAN
netem profile.  It is the direct follow-up to the Wi-Fi 3-seed matrix and tests
whether the `fleetrmw.data_frame.v1` result is stable when the network regime
changes from moderate wireless loss/jitter to a longer-delay, lower-capacity
WAN path.

The useful research question is not "which encoder is always fastest?"  It is
whether packet format, RMW implementation, semantic projection quality, and link
profile interact strongly enough that FleetRMW needs runtime
transport/representation selection.

## Command

```bash
python3 -m scripts.run_ros2_docker_live_bridge \
  --run \
  --analyze \
  --all-rmws \
  --packet-format-matrix \
  --seeds 7,13,29 \
  --profile wan \
  --scenario ros2_live_bridge_t3_repeated_packet_wan_3seed_v1 \
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
  --repeated-summary-json results_ros2_live_bridge/ros2_live_bridge_t3_repeated_packet_wan_3seed_v1_summary.json \
  --repeated-markdown results_ros2_live_bridge/ros2_live_bridge_t3_repeated_packet_wan_3seed_v1_report.md
```

Profile:

```text
wan: 90000 B/s capacity, 60 ms delay, 15 ms jitter, 1.5% loss, 10 mbit
```

## Results

```text
statuses: 18 ran / 18 planned
invalid egress packets: 0 in all 18 runs
grouping: packet_format/RMW
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

Artifacts:

- `results_ros2_live_bridge/ros2_live_bridge_t3_repeated_packet_wan_3seed_v1_summary.json`
- `results_ros2_live_bridge/ros2_live_bridge_t3_repeated_packet_wan_3seed_v1_report.md`
- `results_ros2_live_bridge/ros2_live_bridge_t3_repeated_packet_wan_3seed_v1_run.log`

## Interpretation

The WAN result is deliberately not a repeat of the Wi-Fi result.  In Wi-Fi,
`data_frame/rmw_zenoh_cpp` was the only non-dominated policy.  In WAN, five of
six combinations are non-dominated.  `event_json/rmw_zenoh_cpp` has the highest
mean utility, receive count, and low p95 latency, but
`data_frame/rmw_cyclonedds_cpp` has the lowest mean loss while keeping perfect
measured control delivery.  `data_frame/rmw_zenoh_cpp` remains on the frontier,
but it no longer dominates the comparison.

This is a stronger research signal than a simple packet-format benchmark.  It
shows that the data-plane boundary must remain measurable and selectable.  A
native FleetRMW frame is still required for source identity, timing, admission
contract, and QoX metadata, but the control plane should not assume one fixed
RMW/encoding pair for all profiles.

The high confidence intervals also matter.  WAN produces much larger
seed-to-seed variation than Wi-Fi, including per-branch receive counts ranging
from `31` to `76` packets with zero invalid decodes.  The bottleneck is not
frame parsing; it is profile-sensitive scheduling, projection validity, and
transport behavior under longer delay and tighter capacity.

## Follow-Up Evidence

The same matrix has now run under the `roaming` profile in
`docs/ROS2_REPEATED_PACKET_FORMAT_RMW_ROAMING_3SEED_V1.md`.  The frontier
changes again, so the next FleetRMW milestone should be a profile-aware
transport/representation selector that chooses among packet format, RMW/data
plane, semantic projection mode, and local control contract based on observed
QoS/QoE objectives.

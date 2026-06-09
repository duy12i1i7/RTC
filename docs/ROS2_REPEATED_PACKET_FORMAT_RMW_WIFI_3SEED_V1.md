# ROS 2 Repeated Packet-Format/RMW Wi-Fi 3-Seed V1

## Purpose

This run is the first full ROS-backed repeated packet-format/RMW matrix for the
FleetRMW data-plane transition.  It moves beyond the one-shot transition tests
by comparing both sidecar packet formats across Fast DDS, CycloneDDS, and Zenoh
RMW under the same named Wi-Fi netem profile and three deterministic publisher
workload seeds.

The goal is not to prove that one packet format universally dominates.  The
goal is to test whether the native `fleetrmw.data_frame.v1` path remains
portable and whether packet format, RMW, and wireless impairment interact enough
to justify treating transport selection as a FleetRMW control-plane decision.

## Command

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

Profile:

```text
wifi: 120000 B/s capacity, 20 ms delay, 5 ms jitter, 1% loss, 20 mbit
```

## Results

```text
statuses: 18 ran / 18 planned
invalid egress packets: 0 in all 18 runs
grouping: packet_format/RMW
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

Artifacts:

- `results_ros2_live_bridge/ros2_live_bridge_t3_repeated_packet_wifi_3seed_v1_summary.json`
- `results_ros2_live_bridge/ros2_live_bridge_t3_repeated_packet_wifi_3seed_v1_report.md`
- `results_ros2_live_bridge/ros2_live_bridge_t3_repeated_packet_wifi_3seed_v1_run.log`

## Interpretation

`data_frame/rmw_zenoh_cpp` is the only non-dominated policy in this evidence
set.  It has the highest mean semantic utility, perfect measured control
delivery, lowest mean p95 latency, and zero observed invalid frame decodes.
That is the strongest signal so far that the native FleetRMW frame path is more
than a log-format cleanup.

The result should still be read as a Wi-Fi-profile claim, not a universal
packet-format claim.  `event_json/rmw_cyclonedds_cpp` is close on utility and
loss, while `data_frame/rmw_cyclonedds_cpp` improves control delivery but has
higher measured loss.  This means the performance surface is a joint function
of packet format, RMW implementation, workload timing, and impairment profile.

For the FleetRMW research direction, the useful conclusion is sharper than
"switch JSON to binary."  The data plane should expose native source identity,
timing, contract, and QoX metadata in a frame that the fleet control plane can
reason about.  The RMW or sidecar boundary should then select transport and
representation by measured objective trade-offs, not by a fixed DDS QoS profile
or a fixed packet encoding.

## Follow-Up Evidence

The same matrix has now been repeated under WAN in
`ROS2_REPEATED_PACKET_FORMAT_RMW_WAN_3SEED_V1` and under roaming in
`ROS2_REPEATED_PACKET_FORMAT_RMW_ROAMING_3SEED_V1`.  The frontier changes by
profile in both follow-ups.  The stronger research contribution is now
profile-aware transport/representation selection inside the FleetRMW control
plane before moving the frame boundary closer to a minimal `rmw_fleetrmw_cpp`
prototype.

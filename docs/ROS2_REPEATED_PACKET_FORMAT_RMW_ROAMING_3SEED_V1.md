# ROS 2 Repeated Packet-Format/RMW Roaming 3-Seed V1

## Purpose

This run repeats the ROS-backed packet-format/RMW matrix under the named
`roaming` netem profile.  It completes the first Wi-Fi -> WAN -> roaming sweep
for the live ROS 2 sidecar bridge, using the same workload seeds, typed
projection config, packet formats, and RMW implementations.

The useful question is whether a fixed packet format or RMW can survive a
handoff-like capacity drop.  The result says no: the frame is portable, but the
best operating point is profile-sensitive and objective-sensitive.

## Command

```bash
python3 -m scripts.run_ros2_docker_live_bridge \
  --run \
  --analyze \
  --all-rmws \
  --packet-format-matrix \
  --seeds 7,13,29 \
  --profile roaming \
  --scenario ros2_live_bridge_t3_repeated_packet_roaming_3seed_v1 \
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
  --repeated-summary-json results_ros2_live_bridge/ros2_live_bridge_t3_repeated_packet_roaming_3seed_v1_summary.json \
  --repeated-markdown results_ros2_live_bridge/ros2_live_bridge_t3_repeated_packet_roaming_3seed_v1_report.md
```

Profile:

```text
roaming: 70000 B/s capacity, 80 ms delay, 25 ms jitter, 3% loss, 5 mbit
```

## Results

```text
statuses: 18 ran / 18 planned
invalid egress packets: 0 in all 18 runs
grouping: packet_format/RMW
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

Artifacts:

- `results_ros2_live_bridge/ros2_live_bridge_t3_repeated_packet_roaming_3seed_v1_summary.json`
- `results_ros2_live_bridge/ros2_live_bridge_t3_repeated_packet_roaming_3seed_v1_report.md`
- `results_ros2_live_bridge/ros2_live_bridge_t3_repeated_packet_roaming_3seed_v1_run.log`

## Interpretation

The roaming profile is harsher than WAN for the current live bridge.  Mean
utility drops from WAN's `342.5` best result to `248.5`; mean p95 latency rises
from `111.19 ms` to `162.60 ms` for the highest-utility Zenoh path; and some
Fast DDS runs receive only `11-12` packets.  Even so, all `18` runs decode and
egress without invalid packets, so the frame boundary itself is not the failure
point.

The repeated profile sequence now has three different frontiers:

- Wi-Fi: one non-dominated point, `data_frame/rmw_zenoh_cpp`;
- WAN: five non-dominated points, with `event_json/rmw_zenoh_cpp` highest on
  utility and `data_frame/rmw_cyclonedds_cpp` lowest on loss;
- Roaming: five non-dominated points again, but `data_frame/rmw_zenoh_cpp`
  leaves the reporter's frontier.

That last detail is subtle.  `data_frame/rmw_zenoh_cpp` has the lowest mean p95
latency in this run, but the current Pareto objective set does not optimize
latency directly.  It optimizes utility, control starvation, deadline miss,
loss, control delivery, and control non-delivery.  Under that objective set,
`data_frame/rmw_zenoh_cpp` is dominated by both `event_json/rmw_zenoh_cpp` and
`data_frame/rmw_cyclonedds_cpp`.

The research signal is now stronger than "binary frame is faster than JSON".
FleetRMW needs a profile-aware, objective-aware transport and representation
selector.  The selector must expose the active objective vector explicitly,
because a latency-sensitive teleoperation objective may select differently from
a safety/utility objective.

## Next Evidence Target

The next milestone should stop treating packet format and RMW as static
configuration.  It should add a profile-aware selector that can choose among
`event_json`, `fleetrmw.data_frame.v1`, and candidate RMW/data planes using
observed link profile, semantic mode, control delivery, deadline miss, loss,
and latency/QoE objectives.

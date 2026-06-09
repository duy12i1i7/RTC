# ROS 2 Direct RMW Netem Matrix V1

This artifact is the first direct ROS 2 pub/sub baseline path for the
FleetRMW/FleetQoX RMW testbed.

- Probe: `scripts/run_ros2_direct_rmw_netem_probe.py`
- Matrix: `scripts/run_ros2_direct_rmw_netem_matrix.py`
- Schema: `fleetrmw.ros2_direct_rmw_netem_matrix.v1`
- Full matrix summary:
  `results_rmw_socket/ros2_direct_rmw_netem_matrix_summary.json`
- Full matrix report:
  `results_rmw_socket/ros2_direct_rmw_netem_matrix_report.md`
- Four-robot Wi-Fi smoke summary:
  `results_rmw_socket/ros2_direct_rmw_netem_matrix_4robot_wifi_smoke_summary.json`
- Four-robot Wi-Fi smoke report:
  `results_rmw_socket/ros2_direct_rmw_netem_matrix_4robot_wifi_smoke_report.md`
- Four-robot full matrix summary:
  `results_rmw_socket/ros2_direct_rmw_netem_matrix_4robot_summary.json`
- Four-robot full matrix report:
  `results_rmw_socket/ros2_direct_rmw_netem_matrix_4robot_report.md`
- Deterministic smoke summary:
  `results_rmw_socket/ros2_direct_rmw_netem_matrix_fastrtps_wifi_smoke_summary.json`
- Deterministic smoke report:
  `results_rmw_socket/ros2_direct_rmw_netem_matrix_fastrtps_wifi_smoke_report.md`

## Scope

This runner starts a direct ROS 2 publisher container and subscriber container
on a private Docker network. It publishes the same two FleetRMW study topics:

- `/robot_0000/cmd_vel`;
- `/robot_0001/odom`.

Payloads are `std_msgs/String` JSON envelopes containing sequence and send
timestamp. The subscriber records per-flow payload count and latency. The
publisher container applies the selected profile's `primary_wifi` `tc netem`
configuration, so this is a single-path direct DDS/Zenoh-style baseline rather
than a FleetRMW redundant-router topology.

## RMW Availability

The runner probes each requested RMW package before running the row. Missing
RMW packages are reported as `skipped` with `reason=rmw_unavailable`, not as
failures.

The rebuilt checked image `localhost/fleetrmw/rmw-netem:jazzy` exposes all
requested packages:

- `rmw_fastrtps_cpp`;
- `rmw_cyclonedds_cpp`;
- `rmw_zenoh_cpp`.

## Current Evidence

The deterministic Fast DDS Wi-Fi smoke with strict qdisc verification completed:

- status `ok`;
- `1/1` row OK;
- qdisc applied `1/1`;
- control delivery `3/3`;
- state delivery `3/3`.

An earlier stochastic Wi-Fi smoke before the rebuild exposed a useful negative
row: Fast DDS delivered state `3/3` but control `0/3` in that repetition, while
Cyclone DDS was skipped because that older image had not yet been rebuilt with
Cyclone installed.

The rebuilt full matrix uses `wifi`, `wan`, and `roaming` profiles, seeds
`7,13,29`, strict qdisc verification, and loss scale `0.1`. It completed with
status `partial`: `16/27` rows OK, `0` skipped, and `11` failed.

Grouped result:

| rmw | wifi | wan | roaming | note |
|---|---:|---:|---:|---|
| `rmw_fastrtps_cpp` | `3/3` OK | `2/3` OK | `2/3` OK | Seed `29` loses one WAN control row and one roaming control/state row under the four-robot envelope. |
| `rmw_cyclonedds_cpp` | `3/3` OK | `3/3` OK | `3/3` OK | Full delivery in this envelope, with roaming latency higher than WAN. |
| `rmw_zenoh_cpp` | `0/3` OK | `0/3` OK | `0/3` OK | Direct pub/sub saw no control/state payloads; a debug probe showed publisher OK but zero discovered subscriptions. |

The Zenoh row should be treated as a direct-baseline configuration gap, not as
a broad claim that Zenoh cannot serve the architecture. The existing live-bridge
rows still show Zenoh winning some packet-format/profile combinations when the
sidecar/bridge topology is used.

The probe and matrix runner now support `--robot-count`. With the default
`--robot-count 1`, the runner preserves the original two study topics:
`/robot_0000/cmd_vel` and `/robot_0001/odom`. With `--robot-count N` for
`N > 1`, it creates two topics per robot:
`/robot_XXXX/cmd_vel` and `/robot_XXXX/odom`, then reports aggregate
control/state delivery plus minimum per-topic delivery.

The first four-robot Wi-Fi smoke uses seed `7`, loss scale `0.1`, strict qdisc
verification, `2` samples per topic, and `8` ROS 2 topics. It completed
`2/3` rows OK:

- Fast DDS: `8/8` control and `8/8` state payloads delivered, min-topic
  delivery `1.0`;
- Cyclone DDS: `8/8` control and `8/8` state payloads delivered, min-topic
  delivery `1.0`;
- Zenoh direct pub/sub: `0/8` control and `0/8` state payloads delivered in
  this harness.

The full four-robot matrix then runs Wi-Fi, WAN, and roaming profiles over
seeds `7,13,29`. It completes `16/27` rows OK with no skips:

- Cyclone DDS passes `9/9` rows with full aggregate and per-topic delivery;
- Fast DDS passes Wi-Fi `3/3`, WAN `2/3`, and roaming `2/3`; seed `29` exposes
  one WAN partial-control miss (`7/8` control, `8/8` state) and one roaming
  full delivery miss (`0/8` control, `0/8` state);
- Zenoh direct pub/sub remains `0/9` in this harness.

This is the first point where the direct baseline starts to show scale-sensitive
failure even for a DDS implementation that passed the two-topic matrix. The
matched FleetRMW router/redundancy matrix has now been run against the same
four-robot topic count, profiles, seeds `7,13,29`, and loss scale `0.1`: it
passes `9/9` rows with qdisc applied, router status OK, and application
delivery `12/12` for both control and state in every row. That result is still
not a direct DDS-vs-FleetRMW superiority claim because the direct rows remain
single-path pub/sub while FleetRMW uses router-level deadline sequence repair.

## Example

```bash
python3 scripts/run_ros2_direct_rmw_netem_matrix.py \
  --image localhost/fleetrmw/rmw-netem:jazzy \
  --rmws rmw_fastrtps_cpp,rmw_cyclonedds_cpp,rmw_zenoh_cpp \
  --profiles wifi,wan,roaming \
  --seeds 7,13,29 \
  --netem-loss-scale 0.1 \
  --require-netem \
  --robot-count 1
```

This is the direct-baseline seed for the next paper-grade campaign: either run
DDS/Zenoh through comparable router/repair semantics or expose equivalent
terminal-horizon, ACK/NACK, and QoE metrics on the direct RMW side.

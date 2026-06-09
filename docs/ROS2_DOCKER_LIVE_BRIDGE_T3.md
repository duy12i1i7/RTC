# ROS 2 Docker Live Bridge T3

## Purpose

This is the ROS-backed integration tier for macOS development.  Instead of
installing ROS 2 natively on macOS, the test runs ROS 2 inside Linux containers
through Docker Desktop.

The harness starts eight services:

```text
ROS 2 publisher
-> rclpy live ingress bridge
-> FleetRMW sidecar
-> ROS 2 egress bridge
-> local control lease adapter
-> projection quality gate
-> ROS 2 monitor
-> UDP receiver metrics
```

The bridge subscribes real ROS 2 messages, estimates serialized payload size,
turns callbacks into `Ros2Sample` records, and feeds the sidecar over TCP.  The
sidecar then emits the selected packet representation to the egress bridge.  The
egress bridge republishes sidecar wire decisions as ROS 2 `std_msgs/String`
envelopes and forwards the original UDP packet to the receiver so the previous
latency/loss metric path remains comparable.  For `geometry_msgs/Twist`
control samples, the egress bridge can also publish a typed local command
projection on `/fleetrmw/<robot>/local_cmd_vel`.  It can also project admitted
state/perception semantic payloads to `/fleetrmw/<robot>/local_odom` and
`/fleetrmw/<robot>/local_scan` in sideband/debug mode.  For the default T3
state/perception path it publishes only `/fleetrmw/<robot>/qualified_odom` and
`/fleetrmw/<robot>/qualified_scan`, where each wrapper contains both the typed
sample and its `fleetrmw_interfaces/msg/ProjectionQuality` contract.  The local
controller lease adapter gates the typed command and publishes the safe
robot-local output on `/<robot>/cmd_vel_fleetrmw`.  The projection quality gate
then consumes the qualified wrappers before forwarding accepted state/perception
to `/fleetrmw/<robot>/accepted_odom` and `/fleetrmw/<robot>/accepted_scan`.

## Files

- `external/ros2-live-bridge/Dockerfile`
- `external/ros2-live-bridge/docker-compose.yml`
- `scripts/run_ros2_test_publisher.py`
- `scripts/run_ros2_egress_bridge.py`
- `scripts/run_ros2_local_controller_lease.py`
- `scripts/run_ros2_projection_quality_gate.py`
- `scripts/run_ros2_string_monitor.py`
- `scripts/run_ros2_docker_live_bridge.py`
- `experiments/ros2_live_bridge_tb4_v1.json`
- `experiments/ros2_live_bridge_tb4_typed_projection_v1.json`

## Run

```bash
python3 -m scripts.run_ros2_docker_live_bridge \
  --run \
  --analyze \
  --scenario ros2_live_bridge_t3_v1 \
  --policy fleetqox_semantic_contract_adaptive \
  --json
```

By default the runner uses `ros:jazzy-ros-base` and the
`experiments/ros2_live_bridge_tb4_v1.json` topic config.  It writes:

- `results_ros2_live_bridge/ros2_live_bridge_t3_v1_decisions.jsonl`
- `results_ros2_live_bridge/ros2_live_bridge_t3_v1_received.jsonl`
- `results_ros2_live_bridge/ros2_live_bridge_t3_v1_egress_publications.jsonl`
- `results_ros2_live_bridge/ros2_live_bridge_t3_v1_egress_monitor.jsonl`
- `results_ros2_live_bridge/ros2_live_bridge_t3_v1_lease_decisions.jsonl`
- `results_ros2_live_bridge/ros2_live_bridge_t3_v1_metrics.jsonl`

If Docker Hub rate-limits anonymous pulls, authenticate or pre-pull/provide a
base image:

```bash
docker login
docker pull ros:jazzy-ros-base
```

or:

```bash
python3 -m scripts.run_ros2_docker_live_bridge \
  --run \
  --analyze \
  --base-image <local-or-mirrored-ros-jazzy-image>
```

## What This Proves

This tier is stronger than the dependency-free shim tests because it exercises:

- real `rclpy` subscriptions;
- real ROS 2 topic discovery inside a Docker network;
- serialized ROS 2 message payload sizing;
- live callback coalescing into sidecar ticks;
- the existing adaptive semantic-contract sidecar runtime;
- sidecar UDP egress decoded into ROS 2 control/degraded envelopes;
- typed `geometry_msgs/Twist`, `nav_msgs/Odometry`, and
  `sensor_msgs/LaserScan` egress projections for admitted semantic payloads;
- projection-quality metadata that marks typed outputs as raw-equivalent,
  degraded, or downsampled, either as a typed sideband or inside qualified
  odom/scan wrapper messages;
- local robot-side lease enforcement, acceleration/jerk-aware clipping, and
  fallback stop;
- consumer-side projection-quality gating for typed odometry and scan;
- ROS 2 egress delivery observed by a separate subscriber process;
- the old UDP receiver metric path preserved by egress forwarding.

## Measured Local Lease Run

After authenticating Docker Hub and pulling `ros:jazzy-ros-base`, the T3 local
lease smoke ran successfully on macOS through Docker Desktop:

```text
scenario: ros2_live_bridge_t3_local_profiles_jerk_v1
publisher: 37 ROS 2 publish ticks
decisions: 41
sidecar packets received by egress: 17
ROS 2 egress messages monitored: 39
UDP receiver packets after egress forward: 17
wire modes: 8 supervisory_intent, 9 degraded, 24 native decision drops
typed Twist publications: 8
safe cmd_vel publications: 14
lease statuses: 2 accept, 6 clip, 8 lease_update, 6 fallback_stop
clip stages: 6 acceleration, 1 jerk
controller profile: tb4_lite_safe_v1
control delivery: 1.0000
loss: 0.0000
p95 latency: 210.82 ms
deadline miss: 0.0588
```

The important result is functional, not yet a performance claim: real ROS 2
callbacks inside Docker reached the adaptive semantic-contract sidecar, and
`/robot_0000/cmd_vel` was transformed into `send_supervisory_intent` packets
under the same roaming-like link assumptions used by the sidecar experiments.
Those admitted packets were then decoded by the egress bridge and observed again
as ROS 2 messages on:

- `/fleetrmw/robot_0000/control_lease`
- `/fleetrmw/robot_0000/degraded`
- `/fleetrmw/robot_0000/local_cmd_vel`
- `/robot_0000/cmd_vel_fleetrmw`

This closes the first functional ROS ingress-and-egress loop with both semantic
envelopes, one typed control projection, and robot-side lease enforcement.  The
remaining gap is general typed reconstruction and controller-specific semantics:
odometry, perception, degraded state, profile calibration from measured robot
dynamics, and explicit type-specific policies.

## Typed Projection And Quality-Gate Runs

A separate coverage smoke uses
`experiments/ros2_live_bridge_tb4_typed_projection_v1.json` with a wider link
budget.  Its purpose is not to claim constrained-link performance; it verifies
that command, state, and scan semantic payloads can all leave ROS 2, pass
through the sidecar, re-enter the ROS graph as typed or qualified
FleetRMW-local topics, and then pass a local consumer quality gate.  The first
coverage run below is the older sideband/signature path.

```text
scenario: ros2_live_bridge_t3_typed_quality_compact_v2
publisher: 38 ROS 2 publish ticks
egress UDP packets: 73
ROS egress publications: 183
ROS 2 monitor messages: 239
wire modes: 18 control_intent, 55 native
typed egress publications: 18 Twist, 19 Odometry, 18 LaserScan
projection quality publications: 55
projection quality ROS type: fleetrmw_interfaces/msg/ProjectionQuality
projection quality payload mode: compact
quality records with embedded payload: 0/55
quality gate statuses: 37 accept, 18 ignore_projection_kind
quality gate fidelity: 19 raw_equivalent, 18 downsampled, 18 degraded
signature matched projections: 37
missing signatures: 0
accepted odom publications observed: 19
accepted scan publications observed: 18
safe cmd_vel publications: 19
lease statuses: 18 accept, 18 lease_update, 1 fallback_stop
control delivery: 1.0000
loss: 0.0000
p95 latency: 55.24 ms
deadline miss: 0.0000
```

The current default T3 run uses wrapper delivery instead of the sideband.  This
removes `/projection_quality` as a separate pairing topic for state/perception:

```text
scenario: ros2_live_bridge_t3_source_sample_id_v1
publisher: 38 ROS 2 publish ticks
egress UDP packets: 76
ROS egress publications: 133
ROS 2 monitor messages: 191
wire modes: 19 control_intent, 57 native received by egress
typed egress publications: 19 Twist, 0 Odometry, 0 LaserScan
qualified publications: 19 QualifiedOdometry, 19 QualifiedLaserScan
projection quality sideband publications: 0
quality gate statuses: 38 accept
quality gate message mode: 38 wrapped
quality gate payload present: 38 false
contract IDs in gate log: 38/38 non-empty, 38 unique
source sample IDs in gate log: 38/38 non-empty, 38 unique
decision-to-qualified contract ID matches: 38/38 received qualified samples
decision-to-qualified source sample ID matches: 38/38 received qualified samples
accepted odom publications observed: 19
accepted scan publications observed: 19
safe cmd_vel publications: 20
lease statuses: 19 accept, 19 lease_update, 1 fallback_stop
control delivery: 1.0000
loss: 0.0000
p95 latency: 60.46 ms
deadline miss: 0.0000
```

The constrained `tb4_v1` run still dropped odometry under the adaptive policy
while delivering control and scan projections.  That distinction is intentional:
typed projection capability and fleet-level admission policy are separate
claims.

The source-metadata callback path was then validated with the same wrapper
configuration:

```text
scenario: ros2_live_bridge_t3_source_metadata_v2
sidecar packet decisions: 66/66 carried source_metadata
source metadata fields: 66 sequence_number, 66 source_timestamp_ns, 66 received_timestamp_ns, 0 publisher_gid
egress UDP packets: 64
qualified publications: 18 QualifiedOdometry, 15 QualifiedLaserScan
quality gate statuses: 32 accept, 1 drop_projection
contract IDs in gate log: 33/33 non-empty, 33 unique
source sample IDs in gate log: 33/33 non-empty, 33 unique
decision-to-qualified contract ID matches: 33/33 received qualified samples
decision-to-qualified source sample ID matches: 33/33 received qualified samples
control delivery: 0.9375
loss: 0.0303
p95 latency: 61.86 ms
deadline miss: 0.0000
```

This run proves that the live bridge can receive `MessageInfo` sequence and
timestamp metadata from ROS 2 callbacks and feed it into the FleetRMW source
identity path.

The callback metadata path was then promoted to a cross-RMW matrix:

```text
scenario: ros2_live_bridge_t3_rmw_metadata_v2
rmw_fastrtps_cpp: packets=76 metadata=76 publisher_gid=0 sequence_number=76 source_timestamp_ns=76 received_timestamp_ns=76 gate=38/38 accept loss=0.0000 p95=68.22 ms
rmw_cyclonedds_cpp: packets=80 metadata=80 publisher_gid=0 sequence_number=0 source_timestamp_ns=80 received_timestamp_ns=80 gate=40/40 accept loss=0.0125 p95=51.93 ms
rmw_zenoh_cpp: packets=73 metadata=73 publisher_gid=0 sequence_number=73 source_timestamp_ns=73 received_timestamp_ns=73 gate=36/36 accept loss=0.0137 p95=59.76 ms
```

The result is deliberately stricter than a single-RMW smoke test:
`source_timestamp_ns` and `received_timestamp_ns` were portable across Fast DDS,
CycloneDDS, and Zenoh RMW; `sequence_number` was present in Fast DDS and Zenoh
but absent in CycloneDDS; `publisher_gid` was absent through this `rclpy`
callback path for all three.  FleetRMW therefore treats callback source
metadata as useful but optional, and a future native RMW must provide publisher
identity directly in its own sample envelope.

The same Docker harness can now switch the sidecar UDP payload from legacy
sidecar JSON to `fleetrmw.data_frame.v1` bytes:

```bash
python3 -m scripts.run_ros2_docker_live_bridge \
  --run \
  --analyze \
  --packet-format data_frame \
  --scenario ros2_live_bridge_t3_data_frame_v1 \
  --bridge-config experiments/ros2_live_bridge_tb4_typed_projection_v1.json
```

This mode is intentionally opt-in while the bridge transitions.  The egress
decoder accepts both formats, so frame-mode tests can compare against the
legacy JSON path without changing ROS-facing topics.

The first frame-mode Docker T3 run validated that the data frame can replace
raw sidecar JSON on the UDP sidecar-to-egress path while preserving ROS-facing
delivery:

```text
scenario: ros2_live_bridge_t3_data_frame_v1
packet_format: data_frame
sidecar packet decisions: 73
egress received: 71 packets
receiver measured: 71 packets
egress invalid packets: 0
qualified publications: 18 QualifiedOdometry, 18 QualifiedLaserScan
quality gate statuses: 36 accept
decision-to-gate contract ID matches: 36/36
decision-to-gate source sample ID matches: 36/36
control delivery: 1.0000
loss: 0.0274
p95 latency: 37.35 ms
deadline miss: 0.0000
```

The first attempt exposed a useful transition bug: the egress bridge already
decoded frames correctly, but the UDP trace receiver only understood legacy
JSON and could not compute latency.  `fleetrmw.data_frame.v1` now carries
`send_monotonic_ns`, and the receiver decodes both packet formats.

The frame-mode path was then promoted to the RMW matrix:

```text
scenario: ros2_live_bridge_t3_data_frame_rmw_matrix_v1
rmw_fastrtps_cpp: tx=78 rx=78 loss=0.0000 control_delivery=1.0000 p95=44.98 ms gate=39/39 contract/source match=39/39
rmw_cyclonedds_cpp: tx=73 rx=72 loss=0.0137 control_delivery=1.0000 p95=37.50 ms gate=36/36 contract/source match=36/36
rmw_zenoh_cpp: tx=70 rx=69 loss=0.0143 control_delivery=1.0000 p95=30.90 ms gate=34/34 contract/source match=34/34
```

This confirms that the `fleetrmw.data_frame.v1` sidecar-to-egress path is
portable across the current Fast DDS, CycloneDDS, and Zenoh RMW Docker T3
matrix.

The runner can also compare both packet formats in the same scenario:

```bash
python3 -m scripts.run_ros2_docker_live_bridge \
  --run \
  --analyze \
  --packet-format-matrix \
  --scenario ros2_live_bridge_t3_packet_format_compare_v1 \
  --bridge-config experiments/ros2_live_bridge_tb4_typed_projection_v1.json
```

The first Fast DDS comparison kept the ROS-facing behavior identical across
formats:

```text
scenario: ros2_live_bridge_t3_packet_format_compare_v1
event_json: tx=80 rx=80 loss=0.0000 control_delivery=1.0000 p95=50.02 ms gate=40/40 contract/source match=40/40
data_frame: tx=80 rx=80 loss=0.0000 control_delivery=1.0000 p95=40.87 ms gate=40/40 contract/source match=40/40
```

This is a transition result rather than a final performance claim: legacy JSON
and native frame packets now produce the same typed egress, quality-gate, and
identity-contract outcomes, so the next evidence layer can compare them across
RMWs, repeated seeds, and network profiles.

That RMW comparison now runs as:

```bash
python3 -m scripts.run_ros2_docker_live_bridge \
  --run \
  --analyze \
  --all-rmws \
  --packet-format-matrix \
  --scenario ros2_live_bridge_t3_packet_format_rmw_matrix_v1 \
  --bridge-config experiments/ros2_live_bridge_tb4_typed_projection_v1.json
```

The first 2 x 3 packet-format/RMW matrix completed with `6/6` runs and `0`
invalid egress packets:

```text
event_json rmw_fastrtps_cpp: tx=68 rx=67 loss=0.0147 control_delivery=0.9412 p95=59.04 ms gate=35/35 contract/source match=35/35
event_json rmw_cyclonedds_cpp: tx=80 rx=78 loss=0.0250 control_delivery=0.9500 p95=50.72 ms gate=38/39 contract/source match=39/39
event_json rmw_zenoh_cpp: tx=77 rx=77 loss=0.0000 control_delivery=1.0000 p95=32.60 ms gate=38/38 contract/source match=38/38
data_frame rmw_fastrtps_cpp: tx=72 rx=72 loss=0.0000 control_delivery=1.0000 p95=58.77 ms gate=36/36 contract/source match=36/36
data_frame rmw_cyclonedds_cpp: tx=76 rx=75 loss=0.0132 control_delivery=0.9474 p95=58.17 ms gate=37/38 contract/source match=38/38
data_frame rmw_zenoh_cpp: tx=78 rx=78 loss=0.0000 control_delivery=1.0000 p95=34.98 ms gate=39/39 contract/source match=39/39
```

This confirms portability of `fleetrmw.data_frame.v1` across the current Docker
T3 RMW matrix.  It does not yet justify a latency dominance claim because these
are single realizations.

The same runner now supports repeated packet-format/RMW sweeps with workload
seeds and named netem profiles:

```bash
python3 -m scripts.run_ros2_docker_live_bridge \
  --run \
  --analyze \
  --all-rmws \
  --packet-format-matrix \
  --seeds 7,13,29 \
  --profile wifi \
  --scenario ros2_live_bridge_t3_repeated_packet_wifi_3seed_v1 \
  --bridge-config experiments/ros2_live_bridge_tb4_typed_projection_v1.json
```

The first harness smoke used one Wi-Fi seed and Fast DDS only:

```text
scenario: ros2_live_bridge_t3_repeated_packet_smoke_v1
event_json/rmw_fastrtps_cpp: runs=1 rx=80 loss=0.0000 control_delivery=1.0000 p95=47.49 ms
data_frame/rmw_fastrtps_cpp: runs=1 rx=74 loss=0.0263 control_delivery=1.0000 p95=42.04 ms
```

This validates repeated report generation and seeded publisher variation.  It
is not a statistical packet-format ranking.

The first full Wi-Fi repeated matrix then ran all three RMWs and both packet
formats over three workload seeds:

```text
scenario: ros2_live_bridge_t3_repeated_packet_wifi_3seed_v1
statuses: 18 ran / 18 planned
invalid egress packets: 0 in all 18 runs
data_frame/rmw_zenoh_cpp: runs=3 utility=458.2 control_delivery=1.0000 loss=0.0173 p95=38.27 ms rx=75.33 pareto=yes
event_json/rmw_cyclonedds_cpp: runs=3 utility=456.8 control_delivery=0.9482 loss=0.0176 p95=62.69 ms rx=75.33 pareto=no
data_frame/rmw_cyclonedds_cpp: runs=3 utility=455.6 control_delivery=0.9658 loss=0.0257 p95=56.69 ms rx=75.33 pareto=no
data_frame/rmw_fastrtps_cpp: runs=3 utility=444.4 control_delivery=0.9833 loss=0.0308 p95=59.08 ms rx=73.33 pareto=no
event_json/rmw_fastrtps_cpp: runs=3 utility=443.0 control_delivery=0.9658 loss=0.0351 p95=60.56 ms rx=73.33 pareto=no
event_json/rmw_zenoh_cpp: runs=3 utility=430.8 control_delivery=0.9269 loss=0.0273 p95=53.47 ms rx=71.33 pareto=no
```

This is the strongest ROS-backed frame-transition signal so far:
`data_frame/rmw_zenoh_cpp` is the only non-dominated combination in the current
Wi-Fi evidence set.  The result is still profile-specific, so it cannot be
promoted to a general transport selection claim without other profiles.

The WAN repeated matrix changes the conclusion:

```text
scenario: ros2_live_bridge_t3_repeated_packet_wan_3seed_v1
statuses: 18 ran / 18 planned
invalid egress packets: 0 in all 18 runs
event_json/rmw_zenoh_cpp: runs=3 utility=342.5 control_delivery=1.0000 loss=0.0365 p95=111.19 ms rx=58.00 pareto=yes
data_frame/rmw_zenoh_cpp: runs=3 utility=318.8 control_delivery=0.9778 loss=0.0537 p95=115.65 ms rx=54.33 pareto=yes
event_json/rmw_fastrtps_cpp: runs=3 utility=315.9 control_delivery=0.9778 loss=0.0472 p95=159.33 ms rx=53.33 pareto=yes
data_frame/rmw_cyclonedds_cpp: runs=3 utility=284.6 control_delivery=1.0000 loss=0.0271 p95=131.51 ms rx=48.33 pareto=yes
event_json/rmw_cyclonedds_cpp: runs=3 utility=276.9 control_delivery=1.0000 loss=0.0548 p95=125.05 ms rx=47.67 pareto=yes
data_frame/rmw_fastrtps_cpp: runs=3 utility=269.4 control_delivery=1.0000 loss=0.0328 p95=132.74 ms rx=46.33 pareto=no
```

The roaming repeated matrix adds the harshest profile in the current T3 sweep:

```text
scenario: ros2_live_bridge_t3_repeated_packet_roaming_3seed_v1
statuses: 18 ran / 18 planned
invalid egress packets: 0 in all 18 runs
event_json/rmw_zenoh_cpp: runs=3 utility=248.5 control_delivery=0.9667 loss=0.0645 p95=162.60 ms rx=42.00 pareto=yes
data_frame/rmw_cyclonedds_cpp: runs=3 utility=242.8 control_delivery=0.9188 loss=0.0487 p95=199.81 ms rx=41.67 pareto=yes
event_json/rmw_cyclonedds_cpp: runs=3 utility=242.2 control_delivery=1.0000 loss=0.0578 p95=169.44 ms rx=41.33 pareto=yes
data_frame/rmw_fastrtps_cpp: runs=3 utility=160.6 control_delivery=0.8102 loss=0.0955 p95=217.62 ms rx=27.33 pareto=yes
event_json/rmw_fastrtps_cpp: runs=3 utility=138.6 control_delivery=0.9630 loss=0.0554 p95=227.12 ms rx=24.33 pareto=yes
data_frame/rmw_zenoh_cpp: runs=3 utility=240.0 control_delivery=0.9048 loss=0.0805 p95=158.59 ms rx=41.00 pareto=no
```

This confirms that `fleetrmw.data_frame.v1` is portable, not universally
dominant.  Under WAN, the frontier is broad: legacy JSON with Zenoh has the
highest mean utility, while data-frame with CycloneDDS has the lowest mean
loss.  Under roaming, the frontier changes again and the current reporter
frontier excludes `data_frame/rmw_zenoh_cpp` despite its lowest mean p95
latency, because the objective set emphasizes utility, control delivery,
deadline miss, starvation, and loss.  The next research step is therefore a
measured profile-aware and objective-aware selector over RMW/data plane and
semantic representation, not a fixed packet-format switch.

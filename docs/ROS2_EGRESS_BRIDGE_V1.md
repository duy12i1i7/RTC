# ROS 2 Egress Bridge V1

## Purpose

This milestone closes the first receiving half of the FleetRMW sidecar path.
The sidecar still emits UDP packet events, but a receiving bridge now decodes
the sidecar event contract and republishes a ROS 2-facing envelope.

```text
FleetRMW sidecar UDP packet
-> sidecar event decode
-> wire-mode routing
-> std_msgs/String publication
-> optional UDP forward for metric receiver
```

The goal is not to blindly reconstruct every original ROS message.  The goal is
to prove that sidecar decisions can re-enter the ROS graph as explicit local
robot signals: control leases, degraded representations, semantic deltas,
native trace envelopes, and typed local projections for command, state, and
scan snapshots when the sidecar event carries a valid semantic payload.  State
and perception projections now have a wrapper-first path: the quality contract
can travel in the same ROS sample as the reconstructed message, so local
consumers do not need to pair a typed sample with a separate sideband topic.

## New Code

- `fleetqox/sidecar_egress.py`
  - `decode_sidecar_packet` parses padded sidecar UDP JSON without ROS.
  - `SidecarEgressRouter` maps sidecar `action`/`wire_mode` to ROS topics.
  - `EgressPublication` is the dependency-free publication record.
- `scripts/run_ros2_egress_bridge.py`
  - Lazy-imports `rclpy`, `std_msgs`, `geometry_msgs`, `nav_msgs`, and
    `sensor_msgs`.
  - Listens for sidecar UDP packets.
  - Publishes `std_msgs/String` envelopes.
  - With `--publish-typed`, also publishes typed `geometry_msgs/Twist`,
    `nav_msgs/Odometry`, and `sensor_msgs/LaserScan` local projections when the
    sidecar event carries the corresponding semantic payload.
  - Publishes projection quality as sideband metadata, qualified wrapper
    messages, or both.  Docker T3 uses wrapper delivery by default.
  - Optionally forwards the original packet to the UDP receiver.
- `ros2_ws/src/fleetrmw_interfaces`
  - Defines `SampleIdentity`, `ProjectionQuality`, `QualifiedOdometry`, and
    `QualifiedLaserScan`.
- `scripts/run_ros2_string_monitor.py`
  - Subscribes ROS 2 `std_msgs/String` egress topics and typed Twist/Odometry/
    LaserScan projection topics, plus the qualified wrapper topics.
  - Writes observed messages to JSONL for Docker T3 verification.
- `fleetqox/projection_quality_gate.py` and
  `scripts/run_ros2_projection_quality_gate.py`
  - Apply a consumer-side quality envelope to typed state/perception
    projections before publishing `accepted_odom` and `accepted_scan`.
- `tests/test_sidecar_egress.py`
  - Covers padded packet decode, route selection, invalid packets, and ROS topic
    token sanitization without requiring ROS 2.

## Routing Contract

| sidecar action / wire mode | ROS topic | envelope kind |
| --- | --- | --- |
| `send_supervisory_intent` / `supervisory_intent` | `/fleetrmw/<robot>/control_lease` | `supervisory_intent` |
| `send_intent` / `control_intent` | `/fleetrmw/<robot>/control_lease` | `control_intent` |
| `send_degraded` / `degraded` | `/fleetrmw/<robot>/degraded` | `degraded` |
| `send_compacted` / `semantic_delta` | `/fleetrmw/<robot>/semantic_delta` | `semantic_delta` |
| `send` / `native` | `/fleetrmw/<robot>/native_trace` | `native` |

The envelope includes the source ROS topic, robot ID, flow ID, policy, sidecar
reason, effective deadline/lifespan, reliability, semantic utility, task-risk
context, and observed link context.

When typed projection is enabled, selected command semantic payloads from the
ingress bridge are republished as FleetRMW-local ROS topics:

| semantic payload | ROS topic | ROS type |
| --- | --- | --- |
| `geometry_msgs/msg/Twist` | `/fleetrmw/<robot>/local_cmd_vel` | `geometry_msgs/msg/Twist` |

The command projection is intentionally separate from state/perception because
it is consumed by the robot-local lease adapter.  It is not accepted as actuator
authority until the lease gate validates freshness and controller limits.

## Feedback Ownership

When `--egress-feedback` is enabled, the bridge sends per-robot receiver
feedback to the sidecar over a reusable TCP feedback client.  The feedback
window deliberately separates delivery from deadline ownership:

- control leases (`control_intent` and `supervisory_intent`) count toward
  control delivery and latency samples;
- control-lease receiver latency does not create egress deadline debt, because
  the local lease validity window starts when the robot receives the lease;
- state, safety, coordination, and other network-owned deadline classes still
  create egress deadline debt and `deadline_miss_by_transform` buckets.

This prevents the WAN transit time of a valid lease from being double-counted
as both network tail debt and robot-side command freshness debt.  The
robot-local lease adapter owns the command application deadline feedback.

The egress bridge also has ACK-only control-lease feedback modes that do not
update robot-budget learning state:

- `--feedback-control-lease-ack-immediate` sends each newly observed
  control-lease event ID as soon as it reaches the robot egress boundary.  It is
  a negative-control mode: in the current `8`-robot Docker matrix it overloads
  the sidecar feedback path and collapses control delivery.
- `--feedback-control-lease-ack-window-events <N>` coalesces ACK-only records in
  a fixed event window.  The first fixed `N=8` audit recovers seed `13` alone but
  falls to `1/3` budget pass over three seeds.
- `--feedback-control-lease-ack-adaptive` adds a backpressured ACK pacer.  It
  is piggyback-first by default: regular robot feedback already carries
  `control_lease_event_ids`, so successful regular feedback clears matching
  pending ACK-only records before they create extra feedback traffic.  ACK-only
  fallback is used when pending ACKs become too old or the emergency backlog
  reaches `--feedback-control-lease-ack-adaptive-max-events`.  The older
  event-threshold behavior is still available for comparison with
  `--feedback-control-lease-ack-adaptive-no-piggyback-first`.  The pacer preserves
  pending ACKs when feedback delivery fails, expands the ACK window by
  `--feedback-control-lease-ack-adaptive-failure-multiplier`, and contracts it by
  `--feedback-control-lease-ack-adaptive-success-step` after successful feedback.
  It also flushes old pending ACKs after
  `--feedback-control-lease-ack-adaptive-max-age-ms`; that deadline is scaled by
  the current backpressure window so failures reduce feedback eagerness instead
  of recreating the immediate-ACK storm.  ACK records carry batch metadata
  (`ack_pacing_mode`, `ack_batch_id`, `ack_batch_size`, and `ack_window_events`).
  They also preserve RMW-facing source identity when the sidecar event provides
  it (`source_sample_id`, `source_sequence_number`, source timestamp, and
  receiver timestamp), so the same primitive can later move from the sidecar
  bridge into the FleetRMW transport boundary.

The repeated `8`-robot rows say the transport boundary must use adaptive paced
ACK/NACK with backpressure, not per-packet ACK eagerness or a fixed ACK window.
The bridge tracks source sequences with `RmwAckNackTracker` and piggybacks
`fleetrmw.ack_nack.v1` records in regular feedback windows.  When the receiver
observes a source-sequence gap, the feedback record carries compact
`missing_sequence_ranges`; the sidecar runtime can consume those gaps to request
retransmission of matching tracked control leases.  The live `8`-robot result
only passes after the sender-side history is kept for a liveliness-backed
recovery horizon: seeds `7,13,29` reach hard budget `3/3`, control delivery
`0.9902`, minimum per-robot control delivery `0.9804`, p95 `1085.30 ms`, and
quality coverage `1.0000`.  Urgent out-of-band NACK variants were tested and
rejected because they recreate the feedback storm that the pacer is designed to
avoid.

For state/perception, the default Docker T3 path publishes only qualified
wrappers.  The wrapper carries the reconstructed sample and its quality contract
in one ROS message:

| qualified topic | ROS type | sample field | quality field |
| --- | --- | --- |
| `/fleetrmw/<robot>/qualified_odom` | `fleetrmw_interfaces/msg/QualifiedOdometry` | `nav_msgs/msg/Odometry` | `fleetrmw_interfaces/msg/ProjectionQuality` |
| `/fleetrmw/<robot>/qualified_scan` | `fleetrmw_interfaces/msg/QualifiedLaserScan` | `sensor_msgs/msg/LaserScan` | `fleetrmw_interfaces/msg/ProjectionQuality` |

The old sideband remains available with
`--projection-quality-delivery-mode sideband` or `both`.  In that compatibility
mode, the bridge also publishes the bare local state/perception projections:

| semantic payload | ROS topic | ROS type |
| --- | --- | --- |
| `nav_msgs/msg/Odometry` | `/fleetrmw/<robot>/local_odom` | `nav_msgs/msg/Odometry` |
| `sensor_msgs/msg/LaserScan` | `/fleetrmw/<robot>/local_scan` | `sensor_msgs/msg/LaserScan` |

| metadata topic | ROS type | fields |
| --- | --- | --- |
| `/fleetrmw/<robot>/projection_quality` | `fleetrmw_interfaces/msg/ProjectionQuality` | `identity.contract_id`, `identity.source_sample_id`, `identity.projection_signature`, `fidelity_class`, `lossy`, `degradation_reasons`, `source_sample_count`, `projected_sample_count`, `downsample_stride`, `projection_payload_embedded` |

The default egress mode is compact: it does not embed `projection_payload`.
`--projection-quality-payload-mode full` remains available for debugging.
`--projection-quality-message-mode string` remains available as a fallback for
the sideband mode, but Docker T3 now runs typed wrapper delivery by default.

## Docker T3 Result

The egress bridge is integrated into `external/ros2-live-bridge/docker-compose.yml`.
The latest qualified-only smoke run:

```text
scenario: ros2_live_bridge_t3_source_sample_id_v1
bridge config: experiments/ros2_live_bridge_tb4_typed_projection_v1.json
egress UDP packets: 76
ROS egress publications: 133
ROS monitor observations: 191
receiver packets after forward: 76
typed egress publications: 19 Twist, 0 Odometry, 0 LaserScan
qualified egress publications: 19 QualifiedOdometry, 19 QualifiedLaserScan
projection quality sideband publications: 0
quality gate accepted publications: 38
accepted odom publications observed: 19
accepted scan publications observed: 19
contract IDs in gate log: 38/38 non-empty, 38 unique
source sample IDs in gate log: 38/38 non-empty, 38 unique
decision-to-qualified contract ID matches: 38/38 received qualified samples
decision-to-qualified source sample ID matches: 38/38 received qualified samples
control delivery ratio: 1.0000
deadline miss ratio: 0.0000
p95 latency: 60.46 ms
```

The gate ran in `wrapper` identity mode and accepted every qualified sample
that reached egress.  Egress publication logs contain no bare
`nav_msgs/Odometry` or `sensor_msgs/LaserScan` state/perception publications.
The monitor still observes `accepted_odom` and `accepted_scan` after the gate
republishes accepted samples.  The current path preserves both the sidecar
`contract_id` and the source-derived `source_sample_id` into the qualified
wrapper quality field and the gate decision log, so local delivery can be
traced back to the original source sample independently of the admission
contract.

This proves a functional ROS 2 egress loop in Docker on macOS:

```text
ROS 2 publisher -> ingress bridge -> sidecar -> egress bridge -> ROS 2 monitor
```

## Remaining Gap

V1 egress now has a typed command projection path for `cmd_vel`, compatibility
sideband paths for odometry and downsampled laser scan snapshots, and a default
state/perception wrapper path that binds a quality contract to the sample.  The
robot-side safety step for commands is implemented separately in
`ROS2_LOCAL_CONTROL_LEASE_V1.md`.  The broader remaining gap is architectural:
the wrapper is still a FleetRMW-local ROS topic, not true RMW sample metadata.
The next layer should move identity, quality, and admission provenance toward
the actual RMW boundary.

# ROS 2 Projection Quality Gate V1

## Purpose

Typed projection alone is not enough for local consumers.  A reconstructed
`Odometry` or `LaserScan` may be raw-equivalent, degraded, or downsampled.  This
milestone adds a local consumer gate that validates projection quality before
forwarding typed state/perception to consumer-facing topics.

```text
/fleetrmw/<robot>/qualified_odom
  contains ProjectionQuality(contract_id, source_sample_id, signature, fidelity) + nav_msgs/Odometry
/fleetrmw/<robot>/qualified_scan
  contains ProjectionQuality(contract_id, source_sample_id, signature, fidelity) + sensor_msgs/LaserScan
-> projection quality gate
-> /fleetrmw/<robot>/accepted_odom
-> /fleetrmw/<robot>/accepted_scan
```

The egress bridge may still publish `/fleetrmw/<robot>/local_odom` and
`/fleetrmw/<robot>/local_scan` in sideband or debug mode.  The default gate mode
no longer pairs those samples with a separate metadata topic.  It consumes
`QualifiedOdometry` and `QualifiedLaserScan`, where quality and sample are part
of the same ROS message.  The older signature sideband and embedded
`projection_payload` paths remain as debug/fallback modes.

The gate is intentionally separate from the sidecar admission policy.  The
sidecar decides what may cross the network; the gate decides what a local
consumer is allowed to use.

## New Code

- `fleetqox/projection_identity.py`
  - Builds stable SHA-256 signatures over canonical typed projection fields.
  - Ignores non-ROS projection metadata such as scan downsample annotations.
  - Rounds numeric fields to tolerate float32/float64 representation drift.
- `fleetqox/projection_quality_gate.py`
  - Dependency-free quality policy.
  - Parses `typed_projection_quality` payloads.
  - Accepts raw-equivalent odometry by default.
  - Accepts downsampled scan only inside a local envelope.
  - Rejects degraded projections by default.
  - Rejects downsampled scan when collision risk is high.
- `ros2_ws/src/fleetrmw_interfaces`
  - Defines `SampleIdentity`, `ProjectionQuality`, `QualifiedOdometry`, and
    `QualifiedLaserScan` ROS 2 messages.
  - Lets quality travel either as a typed sideband message or inside a typed
    wrapper message.
  - `SampleIdentity` includes `contract_id`, so typed quality can carry the
    shim/sidecar contract ID without falling back to JSON-only metadata.
  - `SampleIdentity` also includes `source_sample_id`, so gate decisions can be
    traced to the original ROS/RMW-visible source sample.
- `fleetqox/projection_quality_ros.py`
  - Converts between dependency-free quality payloads and typed ROS messages.
- `scripts/run_ros2_projection_quality_gate.py`
  - ROS 2 adapter for the gate.
  - Default `wrapper` identity mode subscribes qualified odom and scan topics.
  - Optional `signature` identity mode subscribes quality plus local typed odom
    and scan, then publishes only when signatures match.
  - Optional `payload` identity mode reconstructs accepted odom/scan messages
    from embedded `projection_payload`.
  - Publishes accepted odom/scan topics and writes JSONL decisions.
  - Supports `--robot-count`; one process creates a gate, pending identity
    queues, accepted publishers, subscriptions, and counter bucket per robot
    namespace.
- `scripts/run_ros2_egress_bridge.py`
  - Default wrapper delivery sends compact quality inside qualified state/scan
    messages.
  - Optional sideband delivery sends compact signature/fidelity metadata, and
    full mode can embed `projection_payload` for debugging.
- `tests/test_projection_identity.py`
  - Covers signature metadata, non-ROS metadata exclusion, and float rounding.
- `tests/test_projection_quality_gate.py`
  - Covers raw, downsampled, degraded, stale, high-risk, and unmanaged projection
    behavior.
- `tests/test_ros2_projection_quality_gate_adapter.py`
  - Covers dependency-free odom/scan reconstruction from embedded projection
    payloads.

## Default Policy

| condition | action |
| --- | --- |
| raw-equivalent `typed_odom` | accept |
| downsampled `typed_scan`, stride <= 3, >= 30 ranges, low risk | accept |
| degraded projection | reject |
| downsampled scan with collision risk >= 0.65 | reject |
| stale projection age > 350 ms | reject |
| `typed_twist` quality | ignore; command safety is handled by local lease |

## Docker T3 Result

The latest Docker coverage run:

```text
scenario: ros2_live_bridge_t3_typed_quality_compact_v2
quality message mode: typed
identity mode: signature
projection-quality payload mode: compact
egress UDP packets: 73
egress ROS publications: 183
monitor observations: 239
projection quality records: 55
projection quality ROS type: fleetrmw_interfaces/msg/ProjectionQuality
quality records with embedded payload: 0/55
signature matched state/perception projections: 37
quality gate accepted publications: 37
quality gate statuses: 37 accept, 18 ignore_projection_kind
quality gate fidelity: 19 raw_equivalent, 18 downsampled, 18 degraded
signature matches: 37/37 accepted odom/scan projections
missing signatures: 0
accepted odom observations: 19
accepted scan observations: 18
control delivery: 1.0000
deadline miss: 0.0000
p95 latency: 55.24 ms
```

The newer wrapper run closes the adjacent-sideband gap for state/perception:

```text
scenario: ros2_live_bridge_t3_source_sample_id_v1
quality message mode: typed
identity mode: wrapper
projection-quality delivery mode: wrapper
projection-quality payload mode: compact
egress UDP packets: 76
egress ROS publications: 133
monitor observations: 191
qualified odom publications: 19
qualified scan publications: 19
bare state/perception egress publications: 0
projection quality sideband publications: 0
quality gate statuses: 38 accept
quality gate message modes: 38 wrapped
quality gate payload present: 38 false
contract IDs in gate log: 38/38 non-empty, 38 unique
source sample IDs in gate log: 38/38 non-empty, 38 unique
decision-to-qualified contract ID matches: 38/38 received qualified samples
decision-to-qualified source sample ID matches: 38/38 received qualified samples
accepted odom observations: 19
accepted scan observations: 19
control delivery: 1.0000
deadline miss: 0.0000
p95 latency: 60.46 ms
```

The sideband path is still typed ROS, not `std_msgs/String`: monitor and egress
logs report `fleetrmw_interfaces/msg/ProjectionQuality` on
`/fleetrmw/<robot>/projection_quality` when sideband delivery is enabled.  In
wrapper delivery, the ROS graph instead uses
`fleetrmw_interfaces/msg/QualifiedOdometry` and
`fleetrmw_interfaces/msg/QualifiedLaserScan`.

The important result is the contract boundary: in wrapper mode, bare
`local_odom` and `local_scan` are not published by egress.  State/perception is
only exposed as a qualified sample until the consumer-side gate republishes it
as `accepted_odom` and `accepted_scan`.  The gate log now also preserves the
same `contract_id` and `source_sample_id` that originated at the ROS shim
boundary.

The two-robot local-services follow-up
`ros2_live_bridge_t3_dynamic_objective_transition_2robot_local_services_3seed_v1`
keeps wrapper mode and expands the gate to `robot_0000` and `robot_0001` in one
ROS 2 process.  Across `3/3` seeds, the projection gate decision log observed
both robot IDs in every run while the bridge was also changing network profile
and active QoS/QoE objective.

## Remaining Gap

The FIFO pairing, payload-duplication, and untyped JSON sideband gaps are closed
in the live prototype.  Signature sideband mode uses generated typed quality
messages; wrapper mode binds quality and sample in the same ROS message.  The
remaining production gap is lower in the stack: quality is still expressed as a
FleetRMW-local application-level topic.  A production RMW path should move this
identity and quality data into RMW sample metadata, loaned message wrappers, or
transport-level sample identity so the contract is native to delivery rather
than an extra local application convention.  The namespace-aware path also
needs to scale beyond two robots with per-robot fairness and freshness budgets.

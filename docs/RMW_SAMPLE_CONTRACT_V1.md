# RMW Sample Contract V1

## Purpose

This milestone separates the FleetRMW sample contract from the ROS 2 egress
bridge.  Before this step, projection quality, sample identity, and qualified
wrapper payloads were assembled directly inside `sidecar_egress.py`.  That
worked as an integration prototype, but it made the contribution look like a
ROS topic bridge.

The new boundary is dependency-free:

```text
sidecar packet event
+ semantic typed projection
-> FleetRmwProjectedSample
-> quality payload / qualified payload / future RMW sample metadata
-> ROS 2 egress adapter or another data plane
```

The goal is to define the contract a future `rmw_fleetrmw` path must preserve:
after admission, every projected sample has stable identity, timing, admission
provenance, fidelity, lossiness, and task context.

V1.1 adds an end-to-end `contract_id`: the ID is generated at the ROS
shim/ingress boundary, copied through the sidecar packet event, and preserved in
projection quality plus qualified wrapper payloads.

V1.2 adds `source_sample_id`: when the original ROS/RMW sample exposes source
metadata, FleetRMW derives a stable source identity that is distinct from the
admission contract ID.  The current derivation accepts application-level
`header.stamp`/`frame_id` and RMW-facing source metadata such as
`publisher_gid`, publication sequence number, and source timestamp.  When
source metadata is not available, `source_sample_id` falls back to the
generated `contract_id`.

V1.3 adds `FleetRmwSampleEnvelope`: a native source-side envelope with
FleetRMW-owned `publisher_id`, `source_sample_id`, source sequence, and source
/ receive timestamps.  This is the contract a future non-DDS RMW should own
directly, because the measured `rclpy` metadata path does not expose publisher
GID consistently and does not expose sequence number for every RMW.

## New Code

- `fleetqox/rmw_contract.py`
  - `FleetRmwSampleEnvelope`: native pre-admission source envelope for publisher
    identity, source sample identity, source sequence, and timestamps.
  - `FleetRmwSampleIdentity`: event, robot, flow, source topic, projection kind,
    projection topic/type, contract ID, source sample ID, and canonical
    signature.
  - `FleetRmwDeliveryContract`: action, wire mode, deadline/lifespan/freshness,
    task context, reconstruction mode, fidelity class, downsampling, and
    degradation reasons.
  - `FleetRmwProjectedSample`: binds identity, delivery contract, and projected
    sample payload.
  - `projected_sample_from_sidecar_event`: builds the contract from sidecar
    admission output plus a typed projection.
  - `typed_projection_payload_base`: shared typed projection metadata builder.
- `fleetqox/ros2_shim.py` and `fleetqox/ros2_live_bridge.py`
  - Carry publisher GID, sequence number, source timestamp, and received
    timestamp from live ROS 2 callbacks or replay records into the sidecar
    batch when available.
  - Preserve a native `sample_envelope` when supplied, and prefer it over
    opportunistic callback metadata.
- `fleetqox/sidecar_egress.py`
  - Delegates quality and qualified payload construction to `rmw_contract.py`.
  - Keeps the old function names as compatibility wrappers for existing tests
    and scripts.
- `tests/test_rmw_contract.py`
  - Verifies stable signature generation, compact quality payloads, qualified
    sample binding, downsampled scan fidelity, and schema boundaries.

## Contract Layers

| layer | schema | role |
| --- | --- | --- |
| sample envelope | `fleetrmw.sample_envelope.v1` | native source publisher/sample identity before admission |
| typed projection | `fleetrmw.typed_projection.v1` | ROS-facing reconstructed sample payload |
| sample contract | `fleetrmw.rmw_sample_contract.v1` | identity plus delivery/fidelity contract |
| projection quality | `fleetrmw.projection_quality.v1` | ROS message-friendly quality view |
| qualified projection | `fleetrmw.qualified_projection.v1` | sample plus quality bound together |

This is not yet a full RMW implementation.  It is the minimum contract surface
needed so the same semantics can later move from application-level local topics
into RMW sample metadata or a non-DDS data plane without rewriting the control
plane.

## Current Invariant

In Docker T3 wrapper mode, egress does not publish bare state/perception topics.
It publishes only:

- `QualifiedOdometry` for odometry;
- `QualifiedLaserScan` for laser scan;
- `accepted_odom` and `accepted_scan` after the consumer-side quality gate.

That means local state/perception consumers cannot bypass the quality gate by
subscribing to an unqualified egress topic in the default path.

## Contract ID Path

```text
Ros2Sample
-> optional FleetRmwSampleEnvelope("publisher_id": "fpub1-...", "source_sample_id": "fsid1-...")
-> Ros2SidecarAdapter.build_batch(... "source_metadata": {...})
-> Ros2SidecarAdapter.build_batch(... "sample_envelope": {...})
-> Ros2SidecarAdapter.build_batch(... "contract_id": "fcid1-...")
-> Ros2SidecarAdapter.build_batch(... "source_sample_id": "fsid1-...")
-> SidecarRuntime.build_sidecar_event(... IDs ...)
-> FleetRmwProjectedSample.identity.contract_id/source_sample_id
-> ProjectionQuality.identity.contract_id/source_sample_id
-> QualifiedOdometry/QualifiedLaserScan.quality.identity.*
-> projection quality gate decision log
```

`Ros2SidecarAdapter` generates deterministic IDs when the input sample does not
already provide one.  Explicit IDs are preserved, which lets future RMW or
rosbag/replay tooling inject stronger source-level sample identity.

The key distinction is:

| ID | meaning |
| --- | --- |
| `source_sample_id` | identity of the original source sample, derived from header stamp or RMW source metadata when available |
| `contract_id` | identity of the FleetRMW admission/delivery contract for that sample in a scenario/tick/flow context |

The same source sample can therefore keep the same `source_sample_id` while
getting a different `contract_id` under a different admission context.

## Verification

```text
python3 -m unittest discover -s tests
Ran 202 tests - OK
```

Docker T3 source-sample-ID smoke:

```text
scenario: ros2_live_bridge_t3_source_sample_id_v1
egress UDP packets: 76
qualified egress publications: 19 QualifiedOdometry, 19 QualifiedLaserScan
quality gate statuses: 38 accept
contract IDs in gate log: 38/38 non-empty, 38 unique
source sample IDs in gate log: 38/38 non-empty, 38 unique
decision-to-qualified contract ID matches: 38/38 received qualified samples
decision-to-qualified source sample ID matches: 38/38 received qualified samples
control delivery: 1.0000
loss: 0.0000
deadline miss: 0.0000
p95 latency: 60.46 ms
```

Every qualified sample that reached egress preserved both its sidecar
`contract_id` and its source-derived `source_sample_id` through the wrapper and
quality-gate log.  This makes the wrapper path distinguish admission/delivery
identity from original ROS/RMW-visible sample identity.

Docker T3 source-metadata smoke:

```text
scenario: ros2_live_bridge_t3_source_metadata_v2
sidecar packet decisions: 66/66 carried source_metadata
source metadata fields: 66 sequence_number, 66 source_timestamp_ns, 66 received_timestamp_ns, 0 publisher_gid
egress UDP packets: 64
qualified egress publications: 18 QualifiedOdometry, 15 QualifiedLaserScan
quality gate statuses: 32 accept, 1 drop_projection
contract IDs in gate log: 33/33 non-empty, 33 unique
source sample IDs in gate log: 33/33 non-empty, 33 unique
decision-to-qualified contract ID matches: 33/33 received qualified samples
decision-to-qualified source sample ID matches: 33/33 received qualified samples
control delivery: 0.9375
loss: 0.0303
deadline miss: 0.0000
p95 latency: 61.86 ms
```

This run validates the live `rclpy` `MessageInfo` path for sequence and
timestamp metadata.

Docker T3 cross-RMW source-metadata matrix:

```text
scenario: ros2_live_bridge_t3_rmw_metadata_v2
rmw_fastrtps_cpp: packets=76 metadata=76 publisher_gid=0 sequence_number=76 source_timestamp_ns=76 received_timestamp_ns=76 gate=38/38 accept
rmw_cyclonedds_cpp: packets=80 metadata=80 publisher_gid=0 sequence_number=0 source_timestamp_ns=80 received_timestamp_ns=80 gate=40/40 accept
rmw_zenoh_cpp: packets=73 metadata=73 publisher_gid=0 sequence_number=73 source_timestamp_ns=73 received_timestamp_ns=73 gate=36/36 accept
```

This matrix proves that timestamps are portable through the current callback
path, but sequence number is RMW-dependent and publisher GID is not exposed by
the observed `rclpy` surface for Fast DDS, CycloneDDS, or Zenoh RMW.  The
source-sample derivation must therefore accept partial metadata and a future
native FleetRMW data plane must supply publisher identity itself.

## Remaining Gap

The contract, contract ID, and source-sample identity now exist outside the
egress bridge, but the transport boundary is still a sidecar UDP packet plus
ROS-local wrapper topics.  The next step is to make this source identity
production-grade:

- stop depending on `rclpy` for publisher identity, because the matrix did not
  expose `publisher_gid` through any tested RMW;
- keep sequence number optional at the bridge boundary, because CycloneDDS did
  not expose it through the observed callback metadata;
- push `FleetRmwSampleEnvelope` into the future publish/take path so publisher
  identity and source sequence are native middleware fields;
- make egress reject malformed IDs for wrapper mode once all ingress paths can
  provide at least explicit, header-derived, timestamp-derived, or native-RMW
  source identity;
- store this contract as RMW sample metadata instead of application-level JSON
  in a future `rmw_fleetrmw` implementation.

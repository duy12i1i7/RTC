# FleetRMW Sample Envelope V1

## Purpose

The cross-RMW metadata matrix showed that `rclpy` callback metadata is useful
but not sufficient as a foundation for a future non-DDS RMW:

- timestamps were portable across Fast DDS, CycloneDDS, and Zenoh RMW;
- sequence number was absent for CycloneDDS in this path;
- publisher GID was absent for all three tested RMWs.

`FleetRmwSampleEnvelope` is the first native FleetRMW answer to that gap.  It
defines the identity material a real `rmw_fleetrmw` data plane should own
instead of hoping that a Python callback exposes DDS-specific fields.

## Schema

```json
{
  "schema_version": "fleetrmw.sample_envelope.v1",
  "publisher_id": "fpub1-native-controller",
  "source_sample_id": "fsid1-...",
  "robot_id": "robot_0000",
  "topic": "/robot_0000/cmd_vel",
  "msg_type": "geometry_msgs/msg/Twist",
  "source_sequence_number": 700,
  "source_timestamp_ns": 555000,
  "received_timestamp_ns": 555100,
  "rmw_implementation": "rmw_fleetrmw_cpp"
}
```

The envelope is source-side metadata.  It is intentionally separate from the
post-admission `contract_id`:

| field | meaning |
| --- | --- |
| `publisher_id` | FleetRMW-native publisher endpoint identity |
| `source_sample_id` | identity of the original published sample |
| `source_sequence_number` | monotonic sequence for a publisher endpoint |
| `source_timestamp_ns` | source-side publication time |
| `received_timestamp_ns` | ingress receive time |
| `contract_id` | separate admission/delivery contract created after policy decision |

This separation matters because one source sample may be admitted differently
under different network, task, or QoE states.  The source identity should remain
stable; the contract identity may change.

## Code Path

Implemented code:

- `fleetqox/rmw_contract.py`
  - `FleetRmwSampleEnvelope`;
  - `publisher_id_for_fields`;
  - `sample_envelope_for_fields`;
  - `sample_envelope_from_payload`.
- `fleetqox/ros2_shim.py`
  - `Ros2Sample.sample_envelope`;
  - native envelope precedence over opportunistic callback metadata;
  - compatibility `source_metadata` view generated from the envelope.
- `fleetqox/sidecar_runtime.py`
  - preserves `sample_envelope` in sidecar decision/packet events.

The current sidecar still accepts old `source_metadata` for bridge mode.  When
`sample_envelope` exists, it is the stronger identity source and is propagated
alongside the compatibility metadata.

## Current Invariant

The native envelope must provide at least one per-sample identity source:

- explicit `source_sample_id`; or
- `source_sequence_number`; or
- `source_timestamp_ns`.

It is invalid to derive a sample identity from publisher identity alone, because
that would collide across multiple samples from the same publisher.

## Verification

```text
python3 -m unittest tests.test_rmw_contract tests.test_ros2_shim
Ran 22 tests - OK

python3 -m unittest discover -s tests
Ran 202 tests - OK
```

The new tests cover:

- native publisher/sample ID generation without DDS publisher GID;
- payload parsing with missing derived IDs;
- `sample_envelope` precedence over callback `publisher_gid`/sequence metadata;
- sidecar event propagation of the native envelope.

## Research Consequence

This shifts the project from "extract what each RMW happens to expose" toward a
stronger middleware design: FleetRMW owns publisher identity and sample identity
as first-class data-plane fields.

The next RMW implementation target should make the envelope part of the publish
and take path, then keep ROS 2 application APIs unchanged above it.

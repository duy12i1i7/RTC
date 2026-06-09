# Sidecar Decision Trace Schema

FleetRMW uses JSONL traces as the bridge between ROS/FleetQoX workloads,
sidecar/RMW-shim policy decisions, and network simulators such as ns-3 and
OMNeT++.

The schema is a contract: a future ROS 2 sidecar or RMW shim should be able to
emit the same fields before handing bytes to UDP/QUIC/TCP/Zenoh-like data
planes. Each row is either a packet that should be injected into a network
simulator or a non-sent decision that can be used for scheduler analysis.

For a production data plane, `FLEETRMW_DATA_FRAME_V1.md` narrows this log/event
schema into a transport frame.  The trace keeps policy/debug fields; the frame
keeps source identity, admission contract, route, timing, and payload fields.

## Event Types

```text
packet    A message admitted by a policy and ready for network simulation.
decision  A defer/drop decision, emitted only when requested.
```

## Required Fields

```json
{
  "schema_version": "fleetrmw.sidecar.trace.v1",
  "event_type": "packet",
  "experiment": "fleetrmw_sidecar_contract",
  "scenario": "warehouse_100_constrained",
  "policy": "fleetqox_predictive",
  "contract_id": "fcid1-8cfd6c6a2d0a43f3b7d1c0c31a2e0001",
  "source_sample_id": "fsid1-63e7d9b6f1a30c497b5e0fa67aeb0010",
  "source_metadata": {
    "publisher_id": "fpub1-7a2c8f5d1b1e4b2a9f5f1d23a0e10001",
    "sequence_number": 42,
    "source_timestamp_ns": 123456789
  },
  "sample_envelope": {
    "schema_version": "fleetrmw.sample_envelope.v1",
    "publisher_id": "fpub1-7a2c8f5d1b1e4b2a9f5f1d23a0e10001",
    "source_sample_id": "fsid1-63e7d9b6f1a30c497b5e0fa67aeb0010",
    "robot_id": "robot_0042",
    "topic": "/fleet_state",
    "msg_type": "nav_msgs/msg/Odometry",
    "source_sequence_number": 42,
    "source_timestamp_ns": 123456789,
    "received_timestamp_ns": 123456999
  },
  "timestamp_ms": 150.0,
  "tick": 3,
  "flow_id": "robot_0042:state",
  "flow_class": "state",
  "topic": "/fleet_state",
  "robot_id": "robot_0042",
  "src": "robot_0042",
  "dst": "fleet_router",
  "action": "send_compacted",
  "bytes": 96,
  "original_bytes": 176,
  "degraded": false,
  "deadline_ms": 120,
  "lifespan_ms": 350,
  "qos_reliability": "reliable",
  "reliability": "best_effort_fresh",
  "wire_mode": "semantic_delta",
  "predicted_slack_ms": 80.0,
  "reason": "predictive admission: semantic compaction",
  "priority": 10.5,
  "semantic_utility": 6.2,
  "task_criticality": 0.9,
  "collision_risk": 0.4,
  "operator_attention": 0.0,
  "coordination_pressure": 0.2,
  "link_capacity_bytes_per_tick": 30000,
  "link_loss": 0.04,
  "link_jitter_ms": 8.0,
  "link_rtt_ms": 22.0
}
```

## Simulator Mapping

For ns-3 or OMNeT++:

- `timestamp_ms` becomes packet generation time;
- `contract_id`, when present, links the shim-visible sample, sidecar decision,
  network packet, projection quality, and accepted local delivery log;
- `source_sample_id`, when present, identifies the original ROS/RMW-visible
  sample independently of the FleetRMW admission contract;
- `source_metadata`, when present, records the RMW-facing identity material used
  to derive `source_sample_id`: FleetRMW publisher ID, optional DDS publisher
  GID, sequence number, and timestamps;
- `sample_envelope`, when present, is the stronger native FleetRMW source
  envelope that a future non-DDS RMW should emit before policy/admission;
- `src` and `dst` become application endpoint nodes;
- `bytes` becomes payload size;
- `original_bytes` preserves native ROS payload cost before sidecar shaping;
- `flow_class` maps to traffic class / queue / DSCP / access category;
- `deadline_ms` and `lifespan_ms` define packet utility windows;
- `qos_reliability` records the ROS-facing QoS request;
- `reliability` records the transport decision after adaptive policy;
- `wire_mode` records whether the sidecar used native bytes, semantic delta,
  degraded bytes, control intent, or supervisory intent;
- `policy` identifies the scheduler baseline;
- `semantic_utility` is used for post-simulation QoT analysis.

## Actions

```text
send            Native payload is admitted.
send_degraded   Opportunistic payload is admitted in degraded form.
send_compacted  Core payload is admitted as semantic delta.
send_intent     Control is admitted as a path-aware command horizon.
send_supervisory_intent
                Control is admitted as a longer goal/constraint lease.
defer           Sample stays queued.
drop            Sample is intentionally dropped.
```

Only admitted `send*` actions become `packet` rows. `defer` and `drop` become
`decision` rows when non-sent decisions are exported.

## Lightweight Replay

The built-in replay can evaluate the exported CSV without ns-3:

```bash
python3 -m scripts.export_traces --scenario warehouse_50_constrained --format csv --policy fleetqox_predictive
python3 -m scripts.replay_trace traces/warehouse_50_constrained.csv \
  --transport-model udp_like \
  --queue-policy class_priority
python3 -m scripts.replay_trace traces/warehouse_50_constrained.csv \
  --transport-model adaptive_reliability \
  --queue-policy class_priority
```

## Why Include Non-Sent Decisions?

Network simulators only need `packet` rows. However, `decision` rows are useful
for analyzing whether a policy protected control traffic by admission control or
merely pushed congestion into the simulator. They can be enabled with
`--include-non-sent`.

# FleetRMW Data Frame V1

## Purpose

`FleetRmwSampleEnvelope` defines native source identity.  `FleetRMW Data Frame`
defines how that identity travels across a future non-DDS data plane.

The current Docker T3 sidecar still emits padded JSON packet events so the ROS
2 bridge remains stable by default.  The data-frame path is now available as
an opt-in runtime mode so the same T3 harness can be switched to frame bytes
without changing the ROS-facing application behavior.

## Frame Shape

The codec lives in `fleetqox/rmw_frame.py`.

```json
{
  "schema_version": "fleetrmw.data_frame.v1",
  "kind": "sidecar_packet_frame",
  "frame_id": "ffrm1-...",
  "event_id": 9,
  "contract": {
    "contract_id": "fcid1-...",
    "source_sample_id": "fsid1-...",
    "policy": "fleetqox_semantic_contract_adaptive",
    "scenario": "frame_test"
  },
  "route": {
    "src": "robot_0000",
    "dst": "fleet_controller",
    "robot_id": "robot_0000",
    "flow_id": "robot_0000:state",
    "flow_class": "state",
    "topic": "/robot_0000/odom",
    "source_msg_type": "nav_msgs/msg/Odometry"
  },
  "delivery": {
    "action": "send",
    "wire_mode": "native",
    "reliability": "reliable",
    "deadline_ms": 120.0,
    "lifespan_ms": 350.0,
    "bytes": 512,
    "original_bytes": 320
  },
  "timing": {
    "timestamp_ms": 10.0,
    "tick": 3,
    "age_ms": 4.0,
    "predicted_slack_ms": 40.0
  },
  "sample_envelope": {
    "schema_version": "fleetrmw.sample_envelope.v1",
    "publisher_id": "fpub1-native",
    "source_sample_id": "fsid1-...",
    "source_sequence_number": 42,
    "source_timestamp_ns": 123000
  },
  "semantic_payload": {
    "msg_type": "nav_msgs/msg/Odometry"
  }
}
```

The byte encoding starts with:

```text
FRMW1\n
```

followed by canonical JSON.  Optional padding is supported so packet-size
experiments can continue to model allocated wire bytes.

## Service Frame

`rmw_fleetqox_cpp` uses a sibling frame, `fleetrmw.service_frame.v1`, for ROS 2
service request/response traffic. It keeps RPC traffic separate from topic
samples while reusing the same `FRMW1\n` magic prefix and hex payload convention.

```json
{
  "schema_version": "fleetrmw.service_frame.v1",
  "kind": "service_frame",
  "role": "request",
  "service_name": "/fleetqox/set_bool",
  "type_name": "std_srvs/srv/SetBool",
  "client_endpoint_id": "127.0.0.1:48291|fclicpp-1",
  "service_endpoint_id": "",
  "sequence_id": 1,
  "source_timestamp_ns": 123000,
  "serialized_payload": {
    "encoding": "hex",
    "size": 1,
    "data": "01"
  }
}
```

Responses use `"role": "response"` and carry the same `client_endpoint_id` plus
the matching `sequence_id`, allowing the client queue to filter responses
without relying on DDS service topics.

## ACK/NACK Frame

`fleetrmw.ack_nack.v1` records receiver-side source sequence state for a data
frame stream. In `rmw_fleetqox_cpp`, subscriptions emit this feedback after
observing each data frame; publishers use missing ranges to retransmit retained
encoded frames from their source-sequence ledger.

```json
{
  "schema_version": "fleetrmw.ack_nack.v1",
  "kind": "source_sequence_ack_nack",
  "robot_id": "local",
  "source_topic": "/fleetqox/reliability_probe",
  "stream_key": [
    "source_stream",
    "local",
    "/fleetqox/reliability_probe",
    "fpubcpp-1"
  ],
  "ack": {
    "source_sequence_number": 3,
    "source_timestamp_ns": 123000
  },
  "nack": {
    "missing_sequence_ranges": [[2, 2]]
  },
  "state": {
    "highest_contiguous_sequence": 1,
    "highest_observed_sequence": 3,
    "duplicate": false,
    "out_of_order": false
  }
}
```

## Why This Is Different From Sidecar Event JSON

Sidecar events are logs and simulator inputs.  They contain policy reasoning,
link estimates, utility scores, and debugging fields.

Data frames are transport objects.  They keep only the fields that should cross
a real middleware data plane:

- source identity and sample envelope;
- admission/delivery contract;
- route and flow class;
- QoX fields needed by the current compatibility egress path;
- timing/deadline fields;
- semantic payload or future serialized payload reference.

That separation is important for `rmw_fleetrmw`: the RMW should not have to
parse a research log record to deliver a sample.

## Verification

```text
python3 -m unittest tests.test_rmw_frame tests.test_udp_trace_receiver tests.test_sidecar_egress tests.test_sidecar_runtime
Ran 33 tests - OK

python3 -m unittest discover -s tests
Ran 202 tests - OK
```

The tests cover:

- converting a sidecar packet event into a data frame;
- reconstructing the sidecar event view needed by the existing egress router;
- preserving `contract_id`, `source_sample_id`, and native `sample_envelope`;
- stable `ffrm1-*` frame IDs;
- magic-prefixed frame encode/decode with packet padding;
- rejecting non-frame bytes and wrong schema versions;
- sidecar UDP emission in `packet_format=data_frame` mode;
- egress auto-detection of both legacy JSON packets and data-frame packets;
- UDP trace receiver decoding of both legacy JSON and data-frame packets,
  including `send_monotonic_ns` for latency metrics.

Docker T3 frame-mode smoke:

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
source metadata fields: 73 sequence_number, 73 source_timestamp_ns, 73 received_timestamp_ns, 0 publisher_gid
control delivery: 1.0000
loss: 0.0274
p95 latency: 37.35 ms
deadline miss: 0.0000
```

Docker T3 cross-RMW frame-mode matrix:

```text
scenario: ros2_live_bridge_t3_data_frame_rmw_matrix_v1
rmw_fastrtps_cpp: tx=78 rx=78 loss=0.0000 control_delivery=1.0000 p95=44.98 ms gate=39/39 contract/source match=39/39
rmw_cyclonedds_cpp: tx=73 rx=72 loss=0.0137 control_delivery=1.0000 p95=37.50 ms gate=36/36 contract/source match=36/36
rmw_zenoh_cpp: tx=70 rx=69 loss=0.0143 control_delivery=1.0000 p95=30.90 ms gate=34/34 contract/source match=34/34
```

Docker T3 packet-format comparison on Fast DDS:

```text
scenario: ros2_live_bridge_t3_packet_format_compare_v1
event_json: tx=80 rx=80 loss=0.0000 control_delivery=1.0000 p95=50.02 ms gate=40/40 contract/source match=40/40
data_frame: tx=80 rx=80 loss=0.0000 control_delivery=1.0000 p95=40.87 ms gate=40/40 contract/source match=40/40
```

Docker T3 packet-format/RMW matrix:

```text
scenario: ros2_live_bridge_t3_packet_format_rmw_matrix_v1
event_json rmw_fastrtps_cpp: tx=68 rx=67 loss=0.0147 control_delivery=0.9412 p95=59.04 ms gate=35/35 contract/source match=35/35
event_json rmw_cyclonedds_cpp: tx=80 rx=78 loss=0.0250 control_delivery=0.9500 p95=50.72 ms gate=38/39 contract/source match=39/39
event_json rmw_zenoh_cpp: tx=77 rx=77 loss=0.0000 control_delivery=1.0000 p95=32.60 ms gate=38/38 contract/source match=38/38
data_frame rmw_fastrtps_cpp: tx=72 rx=72 loss=0.0000 control_delivery=1.0000 p95=58.77 ms gate=36/36 contract/source match=36/36
data_frame rmw_cyclonedds_cpp: tx=76 rx=75 loss=0.0132 control_delivery=0.9474 p95=58.17 ms gate=37/38 contract/source match=38/38
data_frame rmw_zenoh_cpp: tx=78 rx=78 loss=0.0000 control_delivery=1.0000 p95=34.98 ms gate=39/39 contract/source match=39/39
```

Repeated-harness smoke:

```text
scenario: ros2_live_bridge_t3_repeated_packet_smoke_v1
event_json/rmw_fastrtps_cpp: runs=1 rx=80 loss=0.0000 control_delivery=1.0000 p95=47.49 ms
data_frame/rmw_fastrtps_cpp: runs=1 rx=74 loss=0.0263 control_delivery=1.0000 p95=42.04 ms
```

Repeated Wi-Fi packet-format/RMW matrix:

```text
scenario: ros2_live_bridge_t3_repeated_packet_wifi_3seed_v1
statuses: 18 ran / 18 planned
invalid egress packets: 0 in all 18 runs
pareto frontier: data_frame/rmw_zenoh_cpp
data_frame/rmw_zenoh_cpp: runs=3 utility=458.2 control_delivery=1.0000 loss=0.0173 p95=38.27 ms
event_json/rmw_cyclonedds_cpp: runs=3 utility=456.8 control_delivery=0.9482 loss=0.0176 p95=62.69 ms
```

Repeated WAN packet-format/RMW matrix:

```text
scenario: ros2_live_bridge_t3_repeated_packet_wan_3seed_v1
statuses: 18 ran / 18 planned
invalid egress packets: 0 in all 18 runs
pareto frontier: event_json/rmw_zenoh_cpp, data_frame/rmw_zenoh_cpp, event_json/rmw_fastrtps_cpp, data_frame/rmw_cyclonedds_cpp, event_json/rmw_cyclonedds_cpp
event_json/rmw_zenoh_cpp: runs=3 utility=342.5 control_delivery=1.0000 loss=0.0365 p95=111.19 ms
data_frame/rmw_cyclonedds_cpp: runs=3 utility=284.6 control_delivery=1.0000 loss=0.0271 p95=131.51 ms
```

Repeated roaming packet-format/RMW matrix:

```text
scenario: ros2_live_bridge_t3_repeated_packet_roaming_3seed_v1
statuses: 18 ran / 18 planned
invalid egress packets: 0 in all 18 runs
pareto frontier: event_json/rmw_zenoh_cpp, data_frame/rmw_cyclonedds_cpp, event_json/rmw_cyclonedds_cpp, data_frame/rmw_fastrtps_cpp, event_json/rmw_fastrtps_cpp
event_json/rmw_zenoh_cpp: runs=3 utility=248.5 control_delivery=0.9667 loss=0.0645 p95=162.60 ms
data_frame/rmw_cyclonedds_cpp: runs=3 utility=242.8 control_delivery=0.9188 loss=0.0487 p95=199.81 ms
data_frame/rmw_zenoh_cpp: runs=3 utility=240.0 control_delivery=0.9048 loss=0.0805 p95=158.59 ms pareto=no
```

## Runtime Usage

The sidecar remains compatible with legacy JSON by default:

```bash
python3 -m scripts.run_sidecar_runtime --packet-format event_json
```

To emit data-frame bytes:

```bash
python3 -m scripts.run_sidecar_runtime --packet-format data_frame
```

The Docker T3 harness exposes the same switch:

```bash
python3 -m scripts.run_ros2_docker_live_bridge \
  --run \
  --analyze \
  --packet-format data_frame \
  --scenario ros2_live_bridge_t3_data_frame_v1
```

To compare legacy JSON and data-frame packets in the same harness:

```bash
python3 -m scripts.run_ros2_docker_live_bridge \
  --run \
  --analyze \
  --packet-format-matrix \
  --scenario ros2_live_bridge_t3_packet_format_compare_v1
```

The egress bridge can decode both formats during the transition.

## Next Step

The repeated Wi-Fi, WAN, and roaming cross-RMW matrices have now run.  Wi-Fi
identifies `data_frame/rmw_zenoh_cpp` as the non-dominated operating point, WAN
keeps five combinations on the Pareto frontier, and roaming changes the
frontier again while removing `data_frame/rmw_zenoh_cpp` from the reporter's
current objective set.  The next step is to move the frame boundary closer to a
minimal `rmw_fleetrmw_cpp` publish/take path with an explicit profile-aware,
objective-aware transport/representation selector.

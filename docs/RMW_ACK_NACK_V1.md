# FleetRMW ACK/NACK V1

## Purpose

The 8-robot ROS 2 live bridge now shows a precise boundary: feedback cadence and
ACK delivery are part of the transport problem, not a sidecar tuning detail.
Immediate ACK overloads the feedback path, fixed ACK windows regress across
seeds, and piggyback-first adaptive ACK is the best repeated result so far but
still failed seed `13` until retransmission memory was tied to the source QoS
liveliness contract.

This document records the first dependency-free RMW-facing ACK/NACK primitive.
It keeps the ROS mindset, but moves the reliability identity away from
sidecar-local event IDs and toward source sample/sequence identity.

## Implemented Primitive

Implemented in `fleetqox/rmw_ack.py`:

- `fleetrmw.ack_nack.v1` feedback payloads;
- stable `fack1-*` ACK/NACK IDs;
- per-stream source sequence tracking through `RmwAckNackTracker`;
- ACK fields for `source_sample_id`, `source_sequence_number`, source timestamp,
  receiver timestamp, and the legacy event ID when available;
- NACK fields as compact `missing_sequence_ranges`;
- state fields for highest contiguous sequence, highest observed sequence,
  duplicate, and out-of-order samples.

The stream key is:

```text
("source_stream", robot_id, source_topic[, publisher_id])
```

Publisher identity is used when present.  Otherwise the tracker falls back to
robot ID plus source topic or flow ID.

## Runtime Bridge

The sidecar ACK retransmit tracker now has two compatible clear paths:

- legacy `(robot_id, event_id)` ACK;
- source-aware ACK using `source_sample_id` or
  `(robot_id, source_topic, source_sequence_number)`.
- source-sequence NACK gaps using `missing_sequence_ranges`, which request
  retransmission for matching unacked control-lease events still present in the
  source index.

This means the ROS 2 egress bridge can already clear retransmit state using the
same source sequence fields a future `rmw_fleetqox_cpp` publish/take boundary
should own.

The ROS 2 egress bridge now also runs `RmwAckNackTracker` over receiver-side
feedback records.  Regular feedback windows piggyback `fleetrmw.ack_nack.v1`
records, including compact NACK gaps when the receiver observes out-of-order
source sequences.

The sidecar runtime now keeps ACK/NACK retransmit history for a bounded recovery
horizon rather than a fixed small FIFO.  That horizon is derived from source
deadline, measured RTT/jitter, and `liveliness_lease_ms`; with the default ROS
QoS liveliness lease of `500 ms`, control-lease recovery memory spans `2000 ms`.
Control and supervisory-intent events also carry an effective wire lifespan
that is at least the semantic feasibility deadline, while preserving the raw ROS
source lifespan as `source_lifespan_ms`.

## Current Evidence

Unit coverage:

- `tests/test_rmw_ack.py`;
- `tests/test_rmw_boundary.py`;
- `tests/test_rmw_boundary_smoke.py`;
- `tests/test_sidecar_runtime.py::test_control_lease_ack_feedback_can_clear_by_source_sequence`;
- `tests/test_sidecar_runtime.py::test_control_lease_ack_nack_gap_requests_source_sequence_retransmit`;
- `tests/test_sidecar_runtime.py::test_ack_history_keeps_horizon_for_late_sequence_nack`;
- `tests/test_sidecar_egress.py::test_control_lease_feedback_and_ack_carry_source_identity`.
- `tests/test_sidecar_egress.py::test_feedback_window_piggybacks_ack_nack_gap_records`.

Minimal boundary smoke:

```bash
python3 -m scripts.run_rmw_boundary_smoke \
  --robot-count 2 \
  --samples-per-robot 3 \
  --skip-take robot_0000:2 \
  --json
```

The smoke publishes `6` FleetRMW data frames, takes `5`, and reports one missing
source-sequence range for the intentionally skipped `robot_0000:2` sample.

Live ACK/NACK progression:

| run | hard budget | control | loss | p95 ms | min robot control | quality |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| `n_robot_qoe_recovery_quota_8robot_adaptive_ack_piggyback_3seed_summary.json` | `2/3` | `0.9689` | `0.0358` | `1651.42` | `0.9500` | `1.0000` |
| `n_robot_qoe_recovery_quota_8robot_egress_acknack_seed13_aggregate_summary.json` | `0/1` | `0.9444` | `0.0663` | `2012.22` | `0.8889` | `1.0000` |
| `n_robot_qoe_recovery_quota_8robot_liveliness_horizon_seed13_aggregate_summary.json` | `1/1` | `0.9830` | `0.0253` | `1731.48` | `0.9545` | `1.0000` |
| `n_robot_qoe_recovery_quota_8robot_liveliness_horizon_3seed_aggregate_summary.json` | `3/3` | `0.9902` | `0.0311` | `1085.30` | `0.9804` | `1.0000` |

This closes the first repeated `8`-robot hard control-floor claim for the ROS 2
sidecar bridge.  It also rejects a tempting but wrong design: urgent NACKs sent
outside feedback backpressure produce a feedback storm and collapse delivery.
Useful recovery requires source-sequence gaps plus enough bounded sender-side
memory for late receiver feedback to arrive.

## Next RMW Step

The dependency-free publish/take boundary is now implemented in
`fleetqox/rmw_boundary.py` and documented in `docs/RMW_MINIMAL_BOUNDARY_V1.md`.
The Python runtime consumes `fleetrmw.ack_nack.v1` NACK gaps for tracked
control-lease retransmission, and the ROS 2 egress bridge has now proved the
same mechanism in the repeated `8`-robot live scale harness.  The next
implementation step is to harden this exact contract inside the new socket
boundary:

1. keep `fleetqox/rmw_transport_loop.py` and
   `ros2_ws/src/rmw_fleetqox_cpp` aligned as Python and C++ executable
   references for retransmission semantics;
2. preserve liveliness-backed recovery horizon metadata across C++ publish/take
   and replay decisions;
3. replace the C++ transport smoke with real `rmw_fleetqox_cpp` ABI entry
   points;
4. keep the `8`-robot Wi-Fi/WAN/roaming matrix as the regression gate before
   adding `16` robots.

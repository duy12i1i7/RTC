# ROS 2 8-Robot Liveliness ACK Horizon V1

## Purpose

This milestone closes the first repeated `8`-robot hard-SLO gap in the ROS 2
live bridge.  Earlier rows showed that control-lease redundancy, persistent
feedback clients, fixed ACK windows, and piggyback-first ACKs were necessary but
not sufficient: seed `13` could still lose early per-robot control leases during
Wi-Fi/WAN/roaming transition pressure.

The key finding is that retransmission memory is part of the transport QoS
contract.  A source-sequence NACK can only repair loss if the sender still keeps
the source event in a bounded recovery ledger when the NACK arrives.

## Implemented Mechanism

Implemented in `fleetqox/sidecar_runtime.py`:

- `effective_lifespan_ms(...)` lifts the wire lease for `control_intent` and
  `supervisory_intent` to the feasibility-adjusted deadline when the semantic
  transform makes the raw ROS QoS lifespan too short.
- Sidecar events now carry both `lifespan_ms` and `source_lifespan_ms`, plus the
  ROS QoS-derived `liveliness_lease_ms`.
- ACK/NACK retransmit history is no longer a fixed small per-robot FIFO.  The
  history limit is derived from a recovery horizon divided by source deadline,
  capped to avoid unbounded memory growth.
- The recovery horizon includes deadline, measured RTT/jitter, and the ROS
  liveliness lease.  With the default `500 ms` liveliness lease, the control
  recovery horizon becomes `2000 ms`, long enough for late feedback during
  roaming without creating immediate-ACK feedback storms.

The egress bridge keeps ACK/NACK backpressured and piggyback-first.  The
negative urgent-NACK variants were intentionally removed: sending NACK outside
the existing feedback pacing overloaded the sidecar feedback path and collapsed
delivery.

## Evidence

Unit and smoke coverage:

```bash
python3 -m unittest discover tests
```

Result:

```text
Ran 344 tests in 3.949s
OK
```

Single-seed audit after liveliness-backed history:

| artifact | seed | hard budget | control | min robot control | deadline | worst deadline | p95 ms | quality |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| `n_robot_qoe_recovery_quota_8robot_liveliness_horizon_seed13_aggregate_summary.json` | `13` | `1/1` | `0.9830` | `0.9545` | `0.1036` | `0.1600` | `1731.48` | `1.0000` |

Repeated audit:

| artifact | seeds | hard budget | control | min robot control | deadline | worst deadline | p95 ms | rx | quality |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| `n_robot_qoe_recovery_quota_8robot_liveliness_horizon_3seed_aggregate_summary.json` | `7,13,29` | `3/3` | `0.9902` | `0.9804` | `0.1296` | `0.1659` | `1085.30` | `136.00` | `1.0000` |

Per-seed repeated audit:

| seed | pass | control | min robot control | deadline | worst deadline | p95 ms | rx |
| ---: | --- | ---: | ---: | ---: | ---: | ---: | ---: |
| `7` | yes | `1.0000` | `1.0000` | `0.1087` | `0.1176` | `1441.50` | `138` |
| `13` | yes | `1.0000` | `1.0000` | `0.1721` | `0.2222` | `999.61` | `122` |
| `29` | yes | `0.9706` | `0.9412` | `0.1081` | `0.1579` | `814.80` | `148` |

## Interpretation

The result is not "more ACKs".  It is a bounded source-sequence recovery
contract:

```text
source QoS/liveliness
-> semantic feasibility deadline
-> effective wire lifespan
-> liveliness-backed retransmit horizon
-> source-sequence ACK/NACK repair
-> robot-local lease authority
```

This separates three responsibilities that were previously mixed:

- ROS QoS expresses source intent and liveliness.
- FleetQoX semantic transforms determine whether a short raw lifespan is still
  physically feasible over the current link.
- FleetRMW transport memory keeps useful control leases repairable long enough
  for backpressured receiver feedback to arrive.

## Remaining Gap

This is a live ROS 2 sidecar milestone, not a completed `rmw_fleetqox_cpp`.
The next implementation step is to move the same source-sequence, liveliness
horizon, and ACK/NACK semantics from the Python sidecar path into a persistent
RMW publish/take boundary:

1. keep `fleetqox/rmw_socket.py` as the first UDP socket-backed executable
   contract around `fleetrmw.data_frame.v1` and `fleetrmw.ack_nack.v1`;
2. keep `fleetqox/rmw_transport_loop.py` as the persistent multi-flow Python
   reference for bounded talker-side retransmit state;
3. preserve publisher identity, source sequence, source timestamp, effective
   lifespan, liveliness lease, and recovery horizon at the transport boundary;
4. use the new `ros2_ws/src/rmw_fleetqox_cpp` transport reference as the C++
   executable contract for the future RMW ABI;
5. rerun the same `8`-robot live bridge as a regression gate while adding
   larger rows such as `16` robots and longer transition segments.

# RMW Action QoS V1

## Purpose

This milestone verifies real ROS 2 action observation QoS through the
FleetRMW router. Goal, cancel, and result remain request/response traffic;
feedback and status use the regular FleetRMW data-frame path and therefore
inherit publisher graph QoS, router lifespan admission, routing, and telemetry.

## Probe

`scripts/run_rmw_docker_router_rclpy_action_qos_probe.py` runs two
multi-container `rclpy.action` rows with
`RMW_IMPLEMENTATION=rmw_fleetqox_cpp`:

1. `fresh`: router delay `1 ms`, feedback/status lifespan `100 ms`.
2. `expired_observation`: router delay `30 ms`, feedback/status lifespan `5 ms`.
3. `deadline_priority`: feedback deadline `5 ms`, status deadline `100 ms`,
   scheduler window `100 ms`, and a three-frame action burst.

Both rows execute a successful goal and a canceled goal through
`fleetrmw_udp_router_probe`.

## Result

Artifact:

`results_rmw_socket/docker_rmw_router_rclpy_action_qos_probe_summary.json`

The fresh row passes with feedback/status delivery, success result status `4`,
canceled result status `5`, and `qos_dropped_frames=0`.

The expired row also completes both action control paths, while the router
removes stale observation traffic:

```json
{
  "qos_dropped_frames": 9,
  "qos_dropped_topic_counts": {
    "/fleetqox/lookup_transform/_action/feedback": 2,
    "/fleetqox/lookup_transform/_action/status": 7
  },
  "service_frames": 10,
  "service_forwarded": 10
}
```

The client receives no stale feedback or status samples, but still receives
`SUCCEEDED` and `CANCELED` results through the action service path.

The deadline row scopes the scheduler to
`/fleetqox/lookup_transform/_action/`, excluding unrelated parameter traffic.
The first forwarded action topic is feedback:

```json
{
  "scheduler_expected_frames": 3,
  "scheduler_topic_prefix": "/fleetqox/lookup_transform/_action/",
  "forwarded_action_topics": [
    "/fleetqox/lookup_transform/_action/feedback",
    "/fleetqox/lookup_transform/_action/status",
    "/fleetqox/lookup_transform/_action/status"
  ],
  "deadline_order_verified": true
}
```

## Meaning

FleetRMW now treats action traffic as different semantic planes:

- command/control transactions remain complete;
- stale observation traffic is removed at the router;
- drops are attributable by action topic;
- earlier-deadline action traffic can be scheduled within a scoped traffic
  class without including unrelated ROS traffic;
- ROS 2 action APIs and graph availability remain unchanged.

## Remaining Work

- repeat the mixed action/control/state row across profiles, repetitions, and
  larger robot counts;
- expose measured action latency, deadline misses, and result completion time;
- evaluate loss, recovery, and path switching under Wi-Fi/WAN/roaming netem;
- run Nav2/RMF action workloads and larger concurrent robot counts.

## Mixed Action/Control/State Result

`scripts/run_rmw_docker_router_mixed_action_control_state_probe.py` now runs a
real `rclpy.action` success/cancel lifecycle concurrently with reliable control
and state flows for two robots on one roaming-profile router. Fault injection
is scoped with `--drop-topic-prefix /fleetqox/mixed/`, so control/state repair
is exercised without changing action command/result semantics.

The latest artifact passes: action result statuses are `SUCCEEDED=4` and
`CANCELED=5`, all `4/4` control/state flows recover `one`, `three`, `two`, the
router records `17` urgent and `8` queued frames, and `46` ACK/NACK frames are
forwarded. All fresh frames meet their learned deadline. Four repaired control
frames miss the original deadline by roughly `167-196 ms`, demonstrating that
reactive ACK/NACK preserves delivery QoE but cannot retroactively satisfy a
hard deadline after loss on a roaming path.

The follow-on proactive diversity probe closes the first hard-deadline slice.
For control topics whose QoS deadline is at or below the redundancy threshold,
`adaptive_qos` sends each sample through a roaming primary and a Wi-Fi backup.
Across two repeated `loss 0.02%` rows, the primary drops sequence `2`, yet the
backup delivers sequences `1,2,3` within `100 ms`; maximum observed latency is
`63.688 ms` and NACK retransmissions remain `0`.

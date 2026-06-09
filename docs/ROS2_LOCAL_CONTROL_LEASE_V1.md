# ROS 2 Local Control Lease V1

## Purpose

Typed egress alone is not enough for robot control.  A `Twist` that arrives
late, without an active lease, or outside local bounds should not be forwarded
directly to the robot controller.

This milestone adds a robot-side lease adapter:

```text
/fleetrmw/<robot>/control_lease
+ /fleetrmw/<robot>/local_cmd_vel
-> local lease evaluator
-> /<robot>/cmd_vel_fleetrmw
```

The adapter treats FleetRMW control output as a bounded local authority lease:
the command is accepted only while the lease is fresh, is clipped to local
safety, acceleration, and jerk bounds, and follows the configured expiry action
when the lease expires.

## New Code

- `fleetqox/local_control_lease.py`
  - Dependency-free lease state machine.
  - Parses control lease envelopes.
  - Evaluates `TwistCommand` against lease freshness, velocity bounds, and
    acceleration/jerk bounds.
  - Emits `accept`, `clip`, `drop_no_lease`, `invalid_lease`, and
    fallback decisions.
- `scripts/run_ros2_local_controller_lease.py`
  - ROS 2 adapter for the lease state machine.
  - Subscribes control leases and typed `geometry_msgs/Twist` commands.
  - Publishes safe commands to `/<robot>/cmd_vel_fleetrmw`.
  - Writes lease decisions to JSONL.
  - Supports `--robot-count`; one process creates a lease state, subscriptions,
    safe-command publisher, and counter bucket per robot namespace.
- `tests/test_local_control_lease.py`
  - Covers active lease accept, clipping, fallback stop, pending command replay,
    acceleration clipping, jerk clipping, profile validation, hold-last expiry,
    and disallowed-axis clipping.

## Safety Semantics

The current V1 policy is deliberately small:

| condition | action |
| --- | --- |
| typed command with active fresh lease | `accept` and publish |
| command exceeds velocity bounds | `clip` and publish bounded command |
| command exceeds acceleration bounds | `clip` and publish rate-limited command |
| command exceeds jerk bounds | `clip` and publish acceleration-shaped command |
| command arrives before lease | hold briefly, otherwise `drop_no_lease` |
| lease expires with `stop` policy | publish one `fallback_stop` |
| lease expires with `hold_last` policy | publish one `fallback_hold_last` |
| lease expires with `drop` policy | emit `fallback_drop` without publishing |
| malformed lease | `invalid_lease` |

The lease expiration is measured from local receive time plus the lease
lifespan, capped by `max_local_lifespan_ms`.  This avoids relying on perfectly
synchronized monotonic clocks across Docker containers or real robots.
The same boundary owns control-deadline feedback: local-controller feedback
records carry the originating lease `action` and `wire_mode`, report whether the
safe command was published, and mark the deadline as met only if the command was
published before the local lease expiry.  Egress feedback still reports
control-lease delivery and latency, but it does not treat WAN transit time of
the lease as a robot command deadline miss.
The current default controller profile is `diff_drive_safe_v1` with configurable
`max_linear_x`, `max_angular_z`, `max_linear_accel_x`, `max_angular_accel_z`,
`max_linear_jerk_x`, `max_angular_jerk_z`, and `expiry_action`.  These values
are now data-driven and validated from
`experiments/local_controller_profiles_v1.json`; Docker T3 uses
`tb4_lite_safe_v1` by default, while `warehouse_amr_safe_v1` demonstrates a
higher-speed AMR profile with `hold_last` expiry behavior.

## Docker T3 Result

The latest local-lease smoke run:

```text
scenario: ros2_live_bridge_t3_local_profiles_jerk_v1
publisher ticks: 37
sidecar packets received by egress: 17
egress ROS publications: 25
ROS 2 monitor messages: 39
local controller leases: 8
local controller typed commands: 8
safe command publications: 14
lease statuses: 2 accept, 6 clip, 8 lease_update, 6 fallback_stop
clip stages: 6 acceleration, 1 jerk
controller profile: tb4_lite_safe_v1
expiry action: stop
safe command topic: /robot_0000/cmd_vel_fleetrmw
control delivery ratio: 1.0000
loss ratio: 0.0000
deadline miss ratio: 0.0588
p95 latency: 210.82 ms
```

The important result is semantic, not performance: the robot-side path no
longer treats a network-delivered `Twist` as unconditional authority.  It
requires an active FleetRMW lease, enforces a robot-side controller profile,
rate-limits abrupt command changes through acceleration and jerk envelopes, and
proves fallback stop behavior after lease expiry.

The two-robot local-services follow-up
`ros2_live_bridge_t3_dynamic_objective_transition_2robot_local_services_3seed_v1`
keeps the same lease semantics while expanding the adapter to `robot_0000` and
`robot_0001` in one ROS 2 process.  Across `3/3` seeds, the lease decision log
observed both robot IDs in every run.

## Remaining Gap

V1 only handles `cmd_vel`/`Twist`.  The next step is to calibrate the profile
values against measured robot dynamics, scale the namespace-aware path beyond
two robots with per-robot fairness budgets, then add typed adapters for
odometry, scan, degraded perception, and controller-specific lease semantics.

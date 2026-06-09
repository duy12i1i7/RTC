# Fleet Optimizer Runtime Actuation V1

This artifact verifies that the fleet-level optimizer can cross the sidecar runtime boundary.

- Summary: `results_fleet_optimizer/fleet_optimizer_runtime_probe_summary.json`
- Robots: `6`
- Unique sidecar events: `13`
- Emitted UDP packets: `19`

## Runtime Counts

- Fleet response: `{'schema_version': 'fleetrmw.fleet_optimizer_runtime.v1', 'decision_count': 18, 'send_count': 13, 'redundant_count': 6, 'degraded_count': 1, 'drop_count': 5, 'mode_counts': {'redundant': 6, 'unicast': 6, 'degraded': 1, 'drop': 5}, 'action_counts': {'send': 12, 'send_degraded': 1, 'defer': 5}}`
- Event mode counts: `{'redundant': 6, 'unicast': 6, 'degraded': 1}`
- Event action counts: `{'send': 12, 'send_degraded': 1}`
- Selected path counts: `{'backup_5g': 13, 'primary_wifi': 6}`
- Packet path counts: `{'backup_5g': 13, 'primary_wifi': 6}`
- UDP target counts: `{'127.0.0.1:19102': 13, '127.0.0.1:19101': 6}`

## Interpretation

- The sidecar accepts a `fleet_optimizer` payload with multi-path telemetry and per-robot QoE state.
- The runtime annotates each sidecar event with the optimizer mode and selected paths.
- Redundant optimizer decisions actuate as per-path UDP transmissions in this dependency-free harness.
- The current target binding is explicit UDP host/port mapping; binding to ROS 2 RMW router peers and live per-path telemetry feedback remains future C++ RMW/router work.

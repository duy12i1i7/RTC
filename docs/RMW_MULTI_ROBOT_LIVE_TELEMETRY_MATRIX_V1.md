# RMW Multi-Robot Live Telemetry Matrix V1

This artifact extends the two-topic Docker live RMW probe into a repeatable
profile matrix.

- Script: `scripts/run_rmw_docker_multi_robot_live_telemetry_matrix.py`
- Summary:
  `results_rmw_socket/docker_multi_robot_live_telemetry_matrix_summary.json`
- Report:
  `results_rmw_socket/docker_multi_robot_live_telemetry_matrix_report.md`
- Schema: `fleetrmw.rmw_multi_robot_live_telemetry_matrix.v1`
- Default profiles: `wifi`, `wan`, `roaming`
- Default seeds: `7`

## Scope

Each matrix row runs the real Docker RMW publisher/router/subscriber path from
`scripts/run_rmw_docker_multi_robot_live_telemetry_plan_probe.py`.

The profile changes the router telemetry values used by the live controller:

- primary path latency, jitter, loss, NACK rate, and deadline miss ratio;
- backup path latency, jitter, loss, NACK rate, and deadline miss ratio;
- per-path capacity metadata.

By default this is not `tc netem` packet shaping. It is the live RMW closed loop
under profile-shaped telemetry. The same runner can be invoked with
`--enable-netem`, and the dedicated
`scripts/run_rmw_docker_multi_robot_live_netem_matrix.py` entrypoint records the
real packet-shaping artifact.

## Pass Conditions

Each row must satisfy the base multi-robot probe:

- initial plan:
  `/robot_0000/cmd_vel=primary_wifi;/robot_0001/odom=primary_wifi`;
- final plan:
  `/robot_0000/cmd_vel=backup_5g+primary_wifi;/robot_0001/odom=backup_5g`;
- control publisher reports redundant fleet-plan frames;
- state publisher reports zero redundant frames;
- control subscriber de-duplicates redundant data frames;
- state subscriber reports zero duplicate data-frame de-duplication;
- both subscribers receive `one`, `two`, and `three`;
- live controller receives router and subscriber telemetry.

## Reported Metrics

The matrix summary records, per run and per profile:

- router telemetry record count;
- subscriber delivery telemetry record count;
- control redundant frame count;
- selected path count;
- duplicate ACK/NACK count;
- duplicate data frames de-duplicated before application delivery;
- mean subscriber delivery latency for control and state topics.

## Current Result

The current one-seed matrix passes all default profiles:

| profile | ok/runs | router records | subscriber records | control redundant | control de-dup | state de-dup |
|---|---:|---:|---:|---:|---:|---:|
| `wifi` | 1/1 | 8 | 6 | 2 | 2 | 0 |
| `wan` | 1/1 | 8 | 6 | 2 | 2 | 0 |
| `roaming` | 1/1 | 8 | 6 | 2 | 2 | 0 |

## Research Role

This starts the evaluation layer needed for QoS/QoE claims:

single live probe -> profile matrix -> real netem matrix -> ns-3/OMNeT++ replay.

It keeps the ROS 2/RMW data plane in the loop while making network condition
variation explicit and repeatable.

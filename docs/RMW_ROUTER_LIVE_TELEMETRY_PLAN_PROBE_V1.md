# RMW Router Live Telemetry Plan Probe V1

This artifact verifies the first closed loop from router path telemetry to a
live RMW fleet-plan update.

- Summary: `results_rmw_socket/docker_router_live_telemetry_plan_probe_summary.json`
- Schema: `fleetrmw.rmw_router_live_telemetry_plan_probe.v1`
- Router telemetry schema: `fleetrmw.router_path_telemetry.v1`
- Subscriber telemetry schema: `fleetrmw.subscriber_delivery_telemetry.v1`
- Controller schema: `fleetrmw.live_path_plan_controller.v1`
- Initial plan: `/fleetqox/router_live_telemetry_plan_probe=primary_wifi`
- Controller final plan: `/fleetqox/router_live_telemetry_plan_probe=backup_5g+primary_wifi`

## Result

| component | status | count | notes |
|---|---:|---:|---|
| primary router | ok | 3 data frames | writes `primary_wifi` telemetry records |
| backup router | ok | 2 data frames | receives only after controller updates the plan |
| live controller | ok | 5 router records, 3 subscriber records | tails router/subscriber JSONL and rewrites the plan file |
| publisher | ok | 3 data frames | `fleet_plan_redundant_frames=2`, selected path count `5` |
| subscriber | ok | 3 payloads | receives `one`, `two`, `three`, writes delivery latency/deadline telemetry |

## Interpretation

- The publisher starts with `FLEETQOX_RMW_FLEET_PATH_PLAN_FILE` containing a
  primary-only route.
- `fleetrmw_udp_router_probe` appends per-path JSONL telemetry for received data
  frames.
- The subscriber probe appends delivery telemetry with source sequence, source
  timestamp, take timestamp, latency, deadline status, and robot ID.
- `LivePathPlanController` tails those telemetry files, aggregates path
  observations and robot QoE state, runs `OnlineFleetPathPlanner`, and
  atomically rewrites the same plan file.
- The same live publisher process reloads that file and routes the next frames
  through both `backup_5g` and `primary_wifi`.

This closes the first live control loop at the RMW/router/subscriber telemetry
level. The next probe,
`docs/RMW_MULTI_ROBOT_LIVE_TELEMETRY_PLAN_PROBE_V1.md`, scales the same
mechanism to two topics and two robot QoE streams; the remaining research work
is larger N-robot benchmarking and richer QoE/SLO outcome feedback.

# Live Plan Scale Probe V1

This artifact measures the online fleet path planner at N-robot/N-topic scale
without Docker. It is a controller/planner benchmark, not a network data-plane
probe.

- Script: `scripts/run_live_plan_scale_probe.py`
- Summary: `results_rmw_socket/live_plan_scale_probe_summary.json`
- Report: `results_rmw_socket/live_plan_scale_probe_report.md`
- Schema: `fleetrmw.live_plan_scale_probe.v1`
- Default workload: 100 robots, 200 topics, 12 control ticks

## Workload

Each robot contributes two ROS-style topics:

- `/{robot_id}/cmd_vel`: urgent control, 30 ms deadline;
- `/{robot_id}/odom`: lower-criticality state, 120 ms deadline.

The probe starts with healthy `primary_wifi`, then degrades Wi-Fi after the
first third of the run while keeping `backup_5g` stable. The expected final
shape is:

- every `cmd_vel` topic uses redundant `backup_5g+primary_wifi`;
- every `odom` topic uses unicast `backup_5g`.

## Metrics

The summary reports:

- decision latency `min`, `p50`, `p95`, `max`, and `mean`;
- maximum and final `FLEETQOX_RMW_FLEET_PATH_PLAN` byte size;
- final topic rule count;
- final optimizer mode counts;
- final path-plan SHA-256 and a short rule preview.

## Role In The Testbed

This probe fills the gap between the two-topic Docker live RMW probe and larger
network-emulation campaigns. It catches algorithmic scaling and plan-size
issues before we spend Docker/netem/ns-3/OMNeT++ time on the same workload.

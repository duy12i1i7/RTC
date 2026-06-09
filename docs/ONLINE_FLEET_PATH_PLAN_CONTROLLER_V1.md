# Online Fleet Path Plan Controller V1

This artifact verifies the closed-loop planner that converts measured per-path observations into `FLEETQOX_RMW_FLEET_PATH_PLAN` rules.

- Summary: `results_fleet_optimizer/online_fleet_path_plan_probe_summary.json`
- Schema: `fleetrmw.online_fleet_path_plan_probe.v1`
- Status: `ok`
- Changed ticks: `[0, 1, 3]`
- Held ticks: `[2]`

| tick | path plan |
|---:|---|
| 0 | `/robot_0000/cmd_vel=primary_wifi` |
| 1 | `/robot_0000/cmd_vel=backup_5g+primary_wifi` |
| 2 | `/robot_0000/cmd_vel=backup_5g+primary_wifi` |
| 3 | `/robot_0000/cmd_vel=backup_5g` |

## Interpretation

- Tick `0` starts on the best primary Wi-Fi path.
- Tick `1` moves urgent control traffic to redundant backup-plus-primary paths after the primary path degrades.
- Tick `2` intentionally holds the redundant plan because the anti-flapping dwell guard has not expired.
- Tick `3` narrows to backup-only after the backup path becomes stable enough and the dwell guard allows the change.

# RMW Multi-Robot Live Netem Matrix V1

This artifact binds the multi-robot live RMW fleet-plan probe to real Docker
link shaping with `tc netem`.

- Script: `scripts/run_rmw_docker_multi_robot_live_netem_matrix.py`
- Summary:
  `results_rmw_socket/docker_multi_robot_live_netem_matrix_summary.json`
- Report:
  `results_rmw_socket/docker_multi_robot_live_netem_matrix_report.md`
- Schema: `fleetrmw.rmw_multi_robot_live_netem_matrix.v1`
- Netem status schema: `fleetrmw.router_netem.v1`
- Netem-capable image: `external/rmw-netem/Dockerfile`
- Default profiles: `wifi`, `wan`, `roaming`
- Default seeds: `7`

Build the recommended image first:

```bash
docker build \
  -t localhost/fleetrmw/rmw-netem:jazzy \
  -f external/rmw-netem/Dockerfile \
  .
```

## Scope

Each row runs the same live Docker RMW topology as
`scripts/run_rmw_docker_multi_robot_live_telemetry_plan_probe.py`:

- `/robot_0000/cmd_vel` control publisher and subscriber;
- `/robot_0001/odom` state publisher and subscriber;
- one `primary_wifi` UDP router;
- one `backup_5g` UDP router;
- host-side `LivePathPlanController` that rewrites the RMW fleet-plan file.

The difference from the telemetry-only matrix is that each router container is
started with Docker `NET_ADMIN` and applies:

```text
tc qdisc replace dev eth0 root netem delay <latency>ms <jitter>ms loss random <loss>% rate <rate>mbit
```

The router also writes a JSON status file per path, so every run records whether
`tc` was actually applied, missing, or failed.

Router containers stay alive for `--netem-drain-s` seconds after the router
binary exits. This lets delayed qdisc queues flush before Docker destroys the
network namespace.

## Deterministic And Stochastic Modes

The default `--netem-loss-scale 0.0` applies delay, jitter, and rate shaping
while disabling stochastic packet loss for smoke validation. This avoids random
row failures when the goal is to verify the ROS 2/RMW live bridge path.

The `--seeds` values are recorded as repetition IDs. The current
`localhost/fleetrmw/rmw-netem:jazzy` image's `tc netem` does not expose explicit
RNG seeding, so seeds do not make packet-loss draws deterministic.

For stochastic stress, pass a positive loss multiplier:

```bash
python3 scripts/run_rmw_docker_multi_robot_live_stochastic_netem_matrix.py \
  --image localhost/fleetrmw/rmw-netem:jazzy \
  --profiles wifi,wan,roaming \
  --seeds 7 \
  --require-netem \
  --netem-loss-scale 1.0 \
  --netem-drain-s 2.0
```

## Pass Conditions

Each row inherits the base multi-robot live probe requirements:

- initial plan:
  `/robot_0000/cmd_vel=primary_wifi;/robot_0001/odom=primary_wifi`;
- final plan:
  `/robot_0000/cmd_vel=backup_5g+primary_wifi;/robot_0001/odom=backup_5g`;
- control publisher sends redundant fleet-plan frames;
- state publisher remains unicast on `backup_5g`;
- control subscriber de-duplicates redundant frames before delivery;
- state subscriber does not de-duplicate redundant frames;
- both subscribers receive `one`, `two`, and `three`;
- router and subscriber telemetry feed the controller.

When `--require-netem` is set, both router status records must report
`status=applied`. If the image lacks `tc`, or Docker cannot grant `NET_ADMIN`,
the row fails instead of silently falling back to telemetry-only behavior.

## Research Role

This is the first RMW-layer artifact where the controller decision, redundant
wire delivery, ACK/NACK path, subscriber QoE telemetry, and Docker packet
shaping all run in one live session.

It closes the gap between:

- offline sidecar/netem simulations;
- telemetry-shaped controller probes;
- real ROS 2/RMW packets crossing impaired IP links.

The next scale step is to repeat this netem matrix over more seeds and robot
counts, then export packet traces for ns-3 and OMNeT++ replay.

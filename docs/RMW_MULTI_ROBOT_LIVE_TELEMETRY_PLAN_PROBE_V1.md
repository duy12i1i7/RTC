# RMW Multi-Robot Live Telemetry Plan Probe V1

This artifact verifies that the live FleetRMW controller can drive more than
one ROS topic and robot QoE stream through a shared RMW plan file.

- Summary:
  `results_rmw_socket/docker_multi_robot_live_telemetry_plan_probe_summary.json`
- Schema: `fleetrmw.rmw_multi_robot_live_telemetry_plan_probe.v1`
- Optional netem status schema: `fleetrmw.router_netem.v1`
- Router telemetry schema: `fleetrmw.router_path_telemetry.v1`
- Subscriber telemetry schema: `fleetrmw.subscriber_delivery_telemetry.v1`
- Controller schema: `fleetrmw.live_path_plan_controller.v1`
- Initial plan:
  `/robot_0000/cmd_vel=primary_wifi;/robot_0001/odom=primary_wifi`
- Controller final plan:
  `/robot_0000/cmd_vel=backup_5g+primary_wifi;/robot_0001/odom=backup_5g`

## Topology

The probe runs one Docker network with:

- one `primary_wifi` UDP router;
- one `backup_5g` UDP router;
- one subscriber for `/robot_0000/cmd_vel`;
- one subscriber for `/robot_0001/odom`;
- one control publisher for `/robot_0000/cmd_vel`;
- one state publisher for `/robot_0001/odom`;
- one host-side `LivePathPlanController` tailing router and subscriber JSONL.

Both publishers use `FLEETQOX_RMW_PEER_POLICY=fleet_plan`,
path-labeled `FLEETQOX_RMW_PEERS`, and the same
`FLEETQOX_RMW_FLEET_PATH_PLAN_FILE`.

## Expected Behavior

The controller starts from seed observations where Wi-Fi is the best path, so
both topics initially use `primary_wifi`.

The control publisher first generates degraded `primary_wifi` router telemetry.
The controller then rewrites the plan file:

- `/robot_0000/cmd_vel` is a high-criticality control flow with a 30 ms
  deadline, so it switches to redundant `backup_5g+primary_wifi`;
- `/robot_0001/odom` is a lower-criticality state flow with a 120 ms deadline,
  so it switches to unicast `backup_5g`.

This checks that the plan is not a single fleet-wide route. It is a per-topic
decision derived from flow class, deadline, path telemetry, and robot QoE.

## Pass Conditions

The probe requires:

- both publishers, both subscribers, and both routers to exit with `status=ok`;
- the initial plan to match the primary-only two-topic plan;
- the final controller plan to match the mixed redundant/unicast plan;
- at least six router telemetry records and six subscriber delivery records;
- both robot IDs to appear in controller robot QoE state;
- the control publisher to report at least one redundant fleet-plan frame;
- the state publisher to report unicast `backup_5g` and zero redundant frames;
- the control subscriber to report duplicate data frames de-duplicated before
  delivery, while the state subscriber reports zero duplicate de-duplication;
- the control publisher to receive duplicate ACK/NACK state from the redundant
  path, while the state publisher receives none;
- subscribers to receive `one`, `two`, and `three`.

## Research Meaning

This closes the first multi-flow control loop at the RMW layer:

router path telemetry -> subscriber delivery QoE -> online planner ->
topic-specific fleet-plan file -> live RMW publisher reload.

It is still a small fleet probe, but it moves the project beyond a single-topic
demonstration and proves that redundant wire delivery does not double-deliver
application samples. It gives a concrete base for larger N-robot experiments,
netem profile changes, and ns-3/OMNeT++ trace replay.

The probe now has an optional Docker link-shaping mode:

```bash
python3 scripts/run_rmw_docker_multi_robot_live_telemetry_plan_probe.py \
  --image localhost/fleetrmw/rmw-netem:jazzy \
  --profile wifi \
  --enable-netem \
  --require-netem \
  --netem-loss-scale 0.0 \
  --netem-drain-s 2.0
```

With `--enable-netem`, both router containers are started with `NET_ADMIN` and
apply `tc qdisc` to Docker `eth0`. With `--require-netem`, the probe fails if
either router cannot apply the qdisc. The loss scale defaults to `0.0` so smoke
runs are deterministic; stochastic loss stress can raise it toward `1.0`.
`--netem-drain-s` keeps router containers alive briefly after router exit so
delayed qdisc queues can flush before Docker removes the namespace.
Use `external/rmw-netem/Dockerfile` to build an image with `iproute2`; the plain
`ros:jazzy-ros-base` image may not include `tc`.

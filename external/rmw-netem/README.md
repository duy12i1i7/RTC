# FleetRMW RMW Netem Image

This image is for the RMW-layer Docker probes that need both ROS 2 build tools
and Linux `tc netem`.

Build it from the repository root:

```bash
docker build \
  -t localhost/fleetrmw/rmw-netem:jazzy \
  -f external/rmw-netem/Dockerfile \
  .
```

Run the real-netem matrix with strict qdisc verification:

```bash
python3 scripts/run_rmw_docker_multi_robot_live_netem_matrix.py \
  --image localhost/fleetrmw/rmw-netem:jazzy \
  --profiles wifi,wan,roaming \
  --seeds 7 \
  --require-netem \
  --netem-loss-scale 0.0 \
  --netem-drain-s 2.0
```

`ros:jazzy-ros-base` is enough for many RMW smoke tests, but it may not include
`tc`. The netem matrix should use an image with `iproute2`; otherwise
`--require-netem` correctly fails with `status=missing_tc`.

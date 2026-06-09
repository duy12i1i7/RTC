# FleetRMW / FleetQoX

FleetRMW is a research-oriented ROS 2 middleware project for large-scale robot
fleets. The long-term goal is a ROS 2-native, non-DDS RMW that keeps the ROS
programming model while replacing endpoint-centric topic delivery with
fleet-scale, task-aware, QoS/QoE/QoT communication.

This repository starts with the part that should be proven first:

- a project manifesto and research framing;
- a QoX model for control, state, perception, operator, and bulk flows;
- a causal-semantic deadline scheduler prototype;
- a predictive admission control prototype with semantic wire compaction;
- a supervisory intent transform for paths where short-horizon control is
  physically infeasible;
- a dependency-free FleetRMW sample contract boundary for identity, admission
  provenance, fidelity, and qualified delivery metadata;
- end-to-end `contract_id` propagation from ROS 2 shim batches through sidecar
  events, qualified wrappers, and projection-gate logs;
- source-derived `source_sample_id` propagation from ROS header stamps or
  RMW-visible publisher GID/sequence metadata where available;
- native `FleetRmwSampleEnvelope` propagation for FleetRMW-owned publisher
  identity, source sequence, and source/receive timestamps;
- a native `fleetrmw.data_frame.v1` packet path that can replace legacy
  sidecar event JSON on the sidecar-to-egress data plane;
- a minimal in-memory FleetRMW publish/take boundary that emits
  `fleetrmw.data_frame.v1` and receiver-side `fleetrmw.ack_nack.v1` feedback;
- a liveliness-backed ACK/NACK retransmission horizon for ROS 2 live bridge
  control leases, with a repeated `8`-robot Wi-Fi/WAN/roaming audit passing
  seeds `7,13,29`;
- a socket-backed minimal FleetRMW publish/take smoke where
  `fleetrmw.data_frame.v1` crosses UDP and `fleetrmw.ack_nack.v1` returns to the
  talker;
- a first C++ `rmw_fleetqox_cpp` transport-boundary reference package with a
  UDP loopback smoke matching the Python socket retransmit contract and initial
  RMW lifecycle symbols, now verified by Docker ROS Jazzy `colcon` build,
  Python-to-C++ frame probing, an init/context/node lifecycle probe, and a
  socket-backed serialized pub/sub data-frame path with both local loopback and
  env-configured inter-process peer probes, plus a Docker
  publisher-router-subscriber-observer route and lease-aware remote-graph
  synchronization probe, type-erased and introspection-C ROS typed publish/take
  probes, wait/guard, and graph probes;
- a repeated ROS 2 Docker T3 harness for packet-format/RMW matrices across
  publisher seeds and named netem profiles;
- a three-seed Wi-Fi ROS 2 packet-format/RMW matrix where
  `data_frame/rmw_zenoh_cpp` is the current non-dominated operating point;
- a three-seed WAN ROS 2 packet-format/RMW matrix showing that the Pareto
  frontier changes by network profile;
- a three-seed roaming ROS 2 packet-format/RMW matrix showing that the frontier
  changes again and depends on the active QoS/QoE objective vector;
- a profile/objective-aware ROS 2 transport selector that ranks measured
  packet-format/RMW candidates under safety/utility, teleop-latency, autonomy
  safety, or throughput objectives;
- a runtime `TransportBinding` payload that lets the ROS 2 shim/sidecar batch
  carry the selected packet-format/RMW policy and choose per-batch packet
  framing in the sidecar runtime;
- a rule-based online binding manager that infers Wi-Fi/WAN/roaming from link
  telemetry and selects the corresponding measured transport binding;
- an adaptive binding estimator that smooths link telemetry and applies
  hysteresis/min-dwell before switching measured transport bindings;
- a live continuous binding loop that refreshes `TransportBinding` and adaptive
  profile estimates on each ROS 2 bridge batch, then lets the sidecar choose
  per-batch packet framing;
- a Docker T3 profile-transition harness that applies Wi-Fi/WAN/roaming
  `tc netem` changes inside one ROS 2 live bridge run and records binding
  switch evidence;
- a Docker T3 adaptive-vs-static transition binding matrix that compares
  adaptive binding against static Wi-Fi/WAN/roaming bindings under the same
  live ROS 2 workload;
- a three-seed ROS 2 live transition binding matrix that quantifies adaptive
  switch latency, missing switches, flapping, and objective-specific wins
  against static bindings;
- a three-seed ROS 2 live dynamic-objective transition matrix where the same
  bridge session changes both network profile and QoS/QoE objective, then
  records matched profile switches, matched objective switches, policy
  switches, switch latency, and flapping in the sidecar decision log;
- a two-robot, three-seed ROS 2 live dynamic-objective transition matrix that
  expands the same bridge session across multiple robot namespaces and records
  decision, receiver, and egress coverage per robot;
- a two-robot, three-seed ROS 2 live dynamic-objective local-services matrix
  where the local controller, projection quality gate, and monitor are
  namespace-aware and observe both robot IDs under the same live transition;
- a two-robot, three-seed ROS 2 live per-robot QoS budget matrix that reports
  Jain fairness, worst-robot control delivery, worst-robot deadline miss, and
  budget pass/fail under the same dynamic profile/objective transition;
- a per-robot budget-aware admission wrapper that converts robot-level SLO debt
  into virtual-queue pressure on future critical-flow scheduling decisions;
- a fleet-level telemetry-scored QoS/QoE path optimizer that combines path
  loss, latency, jitter, NACKs, deadline misses, utilization, per-robot QoE
  debt, flow class, deadline, criticality, and fleet capacity to choose
  unicast, redundant, degraded, or deferred routing;
- an online fleet path-plan controller that smooths per-path observations,
  applies an anti-flapping dwell guard, and exports
  `FLEETQOX_RMW_FLEET_PATH_PLAN` rules for selected ROS topics;
- a C++ `rmw_fleetqox_cpp` fleet-plan mode that reads controller-written path
  plans from a file and reloads updated topic-to-path rules in the same
  publisher process;
- a router telemetry closed-loop probe where live router JSONL records feed a
  host-side controller, which rewrites the RMW fleet-plan file during the same
  ROS 2 publisher session;
- subscriber delivery telemetry for `rmw_take` source sequence/timestamp,
  receive/take timestamp, latency, deadline status, and robot ID, feeding robot
  QoE state back into the live path-plan controller;
- a multi-robot Docker live telemetry probe where `/robot_0000/cmd_vel` and
  `/robot_0001/odom` share the same RMW plan file but receive different
  controller decisions: redundant `backup_5g+primary_wifi` for urgent control
  and unicast `backup_5g` for lower-criticality state, with duplicate redundant
  data frames counted and de-duplicated before application delivery;
- a multi-robot live telemetry profile matrix over `wifi`, `wan`, and
  `roaming` router-telemetry profiles, preserving the same Docker RMW
  publisher/router/subscriber path while varying path latency, jitter, loss,
  NACK rate, deadline-miss ratio, and capacity metadata;
- a multi-robot live netem matrix that runs the same ROS 2/RMW
  publisher-router-subscriber topology while router containers apply real
  Docker `tc qdisc` delay/jitter/rate shaping, optionally requiring successful
  `NET_ADMIN` qdisc application and scaling stochastic packet loss, with a
  dedicated reproducible image in `external/rmw-netem`;
- a stochastic live netem matrix that turns on `tc netem loss random` while
  recording seed values as repetition IDs, because the current image's netem
  implementation does not expose explicit RNG seeding;
- a stochastic live netem sweep that runs multiple loss multipliers over the
  same RMW topology, reports the strongest tested loss scale where all profiles
  pass, records first-failure loss scale by profile, classifies failure kind,
  and can reuse a single colcon build across campaign rows;
- a stochastic live netem ablation campaign that holds the same ROS 2/RMW
  topology, profiles, seeds, and loss scales constant while comparing
  `none`, `state_only`, and `control_state` proactive repair modes for
  delivery resilience, latency, and duplicate-frame/ACK repair cost;
- a matched four-robot FleetRMW live telemetry matrix where
  `deadline_sequence_repair_v1` combines route-warmup ACK gating, semantic
  application repair cycles, idle missing-range ACK/NACK feedback, and terminal
  guard repeats to pass Wi-Fi/WAN/roaming Docker `tc netem` rows over seeds
  `7,13,29`;
- a FleetRMW live baseline comparison report that normalizes the native
  `rmw_fleetqox_cpp` ablation against existing ROS 2 live-bridge
  Fast DDS/Cyclone DDS/Zenoh profile winners while explicitly marking the
  result as an indirect baseline map, not a direct superiority benchmark;
- a direct ROS 2 RMW netem baseline probe/matrix that runs publisher and
  subscriber containers under the same named Wi-Fi/WAN/roaming impairment
  profiles, records missing RMW packages as `skipped`, and seeds the future
  same-envelope DDS/Zenoh comparison against FleetRMW-native routing;
- a controller-level live plan scale probe that drives the same planner across
  N robots and 2N ROS-style topics, measuring decision latency, final rule
  count, plan byte size, and redundant/unicast mode shape before larger
  Docker/netem campaigns;
- a sidecar runtime `fleet_optimizer` payload boundary that actuates optimizer
  decisions as event annotations, semantic degradation, defer/drop decisions,
  and per-path UDP target transmissions in a deterministic runtime probe;
- a ROS 2 Docker T3 path with typed `cmd_vel` egress and robot-local lease
  gating through velocity, acceleration, and jerk profiles;
- typed FleetRMW-local projections for admitted `cmd_vel`, odometry, and
  downsampled laser scan semantic payloads;
- generated `fleetrmw_interfaces` ROS 2 messages for projection quality and
  qualified odometry/laser-scan wrappers;
- a local projection-quality gate that forwards accepted odometry and scan
  projections to consumer-facing topics after validating sample-local quality;
- a deterministic simulation benchmark for large robot fleets.

The prototype is intentionally dependency-light and runs with the Python
standard library.

## Quick Start

```bash
python3 -m scripts.run_benchmark --robots 100 --seconds 60 --seed 7
python3 -m scripts.run_suite
python3 -m scripts.export_traces --scenario warehouse_50_constrained
python3 -m scripts.export_traces --scenario warehouse_50_constrained --format csv
python3 -m scripts.export_traces --scenario warehouse_50_constrained --format csv --policy fleetqox_predictive
python3 -m scripts.replay_trace traces/warehouse_50_constrained.csv --transport-model udp_like --queue-policy class_priority
python3 -m scripts.run_sidecar_runtime --listen-port 8765 --udp-port 9201
python3 -m scripts.feed_sidecar_synthetic --port 8765 --robots 10 --seconds 2
python3 -m scripts.analyze_sidecar_runtime \
  --decisions results_sidecar_runtime/runtime_v1_decisions.jsonl \
  --received results_sidecar_runtime/runtime_v1_received.jsonl
python3 -m scripts.run_sidecar_netem --run --analyze --scenario sidecar_netem_v1
python3 -m scripts.run_sidecar_netem --run --analyze --scenario sidecar_netem_matrix_v1 --all-policies --output-dir results_sidecar_netem_matrix
python3 -m scripts.run_sidecar_netem --run --analyze --scenario sidecar_netem_closed_loop_v1 --all-policies --closed-loop-feed --output-dir results_sidecar_netem_closed_loop
python3 -m scripts.run_sidecar_netem --run --analyze --scenario sidecar_netem_lagrangian_v3 --policy fleetqox_predictive_lagrangian --closed-loop-feed --output-dir results_sidecar_netem_lagrangian_v3
python3 -m scripts.run_lagrangian_sweep --robots 10,25 --seeds 7,13 --seconds 5
python3 -m scripts.adapt_lagrangian_from_netem \
  --summary results_sidecar_repeated/lag_variants_v1_summary.json \
  --manifest experiments/lagrangian_variants_v1.json \
  --next-label lag_adapt_001
python3 -m scripts.run_sidecar_repeated_netem --scenario-prefix sidecar_repeated_v1 --all-policies --seeds 7,13,29 --closed-loop-feed
python3 -m scripts.run_sidecar_repeated_netem \
  --scenario-prefix sidecar_lag012_v1 \
  --policy fleetqox_predictive_lagrangian \
  --policy-label lag_012 \
  --lagrangian-deadline-risk-budget 0.08 \
  --lagrangian-initial-deadline-lambda 1.8 \
  --lagrangian-risk-barrier-start 0.62 \
  --lagrangian-risk-barrier-scale 12.0 \
  --lagrangian-deadline-drop-risk 0.45 \
  --seeds 7,13 \
  --closed-loop-feed
python3 -m scripts.run_sidecar_repeated_netem \
  --scenario-prefix sidecar_profile_robustness_v1 \
  --profile lan \
  --profile wan \
  --profile roaming \
  --policy fleetqox_csds \
  --policy fleetqox_predictive \
  --policy fleetqox_predictive_guarded \
  --policy fleetqox_predictive_lagrangian \
  --policy-label lag_adapt_003 \
  --closed-loop-feed
python3 -m scripts.run_sidecar_repeated_netem \
  --scenario-prefix sidecar_profiled_wan_v1 \
  --profile wan \
  --policy fleetqox_predictive_guarded \
  --policy fleetqox_predictive_lagrangian \
  --policy fleetqox_predictive_profiled \
  --policy-label lag_adapt_003 \
  --closed-loop-feed
python3 -m scripts.run_sidecar_repeated_netem \
  --scenario-prefix sidecar_intent_wan_v1 \
  --profile wan \
  --policy fleetqox_predictive_guarded \
  --policy fleetqox_predictive_profiled \
  --policy fleetqox_predictive_contextual \
  --policy fleetqox_predictive_intent \
  --closed-loop-feed
python3 -m scripts.run_sidecar_repeated_netem \
  --scenario-prefix sidecar_semantic_contract_wan_v1 \
  --profile wan \
  --policy fleetqox_predictive_profiled \
  --policy fleetqox_predictive_intent \
  --policy fleetqox_semantic_contract \
  --closed-loop-feed
python3 -m scripts.run_sidecar_repeated_netem \
  --scenario-prefix sidecar_semantic_contract_lossaware_compare_wan_v1 \
  --profile wan \
  --policy fleetqox_predictive_intent \
  --policy fleetqox_semantic_contract \
  --policy fleetqox_semantic_contract_lossaware \
  --closed-loop-feed
python3 -m scripts.run_sidecar_repeated_netem \
  --scenario-prefix sidecar_semantic_contract_adaptive_wan_v1 \
  --profile wan \
  --policy fleetqox_predictive_intent \
  --policy fleetqox_semantic_contract \
  --policy fleetqox_semantic_contract_lossaware \
  --policy fleetqox_semantic_contract_adaptive \
  --closed-loop-feed
python3 -m scripts.report_sidecar_repeated \
  --metrics results_sidecar_netem_closed_loop/sidecar_netem_closed_loop_v1_matrix_metrics.jsonl \
  --metrics results_sidecar_netem_lagrangian_v3_matrix/sidecar_netem_lagrangian_v3_matrix_matrix_metrics.jsonl \
  --markdown docs/SIDECAR_REPEATED_STATS_V1.md
python3 -m scripts.run_t2s_network_sim --prepare-inputs
python3 -m scripts.replay_trace traces/warehouse_50_constrained.csv
python3 -m scripts.run_t2e_netem --prepare-inputs
python3 -m scripts.run_t1_ros2_perf --plan-commands
python3 -m scripts.run_t1_ros2_perf --run
python3 -m scripts.run_t2e_ros2_netem --dry-run
python3 -m scripts.run_t2e_ros2_netem --all-rmws --components control,state --runtime-s 30 --run --analyze
python3 -m scripts.run_t2e_ros2_netem --rmw rmw_zenoh_cpp --runtime-s 30 --run --analyze
python3 -m scripts.run_ros2_docker_live_bridge --run --analyze --scenario ros2_live_bridge_t3_local_profiles_jerk_v1 --json
python3 -m scripts.run_ros2_docker_live_bridge \
  --run \
  --analyze \
  --all-rmws \
  --scenario ros2_live_bridge_t3_rmw_metadata_v2 \
  --policy fleetqox_semantic_contract_adaptive \
  --bridge-config experiments/ros2_live_bridge_tb4_typed_projection_v1.json \
  --seconds 2 \
  --rate-hz 20 \
  --bridge-max-batches 20 \
  --delay-ms 20 \
  --jitter-ms 5 \
  --loss-percent 0.5 \
  --rate-mbit 20 \
  --quality-gate-identity-mode wrapper \
  --quality-message-mode typed \
  --projection-quality-message-mode typed \
  --projection-quality-delivery-mode wrapper \
  --projection-quality-payload-mode compact \
  --json
python3 -m scripts.run_ros2_docker_live_bridge \
  --run \
  --analyze \
  --packet-format data_frame \
  --scenario ros2_live_bridge_t3_data_frame_v1 \
  --json
python3 -m scripts.run_rmw_boundary_smoke \
  --robot-count 2 \
  --samples-per-robot 3 \
  --skip-take robot_0000:2 \
  --json
python3 -m scripts.run_ros2_docker_live_bridge \
  --run \
  --analyze \
  --packet-format-matrix \
  --scenario ros2_live_bridge_t3_packet_format_compare_v1 \
  --policy fleetqox_semantic_contract_adaptive \
  --bridge-config experiments/ros2_live_bridge_tb4_typed_projection_v1.json \
  --seconds 2 \
  --rate-hz 20 \
  --bridge-max-batches 20 \
  --delay-ms 20 \
  --jitter-ms 5 \
  --loss-percent 0.5 \
  --rate-mbit 20 \
  --quality-gate-identity-mode wrapper \
  --quality-message-mode typed \
  --projection-quality-message-mode typed \
  --projection-quality-delivery-mode wrapper \
  --projection-quality-payload-mode compact \
  --json
python3 -m scripts.run_ros2_docker_live_bridge \
  --run \
  --analyze \
  --all-rmws \
  --packet-format-matrix \
  --scenario ros2_live_bridge_t3_packet_format_rmw_matrix_v1 \
  --policy fleetqox_semantic_contract_adaptive \
  --bridge-config experiments/ros2_live_bridge_tb4_typed_projection_v1.json \
  --seconds 2 \
  --rate-hz 20 \
  --bridge-max-batches 20 \
  --delay-ms 20 \
  --jitter-ms 5 \
  --loss-percent 0.5 \
  --rate-mbit 20 \
  --quality-gate-identity-mode wrapper \
  --quality-message-mode typed \
  --projection-quality-message-mode typed \
  --projection-quality-delivery-mode wrapper \
  --projection-quality-payload-mode compact \
  --json
python3 -m scripts.run_ros2_docker_live_bridge \
  --run \
  --analyze \
  --all-rmws \
  --packet-format-matrix \
  --seeds 7,13,29 \
  --profile wifi \
  --scenario ros2_live_bridge_t3_repeated_packet_wifi_3seed_v1 \
  --policy fleetqox_semantic_contract_adaptive \
  --bridge-config experiments/ros2_live_bridge_tb4_typed_projection_v1.json \
  --seconds 2 \
  --rate-hz 20 \
  --bridge-max-batches 20 \
  --quality-gate-identity-mode wrapper \
  --quality-message-mode typed \
  --projection-quality-message-mode typed \
  --projection-quality-delivery-mode wrapper \
  --projection-quality-payload-mode compact
python3 -m scripts.select_ros2_transport \
  --summary results_ros2_live_bridge/ros2_live_bridge_t3_repeated_packet_wifi_3seed_v1_summary.json \
  --summary results_ros2_live_bridge/ros2_live_bridge_t3_repeated_packet_wan_3seed_v1_summary.json \
  --summary results_ros2_live_bridge/ros2_live_bridge_t3_repeated_packet_roaming_3seed_v1_summary.json \
  --objective balanced_safety_utility \
  --summary-json results_ros2_live_bridge/profile_objective_selector_balanced_v1_summary.json \
  --markdown results_ros2_live_bridge/profile_objective_selector_balanced_v1_report.md
python3 -m scripts.run_ros2_sidecar_adapter \
  --scenario ros2_shim_transport_binding_runtime_smoke_v1 \
  --decision-log results_ros2_shim/transport_binding_runtime_smoke_decisions.jsonl \
  --transport-binding-summary results_ros2_live_bridge/profile_objective_selector_balanced_v1_summary.json \
  --transport-profile wifi \
  --json
python3 -m scripts.run_ros2_sidecar_adapter \
  --scenario ros2_shim_transport_binding_auto_profile_smoke_v1 \
  --decision-log results_ros2_shim/transport_binding_auto_profile_smoke_decisions.jsonl \
  --transport-binding-summary results_ros2_live_bridge/profile_objective_selector_balanced_v1_summary.json \
  --auto-transport-profile \
  --json
python3 -m scripts.run_ros2_sidecar_adapter \
  --scenario ros2_shim_transport_binding_adaptive_profile_smoke_v1 \
  --decision-log results_ros2_shim/transport_binding_adaptive_profile_smoke_decisions.jsonl \
  --transport-binding-summary results_ros2_live_bridge/profile_objective_selector_balanced_v1_summary.json \
  --adaptive-transport-profile \
  --json
python3 -m scripts.smoke_ros2_live_bridge_binding \
  --selector-summary results_ros2_live_bridge/profile_objective_selector_balanced_v1_summary.json \
  --mode adaptive \
  --process-runtime \
  --output results_ros2_live_bridge/live_bridge_adaptive_binding_runtime_smoke_v1.json \
  --json
python3 -m scripts.run_ros2_docker_live_bridge \
  --run \
  --analyze \
  --scenario ros2_live_bridge_t3_profile_transition_v1 \
  --bridge-config experiments/ros2_live_bridge_tb4_binding_v1.json \
  --transition-profile wifi \
  --transition-profile wan \
  --transition-profile roaming \
  --transition-segment-s 2 \
  --seconds 6 \
  --rate-hz 20 \
  --bridge-max-batches 120 \
  --json
python3 -m scripts.run_ros2_docker_live_bridge \
  --run \
  --analyze \
  --scenario ros2_live_bridge_t3_profile_transition_binding_matrix_v1 \
  --bridge-config experiments/ros2_live_bridge_tb4_binding_v1.json \
  --rmw rmw_zenoh_cpp \
  --transition-profile wifi \
  --transition-profile wan \
  --transition-profile roaming \
  --transition-segment-s 2 \
  --seconds 6 \
  --rate-hz 20 \
  --bridge-max-batches 120 \
  --transition-binding-matrix \
  --title "ROS 2 Live Transition Binding Matrix T3 V1" \
  --json
python3 -m scripts.run_ros2_docker_live_bridge \
  --run \
  --analyze \
  --scenario ros2_live_bridge_t3_profile_transition_binding_matrix_3seed_v1 \
  --bridge-config experiments/ros2_live_bridge_tb4_binding_v1.json \
  --rmw rmw_zenoh_cpp \
  --seeds 7,13,29 \
  --transition-profile wifi \
  --transition-profile wan \
  --transition-profile roaming \
  --transition-segment-s 2 \
  --seconds 6 \
  --rate-hz 20 \
  --bridge-max-batches 120 \
  --transition-binding-matrix \
  --transition-summary-json results_ros2_live_bridge/profile_transition_binding_matrix_3seed_summary.json \
  --transition-markdown results_ros2_live_bridge/profile_transition_binding_matrix_3seed_report.md \
  --title "ROS 2 Live Transition Binding Matrix 3-Seed T3 V1" \
  --json
python3 -m scripts.select_ros2_transport \
  --summary results_ros2_live_bridge/ros2_live_bridge_t3_repeated_packet_wifi_3seed_v1_summary.json \
  --summary results_ros2_live_bridge/ros2_live_bridge_t3_repeated_packet_wan_3seed_v1_summary.json \
  --summary results_ros2_live_bridge/ros2_live_bridge_t3_repeated_packet_roaming_3seed_v1_summary.json \
  --objective autonomy_safety \
  --summary-json results_ros2_live_bridge/profile_objective_selector_autonomy_v1_summary.json \
  --markdown results_ros2_live_bridge/profile_objective_selector_autonomy_v1_report.md
python3 -m scripts.run_ros2_docker_live_bridge \
  --run \
  --analyze \
  --dynamic-objective-transition-matrix \
  --scenario ros2_live_bridge_t3_dynamic_objective_transition_3seed_v1 \
  --bridge-config experiments/ros2_live_bridge_tb4_binding_v1.json \
  --rmw rmw_zenoh_cpp \
  --seeds 7,13,29 \
  --transition-profile wifi \
  --transition-profile wan \
  --transition-profile roaming \
  --transition-segment-s 2 \
  --seconds 6 \
  --rate-hz 20 \
  --bridge-max-batches 120 \
  --binding-objective-summary autonomy_safety:results_ros2_live_bridge/profile_objective_selector_autonomy_v1_summary.json \
  --binding-objective-schedule balanced_safety_utility@0,autonomy_safety@2,balanced_safety_utility@4 \
  --transition-summary-json results_ros2_live_bridge/dynamic_objective_transition_3seed_summary.json \
  --transition-markdown results_ros2_live_bridge/dynamic_objective_transition_3seed_report.md \
  --title "ROS 2 Live Dynamic Objective Transition 3-Seed T3 V1" \
  --json
python3 -m scripts.run_ros2_docker_live_bridge \
  --run \
  --analyze \
  --dynamic-objective-transition-matrix \
  --scenario ros2_live_bridge_t3_dynamic_objective_transition_2robot_3seed_v1 \
  --bridge-config experiments/ros2_live_bridge_tb4_binding_v1.json \
  --rmw rmw_zenoh_cpp \
  --seeds 7,13,29 \
  --robot-count 2 \
  --transition-profile wifi \
  --transition-profile wan \
  --transition-profile roaming \
  --transition-segment-s 2 \
  --seconds 6 \
  --rate-hz 12 \
  --bridge-max-batches 120 \
  --binding-objective-summary autonomy_safety:results_ros2_live_bridge/profile_objective_selector_autonomy_v1_summary.json \
  --binding-objective-schedule balanced_safety_utility@0,autonomy_safety@2,balanced_safety_utility@4 \
  --transition-summary-json results_ros2_live_bridge/dynamic_objective_transition_2robot_3seed_summary.json \
  --transition-markdown results_ros2_live_bridge/dynamic_objective_transition_2robot_3seed_report.md \
  --title "ROS 2 Live Dynamic Objective Transition 2-Robot 3-Seed T3 V1" \
  --json
python3 -m scripts.run_ros2_docker_live_bridge \
  --run \
  --analyze \
  --dynamic-objective-transition-matrix \
  --scenario ros2_live_bridge_t3_dynamic_objective_transition_2robot_local_services_3seed_v1 \
  --bridge-config experiments/ros2_live_bridge_tb4_binding_v1.json \
  --rmw rmw_zenoh_cpp \
  --seeds 7,13,29 \
  --robot-count 2 \
  --transition-profile wifi \
  --transition-profile wan \
  --transition-profile roaming \
  --transition-segment-s 2 \
  --seconds 6 \
  --rate-hz 12 \
  --bridge-max-batches 120 \
  --binding-objective-summary autonomy_safety:results_ros2_live_bridge/profile_objective_selector_autonomy_v1_summary.json \
  --binding-objective-schedule balanced_safety_utility@0,autonomy_safety@2,balanced_safety_utility@4 \
  --transition-summary-json results_ros2_live_bridge/dynamic_objective_transition_2robot_local_services_3seed_summary.json \
  --transition-markdown results_ros2_live_bridge/dynamic_objective_transition_2robot_local_services_3seed_report.md \
  --title "ROS 2 Live Dynamic Objective Transition 2-Robot Local Services 3-Seed T3 V1" \
  --json
python3 -m scripts.run_ros2_docker_live_bridge \
  --run \
  --analyze \
  --dynamic-objective-transition-matrix \
  --scenario ros2_live_bridge_t3_dynamic_objective_transition_2robot_fair_budget_3seed_v1 \
  --bridge-config experiments/ros2_live_bridge_tb4_binding_v1.json \
  --rmw rmw_zenoh_cpp \
  --seeds 7,13,29 \
  --robot-count 2 \
  --transition-profile wifi \
  --transition-profile wan \
  --transition-profile roaming \
  --transition-segment-s 2 \
  --seconds 6 \
  --rate-hz 12 \
  --bridge-max-batches 120 \
  --binding-objective-summary autonomy_safety:results_ros2_live_bridge/profile_objective_selector_autonomy_v1_summary.json \
  --binding-objective-schedule balanced_safety_utility@0,autonomy_safety@2,balanced_safety_utility@4 \
  --transition-summary-json results_ros2_live_bridge/dynamic_objective_transition_2robot_fair_budget_3seed_summary.json \
  --transition-markdown results_ros2_live_bridge/dynamic_objective_transition_2robot_fair_budget_3seed_report.md \
  --title "ROS 2 Live Dynamic Objective Transition 2-Robot Fair Budget 3-Seed T3 V1" \
  --json
python3 -m scripts.report_robot_budget_controller \
  --ticks 12 \
  --summary-json results_robot_budget/robot_budget_controller_smoke_summary.json \
  --markdown results_robot_budget/robot_budget_controller_smoke_report.md
python3 -m scripts.compare_ros2_robot_budget_summaries \
  --summary baseline:results_ros2_live_bridge/dynamic_objective_transition_2robot_fair_budget_3seed_summary.json \
  --summary budgeted:results_ros2_live_bridge/dynamic_objective_transition_2robot_budgeted_3seed_summary.json \
  --summary budgeted_floor:results_ros2_live_bridge/dynamic_objective_transition_2robot_budgeted_floor_3seed_summary.json \
  --summary tailrisk:results_ros2_live_bridge/dynamic_objective_transition_2robot_budgeted_tailrisk_3seed_summary.json \
  --summary-json results_ros2_live_bridge/robot_budget_policy_compare_summary.json \
  --markdown results_ros2_live_bridge/robot_budget_policy_compare_report.md \
  --title "ROS 2 Robot Budget Policy Comparison T3 V1"
python3 -m scripts.report_t2e_results \
  --metrics results_t2e_ros2/metrics.jsonl \
  --markdown results_t2e_ros2/report.md \
  --csv results_t2e_ros2/report.csv
python3 -m scripts.compare_t2e_baselines \
  --baseline wifi_v1:results_t2e_ros2/baseline_wifi_v1_metrics.jsonl:results_t2e_ros2/baseline_wifi_v1_summary.json \
  --baseline roaming_v1:results_t2e_ros2/baseline_roaming_v1_metrics.jsonl:results_t2e_ros2/baseline_roaming_v1_summary.json
python3 -m scripts.run_fleet_scale_benchmark --robots 10,25,50,100 --seeds 7,13,29 --seconds 30
python3 scripts/run_fleet_optimizer_probe.py --json
python3 scripts/run_online_fleet_plan_probe.py --json
python3 scripts/run_fleet_optimizer_runtime_probe.py --json
python3 scripts/run_rmw_docker_router_fleet_plan_probe.py --json
python3 scripts/run_rmw_docker_router_live_telemetry_plan_probe.py --json
python3 -m unittest discover -s tests
```

## Project Structure

```text
docs/
  KIM_CHI_NAM.md          Project mindset and non-negotiable principles
  RESEARCH_PLAN.md        Research gap, novelty, and evaluation plan
  ARCHITECTURE.md         FleetRMW/FleetQoX system architecture
  RMW_ROADMAP.md          Roadmap from simulator to ROS 2 RMW
  FLEETRMW_SAMPLE_ENVELOPE_V1.md  Native publisher/sample identity envelope
  FLEETRMW_DATA_FRAME_V1.md  Dependency-free FleetRMW data-plane frame codec
  ROS2_RMW_DATA_FRAME_MATRIX_V1.md  FastDDS/CycloneDDS/Zenoh frame-mode matrix
  ROS2_PROFILE_OBJECTIVE_SELECTOR_V1.md  Profile/objective-aware packet/RMW selector
  FLEET_LEVEL_QOS_QOE_OPTIMIZER_V1.md  Fleet-level path optimizer over RMW/router telemetry
  ONLINE_FLEET_PATH_PLAN_CONTROLLER_V1.md  Online telemetry-to-path-plan controller probe
  FLEET_OPTIMIZER_RUNTIME_ACTUATION_V1.md  Sidecar runtime optimizer actuation probe
  RMW_ROUTER_FLEET_PLAN_PROBE_V1.md  C++ RMW path-ID to router-peer actuation probe
  RMW_ROUTER_LIVE_TELEMETRY_PLAN_PROBE_V1.md  Router telemetry to live RMW plan update probe
  ROS2_LIVE_CONTINUOUS_BINDING_V1.md  Live bridge adaptive transport binding refresh
  ROS2_LIVE_PROFILE_TRANSITION_T3_V1.md  Docker T3 Wi-Fi/WAN/roaming live transition evidence
  ROS2_LIVE_PROFILE_TRANSITION_BASELINES_T3_V1.md  Adaptive-vs-static live transition binding matrix
  ROS2_LIVE_PROFILE_TRANSITION_BINDING_3SEED_T3_V1.md  Three-seed adaptive-vs-static transition binding evidence
  ROS2_LIVE_DYNAMIC_OBJECTIVE_BINDING_T3_V1.md  Three-seed live profile/objective transition evidence
  ROS2_LIVE_DYNAMIC_OBJECTIVE_MULTI_ROBOT_T3_V1.md  Two-robot live profile/objective transition and local-service evidence
  ROBOT_BUDGET_AWARE_CONTROLLER_V1.md  Per-robot virtual-queue budget-aware admission controller
  ROS2_PACKET_FORMAT_COMPARE_V1.md  Legacy JSON vs FleetRMW data-frame comparison
  ROS2_PACKET_FORMAT_RMW_MATRIX_V1.md  2 x 3 packet-format/RMW transition matrix
  ROS2_REPEATED_PACKET_FORMAT_RMW_HARNESS_V1.md  Repeated seed/profile ROS 2 matrix harness
  ROS2_REPEATED_PACKET_FORMAT_RMW_WIFI_3SEED_V1.md  Full 3-seed Wi-Fi packet-format/RMW evidence
  ROS2_REPEATED_PACKET_FORMAT_RMW_WAN_3SEED_V1.md  Full 3-seed WAN packet-format/RMW evidence
  ROS2_REPEATED_PACKET_FORMAT_RMW_ROAMING_3SEED_V1.md  Full 3-seed roaming packet-format/RMW evidence
  RMW_SAMPLE_CONTRACT_V1.md  Dependency-free post-admission sample contract
  RMW_MULTI_ROBOT_LIVE_STOCHASTIC_NETEM_SWEEP_V1.md  Live RMW stochastic loss-envelope sweep
  RMW_MULTI_ROBOT_LIVE_STOCHASTIC_NETEM_ABLATION_V1.md  Proactive repair ablation over the live stochastic sweep
  RMW_LIVE_BASELINE_COMPARISON_V1.md  Indirect FleetRMW-native vs ROS 2 live-bridge baseline map
  ROS2_DIRECT_RMW_NETEM_MATRIX_V1.md  Direct ROS 2 RMW pub/sub netem baseline seed
  ROS2_RMW_SOURCE_METADATA_MATRIX_V1.md  FastDDS/CycloneDDS/Zenoh callback metadata matrix
  EXPERIMENTAL_RESULTS_V1.md  First evidence snapshot and research gaps
  SIDECAR_REPLAY_V1.md    Sidecar trace/replay evidence
  SIDECAR_RUNTIME_V1.md   Live sidecar TCP/UDP runtime smoke
  SIDECAR_NETEM_V1.md     Live sidecar through Docker/tc-netem
  SIDECAR_NETEM_MATRIX_V1.md  FIFO/static/CSDS/predictive sidecar-netem matrix
  SIDECAR_NETEM_MATRIX_V2.md  Adds risk-guarded predictive sidecar-netem matrix
  SIDECAR_CLOSED_LOOP_V1.md   Closed-loop sidecar feedback over Docker/tc-netem
  SIDECAR_LAGRANGIAN_V1.md    Soft risk-constrained predictive admission
  LAGRANGIAN_SWEEP_V1.md      Offline Lagrangian parameter sweep and risk-reset signal
  LAGRANGIAN_OUTCOME_ADAPTATION_V1.md  Outcome-driven Lagrangian update proposal
  SIDECAR_LAGRANGIAN_VARIANTS_NETEM_V1.md  Labeled Lagrangian netem variants
  SIDECAR_LAGRANGIAN_OUTCOME_ADAPTATION_NETEM_V2.md  Adapted Lagrangian netem evidence
  SIDECAR_LAG_ADAPT_002_5SEED_NETEM.md  Five-seed adapted Lagrangian evidence
  LAGRANGIAN_OUTCOME_ADAPTATION_V3.md  Second measured Lagrangian update proposal
  SIDECAR_LAGRANGIAN_OUTCOME_ADAPTATION_NETEM_V3_5SEED.md  Five-seed lag_adapt_003 evidence
  SIDECAR_PROFILE_ROBUSTNESS_V1.md  LAN/WAN/roaming profile robustness smoke
  SIDECAR_PROFILE_AWARE_LAGRANGIAN_V1.md  Profile-aware Lagrangian controller evidence
  SIDECAR_INTENT_WAN_V1.md  Control-intent WAN feasibility evidence
  ROS2_SHIM_BOUNDARY_V1.md  Dependency-free ROS 2 sample/QoS adapter boundary
  ROS2_LIVE_BRIDGE_V1.md  Live rclpy-to-sidecar ingress bridge
  ROS2_EGRESS_BRIDGE_V1.md  Sidecar UDP to ROS 2 egress envelope and typed Twist bridge
  ROS2_LOCAL_CONTROL_LEASE_V1.md  Robot-side lease gate for typed cmd_vel
  ROS2_PROJECTION_QUALITY_GATE_V1.md  Consumer-side gate for typed state/scan projections
  ROS2_DOCKER_LIVE_BRIDGE_T3.md  Dockerized ROS 2 live integration harness
  ROS2_8ROBOT_LIVELINESS_ACK_HORIZON_V1.md  8-robot source ACK/NACK recovery horizon evidence
  SEMANTIC_CONTRACT_V1.md  Feasibility-aware semantic contract layer
  SIDECAR_SEMANTIC_CONTRACT_WAN_V1.md  Semantic-contract scheduler WAN smoke
  SIDECAR_SEMANTIC_CONTRACT_LOSSAWARE_COMPARE_WAN_V1.md  Loss-aware semantic scheduler comparison
  SIDECAR_SEMANTIC_CONTRACT_ADAPTIVE_WAN_V1.md  Adaptive semantic variant selector comparison
  SIDECAR_SEMANTIC_CONTRACT_SUPERVISORY_ROAMING_PREFLIGHT_V1.md  Supervisory intent roaming preflight
  SIDECAR_SEMANTIC_CONTRACT_ADAPTIVE_ROAMING_V1.md  Supervisory/adaptive roaming netem evidence
  SIDECAR_REPEATED_STATS_V1.md  Repeated-run CI and Pareto evidence

fleetqox/
  model.py                QoX, flow, network, and decision data models
  control_plane.py        Predictive, guarded, Lagrangian, profile/contextual, intent, semantic-contract, and adaptive semantic schedulers
  semantic_contract.py    Flow contracts, semantic transforms, and feasibility certificates
  lagrangian_sweep.py     Offline parameter sweep for Lagrangian admission
  lagrangian_adaptation.py  Outcome-driven Lagrangian variant adaptation
  local_control_lease.py  Robot-side typed command lease evaluator
  projection_quality_gate.py  Consumer-side typed projection quality evaluator
  rmw_contract.py         Post-admission FleetRMW sample identity/delivery contract
  rmw_socket.py           UDP socket-backed FleetRMW data-frame and ACK/NACK boundary
  rmw_transport_loop.py   Persistent multi-stream socket loop with NACK retransmit
  sidecar_contract.py     Sidecar/RMW-shim decision trace contract
  sidecar_egress.py       Dependency-free sidecar packet decode and egress routing
  sidecar_runtime.py      TCP sidecar skeleton with pluggable policies and UDP emission
  sidecar_metrics.py      Runtime decision/receive, per-robot QoS, and budget metric analysis
  sidecar_repeated.py     Repeated-run sidecar statistics and Pareto analysis
  transport_selector.py   Profile/objective-aware packet-format/RMW selector
  scheduler.py            Causal Semantic Deadline Scheduler
  ros2_shim.py            Dependency-free ROS 2 sample/QoS to sidecar batch adapter
  ros2_live_bridge.py     Live ROS 2 callback buffer and sidecar TCP client
  simulator.py            Fleet workload and baseline comparison
  comparison.py           Cross-baseline report helpers
  fleet_scale.py          Fleet-scale benchmark matrix helpers

experiments/
  local_controller_profiles_v1.json  Robot/controller lease safety profiles
  ros2_live_bridge_tb4_binding_v1.json  ROS 2 live bridge config with adaptive binding
  ros2_live_bridge_tb4_typed_projection_v1.json  ROS 2 typed projection coverage config

scripts/
  run_benchmark.py        CLI benchmark entry point
  compare_t2e_baselines.py  Compare ROS 2/netem baseline reports
  run_fleet_scale_benchmark.py  Run local fleet-scale benchmark matrix
  run_sidecar_netem.py    Run live sidecar policies through Docker/tc-netem
  run_lagrangian_sweep.py Run offline Lagrangian parameter sweeps
  adapt_lagrangian_from_netem.py  Generate next Lagrangian variant from measured netem outcomes
  run_sidecar_repeated_netem.py  Run repeated sidecar-netem sweeps over seeds
  report_sidecar_repeated.py  Summarize sidecar metrics across repeated runs
  select_ros2_transport.py    Select packet-format/RMW policy from repeated summaries
  report_robot_budget_controller.py  Offline smoke for per-robot budget-aware admission
  compare_ros2_robot_budget_summaries.py  Compare ROS 2 per-robot budget policy summaries
  smoke_ros2_live_bridge_binding.py  Dependency-free live bridge binding refresh smoke
  apply_netem_transition.py   Apply timed tc/netem profile transitions inside Docker
  run_ros2_docker_live_bridge.py  Docker ROS 2 live bridge, RMW/packet matrices, transition, multi-robot, and binding baseline runner
  feed_sidecar_closed_loop.py  Feed sidecar with per-flow action feedback
  run_ros2_egress_bridge.py    Publish sidecar UDP events back into ROS 2 topics
  run_ros2_local_controller_lease.py  Gate typed Twist with namespace-aware local control leases
  run_ros2_projection_quality_gate.py Gate typed odom/scan from namespace-aware wrapped or identity-carrying projection quality
  run_ros2_string_monitor.py   Monitor ROS 2 String and typed egress topics across robot namespaces in Docker T3
  run_rmw_socket_smoke.py      Exercise FleetRMW data-frame and ACK/NACK over UDP sockets
  run_rmw_docker_multi_robot_live_stochastic_netem_sweep.py  Sweep live RMW Docker netem loss scales
  run_rmw_docker_multi_robot_live_stochastic_netem_ablation.py  Compare proactive repair modes over the live stochastic sweep
  compare_fleetrmw_live_baselines.py  Normalize FleetRMW-native and ROS 2 live-bridge evidence with comparability caveats
  run_ros2_direct_rmw_netem_probe.py  Direct ROS 2 pub/sub RMW baseline under one netem profile
  run_ros2_direct_rmw_netem_matrix.py  Matrix runner for direct ROS 2 RMW netem baselines

ros2_ws/src/
  fleetrmw_interfaces/         ROS 2 message wrappers for FleetRMW projection quality
  rmw_fleetqox_cpp/            C++ FleetRMW transport-boundary reference package
```

## Core Thesis

ROS 2 middleware for robot fleets should not merely deliver topics. It should
prioritize information by the amount of task risk it reduces under real network
constraints.

FleetRMW therefore treats DDS, Zenoh, QUIC, WebRTC, and shared memory as data
plane options. The research contribution is the control plane: causal-semantic
QoX scheduling for large ROS 2 robot fleets.

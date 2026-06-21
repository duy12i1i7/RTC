# Experimental Results V1

## Scope

This snapshot consolidates the first evidence layer for FleetRMW/FleetQoX:

- ROS 2 `performance_test` traffic over Docker + `tc netem`;
- Fast DDS, Cyclone DDS, and Zenoh RMW baselines;
- Wi-Fi loss/jitter and roaming-like capacity-drop impairments;
- local fleet-scale QoS/QoE simulator for 10, 25, 50, and 100 robots;
- live sidecar runtime matrix over Docker + `tc netem`.

These results are not yet a publishable final benchmark. They are the evidence
used to decide what the first FleetRMW prototype must solve.

## Artifacts

| artifact | path |
| --- | --- |
| Wi-Fi baseline report | `results_t2e_ros2/baseline_wifi_v1_report.md` |
| Roaming baseline report | `results_t2e_ros2/baseline_roaming_v1_report.md` |
| Wi-Fi vs roaming comparison | `results_t2e_ros2/baseline_wifi_vs_roaming_report.md` |
| Fleet-scale simulator report | `results_fleet_scale/fleet_scale_v1_report.md` |
| Fleet-scale raw records | `results_fleet_scale/fleet_scale_v1_records.jsonl` |
| Sidecar replay report | `docs/SIDECAR_REPLAY_V1.md` |
| Sidecar runtime report | `docs/SIDECAR_RUNTIME_V1.md` |
| Sidecar netem report | `docs/SIDECAR_NETEM_V1.md` |
| Sidecar netem matrix report | `docs/SIDECAR_NETEM_MATRIX_V1.md` |
| Sidecar netem matrix raw metrics | `results_sidecar_netem_matrix/sidecar_netem_matrix_v1_matrix_metrics.jsonl` |
| Risk-guarded sidecar matrix report | `docs/SIDECAR_NETEM_MATRIX_V2.md` |
| Risk-guarded sidecar raw metrics | `results_sidecar_netem_matrix_v4/sidecar_netem_matrix_v4_matrix_metrics.jsonl` |
| Closed-loop sidecar report | `docs/SIDECAR_CLOSED_LOOP_V1.md` |
| Closed-loop sidecar raw metrics | `results_sidecar_netem_closed_loop/sidecar_netem_closed_loop_v1_matrix_metrics.jsonl` |
| Lagrangian sidecar report | `docs/SIDECAR_LAGRANGIAN_V1.md` |
| Lagrangian sidecar raw metrics | `results_sidecar_netem_lagrangian_v3_matrix/sidecar_netem_lagrangian_v3_matrix_matrix_metrics.jsonl` |
| Lagrangian parameter sweep | `docs/LAGRANGIAN_SWEEP_V1.md` |
| Lagrangian sweep records | `results_lagrangian_sweep/lagrangian_sweep_v1_records.jsonl` |
| Repeated sidecar statistics | `docs/SIDECAR_REPEATED_STATS_V1.md` |
| Repeated sidecar summary JSON | `results_sidecar_repeated/closed_loop_lagrangian_summary.json` |
| Lagrangian netem variants | `docs/SIDECAR_LAGRANGIAN_VARIANTS_NETEM_V1.md` |
| Outcome adaptation netem | `docs/SIDECAR_LAGRANGIAN_OUTCOME_ADAPTATION_NETEM_V2.md` |
| lag_adapt_002 5-seed netem | `docs/SIDECAR_LAG_ADAPT_002_5SEED_NETEM.md` |
| lag_adapt_003 5-seed netem | `docs/SIDECAR_LAGRANGIAN_OUTCOME_ADAPTATION_NETEM_V3_5SEED.md` |
| Profile robustness smoke | `docs/SIDECAR_PROFILE_ROBUSTNESS_V1.md` |
| Profile-aware Lagrangian smoke | `docs/SIDECAR_PROFILE_AWARE_LAGRANGIAN_V1.md` |
| Control-intent WAN smoke | `docs/SIDECAR_INTENT_WAN_V1.md` |
| Semantic contract layer | `docs/SEMANTIC_CONTRACT_V1.md` |
| Semantic contract WAN smoke | `docs/SIDECAR_SEMANTIC_CONTRACT_WAN_V1.md` |
| Loss-aware semantic contract WAN comparison | `docs/SIDECAR_SEMANTIC_CONTRACT_LOSSAWARE_COMPARE_WAN_V1.md` |
| Adaptive semantic contract WAN comparison | `docs/SIDECAR_SEMANTIC_CONTRACT_ADAPTIVE_WAN_V1.md` |
| Adaptive/supervisory semantic contract roaming comparison | `docs/SIDECAR_SEMANTIC_CONTRACT_ADAPTIVE_ROAMING_V1.md` |
| Dockerized ROS 2 live bridge T3 | `docs/ROS2_DOCKER_LIVE_BRIDGE_T3.md` |
| ROS 2 sidecar egress bridge | `docs/ROS2_EGRESS_BRIDGE_V1.md` |
| ROS 2 local control lease | `docs/ROS2_LOCAL_CONTROL_LEASE_V1.md` |
| ROS 2 projection quality gate | `docs/ROS2_PROJECTION_QUALITY_GATE_V1.md` |
| FleetRMW data-frame packet-format comparison | `docs/ROS2_PACKET_FORMAT_COMPARE_V1.md` |
| FleetRMW packet-format/RMW matrix | `docs/ROS2_PACKET_FORMAT_RMW_MATRIX_V1.md` |
| ROS 2 repeated packet-format/RMW harness | `docs/ROS2_REPEATED_PACKET_FORMAT_RMW_HARNESS_V1.md` |
| ROS 2 repeated Wi-Fi packet-format/RMW matrix | `docs/ROS2_REPEATED_PACKET_FORMAT_RMW_WIFI_3SEED_V1.md` |
| ROS 2 repeated WAN packet-format/RMW matrix | `docs/ROS2_REPEATED_PACKET_FORMAT_RMW_WAN_3SEED_V1.md` |
| ROS 2 live continuous binding | `docs/ROS2_LIVE_CONTINUOUS_BINDING_V1.md` |
| ROS 2 live profile transition T3 | `docs/ROS2_LIVE_PROFILE_TRANSITION_T3_V1.md` |
| ROS 2 live profile transition baselines T3 | `docs/ROS2_LIVE_PROFILE_TRANSITION_BASELINES_T3_V1.md` |
| ROS 2 live profile transition binding 3-seed T3 | `docs/ROS2_LIVE_PROFILE_TRANSITION_BINDING_3SEED_T3_V1.md` |
| ROS 2 live dynamic-objective binding 3-seed T3 | `docs/ROS2_LIVE_DYNAMIC_OBJECTIVE_BINDING_T3_V1.md` |
| ROS 2 live dynamic-objective multi-robot T3 | `docs/ROS2_LIVE_DYNAMIC_OBJECTIVE_MULTI_ROBOT_T3_V1.md` |
| ROS 2 live per-robot QoS budget T3 report | `results_ros2_live_bridge/dynamic_objective_transition_2robot_fair_budget_3seed_report.md` |
| Per-robot budget-aware controller | `docs/ROBOT_BUDGET_AWARE_CONTROLLER_V1.md` |
| ROS 2 robot budget policy comparison | `results_ros2_live_bridge/robot_budget_policy_compare_report.md` |
| ROS 2 QoE stable-probe recovery summary | `results_ros2_live_bridge/dynamic_objective_transition_2robot_feedback_deadline_ownership_qoe_stable_probe_3seed_summary.json` |
| ROS 2 QoE stable-probe recovery report | `results_ros2_live_bridge/dynamic_objective_transition_2robot_feedback_deadline_ownership_qoe_stable_probe_3seed_report.md` |
| ROS 2 four-robot QoE recovery quota summary | `results_ros2_live_bridge/dynamic_objective_transition_4robot_qoe_recovery_quota_smoke_summary.json` |
| ROS 2 four-robot QoE recovery quota report | `results_ros2_live_bridge/dynamic_objective_transition_4robot_qoe_recovery_quota_smoke_report.md` |
| ROS 2 N-robot QoE recovery quota matrix | `docs/ROS2_N_ROBOT_QOE_RECOVERY_QUOTA_MATRIX_V1.md` |
| ROS 2 four-robot QoE quota 3-seed summary | `results_ros2_live_bridge/dynamic_objective_transition_4robot_qoe_recovery_quota_3seed_summary.json` |
| ROS 2 eight-robot QoE quota 3-seed summary | `results_ros2_live_bridge/dynamic_objective_transition_8robot_qoe_recovery_quota_3seed_summary.json` |
| ROS 2 N-robot QoE quota aggregate report | `results_ros2_live_bridge/n_robot_qoe_recovery_quota_matrix_report.md` |
| ROS 2 eight-robot terminal-replay audit | `results_ros2_live_bridge/n_robot_qoe_recovery_quota_8robot_terminal_replay_3seed_summary.json` |
| ROS 2 eight-robot ACK-window seed-29 audit | `results_ros2_live_bridge/n_robot_qoe_recovery_quota_8robot_ack_window_seed29_summary.json` |
| ROS 2 eight-robot ACK-window 3-seed audit | `results_ros2_live_bridge/n_robot_qoe_recovery_quota_8robot_ack_window_3seed_summary.json` |
| ROS 2 eight-robot persistent-ACK seed-29 audit | `results_ros2_live_bridge/n_robot_qoe_recovery_quota_8robot_persistent_ack_seed29_summary.json` |
| ROS 2 eight-robot persistent-ACK 3-seed audit | `results_ros2_live_bridge/n_robot_qoe_recovery_quota_8robot_persistent_ack_3seed_summary.json` |
| ROS 2 eight-robot immediate-ACK 3-seed negative control | `results_ros2_live_bridge/n_robot_qoe_recovery_quota_8robot_persistent_ack_immediate_3seed_summary.json` |
| ROS 2 eight-robot paced ACK8 seed-13 audit | `results_ros2_live_bridge/n_robot_qoe_recovery_quota_8robot_paced_ack8_seed13_summary.json` |
| ROS 2 eight-robot paced ACK8 3-seed audit | `results_ros2_live_bridge/n_robot_qoe_recovery_quota_8robot_paced_ack8_3seed_summary.json` |
| ROS 2 eight-robot adaptive ACK-only seed-13 audit | `results_ros2_live_bridge/n_robot_qoe_recovery_quota_8robot_adaptive_ack_timebounded_seed13_summary.json` |
| ROS 2 eight-robot adaptive ACK-only 3-seed audit | `results_ros2_live_bridge/n_robot_qoe_recovery_quota_8robot_adaptive_ack_timebounded_3seed_summary.json` |
| ROS 2 eight-robot adaptive piggyback ACK 3-seed audit | `results_ros2_live_bridge/n_robot_qoe_recovery_quota_8robot_adaptive_ack_piggyback_3seed_summary.json` |
| ROS 2 eight-robot aligned temporal-guard audit | `results_ros2_live_bridge/n_robot_qoe_recovery_quota_8robot_aligned_temporal_guard_seed29_summary.json` |
| ROS 2 eight-robot aligned 8-second audit | `results_ros2_live_bridge/n_robot_qoe_recovery_quota_8robot_aligned_baseline_8s_seed29_summary.json` |
| FleetRMW source-sequence ACK/NACK primitive | `docs/RMW_ACK_NACK_V1.md` |
| FleetRMW minimal publish/take boundary | `docs/RMW_MINIMAL_BOUNDARY_V1.md` |
| ROS 2 eight-robot egress ACK/NACK seed-13 audit | `results_ros2_live_bridge/n_robot_qoe_recovery_quota_8robot_egress_acknack_seed13_aggregate_summary.json` |
| ROS 2 eight-robot liveliness ACK-horizon seed-13 audit | `results_ros2_live_bridge/n_robot_qoe_recovery_quota_8robot_liveliness_horizon_seed13_aggregate_summary.json` |
| ROS 2 eight-robot liveliness ACK-horizon 3-seed audit | `results_ros2_live_bridge/n_robot_qoe_recovery_quota_8robot_liveliness_horizon_3seed_aggregate_summary.json` |
| ROS 2 eight-robot liveliness ACK-horizon milestone | `docs/ROS2_8ROBOT_LIVELINESS_ACK_HORIZON_V1.md` |
| FleetRMW UDP socket publish/take smoke | `results_rmw_socket/socket_smoke_skip_every2_summary.json` |
| C++ FleetRMW transport-boundary smoke | `results_rmw_socket/cpp_transport_smoke_summary.json` |
| Docker ROS C++ FleetRMW transport smoke | `results_rmw_socket/docker_cpp_transport_smoke_summary.json` |
| Docker ROS Python-to-C++ frame probe | `results_rmw_socket/docker_cpp_frame_probe_summary.json` |
| Docker ROS RMW lifecycle probe | `results_rmw_socket/docker_rmw_lifecycle_probe_summary.json` |
| Docker ROS RMW serialized pub/sub probe | `results_rmw_socket/docker_rmw_serialized_pubsub_probe_summary.json` |
| Docker ROS RMW type-erased typed pub/sub probe | `results_rmw_socket/docker_rmw_typed_pubsub_probe_summary.json` |
| Docker ROS RMW std_msgs/String typed probe | `results_rmw_socket/docker_rmw_std_msgs_string_probe_summary.json` |
| Docker ROS RMW geometry_msgs/Twist typed probe | `results_rmw_socket/docker_rmw_geometry_twist_probe_summary.json` |
| Docker ROS RMW service QoS stale-frame probe | `results_rmw_socket/docker_rmw_service_qos_probe_summary.json` |
| Docker ROS RMW service error probe | `results_rmw_socket/docker_rmw_service_error_probe_summary.json` |
| Docker ROS CLI service timeout probe | `results_rmw_socket/docker_ros2_service_timeout_probe_summary.json` |
| Docker ROS CLI router-mediated service timeout probe | `results_rmw_socket/docker_router_ros2_service_timeout_probe_summary.json` |
| Docker ROS CLI router-mediated malformed service response | `results_rmw_socket/docker_router_ros2_malformed_service_response_probe_summary.json` |
| Docker ROS RMW action-frame contract probe | `results_rmw_socket/docker_rmw_action_frame_probe_summary.json` |
| Docker ROS RMW router-mediated action-frame probe | `results_rmw_socket/docker_rmw_router_action_frame_probe_summary.json` |
| Docker ROS RMW rclpy.action smoke probe | `results_rmw_socket/docker_rmw_rclpy_action_probe_summary.json` |
| Docker ROS RMW router-mediated rclpy.action smoke probe | `results_rmw_socket/docker_rmw_router_rclpy_action_probe_summary.json` |
| Docker ROS RMW router-mediated rclpy.action QoS probe | `results_rmw_socket/docker_rmw_router_rclpy_action_qos_probe_summary.json` |
| Docker ROS RMW wait/guard probe | `results_rmw_socket/docker_rmw_wait_probe_summary.json` |
| Docker ROS RMW graph probe | `results_rmw_socket/docker_rmw_graph_probe_summary.json` |
| Docker ROS RMW remote graph lease probe | `results_rmw_socket/docker_rmw_remote_graph_lease_probe_summary.json` |
| Docker ROS RMW inter-process serialized pub/sub probe | `results_rmw_socket/docker_rmw_interprocess_pubsub_probe_summary.json` |
| Docker ROS RMW multi-container router probe | `results_rmw_socket/docker_rmw_multicontainer_router_probe_summary.json` |
| Docker ROS RMW multi-robot QoS scheduler | `results_rmw_socket/docker_router_multi_robot_qos_matrix_summary.json` |
| Docker ROS RMW adaptive multi-robot QoS netem | `results_rmw_socket/docker_router_multi_robot_qos_netem_matrix_summary.json` |
| Docker ROS RMW live adaptive multi-robot QoS netem | `results_rmw_socket/docker_router_multi_robot_qos_live_adaptive_matrix_summary.json` |
| Docker ROS RMW live adaptive repeated-loss QoS netem | `results_rmw_socket/docker_router_multi_robot_qos_live_adaptive_repeated_loss_matrix_summary.json` |
| Docker ROS RMW scheduled ACK/NACK repair | `results_rmw_socket/docker_router_scheduled_reliability_probe_summary.json` |
| Docker ROS RMW repeated-loss scheduled ACK/NACK repair | `results_rmw_socket/docker_router_scheduled_reliability_repeated_loss_matrix_summary.json` |
| Docker ROS RMW concurrent multi-robot scheduled ACK/NACK repair | `results_rmw_socket/docker_router_multi_robot_scheduled_reliability_probe_summary.json` |
| Docker ROS RMW mixed action/control/state repair | `results_rmw_socket/docker_router_mixed_action_control_state_probe_summary.json` |
| Docker ROS RMW proactive deadline diversity | `results_rmw_socket/docker_router_proactive_deadline_diversity_probe_summary.json` |
| Docker ROS RMW repeated proactive deadline diversity | `results_rmw_socket/docker_router_proactive_deadline_diversity_repeated_loss_matrix_summary.json` |
| Docker ROS RMW concurrent proactive deadline diversity | `results_rmw_socket/docker_router_multi_robot_proactive_deadline_diversity_probe_summary.json` |
| Docker ROS RMW repeated concurrent proactive deadline diversity | `results_rmw_socket/docker_router_multi_robot_proactive_deadline_diversity_repeated_loss_matrix_summary.json` |
| Fleet optimizer redundancy-budget/failure-domain probe | `results_rmw_socket/fleet_optimizer_redundancy_budget_probe_summary.json` |
| Docker ROS RMW budgeted multi-robot fleet-plan actuation | `results_rmw_socket/docker_router_multi_robot_budgeted_fleet_plan_probe_summary.json` |
| Docker ROS RMW active-publisher budget epoch transition | `results_rmw_socket/docker_router_multi_robot_budgeted_fleet_plan_epoch_probe_summary.json` |
| Docker ROS RMW subscriber-QoE closed-loop budget epoch | `results_rmw_socket/docker_router_multi_robot_qoe_feedback_budget_probe_summary.json` |
| Docker ROS RMW repeated subscriber-QoE budget matrix | `results_rmw_socket/docker_router_multi_robot_qoe_feedback_budget_repeated_matrix_summary.json` |
| Docker ROS RMW measured-QoE protection migration | `results_rmw_socket/docker_router_multi_robot_qoe_protection_migration_probe_summary.json` |
| Docker ROS RMW 4/8/16-robot protection-migration scale matrix | `results_rmw_socket/docker_router_qoe_protection_migration_scale_matrix_summary.json` |
| Docker ROS RMW repeated sequential-QoE protection migration | `results_rmw_socket/docker_router_qoe_protection_migration_sequential_repeated_matrix_summary.json` |
| Docker ROS RMW harsh-loss sequential-QoE protection migration | `results_rmw_socket/docker_router_qoe_protection_migration_sequential_harsh_matrix_summary.json` |
| Docker ROS RMW confidence-fallback protection smoke | `results_rmw_socket/docker_router_multi_robot_qoe_confidence_fallback_smoke_summary.json` |
| Docker ROS RMW confidence-fallback matrix smoke | `results_rmw_socket/docker_router_qoe_protection_migration_confidence_fallback_matrix_smoke_summary.json` |
| Docker ROS RMW harsh-loss confidence-fallback matrix | `results_rmw_socket/docker_router_qoe_protection_migration_sequential_harsh_fallback_matrix_summary.json` |
| Docker ROS RMW confidence-fallback recovery smoke | `results_rmw_socket/docker_router_multi_robot_qoe_confidence_fallback_recovery_smoke_summary.json` |
| Docker ROS RMW confidence-fallback recovery matrix smoke | `results_rmw_socket/docker_router_qoe_protection_migration_confidence_fallback_recovery_matrix_smoke_summary.json` |
| Docker ROS RMW harsh-loss confidence-fallback recovery matrix | `results_rmw_socket/docker_router_qoe_protection_migration_sequential_harsh_fallback_recovery_matrix_summary.json` |
| Docker ROS RMW targeted repair attribution smoke | `results_rmw_socket/docker_router_qoe_targeted_repair_smoke_summary.json` |
| Docker ROS RMW targeted repair matrix smoke | `results_rmw_socket/docker_router_qoe_targeted_repair_matrix_smoke_summary.json` |
| Docker ROS RMW controller-directed repair at 250 ms SLO | `results_rmw_socket/docker_router_qoe_controller_directed_repair_deadline_aware_smoke_summary.json` |
| Docker ROS RMW controller-directed repair at feasible SLO | `results_rmw_socket/docker_router_qoe_controller_directed_repair_feasible_slo_smoke_summary.json` |
| Docker ROS RMW repair-budget exhaustion smoke | `results_rmw_socket/docker_router_qoe_controller_directed_repair_budget_exhaustion_smoke_summary.json` |
| Docker ROS RMW controller-directed repair matrix smoke | `results_rmw_socket/docker_router_qoe_controller_directed_repair_matrix_smoke_summary.json` |
| Docker ROS RMW coalesced controller-directed repair smoke | `results_rmw_socket/docker_router_qoe_controller_directed_repair_coalesced_smoke_summary.json` |
| Docker ROS RMW single-attempt repair smoke | `results_rmw_socket/docker_router_qoe_controller_directed_repair_single_attempt_smoke_summary.json` |
| Docker ROS RMW fleet repair admission, sufficient capacity | `results_rmw_socket/docker_router_qoe_fleet_repair_admission_full_capacity_smoke_summary.json` |
| Docker ROS RMW fleet repair admission, constrained capacity | `results_rmw_socket/docker_router_qoe_fleet_repair_admission_constrained_capacity_smoke_summary.json` |
| Docker ROS RMW stochastic netem sweep | `docs/RMW_MULTI_ROBOT_LIVE_STOCHASTIC_NETEM_SWEEP_V1.md` |
| Docker ROS RMW proactive repair ablation | `docs/RMW_MULTI_ROBOT_LIVE_STOCHASTIC_NETEM_ABLATION_V1.md` |
| FleetRMW live baseline comparison map | `docs/RMW_LIVE_BASELINE_COMPARISON_V1.md` |
| FleetRMW matched four-robot live telemetry matrix | `results_rmw_socket/docker_multi_robot_live_telemetry_matrix_4robot_report.md` |
| ROS 2 direct RMW netem baseline seed | `docs/ROS2_DIRECT_RMW_NETEM_MATRIX_V1.md` |
| FleetRMW 8/16/32 actuated-repair capacity frontier v3, 3 repetitions | `results_rmw_socket/docker_fleet_repair_capacity_frontier_8_16_32_3seed_actuated_v3_report.md` |
| FleetRMW actuated-repair capacity v3 smoke, 4 robots | `results_rmw_socket/docker_fleet_repair_capacity_frontier_4robot_smoke_v3_report.md` |
| Docker ROS RMW upstream Nav2/RMF lifecycle-manager/concurrent workload | `results_rmw_socket/docker_router_upstream_nav2_rmf_workload_v5_lifecycle_manager_concurrency4_summary.json` |
| Docker ROS standalone C++ type-support round trip | `results_rmw_socket/docker_cpp_typesupport_probe_summary.json` |
| Docker ROS router-mediated C++ interprocess pub/sub + service | `results_rmw_socket/docker_router_rclcpp_interprocess_probe_summary.json` |
| Docker ROS two-container POSIX shared-memory + UDP fallback | `results_rmw_socket/docker_shared_memory_probe_summary.json` |
| Docker ROS SHM-local + UDP-router hybrid de-dup | `results_rmw_socket/docker_shm_udp_hybrid_probe_summary.json` |
| Docker ROS introspection C/C++ loaned-message lifecycle | `results_rmw_socket/docker_loaned_message_probe_summary.json` |
| Native ns-3 Docker 8/16/32 fleet matrix | `results_ns3/ns3_docker_fleet_matrix_8_16_32_3seed_v1_summary.json` |
| Docker ROS RMW matched multi-topic router workload | `results_rmw_socket/docker_router_matched_multi_topic_probe_summary.json` |
| ROS 2 large-scale split-scope RMW comparison, 8/16/32 | `results_rmw_socket/large_scale_rmw_comparison_8_16_32_3seed_split_scope_v2_report.md` |

The repeated fleet-scale actuated-repair v3 artifact covers `8`, `16`, and `32`
robots with protected set size equal to half the fleet. The repetition
`7,13,29` artifact
`results_rmw_socket/docker_fleet_repair_capacity_frontier_8_16_32_3seed_actuated_v3_summary.json`
passes `27/27` rows and all `9/9` robot/capacity groups are monotonic. Capacity
fractions `0.25`, `0.5`, and `1.0` actuate exactly `1/2/4` repairs for `8`
robots, `2/4/8` for `16`, and `4/8/16` for `32`. Live QoE-qualified coverage
rises from `0.625` to `0.75` to `1.0` at every fleet size. Every candidate is
dropped once on both paths; admitted retransmission/repair overhead matches the
schedule exactly and every deferred candidate records the unresolved gap plus
`repair_not_admitted`. The maximum observed latency is `397.314 ms` under the
`400 ms` deadline. Student-t 95% intervals are reported; with only three runs,
some `32`-robot intervals for the mean extend slightly above the SLO even though
no observed row misses it.

The Nav2/RMF workload now passes both local fallback contracts and upstream
interfaces through the router. `NavigateFleet` and `DispatchFleetTask` retain
dependency-light success/cancel coverage; upstream
`nav2_msgs/action/NavigateToPose` passes success, feedback, cancel, and result;
RMF `SubmitTask` followed by `CancelTask` passes with a nested station task.
The v5 artifact reports `status=ok`, all four compatibility/upstream flags are
true, all four concurrent navigation goals and all four concurrent RMF
submissions complete. The official Nav2 C++ lifecycle manager drives STARTUP
and RESET; configure/activate/deactivate/cleanup returns the companion node to
`unconfigured`. The router forwards exactly `82` service frames with zero
invalid frames. This proves upstream manager transport and introspection-C++
service/wait readiness, but not yet a full Nav2 planner/controller plugin
deployment. The ROS CLI message matrix covers
`13/13` message cases, adding `PointCloud2`, `JointTrajectory`,
`DiagnosticArray`, `SampleIdentity`, and `ProjectionQuality` to the earlier
String/time/pose/scan/odometry/path set.

The standalone C++ type-support artifact also reports `status=ok`: C++
`std_msgs/String` and nested `geometry_msgs/PoseStamped` round-trip through
`rmw_serialize`/`rmw_deserialize` using the generic
`rosidl_typesupport_cpp` dispatcher, producing 40-byte and 129-byte FleetRMW
payloads respectively. The same runtime probe calls
`rmw_get_serialized_message_size` for statically bounded nested
`geometry_msgs/Pose` through both introspection C and C++; each predicted
maximum and actual serialized size equals `80` bytes. Unbounded `String`
sizing remains a controlled
`RMW_RET_UNSUPPORTED` boundary because artificial runtime bounds are not yet
interpreted.

The two-container `rclcpp` artifact also reports `status=ok`: a nested
`PoseStamped` request/reply crosses the router in both directions and a C++
`SetBool` client receives the C++ server response. The router records `2/2`
service frames, both Pose topics, reliable ACK/NACK traffic, and zero invalid
frames. Publisher/subscription network-flow queries report UDP/IPv4 on the
configured local port, and both request and response callbacks are observed.

The local transport artifact reports `status=ok` for a separate two-container
POSIX shared-memory run. Publisher and subscriber have zero UDP peers and both
report `transport_mode=shm`; the subscriber receives all `100000` payload bytes
with zero overwritten slots. Because SHM is not an IP flow, both RMW endpoint
queries return zero network-flow endpoints. A second fault-injected row uses an
invalid SHM name, reports `transport_mode=udp_fallback`, and completes local
serialized pub/sub. This proves the local-only SHM and fallback slice, not yet
hybrid local-SHM plus remote-network routing.

The follow-on hybrid artifact closes that scoped gap for UDP. Publisher and
subscriber both report `transport_mode=shm_udp_hybrid`; the publisher writes
the local ring and sends to the UDP router, which forwards one valid data
frame back to the subscriber endpoint. The subscriber observes both paths,
takes the 20 KB payload once, records `duplicate_data_frames_deduped=1`, and
reports zero SHM overwrites. This is evidence for SHM-local plus UDP-remote
hybrid routing, not QUIC.

The loaned-message artifact passes publisher borrow/publish, publisher
borrow/return, and subscription take/return for both introspection C and C++.
Endpoints advertise `can_loan_messages=true`, and outstanding allocations are
owned and finalized by FleetRMW. The artifact explicitly sets
`zero_copy_claim_allowed=false`: subscription data is currently deserialized
into middleware-owned memory rather than delivered by a zero-copy transport.

The native ns-3 3.41 campaign passes all `27/27` rows for `8/16/32` robots,
three network parameter envelopes, and seeds `7,13,29`. FIFO,
static-priority, and guarded FleetQoX use the same generated packet trace in
each row. The current model is a shared CSMA channel with data-rate/delay and
independent receive packet error; therefore the artifact sets
`high_fidelity_wireless_claim_allowed=false` and is not evidence for detailed
Wi-Fi roaming or 5G behavior.

The follow-on ns-3 Wi-Fi/mobility campaign also passes `27/27` rows for the
same fleet sizes and seeds. It uses a single 802.11g infrastructure AP with
stationary-near, mobile-moderate, and mobile-edge station profiles. Every
policy row has a positive receive count (minimum `538` packets). Guarded
FleetQoX has the highest utility in `8/27` rows, static priority in `16/27`,
and FIFO in `3/27`; the result demonstrates policy sensitivity rather than
general FleetQoX superiority. The artifact permits Wi-Fi and mobility-model
claims, but sets `roaming_handoff_claim_allowed=false` because no AP handoff is
modeled.

The dedicated dual-AP campaign closes that scoped gap: `27/27` rows pass and
all `585/585` expected endpoint transitions are observed through ns-3
`StaWifiMac` association/disassociation traces. A bridged CSMA backhaul keeps
station IP addresses stable across AP1-to-AP2 transitions, and every policy
row receives packets (minimum `284`). Static priority has the highest utility
in `20/27` rows, guarded FleetQoX in `5/27`, and FIFO in `2/27`; therefore the
artifact allows `roaming_handoff_claim_allowed=true` but keeps both general
policy superiority and high-fidelity wireless claims false.

The repeated `8/16/32` comparison against Fast DDS, Cyclone DDS, and Zenoh is
recorded in
`results_rmw_socket/large_scale_rmw_comparison_8_16_32_3seed_split_scope_v2_summary.json`.
The runner applies netem only after discovery, uses the same six-second
publisher reliability horizon, starts the required Zenoh router/session, and
reports Wilson success intervals plus Student-t metric intervals. FleetRMW,
Cyclone DDS, and Zenoh pass all `9/9` rows. Fast DDS passes `7/9`; the retained
failures are one incomplete state row at `8` robots and one at `16` robots.
FleetRMW's earlier 16-robot miss is closed, and a retransmit-thread shutdown
race that produced exit code `139` after complete delivery is fixed. This is
still not a same-hop superiority claim: FleetRMW uses
publisher-router-subscriber while DDS and Zenoh use direct application data
paths (Zenoh still requires its session router). The result is a
topology-caveated gap register and throughput/delivery envelope.
The v2 schema exposes allowed `direct_rmw_delivery_latency` and
`fleet_router_repair_value` scopes while marking `cross_scope_superiority` as
disallowed and `direct_claim_allowed=false`.

The latest budgeted fleet-plan actuation closes the gap between the Python
optimizer and the C++ RMW data plane. Four concurrent robot control topics run
through roaming and Wi-Fi netem paths. The optimizer assigns diverse-path
redundancy to the two robots with fairness debt and healthy-path unicast to the
other two. The measured run passes `4/4` robots, delivers every source sequence
within `100 ms`, records maximum latency `56.577 ms`, Jain fairness `1.0`, and
zero NACK retransmissions. FleetRMW executes `18` path transmissions versus
`24` for blanket dual-path protection, a `25%` reduction without lowering the
observed deadline floor.

The active-publisher epoch probe then starts with all four robots protected on
both paths and changes the shared plan after source frame `1`. Robots
`0002/0003` reload the plan and send frames `2/3` by unicast while robots
`0000/0001` retain diverse-path redundancy. The run passes `4/4`, reaches
maximum latency `63.405 ms`, keeps Jain fairness `1.0`, performs zero
retransmissions, and executes `20` path transmissions versus `24` for a
non-adaptive session. This is direct evidence that FleetRMW can actuate a
fleet-wide budget epoch without restarting ROS 2 publishers.

The subscriber-QoE closed-loop probe removes seeded robot debt from that
decision. After the first frame, subscriber telemetry reports QoE scores of
`0.628` and `0.555` for the two roaming robots versus `0.872` and `0.898` for
the two backup-path robots. The controller spends its two-copy budget on the
measured lower-QoE pair, and frames `2/3` follow the new plan while publishers
remain active. All `4/4` robots meet the `250 ms` diagnostic deadline, maximum
latency is `222.266 ms`, Jain fairness is `1.0`, and no NACK retransmission
occurs. The closed loop executes `16` path transmissions rather than `24`
under blanket redundancy, a `33.3%` reduction.
The repeated matrix passes `2/2` independent rows with the same protected pair,
maximum observed latency `210.977 ms`, minimum Jain fairness `1.0`, zero NACK
retransmissions, and `32` aggregate path transmissions versus `48` under full
dual-path protection.

The protection-migration probe extends the loop to two changing network
epochs without restarting ROS 2 publishers. Initially, robot `0000/0001` have
the lower measured QoE and receive redundancy. The test then reverses the
roaming/Wi-Fi qdiscs. The next isolated telemetry window measures QoE `0.934`
for `0000/0001` and `0.792/0.830` for `0002/0003`, causing the budget to move
to `0002/0003` before frame `3`. The run passes `4/4`, records maximum latency
`201.596 ms`, fairness `1.0`, zero retransmissions, and `16` path transmissions
versus `24` under blanket redundancy.

The migration scale matrix runs the same live two-epoch experiment with `4`,
`8`, and `16` robots. All `3/3` rows select the expected lower-QoE half before
and after the qdisc reversal, yielding `14` total protection migrations and
`28` changed set memberships. A publisher readiness barrier and per-epoch
event gate replace the earlier fixed `3000 ms` interval, and a sequential QoE
stopping rule waits for confidence-bound separation before each plan update. In
the main `4/8/16` run, every QoE epoch stops at `3` samples per robot and each
row reserves `5` post-migration confirmation frames. Maximum telemetry-to-plan
convergence is `486.958 ms`; maximum controller actuation is `56.761 ms`,
including a `50 ms` plan visibility guard, while qdisc reconfiguration is
measured separately at up to `222.912 ms`. Across the matrix, maximum delivery
latency is `127.958 ms`, minimum Jain fairness is `1.0`, no NACK
retransmission occurs, and FleetRMW performs `420` path transmissions instead
of `616` for full dual-path protection (`31.8%` reduction).

The repeated sequential-QoE migration matrix then runs six independent rows:
`4`, `8`, and `16` robots crossed with repetition IDs `7` and `13` at `0.02%`
netem loss. All `6/6` rows pass and all `12/12` QoE epochs reach confidence
separation. Maximum telemetry-to-plan convergence is `465.783 ms`, maximum
delivery latency is `125.835 ms`, Jain fairness remains `1.0`, retransmissions
remain zero, and aggregate path transmissions are `840` versus `1232` under
blanket redundancy (`31.8%` reduction). Because the Docker image does not
expose deterministic `tc netem` seeding, repetition IDs identify independent
runs rather than fixed random seeds.

The harsh-loss sequential-QoE matrix raises the live Docker/netem loss to
`0.2%`, `0.5%`, and `1.0%` for `8` and `16` robots. It completes with
`5/6` rows OK and records explicit failure-mode counts:
`ok=5`, `confidence_not_separated=1`. The loss-tolerant telemetry collector no
longer treats a delayed or lost individual feedback sample as an immediate
bridge timeout; it continues sampling until the sequential confidence rule can
separate the QoE groups or reaches its configured sample cap. The failing row is
therefore algorithmically meaningful: at `8` robots and `1.0%` loss, only
`1/2` QoE epochs reached confidence separation, one robot missed the delivery
target, NACK retransmissions rose to `3`, and the worst observed latency reached
`1523.410 ms`. The matrix still preserves the redundancy-budget property:
aggregate path transmissions are reduced from the full-dual-path baseline by
`31.9%`, with maximum controller actuation `61.600 ms`. This is now the first
recorded stress boundary for the online QoE migration policy rather than a
silent stochastic failure.

The confidence-fallback smoke turns that boundary into a live actuation
mechanism. The probe exposes sequential confidence parameters and a conservative
fallback policy: when a QoE epoch reaches its sample cap without confidence
separation, the controller protects the union of the previous protected set and
the current low-QoE candidate set, temporarily increasing the redundancy budget
only for that fallback epoch. A forced four-robot Docker/RMW run sets a high
separation margin so both QoE epochs end as
`maximum samples reached without confidence separation`; both epochs apply the
fallback and protect all four robots. The run passes `4/4` robots, keeps zero
NACK retransmissions, records maximum latency `112.636 ms`, converges within
`189.892 ms`, and uses `20` path transmissions versus `24` under blanket
dual-path protection (`16.7%` reduction). This is not a dominance claim; it is
the first proof that uncertainty is now an explicit control-plane state with a
safe ROS 2/RMW actuation path.

The companion one-row matrix smoke keeps the strict evidence rule intact:
because neither QoE epoch reaches confidence separation, the row is not counted
as an OK dominance row. Instead, its failure taxonomy reports
`failure_mode_counts={confidence_fallback_applied:1}` with `robots_ok=4`,
`confidence_fallback_count=2`, and the same `20/24` path-transmission cost. This
separates "safe fallback was applied" from "statistically confident migration
was proven."

The harsh-loss fallback matrix repeats the `8/16` robot, `0.2/0.5/1.0%` loss
campaign with fallback enabled. Because Docker netem draws are not seeded, it is
not a paired A/B replacement for the strict harsh matrix; it is a boundary
probe. It completes `3/6` rows as strict OK and records
`failure_mode_counts={ok:3, robot_delivery_failure:1,
confidence_fallback_applied:1, confidence_fallback_delivery_failure:1}`. The
`8`-robot rows pass at `0.2%` and `0.5%`; the `8`-robot `1.0%` row reaches
confidence but still loses one robot delivery. The `16`-robot `0.2%` row applies
fallback once, delivers all `16/16`, but remains a strict-evidence failure
because only `1/2` QoE epochs reached confidence separation. The `16`-robot
`1.0%` row applies fallback twice, protects the larger set, but still reaches
only `15/16` robot delivery with `4` retransmissions and `1549.130 ms` maximum
latency. Aggregate path transmissions are `1140` versus `1584` under blanket
dual-path redundancy (`28.0%` reduction). The useful result is the failure
taxonomy: fallback is now observable and can preserve delivery in some
non-separated epochs, but high-loss fleet operation still needs a post-fallback
recovery-window and repair/safe-mode policy.

The post-fallback recovery slice adds that recovery-window accounting. The
forced four-robot recovery smoke uses two non-separated QoE epochs and then
releases three recovery frames after fallback. Strict confidence still fails,
but the recovery window passes: all `4/4` robots receive recovery sequences
`3,4,5` on time, maximum recovery latency is `33.764 ms`, and the run uses
`36/40` full-redundancy path transmissions. The companion matrix smoke reports
`failure_mode_counts={confidence_fallback_recovered_window:1}` rather than
counting the row as a confident migration success.

The harsh-loss recovery matrix repeats the `8/16` robot, `0.2/0.5/1.0%` loss
campaign with `3` recovery frames after fallback. It completes `4/6` rows as
strict OK, but all `6/6` rows have an OK recovery window. The two strict-failed
rows are now classified as `confidence_fallback_recovered_window`: the
`8`-robot `1.0%` row applies fallback twice, has only `7/8` full-session
delivery because of a `1520.810 ms` tail event and `4` retransmissions, but its
recovery window is `8/8`; the `16`-robot `1.0%` row applies fallback once,
keeps `16/16` delivery, and its recovery window is `16/16`, but one QoE epoch
does not reach confidence. Aggregate transmissions are `1364` versus `1872`
under blanket dual-path redundancy (`27.1%` reduction). This is the first
evidence that fallback can be treated as a bounded recovery state rather than a
binary success/failure outcome.

The targeted-repair attribution slice connects that recovery state to the
existing RMW source-sequence ACK/NACK ledger. The probe now reports pre-recovery
missing and late sequences per robot, publisher NACK retransmissions,
subscriber idle-repair requests, unresolved robots, and repair path overhead.
In a forced four-robot loss smoke, robot `0002` loses source sequence `5`,
sends one idle repair request, and causes six retransmissions. The sequence is
eventually delivered at `1603.340 ms`, so strict delivery remains `3/4` and the
repair is classified as `repaired_late`; the following recovery window passes
`4/4` with maximum latency `35.981 ms`. Actual path transmissions are `96`
versus `84` before repair overhead. A separate matrix smoke with the same
forced confidence fallback has no packet gap in that netem draw: strict
confidence remains `0/1`, while `qoe_recovered_run_count=1/1`,
`fallback_repair_status=ok`, recovery is `4/4`, and path transmissions remain
`84` with zero repair overhead. These two runs preserve strict QoS accounting
while separately proving QoE recovery and quantifying reactive repair cost.

The controller-directed repair slice then separates normal and repair data
planes. The live controller writes a dedicated repair-plan file, the C++ RMW
reloads it for NACK retransmissions only, and each publisher enforces a bounded
repair budget. A deterministic primary-path drop of source sequence `2` for two
robots proves that all eight retransmissions use the controller-selected
`backup_5g+primary_wifi` repair plan: `8` repair frames produce `16` repair
path transmissions, while the normal plan remains `84` transmissions. With a
`250 ms` SLO, maximum latency is about `299 ms`, so both repaired samples are
honestly classified `repaired_late`; the following recovery window is still
`4/4`. With a feasible `400 ms` SLO, the same mechanism classifies both robots
`repaired_on_time`, all `4/4` robots are deadline-qualified by the repair
summary, and maximum latency is `327.944 ms`. Setting the repair budget to zero
blocks replay, leaves sequence `2` unresolved for both affected robots, records
`67` rejected repair requests, and sets `qoe_recovery_ok=false` even though
later recovery frames are healthy. The matrix wrapper also preserves the two
evidence layers: strict confidence is `0/1`, while QoE recovery is `1/1`.

Per-sequence NACK coalescing then removes most repair amplification. With a
`50 ms` coalescing interval and two attempts per sequence, the same deterministic
drop reduces retransmissions from `8` to `4`, repair path sends from `16` to
`8`, and repair overhead from `16` to `8`, while preserving `4/4`
repair-deadline success. Limiting each missing sequence to one dual-path repair
reduces the run further to `2` retransmissions and `4` repair path sends; both
affected robots remain `repaired_on_time`, maximum latency is `326.503 ms`,
four duplicate requests are coalesced, and two later requests are rejected by
the per-sequence attempt cap.

Fleet-wide repair admission now closes that gap. A shared scheduler models each
missing source sequence as a demand, generates unicast and failure-domain-aware
diverse-path alternatives, then solves a capacity-constrained multi-choice
knapsack with Pareto pruning. Utility combines deadline pressure, robot
criticality, QoE debt, expected path success/latency, lateness, previous repair
attempts, and byte cost. The selected policy is enforced by C++ publishers at
the `(topic, source_sequence)` boundary rather than as an independent local
budget. With `2800` bytes available, the optimizer admits both forced sequence
`2` gaps but allocates only `1400` bytes because one loss-free `backup_5g`
repair per gap dominates redundant repair. The run recovers `4/4` robots by
the `400 ms` deadline with `2` retransmissions and only `2` repair path sends.
With capacity reduced to `700` bytes, it admits only `robot_0000`, whose
synthetic QoE debt is higher, and explicitly defers `robot_0001`. The admitted
robot is repaired on time, fleet repair-qualified coverage becomes `3/4`, one
path send is added to the normal `84`, and the deferred publisher records `33`
strict admission rejections instead of silently exceeding the shared budget.
This pair establishes a measured capacity-to-QoE tradeoff and leaves repeated
large-fleet optimization, not basic repair admission, as the next scale gap.

The latest direct ROS 2 RMW matrix now runs against the rebuilt
`localhost/fleetrmw/rmw-netem:jazzy` image with Fast DDS, Cyclone DDS, and Zenoh
packages available.  It executes direct ROS 2 pub/sub over Docker `tc netem`
for Wi-Fi, WAN, and roaming profiles with seeds `7,13,29`, strict qdisc
verification, loss scale `0.1`, and the two study topics
`/robot_0000/cmd_vel` and `/robot_0001/odom`.  The current result is
`16/27` OK with no skipped rows: Fast DDS direct pub/sub passes `7/9`, Cyclone
DDS passes `9/9`, and Zenoh direct pub/sub fails `9/9` with missing
control/state delivery in this harness.  A debug probe shows the Zenoh publisher
ran and sent samples but observed zero subscriptions, so this is recorded as a
direct-baseline configuration/discovery gap rather than a final Zenoh-wide
performance claim.  The comparison report now includes all `27` direct seed
rows while still keeping `direct_claim_allowed=false`, because FleetRMW rows use
the router/redundancy topology and direct RMW rows remain single-path pub/sub.
The direct baseline harness has also moved from a fixed two-topic seed to a
parameterized multi-robot workload.  With `--robot-count 4`, the Wi-Fi seed-7
smoke creates `8` ROS 2 topics and delivers all `8/8` control plus `8/8` state
payloads for both Fast DDS and Cyclone DDS, with minimum per-topic delivery
`1.0`; the Zenoh direct row still delivers `0/8` control and `0/8` state in
this harness.  The full four-robot matrix over Wi-Fi, WAN, roaming, and seeds
`7,13,29` completes `16/27` rows OK: Cyclone DDS passes `9/9`, Fast DDS passes
`7/9` but loses seed `29` under WAN and roaming, and Zenoh direct pub/sub fails
`9/9`.  This is the first direct-baseline scale step toward the matched
large-fleet campaign and the first result here where increasing robot/topic
count exposes DDS direct-delivery fragility that the two-topic matrix hid.

The latest eight-robot audits close the first hard-SLO scale gap for the ROS 2
live bridge.  Earlier rows were negative but informative: immediate ACK-only
feedback overloaded the sidecar feedback path, fixed ACK windows recovered
selected seeds but failed repeated rows, and piggyback-first ACK/NACK reached
`2/3` hard budget pass while seed `13` still failed at the per-robot control
floor.  The new mechanism is not another feedback eagerness tweak.  It treats
retransmission memory as a QoS contract: semantic control transforms receive an
effective wire lifespan, events preserve the source ROS lifespan separately, and
ACK/NACK history is retained for a bounded recovery horizon derived from
deadline, RTT/jitter, and ROS liveliness lease.

With that liveliness-backed horizon, the formerly failing seed `13` now passes:
hard budget `1/1`, control delivery `0.9830`, minimum per-robot control
delivery `0.9545`, deadline miss `0.1036`, worst-robot deadline miss `0.1600`,
quality coverage `1.0000`, and p95 `1731.48 ms`.  The repeated row over seeds
`7,13,29` also passes `3/3`, with control delivery `0.9902`, mean minimum
per-robot control delivery `0.9804`, loss `0.0311`, deadline miss `0.1296`,
worst-robot deadline miss `0.1659`, p95 `1085.30 ms`, RX `136.00`, and
quality-gate robot coverage `1.0000`.  The remaining gap is no longer whether
source-sequence ACK/NACK can preserve the `8`-robot hard control floor in the
current ROS 2 bridge.  The gap is moving the same source identity, liveliness
horizon, and retransmission semantics into a persistent FleetRMW publish/take
transport boundary and then into `rmw_fleetqox_cpp`.  The first UDP socket smoke
for that boundary now exists: `scripts/run_rmw_socket_smoke.py` sends
`fleetrmw.data_frame.v1`, takes it at a listener, and returns
`fleetrmw.ack_nack.v1` to the talker. The delayed-sequence smoke publishes and
takes `6` frames, emits `6` ACK/NACK feedback records, performs one
NACK-triggered retransmission, reports one missing range, and repairs it with
one late out-of-order sample.  The first C++ reference package,
`ros2_ws/src/rmw_fleetqox_cpp`, now mirrors that contract below the Python
runtime: its UDP loopback smoke publishes and takes `15` frames, emits `15`
ACK/NACK records, performs `6` retransmissions, and repairs `6` missing ranges.
The same package now builds the initial `librmw_fleetqox_cpp` identifier seed:
unit tests compile and load the shared library and confirm
`rmw_get_implementation_identifier()` returns `rmw_fleetqox_cpp` while
`rmw_get_serialization_format()` returns `cdr`.  The package also builds inside
Docker with `ros:jazzy-ros-base` and `colcon` alongside
`fleetrmw_interfaces`.  The Docker transport artifact repeats the same `15`
frame / `6` retransmission smoke, and the Docker frame-probe artifact verifies
that C++ decodes a `fleetrmw.data_frame.v1` packet emitted by the Python
`FleetRmwBoundary`.  The Docker lifecycle probe now verifies the first real RMW
ABI skeleton path: init options, context init/shutdown/fini, and
create/destroy node all execute with implementation `rmw_fleetqox_cpp`.  The
Docker serialized pub/sub probe extends that ABI skeleton to
publisher/subscription handles, serialized publish/take through
`fleetrmw.data_frame.v1`, matched endpoint counts, and destroy paths over a
UDP loopback socket path with `socket_backed=true`,
`socket_frames_sent=1`, and `socket_frames_received=1`.  The Docker
type-erased typed pub/sub probe then exercises `rmw_publish` and `rmw_take` for
a fixed-size FleetRMW probe message through the same data-frame socket path:
status `ok`, `typed_message_size=40`, `socket_frames_sent=1`,
`socket_frames_received=1`, and recovered label `typed-probe`.  The Docker
introspection C typed probes then move to real ROS message structs:
`std_msgs/msg/String` round-trips payload
`fleetqox std_msgs/String over introspection C`, and `geometry_msgs/msg/Twist`
round-trips nested command fields with `linear_x=0.7`, `linear_y=-0.2`, and
`angular_z=0.33`, each with one socket frame sent and received.  The Docker
wait/guard probe adds graph guard trigger and `rmw_wait` readiness for a local
serialized subscription.  The Docker graph probe adds the first in-process graph cache
checks for node names, topic names/types, publisher counts, and subscriber
counts.  The Docker inter-process probe moves the same serialized RMW path
across two processes: a subscriber bound at `127.0.0.1:48101` takes the
`fleetqox-interprocess-cdr` payload sent by a publisher configured with
`FLEETQOX_RMW_PEERS=127.0.0.1:48101`, with publisher `socket_frames_sent=1`
and subscriber `socket_frames_received=1`.  The Docker multi-container router
probe then runs publisher, router, subscriber, and graph observer in separate
containers on a private Docker network.  The subscriber advertises
`fleetrmw.route_advertisement.v1` to the router, the router learns one route,
the publisher sends only to the router hostname, and the subscriber takes `34`
bytes with `taken=true`; the router reports `route_advertisements=1`,
`learned_routes=1`, `graph_advertisements=2`, `graph_forwarded=2`,
`graph_peer_count=1`, `graph_publishers=1`, `graph_subscriptions=1`,
`received_frames=1`, `forwarded_frames=1`, and `invalid_frames=0`.  The graph
observer receives only the two graph frames and validates the same remote topic
through RMW graph APIs: `topic_found=true`, `publisher_count=1`, and
`subscriber_count=1`.  The remote graph lease probe proves stale endpoint
cleanup: a `30 ms` remote publisher advertisement is visible immediately with
`publisher_count_before=1`, then disappears after expiry with
`publisher_count_after=0` and `topic_found_after=false`.  The service-error
probe verifies empty response queues do not fabricate a response, malformed
response payloads return a controlled error with `taken=false`, and invalid
service frames are rejected.  The ROS CLI service-timeout probe verifies a
delayed service response makes `ros2 service call` exit with timeout code `124`
after the server has observed the request and before any success response is
printed. The router-mediated malformed-response probe then sends a correctly
routed response frame containing an intentionally invalid one-byte serialized
payload. The router forwards both request and response, the service exits
normally after one request, and `ros2 service call` exits with code `1`, emits
the RMW/rcl diagnostic `failed to deserialize service response`, and prints no
`Response`. This proves the serialization failure is caller-visible rather
than converted into a timeout or fabricated reply. The action-frame contract
probe then locks a
dependency-light `fleetrmw.action_frame.v1` shape for goal, feedback, status,
result, and cancel roles before real `rcl_action` APIs are connected.  The
router-mediated action-frame probe now runs those five roles through
`fleetrmw_udp_router_probe`: the router observes `action_frames=5`,
`action_forwarded=5`, `graph_action_servers=1`, and
`graph_action_clients=1`, while the probe observes server-side `goal/cancel`
and client-side `feedback/status/result` delivery.  The first real action API
smoke now runs `tf2_msgs/action/LookupTransform` through
`rclpy.action.ActionServer` and `ActionClient` with `RMW_IMPLEMENTATION` set to
`rmw_fleetqox_cpp`; it observes server availability, accepted goal, execute
callback, GetResult status `4`, `result_frame=map`, and
`result_child_frame=base_link`.  The router-mediated real action smoke then
separates that server and client into different Docker containers that peer
only with `fleetrmw_udp_router_probe`; it observes accepted goal, execute
callback, success GetResult status `4`, canceled GetResult status `5`, feedback
callbacks for both goals, live status samples, and router `service_frames=10` /
`service_forwarded=10`.  The same row verifies router-mediated
`ActionClient.server_is_ready()` before the goal is sent and after the result,
with remote feedback/status publishers and subscribers visible through graph
counts.  The action QoS matrix then compares fresh and expired action
observation traffic. With `1 ms` forwarding delay and `100 ms`
feedback/status lifespan, all observation callbacks arrive. With `30 ms`
delay and `5 ms` lifespan, the router drops `9` stale action data frames by
topic (`2` feedback and `7` status), while all `10`
SendGoal/CancelGoal/GetResult service frames are forwarded and the client still
observes success status `4` and canceled status `5`. A third row scopes a
three-frame scheduler burst to the action topic prefix and forwards feedback
deadline `5 ms` before status deadline `100 ms`. The follow-on multi-robot QoS
matrix assigns publisher identity through
`FLEETQOX_RMW_ROBOT_ID` and drives four robots, each with one control and one
state flow, through real FleetRMW publishers/subscribers and a shared router.
It compares arrival-order FIFO with an online deadline-gated scheduler:
urgent control frames bypass the holdback queue, non-urgent state frames are
sorted by absolute deadline and drained with pacing, and the report records
end-to-end take age, per-robot deadline success, Jain fairness, and scheduler
queue wait.
The current 8-robot Wi-Fi/WAN/roaming netem matrix reports `status=ok` with
zero deadline misses and per-robot fairness `1.0` in all profiles. Raw
deadline-gated holdback improves control p95 in Wi-Fi
(`36.070 -> 34.900 ms`) and WAN (`94.874 -> 93.991 ms`), but regresses in
roaming (`158.036 -> 159.904 ms`). The follow-on adaptive-admission wrapper
selects `deadline_gated_holdback` for Wi-Fi/WAN and FIFO for roaming, keeping
`adaptive_worse_profile_count=0` while raising admitted mean control p95
reduction from `+0.061 ms` raw to `+0.684 ms`. The next live router gate moves that admission
decision into `fleetrmw_udp_router_probe` itself using
`slo_service_epoch`: the router normalizes each non-urgent frame's estimated
link service time by the urgent control deadline, smooths the service-ratio
signal with EWMA, and changes holdback mode only after threshold and epoch
conditions are met. In the latest live Wi-Fi/WAN/roaming run it bypasses
holdback on Wi-Fi, queues WAN and roaming, records `8` admission samples per
profile, switches once into holdback for WAN/roaming, preserves zero deadline
misses/fairness `1.0`, and keeps mean control p95 reduction positive at
`5.021 ms`. This changes the gap from "make admission live" to "validate the
multi-epoch controller across lossy repeated seeds."
The first repeated-loss smoke now does that on a small scale: Wi-Fi and roaming
are rerun with repetition ID `7` and `tc netem loss 0.02%`; both rows pass, the
runner exercises both bypass and holdback branches, and mean control p95
reduction is `6.536 ms`. The runner deliberately reports `partial` rather than
hiding row failures when stochastic UDP loss drops a single-send payload,
because the next research gap is scheduled-path ACK/NACK repair under
non-trivial loss.
The first scheduled-path ACK/NACK repair probe now closes the deterministic
drop version of that gap: with router scheduler window `150 ms`, the router
drops source sequence `2`, forwards `3` ACK/NACK frames, queues and forwards
`4` scheduled data frames including retransmissions, and the subscriber
recovers payloads `one`, `three`, `two`.
The repeated-loss extension runs the same contract under Wi-Fi and roaming
qdiscs with `loss 0.02%`. The latest repetition-`7` smoke passes `2/2` rows:
both recover all payloads, each publisher retransmits twice, each router queues
and forwards four scheduled frames with zero deadline misses, and the matrix
records `12` forwarded ACK/NACK frames. An initial failed run identified that
router process completion could precede kernel qdisc delivery; a
post-satisfaction drain horizon now makes terminal evidence include the
network-emulator queue rather than only userspace forwarding counters.
The concurrent extension then runs four independent ROS 2 publisher/subscriber
pairs through one roaming-profile router. It passes `4/4` robots, drops one
source sequence per publisher identity, forwards `32` ACK/NACK and `16`
scheduled data frames, performs `8` NACK-driven retransmissions, and recovers
all three payloads on every robot. Router telemetry reports zero deadline
misses and per-robot deadline-success Jain fairness `1.0`.
The first real mixed workload then shares one roaming-profile router between a
real `rclpy.action` success/cancel lifecycle and four repaired control/state
flows for two robots. Action completion and all `4/4` flows pass; the scheduler
records `17` urgent and `8` queued frames, while the router forwards `46`
ACK/NACK frames. Topic-scoped fault injection plus structured miss telemetry
shows zero fresh deadline misses but four late sequence-`2` control repairs
(`167-196 ms` beyond the original deadline). The result separates the delivery
QoE benefit of reactive repair from the unresolved hard-real-time protection
problem.
The proactive diversity follow-on sends deadline-critical control samples over
a roaming primary and Wi-Fi backup before loss is observed. Its two-row matrix
passes `2/2`: primary sequence `2` is dropped in both rows, all sequences arrive
within the `100 ms` subscriber deadline, maximum latency is `63.688 ms`, and
the publisher uses `6` redundant sends with `0` NACK retransmissions.
The concurrent extension protects four robots in one shared session. Its
two-row repeated-loss matrix passes `2/2`, keeps all eight robot-runs at `3/3`
on-time samples, reaches maximum latency `56.163 ms`, preserves Jain fairness
`1.0`, and performs no retransmission. Full protection expands `24` source
frames to `48` path transmissions, quantifying the bandwidth cost that the
next budget allocator must reduce.
The first allocator probe applies a `1400`-byte extra-copy budget to four
`700`-byte control flows. It protects the two robots carrying fairness debt,
keeps the other two on the best unicast path, drops no flow, and reduces path
transmissions from `8` under full duplication to `6`. Redundant pairs are
forced across `private_5g_core` and `warehouse_ap`, rather than selecting two
radios sharing the same AP failure domain.
The latest multi-robot live RMW probes move beyond deterministic routing into stochastic
network evidence.  The stochastic netem sweep runs the same ROS 2/RMW
publisher-router-subscriber topology across Wi-Fi/WAN/roaming profiles, loss
scales, and repetition IDs while classifying harness, qdisc, component,
telemetry, contract-evidence, and end-to-end delivery failures.  The new
ablation runner then holds that topology constant and varies only proactive
repair mode (`none`, `state_only`, `control_state`).  The full campaign over
three profiles, seeds `7,13,29`, loss scales `0.1,0.25,0.5`, and three repair
modes completed `78/81` rows with qdisc applied in `81/81` rows.  `control_state`
ranked first: `27/27` OK, maximum all-profile loss scale `0.5`, mean control
latency `76.18 ms`, mean state latency `49.11 ms`, and repair cost `14.30`.
`none` also passed `27/27` with lower repair cost `2.74` but higher combined
control/state latency (`75.04 ms` + `57.16 ms`).  `state_only` exposed the
boundary, passing `24/27` and failing delivery in roaming at loss scales
`0.1/0.25` and WAN at `0.5`.  The baseline comparison map now normalizes the
FleetRMW-native ablation, the matched four-robot FleetRMW matrix, existing ROS
2 live-bridge profile winners, and the direct four-robot RMW matrix while
setting `direct_claim_allowed=false`.  The ROS 2 live-bridge winners are
`data_frame/rmw_zenoh_cpp` for Wi-Fi and `event_json/rmw_zenoh_cpp` for
WAN/roaming, which still shows packet-format/RMW winners are
profile-dependent.  The direct four-robot matrix exposes scale sensitivity:
Cyclone DDS passes `9/9`, Fast DDS passes `7/9`, and Zenoh direct pub/sub
fails `9/9` in this harness.  The matched FleetRMW four-robot
router/redundancy matrix uses the same profiles, seeds `7,13,29`, loss scale
`0.1`, robot count `4`, and `8` ROS 2 topics; it completes `9/9` rows OK with
qdisc applied and router status OK in all rows, and application delivery
`12/12` for control plus `12/12` for state in every row.  That matched row now
uses `deadline_sequence_repair_v1`: pre-payload route-warmup ACK gating, two
semantic application repair cycles, idle missing-range ACK/NACK feedback, and
five terminal guard repeats.  The remaining research gap is topology
equivalence: direct Fast DDS/Cyclone/Zenoh rows are still single-path pub/sub,
while FleetRMW uses router-level repair, route advertisements, deadline
sequence repair, and QoE path planning.

## ROS 2 / netem Findings

### Wi-Fi Loss/Jitter

- `state` traffic is survivable across RMWs.
- Zenoh RMW wins `state` on the current QoE/rank score with zero loss.
- `control` is already fragile: CycloneDDS is best, but still has deadline miss
  around `0.957`.
- Zenoh RMW shows a tail-latency problem on `control`: p99 is much worse than
  Fast DDS and CycloneDDS.

### Roaming Capacity Drop

- `control` collapses for every RMW: deadline miss is `1.000` for Fast DDS,
  CycloneDDS, and Zenoh RMW.
- CycloneDDS wins both `control` and `state`, but the `control` win is only
  relative; it does not satisfy the deadline objective.
- Zenoh RMW keeps `state` loss at `0.000`, but p95/p99 latency and jitter are
  much worse than DDS baselines.

### Cross-Baseline Signal

The impairment shift from Wi-Fi loss/jitter to roaming capacity drop does not
only increase average latency. It changes the operating regime:

- control traffic becomes deadline-infeasible;
- state traffic remains deliverable but tail latency expands;
- reliability/loss wins can hide QoE tail risk.

This supports the FleetRMW thesis that endpoint-level QoS is insufficient for a
large fleet. The system needs a fleet-level control plane that can decide which
flows should be admitted, degraded, delayed, or dropped before the transport is
overloaded.

## Fleet-Scale Simulator Findings

The local simulator compares:

- FIFO;
- static class priority;
- FleetQoX Causal Semantic Deadline Scheduler;
- FleetQoX predictive admission control.

In the `fleet_scale_v1` shared-cell profile:

- FleetQoX predictive admission wins at 10, 25, 50, and 100 robots.
- At 100 robots, predictive admission reduces control deadline miss by `0.078`
  versus static priority and `0.147` versus CSDS.
- At 100 robots, predictive admission reduces defer ratio by `0.346` versus
  static priority while using semantic compaction for `0.571` of decisions.
- FIFO collapses fastest as robot count grows.
- Control deadline miss remains the main scaling bottleneck for FIFO and older
  non-predictive policies at large fleet sizes.

This changes the prototype direction: a publishable FleetRMW contribution should
not stop at local priority scheduling. The stronger claim is predictive fleet
admission with semantic wire compaction and adaptive reliability.

## Sidecar Netem Matrix Findings

The live Docker/netem sidecar matrix compares FIFO, static priority, CSDS, and
FleetQoX predictive admission under the same `20ms +- 5ms`, `1%` loss, `20mbit`
profile.

| policy | rx | loss | deadline miss | control misses | compacted rx | p95 ms | utility |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| FIFO | 64 | 0.000 | 0.031 | 2 | 0 | 27.86 | 306.43 |
| Static priority | 74 | 0.013 | 0.108 | 8 | 0 | 56.26 | 381.43 |
| CSDS | 95 | 0.031 | 0.011 | 1 | 0 | 43.76 | 439.18 |
| Predictive | 120 | 0.000 | 0.083 | 10 | 77 | 52.45 | 549.89 |

Predictive admission delivers the most packets, the highest semantic utility,
zero measured loss, and visible semantic compaction. CSDS is still better on
deadline miss and control misses in this live netem run. This is valuable: it
turns the next research step from "add more heuristics" into a constrained
multi-objective control problem.

The risk-guarded V2 matrix adds `fleetqox_predictive_guarded`. In the current
Docker/netem run it eliminates measured deadline misses (`0.000`) and loss
(`0.000`) with `90` received packets, but delivered utility drops to `348.52`.
This shows the guard is technically effective but too conservative; the next
research contribution should be a soft constrained optimizer, not a hard
deadline gate.

The closed-loop sidecar matrix fixes the open-loop age limitation by feeding
per-flow decisions back into future observations. In that more faithful path,
`fleetqox_predictive` reaches the highest delivered utility (`8645.39`) and
`fleetqox_predictive_guarded` eliminates measured deadline misses with `1107`
received packets and `6748.60` utility. This confirms that feedback materially
changes the interpretation of guarded admission.

The first Lagrangian controller adds a soft risk-constrained objective. In a
single-policy tuning run it delivers `7482.29` utility with `3` control misses,
between guarded predictive and unguarded predictive. In the comparative matrix,
the same controller is not yet statistically stable: it still shows `10` control
misses under that netem realization. This exposes the next evaluation gap:
policy claims need repeated-run confidence intervals and parameter sweeps.

`SIDECAR_REPEATED_STATS_V1` adds the first repeated-run reporting harness. It
aggregates closed-loop sidecar matrix files, computes mean/95% confidence
intervals by policy, and marks the Pareto frontier over utility, control
starvation, deadline miss, and loss. The current evidence still has too few
runs for a publication claim, but the tool now makes the missing experiment
explicit instead of relying on isolated netem realizations.

`LAGRANGIAN_SWEEP_V1` adds an offline parameter sweep for the Lagrangian
controller before spending Docker/netem runs. It exposes the first concrete
algorithmic correction: unadmitted high-risk samples should be risk-reset
dropped instead of deferred until they miss. With `deadline_drop_risk=0.45`, the
best Lagrangian candidate reaches control miss around `0.0060` in the smoke
sweep, versus around `0.2144` for the previous `0.96` threshold.

`SIDECAR_LAGRANGIAN_VARIANTS_NETEM_V1` validates that the new parameter plumbing
works in Docker/netem and compares two labeled Lagrangian variants. `lag_012`
enters the measured Pareto frontier, but it still does not dominate the existing
baselines: predictive keeps higher utility, guarded keeps zero measured miss,
and CSDS remains competitive on loss/utility. This shifts the next algorithmic
step from scalar parameter tuning to observed-risk adaptation: update the dual
state from actual delivered deadline/QoE outcomes, not only from estimated
pre-send risk.

`SIDECAR_LAGRANGIAN_OUTCOME_ADAPTATION_NETEM_V2` adds the first measured
outcome-driven adaptation loop. The adapter reads repeated netem metrics,
selects a labeled Lagrangian source variant, and applies a bounded dual/trust
region update. `lag_adapt_001` over-tightens the risk gate and reaches zero
miss with lower utility. `lag_adapt_002` relaxes from that safe point and lands
near guarded predictive: zero measured miss, slightly lower utility, lower loss,
and slightly higher receive count in the two-seed smoke matrix. This is not yet
publishable evidence, but it is the first closed measured loop from observed
outcome to next middleware configuration.

`SIDECAR_LAG_ADAPT_002_5SEED_NETEM` extends that evidence from two seeds to
five seeds by combining the original seed 7/13 baselines with seed 29/41/53
Docker/netem reruns. `lag_adapt_002` stays at zero measured control starvation
and zero measured deadline miss across the five-seed matrix. Its mean utility
is `6729.7`, slightly above guarded predictive at `6713.5`, with a higher mean
receive count (`1144.4` versus `1134.4`) but higher loss (`0.0093` versus
`0.0084`). The result is not full dominance, but it is a real Pareto operating
point: it preserves the zero-miss safety envelope while recovering a small
amount of utility and throughput over the hard guarded baseline.

`SIDECAR_LAGRANGIAN_OUTCOME_ADAPTATION_NETEM_V3_5SEED` applies one more bounded
outcome update from the safe `lag_adapt_002` point. `lag_adapt_003` keeps zero
measured control starvation and deadline miss over five Docker/netem seeds while
raising mean utility to `6899.2` and mean receive count to `1172.0`. This is the
strongest adapted operating point so far under the current impairment profile:
it improves utility over guarded predictive by about `2.8%` and over
`lag_adapt_002` by about `2.5%`, while keeping loss below unguarded predictive
(`0.0100` versus `0.0121`). The tradeoff is that guarded predictive and CSDS
still have lower loss, so the research claim remains a constrained Pareto
improvement rather than universal dominance.

`SIDECAR_PROFILE_ROBUSTNESS_V1` deliberately breaks the single-profile
assumption. Under the LAN profile, all policies keep zero measured deadline miss
and unguarded predictive dominates on utility. Under WAN and roaming profiles,
all current policies miss deadlines heavily: `lag_adapt_003` reduces deadline
miss relative to unguarded predictive in the one-seed smoke, but it does not
preserve the Wi-Fi zero-miss envelope. This exposes a stronger research gap:
FleetRMW cannot use one global set of admission parameters. It needs a
profile-aware controller that adapts risk budgets and admission pressure from
observed RTT/jitter/capacity.

`SIDECAR_PROFILE_AWARE_LAGRANGIAN_V1` adds that first profile-aware controller
and fixes the testbed path so Docker/netem delay, jitter, and loss are visible
inside the scheduler's `NetworkLink`. The new `fleetqox_predictive_profiled`
policy keeps separate Lagrangian state for LAN, Wi-Fi, WAN, and roaming regimes.
In the one-seed WAN smoke it lowers deadline miss to `0.008`, versus `0.012`
for guarded predictive and `0.015` for fixed `lag_adapt_003`. In the one-seed
roaming smoke it lowers deadline miss to `0.005`, versus `0.060` for fixed
`lag_adapt_003` and `0.311` for guarded predictive. The cost is severe: receive
count and utility drop sharply, so the new research target is no longer "can we
protect deadlines?" but "can we recover utility under a profile-specific safety
envelope?"

`SIDECAR_INTENT_WAN_V1` exposes the deeper issue with that safety envelope:
deadline miss can look good when the policy drops every control sample. The
updated metric layer now reports `control_delivery_ratio` and
`control_non_delivery_events`; in the WAN smoke, guarded, fixed Lagrangian,
profiled, and contextual policies all have `0.0000` control delivery and `944`
control non-deliveries. The new `fleetqox_predictive_intent` policy changes the
wire semantics for infeasible WAN control samples: it sends compact
`control_intent` horizon packets instead of dropping them. In the one-seed WAN
smoke it reaches `0.9862` control delivery, `931` received intent packets, and
`7303.8` delivered utility, with `0.0101` deadline miss and `10` control misses.
This is the first result that addresses the actual WAN control feasibility
problem instead of only optimizing packet admission around it.

`SEMANTIC_CONTRACT_V1` turns that result into a general mechanism. It adds
`FlowContract`, `SemanticTransform`, and `FeasibilityCertificate`, so the
controller can ask whether raw delivery is feasible and which semantic
representation is valid under the current service curve. `control_intent` is now
triggered by a raw-vs-intent certificate comparison rather than by a hard-coded
WAN/roaming profile check. The newer `fleetqox_semantic_contract` policy goes
one step further: it schedules raw, semantic-delta, degraded, and control-intent
representations as first-class certified candidates under the same byte budget.
Its certificate model treats semantic-delta, degraded, and control-intent
packets as newly synthesized representations of the latest local state, while
raw packets preserve source age. In the five-seed Docker/tc-netem WAN sweep,
this policy reaches the highest mean utility (`7560.6 +/- 320.4`) and receive
count (`1279.8 +/- 17.62`) among the three compared policies, with measured
deadline miss `0.0081 +/- 0.0007`; the tradeoff is slightly lower control
delivery and higher loss than the wrapper intent baseline.

`SIDECAR_SEMANTIC_CONTRACT_LOSSAWARE_COMPARE_WAN_V1` adds a packet-level loss
shadow price and non-control packet cap as a separate policy,
`fleetqox_semantic_contract_lossaware`. In the five-seed WAN comparison it is a
cleaner operating point than the raw semantic scheduler: mean utility remains
high (`7455.5`), while loss falls from `0.0252` to `0.0153`, deadline miss falls
from `0.0230` to `0.0084`, and p95 latency falls from `134.2 ms` to `80.81 ms`.
It also stays above `fleetqox_predictive_intent` on utility and receive count.

The next local policy, `fleetqox_semantic_contract_adaptive`, moves this from a
fixed engineering choice to a constrained online selector. It previews the
utility and tail-shield semantic-contract variants on the same batch, scores
them against active contract budgets, and updates primal-dual penalties for
deadline risk, safety/control non-delivery, and packet loss exposure. The target
claim is not that the tail shield is always better, but that the middleware can
switch between high-utility and tail-stable semantic representations without a
preselected WAN profile.

`SIDECAR_SEMANTIC_CONTRACT_ADAPTIVE_WAN_V1` gives the first evidence for that
claim. Across five WAN seeds, `fleetqox_semantic_contract_adaptive` achieved the
highest mean utility (`7597.5`) and reduced the fixed semantic scheduler's loss
from `0.0248` to `0.0130`, deadline miss from `0.0226` to `0.0081`, and p95
latency from `116.2 ms` to `82.53 ms`. Decision traces show both variants being
used (`5137` tail-shield decisions and `2705` utility decisions), which supports
the selector argument rather than a fixed-variant argument.

The first roaming preflight exposed a deeper gap: if the network path is longer
than the original control lifespan, both raw `/cmd_vel` and short
`control_intent` are semantically invalid. The contract layer now includes
`supervisory_intent`, a compact goal/constraint lease with its own validity
horizon. Offline roaming preflight shows previous policies delivering zero
control packets, while the semantic-contract policies deliver supervisory
control intents under the same link assumptions.

`SIDECAR_SEMANTIC_CONTRACT_ADAPTIVE_ROAMING_V1` turns that preflight into a
Docker/tc-netem measurement. Across five roaming seeds (`80 ms` one-way delay,
`25 ms` jitter, `3%` loss, `70 KB/s`), `fleetqox_predictive_intent` again
delivered no control intents (`0.0000` control delivery and `950.4` mean
control non-delivery events). The semantic-contract scheduler reached the
highest delivered utility (`6332.3`) by sending more traffic, while the adaptive
selector stayed on the Pareto frontier with lower bytes (`55.0 KB` vs
`77.4 KB`), lower mean loss (`0.0304` vs `0.0344`), slightly better control
delivery (`0.9686` vs `0.9646`), and lower deadline miss (`0.0002` vs
`0.0004`). It also avoids the fixed loss-aware variant's seed-29 tail collapse:
mean p95 stays near `117.2 ms` instead of `237.1 ms`, and control starvation
stays at zero instead of `17.4` mean events. Trace evidence shows `7842`
tail-shield decisions and `4747` `send_supervisory_intent` packets, so the
roaming behavior is an explicit semantic-mode shift rather than a post-hoc
packet rewrite.

## Research Gap Exposed By V1

The current evidence points to seventeen gaps:

1. RMW transports expose QoS knobs, but they do not optimize a fleet-wide
   objective under shared wireless/WAN bottlenecks.
2. Reliable delivery can reduce loss while worsening tail latency, which harms
   operator QoE and freshness-sensitive state.
3. Control deadlines cannot be protected by topic QoS alone when background
   state, perception, debug, and video flows compete for the same link.
4. A scheduler that only ranks current samples can still react too late; it needs
   predictive admission, semantic compression, and transport-aware shaping.
5. Utility-maximizing predictive admission can still lose to a deadline-focused
   scheduler on control misses unless deadline risk is represented as a hard
   budget or safety constraint.
6. A hard safety gate can remove deadline misses, but it can also collapse
   semantic utility unless capacity is reallocated through a constrained
   optimizer with feedback.
7. Testbed fidelity matters: open-loop traces can exaggerate age accumulation
   and make deadline-aware policies look worse than they are in closed-loop
   execution.
8. Single netem realizations are too noisy for algorithmic claims; the testbed
   now needs repeated-run statistics and Pareto-frontier selection.
9. A controller tuned for one impairment profile can fail under WAN/roaming
   latency even if it is safe under Wi-Fi-like loss/jitter. The control plane
   needs profile-aware adaptation, not just seed-level parameter fitting.
10. A manually chosen profile-specific safety envelope can restore deadline
    protection, but it may waste too much capacity. The next controller needs a
    constrained online optimizer that learns how far each profile can be relaxed
    without violating deadline/QoE budgets.
11. A zero-miss policy is not necessarily a useful control policy if it drops all
    control samples. Fleet middleware needs semantic delivery metrics and
    deadline-feasibility transformations such as control-intent horizons for
    WAN/Internet paths where the original per-sample deadline is physically
    impossible.
12. Even after a network-side control packet is admitted, a robot should not
    treat it as raw actuator authority. Fleet middleware needs a robot-local
    contract layer that validates authority freshness and shapes commands
    against controller-specific velocity, acceleration, and jerk envelopes.
13. A sidecar/RMW transition cannot leave the data plane as a research log JSON
    object. Fleet middleware needs a native frame boundary that preserves
    source identity, admission contract, timing, and QoX metadata while staying
    comparable against legacy packet paths during migration.
14. Packet format, RMW implementation, workload seed, and impairment profile
    interact. In the repeated Wi-Fi ROS 2 matrix, `data_frame` with Zenoh RMW
    is the only non-dominated combination; in the repeated WAN matrix, five
    combinations remain on the Pareto frontier and legacy JSON with Zenoh has
    the highest mean utility. A fleet middleware cannot treat packet encoding
    and RMW selection as independent fixed choices; it needs measured
    representation/transport selection under profile-specific objectives.
15. Selecting a profile-specific packet/RMW binding offline is not enough for
    mobile fleets. The middleware can now refresh bindings continuously and
    quantify switch latency/flapping in a short ROS-backed transition matrix,
    and it can switch binding objectives during one live session. The
    unresolved gap is doing this at fleet scale, over longer dwell windows,
    across repeated seeds, and inside a true RMW boundary.
16. Multi-robot bridge coverage is necessary but not yet sufficient for a
    fleet-scale claim. The current two-robot ROS-backed local-services matrix
    proves that sidecar decisions, receiver packets, egress publications, local
    lease decisions, projection gate decisions, and monitor observations can
    preserve robot namespace coverage while profile and objective both change.
    The new per-robot QoS budget run shows why coverage and aggregate averages
    are not enough: Jain fairness is near-perfect, but only one of three seeds
    passes the absolute per-robot control-delivery budget. The unresolved gap is
    validating the new virtual-queue budget-aware controller in the ROS 2 live
    bridge so each robot's SLO can be protected while the fleet still optimizes
    utility.
17. Multi-source feedback is not useful unless the middleware can assign
    responsibility to the right boundary. The latest ROS 2 feedback branch shows
    that egress, local-controller, and projection-gate signals can all reach the
    control plane, but naive aggregation double-counts control-lease WAN latency
    as command deadline debt. Correct ownership treats control leases as
    locally valid authority windows, so egress owns delivery/tail evidence and
    local-controller owns command freshness. With that rule, the existing
    `feedback_multisource_arbitrated_v2_deadlinefirst` log passes the hard
    two-robot budget (`min_control=0.9000`, `max_deadline=0.3483`) while the
    action-deadline branch still misses (`max_deadline=0.3820`). The unresolved
    gap is proving this ownership-aware arbitration over longer fleet-scale,
    repeated live runs and using transform-specific attribution to prevent
    remaining non-control tail debt before transmission.

## Implemented Prototype Direction

The current local prototype now includes a FleetRMW control plane with:

- predictive per-class admission control before congestion happens;
- semantic age/value estimation per flow;
- adaptive reliability and degradation by flow class;
- explicit deadline budget reservation for control and coordination;
- semantic compaction for control/state/coordination under high pressure;
- a live sidecar-netem matrix runner for FIFO, static priority, CSDS, and
  predictive admission;
- a risk-guarded predictive admission variant for safety/control deadline
  protection;
- a closed-loop sidecar feeder that updates future observation age from sidecar
  action feedback;
- a soft Lagrangian risk-constrained predictive admission variant;
- repeated-run sidecar statistics with confidence intervals and Pareto-frontier
  selection;
- an offline Lagrangian sweep that identifies risk-reset admission as the next
  controller mechanism to validate in Docker/netem;
- labeled Lagrangian sidecar variants, so Docker/netem can compare controller
  configurations without changing code between runs;
- an outcome-driven Lagrangian adaptation loop that generates and validates
  follow-up variants from measured netem results;
- a five-seed Docker/netem validation path for the adapted Lagrangian operating
  point, including confidence intervals and Pareto marking;
- a second outcome-adapted Lagrangian variant that improves the zero-miss
  utility point in the current five-seed profile;
- named LAN/Wi-Fi/WAN/roaming netem profiles with per-profile repeated-run
  report sections;
- graceful closed-loop feeder timeout handling for severely impaired profiles;
- sidecar-visible link profile plumbing from Docker/netem into `NetworkLink`;
- profile-aware Lagrangian admission with separate regime-specific dual state;
- contextual profile-envelope selection for safe/balanced/utility Lagrangian
  arms;
- control delivery metrics that expose dropped-control policies;
- a control-intent wire mode for WAN-infeasible control samples;
- a feasibility-aware semantic contract layer with transform certificates;
- a first-class semantic-contract scheduler that accounts transform bytes before
  admission instead of rewriting dropped packets after scheduling;
- a loss-aware semantic-contract variant with packet-level shadow pricing and
  non-control packet caps;
- an adaptive semantic-contract selector that previews high-utility and
  tail-shield variants, then chooses with contract-derived risk and loss
  exposure budgets;
- a supervisory control-intent lease for roaming paths where direct control and
  short command horizons are physically infeasible;
- measured roaming evidence that the supervisory/adaptive path preserves
  control delivery while moving the utility/byte/loss/deadline trade-off onto a
  Pareto frontier;
- a Dockerized ROS 2 live ingress-and-egress harness that confirms real
  `rclpy` callbacks can feed the adaptive sidecar, admitted sidecar packets can
  re-enter the ROS graph on macOS without native ROS installation, and
  `cmd_vel`, odometry, and laser scan samples can be projected back as typed
  FleetRMW-local ROS 2 messages;
- projection-quality metadata on `/fleetrmw/<robot>/projection_quality`, so
  typed FleetRMW-local messages carry an explicit companion contract describing
  fidelity, lossiness, downsampling, degradation reasons, and a canonical
  projection signature used by the consumer gate;
- qualified odometry and laser-scan wrapper messages, so state/perception can
  bind `ProjectionQuality` to the reconstructed ROS sample without relying on an
  adjacent sideband topic;
- a consumer-side projection quality gate that forwards accepted odometry and
  scan projections to `accepted_odom` and `accepted_scan` only after matching
  typed messages with either wrapper-local quality or identity-carrying quality
  envelopes by signature, while ignoring command projections because those are
  governed by the local control lease;
- compact projection-quality sidebands that carry fidelity and signature without
  embedding typed `projection_payload` for compatibility/debugging, plus a
  newer qualified-only wrapper mode that produced `38` accepted
  state/perception samples with zero `/projection_quality`, `local_odom`, or
  `local_scan` egress publications in Docker T3;
- a generated ROS 2 interface package, `fleetrmw_interfaces`, so projection
  quality now travels as `fleetrmw_interfaces/msg/ProjectionQuality`, or inside
  `QualifiedOdometry`/`QualifiedLaserScan`, rather than an untyped
  `std_msgs/String` JSON sideband;
- a dependency-free RMW sample contract layer, `fleetqox/rmw_contract.py`, that
  separates sample identity, delivery/admission provenance, fidelity, and
  qualified wrapper payload generation from the ROS 2 egress bridge;
- end-to-end `contract_id` propagation from ROS 2 shim batch to sidecar event,
  projection quality, qualified wrapper, and quality-gate decision log;
- source-derived `source_sample_id` propagation, with ROS header stamp metadata
  or RMW-facing publisher GID/sequence metadata producing stable source identity
  independent of the admission `contract_id`;
- native `FleetRmwSampleEnvelope` propagation through shim batches and sidecar
  events, so FleetRMW can own publisher identity and source sequence instead of
  depending on RMW-specific callback metadata;
- Docker T3 evidence that `38/38` received qualified state/perception samples
  preserved matching sidecar `contract_id`s and source-derived
  `source_sample_id`s through egress and gate decisions in
  `ros2_live_bridge_t3_source_sample_id_v1`;
- Docker T3 source-metadata evidence that `66/66` sidecar packet decisions
  carried live ROS 2 callback sequence and timestamp metadata in
  `ros2_live_bridge_t3_source_metadata_v2`;
- Docker T3 cross-RMW metadata evidence in
  `ros2_live_bridge_t3_rmw_metadata_v2`: Fast DDS, CycloneDDS, and Zenoh RMW all
  carried source/received timestamps; Fast DDS and Zenoh carried sequence
  numbers; CycloneDDS did not carry sequence numbers; none exposed publisher GID
  through the observed `rclpy` callback path;
- Docker T3 data-frame evidence in `ros2_live_bridge_t3_data_frame_v1`:
  `packet_format=data_frame` delivered `71/73` sidecar packets to the receiver,
  kept egress invalid packets at `0`, preserved `36/36` decision-to-gate
  `contract_id` and `source_sample_id` matches, and reached `1.0000` control
  delivery with `37.35 ms` p95 latency;
- Docker T3 cross-RMW data-frame evidence in
  `ros2_live_bridge_t3_data_frame_rmw_matrix_v1`: Fast DDS, CycloneDDS, and
  Zenoh RMW all ran with `packet_format=data_frame`, `0` invalid egress packets,
  `1.0000` control delivery, and complete decision-to-gate contract/source
  identity matches for every accepted qualified wrapper;
- Docker T3 packet-format comparison evidence in
  `ros2_live_bridge_t3_packet_format_compare_v1`: legacy `event_json` and
  native `fleetrmw.data_frame.v1` both delivered `80/80` packets with zero
  measured loss, `1.0000` control delivery, `40/40` quality-gate accepts, and
  complete `contract_id`/`source_sample_id` matches, while data-frame mode
  measured lower one-run p95 latency (`40.87 ms` versus `50.02 ms`);
- Docker T3 packet-format/RMW matrix evidence in
  `ros2_live_bridge_t3_packet_format_rmw_matrix_v1`: all six combinations of
  `{event_json,data_frame}` x `{Fast DDS,CycloneDDS,Zenoh RMW}` ran with `0`
  invalid egress packets and complete decision-to-gate identity matches; the
  result confirms frame portability but remains a single-realization transition
  test rather than a repeated latency-dominance claim;
- ROS 2 repeated packet-format/RMW harness evidence in
  `ros2_live_bridge_t3_repeated_packet_smoke_v1`: the live bridge runner now
  expands `--seeds` and named netem `--profile`s, passes deterministic workload
  seeds into the ROS 2 publisher, and writes repeated summary JSON/Markdown
  grouped by `packet_format/RMW`; the first one-seed Fast DDS Wi-Fi smoke ran
  both `event_json` and `data_frame` with `1.0000` control delivery and `0`
  deadline miss, validating the harness but not yet establishing a statistical
  packet-format ranking;
- ROS 2 repeated packet-format/RMW Wi-Fi evidence in
  `ros2_live_bridge_t3_repeated_packet_wifi_3seed_v1`: all `18/18`
  combinations of three workload seeds, two packet formats, and three RMWs ran
  with `0` invalid egress packets. `data_frame/rmw_zenoh_cpp` was the only
  non-dominated policy, with mean utility `458.2`, `1.0000` control delivery,
  mean p95 latency `38.27 ms`, and mean loss `0.0173`. This is the first
  repeated ROS-backed signal that native FleetRMW framing and RMW choice should
  be evaluated jointly;
- ROS 2 repeated packet-format/RMW WAN evidence in
  `ros2_live_bridge_t3_repeated_packet_wan_3seed_v1`: all `18/18`
  combinations again ran with `0` invalid egress packets, but the Pareto
  frontier changed. `event_json/rmw_zenoh_cpp` reached the highest mean utility
  (`342.5`) and receive count (`58.0`), while
  `data_frame/rmw_cyclonedds_cpp` had the lowest mean loss (`0.0271`) with
  `1.0000` control delivery. This confirms that packet format and RMW choice
  are profile-sensitive control-plane decisions rather than a fixed migration
  switch from JSON to binary;
- ROS 2 repeated packet-format/RMW roaming evidence in
  `ros2_live_bridge_t3_repeated_packet_roaming_3seed_v1`: all `18/18`
  combinations ran with `0` invalid egress packets under the `70 KB/s`, `80 ms`
  delay, `25 ms` jitter, `3%` loss roaming stress profile. The frontier changed
  again: `event_json/rmw_zenoh_cpp` had the highest mean utility (`248.5`), but
  `data_frame/rmw_zenoh_cpp` left the reporter's Pareto frontier despite the
  lowest reported mean p95 latency (`158.59 ms`) because the current objective
  vector optimizes utility, control starvation, deadline miss, loss, control
  delivery, and control non-delivery rather than latency directly;
- a first profile/objective-aware ROS 2 selector in
  `fleetqox.transport_selector`, with reproducible artifacts
  `profile_objective_selector_balanced_v1_summary.json` and
  `profile_objective_selector_teleop_v1_summary.json`. Under
  `balanced_safety_utility`, the selector chooses
  `data_frame/rmw_zenoh_cpp` for Wi-Fi, `event_json/rmw_zenoh_cpp` for WAN,
  and `event_json/rmw_zenoh_cpp` for roaming. Under `teleop_latency`, Wi-Fi and
  WAN stay the same, but roaming changes to
  `event_json/rmw_cyclonedds_cpp`, confirming that packet format and RMW choice
  must be profile-aware and objective-aware;
- a runtime `TransportBinding` path from selector summary to ROS 2 shim batch
  and sidecar runtime. The smoke scenario
  `ros2_shim_transport_binding_runtime_smoke_v1` reads the Wi-Fi balanced
  binding, attaches `data_frame/rmw_zenoh_cpp` to the batch, logs the binding on
  all `13/13` sidecar events, and emits `7` packets with
  `packet_format=data_frame`. The auto-profile smoke
  `ros2_shim_transport_binding_auto_profile_smoke_v1` infers the default
  roaming-like link as `roaming`, selects `event_json/rmw_zenoh_cpp`, and emits
  `7` packets with `packet_format=event_json`. The adaptive-profile smoke
  `ros2_shim_transport_binding_adaptive_profile_smoke_v1` uses the smoothing
  and hysteresis estimator path and selects the same roaming binding in this
  one-shot smoke;
- a live continuous binding path in `Ros2LiveSampleBuffer`. The smoke artifact
  `results_ros2_live_bridge/live_bridge_adaptive_binding_runtime_smoke_v1.json`
  feeds a Wi-Fi-like tick followed by a roaming-like tick through the adaptive
  provider and sidecar runtime:
  tick `0` selects `data_frame/rmw_zenoh_cpp` with profile `wifi`, tick `1`
  selects `event_json/rmw_zenoh_cpp` with profile `roaming`, and both batches
  carry estimator confidence, margin, scores, and dwell state into the sidecar
  batch/log path; the runtime decision log records `2/2` rows with
  `transport_binding` and `transport_binding_estimate`;
- a Docker T3 profile-transition harness. The run
  `ros2_live_bridge_t3_profile_transition_v1` keeps the ROS 2 live bridge path
  running while `tc netem` changes from Wi-Fi to WAN to roaming at `0`, `2`,
  and `4` seconds. The transition log records `3/3` applied netem profiles.
  The sidecar decision log records `87/87` rows with `transport_binding` and
  `transport_binding_estimate`, observes both packet formats, and switches
  binding at tick `14` from `wifi/data_frame/rmw_zenoh_cpp` to
  `wan/event_json/rmw_zenoh_cpp`, then at tick `28` to
  `roaming/event_json/rmw_zenoh_cpp`. The same run received `72/80` sidecar
  packets, measured `132.64 ms` p95 latency, `0.8966` control delivery, and
  preserved `46/46` decision-to-gate contract/source identity matches;
- a Docker T3 adaptive-vs-static transition binding matrix. The run
  `ros2_live_bridge_t3_profile_transition_binding_matrix_v1` holds the same
  Wi-Fi/WAN/roaming transition workload constant and compares adaptive binding
  with static Wi-Fi, static WAN, and static roaming bindings under
  `rmw_zenoh_cpp`. All `4/4` runs completed. Adaptive switched twice
  (`wifi -> wan -> roaming`), observed both `data_frame` and `event_json`, and
  delivered the highest control delivery (`0.9787`) and semantic utility
  (`630.45`). Static baselines won some raw metrics in this one-seed smoke:
  `static_wifi` had the lowest loss (`0.0440`), `static_wan` had the lowest
  deadline miss ratio (`0.2093`), and `static_roaming` had the lowest p95
  latency (`115.18 ms`). This turns the current claim into a measurable
  trade-off: adaptive preserves more useful/control traffic under profile
  transitions, while repeated seeds are still needed before making statistical
  dominance claims;
- a three-seed Docker T3 adaptive-vs-static transition binding matrix. The run
  `ros2_live_bridge_t3_profile_transition_binding_matrix_3seed_v1` completes
  all `12/12` adaptive/static runs over seeds `7,13,29`. Adaptive matches both
  scheduled profile switches per run, has zero measured flapping, and measures
  mean absolute switch latency `0.1805 s`. It is the best mean policy for
  control delivery (`0.9654`), deadline miss ratio (`0.1991`), and p95 latency
  (`117.83 ms`). Static roaming remains slightly better on mean loss
  (`0.0600` versus adaptive `0.0605`), and static WAN remains better on mean
  semantic utility (`530.0` versus adaptive `517.7`). This changes the evidence
  status from "needs repeated seeds" to a narrower research gap: adaptive
  transition binding is measured and stable in the short ROS-backed matrix, but
  the system still needs longer runs, more robots, more objective schedules,
  and a deeper RMW boundary before claiming fleet-scale dominance;
- a Docker T3 dynamic-objective live binding matrix. The one-seed smoke
  `ros2_live_bridge_t3_dynamic_objective_transition_smoke_v1` first proved that
  a single ROS 2 live bridge session can change both network profile and active
  binding objective: `balanced_safety_utility@0`, `autonomy_safety@2`, and
  `balanced_safety_utility@4`. The follow-up run
  `ros2_live_bridge_t3_dynamic_objective_transition_3seed_v1` repeats the same
  schedule over seeds `7,13,29` and completes `3/3` runs. Mean results are
  rx `97.33`, loss `0.0642`, control delivery `0.9612`, deadline miss `0.2400`,
  p95 latency `115.50 ms`, and delivered utility `518.28`. It matches both
  scheduled profile switches/run and both scheduled objective switches/run,
  with mean absolute profile switch latency `0.1644 s`, mean absolute objective
  switch latency `0.0468 s`, zero measured flapping, and `2.0` policy
  switches/run. This proves repeated objective-adaptive binding at the sidecar
  boundary, while also exposing the next boundary gap: packet-format selection
  can take effect immediately, but RMW changes remain target metadata until the
  decision moves into `rmw_fleetqox_cpp`;
- a Docker T3 two-robot dynamic-objective live binding matrix. The run
  `ros2_live_bridge_t3_dynamic_objective_transition_2robot_3seed_v1` expands
  the same schedule to `robot_0000` and `robot_0001` namespaces and completes
  `3/3` seeds. Mean results are rx `159.33`, loss `0.0637`, control delivery
  `0.9432`, deadline miss `0.2472`, p95 latency `121.69 ms`, and delivered
  utility `844.71`. Decision logs, receiver packets, and egress publications
  all observed both robot IDs in every seed;
- a Docker T3 two-robot local-services dynamic-objective matrix. The run
  `ros2_live_bridge_t3_dynamic_objective_transition_2robot_local_services_3seed_v1`
  makes the local controller, projection quality gate, and ROS monitor
  namespace-aware under the same two-robot transition schedule. It completes
  `3/3` seeds with mean rx `148.67`, loss `0.0542`, control delivery `0.9524`,
  deadline miss `0.2661`, p95 latency `131.93 ms`, and delivered utility
  `790.50`. In every seed, sidecar decisions, receiver packets, egress
  publications, local lease decisions, projection gate decisions, and monitor
  observations all observed both `robot_0000` and `robot_0001`;
- a Docker T3 two-robot per-robot QoS budget matrix. The run
  `ros2_live_bridge_t3_dynamic_objective_transition_2robot_fair_budget_3seed_v1`
  completes `3/3` seeds and adds `fleetrmw.per_robot_qos.v1` plus
  `fleetrmw.per_robot_qos_budget.v1` reporting. Mean RX fairness is `1.0000`,
  control-delivery fairness is `0.9984`, and deadline-success fairness is
  `0.9997`, but the budget pass ratio is only `0.3333` because seeds `13` and
  `29` fall below the `0.90` minimum per-robot control delivery threshold
  (`0.8846` and `0.8718`). This is the first ROS-backed evidence that relative
  fairness and aggregate control delivery can hide robot-level SLO violations;
- a per-robot budget-aware admission wrapper,
  `RobotBudgetAwareAdmissionController`, that turns those SLO violations into
  virtual-queue pressure on future scheduling rounds. In the deterministic
  two-robot one-slot smoke, the predictive baseline delivers all control
  packets to `robot_0000` and none to `robot_0001` (Jain `0.5000`), while the
  budget-aware wrapper splits delivery `0.5000/0.5000` and raises Jain to
  `1.0000`;
- a ROS 2 Docker validation run for `fleetqox_semantic_contract_budgeted`.
  Against the two-robot dynamic-objective baseline it keeps the same budget pass
  ratio (`0.3333`) but shifts the operating point: mean minimum per-robot
  control delivery rises slightly (`0.8950` to `0.8974`), maximum per-robot
  deadline miss falls (`0.3036` to `0.2783`), aggregate deadline miss falls
  (`0.2920` to `0.2507`), and p95 latency falls (`128.42 ms` to `120.56 ms`).
  The cost is lower aggregate control delivery (`0.9328` to `0.9101`) and lower
  utility (`818.53` to `806.17`). The budgeted wrapper is therefore a measured
  Pareto trade-off, not yet a solved per-robot SLO mechanism;
- a ROS 2 Docker tail-risk validation run for the same
  `fleetqox_semantic_contract_budgeted` policy after adding network-tail-risk
  pressure and pressure-aware semantic shaping. The run
  `ros2_live_bridge_t3_dynamic_objective_transition_2robot_budgeted_tailrisk_3seed_v1`
  completes `3/3` seeds and raises the per-robot budget pass ratio from
  `0.3333` to `1.0000`. Mean minimum per-robot control delivery rises from
  `0.8950` to `0.9222`, and aggregate control delivery rises from `0.9328` to
  `0.9422`. The cost is visible: p95 latency rises from `128.42 ms` to
  `132.73 ms`, utility falls from `818.53` to `767.96`, and seed `13` shows a
  large per-robot p95 spread. Decision logs confirm the mechanism is active:
  seeds `7`, `13`, and `29` record `114`, `84`, and `130`
  `robot_budget=active` decisions plus `25`, `28`, and `29`
  `pressure_shaping` decisions;
- a sidecar `robot_feedback` protocol for the budget-aware policy. When
  `fleetqox_semantic_contract_budgeted` is active, feedback records containing
  observed per-robot delivery/deadline ratios update the same virtual queues
  used by scheduler-side pressure. Unit coverage verifies that a feedback
  message changes pressure and annotates the next batch with
  `robot_budget=active`;
- a ROS 2 egress feedback producer and multi-client sidecar TCP server. The
  egress bridge can aggregate received packet outcomes into per-robot feedback
  windows while the live bridge keeps its batch connection open. The Docker
  smoke `ros2_live_bridge_t3_dynamic_objective_transition_2robot_feedback_core_window_smoke_v1`
  confirms wiring with `28` feedback records applied and `0` feedback
  connection failures. It is intentionally not promoted to the main benchmark:
  budget pass remains `0.0`, aggregate control delivery is `0.9024`, and p95
  latency is `293.18 ms`, so the feedback law needs damping/QoE shaping before
  it can replace the tail-risk result;
- a damped live feedback law for the same egress path. Feedback windows now
  carry sample counts, the controller scales external feedback learning by
  window evidence, caps deadline-risk feedback, and treats perception deadline
  misses as non-core for robot-budget feedback. The one-seed smoke
  `ros2_live_bridge_t3_dynamic_objective_transition_2robot_feedback_damped_smoke_v1`
  reports aggregate control delivery `0.9412` and worst-robot control delivery
  `0.9118`, up from `0.9024` and `0.8537` in the previous feedback smoke. The
  decision log shows less overreaction: `pressure_shaping` falls from `74` to
  `42`, `drop` from `32` to `22`, and `defer` from `38` to `18`. This is still
  a negative benchmark result because budget pass remains `0.0`, deadline miss
  rises to `0.6405`, and p95 latency rises to `399.36 ms`. The next controller
  step is therefore QoE/latency-aware feedback, not another raw gain tweak;
- a QoE/latency-aware feedback boundary for the same live path. Egress windows
  now report `mean_latency_ms`, `tail_latency_ms`, `mean_deadline_ms`,
  `latency_deadline_ratio`, and `latency_sample_count`. The controller keeps
  that signal in a separate `latency_deficit`: control/deadline debt drives
  critical-flow service pressure, while non-critical shaping sees total pressure
  including latency debt. The one-seed smoke
  `ros2_live_bridge_t3_dynamic_objective_transition_2robot_feedback_qoe_smoke_v1`
  improves deadline miss to `0.5097` and p95 to `302.53 ms` versus the damped
  feedback run, with utility `851.69`. It remains a negative benchmark result
  because budget pass is still `0.0` and worst-robot control delivery is
  `0.8718`. This converts the next research gap into a control-first,
  lexicographic feedback objective: optimize QoE only inside the envelope where
  every robot still satisfies its control SLO;
- a control-first QoE feedback gate. The controller now stores latency debt but
  only lets it contribute to total non-critical shaping pressure when the robot
  has control-delivery headroom above the SLO. The one-seed smoke
  `ros2_live_bridge_t3_dynamic_objective_transition_2robot_feedback_control_first_qoe_smoke_v1`
  recovers aggregate control delivery to `0.9136`, worst-robot control delivery
  to `0.9024`, RX to `163`, loss to `0.0686`, and utility to `906.17`. Budget
  pass remains `0.0` because worst-robot deadline miss is `0.7125`, so the next
  hard-SLO gap is deadline-first feedback inside the control-first envelope;
- an experimental deadline-first budgeted policy,
  `fleetqox_semantic_contract_budgeted_deadline_first`, that adds deadline debt
  as extra non-critical shaping pressure without changing critical service
  pressure. The policy smoke
  `ros2_live_bridge_t3_dynamic_objective_transition_2robot_feedback_deadline_first_policy_smoke_v1`
  reaches aggregate control delivery `0.9846`, worst-robot control delivery
  `0.9697`, RX `144`, loss `0.0649`, and utility `797.30`. Budget pass remains
  `0.0` because worst-robot deadline miss is `0.5694`, so this is a promising
  high-control/high-utility branch but not a replacement for the tail-risk
  benchmark;
- multi-source ROS-side feedback producers. The local control lease adapter now
  reports command-delivery outcomes, while the projection quality gate reports
  publish/drop QoE risk for qualified state and perception projections. The
  one-seed smoke
  `ros2_live_bridge_t3_dynamic_objective_transition_2robot_feedback_multisource_smoke_v1`
  applies `24` egress, `60` local-controller, and `93` quality-gate feedback
  records. RX rises to `166` and utility reaches `912.44`, but budget pass
  remains `0.0`: worst-robot control delivery falls to `0.8049`, worst-robot
  deadline miss is `0.6000`, and p95 is `320.51 ms`. This validates the feedback
  boundary and moves the hard research gap to arbitration and credit assignment
  across feedback sources;
- source-aware multi-source feedback arbitration. Feedback records are now
  partial dimension updates instead of implicit full-state credit: egress owns
  receiver-visible delivery/latency and non-control deadline feedback,
  local-controller feedback owns command-application deadline evidence with a
  separate responsibility weight, and projection-gate feedback only updates
  QoE/latency debt. The conservative v1 arbitration smoke was negative, with RX
  `97`, control delivery `0.8491`, and utility `535.84`. The v2 arbitration
  smoke recovers the hard control side with worst-robot control delivery
  `0.9722`, aggregate control delivery `0.9722`, loss `0.0608`, and p95
  `299.45 ms`, but budget pass remains `0.0` because worst-robot deadline miss
  is `0.3857`. Combining v2 with the deadline-first policy gives the best
  multi-source branch so far: reanalysis of the existing log passes the hard
  budget with RX `175`, utility `953.89`, control delivery `0.9500`, p95
  `284.66 ms`, minimum per-robot control delivery `0.9000`, and worst-robot
  deadline miss `0.3483`. A fresh corrected live smoke also passes with RX
  `134`, control delivery `0.9394`, deadline miss `0.2164`, p95 `262.47 ms`,
  minimum control delivery `0.9091`, and worst-robot deadline miss `0.2319`.
  A deadline-debt firewall knob and control horizon-lift knob both exist but
  remain disabled by default after negative smokes;
- action-aware deadline attribution. Egress feedback windows now report
  deadline miss ratios by `flow_class:wire_mode`, and the robot budget wrapper
  stores per-transform deadline debt, for example `control:control_intent`. The
  experimental
  `fleetqox_semantic_contract_budgeted_action_deadline_first` policy exposes the
  signal to targeted transform hooks. Its v2 smoke reaches RX `178`, utility
  `1010.71`, aggregate control delivery `0.9885`, loss `0.0481`, and p95
  `293.55 ms`; after correcting control-lease deadline ownership it still
  misses hard budget because worst-robot non-control deadline miss is `0.3820`.
  A lower action threshold triggers horizon lifts but is negative:
  RX falls to `145` and p95 rises to `378.50 ms`;
- hard-SLO volatility guarding. Control-lease redundancy fixes residual UDP
  loss in the lease path, while `event_id` de-duplication keeps delivery metrics
  unique. A current-link deadline firewall improves the repeated ownership run
  to `2/3` passing seeds, but seed `13` still shows non-control samples sent
  during low-confidence binding epochs arriving late after startup/profile
  volatility. The runtime now defers non-control packets when
  `transport_binding_estimate` confidence or margin is low, or immediately
  after a binding change. The repeated ROS 2 live scenario
  `ros2_live_bridge_t3_dynamic_objective_transition_2robot_feedback_deadline_ownership_volatility_guard_3seed_v1`
  passes all hard per-robot budgets: pass ratio `1.0000`, RX `70.3333`, loss
  `0.0128`, control delivery `0.9872`, deadline miss `0.0000`, p95
  `241.78 ms`, minimum per-robot control delivery `0.9872`, and worst-robot
  deadline miss `0.0000`. This is a safe-envelope result, not a solved QoE
  result, because quality-gate coverage falls to `0.0000`;
- bounded QoE recovery inside that volatility shield. The runtime now has a
  low-cost recovery probe that can pass only `semantic_delta`/`degraded`
  state, perception, or human-QoE packets, rate-limited per robot/class and
  gated by binding-estimator confidence, margin, dwell, and predicted slack.
  `semantic_delta` odometry is classified as `semantic_projection` instead of
  degraded projection, so a local quality gate can distinguish usable semantic
  state from lossy degraded samples. The stable 3-seed run
  `ros2_live_bridge_t3_dynamic_objective_transition_2robot_feedback_deadline_ownership_qoe_stable_probe_3seed_v1`
  keeps hard budget pass `1.0000` and restores quality-gate robot coverage to
  `2.0000`, with RX `77.6667`, loss `0.0127`, control delivery `0.9870`,
  deadline miss `0.0171`, p95 `293.40 ms`, semantic utility `564.22`, and
  worst-robot deadline miss `0.0264`. This is a conservative QoE-recovery
  default, not the final optimum: an aggressive probe recovers more projection
  samples but raises non-control deadline miss;
- fleet-quota QoE recovery for more than two robots. The volatility recovery
  path now selects probes at batch level using a sublinear fleet quota
  `ceil(scale * sqrt(active_robot_count))` plus a per-robot cap. It can admit
  low-cost semantic probes during uncertain binding epochs, so QoE evidence is
  not blocked until the estimator is already stable. The one-seed four-robot
  smoke first proved the path; the repeated 3-seed matrix
  `ros2_live_bridge_t3_dynamic_objective_transition_4robot_qoe_recovery_quota_3seed_v1`
  now completes `3/3` seeds and observes all four robots in decisions,
  receiver, egress, local leases, quality gate, and monitor logs. It keeps hard
  budget pass `1.0000` with RX `91.3333`, loss `0.0109`, control delivery
  `0.9957`, deadline miss `0.0773`, p95 `422.22 ms`, semantic utility `646.41`,
  worst-robot deadline miss `0.1209`, and quality-gate robot coverage ratio
  `1.0000`. The same harness then exposed the first `8`-robot scale frontier:
  the initial repeated row over seeds `7,13,29` failed hard budget with control
  delivery `0.7859`, loss `0.1960`, p95 `1387.09 ms`, minimum per-robot control
  delivery `0.6164`, and quality-gate coverage `0.9583`. That negative row
  forced three transport-side changes rather than another pure scheduler tweak:
  an N-aware command service floor, paced control-lease redundancy, and finally
  source-sequence ACK/NACK recovery with a liveliness-backed history horizon.
  The current repeated `8`-robot audit now passes all seeds `7,13,29`: hard
  budget pass `1.0000`, control delivery `0.9902`, mean minimum per-robot
  control delivery `0.9804`, loss `0.0311`, deadline miss `0.1296`, p95
  `1085.30 ms`, and quality-gate coverage `1.0000`. This upgrades the
  multi-robot claim from structural wiring to a measured `8`-robot hard-SLO
  bridge result; the next scale claim should use longer segments, larger rows,
  and a socket-backed FleetRMW boundary rather than more sidecar-local ACK
  tuning;
- a robot-side local control lease adapter that gates typed commands by lease
  freshness, local velocity bounds, acceleration bounds, and jerk bounds, then
  publishes fallback stop or another configured expiry action when authority
  expires;
- data-driven local controller profiles in
  `experiments/local_controller_profiles_v1.json`, currently covering
  `tb4_lite_safe_v1` and `warehouse_amr_safe_v1`, with required-field and
  numeric validation before the ROS 2 adapter starts.

The next step is to harden the ROS 2 path beyond profile-driven `cmd_vel`:

- use action-aware deadline attribution to prevent transform-specific deadline
  misses before rerunning the
  repeated Docker T3 profile/objective transition matrix before extending it to
  longer profile segments, more than two robots, more objective schedules, and
  confidence intervals;
- map odometry, scan/perception, degraded state, and controller-specific leases
  into typed local commands or reconstructed ROS messages where that is
  semantically valid;
- extend the projection-quality contract with covariance confidence, perception
  confidence, and controller-specific validity constraints;
- push the new qualified wrapper contract down toward RMW sample metadata or a
  true RMW shim boundary, instead of leaving it as a FleetRMW-local application
  topic;
- calibrate jerk envelopes and validate hold-last versus stop policies against
  measured robot dynamics per controller type;
- replay the same flow decisions through UDP/QUIC-like transports;
- validate against larger ROS 2 `performance_test` traffic under `tc netem`;
- later, connect it to `rmw` implementation boundaries;
- extend predictive admission with deadline-risk constraints so it keeps its
  utility/compaction advantage while matching or beating CSDS on control misses;
- use closed-loop feedback to implement a soft risk-constrained optimizer with
  measured deadline/QoE multipliers;
- expand repeated closed-loop Docker/netem sweeps across impairment profiles,
  then compare the same controller envelope against ROS 2 traffic;
- tune the profile-aware safety envelopes over multiple WAN/roaming seeds to
  recover utility without giving back the deadline reduction;
- replace hand-selected per-profile envelopes with a constrained context-bandit
  or online optimizer over link regime, flow class, semantic value, and observed
  deadline/QoE outcomes;
- validate and tune control-intent horizon sizing, rate control, and loss
  recovery across WAN and roaming profiles;
- run repeated Docker/netem sweeps for `fleetqox_semantic_contract`, then compare
  it against `fleetqox_predictive_intent` and profile-aware baselines across WAN
  and roaming profiles.

The key research claim to test next:

```text
Fleet-level semantic admission plus adaptive reliability can reduce p99
deadline miss for control/state flows under shared network bottlenecks while
preserving operator-visible QoE better than DDS/Zenoh QoS tuning or static
priority alone.
```

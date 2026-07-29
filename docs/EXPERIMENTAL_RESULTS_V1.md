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
| Docker ROS RMW domain-isolation probe | `results_rmw_socket/docker_rmw_domain_isolation_probe_summary.json` |
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
| Docker ROS RMW upstream Nav2/RMF concurrency-8 action/service workload | `results_rmw_socket/docker_router_nav2_rmf_action_workload_concurrency8_summary.json` |
| Docker chained Nav2/RMF task-outcome gateway submission 5-run mTLS/netem | `results_rmw_socket/docker_nav2_rmf_task_outcome_gateway_probe_summary.json` |
| Docker live-process Nav2/RMF task-outcome gateway submission 5-run mTLS/netem | `results_rmw_socket/docker_nav2_rmf_live_task_outcome_probe_summary.json` |
| Docker ROS RMW upstream Nav2/RMF concurrency-16 action/service workload | `results_rmw_socket/docker_router_nav2_rmf_action_workload_concurrency16_summary.json` |
| Docker ROS RMW upstream Nav2/RMF concurrency-32 action/service workload | `results_rmw_socket/docker_router_nav2_rmf_action_workload_concurrency32_summary.json` |
| Docker ROS RMW upstream Nav2/RMF concurrency-64 action/service workload | `results_rmw_socket/docker_router_nav2_rmf_action_workload_concurrency64_summary.json` |
| Docker ROS RMW upstream Nav2/RMF concurrency-128 action/service workload | `results_rmw_socket/docker_router_nav2_rmf_action_workload_concurrency128_summary.json` |
| Docker ROS RMW upstream Nav2/RMF concurrency-256 action/service workload | `results_rmw_socket/docker_router_nav2_rmf_action_workload_concurrency256_summary.json` |
| Docker ROS RMW upstream Nav2/RMF concurrency-512 action/service workload | `results_rmw_socket/docker_router_nav2_rmf_action_workload_concurrency512_summary.json` |
| Docker ROS RMW upstream Nav2/RMF concurrency-1024 action/service workload | `results_rmw_socket/docker_router_nav2_rmf_action_workload_concurrency1024_summary.json` |
| Docker ROS RMW upstream Nav2/RMF concurrency-2048 action/service workload | `results_rmw_socket/docker_router_nav2_rmf_action_workload_concurrency2048_summary.json` |
| Docker ROS RMW upstream Nav2/RMF unwindowed concurrency-4096 action/service workload | `results_rmw_socket/docker_router_nav2_rmf_action_workload_concurrency4096_summary.json` |
| Docker ROS RMW upstream Nav2/RMF total-4096 admission-windowed workload | `results_rmw_socket/docker_router_nav2_rmf_action_workload_total4096_goalbatch8_summary.json` |
| Docker ROS real Nav2 planner/controller lifecycle configure | `results_rmw_socket/docker_nav2_planner_controller_lifecycle_probe_summary.json` |
| Docker ROS real Nav2 planner/controller lifecycle activation with dynamic TF | `results_rmw_socket/docker_nav2_planner_controller_activation_probe_summary.json` |
| Docker ROS real Nav2 ComputePathToPose planner action with map/TF | `results_rmw_socket/docker_nav2_planner_compute_path_probe_summary.json` |
| Docker ROS real Nav2 FollowPath controller action with map/TF/odom | `results_rmw_socket/docker_nav2_controller_follow_path_probe_summary.json` |
| Docker ROS real Nav2 NavigateToPose same-pose BT pipeline | `results_rmw_socket/docker_nav2_navigate_to_pose_probe_summary.json` |
| Docker ROS repeated Nav2 NavigateToPose same-pose BT pipeline | `results_rmw_socket/docker_nav2_navigate_to_pose_repeated_probe_summary.json` |
| Docker ROS moving-base Nav2 NavigateToPose BT pipeline | `results_rmw_socket/docker_nav2_navigate_to_pose_moving_probe_summary.json` |
| Docker ROS extended moving-base Nav2 NavigateToPose BT pipeline | `results_rmw_socket/docker_nav2_navigate_to_pose_extended_moving_probe_summary.json` |
| Docker ROS long repeated moving-base Nav2 NavigateToPose BT workload | `results_rmw_socket/docker_nav2_navigate_to_pose_long_moving_probe_summary.json` |
| Docker ROS Nav2 planner static-obstacle repair/replan | `results_rmw_socket/docker_nav2_planner_obstacle_repair_probe_summary.json` |
| Docker ROS Nav2 NavigateToPose obstacle retry after clear map | `results_rmw_socket/docker_nav2_navigate_to_pose_obstacle_retry_probe_summary.json` |
| Docker ROS Nav2 same-goal NavigateToPose obstacle recovery after clear map | `results_rmw_socket/docker_nav2_navigate_to_pose_autonomous_obstacle_recovery_probe_summary.json` |
| Docker ROS Nav2 dynamic LaserScan obstacle mark and costmap clear | `results_rmw_socket/docker_nav2_dynamic_costmap_clear_summary.json` |
| Docker ROS moving NavigateToPose dynamic-obstacle stop/clear/resume | `results_rmw_socket/docker_nav2_dynamic_obstacle_navigation_summary.json` |
| Docker ROS Nav2 behavior_server Spin recovery action | `results_rmw_socket/docker_nav2_behavior_spin_probe_summary.json` |
| Docker ROS Nav2 NavigateToPose recovery-tree fallback | `results_rmw_socket/docker_nav2_navigate_to_pose_recovery_tree_probe_summary.json` |
| Docker ROS Nav2 NavigateToPose recovered success after Spin | `results_rmw_socket/docker_nav2_navigate_to_pose_recovered_success_probe_summary.json` |
| Docker ROS repeated Nav2 NavigateToPose recovered success after Spin | `results_rmw_socket/docker_nav2_navigate_to_pose_recovered_success_repeated_probe_summary.json` |
| Docker ROS standalone C++ type-support round trip | `results_rmw_socket/docker_cpp_typesupport_probe_summary.json` |
| Docker ROS router-mediated C++ interprocess pub/sub + service | `results_rmw_socket/docker_router_rclcpp_interprocess_probe_summary.json` |
| Docker/netem bidirectional C++/rclpy 64-pose Path + 512-pose GetPlan service | `results_rmw_socket/docker_router_cpp_python_path_probe_summary.json` |
| Docker/netem generated bounded-shape C++/rclpy service matrix | `results_rmw_socket/docker_router_bounded_shape_service_probe_summary.json` |
| Docker/loopback-netem bounded service resource/backpressure matrix | `results_rmw_socket/docker_service_resource_limit_probe_summary.json` |
| Docker/loopback-netem noisy/quiet service-client isolation matrix | `results_rmw_socket/docker_service_client_isolation_probe_summary.json` |
| Docker/loopback-netem bounded service-repair admission matrix | `results_rmw_socket/docker_service_repair_admission_probe_summary.json` |
| Docker/loopback-netem service priority and aging matrix | `results_rmw_socket/docker_service_priority_probe_summary.json` |
| Docker/loopback-netem smooth weighted service matrix | `results_rmw_socket/docker_service_weighted_fairness_probe_summary.json` |
| Docker/loopback-netem deadline-aware service matrix | `results_rmw_socket/docker_service_deadline_scheduler_probe_summary.json` |
| Docker/netem SIGKILL durable completed-service replay matrix | `results_rmw_socket/docker_service_durable_replay_probe_summary.json` |
| Same-hop generic-serialized 8/16/32 three-seed v3 post-fix matrix | `results_rmw_socket/same_hop_rmw_comparison_8_16_32_3seed_v3_summary.json` |
| Same-hop common generic-middle 8/16/32 three-seed v4 matrix | `results_rmw_socket/same_hop_rmw_comparison_8_16_32_3seed_v4_common_middle_summary.json` |
| Same-hop exact-configuration 36-row resume-provenance control | `results_rmw_socket/same_hop_rmw_comparison_8_16_32_3seed_v5_resume_provenance_summary.json` |
| Same-hop roaming-to-Wi-Fi resume mismatch Docker control | `results_rmw_socket/same_hop_rmw_comparison_resume_profile_mismatch_docker_summary.json` |
| Same-hop 16-robot Wi-Fi/WAN/roaming three-seed profile sensitivity | `results_rmw_socket/same_hop_profile_sensitivity_16robot_3profile_3seed_summary.json` |
| Same-hop 8/16/32-robot × Wi-Fi/WAN/roaming full-factorial sensitivity | `results_rmw_socket/same_hop_profile_scale_sensitivity_8_16_32_3profile_3seed_summary.json` |
| Same-hop 16-robot exact 256/4096/32768-byte payload sensitivity | `results_rmw_socket/same_hop_payload_sensitivity_16robot_3size_3seed_summary.json` |
| Same-hop 16-robot exact 32768-byte offered-load sensitivity | `results_rmw_socket/same_hop_offered_load_sensitivity_32768b_16robot_3interval_3seed_summary.json` |
| Docker/netem FleetRMW 32768-byte loss-resilient fragment accumulation, five seeds | `results_rmw_socket/docker_loss_resilient_large_sample_fragment_5run_summary.json` |
| Docker deterministic FleetRMW fragment-specific NACK/selective repair with whole-sample retry disabled | `results_rmw_socket/docker_selective_fragment_repair_probe_summary.json` |
| Docker ROS two-container POSIX shared-memory + UDP fallback | `results_rmw_socket/docker_shared_memory_probe_summary.json` |
| Docker ROS SHM-local + UDP-router hybrid de-dup | `results_rmw_socket/docker_shm_udp_hybrid_probe_summary.json` |
| Docker ROS publisher/subscription payload-scratch allocation ABI | `results_rmw_socket/docker_allocation_probe_summary.json` |
| Docker ROS `rmw_take_sequence` ordering/thread-safety and Fast DDS Jazzy symbol audit | `results_rmw_socket/docker_rmw_take_sequence_probe_summary.json` |
| Docker ROS multi-subscriber `rmw_publisher_wait_for_all_acked` timeout/completion | `results_rmw_socket/docker_rmw_wait_for_all_acked_probe_summary.json` |
| Docker ROS four-container remote UDP/router/netem `rmw_publisher_wait_for_all_acked` timeout/completion | `results_rmw_socket/docker_remote_wait_for_all_acked_probe_summary.json` |
| Docker ROS BEST_AVAILABLE endpoint QoS discovery adaptation | `results_rmw_socket/docker_qos_best_available_probe_summary.json` |
| Docker ROS QoS deadline event ABI, production, and wait readiness | `results_rmw_socket/docker_qos_event_probe_summary.json` |
| Docker ROS complete Jazzy QoS-event wait/take matrix | `results_rmw_socket/docker_qos_event_waitability_matrix_summary.json` |
| Docker ROS publication/subscription matched event production | `results_rmw_socket/docker_matched_event_probe_summary.json` |
| Docker ROS two-container remote matched/QoS/type/liveliness event production and lease expiry | `results_rmw_socket/docker_remote_event_probe_summary.json` |
| Docker ROS two-container remote offered/requested deadline-missed events | `results_rmw_socket/docker_remote_deadline_event_probe_summary.json` |
| Aggregate repeated remote UDP/netem coverage for all 11 Jazzy RMW event types | `results_rmw_socket/remote_qos_event_coverage_summary.json` |
| Docker ROS reliability/durability-incompatible QoS event production | `results_rmw_socket/docker_qos_incompatible_event_probe_summary.json` |
| Docker ROS deadline-incompatible QoS event production | `results_rmw_socket/docker_qos_deadline_incompatible_event_probe_summary.json` |
| Docker ROS liveliness kind/lease-incompatible QoS event production | `results_rmw_socket/docker_qos_liveliness_incompatible_event_probe_summary.json` |
| Docker ROS incompatible-type event production | `results_rmw_socket/docker_type_incompatible_event_probe_summary.json` |
| Docker ROS message-lost event production | `results_rmw_socket/docker_message_lost_event_probe_summary.json` |
| Docker ROS two-container reliable message-lost notification under UDP/netem | `results_rmw_socket/docker_message_lost_interprocess_probe_summary.json` |
| Docker ROS two-container terminal repair budget/attempt/admission message-lost controls | `results_rmw_socket/docker_message_lost_terminal_repair_probe_summary.json` |
| Docker ROS liveliness event production | `results_rmw_socket/docker_liveliness_event_probe_summary.json` |
| Docker ROS AUTOMATIC liveliness idle renewal and false-loss suppression | `results_rmw_socket/docker_automatic_liveliness_probe_summary.json` |
| Docker ROS two-container remote MANUAL_BY_TOPIC timeout, publisher lost event, and wire reassertion | `results_rmw_socket/docker_remote_manual_liveliness_probe_summary.json` |
| Docker ROS two-container remote liveliness multi-endpoint isolation and churn | `results_rmw_socket/docker_remote_liveliness_multi_endpoint_probe_summary.json` |
| Docker ROS 64-endpoint MANUAL_BY_TOPIC scale and 16-endpoint SYSTEM_DEFAULT renewal | `results_rmw_socket/docker_liveliness_scale_probe_summary.json` |
| Docker ROS two-container 64-endpoint remote MANUAL_BY_TOPIC scale under netem | `results_rmw_socket/docker_remote_liveliness_scale_probe_summary.json` |
| Docker ROS default/non-expiring liveliness lifecycle and unresolved-policy controls | `results_rmw_socket/docker_liveliness_default_lease_probe_summary.json` |
| Docker ROS content-filter ABI and key-value/std_msgs enforcement | `results_rmw_socket/docker_content_filter_probe_summary.json` |
| Docker ROS SQL-like content-filter subset, precedence, and invalid-expression controls | `results_rmw_socket/docker_content_filter_sql_probe_summary.json` |
| Docker ROS typed content-filter reflection over introspection C/C++ nested and sequence fields | `results_rmw_socket/docker_content_filter_typed_probe_summary.json` |
| Docker ROS security-options lifecycle ABI | `results_rmw_socket/docker_security_options_probe_summary.json` |
| Docker ROS FleetQoX security allow/deny policy enforcement | `results_rmw_socket/docker_security_policy_probe_summary.json` |
| Docker ROS SROS2-generated permissions XML publish/subscribe enforcement | `results_rmw_socket/docker_sros2_permissions_probe_summary.json` |
| Docker ROS stress/security campaign smoke | `results_rmw_socket/docker_stress_security_campaign_summary.json` |
| Docker ROS introspection C/C++ loaned-message lifecycle | `results_rmw_socket/docker_loaned_message_probe_summary.json` |
| Docker ROS QUIC gateway session/tp/token file plumbing | `results_rmw_socket/docker_quic_gateway_session_reuse_probe_summary.json` |
| Docker ROS QUIC gateway take/download frame path | `results_rmw_socket/docker_quic_gateway_take_probe_summary.json` |
| Docker ROS QUIC gateway RMW take/download smoke | `results_rmw_socket/docker_quic_gateway_rmw_take_probe_summary.json` |
| Docker ROS QUIC gateway RMW take session-file reuse | `results_rmw_socket/docker_quic_gateway_rmw_take_session_reuse_probe_summary.json` |
| Docker ROS QUIC gateway bidirectional publish/take boundary | `results_rmw_socket/docker_quic_gateway_bidirectional_probe_summary.json` |
| Docker ROS QUIC gateway disable-early-data control | `results_rmw_socket/docker_quic_gateway_bidirectional_no_0rtt_probe_summary.json` |
| Docker ROS repeated async-burst QUIC gateway 10-run netem soak | `results_rmw_socket/docker_quic_gateway_async_burst_soak_summary.json` |
| Docker stateful FleetQoX QUIC/H3 gateway 5-run netem | `results_rmw_socket/docker_quic_stateful_gateway_probe_summary.json` |
| Docker stateful FleetQoX public-RMW publish/take 5-run netem | `results_rmw_socket/docker_quic_stateful_rmw_probe_summary.json` |
| Docker stateful FleetQoX QUIC mutual-TLS client-auth 5-run netem | `results_rmw_socket/docker_quic_mtls_probe_summary.json` |
| Docker public-API ngtcp2/GnuTLS mTLS server 5-run netem | `results_rmw_socket/docker_ngtcp2_public_mtls_server_summary.json` |
| Docker public-API ngtcp2 stateful FleetQoX gateway 5-run netem | `results_rmw_socket/docker_ngtcp2_public_stateful_gateway_summary.json` |
| Docker public-API ngtcp2 path-metric admission contrast 5-run netem | `results_rmw_socket/docker_ngtcp2_public_path_admission_summary.json` |
| Docker public-API ngtcp2 bounded async backend 5-run netem | `results_rmw_socket/docker_ngtcp2_public_async_backend_summary.json` |
| Docker public-API ngtcp2 certificate-identity queue fairness 5-run netem | `results_rmw_socket/docker_ngtcp2_public_identity_fairness_summary.json` |
| Docker public-API ngtcp2 per-identity active-worker isolation 5-run netem | `results_rmw_socket/docker_ngtcp2_public_active_worker_isolation_summary.json` |
| Docker public-API ngtcp2 online client-CRL refresh 5-run netem | `results_rmw_socket/docker_ngtcp2_public_online_crl_refresh_summary.json` |
| Docker stateful FleetQoX QUIC fleet-admission policy 5-run netem | `results_rmw_socket/docker_quic_admission_probe_summary.json` |
| Docker stateful FleetQoX QUIC QoS/QoE admission-repair coupling 5-run netem | `results_rmw_socket/docker_quic_qox_repair_probe_summary.json` |
| Docker stateful FleetQoX QUIC observation-fed competing batch 5-run netem | `results_rmw_socket/docker_quic_feedback_batch_probe_summary.json` |
| Docker stateful FleetQoX QUIC native path-observation mTLS contrast 5-run netem | `results_rmw_socket/docker_quic_native_path_observation_probe_summary.json` |
| Docker stateful FleetQoX authenticated native QoE-debt contrast 5-run netem | `results_rmw_socket/docker_quic_native_qoe_debt_probe_summary.json` |
| Docker stateful FleetQoX authenticated application-outcome QoE debt 5-run netem | `results_rmw_socket/docker_quic_application_outcome_probe_summary.json` |
| Docker stateful FleetQoX durable application-outcome failover 5-run netem | `results_rmw_socket/docker_quic_durable_application_outcome_failover_probe_summary.json` |
| Docker stateful FleetQoX PostgreSQL application-outcome failover 5-run netem | `results_rmw_socket/docker_quic_postgresql_application_outcome_failover_probe_summary.json` |
| Docker stateful FleetQoX QUIC durable active/passive failover 5-run netem | `results_rmw_socket/docker_quic_durable_failover_probe_summary.json` |
| Docker stateful FleetQoX QUIC durable admission/repair failover 5-run netem | `results_rmw_socket/docker_quic_durable_admission_failover_probe_summary.json` |
| Docker stateful FleetQoX QUIC single-writer fencing/takeover 5-run netem | `results_rmw_socket/docker_quic_writer_fencing_probe_summary.json` |
| Docker stateful FleetQoX QUIC automatic standby takeover 5-run netem | `results_rmw_socket/docker_quic_automatic_standby_takeover_probe_summary.json` |
| Docker stateful FleetQoX QUIC PostgreSQL automatic takeover 5-run netem | `results_rmw_socket/docker_quic_postgresql_failover_probe_summary.json` |
| Docker stateful FleetQoX QUIC synchronous PostgreSQL process failover 5-run netem | `results_rmw_socket/docker_quic_postgresql_replication_failover_probe_summary.json` |
| Docker stateful FleetQoX QUIC etcd-quorum automatic PostgreSQL failover 5-run netem | `results_rmw_socket/docker_quic_postgresql_quorum_failover_probe_summary.json` |
| Native ns-3 Docker 8/16/32 fleet matrix | `results_ns3/ns3_docker_fleet_matrix_8_16_32_3seed_v1_summary.json` |
| OMNeT++/INET template and input-trace integrity | `results_omnetpp/omnetpp_template_integrity_probe_summary.json` |
| OMNeT++/INET runtime and matched ns-3 bounded parity | `results_omnetpp/omnetpp_ns3_docker_parity_8_16_32_3seed_v1_summary.json` |
| Docker ROS RMW matched multi-topic router workload | `results_rmw_socket/docker_router_matched_multi_topic_probe_summary.json` |
| ROS 2 large-scale split-scope RMW comparison, 8/16/32 | `results_rmw_socket/large_scale_rmw_comparison_8_16_32_3seed_20260713_report.md` |
| ROS 2 matched-hop RMW comparison, 8/16/32 | `results_rmw_socket/same_hop_rmw_comparison_8_16_32_3seed_v1_report.md` |
| Unified benchmark/capability-boundary report | `results_rmw_socket/unified_benchmark_report.md` |

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
service/wait readiness. A concurrency-8 rerun of the same upstream Nav2/RMF
action/service workload reports `nav2_upstream=true`, `rmf_upstream=true`,
`navigation_batch=true`, `rmf_batch=true`,
`nav2_lifecycle_manager_upstream=true`, and `106/106` expected service frames.
The refreshed clean-build artifact additionally maps actual upstream Nav2
success/cancel results and the RMF submit response into three
`fleetrmw.quic_gateway_application_outcome.v1` documents. All three results are
delivered; only the canceled Nav2 goal has `task_succeeded=false`. This proves
the standardized mapping and delivery/success separation, while
`task_outcome_gateway_submission_performed=false` keeps automatic QUIC
submission outside that workload's claim. The chained
`docker_nav2_rmf_task_outcome_gateway_probe_summary.json` then consumes the
exact artifact (recording its SHA-256), seeds the three known frame identities,
and submits the three documents over mTLS/H3 in each of `5/5` netem runs. All
15 reports are accepted; each run records three task updates, one task failure,
two handshakes, six streams, and four connection reuses. This proves an
artifact-chained gateway submission path, not submission from the same live ROS
client process. The separate
`docker_nav2_rmf_live_task_outcome_probe_summary.json` closes that boundary:
`5/5` fresh workloads map their actual results and call the Python H3 client
before ROS teardown. In every run the submitter PID equals the ROS client PID,
the `rclpy` context and node are active, and one mTLS handshake carries three
known-frame POSTs plus three application-outcome POSTs over six streams (five
connection reuses). Netem runs on the ROS client and gateway, the URI-SAN
publisher binding rejects no valid request, and gateway state records three
task updates plus one canceled-task failure per run. During repeated validation
an RMF batch response loss was reproduced; enabling two existing FleetRMW
request/response repeats for this live workload repaired it, after which all
five RMF batches and all container exits passed. This does not change the
explicit `production_quic_backend_claim=false` boundary.
The concurrency-16 rerun keeps those same flags true and forwards `154/154`
expected service frames. The concurrency-32 rerun keeps those same flags true
and forwards `250/250` expected service frames. The concurrency-64 rerun also
keeps those same flags true and forwards `442/442` expected service frames.
The concurrency-128 rerun forwards `826/826` expected service frames, and the
concurrency-256 rerun forwards `1594/1594` expected service frames. The
concurrency-512 rerun forwards `3130/3130` expected service frames, the
concurrency-1024 rerun forwards `6202/6202`, and the concurrency-2048 rerun
forwards `12346/12346` expected service frames with zero invalid router frames
after FleetRMW UDP large-frame fragmentation/reassembly and router fragment
passthrough for oversized action status/service bursts. The concurrency-4096
rerun now passes as one unwindowed `goal_batch_size=4096` workload. The client
spins its executor during an automatic `0.5 ms` inter-send interval instead of
enqueueing every future before processing responses. All `4096/4096`
`NavigateToPose` goals are accepted and complete with status `4`, all
`4096/4096` RMF `SubmitTask` calls return, lifecycle startup/reset succeeds,
and the router forwards `98704` service frames with zero invalid frames. This
closes an unwindowed 4096-request transport/workload boundary under executor
spin pacing, 16 MiB UDP socket buffers, 250 us packet pacing, and three
duplicate-safe request/response transmissions. It does not claim 4096
simultaneously long-running navigation executions. The separate total-4096
admission-windowed rerun (`goal_batch_size=8`) remains a positive control:
`4096/4096` action goals and RMF calls complete, lifecycle transport stays
green, and the router forwards `106088` service frames. The follow-on
`docker_nav2_planner_controller_lifecycle_probe_summary.json` starts real
upstream `planner_server` and `controller_server`, configures
`nav2_navfn_planner::NavfnPlanner` and `dwb_core::DWBLocalPlanner` through
FleetRMW router lifecycle services, and leaves both nodes in `inactive`; that
configure-only artifact keeps `activation_claim=false`. The next
`docker_nav2_planner_controller_activation_probe_summary.json` adds repeated
dynamic `/tf` (`map->odom`, `odom->base_link`) over the same FleetRMW router,
then activates both upstream nodes. It reports planner and controller final
state `active`, `planner_activate_transition=true`,
`controller_activate_transition=true`, `/tf` advertised/forwarded, and `28`
lifecycle service frames forwarded. It still sets map server, odometry source,
navigation-goal, and full-navigation claims to false because no map server, BT
navigator, odometry source, or NavigateToPose execution is started.
The planner runtime probe
`docker_nav2_planner_compute_path_probe_summary.json` then provides a repeated
`nav_msgs/msg/OccupancyGrid` `/map` and dynamic `/tf` through the FleetRMW
router, activates `planner_server`, sends upstream
`nav2_msgs/action/ComputePathToPose`, and receives a successful Navfn result:
`compute_path_goal_succeeded=true`, `compute_path_error_code=0`, and
`compute_path_path_pose_count=14` with `18` lifecycle/action service frames
forwarded. It claims planner action execution only; controller execution,
odometry, BT navigator, NavigateToPose, and full navigation remain false.
The controller runtime probe
`docker_nav2_controller_follow_path_probe_summary.json` provides repeated
`/map`, dynamic `/tf`, and `nav_msgs/msg/Odometry` `/odom`, activates
`controller_server`, sends upstream `nav2_msgs/action/FollowPath`, and receives
a successful DWB result: `follow_path_goal_succeeded=true`,
`follow_path_error_code=0`, with controller log `Reached the goal!` and `18`
lifecycle/action service frames forwarded. This artifact itself is controller
execution only; BT navigator and NavigateToPose are covered by the next
artifact.
The current full-stack CI-light Nav2 probe
`docker_nav2_navigate_to_pose_probe_summary.json` starts upstream
`planner_server`, `controller_server`, and `bt_navigator`, drives all three to
`active [3]`, publishes repeated `/map`, `/tf`, and `/odom`, and sends
upstream `nav2_msgs/action/NavigateToPose` through a minimal
`ComputePathToPose -> FollowPath` behavior tree. It reports
`navigate_to_pose_goal_succeeded=true`, `navigate_to_pose_error_code=0`,
`bt_navigator_activate_transition=true`, `full_nav2_navigation_stack_claim=true`
with scope `ci_light_same_pose_nav2_bt_pipeline_no_motion`, and `54`
lifecycle/action service frames forwarded. The artifact keeps
`moving_robot_navigation_claim=false`, `recovery_behavior_claim=false`, and
`long_navigation_workload_claim=false`.
The repeated same-pose artifact
`docker_nav2_navigate_to_pose_repeated_probe_summary.json` repeats the same
full-stack CI-light pipeline twice with fresh ports and fresh Docker processes.
It reports `ok_run_count=2`, `navigate_to_pose_goal_succeeded_run_count=2`,
`min_service_frames_per_run=54`, and `total_fleetqox_router_service_frames=108`.
This strengthens repeatability for the no-motion BT pipeline.
The moving-base artifact
`docker_nav2_navigate_to_pose_moving_probe_summary.json` then replaces the
static odometry publisher with a fake base node that receives Nav2 `/cmd_vel`,
integrates a short forward motion, and publishes dynamic `/odom` and `/tf`
through FleetRMW. It sends a goal at `x=0.6`, succeeds with
`navigate_to_pose_error_code=0`, forwards `/cmd_vel`, records
`fake_base_cmd_vel_count=4`, and moves about `0.406 m`. This permits the scoped
`moving_robot_navigation_claim=true` for a short unobstructed CI-light Nav2 BT
pipeline. The extended moving-base artifact
`docker_nav2_navigate_to_pose_extended_moving_probe_summary.json` raises the
goal to `x=1.2`, still succeeds with `navigate_to_pose_error_code=0`, forwards
`/cmd_vel`, records `fake_base_cmd_vel_count=6`, and moves about `0.956 m`;
this permits `extended_moving_navigation_claim=true` for a single-goal
unobstructed 1m-plus fake-base pipeline. The long moving-base artifact
`docker_nav2_navigate_to_pose_long_moving_probe_summary.json` repeats that
unobstructed 1m-plus Nav2 BT path three times with fresh Docker processes,
requires every run to succeed, and aggregates `/cmd_vel`, service-frame, and
fake-base movement evidence. It permits
`long_navigation_workload_claim=true` for the scoped
`repeated_unobstructed_1m_plus_moving_base_nav2_bt_pipeline`. The planner-level
static-obstacle repair artifact
`docker_nav2_planner_obstacle_repair_probe_summary.json` starts upstream
`planner_server`, publishes `/tf`, then publishes a static occupancy-grid wall
on `/map`. The blocked `ComputePathToPose` goal is accepted but aborts with
`blocked_compute_path_error_code=208`; after replacing the wall map with a clear
map, the same goal succeeds with `clear_compute_path_error_code=0` and
`clear_compute_path_path_pose_count=14`. The FleetRMW router reports
`fleetqox_router_service_frames=22` against `expected_service_frames=18`.
This permits `planner_static_obstacle_repair_claim=true` and the scoped
`obstacle_field_recovery_claim=true` for
`planner_level_static_map_obstacle_blocks_then_clear_map_replans`; it keeps
`full_nav2_obstacle_recovery_claim=false` because this is not a full
`NavigateToPose` controller/BT obstacle-recovery behavior pipeline. The
full-stack obstacle retry artifact
`docker_nav2_navigate_to_pose_obstacle_retry_probe_summary.json` then starts
`planner_server`, `controller_server`, and `bt_navigator` with a fake moving
base. Its first `NavigateToPose` goal targets `x=0.8` against the wall and
aborts with `blocked_navigate_to_pose_status=ABORTED` and
`blocked_navigate_to_pose_error_code=208`; after publishing the clear map, the
retry succeeds with `clear_navigate_to_pose_status=SUCCEEDED` and
`clear_navigate_to_pose_error_code=0`. The router forwards
`fleetqox_router_service_frames=62` against `expected_service_frames=58`, the
fake base receives `fake_base_cmd_vel_count=6`, and it moves about `0.610 m`.
This permits `nav2_obstacle_retry_after_clear_claim=true` and
`full_nav2_obstacle_recovery_claim=true` for the scoped two-goal
retry-after-clear pipeline, while
`autonomous_same_goal_nav2_obstacle_recovery_claim=false` remains explicit for
that two-goal artifact. The same-goal obstacle recovery artifact
`docker_nav2_navigate_to_pose_autonomous_obstacle_recovery_probe_summary.json`
then runs one `NavigateToPose` goal with a custom BT
`ComputePathToPose -> Wait retry -> FollowPath`: the blocked static map causes
planner failure, `clear_map_published_during_goal=true` after an external map
repair, `/wait` action traffic is forwarded, and the same top-level goal
succeeds with `navigate_to_pose_status=SUCCEEDED`,
`navigate_to_pose_error_code=0`, `fake_base_cmd_vel_count=6`, about `0.610 m`
of fake-base motion, and `fleetqox_router_service_frames=1989`. This permits
`autonomous_same_goal_nav2_obstacle_recovery_claim=true` only for
`same_goal_bt_compute_path_wait_retry_after_external_static_map_repair`;
the independent `docker_nav2_dynamic_costmap_clear_summary.json` artifact now
starts the real `nav2_costmap_2d` lifecycle node, activates
`nav2_costmap_2d::ObstacleLayer`, and sends dynamic `LaserScan` plus `/tf`
through FleetRMW under Docker loopback `netem delay 2ms 1ms`. It records three
lethal cells at cost `254`, calls the real
`/local_costmap/clear_entirely_costmap` service, and then records maximum cost
`0` with zero occupied cells. FleetRMW forwards six lifecycle/clear service
frames with zero invalid frames. This permits
`nav2_dynamic_costmap_mark_clear_claim=true`; it deliberately keeps
`full_dynamic_obstacle_navigation_claim=false` and
`production_costmap_recovery_policy_claim=false` for that standalone artifact.
The follow-on
`docker_nav2_dynamic_obstacle_navigation_summary.json` starts planner,
controller, BT navigator, an obstacle/inflation local costmap, and a moving
fake base in one Docker/netem gate. A five-second controller failure tolerance
bounds recovery. In the negative control, the persistent LaserScan obstacle is
re-marked after a real clear response, progress remains below `0.004 m`, and
the action cancels with status `5`. In the positive case, the same running goal
first advances, then stops with a lethal cost `254`; after the obstacle source is
removed and one recovery clear succeeds, motion resumes and the action finishes
with status `4` at about `x=0.96 m`. The router recognizes terminal
unrecoverable-loss notices, forwards them to matching topic/domain subscriber
routes, and reports zero invalid frames. This permits the scoped
`navigate_to_pose_dynamic_obstacle_clear_resume_claim` and persistent-obstacle
negative-control claim. Version 2 adds a third goal and a persistent circular
obstacle fixed in the world after the robot begins moving. The 2D fake base
publishes ray-circle LaserScan intersections while upstream DWB controls
`(x,y,theta)`. Two independent Docker/netem runs both finish with action status
`4`; lateral excursion is `0.173-0.177 m`, measured obstacle-edge clearance is
`0.119-0.127 m`, and the robot passes the obstacle while its source remains
enabled. This permits the scoped
`dynamic_obstacle_detour_avoidance_claim=true`. Version 3 isolates global
replanning in a fourth goal: it clears residual local state, disables the
LaserScan obstacle source, inserts a persistent `0.3 x 0.9 m` occupied wall
into the global map after motion starts, and runs `ComputePathToPose` at two Hz.
In two final independent Docker/netem runs, the planner publishes `36`
post-update paths, maximum path excursion is `0.826 m`, robot excursion is
`0.545-0.547 m`, the robot passes the wall, and the same action finishes with
status `4`. This permits
`navigate_to_pose_global_dynamic_replanning_claim=true`. It does not prove
arbitrary/multiple obstacle fields or a production recovery policy, so
`full_dynamic_obstacle_navigation_claim` and
`production_costmap_recovery_policy_claim` remain false. The direct
recovery-behavior artifact
`docker_nav2_behavior_spin_probe_summary.json` starts upstream
`behavior_server`, activates `nav2_behaviors::Spin` through FleetRMW lifecycle
services, sends `/spin`, receives `spin_error_code=0`, forwards `/cmd_vel`,
records `fake_base_cmd_vel_count=8`, and rotates about `0.616 rad`. This
permits `nav2_recovery_behavior_claim=true` for a direct behavior-server action;
the follow-on recovery-tree artifact
`docker_nav2_navigate_to_pose_recovery_tree_probe_summary.json` starts
`planner_server`, `behavior_server`, and `bt_navigator`, then runs a
`RecoveryNode` whose primary `ComputePathToPose` intentionally uses
`MissingPlanner` and whose recovery child is `Spin`. The top-level
`NavigateToPose` goal aborts as expected with `navigate_to_pose_error_code=201`
after the retry, but the recovery branch executes: `/spin` status/feedback and
`/cmd_vel` are forwarded, `spin_goal_succeeded=true`,
`fake_base_cmd_vel_count=8`, and fake-base rotation is about `0.616 rad`. This
permits `navigate_to_pose_recovery_tree_claim=true` for an intentional-failure
BT fallback. The follow-on recovered-success artifact
`docker_nav2_navigate_to_pose_recovered_success_probe_summary.json` executes
`Spin` first, then successfully plans and follows a short `x=0.6`
`NavigateToPose` goal through `planner_server`, `controller_server`,
`behavior_server`, and `bt_navigator`: `navigate_to_pose_error_code=0`,
`spin_goal_succeeded=true`, `fake_base_cmd_vel_count=9`, and
`successful_recovered_navigation_claim=true`. The claim is scoped to
`spin_recovery_action_then_successful_navigate_to_pose`;
the repeated recovered-success artifact
`docker_nav2_navigate_to_pose_recovered_success_repeated_probe_summary.json`
then runs the same scoped path twice with fresh Docker processes, reports
`ok_run_count=2`, `spin_goal_succeeded_run_count=2`,
`successful_recovered_navigation_run_count=2`, `total_fake_base_cmd_vel_count=18`,
and `total_fleetqox_router_service_frames=144`. `obstacle_field_recovery_claim=false`
remains explicitly false for that recovered-success artifact; the positive
obstacle-field claims come from the separate planner-level static-map repair,
full-stack retry-after-clear, and same-goal external-repair artifacts above.
The ROS CLI message matrix covers
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

The two-container `rclcpp` artifact also reports `status=ok`: nested
`PoseStamped` and a 64-element `nav_msgs/Path` request/reply cross the router
in both directions; C++ `SetBool` and `nav_msgs/GetPlan` clients receive the
C++ server responses. GetPlan validates nested start/goal/tolerance request
fields and returns a 512-pose Path.
Every Path pose validates nested frame IDs, signed seconds, nanoseconds,
position, and orientation before the server mutates and returns it. The router
records all four application topics, reliable ACK/NACK traffic, service
request/response, and zero invalid frames. Publisher/subscription network-flow
queries report UDP/IPv4 on the configured local port, and both request and
response callbacks are observed.

The cross-language follow-on artifact passes `5/5` independent Docker/netem
runs and `10/10` direction rows: C++ server/Python client and Python
server/C++ client each exchange the same 64-pose Path, PoseStamped, SetBool,
and 512-pose GetPlan contract through a fresh FleetRMW router. The serialized
GetPlan response is 73,181 bytes in every direction row, exceeding the
65,507-byte UDP datagram limit and forcing FleetRMW fragmentation/reassembly.
All endpoint processes and routers
exit cleanly, all ten rows validate the complete nested sequence, netem is
applied to every endpoint, and every router reports zero invalid frames. The
service leg uses the middleware default of five request repairs at 100 ms and
does not set either retry environment variable. `rmw_send_request` performs
the initial send and returns while a background worker owns the bounded retry
window. Trace evidence shows requests arriving before the reciprocal client
graph record being rejected; after convergence a same-sequence repair is
accepted, the matching response cancels remaining work, server deduplication
limits callback execution, and response replay handles later duplicates. This
is a scoped nonblocking discovery-repair result, not crash-persistent
exactly-once service semantics or an exhaustive cross-language ROSIDL corpus.

The generated bounded-shape artifact adds the complementary ROSIDL boundary
and also passes `5/5` runs and `10/10` C++/Python direction rows under netem.
Its FleetShape request fills `string<=32`, `uint8[16]`, `float32[<=128]`,
`geometry_msgs/PoseStamped[<=16]`, and `builtin_interfaces/Duration` fields at
their declared limits. The response validates `uint32[<=64]`, repaired
`PoseStamped[<=16]`, and `string<=64`. Every server checks every request field,
every client checks every response field, and every router reports zero invalid
frames. This closes the scoped bounded-shape gap, not all generated ROSIDL
types.

The bounded service-resource artifact then covers that resource-limit slice
directly. It repeats `5/5` in fresh Docker containers with loopback netem and
forces request queue, response queue, dedupe history, pending-response state,
and response replay limits to four. Every run first injects ten unique requests
into a full queue: eight capacity attempts are rejected across three rounds,
one true duplicate is suppressed, and rejected requests remain eligible for
same-sequence repair. All ten unique requests and ten matching responses are
eventually taken. Request and response queues peak at exactly four, pending
response state peaks at one, replay peaks at four, and six old request,
response, and replay records are evicted per run. This proves bounded in-memory
service state and repair-compatible backpressure, not multi-client fairness,
crash-persistent deduplication, or full exactly-once semantics.

The follow-on service-client isolation artifact also passes `5/5`. It keeps
the global request queue at four but enables a two-entry per-client pending
quota. An eight-request noisy client arrives first; only its first two requests
enter. A two-request quiet client then occupies the two remaining first-wave
slots. Twelve noisy attempts are explicitly deferred over the bounded repair
rounds, global queue rejection remains zero, the global/per-client observed
maxima stay at four/two, first-wave dequeue is exactly
noisy-quiet-noisy-quiet while per-client FIFO is retained, and all eight noisy
plus both quiet requests receive their matching responses. This is bounded
noisy-neighbor isolation and unweighted inter-client round-robin, not
weighted, priority-aware, or globally optimal service scheduling.

The service-repair admission artifact bounds the asynchronous worker itself
and passes `5/5` under loopback netem. Two clients each issue four requests
while the repair pool is capped at four jobs globally and three per client.
Exactly four repair jobs are scheduled, one request is excluded by the
per-client cap, and three are excluded by the global cap. All eight initial
network sends still return success, so overload removes only the optional
background repair guarantee rather than the one-shot request. Destroying both
clients cancels all four admitted jobs and every process exits cleanly. This is
bounded fail-open repair admission, not a guarantee that overload-rejected
requests survive packet loss.

The priority scheduler artifact passes `5/5` with optional service-wire
priorities 0, 5, and 10; a missing field remains backward-compatible priority
zero. Every strict-order phase dequeues sequence 200, 100, then 1. A second
phase uses a 10 ms aging quantum: after 120 ms in the local receive queue, a
priority-zero sequence 2 request is selected before a newly arrived
priority-ten sequence 201 request. Aging uses the server's local enqueue time,
not incomparable monotonic clocks from different robots. This proves strict
priority plus a bounded anti-starvation mechanism. Weighted shares are
evaluated separately below; deadline-aware service scheduling remains outside
this artifact.

The opt-in weighted scheduler artifact separately passes `5/5`. Service frames
carry a bounded client weight with a backward-compatible default of one, and
the server uses smooth weighted round-robin over active client heads while
preserving FIFO within each client. The probe creates each client with a
different configured weight and sends through `rmw_send_request`, rather than
injecting internal frames. With both clients continuously backlogged at
weights 1 and 3, every 40-request measurement window contains exactly 10
low-weight and 30 high-weight dequeues; the low-weight client is served at
least once every four dequeues. Per-client heads are chosen by source sequence,
so the same runs retain FIFO despite reordered netem arrival. This is a
measured 3:1 fairness boundary, not a proof for every workload distribution;
deadline-aware scheduling is evaluated separately below.

The deadline scheduler artifact separately passes `5/5` through
`rmw_send_request`. A FleetQoX request frame carries a relative scheduling
deadline; the server combines it with local enqueue time so robot clock epochs
are never compared. Earliest-deadline-first selects the 20 ms request before an
earlier 200 ms request. A request without a declared deadline receives a
synthetic 100 ms aging deadline and, after waiting 150 ms, is selected before a
new 20 ms request. Standard bidirectional ROS service QoS compatibility remains
unchanged; heterogeneous per-client scheduling deadlines are explicitly a
FleetQoX extension.

The durable service artifact passes `5/5` with distinct server containers.
After the first server executes one request and persists its completed response
through file `fsync`, atomic rename, directory `fsync`, and mode `0600`, the
runner sends SIGKILL and requires exit code 137. A replacement server loads one
record. A fresh client reuses the original fixed endpoint and sequence; the
replacement reports `request_taken=false`, sends no application response, and
replays the durable response successfully through the router under netem.
There are zero replacement application executions across the five runs. This
closes completed-response crash replay only: a crash before persistence,
application side effects without a shared transaction, host power loss, and
full exactly-once semantics remain unclaimed.

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

The allocation artifact verifies a real ROS 2 publisher/subscription
payload-scratch lifecycle. `rmw_init_publisher_allocation` and
`rmw_init_subscription_allocation` reserve type-support-bound 64 KiB vectors;
typed/serialized publish and take validate and reuse them under a per-allocation
mutex. Across `5/5` fresh Docker processes, every run completes eight
publish/take pairs, records eight uses on each handle, keeps capacity unchanged,
reports zero payload-scratch growths, and rejects an uninitialized handle. The
artifact keeps `deep_preallocation=false`: frame encoding, reliability history,
transport queues, and application-message deserialization can still allocate,
so this is not an all-hot-path or zero-copy claim.

The `rmw_take_sequence` artifact passes `5/5` independent Docker processes.
Each run verifies an ordered three-message take, a two-message partial take,
unchanged output sizes when the queue is empty, fail-without-mutation for
undersized capacity, and two simultaneous calls on one subscription that
return internally consecutive ranges covering all twenty queued messages.
The same artifact audits dynamic exports: FleetRMW exposes `283` `rmw_*`
symbols versus `95` in the Fast DDS Jazzy baseline, with an empty missing-symbol
set. This proves the named contract and exported-symbol coverage, not semantic
equivalence of all optional functions.

The publisher all-ACK artifact replaces the former unconditional-success ABI
stub with observable reliable-writer behavior. Two matched subscriptions emit
subscriber-identified ACKs, with the second ACK deliberately delayed by 700 ms.
Across `5/5` processes, the 200 ms call times out after exactly `1/2` ACKs
(measured 200–202 ms), the following completion call succeeds at `2/2`, an
empty ledger and a fully acknowledged ledger both satisfy a zero timeout, and
a null publisher is rejected. The v2 contract then publishes a later write
while a wait is in progress: the original snapshot completes in `701–707 ms`,
the later write remains unacknowledged at that instant, and a subsequent wait
completes it. Two simultaneous finite/infinite waiters both complete on one
publisher; destroying a delayed reader releases its obligation in `156–161 ms`;
BEST_EFFORT returns immediately; and a foreign implementation handle
fails closed. This proves FleetRMW's public matched-endpoint snapshot and
thread-safety contract; it is not DDS wire or full writer-history/resource
equivalence.

The QoS event artifact verifies event-object ABI compatibility plus scoped
deadline event production. Publisher/subscription deadline event objects
initialize/finalize successfully, support checks report known event types,
callback setters return OK, and a publish/receive gap beyond the configured
deadline produces offered/requested deadline-missed status. A timer also
produces idle deadline misses after the first publish/receive, before any next
sample is sent. `rmw_take_event` returns `taken=true` with positive
total/change counts, then clears the change count on the next read; callbacks
also receive the pending event count. `rmw_wait` marks those unread deadline
statuses ready before take and clears readiness after take. This deadline
event object/waitable slice now passes `5/5` repeated Docker runs. The aggregate
waitability matrix then runs seven production probes per round and covers all
eleven non-invalid Jazzy `rmw_event_type_t` values: offered/requested deadline,
matched, incompatible QoS, incompatible type, liveliness, and message-lost.
Across `5/5` rounds (`35/35` component executions), every unread status becomes
ready through `rmw_wait`, is consumed through `rmw_take_event`, and the probes'
initial/cleared controls stay not-ready. This closes the Jazzy event waitability
claim; it does not broaden each event family's separate DDS-semantic or remote
production boundary.

The base QoS artifact is now schema v2 and also exercises
`rmw_qos_profile_check_compatible`. It passes compatible profiles, aggregates
simultaneous reliability and durability errors into the reason buffer, rejects
missing or slower offered deadlines, rejects automatic/manual liveliness and
too-slow offered lease duration, and returns WARNING when a requested policy
depends on an unresolved publisher setting. This is profile-checking evidence;
the local/remote event-production scope below remains separate.

Endpoint creation now delegates BEST_AVAILABLE resolution to the Jazzy
`rmw_dds_common` algorithms using FleetRMW graph queries. A `5/5` Docker
artifact verifies a BEST publisher selects MANUAL_BY_TOPIC with a `200 ms`
lease from an existing manual subscription, a BEST subscription selects
AUTOMATIC with a `300 ms` lease from an automatic publisher, zero-endpoint
creation selects AUTOMATIC/default lease, and a mixed automatic/manual pair
selects AUTOMATIC with the maximum `500 ms` offered lease. Actual QoS getters
return the selected values, and the result remains frozen after endpoint churn
as required by the create-time contract.

The matched-event artifact verifies local compatible endpoint matching.
Publisher `RMW_EVENT_PUBLICATION_MATCHED` and subscription
`RMW_EVENT_SUBSCRIPTION_MATCHED` objects initialize/finalize successfully,
callbacks fire on local same-process endpoint create/destroy, `rmw_wait` marks
the unread matched status ready, `rmw_take_event` reports connect
`current_count_change=+1`, disconnect `current_count_change=-1`, and a second
take clears the change counts. This artifact is scoped to local endpoint
matching; remote behavior is covered by the separate artifact below. Same-topic
endpoints with incompatible type, reliability, durability, or deadline are not
counted as matched. The matched-event Docker artifact now passes this local
create/destroy sequence across `5/5` repeated runs.

The incompatible-QoS artifact verifies a second non-deadline event subset:
local same-process reliability, durability, and deadline mismatch. A best-effort
publisher discovered by a reliable subscription produces offered/requested
statuses with `last_policy_kind=RMW_QOS_POLICY_RELIABILITY`; a volatile
publisher discovered by a transient-local subscription produces the same event
families with `last_policy_kind=RMW_QOS_POLICY_DURABILITY`; and an offered
deadline longer than the requested deadline produces
`last_policy_kind=RMW_QOS_POLICY_DEADLINE`. A separate liveliness artifact
checks both offered and requested event directions for an AUTOMATIC publisher
against a MANUAL_BY_TOPIC subscription, a slower offered lease, and a missing
offered lease; each reports `RMW_QOS_POLICY_LIVELINESS`, remains unmatched, and
clears readiness after take. A faster manual offered lease is the positive
matched/no-event control. Docker repeats all seven scenarios `5/5`. These
artifacts verify callback delivery,
`rmw_wait` readiness, `rmw_take_event` with `total_count_change=1`, and that
incompatible endpoints are not counted as matched. This local artifact remains
scoped to four policy families and is not a full DDS QoS compatibility
matrix. The reliability/durability
incompatible-QoS Docker artifact now passes `5/5` repeated runs.

The incompatible-type artifact verifies local same-topic type mismatch
production. Publisher and subscription `RMW_EVENT_*_INCOMPATIBLE_TYPE` objects
initialize/finalize successfully, callbacks fire, `rmw_wait` marks unread
statuses ready, and `rmw_take_event` reports `total_count_change=1` before
clearing readiness. This local artifact remains scoped to exact type-name
mismatch and is not a full ROS/DDS type compatibility claim.
The incompatible-type Docker artifact now passes `5/5` repeated runs.

The message-lost artifact verifies local queue overwrite plus real
best-effort transport gaps. With `KEEP_LAST` depth `1`, two frames leave only
the second payload and produce one event. In a separate four-frame
`BEST_EFFORT` stream, the transport test hook drops source sequence `3`; the
reader receives three frames and produces exactly one event/callback after the
reorder grace interval. A mixed reliable/best-effort control drops sequence
`3`, repairs it, delivers all four payloads to both readers, and leaves the
best-effort observer's loss status at zero. All statuses are checked through
callback, `rmw_wait`, and `rmw_take_event`. A fourth reliable control uses
`KEEP_LAST depth=1`, evicts dropped sequence `3` before its NACK, emits exactly
one subscriber-targeted unrecoverable-loss notice, retains three payloads, and
reports one loss event. The local Docker artifact passes `5/5`. A separate
two-container probe places `delay 8ms 2ms` netem on both UDP peers, drops reliable
source sequence `3` after it has left writer `KEEP_LAST depth=1` history, and
passes `20/20`. Each publisher sends two notices in response to immediate and
idle NACKs; the targeted subscriber receives both but idempotently reports one
lost sample, one callback event, one wait-ready event, and payloads `1,2,4`.
A second artifact retains sequence `3` in writer depth-`16` history and exercises
three policy-terminal paths under the same two-container netem: global repair
budget `0`, per-sequence max-attempt `1` after deliberately losing the first
retransmission, and strict admission with no matching plan. Each path passes
`5/5` (`15/15` total), produces its distinct terminal counter, reports exactly
one lost sample/event, and exits both processes cleanly. Budget and admission
also receive duplicate notices without double-counting. Full DDS
message-lost/resource-limit semantics remain outside these scoped claims.

The liveliness artifact verifies the local finite-lease subset.
`RMW_EVENT_LIVELINESS_CHANGED` first reports a compatible publisher as alive;
after the lease expires, `RMW_EVENT_LIVELINESS_LOST` reports one lost event and
the subscription reports alive-to-not-alive transition; a later
`rmw_publisher_assert_liveliness` reasserts the publisher as alive. This is
the manual-assertion timeout/reassert boundary and passes `5/5` repeated runs.
A separate AUTOMATIC-policy artifact keeps an otherwise idle local publisher
alive for `120 ms` under a `20 ms` lease (six lease intervals): it observes the
initial alive transition but no lost wait readiness, no not-alive transition,
no lost callback, and zero lost total across `5/5` runs with clean teardown.
A two-container MANUAL_BY_TOPIC artifact then separates the `100 ms` graph
renewal interval from the `200 ms` liveliness lease under UDP/netem. Periodic
graph `add` renewal keeps the publisher matched but no longer masks two idle
liveliness expiries. Five explicit assertions and five serialized publishes
produce ten wire `liveliness_assert` frames and reassert the remote publisher
after each idle loss path; the observer records exactly two expiries and two
not-alive-to-alive reassertions. All `5/5` runs take the published payload and
tear both processes down cleanly. A second multi-endpoint artifact passes `5/5`
with two simultaneous manual publishers: repeated keepalive of one endpoint
does not mask two expiry cycles of the other, alive and not-alive removal each
produce the correct aggregate delta, and a third endpoint can be created and
removed after the pair returns to zero. Liveliness expiry remains distinct from
matching throughout. Local liveliness kind and lease incompatibility events are
covered by the separate QoS artifact above. These scoped results do not yet
claim fleet-scale churn or broader unresolved/system-default policy semantics.

The remote-event artifact exercises the production UDP graph-advertisement
receive path between two containers. Eleven advertised endpoints jointly cover
publication/subscription matched connect/disconnect, offered/requested
reliability/durability/deadline-incompatible QoS, publisher/subscription exact type mismatch, and
finite-liveliness changed state. `add` renewals extend a per-endpoint lease
without duplicating incompatible-event totals. Across `5/5` runs, three cases
remove all eleven endpoints explicitly and two terminate the advertiser without
cleanup; the latter expire all eleven endpoints after the graph lease. Every run
ends with matched and liveliness current counts at zero, one QoS/type event per
incompatible endpoint, callback delivery, at least one full renewal round, and
an empty remote event registry. Each run also observes automatic graph-guard
wakeup on remote add and disconnect and suppresses guard wakeup across an
unchanged renewal interval; explicit-remove runs receive `66` advertisements
(`11` add, `44` renewal, `11` remove), while crash runs receive `55` before
all `11` leases expire. This closes the scoped remote matched/QoS/type and
graph-lifecycle liveliness claim. The aggregate artifact below adds one
repeated remote path for every Jazzy event type, without implying the full DDS
compatibility matrix or every vendor/resource-limit semantic.

The content-filter artifact verifies set/get ABI compatibility plus scoped
data-plane enforcement. A subscription stores a filter expression plus
parameters, reports CFT-enabled after set, returns the same
expression/parameters through `rmw_subscription_get_content_filter`, drops two
non-matching raw key-value payloads while delivering only the matching payload
for `robot_id = %0 AND sequence > %1`, and repeats enforcement against a
`std_msgs/String`-style serialized text payload with `!=`, `>=`, and `<=`
predicates. It then disables the filter with an empty expression and verifies
that an otherwise non-matching payload bypasses filtering without increasing
filter counters. The artifact sets `content_filter_enforcement=true` with raw,
std_msgs-specific, and disabled-bypass counters; the full DDS SQL-like
expression dialect remains unclaimed. The content-filter Docker artifact now
passes this set/get, reconfigure, enforcement, and disable sequence across
`5/5` repeated runs.

A second `5/5` artifact exercises the SQL-like parser and real data plane with
operator precedence and parentheses across `AND`, `OR`, and `NOT`, plus
parameterized `LIKE`, `BETWEEN`, `IN`/`NOT IN`, `IS NULL`, and `IS NOT NULL`.
Each run evaluates eleven payloads, delivers four, and drops seven exactly;
missing fields under `NOT` remain SQL `unknown` and cannot fail open. A malformed
predicate and an out-of-range parameter reference both return
`RMW_RET_INVALID_ARGUMENT`, leave the active filter intact, and the subsequent
empty-expression disable succeeds. This remains a scoped text-field subset,
not the full DDS SQL dialect.

A third `5/5` artifact executes filters against real typed ROSIDL messages.
`geometry_msgs/Twist` through introspection C++ and `geometry_msgs/Pose` through
introspection C each evaluate four nested-field samples and deliver exactly two.
The C++ `std_msgs/Float64MultiArray` case additionally resolves `data._length`,
`data[1]`, `layout.dim._length`, and `layout.dim[0].label`, delivering one of
four samples. Every run records exactly twelve successful typed reflections,
plus a thirteenth evaluation where a serialized message with an invalid
member-count is dropped without being counted as a successful reflection.
Reflection parses the FleetRMW serialized payload directly rather than
constructing an application message; arbitrary DDS SQL functions and
vendor-specific semantics remain unclaimed.

The security-options artifact verifies the `rmw_init_options` lifecycle for
default security options, custom enclave configuration, deep-copy behavior,
context initialization copy, shutdown, and fini across `5/5` repeated Docker
runs. It is an ABI/lifecycle repeat boundary, not SROS2 policy enforcement or
keystore validation. `results_rmw_socket/docker_security_policy_probe_summary.json`
adds a separate opt-in FleetQoX authorization slice: with
`FLEETQOX_RMW_SECURITY_POLICY=publish_allow=/fleetqox/security_allowed;publish_deny=/fleetqox/security_denied`,
allowed publishes are delivered and denied publishes return an error without
queueing data across `5/5` repeated Docker runs. That artifact sets
`fleetqox_security_policy_enforcement_claim=true` and
`security_policy_repeated_enforcement_claim=true`, but still sets
`sros2_policy_enforcement_claim=false` and
`production_security_hardening_claim=false`; the scope is explicitly
`fleetqox_publish_allow_deny_env_policy`.

`results_rmw_socket/docker_sros2_permissions_probe_summary.json` closes the
next scoped boundary. It uses the installed `ros2 security` CLI to generate a
keystore, enclave, `permissions.xml`, and signed `permissions.p7s` for domain
`7`; verifies the S/MIME payload against the permissions CA; validates the
verified payload with the official SROS2 DDS permissions XSD. FleetRMW then
loads `permissions.p7s` directly, verifies its S/MIME signature and chain
against the configured permissions CA at runtime, selects the grant from the
configured enclave, checks validity and domain constraints, maps ROS topics to
`rt/...` DDS topic expressions, applies ordered publish and subscribe `*`/`?`
allow/deny wildcard rules, and falls back to the grant default. Across `5/5`
runs the allowed publish/subscribe path is delivered, publish explicit/default
denies return errors, and subscribe explicit/default denies accept the publish
but keep the local queue empty. A malformed-XML control and a byte-tampered signed-policy
control both deny every publish fail-closed. The artifact sets
`sros2_permissions_xml_publish_enforcement_claim=true`,
`sros2_permissions_xml_subscribe_enforcement_claim=true`,
`sros2_permissions_xml_pubsub_enforcement_claim=true`,
`sros2_permissions_xml_repeated_enforcement_claim=true`, and
`runtime_sros2_permissions_signature_validation_claim=true`,
`malformed_permissions_fail_closed_claim=true`, and
`tampered_signed_permissions_fail_closed_claim=true`. It keeps
`sros2_service_request_reply_authorization_claim=true` after additionally
exercising actual SetBool `rmw_send_request`, request receive,
`rmw_send_response`, and response receive paths. The generated SROS2
`request`/`reply` rules map to `rq...Request` and `rr...Reply`; allowed traffic
round-trips, explicit/default request denies return errors, and a reply deny
blocks server request-subscribe plus response-publish. The same generated
policy now sets `sros2_action_authorization_claim=true` and
`sros2_action_repeated_authorization_claim=true`: a real rclpy
`tf2_msgs/action/LookupTransform` goal completes with result and feedback,
`call=DENY` fails closed in the request-publish path, and `execute=DENY` drops
the request at server subscribe before callback dispatch across `5/5` runs.
The runner additionally signs and validates a scoped Governance document,
verifies `governance.p7s` inside FleetRMW, and applies domain/topic read-write
access-control switches across `5/5` runs. The stock SROS2 Governance profile
requiring ENCRYPT/SIGN and a byte-tampered signed Governance artifact are both
denied fail-closed. Thus `governance_xml_enforcement_claim=true`, while
`governance_transport_security_claim=false`; the broad
`sros2_policy_enforcement_claim=false` remains. Local identity validation now
checks the enclave certificate chain against the identity CA, private-key
correspondence, and certificate-CN/enclave equality before `rmw_init` across
`5/5`; tampered-certificate, wrong-key, and wrong-enclave controls fail closed.
The UDP data path additionally passes an AES-256-GCM PSK envelope `5/5`; a
tag/ciphertext tamper is rejected before queue delivery, and strict mode
without a configured key refuses endpoint creation. This sets
`udp_aead_authenticated_encryption_claim=true`. A separate two-process Docker
probe signs the encrypted envelope with each peer's SROS2 private key and
validates the remote X.509 chain, identity allowlist, and signature before
decryption across `5/5`. Unauthorized identity, modified signature, and
untrusted-CA and CRL-revoked-certificate controls fail closed, so
`sros2_peer_identity_authentication_claim=true`; however,
`dds_security_interoperability_claim=false`, while HKDF-SHA256 derivation,
reuse, and forced rotation establish a scoped authenticated PSK session, so
`session_key_establishment_claim=true` and
`certificate_revocation_claim=true`. This remains a FleetRMW PSK envelope
rather than forward-secret DDS-Security key exchange or a complete production
PKI lifecycle; `forward_secrecy_claim=false`.

The first QUIC/TLS artifact is a dependency and handshake gate, not an RMW
backend claim. `results_rmw_socket/docker_quic_tls_probe_summary.json` uses
ngtcp2/GnuTLS `gtlsserver` and `gtlsclient` in Docker, verifies QUIC v1,
TLS handshake completion, ALPN `h3`, qlog emission, and a byte-for-byte
payload download. It sets `rmw_integrated_backend=false` so the project cannot
mistake a real QUIC/TLS smoke for an integrated FleetRMW publish/take path.
The follow-on artifact
`results_rmw_socket/docker_quic_fleet_frame_probe_summary.json` serves a real
`fleetrmw.data_frame.v1` over that same QUIC/TLS/H3 path and requires the
downloaded bytes to decode with the C++ `fleetrmw_frame_probe`.
`results_rmw_socket/docker_quic_netem_frame_probe_summary.json` repeats the
FleetRMW-frame transfer across two Docker containers after applying verified
`tc netem` to the client interface. The artifact also carries qdisc
before/after counters plus parsed ngtcp2 path telemetry, and the gate requires
QUIC v1 negotiation, sent/received packet logs, and at least one RTT sample.
`results_rmw_socket/docker_quic_gateway_publish_probe_summary.json` verifies
the first RMW publish-side QUIC gateway slice: `rmw_publish` emits one encoded
FleetRMW frame through ngtcp2/GnuTLS `gtlsclient --data`, `gtlsserver` receives
matching `content-length` and body bytes, ALPN is `h3`, and qlog files are
emitted. The artifact sets `production_quic_backend=false` and
`full_bidirectional_quic_backend=false`.
`results_rmw_socket/docker_quic_gateway_take_probe_summary.json` verifies the
first QUIC gateway take/download slice below `rmw_take`: the shared transport
helper uses ngtcp2/GnuTLS `gtlsclient --download` to fetch a hosted
`fleetrmw.data_frame.v1` over QUIC/TLS/H3 GET, checks byte-for-byte payload
integrity, decodes the frame in C++, and records one received frame plus byte
counter. It sets `rmw_take_path_integrated=false`,
`production_quic_backend=false`, and `full_bidirectional_quic_backend=false`.
`results_rmw_socket/docker_quic_gateway_rmw_take_probe_summary.json` verifies
the follow-on opt-in RMW take smoke: with
`FLEETQOX_RMW_QUIC_GATEWAY_TAKE_ON_DEMAND=1`, an empty
`rmw_take_serialized_message` call downloads a hosted FleetRMW data frame over
the same ngtcp2/GnuTLS QUIC/TLS/H3 GET path, enqueues it for the matching
subscription, and returns the serialized payload. It sets
`rmw_take_path_integrated=true` for this on-demand subprocess-backed smoke,
while still setting `production_quic_backend=false` and
`full_bidirectional_quic_backend=false`.
`results_rmw_socket/docker_quic_gateway_rmw_take_session_reuse_probe_summary.json`
extends the same opt-in RMW take smoke across five GET downloads that share
ngtcp2/GnuTLS session, transport-parameter, and token files. It verifies five
successful `rmw_take_serialized_message` downloads, five client/server
handshakes, ten qlog files, and persisted session artifacts, while leaving
`zero_rtt_claim=false`, `production_quic_backend=false`, and
`full_bidirectional_quic_backend=false`. The runner now also parses
ngtcp2/GnuTLS log telemetry into separate fields for file-read/missing counts,
`session_resumption_attempted_observed`, `zero_rtt_packet_observed`,
`zero_rtt_accepted_observed`, and `session_resumption_observed`, so packet-level
0-RTT attempts cannot be mistaken for accepted 0-RTT.
`results_rmw_socket/docker_quic_gateway_bidirectional_probe_summary.json`
adds the first combined publish+take gateway boundary: one ngtcp2/GnuTLS
`gtlsserver` accepts the RMW publish POST, then serves the opt-in RMW take GET,
with both client invocations sharing session, transport-parameter, and token
files across `5/5` repeated publish+take pairs. It verifies publish and take
integration, payload integrity, `5` uploaded frames, `5` downloaded frames,
ten client/server handshakes, twenty qlog files, and persisted shared session
artifacts. The artifact sets `quic_gateway_bidirectional_boundary_claim=true`
and `quic_gateway_bidirectional_repeated_claim=true`, while still keeping
`zero_rtt_claim=false`, `production_quic_backend=false`, and
`full_bidirectional_quic_backend=false`. Bidirectional artifacts expose
`zero_rtt_packet_observed` separately from `zero_rtt_accepted_observed`; only the
latter can support a future 0-RTT claim.
`results_rmw_socket/docker_quic_inprocess_rmw_bidirectional_probe_summary.json`
closes the subprocess boundary for the integrated client path. It links
ngtcp2 0.12.1, GnuTLS 3.8.3, and nghttp3 0.8.0 into the RMW transport and runs
under Docker loopback netem (`5 ms`, `1%` loss). 128 real `rmw_publish` H3
POSTs and one on-demand `rmw_take_serialized_message` H3 GET complete through
one QUIC v1 connection, one certificate-verified TLS handshake, 129 reliable
bidirectional streams, 128 same-connection reuses, and zero reconnects. The
v3 artifact launches the final `rmw_publish` and
`rmw_take_serialized_message` from independent threads. With a bounded
rendezvous window they submit POST and GET before driving either response and
record one concurrent RMW API pair, a maximum of two simultaneous API calls,
two simultaneous H3 streams, and no reconnect. A second positive client
verifies the explicit paired transport API. Across both positive clients the
server records 129 POSTs, two GETs, and two completed handshakes. The three
clients export three non-empty native qlogs, while the server exports three
more; the artifact records all six files and their byte totals. The
third client uses an unrelated CA and fails closed with TLS alert 42. This
supports the integrated qlog,
same-connection bidirectional, scoped concurrent full-duplex, and
multi-threaded RMW publish/take operation claims. It does not support
production readiness: unmatched calls fall back to single-stream execution,
and accepted 0-RTT/resumption is not claimed.
`results_rmw_socket/docker_quic_stateful_gateway_probe_summary.json` closes the
previously missing stateful gateway-service slice. A Python aioquic QUIC v1/H3
service validates complete `FRMW1`/`fleetrmw.data_frame.v1` bodies before
admission, retains a bounded history per domain/topic, deduplicates publisher
sequence keys, and advances independent per-consumer cursors. Across `5/5`
two-container Docker/netem runs it processes exactly eleven requests per run:
three unique POSTs, one duplicate POST, one invalid POST rejected with HTTP
400, and six GETs replaying sequences `1..3` to each of two consumers. Each
run negotiates three server H3 sessions; the alpha session reuses one verified
TLS connection across seven streams and beta across three streams. Client and
server qlogs are non-empty and teardown is clean. This is a scoped stateful
single-process gateway proof, not clustered durability, fleet admission/QoE
integration, accepted 0-RTT/resumption, or production QUIC readiness.
`results_rmw_socket/docker_quic_stateful_rmw_probe_summary.json` then exercises
the same service through public RMW APIs in separate endpoint processes. Each
of `5/5` three-container netem runs publishes three introspection-C
`std_msgs/String` samples with `rmw_publish`, then takes the same three payloads
in order through `rmw_take` in another container. The gateway records exactly
three accepted POSTs and three dequeued GETs, with no duplicate, invalid,
empty, eviction, or consumer-overrun event. Publisher and subscriber each use
one verified-TLS connection, one H3 handshake, three streams, two session
reuses, and one native client qlog; the server negotiates both sessions and
exports qlogs. This closes the stateful inter-process public-RMW integration
claim while retaining `production_quic_backend_claim=false`.
`results_rmw_socket/docker_quic_mtls_probe_summary.json` hardens that gateway
boundary with mutual TLS client authentication. Across `5/5` six-container
Docker/netem runs, the in-process GnuTLS client presents a certificate and key
signed by the configured client CA and successfully writes exactly one frame.
Two independent negative clients complete enough of the client-side QUIC/TLS
path to receive a server authentication alert, but a client with no
certificate and a client signed by an unrelated CA both report failed sends.
The gateway records four connections and H3 negotiations, two authenticated
client certificates, one missing-certificate rejection, one untrusted-chain
rejection, one revoked-certificate rejection, one publisher-identity
authorization rejection, and exactly one
admitted POST/frame. The second CA-trusted certificate deliberately presents a
publisher URI SAN whose SPIFFE-style suffix differs from the frame's
`publisher_id`; opt-in identity binding rejects it with HTTP/3 403. Thus none
of the three rejected identities mutates topic history. The revoked certificate
is signed by the trusted CA and carries the correct publisher URI SAN; its
serial appears in a current CRL whose issuer and
signature are checked against the client CA before the service starts. All six
containers have netem configured and emit non-empty qlogs.
The apt aioquic 0.9.25 server does not expose native client-certificate
verification through its public server configuration, and inspection of
upstream 1.3.0 still finds the CertificateRequest switch private. The adapter
is now isolated in `fleetqox/aioquic_mtls_adapter.py`; the Dockerfile pins
`python3-aioquic=0.9.25-3build2`, runtime requires exact version `0.9.25`, and
three private method signatures are fingerprinted before service startup.
Version/signature drift fails closed. The adapter also verifies the TLS
CertificateVerify signature before chain/revocation acceptance and before
setting the authenticated flag. The refreshed `5/5` artifact records five
successful adapter installs per run and the exact compatibility report. This is
evidence for scoped mutual authentication and unauthenticated state isolation,
not production PKI, broader fleet identity policy, online revocation/rotation,
or production QUIC readiness.
`results_rmw_socket/docker_ngtcp2_public_mtls_server_summary.json` removes the
private-hook dependency from a standalone transport-server edge. It rebuilds
the official ngtcp2 `v0.12.1` GnuTLS server at commit
`a4ba3f20d70d4a4d79674cee1093c55b4c1d78ed`, using public GnuTLS APIs for
client-CA trust, CRL revocation, client-auth EKU, exact URI SAN, and disabled
early data. Across `5/5` Docker/netem rounds, the valid client submits and
receives six HTTP/3 requests on one session. Missing-certificate,
unrelated-CA, wrong-URI, and revoked controls each receive a QUIC/TLS
`CRYPTO_ERROR` and no HTTP response. This establishes the public-API mTLS
transport-server claim; the artifact deliberately keeps
`stateful_gateway_backend_integrated=false` and
`production_quic_backend_claim=false`.
`results_rmw_socket/docker_ngtcp2_public_stateful_gateway_summary.json` closes
that artifact's next scoped boundary. The patched public ngtcp2 edge buffers a
bounded H3 request and forwards method, path, body, and the GnuTLS-verified
URI-SAN identity over a length-prefixed Unix socket to the shared
`FleetQoxGatewayState` engine. Across `5/5` Docker/netem rounds, every run
returns 12 backend responses over four verified mTLS connections: three unique
POSTs plus one duplicate, six ordered GETs for two independent consumer
cursors, one invalid-frame HTTP 400, and one CA-valid but publisher-mismatched
HTTP 403. The 403 control leaves retained state at exactly three frames.
Alpha reuses one QUIC/H3 connection for seven streams and beta reuses one for
three; both endpoints emit four non-empty qlogs per run. The tested server
runtime uses neither aioquic nor a private TLS hook.
`results_rmw_socket/docker_ngtcp2_public_path_admission_summary.json` closes
the next public path-metric boundary. The edge reads initialized smoothed RTT,
RTT variation, congestion window, bytes in flight, PTO count, and raw
per-stream packet-loss count from public ngtcp2 APIs, then sends them through
backend protocol v2. Across `5/5` matched Docker/netem rounds, the backend with
path observations disabled rejects the score-zero frame with HTTP 429. The
enabled backend records source `ngtcp2_public_api`, makes no external
observation-API request, admits the identical policy/frame with HTTP 200, and
serves it on take. The raw stream-loss count is retained as telemetry and is
not mislabeled as a loss ratio because ngtcp2 exposes no corresponding
sent-packet denominator. `production_quic_backend_claim=false` remains because
the remaining broad multi-publisher identity selection, online rotation,
clustered state, and production operations are not closed.
`results_rmw_socket/docker_ngtcp2_public_async_backend_summary.json` closes
the synchronous-dispatch boundary without adding test delays to the edge or
state engine. The public ngtcp2 server now copies each bounded request into a
configurable worker pool and bounded queue, performs Unix-socket I/O outside
the libev thread, and submits the H3 response only after `ev_async` returns the
completion to that thread. Across `5/5` Docker/netem rounds, a test-only
concurrent proxy delays one request before forwarding it to the real
`FleetQoxGatewayState`; an independent fast request receives HTTP 204 while the
slow request is still in flight. A separate `1 worker + queue 1` phase returns
HTTP 503 for the third concurrent request while the first two later receive
204. A short server idle timeout then removes a slow request's handler before
its backend result returns; generation fencing drops exactly one stale
completion and a subsequent connection still receives 204. Every phase uses
verified mTLS, non-empty qlogs, netem at both endpoints, bounded proxy
concurrency, clean backend/proxy/server teardown, and zero completion failures.
This proves bounded off-thread dispatch and event-loop survival, not clustered
state, online PKI rotation, or production operations;
`production_quic_backend_claim=false` remains explicit.
`results_rmw_socket/docker_ngtcp2_public_identity_fairness_summary.json`
closes the next scoped multi-publisher queue boundary. The edge derives a
bounded publisher identity independently for every verified connection from
the peer certificate URI SAN, rejects a CA-trusted out-of-prefix URI before
backend access, and schedules bounded per-identity pending queues in
round-robin order. Across `5/5` Docker/netem rounds, publisher A fills its
two-request pending allowance and receives HTTP 429 for the next request;
publisher B is still admitted and its request runs before A's remaining
queued request. All four accepted requests reach the real state engine through
the test-only delay proxy, six client qlogs are non-empty, and backend,
proxy, and server teardown are clean. This proves certificate-derived
multi-publisher selection, per-identity pending limits, and round-robin
pending-queue fairness. It does not prove active-worker reservation, weighted
QoS-aware traffic classes, cluster-wide fairness, online certificate
rotation/revocation refresh, or production operations, so
`production_quic_backend_claim=false` remains explicit.
`results_rmw_socket/docker_ngtcp2_public_active_worker_isolation_summary.json`
closes the active-worker portion of that boundary. The edge now tracks active
backend calls separately from pending requests and exposes a bounded
`FLEETQOX_STATE_BACKEND_PER_IDENTITY_ACTIVE_LIMIT`. Identities at their active
limit leave queued work non-runnable until a worker releases the identity,
while other ready identities can use free workers. Across `5/5` matched
Docker/netem rounds with two workers, limit `1` lets publisher B complete in
roughly `120-135 ms` while both delayed publisher-A clients remain open and A
never exceeds one active worker. The limit-`2` control records A at two active
workers and makes B wait roughly `1.3 s`. All three requests in both phases
reach the real state engine, all qlogs are non-empty, and teardown is clean.
The default active limit equals the configured worker count, preserving the
existing work-conserving default unless operators opt into isolation. Weighted
QoS-aware scheduling, cluster-wide coordination, and production operations
remain outside the claim; `production_quic_backend_claim=false` remains
explicit.
`results_rmw_socket/docker_ngtcp2_public_online_crl_refresh_summary.json`
closes online client-CRL refresh for new connections. The opt-in GnuTLS verify
path clears and reloads the configured CRL through public APIs before each peer
verification. Across `5/5` Docker/netem rounds, the same server PID/start time
first accepts the stateful client with HTTP 204, rejects a new connection with
QUIC/TLS `CRYPTO_ERROR` after an atomic CRL replacement revokes that client's
serial, and accepts a new connection again after the original CRL is restored.
A malformed CRL replacement is separately rejected fail-closed. The real state
backend and test-only proxy see exactly the two valid GETs, four client qlogs
are non-empty, and teardown is clean. The artifact does not evict or reverify
established sessions and does not rotate the client CA or server certificate;
those boundaries and `production_quic_backend_claim=false` remain explicit.
`results_rmw_socket/docker_quic_admission_probe_summary.json` adds scoped
fleet-level admission to the same stateful service. A fail-closed JSON policy
maps three domain/topic streams to control, bulk, and state classes, applies
publisher allowlists and per-stream frame quotas, and shares a three-frame
fleet quota across all streams with a one-second monotonic replenishment epoch.
Each of `5/5` two-container Docker/netem runs
admits and replays exactly two control frames and one bulk frame. It then
observes distinct HTTP/3 rejections for bulk stream-quota exhaustion (429),
shared fleet-quota exhaustion on the state stream (429), and a control frame
from a non-allowlisted publisher (403). The state snapshot remains exactly
three retained frames in two topics, while admission telemetry records one of
each rejection reason; rejected streams cannot create empty topic state. Four
verified-TLS H3 client roles first open the rejection/acceptance paths. After
the epoch rolls over, the previously fleet-quota-rejected state frame is
admitted and replayed, producing four accepted/taken frames over eleven request
streams and five connections total; cumulative admission remains four even if
the current-epoch counter resets again before shutdown. Both containers export
non-empty qlogs. This proves deterministic gateway admission, replenishment,
and state isolation, not dynamic deadline/QoE prediction or multi-instance
fleet capacity coordination.
`results_rmw_socket/docker_quic_qox_repair_probe_summary.json` moves beyond
static quota inputs while retaining a narrow claim boundary. The C++ data-frame
codec adds optional traffic class, deadline, age, QoE debt, task criticality,
repair intent, and prior-attempt fields without changing the v1 schema or
breaking legacy frames. The gateway validates those ranges and computes
`0.45*criticality + 0.35*qoe_debt + 0.20*deadline_urgency`. In every one of
`5/5` two-container Docker/netem runs, a score-zero control frame is rejected
with HTTP/3 429 and a score-0.925 frame is admitted. A subsequent high-debt,
high-criticality repair exceeds the normal one-frame stream/fleet quota but is
admitted by `FleetRepairScheduler` over the configured `private_5g` path. A
second repair is evaluated and deferred because the first allocation consumed
the shared 1024-byte repair budget. The service records one repair and one
defer decision, retains/replays exactly the high-score and repaired frames,
and emits client/server qlogs. Non-2xx boundaries deliberately reconnect, so
the six requests use three verified H3 connections with three measured reuses.
This proves frame-metadata admission and live gateway/scheduler plumbing; the
gateway is not yet deriving debt/path observations from closed-loop telemetry
or jointly optimizing a batch of simultaneous repair demands.
`results_rmw_socket/docker_quic_feedback_batch_probe_summary.json` closes the
next scoped feedback/batch slice. In each of `5/5` two-container Docker/netem
runs, a versioned observation POST supplies bounded debt, loss, RTT, and jitter
for one publisher and remains active for a configured 5000 ms TTL. The gateway
combines that observation with frame criticality and deadline urgency, sorts a
two-frame batch by effective score, and admits the observed frame even though
it appears second in the request and only one normal slot exists. A second
two-frame batch sorts competing repair demands before admission: the urgent
`repair-high` frame consumes 622 of 1024 shared repair bytes on `private_5g`,
while `repair-low` is evaluated afterward and deferred. Exactly the observed
normal frame and urgent repair replay over two reused GET streams. Across five
requests the C++ probe measures three verified H3 connections, five streams,
two connection reuses, qlogs at both endpoints, and clean teardown. The
observation currently enters through the external API; it is not gateway-native
transport telemetry. Batch scheduling is deterministic score ordering followed
by sequential admission, not a globally optimal joint optimizer or
multi-instance capacity protocol.
`results_rmw_socket/docker_quic_native_path_observation_probe_summary.json`
closes the scoped native transport-feedback gap with an explicit contrast. Each
of `5/5` runs starts two fresh mTLS/URI-SAN-bound gateway instances under matched
Docker netem. The baseline receives no observation and rejects a score-0.315
frame at threshold 0.32. The native instance also receives zero observation-API
requests, but an exact-version-gated aioquic recovery adapter samples the
authenticated session's smoothed RTT, RTT-variation estimate, sent-packet count,
and recovery-declared losses before admission. It records the source as
`quic_session_native`, uses the observation exactly once, and admits the same
frame in all five runs. Client and server retain qlog evidence. This does not
turn frame-carried QoE debt into a measured signal: only path metrics are native.
The `measured_jitter_ms` score input is explicitly a QUIC recovery RTT-variance
proxy, not application inter-arrival jitter. aioquic exposes no public stable
path-metrics API, so version/signature drift fails startup and production
support remains false.
`results_rmw_socket/docker_quic_native_qoe_debt_probe_summary.json` adds an
opt-in debt derivation layer on top of those authenticated path samples. Both
sides of each `5/5` contrast use mTLS, URI-SAN publisher binding, native path
observation, matched netem, and a frame whose publisher-provided QoE debt is
exactly zero. With a 0.40 admission threshold, path-only scoring rejects the
frame in all five controls. The derived policy saturates measured loss plus
RTT/deadline and RTT-variation/deadline ratios, EWMA-smooths repeated samples,
records debt provenance as `gateway_derived_path`, and admits the same frame in
all five cases. Native-debt policy startup fails unless native observation,
client authentication, and certificate-to-publisher binding are all enabled.
The derived value and provenance survive durable admission-state export and
restore. This remains an authenticated QUIC path-pressure proxy rather than an
application task result.
`results_rmw_socket/docker_quic_application_outcome_probe_summary.json` closes
the scoped task-result feedback gap. Every one of `5/5` two-container
Docker/netem runs uses real QUIC v1/H3, mutual TLS, URI-SAN publisher binding,
and qlogs at both endpoints. A critical frame is accepted, then a
low-criticality frame is rejected at the 0.45 threshold. Outcome reports use a
versioned schema and must match a recent accepted `(domain, topic, publisher,
sequence)` key. A certificate-authenticated publisher impersonation is rejected
with HTTP 403 before state mutation, an unknown sequence returns 404, and a
non-boolean delivery flag returns 400. A failed task delivery/deadline outcome
for the known frame derives debt 1.0 from bounded delivery, deadline,
latency/deadline, and task pressure, records provenance as `gateway_derived_outcome`, and
makes an exact replay idempotent. The formerly rejected low-criticality frame is
then admitted and both payloads replay in order. Each C++ probe records seven
verified mTLS connections, ten H3 streams, three same-connection reuses, and
four fail-closed reconnects. The task-aware report also proves one failed task
updates task-failure counters exactly once despite replay. This artifact alone
uses bounded in-memory outcome replay keys and does not prove automatic
Nav2/RMF task-result submission or production QUIC support. The separate
concurrency-8 Nav2/RMF artifact proves terminal-result mapping but explicitly
performs no gateway POST. The separate chained `5/5` submission artifact closes
the gateway-ingestion step while retaining the same-live-process claim as false.
`results_rmw_socket/docker_quic_durable_application_outcome_failover_probe_summary.json`
adds the durability boundary. Every one of `5/5` runs starts two sequential
mTLS/URI-SAN-bound gateway instances against a fresh SQLite WAL database under
netem on both client and service containers. Instance A atomically commits a
known frame, its failed application-outcome key, and the post-outcome admission
snapshot. Instance B recovers one frame, one dedup key, one outcome key, and one
admission state; an exact outcome replay is accepted as a duplicate without a
second policy update or durable commit. The restored debt then admits the same
low-criticality frame that would otherwise fail the 0.45 threshold, and both
payloads replay in order. Across the five runs this exercises 20 containers and
10 gateway instances with non-empty qlogs, exact QUIC/H3 accounting, no
persistence errors, and no malformed H3 requests. This proves sequential
active/passive idempotence over one shared SQLite store, not active/active
consensus, distributed replication, automatic task instrumentation, or
production readiness.
`results_rmw_socket/docker_quic_postgresql_application_outcome_failover_probe_summary.json`
repeats the same authenticated outcome boundary against a networked PostgreSQL
16 instance. All `5/5` runs keep the database alive while gateway A commits the
frame, outcome key, and admission snapshot under fence token 1; gateway B then
acquires token 2, recovers all four state dimensions, suppresses the replay,
admits the low-criticality frame, and replays both payloads. PostgreSQL reports
`synchronous_commit=on`; service telemetry removes username/password from the
endpoint; every client/service pair has netem and non-empty qlogs. The maximum
measured replacement cycle is 4245 ms. This artifact proves networked durable
state and fenced gateway replacement, not PostgreSQL process promotion,
replication, active/active consensus, or production readiness.
`results_rmw_socket/docker_quic_durable_failover_probe_summary.json` adds a
separate durability boundary. The gateway's optional `--state-db` stores
retained frame payloads, dedup keys, and consumer cursors in SQLite WAL with
`synchronous=FULL`; persistence errors return HTTP 503 instead of acknowledging
an unstored frame/cursor. Every one of `5/5` Docker/netem runs uses a fresh
database and three sequential gateway instances. Instance A commits three
frames over one verified H3 session. Instance B recovers all three frames and
dedup keys, recognizes sequence 1 as a duplicate without adding state, then
commits a cursor after replaying sequences 1 and 2. Instance C recovers the
same three retained frames plus that consumer cursor and replays only sequence
3. All three service phases and their C++ clients emit non-empty qlogs and tear
down cleanly. This is shared-storage active/passive recovery. The artifact
explicitly keeps active/active consensus and cluster-wide admission-state
claims false; it does not prove leader election, synchronous multi-node
replication, fencing, or regional disaster recovery.
`results_rmw_socket/docker_quic_durable_admission_failover_probe_summary.json`
extends that boundary to policy state. In every `5/5` run, instance A admits one
normal frame and one quota-overflow repair, committing each frame plus the
post-decision admission snapshot in one SQLite transaction. Instance B restores
two retained frames, the exhausted one-frame normal quota, cumulative count 2,
and the prior repair allocation/count; it rejects a third repair rather than
silently resetting capacity. A third startup with a changed policy is rejected
because its deterministic policy fingerprint differs from the stored state.
Legacy retained frames without an admission snapshot also fail closed. This is
sequential gateway replacement over one local shared SQLite store. It is not
active/active consensus, a distributed database, or cross-region replication.
`results_rmw_socket/docker_quic_writer_fencing_probe_summary.json` closes the
concurrent-writer hole in that shared-store boundary. In every `5/5` run,
gateway A acquires and renews a three-second SQLite writer lease with fence
token 1, admits the normal and repair frames, and keeps the lease live while a
concurrent gateway B startup fails closed. After A releases the lease, gateway
C acquires monotonically increasing token 2, restores frame plus admission and
repair state, and rejects the next repair under the exhausted quota. Frame,
admission, and consumer-cursor writes verify holder, token, and expiry inside
the same `BEGIN IMMEDIATE` transaction, so an expired writer cannot commit a
stale write. This proves manual single-writer active/passive takeover on one
shared SQLite file. It does not provide automatic leader election, consensus,
a distributed database, synchronous multi-node replication, or cross-region
failover; production readiness therefore remains false.
`results_rmw_socket/docker_quic_automatic_standby_takeover_probe_summary.json`
adds a waiting standby without changing that storage scope. In all `5/5` runs,
gateway B is already alive and reports `writer_lease_waiting` while A owns and
renews token 1. After A stops, the same B process acquires token 2, starts its
QUIC/H3 listener, restores the exhausted admission/repair state, and rejects
the next repair. B makes 13 acquisition attempts per run; observed stop-to-ready
takeover is 203--208 ms (median 205 ms). A bounded wait timeout fails closed
instead of bypassing the lease. This is automatic standby takeover coordinated
by one shared SQLite file, not quorum/consensus leader election, replicated
storage, multi-host partition tolerance, or active/active operation.
`results_rmw_socket/docker_quic_postgresql_failover_probe_summary.json`
removes the shared-host-file assumption from the gateway layer. Every one of
`5/5` runs creates a fresh PostgreSQL 16.14 container and connects two gateway
containers to it over the Docker network. Gateway A owns fence token 1 and
commits the normal frame, quota-overflow repair, and post-decision admission
snapshot with `synchronous_commit=on`. Gateway B is already running and blocked
on A's live lease. After A stops, B acquires token 2, starts its QUIC/H3
listener, restores both frames and the exhausted repair allocation, and rejects
the next repair. Lease transitions use a PostgreSQL advisory transaction lock;
frame/admission and cursor transactions lock and verify the lease row
`FOR UPDATE`. Both QUIC clients and services run under matched netem and emit
non-empty qlogs. Stop-to-ready takeover is 429--715 ms. Snapshot endpoints omit
database credentials. This proves networked durable state and gateway
active/passive takeover while one database process remains healthy. It does not
prove database-process failover, replicated PostgreSQL, quorum/consensus,
partition tolerance, active/active operation, or production readiness.
`results_rmw_socket/docker_quic_postgresql_replication_failover_probe_summary.json`
extends that boundary to two database processes. Each of `5/5` fresh runs
bootstraps a PostgreSQL 16.14 primary and streaming standby with a physical
replication slot, then requires the primary to report
`fleetqox_standby|streaming|sync`. Flush and replay WAL positions are positive
after gateway A's two acknowledged frame/admission transactions. The runner
then kills the primary process. A detects durable lease-store loss and exits
fail-closed with code 1; its final durable snapshot is explicitly marked stale
and unavailable. The standby database is promoted read-write and pre-started
gateway B reconnects through a `target_session_attrs=read-write` multi-host
DSN. B acquires fence token 2, recovers both frames, dedup and admission/repair
state, and rejects the next repair over a new verified H3 session. Both gateway
phases run under netem and emit qlogs. Database-failure-to-gateway-ready is
3.129--3.154 s. This proves controlled synchronous database-process failover
without loss of the seeded acknowledged state. Promotion is manual from the
experiment runner; automatic leader election, quorum DCS/consensus,
partition-induced split-brain tolerance, failback, active/active operation,
regional disaster recovery, and production readiness remain false.
`results_rmw_socket/docker_quic_postgresql_quorum_failover_probe_summary.json`
adds consensus coordination without changing the PostgreSQL primary/standby
data model. Every `5/5` run starts three etcd 3.5.17 Raft members, two
failover controllers, two failback controllers, a Docker-socket fence agent,
an mTLS Docker-socket switchover agent, three PostgreSQL lifecycle instances,
three gateways, and three QUIC clients. The runner first confirms synchronous
streaming replication and acknowledged WAL. A forged fence request with no
current lease is rejected and the primary remains live. The runner then kills
two etcd members and applies 100% egress loss in the still-running primary
network namespace. The active gateway exits fail-closed, the replica remains in
recovery, gateway B remains unready, and both controllers emit a
`quorum_unavailable` event before one member is restarted. Exactly one
controller wins a TTL-bound compare-and-put lease at create revision zero. The
fence agent performs a linearizable mTLS etcd range lookup and requires the
stored controller value and lease ID to match the request, then kills only the
configured primary via the Docker API and confirms it stopped. The winner calls
`pg_promote` only after that confirmation; the other controller observes the
result without promoting. B reconnects, obtains fence token 2, restores both
frames and admission state, and rejects the exhausted repair over H3/netem.
End-to-end latency is 9.934--10.478 s. This proves scoped quorum-gated
automatic promotion, DCS-authorized Docker STONITH, and one live-primary
partition/fence sequence. etcd peer and client paths require CA-verified mutual
TLS; an `etcdctl` control that trusts the CA but omits its client certificate is
rejected in every run. The fence HTTPS endpoint also requires a CA-verified
client certificate, binds certificate CN to controller ID, rejects a no-cert
client, and rejects an authenticated forged lease in every run. After gateway
takeover, the runner rebuilds the fenced primary from a fresh physical
basebackup with a dedicated slot. The new primary must report that node as
`streaming|sync` with positive flush/replay WAL; the rebuilt node stays in
recovery and exposes the same two frame rows and one admission-state row. This
proves Docker-automated rejoin and restored post-failover redundancy. Each run
then starts two independent automatic failback policy controllers. With the
replica deliberately changed to `streaming|async`, both emit
`unsafe_preconditions` and leave both database roles unchanged. The runner
restores `streaming|sync|0` while only 1/3 etcd remains; both controllers then
emit `quorum_unavailable` and still do not switch roles. Once 2/3 quorum is
restored, exactly one controller wins the failback lease. A separate mTLS
switchover agent binds its client CN to controller ID, validates the live lease,
and gracefully stops the current primary before the winner promotes the
original primary. Gateway C acquires fence token 3, recovers both frames plus
admission state, and repeats the exhausted-repair rejection over verified
H3/netem. Automatic failback-to-gateway-ready is 1.699--3.449 s. Finally, the
runner re-creates the former primary from a fresh physical basebackup and
requires it to be a synchronous read-only standby with the same seeded rows.
This proves scoped automatic policy/DCS failback and restored post-failback
redundancy in Docker; production automatic failback remains false. The fence is
not hardware/cloud fencing, and certificate rotation/revocation, broader
partition/split-brain tolerance, regional DR, and production readiness remain
false.
`results_rmw_socket/docker_quic_gateway_bidirectional_no_0rtt_probe_summary.json`
reruns the same boundary with `FLEETQOX_RMW_QUIC_DISABLE_EARLY_DATA=1` and
requires `zero_rtt_packet_observed=false` plus
`zero_rtt_disabled_control_claim=true`, providing a negative control for the
0-RTT telemetry parser.
`results_rmw_socket/docker_quic_gateway_async_publish_probe_summary.json`
exercises the same real QUIC/TLS/H3 upload with
`FLEETQOX_RMW_QUIC_GATEWAY_ASYNC=1`; the probe requires enqueue telemetry,
zero async drops/failures, worker drain to depth zero, and the same server-side
body-byte match. This reduces publish-path blocking but remains
subprocess-backed rather than a production in-process QUIC backend.
`results_rmw_socket/docker_quic_gateway_async_burst_probe_summary.json`
extends that proof from one publish to a bounded burst: multiple `rmw_publish`
calls enqueue, the async worker drains all frames, the server sees matching
aggregate body bytes/content-lengths, and queue depth returns to zero with no
drops or worker failures.
`results_rmw_socket/docker_quic_gateway_netem_publish_probe_summary.json`
extends that publish-side gateway proof across two Docker containers with
`tc netem` applied on the publishing client. It records qdisc before/after
counters, parsed ngtcp2 path telemetry, QUIC v1 negotiation, ALPN `h3`, qlog
files, and matching server body bytes.
`results_rmw_socket/docker_quic_gateway_netem_async_burst_probe_summary.json`
combines the async-burst worker with the two-container netem path: the artifact
requires multiple successful queued `rmw_publish` calls, zero async drops or
worker failures, aggregate server body/content-length bytes matching RMW frame
bytes, qdisc before/after counters, qlog emission, and parsed ngtcp2 packet/RTT
telemetry. It is still a subprocess-backed publish-side gate, not evidence for
a full-duplex production QUIC backend.
`results_rmw_socket/docker_quic_gateway_session_reuse_probe_summary.json`
verifies the gateway can pass stable `gtlsclient --session-file`, `--tp-file`,
and `--token-file` arguments across a burst of RMW publishes and that the
session/transport-parameter artifacts persist. It keeps
`zero_rtt_claim=false`; this is file plumbing and telemetry evidence, not proof
of accepted 0-RTT data, certificate policy, or full-duplex backend readiness.
`results_rmw_socket/docker_quic_gateway_async_burst_soak_summary.json` now
repeats the async-burst gateway probe for `10/10` Docker/netem iterations and
aggregates `40` sent/enqueued frames, zero drops/failures, matching server body
bytes, qlog bytes, `208` qdisc packets, and `160` RTT samples. This is a
CI-friendly 10-run soak and reproducibility artifact; it is not a full long
stress/security campaign and does not prove QUIC take-path, session reuse, or
full-duplex production backend readiness.
`results_rmw_socket/docker_stress_security_campaign_summary.json` aggregates
the security-options, FleetQoX security-policy, SROS2 permissions XML, UDP
AEAD and X.509 peer-authentication, plugin-backed dynamic serialization/take,
allocation, QoS event, content-filter, and QUIC async-burst soak components
behind one Docker campaign artifact. The repeated profile currently passes all
ten components across `48/48` component runs and sets `stress_security_smoke_claim=true` plus
`stress_security_repeated_claim=true`. `long_stress_security_campaign_claim`
is now true after eight complete active-soak rounds over `3793.205 s` with
netem (`20±5 ms`, `0.5%` loss): `80/80` component executions and
`1680/1680` probe runs completed without a failed run.

`results_rmw_socket/unified_benchmark_report.md` is generated from existing
summary JSON artifacts plus `rmw_fleetqox_cpp/capabilities.json`. It normalizes
artifact status, run counts, selected key metrics, and claim boundaries in one
place, so benchmark evidence remains tied to the explicit unsupported surfaces
instead of being read as a production-ready or same-hop superiority claim. Its
all-artifact history status includes retained debug, negative-control,
superseded, and canonical files; current capability-manifest health and claim
counts are shown separately rather than filtering old failures.

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

The earlier OMNeT++/INET boundary artifact still records template/input
integrity and the two large manifest trace exports. Runtime is now closed by a
separate pinned OMNeT++ 6.4.0/INET 4.7.0 Docker image and a real INET
`UdpSocket` trace application. The matched routed-P2P matrix uses the same CSV,
robot count, policy rows, seed, data rate, two-link propagation delay, converted
end-to-end PER target, warm-up, and drain horizon in ns-3 3.41 and INET. It
passes all `27/27` runtime pairs and `27/27` bounded-parity cases at
`8/16/32` robots over seeds `7,13,29`, covering `72,213` packet rows. Across
all policies and cases, the maxima are delivery-ratio delta `0.018314`, p99
latency delta `1.234667 ms`, relative delivered-utility delta `0.023683`, and
deadline-miss-ratio delta `0`, against declared bounds `0.05`, `5 ms`, `0.10`,
and `0.10`. Thus `omnetpp_inet_runtime_claim=true`,
`omnetpp_parity_claim=true`, and `ns3_omnetpp_parity_claim=true` apply only to
this matched routed-P2P scope. `full_tsn_mesh_parity_claim=false` and
`high_fidelity_wireless_parity_claim=false` remain explicit.

The current repeated `8/16/32` comparison against Fast DDS, Cyclone DDS, and
Zenoh is recorded in
`results_rmw_socket/large_scale_rmw_comparison_8_16_32_3seed_20260713_summary.json`.
The runner applies netem only after discovery, uses the same six-second
publisher reliability horizon, starts the required Zenoh router/session, and
reports Wilson success intervals plus Student-t metric intervals. The
current-image rerun passes all `36/36` rows. This is still not a same-hop
superiority claim: FleetRMW uses
publisher-router-subscriber while DDS and Zenoh use direct application data
paths (Zenoh still requires its session router). The result is a
topology-caveated gap register and throughput/delivery envelope.
The v2 schema exposes allowed `direct_rmw_delivery_latency` and
`fleet_router_repair_value` scopes while marking `cross_scope_superiority` as
disallowed and `direct_claim_allowed=false`.

A separate artifact,
`results_rmw_socket/same_hop_rmw_comparison_8_16_32_3seed_v1_summary.json`,
matches publisher-middle-subscriber hop count, roaming netem at loss scale
`0.25`, ROS QoS RELIABLE, five samples/topic, and a six-second publisher
horizon. It records `32/36` passing rows: Cyclone DDS and Zenoh `9/9`,
FleetRMW `8/9`, and Fast DDS `6/9`. The FleetRMW failure misses one of `80`
payloads; the three Fast DDS failures miss `3/160`, `2/160`, and `5/320`.
Baseline relays forward `5030/5040` ingress payloads. These are delivery
failures with successful harness setup, so they are retained. The artifact
allows matched-hop delivery/reliability comparison, but disallows latency and
architectural superiority: FleetRMW forwards raw frames while that historical
artifact used a common typed rclpy relay for the three baselines.

The current v2 harness replaces the typed relay with a C++ `rclcpp` generic
serialized-message relay and uses bounded `wait_for_all_acked` publisher
horizons. Fast DDS, Cyclone DDS, and Zenoh each pass an individual `12/12`
relay smoke. A fresh full `8/16/32`-robot, seed `7/13/29` Docker/netem matrix
passes `35/36`: every baseline passes `9/9`, FleetRMW passes `8/9`, and the
baseline relays forward `5040/5040` payloads. The retained FleetRMW
32-robot/seed-29 row delivers `319/320`; it is not retried away. All 36
publishers report supported and completed ACK waits with zero unacked topics.
All baseline rows report opaque serialized forwarding and
`application_deserialization=false`. This matches the application payload's
serialized state, not byte-level cross-RMW serialization and not the
transport-envelope semantics:
FleetRMW forwards raw frames while the baselines terminate and republish
serialized messages through an RMW endpoint. Therefore delivery/reliability
comparison remains allowed, while latency and architectural superiority remain
disallowed.

The follow-on FleetRMW middle-equivalence prerequisite replaces its raw router
with the same C++ generic serialized relay. Three direct FleetRMW UDP peers use
static per-network addresses to avoid startup-order DNS races; publisher and
relay ACK timeout/retry settings are derived from the same roaming netem
profile. An 8-robot, 16-topic, five-sample row under 7% source loss delivers
and relays `80/80`, preserves `application_deserialization=false`, and completes
the publisher ACK horizon. The repeated artifact runs this row `5/5`. This
proves FleetRMW can execute RMW termination/republish with the common middle;
the historical full matrix still records the earlier raw-routing boundary.

The v4 common-middle matrix replaces all nine historical FleetRMW raw-router
rows with direct-peer FleetRMW rows that use the same C++ generic serialized
subscription/publisher relay as Fast DDS, Cyclone DDS, and Zenoh. It preserves
the 27 successful baseline rows, runs the nine new FleetRMW rows, and passes
all `36/36` cells across `8/16/32` robots and seeds `7,13,29`. The relay count
is `6720/6720`; all 36 publisher ACK horizons are supported and complete.
Nine new rows state RMW termination/republish explicitly. The 27
earlier-schema baseline rows provide equivalent strict evidence through
generic subscription, generic publisher, serialized passthrough, and
`application_deserialization=false`. Within this matched envelope,
delivery/reliability and latency-distribution comparison are allowed.
Broad latency superiority, architectural superiority, byte-identical
cross-RMW serialization, and production superiority remain disallowed: three
repetitions per cell and one roaming profile are insufficient for those
claims.

Resume provenance is now fail-closed before extending this matrix into a
profile sensitivity study. Reuse requires matching image tag, profile, netem
loss scale, sample count, publish interval, generic relay mode/scope, required
netem, and publisher reliability horizon. The exact-configuration control
reuses all `36/36` v4 rows, executes zero rows, and preserves `6720/6720`
relay payloads. The negative control supplies that roaming artifact to a
Wi-Fi request for FleetRMW and Cyclone DDS: both candidates are counted as
configuration mismatches, zero rows are reused, both rows execute in Docker,
and both pass with `160/160` relay payloads. Thus a profile change cannot be
silently satisfied by stale measurements.

The first profile-sensitivity campaign then fixes scale at 16 robots and runs
all four RMWs over Wi-Fi, WAN, and roaming with seeds `7,13,29`. Wi-Fi and WAN
contribute 24 fresh Docker/netem rows; roaming contributes 12
configuration-matched rows from v4. Every profile/system/seed cell passes
(`36/36`) and the common relay forwards `5760/5760` payloads. The aggregate
allows profile-scoped delivery/reliability and latency-distribution
comparison. It still forbids broad latency, cross-RMW, architectural, or
production superiority; only one robot scale, three repetitions per profile,
and one payload/sample schedule are represented.

The follow-on full-factorial campaign closes the robot-scale-by-profile gap.
It covers `8/16/32` robots, Wi-Fi/WAN/roaming, seeds `7,13,29`, and all four
RMWs. Wi-Fi and WAN contribute 72 fresh Docker/netem rows; roaming contributes
36 configuration-matched rows. Every one of the `108/108` cells passes and
the common relay forwards `20160/20160` payloads. The v2 aggregator rejects
duplicate or missing profile/robot/system/seed cells and requires all common
middle, ACK horizon, configuration-provenance, and relay-count contracts.
Profile/scale-scoped delivery/reliability and latency-distribution comparison
is now allowed. Broad superiority remains disallowed because each cell still
has only three repetitions and one sample/resource schedule.

The exact-payload campaign then fixes roaming, 16 robots, five samples per
topic, a 50 ms batch interval, and all four common-middle RMW paths while
varying UTF-8 message data over `256`, `4096`, and `32768` bytes. The
fail-closed aggregator accepts measured delivery failures but rejects skipped,
missing, duplicate, configuration-drifted, or byte-mismatched cells. All
`36/36` cells are measured, `18/36` satisfy the complete row contract, and the
relay forwards `3855/5760` payloads. At 256 bytes every RMW passes `3/3`; at
4096 bytes Fast DDS and Cyclone DDS pass `3/3`, while FleetRMW and Zenoh pass
`0/3`; at 32768 bytes every RMW passes `0/3` under the fixed 5 Mbit/s, 7% loss
offered-load schedule. This permits payload-scoped delivery/reliability
comparison, not latency superiority: the 32768-byte cells have no successful
run, repetition remains three, and offered-load/CPU/memory sweeps are absent.

The follow-on 32768-byte offered-load sweep changes only the batch interval
over `50/500/2000` ms, corresponding to payload-only offered rates of
`167.772/16.777/4.194` Mbit/s at the source publisher, before ROS/wire overhead
and excluding the relay hop. Every one of the
`36/36` interval/system/seed cells is measured, but `0/36` satisfies the full
delivery/ACK/process contract and relay delivery is `1149/5760`; no fully
successful interval is observed. Delivery ratios are still valid measured
outcomes, while latency and sustainable-rate claims remain blocked. In
particular, failure at 4.194 Mbit/s under a nominal 5 Mbit/s link means average
offered load alone is not explanatory: batch burst shape, fragmentation under
7% packet loss, protocol overhead, and repair granularity remain confounded.
The follow-up FleetRMW transport path now fragments the plaintext frame into
1024-byte chunks before per-chunk AEAD/signing, derives a stable frame
identity, retains bounded sender history, and returns bounded missing-index
NACK ranges after receiver quiescence. Selective sends use a bounded async
queue with duplicate-key coalescing and observable queue/failure counters. A
fail-closed Docker probe deliberately drops fragment index 2 from each of two
exact 32768-byte messages while whole-sample timeout retransmission is zero.
It relays `2/2`, records exactly two drops, two received fragment NACKs, and
two selective retransmissions, completes every ACK, reports zero queue
rejection/failure, and exits `0/0/0`. This proves the scoped selective path;
it does not retroactively change the historical four-RMW frontier or prove
secure-fragment operation, high-rate/16-robot resource bounds, arbitrary
sample sizes, or production reliability.

A four-robot selective-repair run at roaming loss scale 0.25 and seed 7
delivers `40/40`, completes all ACKs, and exits cleanly. Delaying NACK until an
assembly is quiescent reduces selective sends from `3884` in the
premature-NACK build to `707`. The first 16-robot selective follow-up is still
negative: the best measured run reaches `125/160`, while a slower
2200-microsecond pacing calibration reaches `101/160`. This is not a repaired
fleet-scale operating point. Same-hop resume validation includes `timeout_s`,
fragment size, retry count, pacing, NACK interval/max requests/history, async
mode, queue limit, and relay drain mode. The next transport step is adaptive
capacity admission/pacing plus repeated CPU/memory and secure-fragment gates.

The full-scale rerun also exposed and fixed a FleetRMW initial-sequence ACK
bug. A first observation at sequence 2 previously advanced the cumulative ACK
through a dropped sequence 1. ACK feedback now carries
`lowest_observed_sequence`, and the writer applies cumulative ACK only within
that observed floor. A deterministic Docker probe preserves the sequence-2
NACK-repair path and separately drops sequence 1; timeout retransmission
recovers it and both phases receive all three payloads.

The retained v2 `319/320` row exposed a second, subtler reorder case. If the
first observed sample was sequence 4, the old code established a baseline at
4 but later recomputed the lower cumulative-ACK bound from reordered sequence
1. An ACK could then cover `1..4` even though sequence 3 had never arrived.
The reader now stores an immutable `cumulative_ack_floor` when establishing
its reception baseline. The production writer and deterministic frame
regression share one `ack_nack_acknowledges_sequence` predicate; order
`4,1,5,2` does not acknowledge 3, and sequence 3 is accepted only by its later
exact ACK. The repaired 32-robot/seed-29 Docker/netem row delivers `320/320`.
The v3 comparison records `prior_row_count=36`,
`rerun_failed_rows=true`, preserves the other 35 rows, and passes `36/36`;
FleetRMW, Fast DDS, Cyclone DDS, and Zenoh each pass `9/9`, while baseline
relays remain `5040/5040`. This closes the measured delivery failure, not the
middle-processing or latency-equivalence caveat.

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
  wait/guard probe adds automatic graph-guard notification and `rmw_wait`
readiness for a local serialized subscription. It also passes capacity,
zero-as-unbounded, null-entry, same-domain cross-context, shutdown-context, and
wrong-owner-node negative controls while preserving normal pub/sub operation.
The Docker graph probe adds the
first in-process graph cache
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
bytes with `taken=true`; the router receives at least one route advertisement
and learns exactly one route. Advertisement occurrence counts may be greater
than one because leases renew. The graph observer receives those renewals but
still resolves exactly one unique publisher and one unique subscription. The
router reports `graph_peer_count=1`, `received_frames=1`,
`forwarded_frames=1`, and `invalid_frames=0`; the observer validates the same
remote topic through RMW graph APIs with `topic_found=true`,
`publisher_count=1`, and `subscriber_count=1`.  The remote graph lease probe proves stale endpoint
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

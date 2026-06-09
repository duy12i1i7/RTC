import json
import argparse
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from scripts.run_ros2_docker_live_bridge import (
    apply_netem_profile,
    binding_objective_schedule_for_args,
    binding_objective_summaries_for_args,
    build_repeated_plan,
    build_transition_binding_plan,
    dynamic_objective_transition_summary,
    expand_bridge_topics_for_robots,
    link_schedule_payload_for_profile,
    objective_switch_latency_summary,
    packet_format_comparison,
    parse_ints,
    quality_gate_identity_match_summary,
    render_dynamic_objective_transition_markdown_report,
    render_transition_binding_markdown_report,
    metadata_matrix,
    repeated_metric_rows,
    robot_coverage_summary,
    summarize_repeated_packet_format_records,
    source_metadata_summary,
    switch_latency_summary,
    transition_binding_matrix_summary,
    transition_binding_comparison,
    transport_binding_transition_summary,
    transition_schedule_for_args,
    write_transition_bridge_config,
    write_repeated_report_if_requested,
)
from scripts.apply_netem_transition import (
    NetemTransition,
    apply_transition_schedule,
    parse_transition_schedule,
    tc_command_for_transition,
)


class Ros2DockerLiveBridgeMetadataTest(unittest.TestCase):
    def test_parse_ints_and_repeated_plan_expands_profiles(self) -> None:
        self.assertEqual(parse_ints("7, 13", "--seeds"), [7, 13])

        plans = build_repeated_plan("packet_matrix", [7, 13], ["wifi", "wan"])

        self.assertEqual(plans[0].scenario, "packet_matrix_wifi_seed_7")
        self.assertEqual(plans[1].profile, "wifi")
        self.assertEqual(plans[2].scenario, "packet_matrix_wan_seed_7")
        self.assertEqual(plans[3].seed, 13)

    def test_apply_netem_profile_overrides_network_values(self) -> None:
        args = argparse.Namespace(delay_ms=1, jitter_ms=2, loss_percent=3, rate_mbit=4)

        apply_netem_profile(args, "wan")

        self.assertEqual(args.delay_ms, 60.0)
        self.assertEqual(args.jitter_ms, 15.0)
        self.assertEqual(args.loss_percent, 1.5)
        self.assertEqual(args.rate_mbit, 10.0)

    def test_transition_schedule_for_args_uses_profiles_and_segment(self) -> None:
        args = argparse.Namespace(
            transition_schedule=None,
            transition_profile=["wifi", "wan", "roaming"],
            transition_segment_s=2.5,
        )

        schedule = transition_schedule_for_args(args)

        self.assertEqual([item.profile for item in schedule], ["wifi", "wan", "roaming"])
        self.assertEqual([item.at_s for item in schedule], [0.0, 2.5, 5.0])

    def test_transition_binding_plan_includes_adaptive_and_static_baselines(self) -> None:
        plans = build_transition_binding_plan("transition", [7], ["wifi", "wan"])

        self.assertEqual([plan.binding_label for plan in plans], ["adaptive", "static_wifi", "static_wan"])
        self.assertEqual(plans[1].scenario, "transition_static_wifi")
        self.assertEqual(plans[2].binding_profile, "wan")

    def test_parse_netem_transition_schedule_accepts_explicit_offsets(self) -> None:
        schedule = parse_transition_schedule("wifi@0,wan@3,roaming:7")

        self.assertEqual(schedule[1].profile, "wan")
        self.assertEqual(schedule[2].at_s, 7.0)

    def test_tc_command_for_transition_uses_profile_values(self) -> None:
        command = tc_command_for_transition(NetemTransition("wan", 3.0), dev="eth0")

        self.assertIn("60ms", command)
        self.assertIn("15ms", command)
        self.assertIn("1.5%", command)
        self.assertIn("10mbit", command)

    def test_apply_transition_schedule_dry_run_writes_log(self) -> None:
        with TemporaryDirectory() as tmpdir:
            log = Path(tmpdir) / "transition.jsonl"
            records = apply_transition_schedule(
                [NetemTransition("wifi", 0.0), NetemTransition("wan", 0.0)],
                dev="eth0",
                log=log,
                dry_run=True,
            )

            rows = [json.loads(line) for line in log.read_text(encoding="utf-8").splitlines()]

        self.assertEqual(len(records), 2)
        self.assertEqual(rows[0]["status"], "dry_run")
        self.assertEqual(rows[1]["profile"], "wan")

    def test_write_transition_bridge_config_injects_link_schedule(self) -> None:
        with TemporaryDirectory() as tmpdir:
            base = Path(tmpdir) / "bridge.json"
            output = Path(tmpdir) / "bridge_transition.json"
            base.write_text(
                json.dumps(
                    {
                        "scenario": "base",
                        "link": {"capacity_bytes_per_tick": 1},
                        "topics": [{"topic": "/cmd_vel", "msg_type": "geometry_msgs/msg/Twist"}],
                    }
                ),
                encoding="utf-8",
            )

            write_transition_bridge_config(
                base,
                output,
                [
                    NetemTransition("wifi", 0.0),
                    NetemTransition("roaming", 6.0),
                ],
            )
            payload = json.loads(output.read_text(encoding="utf-8"))

        self.assertEqual(payload["link"]["capacity_bytes_per_tick"], 2400)
        self.assertEqual(payload["link_schedule"][1]["profile"], "roaming")
        self.assertEqual(payload["link_schedule"][1]["rtt_ms"], 160.0)

    def test_write_transition_bridge_config_can_lock_static_binding_profile(self) -> None:
        with TemporaryDirectory() as tmpdir:
            base = Path(tmpdir) / "bridge.json"
            output = Path(tmpdir) / "bridge_transition.json"
            base.write_text(
                json.dumps(
                    {
                        "scenario": "base",
                        "link": {"capacity_bytes_per_tick": 1},
                        "transport_binding": {
                            "summary": "selector.json",
                            "adaptive_profile": True,
                            "smoothing_alpha": 0.35,
                        },
                        "topics": [{"topic": "/cmd_vel", "msg_type": "geometry_msgs/msg/Twist"}],
                    }
                ),
                encoding="utf-8",
            )

            write_transition_bridge_config(
                base,
                output,
                [NetemTransition("wifi", 0.0)],
                binding_profile="wan",
            )
            payload = json.loads(output.read_text(encoding="utf-8"))

        self.assertEqual(payload["transport_binding"], {"summary": "selector.json", "profile": "wan"})
        self.assertEqual(payload["link_schedule"][0]["profile"], "wifi")

    def test_binding_objective_schedule_parses_timed_objectives(self) -> None:
        args = argparse.Namespace(
            binding_objective_summary=[
                "autonomy_safety:results/autonomy.json",
                "teleop_latency:results/teleop.json",
            ],
            binding_objective_schedule=(
                "balanced_safety_utility@0,autonomy_safety@2,teleop_latency@4"
            ),
        )

        summaries = binding_objective_summaries_for_args(args)
        schedule = binding_objective_schedule_for_args(args)

        self.assertEqual(summaries["autonomy_safety"], "results/autonomy.json")
        self.assertEqual(schedule[1]["objective"], "autonomy_safety")
        self.assertEqual(schedule[2]["at_s"], 4.0)

    def test_write_transition_bridge_config_injects_objective_schedule(self) -> None:
        with TemporaryDirectory() as tmpdir:
            base = Path(tmpdir) / "bridge.json"
            output = Path(tmpdir) / "bridge_transition.json"
            base.write_text(
                json.dumps(
                    {
                        "scenario": "base",
                        "transport_binding": {
                            "summary": "balanced.json",
                            "adaptive_profile": True,
                            "smoothing_alpha": 0.35,
                        },
                        "topics": [{"topic": "/cmd_vel", "msg_type": "geometry_msgs/msg/Twist"}],
                    }
                ),
                encoding="utf-8",
            )

            write_transition_bridge_config(
                base,
                output,
                [NetemTransition("wifi", 0.0)],
                objective_summaries={"autonomy_safety": "autonomy.json"},
                objective_schedule=[
                    {"objective": "balanced_safety_utility", "at_s": 0.0},
                    {"objective": "autonomy_safety", "at_s": 2.0},
                ],
            )
            payload = json.loads(output.read_text(encoding="utf-8"))

        self.assertEqual(
            payload["transport_binding"]["objective_summaries"]["autonomy_safety"],
            "autonomy.json",
        )
        self.assertEqual(
            payload["transport_binding"]["objective_schedule"][1]["objective"],
            "autonomy_safety",
        )

    def test_expand_bridge_topics_for_robots_rewrites_namespace(self) -> None:
        topics = expand_bridge_topics_for_robots(
            [
                {
                    "topic": "/robot_0000/cmd_vel",
                    "msg_type": "geometry_msgs/msg/Twist",
                    "robot_id": "robot_0000",
                    "tags": {"source": "robot_0000"},
                },
                {
                    "topic": "/robot_0000/odom",
                    "msg_type": "nav_msgs/msg/Odometry",
                    "robot_id": "robot_0000",
                },
            ],
            robot_count=3,
        )

        self.assertEqual(len(topics), 6)
        self.assertEqual(topics[0]["topic"], "/robot_0000/cmd_vel")
        self.assertEqual(topics[2]["topic"], "/robot_0001/cmd_vel")
        self.assertEqual(topics[4]["topic"], "/robot_0002/cmd_vel")
        self.assertEqual(topics[2]["robot_id"], "robot_0001")
        self.assertEqual(topics[4]["tags"]["source"], "robot_0002")

    def test_write_transition_bridge_config_can_expand_robot_topics(self) -> None:
        with TemporaryDirectory() as tmpdir:
            base = Path(tmpdir) / "bridge.json"
            output = Path(tmpdir) / "bridge_multi.json"
            base.write_text(
                json.dumps(
                    {
                        "scenario": "base",
                        "topics": [
                            {
                                "topic": "/robot_0000/cmd_vel",
                                "msg_type": "geometry_msgs/msg/Twist",
                                "robot_id": "robot_0000",
                            }
                        ],
                    }
                ),
                encoding="utf-8",
            )

            write_transition_bridge_config(
                base,
                output,
                [],
                robot_count=2,
            )
            payload = json.loads(output.read_text(encoding="utf-8"))

        self.assertEqual(payload["robot_count"], 2)
        self.assertEqual(
            [row["topic"] for row in payload["topics"]],
            ["/robot_0000/cmd_vel", "/robot_0001/cmd_vel"],
        )

    def test_link_schedule_payload_for_profile_converts_to_bridge_link(self) -> None:
        payload = link_schedule_payload_for_profile("wifi", at_s=1.0)

        self.assertEqual(payload["capacity_bytes_per_tick"], 2400)
        self.assertEqual(payload["rtt_ms"], 40.0)
        self.assertEqual(payload["loss"], 0.01)

    def test_source_metadata_summary_counts_fields_by_topic_and_type(self) -> None:
        with TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "decisions.jsonl"
            _write_jsonl(
                path,
                [
                    {
                        "event_type": "packet",
                        "topic": "/robot_0000/cmd_vel",
                        "source_msg_type": "geometry_msgs/msg/Twist",
                        "source_metadata": {
                            "sequence_number": 1,
                            "source_timestamp_ns": 100,
                            "received_timestamp_ns": 200,
                        },
                    },
                    {
                        "event_type": "packet",
                        "topic": "/robot_0000/odom",
                        "source_msg_type": "nav_msgs/msg/Odometry",
                        "source_metadata": {
                            "publisher_gid": "0102",
                            "sequence_number": 2,
                            "source_timestamp_ns": 300,
                        },
                    },
                    {
                        "event_type": "decision",
                        "topic": "/robot_0000/odom",
                        "source_metadata": {"sequence_number": 3},
                    },
                    {
                        "event_type": "packet",
                        "topic": "/robot_0000/scan",
                        "source_msg_type": "sensor_msgs/msg/LaserScan",
                    },
                ],
            )

            summary = source_metadata_summary(path)

        self.assertEqual(summary["packet_count"], 3)
        self.assertEqual(summary["records_with_metadata"], 2)
        self.assertEqual(summary["records_without_metadata"], 1)
        self.assertEqual(summary["fields"]["publisher_gid"], 1)
        self.assertEqual(summary["fields"]["sequence_number"], 2)
        self.assertEqual(summary["fields"]["source_timestamp_ns"], 2)
        self.assertEqual(summary["fields"]["received_timestamp_ns"], 1)
        self.assertEqual(summary["by_topic"]["/robot_0000/odom"]["fields"]["publisher_gid"], 1)
        self.assertEqual(
            summary["by_topic_msg_type"]["/robot_0000/cmd_vel|geometry_msgs/msg/Twist"]["fields"][
                "sequence_number"
            ],
            1,
        )

    def test_robot_coverage_summary_counts_robots_from_logs(self) -> None:
        with TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "events.jsonl"
            _write_jsonl(
                path,
                [
                    {
                        "event_type": "packet",
                        "robot_id": "robot_0000",
                        "flow_class": "control",
                        "topic": "/robot_0000/cmd_vel",
                    },
                    {
                        "event_type": "packet",
                        "flow_id": "robot_0001:state",
                        "flow_class": "state",
                        "topic": "/robot_0001/odom",
                    },
                    {
                        "kind": "typed_twist",
                        "topic": "/fleetrmw/robot_0001/local_cmd_vel",
                    },
                ],
            )

            summary = robot_coverage_summary(path)

        self.assertEqual(summary["robot_count"], 2)
        self.assertEqual(summary["robots"], ["robot_0000", "robot_0001"])
        self.assertEqual(summary["by_robot"]["robot_0001"]["events"], 2)
        self.assertEqual(summary["by_robot"]["robot_0000"]["flow_classes"]["control"], 1)

    def test_transport_binding_transition_summary_counts_switches_by_tick(self) -> None:
        with TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "decisions.jsonl"
            _write_jsonl(
                path,
                [
                    _binding_event(0, "wifi", "data_frame/rmw_zenoh_cpp", "data_frame"),
                    _binding_event(0, "wifi", "data_frame/rmw_zenoh_cpp", "data_frame"),
                    _binding_event(1, "roaming", "event_json/rmw_zenoh_cpp", "event_json"),
                ],
            )

            summary = transport_binding_transition_summary(path)

        self.assertEqual(summary["rows"], 3)
        self.assertEqual(summary["rows_with_transport_binding_estimate"], 3)
        self.assertEqual(summary["switch_count"], 1)
        self.assertEqual(summary["switches"][0]["from_profile"], "wifi")
        self.assertEqual(summary["switches"][0]["to_profile"], "roaming")

    def test_transport_binding_transition_summary_tracks_elapsed_switch_time(self) -> None:
        with TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "decisions.jsonl"
            _write_jsonl(
                path,
                [
                    _binding_event(
                        0,
                        "wifi",
                        "data_frame/rmw_zenoh_cpp",
                        "data_frame",
                        timestamp_ms=1000.0,
                    ),
                    _binding_event(
                        1,
                        "wan",
                        "event_json/rmw_zenoh_cpp",
                        "event_json",
                        timestamp_ms=3200.0,
                    ),
                    _binding_event(
                        2,
                        "roaming",
                        "event_json/rmw_zenoh_cpp",
                        "event_json",
                        timestamp_ms=5300.0,
                    ),
                ],
            )

            summary = transport_binding_transition_summary(path)
            latency = switch_latency_summary(
                summary,
                [
                    {"profile": "wifi", "at_s": 0.0},
                    {"profile": "wan", "at_s": 2.0},
                    {"profile": "roaming", "at_s": 4.0},
                ],
            )

        self.assertEqual(summary["switches"][0]["elapsed_s"], 2.2)
        self.assertEqual(latency["matched_switch_count"], 2)
        self.assertAlmostEqual(latency["mean_abs_switch_latency_s"], 0.25)
        self.assertEqual(latency["flapping_switch_count"], 0)

    def test_transport_binding_transition_summary_tracks_objective_switches(self) -> None:
        with TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "decisions.jsonl"
            _write_jsonl(
                path,
                [
                    _binding_event(
                        0,
                        "wan",
                        "event_json/rmw_zenoh_cpp",
                        "event_json",
                        objective="balanced_safety_utility",
                    ),
                    _binding_event(
                        1,
                        "wan",
                        "data_frame/rmw_cyclonedds_cpp",
                        "data_frame",
                        objective="autonomy_safety",
                    ),
                ],
            )

            summary = transport_binding_transition_summary(path)

        self.assertEqual(summary["switch_count"], 0)
        self.assertEqual(summary["objective_switch_count"], 1)
        self.assertEqual(summary["policy_switch_count"], 1)
        self.assertEqual(summary["objectives"], ["autonomy_safety", "balanced_safety_utility"])
        self.assertEqual(
            summary["objective_switches"][0]["to_objective"],
            "autonomy_safety",
        )

    def test_objective_switch_latency_summary_matches_schedule(self) -> None:
        summary = {
            "objective_switches": [
                {
                    "tick": 42,
                    "elapsed_s": 2.1,
                    "from_objective": "balanced_safety_utility",
                    "to_objective": "autonomy_safety",
                    "from_policy": "event_json/rmw_zenoh_cpp",
                    "to_policy": "data_frame/rmw_cyclonedds_cpp",
                },
                {
                    "tick": 80,
                    "elapsed_s": 4.0,
                    "from_objective": "autonomy_safety",
                    "to_objective": "balanced_safety_utility",
                    "from_policy": "data_frame/rmw_cyclonedds_cpp",
                    "to_policy": "event_json/rmw_zenoh_cpp",
                },
            ]
        }

        latency = objective_switch_latency_summary(
            summary,
            [
                {"objective": "balanced_safety_utility", "at_s": 0.0},
                {"objective": "autonomy_safety", "at_s": 2.0},
                {"objective": "balanced_safety_utility", "at_s": 4.0},
            ],
        )

        self.assertEqual(latency["expected_objective_switch_count"], 2)
        self.assertEqual(latency["matched_objective_switch_count"], 2)
        self.assertEqual(latency["missing_objective_switch_count"], 0)
        self.assertEqual(latency["objective_flapping_switch_count"], 0)
        self.assertAlmostEqual(latency["mean_abs_objective_switch_latency_s"], 0.05)

    def test_metadata_matrix_flattens_per_rmw_counts(self) -> None:
        matrix = metadata_matrix(
            [
                {
                    "rmw": "rmw_fastrtps_cpp",
                    "scenario": "fast",
                    "status": "ran",
                    "decision_packet_source_metadata_summary": {
                        "packet_count": 2,
                        "records_with_metadata": 2,
                        "fields": {
                            "publisher_gid": 0,
                            "sequence_number": 2,
                            "source_timestamp_ns": 2,
                            "received_timestamp_ns": 2,
                        },
                    },
                },
                {"rmw": "rmw_missing_cpp", "scenario": "missing", "status": "failed"},
            ]
        )

        self.assertEqual(matrix[0]["rmw"], "rmw_fastrtps_cpp")
        self.assertEqual(matrix[0]["sequence_number"], 2)
        self.assertEqual(matrix[1]["status"], "failed")
        self.assertEqual(matrix[1]["packet_count"], 0)

    def test_packet_format_comparison_flattens_metrics_and_identity(self) -> None:
        rows = packet_format_comparison(
            [
                {
                    "rmw": "rmw_fastrtps_cpp",
                    "packet_format": "data_frame",
                    "scenario": "frame",
                    "status": "ran",
                    "summary": [
                        {
                            "tx": 10,
                            "rx": 9,
                            "loss_ratio": 0.1,
                            "control_delivery_ratio": 1.0,
                            "latency_p95_ms": 12.5,
                        }
                    ],
                    "quality_gate_status_counts": {"accept": 4},
                    "quality_gate_identity_match_summary": {
                        "contract_matches": 4,
                        "contract_gate_total": 4,
                        "source_matches": 4,
                        "source_gate_total": 4,
                    },
                }
            ]
        )

        self.assertEqual(rows[0]["packet_format"], "data_frame")
        self.assertEqual(rows[0]["rx"], 9)
        self.assertEqual(rows[0]["quality_gate_accept"], 4)
        self.assertEqual(rows[0]["contract_matches"], 4)

    def test_repeated_metric_rows_group_by_packet_format_and_rmw(self) -> None:
        records = [
            _record_for_repeated("event_json", "rmw_fastrtps_cpp", 7, 10, 9),
            _record_for_repeated("event_json", "rmw_fastrtps_cpp", 13, 12, 12),
            _record_for_repeated("data_frame", "rmw_fastrtps_cpp", 7, 10, 10),
        ]

        rows = repeated_metric_rows(records)
        summary = summarize_repeated_packet_format_records(records)
        by_group = {row["policy"]: row for row in summary["policies"]}

        self.assertEqual(rows[0]["policy"], "event_json/rmw_fastrtps_cpp")
        self.assertEqual(rows[0]["seed"], 7)
        self.assertEqual(rows[0]["contract_match_ratio"], 1.0)
        self.assertEqual(by_group["event_json/rmw_fastrtps_cpp"]["runs"], 2)
        self.assertEqual(by_group["data_frame/rmw_fastrtps_cpp"]["runs"], 1)

    def test_repeated_metric_rows_skip_unsuccessful_records(self) -> None:
        records = [
            _record_for_repeated("event_json", "rmw_fastrtps_cpp", 7, 10, 9),
            _record_for_repeated("data_frame", "rmw_fastrtps_cpp", 7, 10, 0, status="failed"),
            {"packet_format": "event_json", "rmw": "rmw_zenoh_cpp", "seed": 7, "status": "missing_tool"},
        ]

        rows = repeated_metric_rows(records)
        summary = summarize_repeated_packet_format_records(records)

        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["policy"], "event_json/rmw_fastrtps_cpp")
        self.assertEqual(summary["records"], 1)
        self.assertEqual(len(summary["policies"]), 1)

    def test_repeated_report_skips_plan_mode(self) -> None:
        with TemporaryDirectory() as tmpdir:
            args = argparse.Namespace(
                report=True,
                run=False,
                repeated_summary_json=Path(tmpdir) / "summary.json",
                repeated_markdown=Path(tmpdir) / "report.md",
                title="Plan",
            )
            result = write_repeated_report_if_requested(
                args,
                {"records": 0, "policies": []},
                [_record_for_repeated("event_json", "rmw_fastrtps_cpp", 7, 10, 10)],
            )

            self.assertEqual(result, {})
            self.assertFalse(args.repeated_summary_json.exists())

    def test_repeated_report_skips_when_no_successful_metrics(self) -> None:
        with TemporaryDirectory() as tmpdir:
            args = argparse.Namespace(
                report=True,
                run=True,
                repeated_summary_json=Path(tmpdir) / "summary.json",
                repeated_markdown=Path(tmpdir) / "report.md",
                title="Invalid",
            )
            records = [
                {"packet_format": "event_json", "rmw": "rmw_fastrtps_cpp", "seed": 7, "status": "missing_tool"}
            ]
            summary = summarize_repeated_packet_format_records(records)
            result = write_repeated_report_if_requested(args, summary, records)

            self.assertEqual(summary["records"], 0)
            self.assertEqual(result, {})
            self.assertFalse(args.repeated_summary_json.exists())

    def test_transition_binding_summary_compares_adaptive_against_static(self) -> None:
        records = [
            _record_for_transition_binding("adaptive", None, 80, 76, 0.95, 100.0, 2),
            _record_for_transition_binding("static", "wifi", 80, 70, 0.875, 120.0, 0),
            _record_for_transition_binding("static", "wan", 80, 72, 0.9, 90.0, 0),
        ]

        summary = transition_binding_matrix_summary(
            records,
            transitions=[NetemTransition("wifi", 0.0), NetemTransition("wan", 2.0)],
            static_profiles=["wifi", "wan"],
        )
        rows = transition_binding_comparison(records)

        self.assertEqual(summary["records"], 3)
        self.assertEqual(rows[0]["binding_label"], "adaptive")
        self.assertEqual(summary["best_policy"]["control_delivery"], "adaptive")
        by_baseline = {row["baseline"]: row for row in summary["adaptive_advantage"]}
        self.assertGreater(by_baseline["static_wifi"]["control_delivery_delta"], 0)
        self.assertLess(by_baseline["static_wan"]["latency_p95_delta_ms"], 0)
        adaptive = next(row for row in summary["policies"] if row["policy"] == "adaptive")
        self.assertEqual(adaptive["switch_count_mean"], 2.0)
        self.assertEqual(adaptive["matched_switch_count_mean"], 2.0)
        self.assertAlmostEqual(adaptive["mean_abs_switch_latency_s_mean"], 0.25)

    def test_dynamic_objective_transition_summary_tracks_objective_evidence(self) -> None:
        records = [
            _record_for_dynamic_objective_transition(7, 80, 76, 2.1, 4.0),
            _record_for_dynamic_objective_transition(13, 82, 78, 2.0, 4.2),
        ]
        objective_schedule = [
            {"objective": "balanced_safety_utility", "at_s": 0.0},
            {"objective": "autonomy_safety", "at_s": 2.0},
            {"objective": "balanced_safety_utility", "at_s": 4.0},
        ]

        summary = dynamic_objective_transition_summary(
            records,
            transitions=[
                NetemTransition("wifi", 0.0),
                NetemTransition("wan", 2.0),
                NetemTransition("roaming", 4.0),
            ],
            objective_schedule=objective_schedule,
        )
        markdown = render_dynamic_objective_transition_markdown_report(
            summary,
            title="Dynamic Objective",
            metrics_paths=["run_metrics.jsonl"],
        )

        policy = summary["policies"][0]
        self.assertEqual(summary["records"], 2)
        self.assertEqual(
            policy["policy"],
            "dynamic_objective/fleetqox_semantic_contract_adaptive/rmw_zenoh_cpp",
        )
        self.assertEqual(policy["switch_count_mean"], 2.0)
        self.assertEqual(policy["objective_switch_count_mean"], 2.0)
        self.assertEqual(policy["policy_switch_count_mean"], 2.0)
        self.assertEqual(policy["matched_objective_switch_count_mean"], 2.0)
        self.assertAlmostEqual(policy["mean_abs_objective_switch_latency_s_mean"], 0.075)
        self.assertEqual(policy["robot_count_mean"], 2.0)
        self.assertEqual(policy["decision_robot_count_observed_mean"], 2.0)
        self.assertEqual(policy["received_robot_count_observed_mean"], 2.0)
        self.assertEqual(policy["egress_robot_count_observed_mean"], 2.0)
        self.assertEqual(policy["lease_robot_count_observed_mean"], 2.0)
        self.assertEqual(policy["quality_gate_robot_count_observed_mean"], 2.0)
        self.assertEqual(policy["egress_monitor_robot_count_observed_mean"], 2.0)
        self.assertEqual(policy["decision_robot_coverage_ratio_mean"], 1.0)
        self.assertEqual(policy["received_robot_coverage_ratio_mean"], 1.0)
        self.assertEqual(policy["egress_robot_coverage_ratio_mean"], 1.0)
        self.assertEqual(policy["lease_robot_coverage_ratio_mean"], 1.0)
        self.assertEqual(policy["quality_gate_robot_coverage_ratio_mean"], 1.0)
        self.assertEqual(policy["egress_monitor_robot_coverage_ratio_mean"], 1.0)
        self.assertEqual(policy["per_robot_budget_pass_ratio"], 1.0)
        self.assertAlmostEqual(policy["per_robot_rx_jain_index_mean"], 0.99)
        self.assertIn("## Objective Schedule", markdown)
        self.assertIn("objective abs s", markdown)
        self.assertIn("decision robots", markdown)
        self.assertIn("gate robots", markdown)
        self.assertIn("## Per-Robot QoS Budget", markdown)

    def test_transition_binding_report_renders_nested_netem_schedule_values(self) -> None:
        markdown = render_transition_binding_markdown_report(
            {
                "records": 1,
                "static_profiles": ["wifi"],
                "transition_schedule": [
                    {
                        "profile": "wifi",
                        "at_s": 0.0,
                        "config": {"delay_ms": 20, "jitter_ms": 5, "loss_percent": 1},
                    }
                ],
                "policies": [],
                "adaptive_advantage": [],
                "best_policy": {},
            },
            title="Transition",
            metrics_paths=[],
        )

        self.assertIn("| wifi | 0.0000 | 40.0000 | 5.0000 | 0.0100 |", markdown)

    def test_quality_gate_identity_match_summary_counts_gate_matches(self) -> None:
        with TemporaryDirectory() as tmpdir:
            decisions = Path(tmpdir) / "decisions.jsonl"
            gates = Path(tmpdir) / "gates.jsonl"
            _write_jsonl(
                decisions,
                [
                    {
                        "event_type": "packet",
                        "topic": "/robot_0000/odom",
                        "contract_id": "fcid1-a",
                        "source_sample_id": "fsid1-a",
                    },
                    {
                        "event_type": "packet",
                        "topic": "/robot_0000/cmd_vel",
                        "contract_id": "fcid1-control",
                        "source_sample_id": "fsid1-control",
                    },
                    {
                        "event_type": "packet",
                        "topic": "/robot_0000/scan",
                        "contract_id": "fcid1-b",
                        "source_sample_id": "fsid1-b",
                    },
                    {
                        "event_type": "packet",
                        "topic": "/robot_0001/odom",
                        "contract_id": "fcid2-a",
                        "source_sample_id": "fsid2-a",
                    },
                ],
            )
            _write_jsonl(
                gates,
                [
                    {"contract_id": "fcid1-a", "source_sample_id": "fsid1-a"},
                    {"contract_id": "fcid1-missing", "source_sample_id": "fsid1-b"},
                    {"contract_id": "fcid2-a", "source_sample_id": "fsid2-a"},
                ],
            )

            summary = quality_gate_identity_match_summary(decisions, gates)

        self.assertEqual(summary["decision_state_scan_packets"], 3)
        self.assertEqual(summary["gate_decisions"], 3)
        self.assertEqual(summary["contract_matches"], 2)
        self.assertEqual(summary["contract_gate_total"], 3)
        self.assertEqual(summary["source_matches"], 3)


def _write_jsonl(path: Path, records: list[dict[str, object]]) -> None:
    path.write_text(
        "".join(json.dumps(record, sort_keys=True) + "\n" for record in records),
        encoding="utf-8",
    )


def _record_for_repeated(
    packet_format: str,
    rmw: str,
    seed: int,
    tx: int,
    rx: int,
    *,
    status: str = "ran",
) -> dict[str, object]:
    return {
        "packet_format": packet_format,
        "rmw": rmw,
        "scenario": f"{packet_format}_{rmw}_seed_{seed}",
        "status": status,
        "seed": seed,
        "profile": "wifi",
        "summary": [
            {
                "policy": "fleetqox_semantic_contract_adaptive",
                "scenario": f"{packet_format}_{rmw}_seed_{seed}",
                "tx": tx,
                "rx": rx,
                "loss_ratio": 1.0 - (rx / tx),
                "control_delivery_ratio": 1.0,
                "control_non_delivery_events": 0,
                "control_starvation_events": 0,
                "deadline_miss_ratio": 0.0,
                "semantic_utility_delivered": float(rx),
                "latency_p95_ms": 20.0,
                "latency_p99_ms": 30.0,
                "compacted_rx": 0,
                "intent_rx": 1,
                "bytes_rx": rx * 10,
            }
        ],
        "quality_gate_status_counts": {"accept": 2},
        "quality_gate_identity_match_summary": {
            "contract_matches": 2,
            "contract_gate_total": 2,
            "source_matches": 2,
            "source_gate_total": 2,
        },
    }


def _record_for_transition_binding(
    mode: str,
    profile: str | None,
    tx: int,
    rx: int,
    control_delivery_ratio: float,
    p95_ms: float,
    switch_count: int,
) -> dict[str, object]:
    label = f"static_{profile}" if mode == "static" else "adaptive"
    loss_ratio = 1.0 - (rx / tx)
    return {
        "scenario": f"transition_{label}",
        "status": "ran",
        "seed": 7,
        "rmw": "rmw_zenoh_cpp",
        "packet_format": "event_json",
        "binding_mode": mode,
        "binding_profile": profile or mode,
        "binding_label": label,
        "summary": [
            {
                "policy": "fleetqox_semantic_contract_adaptive",
                "scenario": f"transition_{label}",
                "tx": tx,
                "rx": rx,
                "loss_ratio": loss_ratio,
                "control_delivery_ratio": control_delivery_ratio,
                "control_non_delivery_events": 0,
                "control_starvation_events": 0,
                "deadline_miss_ratio": loss_ratio / 2.0,
                "semantic_utility_delivered": float(rx),
                "latency_p95_ms": p95_ms,
                "latency_p99_ms": p95_ms + 20.0,
                "compacted_rx": 0,
                "intent_rx": 1,
                "bytes_rx": rx * 10,
            }
        ],
        "transition_schedule": [
            {"profile": "wifi", "at_s": 0.0},
            {"profile": "wan", "at_s": 2.0},
            {"profile": "roaming", "at_s": 4.0},
        ],
        "transport_binding_transition_summary": {
            "rows": 10,
            "rows_with_transport_binding": 10,
            "rows_with_transport_binding_estimate": 10 if mode == "adaptive" else 0,
            "switch_count": switch_count,
            "switches": (
                [
                    {
                        "tick": 10,
                        "elapsed_s": 2.2,
                        "from_profile": "wifi",
                        "to_profile": "wan",
                        "from_policy": "data_frame/rmw_zenoh_cpp",
                        "to_policy": "event_json/rmw_zenoh_cpp",
                    },
                    {
                        "tick": 20,
                        "elapsed_s": 4.3,
                        "from_profile": "wan",
                        "to_profile": "roaming",
                        "from_policy": "event_json/rmw_zenoh_cpp",
                        "to_policy": "event_json/rmw_zenoh_cpp",
                    },
                ][:switch_count]
                if mode == "adaptive"
                else []
            ),
            "profiles": ["wifi", "wan", "roaming"] if mode == "adaptive" else [profile],
            "packet_formats": ["data_frame", "event_json"] if mode == "adaptive" else ["event_json"],
        },
        "netem_transition_summary": {
            "profiles": ["wifi", "wan"],
            "statuses": {"applied": 2},
        },
    }


def _record_for_dynamic_objective_transition(
    seed: int,
    tx: int,
    rx: int,
    autonomy_elapsed_s: float,
    balanced_elapsed_s: float,
) -> dict[str, object]:
    loss_ratio = 1.0 - (rx / tx)
    return {
        "scenario": f"dynamic_objective_seed_{seed}",
        "status": "ran",
        "seed": seed,
        "robot_count": 2,
        "rmw": "rmw_zenoh_cpp",
        "policy": "fleetqox_semantic_contract_adaptive",
        "packet_format": "event_json",
        "summary": [
            {
                "policy": "fleetqox_semantic_contract_adaptive",
                "scenario": f"dynamic_objective_seed_{seed}",
                "tx": tx,
                "rx": rx,
                "loss_ratio": loss_ratio,
                "control_delivery_ratio": 0.95,
                "control_non_delivery_events": 0,
                "control_starvation_events": 0,
                "deadline_miss_ratio": loss_ratio / 2.0,
                "semantic_utility_delivered": float(rx),
                "latency_p95_ms": 120.0,
                "latency_p99_ms": 140.0,
                "compacted_rx": 0,
                "intent_rx": 1,
                "bytes_rx": rx * 10,
            }
        ],
        "transition_schedule": [
            {"profile": "wifi", "at_s": 0.0},
            {"profile": "wan", "at_s": 2.0},
            {"profile": "roaming", "at_s": 4.0},
        ],
        "binding_objective_schedule": [
            {"objective": "balanced_safety_utility", "at_s": 0.0},
            {"objective": "autonomy_safety", "at_s": 2.0},
            {"objective": "balanced_safety_utility", "at_s": 4.0},
        ],
        "transport_binding_transition_summary": {
            "rows": 100,
            "rows_with_transport_binding": 100,
            "rows_with_transport_binding_estimate": 100,
            "switch_count": 2,
            "switches": [
                {
                    "tick": 40,
                    "elapsed_s": 2.0,
                    "from_profile": "wifi",
                    "to_profile": "wan",
                    "from_policy": "event_json/rmw_zenoh_cpp",
                    "to_policy": "data_frame/rmw_cyclonedds_cpp",
                },
                {
                    "tick": 80,
                    "elapsed_s": 4.0,
                    "from_profile": "wan",
                    "to_profile": "roaming",
                    "from_policy": "data_frame/rmw_cyclonedds_cpp",
                    "to_policy": "event_json/rmw_zenoh_cpp",
                },
            ],
            "objective_switch_count": 2,
            "objective_switches": [
                {
                    "tick": 42,
                    "elapsed_s": autonomy_elapsed_s,
                    "from_objective": "balanced_safety_utility",
                    "to_objective": "autonomy_safety",
                    "from_policy": "event_json/rmw_zenoh_cpp",
                    "to_policy": "data_frame/rmw_cyclonedds_cpp",
                },
                {
                    "tick": 80,
                    "elapsed_s": balanced_elapsed_s,
                    "from_objective": "autonomy_safety",
                    "to_objective": "balanced_safety_utility",
                    "from_policy": "data_frame/rmw_cyclonedds_cpp",
                    "to_policy": "event_json/rmw_zenoh_cpp",
                },
            ],
            "policy_switch_count": 2,
            "profiles": ["wifi", "wan", "roaming"],
            "objectives": ["autonomy_safety", "balanced_safety_utility"],
            "packet_formats": ["data_frame", "event_json"],
        },
        "netem_transition_summary": {
            "profiles": ["wifi", "wan", "roaming"],
            "statuses": {"applied": 3},
        },
        "decision_robot_coverage": {
            "robot_count": 2,
            "robots": ["robot_0000", "robot_0001"],
        },
        "received_robot_coverage": {
            "robot_count": 2,
            "robots": ["robot_0000", "robot_0001"],
        },
        "egress_robot_coverage": {
            "robot_count": 2,
            "robots": ["robot_0000", "robot_0001"],
        },
        "lease_robot_coverage": {
            "robot_count": 2,
            "robots": ["robot_0000", "robot_0001"],
        },
        "quality_gate_robot_coverage": {
            "robot_count": 2,
            "robots": ["robot_0000", "robot_0001"],
        },
        "egress_monitor_robot_coverage": {
            "robot_count": 2,
            "robots": ["robot_0000", "robot_0001"],
        },
        "per_robot_qos_summary": {
            "robot_count": 2,
            "robots": ["robot_0000", "robot_0001"],
            "fairness": {
                "rx_jain_index": 0.99,
                "control_delivery_jain_index": 1.0,
                "deadline_success_jain_index": 0.98,
                "min_control_delivery_ratio": 0.95,
                "max_deadline_miss_ratio": 0.20,
                "latency_p95_spread_ms": 12.0,
                "worst_control_delivery_robot": "robot_0001",
                "worst_deadline_miss_robot": "robot_0001",
                "worst_latency_p95_robot": "robot_0001",
            },
        },
        "per_robot_budget_report": {
            "pass": True,
        },
    }


def _binding_event(
    tick: int,
    profile: str,
    policy: str,
    packet_format: str,
    *,
    timestamp_ms: float | None = None,
    objective: str = "balanced_safety_utility",
) -> dict[str, object]:
    payload: dict[str, object] = {
        "event_type": "packet",
        "tick": tick,
        "transport_binding": {
            "profile": profile,
            "objective": objective,
            "policy": policy,
            "packet_format": packet_format,
        },
        "transport_binding_estimate": {
            "profile": profile,
            "candidate_profile": profile,
            "confidence": 0.8,
        },
    }
    if timestamp_ms is not None:
        payload["timestamp_ms"] = timestamp_ms
    return payload


if __name__ == "__main__":
    unittest.main()

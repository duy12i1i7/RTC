import unittest

from scripts.run_large_scale_rmw_comparison import (
    aggregate as aggregate_comparison,
    metric_summary,
    normalize_row,
    render_markdown as render_comparison_markdown,
    row_needs_infrastructure_rerun,
)
from scripts.run_rmw_docker_fleet_repair_capacity_frontier import (
    aggregate_rows as aggregate_frontier_rows,
    frontier_row,
    render_markdown as render_frontier_markdown,
    reusable_prior_row,
    RUNNER_SEMANTICS_VERSION,
)
from scripts.run_rmw_docker_router_matched_multi_topic_probe import (
    reliable_timing_for_netem,
)
from scripts.run_rmw_docker_quic_netem_frame_probe import (
    parse_netem_qdisc_counters,
    parse_ngtcp2_path_telemetry,
)
from scripts.run_rmw_docker_quic_gateway_publish_probe import (
    parse_server_body_bytes,
    parse_server_body_sizes,
    parse_server_content_length,
    parse_server_content_lengths,
)
from scripts.run_ns3_docker_fleet_matrix import parse_csv_summary


class FleetScaleReportRunnersTest(unittest.TestCase):
    def test_ns3_summary_parser_preserves_policy_metrics(self) -> None:
        rows = parse_csv_summary(
            "noise\n"
            "policy,tx,rx,bytes,deadline_miss_ratio,p50_ms,p99_ms,utility\n"
            "fifo,10,9,900,0.1,2.0,7.0,4.5\n"
        )
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["policy"], "fifo")
        self.assertEqual(rows[0]["tx"], 10)
        self.assertEqual(rows[0]["rx"], 9)
        self.assertEqual(rows[0]["p99_ms"], 7.0)

    def test_reliable_timing_uses_profile_rtt_and_retry_horizon(self) -> None:
        timeout_ms, linger_s = reliable_timing_for_netem(
            {"delay_ms": 58.0, "jitter_ms": 22.0},
            configured_ack_timeout_ms=None,
            max_retransmissions=3,
        )

        self.assertEqual(timeout_ms, 254)
        self.assertEqual(linger_s, 6.0)

        disabled_timeout, disabled_linger = reliable_timing_for_netem(
            {"delay_ms": 58.0, "jitter_ms": 22.0},
            configured_ack_timeout_ms=0,
            max_retransmissions=3,
        )
        self.assertEqual(disabled_timeout, 0)
        self.assertEqual(disabled_linger, 0.5)

    def test_quic_netem_telemetry_parser_tracks_ngtcp2_path_state(self) -> None:
        telemetry = parse_ngtcp2_path_telemetry(
            "Sent packet: local=[172.18.0.3]:35048 remote=[172.18.0.2]:4445 "
            "ecn=0x2 1200 bytes\n"
            "Received packet: local=[172.18.0.3]:35048 remote=[172.18.0.2]:4445 "
            "ecn=0x2 1200 bytes\n"
            "I00000049 conn pkt tx pkn=1 type=1RTT len=64\n"
            "I00000049 conn pkt rx pkn=0 type=Initial len=119\n"
            "I00000049 conn rcv latest_rtt=49 min_rtt=49 smoothed_rtt=49 "
            "rttvar=24 ack_delay=0\n"
            "I00000049 conn rcv pkn=0 acked, slow start cwnd=15720\n"
            "I00000049 conn con path is ECN capable\n"
            "I00000049 conn con the negotiated version is 0x00000001\n",
            "I00000072 conn rcv latest_rtt=53 min_rtt=20 smoothed_rtt=50 "
            "rttvar=12 target_cwnd=226120 max_delivery_rate_sec=1048576\n",
        )

        self.assertTrue(telemetry["quic_v1_negotiated_observed"])
        self.assertTrue(telemetry["ecn_capable_observed"])
        self.assertEqual(telemetry["sent_packet_log_count"], 1)
        self.assertEqual(telemetry["received_packet_log_count"], 1)
        self.assertEqual(telemetry["sent_packet_bytes_logged"], 1200)
        self.assertEqual(telemetry["packet_tx_log_count"], 1)
        self.assertEqual(telemetry["packet_rx_log_count"], 1)
        self.assertEqual(telemetry["rtt_raw"]["latest"]["sample_count"], 2)
        self.assertEqual(telemetry["rtt_raw"]["latest"]["max"], 53)
        self.assertEqual(telemetry["rtt_raw"]["min"]["min"], 20)
        self.assertEqual(telemetry["congestion_raw"]["cwnd_bytes"]["last"], 15720)
        self.assertEqual(
            telemetry["congestion_raw"]["target_cwnd_bytes"]["last"],
            226120,
        )
        self.assertEqual(
            telemetry["congestion_raw"]["max_delivery_rate_per_s"]["last"],
            1048576,
        )

    def test_netem_qdisc_counter_parser_reads_before_after_snapshots(self) -> None:
        counters = parse_netem_qdisc_counters(
            "qdisc netem 8002: root refcnt 13 limit 1000 delay 20ms  5ms\n"
            " Sent 8400 bytes 7 pkt (dropped 1, overlimits 2 requeues 3)\n"
            " backlog 120b 1p requeues 4\n"
        )

        self.assertEqual(counters["sent_bytes"], 8400)
        self.assertEqual(counters["sent_packets"], 7)
        self.assertEqual(counters["dropped_packets"], 1)
        self.assertEqual(counters["overlimits"], 2)
        self.assertEqual(counters["requeues"], 3)
        self.assertEqual(counters["backlog_bytes"], 120)
        self.assertEqual(counters["backlog_packets"], 1)
        self.assertEqual(counters["backlog_requeues"], 4)

    def test_quic_gateway_server_log_parser_tracks_uploaded_body(self) -> None:
        server_log = (
            "http: stream 0x0 [content-length: 536]\n"
            "http: stream 0x0 body 536 bytes\n"
            "http: stream 0x4 [content-length: 17]\n"
            "http: stream 0x4 body 17 bytes\n"
        )

        self.assertEqual(parse_server_content_length(server_log), 536)
        self.assertEqual(parse_server_body_bytes(server_log), 536)
        self.assertEqual(parse_server_content_lengths(server_log), [536, 17])
        self.assertEqual(parse_server_body_sizes(server_log), [536, 17])

    def test_frontier_aggregate_tracks_admission_monotonicity(self) -> None:
        rows = [
            {
                "status": "ok",
                "admission_ok": True,
                "live_qoe_ok": True,
                "repair_actuation_ok": True,
                "robot_count": 8,
                "capacity_bytes": 700,
                "admitted_count": 1,
                "repair_qualified_ratio": 0.25,
                "live_qoe_qualified_ratio": 1.0,
                "repair_path_transmission_overhead": 1,
                "max_latency_ms": 200.0,
            },
            {
                "status": "ok",
                "admission_ok": True,
                "live_qoe_ok": True,
                "repair_actuation_ok": True,
                "robot_count": 8,
                "capacity_bytes": 1400,
                "admitted_count": 2,
                "repair_qualified_ratio": 0.5,
                "live_qoe_qualified_ratio": 1.0,
                "repair_path_transmission_overhead": 2,
                "max_latency_ms": 210.0,
            },
        ]

        frontier = aggregate_frontier_rows(rows)

        self.assertEqual(len(frontier), 2)
        self.assertTrue(all(row["monotonic"] for row in frontier))
        self.assertEqual(frontier[0]["admitted_count_mean"], 1.0)
        self.assertEqual(frontier[1]["admission_qualified_ratio_mean"], 0.5)
        self.assertEqual(frontier[1]["repair_qualified_ratio_mean"], 0.5)
        self.assertIn("max_latency_ms_ci95_low", frontier[1])

    def test_frontier_resume_rejects_pre_actuation_semantics(self) -> None:
        result = {"repair_capacity_fault": True}
        self.assertFalse(reusable_prior_row({
            "runner_semantics_version": "fleetrmw.fleet_repair_capacity_frontier.live_qoe.v2",
            "result": result,
        }))
        self.assertTrue(reusable_prior_row({
            "runner_semantics_version": RUNNER_SEMANTICS_VERSION,
            "result": result,
        }))

    def test_frontier_monotonicity_includes_live_qoe(self) -> None:
        common = {
            "status": "ok",
            "admission_ok": True,
            "repair_actuation_ok": True,
            "live_qoe_ok": True,
            "robot_count": 8,
            "repair_path_transmission_overhead": 1,
            "max_latency_ms": 200.0,
        }
        frontier = aggregate_frontier_rows([
            {
                **common,
                "capacity_bytes": 700,
                "admitted_count": 1,
                "repair_qualified_ratio": 0.25,
                "live_qoe_qualified_ratio": 0.875,
            },
            {
                **common,
                "capacity_bytes": 1400,
                "admitted_count": 2,
                "repair_qualified_ratio": 0.5,
                "live_qoe_qualified_ratio": 0.75,
            },
        ])

        self.assertTrue(frontier[0]["monotonic"])
        self.assertFalse(frontier[1]["monotonic"])

    def test_frontier_report_names_admission_semantics(self) -> None:
        summary = {
            "status": "ok",
            "ok_run_count": 1,
            "admission_ok_run_count": 1,
            "run_count": 1,
            "frontier": [
                {
                    "robot_count": 8,
                    "capacity_bytes": 700,
                    "ok_run_count": 1,
                    "admission_ok_run_count": 1,
                    "run_count": 1,
                    "admitted_count_mean": 1.0,
                    "admitted_count_ci95_low": 1.0,
                    "admitted_count_ci95_high": 1.0,
                    "repair_qualified_ratio_mean": 0.25,
                    "live_qoe_qualified_ratio_mean": 1.0,
                    "live_qoe_qualified_ratio_ci95_low": 1.0,
                    "live_qoe_qualified_ratio_ci95_high": 1.0,
                    "admission_qualified_ratio_mean": 0.25,
                    "admission_qualified_ratio_ci95_low": 0.25,
                    "admission_qualified_ratio_ci95_high": 0.25,
                    "repair_overhead_mean": 1.0,
                    "repair_overhead_ci95_low": 1.0,
                    "repair_overhead_ci95_high": 1.0,
                    "max_latency_ms_mean": 200.0,
                    "max_latency_ms_ci95_low": 200.0,
                    "max_latency_ms_ci95_high": 200.0,
                    "monotonic": True,
                }
            ],
        }

        markdown = render_frontier_markdown(summary)

        self.assertIn("admission-qualified ratio", markdown)
        self.assertIn("admitted gaps are repaired on time", markdown)

    def test_frontier_row_requires_admission_and_actuated_repair(self) -> None:
        base_result = {
            "status": "ok",
            "qoe_recovery_ok": False,
            "repair_capacity_fault": True,
            "repair_capacity_outcome_ok": True,
            "repair_deadline_robots_ok": 5,
            "fleet_repair_schedule": {
                "admitted_count": 1,
                "deferred_count": 3,
                "allocated_bytes": 700,
                "decisions": [
                    {"robot_id": "robot_0000", "action": "repair"},
                    {"robot_id": "robot_0001", "action": "defer"},
                    {"robot_id": "robot_0002", "action": "defer"},
                    {"robot_id": "robot_0003", "action": "defer"},
                ],
            },
            "fallback_repair": {
                "robots": [
                    {
                        "robot_id": "robot_0000",
                        "status": "repaired_on_time",
                        "repair_evidence": True,
                        "publisher_repair_plan_frames": 1,
                    },
                    *[
                        {
                            "robot_id": f"robot_{index:04d}",
                            "status": "unresolved",
                            "missing_sequences": [2],
                            "publisher_repair_not_admitted": 1,
                        }
                        for index in range(1, 4)
                    ],
                ]
            },
        }
        passed = frontier_row(
            result=base_result,
            robot_count=8,
            protected_count=4,
            repetition_id=7,
            capacity_fraction=0.25,
            capacity_bytes=700,
            admitted_slots=1,
        )
        failed = frontier_row(
            result={**base_result, "repair_deadline_robots_ok": 4},
            robot_count=8,
            protected_count=4,
            repetition_id=7,
            capacity_fraction=0.25,
            capacity_bytes=700,
            admitted_slots=1,
        )

        self.assertEqual(passed["status"], "ok")
        self.assertTrue(passed["admission_ok"])
        self.assertTrue(passed["repair_actuation_ok"])
        self.assertEqual(passed["repair_qualified_ratio"], 0.25)
        self.assertEqual(passed["live_qoe_qualified_ratio"], 0.625)
        self.assertEqual(failed["status"], "failed")
        self.assertTrue(failed["admission_ok"])
        self.assertFalse(failed["repair_actuation_ok"])

    def test_large_scale_comparison_reports_delivery_failures_and_latency_passes(self) -> None:
        rows = [
            normalize_row(
                {
                    "status": "ok",
                    "robot_count": 8,
                    "topic_count": 16,
                    "control_delivery_ratio": 1.0,
                    "state_delivery_ratio": 1.0,
                    "min_topic_delivery_ratio": 1.0,
                    "control_latency_ms_p95": 80.0,
                    "state_latency_ms_p95": 82.0,
                },
                system="rmw_fleetqox_cpp_router",
            ),
            normalize_row(
                {
                    "status": "failed",
                    "robot_count": 8,
                    "topic_count": 16,
                    "control_delivery_ratio": 0.0,
                    "state_delivery_ratio": 0.0,
                    "min_topic_delivery_ratio": 0.0,
                    "control_latency_ms_p95": 0.0,
                    "state_latency_ms_p95": 0.0,
                },
                system="rmw_fleetqox_cpp_router",
            ),
        ]

        aggregates = aggregate_comparison(rows)

        self.assertEqual(aggregates[0]["run_count"], 2)
        self.assertEqual(aggregates[0]["ok_run_count"], 1)
        self.assertEqual(aggregates[0]["control_delivery_ratio_mean"], 0.5)
        self.assertEqual(aggregates[0]["control_latency_ms_p95_mean"], 80.0)
        self.assertEqual(aggregates[0]["success_rate_mean"], 0.5)

    def test_metric_summary_reports_three_seed_student_t_interval(self) -> None:
        summary = metric_summary(
            [{"value": 90.0}, {"value": 100.0}, {"value": 110.0}],
            "value",
        )

        self.assertEqual(summary["count"], 3)
        self.assertEqual(summary["mean"], 100.0)
        self.assertLess(summary["ci95_low"], 90.0)
        self.assertGreater(summary["ci95_high"], 110.0)

    def test_resume_only_reruns_infrastructure_failures(self) -> None:
        delivery_failure = normalize_row(
            {
                "status": "failed",
                "robot_count": 8,
                "topic_count": 16,
                "control_payload_count": 39,
                "control_expected_count": 40,
                "state_payload_count": 40,
                "state_expected_count": 40,
                "subscriber_returncode": 1,
            },
            system="rmw_fastrtps_cpp",
        )
        lifecycle_failure = normalize_row(
            {
                "status": "failed",
                "robot_count": 16,
                "topic_count": 32,
                "control_payload_count": 80,
                "control_expected_count": 80,
                "state_payload_count": 80,
                "state_expected_count": 80,
                "publisher_returncode": 139,
            },
            system="rmw_fleetqox_cpp_router",
        )

        self.assertFalse(row_needs_infrastructure_rerun(delivery_failure))
        self.assertTrue(row_needs_infrastructure_rerun(lifecycle_failure))

    def test_large_scale_report_preserves_topology_caveat(self) -> None:
        markdown = render_comparison_markdown(
            {
                "comparison_design": "split_scope_topology_caveated",
                "direct_claim_allowed": False,
                "topology_note": (
                    "FleetRMW uses publisher-router-subscriber; DDS/Zenoh rows "
                    "use direct publisher-subscriber."
                ),
                "aggregates": [
                    {
                        "system": "rmw_fleetqox_cpp_router",
                        "robot_count": 8,
                        "ok_run_count": 1,
                        "run_count": 1,
                        "success_rate_mean": 1.0,
                        "success_rate_ci95_low": 0.2,
                        "success_rate_ci95_high": 1.0,
                        "control_delivery_ratio_mean": 1.0,
                        "control_delivery_ratio_ci95_low": 1.0,
                        "control_delivery_ratio_ci95_high": 1.0,
                        "state_delivery_ratio_mean": 1.0,
                        "state_delivery_ratio_ci95_low": 1.0,
                        "state_delivery_ratio_ci95_high": 1.0,
                        "min_topic_delivery_ratio_mean": 1.0,
                        "min_topic_delivery_ratio_ci95_low": 1.0,
                        "min_topic_delivery_ratio_ci95_high": 1.0,
                        "control_latency_ms_p95_mean": 80.0,
                        "control_latency_ms_p95_ci95_low": 80.0,
                        "control_latency_ms_p95_ci95_high": 80.0,
                        "state_latency_ms_p95_mean": 82.0,
                        "state_latency_ms_p95_ci95_low": 82.0,
                        "state_latency_ms_p95_ci95_high": 82.0,
                        "reliability_modes": ["ack_timeout_retransmit"],
                    }
                ],
            }
        )

        self.assertIn("mixed-hop table", markdown)
        self.assertIn("publisher-router-subscriber", markdown)
        self.assertIn("cross-scope superiority allowed: `false`", markdown)
        self.assertIn("Disallowed scope", markdown)
        self.assertIn("ack_timeout_retransmit", markdown)


if __name__ == "__main__":
    unittest.main()

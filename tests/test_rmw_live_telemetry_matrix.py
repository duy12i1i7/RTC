import unittest

from scripts.run_rmw_docker_multi_robot_live_telemetry_matrix import (
    FINAL_PATH_PLAN,
    INITIAL_PATH_PLAN,
    _all_netem_applied,
    parse_profiles,
    render_markdown,
    run_record_from_summary,
    summarize_runs,
)
from scripts.run_rmw_docker_multi_robot_live_telemetry_plan_probe import (
    NETEM_SCHEMA_VERSION,
    STATE_TERMINAL_GUARD_PAYLOAD,
    live_topic_specs_for_robot_count,
    netem_config_for_path,
    netem_shell_prefix,
    path_plan_for_specs,
    profile_by_name,
    publisher_command,
    router_netem_drain_suffix,
    terminal_horizon_for_profile,
)
from scripts.run_rmw_docker_multi_robot_live_stochastic_netem_sweep import (
    classify_failure,
    parse_loss_scales,
    render_markdown as render_sweep_markdown,
    summarize_sweep,
)
from scripts.run_rmw_docker_multi_robot_live_stochastic_netem_ablation import (
    mode_record_from_sweep,
    parse_modes,
    render_markdown as render_ablation_markdown,
    summarize_ablation,
)


class RmwLiveTelemetryMatrixTest(unittest.TestCase):
    def test_run_record_extracts_qoe_and_dedup_metrics(self) -> None:
        record = run_record_from_summary(_summary("wifi"), seed=7)

        self.assertEqual(record["schema_version"], "fleetrmw.rmw_multi_robot_live_telemetry_matrix_run.v1")
        self.assertEqual(record["status"], "ok")
        self.assertEqual(record["profile"], "wifi")
        self.assertEqual(record["image"], "localhost/fleetrmw/rmw-netem:jazzy")
        self.assertEqual(record["initial_path_plan"], INITIAL_PATH_PLAN)
        self.assertEqual(record["controller_final_path_plan"], FINAL_PATH_PLAN)
        self.assertEqual(record["control_redundant_frames"], 2)
        self.assertEqual(record["control_duplicate_data_frames_deduped"], 2)
        self.assertEqual(record["state_duplicate_data_frames_deduped"], 0)
        self.assertEqual(record["control_payload_count"], 3)
        self.assertEqual(record["state_payload_count"], 3)
        self.assertEqual(record["control_payloads"], ["one", "two", "three"])
        self.assertAlmostEqual(record["control_delivery_latency_ms_mean"], 2.0)
        self.assertAlmostEqual(record["state_delivery_latency_ms_mean"], 4.0)
        self.assertTrue(record["netem_enabled"])
        self.assertAlmostEqual(record["netem_drain_s"], 2.0)
        self.assertEqual(record["repetition_seed"], 7)
        self.assertIn("repetition_id_only", record["netem_seed_semantics"])
        self.assertIsNone(record["failure_returncode"])
        self.assertEqual(record["failure_phase"], "")
        self.assertFalse(record["reuse_build"])
        self.assertTrue(record["build_performed"])
        self.assertTrue(record["control_duplicate_ack_required"])
        self.assertTrue(record["stochastic_netem"])
        self.assertFalse(record["state_duplicate_dedup_required"])
        self.assertFalse(record["state_duplicate_ack_required"])
        self.assertEqual(record["state_proactive_data_repeats"], 1)
        self.assertTrue(_all_netem_applied(record))

    def test_run_record_extracts_harness_failure_diagnostics(self) -> None:
        record = run_record_from_summary(
            {
                "status": "failed",
                "profile": "wifi",
                "image": "localhost/fleetrmw/rmw-netem:jazzy",
                "repetition_seed": 7,
                "netem_enabled": True,
                "netem_required": True,
                "netem_status": {
                    "primary_wifi": {"status": "applied"},
                    "backup_5g": {"status": "applied"},
                },
                "failure": {
                    "phase": "run_state_publisher",
                    "command": ["docker", "run", "localhost/fleetrmw/rmw-netem:jazzy"],
                    "returncode": 42,
                    "stdout_excerpt": "state publisher stdout",
                    "stderr_excerpt": "state publisher stderr",
                    "container_logs": {"router": "router tail"},
                },
            },
            seed=7,
        )

        self.assertEqual(record["status"], "failed")
        self.assertEqual(record["failure_phase"], "run_state_publisher")
        self.assertEqual(record["failure_returncode"], 42)
        self.assertIn("docker", record["failure_command"])
        self.assertIn("state publisher stdout", record["failure_stdout_excerpt"])
        self.assertIn("state publisher stderr", record["failure_stderr_excerpt"])
        self.assertIn("router tail", record["failure_container_log_excerpt"])

    def test_summary_groups_by_profile(self) -> None:
        records = [
            run_record_from_summary(_summary("wifi"), seed=7),
            run_record_from_summary(_summary("wan"), seed=7),
        ]
        summary = summarize_runs(records)

        self.assertEqual(summary["run_count"], 2)
        self.assertEqual(summary["ok_run_count"], 2)
        self.assertEqual(summary["netem_applied_run_count"], 2)
        self.assertEqual([row["profile"] for row in summary["profiles"]], ["wan", "wifi"])

    def test_markdown_contains_profile_table(self) -> None:
        records = [run_record_from_summary(_summary("roaming"), seed=7)]
        summary = {
            "schema_version": "fleetrmw.rmw_multi_robot_live_telemetry_matrix.v1",
            "status": "ok",
            "profiles": ["roaming"],
            "seeds": [7],
            "runs": records,
            "summary": summarize_runs(records),
            "seed_semantics": "repetition_id_only; current tc netem image does not support explicit RNG seed",
        }
        markdown = render_markdown(summary)

        self.assertIn("# RMW Multi-Robot Live Telemetry Matrix V1", markdown)
        self.assertIn("| roaming | 1/1 |", markdown)
        self.assertIn("Netem enabled", markdown)
        self.assertIn("Netem drain seconds", markdown)
        self.assertIn("Reuse build", markdown)
        self.assertIn("Seed semantics", markdown)
        self.assertIn("redundant-path de-duplication", markdown)

    def test_live_topic_specs_and_path_plan_scale_by_robot_count(self) -> None:
        specs = live_topic_specs_for_robot_count(3)
        initial = path_plan_for_specs(specs, final=False)
        final = path_plan_for_specs(specs, final=True)

        self.assertEqual(len(specs), 6)
        self.assertIn("/robot_0002/cmd_vel=primary_wifi", initial)
        self.assertIn("/robot_0002/odom=primary_wifi", initial)
        self.assertIn("/robot_0002/cmd_vel=backup_5g+primary_wifi", final)
        self.assertIn("/robot_0002/odom=backup_5g", final)

    def test_run_record_extracts_scaled_robot_count_and_kind_latency(self) -> None:
        record = run_record_from_summary(_scaled_summary("wifi"), seed=7)

        self.assertEqual(record["robot_count"], 2)
        self.assertEqual(record["topic_count"], 4)
        self.assertEqual(record["control_payload_count"], 40)
        self.assertEqual(record["state_payload_count"], 40)
        self.assertEqual(record["state_terminal_guard_payload"], "terminal_guard")
        self.assertEqual(record["terminal_guard_algorithm"], "deadline_sequence_repair_v1")
        self.assertEqual(record["terminal_guard_repeat_count"], 5)
        self.assertEqual(record["terminal_guard_router_dwell_ms"], 4000)
        self.assertEqual(record["terminal_guard_required_sequence"], 4)
        self.assertEqual(record["terminal_horizon"]["algorithm"], "deadline_sequence_repair_v1")
        self.assertEqual(record["terminal_horizon"]["proactive_data_repeats"], 1)
        self.assertEqual(record["terminal_horizon"]["startup_settle_ms"], 1000)
        self.assertEqual(record["terminal_horizon"]["pre_publish_wait_ms"], 0)
        self.assertEqual(record["terminal_horizon"]["post_plan_settle_ms"], 0)
        self.assertEqual(record["terminal_horizon"]["pre_payload_warmup_count"], 1)
        self.assertEqual(record["terminal_horizon"]["pre_payload_warmup_ack_count"], 1)
        self.assertEqual(record["terminal_horizon"]["pre_payload_warmup_ack_timeout_ms"], 2000)
        self.assertEqual(record["terminal_horizon"]["app_repair_cycle_count"], 2)
        self.assertEqual(record["terminal_horizon"]["tail_repair_repeat_count"], 5)
        self.assertEqual(record["state_payloads_per_publisher"], 3)
        self.assertEqual(record["state_wire_payloads_per_publisher"], 20)
        self.assertIn(
            "/robot_0001/odom=4",
            record["backup_expected_forwarded_topic_source_sequences"],
        )
        self.assertAlmostEqual(record["control_delivery_latency_ms_mean"], 3.0)
        self.assertAlmostEqual(record["state_delivery_latency_ms_mean"], 6.0)
        self.assertIn("/robot_0001/cmd_vel=backup_5g+primary_wifi", record["expected_final_path_plan"])

    def test_publisher_command_supports_terminal_guard_before_hold(self) -> None:
        command = publisher_command(
            install_base="/work/install",
            endpoint_binary="/work/bin/probe",
            topic="/robot_0000/odom",
            plan_file="/work/plan.txt",
            primary_router_name="primary",
            backup_router_name="backup",
            min_ack_nack_received=0,
            proactive_data_repeats=1,
            publish_interval_ms=500,
            hold_ms=5500,
            post_recovery_payload=STATE_TERMINAL_GUARD_PAYLOAD,
            post_recovery_before_hold=True,
            post_recovery_repeat_count=5,
        )

        self.assertIn(f"--post-recovery-payload {STATE_TERMINAL_GUARD_PAYLOAD}", command)
        self.assertIn("--post-recovery-before-hold", command)
        self.assertIn("--post-recovery-repeat-count 5", command)
        self.assertIn("--pre-payload-warmup-ack-count 0", command)
        self.assertIn("--pre-payload-warmup-ack-timeout-ms 0", command)
        self.assertIn("--app-repair-cycle-count 0", command)
        self.assertIn("--app-repair-cycle-payloads one,two,three", command)

    def test_terminal_horizon_derives_from_profile_risk(self) -> None:
        wifi = terminal_horizon_for_profile(
            profile_by_name("wifi"),
            robot_count=4,
            loss_scale=0.1,
        )
        roaming = terminal_horizon_for_profile(
            profile_by_name("roaming"),
            robot_count=4,
            loss_scale=0.1,
        )

        self.assertEqual(wifi.algorithm, "deadline_sequence_repair_v1")
        self.assertEqual(wifi.repeat_count, 5)
        self.assertEqual(wifi.router_dwell_ms, 4000)
        self.assertEqual(wifi.startup_settle_ms, 1000)
        self.assertEqual(wifi.pre_publish_wait_ms, 0)
        self.assertEqual(wifi.post_plan_settle_ms, 0)
        self.assertEqual(wifi.pre_payload_warmup_count, 1)
        self.assertEqual(wifi.pre_payload_warmup_ack_count, 1)
        self.assertEqual(wifi.pre_payload_warmup_ack_timeout_ms, 2000)
        self.assertEqual(wifi.app_repair_cycle_count, 2)
        self.assertEqual(wifi.tail_repair_repeat_count, 5)
        self.assertEqual(wifi.required_sequence, 4)
        self.assertEqual(wifi.proactive_data_repeats, 1)
        self.assertEqual(wifi.wire_payloads_per_publisher, 20)
        self.assertGreater(roaming.risk_score, wifi.risk_score)
        self.assertGreaterEqual(roaming.repeat_count, wifi.repeat_count)
        self.assertGreaterEqual(roaming.router_dwell_ms, wifi.router_dwell_ms)
        self.assertEqual(roaming.pre_publish_wait_ms, wifi.pre_publish_wait_ms)
        self.assertEqual(roaming.post_plan_settle_ms, wifi.post_plan_settle_ms)
        self.assertEqual(roaming.proactive_data_repeats, 1)

    def test_parse_profiles_rejects_unknown_values(self) -> None:
        self.assertEqual(parse_profiles("wifi,wan,wifi"), ["wifi", "wan"])
        with self.assertRaises(SystemExit):
            parse_profiles("wifi,missing")

    def test_netem_config_and_shell_prefix_are_auditable(self) -> None:
        profile = profile_by_name("wifi")
        config = netem_config_for_path(profile, path_id="primary_wifi", loss_scale=0.5)
        prefix = netem_shell_prefix(
            config,
            status_file="/work/.tmp_fleetrmw/netem_status.json",
            require=True,
        )

        self.assertEqual(config["schema_version"], NETEM_SCHEMA_VERSION)
        self.assertEqual(config["path_id"], "primary_wifi")
        self.assertAlmostEqual(config["loss_percent"], 9.0)
        self.assertIn("tc qdisc replace dev eth0 root netem", prefix)
        self.assertIn("delay 58ms 22ms", prefix)
        self.assertIn("loss random 9%", prefix)
        self.assertIn("rate 20mbit", prefix)
        self.assertIn("router_netem.v1", prefix)
        self.assertIn("exit 24", prefix)
        self.assertEqual(router_netem_drain_suffix(2.0), "; rc=$?; sleep 2; exit $rc")

    def test_stochastic_sweep_summarizes_failure_envelope(self) -> None:
        rows = [
            _sweep_row("wifi", 0.1, "ok", 40.0),
            _sweep_row("wan", 0.1, "ok", 55.0),
            _sweep_row("wifi", 0.5, "failed", 0.0),
            _sweep_row("wan", 0.5, "ok", 90.0),
        ]
        summary = summarize_sweep(rows, profiles=["wifi", "wan"])
        markdown = render_sweep_markdown(
            {
                "status": "partial",
                "image": "localhost/fleetrmw/rmw-netem:jazzy",
                "profiles": ["wifi", "wan"],
                "seeds": [7],
                "seed_semantics": "repetition_id_only",
                "loss_scales": [0.1, 0.5],
                "netem_required": True,
                "summary": summary,
                "runs": rows,
            }
        )

        self.assertEqual(summary["run_count"], 4)
        self.assertEqual(summary["ok_run_count"], 3)
        self.assertEqual(summary["failed_run_count"], 1)
        self.assertEqual(summary["failure_kind_counts"], {"delivery_failed": 1})
        self.assertEqual(summary["max_all_profiles_ok_loss_scale"], 0.1)
        self.assertEqual(summary["first_failed_loss_scale_by_profile"], {"wifi": 0.5})
        self.assertEqual(classify_failure(rows[2]), "delivery_failed")
        self.assertIn("# RMW Multi-Robot Live Stochastic Netem Sweep V1", markdown)
        self.assertIn("| 0.100 | 2/2 |", markdown)
        self.assertIn("delivery_failed:1", markdown)
        self.assertIn("| wifi | 0.500 | 0/1 | delivery_failed:1 |", markdown)
        self.assertIn("## Failure Detail", markdown)

    def test_stochastic_sweep_classifies_harness_and_netem_failures(self) -> None:
        harness = _sweep_row("wifi", 0.1, "failed", 0.0)
        harness.update(
            {
                "failure_returncode": 125,
                "failure_phase": "start_backup_router",
                "failure_stderr_excerpt": "docker: network not found",
            }
        )
        netem = _sweep_row("wan", 0.1, "failed", 0.0)
        netem.update(
            {
                "netem_required": True,
                "netem_status": {
                    "primary_wifi": {"status": "applied"},
                    "backup_5g": {"status": "failed"},
                },
            }
        )

        summary = summarize_sweep([harness, netem], profiles=["wifi", "wan"])
        markdown = render_sweep_markdown(
            {
                "status": "failed",
                "image": "localhost/fleetrmw/rmw-netem:jazzy",
                "profiles": ["wifi", "wan"],
                "seeds": [7],
                "seed_semantics": "repetition_id_only",
                "loss_scales": [0.1],
                "netem_required": True,
                "summary": summary,
                "runs": [harness, netem],
            }
        )

        self.assertEqual(
            summary["failure_kind_counts"],
            {"harness_exception": 1, "netem_not_applied": 1},
        )
        self.assertEqual(classify_failure(harness), "harness_exception")
        self.assertEqual(classify_failure(netem), "netem_not_applied")
        self.assertIn("harness_exception:1,netem_not_applied:1", markdown)
        self.assertIn("phase=start_backup_router", markdown)

    def test_stochastic_sweep_classifies_deterministic_contract_evidence(self) -> None:
        row = _sweep_row("wifi", 0.0, "failed", 12.0)
        row.update(
            {
                "control_payload_count": 3,
                "state_payload_count": 3,
                "control_duplicate_ack_required": True,
                "control_duplicate_ack_received": 0,
            }
        )

        self.assertEqual(classify_failure(row), "contract_evidence_failed")

    def test_stochastic_sweep_classifies_subscriber_timeout_as_delivery_failure(self) -> None:
        row = _sweep_row("roaming", 0.25, "failed", 0.0)
        row.update(
            {
                "control_subscriber_status": "failed",
                "state_subscriber_status": "failed",
                "control_subscriber_returncode": 1,
                "state_subscriber_returncode": 1,
                "control_publisher_status": "ok",
                "state_publisher_status": "ok",
                "primary_router_status": "ok",
                "backup_router_status": "ok",
                "control_publisher_returncode": 0,
                "state_publisher_returncode": 0,
                "primary_router_returncode": 0,
                "backup_router_returncode": 0,
                "control_payload_count": 2,
                "state_payload_count": 2,
            }
        )

        self.assertEqual(classify_failure(row), "delivery_failed")

    def test_parse_loss_scales_rejects_invalid_values(self) -> None:
        self.assertEqual(parse_loss_scales("0.1,0.25,0.1"), [0.1, 0.25])
        with self.assertRaises(SystemExit):
            parse_loss_scales("0.1,bad")
        with self.assertRaises(SystemExit):
            parse_loss_scales("-0.1")

    def test_stochastic_ablation_ranks_resilience_before_repair_cost(self) -> None:
        none_rows = [
            _sweep_row("wifi", 0.1, "ok", 35.0),
            _sweep_row("wan", 0.1, "ok", 45.0),
            _sweep_row("wifi", 0.5, "failed", 0.0),
            _sweep_row("wan", 0.5, "failed", 0.0),
        ]
        control_state_rows = [
            _sweep_row("wifi", 0.1, "ok", 40.0, repair_cost=3),
            _sweep_row("wan", 0.1, "ok", 55.0, repair_cost=3),
            _sweep_row("wifi", 0.5, "ok", 90.0, repair_cost=4),
            _sweep_row("wan", 0.5, "ok", 105.0, repair_cost=4),
        ]
        none = mode_record_from_sweep(
            mode="none",
            sweep=_sweep_summary(none_rows, profiles=["wifi", "wan"]),
            control_proactive_data_repeats=0,
            state_proactive_data_repeats=0,
        )
        control_state = mode_record_from_sweep(
            mode="control_state",
            sweep=_sweep_summary(control_state_rows, profiles=["wifi", "wan"]),
            control_proactive_data_repeats=1,
            state_proactive_data_repeats=1,
        )
        summary = summarize_ablation([none, control_state])
        markdown = render_ablation_markdown(
            {
                "status": summary["status"],
                "image": "localhost/fleetrmw/rmw-netem:jazzy",
                "profiles": ["wifi", "wan"],
                "seeds": [7],
                "seed_semantics": "repetition_id_only",
                "loss_scales": [0.1, 0.5],
                "modes": ["none", "control_state"],
                "netem_required": True,
                "reuse_build": True,
                "build_performed": True,
                "summary": summary,
            }
        )

        self.assertEqual(summary["status"], "ok")
        self.assertEqual(summary["best_mode"], "control_state")
        self.assertEqual(summary["ranking"][0]["mode"], "control_state")
        self.assertEqual(summary["run_count"], 8)
        self.assertEqual(summary["ok_run_count"], 6)
        self.assertIn("# RMW Multi-Robot Live Stochastic Netem Ablation V1", markdown)
        self.assertIn("| 1 | control_state | 1 | 1 | 4/4 |", markdown)
        self.assertIn("| none | wan:0.500,wifi:0.500 |", markdown)

    def test_parse_modes_rejects_invalid_values(self) -> None:
        self.assertEqual(parse_modes("none,control_state,none"), ["none", "control_state"])
        with self.assertRaises(SystemExit):
            parse_modes("none,missing")


def _summary(profile: str) -> dict[str, object]:
    return {
        "status": "ok",
        "profile": profile,
        "image": "localhost/fleetrmw/rmw-netem:jazzy",
        "profile_config": {"label": profile},
        "netem_enabled": True,
        "netem_required": True,
        "netem_loss_scale": 0.5,
        "netem_drain_s": 2.0,
        "stochastic_netem": True,
        "reuse_build": False,
        "build_performed": True,
        "control_duplicate_ack_required": True,
        "state_duplicate_dedup_required": False,
        "state_duplicate_ack_required": False,
        "control_proactive_data_repeats": 1,
        "state_proactive_data_repeats": 1,
        "repetition_seed": 7,
        "netem_seed_semantics": "repetition_id_only; current tc netem in the RMW image does not support explicit RNG seed",
        "netem_status": {
            "primary_wifi": {"status": "applied"},
            "backup_5g": {"status": "applied"},
        },
        "initial_path_plan": INITIAL_PATH_PLAN,
        "controller_final_path_plan": FINAL_PATH_PLAN,
        "controller": {"record_count": 8, "subscriber_record_count": 6},
        "control_publisher": {
            "fleet_plan_redundant_frames": 2,
            "fleet_plan_selected_path_count": 5,
            "ack_nack_duplicate_received": 2,
        },
        "state_publisher": {
            "fleet_plan_redundant_frames": 0,
            "fleet_plan_selected_path_count": 3,
            "ack_nack_duplicate_received": 0,
        },
        "control_subscriber": {
            "duplicate_data_frames_deduped": 2,
            "payloads": ["one", "two", "three"],
        },
        "state_subscriber": {
            "duplicate_data_frames_deduped": 0,
            "payloads": ["one", "two", "three"],
        },
        "subscriber_telemetry": {
            "robot_0000": [{"latency_ms": 1.0}, {"latency_ms": 3.0}],
            "robot_0001": [{"latency_ms": 2.0}, {"latency_ms": 6.0}],
        },
    }


def _scaled_summary(profile: str) -> dict[str, object]:
    specs = live_topic_specs_for_robot_count(2)
    initial = path_plan_for_specs(specs, final=False)
    final = path_plan_for_specs(specs, final=True)
    horizon = terminal_horizon_for_profile(
        profile_by_name(profile),
        robot_count=2,
        loss_scale=0.1,
    )
    publisher_payloads = (
        ["route_warmup"] * horizon.pre_payload_warmup_count +
        ["one", "two", "three"] +
        ["one", "two", "three"] * horizon.app_repair_cycle_count +
        ["three"] * horizon.tail_repair_repeat_count +
        ["terminal_guard"] * horizon.repeat_count
    )
    return {
        "status": "ok",
        "profile": profile,
        "image": "localhost/fleetrmw/rmw-netem:jazzy",
        "profile_config": {"label": profile},
        "robot_count": 2,
        "topic_count": 4,
        "topic_specs": [spec.as_dict() for spec in specs],
        "netem_enabled": True,
        "netem_required": True,
        "netem_loss_scale": 0.1,
        "netem_drain_s": 2.0,
        "stochastic_netem": True,
        "reuse_build": True,
        "build_performed": True,
        "control_duplicate_ack_required": False,
        "state_duplicate_dedup_required": False,
        "state_duplicate_ack_required": False,
        "control_proactive_data_repeats": 1,
        "state_proactive_data_repeats": 1,
        "state_terminal_guard_payload": "terminal_guard",
        "terminal_guard_algorithm": horizon.algorithm,
        "terminal_guard_repeat_count": horizon.repeat_count,
        "terminal_guard_router_dwell_ms": horizon.router_dwell_ms,
        "terminal_guard_required_sequence": horizon.required_sequence,
        "terminal_horizon": horizon.as_dict(),
        "control_payloads_per_publisher": 3,
        "state_payloads_per_publisher": 3,
        "control_wire_payloads_per_publisher": horizon.wire_payloads_per_publisher,
        "state_wire_payloads_per_publisher": horizon.wire_payloads_per_publisher,
        "primary_expected_forwarded_topic_source_sequences": "/robot_0000/cmd_vel=4;/robot_0001/cmd_vel=4",
        "backup_expected_forwarded_topic_source_sequences": "/robot_0000/odom=4;/robot_0001/odom=4",
        "repetition_seed": 7,
        "netem_seed_semantics": "repetition_id_only; current tc netem in the RMW image does not support explicit RNG seed",
        "netem_status": {
            "primary_wifi": {"status": "applied"},
            "backup_5g": {"status": "applied"},
        },
        "initial_path_plan": initial,
        "expected_initial_path_plan": initial,
        "controller_final_path_plan": final,
        "expected_final_path_plan": final,
        "controller": {"record_count": 12, "subscriber_record_count": 12},
        "control_publisher": {
            "status": "ok",
            "fleet_plan_redundant_frames": 4,
            "fleet_plan_selected_path_count": 8,
            "ack_nack_duplicate_received": 2,
        },
        "state_publisher": {
            "status": "ok",
            "fleet_plan_redundant_frames": 0,
            "fleet_plan_selected_path_count": 6,
            "ack_nack_duplicate_received": 0,
        },
        "control_subscriber": {
            "status": "ok",
            "duplicate_data_frames_deduped": 2,
            "payloads": [*publisher_payloads, *publisher_payloads],
        },
        "state_subscriber": {
            "status": "ok",
            "duplicate_data_frames_deduped": 0,
            "payloads": [*publisher_payloads, *publisher_payloads],
        },
        "primary_router": {"status": "ok"},
        "backup_router": {"status": "ok"},
        "subscriber_telemetry": {
            "robot_0000/cmd_vel": [{"latency_ms": 2.0}, {"latency_ms": 4.0}],
            "robot_0001/cmd_vel": [{"latency_ms": 1.0}, {"latency_ms": 5.0}],
            "robot_0000/odom": [{"latency_ms": 4.0}, {"latency_ms": 8.0}],
            "robot_0001/odom": [{"latency_ms": 3.0}, {"latency_ms": 9.0}],
        },
        "control_publisher_returncode": 0,
        "state_publisher_returncode": 0,
        "control_subscriber_returncode": 0,
        "state_subscriber_returncode": 0,
        "primary_router_returncode": 0,
        "backup_router_returncode": 0,
    }


def _sweep_summary(rows: list[dict[str, object]], *, profiles: list[str]) -> dict[str, object]:
    summary = summarize_sweep(rows, profiles=profiles)
    status = "ok" if summary["failed_run_count"] == 0 else "partial"
    if summary["ok_run_count"] == 0:
        status = "failed"
    return {
        "status": status,
        "summary": summary,
        "runs": rows,
    }


def _sweep_row(
    profile: str,
    loss_scale: float,
    status: str,
    latency_ms: float,
    *,
    repair_cost: int = 1,
) -> dict[str, object]:
    delivered = status == "ok"
    return {
        "status": status,
        "profile": profile,
        "loss_scale": loss_scale,
        "netem_enabled": True,
        "netem_status": {
            "primary_wifi": {"status": "applied"},
            "backup_5g": {"status": "applied"},
        },
        "control_publisher_status": "ok",
        "state_publisher_status": "ok",
        "control_subscriber_status": "ok",
        "state_subscriber_status": "ok",
        "primary_router_status": "ok",
        "backup_router_status": "ok",
        "control_publisher_returncode": 0,
        "state_publisher_returncode": 0,
        "control_subscriber_returncode": 0,
        "state_subscriber_returncode": 0,
        "primary_router_returncode": 0,
        "backup_router_returncode": 0,
        "router_record_count": 8,
        "subscriber_record_count": 6,
        "control_payload_count": 3 if delivered else 2,
        "state_payload_count": 3,
        "control_delivery_latency_ms_mean": latency_ms,
        "state_delivery_latency_ms_mean": latency_ms / 2.0,
        "control_redundant_frames": 2 if delivered else 0,
        "state_redundant_frames": 0,
        "control_duplicate_data_frames_deduped": repair_cost if delivered else 0,
        "state_duplicate_data_frames_deduped": 0,
        "control_duplicate_ack_received": repair_cost if delivered else 0,
        "state_duplicate_ack_received": 0,
    }


if __name__ == "__main__":
    unittest.main()

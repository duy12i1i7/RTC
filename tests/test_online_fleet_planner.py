import unittest
from pathlib import Path
import tempfile
import threading

from fleetqox.fleet_optimizer import FleetFlowDemand, FleetOptimizerConfig
from fleetqox.live_path_controller import (
    LivePathPlanController,
    LivePathPlanControllerConfig,
    QoEConfidenceFallbackConfig,
    QoESequentialStoppingDecision,
    QoESequentialStoppingConfig,
    RobotQoEEstimate,
    RouterTelemetryAggregator,
    SubscriberDeliveryAggregator,
    SubscriberDeliveryTelemetryRecord,
    atomic_write_text,
    parse_router_telemetry_line,
    parse_subscriber_telemetry_line,
    qoe_confidence_fallback_protected_robots,
)
from fleetqox.model import FlowClass
from fleetqox.online_fleet_planner import (
    FleetTopicDemand,
    OnlineFleetPathPlanner,
    OnlineFleetPlannerConfig,
    PathObservation,
    optimizer_payload_from_plan,
)
from scripts.run_online_fleet_plan_probe import run_probe
from scripts.run_rmw_docker_router_multi_robot_budgeted_fleet_plan_probe import (
    build_budgeted_plan,
    build_qoe_feedback_controller,
    fallback_repair_summary,
    recovery_window_summary,
)


class OnlineFleetPathPlannerTest(unittest.TestCase):
    def test_qoe_sequential_stopping_separates_budget_boundary(self) -> None:
        aggregator = SubscriberDeliveryAggregator()
        for sequence in range(1, 4):
            for index in range(4):
                aggregator.ingest(
                    SubscriberDeliveryTelemetryRecord(
                        robot_id=f"robot_{index:04d}",
                        topic=f"/robot_{index:04d}/control",
                        sequence_number=sequence,
                        latency_ms=100.0 if index < 2 else 20.0,
                        deadline_ms=200.0,
                    )
                )

        decision = aggregator.sequential_stopping_decision(
            robot_ids=[f"robot_{index:04d}" for index in range(4)],
            protected_robot_budget=2,
            config=QoESequentialStoppingConfig(),
        )

        self.assertTrue(decision.should_stop)
        self.assertTrue(decision.confidence_separated)
        self.assertEqual(
            decision.candidate_protected_robots,
            ("robot_0000", "robot_0001"),
        )
        self.assertGreater(decision.boundary_gap, decision.required_gap)
        self.assertEqual(decision.min_sample_count, 3)

    def test_qoe_sequential_stopping_uses_max_sample_fallback(self) -> None:
        aggregator = SubscriberDeliveryAggregator()
        config = QoESequentialStoppingConfig(
            min_samples_per_robot=2,
            max_samples_per_robot=3,
            min_sample_stddev=0.02,
            separation_margin=0.05,
        )
        for sequence in range(1, 3):
            for index in range(2):
                aggregator.ingest(
                    SubscriberDeliveryTelemetryRecord(
                        robot_id=f"robot_{index:04d}",
                        topic="/control",
                        sequence_number=sequence,
                        latency_ms=50.0,
                        deadline_ms=100.0,
                    )
                )
        collecting = aggregator.sequential_stopping_decision(
            robot_ids=["robot_0000", "robot_0001"],
            protected_robot_budget=1,
            config=config,
        )
        self.assertFalse(collecting.should_stop)

        for index in range(2):
            aggregator.ingest(
                SubscriberDeliveryTelemetryRecord(
                    robot_id=f"robot_{index:04d}",
                    topic="/control",
                    sequence_number=3,
                    latency_ms=50.0,
                    deadline_ms=100.0,
                )
            )
        fallback = aggregator.sequential_stopping_decision(
            robot_ids=["robot_0000", "robot_0001"],
            protected_robot_budget=1,
            config=config,
        )
        self.assertTrue(fallback.should_stop)
        self.assertFalse(fallback.confidence_separated)
        self.assertIn("maximum samples", fallback.reason)

    def test_qoe_confidence_fallback_selects_union_when_budget_escalates(self) -> None:
        decision = QoESequentialStoppingDecision(
            should_stop=True,
            confidence_separated=False,
            reason="maximum samples reached without confidence separation",
            candidate_protected_robots=("robot_0002", "robot_0003"),
            previous_protected_robots=("robot_0000", "robot_0001"),
            boundary_gap=-0.02,
            required_gap=0.02,
            min_sample_count=5,
            max_sample_count=5,
            estimates=(
                RobotQoEEstimate("robot_0000", 5, 0.58, 0.01, 0.06, 0.52, 0.64),
                RobotQoEEstimate("robot_0001", 5, 0.59, 0.01, 0.06, 0.53, 0.65),
                RobotQoEEstimate("robot_0002", 5, 0.56, 0.01, 0.06, 0.50, 0.62),
                RobotQoEEstimate("robot_0003", 5, 0.57, 0.01, 0.06, 0.51, 0.63),
            ),
        )

        selected = qoe_confidence_fallback_protected_robots(
            decision,
            protected_robot_budget=2,
            config=QoEConfidenceFallbackConfig(max_extra_protected_robots=2),
        )

        self.assertEqual(
            selected,
            ("robot_0000", "robot_0001", "robot_0002", "robot_0003"),
        )

    def test_qoe_confidence_fallback_prioritizes_missing_telemetry(self) -> None:
        decision = QoESequentialStoppingDecision(
            should_stop=False,
            confidence_separated=False,
            reason="collect more subscriber QoE samples",
            candidate_protected_robots=("robot_0000", "robot_0001"),
            previous_protected_robots=(),
            boundary_gap=-0.10,
            required_gap=0.01,
            min_sample_count=3,
            max_sample_count=5,
            estimates=(
                RobotQoEEstimate("robot_0000", 5, 0.70, 0.01, 0.03, 0.67, 0.73),
                RobotQoEEstimate("robot_0001", 5, 0.71, 0.01, 0.03, 0.68, 0.74),
                RobotQoEEstimate("robot_0002", 3, 0.96, 0.01, 0.04, 0.92, 1.00),
                RobotQoEEstimate("robot_0003", 3, 0.97, 0.01, 0.04, 0.93, 1.00),
            ),
        )

        selected = qoe_confidence_fallback_protected_robots(
            decision,
            protected_robot_budget=2,
            config=QoEConfidenceFallbackConfig(),
        )

        self.assertEqual(selected, ("robot_0002", "robot_0003"))

    def test_live_controller_writes_conservative_qoe_fallback_plan(self) -> None:
        topics = [f"/robot_{index:04d}/cmd_vel" for index in range(4)]
        demands = tuple(
            FleetTopicDemand(
                topic,
                FleetFlowDemand(
                    flow_id=f"robot_{index:04d}/control",
                    robot_id=f"robot_{index:04d}",
                    flow_class=FlowClass.CONTROL,
                    deadline_ms=100.0,
                    payload_bytes=700,
                    rate_hz=20.0,
                    criticality=1.0,
                ),
            )
            for index, topic in enumerate(topics)
        )
        decision = QoESequentialStoppingDecision(
            should_stop=True,
            confidence_separated=False,
            reason="maximum samples reached without confidence separation",
            candidate_protected_robots=("robot_0002", "robot_0003"),
            previous_protected_robots=("robot_0000", "robot_0001"),
            boundary_gap=-0.02,
            required_gap=0.02,
            min_sample_count=5,
            max_sample_count=5,
            estimates=(
                RobotQoEEstimate("robot_0000", 5, 0.58, 0.01, 0.06, 0.52, 0.64),
                RobotQoEEstimate("robot_0001", 5, 0.59, 0.01, 0.06, 0.53, 0.65),
                RobotQoEEstimate("robot_0002", 5, 0.56, 0.01, 0.06, 0.50, 0.62),
                RobotQoEEstimate("robot_0003", 5, 0.57, 0.01, 0.06, 0.51, 0.63),
            ),
        )
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            controller = LivePathPlanController(
                LivePathPlanControllerConfig(
                    plan_file=root / "plan.txt",
                    telemetry_files=(),
                    demands=demands,
                    seed_observations=(
                        PathObservation(
                            "backup_5g",
                            latency_ms=24.0,
                            jitter_ms=5.0,
                            loss=0.02,
                            failure_domain="private_5g_core",
                        ),
                        PathObservation(
                            "primary_wifi",
                            latency_ms=95.0,
                            jitter_ms=20.0,
                            loss=0.08,
                            failure_domain="warehouse_wifi",
                        ),
                    ),
                    optimizer=FleetOptimizerConfig(
                        capacity_bytes_per_tick=4 * 700 + 2 * 700,
                        redundancy_budget_bytes_per_tick=2 * 700,
                        redundant_deadline_ms=100.0,
                        redundancy_risk_threshold=0.0,
                        require_failure_domain_diversity=True,
                    ),
                )
            )

            fallback = controller.apply_qoe_confidence_fallback(
                decision=decision,
                protected_robot_budget=2,
                config=QoEConfidenceFallbackConfig(max_extra_protected_robots=2),
            )

            self.assertTrue(fallback.applied)
            self.assertEqual(fallback.extra_protected_robot_count, 2)
            self.assertEqual(
                fallback.protected_robots,
                ("robot_0000", "robot_0001", "robot_0002", "robot_0003"),
            )
            self.assertEqual(
                [
                    decision.selected_paths
                    for decision in fallback.plan.topic_decisions
                ],
                [
                    ("backup_5g", "primary_wifi"),
                    ("backup_5g", "primary_wifi"),
                    ("backup_5g", "primary_wifi"),
                    ("backup_5g", "primary_wifi"),
                ],
            )
            self.assertEqual(
                root.joinpath("plan.txt").read_text(encoding="utf-8").strip(),
                fallback.plan.path_plan_env,
            )

    def test_recovery_window_summary_tracks_missing_and_late_sequences(self) -> None:
        summary = recovery_window_summary(
            [
                {
                    "robot_id": "robot_0000",
                    "delivery_telemetry": [
                        {
                            "source_sequence_number": 6,
                            "deadline_missed": False,
                            "latency_ms": 40.0,
                        },
                        {
                            "source_sequence_number": 7,
                            "deadline_missed": False,
                            "latency_ms": 42.0,
                        },
                    ],
                },
                {
                    "robot_id": "robot_0001",
                    "delivery_telemetry": [
                        {
                            "source_sequence_number": 6,
                            "deadline_missed": True,
                            "latency_ms": 300.0,
                        },
                    ],
                },
            ],
            [6, 7],
        )

        self.assertEqual(summary["status"], "failed")
        self.assertEqual(summary["robots_ok"], 1)
        self.assertEqual(summary["missing_robot_count"], 1)
        self.assertEqual(summary["max_latency_ms"], 300.0)
        self.assertEqual(summary["robots"][0]["status"], "ok")
        self.assertEqual(summary["robots"][1]["late_sequences"], [6])
        self.assertEqual(summary["robots"][1]["missing_sequences"], [7])

    def test_fallback_repair_summary_classifies_targeted_repair_evidence(self) -> None:
        summary = fallback_repair_summary(
            [
                {
                    "robot_id": "robot_0000",
                    "publisher": {"nack_retransmissions": 2},
                    "subscriber": {
                        "ack_nack_sent": 4,
                        "idle_repair_ack_nack_sent": 1,
                    },
                    "delivery_telemetry": [
                        {
                            "source_sequence_number": 1,
                            "deadline_missed": False,
                        },
                        {
                            "source_sequence_number": 2,
                            "deadline_missed": False,
                        },
                    ],
                },
                {
                    "robot_id": "robot_0001",
                    "publisher": {"nack_retransmissions": 1},
                    "subscriber": {
                        "ack_nack_sent": 3,
                        "idle_repair_ack_nack_sent": 0,
                    },
                    "delivery_telemetry": [
                        {
                            "source_sequence_number": 1,
                            "deadline_missed": True,
                        },
                    ],
                },
                {
                    "robot_id": "robot_0002",
                    "publisher": {"nack_retransmissions": 0},
                    "subscriber": {
                        "ack_nack_sent": 1,
                        "idle_repair_ack_nack_sent": 0,
                    },
                    "delivery_telemetry": [
                        {
                            "source_sequence_number": 1,
                            "deadline_missed": False,
                        },
                    ],
                },
            ],
            [1, 2],
        )

        self.assertEqual(summary["status"], "unresolved")
        self.assertEqual(summary["deadline_ok_robot_count"], 1)
        self.assertEqual(summary["delivered_robot_count"], 1)
        self.assertEqual(summary["unresolved_robot_count"], 1)
        self.assertEqual(summary["explicit_candidate_count"], 3)
        self.assertEqual(summary["missing_sequence_count"], 2)
        self.assertEqual(summary["late_sequence_count"], 1)
        self.assertEqual(summary["repair_evidence_robot_count"], 2)
        self.assertEqual(summary["nack_retransmission_count"], 3)
        self.assertEqual(summary["idle_repair_ack_nack_count"], 1)
        self.assertEqual(summary["robots"][0]["status"], "repaired_on_time")
        self.assertEqual(summary["robots"][1]["status"], "unresolved")
        self.assertEqual(summary["robots"][1]["late_sequences"], [1])
        self.assertEqual(summary["robots"][1]["missing_sequences"], [2])
        self.assertEqual(summary["robots"][2]["status"], "unresolved")

    def test_atomic_write_text_uses_unique_temp_files_under_concurrency(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "plan.txt"
            errors: list[BaseException] = []

            def writer(index: int) -> None:
                try:
                    atomic_write_text(path, f"plan-{index}\n")
                except BaseException as exc:  # pragma: no cover - test diagnostic path
                    errors.append(exc)

            threads = [threading.Thread(target=writer, args=(index,)) for index in range(32)]
            for thread in threads:
                thread.start()
            for thread in threads:
                thread.join()

            self.assertEqual(errors, [])
            self.assertRegex(path.read_text(encoding="utf-8"), r"^plan-\d+\n$")

    def test_path_observation_derives_qos_telemetry(self) -> None:
        telemetry = PathObservation(
            "primary_wifi",
            latency_ms=30.0,
            jitter_ms=7.0,
            sent_frames=10,
            delivered_frames=7,
            nack_frames=2,
            deadline_miss_frames=3,
            bytes_sent=40_000,
            capacity_bytes=100_000,
            failure_domain="wifi_ap_a",
        ).to_telemetry()

        self.assertEqual(telemetry.path_id, "primary_wifi")
        self.assertAlmostEqual(telemetry.loss, 0.3)
        self.assertAlmostEqual(telemetry.nack_rate, 0.2)
        self.assertAlmostEqual(telemetry.deadline_miss_ratio, 0.3)
        self.assertAlmostEqual(telemetry.bandwidth_utilization, 0.4)
        self.assertEqual(telemetry.failure_domain, "wifi_ap_a")

    def test_online_plan_preserves_failure_domain_and_avoids_correlated_paths(self) -> None:
        planner = OnlineFleetPathPlanner(
            OnlineFleetPlannerConfig(
                optimizer=FleetOptimizerConfig(
                    capacity_bytes_per_tick=10_000,
                    redundant_deadline_ms=35.0,
                    redundancy_risk_threshold=0.0,
                ),
                telemetry_alpha=0.5,
                min_dwell_ticks=0,
            )
        )
        demand = FleetTopicDemand(
            "/robot_0006/cmd_vel",
            FleetFlowDemand(
                flow_id="robot_0006/cmd_vel",
                robot_id="robot_0006",
                flow_class=FlowClass.CONTROL,
                deadline_ms=30.0,
                payload_bytes=700,
                rate_hz=20.0,
                criticality=1.0,
            ),
        )

        first = planner.update(
            tick=0,
            observations=[
                PathObservation("wifi_primary", 10.0, 1.0, loss=0.02, failure_domain="ap_a"),
                PathObservation("wifi_backup", 12.0, 1.0, loss=0.02, failure_domain="ap_a"),
                PathObservation("private_5g", 20.0, 2.0, loss=0.02, failure_domain="ran_b"),
            ],
            demands=[demand],
        )
        second = planner.update(
            tick=1,
            observations=[
                PathObservation("wifi_primary", 14.0, 2.0, loss=0.03),
                PathObservation("wifi_backup", 15.0, 2.0, loss=0.03),
                PathObservation("private_5g", 22.0, 3.0, loss=0.03),
            ],
            demands=[demand],
        )

        self.assertEqual(first.path_plan_env, "/robot_0006/cmd_vel=wifi_primary+private_5g")
        self.assertEqual(second.path_plan_env, "/robot_0006/cmd_vel=wifi_primary+private_5g")
        self.assertEqual(
            {path.path_id: path.failure_domain for path in second.path_telemetry},
            {"private_5g": "ran_b", "wifi_backup": "ap_a", "wifi_primary": "ap_a"},
        )
        self.assertEqual(
            {path["path_id"]: path["failure_domain"] for path in second.as_dict()["path_telemetry"]},
            {"private_5g": "ran_b", "wifi_backup": "ap_a", "wifi_primary": "ap_a"},
        )

    def test_online_plan_switches_to_redundant_paths_when_primary_degrades(self) -> None:
        planner = OnlineFleetPathPlanner(
            OnlineFleetPlannerConfig(
                optimizer=FleetOptimizerConfig(
                    capacity_bytes_per_tick=10_000,
                    redundant_deadline_ms=35.0,
                    redundancy_risk_threshold=1.0,
                ),
                telemetry_alpha=0.45,
                min_dwell_ticks=3,
                switch_score_margin=0.25,
            )
        )
        demand = FleetTopicDemand(
            "/robot_0001/cmd_vel",
            FleetFlowDemand(
                flow_id="robot_0001/cmd_vel",
                robot_id="robot_0001",
                flow_class=FlowClass.CONTROL,
                deadline_ms=30.0,
                payload_bytes=700,
                rate_hz=20.0,
                criticality=1.0,
            ),
        )

        first = planner.update(
            tick=0,
            observations=[
                PathObservation("primary_wifi", 10.0, 1.0, sent_frames=100, delivered_frames=99, nack_frames=1),
                PathObservation("backup_5g", 24.0, 5.0, sent_frames=100, delivered_frames=97, nack_frames=3),
            ],
            demands=[demand],
        )
        second = planner.update(
            tick=1,
            observations=[
                PathObservation(
                    "primary_wifi",
                    80.0,
                    20.0,
                    sent_frames=100,
                    delivered_frames=80,
                    nack_frames=20,
                    deadline_miss_frames=40,
                    bytes_sent=160_000,
                    capacity_bytes=200_000,
                ),
                PathObservation(
                    "backup_5g",
                    22.0,
                    4.0,
                    sent_frames=100,
                    delivered_frames=96,
                    nack_frames=3,
                    deadline_miss_frames=4,
                    bytes_sent=80_000,
                    capacity_bytes=200_000,
                ),
            ],
            demands=[demand],
        )

        self.assertEqual(first.path_plan_env, "/robot_0001/cmd_vel=primary_wifi")
        self.assertEqual(second.path_plan_env, "/robot_0001/cmd_vel=backup_5g+primary_wifi")
        self.assertEqual(second.changed_topics, ("/robot_0001/cmd_vel",))
        self.assertEqual(second.topic_decisions[0].mode, "redundant")

    def test_hysteresis_holds_previous_paths_for_small_short_lived_changes(self) -> None:
        planner = OnlineFleetPathPlanner(
            OnlineFleetPlannerConfig(
                optimizer=FleetOptimizerConfig(capacity_bytes_per_tick=10_000),
                telemetry_alpha=1.0,
                min_dwell_ticks=5,
                switch_score_margin=10.0,
                emergency_score_margin=10.0,
            )
        )
        demand = FleetTopicDemand(
            "/robot_0002/odom",
            FleetFlowDemand(
                flow_id="robot_0002/odom",
                robot_id="robot_0002",
                flow_class=FlowClass.STATE,
                deadline_ms=120.0,
                payload_bytes=900,
                rate_hz=10.0,
                criticality=0.4,
            ),
        )

        planner.update(
            tick=0,
            observations=[
                PathObservation("primary_wifi", 20.0, 2.0, sent_frames=100, delivered_frames=98),
                PathObservation("backup_5g", 30.0, 2.0, sent_frames=100, delivered_frames=98),
            ],
            demands=[demand],
        )
        held = planner.update(
            tick=1,
            observations=[
                PathObservation("primary_wifi", 40.0, 4.0, sent_frames=100, delivered_frames=97),
                PathObservation("backup_5g", 30.0, 2.0, sent_frames=100, delivered_frames=98),
            ],
            demands=[demand],
        )

        self.assertEqual(held.path_plan_env, "/robot_0002/odom=primary_wifi")
        self.assertTrue(held.topic_decisions[0].held_by_dwell)
        self.assertEqual(held.topic_decisions[0].optimizer_selected_paths, ("backup_5g",))

    def test_plan_exports_sidecar_optimizer_payload_shape(self) -> None:
        planner = OnlineFleetPathPlanner()
        demand = FleetTopicDemand(
            "/robot_0003/state",
            FleetFlowDemand(
                flow_id="robot_0003/state",
                robot_id="robot_0003",
                flow_class=FlowClass.STATE,
                deadline_ms=100.0,
                payload_bytes=800,
                rate_hz=10.0,
                criticality=0.5,
            ),
        )

        plan = planner.update(
            tick=0,
            observations=[PathObservation("primary_wifi", 18.0, 2.0, sent_frames=100, delivered_frames=99)],
            demands=[demand],
        )
        payload = optimizer_payload_from_plan(
            plan,
            path_targets={"primary_wifi": {"udp_host": "127.0.0.1", "udp_port": 19101}},
        )

        self.assertEqual(payload["schema_version"], "fleetrmw.online_fleet_path_plan.v1")
        self.assertEqual(payload["paths"][0]["path_id"], "primary_wifi")
        self.assertEqual(payload["path_targets"]["primary_wifi"]["udp_port"], 19101)

    def test_online_probe_reports_expected_path_sequence(self) -> None:
        summary = run_probe(topic="/robot_0000/cmd_vel")

        self.assertEqual(summary["schema_version"], "fleetrmw.online_fleet_path_plan_probe.v1")
        self.assertEqual(summary["status"], "ok")
        self.assertEqual(
            summary["path_plans"],
            [
                "/robot_0000/cmd_vel=primary_wifi",
                "/robot_0000/cmd_vel=backup_5g+primary_wifi",
                "/robot_0000/cmd_vel=backup_5g+primary_wifi",
                "/robot_0000/cmd_vel=backup_5g",
            ],
        )
        self.assertEqual(summary["held_ticks"], [2])

    def test_budgeted_plan_protects_fairness_debt_robots_only(self) -> None:
        topics = [f"/robot_{index:04d}/cmd_vel" for index in range(4)]

        plan = build_budgeted_plan(
            robot_count=4,
            topics=topics,
            deadline_ms=100,
            protected_robot_budget=2,
        )

        decisions = {decision.robot_id: decision for decision in plan.topic_decisions}
        self.assertEqual(decisions["robot_0000"].selected_paths, ("backup_5g", "primary_wifi"))
        self.assertEqual(decisions["robot_0001"].selected_paths, ("backup_5g", "primary_wifi"))
        self.assertEqual(decisions["robot_0002"].selected_paths, ("backup_5g",))
        self.assertEqual(decisions["robot_0003"].selected_paths, ("backup_5g",))
        self.assertEqual(sum(len(item.selected_paths) for item in plan.topic_decisions), 6)
        self.assertEqual(
            {path.path_id: path.failure_domain for path in plan.path_telemetry},
            {"backup_5g": "private_5g_core", "primary_wifi": "warehouse_wifi"},
        )

    def test_qoe_feedback_controller_allocates_budget_from_measured_latency(self) -> None:
        topics = [f"/robot_{index:04d}/cmd_vel" for index in range(4)]
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            telemetry_paths = [root / f"robot-{index}.jsonl" for index in range(4)]
            for index, path in enumerate(telemetry_paths):
                latency_ms = 125.0 if index < 2 else 25.0
                path.write_text(
                    '{"schema_version":"fleetrmw.subscriber_delivery_telemetry.v1",'
                    f'"robot_id":"robot_{index:04d}","topic":"{topics[index]}",'
                    f'"source_sequence_number":1,"latency_ms":{latency_ms},'
                    '"deadline_ms":160,"deadline_missed":false,'
                    '"delivered":true,"duplicate":false}\n',
                    encoding="utf-8",
                )
            controller = build_qoe_feedback_controller(
                plan_file=root / "plan.txt",
                telemetry_paths=telemetry_paths,
                topics=topics,
                deadline_ms=160,
                protected_robot_budget=2,
            )

            plan = controller.poll_once()
            states = {
                row["robot_id"]: row for row in controller.summary()["robot_states"]
            }

            self.assertEqual(
                [decision.robot_id for decision in plan.topic_decisions if decision.mode == "redundant"],
                ["robot_0000", "robot_0001"],
            )
            self.assertLess(states["robot_0000"]["qoe_score"], states["robot_0002"]["qoe_score"])
            self.assertEqual(plan.path_telemetry[0].failure_domain, "private_5g_core")

    def test_router_telemetry_aggregates_into_path_observation(self) -> None:
        record = parse_router_telemetry_line(
            '{"schema_version":"fleetrmw.router_path_telemetry.v1",'
            '"path_id":"primary_wifi","topic":"/robot_0004/cmd_vel",'
            '"source_sequence_number":7,"latency_ms":70,"jitter_ms":18,'
            '"loss":0.2,"nack_rate":0.12,"deadline_miss_ratio":0.30,'
            '"bytes_sent":800,"capacity_bytes":1000,"failure_domain":"warehouse_ap"}'
        )

        self.assertIsNotNone(record)
        aggregator = RouterTelemetryAggregator(
            [PathObservation("backup_5g", 20.0, 3.0, loss=0.02)]
        )
        aggregator.ingest(record)  # type: ignore[arg-type]
        observations = {item.path_id: item.to_telemetry() for item in aggregator.observations()}

        self.assertEqual(set(observations), {"primary_wifi", "backup_5g"})
        self.assertAlmostEqual(observations["primary_wifi"].loss, 0.2)
        self.assertAlmostEqual(observations["primary_wifi"].deadline_miss_ratio, 0.30)
        self.assertEqual(observations["primary_wifi"].failure_domain, "warehouse_ap")

    def test_router_telemetry_preserves_seed_failure_domain_when_record_omits_it(self) -> None:
        aggregator = RouterTelemetryAggregator(
            [PathObservation("primary_wifi", 10.0, 1.0, loss=0.01, failure_domain="ap_a")]
        )
        record = parse_router_telemetry_line(
            '{"schema_version":"fleetrmw.router_path_telemetry.v1",'
            '"path_id":"primary_wifi","topic":"/robot_0000/cmd_vel",'
            '"source_sequence_number":1,"latency_ms":45,"jitter_ms":8}'
        )

        aggregator.ingest(record)  # type: ignore[arg-type]
        observation = aggregator.observations()[0]

        self.assertEqual(observation.failure_domain, "ap_a")

    def test_subscriber_telemetry_updates_robot_qoe_state(self) -> None:
        record = parse_subscriber_telemetry_line(
            '{"schema_version":"fleetrmw.subscriber_delivery_telemetry.v1",'
            '"robot_id":"robot_0004","topic":"/robot_0004/cmd_vel",'
            '"source_sequence_number":7,"latency_ms":45,"deadline_ms":30,'
            '"deadline_missed":true,"delivered":true,"duplicate":false}'
        )

        self.assertIsNotNone(record)
        demand = FleetTopicDemand(
            "/robot_0004/cmd_vel",
            FleetFlowDemand(
                flow_id="robot_0004/cmd_vel",
                robot_id="robot_0004",
                flow_class=FlowClass.CONTROL,
                deadline_ms=30.0,
                payload_bytes=700,
                rate_hz=20.0,
                criticality=1.0,
            ),
        )
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            subscriber_file = tmp_path / "subscriber.jsonl"
            subscriber_file.write_text(
                '{"schema_version":"fleetrmw.subscriber_delivery_telemetry.v1",'
                '"robot_id":"robot_0004","topic":"/robot_0004/cmd_vel",'
                '"source_sequence_number":7,"latency_ms":45,"deadline_ms":30,'
                '"deadline_missed":true,"delivered":true,"duplicate":false}\n',
                encoding="utf-8",
            )
            controller = LivePathPlanController(
                LivePathPlanControllerConfig(
                    plan_file=tmp_path / "plan.txt",
                    telemetry_files=(),
                    subscriber_telemetry_files=(subscriber_file,),
                    demands=(demand,),
                    seed_observations=(
                        PathObservation("primary_wifi", 12.0, 1.0, loss=0.01),
                    ),
                    optimizer=FleetOptimizerConfig(capacity_bytes_per_tick=10_000),
                )
            )

            controller.poll_once()
            summary = controller.summary()

            self.assertEqual(summary["subscriber_record_count"], 1)
            self.assertEqual(summary["robot_states"][0]["robot_id"], "robot_0004")
            self.assertEqual(summary["robot_states"][0]["deadline_miss_ratio"], 1.0)
            self.assertLess(summary["robot_states"][0]["qoe_score"], 1.0)

    def test_live_path_controller_writes_plan_from_router_telemetry(self) -> None:
        demand = FleetTopicDemand(
            "/robot_0005/cmd_vel",
            FleetFlowDemand(
                flow_id="robot_0005/cmd_vel",
                robot_id="robot_0005",
                flow_class=FlowClass.CONTROL,
                deadline_ms=30.0,
                payload_bytes=700,
                rate_hz=20.0,
                criticality=1.0,
            ),
        )
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            telemetry = tmp_path / "router.jsonl"
            plan_file = tmp_path / "plan.txt"
            controller = LivePathPlanController(
                LivePathPlanControllerConfig(
                    plan_file=plan_file,
                    telemetry_files=(telemetry,),
                    demands=(demand,),
                    seed_observations=(
                        PathObservation("primary_wifi", 10.0, 1.0, loss=0.01, bandwidth_utilization=0.10),
                        PathObservation("backup_5g", 24.0, 5.0, loss=0.03, bandwidth_utilization=0.42),
                    ),
                    optimizer=FleetOptimizerConfig(
                        capacity_bytes_per_tick=10_000,
                        redundant_deadline_ms=35.0,
                        redundancy_risk_threshold=1.0,
                    ),
                    telemetry_alpha=1.0,
                    min_dwell_ticks=0,
                )
            )

            first = controller.poll_once()
            telemetry.write_text(
                '{"schema_version":"fleetrmw.router_path_telemetry.v1",'
                '"path_id":"primary_wifi","topic":"/robot_0005/cmd_vel",'
                '"source_sequence_number":1,"latency_ms":80,"jitter_ms":24,'
                '"loss":0.22,"nack_rate":0.18,"deadline_miss_ratio":0.35,'
                '"bytes_sent":900,"capacity_bytes":1000}\n',
                encoding="utf-8",
            )
            second = controller.poll_once()

            self.assertEqual(first.path_plan_env, "/robot_0005/cmd_vel=primary_wifi")
            self.assertEqual(second.path_plan_env, "/robot_0005/cmd_vel=backup_5g+primary_wifi")
            self.assertEqual(plan_file.read_text(encoding="utf-8").strip(), second.path_plan_env)
            self.assertEqual(controller.record_count, 1)

    def test_live_controller_new_epoch_uses_only_new_subscriber_samples(self) -> None:
        demand = FleetTopicDemand(
            "/robot_0007/cmd_vel",
            FleetFlowDemand(
                flow_id="robot_0007/cmd_vel",
                robot_id="robot_0007",
                flow_class=FlowClass.CONTROL,
                deadline_ms=100.0,
                payload_bytes=700,
                rate_hz=20.0,
                criticality=1.0,
            ),
        )
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            telemetry = root / "subscriber.jsonl"
            telemetry.write_text(
                '{"schema_version":"fleetrmw.subscriber_delivery_telemetry.v1",'
                '"robot_id":"robot_0007","source_sequence_number":1,'
                '"latency_ms":90,"deadline_ms":100,"deadline_missed":false}\n',
                encoding="utf-8",
            )
            controller = LivePathPlanController(
                LivePathPlanControllerConfig(
                    plan_file=root / "plan.txt",
                    telemetry_files=(),
                    subscriber_telemetry_files=(telemetry,),
                    demands=(demand,),
                    seed_observations=(
                        PathObservation("primary_wifi", 10.0, 1.0, loss=0.01),
                    ),
                )
            )

            controller.poll_once()
            first_qoe = controller.summary()["robot_states"][0]["qoe_score"]
            controller.start_new_epoch()
            with telemetry.open("a", encoding="utf-8") as handle:
                handle.write(
                    '{"schema_version":"fleetrmw.subscriber_delivery_telemetry.v1",'
                    '"robot_id":"robot_0007","source_sequence_number":2,'
                    '"latency_ms":10,"deadline_ms":100,"deadline_missed":false}\n'
                )
            controller.poll_once()
            second_qoe = controller.summary()["robot_states"][0]["qoe_score"]

            self.assertLess(first_qoe, second_qoe)
            self.assertAlmostEqual(second_qoe, 0.95)


if __name__ == "__main__":
    unittest.main()

import unittest
from pathlib import Path
import tempfile
import threading

from fleetqox.fleet_optimizer import FleetFlowDemand, FleetOptimizerConfig
from fleetqox.live_path_controller import (
    LivePathPlanController,
    LivePathPlanControllerConfig,
    RouterTelemetryAggregator,
    atomic_write_text,
    parse_router_telemetry_line,
    parse_subscriber_telemetry_line,
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


class OnlineFleetPathPlannerTest(unittest.TestCase):
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
        ).to_telemetry()

        self.assertEqual(telemetry.path_id, "primary_wifi")
        self.assertAlmostEqual(telemetry.loss, 0.3)
        self.assertAlmostEqual(telemetry.nack_rate, 0.2)
        self.assertAlmostEqual(telemetry.deadline_miss_ratio, 0.3)
        self.assertAlmostEqual(telemetry.bandwidth_utilization, 0.4)

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

    def test_router_telemetry_aggregates_into_path_observation(self) -> None:
        record = parse_router_telemetry_line(
            '{"schema_version":"fleetrmw.router_path_telemetry.v1",'
            '"path_id":"primary_wifi","topic":"/robot_0004/cmd_vel",'
            '"source_sequence_number":7,"latency_ms":70,"jitter_ms":18,'
            '"loss":0.2,"nack_rate":0.12,"deadline_miss_ratio":0.30,'
            '"bytes_sent":800,"capacity_bytes":1000}'
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


if __name__ == "__main__":
    unittest.main()

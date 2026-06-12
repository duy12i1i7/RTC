import unittest

from fleetqox.fleet_optimizer import (
    FleetFlowDemand,
    FleetOptimizerConfig,
    FleetQoEPathOptimizer,
    PathTelemetry,
    RobotQoEState,
    TransportMode,
    static_primary_decisions,
    summarize_decisions,
)
from fleetqox.model import FlowClass
from scripts.run_fleet_optimizer_probe import run_probe
from scripts.run_fleet_optimizer_redundancy_budget_probe import (
    run_probe as run_redundancy_budget_probe,
)


class FleetOptimizerTest(unittest.TestCase):
    def test_selects_lower_risk_backup_for_unicast(self) -> None:
        optimizer = FleetQoEPathOptimizer(FleetOptimizerConfig(capacity_bytes_per_tick=10_000))
        flow = FleetFlowDemand(
            flow_id="robot_0001/odom",
            robot_id="robot_0001",
            flow_class=FlowClass.STATE,
            deadline_ms=120.0,
            payload_bytes=800,
            rate_hz=10.0,
            criticality=0.6,
        )
        paths = [
            PathTelemetry("primary_wifi", latency_ms=80.0, jitter_ms=30.0, loss=0.2, nack_rate=0.2),
            PathTelemetry("backup_5g", latency_ms=25.0, jitter_ms=4.0, loss=0.02, nack_rate=0.02),
        ]

        decision = optimizer.decide([flow], paths)[0]

        self.assertEqual(decision.mode, TransportMode.UNICAST)
        self.assertEqual(decision.selected_paths, ("backup_5g",))

    def test_urgent_high_risk_control_uses_redundancy(self) -> None:
        optimizer = FleetQoEPathOptimizer(
            FleetOptimizerConfig(
                capacity_bytes_per_tick=10_000,
                redundant_deadline_ms=35.0,
                redundancy_risk_threshold=1.0,
            )
        )
        flow = FleetFlowDemand(
            flow_id="robot_0001/cmd_vel",
            robot_id="robot_0001",
            flow_class=FlowClass.CONTROL,
            deadline_ms=30.0,
            payload_bytes=700,
            rate_hz=20.0,
            criticality=1.0,
        )
        paths = [
            PathTelemetry("wifi_a", latency_ms=36.0, jitter_ms=12.0, loss=0.08, nack_rate=0.08),
            PathTelemetry("wifi_b", latency_ms=34.0, jitter_ms=10.0, loss=0.07, nack_rate=0.07),
        ]

        decision = optimizer.decide([flow], paths)[0]

        self.assertEqual(decision.mode, TransportMode.REDUNDANT)
        self.assertEqual(len(decision.selected_paths), 2)

    def test_robot_fairness_debt_changes_admission_order_under_capacity(self) -> None:
        optimizer = FleetQoEPathOptimizer(FleetOptimizerConfig(capacity_bytes_per_tick=900))
        flows = [
            FleetFlowDemand(
                flow_id="robot_good/cmd_vel",
                robot_id="robot_good",
                flow_class=FlowClass.CONTROL,
                deadline_ms=40.0,
                payload_bytes=700,
                rate_hz=20.0,
                criticality=0.8,
            ),
            FleetFlowDemand(
                flow_id="robot_debt/cmd_vel",
                robot_id="robot_debt",
                flow_class=FlowClass.CONTROL,
                deadline_ms=40.0,
                payload_bytes=700,
                rate_hz=20.0,
                criticality=0.8,
            ),
        ]
        paths = [PathTelemetry("backup_5g", latency_ms=20.0, jitter_ms=3.0, loss=0.02)]
        states = [
            RobotQoEState("robot_good", control_delivery_ratio=0.99, deadline_miss_ratio=0.0, qoe_score=0.98),
            RobotQoEState("robot_debt", control_delivery_ratio=0.82, deadline_miss_ratio=0.24, qoe_score=0.75),
        ]

        decisions = optimizer.decide(flows, paths, states)
        sent = [decision.flow_id for decision in decisions if decision.action == "send"]

        self.assertEqual(sent, ["robot_debt/cmd_vel"])

    def test_redundancy_budget_preserves_unicast_for_lower_priority_flow(self) -> None:
        optimizer = FleetQoEPathOptimizer(
            FleetOptimizerConfig(
                capacity_bytes_per_tick=2_100,
                redundant_deadline_ms=100.0,
                redundancy_risk_threshold=0.1,
                redundancy_budget_bytes_per_tick=700,
            )
        )
        flows = [
            FleetFlowDemand(
                flow_id=f"{robot_id}/cmd_vel",
                robot_id=robot_id,
                flow_class=FlowClass.CONTROL,
                deadline_ms=80.0,
                payload_bytes=700,
                rate_hz=20.0,
                criticality=1.0,
            )
            for robot_id in ("robot_debt", "robot_good")
        ]
        paths = [
            PathTelemetry(
                "wifi_primary",
                latency_ms=70.0,
                jitter_ms=20.0,
                loss=0.1,
                failure_domain="ap_a",
            ),
            PathTelemetry(
                "wifi_backup",
                latency_ms=35.0,
                jitter_ms=8.0,
                loss=0.02,
                failure_domain="ap_b",
            ),
        ]
        states = [
            RobotQoEState(
                "robot_debt",
                control_delivery_ratio=0.8,
                deadline_miss_ratio=0.2,
                qoe_score=0.75,
            ),
            RobotQoEState("robot_good"),
        ]

        decisions = {decision.robot_id: decision for decision in optimizer.decide(flows, paths, states)}

        self.assertEqual(decisions["robot_debt"].mode, TransportMode.REDUNDANT)
        self.assertEqual(decisions["robot_good"].mode, TransportMode.UNICAST)
        self.assertIn("budget exhausted", decisions["robot_good"].reason)

    def test_redundancy_avoids_correlated_failure_domains(self) -> None:
        optimizer = FleetQoEPathOptimizer(
            FleetOptimizerConfig(
                capacity_bytes_per_tick=10_000,
                redundant_deadline_ms=100.0,
                redundancy_risk_threshold=0.1,
            )
        )
        flow = FleetFlowDemand(
            flow_id="robot_0001/cmd_vel",
            robot_id="robot_0001",
            flow_class=FlowClass.CONTROL,
            deadline_ms=80.0,
            payload_bytes=700,
            rate_hz=20.0,
            criticality=1.0,
        )
        paths = [
            PathTelemetry(
                "wifi_5ghz",
                latency_ms=30.0,
                jitter_ms=6.0,
                loss=0.03,
                failure_domain="site_ap",
            ),
            PathTelemetry(
                "wifi_24ghz",
                latency_ms=32.0,
                jitter_ms=7.0,
                loss=0.04,
                failure_domain="site_ap",
            ),
            PathTelemetry(
                "private_5g",
                latency_ms=38.0,
                jitter_ms=5.0,
                loss=0.02,
                failure_domain="carrier_5g",
            ),
        ]

        decision = optimizer.decide([flow], paths)[0]

        self.assertEqual(decision.mode, TransportMode.REDUNDANT)
        self.assertIn("private_5g", decision.selected_paths)
        self.assertEqual(len(decision.selected_paths), 2)

    def test_summary_improves_over_static_primary(self) -> None:
        paths = [
            PathTelemetry("primary_wifi", latency_ms=70.0, jitter_ms=30.0, loss=0.22, nack_rate=0.2),
            PathTelemetry("backup_5g", latency_ms=22.0, jitter_ms=4.0, loss=0.03, nack_rate=0.02),
        ]
        flows = [
            FleetFlowDemand(
                flow_id="robot_0001/cmd_vel",
                robot_id="robot_0001",
                flow_class=FlowClass.CONTROL,
                deadline_ms=35.0,
                payload_bytes=700,
                rate_hz=20.0,
                criticality=1.0,
            ),
            FleetFlowDemand(
                flow_id="robot_0001/operator_view",
                robot_id="robot_0001",
                flow_class=FlowClass.HUMAN_QOE,
                deadline_ms=120.0,
                payload_bytes=2200,
                rate_hz=6.0,
                criticality=0.4,
                qoe_weight=0.9,
            ),
        ]
        optimizer = FleetQoEPathOptimizer(FleetOptimizerConfig(capacity_bytes_per_tick=10_000))
        optimized = summarize_decisions(optimizer.decide(flows, paths), flows, paths, policy="optimizer")
        static = summarize_decisions(
            static_primary_decisions(flows, "primary_wifi", capacity_bytes_per_tick=10_000),
            flows,
            paths,
            policy="static",
        )

        self.assertGreater(optimized.expected_delivery_ratio, static.expected_delivery_ratio)
        self.assertGreater(optimized.expected_deadline_success_ratio, static.expected_deadline_success_ratio)

    def test_probe_reports_optimizer_advantage(self) -> None:
        summary = run_probe(robots=8, capacity_bytes=36_000)

        self.assertEqual(summary["schema_version"], "fleetrmw.fleet_optimizer_probe.v1")
        self.assertEqual(summary["status"], "ok")
        self.assertGreater(summary["improvements"]["expected_delivery_delta"], 0.08)
        self.assertGreater(summary["optimizer"]["redundant_count"], 0)

    def test_redundancy_budget_probe_reduces_path_transmissions(self) -> None:
        summary = run_redundancy_budget_probe(
            robots=4,
            payload_bytes=700,
            protected_robot_budget=2,
        )

        self.assertEqual(summary["status"], "ok")
        self.assertEqual(summary["redundant_count"], 2)
        self.assertEqual(summary["unicast_count"], 2)
        self.assertEqual(summary["drop_count"], 0)
        self.assertEqual(summary["path_transmissions"], 6)
        self.assertEqual(summary["full_redundancy_path_transmissions"], 8)
        self.assertTrue(summary["failure_domain_diverse"])


if __name__ == "__main__":
    unittest.main()

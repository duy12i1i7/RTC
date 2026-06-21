import unittest

from fleetqox.repair_scheduler import (
    FleetRepairScheduler,
    FleetRepairSchedulerConfig,
    RepairDemand,
    RepairPath,
)


class FleetRepairSchedulerTest(unittest.TestCase):
    def test_shared_capacity_prioritizes_deadline_and_qoe_debt(self) -> None:
        scheduler = FleetRepairScheduler(
            FleetRepairSchedulerConfig(capacity_bytes=700, max_paths_per_repair=1)
        )
        paths = [RepairPath("backup_5g", latency_ms=20.0, loss=0.01)]
        demands = [
            RepairDemand(
                topic="/robot_good/control",
                robot_id="robot_good",
                publisher_id="pub-good",
                source_sequence_number=2,
                payload_bytes=700,
                remaining_deadline_ms=200.0,
                qoe_debt=0.05,
                criticality=0.8,
            ),
            RepairDemand(
                topic="/robot_debt/control",
                robot_id="robot_debt",
                publisher_id="pub-debt",
                source_sequence_number=2,
                payload_bytes=700,
                remaining_deadline_ms=70.0,
                qoe_debt=0.9,
                criticality=1.0,
            ),
        ]

        schedule = scheduler.schedule(demands, paths)
        admitted = [decision.robot_id for decision in schedule.admitted]

        self.assertEqual(admitted, ["robot_debt"])
        self.assertEqual(schedule.allocated_bytes, 700)
        self.assertIn("/robot_debt/control=backup_5g|sequences=2|attempts=1", schedule.policy_text)

    def test_multi_choice_knapsack_selects_diverse_repair_when_capacity_allows(self) -> None:
        scheduler = FleetRepairScheduler(
            FleetRepairSchedulerConfig(
                capacity_bytes=1400,
                max_admitted_repairs=1,
                max_paths_per_repair=2,
            )
        )
        paths = [
            RepairPath(
                "primary_wifi",
                latency_ms=30.0,
                loss=0.2,
                failure_domain="warehouse_wifi",
            ),
            RepairPath(
                "backup_5g",
                latency_ms=35.0,
                loss=0.02,
                failure_domain="private_5g",
            ),
        ]
        demand = RepairDemand(
            topic="/robot_0000/control",
            robot_id="robot_0000",
            publisher_id="pub-0",
            source_sequence_number=7,
            payload_bytes=700,
            remaining_deadline_ms=80.0,
            qoe_debt=0.8,
            criticality=1.0,
        )

        decision = scheduler.schedule([demand], paths).admitted[0]

        self.assertEqual(decision.selected_paths, ("backup_5g", "primary_wifi"))
        self.assertEqual(decision.allocated_bytes, 1400)
        self.assertGreater(decision.expected_success, 0.99)

    def test_failure_domain_diversity_skips_correlated_second_path(self) -> None:
        scheduler = FleetRepairScheduler(
            FleetRepairSchedulerConfig(capacity_bytes=1400, max_paths_per_repair=2)
        )
        paths = [
            RepairPath("wifi_5", 20.0, 0.02, failure_domain="site_ap"),
            RepairPath("wifi_24", 22.0, 0.03, failure_domain="site_ap"),
            RepairPath("private_5g", 28.0, 0.04, failure_domain="carrier"),
        ]
        demand = RepairDemand(
            topic="/robot_0000/control",
            robot_id="robot_0000",
            publisher_id="pub-0",
            source_sequence_number=3,
            payload_bytes=700,
            remaining_deadline_ms=100.0,
            qoe_debt=0.7,
            criticality=1.0,
        )

        decision = scheduler.schedule([demand], paths).admitted[0]

        self.assertEqual(len(decision.selected_paths), 2)
        self.assertIn("private_5g", decision.selected_paths)
        self.assertNotEqual(set(decision.selected_paths), {"wifi_5", "wifi_24"})

    def test_zero_capacity_defers_all_repairs(self) -> None:
        scheduler = FleetRepairScheduler(FleetRepairSchedulerConfig(capacity_bytes=0))
        demand = RepairDemand(
            topic="/robot_0000/control",
            robot_id="robot_0000",
            publisher_id="pub-0",
            source_sequence_number=1,
            payload_bytes=700,
            remaining_deadline_ms=100.0,
            qoe_debt=1.0,
            criticality=1.0,
        )

        schedule = scheduler.schedule(
            [demand],
            [RepairPath("backup_5g", latency_ms=20.0, loss=0.01)],
        )

        self.assertEqual(schedule.admitted, ())
        self.assertEqual(schedule.policy_text, "")
        self.assertEqual(schedule.decisions[0].action, "defer")


if __name__ == "__main__":
    unittest.main()

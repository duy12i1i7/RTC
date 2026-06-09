import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from fleetqox.sidecar_metrics import (
    analyze_sidecar_runtime,
    analyze_sidecar_runtime_by_robot,
    jain_index,
    per_robot_budget_report,
)


class SidecarMetricsTest(unittest.TestCase):
    def test_analyze_sidecar_runtime_counts_compacted_delivery(self) -> None:
        with TemporaryDirectory() as tmpdir:
            decisions = Path(tmpdir) / "decisions.jsonl"
            received = Path(tmpdir) / "received.jsonl"
            decisions.write_text(
                json.dumps(
                    {
                        "event_type": "packet",
                        "event_id": 1,
                        "policy": "fleetqox_predictive",
                        "bytes": 52,
                        "action": "send_compacted",
                        "flow_class": "control",
                    }
                )
                + "\n",
                encoding="utf-8",
            )
            received.write_text(
                json.dumps(
                    {
                        "event_id": 1,
                        "policy": "fleetqox_predictive",
                        "flow_class": "control",
                        "bytes": 52,
                        "deadline_ms": 45,
                        "latency_ms": 10,
                        "semantic_utility": 5.0,
                    }
                )
                + "\n",
                encoding="utf-8",
            )

            records = analyze_sidecar_runtime(decisions, received)

        self.assertEqual(records[0]["tx"], 1)
        self.assertEqual(records[0]["rx"], 1)
        self.assertEqual(records[0]["compacted_rx"], 1)
        self.assertEqual(records[0]["control_decisions"], 1)
        self.assertEqual(records[0]["control_rx"], 1)
        self.assertEqual(records[0]["control_delivery_ratio"], 1.0)

    def test_analyze_sidecar_runtime_counts_control_non_delivery(self) -> None:
        with TemporaryDirectory() as tmpdir:
            decisions = Path(tmpdir) / "decisions.jsonl"
            received = Path(tmpdir) / "received.jsonl"
            decisions.write_text(
                json.dumps(
                    {
                        "event_type": "decision",
                        "event_id": 1,
                        "policy": "fleetqox_predictive_profiled",
                        "bytes": 0,
                        "action": "drop",
                        "flow_class": "control",
                    }
                )
                + "\n",
                encoding="utf-8",
            )
            received.write_text("", encoding="utf-8")

            records = analyze_sidecar_runtime(decisions, received)

        self.assertEqual(records[0]["tx"], 0)
        self.assertEqual(records[0]["control_decisions"], 1)
        self.assertEqual(records[0]["control_drop_events"], 1)
        self.assertEqual(records[0]["control_non_delivery_events"], 1)
        self.assertEqual(records[0]["control_delivery_ratio"], 0.0)

    def test_analyze_sidecar_runtime_counts_control_intent_delivery(self) -> None:
        with TemporaryDirectory() as tmpdir:
            decisions = Path(tmpdir) / "decisions.jsonl"
            received = Path(tmpdir) / "received.jsonl"
            decisions.write_text(
                json.dumps(
                    {
                        "event_type": "packet",
                        "event_id": 2,
                        "policy": "fleetqox_predictive_intent",
                        "bytes": 48,
                        "action": "send_intent",
                        "flow_class": "control",
                    }
                )
                + "\n",
                encoding="utf-8",
            )
            received.write_text(
                json.dumps(
                    {
                        "event_id": 2,
                        "policy": "fleetqox_predictive_intent",
                        "flow_class": "control",
                        "bytes": 48,
                        "deadline_ms": 125,
                        "latency_ms": 80,
                        "semantic_utility": 6.0,
                    }
                )
                + "\n",
                encoding="utf-8",
            )

            records = analyze_sidecar_runtime(decisions, received)

        self.assertEqual(records[0]["intent_tx"], 1)
        self.assertEqual(records[0]["intent_rx"], 1)
        self.assertEqual(records[0]["control_delivery_ratio"], 1.0)

    def test_analyze_sidecar_runtime_deduplicates_redundant_received_event_ids(self) -> None:
        with TemporaryDirectory() as tmpdir:
            decisions = Path(tmpdir) / "decisions.jsonl"
            received = Path(tmpdir) / "received.jsonl"
            decisions.write_text(
                json.dumps(
                    {
                        "event_type": "packet",
                        "event_id": 2,
                        "policy": "fleetqox_predictive_intent",
                        "bytes": 48,
                        "action": "send_intent",
                        "wire_mode": "control_intent",
                        "flow_class": "control",
                    }
                )
                + "\n",
                encoding="utf-8",
            )
            packet = {
                "event_id": 2,
                "policy": "fleetqox_predictive_intent",
                "flow_class": "control",
                "bytes": 48,
                "deadline_ms": 125,
                "latency_ms": 80,
                "semantic_utility": 6.0,
            }
            received.write_text(
                json.dumps(packet) + "\n" + json.dumps(packet | {"latency_ms": 90}) + "\n",
                encoding="utf-8",
            )

            records = analyze_sidecar_runtime(decisions, received)

        self.assertEqual(records[0]["rx"], 1)
        self.assertEqual(records[0]["control_rx"], 1)
        self.assertEqual(records[0]["control_delivery_ratio"], 1.0)

    def test_analyze_sidecar_runtime_counts_supervisory_intent_as_intent_delivery(self) -> None:
        with TemporaryDirectory() as tmpdir:
            decisions = Path(tmpdir) / "decisions.jsonl"
            received = Path(tmpdir) / "received.jsonl"
            decisions.write_text(
                json.dumps(
                    {
                        "event_type": "packet",
                        "event_id": 3,
                        "policy": "fleetqox_semantic_contract_adaptive",
                        "bytes": 48,
                        "action": "send_supervisory_intent",
                        "flow_class": "control",
                    }
                )
                + "\n",
                encoding="utf-8",
            )
            received.write_text(
                json.dumps(
                    {
                        "event_id": 3,
                        "policy": "fleetqox_semantic_contract_adaptive",
                        "flow_class": "control",
                        "bytes": 48,
                        "deadline_ms": 260,
                        "latency_ms": 120,
                        "semantic_utility": 4.5,
                    }
                )
                + "\n",
                encoding="utf-8",
            )

            records = analyze_sidecar_runtime(decisions, received)

        self.assertEqual(records[0]["intent_tx"], 1)
        self.assertEqual(records[0]["intent_rx"], 1)
        self.assertEqual(records[0]["control_delivery_ratio"], 1.0)

    def test_analyze_sidecar_runtime_ignores_control_lease_egress_deadline_miss(self) -> None:
        with TemporaryDirectory() as tmpdir:
            decisions = Path(tmpdir) / "decisions.jsonl"
            received = Path(tmpdir) / "received.jsonl"
            decisions.write_text(
                "\n".join(
                    json.dumps(record)
                    for record in [
                        {
                            "event_type": "packet",
                            "event_id": 1,
                            "policy": "fleetqox",
                            "bytes": 48,
                            "action": "send_intent",
                            "wire_mode": "control_intent",
                            "flow_class": "control",
                        },
                        {
                            "event_type": "packet",
                            "event_id": 2,
                            "policy": "fleetqox",
                            "bytes": 128,
                            "action": "send",
                            "wire_mode": "native",
                            "flow_class": "state",
                        },
                    ]
                )
                + "\n",
                encoding="utf-8",
            )
            received.write_text(
                "\n".join(
                    json.dumps(record)
                    for record in [
                        {
                            "event_id": 1,
                            "policy": "fleetqox",
                            "flow_class": "control",
                            "bytes": 48,
                            "deadline_ms": 45,
                            "latency_ms": 120,
                            "semantic_utility": 5.0,
                        },
                        {
                            "event_id": 2,
                            "policy": "fleetqox",
                            "flow_class": "state",
                            "bytes": 128,
                            "deadline_ms": 90,
                            "latency_ms": 120,
                            "semantic_utility": 3.0,
                        },
                    ]
                )
                + "\n",
                encoding="utf-8",
            )

            records = analyze_sidecar_runtime(decisions, received)

        self.assertEqual(records[0]["rx"], 2)
        self.assertEqual(records[0]["deadline_miss_ratio"], 0.5)
        self.assertEqual(records[0]["control_starvation_events"], 0)

    def test_analyze_sidecar_runtime_by_robot_reports_fairness(self) -> None:
        with TemporaryDirectory() as tmpdir:
            decisions = Path(tmpdir) / "decisions.jsonl"
            received = Path(tmpdir) / "received.jsonl"
            decisions.write_text(
                "\n".join(
                    json.dumps(record)
                    for record in [
                        {
                            "event_type": "packet",
                            "event_id": 1,
                            "policy": "fleetqox",
                            "bytes": 48,
                            "action": "send_intent",
                            "flow_class": "control",
                            "robot_id": "robot_0000",
                        },
                        {
                            "event_type": "packet",
                            "event_id": 2,
                            "policy": "fleetqox",
                            "bytes": 48,
                            "action": "send_intent",
                            "flow_class": "control",
                            "robot_id": "robot_0001",
                        },
                        {
                            "event_type": "decision",
                            "event_id": 3,
                            "policy": "fleetqox",
                            "bytes": 0,
                            "action": "drop",
                            "flow_class": "control",
                            "robot_id": "robot_0001",
                        },
                        {
                            "event_type": "packet",
                            "event_id": 4,
                            "policy": "fleetqox",
                            "bytes": 128,
                            "action": "send",
                            "wire_mode": "native",
                            "flow_class": "state",
                            "robot_id": "robot_0001",
                        },
                    ]
                )
                + "\n",
                encoding="utf-8",
            )
            received.write_text(
                "\n".join(
                    json.dumps(record)
                    for record in [
                        {
                            "event_id": 1,
                            "policy": "fleetqox",
                            "flow_class": "control",
                            "robot_id": "robot_0000",
                            "bytes": 48,
                            "deadline_ms": 90,
                            "latency_ms": 50,
                            "semantic_utility": 7.0,
                        },
                        {
                            "event_id": 2,
                            "policy": "fleetqox",
                            "flow_class": "control",
                            "robot_id": "robot_0001",
                            "bytes": 48,
                            "deadline_ms": 90,
                            "latency_ms": 120,
                            "semantic_utility": 6.0,
                        },
                        {
                            "event_id": 4,
                            "policy": "fleetqox",
                            "flow_class": "state",
                            "robot_id": "robot_0001",
                            "bytes": 128,
                            "deadline_ms": 90,
                            "latency_ms": 120,
                            "semantic_utility": 3.0,
                        },
                    ]
                )
                + "\n",
                encoding="utf-8",
            )

            summary = analyze_sidecar_runtime_by_robot(decisions, received)

        self.assertEqual(summary["robot_count"], 2)
        by_robot = summary["by_robot"]
        self.assertEqual(by_robot["robot_0000"]["control_delivery_ratio"], 1.0)
        self.assertEqual(by_robot["robot_0001"]["control_delivery_ratio"], 0.5)
        self.assertEqual(by_robot["robot_0001"]["deadline_miss_ratio"], 0.5)
        fairness = summary["fairness"]
        self.assertEqual(fairness["min_control_delivery_ratio"], 0.5)
        self.assertEqual(fairness["max_deadline_miss_ratio"], 0.5)
        self.assertEqual(fairness["worst_control_delivery_robot"], "robot_0001")
        self.assertLess(fairness["control_delivery_jain_index"], 1.0)

    def test_per_robot_budget_report_flags_violations(self) -> None:
        summary = {
            "fairness": {
                "min_control_delivery_ratio": 0.80,
                "max_deadline_miss_ratio": 0.20,
                "rx_jain_index": 0.99,
                "control_delivery_jain_index": 0.97,
                "deadline_success_jain_index": 0.98,
            }
        }

        report = per_robot_budget_report(summary, min_control_delivery_ratio=0.90)

        self.assertFalse(report["pass"])
        self.assertEqual(report["violations"][0]["name"], "min_control_delivery_ratio")

    def test_jain_index_handles_balanced_and_empty_values(self) -> None:
        self.assertEqual(jain_index([]), 0.0)
        self.assertEqual(jain_index([0.0, 0.0]), 1.0)
        self.assertEqual(jain_index([5.0, 5.0]), 1.0)
        self.assertLess(jain_index([1.0, 3.0]), 1.0)


if __name__ == "__main__":
    unittest.main()

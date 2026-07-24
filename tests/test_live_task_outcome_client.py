import copy
import json
import unittest

from fleetqox.live_task_outcome_client import task_seed_frame
from fleetqox.quic_gateway_state import parse_data_frame
from fleetqox.task_outcome import (
    TaskOutcomeCorrelation,
    nav2_application_outcome,
)


def nav2_outcome(sequence: int = 1) -> dict:
    return nav2_application_outcome(
        TaskOutcomeCorrelation(
            42,
            "/fleetqox/nav2_rmf_tasks",
            "nav2-rmf-workload-client",
            sequence,
        ),
        goal_status=4,
        observed_latency_ms=12.5,
        deadline_ms=10000.0,
    )


class LiveTaskOutcomeClientTest(unittest.TestCase):
    def test_seed_frame_has_exact_application_outcome_identity(self) -> None:
        outcome = nav2_outcome()
        encoded = task_seed_frame(outcome)
        metadata = parse_data_frame(encoded, max_frame_bytes=65536)
        self.assertEqual(metadata.domain_id, outcome["domain_id"])
        self.assertEqual(metadata.topic, outcome["topic"])
        self.assertEqual(metadata.publisher_id, outcome["publisher_id"])
        self.assertEqual(
            metadata.source_sequence_number,
            outcome["source_sequence_number"],
        )
        self.assertEqual(metadata.traffic_class, "control")
        self.assertEqual(metadata.criticality, 1.0)
        self.assertEqual(metadata.deadline_ms, outcome["deadline_ms"])

    def test_seed_frame_is_valid_json_and_rejects_contradictions(self) -> None:
        encoded = task_seed_frame(nav2_outcome())
        document = json.loads(encoded.split(b"\n", 1)[1])
        self.assertEqual(document["schema_version"], "fleetrmw.data_frame.v1")
        self.assertEqual(
            document["sample_envelope"]["publisher_id"],
            "nav2-rmf-workload-client",
        )

        mutated = copy.deepcopy(nav2_outcome())
        mutated["task_succeeded"] = False
        with self.assertRaisesRegex(ValueError, "contradicts"):
            task_seed_frame(mutated)

        mutated = copy.deepcopy(nav2_outcome())
        mutated["observed_latency_ms"] = float("nan")
        with self.assertRaisesRegex(ValueError, "timing"):
            task_seed_frame(mutated)


if __name__ == "__main__":
    unittest.main()

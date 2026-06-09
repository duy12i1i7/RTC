import unittest

from fleetqox.network_replay import ReplayConfig, replay_trace
from fleetqox.trace import generate_trace_events


class NetworkReplayTest(unittest.TestCase):
    def test_replay_produces_policy_metrics(self) -> None:
        events = generate_trace_events(
            scenario="test",
            robots=5,
            seconds=1,
            seed=7,
            capacity_bytes_per_second=120_000,
            policies=["fifo", "fleetqox_csds"],
        )
        packet_events = [
            _event_to_packet(event)
            for event in events
            if event["event_type"] == "packet"
        ]

        records = replay_trace(packet_events, ReplayConfig(data_rate_mbps=10.0))
        policies = {record["policy"] for record in records}

        self.assertEqual({"fifo", "fleetqox_csds"}, policies)
        self.assertTrue(all(record["tx"] > 0 for record in records))

    def test_adaptive_reliability_counts_retransmissions(self) -> None:
        from fleetqox.network_replay import PacketEvent

        event = PacketEvent(
            event_id=1,
            timestamp_ms=0.0,
            policy="p",
            flow_id="robot_1:cmd",
            flow_class="control",
            src="fleet_controller",
            dst="robot_1",
            bytes=100,
            deadline_ms=45,
            semantic_utility=1.0,
            reliability="reliable",
        )

        records = replay_trace(
            [event],
            ReplayConfig(
                data_rate_mbps=10.0,
                loss=0.5,
                seed=1,
                transport_model="adaptive_reliability",
            ),
        )

        self.assertEqual(records[0]["retransmissions"], 1)
        self.assertEqual(records[0]["rx"], 1)


def _event_to_packet(event):
    from fleetqox.network_replay import PacketEvent

    return PacketEvent(
        event_id=int(event["tick"]),
        timestamp_ms=float(event["timestamp_ms"]),
        policy=str(event["policy"]),
        flow_id=str(event["flow_id"]),
        flow_class=str(event["flow_class"]),
        src=str(event["src"]),
        dst=str(event["dst"]),
        bytes=int(event["bytes"]),
        deadline_ms=float(event["deadline_ms"]),
        semantic_utility=float(event["semantic_utility"]),
        action=str(event.get("action", "send")),
        reliability=str(event.get("reliability", "best_effort")),
        wire_mode=str(event.get("wire_mode", "native")),
        predicted_slack_ms=float(event.get("predicted_slack_ms", 0.0)),
    )


if __name__ == "__main__":
    unittest.main()

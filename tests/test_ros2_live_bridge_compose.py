import unittest
from pathlib import Path


class Ros2LiveBridgeComposeTest(unittest.TestCase):
    def test_zenoh_overlay_waits_for_healthy_router(self) -> None:
        text = Path("external/ros2-live-bridge/docker-compose.zenoh.yml").read_text(
            encoding="utf-8"
        )

        self.assertIn("healthcheck:", text)
        self.assertIn("service_healthy", text)
        self.assertIn("127.0.0.1", text)
        self.assertIn("7447", text)
        self.assertNotIn("|| true", text)

    def test_live_bridge_compose_exposes_adaptive_ack_pacer(self) -> None:
        text = Path("external/ros2-live-bridge/docker-compose.yml").read_text(
            encoding="utf-8"
        )

        self.assertIn("EGRESS_FEEDBACK_CONTROL_LEASE_ACK_ADAPTIVE_FLAG", text)
        self.assertIn("--feedback-control-lease-ack-adaptive-min-events", text)
        self.assertIn("--feedback-control-lease-ack-adaptive-failure-multiplier", text)
        self.assertIn("--feedback-control-lease-ack-adaptive-max-age-ms", text)
        self.assertIn(
            "EGRESS_FEEDBACK_CONTROL_LEASE_ACK_ADAPTIVE_NO_PIGGYBACK_FIRST_FLAG",
            text,
        )


if __name__ == "__main__":
    unittest.main()

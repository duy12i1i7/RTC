import importlib.util
from pathlib import Path
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
RUNNER = ROOT / "scripts" / "run_ros2_relay_rmw_netem_probe.py"
RELAY_SOURCE = (
    ROOT
    / "ros2_ws"
    / "src"
    / "rmw_fleetqox_cpp"
    / "src"
    / "generic_serialized_relay_probe.cpp"
)
CMAKE = ROOT / "ros2_ws" / "src" / "rmw_fleetqox_cpp" / "CMakeLists.txt"


def load_runner():
    spec = importlib.util.spec_from_file_location("ros2_relay_runner", RUNNER)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class Ros2RelayRmwRunnerTest(unittest.TestCase):
    def test_ingress_specs_preserve_flow_and_change_topic(self):
        module = load_runner()
        original = [{"topic": "/r/cmd_vel", "kind": "control", "flow": "r/cmd_vel"}]
        source = module.ingress_specs(original)
        self.assertEqual(source[0]["topic"], "/r/cmd_vel/_fleetqox_ingress")
        self.assertEqual(source[0]["flow"], "r/cmd_vel")
        self.assertEqual(original[0]["topic"], "/r/cmd_vel")

    def test_generated_relay_maps_every_topic(self):
        module = load_runner()
        destination = module.topic_specs_for_robot_count(2)
        source = module.ingress_specs(destination)
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)
            subscriber = path / "subscriber.py"
            publisher = path / "publisher.py"
            relay = path / "relay.py"
            module.write_relay_probe_scripts(
                subscriber_script=subscriber,
                publisher_script=publisher,
                relay_script=relay,
                destination_specs=destination,
                source_specs=source,
                samples=5,
                payload_bytes=4096,
                publish_interval_ms=50,
                timeout_s=25.0,
                publisher_linger_s=6.0,
            )
            relay_source = relay.read_text()
            self.assertNotIn("__MAPPINGS_JSON__", relay_source)
            for spec in destination:
                self.assertIn(f'"destination": "{spec["topic"]}"', relay_source)
            self.assertIn("ReliabilityPolicy.RELIABLE", relay_source)
            self.assertIn("PAYLOAD_BYTES = 4096", publisher.read_text())

    def test_runner_declares_matched_hop_topology(self):
        source = RUNNER.read_text()
        self.assertIn('"topology": "publisher-relay-subscriber"', source)
        self.assertIn('"rclcpp_generic_serialized_passthrough"', source)
        self.assertIn('"middle_payload_remains_serialized":', source)
        self.assertIn("generic_serialized_relay_command", source)
        self.assertIn("fleetqox_static_addresses", source)
        self.assertIn('"middle_rmw_termination_republish":', source)
        self.assertIn('"fleetqox_direct_peer_transport":', source)
        self.assertIn("FLEETQOX_RMW_RELIABLE_ACK_TIMEOUT_MS", source)
        self.assertIn(
            "FLEETQOX_RMW_LOSS_RESILIENT_FRAGMENT_CHUNK_BYTES",
            source,
        )
        self.assertIn(
            "DEFAULT_FLEETQOX_RELIABLE_MAX_RETRANSMISSIONS = 6",
            source,
        )
        self.assertIn("FLEETQOX_RMW_UDP_SEND_PACING_US", source)
        self.assertIn('"fleetqox_udp_send_pacing_us":', source)
        self.assertIn("FLEETQOX_RMW_FRAGMENT_NACK_INTERVAL_MS", source)
        self.assertIn("FLEETQOX_RMW_FRAGMENT_NACK_MAX_REQUESTS", source)
        self.assertIn(
            "FLEETQOX_RMW_FRAGMENT_NACK_MAX_INDEXES_PER_REQUEST",
            source,
        )
        self.assertIn("FLEETQOX_RMW_FRAGMENT_HISTORY_LIMIT", source)
        self.assertIn("FLEETQOX_RMW_FRAGMENT_ASSEMBLY_TTL_MS", source)
        self.assertIn("FLEETQOX_RMW_FRAGMENT_ASYNC_SEND", source)
        self.assertIn("FLEETQOX_RMW_FRAGMENT_SEND_QUEUE_LIMIT", source)
        self.assertIn(
            "FLEETQOX_RMW_FRAGMENT_QUEUE_ADMISSION_THRESHOLD",
            source,
        )
        self.assertIn(
            "FLEETQOX_RMW_FRAGMENT_QUEUE_ADMISSION_TIMEOUT_MS",
            source,
        )
        self.assertIn("FLEETQOX_RMW_FRAGMENT_REPAIR_COOLDOWN_MS", source)
        self.assertIn("FLEETQOX_RMW_FRAGMENT_REPAIR_QUEUE_LIMIT", source)
        self.assertIn('"fleetqox_fragment_async_send":', source)
        self.assertIn('"publisher_stderr_excerpt":', source)
        self.assertIn("netem_shell_prefix", source)
        self.assertIn("publisher_linger_s", source)

    def test_cpp_generic_relay_forwards_serialized_messages(self):
        source = RELAY_SOURCE.read_text()
        cmake = CMAKE.read_text()
        self.assertIn("create_generic_subscription", source)
        self.assertIn("create_generic_publisher", source)
        self.assertIn("publisher->publish(*message)", source)
        self.assertIn('"application_deserialization\\":false', source)
        self.assertIn("fleetrmw.generic_serialized_relay_probe.v2", source)
        self.assertIn('"executor_drain_mode\\":\\"spin_some_bounded', source)
        self.assertIn("wait_for_all_acked", source)
        self.assertIn('"downstream_ack_wait_complete\\":', source)
        self.assertIn(
            'std::string(implementation) != "rmw_fleetqox_cpp"',
            source,
        )
        self.assertIn(
            "rmw_fleetqox_cpp_socket_fragment_nacks_sent",
            source,
        )
        self.assertIn(
            "rmw_fleetqox_cpp_socket_fragment_repair_requests_coalesced",
            source,
        )
        self.assertIn(
            "rmw_fleetqox_cpp_socket_fragment_repair_cooldown_coalesced",
            source,
        )
        self.assertIn(
            "rmw_fleetqox_cpp_socket_completed_fragment_duplicates_dropped",
            source,
        )
        self.assertIn(
            "rmw_fleetqox_cpp_socket_fragment_repair_queue_deferrals",
            source,
        )
        self.assertIn(
            "rmw_fleetqox_cpp_socket_fragment_active_missing_indexes",
            source,
        )
        self.assertIn(
            "fragment_observed_timeout_retransmissions_suppressed",
            source,
        )
        self.assertIn("fragment_whole_fallback_pacing_deferrals", source)
        self.assertIn("fragment_assembly_oversize_drops", source)
        self.assertIn("fleetrmw_generic_serialized_relay_probe", cmake)

    def test_fleetqox_repeat_runner_preserves_broad_claim_boundary(self):
        runner = (
            ROOT / "scripts" /
            "run_rmw_docker_fleetqox_generic_relay_probe.py"
        )
        self.assertTrue(runner.exists())
        source = runner.read_text()
        self.assertIn(
            "fleetrmw.docker_fleetqox_generic_relay_probe.v1",
            source,
        )
        self.assertIn("fleetqox_middle_rmw_termination_republish_claim", source)
        self.assertIn('"same_hop_middle_processing_equivalence_claim": False', source)
        self.assertIn('"same_hop_latency_superiority_claim": False', source)


if __name__ == "__main__":
    unittest.main()

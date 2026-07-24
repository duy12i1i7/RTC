import importlib.util
from pathlib import Path
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
RUNNER = ROOT / "scripts" / "run_ros2_relay_rmw_netem_probe.py"


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
                publish_interval_ms=50,
                timeout_s=25.0,
                publisher_linger_s=6.0,
            )
            relay_source = relay.read_text()
            self.assertNotIn("__MAPPINGS_JSON__", relay_source)
            for spec in destination:
                self.assertIn(f'"destination": "{spec["topic"]}"', relay_source)
            self.assertIn("ReliabilityPolicy.RELIABLE", relay_source)

    def test_runner_declares_matched_hop_topology(self):
        source = RUNNER.read_text()
        self.assertIn('"topology": "publisher-relay-subscriber"', source)
        self.assertIn('"relay_scope": "rclpy_std_msgs_string_deserialize_republish"', source)
        self.assertIn("netem_shell_prefix", source)
        self.assertIn("publisher_linger_s", source)


if __name__ == "__main__":
    unittest.main()

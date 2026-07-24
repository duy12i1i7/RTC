import importlib.util
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
RUNNER = ROOT / "scripts" / "run_rmw_docker_quic_inprocess_bidirectional_probe.py"


def load_runner():
    spec = importlib.util.spec_from_file_location("quic_inprocess_runner", RUNNER)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class QuicInProcessRunnerTest(unittest.TestCase):
    def test_runner_exists(self):
        self.assertTrue(RUNNER.exists())

    def test_schema_and_default_image_are_explicit(self):
        module = load_runner()
        self.assertEqual(
            module.SCHEMA_VERSION,
            "fleetrmw.docker_quic_inprocess_bidirectional_probe.v3",
        )
        self.assertEqual(module.DEFAULT_IMAGE, "localhost/fleetrmw/rmw-netem:jazzy")

    def test_certificate_chain_has_san_and_server_auth(self):
        module = load_runner()
        command = module.certificate_commands(certs=ROOT / "certs", root=ROOT)
        self.assertIn("subjectAltName=DNS:localhost,IP:127.0.0.1", command)
        self.assertIn("extendedKeyUsage=serverAuth", command)
        self.assertIn("wrong-ca.crt", command)

    def test_runner_requires_inprocess_backend(self):
        source = RUNNER.read_text()
        self.assertIn("FLEETQOX_RMW_QUIC_BACKEND=inprocess", source)
        self.assertIn('positive.get("subprocess_backed") is False', source)

    def test_runner_proves_one_handshake_and_reused_streams(self):
        source = RUNNER.read_text()
        self.assertIn('int(positive.get("connections_created", 0)) == 1', source)
        self.assertIn('int(positive.get("handshakes_completed", 0)) == 1', source)
        self.assertIn('== publish_count + 1', source)
        self.assertIn('== publish_count', source)
        self.assertIn('default=128', source)

    def test_runner_has_netem_impairment(self):
        source = RUNNER.read_text()
        self.assertIn("loss {loss_percent:.3f}%", source)
        self.assertIn('"seed": None', source)
        self.assertIn('"--cap-add"', source)
        self.assertIn('"NET_ADMIN"', source)

    def test_runner_proves_concurrent_post_get_stream_pair(self):
        source = RUNNER.read_text()
        self.assertIn("fleetrmw_quic_inprocess_concurrent_stream_probe", source)
        self.assertIn('concurrent.get("concurrent_post_get_stream_pair") is True', source)
        self.assertIn('int(concurrent.get("streams_opened", 0)) == 2', source)
        self.assertIn('int(concurrent.get("concurrent_stream_pairs", 0)) == 1', source)
        self.assertIn('int(concurrent.get("max_concurrent_request_streams", 0)) >= 2', source)
        self.assertIn('concurrent.get("multi_threaded_rmw_api_claim") is False', source)

    def test_runner_proves_independent_rmw_publish_take_pair(self):
        source = RUNNER.read_text()
        self.assertIn("FLEETQOX_RMW_QUIC_CONCURRENT_PAIR_WAIT_MS=100", source)
        self.assertIn(
            'positive.get("concurrent_rmw_publish_take_operation_loop") is True',
            source,
        )
        self.assertIn('positive.get("multi_threaded_rmw_api_claim") is True', source)
        self.assertIn('int(positive.get("concurrent_api_operation_pairs", 0)) == 1', source)
        self.assertIn('int(positive.get("max_concurrent_api_calls", 0)) >= 2', source)

    def test_runner_keeps_production_boundary(self):
        source = RUNNER.read_text()
        self.assertIn('"serialized_operation_loop": False', source)
        self.assertIn('"production_readiness": False', source)


if __name__ == "__main__":
    unittest.main()

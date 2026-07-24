from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from fleetqox.public_quic_gateway_backend import BackendRequest
from scripts.fleetqox_public_quic_backend_delay_proxy import (
    DelayProxy,
    SCHEMA_VERSION as PROXY_SCHEMA_VERSION,
)
from scripts.run_rmw_docker_ngtcp2_public_async_backend_probe import (
    ROOT,
    SCHEMA_VERSION,
)


class Ngtcp2PublicAsyncBackendTest(unittest.TestCase):
    def test_pinned_patch_uses_bounded_worker_dispatch_and_event_loop_completion(
        self,
    ) -> None:
        patch = (
            ROOT / "external/ngtcp2-public-mtls/async-backend.patch"
        ).read_text(encoding="utf-8")
        self.assertIn("#include <condition_variable>", patch)
        self.assertIn("ev_async_init(&backend_async_", patch)
        self.assertIn("backend_tasks_.size() >= backend_queue_capacity_", patch)
        self.assertIn("FLEETQOX_STATE_BACKEND_WORKERS", patch)
        self.assertIn("FLEETQOX_STATE_BACKEND_QUEUE_CAPACITY", patch)
        self.assertIn("FLEETQOX_STATE_BACKEND_QUEUE_FULL", patch)
        self.assertIn("handler_generation", patch)
        self.assertIn("FLEETQOX_STATE_BACKEND_DROPPED_HANDLER", patch)
        self.assertIn("worker.join()", patch)
        shutdown = patch.split("void Server::stop_backend_dispatcher()", 1)[1]
        self.assertLess(
            shutdown.index("backend_tasks_.clear()"),
            shutdown.index("backend_cv_.notify_all()"),
        )
        worker = patch.split("void Server::backend_worker_loop()", 1)[1].split(
            "void Server::drain_backend_completions()", 1
        )[0]
        self.assertNotIn("nghttp3_submit_response", worker)

    def test_dockerfile_applies_async_patch_after_stateful_patch(self) -> None:
        dockerfile = (
            ROOT / "external/ngtcp2-public-mtls/Dockerfile"
        ).read_text(encoding="utf-8")
        stateful = dockerfile.index("stateful-backend.patch")
        asynchronous = dockerfile.index("async-backend.patch")
        self.assertLess(stateful, asynchronous)

    def test_delay_proxy_selects_only_configured_consumer_prefixes(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            proxy = DelayProxy(
                root / "listen.sock",
                root / "upstream.sock",
                delay_prefixes=("slow", "queue-"),
                delay_ms=10,
                workers=1,
                max_in_flight=1,
            )
            slow = BackendRequest(
                method="GET",
                path=(
                    "/fleetrmw/v1/frames?domain_id=42&topic=%2Fx"
                    "&consumer_id=slow-lifecycle"
                ),
                client_identity="publisher",
                body=b"",
            )
            fast = BackendRequest(
                method="GET",
                path=(
                    "/fleetrmw/v1/frames?domain_id=42&topic=%2Fx"
                    "&consumer_id=fast"
                ),
                client_identity="publisher",
                body=b"",
            )
            self.assertEqual(proxy._should_delay(slow), (True, "slow-lifecycle"))
            self.assertEqual(proxy._should_delay(fast), (False, "fast"))
            snapshot = proxy.snapshot()
            self.assertEqual(snapshot["schema_version"], PROXY_SCHEMA_VERSION)
            self.assertEqual(snapshot["max_in_flight"], 1)

    def test_runner_has_explicit_proof_phases_and_production_boundary(self) -> None:
        runner = (
            ROOT
            / "scripts/run_rmw_docker_ngtcp2_public_async_backend_probe.py"
        ).read_text(encoding="utf-8")
        self.assertIn(SCHEMA_VERSION, runner)
        self.assertIn("slow_in_flight_when_fast_completed", runner)
        self.assertIn("bounded_backend_queue_http_503_claim", runner)
        self.assertIn("stale_completion_dropped", runner)
        self.assertIn("real_state_engine_behind_test_delay_proxy_claim", runner)
        self.assertIn('"production_quic_backend_claim": False', runner)

    def test_canonical_artifact_passes_five_runs(self) -> None:
        artifact = (
            ROOT
            / "results_rmw_socket/"
            "docker_ngtcp2_public_async_backend_summary.json"
        )
        if not artifact.exists():
            self.skipTest("canonical public async artifact has not been generated")
        summary = json.loads(artifact.read_text(encoding="utf-8"))
        self.assertEqual(summary["schema_version"], SCHEMA_VERSION)
        self.assertEqual(summary["status"], "ok")
        self.assertEqual(summary["run_count"], 5)
        self.assertEqual(summary["ok_run_count"], 5)
        self.assertTrue(
            summary["public_ngtcp2_backend_event_loop_nonblocking_claim"]
        )
        self.assertTrue(summary["bounded_backend_queue_http_503_claim"])
        self.assertTrue(summary["handler_generation_fencing_claim"])
        self.assertFalse(summary["production_quic_backend_claim"])


if __name__ == "__main__":
    unittest.main()

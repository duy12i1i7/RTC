import asyncio
import copy
import json
from pathlib import Path
import unittest

from scripts.run_rmw_docker_quic_durable_admission_failover_probe import probe_ok
from scripts.run_rmw_docker_quic_writer_fencing_probe import service_with_lease_ok
from fleetqox.quic_gateway_lease import acquire_gateway_state_with_lease_wait
from fleetqox.quic_gateway_state import (
    FleetQoxGatewayState,
    FramePersistenceError,
    FramePersistenceUnavailableError,
)


ROOT = Path(__file__).resolve().parents[1]
ARTIFACT = (
    ROOT
    / "results_rmw_socket"
    / "docker_quic_writer_fencing_probe_summary.json"
)


class QuicWriterFencingTest(unittest.TestCase):
    def test_standby_retries_temporary_durable_backend_unavailability(self) -> None:
        async def scenario() -> None:
            attempts = 0

            def factory():
                nonlocal attempts
                attempts += 1
                if attempts < 3:
                    raise FramePersistenceUnavailableError("database unavailable")
                return object()

            state, telemetry = await acquire_gateway_state_with_lease_wait(
                factory=factory,
                wait_timeout_ms=500,
                retry_ms=1,
            )
            self.assertIsNotNone(state)
            self.assertEqual(telemetry["writer_lease_acquisition_attempts"], 3)
            self.assertEqual(telemetry["writer_lease_unavailable_retries"], 2)

        asyncio.run(scenario())

    def test_standby_waits_then_acquires_after_active_release(self) -> None:
        async def scenario(database: Path) -> None:
            active = FleetQoxGatewayState(
                durable_state_path=database,
                durable_writer_id="gateway-a",
                durable_writer_lease_ms=1000,
            )

            async def release_active() -> None:
                await asyncio.sleep(0.03)
                active.close()

            release_task = asyncio.create_task(release_active())
            standby, telemetry = await acquire_gateway_state_with_lease_wait(
                factory=lambda: FleetQoxGatewayState(
                    durable_state_path=database,
                    durable_writer_id="gateway-b",
                    durable_writer_lease_ms=1000,
                ),
                wait_timeout_ms=500,
                retry_ms=10,
            )
            await release_task
            self.assertGreater(telemetry["writer_lease_acquisition_attempts"], 1)
            self.assertTrue(telemetry["automatic_standby_wait_configured"])
            lease = standby.snapshot()["durable_state"]["writer_lease"]
            self.assertEqual(lease["holder_id"], "gateway-b")
            self.assertEqual(lease["fence_token"], 2)
            standby.close()

        import tempfile

        with tempfile.TemporaryDirectory() as temporary_directory:
            asyncio.run(scenario(Path(temporary_directory) / "state.sqlite3"))

    def test_standby_wait_timeout_fails_closed(self) -> None:
        async def scenario(database: Path) -> None:
            active = FleetQoxGatewayState(
                durable_state_path=database,
                durable_writer_id="gateway-a",
                durable_writer_lease_ms=1000,
            )
            with self.assertRaisesRegex(
                FramePersistenceError, "timed out waiting"
            ):
                await acquire_gateway_state_with_lease_wait(
                    factory=lambda: FleetQoxGatewayState(
                        durable_state_path=database,
                        durable_writer_id="gateway-b",
                        durable_writer_lease_ms=1000,
                    ),
                    wait_timeout_ms=30,
                    retry_ms=10,
                )
            active.close()

        import tempfile

        with tempfile.TemporaryDirectory() as temporary_directory:
            asyncio.run(scenario(Path(temporary_directory) / "state.sqlite3"))

    @unittest.skipUnless(ARTIFACT.is_file(), "external Docker evidence artifact absent")
    def test_validators_reject_missing_renewal_wrong_holder_or_reset_state(self) -> None:
        summary = json.loads(ARTIFACT.read_text(encoding="utf-8"))
        run = summary["runs"][0]
        active = run["active"]["service"]
        takeover = run["takeover"]["service"]
        self.assertTrue(
            service_with_lease_ok(active, mode="seed", holder="gateway-a", token=1)
        )
        self.assertTrue(
            service_with_lease_ok(
                takeover, mode="resume", holder="gateway-c", token=2
            )
        )

        mutated = copy.deepcopy(active)
        mutated["metrics"]["durable_writer_lease_renewals"] = 0
        self.assertFalse(
            service_with_lease_ok(mutated, mode="seed", holder="gateway-a", token=1)
        )
        mutated = copy.deepcopy(takeover)
        mutated["metrics"]["durable_state"]["writer_lease"]["holder_id"] = (
            "gateway-a"
        )
        self.assertFalse(
            service_with_lease_ok(
                mutated, mode="resume", holder="gateway-c", token=2
            )
        )
        mutated = copy.deepcopy(takeover)
        mutated["metrics"]["durable_state"]["writer_lease"]["fence_token"] = 1
        self.assertFalse(
            service_with_lease_ok(
                mutated, mode="resume", holder="gateway-c", token=2
            )
        )
        mutated = copy.deepcopy(takeover)
        mutated["metrics"]["recovered_admission_state"] = 0
        self.assertFalse(
            service_with_lease_ok(
                mutated, mode="resume", holder="gateway-c", token=2
            )
        )

    @unittest.skipUnless(ARTIFACT.is_file(), "external Docker evidence artifact absent")
    def test_canonical_docker_netem_fencing_passes_five_runs(self) -> None:
        summary = json.loads(ARTIFACT.read_text(encoding="utf-8"))
        self.assertEqual(summary["status"], "ok")
        self.assertEqual(summary["run_count"], 5)
        self.assertEqual(summary["successful_runs"], 5)
        self.assertEqual(summary["container_count_per_run"], 5)
        self.assertTrue(summary["real_quic_v1_h3"])
        self.assertTrue(summary["sqlite_single_writer_lease_claim"])
        self.assertTrue(summary["concurrent_standby_startup_fenced_claim"])
        self.assertTrue(summary["monotonic_fence_token_takeover_claim"])
        self.assertTrue(summary["lease_renewal_claim"])
        self.assertTrue(summary["post_takeover_admission_recovery_claim"])
        self.assertTrue(summary["manual_active_passive_takeover_claim"])
        self.assertFalse(summary["automatic_leader_election_claim"])
        self.assertFalse(summary["active_active_consensus_claim"])
        self.assertFalse(summary["distributed_database_claim"])
        self.assertFalse(summary["production_readiness"])
        for run in summary["runs"]:
            self.assertEqual(run["status"], "ok")
            self.assertTrue(run["blocked_standby"]["concurrent_standby_fenced"])
            self.assertNotEqual(run["blocked_standby"]["returncode"], 0)
            self.assertTrue(probe_ok(run["active"]["probe"], "seed"))
            self.assertTrue(probe_ok(run["takeover"]["probe"], "resume"))
            self.assertTrue(
                service_with_lease_ok(
                    run["active"]["service"],
                    mode="seed",
                    holder="gateway-a",
                    token=1,
                )
            )
            self.assertTrue(
                service_with_lease_ok(
                    run["takeover"]["service"],
                    mode="resume",
                    holder="gateway-c",
                    token=2,
                )
            )

    def test_all_durable_writes_are_transaction_fenced(self) -> None:
        state = (ROOT / "fleetqox" / "quic_gateway_state.py").read_text()
        service = (ROOT / "scripts" / "fleetrmw_quic_gateway_service.py").read_text()
        self.assertIn("CREATE TABLE IF NOT EXISTS writer_lease", state)
        self.assertIn("def acquire_writer_lease", state)
        self.assertIn("def renew_writer_lease", state)
        self.assertGreaterEqual(state.count('execute("BEGIN IMMEDIATE")'), 4)
        self.assertGreaterEqual(state.count("self._verify_writer_lease"), 2)
        self.assertIn("writer_lease_lost", service)


if __name__ == "__main__":
    unittest.main()

import copy
import json
from pathlib import Path
import unittest

from scripts.run_rmw_docker_quic_postgres_failover_probe import (
    POSTGRES_SCHEMA_VERSION,
    case_ok,
    postgres_service_ok,
)


ROOT = Path(__file__).resolve().parents[1]
ARTIFACT = (
    ROOT
    / "results_rmw_socket"
    / "docker_quic_postgresql_failover_probe_summary.json"
)


class QuicPostgresFailoverTest(unittest.TestCase):
    @unittest.skipUnless(ARTIFACT.is_file(), "external Docker evidence artifact absent")
    def test_validators_reject_storage_or_evidence_regressions(self) -> None:
        summary = json.loads(ARTIFACT.read_text(encoding="utf-8"))
        run = summary["runs"][0]
        self.assertTrue(case_ok(run))
        self.assertTrue(
            postgres_service_ok(
                run["active"]["service"], mode="seed", holder="gateway-a",
                token=1, automatic_wait=False,
            )
        )
        self.assertTrue(
            postgres_service_ok(
                run["standby"]["service"], mode="resume", holder="gateway-b",
                token=2, automatic_wait=True,
            )
        )

        mutations = []
        mutated = copy.deepcopy(run)
        mutated["standby"]["service"]["metrics"]["durable_state"]["backend"] = (
            "sqlite"
        )
        mutations.append(mutated)
        mutated = copy.deepcopy(run)
        mutated["standby"]["service"]["metrics"]["durable_state"][
            "synchronous_commit"
        ] = "off"
        mutations.append(mutated)
        mutated = copy.deepcopy(run)
        mutated["standby"]["service"]["metrics"]["durable_state"][
            "writer_lease"
        ]["fence_token"] = 1
        mutations.append(mutated)
        mutated = copy.deepcopy(run)
        mutated["standby"]["service"]["metrics"]["recovered_admission_state"] = 0
        mutations.append(mutated)
        mutated = copy.deepcopy(run)
        mutated["database_shutdown"]["running_through_gateway_takeover"] = False
        mutations.append(mutated)
        mutated = copy.deepcopy(run)
        mutated["standby"]["qlog_file_count"] = 0
        mutations.append(mutated)
        for mutation in mutations:
            with self.subTest(mutation=mutations.index(mutation)):
                self.assertFalse(case_ok(mutation))

    @unittest.skipUnless(ARTIFACT.is_file(), "external Docker evidence artifact absent")
    def test_canonical_docker_netem_postgresql_takeover_passes_five_runs(
        self,
    ) -> None:
        summary = json.loads(ARTIFACT.read_text(encoding="utf-8"))
        self.assertEqual(summary["status"], "ok")
        self.assertEqual(summary["run_count"], 5)
        self.assertEqual(summary["successful_runs"], 5)
        self.assertEqual(summary["failed_run_count"], 0)
        self.assertEqual(summary["container_count_per_run"], 5)
        self.assertEqual(summary["gateway_instance_count_per_run"], 2)
        self.assertEqual(summary["database_instance_count_per_run"], 1)
        self.assertTrue(summary["real_quic_v1_h3"])
        self.assertTrue(summary["networked_postgresql_durable_state_claim"])
        self.assertTrue(summary["synchronous_commit_claim"])
        self.assertTrue(summary["frame_and_admission_single_transaction_claim"])
        self.assertTrue(summary["postgresql_writer_fencing_claim"])
        self.assertTrue(summary["automatic_gateway_takeover_claim"])
        self.assertTrue(summary["post_takeover_admission_recovery_claim"])
        self.assertLess(summary["max_takeover_latency_ms"], 8000)
        self.assertFalse(summary["database_process_failover_claim"])
        self.assertFalse(summary["replicated_database_claim"])
        self.assertFalse(summary["consensus_leader_election_claim"])
        self.assertFalse(summary["active_active_consensus_claim"])
        self.assertFalse(summary["production_readiness"])
        for run in summary["runs"]:
            self.assertTrue(case_ok(run))
            self.assertTrue(run["database"]["server_version"].startswith("16."))
            endpoint = run["standby"]["service"]["metrics"]["durable_state"][
                "endpoint"
            ]
            self.assertNotIn("@", endpoint)
            self.assertNotIn("fleetqox-postgresql-probe", endpoint)

    def test_backend_dependency_and_transaction_fencing_are_wired(self) -> None:
        dockerfile = (ROOT / "external" / "rmw-netem" / "Dockerfile").read_text()
        state = (ROOT / "fleetqox" / "quic_gateway_state.py").read_text()
        postgres = (ROOT / "fleetqox" / "quic_gateway_postgres.py").read_text()
        self.assertIn("ARG PSYCOPG_DEB_VERSION=3.1.17-2", dockerfile)
        self.assertIn("python3-psycopg=${PSYCOPG_DEB_VERSION}", dockerfile)
        self.assertIn('startswith(("postgresql://", "postgres://"))', state)
        self.assertIn(POSTGRES_SCHEMA_VERSION, postgres)
        self.assertIn("synchronous_commit=on", postgres)
        self.assertIn("pg_advisory_xact_lock", postgres)
        self.assertGreaterEqual(postgres.count("FOR UPDATE"), 3)
        self.assertGreaterEqual(postgres.count("self._verify_writer_lease"), 2)


if __name__ == "__main__":
    unittest.main()

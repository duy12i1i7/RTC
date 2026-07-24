import unittest

from scripts.fleetqox_postgres_failback_controller import (
    database_recovery_state,
    synchronous_replay_gap,
)


class FakeOperationalError(Exception):
    pass


class FakeInterfaceError(Exception):
    pass


class FakeCursor:
    def __init__(self, row):
        self.row = row

    def fetchone(self):
        return self.row


class FakeConnection:
    def __init__(self, rows):
        self.rows = list(rows)
        self.calls = []
        self.closed = False

    def execute(self, statement, parameters=None):
        self.calls.append((statement, parameters))
        return FakeCursor(self.rows.pop(0))

    def close(self):
        self.closed = True


class FakePsycopg:
    OperationalError = FakeOperationalError
    InterfaceError = FakeInterfaceError

    def __init__(self, connection=None, error=None):
        self.connection = connection
        self.error = error

    def connect(self, dsn, **kwargs):
        if self.error is not None:
            raise self.error
        return self.connection


class PostgresFailbackControllerTest(unittest.TestCase):
    def test_synchronous_replay_gap_requires_named_replication_row(self):
        connection = FakeConnection([("streaming", "sync", 0)])
        result = synchronous_replay_gap(
            FakePsycopg(connection), "postgresql://source/db", "rejoined"
        )
        self.assertEqual(result, {
            "state": "streaming",
            "sync_state": "sync",
            "replay_gap_bytes": 0,
        })
        self.assertEqual(connection.calls[0][1], ("rejoined",))
        self.assertTrue(connection.closed)

    def test_missing_replication_row_is_unsafe(self):
        connection = FakeConnection([None])
        self.assertIsNone(synchronous_replay_gap(
            FakePsycopg(connection), "postgresql://source/db", "rejoined"
        ))
        self.assertTrue(connection.closed)

    def test_database_unavailability_fails_closed(self):
        psycopg = FakePsycopg(error=FakeOperationalError())
        self.assertIsNone(database_recovery_state(psycopg, "postgresql://db"))
        self.assertIsNone(synchronous_replay_gap(
            psycopg, "postgresql://db", "rejoined"
        ))


if __name__ == "__main__":
    unittest.main()

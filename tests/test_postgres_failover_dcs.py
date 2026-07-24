import base64
import unittest

from fleetqox.postgres_failover_dcs import EtcdQuorumLease


class FakeEtcdQuorumLease(EtcdQuorumLease):
    def __init__(
        self, *, transaction_succeeds: bool,
        range_rows: list[dict[str, str]] | None = None,
    ) -> None:
        super().__init__(("http://etcd-1:2379",), timeout_s=0.1)
        self.transaction_succeeds = transaction_succeeds
        self.range_rows = range_rows or []
        self.calls = []

    def _post(self, path, payload):
        self.calls.append((path, payload))
        if path == "/v3/lease/grant":
            return {"ID": "42"}, "http://etcd-1:2379", 1
        if path == "/v3/kv/range":
            return {
                "header": {"cluster_id": "cluster", "revision": "8"},
                "kvs": self.range_rows,
            }, "http://etcd-1:2379", 0
        return {
            "succeeded": self.transaction_succeeds,
            "header": {"cluster_id": "cluster", "revision": "7"},
        }, "http://etcd-1:2379", 2


class PostgresFailoverDcsTest(unittest.TestCase):
    def test_compare_and_put_is_ttl_bound_and_quorum_accounted(self) -> None:
        client = FakeEtcdQuorumLease(transaction_succeeds=True)
        result = client.acquire(
            key="/fleetqox/postgresql/failover",
            value="controller-a",
            ttl_s=15,
        )
        self.assertTrue(result.acquired)
        self.assertEqual(result.lease_id, "42")
        self.assertEqual(result.cluster_id, "cluster")
        self.assertEqual(result.revision, "7")
        self.assertEqual(result.request_failures, 3)
        self.assertEqual(client.calls[0], ("/v3/lease/grant", {"TTL": 15}))
        transaction = client.calls[1][1]
        self.assertEqual(transaction["compare"][0]["target"], "CREATE")
        self.assertEqual(transaction["compare"][0]["createRevision"], "0")
        self.assertEqual(
            base64.b64decode(transaction["compare"][0]["key"]).decode(),
            "/fleetqox/postgresql/failover",
        )
        put = transaction["success"][0]["requestPut"]
        self.assertEqual(base64.b64decode(put["value"]).decode(), "controller-a")
        self.assertEqual(put["lease"], "42")

    def test_losing_controller_does_not_acquire_same_create_revision(self) -> None:
        client = FakeEtcdQuorumLease(transaction_succeeds=False)
        self.assertFalse(
            client.acquire(key="/fleetqox/leader", value="controller-b").acquired
        )

    def test_invalid_configuration_fails_closed(self) -> None:
        with self.assertRaises(ValueError):
            EtcdQuorumLease(())
        client = FakeEtcdQuorumLease(transaction_succeeds=True)
        with self.assertRaises(ValueError):
            client.acquire(key="", value="controller")

    def test_linearizable_lookup_returns_value_and_bound_lease(self) -> None:
        client = FakeEtcdQuorumLease(
            transaction_succeeds=True,
            range_rows=[{
                "value": base64.b64encode(b"controller-a").decode(),
                "lease": "42",
            }],
        )
        value = client.get(key="/fleetqox/postgresql/failover")
        self.assertIsNotNone(value)
        assert value is not None
        self.assertEqual(value.value, "controller-a")
        self.assertEqual(value.lease_id, "42")
        self.assertEqual(value.cluster_id, "cluster")
        self.assertEqual(value.revision, "8")
        path, payload = client.calls[-1]
        self.assertEqual(path, "/v3/kv/range")
        self.assertEqual(
            base64.b64decode(payload["key"]).decode(),
            "/fleetqox/postgresql/failover",
        )

    def test_lookup_without_current_leader_fails_closed(self) -> None:
        client = FakeEtcdQuorumLease(transaction_succeeds=True)
        self.assertIsNone(client.get(key="/fleetqox/postgresql/failover"))
        with self.assertRaises(ValueError):
            client.get(key="")


if __name__ == "__main__":
    unittest.main()

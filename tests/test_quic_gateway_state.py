import json
from pathlib import Path
import tempfile
import unittest
from urllib.parse import quote

from fleetqox.quic_gateway_state import (
    APPLICATION_OUTCOME_API_PATH,
    APPLICATION_OUTCOME_SCHEMA_VERSION,
    DATA_FRAME_MAGIC,
    FRAME_BATCH_SCHEMA_VERSION,
    GATEWAY_BATCH_API_PATH,
    OBSERVATION_API_PATH,
    OBSERVATION_SCHEMA_VERSION,
    FleetQoxGatewayState,
    FrameAdmissionError,
    FramePersistenceError,
    FrameValidationError,
    GatewayAdmissionPolicy,
    parse_data_frame,
)


def frame(
    sequence: int,
    *,
    topic: str = "/fleetqox/gateway",
    domain_id: int = 42,
    publisher_id: str = "gateway-probe-publisher",
    payload: bytes = b"payload",
    flow_class: str = "",
    deadline_ms: float = 0.0,
    age_ms: float = 0.0,
    qoe_debt: float = 0.0,
    criticality: float = 0.0,
    repair_requested: bool = False,
    prior_repair_attempts: int = 0,
) -> bytes:
    document = {
        "schema_version": "fleetrmw.data_frame.v1",
        "kind": "sidecar_packet_frame",
        "domain_id": domain_id,
        "route": {
            "robot_id": "robot-1",
            "topic": topic,
            **({"flow_class": flow_class} if flow_class else {}),
        },
        "sample_envelope": {
            "robot_id": "robot-1",
            "topic": topic,
            "publisher_id": publisher_id,
            "source_sequence_number": sequence,
            "source_timestamp_ns": sequence * 1000,
        },
        **(
            {"delivery": {"deadline_ms": deadline_ms}}
            if deadline_ms > 0.0
            else {}
        ),
        **({"timing": {"age_ms": age_ms}} if age_ms > 0.0 else {}),
        **(
            {"qox": {"qoe_debt": qoe_debt, "task_criticality": criticality}}
            if qoe_debt > 0.0 or criticality > 0.0
            else {}
        ),
        **(
            {
                "repair": {
                    "requested": repair_requested,
                    "prior_attempts": prior_repair_attempts,
                }
            }
            if repair_requested or prior_repair_attempts > 0
            else {}
        ),
        "serialized_payload": {
            "encoding": "hex",
            "size": len(payload),
            "data": payload.hex(),
        },
    }
    return DATA_FRAME_MAGIC + json.dumps(document, separators=(",", ":")).encode()


class QuicGatewayStateTest(unittest.TestCase):
    def test_frame_validation_checks_magic_schema_and_payload_size(self) -> None:
        metadata = parse_data_frame(frame(1), max_frame_bytes=4096)
        self.assertEqual(metadata.domain_id, 42)
        self.assertEqual(metadata.topic, "/fleetqox/gateway")
        self.assertEqual(metadata.source_sequence_number, 1)
        with self.assertRaises(FrameValidationError):
            parse_data_frame(b"{}", max_frame_bytes=4096)
        malformed = frame(1).replace(b'"size":7', b'"size":8')
        with self.assertRaises(FrameValidationError):
            parse_data_frame(malformed, max_frame_bytes=4096)

    def test_frame_validation_extracts_qos_qoe_and_repair_metadata(self) -> None:
        metadata = parse_data_frame(
            frame(
                7,
                flow_class="control",
                deadline_ms=100.0,
                age_ms=80.0,
                qoe_debt=0.9,
                criticality=1.0,
                repair_requested=True,
                prior_repair_attempts=2,
            ),
            max_frame_bytes=4096,
        )
        self.assertEqual(metadata.robot_id, "robot-1")
        self.assertEqual(metadata.traffic_class, "control")
        self.assertEqual(metadata.remaining_deadline_ms, 20.0)
        self.assertAlmostEqual(metadata.admission_score, 0.925)
        self.assertTrue(metadata.repair_requested)
        self.assertEqual(metadata.prior_repair_attempts, 2)

    def test_dedup_and_independent_consumer_replay(self) -> None:
        state = FleetQoxGatewayState(max_frames_per_topic=4)
        first = state.publish(frame(1))
        duplicate = state.publish(frame(1))
        state.publish(frame(2))
        self.assertTrue(first.accepted)
        self.assertFalse(duplicate.accepted)
        self.assertTrue(duplicate.duplicate)
        self.assertEqual(
            state.take(domain_id=42, topic="/fleetqox/gateway", consumer_id="a"),
            frame(1),
        )
        self.assertEqual(
            state.take(domain_id=42, topic="/fleetqox/gateway", consumer_id="a"),
            frame(2),
        )
        self.assertEqual(
            state.take(domain_id=42, topic="/fleetqox/gateway", consumer_id="b"),
            frame(1),
        )
        snapshot = state.snapshot()
        self.assertEqual(snapshot["accepted_frames"], 2)
        self.assertEqual(snapshot["duplicate_frames"], 1)
        self.assertEqual(snapshot["dequeued_frames"], 3)
        self.assertEqual(snapshot["consumer_count"], 2)

    def test_bounded_history_advances_slow_consumer(self) -> None:
        state = FleetQoxGatewayState(max_frames_per_topic=2)
        state.publish(frame(1))
        self.assertEqual(
            state.take(domain_id=42, topic="/fleetqox/gateway", consumer_id="slow"),
            frame(1),
        )
        state.publish(frame(2))
        state.publish(frame(3))
        state.publish(frame(4))
        self.assertEqual(
            state.take(domain_id=42, topic="/fleetqox/gateway", consumer_id="slow"),
            frame(3),
        )
        snapshot = state.snapshot()
        self.assertEqual(snapshot["retained_frames"], 2)
        self.assertEqual(snapshot["evicted_frames"], 2)
        self.assertEqual(snapshot["consumer_overruns"], 1)

    def test_http_api_validates_path_and_uses_consumer_cursor(self) -> None:
        state = FleetQoxGatewayState(max_frames_per_topic=4)
        topic = quote("/fleetqox/gateway", safe="")
        alpha = (
            f"/fleetrmw/v1/frames?domain_id=42&topic={topic}&consumer_id=alpha"
        )
        beta = f"/fleetrmw/v1/frames?domain_id=42&topic={topic}&consumer_id=beta"
        posted = state.handle_request("POST", alpha, frame(1))
        duplicated = state.handle_request("POST", alpha, frame(1))
        alpha_take = state.handle_request("GET", alpha)
        beta_take = state.handle_request("GET", beta)
        empty = state.handle_request("GET", alpha)
        invalid = state.handle_request("POST", alpha, b"not-a-frame")
        missing_query = state.handle_request("GET", "/fleetrmw/v1/frames")
        self.assertEqual(posted.status, 200)
        self.assertEqual(duplicated.status, 200)
        self.assertIn(b'"duplicate":true', duplicated.body)
        self.assertEqual(alpha_take.body, frame(1))
        self.assertEqual(beta_take.body, frame(1))
        self.assertEqual(empty.status, 204)
        self.assertEqual(invalid.status, 400)
        self.assertEqual(missing_query.status, 400)

    def test_fleet_admission_enforces_publisher_and_stream_quota(self) -> None:
        policy = GatewayAdmissionPolicy.from_document(
            {
                "schema_version": "fleetrmw.quic_gateway_admission_policy.v1",
                "default_action": "deny",
                "max_accepted_frames": 3,
                "rules": [
                    {
                        "domain_id": 42,
                        "topic": "/fleetqox/control",
                        "traffic_class": "control",
                        "max_accepted_frames": 2,
                        "allowed_publishers": ["control-publisher"],
                    }
                ],
            }
        )
        state = FleetQoxGatewayState(max_frames_per_topic=4, admission_policy=policy)
        control = quote("/fleetqox/control", safe="")
        uri = f"/fleetrmw/v1/frames?domain_id=42&topic={control}&consumer_id=a"
        first = state.handle_request(
            "POST", uri, frame(1, topic="/fleetqox/control", publisher_id="control-publisher")
        )
        duplicate = state.handle_request(
            "POST", uri, frame(1, topic="/fleetqox/control", publisher_id="control-publisher")
        )
        second = state.handle_request(
            "POST", uri, frame(2, topic="/fleetqox/control", publisher_id="control-publisher")
        )
        quota = state.handle_request(
            "POST", uri, frame(3, topic="/fleetqox/control", publisher_id="control-publisher")
        )
        denied = state.handle_request(
            "POST", uri, frame(4, topic="/fleetqox/control", publisher_id="intruder")
        )
        self.assertEqual(first.status, 200)
        self.assertEqual(duplicate.status, 200)
        self.assertEqual(second.status, 200)
        self.assertEqual(quota.status, 429)
        self.assertEqual(denied.status, 403)
        snapshot = state.snapshot()
        self.assertEqual(snapshot["accepted_frames"], 2)
        self.assertEqual(snapshot["duplicate_frames"], 1)
        self.assertEqual(snapshot["admission"]["accepted_by_class"], {"control": 2})
        self.assertEqual(
            snapshot["admission"]["rejected_by_reason"],
            {"publisher_not_allowed": 1, "stream_quota_exhausted": 1},
        )

    def test_fleet_admission_default_deny_does_not_create_topic_state(self) -> None:
        policy = GatewayAdmissionPolicy.from_document(
            {
                "schema_version": "fleetrmw.quic_gateway_admission_policy.v1",
                "default_action": "deny",
                "rules": [],
            }
        )
        state = FleetQoxGatewayState(admission_policy=policy)
        denied = state.handle_request(
            "POST",
            "/fleetrmw/v1/frames",
            frame(1, topic="/fleetqox/unknown"),
        )
        self.assertEqual(denied.status, 403)
        self.assertEqual(state.snapshot()["topic_count"], 0)

    def test_fleet_admission_epoch_replenishes_quota(self) -> None:
        now = [100.0]
        policy = GatewayAdmissionPolicy.from_document(
            {
                "schema_version": "fleetrmw.quic_gateway_admission_policy.v1",
                "default_action": "deny",
                "max_accepted_frames": 1,
                "epoch_ms": 250,
                "rules": [
                    {
                        "domain_id": 42,
                        "topic": "/fleetqox/control",
                        "traffic_class": "control",
                        "max_accepted_frames": 1,
                        "allowed_publishers": ["control-publisher"],
                    }
                ],
            },
            clock=lambda: now[0],
        )
        metadata = parse_data_frame(
            frame(1, topic="/fleetqox/control", publisher_id="control-publisher"),
            max_frame_bytes=4096,
        )
        policy.admit(metadata)
        with self.assertRaisesRegex(RuntimeError, "stream admission quota"):
            policy.admit(metadata)
        now[0] += 0.251
        policy.admit(metadata)
        snapshot = policy.snapshot()
        self.assertEqual(snapshot["accepted_total"], 1)
        self.assertEqual(snapshot["accepted_cumulative"], 2)
        self.assertEqual(snapshot["epoch_reset_count"], 1)

    def test_qos_qoe_threshold_and_repair_scheduler_override(self) -> None:
        policy = GatewayAdmissionPolicy.from_document(
            {
                "schema_version": "fleetrmw.quic_gateway_admission_policy.v1",
                "default_action": "deny",
                "max_accepted_frames": 1,
                "rules": [
                    {
                        "domain_id": 42,
                        "topic": "/fleetqox/control",
                        "traffic_class": "control",
                        "max_accepted_frames": 1,
                        "min_admission_score": 0.5,
                        "allowed_publishers": ["control-publisher"],
                    }
                ],
                "repair": {
                    "capacity_bytes": 65536,
                    "max_admitted": 1,
                    "paths": [
                        {
                            "path_id": "private_5g",
                            "latency_ms": 20.0,
                            "loss": 0.01,
                            "failure_domain": "private_5g",
                        }
                    ],
                },
            }
        )
        state = FleetQoxGatewayState(admission_policy=policy)
        uri = "/fleetrmw/v1/frames?domain_id=42&topic=%2Ffleetqox%2Fcontrol"
        low = state.handle_request(
            "POST",
            uri,
            frame(
                1,
                topic="/fleetqox/control",
                publisher_id="control-publisher",
                flow_class="control",
                deadline_ms=100.0,
            ),
        )
        high = state.handle_request(
            "POST",
            uri,
            frame(
                2,
                topic="/fleetqox/control",
                publisher_id="control-publisher",
                flow_class="control",
                deadline_ms=100.0,
                age_ms=80.0,
                qoe_debt=0.9,
                criticality=1.0,
            ),
        )
        repaired = state.handle_request(
            "POST",
            uri,
            frame(
                3,
                topic="/fleetqox/control",
                publisher_id="control-publisher",
                flow_class="control",
                deadline_ms=100.0,
                age_ms=85.0,
                qoe_debt=1.0,
                criticality=1.0,
                repair_requested=True,
            ),
        )
        deferred = state.handle_request(
            "POST",
            uri,
            frame(
                4,
                topic="/fleetqox/control",
                publisher_id="control-publisher",
                flow_class="control",
                deadline_ms=100.0,
                age_ms=90.0,
                qoe_debt=1.0,
                criticality=1.0,
                repair_requested=True,
                prior_repair_attempts=1,
            ),
        )
        self.assertEqual(low.status, 429)
        self.assertEqual(high.status, 200)
        self.assertEqual(repaired.status, 200)
        self.assertEqual(deferred.status, 429)
        snapshot = state.snapshot()
        self.assertEqual(snapshot["accepted_frames"], 2)
        self.assertEqual(snapshot["admission"]["repair_admitted_count"], 1)
        self.assertEqual(snapshot["admission"]["repair_deferred_count"], 1)
        self.assertGreater(snapshot["admission"]["repair_allocated_bytes"], 0)
        self.assertEqual(
            snapshot["admission"]["rejected_by_reason"],
            {"qox_score_below_threshold": 1, "stream_quota_exhausted": 1},
        )

    def test_closed_loop_observation_and_batch_prioritize_admission_and_repair(
        self,
    ) -> None:
        policy = GatewayAdmissionPolicy.from_document(
            {
                "schema_version": "fleetrmw.quic_gateway_admission_policy.v1",
                "default_action": "deny",
                "max_accepted_frames": 1,
                "observation_ttl_ms": 5000,
                "rules": [
                    {
                        "domain_id": 42,
                        "topic": "/fleetqox/closed-loop",
                        "traffic_class": "control",
                        "max_accepted_frames": 1,
                        "allowed_publishers": [
                            "low-publisher",
                            "observed-publisher",
                            "repair-low",
                            "repair-high",
                        ],
                    }
                ],
                "repair": {
                    "capacity_bytes": 1024,
                    "max_admitted": 2,
                    "paths": [
                        {
                            "path_id": "private_5g",
                            "latency_ms": 20.0,
                            "loss": 0.01,
                            "failure_domain": "private_5g",
                        }
                    ],
                },
            }
        )
        state = FleetQoxGatewayState(admission_policy=policy)
        observation = state.handle_request(
            "POST",
            OBSERVATION_API_PATH,
            json.dumps(
                {
                    "schema_version": OBSERVATION_SCHEMA_VERSION,
                    "domain_id": 42,
                    "topic": "/fleetqox/closed-loop",
                    "publisher_id": "observed-publisher",
                    "qoe_debt": 1.0,
                    "measured_loss": 1.0,
                    "measured_rtt_ms": 100.0,
                    "measured_jitter_ms": 100.0,
                },
                separators=(",", ":"),
            ).encode(),
        )
        self.assertEqual(observation.status, 200)

        low = frame(
            1,
            topic="/fleetqox/closed-loop",
            publisher_id="low-publisher",
            flow_class="control",
            deadline_ms=100.0,
            criticality=0.3,
        )
        observed = frame(
            2,
            topic="/fleetqox/closed-loop",
            publisher_id="observed-publisher",
            flow_class="control",
            deadline_ms=100.0,
            criticality=0.3,
        )
        normal_batch = state.handle_request(
            "POST",
            GATEWAY_BATCH_API_PATH,
            json.dumps(
                {
                    "schema_version": FRAME_BATCH_SCHEMA_VERSION,
                    "frames": [low.hex(), observed.hex()],
                },
                separators=(",", ":"),
            ).encode(),
        )
        self.assertEqual(normal_batch.status, 200)
        normal_results = json.loads(normal_batch.body)["results"]
        self.assertFalse(normal_results[0]["accepted"])
        self.assertEqual(normal_results[0]["reason"], "stream_quota_exhausted")
        self.assertTrue(normal_results[1]["accepted"])
        self.assertGreater(normal_results[1]["score"], normal_results[0]["score"])

        repair_low = frame(
            3,
            topic="/fleetqox/closed-loop",
            publisher_id="repair-low",
            flow_class="control",
            deadline_ms=100.0,
            age_ms=10.0,
            qoe_debt=0.1,
            criticality=0.2,
            repair_requested=True,
        )
        repair_high = frame(
            4,
            topic="/fleetqox/closed-loop",
            publisher_id="repair-high",
            flow_class="control",
            deadline_ms=100.0,
            age_ms=90.0,
            qoe_debt=1.0,
            criticality=1.0,
            repair_requested=True,
        )
        repair_batch = state.handle_request(
            "POST",
            GATEWAY_BATCH_API_PATH,
            json.dumps(
                {
                    "schema_version": FRAME_BATCH_SCHEMA_VERSION,
                    "frames": [repair_low.hex(), repair_high.hex()],
                },
                separators=(",", ":"),
            ).encode(),
        )
        self.assertEqual(repair_batch.status, 200)
        repair_results = json.loads(repair_batch.body)["results"]
        self.assertFalse(repair_results[0]["accepted"])
        self.assertTrue(repair_results[1]["accepted"])
        self.assertEqual(repair_results[1]["admission_action"], "repair")
        self.assertGreater(repair_results[1]["score"], repair_results[0]["score"])

        uri = (
            "/fleetrmw/v1/frames?domain_id=42&topic=%2Ffleetqox%2Fclosed-loop"
            "&consumer_id=feedback-test"
        )
        self.assertEqual(state.handle_request("GET", uri).body, observed)
        self.assertEqual(state.handle_request("GET", uri).body, repair_high)
        snapshot = state.snapshot()
        self.assertEqual(snapshot["batch_requests"], 2)
        self.assertEqual(snapshot["batch_frames"], 4)
        self.assertEqual(snapshot["batch_accepted_frames"], 2)
        self.assertEqual(snapshot["batch_rejected_frames"], 2)
        self.assertEqual(snapshot["admission"]["accepted_total"], 1)
        self.assertEqual(snapshot["admission"]["accepted_cumulative"], 2)
        self.assertEqual(snapshot["admission"]["accepted_by_class"], {"control": 2})
        self.assertEqual(snapshot["admission"]["repair_admitted_count"], 1)
        self.assertEqual(snapshot["admission"]["repair_deferred_count"], 1)
        self.assertGreater(snapshot["admission"]["repair_allocated_bytes"], 0)
        self.assertEqual(snapshot["admission"]["observation_updates"], 1)
        self.assertEqual(snapshot["admission"]["active_observation_count"], 1)
        self.assertEqual(
            snapshot["admission"]["observation_updates_by_source"],
            {"external_api": 1},
        )
        self.assertEqual(
            snapshot["admission"]["active_observations_by_source"],
            {"external_api": 1},
        )
        self.assertGreaterEqual(snapshot["admission"]["observation_score_uses"], 2)

    def test_closed_loop_observation_expires_at_configured_ttl(self) -> None:
        now = [100.0]
        policy = GatewayAdmissionPolicy.from_document(
            {
                "schema_version": "fleetrmw.quic_gateway_admission_policy.v1",
                "default_action": "allow",
                "observation_ttl_ms": 100,
                "rules": [],
            },
            clock=lambda: now[0],
        )
        metadata = parse_data_frame(
            frame(
                1,
                publisher_id="ttl-publisher",
                deadline_ms=100.0,
                criticality=0.2,
            ),
            max_frame_bytes=4096,
        )
        policy.update_observation(
            domain_id=42,
            topic="/fleetqox/gateway",
            publisher_id="ttl-publisher",
            qoe_debt=1.0,
            measured_loss=1.0,
            measured_rtt_ms=100.0,
            measured_jitter_ms=100.0,
        )
        self.assertGreater(
            policy.effective_admission_score(metadata), metadata.admission_score
        )
        now[0] += 0.101
        self.assertEqual(
            policy.effective_admission_score(metadata), metadata.admission_score
        )
        snapshot = policy.snapshot()
        self.assertEqual(snapshot["active_observation_count"], 0)
        self.assertEqual(snapshot["observation_expirations"], 1)

    def test_native_path_qoe_debt_is_derived_ewma_and_durable(self) -> None:
        document = {
            "schema_version": "fleetrmw.quic_gateway_admission_policy.v1",
            "default_action": "deny",
            "rules": [{
                "domain_id": 42,
                "topic": "/fleetqox/native-qoe",
                "traffic_class": "control",
                "max_accepted_frames": 2,
                "allowed_publishers": ["native-qoe-publisher"],
            }],
            "native_qoe_debt": {
                "enabled": True,
                "ewma_alpha": 0.5,
                "loss_saturation": 0.05,
                "rtt_deadline_ratio_saturation": 1.0,
                "jitter_deadline_ratio_saturation": 0.25,
            },
        }
        policy = GatewayAdmissionPolicy.from_document(document)
        metadata = parse_data_frame(
            frame(
                1,
                topic="/fleetqox/native-qoe",
                publisher_id="native-qoe-publisher",
                deadline_ms=100.0,
            ),
            max_frame_bytes=4096,
        )
        first = policy.update_native_path_observation(
            metadata=metadata,
            measured_loss=0.025,
            measured_rtt_ms=50.0,
            measured_jitter_ms=10.0,
        )
        self.assertAlmostEqual(first, 0.485)
        second = policy.update_native_path_observation(
            metadata=metadata,
            measured_loss=0.0,
            measured_rtt_ms=0.0,
            measured_jitter_ms=0.0,
        )
        self.assertAlmostEqual(second, 0.2425)
        self.assertGreater(policy.effective_admission_score(metadata), 0.0)
        snapshot = policy.snapshot()
        self.assertTrue(snapshot["native_qoe_debt_enabled"])
        self.assertEqual(snapshot["native_qoe_debt_updates"], 2)
        self.assertEqual(
            snapshot["active_observations_by_qoe_debt_source"],
            {"gateway_derived_path": 1},
        )
        durable = policy.export_durable_state()
        self.assertEqual(
            durable["observations"][0]["qoe_debt_source"],
            "gateway_derived_path",
        )
        replacement = GatewayAdmissionPolicy.from_document(document)
        replacement.restore_durable_state(durable)
        restored = replacement.snapshot()
        self.assertEqual(restored["native_qoe_debt_updates"], 2)
        self.assertEqual(
            restored["active_observations_by_qoe_debt_source"],
            {"gateway_derived_path": 1},
        )

    def test_native_qoe_debt_policy_parameters_fail_closed(self) -> None:
        base = {
            "schema_version": "fleetrmw.quic_gateway_admission_policy.v1",
            "default_action": "allow",
            "rules": [],
        }
        for native_qoe in (
            {"enabled": "yes"},
            {"enabled": True, "ewma_alpha": 0.0},
            {"enabled": True, "loss_saturation": 2.0},
            {"enabled": True, "rtt_deadline_ratio_saturation": 0.0},
            {"enabled": True, "jitter_deadline_ratio_saturation": -1.0},
        ):
            with self.subTest(native_qoe=native_qoe), self.assertRaises(ValueError):
                GatewayAdmissionPolicy.from_document(
                    {**base, "native_qoe_debt": native_qoe}
                )

    def test_application_outcome_debt_is_derived_ewma_and_durable(self) -> None:
        document = {
            "schema_version": "fleetrmw.quic_gateway_admission_policy.v1",
            "default_action": "allow",
            "rules": [],
            "application_outcome_qoe_debt": {
                "enabled": True,
                "ewma_alpha": 0.5,
            },
        }
        policy = GatewayAdmissionPolicy.from_document(document)
        first = policy.update_application_outcome(
            domain_id=42,
            topic="/fleetqox/outcome",
            publisher_id="outcome-publisher",
            delivered=False,
            deadline_met=False,
            observed_latency_ms=100.0,
            deadline_ms=100.0,
        )
        self.assertEqual(first, 1.0)
        second = policy.update_application_outcome(
            domain_id=42,
            topic="/fleetqox/outcome",
            publisher_id="outcome-publisher",
            delivered=True,
            deadline_met=True,
            observed_latency_ms=0.0,
            deadline_ms=100.0,
        )
        self.assertEqual(second, 0.5)
        snapshot = policy.snapshot()
        self.assertTrue(snapshot["application_outcome_qoe_debt_enabled"])
        self.assertEqual(snapshot["application_outcome_qoe_debt_updates"], 2)
        self.assertEqual(
            snapshot["active_observations_by_source"],
            {"application_outcome": 1},
        )
        self.assertEqual(
            snapshot["active_observations_by_qoe_debt_source"],
            {"gateway_derived_outcome": 1},
        )
        durable = policy.export_durable_state()
        replacement = GatewayAdmissionPolicy.from_document(document)
        replacement.restore_durable_state(durable)
        self.assertEqual(
            replacement.snapshot()["application_outcome_qoe_debt_updates"], 2
        )

    def test_application_outcome_policy_parameters_fail_closed(self) -> None:
        base = {
            "schema_version": "fleetrmw.quic_gateway_admission_policy.v1",
            "default_action": "allow",
            "rules": [],
        }
        for outcome_qoe in (
            "enabled",
            {"enabled": "yes"},
            {"enabled": True, "ewma_alpha": 0.0},
            {"enabled": True, "ewma_alpha": 1.1},
            {"enabled": True, "ewma_alpha": float("nan")},
        ):
            with self.subTest(outcome_qoe=outcome_qoe), self.assertRaises(ValueError):
                GatewayAdmissionPolicy.from_document({
                    **base,
                    "application_outcome_qoe_debt": outcome_qoe,
                })

    def test_application_task_outcome_keeps_delivery_and_success_distinct(
        self,
    ) -> None:
        policy = GatewayAdmissionPolicy.from_document({
            "schema_version": "fleetrmw.quic_gateway_admission_policy.v1",
            "default_action": "allow",
            "rules": [],
            "application_outcome_qoe_debt": {
                "enabled": True,
                "ewma_alpha": 1.0,
            },
        })
        state = FleetQoxGatewayState(admission_policy=policy)
        state.publish(frame(1))
        canceled = {
            "schema_version": APPLICATION_OUTCOME_SCHEMA_VERSION,
            "domain_id": 42,
            "topic": "/fleetqox/gateway",
            "publisher_id": "gateway-probe-publisher",
            "source_sequence_number": 1,
            "delivered": True,
            "deadline_met": True,
            "observed_latency_ms": 0.0,
            "deadline_ms": 100.0,
            "task_kind": "nav2",
            "terminal_status": "canceled",
            "task_succeeded": False,
        }
        accepted = state.handle_request(
            "POST", APPLICATION_OUTCOME_API_PATH, json.dumps(canceled).encode()
        )
        self.assertEqual(accepted.status, 200)
        self.assertEqual(json.loads(accepted.body)["qoe_debt"], 0.25)

        duplicate = state.handle_request(
            "POST", APPLICATION_OUTCOME_API_PATH, json.dumps(canceled).encode()
        )
        self.assertEqual(duplicate.status, 200)
        self.assertTrue(json.loads(duplicate.body)["duplicate"])
        snapshot = state.snapshot()
        self.assertEqual(snapshot["application_task_outcome_updates"], 1)
        self.assertEqual(snapshot["application_task_outcome_failures"], 1)
        self.assertEqual(
            snapshot["admission"]["application_task_outcome_updates"], 1
        )
        self.assertEqual(
            snapshot["admission"]["application_task_outcome_failures"], 1
        )

        for mutation in (
            {"task_succeeded": None},
            {"terminal_status": "succeeded"},
            {"task_kind": "unknown"},
        ):
            malformed = {**canceled, **mutation}
            with self.subTest(mutation=mutation):
                self.assertEqual(
                    state.handle_request(
                        "POST",
                        APPLICATION_OUTCOME_API_PATH,
                        json.dumps(malformed).encode(),
                    ).status,
                    400,
                )

    def test_successful_application_task_outcome_adds_no_task_pressure(
        self,
    ) -> None:
        policy = GatewayAdmissionPolicy.from_document({
            "schema_version": "fleetrmw.quic_gateway_admission_policy.v1",
            "default_action": "allow",
            "rules": [],
            "application_outcome_qoe_debt": {
                "enabled": True,
                "ewma_alpha": 1.0,
            },
        })
        self.assertEqual(
            policy.update_application_outcome(
                domain_id=42,
                topic="/fleetqox/task-success",
                publisher_id="task-client",
                delivered=True,
                deadline_met=True,
                observed_latency_ms=0.0,
                deadline_ms=100.0,
                task_succeeded=True,
            ),
            0.0,
        )
        snapshot = policy.snapshot()
        self.assertEqual(snapshot["application_task_outcome_updates"], 1)
        self.assertEqual(snapshot["application_task_outcome_failures"], 0)

    def test_application_outcome_requires_known_frame_and_changes_admission(self) -> None:
        policy = GatewayAdmissionPolicy.from_document(
            {
                "schema_version": "fleetrmw.quic_gateway_admission_policy.v1",
                "default_action": "deny",
                "rules": [{
                    "domain_id": 42,
                    "topic": "/fleetqox/outcome",
                    "traffic_class": "control",
                    "max_accepted_frames": 2,
                    "allowed_publishers": ["outcome-publisher"],
                    "min_admission_score": 0.45,
                }],
                "application_outcome_qoe_debt": {
                    "enabled": True,
                    "ewma_alpha": 1.0,
                },
            }
        )
        state = FleetQoxGatewayState(
            max_frames_per_topic=4, admission_policy=policy
        )
        seed = frame(
            1,
            topic="/fleetqox/outcome",
            publisher_id="outcome-publisher",
            deadline_ms=100.0,
            criticality=1.0,
        )
        low = frame(
            2,
            topic="/fleetqox/outcome",
            publisher_id="outcome-publisher",
            deadline_ms=100.0,
            criticality=0.2,
        )
        self.assertEqual(state.handle_request("POST", "/fleetrmw/v1/frames", seed).status, 200)
        self.assertEqual(state.handle_request("POST", "/fleetrmw/v1/frames", low).status, 429)

        def outcome(sequence: int, *, delivered=True, deadline_met=True):
            return json.dumps({
                "schema_version": APPLICATION_OUTCOME_SCHEMA_VERSION,
                "domain_id": 42,
                "topic": "/fleetqox/outcome",
                "publisher_id": "outcome-publisher",
                "source_sequence_number": sequence,
                "delivered": delivered,
                "deadline_met": deadline_met,
                "observed_latency_ms": 100.0,
                "deadline_ms": 100.0,
            }).encode()

        self.assertEqual(
            state.handle_request("POST", APPLICATION_OUTCOME_API_PATH, outcome(9)).status,
            404,
        )
        malformed = json.loads(outcome(1))
        malformed["delivered"] = "no"
        self.assertEqual(
            state.handle_request(
                "POST", APPLICATION_OUTCOME_API_PATH, json.dumps(malformed).encode()
            ).status,
            400,
        )
        accepted = state.handle_request(
            "POST",
            APPLICATION_OUTCOME_API_PATH,
            outcome(1, delivered=False, deadline_met=False),
        )
        self.assertEqual(accepted.status, 200)
        self.assertEqual(json.loads(accepted.body)["qoe_debt"], 1.0)
        duplicate = state.handle_request(
            "POST",
            APPLICATION_OUTCOME_API_PATH,
            outcome(1, delivered=False, deadline_met=False),
        )
        self.assertEqual(duplicate.status, 200)
        self.assertTrue(json.loads(duplicate.body)["duplicate"])
        self.assertEqual(state.handle_request("POST", "/fleetrmw/v1/frames", low).status, 200)
        snapshot = state.snapshot()
        self.assertEqual(snapshot["application_outcome_requests"], 4)
        self.assertEqual(snapshot["application_outcome_updates"], 1)
        self.assertEqual(snapshot["application_outcome_duplicates"], 1)
        self.assertEqual(snapshot["application_outcome_unknown_frames"], 1)
        self.assertEqual(snapshot["invalid_application_outcomes"], 1)
        self.assertEqual(snapshot["application_outcome_key_count"], 1)
        self.assertEqual(
            snapshot["admission"]["rejected_by_reason"],
            {"qox_score_below_threshold": 1},
        )

    def test_durable_application_outcome_and_admission_resume_idempotently(
        self,
    ) -> None:
        policy_document = {
            "schema_version": "fleetrmw.quic_gateway_admission_policy.v1",
            "default_action": "allow",
            "rules": [],
            "application_outcome_qoe_debt": {
                "enabled": True,
                "ewma_alpha": 1.0,
            },
        }
        outcome = json.dumps({
            "schema_version": APPLICATION_OUTCOME_SCHEMA_VERSION,
            "domain_id": 42,
            "topic": "/fleetqox/durable-outcome",
            "publisher_id": "durable-outcome-publisher",
            "source_sequence_number": 1,
            "delivered": False,
            "deadline_met": False,
            "observed_latency_ms": 100.0,
            "deadline_ms": 100.0,
        }).encode()
        with tempfile.TemporaryDirectory() as temporary_directory:
            database = Path(temporary_directory) / "gateway-state.sqlite3"
            active = FleetQoxGatewayState(
                durable_state_path=database,
                admission_policy=GatewayAdmissionPolicy.from_document(
                    policy_document
                ),
            )
            active.publish(frame(
                1,
                topic="/fleetqox/durable-outcome",
                publisher_id="durable-outcome-publisher",
            ))
            accepted = active.handle_request(
                "POST", APPLICATION_OUTCOME_API_PATH, outcome
            )
            self.assertEqual(accepted.status, 200)
            self.assertEqual(json.loads(accepted.body)["qoe_debt"], 1.0)
            before = active.snapshot()
            self.assertEqual(before["durable_application_outcome_commits"], 1)
            self.assertEqual(before["durable_admission_commits"], 2)
            self.assertEqual(
                before["durable_state"]["application_outcome_count"], 1
            )
            active.close()

            standby = FleetQoxGatewayState(
                durable_state_path=database,
                admission_policy=GatewayAdmissionPolicy.from_document(
                    policy_document
                ),
            )
            recovered = standby.snapshot()
            self.assertEqual(recovered["recovered_application_outcomes"], 1)
            self.assertEqual(recovered["application_outcome_key_count"], 1)
            self.assertEqual(
                recovered["admission"]["application_outcome_qoe_debt_updates"],
                1,
            )
            self.assertEqual(
                recovered["admission"][
                    "active_observations_by_qoe_debt_source"
                ],
                {"gateway_derived_outcome": 1},
            )
            duplicate = standby.handle_request(
                "POST", APPLICATION_OUTCOME_API_PATH, outcome
            )
            self.assertEqual(duplicate.status, 200)
            self.assertTrue(json.loads(duplicate.body)["duplicate"])
            after = standby.snapshot()
            self.assertEqual(after["application_outcome_duplicates"], 1)
            self.assertEqual(after["durable_application_outcome_commits"], 0)
            self.assertEqual(
                after["admission"]["application_outcome_qoe_debt_updates"], 1
            )
            standby.close()

    def test_durable_application_outcome_failure_restores_policy_state(self) -> None:
        policy = GatewayAdmissionPolicy.from_document({
            "schema_version": "fleetrmw.quic_gateway_admission_policy.v1",
            "default_action": "allow",
            "rules": [],
            "application_outcome_qoe_debt": {"enabled": True},
        })
        with tempfile.TemporaryDirectory() as temporary_directory:
            state = FleetQoxGatewayState(
                durable_state_path=(
                    Path(temporary_directory) / "gateway-state.sqlite3"
                ),
                admission_policy=policy,
            )
            state.publish(frame(1))

            def fail_commit(**_kwargs):
                raise FramePersistenceError("injected outcome persistence failure")

            state._durable_store.commit_application_outcome = fail_commit
            response = state.handle_request(
                "POST",
                APPLICATION_OUTCOME_API_PATH,
                json.dumps({
                    "schema_version": APPLICATION_OUTCOME_SCHEMA_VERSION,
                    "domain_id": 42,
                    "topic": "/fleetqox/gateway",
                    "publisher_id": "gateway-probe-publisher",
                    "source_sequence_number": 1,
                    "delivered": False,
                    "deadline_met": False,
                    "observed_latency_ms": 100.0,
                    "deadline_ms": 100.0,
                    "task_kind": "generic",
                    "terminal_status": "failed",
                    "task_succeeded": False,
                }).encode(),
            )
            self.assertEqual(response.status, 503)
            snapshot = state.snapshot()
            self.assertEqual(snapshot["application_outcome_key_count"], 0)
            self.assertEqual(snapshot["durable_persistence_failures"], 1)
            self.assertEqual(
                snapshot["admission"]["application_outcome_qoe_debt_updates"],
                0,
            )
            self.assertEqual(snapshot["application_task_outcome_updates"], 0)
            self.assertEqual(snapshot["application_task_outcome_failures"], 0)
            self.assertEqual(
                snapshot["admission"]["application_task_outcome_updates"], 0
            )
            self.assertEqual(
                snapshot["admission"]["application_task_outcome_failures"], 0
            )
            self.assertEqual(snapshot["admission"]["active_observation_count"], 0)
            self.assertEqual(
                snapshot["durable_state"]["application_outcome_count"], 0
            )
            state.close()

    def test_durable_state_recovers_frames_dedup_and_consumer_cursor(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            database = Path(temporary_directory) / "gateway-state.sqlite3"
            active = FleetQoxGatewayState(
                max_frames_per_topic=4, durable_state_path=database
            )
            active.publish(frame(1))
            active.publish(frame(2))
            active.publish(frame(3))
            self.assertEqual(
                active.snapshot()["durable_state"]["retained_frame_count"], 3
            )
            active.close()

            standby = FleetQoxGatewayState(
                max_frames_per_topic=4, durable_state_path=database
            )
            recovered = standby.snapshot()
            self.assertEqual(recovered["recovered_frames"], 3)
            self.assertEqual(recovered["recovered_dedup_keys"], 3)
            duplicate = standby.publish(frame(1))
            self.assertTrue(duplicate.duplicate)
            self.assertFalse(duplicate.accepted)
            self.assertEqual(
                standby.take(
                    domain_id=42,
                    topic="/fleetqox/gateway",
                    consumer_id="durable-consumer",
                ),
                frame(1),
            )
            self.assertEqual(
                standby.take(
                    domain_id=42,
                    topic="/fleetqox/gateway",
                    consumer_id="durable-consumer",
                ),
                frame(2),
            )
            standby.close()

            replacement = FleetQoxGatewayState(
                max_frames_per_topic=4, durable_state_path=database
            )
            resumed = replacement.snapshot()
            self.assertEqual(resumed["recovered_frames"], 3)
            self.assertEqual(resumed["recovered_consumers"], 1)
            self.assertEqual(
                replacement.take(
                    domain_id=42,
                    topic="/fleetqox/gateway",
                    consumer_id="durable-consumer",
                ),
                frame(3),
            )
            self.assertEqual(
                replacement.snapshot()["durable_state"]["consumer_cursor_count"],
                1,
            )
            replacement.close()

    def test_durable_state_retains_evicted_dedup_keys_across_restart(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            database = Path(temporary_directory) / "gateway-state.sqlite3"
            active = FleetQoxGatewayState(
                max_frames_per_topic=2, durable_state_path=database
            )
            active.publish(frame(1))
            active.publish(frame(2))
            active.publish(frame(3))
            active.close()

            standby = FleetQoxGatewayState(
                max_frames_per_topic=2, durable_state_path=database
            )
            snapshot = standby.snapshot()
            self.assertEqual(snapshot["retained_frames"], 2)
            self.assertEqual(snapshot["recovered_frames"], 2)
            self.assertEqual(snapshot["recovered_dedup_keys"], 3)
            duplicate = standby.publish(frame(1))
            self.assertTrue(duplicate.duplicate)
            self.assertEqual(
                standby.take(
                    domain_id=42,
                    topic="/fleetqox/gateway",
                    consumer_id="eviction-consumer",
                ),
                frame(2),
            )
            standby.close()

    def test_legacy_durable_frames_without_admission_state_fail_closed(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            database = Path(temporary_directory) / "gateway-state.sqlite3"
            active = FleetQoxGatewayState(durable_state_path=database)
            active.publish(frame(1))
            active.close()
            policy = GatewayAdmissionPolicy.from_document(
                {
                    "schema_version": "fleetrmw.quic_gateway_admission_policy.v1",
                    "default_action": "allow",
                    "rules": [],
                }
            )
            with self.assertRaisesRegex(
                ValueError, "retained frames lack durable admission state"
            ):
                FleetQoxGatewayState(
                    durable_state_path=database, admission_policy=policy
                )

    def test_durable_admission_and_repair_state_resume_across_restart(self) -> None:
        policy_document = {
            "schema_version": "fleetrmw.quic_gateway_admission_policy.v1",
            "default_action": "deny",
            "max_accepted_frames": 1,
            "rules": [
                {
                    "domain_id": 42,
                    "topic": "/fleetqox/gateway",
                    "traffic_class": "control",
                    "max_accepted_frames": 1,
                    "allowed_publishers": ["gateway-probe-publisher"],
                }
            ],
            "repair": {
                "capacity_bytes": 1024,
                "max_admitted": 1,
                "paths": [
                    {
                        "path_id": "private_5g",
                        "latency_ms": 10.0,
                        "loss": 0.01,
                        "failure_domain": "private_5g",
                    }
                ],
            },
        }
        with tempfile.TemporaryDirectory() as temporary_directory:
            database = Path(temporary_directory) / "gateway-state.sqlite3"
            active = FleetQoxGatewayState(
                durable_state_path=database,
                admission_policy=GatewayAdmissionPolicy.from_document(
                    policy_document
                ),
            )
            active.publish(
                frame(1, flow_class="control", qoe_debt=1.0, criticality=1.0)
            )
            repaired = active.publish(
                frame(
                    2,
                    flow_class="control",
                    qoe_debt=1.0,
                    criticality=1.0,
                    repair_requested=True,
                )
            )
            self.assertEqual(repaired.admission_action, "repair")
            before = active.snapshot()
            self.assertEqual(before["durable_admission_commits"], 2)
            self.assertEqual(
                before["durable_state"]["admission_state_count"], 1
            )
            allocated = before["admission"]["repair_allocated_bytes"]
            active.close()

            standby = FleetQoxGatewayState(
                durable_state_path=database,
                admission_policy=GatewayAdmissionPolicy.from_document(
                    policy_document
                ),
            )
            recovered = standby.snapshot()
            self.assertEqual(recovered["recovered_frames"], 2)
            self.assertEqual(recovered["recovered_admission_state"], 1)
            self.assertEqual(recovered["admission"]["accepted_total"], 1)
            self.assertEqual(recovered["admission"]["accepted_cumulative"], 2)
            self.assertEqual(recovered["admission"]["repair_admitted_count"], 1)
            self.assertEqual(
                recovered["admission"]["repair_allocated_bytes"], allocated
            )
            with self.assertRaises(FrameAdmissionError):
                standby.publish(
                    frame(
                        3,
                        flow_class="control",
                        qoe_debt=1.0,
                        criticality=1.0,
                        repair_requested=True,
                    )
                )
            standby.close()

    def test_durable_admission_policy_fingerprint_mismatch_fails_closed(self) -> None:
        base_document = {
            "schema_version": "fleetrmw.quic_gateway_admission_policy.v1",
            "default_action": "allow",
            "max_accepted_frames": 1,
            "rules": [],
        }
        with tempfile.TemporaryDirectory() as temporary_directory:
            database = Path(temporary_directory) / "gateway-state.sqlite3"
            active = FleetQoxGatewayState(
                durable_state_path=database,
                admission_policy=GatewayAdmissionPolicy.from_document(base_document),
            )
            active.publish(frame(1))
            active.close()
            changed_document = {**base_document, "max_accepted_frames": 2}
            with self.assertRaisesRegex(
                FramePersistenceError, "fingerprint does not match"
            ):
                FleetQoxGatewayState(
                    durable_state_path=database,
                    admission_policy=GatewayAdmissionPolicy.from_document(
                        changed_document
                    ),
                )

    def test_durable_writer_lease_fences_concurrent_standby_then_allows_takeover(
        self,
    ) -> None:
        now = [100.0]
        with tempfile.TemporaryDirectory() as temporary_directory:
            database = Path(temporary_directory) / "gateway-state.sqlite3"
            active = FleetQoxGatewayState(
                durable_state_path=database,
                durable_writer_id="gateway-a",
                durable_writer_lease_ms=1000,
                wall_clock=lambda: now[0],
            )
            with self.assertRaisesRegex(
                FramePersistenceError, "writer lease is held"
            ):
                FleetQoxGatewayState(
                    durable_state_path=database,
                    durable_writer_id="gateway-b",
                    durable_writer_lease_ms=1000,
                    wall_clock=lambda: now[0],
                )
            active.close()
            standby = FleetQoxGatewayState(
                durable_state_path=database,
                durable_writer_id="gateway-b",
                durable_writer_lease_ms=1000,
                wall_clock=lambda: now[0],
            )
            lease = standby.snapshot()["durable_state"]["writer_lease"]
            self.assertEqual(lease["holder_id"], "gateway-b")
            self.assertEqual(lease["fence_token"], 2)
            standby.close()

    def test_expired_writer_is_rejected_inside_frame_transaction(self) -> None:
        now_a = [100.0]
        now_b = [102.0]
        with tempfile.TemporaryDirectory() as temporary_directory:
            database = Path(temporary_directory) / "gateway-state.sqlite3"
            stale = FleetQoxGatewayState(
                durable_state_path=database,
                durable_writer_id="gateway-a",
                durable_writer_lease_ms=1000,
                wall_clock=lambda: now_a[0],
            )
            takeover = FleetQoxGatewayState(
                durable_state_path=database,
                durable_writer_id="gateway-b",
                durable_writer_lease_ms=1000,
                wall_clock=lambda: now_b[0],
            )
            with self.assertRaisesRegex(FramePersistenceError, "writer fence"):
                stale.publish(frame(1))
            self.assertEqual(stale.snapshot()["retained_frames"], 0)
            takeover.publish(frame(1))
            self.assertEqual(takeover.snapshot()["retained_frames"], 1)
            stale.close()
            takeover.close()

    def test_expired_writer_is_rejected_inside_cursor_transaction(self) -> None:
        now_a = [100.0]
        now_b = [102.0]
        with tempfile.TemporaryDirectory() as temporary_directory:
            database = Path(temporary_directory) / "gateway-state.sqlite3"
            stale = FleetQoxGatewayState(
                durable_state_path=database,
                durable_writer_id="gateway-a",
                durable_writer_lease_ms=1000,
                wall_clock=lambda: now_a[0],
            )
            stale.publish(frame(1))
            takeover = FleetQoxGatewayState(
                durable_state_path=database,
                durable_writer_id="gateway-b",
                durable_writer_lease_ms=1000,
                wall_clock=lambda: now_b[0],
            )
            with self.assertRaisesRegex(FramePersistenceError, "writer fence"):
                stale.take(
                    domain_id=42,
                    topic="/fleetqox/gateway",
                    consumer_id="stale",
                )
            self.assertEqual(stale.snapshot()["consumer_count"], 0)
            self.assertIsNotNone(
                takeover.take(
                    domain_id=42,
                    topic="/fleetqox/gateway",
                    consumer_id="takeover",
                )
            )
            self.assertEqual(takeover.snapshot()["consumer_count"], 1)
            stale.close()
            takeover.close()


if __name__ == "__main__":
    unittest.main()

import json
import unittest
from unittest.mock import patch

from fleetqox.projection_identity import projection_signature
from fleetqox.projection_quality_ros import FLEETRMW_PROJECTION_QUALITY_MSG_TYPE
from fleetqox.projection_quality_ros import (
    FLEETRMW_QUALIFIED_LASER_SCAN_MSG_TYPE,
    FLEETRMW_QUALIFIED_ODOMETRY_MSG_TYPE,
)
from fleetqox.rmw_ack import ACK_NACK_SCHEMA_VERSION, RmwAckNackTracker
from fleetqox.sidecar_contract import SIDECAR_TRACE_SCHEMA_VERSION
from fleetqox.rmw_frame import data_frame_from_sidecar_event, encode_data_frame
from fleetqox.sidecar_egress import (
    SidecarEgressRouter,
    decode_sidecar_packet,
    publication_kind_and_suffix,
    robot_feedback_record_from_event,
    ros_topic_token,
    sanitize_twist_payload,
)
from scripts.run_ros2_egress_bridge import (
    ControlLeaseAckPacer,
    control_lease_ack_keys_from_feedback_windows,
    flush_feedback_windows,
    immediate_control_lease_ack_record,
    is_control_lease_feedback,
    maybe_send_immediate_control_lease_ack,
    maybe_queue_control_lease_ack,
    update_feedback_window,
)


class SidecarEgressTest(unittest.TestCase):
    def test_decodes_padded_sidecar_packet(self) -> None:
        packet = json.dumps(_event(action="send_supervisory_intent", wire_mode="supervisory_intent")).encode("utf-8")

        decoded = decode_sidecar_packet(packet + b"    ")

        self.assertIsNotNone(decoded)
        self.assertEqual(decoded["event_id"], 7)
        self.assertEqual(decoded["wire_mode"], "supervisory_intent")

    def test_decodes_data_frame_sidecar_packet(self) -> None:
        event = _event(action="send", wire_mode="native")
        event["source_sample_id"] = "fsid1-source"
        event["sample_envelope"] = {
            "schema_version": "fleetrmw.sample_envelope.v1",
            "publisher_id": "fpub1-native",
            "source_sample_id": "fsid1-source",
            "robot_id": "robot_0000",
            "topic": "/robot_0000/cmd_vel",
            "msg_type": "geometry_msgs/msg/Twist",
            "source_sequence_number": 1,
        }
        packet = encode_data_frame(data_frame_from_sidecar_event(event), target_size=2048)

        decoded = decode_sidecar_packet(packet)

        self.assertIsNotNone(decoded)
        assert decoded is not None
        self.assertEqual(decoded["event_id"], 7)
        self.assertEqual(decoded["data_frame_id"][:6], "ffrm1-")
        self.assertEqual(decoded["sample_envelope"]["publisher_id"], "fpub1-native")

    def test_routes_supervisory_intent_to_control_lease(self) -> None:
        router = SidecarEgressRouter()
        event = _event(action="send_supervisory_intent", wire_mode="supervisory_intent")

        publications = router.route(event)

        self.assertEqual(len(publications), 1)
        self.assertEqual(publications[0].topic, "/fleetrmw/robot_0000/control_lease")
        self.assertEqual(publications[0].kind, "supervisory_intent")
        payload = json.loads(publications[0].payload)
        self.assertEqual(payload["kind"], "supervisory_intent")
        self.assertEqual(payload["source_topic"], "/robot_0000/cmd_vel")
        self.assertEqual(payload["valid_until_timestamp_ms"], 90.0)

    def test_routes_typed_twist_when_enabled_and_payload_available(self) -> None:
        router = SidecarEgressRouter(enable_typed_reconstruction=True)
        event = _event(action="send_supervisory_intent", wire_mode="supervisory_intent")
        event["semantic_payload"] = _twist_payload()

        publications = router.route(event)

        self.assertEqual(len(publications), 3)
        typed = [publication for publication in publications if publication.msg_type == "geometry_msgs/msg/Twist"][0]
        meta = [publication for publication in publications if publication.kind == "typed_projection_quality"][0]
        self.assertEqual(typed.topic, "/fleetrmw/robot_0000/local_cmd_vel")
        self.assertEqual(typed.kind, "typed_twist")
        payload = json.loads(typed.payload)
        self.assertEqual(payload["twist"]["linear"]["x"], 0.4)
        self.assertEqual(payload["twist"]["angular"]["z"], 0.15)
        quality = json.loads(meta.payload)
        self.assertEqual(quality["projection_kind"], "typed_twist")
        self.assertEqual(quality["projection_topic"], "/fleetrmw/robot_0000/local_cmd_vel")
        self.assertEqual(quality["fidelity_class"], "degraded_projection")
        self.assertTrue(quality["lossy"])
        self.assertIn("control_authority_projection", quality["degradation_reasons"])
        self.assertEqual(quality["projection_payload"]["event_id"], 7)
        self.assertEqual(quality["projection_payload"]["twist"]["linear"]["x"], 0.4)
        self.assertRegex(quality["projection_signature"], r"^[0-9a-f]{64}$")
        self.assertEqual(quality["projection_signature"], projection_signature("typed_twist", quality["projection_payload"]))

    def test_routes_typed_odom_when_enabled_and_payload_available(self) -> None:
        router = SidecarEgressRouter(enable_typed_reconstruction=True)
        event = _event(action="send_degraded", wire_mode="degraded")
        event["topic"] = "/robot_0000/odom"
        event["semantic_payload"] = _odom_payload()

        publications = router.route(event)

        typed = [publication for publication in publications if publication.msg_type == "nav_msgs/msg/Odometry"][0]
        meta = [publication for publication in publications if publication.kind == "typed_projection_quality"][0]
        self.assertEqual(typed.topic, "/fleetrmw/robot_0000/local_odom")
        self.assertEqual(typed.kind, "typed_odom")
        payload = json.loads(typed.payload)
        self.assertEqual(payload["header"]["frame_id"], "odom")
        self.assertEqual(payload["odometry"]["child_frame_id"], "robot_0000")
        self.assertEqual(payload["odometry"]["pose"]["position"]["x"], 1.2)
        quality = json.loads(meta.payload)
        self.assertEqual(quality["projection_kind"], "typed_odom")
        self.assertEqual(quality["projection_msg_type"], "nav_msgs/msg/Odometry")
        self.assertEqual(quality["fidelity_class"], "degraded_projection")
        self.assertEqual(quality["projection_payload"]["projection_topic"], "/fleetrmw/robot_0000/local_odom")
        self.assertEqual(quality["projection_payload"]["odometry"]["pose"]["position"]["x"], 1.2)
        self.assertEqual(quality["projection_signature"], projection_signature("typed_odom", quality["projection_payload"]))

    def test_semantic_delta_odom_projection_is_semantic_not_degraded(self) -> None:
        router = SidecarEgressRouter(enable_typed_reconstruction=True)
        event = _event(action="send_compacted", wire_mode="semantic_delta")
        event["flow_class"] = "state"
        event["topic"] = "/robot_0000/odom"
        event["semantic_payload"] = _odom_payload()

        publications = router.route(event)

        meta = [publication for publication in publications if publication.kind == "typed_projection_quality"][0]
        quality = json.loads(meta.payload)
        self.assertEqual(quality["projection_kind"], "typed_odom")
        self.assertEqual(quality["fidelity_class"], "semantic_projection")
        self.assertTrue(quality["lossy"])
        self.assertIn("wire_mode:semantic_delta", quality["degradation_reasons"])

    def test_routes_typed_scan_when_enabled_and_payload_available(self) -> None:
        router = SidecarEgressRouter(enable_typed_reconstruction=True)
        event = _event(action="send_degraded", wire_mode="degraded")
        event["topic"] = "/robot_0000/scan"
        event["semantic_payload"] = _scan_payload()

        publications = router.route(event)

        typed = [publication for publication in publications if publication.msg_type == "sensor_msgs/msg/LaserScan"][0]
        meta = [publication for publication in publications if publication.kind == "typed_projection_quality"][0]
        self.assertEqual(typed.topic, "/fleetrmw/robot_0000/local_scan")
        self.assertEqual(typed.kind, "typed_scan")
        payload = json.loads(typed.payload)
        self.assertEqual(payload["header"]["frame_id"], "robot_0000/base_scan")
        self.assertEqual(payload["scan"]["ranges"], [1.0, 1.1, 1.2])
        self.assertEqual(payload["scan"]["downsample_stride"], 2)
        quality = json.loads(meta.payload)
        self.assertEqual(quality["projection_kind"], "typed_scan")
        self.assertEqual(quality["fidelity_class"], "downsampled_projection")
        self.assertEqual(quality["source_sample_count"], 6)
        self.assertEqual(quality["projected_sample_count"], 3)
        self.assertEqual(quality["downsample_stride"], 2)
        self.assertIn("range_downsampled", quality["degradation_reasons"])
        self.assertEqual(quality["projection_payload"]["projection_topic"], "/fleetrmw/robot_0000/local_scan")
        self.assertEqual(quality["projection_payload"]["scan"]["ranges"], [1.0, 1.1, 1.2])
        self.assertEqual(quality["projection_signature"], projection_signature("typed_scan", quality["projection_payload"]))

    def test_can_publish_compact_projection_quality_without_embedded_payload(self) -> None:
        router = SidecarEgressRouter(enable_typed_reconstruction=True, include_projection_payload=False)
        event = _event(action="send", wire_mode="native")
        event["topic"] = "/robot_0000/odom"
        event["semantic_payload"] = _odom_payload()

        publications = router.route(event)

        typed = [publication for publication in publications if publication.msg_type == "nav_msgs/msg/Odometry"][0]
        meta = [publication for publication in publications if publication.kind == "typed_projection_quality"][0]
        typed_payload = json.loads(typed.payload)
        quality = json.loads(meta.payload)
        self.assertEqual(quality["projection_kind"], "typed_odom")
        self.assertEqual(quality["projection_payload_embedded"], False)
        self.assertNotIn("projection_payload", quality)
        self.assertEqual(quality["projection_signature"], projection_signature("typed_odom", typed_payload))

    def test_can_route_projection_quality_as_typed_interface_message(self) -> None:
        router = SidecarEgressRouter(
            enable_typed_reconstruction=True,
            include_projection_payload=False,
            projection_quality_msg_type=FLEETRMW_PROJECTION_QUALITY_MSG_TYPE,
        )
        event = _event(action="send", wire_mode="native")
        event["topic"] = "/robot_0000/odom"
        event["semantic_payload"] = _odom_payload()

        publications = router.route(event)

        meta = [publication for publication in publications if publication.kind == "typed_projection_quality"][0]
        self.assertEqual(meta.msg_type, FLEETRMW_PROJECTION_QUALITY_MSG_TYPE)
        self.assertEqual(meta.topic, "/fleetrmw/robot_0000/projection_quality")

    def test_can_route_qualified_odom_without_sideband_or_bare_state_topic(self) -> None:
        router = SidecarEgressRouter(
            enable_typed_reconstruction=True,
            include_projection_payload=False,
            projection_quality_delivery="wrapper",
        )
        event = _event(action="send", wire_mode="native")
        event["topic"] = "/robot_0000/odom"
        event["semantic_payload"] = _odom_payload()

        publications = router.route(event)

        self.assertEqual([publication.kind for publication in publications], ["native", "qualified_odom"])
        self.assertFalse(any(publication.topic.endswith("/projection_quality") for publication in publications))
        self.assertFalse(any(publication.topic.endswith("/local_odom") for publication in publications))
        qualified = [publication for publication in publications if publication.kind == "qualified_odom"][0]
        payload = json.loads(qualified.payload)
        self.assertEqual(qualified.msg_type, FLEETRMW_QUALIFIED_ODOMETRY_MSG_TYPE)
        self.assertEqual(qualified.topic, "/fleetrmw/robot_0000/qualified_odom")
        self.assertEqual(payload["sample"]["odometry"]["pose"]["position"]["x"], 1.2)
        self.assertEqual(payload["quality"]["projection_kind"], "typed_odom")
        self.assertFalse(payload["quality"]["projection_payload_embedded"])
        self.assertNotIn("projection_payload", payload["quality"])

    def test_can_route_qualified_scan_without_sideband_or_bare_state_topic(self) -> None:
        router = SidecarEgressRouter(
            enable_typed_reconstruction=True,
            include_projection_payload=False,
            projection_quality_delivery="wrapper",
        )
        event = _event(action="send_degraded", wire_mode="degraded")
        event["topic"] = "/robot_0000/scan"
        event["semantic_payload"] = _scan_payload()

        publications = router.route(event)

        self.assertEqual([publication.kind for publication in publications], ["degraded", "qualified_scan"])
        self.assertFalse(any(publication.topic.endswith("/projection_quality") for publication in publications))
        self.assertFalse(any(publication.topic.endswith("/local_scan") for publication in publications))
        qualified = [publication for publication in publications if publication.kind == "qualified_scan"][0]
        payload = json.loads(qualified.payload)
        self.assertEqual(qualified.msg_type, FLEETRMW_QUALIFIED_LASER_SCAN_MSG_TYPE)
        self.assertEqual(qualified.topic, "/fleetrmw/robot_0000/qualified_scan")
        self.assertEqual(payload["sample"]["scan"]["ranges"], [1.0, 1.1, 1.2])
        self.assertEqual(payload["quality"]["projection_kind"], "typed_scan")
        self.assertEqual(payload["quality"]["fidelity_class"], "downsampled_projection")

    def test_can_route_both_sideband_and_qualified_state_for_debug(self) -> None:
        router = SidecarEgressRouter(
            enable_typed_reconstruction=True,
            include_projection_payload=False,
            projection_quality_msg_type=FLEETRMW_PROJECTION_QUALITY_MSG_TYPE,
            projection_quality_delivery="both",
        )
        event = _event(action="send", wire_mode="native")
        event["topic"] = "/robot_0000/odom"
        event["semantic_payload"] = _odom_payload()

        publications = router.route(event)

        self.assertEqual([publication.kind for publication in publications], ["native", "typed_odom", "typed_projection_quality", "qualified_odom"])
        self.assertTrue(any(publication.topic.endswith("/local_odom") for publication in publications))
        self.assertTrue(any(publication.topic.endswith("/projection_quality") for publication in publications))
        self.assertTrue(any(publication.topic.endswith("/qualified_odom") for publication in publications))

    def test_routes_degraded_packet_to_degraded_topic(self) -> None:
        router = SidecarEgressRouter()
        event = _event(action="send_degraded", wire_mode="degraded")

        publications = router.route(event)

        self.assertEqual(publications[0].topic, "/fleetrmw/robot_0000/degraded")
        self.assertEqual(publications[0].kind, "degraded")

    def test_routes_semantic_delta_to_delta_topic(self) -> None:
        self.assertEqual(publication_kind_and_suffix(action="send_compacted", wire_mode="semantic_delta"), ("semantic_delta", "semantic_delta"))

    def test_invalid_packet_returns_none(self) -> None:
        self.assertIsNone(decode_sidecar_packet(b"not-json"))

    def test_ros_topic_token_sanitizes_robot_ids(self) -> None:
        self.assertEqual(ros_topic_token("tb4-01.local"), "tb4_01_local")
        self.assertEqual(ros_topic_token("42"), "r_42")

    def test_sanitize_twist_payload_defaults_missing_fields(self) -> None:
        twist = sanitize_twist_payload({"linear": {"x": "0.5"}, "angular": {"z": None}})

        self.assertEqual(twist["linear"]["x"], 0.5)
        self.assertEqual(twist["linear"]["y"], 0.0)
        self.assertEqual(twist["angular"]["z"], 0.0)

    def test_robot_feedback_record_tracks_control_deadline(self) -> None:
        event = _event(action="send_intent", wire_mode="control_intent")
        event["send_monotonic_ns"] = 1_000_000_000

        on_time = robot_feedback_record_from_event(
            event,
            recv_monotonic_ns=1_020_000_000,
        )
        late = robot_feedback_record_from_event(
            event,
            recv_monotonic_ns=1_080_000_000,
        )

        self.assertIsNotNone(on_time)
        self.assertIsNotNone(late)
        assert on_time is not None
        assert late is not None
        self.assertEqual(on_time["source"], "egress")
        self.assertEqual(on_time["action"], "send_intent")
        self.assertEqual(on_time["wire_mode"], "control_intent")
        self.assertTrue(on_time["control_delivered"])
        self.assertTrue(on_time["deadline_met"])
        self.assertEqual(on_time["deadline_risk"], 0.0)
        self.assertEqual(on_time["latency_ms"], 20.0)
        self.assertFalse(late["deadline_met"])
        self.assertEqual(late["deadline_risk"], 1.0)
        self.assertEqual(late["latency_ms"], 80.0)

    def test_feedback_window_aggregates_per_robot_ratios(self) -> None:
        windows = {}

        update_feedback_window(
            windows,
            {
                "robot_id": "robot_0000",
                "flow_class": "control",
                "wire_mode": "control_intent",
                "control_delivered": True,
                "deadline_met": True,
                "latency_ms": 20.0,
                "deadline_ms": 45.0,
            },
        )
        update_feedback_window(
            windows,
            {
                "robot_id": "robot_0000",
                "flow_class": "control",
                "wire_mode": "control_intent",
                "control_delivered": True,
                "deadline_met": False,
                "latency_ms": 50.0,
                "deadline_ms": 45.0,
            },
        )
        update_feedback_window(
            windows,
            {
                "robot_id": "robot_0000",
                "flow_class": "state",
                "wire_mode": "native",
                "deadline_met": False,
                "latency_ms": 120.0,
                "deadline_ms": 90.0,
            },
        )

        self.assertEqual(windows["robot_0000"]["control_total"], 2.0)
        self.assertEqual(windows["robot_0000"]["control_delivered"], 2.0)
        self.assertEqual(windows["robot_0000"]["deadline_total"], 1.0)
        self.assertEqual(windows["robot_0000"]["deadline_miss"], 1.0)
        self.assertEqual(windows["robot_0000"]["latency_count"], 3.0)
        self.assertEqual(windows["robot_0000"]["latency_tail_ms"], 120.0)
        by_transform = windows["robot_0000"]["deadline_by_transform"]
        self.assertNotIn("control:control_intent", by_transform)
        self.assertEqual(by_transform["state:native"]["deadline_total"], 1.0)
        self.assertEqual(by_transform["state:native"]["deadline_miss"], 1.0)

    def test_control_lease_feedback_keeps_delivery_without_egress_deadline_debt(self) -> None:
        windows = {}
        record = {
            "robot_id": "robot_0000",
            "event_id": 8,
            "flow_class": "control",
            "action": "send_intent",
            "wire_mode": "control_intent",
            "control_delivered": True,
            "deadline_met": False,
            "latency_ms": 80.0,
            "deadline_ms": 45.0,
        }

        update_feedback_window(windows, record)

        self.assertTrue(is_control_lease_feedback(record))
        self.assertEqual(windows["robot_0000"]["control_total"], 1.0)
        self.assertEqual(windows["robot_0000"]["control_delivered"], 1.0)
        self.assertEqual(windows["robot_0000"]["deadline_total"], 0.0)
        self.assertEqual(windows["robot_0000"]["deadline_miss"], 0.0)
        self.assertEqual(windows["robot_0000"]["latency_count"], 1.0)
        self.assertEqual(windows["robot_0000"]["latency_tail_ms"], 80.0)
        self.assertEqual(windows["robot_0000"]["deadline_by_transform"], {})

    def test_control_lease_feedback_deduplicates_redundant_event_ids(self) -> None:
        windows = {}
        record = {
            "robot_id": "robot_0000",
            "event_id": 8,
            "flow_class": "control",
            "action": "send_intent",
            "wire_mode": "control_intent",
            "control_delivered": True,
            "deadline_met": True,
            "latency_ms": 20.0,
            "deadline_ms": 45.0,
        }

        update_feedback_window(windows, record)
        update_feedback_window(windows, record | {"latency_ms": 25.0})

        self.assertEqual(windows["robot_0000"]["control_total"], 1.0)
        self.assertEqual(windows["robot_0000"]["control_delivered"], 1.0)
        self.assertEqual(windows["robot_0000"]["latency_count"], 1.0)
        self.assertEqual(windows["robot_0000"]["latency_tail_ms"], 20.0)

    def test_flush_feedback_window_includes_sample_counts(self) -> None:
        class Args:
            feedback_sidecar_host = "127.0.0.1"
            feedback_sidecar_port = 1
            feedback_timeout_s = 0.01

        windows = {
            "robot_0000": {
                "control_total": 2.0,
                "control_delivered": 1.0,
                "deadline_total": 4.0,
                "deadline_miss": 1.0,
                "latency_total_ms": 90.0,
                "latency_tail_ms": 40.0,
                "latency_count": 3.0,
                "latency_deadline_total_ms": 120.0,
                "latency_deadline_count": 3.0,
                "_seen_control_lease_event_ids": {8, 9},
                "deadline_by_transform": {
                    "control:control_intent": {
                        "deadline_total": 2.0,
                        "deadline_miss": 1.0,
                    },
                    "state:native": {
                        "deadline_total": 2.0,
                        "deadline_miss": 0.0,
                    },
                },
            }
        }

        captured = {}

        def fake_send_robot_feedback(**kwargs):
            captured.update(kwargs)
            return {"applied": len(kwargs["records"])}

        with patch(
            "scripts.run_ros2_egress_bridge.send_robot_feedback",
            side_effect=fake_send_robot_feedback,
        ):
            sent, failed = flush_feedback_windows(Args(), windows)

        self.assertEqual(sent, 1)
        self.assertEqual(failed, 0)
        self.assertEqual(windows, {})
        record = captured["records"][0]
        self.assertEqual(record["control_sample_count"], 2)
        self.assertEqual(record["control_lease_event_ids"], [8, 9])
        self.assertEqual(record["source"], "egress")
        self.assertEqual(record["deadline_sample_count"], 4)
        self.assertEqual(
            record["deadline_miss_by_transform"],
            {"control:control_intent": 0.5, "state:native": 0.0},
        )
        self.assertEqual(
            record["deadline_sample_count_by_transform"],
            {"control:control_intent": 2, "state:native": 2},
        )
        self.assertEqual(record["latency_sample_count"], 3)
        self.assertEqual(record["feedback_sample_count"], 4)
        self.assertEqual(record["mean_latency_ms"], 30.0)
        self.assertEqual(record["tail_latency_ms"], 40.0)
        self.assertEqual(record["mean_deadline_ms"], 40.0)
        self.assertEqual(record["latency_deadline_ratio"], 1.0)

    def test_feedback_window_piggybacks_ack_nack_gap_records(self) -> None:
        class Args:
            feedback_sidecar_host = "127.0.0.1"
            feedback_sidecar_port = 1
            feedback_timeout_s = 0.01

        class Client:
            def __init__(self) -> None:
                self.calls = []

            def send_feedback(self, records):
                self.calls.append(list(records))
                return {
                    "status": "ok",
                    "applied": 1,
                    "control_lease_ack": {"ack_feedback_records": len(records)},
                }

        tracker = RmwAckNackTracker()
        windows: dict[str, dict[str, float]] = {}
        first = robot_feedback_record_from_event(
            _event_with_source_sequence(event_id=7, sequence=1),
            recv_monotonic_ns=1_000_000,
        )
        third = robot_feedback_record_from_event(
            _event_with_source_sequence(event_id=9, sequence=3),
            recv_monotonic_ns=3_000_000,
        )
        assert first is not None
        assert third is not None
        update_feedback_window(
            windows,
            first,
            ack_nack_record=tracker.observe(first),
        )
        update_feedback_window(
            windows,
            third,
            ack_nack_record=tracker.observe(third),
        )
        client = Client()

        sent, failed = flush_feedback_windows(
            Args(),
            windows,
            feedback_client=client,  # type: ignore[arg-type]
        )

        self.assertEqual((sent, failed), (1, 0))
        self.assertEqual(len(client.calls), 1)
        ack_nacks = [
            record
            for record in client.calls[0]
            if record.get("schema_version") == ACK_NACK_SCHEMA_VERSION
        ]
        self.assertEqual(len(ack_nacks), 2)
        self.assertEqual(ack_nacks[-1]["ack"]["source_sequence_number"], 3)
        self.assertEqual(ack_nacks[-1]["nack"]["missing_sequence_ranges"], [[2, 2]])

    def test_flush_feedback_window_can_use_persistent_client(self) -> None:
        class Args:
            feedback_sidecar_host = "127.0.0.1"
            feedback_sidecar_port = 1
            feedback_timeout_s = 0.01

        class Client:
            def __init__(self) -> None:
                self.calls = []

            def send_feedback(self, records):
                self.calls.append(list(records))
                return {"applied": len(records)}

        windows = {
            "robot_0000": {
                "control_total": 1.0,
                "control_delivered": 1.0,
                "deadline_total": 0.0,
                "deadline_miss": 0.0,
                "latency_total_ms": 0.0,
                "latency_tail_ms": 0.0,
                "latency_count": 0.0,
                "latency_deadline_total_ms": 0.0,
                "latency_deadline_count": 0.0,
                "_seen_control_lease_event_ids": {7},
                "deadline_by_transform": {},
            }
        }
        client = Client()

        with patch("scripts.run_ros2_egress_bridge.send_robot_feedback") as send:
            sent, failed = flush_feedback_windows(
                Args(),
                windows,
                feedback_client=client,  # type: ignore[arg-type]
            )

        self.assertEqual(sent, 1)
        self.assertEqual(failed, 0)
        self.assertEqual(windows, {})
        self.assertEqual(len(client.calls), 1)
        self.assertEqual(client.calls[0][0]["control_lease_event_ids"], [7])
        send.assert_not_called()

    def test_immediate_control_lease_ack_is_ack_only_and_deduped(self) -> None:
        class Args:
            feedback_sidecar_host = "127.0.0.1"
            feedback_sidecar_port = 1
            feedback_timeout_s = 0.01

        class Client:
            def __init__(self) -> None:
                self.calls = []

            def send_feedback(self, records):
                self.calls.append(list(records))
                return {
                    "status": "ok",
                    "control_lease_ack": {"ack_feedback_records": len(records)},
                }

        record = robot_feedback_record_from_event(
            _event(action="send_intent", wire_mode="control_intent"),
            recv_monotonic_ns=1_000_000,
        )
        assert record is not None
        ack = immediate_control_lease_ack_record(record)

        self.assertIsNotNone(ack)
        assert ack is not None
        self.assertEqual(ack["source"], "egress_ack")
        self.assertEqual(ack["robot_id"], "robot_0000")
        self.assertEqual(ack["control_lease_event_ids"], [7])
        self.assertNotIn("control_delivery_ratio", ack)

        seen = set()
        client = Client()
        first = maybe_send_immediate_control_lease_ack(
            Args(),
            record,
            seen=seen,
            feedback_client=client,  # type: ignore[arg-type]
        )
        duplicate = maybe_send_immediate_control_lease_ack(
            Args(),
            record,
            seen=seen,
            feedback_client=client,  # type: ignore[arg-type]
        )

        self.assertEqual(first, (1, 0))
        self.assertEqual(duplicate, (0, 0))
        self.assertEqual(len(client.calls), 1)

    def test_control_lease_feedback_and_ack_carry_source_identity(self) -> None:
        event = _event(action="send_intent", wire_mode="control_intent")
        event["source_sample_id"] = "fsid1-control"
        event["semantic_payload"] = {
            "schema_version": "fleetrmw.semantic_payload.v1",
            "msg_type": "geometry_msgs/msg/Twist",
            "source_topic": "/robot_0000/cmd_vel",
            "source_metadata": {
                "sequence_number": 42,
                "source_timestamp_ns": 123_000,
                "received_timestamp_ns": 456_000,
            },
        }

        record = robot_feedback_record_from_event(event, recv_monotonic_ns=1_000_000)
        assert record is not None
        ack = immediate_control_lease_ack_record(record)

        self.assertEqual(record["source_topic"], "/robot_0000/cmd_vel")
        self.assertEqual(record["source_sample_id"], "fsid1-control")
        self.assertEqual(record["source_sequence_number"], 42)
        self.assertEqual(record["source_timestamp_ns"], 123_000)
        self.assertEqual(record["source_received_timestamp_ns"], 456_000)
        self.assertIsNotNone(ack)
        assert ack is not None
        self.assertEqual(ack["source_sample_id"], "fsid1-control")
        self.assertEqual(ack["source_sequence_number"], 42)
        self.assertEqual(ack["source_timestamp_ns"], 123_000)
        self.assertEqual(ack["source_received_timestamp_ns"], 456_000)

    def test_control_lease_ack_window_coalesces_before_send(self) -> None:
        class Args:
            feedback_sidecar_host = "127.0.0.1"
            feedback_sidecar_port = 1
            feedback_timeout_s = 0.01
            feedback_control_lease_ack_window_events = 2

        class Client:
            def __init__(self) -> None:
                self.calls = []

            def send_feedback(self, records):
                self.calls.append(list(records))
                return {
                    "status": "ok",
                    "control_lease_ack": {"ack_feedback_records": len(records)},
                }

        first = robot_feedback_record_from_event(
            _event(action="send_intent", wire_mode="control_intent"),
            recv_monotonic_ns=1_000_000,
        )
        second_event = _event(action="send_intent", wire_mode="control_intent")
        second_event["event_id"] = 8
        second = robot_feedback_record_from_event(
            second_event,
            recv_monotonic_ns=2_000_000,
        )
        assert first is not None
        assert second is not None
        seen = set()
        pending: list[dict[str, object]] = []
        client = Client()

        held = maybe_queue_control_lease_ack(
            Args(),
            first,
            pending=pending,
            seen=seen,
            feedback_client=client,  # type: ignore[arg-type]
        )
        flushed = maybe_queue_control_lease_ack(
            Args(),
            second,
            pending=pending,
            seen=seen,
            feedback_client=client,  # type: ignore[arg-type]
        )

        self.assertEqual(held, (0, 0))
        self.assertEqual(flushed, (2, 0))
        self.assertEqual(pending, [])
        self.assertEqual(len(client.calls), 1)
        self.assertEqual(
            [item["control_lease_event_ids"][0] for item in client.calls[0]],  # type: ignore[index]
            [7, 8],
        )

    def test_adaptive_control_lease_ack_pacer_backpressures_after_failure(self) -> None:
        class Args:
            feedback_sidecar_host = "127.0.0.1"
            feedback_sidecar_port = 1
            feedback_timeout_s = 0.01

        class Client:
            def __init__(self) -> None:
                self.calls = []

            def send_feedback(self, records):
                self.calls.append(list(records))
                if len(self.calls) == 1:
                    raise OSError("sidecar feedback unavailable")
                return {
                    "status": "ok",
                    "control_lease_ack": {"ack_feedback_records": len(records)},
                }

        pacer = ControlLeaseAckPacer(
            min_window_events=2,
            max_window_events=8,
            success_step=1,
            failure_multiplier=2.0,
            piggyback_first=False,
        )
        client = Client()

        first = pacer.maybe_ack(
            Args(),
            _feedback_for_event_id(7),
            feedback_client=client,  # type: ignore[arg-type]
        )
        failed = pacer.maybe_ack(
            Args(),
            _feedback_for_event_id(8),
            feedback_client=client,  # type: ignore[arg-type]
        )
        held_after_failure = pacer.maybe_ack(
            Args(),
            _feedback_for_event_id(9),
            feedback_client=client,  # type: ignore[arg-type]
        )
        recovered = pacer.maybe_ack(
            Args(),
            _feedback_for_event_id(10),
            feedback_client=client,  # type: ignore[arg-type]
        )

        self.assertEqual(first, (0, 0))
        self.assertEqual(failed, (0, 1))
        self.assertEqual(held_after_failure, (0, 0))
        self.assertEqual(recovered, (4, 0))
        self.assertEqual(pacer.current_window_events, 3)
        self.assertEqual(len(client.calls), 2)
        self.assertEqual(
            [item["control_lease_event_ids"][0] for item in client.calls[0]],  # type: ignore[index]
            [7, 8],
        )
        self.assertEqual(
            [item["control_lease_event_ids"][0] for item in client.calls[1]],  # type: ignore[index]
            [7, 8, 9, 10],
        )
        self.assertEqual(client.calls[1][0]["ack_pacing_mode"], "adaptive_window")
        self.assertEqual(client.calls[1][0]["ack_batch_size"], 4)
        self.assertEqual(client.calls[1][0]["ack_window_events"], 4)

    def test_adaptive_control_lease_ack_pacer_dedupes_pending_and_delivered(self) -> None:
        class Args:
            feedback_sidecar_host = "127.0.0.1"
            feedback_sidecar_port = 1
            feedback_timeout_s = 0.01

        class Client:
            def __init__(self) -> None:
                self.calls = []

            def send_feedback(self, records):
                self.calls.append(list(records))
                return {
                    "status": "ok",
                    "control_lease_ack": {"ack_feedback_records": len(records)},
                }

        pacer = ControlLeaseAckPacer(
            min_window_events=2,
            max_window_events=4,
            piggyback_first=False,
        )
        client = Client()

        held = pacer.maybe_ack(
            Args(),
            _feedback_for_event_id(7),
            feedback_client=client,  # type: ignore[arg-type]
        )
        duplicate_pending = pacer.maybe_ack(
            Args(),
            _feedback_for_event_id(7),
            feedback_client=client,  # type: ignore[arg-type]
        )
        flushed = pacer.maybe_ack(
            Args(),
            _feedback_for_event_id(8),
            feedback_client=client,  # type: ignore[arg-type]
        )
        duplicate_delivered = pacer.maybe_ack(
            Args(),
            _feedback_for_event_id(7),
            feedback_client=client,  # type: ignore[arg-type]
        )

        self.assertEqual(held, (0, 0))
        self.assertEqual(duplicate_pending, (0, 0))
        self.assertEqual(flushed, (2, 0))
        self.assertEqual(duplicate_delivered, (0, 0))
        self.assertEqual(len(client.calls), 1)

    def test_adaptive_control_lease_ack_pacer_flushes_pending_age(self) -> None:
        class Args:
            feedback_sidecar_host = "127.0.0.1"
            feedback_sidecar_port = 1
            feedback_timeout_s = 0.01

        class Client:
            def __init__(self) -> None:
                self.calls = []

            def send_feedback(self, records):
                self.calls.append(list(records))
                return {
                    "status": "ok",
                    "control_lease_ack": {"ack_feedback_records": len(records)},
                }

        pacer = ControlLeaseAckPacer(
            min_window_events=8,
            max_window_events=16,
            max_age_ms=50.0,
        )
        client = Client()

        held = pacer.maybe_ack(
            Args(),
            _feedback_for_event_id(7),
            feedback_client=client,  # type: ignore[arg-type]
            now_monotonic_ns=1_000_000_000,
        )
        not_due = pacer.flush_if_due(
            Args(),
            feedback_client=client,  # type: ignore[arg-type]
            now_monotonic_ns=1_040_000_000,
        )
        due = pacer.flush_if_due(
            Args(),
            feedback_client=client,  # type: ignore[arg-type]
            now_monotonic_ns=1_051_000_000,
        )

        self.assertEqual(held, (0, 0))
        self.assertEqual(not_due, (0, 0))
        self.assertEqual(due, (1, 0))
        self.assertEqual(len(client.calls), 1)
        self.assertEqual(client.calls[0][0]["ack_batch_size"], 1)
        self.assertEqual(client.calls[0][0]["ack_window_events"], 8)

    def test_adaptive_control_lease_ack_pacer_prefers_regular_feedback_piggyback(self) -> None:
        class Args:
            feedback_sidecar_host = "127.0.0.1"
            feedback_sidecar_port = 1
            feedback_timeout_s = 0.01

        class Client:
            def __init__(self) -> None:
                self.calls = []

            def send_feedback(self, records):
                self.calls.append(list(records))
                return {
                    "status": "ok",
                    "control_lease_ack": {"ack_feedback_records": len(records)},
                }

        pacer = ControlLeaseAckPacer(
            min_window_events=2,
            max_window_events=4,
            max_age_ms=500.0,
            piggyback_first=True,
        )
        client = Client()
        windows = {
            "robot_0000": {
                "_seen_control_lease_event_ids": {7, 8},
            }
        }

        first = pacer.maybe_ack(
            Args(),
            _feedback_for_event_id(7),
            feedback_client=client,  # type: ignore[arg-type]
            now_monotonic_ns=1_000_000_000,
        )
        second = pacer.maybe_ack(
            Args(),
            _feedback_for_event_id(8),
            feedback_client=client,  # type: ignore[arg-type]
            now_monotonic_ns=1_010_000_000,
        )
        pacer.mark_delivered(control_lease_ack_keys_from_feedback_windows(windows))  # type: ignore[arg-type]
        late = pacer.flush_if_due(
            Args(),
            feedback_client=client,  # type: ignore[arg-type]
            now_monotonic_ns=2_000_000_000,
        )

        self.assertEqual(first, (0, 0))
        self.assertEqual(second, (0, 0))
        self.assertEqual(late, (0, 0))
        self.assertEqual(pacer.pending, [])
        self.assertEqual(len(client.calls), 0)


def _event(*, action: str, wire_mode: str) -> dict[str, object]:
    return {
        "schema_version": SIDECAR_TRACE_SCHEMA_VERSION,
        "event_type": "packet",
        "scenario": "test",
        "policy": "fleetqox_semantic_contract_adaptive",
        "event_id": 7,
        "timestamp_ms": 0.0,
        "tick": 1,
        "flow_id": "robot_0000:/robot_0000/cmd_vel",
        "flow_class": "control",
        "topic": "/robot_0000/cmd_vel",
        "robot_id": "robot_0000",
        "src": "fleet_controller",
        "dst": "robot_0000",
        "action": action,
        "bytes": 128,
        "original_bytes": 96,
        "degraded": wire_mode != "native",
        "deadline_ms": 45,
        "source_deadline_ms": 45,
        "lifespan_ms": 90,
        "qos_reliability": "reliable",
        "reliability": "best_effort_fresh",
        "wire_mode": wire_mode,
        "predicted_slack_ms": 12.0,
        "reason": "unit test",
        "priority": 0.9,
        "semantic_utility": 5.0,
        "age_ms": 5.0,
        "queue_depth": 1,
        "task_criticality": 1.0,
        "collision_risk": 0.2,
        "operator_attention": 0.1,
        "coordination_pressure": 0.3,
        "link_capacity_bytes_per_tick": 588,
        "link_loss": 0.03,
        "link_jitter_ms": 25.0,
        "link_rtt_ms": 160.0,
    }


def _feedback_for_event_id(event_id: int) -> dict[str, object]:
    event = _event(action="send_intent", wire_mode="control_intent")
    event["event_id"] = event_id
    record = robot_feedback_record_from_event(event, recv_monotonic_ns=event_id * 1_000_000)
    assert record is not None
    return record


def _event_with_source_sequence(*, event_id: int, sequence: int) -> dict[str, object]:
    event = _event(action="send_intent", wire_mode="control_intent")
    event["event_id"] = event_id
    event["source_sample_id"] = f"fsid1-control-{sequence}"
    event["source_metadata"] = {
        "sequence_number": sequence,
        "source_timestamp_ns": sequence * 1_000_000,
        "received_timestamp_ns": sequence * 1_000_000 + 10,
    }
    return event


def _twist_payload() -> dict[str, object]:
    return {
        "schema_version": "fleetrmw.semantic_payload.v1",
        "msg_type": "geometry_msgs/msg/Twist",
        "source_topic": "/robot_0000/cmd_vel",
        "twist": {
            "linear": {"x": 0.4, "y": 0.0, "z": 0.0},
            "angular": {"x": 0.0, "y": 0.0, "z": 0.15},
        },
    }


def _odom_payload() -> dict[str, object]:
    return {
        "schema_version": "fleetrmw.semantic_payload.v1",
        "msg_type": "nav_msgs/msg/Odometry",
        "source_topic": "/robot_0000/odom",
        "header": {"frame_id": "odom", "stamp": {"sec": 1, "nanosec": 2}},
        "odometry": {
            "child_frame_id": "robot_0000",
            "pose": {
                "position": {"x": 1.2, "y": 0.3, "z": 0.0},
                "orientation": {"x": 0.0, "y": 0.0, "z": 0.1, "w": 0.99},
                "covariance": [0.0] * 36,
            },
            "twist": {
                "linear": {"x": 0.2, "y": 0.0, "z": 0.0},
                "angular": {"x": 0.0, "y": 0.0, "z": 0.1},
                "covariance": [0.0] * 36,
            },
        },
    }


def _scan_payload() -> dict[str, object]:
    return {
        "schema_version": "fleetrmw.semantic_payload.v1",
        "msg_type": "sensor_msgs/msg/LaserScan",
        "source_topic": "/robot_0000/scan",
        "header": {"frame_id": "robot_0000/base_scan", "stamp": {"sec": 1, "nanosec": 2}},
        "scan": {
            "angle_min": -1.0,
            "angle_max": 1.0,
            "angle_increment": 0.1,
            "range_min": 0.12,
            "range_max": 8.0,
            "ranges": [1.0, 1.1, 1.2],
            "intensities": [],
            "source_sample_count": 6,
            "downsample_stride": 2,
        },
    }


if __name__ == "__main__":
    unittest.main()

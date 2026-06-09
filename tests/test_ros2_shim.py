import json
import socket
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from fleetqox.model import FlowClass, NetworkLink
from fleetqox.ros2_shim import (
    Ros2QoS,
    Ros2Sample,
    Ros2SidecarAdapter,
    Ros2TopicRule,
    defaults_for_topic,
    infer_robot_id,
)
from fleetqox.rmw_contract import sample_envelope_for_fields
from fleetqox.sidecar_runtime import RuntimeConfig, SidecarRuntime
from fleetqox.transport_selector import TransportBinding
from scripts.run_ros2_sidecar_adapter import _read_transport_binding


class Ros2ShimTest(unittest.TestCase):
    def test_cmd_vel_maps_to_control_contract_defaults(self) -> None:
        adapter = Ros2SidecarAdapter()
        sample = Ros2Sample(
            topic="/robot_0007/cmd_vel",
            msg_type="geometry_msgs/msg/Twist",
            qos=Ros2QoS(reliability="SYSTEM_DEFAULT"),
        )

        flow = adapter.flow_spec_for_sample(sample)

        self.assertEqual(flow.robot_id, "robot_0007")
        self.assertEqual(flow.flow_id, "robot_0007:cmd")
        self.assertEqual(flow.flow_class, FlowClass.CONTROL)
        self.assertEqual(flow.qos.reliability, "reliable")
        self.assertEqual(flow.qos.deadline_ms, 45.0)
        self.assertEqual(flow.qos.lifespan_ms, 90.0)
        self.assertEqual(flow.nominal_size_bytes, 96)

    def test_camera_qoe_maps_to_operator_visible_human_qoe(self) -> None:
        adapter = Ros2SidecarAdapter()
        sample = Ros2Sample(
            topic="/tb4_01/front_camera/qoe",
            msg_type="sensor_msgs/msg/CompressedImage",
            operator_visible=True,
            payload_size_bytes=12_000,
        )

        flow = adapter.flow_spec_for_sample(sample)

        self.assertEqual(flow.robot_id, "tb4_01")
        self.assertEqual(flow.flow_class, FlowClass.HUMAN_QOE)
        self.assertTrue(flow.qoe.operator_visible)
        self.assertEqual(flow.nominal_size_bytes, 12_000)
        self.assertEqual(flow.qos.reliability, "best_effort")

    def test_missing_qos_depth_uses_semantic_default(self) -> None:
        adapter = Ros2SidecarAdapter()

        flow = adapter.flow_spec_for_sample(Ros2Sample(topic="/robot_0001/fleet_state"))

        self.assertEqual(flow.flow_class, FlowClass.STATE)
        self.assertEqual(flow.qos.depth, 3)

    def test_topic_rule_can_override_semantic_class_and_logical_name(self) -> None:
        adapter = Ros2SidecarAdapter(
            [
                Ros2TopicRule(
                    pattern="/fleet/*/lease",
                    flow_class=FlowClass.COORDINATION,
                    logical_name="lease",
                    nominal_size_bytes=144,
                )
            ]
        )

        flow = adapter.flow_spec_for_sample(Ros2Sample(topic="/fleet/robot_0002/lease"))

        self.assertEqual(flow.flow_class, FlowClass.COORDINATION)
        self.assertEqual(flow.flow_id, "robot_0002:lease")
        self.assertEqual(flow.nominal_size_bytes, 144)

    def test_build_batch_from_ros2_samples_can_feed_sidecar_runtime(self) -> None:
        udp_port = _free_udp_port()
        adapter = Ros2SidecarAdapter()
        link = NetworkLink(
            capacity_bytes_per_tick=588,
            rtt_ms=160.0,
            jitter_ms=25.0,
            loss=0.03,
        )
        samples = [
            Ros2Sample(
                topic="/robot_0000/cmd_vel",
                msg_type="geometry_msgs/msg/Twist",
                robot_id="robot_0000",
                age_ms=20.0,
                collision_risk=0.9,
            ),
            Ros2Sample(
                topic="/robot_0000/fleet_state",
                msg_type="nav_msgs/msg/Odometry",
                robot_id="robot_0000",
                age_ms=40.0,
            ),
        ]
        batch = adapter.build_batch(
            samples,
            scenario="ros2_shim_runtime_test",
            link=link,
            timestamp_ms=0.0,
            tick=0,
        )

        with TemporaryDirectory() as tmpdir:
            log_path = Path(tmpdir) / "decisions.jsonl"
            runtime = SidecarRuntime(
                RuntimeConfig(
                    udp_host="127.0.0.1",
                    udp_port=udp_port,
                    policy="fleetqox_semantic_contract_adaptive",
                    decision_log=log_path,
                )
            )
            try:
                response = runtime.process_batch(batch)
            finally:
                runtime.close()

            events = [json.loads(line) for line in log_path.read_text(encoding="utf-8").splitlines()]

        self.assertEqual(response["status"], "ok")
        self.assertTrue(any(event["wire_mode"] == "supervisory_intent" for event in events))

    def test_build_batch_preserves_semantic_payload_for_egress(self) -> None:
        adapter = Ros2SidecarAdapter()
        sample = Ros2Sample(
            topic="/robot_0000/cmd_vel",
            msg_type="geometry_msgs/msg/Twist",
            robot_id="robot_0000",
            semantic_payload={
                "schema_version": "fleetrmw.semantic_payload.v1",
                "msg_type": "geometry_msgs/msg/Twist",
                "twist": {
                    "linear": {"x": 0.3, "y": 0.0, "z": 0.0},
                    "angular": {"x": 0.0, "y": 0.0, "z": 0.2},
                },
            },
        )

        batch = adapter.build_batch(
            [sample],
            scenario="semantic_payload_test",
            link=NetworkLink(capacity_bytes_per_tick=588),
            timestamp_ms=0.0,
            tick=0,
        )

        self.assertEqual(batch["flows"][0]["semantic_payload"]["msg_type"], "geometry_msgs/msg/Twist")
        self.assertEqual(batch["flows"][0]["semantic_payload"]["twist"]["linear"]["x"], 0.3)

    def test_build_batch_can_attach_transport_binding(self) -> None:
        adapter = Ros2SidecarAdapter()
        binding = TransportBinding(
            profile="wifi",
            objective="balanced_safety_utility",
            policy="data_frame/rmw_zenoh_cpp",
            packet_format="data_frame",
            rmw="rmw_zenoh_cpp",
            score=1.0,
        )

        batch = adapter.build_batch(
            [Ros2Sample(topic="/robot_0000/odom", robot_id="robot_0000")],
            scenario="transport_binding_batch_test",
            link=NetworkLink(capacity_bytes_per_tick=588),
            timestamp_ms=0.0,
            tick=0,
            transport_binding=binding,
        )

        self.assertEqual(batch["transport_binding"]["profile"], "wifi")
        self.assertEqual(batch["transport_binding"]["packet_format"], "data_frame")
        self.assertEqual(batch["transport_binding"]["rmw"], "rmw_zenoh_cpp")

    def test_adapter_cli_can_read_transport_binding_summary(self) -> None:
        with TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "selector_summary.json"
            path.write_text(
                json.dumps(
                    {
                        "bindings": [
                            {
                                "profile": "wifi",
                                "objective": "balanced_safety_utility",
                                "policy": "data_frame/rmw_zenoh_cpp",
                                "packet_format": "data_frame",
                                "rmw": "rmw_zenoh_cpp",
                                "score": 1.0,
                            },
                            {
                                "profile": "wan",
                                "objective": "balanced_safety_utility",
                                "policy": "event_json/rmw_zenoh_cpp",
                                "packet_format": "event_json",
                                "rmw": "rmw_zenoh_cpp",
                                "score": 0.8,
                            },
                        ]
                    }
                ),
                encoding="utf-8",
            )

            binding = _read_transport_binding(path, profile="wan")

        self.assertIsNotNone(binding)
        assert binding is not None
        self.assertEqual(binding.profile, "wan")
        self.assertEqual(binding.packet_format, "event_json")

    def test_adapter_cli_can_auto_select_transport_profile(self) -> None:
        with TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "selector_summary.json"
            path.write_text(
                json.dumps(
                    {
                        "bindings": [
                            {
                                "profile": "wifi",
                                "objective": "balanced_safety_utility",
                                "policy": "data_frame/rmw_zenoh_cpp",
                                "packet_format": "data_frame",
                                "rmw": "rmw_zenoh_cpp",
                                "score": 1.0,
                            },
                            {
                                "profile": "roaming",
                                "objective": "balanced_safety_utility",
                                "policy": "event_json/rmw_zenoh_cpp",
                                "packet_format": "event_json",
                                "rmw": "rmw_zenoh_cpp",
                                "score": 0.8,
                            },
                        ]
                    }
                ),
                encoding="utf-8",
            )

            binding = _read_transport_binding(
                path,
                profile=None,
                link_payload={
                    "capacity_bytes_per_tick": 1000,
                    "rtt_ms": 160,
                    "jitter_ms": 25,
                    "loss": 0.03,
                },
                auto_profile=True,
            )

        self.assertIsNotNone(binding)
        assert binding is not None
        self.assertEqual(binding.profile, "roaming")
        self.assertEqual(binding.packet_format, "event_json")

    def test_adapter_cli_can_adaptively_select_transport_profile(self) -> None:
        with TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "selector_summary.json"
            path.write_text(
                json.dumps(
                    {
                        "bindings": [
                            {
                                "profile": "wifi",
                                "objective": "balanced_safety_utility",
                                "policy": "data_frame/rmw_zenoh_cpp",
                                "packet_format": "data_frame",
                                "rmw": "rmw_zenoh_cpp",
                                "score": 1.0,
                            },
                            {
                                "profile": "wan",
                                "objective": "balanced_safety_utility",
                                "policy": "event_json/rmw_zenoh_cpp",
                                "packet_format": "event_json",
                                "rmw": "rmw_zenoh_cpp",
                                "score": 0.8,
                            },
                        ]
                    }
                ),
                encoding="utf-8",
            )

            binding = _read_transport_binding(
                path,
                profile=None,
                link_payload={
                    "capacity_bytes_per_tick": 1800,
                    "rtt_ms": 90,
                    "jitter_ms": 15,
                    "loss": 0.015,
                },
                adaptive_profile=True,
                smoothing_alpha=1.0,
            )

        self.assertIsNotNone(binding)
        assert binding is not None
        self.assertEqual(binding.profile, "wan")
        self.assertEqual(binding.packet_format, "event_json")

    def test_build_batch_generates_stable_contract_id_for_each_sample(self) -> None:
        adapter = Ros2SidecarAdapter()
        sample = Ros2Sample(topic="/robot_0000/odom", msg_type="nav_msgs/msg/Odometry", robot_id="robot_0000")

        first = adapter.build_batch(
            [sample],
            scenario="contract_id_test",
            link=NetworkLink(capacity_bytes_per_tick=588),
            timestamp_ms=100.0,
            tick=3,
        )
        second = adapter.build_batch(
            [sample],
            scenario="contract_id_test",
            link=NetworkLink(capacity_bytes_per_tick=588),
            timestamp_ms=120.0,
            tick=3,
        )

        self.assertRegex(first["flows"][0]["contract_id"], r"^fcid1-[0-9a-f]{32}$")
        self.assertEqual(first["flows"][0]["contract_id"], second["flows"][0]["contract_id"])
        self.assertEqual(first["flows"][0]["source_sample_id"], first["flows"][0]["contract_id"])

    def test_source_sample_id_stays_stable_when_contract_context_changes(self) -> None:
        adapter = Ros2SidecarAdapter()
        sample = Ros2Sample(
            topic="/robot_0000/odom",
            msg_type="nav_msgs/msg/Odometry",
            robot_id="robot_0000",
            semantic_payload={
                "schema_version": "fleetrmw.semantic_payload.v1",
                "msg_type": "nav_msgs/msg/Odometry",
                "source_topic": "/robot_0000/odom",
                "header": {"frame_id": "odom", "stamp": {"sec": 10, "nanosec": 20}},
            },
        )

        first = adapter.build_batch(
            [sample],
            scenario="source_sample_id_test",
            link=NetworkLink(capacity_bytes_per_tick=588),
            timestamp_ms=100.0,
            tick=3,
        )
        second = adapter.build_batch(
            [sample],
            scenario="source_sample_id_test",
            link=NetworkLink(capacity_bytes_per_tick=588),
            timestamp_ms=120.0,
            tick=4,
        )

        self.assertRegex(first["flows"][0]["source_sample_id"], r"^fsid1-[0-9a-f]{32}$")
        self.assertEqual(first["flows"][0]["source_sample_id"], second["flows"][0]["source_sample_id"])
        self.assertNotEqual(first["flows"][0]["contract_id"], second["flows"][0]["contract_id"])

    def test_source_sample_id_can_use_rmw_publisher_metadata_without_header(self) -> None:
        adapter = Ros2SidecarAdapter()
        sample = Ros2Sample(
            topic="/robot_0000/cmd_vel",
            msg_type="geometry_msgs/msg/Twist",
            robot_id="robot_0000",
            publisher_gid="01020304",
            sequence_number=77,
            source_timestamp_ns=123_456_789,
        )

        first = adapter.build_batch(
            [sample],
            scenario="source_sample_metadata_test",
            link=NetworkLink(capacity_bytes_per_tick=588),
            timestamp_ms=100.0,
            tick=3,
        )
        second = adapter.build_batch(
            [sample],
            scenario="source_sample_metadata_test",
            link=NetworkLink(capacity_bytes_per_tick=588),
            timestamp_ms=120.0,
            tick=4,
        )

        flow = first["flows"][0]
        self.assertRegex(flow["source_sample_id"], r"^fsid1-[0-9a-f]{32}$")
        self.assertEqual(flow["source_metadata"]["publisher_gid"], "01020304")
        self.assertEqual(flow["source_metadata"]["sequence_number"], 77)
        self.assertEqual(flow["source_metadata"]["source_timestamp_ns"], 123_456_789)
        self.assertEqual(flow["source_sample_id"], second["flows"][0]["source_sample_id"])
        self.assertNotEqual(flow["contract_id"], second["flows"][0]["contract_id"])

    def test_native_sample_envelope_takes_precedence_over_callback_metadata(self) -> None:
        adapter = Ros2SidecarAdapter()
        envelope = sample_envelope_for_fields(
            robot_id="robot_0000",
            topic="/robot_0000/cmd_vel",
            msg_type="geometry_msgs/msg/Twist",
            publisher_id="fpub1-native-controller",
            source_sequence_number=700,
            source_timestamp_ns=555_000,
            received_timestamp_ns=555_100,
        )
        sample = Ros2Sample(
            topic="/robot_0000/cmd_vel",
            msg_type="geometry_msgs/msg/Twist",
            robot_id="robot_0000",
            publisher_gid="dds-gid",
            sequence_number=7,
            source_timestamp_ns=111,
            sample_envelope=envelope,
        )

        batch = adapter.build_batch(
            [sample],
            scenario="native_envelope_test",
            link=NetworkLink(capacity_bytes_per_tick=4096),
            timestamp_ms=0.0,
            tick=0,
        )

        flow = batch["flows"][0]
        self.assertEqual(flow["source_sample_id"], envelope.source_sample_id)
        self.assertEqual(flow["sample_envelope"]["publisher_id"], "fpub1-native-controller")
        self.assertEqual(flow["source_metadata"]["publisher_id"], "fpub1-native-controller")
        self.assertEqual(flow["source_metadata"]["sequence_number"], 700)
        self.assertEqual(flow["source_metadata"]["source_timestamp_ns"], 555_000)
        self.assertNotIn("publisher_gid", flow["source_metadata"])

    def test_native_sample_envelope_reaches_sidecar_event(self) -> None:
        udp_port = _free_udp_port()
        adapter = Ros2SidecarAdapter()
        envelope = sample_envelope_for_fields(
            robot_id="robot_0000",
            topic="/robot_0000/odom",
            msg_type="nav_msgs/msg/Odometry",
            publisher_id="fpub1-state-estimator",
            source_sequence_number=12,
            source_timestamp_ns=999_000,
        )
        batch = adapter.build_batch(
            [
                Ros2Sample(
                    topic="/robot_0000/odom",
                    msg_type="nav_msgs/msg/Odometry",
                    robot_id="robot_0000",
                    sample_envelope=envelope,
                )
            ],
            scenario="native_envelope_runtime_test",
            link=NetworkLink(capacity_bytes_per_tick=4096),
            timestamp_ms=0.0,
            tick=0,
        )

        with TemporaryDirectory() as tmpdir:
            log_path = Path(tmpdir) / "decisions.jsonl"
            runtime = SidecarRuntime(
                RuntimeConfig(
                    udp_host="127.0.0.1",
                    udp_port=udp_port,
                    policy="fleetqox_semantic_contract_adaptive",
                    decision_log=log_path,
                )
            )
            try:
                runtime.process_batch(batch)
            finally:
                runtime.close()
            events = [json.loads(line) for line in log_path.read_text(encoding="utf-8").splitlines()]

        self.assertEqual(events[0]["source_sample_id"], envelope.source_sample_id)
        self.assertEqual(events[0]["sample_envelope"]["publisher_id"], "fpub1-state-estimator")
        self.assertEqual(events[0]["sample_envelope"]["source_sequence_number"], 12)
        self.assertEqual(events[0]["source_metadata"]["publisher_id"], "fpub1-state-estimator")

    def test_explicit_contract_id_reaches_sidecar_event(self) -> None:
        udp_port = _free_udp_port()
        adapter = Ros2SidecarAdapter()
        sample = Ros2Sample(
            topic="/robot_0000/odom",
            msg_type="nav_msgs/msg/Odometry",
            robot_id="robot_0000",
            contract_id="fcid1-explicit",
            source_sample_id="fsid1-explicit",
            publisher_gid="01020304",
            sequence_number=99,
        )
        batch = adapter.build_batch(
            [sample],
            scenario="contract_id_runtime_test",
            link=NetworkLink(capacity_bytes_per_tick=4096),
            timestamp_ms=0.0,
            tick=0,
        )

        with TemporaryDirectory() as tmpdir:
            log_path = Path(tmpdir) / "decisions.jsonl"
            runtime = SidecarRuntime(
                RuntimeConfig(
                    udp_host="127.0.0.1",
                    udp_port=udp_port,
                    policy="fleetqox_semantic_contract_adaptive",
                    decision_log=log_path,
                )
            )
            try:
                runtime.process_batch(batch)
            finally:
                runtime.close()
            events = [json.loads(line) for line in log_path.read_text(encoding="utf-8").splitlines()]

        self.assertEqual(events[0]["contract_id"], "fcid1-explicit")
        self.assertEqual(events[0]["source_sample_id"], "fsid1-explicit")
        self.assertEqual(events[0]["source_metadata"]["publisher_gid"], "01020304")
        self.assertEqual(events[0]["source_metadata"]["sequence_number"], 99)

    def test_helpers_infer_defaults_without_ros_dependency(self) -> None:
        self.assertEqual(infer_robot_id("/tb4_01/odom"), "tb4_01")
        self.assertEqual(defaults_for_topic("/scan").flow_class, FlowClass.PERCEPTION)


def _free_udp_port() -> int:
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        try:
            sock.bind(("127.0.0.1", 0))
        except PermissionError as exc:
            raise unittest.SkipTest("sandbox disallows local UDP bind") from exc
        return int(sock.getsockname()[1])
    finally:
        sock.close()


if __name__ == "__main__":
    unittest.main()

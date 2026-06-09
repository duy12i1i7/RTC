import json
import socket
import threading
import unittest
from pathlib import Path
from types import SimpleNamespace
from tempfile import TemporaryDirectory

from fleetqox.model import NetworkLink
from fleetqox.ros2_live_bridge import (
    BridgeTopicConfig,
    LiveBridgeConfig,
    Ros2LiveSampleBuffer,
    SidecarTcpClient,
    link_provider_for_config,
    load_bridge_config,
    transport_binding_provider_for_config,
)
from scripts.run_ros2_live_bridge import (
    _semantic_payload_for_message,
    _source_metadata_for_message_info,
)
from fleetqox.sidecar_runtime import RobotFeedbackTcpClient, RuntimeConfig, SidecarRuntime, serve_tcp
from fleetqox.transport_selector import TransportBinding


class Ros2LiveBridgeTest(unittest.TestCase):
    def test_load_bridge_config_parses_topics_and_link(self) -> None:
        payload = {
            "scenario": "tb4_live",
            "sidecar": {"host": "127.0.0.1", "port": 8765},
            "flush_period_ms": 25,
            "include_feedback": True,
            "link": {
                "capacity_bytes_per_tick": 700,
                "rtt_ms": 80,
                "jitter_ms": 10,
                "loss": 0.02,
            },
            "link_schedule": [
                {
                    "at_s": 0,
                    "profile": "wifi",
                    "capacity_bytes_per_tick": 2400,
                    "rtt_ms": 40,
                    "jitter_ms": 5,
                    "loss": 0.01,
                },
                {
                    "at_s": 3,
                    "profile": "roaming",
                    "capacity_bytes_per_tick": 1400,
                    "rtt_ms": 160,
                    "jitter_ms": 25,
                    "loss": 0.03,
                },
            ],
            "transport_binding": {
                "summary": (
                    "results_ros2_live_bridge/"
                    "profile_objective_selector_balanced_v1_summary.json"
                ),
                "adaptive_profile": True,
                "smoothing_alpha": 1.0,
                "min_dwell_ticks": 0,
            },
            "topics": [
                {
                    "topic": "/robot_0001/cmd_vel",
                    "msg_type": "geometry_msgs/msg/Twist",
                    "qos": {
                        "reliability": "reliable",
                        "deadline_ms": 45,
                        "lifespan_ms": 90,
                    },
                }
            ],
        }

        config = LiveBridgeConfig.from_payload(payload)
        config.validates()

        self.assertEqual(config.scenario, "tb4_live")
        self.assertEqual(config.sidecar_port, 8765)
        self.assertEqual(config.flush_period_ms, 25.0)
        self.assertTrue(config.include_feedback)
        self.assertEqual(config.link.capacity_bytes_per_tick, 700)
        self.assertEqual(config.link_schedule[1].profile, "roaming")
        self.assertEqual(config.link_schedule[1].link.capacity_bytes_per_tick, 1400)
        self.assertEqual(config.topics[0].topic, "/robot_0001/cmd_vel")
        self.assertEqual(config.topics[0].qos.deadline_ms, 45.0)
        self.assertIsNotNone(config.transport_binding)
        assert config.transport_binding is not None
        self.assertTrue(config.transport_binding.adaptive_profile)

    def test_load_bridge_config_from_file(self) -> None:
        with TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "bridge.json"
            path.write_text(
                json.dumps(
                    {
                        "topics": [
                            {
                                "topic": "/robot_0001/fleet_state",
                                "msg_type": "nav_msgs/msg/Odometry",
                            }
                        ]
                    }
                ),
                encoding="utf-8",
            )

            config = load_bridge_config(path)

        self.assertEqual(config.topics[0].msg_type, "nav_msgs/msg/Odometry")

    def test_live_sample_buffer_coalesces_callbacks_into_latest_sample(self) -> None:
        now = [100.0]
        buffer = Ros2LiveSampleBuffer(clock_ms=lambda: now[0])
        config = BridgeTopicConfig(
            topic="/robot_0002/cmd_vel",
            msg_type="geometry_msgs/msg/Twist",
            robot_id="robot_0002",
        )

        buffer.record_sample(config, payload_size_bytes=96)
        now[0] = 105.0
        buffer.record_sample(config, payload_size_bytes=104)
        batch = buffer.drain_batch(timestamp_ms=120.0)

        self.assertEqual(buffer.pending_count(), 0)
        self.assertEqual(batch["tick"], 0)
        self.assertEqual(len(batch["flows"]), 1)
        observation = batch["flows"][0]["observation"]
        flow = batch["flows"][0]["flow"]
        self.assertEqual(observation["queue_depth"], 2)
        self.assertEqual(observation["age_ms"], 15.0)
        self.assertEqual(flow["nominal_size_bytes"], 104)

    def test_live_sample_buffer_carries_rmw_source_metadata(self) -> None:
        buffer = Ros2LiveSampleBuffer(clock_ms=lambda: 100.0)
        config = BridgeTopicConfig(
            topic="/robot_0002/cmd_vel",
            msg_type="geometry_msgs/msg/Twist",
            robot_id="robot_0002",
        )

        buffer.record_sample(
            config,
            payload_size_bytes=96,
            publisher_gid="0a0b0c",
            sequence_number=12,
            source_timestamp_ns=111,
            received_timestamp_ns=222,
        )
        batch = buffer.drain_batch(timestamp_ms=120.0)

        flow = batch["flows"][0]
        self.assertRegex(flow["source_sample_id"], r"^fsid1-[0-9a-f]{32}$")
        self.assertEqual(flow["source_metadata"]["publisher_gid"], "0a0b0c")
        self.assertEqual(flow["source_metadata"]["sequence_number"], 12)
        self.assertEqual(flow["source_metadata"]["source_timestamp_ns"], 111)
        self.assertEqual(flow["source_metadata"]["received_timestamp_ns"], 222)

    def test_live_sample_buffer_attaches_static_transport_binding(self) -> None:
        buffer = Ros2LiveSampleBuffer(
            clock_ms=lambda: 100.0,
            transport_binding=TransportBinding(
                profile="wifi",
                objective="balanced_safety_utility",
                policy="data_frame/rmw_zenoh_cpp",
                packet_format="data_frame",
                rmw="rmw_zenoh_cpp",
                score=1.0,
            ),
        )
        config = BridgeTopicConfig(
            topic="/robot_0002/cmd_vel",
            msg_type="geometry_msgs/msg/Twist",
            robot_id="robot_0002",
        )

        buffer.record_sample(config, payload_size_bytes=96)
        batch = buffer.drain_batch(timestamp_ms=120.0)

        self.assertEqual(batch["transport_binding"]["profile"], "wifi")
        self.assertEqual(
            batch["transport_binding"]["policy"],
            "data_frame/rmw_zenoh_cpp",
        )

    def test_live_sample_buffer_refreshes_adaptive_binding_provider(self) -> None:
        with TemporaryDirectory() as tmpdir:
            summary = Path(tmpdir) / "selector_summary.json"
            summary.write_text(json.dumps(_selector_summary()), encoding="utf-8")
            bridge_config = LiveBridgeConfig.from_payload(
                {
                    "transport_binding": {
                        "summary": str(summary),
                        "adaptive_profile": True,
                        "smoothing_alpha": 1.0,
                        "hysteresis_margin": 0.0,
                        "min_dwell_ticks": 0,
                    },
                    "topics": [
                        {
                            "topic": "/robot_0002/cmd_vel",
                            "msg_type": "geometry_msgs/msg/Twist",
                            "robot_id": "robot_0002",
                        }
                    ],
                }
            )
            provider = transport_binding_provider_for_config(bridge_config)

        assert provider is not None
        buffer = Ros2LiveSampleBuffer(
            clock_ms=lambda: 100.0,
            link=NetworkLink(
                capacity_bytes_per_tick=2400,
                rtt_ms=40,
                jitter_ms=5,
                loss=0.01,
            ),
            transport_binding_provider=provider,
        )
        config = bridge_config.topics[0]

        buffer.record_sample(config, payload_size_bytes=96)
        wifi_batch = buffer.drain_batch(timestamp_ms=120.0)
        buffer.link = NetworkLink(
            capacity_bytes_per_tick=1000,
            rtt_ms=160,
            jitter_ms=25,
            loss=0.03,
        )
        buffer.record_sample(config, payload_size_bytes=96)
        roaming_batch = buffer.drain_batch(timestamp_ms=140.0)

        self.assertEqual(wifi_batch["transport_binding"]["profile"], "wifi")
        self.assertEqual(roaming_batch["transport_binding"]["profile"], "roaming")
        self.assertEqual(wifi_batch["transport_binding_estimate"]["profile"], "wifi")
        self.assertEqual(
            roaming_batch["transport_binding_estimate"]["profile"],
            "roaming",
        )
        self.assertTrue(roaming_batch["transport_binding_estimate"]["changed"])

    def test_live_sample_buffer_uses_scheduled_link_provider_for_binding(self) -> None:
        with TemporaryDirectory() as tmpdir:
            summary = Path(tmpdir) / "selector_summary.json"
            summary.write_text(json.dumps(_selector_summary()), encoding="utf-8")
            bridge_config = LiveBridgeConfig.from_payload(
                {
                    "transport_binding": {
                        "summary": str(summary),
                        "adaptive_profile": True,
                        "smoothing_alpha": 1.0,
                        "hysteresis_margin": 0.0,
                        "min_dwell_ticks": 0,
                    },
                    "link_schedule": [
                        {
                            "at_s": 0.0,
                            "profile": "wifi",
                            "capacity_bytes_per_tick": 2400,
                            "rtt_ms": 40,
                            "jitter_ms": 5,
                            "loss": 0.01,
                        },
                        {
                            "at_s": 1.0,
                            "profile": "roaming",
                            "capacity_bytes_per_tick": 1000,
                            "rtt_ms": 160,
                            "jitter_ms": 25,
                            "loss": 0.03,
                        },
                    ],
                    "topics": [
                        {
                            "topic": "/robot_0002/cmd_vel",
                            "msg_type": "geometry_msgs/msg/Twist",
                            "robot_id": "robot_0002",
                        }
                    ],
                }
            )
            binding_provider = transport_binding_provider_for_config(bridge_config)
            link_provider = link_provider_for_config(bridge_config)

        assert binding_provider is not None
        assert link_provider is not None
        buffer = Ros2LiveSampleBuffer(
            clock_ms=lambda: 0.0,
            link=bridge_config.link,
            link_provider=link_provider,
            transport_binding_provider=binding_provider,
        )
        topic = bridge_config.topics[0]

        buffer.record_sample(topic, payload_size_bytes=96, received_ms=0.0)
        wifi_batch = buffer.drain_batch(timestamp_ms=0.0)
        buffer.record_sample(topic, payload_size_bytes=96, received_ms=1000.0)
        roaming_batch = buffer.drain_batch(timestamp_ms=1000.0)

        self.assertEqual(wifi_batch["link"]["capacity_bytes_per_tick"], 2400)
        self.assertEqual(roaming_batch["link"]["capacity_bytes_per_tick"], 1000)
        self.assertEqual(wifi_batch["transport_binding"]["profile"], "wifi")
        self.assertEqual(roaming_batch["transport_binding"]["profile"], "roaming")

    def test_live_sample_buffer_uses_objective_schedule_for_binding(self) -> None:
        with TemporaryDirectory() as tmpdir:
            balanced = Path(tmpdir) / "balanced_summary.json"
            autonomy = Path(tmpdir) / "autonomy_summary.json"
            balanced.write_text(json.dumps(_selector_summary()), encoding="utf-8")
            autonomy.write_text(
                json.dumps(
                    _selector_summary(
                        objective="autonomy_safety",
                        bindings=[
                            _binding_payload(
                                "wifi",
                                "data_frame/rmw_zenoh_cpp",
                                objective="autonomy_safety",
                            ),
                            _binding_payload(
                                "wan",
                                "data_frame/rmw_cyclonedds_cpp",
                                objective="autonomy_safety",
                            ),
                            _binding_payload(
                                "roaming",
                                "event_json/rmw_zenoh_cpp",
                                objective="autonomy_safety",
                            ),
                        ],
                    )
                ),
                encoding="utf-8",
            )
            bridge_config = LiveBridgeConfig.from_payload(
                {
                    "transport_binding": {
                        "summary": str(balanced),
                        "objective_summaries": {
                            "autonomy_safety": str(autonomy),
                        },
                        "adaptive_profile": True,
                        "smoothing_alpha": 1.0,
                        "hysteresis_margin": 0.0,
                        "min_dwell_ticks": 0,
                        "objective_schedule": [
                            {
                                "at_s": 0.0,
                                "objective": "balanced_safety_utility",
                            },
                            {
                                "at_s": 1.0,
                                "objective": "autonomy_safety",
                            },
                        ],
                    },
                    "topics": [
                        {
                            "topic": "/robot_0002/cmd_vel",
                            "msg_type": "geometry_msgs/msg/Twist",
                            "robot_id": "robot_0002",
                        }
                    ],
                }
            )
            provider = transport_binding_provider_for_config(bridge_config)

        assert provider is not None
        buffer = Ros2LiveSampleBuffer(
            clock_ms=lambda: 0.0,
            link=NetworkLink(
                capacity_bytes_per_tick=1800,
                rtt_ms=90,
                jitter_ms=15,
                loss=0.015,
            ),
            transport_binding_provider=provider,
        )
        topic = bridge_config.topics[0]

        buffer.record_sample(topic, payload_size_bytes=96, received_ms=0.0)
        balanced_batch = buffer.drain_batch(timestamp_ms=0.0)
        buffer.record_sample(topic, payload_size_bytes=96, received_ms=1000.0)
        autonomy_batch = buffer.drain_batch(timestamp_ms=1000.0)

        self.assertEqual(
            balanced_batch["transport_binding"]["objective"],
            "balanced_safety_utility",
        )
        self.assertEqual(
            balanced_batch["transport_binding"]["policy"],
            "event_json/rmw_zenoh_cpp",
        )
        self.assertEqual(
            autonomy_batch["transport_binding"]["objective"],
            "autonomy_safety",
        )
        self.assertEqual(
            autonomy_batch["transport_binding"]["policy"],
            "data_frame/rmw_cyclonedds_cpp",
        )

    def test_sidecar_tcp_client_sends_ros2_bridge_batch(self) -> None:
        listen_port = _free_tcp_port()
        udp_port = _free_udp_port()
        config = BridgeTopicConfig(
            topic="/robot_0000/cmd_vel",
            msg_type="geometry_msgs/msg/Twist",
            robot_id="robot_0000",
        )
        buffer = Ros2LiveSampleBuffer(
            scenario="live_tcp_test",
            clock_ms=lambda: 0.0,
            include_feedback=True,
        )
        buffer.record_sample(config, payload_size_bytes=96, received_ms=0.0)
        batch = buffer.drain_batch(timestamp_ms=20.0)

        with TemporaryDirectory() as tmpdir:
            runtime = SidecarRuntime(
                RuntimeConfig(
                    udp_host="127.0.0.1",
                    udp_port=udp_port,
                    policy="fleetqox_semantic_contract_adaptive",
                    decision_log=Path(tmpdir) / "decisions.jsonl",
                )
            )
            thread = threading.Thread(
                target=serve_tcp,
                kwargs={
                    "host": "127.0.0.1",
                    "port": listen_port,
                    "runtime": runtime,
                    "idle_timeout_s": 5.0,
                    "max_runtime_s": 5.0,
                },
                daemon=True,
            )
            thread.start()
            try:
                client = SidecarTcpClient("127.0.0.1", listen_port)
                response = client.send_batch(batch)
                stop = client.stop()
                client.close()
                thread.join(timeout=2.0)
            finally:
                runtime.close()

        self.assertEqual(response["status"], "ok")
        self.assertEqual(response["accepted"], 1)
        self.assertIn("feedback", response)
        self.assertEqual(stop["status"], "stopping")

    def test_robot_feedback_tcp_client_reuses_connection(self) -> None:
        listen_port = _free_tcp_port()
        ready = threading.Event()
        accepted = []
        messages = []

        def server() -> None:
            with socket.create_server(("127.0.0.1", listen_port), reuse_port=False) as sock:
                ready.set()
                conn, _ = sock.accept()
                accepted.append(True)
                with conn:
                    conn_file = conn.makefile("rwb")
                    for _ in range(2):
                        raw = conn_file.readline()
                        messages.append(json.loads(raw.decode("utf-8")))
                        conn_file.write(b'{"status":"ok","applied":1}\n')
                        conn_file.flush()

        thread = threading.Thread(target=server, daemon=True)
        thread.start()
        self.assertTrue(ready.wait(timeout=2.0))

        client = RobotFeedbackTcpClient(
            host="127.0.0.1",
            port=listen_port,
            timeout_s=1.0,
        )
        try:
            first = client.send_feedback([{"robot_id": "robot_0000"}])
            second = client.send_feedback([{"robot_id": "robot_0001"}])
        finally:
            client.close()
        thread.join(timeout=2.0)

        self.assertEqual(first["applied"], 1)
        self.assertEqual(second["applied"], 1)
        self.assertEqual(len(accepted), 1)
        self.assertEqual(len(messages), 2)
        self.assertEqual(messages[0]["type"], "robot_feedback")
        self.assertEqual(messages[1]["feedback"][0]["robot_id"], "robot_0001")

    def test_live_bridge_extracts_odometry_semantic_payload(self) -> None:
        config = BridgeTopicConfig(
            topic="/robot_0000/odom",
            msg_type="nav_msgs/msg/Odometry",
            robot_id="robot_0000",
        )
        message = SimpleNamespace(
            header=_header("odom"),
            child_frame_id="robot_0000",
            pose=SimpleNamespace(
                pose=SimpleNamespace(
                    position=SimpleNamespace(x=1.2, y=0.3, z=0.0),
                    orientation=SimpleNamespace(x=0.0, y=0.0, z=0.1, w=0.99),
                ),
                covariance=[0.0] * 36,
            ),
            twist=SimpleNamespace(
                twist=SimpleNamespace(
                    linear=SimpleNamespace(x=0.2, y=0.0, z=0.0),
                    angular=SimpleNamespace(x=0.0, y=0.0, z=0.1),
                ),
                covariance=[0.0] * 36,
            ),
        )

        payload = _semantic_payload_for_message(config, message)

        self.assertEqual(payload["msg_type"], "nav_msgs/msg/Odometry")
        self.assertEqual(payload["header"]["frame_id"], "odom")
        self.assertEqual(payload["odometry"]["child_frame_id"], "robot_0000")
        self.assertEqual(payload["odometry"]["pose"]["position"]["x"], 1.2)

    def test_live_bridge_extracts_downsampled_scan_semantic_payload(self) -> None:
        config = BridgeTopicConfig(
            topic="/robot_0000/scan",
            msg_type="sensor_msgs/msg/LaserScan",
            robot_id="robot_0000",
        )
        message = SimpleNamespace(
            header=_header("robot_0000/base_scan"),
            angle_min=-1.0,
            angle_max=1.0,
            angle_increment=0.1,
            time_increment=0.0,
            scan_time=0.05,
            range_min=0.12,
            range_max=8.0,
            ranges=[float(index) for index in range(180)],
            intensities=[],
        )

        payload = _semantic_payload_for_message(config, message)

        self.assertEqual(payload["msg_type"], "sensor_msgs/msg/LaserScan")
        self.assertEqual(payload["scan"]["source_sample_count"], 180)
        self.assertEqual(payload["scan"]["downsample_stride"], 3)
        self.assertEqual(len(payload["scan"]["ranges"]), 60)
        self.assertEqual(payload["scan"]["angle_increment"], 0.30000000000000004)

    def test_live_bridge_enriches_semantic_payload_with_message_info_metadata(self) -> None:
        config = BridgeTopicConfig(
            topic="/robot_0000/cmd_vel",
            msg_type="geometry_msgs/msg/Twist",
            robot_id="robot_0000",
        )
        message = SimpleNamespace(
            linear=SimpleNamespace(x=0.3, y=0.0, z=0.0),
            angular=SimpleNamespace(x=0.0, y=0.0, z=0.1),
        )
        message_info = {
            "publisher_gid": {"data": [1, 2, 3, 4]},
            "publication_sequence_number": 42,
            "source_timestamp": 123_000,
            "received_timestamp": 456_000,
        }

        source_metadata = _source_metadata_for_message_info(message_info)
        payload = _semantic_payload_for_message(config, message, source_metadata=source_metadata)

        self.assertEqual(source_metadata["publisher_gid"], "01020304")
        self.assertEqual(source_metadata["sequence_number"], 42)
        self.assertEqual(payload["publisher_gid"], "01020304")
        self.assertEqual(payload["source_metadata"]["source_timestamp_ns"], 123_000)


def _free_tcp_port() -> int:
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        try:
            sock.bind(("127.0.0.1", 0))
        except PermissionError as exc:
            raise unittest.SkipTest("sandbox disallows local TCP bind") from exc
        return int(sock.getsockname()[1])
    finally:
        sock.close()


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


def _header(frame_id: str):
    return SimpleNamespace(
        frame_id=frame_id,
        stamp=SimpleNamespace(sec=1, nanosec=2),
    )


def _selector_summary(
    *,
    objective: str = "balanced_safety_utility",
    bindings: list[dict[str, object]] | None = None,
) -> dict[str, object]:
    return {
        "bindings": bindings
        or [
            _binding_payload(
                "wifi",
                "data_frame/rmw_zenoh_cpp",
                objective=objective,
                score=1.0,
            ),
            _binding_payload(
                "wan",
                "event_json/rmw_zenoh_cpp",
                objective=objective,
                score=0.9,
            ),
            _binding_payload(
                "roaming",
                "event_json/rmw_zenoh_cpp",
                objective=objective,
                score=0.8,
            ),
        ],
    }


def _binding_payload(
    profile: str,
    policy: str,
    *,
    objective: str,
    score: float = 1.0,
) -> dict[str, object]:
    packet_format, rmw = policy.split("/", 1)
    return {
        "profile": profile,
        "objective": objective,
        "policy": policy,
        "packet_format": packet_format,
        "rmw": rmw,
        "score": score,
    }


if __name__ == "__main__":
    unittest.main()

import ctypes
import json
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

from fleetqox.rmw_boundary import FleetRmwBoundary
from fleetqox.ros2_shim import Ros2Sample


ROOT = Path(__file__).resolve().parents[1]
PKG = ROOT / "ros2_ws" / "src" / "rmw_fleetqox_cpp"
IFACE_PKG = ROOT / "ros2_ws" / "src" / "fleetrmw_interfaces"


class RmwFleetQoxCppPackageTest(unittest.TestCase):
    def test_package_manifest_and_targets_exist(self) -> None:
        self.assertTrue((PKG / "package.xml").exists())
        cmake = (PKG / "CMakeLists.txt").read_text()
        self.assertIn("${PROJECT_NAME}_transport", cmake)
        self.assertIn("POSITION_INDEPENDENT_CODE ON", cmake)
        self.assertIn("src/rmw_identifier.cpp", cmake)
        self.assertIn("src/rmw_graph.cpp", cmake)
        self.assertIn("src/rmw_lifecycle.cpp", cmake)
        self.assertIn("src/rmw_pubsub.cpp", cmake)
        self.assertIn("src/rmw_stubs.cpp", cmake)
        self.assertIn("src/rmw_wait.cpp", cmake)
        self.assertIn("fleetrmw_transport_loop_smoke", cmake)
        self.assertIn("fleetrmw_frame_probe", cmake)
        self.assertIn("fleetrmw_action_frame_probe", cmake)
        self.assertIn("fleetrmw_lifecycle_probe", cmake)
        self.assertIn("fleetrmw_serialized_pubsub_probe", cmake)
        self.assertIn("fleetrmw_qos_probe", cmake)
        self.assertIn("fleetrmw_service_qos_probe", cmake)
        self.assertIn("fleetrmw_service_error_probe", cmake)
        self.assertIn("fleetrmw_reliability_probe", cmake)
        self.assertIn("fleetrmw_reliable_interprocess_probe", cmake)
        self.assertIn("fleetrmw_typed_pubsub_probe", cmake)
        self.assertIn("fleetrmw_std_msgs_string_probe", cmake)
        self.assertIn("fleetrmw_geometry_twist_probe", cmake)
        self.assertIn("fleetrmw_cpp_typesupport_probe", cmake)
        self.assertIn("fleetrmw_rclcpp_interprocess_probe", cmake)
        self.assertIn("fleetrmw_rcl_string_probe", cmake)
        self.assertIn("fleetrmw_rcl_graph_talker", cmake)
        self.assertIn("fleetrmw_rcl_service_node", cmake)
        self.assertIn('"c:rosidl_typesupport_introspection_c"', cmake)
        self.assertIn('"cpp:rosidl_typesupport_introspection_cpp"', cmake)
        self.assertIn("fleetrmw_wait_probe", cmake)
        self.assertIn("fleetrmw_graph_probe", cmake)
        self.assertIn("fleetrmw_interprocess_pubsub_probe", cmake)
        self.assertIn("fleetrmw_udp_router_probe", cmake)
        self.assertIn("fleetrmw_remote_graph_probe", cmake)
        self.assertIn("fleetrmw_remote_graph_lease_probe", cmake)
        manifest = (PKG / "package.xml").read_text()
        self.assertIn("<depend>rmw</depend>", manifest)
        self.assertIn("<depend>rcutils</depend>", manifest)
        self.assertIn("<depend>rcl</depend>", manifest)
        self.assertIn("<depend>rclcpp</depend>", manifest)
        self.assertIn("<depend>rosidl_typesupport_c</depend>", manifest)
        self.assertIn("<depend>rosidl_typesupport_cpp</depend>", manifest)
        self.assertIn("<depend>rosidl_typesupport_introspection_cpp</depend>", manifest)
        wait_source = (PKG / "src" / "rmw_wait.cpp").read_text()
        self.assertIn("guard_data_from_waitable", wait_source)
        self.assertIn("std::atomic<bool> triggered", wait_source)
        service_source = (PKG / "src" / "rmw_stubs.cpp").read_text()
        self.assertIn("service_cpp_introspection_members", service_source)
        self.assertIn(
            "rosidl_typesupport_cpp::get_service_typesupport_handle_function",
            service_source,
        )
        self.assertIn("<depend>std_srvs</depend>", manifest)
        cpp_probe = (PKG / "src" / "cpp_typesupport_probe.cpp").read_text()
        self.assertIn("fleetrmw.cpp_typesupport_probe.v1", cpp_probe)
        self.assertIn("rosidl_typesupport_cpp", cpp_probe)
        self.assertIn("geometry_msgs::msg::PoseStamped", cpp_probe)
        self.assertIn("bounded_pose_size_ok", cpp_probe)
        self.assertIn("bounded_c_pose_size_ok", cpp_probe)
        self.assertIn("rmw_get_serialized_message_size", cpp_probe)
        cpp_runner = ROOT / "scripts" / "run_rmw_docker_cpp_typesupport_probe.py"
        self.assertTrue(cpp_runner.exists())
        self.assertIn(
            "fleetrmw.docker_cpp_typesupport_probe.v1",
            cpp_runner.read_text(),
        )
        rclcpp_probe = (PKG / "src" / "rclcpp_interprocess_probe.cpp").read_text()
        self.assertIn("fleetrmw.rclcpp_interprocess_client.v1", rclcpp_probe)
        self.assertIn("geometry_msgs::msg::PoseStamped", rclcpp_probe)
        self.assertIn("publisher_network_flow", rclcpp_probe)
        self.assertIn("subscription_network_flow", rclcpp_probe)
        self.assertIn("request_callback_observed", rclcpp_probe)
        self.assertIn("response_callback_observed", rclcpp_probe)
        rclcpp_runner = ROOT / "scripts" / "run_rmw_docker_router_rclcpp_interprocess_probe.py"
        self.assertTrue(rclcpp_runner.exists())
        self.assertIn(
            "fleetrmw.docker_router_rclcpp_interprocess_probe.v1",
            rclcpp_runner.read_text(),
        )
        header = (PKG / "include" / "rmw_fleetqox_cpp" / "data_frame.hpp").read_text()
        self.assertIn("fleetrmw.data_frame.v1", header)
        self.assertIn("fleetrmw.ack_nack.v1", header)
        self.assertIn("fleetrmw.route_advertisement.v1", header)
        self.assertIn("fleetrmw.graph_advertisement.v1", header)
        self.assertIn("fleetrmw.service_frame.v1", header)
        self.assertIn("fleetrmw.action_frame.v1", header)
        self.assertIn("AckNackFrame", header)
        self.assertIn("ActionFrame", header)
        self.assertIn("decode_action_frame", header)
        self.assertIn("decode_ack_nack", header)
        self.assertIn("initialized", header)

    def test_transport_loop_smoke_compiles_and_runs_without_ros(self) -> None:
        compiler = shutil.which("c++")
        if compiler is None:
            self.skipTest("c++ compiler is not available")
        with tempfile.TemporaryDirectory() as tmp:
            binary = Path(tmp) / "fleetrmw_transport_loop_smoke"
            subprocess.run(
                [
                    compiler,
                    "-std=c++17",
                    "-I",
                    str(PKG / "include"),
                    str(PKG / "src" / "data_frame.cpp"),
                    str(PKG / "src" / "transport_loop_smoke.cpp"),
                    "-o",
                    str(binary),
                ],
                check=True,
                cwd=ROOT,
            )
            result = subprocess.run(
                [
                    str(binary),
                    "--robot-count",
                    "3",
                    "--samples-per-robot",
                    "5",
                    "--skip-every",
                    "2",
                    "--json",
                ],
                check=True,
                cwd=ROOT,
                text=True,
                stdout=subprocess.PIPE,
            )
            first_loss_result = subprocess.run(
                [
                    str(binary),
                    "--robot-count",
                    "1",
                    "--samples-per-robot",
                    "3",
                    "--skip-first",
                    "--json",
                ],
                check=True,
                cwd=ROOT,
                text=True,
                stdout=subprocess.PIPE,
            )
        summary = json.loads(result.stdout)
        first_loss_summary = json.loads(first_loss_result.stdout)
        self.assertEqual(summary["published"], 15)
        self.assertEqual(summary["taken"], 15)
        self.assertEqual(summary["retransmitted"], 6)
        self.assertEqual(summary["missing_sequence_range_count"], 6)
        self.assertEqual(first_loss_summary["published"], 3)
        self.assertEqual(first_loss_summary["taken"], 3)
        self.assertEqual(first_loss_summary["retransmitted"], 1)
        self.assertEqual(first_loss_summary["missing_sequence_range_count"], 1)
        self.assertEqual(first_loss_summary["late_out_of_order_count"], 1)

    def test_cpp_frame_probe_decodes_python_data_frame(self) -> None:
        compiler = shutil.which("c++")
        if compiler is None:
            self.skipTest("c++ compiler is not available")
        boundary = FleetRmwBoundary()
        published = boundary.publish(
            Ros2Sample(
                topic="/robot_0005/cmd_vel",
                msg_type="geometry_msgs/msg/Twist",
                robot_id="robot_0005",
                sequence_number=42,
                source_timestamp_ns=42_000_000,
            ),
            timestamp_ms=42.0,
            tick=42,
        )
        with tempfile.TemporaryDirectory() as tmp:
            binary = Path(tmp) / "fleetrmw_frame_probe"
            subprocess.run(
                [
                    compiler,
                    "-std=c++17",
                    "-I",
                    str(PKG / "include"),
                    str(PKG / "src" / "data_frame.cpp"),
                    str(PKG / "src" / "frame_probe.cpp"),
                    "-o",
                    str(binary),
                ],
                check=True,
                cwd=ROOT,
            )
            result = subprocess.run(
                [str(binary)],
                input=published["encoded"],
                check=True,
                cwd=ROOT,
                stdout=subprocess.PIPE,
            )
        decoded = json.loads(result.stdout)
        self.assertEqual(decoded["status"], "decoded")
        self.assertEqual(decoded["robot_id"], "robot_0005")
        self.assertEqual(decoded["topic"], "/robot_0005/cmd_vel")
        self.assertEqual(decoded["source_sequence_number"], 42)

    def test_cpp_data_frame_round_trips_serialized_payload(self) -> None:
        compiler = shutil.which("c++")
        if compiler is None:
            self.skipTest("c++ compiler is not available")
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp) / "payload_roundtrip.cpp"
            source.write_text(
                r'''
#include "rmw_fleetqox_cpp/data_frame.hpp"

#include <cstdint>
#include <iostream>
#include <vector>

int main()
{
  rmw_fleetqox_cpp::DataFrame frame{
    "robot_0001",
    "/robot_0001/cmd_vel",
    "fpubcpp-test",
    7,
    7000000,
    std::vector<std::uint8_t>{0x66, 0x72, 0x6d, 0x77}};
  const std::string encoded = rmw_fleetqox_cpp::encode_data_frame(frame);
  const auto decoded = rmw_fleetqox_cpp::decode_data_frame(encoded);
  if (!decoded || decoded->serialized_payload != frame.serialized_payload) {
    return 1;
  }
  std::cout << decoded->serialized_payload.size() << std::endl;
  return 0;
}
''',
                encoding="utf-8",
            )
            binary = Path(tmp) / "payload_roundtrip"
            subprocess.run(
                [
                    compiler,
                    "-std=c++17",
                    "-I",
                    str(PKG / "include"),
                    str(PKG / "src" / "data_frame.cpp"),
                    str(source),
                    "-o",
                    str(binary),
                ],
                check=True,
                cwd=ROOT,
            )
            result = subprocess.run(
                [str(binary)],
                check=True,
                cwd=ROOT,
                text=True,
                stdout=subprocess.PIPE,
            )
        self.assertEqual(result.stdout.strip(), "4")

    def test_cpp_route_advertisement_round_trips(self) -> None:
        compiler = shutil.which("c++")
        if compiler is None:
            self.skipTest("c++ compiler is not available")
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp) / "route_advertisement_roundtrip.cpp"
            source.write_text(
                r'''
#include "rmw_fleetqox_cpp/data_frame.hpp"

#include <iostream>

int main()
{
  rmw_fleetqox_cpp::RouteAdvertisement advertisement{
    "subscriber-1",
    "subscriber",
    "/fleetqox/discovery_probe",
    "std_msgs/msg/String",
    5000};
  const std::string encoded = rmw_fleetqox_cpp::encode_route_advertisement(advertisement);
  const auto decoded = rmw_fleetqox_cpp::decode_route_advertisement(encoded);
  if (!decoded || decoded->topic != advertisement.topic ||
    decoded->role != advertisement.role || decoded->lease_ms != advertisement.lease_ms)
  {
    return 1;
  }
  std::cout << decoded->topic << std::endl;
  return 0;
}
''',
                encoding="utf-8",
            )
            binary = Path(tmp) / "route_advertisement_roundtrip"
            subprocess.run(
                [
                    compiler,
                    "-std=c++17",
                    "-I",
                    str(PKG / "include"),
                    str(PKG / "src" / "data_frame.cpp"),
                    str(source),
                    "-o",
                    str(binary),
                ],
                check=True,
                cwd=ROOT,
            )
            result = subprocess.run(
                [str(binary)],
                check=True,
                cwd=ROOT,
                text=True,
                stdout=subprocess.PIPE,
            )
        self.assertEqual(result.stdout.strip(), "/fleetqox/discovery_probe")

    def test_cpp_graph_advertisement_round_trips(self) -> None:
        compiler = shutil.which("c++")
        if compiler is None:
            self.skipTest("c++ compiler is not available")
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp) / "graph_advertisement_roundtrip.cpp"
            source.write_text(
                r'''
#include "rmw_fleetqox_cpp/data_frame.hpp"

#include <iostream>

int main()
{
  rmw_fleetqox_cpp::GraphAdvertisement advertisement{
    "publisher-1",
    "add",
    "publisher",
    "talker",
    "/fleetqox",
    "/fleetqox/chatter",
    "std_msgs/msg/String",
    "00112233445566778899aabbccddeeff",
    rmw_fleetqox_cpp::GraphQosProfile{1, 10, 2, 2, 0, 0, 0, 0, 1, 0, 0, 0},
    5000};
  const std::string encoded = rmw_fleetqox_cpp::encode_graph_advertisement(advertisement);
  const auto decoded = rmw_fleetqox_cpp::decode_graph_advertisement(encoded);
  if (!decoded || decoded->entity_kind != advertisement.entity_kind ||
    decoded->topic != advertisement.topic || decoded->node_name != advertisement.node_name ||
    decoded->endpoint_gid != advertisement.endpoint_gid || decoded->qos.depth != 10)
  {
    return 1;
  }
  std::cout << decoded->entity_kind << ":" << decoded->topic << std::endl;
  return 0;
}
''',
                encoding="utf-8",
            )
            binary = Path(tmp) / "graph_advertisement_roundtrip"
            subprocess.run(
                [
                    compiler,
                    "-std=c++17",
                    "-I",
                    str(PKG / "include"),
                    str(PKG / "src" / "data_frame.cpp"),
                    str(source),
                    "-o",
                    str(binary),
                ],
                check=True,
                cwd=ROOT,
            )
            result = subprocess.run(
                [str(binary)],
                check=True,
                cwd=ROOT,
                text=True,
                stdout=subprocess.PIPE,
            )
        self.assertEqual(result.stdout.strip(), "publisher:/fleetqox/chatter")

    def test_cpp_service_frame_round_trips(self) -> None:
        compiler = shutil.which("c++")
        if compiler is None:
            self.skipTest("c++ compiler is not available")
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp) / "service_frame_roundtrip.cpp"
            source.write_text(
                r'''
#include "rmw_fleetqox_cpp/data_frame.hpp"

#include <iostream>

int main()
{
  rmw_fleetqox_cpp::ServiceFrame frame{
    "request",
    "/fleetqox/set_bool",
    "std_srvs/srv/SetBool",
    "client-1",
    "service-1",
    9,
    12345,
    5000000,
    {0x01, 0x02, 0x03}};
  const std::string encoded = rmw_fleetqox_cpp::encode_service_frame(frame);
  const auto decoded = rmw_fleetqox_cpp::decode_service_frame(encoded);
  if (!decoded || decoded->role != frame.role ||
    decoded->service_name != frame.service_name ||
    decoded->client_endpoint_id != frame.client_endpoint_id ||
    decoded->sequence_id != frame.sequence_id ||
    decoded->lifespan_ns != frame.lifespan_ns ||
    decoded->serialized_payload != frame.serialized_payload)
  {
    return 1;
  }
  if (rmw_fleetqox_cpp::service_frame_expired(frame, frame.source_timestamp_ns + 4999999)) {
    return 2;
  }
  if (!rmw_fleetqox_cpp::service_frame_expired(frame, frame.source_timestamp_ns + 5000001)) {
    return 3;
  }
  const std::string legacy = std::string(rmw_fleetqox_cpp::kDataFrameMagic) +
    "{\"schema_version\":\"fleetrmw.service_frame.v1\",\"kind\":\"service_frame\","
    "\"role\":\"response\",\"service_name\":\"/fleetqox/set_bool\","
    "\"type_name\":\"std_srvs/srv/SetBool\",\"client_endpoint_id\":\"client-1\","
    "\"service_endpoint_id\":\"service-1\",\"sequence_id\":10,"
    "\"source_timestamp_ns\":12345}";
  const auto legacy_decoded = rmw_fleetqox_cpp::decode_service_frame(legacy);
  if (!legacy_decoded || legacy_decoded->lifespan_ns != 0 ||
    rmw_fleetqox_cpp::service_frame_expired(*legacy_decoded, 999999999))
  {
    return 4;
  }
  std::cout << decoded->role << ":" << decoded->service_name << std::endl;
  return 0;
}
''',
                encoding="utf-8",
            )
            binary = Path(tmp) / "service_frame_roundtrip"
            subprocess.run(
                [
                    compiler,
                    "-std=c++17",
                    "-I",
                    str(PKG / "include"),
                    str(PKG / "src" / "data_frame.cpp"),
                    str(source),
                    "-o",
                    str(binary),
                ],
                check=True,
                cwd=ROOT,
            )
            result = subprocess.run(
                [str(binary)],
                check=True,
                cwd=ROOT,
                text=True,
                stdout=subprocess.PIPE,
            )
        self.assertEqual(result.stdout.strip(), "request:/fleetqox/set_bool")

    def test_cpp_action_frame_round_trips(self) -> None:
        compiler = shutil.which("c++")
        if compiler is None:
            self.skipTest("c++ compiler is not available")
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp) / "action_frame_roundtrip.cpp"
            source.write_text(
                r'''
#include "rmw_fleetqox_cpp/data_frame.hpp"

#include <iostream>
#include <string>

int main()
{
  rmw_fleetqox_cpp::ActionFrame frame{
    "feedback",
    "/fleetqox/navigate_to_pose",
    "nav2_msgs/action/NavigateToPose",
    "action-endpoint-1",
    "goal-00112233",
    42,
    12345,
    5000000,
    {0x42, 0xA0, 0x5A}};
  const std::string encoded = rmw_fleetqox_cpp::encode_action_frame(frame);
  const auto decoded = rmw_fleetqox_cpp::decode_action_frame(encoded);
  if (!decoded || decoded->role != frame.role ||
    decoded->action_name != frame.action_name ||
    decoded->type_name != frame.type_name ||
    decoded->endpoint_id != frame.endpoint_id ||
    decoded->goal_id != frame.goal_id ||
    decoded->sequence_id != frame.sequence_id ||
    decoded->lifespan_ns != frame.lifespan_ns ||
    decoded->serialized_payload != frame.serialized_payload)
  {
    return 1;
  }
  if (rmw_fleetqox_cpp::action_frame_expired(frame, frame.source_timestamp_ns + 4999999)) {
    return 2;
  }
  if (!rmw_fleetqox_cpp::action_frame_expired(frame, frame.source_timestamp_ns + 5000001)) {
    return 3;
  }
  const std::string legacy = std::string(rmw_fleetqox_cpp::kDataFrameMagic) +
    "{\"schema_version\":\"fleetrmw.action_frame.v1\",\"kind\":\"action_frame\","
    "\"role\":\"result\",\"action_name\":\"/fleetqox/navigate_to_pose\","
    "\"type_name\":\"nav2_msgs/action/NavigateToPose\","
    "\"endpoint_id\":\"action-endpoint-1\",\"goal_id\":\"goal-00112233\","
    "\"sequence_id\":43,\"source_timestamp_ns\":12345}";
  const auto legacy_decoded = rmw_fleetqox_cpp::decode_action_frame(legacy);
  if (!legacy_decoded || legacy_decoded->lifespan_ns != 0 ||
    rmw_fleetqox_cpp::action_frame_expired(*legacy_decoded, 999999999))
  {
    return 4;
  }
  const bool rejects_service_schema = !rmw_fleetqox_cpp::decode_action_frame(
    rmw_fleetqox_cpp::encode_service_frame(
      rmw_fleetqox_cpp::ServiceFrame{
        "request",
        "/fleetqox/set_bool",
        "std_srvs/srv/SetBool",
        "client-1",
        "service-1",
        1,
        1000000,
        5000000,
        {0x01}}));
  if (!rejects_service_schema) {
    return 5;
  }
  std::cout << decoded->role << ":" << decoded->action_name << std::endl;
  return 0;
}
''',
                encoding="utf-8",
            )
            binary = Path(tmp) / "action_frame_roundtrip"
            subprocess.run(
                [
                    compiler,
                    "-std=c++17",
                    "-I",
                    str(PKG / "include"),
                    str(PKG / "src" / "data_frame.cpp"),
                    str(source),
                    "-o",
                    str(binary),
                ],
                check=True,
                cwd=ROOT,
            )
            result = subprocess.run(
                [str(binary)],
                check=True,
                cwd=ROOT,
                text=True,
                stdout=subprocess.PIPE,
            )
        self.assertEqual(result.stdout.strip(), "feedback:/fleetqox/navigate_to_pose")

    def test_rmw_pubsub_uses_socket_backed_data_frame_transport(self) -> None:
        source = (PKG / "src" / "rmw_pubsub.cpp").read_text()
        self.assertIn("LoopbackSocketTransport", source)
        self.assertIn("sendto(", source)
        self.assertIn("recvfrom(", source)
        self.assertIn("FLEETQOX_RMW_BIND", source)
        self.assertIn("FLEETQOX_RMW_PEERS", source)
        self.assertIn("getaddrinfo", source)
        self.assertIn("decode_data_frame(encoded_frame)", source)
        self.assertIn("rmw_fleetqox_cpp_socket_frames_sent", source)
        self.assertIn("rmw_fleetqox_cpp_socket_frames_received", source)
        self.assertIn("send_subscription_advertisement", source)
        self.assertIn("send_graph_advertisement", source)
        self.assertIn("apply_received_graph_advertisement", source)
        self.assertIn("rmw_fleetqox_cpp_graph_apply_remote_advertisement", source)
        self.assertIn("typed_message_size_from_type_support", source)
        self.assertIn("rmw_fleetqox_cpp_type_erased_probe", source)
        self.assertIn("rosidl_typesupport_introspection_c__identifier", source)
        self.assertIn("serialize_introspection_c_message", source)
        self.assertIn("deserialize_introspection_c_message", source)
        self.assertIn("serialize_introspection_cpp_message", source)
        self.assertIn("deserialize_introspection_cpp_message", source)
        self.assertIn("rosidl_typesupport_introspection_cpp::typesupport_identifier", source)
        self.assertIn("rosidl_typesupport_cpp::get_message_typesupport_handle_function", source)
        self.assertIn("type_name_from_type_support", source)
        self.assertIn("resolve_effective_type_support", source)
        self.assertIn("rosidl_typesupport_c__get_message_typesupport_handle_function", source)
        self.assertIn("rmw_fleetqox_cpp_socket_ensure_started", source)
        self.assertIn("g_retransmit_ledger", source)
        self.assertIn("decode_ack_nack", source)
        self.assertIn("send_ack_nack", source)
        self.assertIn("send_retransmission_frame", source)
        self.assertIn("FLEETQOX_RMW_DROP_SOURCE_SEQUENCES", source)
        self.assertIn("FLEETQOX_RMW_PEER_POLICY", source)
        self.assertIn("adaptive_failover", source)
        self.assertIn("adaptive_score", source)
        self.assertIn("adaptive_qos", source)
        self.assertIn("fleet_plan", source)
        self.assertIn("FLEETQOX_RMW_FLEET_PATH_PLAN", source)
        self.assertIn("FLEETQOX_RMW_FLEET_PATH_PLAN_FILE", source)
        self.assertIn("FLEETQOX_RMW_REPAIR_PATH_PLAN", source)
        self.assertIn("FLEETQOX_RMW_REPAIR_PATH_PLAN_FILE", source)
        self.assertIn("FLEETQOX_RMW_REPAIR_RETRANSMISSION_BUDGET", source)
        self.assertIn("FLEETQOX_RMW_REPAIR_MIN_INTERVAL_MS", source)
        self.assertIn("FLEETQOX_RMW_REPAIR_MAX_ATTEMPTS_PER_SEQUENCE", source)
        self.assertIn("FLEETQOX_RMW_REPAIR_ADMISSION_STRICT", source)
        self.assertIn("parse_fleet_repair_plan", source)
        self.assertIn("source_sequences", source)
        self.assertIn("FleetPathPlanRule", source)
        self.assertIn("parse_fleet_path_plan", source)
        self.assertIn("refresh_fleet_path_plan_from_file", source)
        self.assertIn("refresh_repair_path_plan_from_file", source)
        self.assertIn("rmw_fleetqox_cpp_last_take_source_sequence", source)
        self.assertIn("rmw_fleetqox_cpp_last_take_source_timestamp_ns", source)
        self.assertIn("rmw_fleetqox_cpp_last_take_timestamp_ns", source)
        self.assertIn("rmw_fleetqox_cpp_duplicate_data_frames_deduped", source)
        self.assertIn("rmw_fleetqox_cpp_out_of_order_data_frames_observed", source)
        self.assertIn("rmw_fleetqox_cpp_socket_ack_nack_duplicate_received", source)
        self.assertIn("rmw_fleetqox_cpp_socket_ack_nack_out_of_order_received", source)
        self.assertIn("rmw_fleetqox_cpp_socket_idle_repair_ack_nack_sent", source)
        self.assertIn("g_idle_repair_ack_nack_sent", source)
        self.assertIn("feedback_from_sequence_state", source)
        self.assertIn("last_repair_request_ns", source)
        self.assertIn('"fpubcpp-" + socket_transport().bound_endpoint()', source)
        self.assertIn('"fsubcpp-" + socket_transport().bound_endpoint()', source)
        self.assertIn("peer_path_ids_", source)
        self.assertIn("fleet_plan_targets", source)
        self.assertIn("FLEETQOX_RMW_REDUNDANT_DEADLINE_MS", source)
        self.assertIn("adaptive_failovers", source)
        self.assertIn("adaptive_unicast_frames", source)
        self.assertIn("adaptive_redundant_frames", source)
        self.assertIn("fleet_plan_frames", source)
        self.assertIn("fleet_plan_redundant_frames", source)
        self.assertIn("fleet_plan_selected_path_count", source)
        self.assertIn("rmw_fleetqox_cpp_socket_fleet_plan_last_paths", source)
        self.assertIn("repair_plan_selected_path_count", source)
        self.assertIn("rmw_fleetqox_cpp_socket_repair_plan_last_paths", source)
        self.assertIn("rmw_fleetqox_cpp_socket_repair_budget_exhausted", source)
        self.assertIn("rmw_fleetqox_cpp_socket_repair_requests_coalesced", source)
        self.assertIn(
            "rmw_fleetqox_cpp_socket_repair_sequence_attempt_limit_exhausted",
            source,
        )
        self.assertIn("rmw_fleetqox_cpp_socket_repair_not_admitted", source)
        self.assertIn("adaptive_peer_score_sum", source)
        self.assertIn("adaptive_selected_peer_index", source)
        self.assertIn("rmw_fleetqox_cpp_socket_peer_policy", source)
        self.assertIn("send_data_frame", source)
        self.assertIn("rmw_fleetqox_cpp_socket_nack_retransmissions", source)
        self.assertIn("ReliableRetransmitEntry", source)
        self.assertIn("FLEETQOX_RMW_RELIABLE_ACK_TIMEOUT_MS", source)
        self.assertIn("FLEETQOX_RMW_RELIABLE_MAX_RETRANSMISSIONS", source)
        self.assertIn("FLEETQOX_RMW_GRAPH_RENEW_INTERVAL_MS", source)
        self.assertIn("reliable_retransmit_loop", source)
        self.assertIn("rmw_fleetqox_cpp_socket_reliable_timeout_retransmissions", source)
        self.assertIn("rmw_subscription_set_on_new_message_callback", source)
        self.assertIn("on_new_message_callback", source)
        self.assertIn("rmw_fleetqox_cpp_waitable_subscription_has_data", source)
        self.assertIn("make_endpoint_gid", source)
        self.assertIn("endpoint_gid", source)
        self.assertIn("graph_qos_from_rmw", source)
        self.assertIn("rmw_fleetqox_cpp_send_graph_advertisement", source)
        self.assertIn("rmw_fleetqox_cpp_send_encoded_frame", source)
        router_source = (PKG / "src" / "udp_router_probe.cpp").read_text()
        self.assertIn("fleetrmw.router_path_telemetry.v1", router_source)
        self.assertIn("--path-id", router_source)
        self.assertIn("--telemetry-file", router_source)
        self.assertIn("--telemetry-latency-ms", router_source)
        self.assertIn("--telemetry-deadline-miss-ratio", router_source)
        self.assertIn("expected_ack_nack_forwarded", router_source)
        self.assertIn("--expected-ack-nack-forwarded", router_source)
        self.assertIn("drop_topic_prefix", router_source)
        self.assertIn("--drop-topic-prefix", router_source)
        self.assertIn("scheduler_fresh_deadline_misses", router_source)
        self.assertIn("scheduler_repair_deadline_misses", router_source)
        self.assertIn("scheduler_deadline_miss_frames", router_source)
        self.assertIn("append_router_path_telemetry", router_source)
        self.assertIn("rmw_fleetqox_cpp_handle_service_frame", source)
        self.assertIn("rmw_fleetqox_cpp_serialize_introspection_message", source)
        self.assertIn("frame_exceeds_lifespan", source)
        self.assertIn("enforce_subscription_depth_locked", source)
        self.assertIn("qos.lifespan", source)
        self.assertIn("RMW_QOS_POLICY_HISTORY_KEEP_LAST", source)
        typed_probe = PKG / "src" / "typed_pubsub_probe.cpp"
        self.assertTrue(typed_probe.exists())
        typed_probe_source = typed_probe.read_text()
        self.assertIn("fleetrmw.rmw_typed_pubsub_probe.v1", typed_probe_source)
        self.assertIn("rmw_publish(publisher", typed_probe_source)
        self.assertIn("rmw_take(subscription", typed_probe_source)
        std_msgs_probe = PKG / "src" / "std_msgs_string_probe.cpp"
        self.assertTrue(std_msgs_probe.exists())
        std_msgs_probe_source = std_msgs_probe.read_text()
        self.assertIn("fleetrmw.rmw_std_msgs_string_probe.v1", std_msgs_probe_source)
        self.assertIn("rmw_serialize(&outgoing", std_msgs_probe_source)
        self.assertIn("rmw_deserialize(&standalone", std_msgs_probe_source)
        self.assertIn("standalone_serialization", std_msgs_probe_source)
        self.assertIn("std_msgs__msg__String", std_msgs_probe_source)
        twist_probe = PKG / "src" / "geometry_twist_probe.cpp"
        self.assertTrue(twist_probe.exists())
        twist_probe_source = twist_probe.read_text()
        self.assertIn("fleetrmw.rmw_geometry_twist_probe.v1", twist_probe_source)
        self.assertIn("geometry_msgs__msg__Twist", twist_probe_source)
        rcl_probe = PKG / "src" / "rcl_string_probe.cpp"
        self.assertTrue(rcl_probe.exists())
        rcl_probe_source = rcl_probe.read_text()
        self.assertIn("fleetrmw.rcl_string_probe.v1", rcl_probe_source)
        self.assertIn("RMW_IMPLEMENTATION", rcl_probe_source)
        rcl_talker = PKG / "src" / "rcl_graph_talker.cpp"
        self.assertTrue(rcl_talker.exists())
        rcl_talker_source = rcl_talker.read_text()
        self.assertIn("fleetrmw.rcl_graph_talker.v1", rcl_talker_source)
        self.assertIn("rcl_publisher_init", rcl_talker_source)
        self.assertIn("std_msgs/msg/String", rcl_talker_source)
        rcl_service_node = PKG / "src" / "rcl_service_node.cpp"
        self.assertTrue(rcl_service_node.exists())
        rcl_service_node_source = rcl_service_node.read_text()
        self.assertIn("fleetrmw.rcl_service_node.v1", rcl_service_node_source)
        self.assertIn("rcl_service_init", rcl_service_node_source)
        self.assertIn("rcl_take_request", rcl_service_node_source)
        self.assertIn("rcl_send_response", rcl_service_node_source)
        self.assertIn("--response-delay-ms", rcl_service_node_source)
        self.assertIn("response_delay_ms", rcl_service_node_source)
        self.assertIn("std_srvs/srv/SetBool", rcl_service_node_source)
        graph_source = (PKG / "src" / "rmw_graph.cpp").read_text()
        self.assertIn("purge_expired_remote_graph_locked", graph_source)
        self.assertIn("g_remote_graph_endpoints", graph_source)
        self.assertIn("g_local_graph_endpoints", graph_source)
        self.assertIn("rmw_get_publishers_info_by_topic", graph_source)
        self.assertIn("rmw_get_subscriptions_info_by_topic", graph_source)
        self.assertIn("rmw_get_publisher_names_and_types_by_node", graph_source)
        self.assertIn("rmw_get_subscriber_names_and_types_by_node", graph_source)
        self.assertIn("g_remote_service_endpoints", graph_source)
        self.assertIn("rmw_get_service_names_and_types", graph_source)
        self.assertIn("rmw_get_service_names_and_types_by_node", graph_source)
        self.assertIn("rmw_get_client_names_and_types_by_node", graph_source)
        self.assertIn("rmw_count_services", graph_source)
        self.assertIn("rmw_count_clients", graph_source)
        self.assertIn("rmw_fleetqox_cpp_graph_service_count", graph_source)
        self.assertIn("rmw_fleetqox_cpp_graph_publisher_count", graph_source)
        self.assertIn("rmw_fleetqox_cpp_graph_subscription_count", graph_source)
        self.assertIn("rmw_topic_endpoint_info_set_qos_profile", graph_source)
        pubsub_source = (PKG / "src" / "rmw_pubsub.cpp").read_text()
        self.assertIn("rmw_publisher_count_matched_subscriptions", pubsub_source)
        self.assertIn("rmw_subscription_count_matched_publishers", pubsub_source)
        self.assertIn("rmw_fleetqox_cpp_graph_publisher_count", pubsub_source)
        self.assertIn("rmw_fleetqox_cpp_graph_subscription_count", pubsub_source)
        stub_source = (PKG / "src" / "rmw_stubs.cpp").read_text()
        self.assertIn("rmw_init_publisher_allocation", stub_source)
        self.assertIn("rmw_create_client", stub_source)
        self.assertIn("rmw_create_service", stub_source)
        self.assertIn("service_type_name_from_type_support", stub_source)
        self.assertIn("service_graph_renewal_loop", stub_source)
        self.assertIn("rmw_send_request", stub_source)
        self.assertIn("rmw_take_request", stub_source)
        self.assertIn("rmw_send_response", stub_source)
        self.assertIn("rmw_take_response", stub_source)
        self.assertIn("rmw_fleetqox_cpp_handle_service_frame", stub_source)
        self.assertIn("rmw_fleetqox_cpp_service_expired_frames_dropped", stub_source)
        self.assertIn("rmw_fleetqox_cpp_service_endpoint_id", stub_source)
        self.assertIn("rmw_fleetqox_cpp_client_endpoint_id", stub_source)
        self.assertIn("drop_if_expired_service_frame", stub_source)
        self.assertIn("service_frame_expired(frame, monotonic_timestamp_ns())", stub_source)
        self.assertIn("qos_duration_ns(data->qos.lifespan)", stub_source)
        self.assertIn("frame = rmw_fleetqox_cpp::ServiceFrame{};", stub_source)
        self.assertIn("response_queue", stub_source)
        self.assertIn("request_queue", stub_source)
        self.assertIn("rmw_fleetqox_cpp_graph_register_service_endpoint", stub_source)
        self.assertIn("rmw_fleetqox_cpp_graph_register_client_endpoint", stub_source)
        self.assertIn("rmw_fleetqox_cpp_graph_service_count", stub_source)
        self.assertIn("rmw_qos_profile_check_compatible", stub_source)
        self.assertIn("rmw_take_dynamic_message", stub_source)
        self.assertIn("rmw_serialization_support_init", stub_source)
        self.assertIn("RMW_RET_UNSUPPORTED", stub_source)
        self.assertTrue((PKG / "src" / "interprocess_pubsub_probe.cpp").exists())
        remote_graph_probe = PKG / "src" / "remote_graph_probe.cpp"
        self.assertTrue(remote_graph_probe.exists())
        remote_graph_source = remote_graph_probe.read_text()
        self.assertIn("fleetrmw.rmw_remote_graph_probe.v1", remote_graph_source)
        self.assertIn("rmw_get_topic_names_and_types", remote_graph_source)
        self.assertIn("rmw_count_publishers", remote_graph_source)
        self.assertIn("rmw_count_subscribers", remote_graph_source)
        remote_graph_lease_probe = PKG / "src" / "remote_graph_lease_probe.cpp"
        self.assertTrue(remote_graph_lease_probe.exists())
        remote_graph_lease_source = remote_graph_lease_probe.read_text()
        self.assertIn("fleetrmw.rmw_remote_graph_lease_probe.v1", remote_graph_lease_source)
        self.assertIn("publisher_count_after", remote_graph_lease_source)
        router = (PKG / "src" / "udp_router_probe.cpp").read_text()
        self.assertIn("fleetrmw.rmw_udp_router_probe.v1", router)
        self.assertIn("expected_route_advertisements", router)
        self.assertIn("expected_graph_advertisements", router)
        self.assertIn("expected_service_frames", router)
        self.assertIn("expected_ack_nack_frames", router)
        self.assertIn("expected_qos_drops", router)
        self.assertIn("ack_nack_forwarded", router)
        self.assertIn("decode_ack_nack", router)
        self.assertIn("drop_source_sequences", router)
        self.assertIn("forward_delay_ms", router)
        self.assertIn("scheduler_window_ms", router)
        self.assertIn("scheduler_expected_frames", router)
        self.assertIn("scheduler_topic_prefix", router)
        self.assertIn("scheduler_batch_ready", router)
        self.assertIn("qos_dropped_frames", router)
        self.assertIn("qos_dropped_topic_counts", router)
        self.assertIn("increment_topic_count", router)
        self.assertIn("forwarded_topics", router)
        self.assertIn("frame_exceeds_learned_lifespan", router)
        self.assertIn("absolute_deadline_ns_for_frame", router)
        self.assertIn("decode_service_frame", router)
        self.assertIn("service_forwarded", router)
        self.assertIn("graph_services", router)
        self.assertIn("graph_clients", router)
        self.assertIn("graph_peer_count", router)
        self.assertIn("graph_forwarded", router)
        self.assertIn("purge_expired_routes", router)
        self.assertIn("decode_route_advertisement", router)
        self.assertIn("decode_graph_advertisement", router)
        self.assertIn("getaddrinfo", router)
        self.assertIn("decode_data_frame(encoded_frame)", router)
        self.assertIn("sendto(", router)
        interprocess_probe = (PKG / "src" / "interprocess_pubsub_probe.cpp").read_text()
        self.assertIn("expect_taken", interprocess_probe)
        self.assertIn("lifespan_ms", interprocess_probe)
        self.assertIn("deadline_ms", interprocess_probe)
        probe = (PKG / "src" / "serialized_pubsub_probe.cpp").read_text()
        self.assertIn('socket_backed', probe)
        self.assertIn("socket_frames_sent >= 1", probe)
        self.assertIn("socket_frames_received >= 1", probe)
        qos_probe = PKG / "src" / "qos_probe.cpp"
        self.assertTrue(qos_probe.exists())
        qos_probe_source = qos_probe.read_text()
        self.assertIn("fleetrmw.rmw_qos_probe.v1", qos_probe_source)
        self.assertIn("RMW_QOS_POLICY_HISTORY_KEEP_LAST", qos_probe_source)
        self.assertIn("lifespan_qos.lifespan.nsec", qos_probe_source)
        self.assertIn("depth_received == \"second\"", qos_probe_source)
        reliability_probe = PKG / "src" / "reliability_probe.cpp"
        self.assertTrue(reliability_probe.exists())
        reliability_probe_source = reliability_probe.read_text()
        self.assertIn("fleetrmw.rmw_reliability_probe.v1", reliability_probe_source)
        self.assertIn("rmw_fleetqox_cpp_socket_test_dropped_frames", reliability_probe_source)
        self.assertIn("rmw_fleetqox_cpp_socket_nack_retransmissions", reliability_probe_source)
        self.assertIn("\"one\"", reliability_probe_source)
        self.assertIn("\"two\"", reliability_probe_source)
        self.assertIn("\"three\"", reliability_probe_source)
        reliable_interprocess_probe = PKG / "src" / "reliable_interprocess_probe.cpp"
        self.assertTrue(reliable_interprocess_probe.exists())
        reliable_interprocess_source = reliable_interprocess_probe.read_text()
        self.assertIn("fleetrmw.rmw_reliable_interprocess_probe.v1", reliable_interprocess_source)
        self.assertIn("rmw_fleetqox_cpp_socket_ack_nack_received", reliable_interprocess_source)
        self.assertIn("rmw_fleetqox_cpp_socket_nack_retransmissions", reliable_interprocess_source)
        self.assertIn("min_ack_nack_received", reliable_interprocess_source)
        self.assertIn("min_ack_nack_sent", reliable_interprocess_source)
        self.assertIn("min_retransmissions", reliable_interprocess_source)
        self.assertIn("deadline_ms", reliable_interprocess_source)
        self.assertIn("pre_publish_wait_ms", reliable_interprocess_source)
        self.assertIn("pre_payload_warmup_count", reliable_interprocess_source)
        self.assertIn("pre_payload_warmup_ack_count", reliable_interprocess_source)
        self.assertIn("pre_payload_warmup_ack_timeout_ms", reliable_interprocess_source)
        self.assertIn("app_repair_cycle_count", reliable_interprocess_source)
        self.assertIn("tail_repair_repeat_count", reliable_interprocess_source)
        self.assertIn("publish_interval_ms", reliable_interprocess_source)
        self.assertIn("--payload-sequence", reliable_interprocess_source)
        self.assertIn("split_payloads(config.payload_sequence)", reliable_interprocess_source)
        self.assertIn("--pre-publish-wait-ms", reliable_interprocess_source)
        self.assertIn("--pre-payload-warmup-count", reliable_interprocess_source)
        self.assertIn("--pre-payload-warmup-payload", reliable_interprocess_source)
        self.assertIn("--pre-payload-warmup-ack-count", reliable_interprocess_source)
        self.assertIn("--pre-payload-warmup-ack-timeout-ms", reliable_interprocess_source)
        self.assertIn("--app-repair-cycle-count", reliable_interprocess_source)
        self.assertIn("--app-repair-cycle-payloads", reliable_interprocess_source)
        self.assertIn("--tail-repair-repeat-count", reliable_interprocess_source)
        self.assertIn("--tail-repair-payload", reliable_interprocess_source)
        self.assertIn("--publish-interval-ms", reliable_interprocess_source)
        self.assertIn("plan_update_after_publishes", reliable_interprocess_source)
        self.assertIn("--plan-update-after-publishes", reliable_interprocess_source)
        self.assertIn("--plan-update-text", reliable_interprocess_source)
        self.assertIn("FLEETQOX_RMW_FLEET_PATH_PLAN_FILE", reliable_interprocess_source)
        self.assertIn("fleetrmw.subscriber_delivery_telemetry.v1", reliable_interprocess_source)
        self.assertIn("--subscriber-telemetry-file", reliable_interprocess_source)
        self.assertIn("--subscriber-deadline-ms", reliable_interprocess_source)
        self.assertIn("append_subscriber_telemetry", reliable_interprocess_source)
        self.assertIn("duplicate_data_frames_deduped", reliable_interprocess_source)
        self.assertIn("ack_nack_duplicate_received", reliable_interprocess_source)
        self.assertIn("idle_repair_ack_nack_sent", reliable_interprocess_source)
        self.assertIn("post_recovery_payload", reliable_interprocess_source)
        self.assertIn("post_recovery_before_hold", reliable_interprocess_source)
        self.assertIn("post_payload_wait_ms", reliable_interprocess_source)
        self.assertIn("--post-recovery-before-hold", reliable_interprocess_source)
        self.assertIn("--post-recovery-repeat-count", reliable_interprocess_source)
        self.assertIn("--post-payload-wait-ms", reliable_interprocess_source)
        self.assertIn("--require-post-recovery-payload", reliable_interprocess_source)
        self.assertIn("publish_payload_once", reliable_interprocess_source)
        self.assertIn("required_payloads", reliable_interprocess_source)
        self.assertIn("rmw_fleetqox_cpp_socket_adaptive_failovers", reliable_interprocess_source)
        self.assertIn("rmw_fleetqox_cpp_socket_adaptive_unicast_frames", reliable_interprocess_source)
        self.assertIn("rmw_fleetqox_cpp_socket_adaptive_redundant_frames", reliable_interprocess_source)
        self.assertIn("rmw_fleetqox_cpp_socket_adaptive_peer_score_sum", reliable_interprocess_source)
        self.assertIn("rmw_fleetqox_cpp_socket_adaptive_selected_peer_index", reliable_interprocess_source)
        self.assertIn("rmw_fleetqox_cpp_socket_fleet_plan_frames", reliable_interprocess_source)
        self.assertIn("rmw_fleetqox_cpp_socket_fleet_plan_redundant_frames", reliable_interprocess_source)
        self.assertIn("rmw_fleetqox_cpp_socket_fleet_plan_selected_path_count", reliable_interprocess_source)
        self.assertIn("fleet_plan_last_paths", reliable_interprocess_source)
        self.assertIn("repair_plan_frames", reliable_interprocess_source)
        self.assertIn("repair_plan_selected_path_count", reliable_interprocess_source)
        self.assertIn("repair_retransmission_budget", reliable_interprocess_source)
        self.assertIn("repair_budget_exhausted", reliable_interprocess_source)
        self.assertIn("repair_requests_coalesced", reliable_interprocess_source)
        self.assertIn(
            "repair_sequence_attempt_limit_exhausted",
            reliable_interprocess_source,
        )
        self.assertIn("repair_not_admitted", reliable_interprocess_source)
        self.assertIn("reliable_timeout_retransmissions", reliable_interprocess_source)
        self.assertIn("peer_policy", reliable_interprocess_source)
        docker_router_script = ROOT / "scripts" / "run_rmw_docker_multicontainer_router_probe.py"
        self.assertTrue(docker_router_script.exists())
        docker_router_source = docker_router_script.read_text()
        self.assertIn("fleetrmw.rmw_multicontainer_router_probe.v1", docker_router_source)
        self.assertIn("fleetrmw_udp_router_probe", docker_router_source)
        self.assertIn("fleetrmw_remote_graph_probe", docker_router_source)
        self.assertIn("expected-route-advertisements", docker_router_source)
        self.assertIn("expected-graph-advertisements", docker_router_source)
        self.assertIn("graph-peers", docker_router_source)
        self.assertIn("observer", docker_router_source)
        udp_router_probe = PKG / "src" / "udp_router_probe.cpp"
        udp_router_source = udp_router_probe.read_text()
        self.assertIn("--expected-forwarded-topic-source-sequences", udp_router_source)
        self.assertIn("--post-satisfaction-ms", udp_router_source)
        self.assertIn("topic_source_sequence_expectations_satisfied", udp_router_source)
        docker_topic_list_script = ROOT / "scripts" / "run_rmw_docker_ros2_topic_list_probe.py"
        self.assertTrue(docker_topic_list_script.exists())
        docker_topic_list_source = docker_topic_list_script.read_text()
        self.assertIn("fleetrmw.rmw_ros2_topic_list_probe.v1", docker_topic_list_source)
        self.assertIn("ros2 topic list --no-daemon", docker_topic_list_source)
        self.assertIn("fleetrmw_rcl_graph_talker", docker_topic_list_source)
        docker_pub_echo_script = ROOT / "scripts" / "run_rmw_docker_ros2_pub_echo_probe.py"
        self.assertTrue(docker_pub_echo_script.exists())
        docker_pub_echo_source = docker_pub_echo_script.read_text()
        self.assertIn("fleetrmw.rmw_ros2_pub_echo_probe.v1", docker_pub_echo_source)
        self.assertIn("ros2 topic echo --no-daemon", docker_pub_echo_source)
        self.assertIn("ros2 topic pub --times 3", docker_pub_echo_source)
        docker_topic_info_script = ROOT / "scripts" / "run_rmw_docker_ros2_topic_info_probe.py"
        self.assertTrue(docker_topic_info_script.exists())
        docker_topic_info_source = docker_topic_info_script.read_text()
        self.assertIn("fleetrmw.rmw_ros2_topic_info_probe.v1", docker_topic_info_source)
        self.assertIn("ros2 topic info --no-daemon", docker_topic_info_source)
        self.assertIn("--verbose", docker_topic_info_source)
        self.assertIn("Endpoint type: PUBLISHER", docker_topic_info_source)
        docker_cli_matrix_script = ROOT / "scripts" / "run_rmw_docker_ros2_cli_message_matrix.py"
        self.assertTrue(docker_cli_matrix_script.exists())
        docker_cli_matrix_source = docker_cli_matrix_script.read_text()
        self.assertIn("fleetrmw.rmw_ros2_cli_message_matrix.v1", docker_cli_matrix_source)
        self.assertIn("builtin_interfaces/msg/Time", docker_cli_matrix_source)
        self.assertIn("builtin_interfaces/msg/Duration", docker_cli_matrix_source)
        self.assertIn("geometry_msgs/msg/PoseStamped", docker_cli_matrix_source)
        self.assertIn("sensor_msgs/msg/LaserScan", docker_cli_matrix_source)
        self.assertIn("nav_msgs/msg/Odometry", docker_cli_matrix_source)
        self.assertIn("nav_msgs/msg/Path", docker_cli_matrix_source)
        self.assertIn("ros2\", \"topic\", \"echo", docker_cli_matrix_source)
        docker_node_info_script = ROOT / "scripts" / "run_rmw_docker_ros2_node_info_probe.py"
        self.assertTrue(docker_node_info_script.exists())
        docker_node_info_source = docker_node_info_script.read_text()
        self.assertIn("fleetrmw.rmw_ros2_node_info_probe.v1", docker_node_info_source)
        self.assertIn("ros2 node list --no-daemon", docker_node_info_source)
        self.assertIn("ros2 node info --no-daemon", docker_node_info_source)
        rcl_service_node_source = (PKG / "src" / "rcl_service_node.cpp").read_text()
        self.assertIn("rmw_fleetqox_cpp_send_malformed_response", rcl_service_node_source)
        self.assertIn("--malformed-response", rcl_service_node_source)
        self.assertIn("--exit-after-request", rcl_service_node_source)
        docker_service_graph_script = ROOT / "scripts" / "run_rmw_docker_ros2_service_graph_probe.py"
        self.assertTrue(docker_service_graph_script.exists())
        docker_service_graph_source = docker_service_graph_script.read_text()
        self.assertIn("fleetrmw.rmw_ros2_service_graph_probe.v1", docker_service_graph_source)
        self.assertIn("ros2 service list --no-daemon", docker_service_graph_source)
        self.assertIn("ros2 node info --no-daemon", docker_service_graph_source)
        self.assertIn("fleetrmw_rcl_service_node", docker_service_graph_source)
        docker_service_call_script = ROOT / "scripts" / "run_rmw_docker_ros2_service_call_probe.py"
        self.assertTrue(docker_service_call_script.exists())
        docker_service_call_source = docker_service_call_script.read_text()
        self.assertIn("fleetrmw.rmw_ros2_service_call_probe.v1", docker_service_call_source)
        self.assertIn("ros2 service call", docker_service_call_source)
        self.assertIn("fleetqox set_bool accepted", docker_service_call_source)
        docker_service_timeout_script = ROOT / "scripts" / "run_rmw_docker_ros2_service_timeout_probe.py"
        self.assertTrue(docker_service_timeout_script.exists())
        docker_service_timeout_source = docker_service_timeout_script.read_text()
        self.assertIn("fleetrmw.rmw_ros2_service_timeout_probe.v1", docker_service_timeout_source)
        self.assertIn("--response-delay-ms", docker_service_timeout_source)
        self.assertIn("service_call_returncode", docker_service_timeout_source)
        self.assertIn("timed_out", docker_service_timeout_source)
        self.assertIn("server_saw_request", docker_service_timeout_source)
        malformed_service_script = (
            ROOT / "scripts" / "run_rmw_docker_router_ros2_malformed_service_response_probe.py"
        )
        self.assertTrue(malformed_service_script.exists())
        malformed_service_source = malformed_service_script.read_text()
        self.assertIn(
            "fleetrmw.rmw_router_ros2_malformed_service_response_probe.v1",
            malformed_service_source,
        )
        self.assertIn("--malformed-response", malformed_service_source)
        self.assertIn("diagnostic_observed", malformed_service_source)
        self.assertIn("client_failed_cleanly", malformed_service_source)
        docker_router_service_call_script = ROOT / "scripts" / "run_rmw_docker_router_service_call_probe.py"
        self.assertTrue(docker_router_service_call_script.exists())
        docker_router_service_call_source = docker_router_service_call_script.read_text()
        self.assertIn("fleetrmw.rmw_router_service_call_probe.v1", docker_router_service_call_source)
        self.assertIn("expected-service-frames", docker_router_service_call_source)
        self.assertIn("ros2 service call", docker_router_service_call_source)
        docker_qos_script = ROOT / "scripts" / "run_rmw_docker_qos_probe.py"
        self.assertTrue(docker_qos_script.exists())
        docker_qos_source = docker_qos_script.read_text()
        self.assertIn("fleetrmw.rmw_docker_qos_probe.v1", docker_qos_source)
        self.assertIn("fleetrmw_qos_probe", docker_qos_source)
        self.assertIn("depth_received", docker_qos_source)
        self.assertIn("lifespan_taken", docker_qos_source)
        service_qos_probe = PKG / "src" / "service_qos_probe.cpp"
        self.assertTrue(service_qos_probe.exists())
        service_qos_source = service_qos_probe.read_text()
        self.assertIn("fleetrmw.rmw_service_qos_probe.v1", service_qos_source)
        self.assertIn("rmw_send_request", service_qos_source)
        self.assertIn("rmw_take_request", service_qos_source)
        self.assertIn("rmw_send_response", service_qos_source)
        self.assertIn("rmw_take_response", service_qos_source)
        self.assertIn("rmw_fleetqox_cpp_service_expired_frames_dropped", service_qos_source)
        self.assertIn("stale_request_taken", service_qos_source)
        self.assertIn("stale_response_taken", service_qos_source)
        self.assertIn("unknown_response_error", service_qos_source)
        self.assertIn("unknown_response_sent_delta", service_qos_source)
        docker_service_qos_script = ROOT / "scripts" / "run_rmw_docker_service_qos_probe.py"
        self.assertTrue(docker_service_qos_script.exists())
        docker_service_qos_source = docker_service_qos_script.read_text()
        self.assertIn("fleetrmw.rmw_docker_service_qos_probe.v1", docker_service_qos_source)
        self.assertIn("fleetrmw_service_qos_probe", docker_service_qos_source)
        self.assertIn("expired_frames_dropped_delta", docker_service_qos_source)
        self.assertIn("unknown_response_error", docker_service_qos_source)
        service_error_probe = PKG / "src" / "service_error_probe.cpp"
        self.assertTrue(service_error_probe.exists())
        service_error_source = service_error_probe.read_text()
        self.assertIn("fleetrmw.rmw_service_error_probe.v1", service_error_source)
        self.assertIn("rmw_fleetqox_cpp_handle_service_frame", service_error_source)
        self.assertIn("rmw_fleetqox_cpp_client_endpoint_id", service_error_source)
        self.assertIn("empty_response_taken", service_error_source)
        self.assertIn("malformed_response_error", service_error_source)
        self.assertIn("invalid_frame_rejected", service_error_source)
        docker_service_error_script = ROOT / "scripts" / "run_rmw_docker_service_error_probe.py"
        self.assertTrue(docker_service_error_script.exists())
        docker_service_error_source = docker_service_error_script.read_text()
        self.assertIn("fleetrmw.rmw_docker_service_error_probe.v1", docker_service_error_source)
        self.assertIn("fleetrmw_service_error_probe", docker_service_error_source)
        self.assertIn("malformed_response_error", docker_service_error_source)
        self.assertIn("after_invalid_response_taken", docker_service_error_source)
        action_probe = PKG / "src" / "action_frame_probe.cpp"
        self.assertTrue(action_probe.exists())
        action_probe_source = action_probe.read_text()
        self.assertIn("fleetrmw.rmw_action_frame_probe.v1", action_probe_source)
        self.assertIn("encode_action_frame", action_probe_source)
        self.assertIn("decode_action_frame", action_probe_source)
        self.assertIn("goal\", \"feedback\", \"status\", \"result\", \"cancel", action_probe_source)
        self.assertIn("action_frame_expired", action_probe_source)
        self.assertIn("rejects_service_schema", action_probe_source)
        docker_action_script = ROOT / "scripts" / "run_rmw_docker_action_frame_probe.py"
        self.assertTrue(docker_action_script.exists())
        docker_action_source = docker_action_script.read_text()
        self.assertIn("fleetrmw.rmw_docker_action_frame_probe.v1", docker_action_source)
        self.assertIn("fleetrmw_action_frame_probe", docker_action_source)
        self.assertIn("expected_roles", docker_action_source)
        self.assertIn("rejects_service_schema", docker_action_source)
        action_router_probe = PKG / "src" / "action_router_probe.cpp"
        self.assertTrue(action_router_probe.exists())
        action_router_probe_source = action_router_probe.read_text()
        self.assertIn("fleetrmw.rmw_action_router_probe.v1", action_router_probe_source)
        self.assertIn("action_server", action_router_probe_source)
        self.assertIn("action_client", action_router_probe_source)
        self.assertIn("server_received_roles", action_router_probe_source)
        self.assertIn("client_received_roles", action_router_probe_source)
        docker_action_router_script = ROOT / "scripts" / "run_rmw_docker_router_action_frame_probe.py"
        self.assertTrue(docker_action_router_script.exists())
        docker_action_router_source = docker_action_router_script.read_text()
        self.assertIn("fleetrmw.rmw_docker_router_action_frame_probe.v1", docker_action_router_source)
        self.assertIn("fleetrmw_action_router_probe", docker_action_router_source)
        self.assertIn("expected-action-frames", docker_action_router_source)
        self.assertIn("action_forwarded", docker_action_router_source)
        udp_router_source = (PKG / "src" / "udp_router_probe.cpp").read_text()
        self.assertIn("expected_action_frames", udp_router_source)
        self.assertIn("decode_action_frame", udp_router_source)
        self.assertIn("ActionRoute", udp_router_source)
        self.assertIn("graph_action_servers", udp_router_source)
        self.assertIn("graph_action_clients", udp_router_source)
        self.assertIn("action_forwarded", udp_router_source)
        cmake_source = (PKG / "CMakeLists.txt").read_text()
        self.assertIn("fleetrmw_action_router_probe", cmake_source)
        docker_rclpy_action_script = ROOT / "scripts" / "run_rmw_docker_rclpy_action_probe.py"
        self.assertTrue(docker_rclpy_action_script.exists())
        docker_rclpy_action_source = docker_rclpy_action_script.read_text()
        self.assertIn("fleetrmw.rmw_docker_rclpy_action_probe.v1", docker_rclpy_action_source)
        self.assertIn("ActionServer", docker_rclpy_action_source)
        self.assertIn("ActionClient", docker_rclpy_action_source)
        self.assertIn("LookupTransform", docker_rclpy_action_source)
        self.assertIn("spin_until", docker_rclpy_action_source)
        self.assertIn("result_status", docker_rclpy_action_source)
        self.assertIn("result_child_frame", docker_rclpy_action_source)
        docker_router_rclpy_action_script = ROOT / "scripts" / "run_rmw_docker_router_rclpy_action_probe.py"
        self.assertTrue(docker_router_rclpy_action_script.exists())
        docker_router_rclpy_action_source = docker_router_rclpy_action_script.read_text()
        self.assertIn("fleetrmw.rmw_docker_router_rclpy_action_probe.v1", docker_router_rclpy_action_source)
        self.assertIn("ActionServer", docker_router_rclpy_action_source)
        self.assertIn("ActionClient", docker_router_rclpy_action_source)
        self.assertIn("expected-service-frames 10", docker_router_rclpy_action_source)
        self.assertIn("service_forwarded", docker_router_rclpy_action_source)
        self.assertIn("graph_services", docker_router_rclpy_action_source)
        self.assertIn("graph_clients", docker_router_rclpy_action_source)
        self.assertIn("available_before_send", docker_router_rclpy_action_source)
        self.assertIn("available_after_result", docker_router_rclpy_action_source)
        self.assertIn("status_subscribers", docker_router_rclpy_action_source)
        self.assertIn("feedback_subscribers", docker_router_rclpy_action_source)
        self.assertIn("feedback_callbacks", docker_router_rclpy_action_source)
        self.assertIn("cancel_goal_async", docker_router_rclpy_action_source)
        self.assertIn("cancel_result_status", docker_router_rclpy_action_source)
        self.assertIn("GoalStatusArray", docker_router_rclpy_action_source)
        self.assertIn("status_observed", docker_router_rclpy_action_source)
        self.assertIn("feedback_pub_qos_profile", docker_router_rclpy_action_source)
        self.assertIn("status_pub_qos_profile", docker_router_rclpy_action_source)
        self.assertIn("feedback_lifespan_ms", docker_router_rclpy_action_source)
        self.assertIn("feedback_deadline_ms", docker_router_rclpy_action_source)
        self.assertIn("scheduler_window_ms", docker_router_rclpy_action_source)
        self.assertIn("scheduler-expected-frames", docker_router_rclpy_action_source)
        self.assertIn("scheduler-topic-prefix", docker_router_rclpy_action_source)
        self.assertIn("expected_data_frames", docker_router_rclpy_action_source)
        docker_router_rclpy_action_qos_script = (
            ROOT / "scripts" / "run_rmw_docker_router_rclpy_action_qos_probe.py"
        )
        self.assertTrue(docker_router_rclpy_action_qos_script.exists())
        docker_router_rclpy_action_qos_source = docker_router_rclpy_action_qos_script.read_text()
        self.assertIn(
            "fleetrmw.rmw_docker_router_rclpy_action_qos_probe.v1",
            docker_router_rclpy_action_qos_source,
        )
        self.assertIn("expired_observation", docker_router_rclpy_action_qos_source)
        self.assertIn("deadline_priority", docker_router_rclpy_action_qos_source)
        self.assertIn("qos_dropped_topic_counts", docker_router_rclpy_action_qos_source)
        self.assertIn("drop_topics_verified", docker_router_rclpy_action_qos_source)
        self.assertIn("deadline_order_verified", docker_router_rclpy_action_qos_source)
        docker_reliability_script = ROOT / "scripts" / "run_rmw_docker_reliability_probe.py"
        self.assertTrue(docker_reliability_script.exists())
        docker_reliability_source = docker_reliability_script.read_text()
        self.assertIn("fleetrmw.rmw_docker_reliability_probe.v1", docker_reliability_source)
        self.assertIn("FLEETQOX_RMW_DROP_SOURCE_SEQUENCES=2", docker_reliability_source)
        self.assertIn("fleetrmw_reliability_probe", docker_reliability_source)
        self.assertIn("nack_retransmissions", docker_reliability_source)
        docker_router_reliability_script = ROOT / "scripts" / "run_rmw_docker_router_reliability_probe.py"
        self.assertTrue(docker_router_reliability_script.exists())
        docker_router_reliability_source = docker_router_reliability_script.read_text()
        self.assertIn("fleetrmw.rmw_router_reliability_probe.v1", docker_router_reliability_source)
        self.assertIn("expected-ack-nack-frames", docker_router_reliability_source)
        self.assertIn("drop-source-sequences", docker_router_reliability_source)
        self.assertIn("ack_nack_forwarded", docker_router_reliability_source)
        docker_router_scheduled_reliability_script = (
            ROOT / "scripts" / "run_rmw_docker_router_scheduled_reliability_probe.py"
        )
        self.assertTrue(docker_router_scheduled_reliability_script.exists())
        docker_router_scheduled_reliability_source = (
            docker_router_scheduled_reliability_script.read_text()
        )
        self.assertIn(
            "fleetrmw.rmw_router_scheduled_reliability_probe.v1",
            docker_router_scheduled_reliability_source,
        )
        self.assertIn("--scheduler-window-ms 150", docker_router_scheduled_reliability_source)
        self.assertIn("--scheduler-expected-frames 2", docker_router_scheduled_reliability_source)
        self.assertIn("--drop-source-sequences 2", docker_router_scheduled_reliability_source)
        self.assertIn("scheduler_forwarded_frames", docker_router_scheduled_reliability_source)
        self.assertIn("nack_retransmissions", docker_router_scheduled_reliability_source)
        self.assertIn("NETEM_PROFILES", docker_router_scheduled_reliability_source)
        self.assertIn("netem_loss_percent", docker_router_scheduled_reliability_source)
        self.assertIn("netem_qdisc", docker_router_scheduled_reliability_source)
        self.assertIn('"--cap-add", "NET_ADMIN"', docker_router_scheduled_reliability_source)
        self.assertIn("post_satisfaction_ms", docker_router_scheduled_reliability_source)
        docker_router_scheduled_repeated_loss_script = (
            ROOT
            / "scripts"
            / "run_rmw_docker_router_scheduled_reliability_repeated_loss_matrix.py"
        )
        self.assertTrue(docker_router_scheduled_repeated_loss_script.exists())
        docker_router_scheduled_repeated_loss_source = (
            docker_router_scheduled_repeated_loss_script.read_text()
        )
        self.assertIn(
            "fleetrmw.rmw_router_scheduled_reliability_repeated_loss_matrix.v1",
            docker_router_scheduled_repeated_loss_source,
        )
        self.assertIn("SEED_SEMANTICS", docker_router_scheduled_repeated_loss_source)
        self.assertIn("loss_percents", docker_router_scheduled_repeated_loss_source)
        self.assertIn('"partial"', docker_router_scheduled_repeated_loss_source)
        self.assertIn("run_probe(", docker_router_scheduled_repeated_loss_source)
        self.assertIn(
            "netem_loss_percent=loss_percent",
            docker_router_scheduled_repeated_loss_source,
        )
        docker_router_multi_robot_scheduled_reliability_script = (
            ROOT
            / "scripts"
            / "run_rmw_docker_router_multi_robot_scheduled_reliability_probe.py"
        )
        self.assertTrue(
            docker_router_multi_robot_scheduled_reliability_script.exists()
        )
        docker_router_multi_robot_scheduled_reliability_source = (
            docker_router_multi_robot_scheduled_reliability_script.read_text()
        )
        self.assertIn(
            "fleetrmw.rmw_router_multi_robot_scheduled_reliability_probe.v1",
            docker_router_multi_robot_scheduled_reliability_source,
        )
        self.assertIn(
            "FLEETQOX_RMW_ROBOT_ID",
            docker_router_multi_robot_scheduled_reliability_source,
        )
        self.assertIn(
            "--drop-source-sequences 2",
            docker_router_multi_robot_scheduled_reliability_source,
        )
        self.assertIn(
            "scheduler_per_robot",
            docker_router_multi_robot_scheduled_reliability_source,
        )
        self.assertIn(
            "total_nack_retransmissions",
            docker_router_multi_robot_scheduled_reliability_source,
        )
        docker_router_mixed_workload_script = (
            ROOT
            / "scripts"
            / "run_rmw_docker_router_mixed_action_control_state_probe.py"
        )
        self.assertTrue(docker_router_mixed_workload_script.exists())
        docker_router_mixed_workload_source = (
            docker_router_mixed_workload_script.read_text()
        )
        self.assertIn(
            "fleetrmw.rmw_router_mixed_action_control_state_probe.v1",
            docker_router_mixed_workload_source,
        )
        self.assertIn("mixed_robot_count", docker_router_mixed_workload_source)
        self.assertIn("scheduler_urgent_frames", docker_router_mixed_workload_source)
        self.assertIn("/fleetqox/mixed/", docker_router_mixed_workload_source)
        docker_router_proactive_diversity_script = (
            ROOT
            / "scripts"
            / "run_rmw_docker_router_proactive_deadline_diversity_probe.py"
        )
        self.assertTrue(docker_router_proactive_diversity_script.exists())
        docker_router_proactive_diversity_source = (
            docker_router_proactive_diversity_script.read_text()
        )
        self.assertIn(
            "fleetrmw.rmw_router_proactive_deadline_diversity_probe.v1",
            docker_router_proactive_diversity_source,
        )
        self.assertIn("FLEETQOX_RMW_PEER_POLICY=adaptive_qos", docker_router_proactive_diversity_source)
        self.assertIn("on_time_sequences", docker_router_proactive_diversity_source)
        self.assertIn("subscriber-deadline-ms", docker_router_proactive_diversity_source)
        docker_router_proactive_repeated_script = (
            ROOT
            / "scripts"
            / "run_rmw_docker_router_proactive_deadline_diversity_repeated_loss_matrix.py"
        )
        self.assertTrue(docker_router_proactive_repeated_script.exists())
        docker_router_proactive_repeated_source = (
            docker_router_proactive_repeated_script.read_text()
        )
        self.assertIn(
            "fleetrmw.rmw_router_proactive_deadline_diversity_repeated_loss_matrix.v1",
            docker_router_proactive_repeated_source,
        )
        self.assertIn("SEED_SEMANTICS", docker_router_proactive_repeated_source)
        self.assertIn("max_observed_latency_ms", docker_router_proactive_repeated_source)
        docker_router_multi_proactive_script = (
            ROOT
            / "scripts"
            / "run_rmw_docker_router_multi_robot_proactive_deadline_diversity_probe.py"
        )
        self.assertTrue(docker_router_multi_proactive_script.exists())
        docker_router_multi_proactive_source = (
            docker_router_multi_proactive_script.read_text()
        )
        self.assertIn(
            "fleetrmw.rmw_router_multi_robot_proactive_deadline_diversity_probe.v1",
            docker_router_multi_proactive_source,
        )
        self.assertIn("deadline_success_jain_index", docker_router_multi_proactive_source)
        self.assertIn("proactive_path_transmissions", docker_router_multi_proactive_source)
        self.assertIn("FLEETQOX_RMW_PEER_POLICY=adaptive_qos", docker_router_multi_proactive_source)
        docker_router_budgeted_fleet_plan_script = (
            ROOT
            / "scripts"
            / "run_rmw_docker_router_multi_robot_budgeted_fleet_plan_probe.py"
        )
        self.assertTrue(docker_router_budgeted_fleet_plan_script.exists())
        docker_router_budgeted_fleet_plan_source = (
            docker_router_budgeted_fleet_plan_script.read_text()
        )
        self.assertIn(
            "fleetrmw.rmw_router_multi_robot_budgeted_fleet_plan_probe.v1",
            docker_router_budgeted_fleet_plan_source,
        )
        self.assertIn("redundancy_budget_bytes_per_tick", docker_router_budgeted_fleet_plan_source)
        self.assertIn("failure_domain=\"private_5g_core\"", docker_router_budgeted_fleet_plan_source)
        self.assertIn("FLEETQOX_RMW_PEER_POLICY=fleet_plan", docker_router_budgeted_fleet_plan_source)
        self.assertIn("path_transmission_reduction_ratio", docker_router_budgeted_fleet_plan_source)
        self.assertIn("sequential_confidence_fallback", docker_router_budgeted_fleet_plan_source)
        self.assertIn("sequential_separation_margin", docker_router_budgeted_fleet_plan_source)
        self.assertIn("confidence_fallback_actuations", docker_router_budgeted_fleet_plan_source)
        self.assertIn("feedback_safe_mode_count", docker_router_budgeted_fleet_plan_source)
        self.assertIn("fallback_recovery_samples", docker_router_budgeted_fleet_plan_source)
        self.assertIn("fallback_recovery", docker_router_budgeted_fleet_plan_source)
        self.assertIn("subscriber_timeout_ms", docker_router_budgeted_fleet_plan_source)
        self.assertIn("publisher_trigger_timeout_ms", docker_router_budgeted_fleet_plan_source)
        self.assertIn("graph_renew_interval_ms", docker_router_budgeted_fleet_plan_source)
        docker_router_budgeted_epoch_script = (
            ROOT
            / "scripts"
            / "run_rmw_docker_router_multi_robot_budgeted_fleet_plan_epoch_probe.py"
        )
        self.assertTrue(docker_router_budgeted_epoch_script.exists())
        docker_router_budgeted_epoch_source = docker_router_budgeted_epoch_script.read_text()
        self.assertIn(
            "fleetrmw.rmw_router_multi_robot_budgeted_fleet_plan_epoch_probe.v1",
            docker_router_budgeted_epoch_source,
        )
        self.assertIn("epoch_transition=True", docker_router_budgeted_epoch_source)
        self.assertIn("actual_path_transmissions", docker_router_budgeted_epoch_source)
        docker_router_qoe_feedback_script = (
            ROOT
            / "scripts"
            / "run_rmw_docker_router_multi_robot_qoe_feedback_budget_probe.py"
        )
        self.assertTrue(docker_router_qoe_feedback_script.exists())
        docker_router_qoe_feedback_source = docker_router_qoe_feedback_script.read_text()
        self.assertIn(
            "fleetrmw.rmw_router_multi_robot_qoe_feedback_budget_probe.v1",
            docker_router_qoe_feedback_source,
        )
        self.assertIn("qoe_feedback=True", docker_router_qoe_feedback_source)
        self.assertIn("protected_robots", docker_router_qoe_feedback_source)
        docker_router_qoe_feedback_matrix_script = (
            ROOT
            / "scripts"
            / "run_rmw_docker_router_multi_robot_qoe_feedback_budget_repeated_matrix.py"
        )
        self.assertTrue(docker_router_qoe_feedback_matrix_script.exists())
        docker_router_qoe_feedback_matrix_source = (
            docker_router_qoe_feedback_matrix_script.read_text()
        )
        self.assertIn(
            "fleetrmw.rmw_router_multi_robot_qoe_feedback_budget_repeated_matrix.v1",
            docker_router_qoe_feedback_matrix_source,
        )
        self.assertIn("SEED_SEMANTICS", docker_router_qoe_feedback_matrix_source)
        self.assertIn("total_actual_path_transmissions", docker_router_qoe_feedback_matrix_source)
        docker_router_qoe_migration_script = (
            ROOT
            / "scripts"
            / "run_rmw_docker_router_multi_robot_qoe_protection_migration_probe.py"
        )
        self.assertTrue(docker_router_qoe_migration_script.exists())
        docker_router_qoe_migration_source = docker_router_qoe_migration_script.read_text()
        self.assertIn(
            "fleetrmw.rmw_router_multi_robot_qoe_protection_migration_probe.v1",
            docker_router_qoe_migration_source,
        )
        self.assertIn("qoe_migration=True", docker_router_qoe_migration_source)
        self.assertIn("epoch_path_plans", docker_router_qoe_migration_source)
        self.assertIn("max_epoch_convergence_ms", docker_router_budgeted_fleet_plan_source)
        self.assertIn("protected_set_churn", docker_router_budgeted_fleet_plan_source)
        self.assertIn("--publish-trigger-file", reliable_interprocess_source)
        self.assertIn("wait_for_publish_trigger", reliable_interprocess_source)
        self.assertIn("--publisher-ready-file", reliable_interprocess_source)
        self.assertIn("mark_publisher_ready", reliable_interprocess_source)
        docker_router_qoe_migration_scale_script = (
            ROOT
            / "scripts"
            / "run_rmw_docker_router_qoe_protection_migration_scale_matrix.py"
        )
        self.assertTrue(docker_router_qoe_migration_scale_script.exists())
        docker_router_qoe_migration_scale_source = (
            docker_router_qoe_migration_scale_script.read_text()
        )
        self.assertIn(
            "fleetrmw.rmw_router_qoe_protection_migration_scale_matrix.v1",
            docker_router_qoe_migration_scale_source,
        )
        self.assertIn("--robot-counts", docker_router_qoe_migration_scale_source)
        self.assertIn("aggregate_path_transmission_reduction_ratio", docker_router_qoe_migration_scale_source)
        self.assertIn("total_protection_migrations", docker_router_qoe_migration_scale_source)
        self.assertIn("event_triggered_feedback=True", docker_router_qoe_migration_scale_source)
        self.assertIn("sequential_qoe_feedback=True", docker_router_qoe_migration_scale_source)
        docker_router_qoe_migration_repeated_script = (
            ROOT
            / "scripts"
            / "run_rmw_docker_router_qoe_protection_migration_sequential_repeated_matrix.py"
        )
        self.assertTrue(docker_router_qoe_migration_repeated_script.exists())
        docker_router_qoe_migration_repeated_source = (
            docker_router_qoe_migration_repeated_script.read_text()
        )
        self.assertIn(
            "fleetrmw.rmw_router_qoe_protection_migration_sequential_repeated_matrix.v1",
            docker_router_qoe_migration_repeated_source,
        )
        self.assertIn("SEED_SEMANTICS", docker_router_qoe_migration_repeated_source)
        self.assertIn("confidence_epoch_ratio", docker_router_qoe_migration_repeated_source)
        self.assertIn("failure_mode_counts", docker_router_qoe_migration_repeated_source)
        self.assertIn("confidence_not_separated", docker_router_qoe_migration_repeated_source)
        self.assertIn("confidence_fallback_applied", docker_router_qoe_migration_repeated_source)
        self.assertIn("confidence_fallback_run_count", docker_router_qoe_migration_repeated_source)
        self.assertIn("confidence_fallback_delivery_failure", docker_router_qoe_migration_repeated_source)
        self.assertIn("confidence_fallback_recovered_window", docker_router_qoe_migration_repeated_source)
        self.assertIn("feedback_safe_mode_delivery_failure", docker_router_qoe_migration_repeated_source)
        self.assertIn("feedback_safe_mode_run_count", docker_router_qoe_migration_repeated_source)
        self.assertIn("fallback_recovery_ok_run_count", docker_router_qoe_migration_repeated_source)
        self.assertIn("sequential_separation_margin", docker_router_qoe_migration_repeated_source)
        docker_router_service_timeout_script = (
            ROOT / "scripts" / "run_rmw_docker_router_ros2_service_timeout_probe.py"
        )
        self.assertTrue(docker_router_service_timeout_script.exists())
        docker_router_service_timeout_source = docker_router_service_timeout_script.read_text()
        self.assertIn(
            "fleetrmw.rmw_router_ros2_service_timeout_probe.v1",
            docker_router_service_timeout_source,
        )
        self.assertIn("--expected-service-frames 2", docker_router_service_timeout_source)
        self.assertIn("timed_out", docker_router_service_timeout_source)
        docker_router_multi_proactive_repeated_script = (
            ROOT
            / "scripts"
            / "run_rmw_docker_router_multi_robot_proactive_deadline_diversity_repeated_loss_matrix.py"
        )
        self.assertTrue(docker_router_multi_proactive_repeated_script.exists())
        docker_router_multi_proactive_repeated_source = (
            docker_router_multi_proactive_repeated_script.read_text()
        )
        self.assertIn(
            "fleetrmw.rmw_router_multi_robot_proactive_deadline_diversity_repeated_loss_matrix.v1",
            docker_router_multi_proactive_repeated_source,
        )
        self.assertIn("min_deadline_success_jain_index", docker_router_multi_proactive_repeated_source)
        self.assertIn("total_proactive_path_transmissions", docker_router_multi_proactive_repeated_source)
        docker_router_multihop_reliability_script = (
            ROOT / "scripts" / "run_rmw_docker_router_multihop_reliability_probe.py"
        )
        self.assertTrue(docker_router_multihop_reliability_script.exists())
        docker_router_multihop_reliability_source = docker_router_multihop_reliability_script.read_text()
        self.assertIn(
            "fleetrmw.rmw_router_multihop_reliability_probe.v1",
            docker_router_multihop_reliability_source,
        )
        self.assertIn("router_a", docker_router_multihop_reliability_source)
        self.assertIn("router_b", docker_router_multihop_reliability_source)
        self.assertIn("--peers {router_b_name}:48351", docker_router_multihop_reliability_source)
        self.assertIn("--graph-peers {router_b_name}:48351", docker_router_multihop_reliability_source)
        self.assertIn("--drop-source-sequences 2", docker_router_multihop_reliability_source)
        self.assertIn("ack_nack_forwarded", docker_router_multihop_reliability_source)
        self.assertIn("nack_retransmissions", docker_router_multihop_reliability_source)
        docker_router_path_diversity_script = ROOT / "scripts" / "run_rmw_docker_router_path_diversity_probe.py"
        self.assertTrue(docker_router_path_diversity_script.exists())
        docker_router_path_diversity_source = docker_router_path_diversity_script.read_text()
        self.assertIn(
            "fleetrmw.rmw_router_path_diversity_probe.v1",
            docker_router_path_diversity_source,
        )
        self.assertIn("primary_router", docker_router_path_diversity_source)
        self.assertIn("backup_router", docker_router_path_diversity_source)
        self.assertIn("--drop-source-sequences 2", docker_router_path_diversity_source)
        self.assertIn("--min-retransmissions 0", docker_router_path_diversity_source)
        self.assertIn('nack_retransmissions", 0) == 0', docker_router_path_diversity_source)
        docker_router_adaptive_failover_script = ROOT / "scripts" / "run_rmw_docker_router_adaptive_failover_probe.py"
        self.assertTrue(docker_router_adaptive_failover_script.exists())
        docker_router_adaptive_failover_source = docker_router_adaptive_failover_script.read_text()
        self.assertIn(
            "fleetrmw.rmw_router_adaptive_failover_probe.v1",
            docker_router_adaptive_failover_source,
        )
        self.assertIn("FLEETQOX_RMW_PEER_POLICY=adaptive_failover", docker_router_adaptive_failover_source)
        self.assertIn("adaptive_failovers", docker_router_adaptive_failover_source)
        self.assertIn("adaptive_selected_peer_index", docker_router_adaptive_failover_source)
        self.assertIn("adaptive_unicast_frames", docker_router_adaptive_failover_source)
        self.assertIn("primary_router", docker_router_adaptive_failover_source)
        self.assertIn("backup_router", docker_router_adaptive_failover_source)
        docker_router_adaptive_score_script = ROOT / "scripts" / "run_rmw_docker_router_adaptive_score_probe.py"
        self.assertTrue(docker_router_adaptive_score_script.exists())
        docker_router_adaptive_score_source = docker_router_adaptive_score_script.read_text()
        self.assertIn(
            "fleetrmw.rmw_router_adaptive_score_probe.v1",
            docker_router_adaptive_score_source,
        )
        self.assertIn("FLEETQOX_RMW_PEER_POLICY=adaptive_score", docker_router_adaptive_score_source)
        self.assertIn("--post-recovery-payload", docker_router_adaptive_score_source)
        self.assertIn("adaptive_peer_score_sum", docker_router_adaptive_score_source)
        self.assertIn("adaptive_selected_peer_index", docker_router_adaptive_score_source)
        self.assertIn("backup_router", docker_router_adaptive_score_source)
        docker_router_adaptive_qos_script = ROOT / "scripts" / "run_rmw_docker_router_adaptive_qos_probe.py"
        self.assertTrue(docker_router_adaptive_qos_script.exists())
        docker_router_adaptive_qos_source = docker_router_adaptive_qos_script.read_text()
        self.assertIn(
            "fleetrmw.rmw_router_adaptive_qos_probe.v1",
            docker_router_adaptive_qos_source,
        )
        self.assertIn("FLEETQOX_RMW_PEER_POLICY=adaptive_qos", docker_router_adaptive_qos_source)
        self.assertIn("FLEETQOX_RMW_REDUNDANT_DEADLINE_MS=50", docker_router_adaptive_qos_source)
        self.assertIn("--deadline-ms 20", docker_router_adaptive_qos_source)
        self.assertIn("adaptive_redundant_frames", docker_router_adaptive_qos_source)
        self.assertIn("adaptive_unicast_frames", docker_router_adaptive_qos_source)
        self.assertIn('nack_retransmissions", 0) == 0', docker_router_adaptive_qos_source)
        docker_router_fleet_plan_script = ROOT / "scripts" / "run_rmw_docker_router_fleet_plan_probe.py"
        self.assertTrue(docker_router_fleet_plan_script.exists())
        docker_router_fleet_plan_source = docker_router_fleet_plan_script.read_text()
        self.assertIn(
            "fleetrmw.rmw_router_fleet_plan_probe.v1",
            docker_router_fleet_plan_source,
        )
        self.assertIn("FLEETQOX_RMW_PEER_POLICY=fleet_plan", docker_router_fleet_plan_source)
        self.assertIn("FLEETQOX_RMW_FLEET_PATH_PLAN_FILE", docker_router_fleet_plan_source)
        self.assertIn("OnlineFleetPathPlanner", docker_router_fleet_plan_source)
        self.assertIn("PathObservation", docker_router_fleet_plan_source)
        self.assertIn("primary_wifi=", docker_router_fleet_plan_source)
        self.assertIn("backup_5g=", docker_router_fleet_plan_source)
        self.assertIn("fleet_plan_redundant_frames", docker_router_fleet_plan_source)
        self.assertIn("fleet_plan_selected_path_count", docker_router_fleet_plan_source)
        docker_router_live_plan_script = (
            ROOT / "scripts" / "run_rmw_docker_router_live_telemetry_plan_probe.py"
        )
        self.assertTrue(docker_router_live_plan_script.exists())
        docker_router_live_plan_source = docker_router_live_plan_script.read_text()
        self.assertIn(
            "fleetrmw.rmw_router_live_telemetry_plan_probe.v1",
            docker_router_live_plan_source,
        )
        self.assertIn("LivePathPlanController", docker_router_live_plan_source)
        self.assertIn("ROUTER_TELEMETRY_SCHEMA_VERSION", docker_router_live_plan_source)
        self.assertIn("subscriber_telemetry_file", docker_router_live_plan_source)
        self.assertIn("--subscriber-telemetry-file", docker_router_live_plan_source)
        self.assertIn("--telemetry-file", docker_router_live_plan_source)
        self.assertIn("FLEETQOX_RMW_FLEET_PATH_PLAN_FILE", docker_router_live_plan_source)
        docker_multi_robot_live_plan_script = (
            ROOT / "scripts" / "run_rmw_docker_multi_robot_live_telemetry_plan_probe.py"
        )
        self.assertTrue(docker_multi_robot_live_plan_script.exists())
        docker_multi_robot_live_plan_source = docker_multi_robot_live_plan_script.read_text()
        self.assertIn(
            "fleetrmw.rmw_multi_robot_live_telemetry_plan_probe.v1",
            docker_multi_robot_live_plan_source,
        )
        self.assertIn("CONTROL_TOPIC = \"/robot_0000/cmd_vel\"", docker_multi_robot_live_plan_source)
        self.assertIn("STATE_TOPIC = \"/robot_0001/odom\"", docker_multi_robot_live_plan_source)
        self.assertIn("FINAL_PATH_PLAN", docker_multi_robot_live_plan_source)
        self.assertIn("backup_5g+primary_wifi", docker_multi_robot_live_plan_source)
        self.assertIn("subscriber_telemetry_files", docker_multi_robot_live_plan_source)
        self.assertIn("LivePathPlanController", docker_multi_robot_live_plan_source)
        self.assertIn("wait_for_path_plan", docker_multi_robot_live_plan_source)
        self.assertIn("duplicate_data_frames_deduped", docker_multi_robot_live_plan_source)
        self.assertIn("ack_nack_duplicate_received", docker_multi_robot_live_plan_source)
        self.assertIn("ROUTER_TELEMETRY_PROFILES", docker_multi_robot_live_plan_source)
        self.assertIn("--profile", docker_multi_robot_live_plan_source)
        self.assertIn("NETEM_SCHEMA_VERSION", docker_multi_robot_live_plan_source)
        self.assertIn("--enable-netem", docker_multi_robot_live_plan_source)
        self.assertIn("--require-netem", docker_multi_robot_live_plan_source)
        self.assertIn("--netem-drain-s", docker_multi_robot_live_plan_source)
        self.assertIn("--reuse-build", docker_multi_robot_live_plan_source)
        self.assertIn("ensure_live_plan_build", docker_multi_robot_live_plan_source)
        self.assertIn("cleanup_live_plan_build", docker_multi_robot_live_plan_source)
        self.assertIn("--cap-add", docker_multi_robot_live_plan_source)
        self.assertIn("tc qdisc replace dev eth0 root netem", docker_multi_robot_live_plan_source)
        self.assertIn("loss random", docker_multi_robot_live_plan_source)
        self.assertIn("NETEM_SEED_SEMANTICS", docker_multi_robot_live_plan_source)
        self.assertIn("router_netem_drain_suffix", docker_multi_robot_live_plan_source)
        self.assertIn("--expected-ack-nack-forwarded", docker_multi_robot_live_plan_source)
        self.assertIn("control_duplicate_ack_required", docker_multi_robot_live_plan_source)
        self.assertIn("stochastic_netem", docker_multi_robot_live_plan_source)
        self.assertIn("state_proactive_data_repeats", docker_multi_robot_live_plan_source)
        self.assertIn("FLEETQOX_RMW_PROACTIVE_DATA_REPEATS", docker_multi_robot_live_plan_source)
        docker_multi_robot_live_matrix_script = (
            ROOT / "scripts" / "run_rmw_docker_multi_robot_live_telemetry_matrix.py"
        )
        self.assertTrue(docker_multi_robot_live_matrix_script.exists())
        docker_multi_robot_live_matrix_source = docker_multi_robot_live_matrix_script.read_text()
        self.assertIn(
            "fleetrmw.rmw_multi_robot_live_telemetry_matrix.v1",
            docker_multi_robot_live_matrix_source,
        )
        self.assertIn("DEFAULT_PROFILES = \"wifi,wan,roaming\"", docker_multi_robot_live_matrix_source)
        self.assertIn("run_record_from_summary", docker_multi_robot_live_matrix_source)
        self.assertIn("render_markdown", docker_multi_robot_live_matrix_source)
        self.assertIn("control_duplicate_data_frames_deduped", docker_multi_robot_live_matrix_source)
        self.assertIn("netem_applied_run_count", docker_multi_robot_live_matrix_source)
        self.assertIn("repetition_seed=seed", docker_multi_robot_live_matrix_source)
        self.assertIn("reuse_build", docker_multi_robot_live_matrix_source)
        self.assertIn("control_duplicate_ack_required", docker_multi_robot_live_matrix_source)
        self.assertIn("stochastic_netem", docker_multi_robot_live_matrix_source)
        self.assertIn("state_proactive_data_repeats", docker_multi_robot_live_matrix_source)
        docker_multi_robot_netem_matrix_script = (
            ROOT / "scripts" / "run_rmw_docker_multi_robot_live_netem_matrix.py"
        )
        self.assertTrue(docker_multi_robot_netem_matrix_script.exists())
        docker_multi_robot_netem_matrix_source = docker_multi_robot_netem_matrix_script.read_text()
        self.assertIn(
            "fleetrmw.rmw_multi_robot_live_netem_matrix.v1",
            docker_multi_robot_netem_matrix_source,
        )
        self.assertIn("enable_netem=True", docker_multi_robot_netem_matrix_source)
        self.assertIn("--require-netem", docker_multi_robot_netem_matrix_source)
        self.assertIn("--netem-drain-s", docker_multi_robot_netem_matrix_source)
        self.assertIn("--reuse-build", docker_multi_robot_netem_matrix_source)
        docker_multi_robot_stochastic_netem_matrix_script = (
            ROOT / "scripts" / "run_rmw_docker_multi_robot_live_stochastic_netem_matrix.py"
        )
        self.assertTrue(docker_multi_robot_stochastic_netem_matrix_script.exists())
        docker_multi_robot_stochastic_netem_matrix_source = (
            docker_multi_robot_stochastic_netem_matrix_script.read_text()
        )
        self.assertIn(
            "fleetrmw.rmw_multi_robot_live_stochastic_netem_matrix.v1",
            docker_multi_robot_stochastic_netem_matrix_source,
        )
        self.assertIn("DEFAULT_LOSS_SCALE = 0.1", docker_multi_robot_stochastic_netem_matrix_source)
        self.assertIn("--reuse-build", docker_multi_robot_stochastic_netem_matrix_source)
        docker_multi_robot_stochastic_netem_sweep_script = (
            ROOT / "scripts" / "run_rmw_docker_multi_robot_live_stochastic_netem_sweep.py"
        )
        self.assertTrue(docker_multi_robot_stochastic_netem_sweep_script.exists())
        docker_multi_robot_stochastic_netem_sweep_source = (
            docker_multi_robot_stochastic_netem_sweep_script.read_text()
        )
        self.assertIn(
            "fleetrmw.rmw_multi_robot_live_stochastic_netem_sweep.v1",
            docker_multi_robot_stochastic_netem_sweep_source,
        )
        self.assertIn("DEFAULT_LOSS_SCALES = \"0.1,0.25,0.5\"", docker_multi_robot_stochastic_netem_sweep_source)
        self.assertIn("--reuse-build", docker_multi_robot_stochastic_netem_sweep_source)
        self.assertIn("prepare_reused_build=False", docker_multi_robot_stochastic_netem_sweep_source)
        self.assertIn("prepare_reused_build: bool = True", docker_multi_robot_stochastic_netem_sweep_source)
        self.assertIn("contract_evidence_failed", docker_multi_robot_stochastic_netem_sweep_source)
        stochastic_sweep_doc = ROOT / "docs" / "RMW_MULTI_ROBOT_LIVE_STOCHASTIC_NETEM_SWEEP_V1.md"
        self.assertTrue(stochastic_sweep_doc.exists())
        self.assertIn("failure boundary", stochastic_sweep_doc.read_text())
        docker_multi_robot_stochastic_netem_ablation_script = (
            ROOT / "scripts" / "run_rmw_docker_multi_robot_live_stochastic_netem_ablation.py"
        )
        self.assertTrue(docker_multi_robot_stochastic_netem_ablation_script.exists())
        docker_multi_robot_stochastic_netem_ablation_source = (
            docker_multi_robot_stochastic_netem_ablation_script.read_text()
        )
        self.assertIn(
            "fleetrmw.rmw_multi_robot_live_stochastic_netem_ablation.v1",
            docker_multi_robot_stochastic_netem_ablation_source,
        )
        self.assertIn("DEFAULT_MODES = \"none,state_only,control_state\"", docker_multi_robot_stochastic_netem_ablation_source)
        self.assertIn("mode_record_from_sweep", docker_multi_robot_stochastic_netem_ablation_source)
        self.assertIn("repair_cost_frames_mean", docker_multi_robot_stochastic_netem_ablation_source)
        self.assertIn("prepare_reused_build=not reuse_build", docker_multi_robot_stochastic_netem_ablation_source)
        stochastic_ablation_doc = ROOT / "docs" / "RMW_MULTI_ROBOT_LIVE_STOCHASTIC_NETEM_ABLATION_V1.md"
        self.assertTrue(stochastic_ablation_doc.exists())
        self.assertIn("proactive repair", stochastic_ablation_doc.read_text())
        live_baseline_comparison_script = ROOT / "scripts" / "compare_fleetrmw_live_baselines.py"
        self.assertTrue(live_baseline_comparison_script.exists())
        live_baseline_comparison_source = live_baseline_comparison_script.read_text()
        self.assertIn("fleetrmw.live_baseline_comparison.v1", live_baseline_comparison_source)
        self.assertIn("direct_claim_allowed", live_baseline_comparison_source)
        self.assertIn("indirect_named_profile", live_baseline_comparison_source)
        self.assertIn("fleet_router_terminal_horizon", live_baseline_comparison_source)
        self.assertIn("FleetRMW Matched 4-Robot Profile Rows", live_baseline_comparison_source)
        live_baseline_comparison_doc = ROOT / "docs" / "RMW_LIVE_BASELINE_COMPARISON_V1.md"
        self.assertTrue(live_baseline_comparison_doc.exists())
        self.assertIn("direct superiority benchmark", live_baseline_comparison_doc.read_text())
        ros2_direct_rmw_netem_probe_script = ROOT / "scripts" / "run_ros2_direct_rmw_netem_probe.py"
        self.assertTrue(ros2_direct_rmw_netem_probe_script.exists())
        ros2_direct_rmw_netem_probe_source = ros2_direct_rmw_netem_probe_script.read_text()
        self.assertIn("fleetrmw.ros2_direct_rmw_netem_probe.v1", ros2_direct_rmw_netem_probe_source)
        self.assertIn("rmw_unavailable", ros2_direct_rmw_netem_probe_source)
        self.assertIn("control_delivery_ratio", ros2_direct_rmw_netem_probe_source)
        self.assertIn("netem_shell_prefix", ros2_direct_rmw_netem_probe_source)
        ros2_direct_rmw_netem_matrix_script = ROOT / "scripts" / "run_ros2_direct_rmw_netem_matrix.py"
        self.assertTrue(ros2_direct_rmw_netem_matrix_script.exists())
        ros2_direct_rmw_netem_matrix_source = ros2_direct_rmw_netem_matrix_script.read_text()
        self.assertIn("fleetrmw.ros2_direct_rmw_netem_matrix.v1", ros2_direct_rmw_netem_matrix_source)
        self.assertIn("skipped_run_count", ros2_direct_rmw_netem_matrix_source)
        self.assertIn("run_probe", ros2_direct_rmw_netem_matrix_source)
        ros2_direct_rmw_netem_doc = ROOT / "docs" / "ROS2_DIRECT_RMW_NETEM_MATRIX_V1.md"
        self.assertTrue(ros2_direct_rmw_netem_doc.exists())
        self.assertIn("ROS 2 Direct RMW Netem Matrix", ros2_direct_rmw_netem_doc.read_text())
        manifest_source = (ROOT / "experiments" / "testbed_manifest.json").read_text()
        self.assertIn("fleetrmw_multi_robot_live_stochastic_netem_ablation", manifest_source)
        self.assertIn("ros2_direct_rmw_netem_matrix", manifest_source)
        rmw_netem_dockerfile = ROOT / "external" / "rmw-netem" / "Dockerfile"
        self.assertTrue(rmw_netem_dockerfile.exists())
        rmw_netem_dockerfile_source = rmw_netem_dockerfile.read_text()
        self.assertIn("iproute2", rmw_netem_dockerfile_source)
        self.assertIn("python3-colcon-common-extensions", rmw_netem_dockerfile_source)
        self.assertIn("ros-jazzy-nav2-msgs", rmw_netem_dockerfile_source)
        self.assertIn("ros-jazzy-rmf-task-msgs", rmw_netem_dockerfile_source)
        self.assertIn("ros-jazzy-rmf-fleet-msgs", rmw_netem_dockerfile_source)
        self.assertIn("ros-jazzy-rmw-cyclonedds-cpp", rmw_netem_dockerfile_source)
        self.assertIn("ros-jazzy-rmw-zenoh-cpp", rmw_netem_dockerfile_source)
        rmw_netem_readme = ROOT / "external" / "rmw-netem" / "README.md"
        self.assertTrue(rmw_netem_readme.exists())
        self.assertIn("localhost/fleetrmw/rmw-netem:jazzy", rmw_netem_readme.read_text())
        docker_router_qos_script = ROOT / "scripts" / "run_rmw_docker_router_qos_drop_probe.py"
        self.assertTrue(docker_router_qos_script.exists())
        docker_router_qos_source = docker_router_qos_script.read_text()
        self.assertIn("fleetrmw.rmw_router_qos_drop_probe.v1", docker_router_qos_source)
        self.assertIn("expected-qos-drops", docker_router_qos_source)
        self.assertIn("forward-delay-ms", docker_router_qos_source)
        self.assertIn("--expect-taken false", docker_router_qos_source)
        self.assertIn("--entrypoint", docker_router_qos_source)
        self.assertIn("parse_last_json", docker_router_qos_source)
        self.assertIn("publisher_stderr", docker_router_qos_source)
        docker_router_priority_script = ROOT / "scripts" / "run_rmw_docker_router_qos_priority_probe.py"
        self.assertTrue(docker_router_priority_script.exists())
        docker_router_priority_source = docker_router_priority_script.read_text()
        self.assertIn("fleetrmw.rmw_router_qos_priority_probe.v1", docker_router_priority_source)
        self.assertIn("scheduler-window-ms", docker_router_priority_source)
        self.assertIn("deadline-ms", docker_router_priority_source)
        self.assertIn("expected-order", docker_router_priority_source)
        self.assertIn("forwarded_topics", docker_router_priority_source)
        docker_router_priority_matrix = ROOT / "scripts" / "run_rmw_docker_router_qos_priority_matrix.py"
        self.assertTrue(docker_router_priority_matrix.exists())
        docker_router_priority_matrix_source = docker_router_priority_matrix.read_text()
        self.assertIn("fleetrmw.rmw_router_qos_priority_matrix.v1", docker_router_priority_matrix_source)
        self.assertIn("fifo_baseline", docker_router_priority_matrix_source)
        self.assertIn("deadline_scheduler", docker_router_priority_matrix_source)
        self.assertIn("priority_improved", docker_router_priority_matrix_source)
        multi_robot_qos_script = (
            ROOT / "scripts" / "run_rmw_docker_router_multi_robot_qos_matrix.py"
        )
        self.assertTrue(multi_robot_qos_script.exists())
        multi_robot_qos_source = multi_robot_qos_script.read_text()
        self.assertIn(
            "fleetrmw.rmw_router_multi_robot_qos_matrix.v1",
            multi_robot_qos_source,
        )
        self.assertIn("FLEETQOX_RMW_ROBOT_ID", multi_robot_qos_source)
        self.assertIn("scheduler_deadline_success_jain_index", multi_robot_qos_source)
        self.assertIn("per_robot_complete", multi_robot_qos_source)
        multi_robot_qos_doc = ROOT / "docs" / "RMW_MULTI_ROBOT_QOS_SCHEDULER_V1.md"
        self.assertTrue(multi_robot_qos_doc.exists())
        rmw_pubsub_source = (PKG / "src" / "rmw_pubsub.cpp").read_text()
        self.assertIn("FLEETQOX_RMW_ROBOT_ID", rmw_pubsub_source)
        self.assertIn("local_robot_id()", rmw_pubsub_source)
        self.assertIn("scheduler_per_robot", router_source)
        self.assertIn("scheduler_deadline_misses", router_source)
        self.assertIn("scheduler_queue_wait_ms_mean", router_source)
        self.assertIn("scheduler_urgent_deadline_ms", router_source)
        self.assertIn("scheduler_urgent_frames", router_source)
        self.assertIn("scheduler_paced_frames", router_source)
        self.assertIn("scheduler_drain_pacing_ms", router_source)
        self.assertIn("scheduler_admission_policy", router_source)
        self.assertIn("scheduler_admits_holdback", router_source)
        self.assertIn("slo_service_time", router_source)
        self.assertIn("slo_service_epoch", router_source)
        self.assertIn("scheduler_admission_ewma_alpha", router_source)
        self.assertIn("scheduler_admission_min_epoch_frames", router_source)
        self.assertIn("scheduler_admission_switches", router_source)
        self.assertIn("scheduler_admission_holdback_enabled", router_source)
        self.assertIn("scheduler_admission_bypassed_frames", router_source)
        self.assertIn("scheduler_admission_service_ratio_max", router_source)
        self.assertIn("take_age_ms", multi_robot_qos_source)
        self.assertIn("payload-size", multi_robot_qos_source)
        self.assertIn("e2e_deadline_misses", multi_robot_qos_source)
        self.assertIn("scheduler_admission_policy", multi_robot_qos_source)
        self.assertIn("scheduler_admission_min_service_ratio", multi_robot_qos_source)
        self.assertIn("netem_loss_percent", multi_robot_qos_source)
        self.assertIn("netem_config_for_profile", multi_robot_qos_source)
        multi_robot_netem_script = (
            ROOT / "scripts" / "run_rmw_docker_router_multi_robot_qos_netem_matrix.py"
        )
        self.assertTrue(multi_robot_netem_script.exists())
        multi_robot_netem_source = multi_robot_netem_script.read_text()
        self.assertIn(
            "fleetrmw.rmw_router_multi_robot_qos_netem_matrix.v1",
            multi_robot_netem_source,
        )
        self.assertIn("control_p95_reduction_ms", multi_robot_netem_source)
        self.assertIn("adaptive_selected_policy", multi_robot_netem_source)
        self.assertIn("adaptive_worse_profile_count", multi_robot_netem_source)
        self.assertIn("adaptive_mean_control_p95_reduction_ms", multi_robot_netem_source)
        self.assertIn("adaptive_mean_reduction > 0.0", multi_robot_netem_source)
        self.assertIn("deadline_gated_holdback", multi_robot_netem_source)
        self.assertIn("adaptive_selected_policy(", multi_robot_netem_source)
        self.assertIn("scheduler_urgent_frames", multi_robot_netem_source)
        self.assertIn("netem_qdisc", multi_robot_netem_source)
        live_adaptive_script = (
            ROOT / "scripts" / "run_rmw_docker_router_multi_robot_qos_live_adaptive_matrix.py"
        )
        self.assertTrue(live_adaptive_script.exists())
        live_adaptive_source = live_adaptive_script.read_text()
        self.assertIn(
            "fleetrmw.rmw_router_multi_robot_qos_live_adaptive_matrix.v1",
            live_adaptive_source,
        )
        self.assertIn("slo_service_epoch", live_adaptive_source)
        self.assertIn("queued_profile_count", live_adaptive_source)
        self.assertIn("bypassed_profile_count", live_adaptive_source)
        self.assertIn("control_p95_regression_count", live_adaptive_source)
        self.assertIn("scheduler_admission_bypassed_frames", live_adaptive_source)
        self.assertIn("scheduler_admission_epoch_samples", live_adaptive_source)
        self.assertIn("scheduler_admission_switches", live_adaptive_source)
        repeated_loss_script = (
            ROOT / "scripts" /
            "run_rmw_docker_router_multi_robot_qos_live_adaptive_repeated_loss_matrix.py"
        )
        self.assertTrue(repeated_loss_script.exists())
        repeated_loss_source = repeated_loss_script.read_text()
        self.assertIn(
            "fleetrmw.rmw_router_multi_robot_qos_live_adaptive_repeated_loss_matrix.v1",
            repeated_loss_source,
        )
        self.assertIn("loss_percents", repeated_loss_source)
        self.assertIn("SEED_SEMANTICS", repeated_loss_source)
        self.assertIn("partial", repeated_loss_source)
        self.assertIn("fail_on_row_failure", repeated_loss_source)
        self.assertIn("netem_loss_percent=loss_percent", repeated_loss_source)

    def test_fleet_scale_frontier_action_and_comparison_contracts_exist(self) -> None:
        iface_cmake = (IFACE_PKG / "CMakeLists.txt").read_text()
        iface_manifest = (IFACE_PKG / "package.xml").read_text()
        self.assertIn("action/NavigateFleet.action", iface_cmake)
        self.assertIn("action/DispatchFleetTask.action", iface_cmake)
        self.assertIn("DEPENDENCIES builtin_interfaces geometry_msgs nav_msgs sensor_msgs", iface_cmake)
        self.assertIn("<depend>builtin_interfaces</depend>", iface_manifest)
        self.assertIn("<depend>geometry_msgs</depend>", iface_manifest)
        navigate_action = (IFACE_PKG / "action" / "NavigateFleet.action").read_text()
        dispatch_action = (IFACE_PKG / "action" / "DispatchFleetTask.action").read_text()
        self.assertIn("geometry_msgs/PoseStamped pose", navigate_action)
        self.assertIn("builtin_interfaces/Duration navigation_time", navigate_action)
        self.assertIn("uint16 number_of_recoveries", navigate_action)
        self.assertIn("string[] phases", dispatch_action)
        self.assertIn("builtin_interfaces/Time completion_time", dispatch_action)
        self.assertIn("float32 progress", dispatch_action)

        docker_cli_matrix_script = ROOT / "scripts" / "run_rmw_docker_ros2_cli_message_matrix.py"
        docker_cli_matrix_source = docker_cli_matrix_script.read_text()
        for msg_type in (
            "sensor_msgs/msg/PointCloud2",
            "trajectory_msgs/msg/JointTrajectory",
            "diagnostic_msgs/msg/DiagnosticArray",
            "fleetrmw_interfaces/msg/SampleIdentity",
            "fleetrmw_interfaces/msg/ProjectionQuality",
        ):
            self.assertIn(msg_type, docker_cli_matrix_source)

        nav_rmf_script = ROOT / "scripts" / "run_rmw_docker_router_nav2_rmf_action_workload.py"
        self.assertTrue(nav_rmf_script.exists())
        nav_rmf_source = nav_rmf_script.read_text()
        self.assertIn("fleetrmw.rmw_router_nav2_rmf_action_workload.v5", nav_rmf_source)
        self.assertIn("NavigateFleet", nav_rmf_source)
        self.assertIn("DispatchFleetTask", nav_rmf_source)
        self.assertIn("NavigateToPose", nav_rmf_source)
        self.assertIn("SubmitTask", nav_rmf_source)
        self.assertIn("CancelTask", nav_rmf_source)
        self.assertIn("ActionServer", nav_rmf_source)
        self.assertIn("ActionClient", nav_rmf_source)
        self.assertIn("expected_service_frames = 58 + upstream_concurrency * 6", nav_rmf_source)
        self.assertIn("--upstream-concurrency", nav_rmf_source)
        self.assertIn("ManagedNavLifecycle", nav_rmf_source)
        self.assertIn("ManageLifecycleNodes", nav_rmf_source)
        self.assertIn("nav2_lifecycle_manager lifecycle_manager", nav_rmf_source)
        self.assertIn("nav2_lifecycle_manager_upstream", nav_rmf_source)
        self.assertIn("lifecycle_transport", nav_rmf_source)
        self.assertIn("nav2_compatible", nav_rmf_source)
        self.assertIn("rmf_compatible", nav_rmf_source)
        self.assertIn("nav2_upstream", nav_rmf_source)
        self.assertIn("rmf_upstream", nav_rmf_source)

        ns3_runner = ROOT / "scripts" / "run_ns3_docker_fleet_matrix.py"
        self.assertTrue(ns3_runner.exists())
        ns3_source = ns3_runner.read_text()
        self.assertIn("fleetqox.ns3_docker_fleet_matrix.v1", ns3_source)
        self.assertIn("high_fidelity_wireless_claim_allowed", ns3_source)
        ns3_wifi_runner = ROOT / "scripts" / "run_ns3_docker_wifi_mobility_matrix.py"
        self.assertTrue(ns3_wifi_runner.exists())
        ns3_wifi_source = ns3_wifi_runner.read_text()
        self.assertIn("fleetqox.ns3_docker_wifi_mobility_matrix.v1", ns3_wifi_source)
        self.assertIn("roaming_handoff_claim_allowed", ns3_wifi_source)
        self.assertIn("single_ap_80211g_infrastructure", ns3_wifi_source)
        ns3_roaming_runner = ROOT / "scripts" / "run_ns3_docker_wifi_roaming_matrix.py"
        self.assertTrue(ns3_roaming_runner.exists())
        ns3_roaming_source = ns3_roaming_runner.read_text()
        self.assertIn("fleetqox.ns3_docker_wifi_roaming_matrix.v1", ns3_roaming_source)
        self.assertIn("bridged_dual_ap_80211g", ns3_roaming_source)
        self.assertIn("association_transition_events_measured", ns3_roaming_source)
        shm_header = PKG / "include" / "rmw_fleetqox_cpp" / "shared_memory_transport.hpp"
        shm_source = PKG / "src" / "shared_memory_transport.cpp"
        self.assertTrue(shm_header.exists())
        self.assertTrue(shm_source.exists())
        self.assertIn("PTHREAD_PROCESS_SHARED", shm_source.read_text())
        self.assertIn("shm_open", shm_source.read_text())
        shm_runner = ROOT / "scripts" / "run_rmw_docker_shared_memory_probe.py"
        self.assertTrue(shm_runner.exists())
        self.assertIn("fleetrmw.docker_shared_memory_probe.v1", shm_runner.read_text())
        self.assertIn("udp_fallback", shm_runner.read_text())
        hybrid_runner = ROOT / "scripts" / "run_rmw_docker_shm_udp_hybrid_probe.py"
        self.assertTrue(hybrid_runner.exists())
        self.assertIn("fleetrmw.docker_shm_udp_hybrid_probe.v1", hybrid_runner.read_text())
        self.assertIn("duplicate_data_frames_deduped", hybrid_runner.read_text())
        loan_probe = PKG / "src" / "loaned_message_probe.cpp"
        self.assertTrue(loan_probe.exists())
        self.assertIn("fleetrmw.loaned_message_probe.v1", loan_probe.read_text())
        loan_runner = ROOT / "scripts" / "run_rmw_docker_loaned_message_probe.py"
        self.assertTrue(loan_runner.exists())
        self.assertIn("zero_copy_claim_allowed", loan_runner.read_text())
        dockerfile = (ROOT / "external" / "rmw-netem" / "Dockerfile").read_text()
        self.assertIn("libns3-dev", dockerfile)
        self.assertIn("libgsl-dev", dockerfile)

        matched_script = ROOT / "scripts" / "run_rmw_docker_router_matched_multi_topic_probe.py"
        self.assertTrue(matched_script.exists())
        matched_source = matched_script.read_text()
        self.assertIn("fleetrmw.router_matched_multi_topic_probe.v1", matched_source)
        self.assertIn("publisher-router-subscriber", matched_source)
        self.assertIn("topic_specs_for_robot_count", matched_source)
        self.assertIn("--reuse-build", matched_source)
        self.assertIn("NETEM_SEED_SEMANTICS", matched_source)
        self.assertIn("--reliable-ack-timeout-ms", matched_source)
        self.assertIn("FLEETQOX_RMW_RELIABLE_ACK_TIMEOUT_MS", matched_source)
        self.assertIn("ack_timeout_retransmit", matched_source)

        comparison_script = ROOT / "scripts" / "run_large_scale_rmw_comparison.py"
        self.assertTrue(comparison_script.exists())
        comparison_source = comparison_script.read_text()
        self.assertIn("fleetrmw.large_scale_rmw_comparison.v2", comparison_source)
        self.assertIn("rmw_fleetqox_cpp_router", comparison_source)
        self.assertIn("rmw_fastrtps_cpp", comparison_source)
        self.assertIn("rmw_cyclonedds_cpp", comparison_source)
        self.assertIn("rmw_zenoh_cpp", comparison_source)
        self.assertIn("topology_note", comparison_source)
        self.assertIn("split_scope_topology_caveated", comparison_source)
        self.assertIn("direct_claim_allowed", comparison_source)
        self.assertIn("cross_scope_superiority", comparison_source)
        self.assertIn("run_fleetrmw(", comparison_source)
        self.assertIn("run_direct(", comparison_source)

        frontier_script = ROOT / "scripts" / "run_rmw_docker_fleet_repair_capacity_frontier.py"
        self.assertTrue(frontier_script.exists())
        frontier_source = frontier_script.read_text()
        self.assertIn("fleetrmw.fleet_repair_capacity_frontier.v1", frontier_source)
        self.assertIn("--robot-counts", frontier_source)
        self.assertIn("8,16,32", frontier_source)
        self.assertIn("--capacity-fractions", frontier_source)
        self.assertIn(
            "shared_budget_admission_actuated_repair_qoe_frontier",
            frontier_source,
        )
        self.assertIn("repair_admission_qualified_ratio", frontier_source)
        self.assertIn("fleet_repair_capacity_bytes=capacity_bytes", frontier_source)
        self.assertIn("repair_capacity_fault=True", frontier_source)
        self.assertIn("reuse_build=True", frontier_source)

    def test_capability_manifest_scopes_unsupported_abi(self) -> None:
        manifest_path = PKG / "capabilities.json"
        self.assertTrue(manifest_path.exists())
        manifest = json.loads(manifest_path.read_text())
        self.assertEqual(manifest["schema_version"], "fleetrmw.rmw_capabilities.v1")
        self.assertFalse(manifest["production_ready"])
        self.assertEqual(
            manifest["serialization_format"],
            "fleetrmw.introspection_c.v1",
        )
        self.assertTrue(manifest["supported"]["source_sequence_ack_nack_repair"])
        for capability in (
            "publisher_events",
            "content_filtered_topics",
            "dynamic_messages",
        ):
            self.assertIn(capability, manifest["unsupported"])
        self.assertTrue(manifest["supported"]["udp_network_flow_endpoints"])
        self.assertTrue(
            manifest["supported"]["new_message_request_response_callbacks"]
        )
        self.assertTrue(manifest["supported"]["same_host_posix_shared_memory_pubsub"])
        self.assertTrue(manifest["supported"]["shared_memory_to_udp_fallback"])
        self.assertTrue(manifest["supported"]["shared_memory_udp_remote_hybrid"])
        self.assertTrue(
            manifest["supported"]["middleware_owned_loaned_messages_introspection_c_cpp"]
        )
        self.assertNotIn("loaned_messages", manifest["unsupported"])
        self.assertTrue(
            manifest["supported"][
                "bounded_standalone_serialization_size_introspection_c_cpp"
            ]
        )
        self.assertNotIn("network_flow_endpoints", manifest["unsupported"])
        self.assertNotIn("event_callbacks", manifest["unsupported"])
        self.assertIn("qos_event_callbacks", manifest["unsupported"])
        self.assertNotIn("standalone_serialization_size", manifest["unsupported"])
        self.assertIn(
            "unbounded_standalone_serialization_size", manifest["unsupported"]
        )
        claims = manifest["claim_boundaries"]
        self.assertTrue(claims["docker_two_container_shared_memory_100kb"])
        self.assertTrue(claims["docker_shared_memory_udp_hybrid_dedup"])
        self.assertTrue(claims["docker_loaned_message_lifecycle_c_cpp"])
        self.assertFalse(claims["zero_copy_loaned_message_claim"])
        self.assertTrue(claims["native_ns3_wifi_mobility_matrix_8_16_32_3seed"])
        self.assertTrue(claims["native_ns3_wifi_roaming_matrix_8_16_32_3seed"])
        self.assertTrue(claims["ns3_wifi_model_claim"])
        self.assertTrue(claims["ns3_mobility_model_claim"])
        self.assertTrue(claims["ns3_roaming_handoff_claim"])
        self.assertFalse(claims["high_fidelity_wireless_simulator_claim"])
        cmake = (PKG / "CMakeLists.txt").read_text()
        self.assertIn("FILES capabilities.json", cmake)

    def test_identifier_library_exports_initial_rmw_symbols(self) -> None:
        compiler = shutil.which("c++")
        if compiler is None:
            self.skipTest("c++ compiler is not available")
        with tempfile.TemporaryDirectory() as tmp:
            library = Path(tmp) / "librmw_fleetqox_cpp.so"
            subprocess.run(
                [
                    compiler,
                    "-std=c++17",
                    "-shared",
                    "-fPIC",
                    str(PKG / "src" / "rmw_identifier.cpp"),
                    "-o",
                    str(library),
                ],
                check=True,
                cwd=ROOT,
            )
            loaded = ctypes.CDLL(str(library))
            loaded.rmw_get_implementation_identifier.restype = ctypes.c_char_p
            loaded.rmw_get_serialization_format.restype = ctypes.c_char_p
            self.assertEqual(
                loaded.rmw_get_implementation_identifier().decode(),
                "rmw_fleetqox_cpp",
            )
            self.assertEqual(
                loaded.rmw_get_serialization_format().decode(),
                "fleetrmw.introspection_c.v1",
            )


if __name__ == "__main__":
    unittest.main()

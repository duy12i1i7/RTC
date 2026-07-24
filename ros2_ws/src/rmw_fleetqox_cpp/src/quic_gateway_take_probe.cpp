#include "rmw_fleetqox_cpp/data_frame.hpp"
#include "rmw_fleetqox_cpp/quic_gateway_transport.hpp"

#include <cstdint>
#include <iostream>
#include <sstream>
#include <string>

namespace
{

std::string json_escape(const std::string & value)
{
  std::ostringstream out;
  for (const char c : value) {
    if (c == '\\' || c == '"') {
      out << '\\' << c;
    } else if (c == '\n') {
      out << "\\n";
    } else {
      out << c;
    }
  }
  return out.str();
}

rmw_fleetqox_cpp::DataFrame expected_frame()
{
  rmw_fleetqox_cpp::DataFrame frame;
  frame.robot_id = "robot_quic_take_0001";
  frame.topic = "/fleetqox/quic_gateway_take_probe";
  frame.publisher_id = "fpub-quic-gateway-take-0001";
  frame.source_sequence_number = 23;
  frame.source_timestamp_ns = 23000000;
  const std::string payload = "fleetqox-quic-gateway-take-v1";
  frame.serialized_payload.assign(payload.begin(), payload.end());
  return frame;
}

}  // namespace

int main()
{
  rmw_fleetqox_cpp::QuicGatewayTransport transport;
  const bool configured = transport.configure_from_environment();
  std::string downloaded_payload;
  const bool received = configured && transport.receive(&downloaded_payload);
  const auto expected = expected_frame();
  const std::string expected_payload = rmw_fleetqox_cpp::encode_data_frame(expected);
  const auto decoded = rmw_fleetqox_cpp::decode_data_frame(downloaded_payload);
  const bool decoded_ok =
    decoded.has_value() &&
    decoded->robot_id == expected.robot_id &&
    decoded->topic == expected.topic &&
    decoded->publisher_id == expected.publisher_id &&
    decoded->source_sequence_number == expected.source_sequence_number &&
    decoded->source_timestamp_ns == expected.source_timestamp_ns &&
    decoded->serialized_payload == expected.serialized_payload;
  const bool payload_integrity_ok = downloaded_payload == expected_payload;
  const bool ok =
    configured &&
    received &&
    payload_integrity_ok &&
    decoded_ok &&
    transport.frames_received() == 1 &&
    transport.bytes_received() == downloaded_payload.size() &&
    transport.frames_failed() == 0 &&
    transport.last_exit_code() == 0;

  std::cout << "{\"schema_version\":\"fleetrmw.quic_gateway_take_probe.v1\",";
  std::cout << "\"status\":\"" << (ok ? "ok" : "failed") << "\",";
  std::cout << "\"configured\":" << (configured ? "true" : "false") << ",";
  std::cout << "\"received\":" << (received ? "true" : "false") << ",";
  std::cout << "\"endpoint_uri\":\"" << json_escape(transport.endpoint_uri()) << "\",";
  std::cout << "\"received_bytes\":" << downloaded_payload.size() << ",";
  std::cout << "\"expected_bytes\":" << expected_payload.size() << ",";
  std::cout << "\"quic_gateway_frames_received\":" << transport.frames_received() << ",";
  std::cout << "\"quic_gateway_bytes_received\":" << transport.bytes_received() << ",";
  std::cout << "\"quic_gateway_frames_failed\":" << transport.frames_failed() << ",";
  std::cout << "\"quic_gateway_last_exit_code\":" << transport.last_exit_code() << ",";
  std::cout << "\"payload_integrity_ok\":" << (payload_integrity_ok ? "true" : "false") << ",";
  std::cout << "\"decoded_frame_ok\":" << (decoded_ok ? "true" : "false") << ",";
  if (decoded.has_value()) {
    std::cout << "\"decoded_robot_id\":\"" << json_escape(decoded->robot_id) << "\",";
    std::cout << "\"decoded_topic\":\"" << json_escape(decoded->topic) << "\",";
    std::cout << "\"decoded_publisher_id\":\"" << json_escape(decoded->publisher_id) << "\",";
    std::cout << "\"decoded_source_sequence_number\":" <<
      decoded->source_sequence_number << ",";
    std::cout << "\"decoded_source_timestamp_ns\":" << decoded->source_timestamp_ns << ",";
  }
  std::cout << "\"quic_gateway_take_path_download\":true,";
  std::cout << "\"download_path_scope\":\"ngtcp2_gtls_quic_tls_h3_get_fleetrmw_frame\",";
  std::cout << "\"subprocess_backed\":true,";
  std::cout << "\"rmw_take_path_integrated\":false,";
  std::cout << "\"production_quic_backend\":false,";
  std::cout << "\"full_bidirectional_quic_backend\":false";
  const std::string error = transport.error();
  if (!error.empty()) {
    std::cout << ",\"error\":\"" << json_escape(error) << "\"";
  }
  std::cout << "}\n";
  return ok ? 0 : 1;
}

#include "rmw_fleetqox_cpp/data_frame.hpp"
#include "rmw_fleetqox_cpp/quic_gateway_transport.hpp"

#include <cstdint>
#include <cstdlib>
#include <iostream>
#include <sstream>
#include <string>
#include <vector>

namespace
{

bool truthy(const char * name)
{
  const char * raw = std::getenv(name);
  if (raw == nullptr) {
    return false;
  }
  const std::string value(raw);
  return value == "1" || value == "true" || value == "yes";
}

std::string json_escape(const std::string & value)
{
  std::ostringstream out;
  for (const char character : value) {
    if (character == '\\' || character == '"') {
      out << '\\' << character;
    } else if (character == '\n') {
      out << "\\n";
    } else if (character == '\r') {
      out << "\\r";
    } else if (static_cast<unsigned char>(character) < 0x20) {
      out << '?';
    } else {
      out << character;
    }
  }
  return out.str();
}

}  // namespace

int main()
{
  const bool expect_success = truthy("FLEETQOX_NATIVE_PATH_EXPECT_SUCCESS");
  const std::string text = "fleetqox-native-path-frame";
  const std::string frame = rmw_fleetqox_cpp::encode_data_frame(
    rmw_fleetqox_cpp::DataFrame{
      "native-path-robot",
      "/fleetqox/native_path",
      "mtls-publisher",
      1,
      1000000,
      std::vector<std::uint8_t>(text.begin(), text.end()),
      42,
      "std_msgs/msg/String",
      "control",
      20.0,
      0.0,
      0.0,
      0.7,
      false,
      0});

  rmw_fleetqox_cpp::QuicGatewayTransport transport;
  const bool transport_configured = transport.configure_from_environment();
  const bool send_success = transport_configured && transport.send(frame);
  const std::string error = transport.error();
  const bool expected_result = send_success == expect_success;
  const bool expected_rejection =
    !expect_success && error.find("HTTP/3 response status 429") != std::string::npos;
  const bool counters_ok =
    transport.connections_created() == 1 &&
    transport.handshakes_completed() == 1 &&
    transport.streams_opened() == 1 &&
    transport.frames_sent() == (expect_success ? 1U : 0U) &&
    transport.frames_failed() == (expect_success ? 0U : 1U);
  const bool inprocess =
    transport.backend_name() == "inprocess" && !transport.subprocess_backed();
  const bool ok =
    transport_configured && expected_result &&
    (expect_success || expected_rejection) && counters_ok && inprocess;

  std::cout << "{\"schema_version\":\"fleetrmw.quic_native_path_observation_probe.v1\",";
  std::cout << "\"status\":\"" << (ok ? "ok" : "failed") << "\",";
  std::cout << "\"expected_success\":" << (expect_success ? "true" : "false") << ",";
  std::cout << "\"send_success\":" << (send_success ? "true" : "false") << ",";
  std::cout << "\"expected_qox_rejection\":" <<
    (expected_rejection ? "true" : "false") << ",";
  std::cout << "\"connections_created\":" << transport.connections_created() << ",";
  std::cout << "\"handshakes_completed\":" << transport.handshakes_completed() << ",";
  std::cout << "\"streams_opened\":" << transport.streams_opened() << ",";
  std::cout << "\"frames_sent\":" << transport.frames_sent() << ",";
  std::cout << "\"frames_failed\":" << transport.frames_failed() << ",";
  std::cout << "\"external_observation_request_sent\":false,";
  std::cout << "\"frame_qoe_debt\":0.0,\"frame_criticality\":0.7,";
  std::cout << "\"mutual_tls_client_authentication_required\":true,";
  std::cout << "\"error\":\"" << json_escape(error) << "\",";
  std::cout << "\"subprocess_backed\":false,\"production_readiness\":false}" << std::endl;
  transport.stop();
  return ok ? 0 : 1;
}

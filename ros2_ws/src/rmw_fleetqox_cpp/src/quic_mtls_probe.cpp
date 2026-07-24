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

bool configured(const char * name)
{
  const char * raw = std::getenv(name);
  return raw != nullptr && raw[0] != '\0';
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
  const bool expect_success = truthy("FLEETQOX_RMW_QUIC_MTLS_EXPECT_SUCCESS");
  const bool expect_authorization_failure =
    truthy("FLEETQOX_RMW_QUIC_MTLS_EXPECT_AUTHORIZATION_FAILURE");
  const bool client_certificate_configured =
    configured("FLEETQOX_RMW_QUIC_CLIENT_CERT_FILE") &&
    configured("FLEETQOX_RMW_QUIC_CLIENT_KEY_FILE");
  const std::string text = "fleetqox-mtls-frame";
  const std::vector<std::uint8_t> payload(text.begin(), text.end());
  const std::string frame = rmw_fleetqox_cpp::encode_data_frame(
    rmw_fleetqox_cpp::DataFrame{
      "mtls-robot",
      "/fleetqox/mtls",
      "mtls-publisher",
      1,
      1000000,
      payload,
      42,
      "std_msgs/msg/String"});

  rmw_fleetqox_cpp::QuicGatewayTransport transport;
  const bool transport_configured = transport.configure_from_environment();
  const bool send_success = transport_configured && transport.send(frame);
  const std::string error = transport.error();
  const bool positive_ok =
    expect_success && client_certificate_configured && send_success &&
    transport.connections_created() == 1 && transport.handshakes_completed() == 1 &&
    transport.streams_opened() == 1 && transport.frames_sent() == 1 &&
    transport.frames_failed() == 0;
  const bool negative_ok =
    !expect_success && transport_configured && !send_success &&
    transport.connections_created() == 1 && transport.frames_sent() == 0 &&
    transport.frames_failed() == 1 && !error.empty();
  const bool authorization_fail_closed =
    negative_ok && expect_authorization_failure &&
    error.find("HTTP/3 response status 403") != std::string::npos;
  const bool client_auth_fail_closed = negative_ok && !expect_authorization_failure;
  const bool ok = (positive_ok || negative_ok) &&
    transport.backend_name() == "inprocess" && !transport.subprocess_backed();

  std::cout << "{\"schema_version\":\"fleetrmw.quic_mtls_probe.v1\",";
  std::cout << "\"status\":\"" << (ok ? "ok" : "failed") << "\",";
  std::cout << "\"expected_success\":" << (expect_success ? "true" : "false") << ",";
  std::cout << "\"expected_authorization_failure\":" <<
    (expect_authorization_failure ? "true" : "false") << ",";
  std::cout << "\"transport_configured\":" <<
    (transport_configured ? "true" : "false") << ",";
  std::cout << "\"client_certificate_configured\":" <<
    (client_certificate_configured ? "true" : "false") << ",";
  std::cout << "\"send_success\":" << (send_success ? "true" : "false") << ",";
  std::cout << "\"client_auth_fail_closed\":" <<
    (client_auth_fail_closed ? "true" : "false") << ",";
  std::cout << "\"authorization_fail_closed\":" <<
    (authorization_fail_closed ? "true" : "false") << ",";
  std::cout << "\"connections_created\":" << transport.connections_created() << ",";
  std::cout << "\"handshakes_completed\":" << transport.handshakes_completed() << ",";
  std::cout << "\"streams_opened\":" << transport.streams_opened() << ",";
  std::cout << "\"frames_sent\":" << transport.frames_sent() << ",";
  std::cout << "\"frames_failed\":" << transport.frames_failed() << ",";
  std::cout << "\"error\":\"" << json_escape(error) << "\",";
  std::cout << "\"mutual_tls_client_authentication_claim\":" <<
    (positive_ok ? "true" : "false") << ",";
  std::cout << "\"tls_peer_verification_required\":true,";
  std::cout << "\"subprocess_backed\":false,";
  std::cout << "\"production_readiness\":false}" << std::endl;
  transport.stop();
  return ok ? 0 : 1;
}

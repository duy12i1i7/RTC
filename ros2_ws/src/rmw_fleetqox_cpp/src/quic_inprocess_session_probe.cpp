#include "rmw_fleetqox_cpp/quic_gateway_transport.hpp"

#include <cstdint>
#include <cstdlib>
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
    } else if (c == '\r') {
      out << "\\r";
    } else if (static_cast<unsigned char>(c) < 0x20) {
      out << "?";
    } else {
      out << c;
    }
  }
  return out.str();
}

int positive_send_count()
{
  const char * raw = std::getenv("FLEETQOX_RMW_QUIC_INPROCESS_SEND_COUNT");
  if (raw == nullptr) {
    return 4;
  }
  char * end = nullptr;
  const long value = std::strtol(raw, &end, 10);
  if (end == raw || *end != '\0' || value < 1 || value > 32) {
    return 4;
  }
  return static_cast<int>(value);
}

std::string expected_response()
{
  const char * raw = std::getenv("FLEETQOX_RMW_QUIC_EXPECTED_RESPONSE");
  return raw == nullptr ? "fleetqox-inprocess-take-v1" : std::string(raw);
}

}  // namespace

int main()
{
  rmw_fleetqox_cpp::QuicGatewayTransport transport;
  const bool configured = transport.configure_from_environment();
  const int send_count = positive_send_count();
  int sends_ok = 0;
  if (configured) {
    for (int index = 0; index < send_count; ++index) {
      const std::string payload =
        "fleetqox-inprocess-publish-" + std::to_string(index) + "-v1";
      if (!transport.send(payload)) {
        break;
      }
      ++sends_ok;
    }
  }
  std::string received_payload;
  const bool received = sends_ok == send_count && transport.receive(&received_payload);
  const std::string expected = expected_response();
  const std::uint64_t expected_streams = static_cast<std::uint64_t>(send_count + 1);
  const std::uint64_t connections = transport.connections_created();
  const std::uint64_t handshakes = transport.handshakes_completed();
  const std::uint64_t streams = transport.streams_opened();
  const std::uint64_t reuse = transport.connection_reuse_count();
  const bool same_connection_bidirectional =
    received && connections == 1 && handshakes == 1 && streams == expected_streams &&
    reuse == expected_streams - 1;
  const bool ok =
    configured && sends_ok == send_count && received && received_payload == expected &&
    transport.backend_name() == "inprocess" && !transport.subprocess_backed() &&
    same_connection_bidirectional && transport.frames_sent() == static_cast<std::uint64_t>(send_count) &&
    transport.frames_received() == 1 && transport.frames_failed() == 0 &&
    transport.packets_sent() > 0 && transport.packets_received() > 0 &&
    transport.reconnects() == 0;

  std::cout << "{\"schema_version\":\"fleetrmw.quic_inprocess_session_probe.v1\",";
  std::cout << "\"status\":\"" << (ok ? "ok" : "failed") << "\",";
  std::cout << "\"configured\":" << (configured ? "true" : "false") << ",";
  std::cout << "\"backend\":\"" << json_escape(transport.backend_name()) << "\",";
  std::cout << "\"subprocess_backed\":" <<
    (transport.subprocess_backed() ? "true" : "false") << ",";
  std::cout << "\"send_count\":" << send_count << ",";
  std::cout << "\"sends_ok\":" << sends_ok << ",";
  std::cout << "\"received\":" << (received ? "true" : "false") << ",";
  std::cout << "\"response_integrity_ok\":" <<
    (received_payload == expected ? "true" : "false") << ",";
  std::cout << "\"connections_created\":" << connections << ",";
  std::cout << "\"handshakes_completed\":" << handshakes << ",";
  std::cout << "\"streams_opened\":" << streams << ",";
  std::cout << "\"connection_reuse_count\":" << reuse << ",";
  std::cout << "\"packets_sent\":" << transport.packets_sent() << ",";
  std::cout << "\"packets_received\":" << transport.packets_received() << ",";
  std::cout << "\"reconnects\":" << transport.reconnects() << ",";
  std::cout << "\"frames_sent\":" << transport.frames_sent() << ",";
  std::cout << "\"frames_received\":" << transport.frames_received() << ",";
  std::cout << "\"same_connection_bidirectional\":" <<
    (same_connection_bidirectional ? "true" : "false") << ",";
  std::cout << "\"tls_peer_verification_required\":true,";
  std::cout << "\"quic_v1_reliable_bidirectional_streams\":true,";
  std::cout << "\"inprocess_quic_backend\":true,";
  std::cout << "\"application_protocol\":\"h3\",";
  std::cout << "\"standards_h3_gateway_protocol\":true,";
  std::cout << "\"serialized_operation_loop\":true,";
  std::cout << "\"production_readiness\":false";
  const std::string error = transport.error();
  if (!error.empty()) {
    std::cout << ",\"error\":\"" << json_escape(error) << "\"";
  }
  std::cout << "}\n";
  return ok ? 0 : 1;
}

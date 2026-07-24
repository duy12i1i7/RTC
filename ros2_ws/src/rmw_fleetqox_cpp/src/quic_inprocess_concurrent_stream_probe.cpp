#include "rmw_fleetqox_cpp/quic_gateway_transport.hpp"

#include <cstdint>
#include <cstdlib>
#include <iostream>
#include <sstream>
#include <string>

namespace
{

std::string environment_or(const char * name, const char * fallback)
{
  const char * value = std::getenv(name);
  return value == nullptr ? std::string(fallback) : std::string(value);
}

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
      out << '?';
    } else {
      out << c;
    }
  }
  return out.str();
}

}  // namespace

int main()
{
  const std::string send_payload = environment_or(
    "FLEETQOX_RMW_QUIC_CONCURRENT_SEND_PAYLOAD",
    "fleetqox-concurrent-post-v1");
  const std::string expected_response = environment_or(
    "FLEETQOX_RMW_QUIC_EXPECTED_RESPONSE",
    "fleetqox-concurrent-get-v1");

  rmw_fleetqox_cpp::QuicGatewayTransport transport;
  const bool configured = transport.configure_from_environment();
  std::string received_payload;
  const bool exchanged = configured &&
    transport.send_and_receive(send_payload, &received_payload);
  const std::uint64_t connections = transport.connections_created();
  const std::uint64_t handshakes = transport.handshakes_completed();
  const std::uint64_t streams = transport.streams_opened();
  const std::uint64_t reuse = transport.connection_reuse_count();
  const std::uint64_t pairs = transport.concurrent_stream_pairs();
  const std::uint64_t max_concurrent = transport.max_concurrent_request_streams();
  const bool concurrent_pair_ok =
    exchanged && connections == 1 && handshakes == 1 && streams == 2 &&
    reuse == 1 && pairs == 1 && max_concurrent >= 2 &&
    transport.reconnects() == 0;
  const bool response_ok = received_payload == expected_response;
  const bool ok =
    configured && exchanged && response_ok && concurrent_pair_ok &&
    transport.backend_name() == "inprocess" && !transport.subprocess_backed() &&
    transport.frames_sent() == 1 && transport.frames_received() == 1 &&
    transport.frames_failed() == 0 && transport.packets_sent() > 0 &&
    transport.packets_received() > 0;

  std::cout <<
    "{\"schema_version\":\"fleetrmw.quic_inprocess_concurrent_stream_probe.v1\",";
  std::cout << "\"status\":\"" << (ok ? "ok" : "failed") << "\",";
  std::cout << "\"configured\":" << (configured ? "true" : "false") << ",";
  std::cout << "\"backend\":\"" << json_escape(transport.backend_name()) << "\",";
  std::cout << "\"subprocess_backed\":" <<
    (transport.subprocess_backed() ? "true" : "false") << ",";
  std::cout << "\"exchange_ok\":" << (exchanged ? "true" : "false") << ",";
  std::cout << "\"response_integrity_ok\":" << (response_ok ? "true" : "false") << ",";
  std::cout << "\"connections_created\":" << connections << ",";
  std::cout << "\"handshakes_completed\":" << handshakes << ",";
  std::cout << "\"streams_opened\":" << streams << ",";
  std::cout << "\"connection_reuse_count\":" << reuse << ",";
  std::cout << "\"concurrent_stream_pairs\":" << pairs << ",";
  std::cout << "\"max_concurrent_request_streams\":" << max_concurrent << ",";
  std::cout << "\"packets_sent\":" << transport.packets_sent() << ",";
  std::cout << "\"packets_received\":" << transport.packets_received() << ",";
  std::cout << "\"reconnects\":" << transport.reconnects() << ",";
  std::cout << "\"frames_sent\":" << transport.frames_sent() << ",";
  std::cout << "\"frames_received\":" << transport.frames_received() << ",";
  std::cout << "\"concurrent_post_get_stream_pair\":" <<
    (concurrent_pair_ok ? "true" : "false") << ",";
  std::cout << "\"same_connection_full_duplex_streams\":true,";
  std::cout << "\"multi_threaded_rmw_api_claim\":false,";
  std::cout << "\"tls_peer_verification_required\":true,";
  std::cout << "\"application_protocol\":\"h3\",";
  std::cout << "\"production_readiness\":false";
  const std::string error = transport.error();
  if (!error.empty()) {
    std::cout << ",\"error\":\"" << json_escape(error) << "\"";
  }
  std::cout << "}\n";
  return ok ? 0 : 1;
}

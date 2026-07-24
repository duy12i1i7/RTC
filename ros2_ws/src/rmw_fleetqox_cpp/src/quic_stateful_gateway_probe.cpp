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

std::string environment_or_empty(const char * name)
{
  const char * value = std::getenv(name);
  return value == nullptr ? std::string{} : std::string(value);
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

std::string replace_consumer(const std::string & uri, const std::string & consumer)
{
  const std::string marker = "consumer_id=";
  const size_t begin = uri.find(marker);
  if (begin == std::string::npos) {
    return uri + (uri.find('?') == std::string::npos ? "?" : "&") + marker + consumer;
  }
  const size_t value_begin = begin + marker.size();
  const size_t value_end = uri.find('&', value_begin);
  return uri.substr(0, value_begin) + consumer +
         (value_end == std::string::npos ? std::string{} : uri.substr(value_end));
}

std::vector<std::string> encoded_frames()
{
  std::vector<std::string> frames;
  for (std::uint64_t sequence = 1; sequence <= 3; ++sequence) {
    const std::string text = "stateful-gateway-payload-" + std::to_string(sequence);
    const std::vector<std::uint8_t> payload(text.begin(), text.end());
    frames.push_back(rmw_fleetqox_cpp::encode_data_frame(
      rmw_fleetqox_cpp::DataFrame{
        "gateway-robot-1",
        "/fleetqox/gateway",
        "stateful-gateway-publisher",
        sequence,
        static_cast<std::int64_t>(sequence * 1000000),
        payload,
        42,
        "std_msgs/msg/String"}));
  }
  return frames;
}

bool receive_exact_sequence(
  rmw_fleetqox_cpp::QuicGatewayTransport * transport,
  const std::vector<std::string> & expected)
{
  if (transport == nullptr) {
    return false;
  }
  for (const std::string & frame : expected) {
    std::string received;
    if (!transport->receive(&received) || received != frame) {
      return false;
    }
    const auto decoded = rmw_fleetqox_cpp::decode_data_frame(received);
    const auto expected_decoded = rmw_fleetqox_cpp::decode_data_frame(frame);
    if (!decoded || !expected_decoded ||
      decoded->source_sequence_number != expected_decoded->source_sequence_number ||
      decoded->serialized_payload != expected_decoded->serialized_payload)
    {
      return false;
    }
  }
  return true;
}

}  // namespace

int main()
{
  const std::string alpha_uri = environment_or_empty("FLEETQOX_RMW_QUIC_URI");
  const std::vector<std::string> frames = encoded_frames();
  rmw_fleetqox_cpp::QuicGatewayTransport alpha;
  const bool alpha_configured = !alpha_uri.empty() && alpha.configure_from_environment();
  bool alpha_published = alpha_configured;
  if (alpha_published) {
    alpha_published = alpha.send(frames[0]) && alpha.send(frames[0]) &&
      alpha.send(frames[1]) && alpha.send(frames[2]);
  }
  const bool alpha_received = alpha_published && receive_exact_sequence(&alpha, frames);
  const bool alpha_session_reused =
    alpha.connections_created() == 1 && alpha.handshakes_completed() == 1 &&
    alpha.streams_opened() == 7 && alpha.connection_reuse_count() == 6 &&
    alpha.reconnects() == 0;
  alpha.stop();

  const std::string beta_uri = replace_consumer(alpha_uri, "beta");
  const bool beta_uri_set = ::setenv("FLEETQOX_RMW_QUIC_URI", beta_uri.c_str(), 1) == 0;
  rmw_fleetqox_cpp::QuicGatewayTransport beta;
  const bool beta_configured = beta_uri_set && beta.configure_from_environment();
  const bool beta_replayed = beta_configured && receive_exact_sequence(&beta, frames);
  const bool beta_session_reused =
    beta.connections_created() == 1 && beta.handshakes_completed() == 1 &&
    beta.streams_opened() == 3 && beta.connection_reuse_count() == 2 &&
    beta.reconnects() == 0;
  beta.stop();

  const std::string invalid_uri = replace_consumer(alpha_uri, "invalid");
  const bool invalid_uri_set =
    ::setenv("FLEETQOX_RMW_QUIC_URI", invalid_uri.c_str(), 1) == 0;
  rmw_fleetqox_cpp::QuicGatewayTransport invalid;
  const bool invalid_configured = invalid_uri_set && invalid.configure_from_environment();
  const bool invalid_rejected = invalid_configured && !invalid.send("not-a-fleetrmw-frame");
  const std::string invalid_error = invalid.error();
  const bool invalid_status_propagated =
    invalid_rejected && invalid_error.find("HTTP/3 response status 400") != std::string::npos;
  invalid.stop();
  const bool uri_restored = ::setenv("FLEETQOX_RMW_QUIC_URI", alpha_uri.c_str(), 1) == 0;

  const bool ok = alpha_configured && alpha_published && alpha_received &&
    alpha_session_reused && beta_configured && beta_replayed && beta_session_reused &&
    invalid_status_propagated && uri_restored && alpha.backend_name() == "inprocess" &&
    beta.backend_name() == "inprocess" && !alpha.subprocess_backed() &&
    !beta.subprocess_backed();
  std::cout <<
    "{\"schema_version\":\"fleetrmw.quic_stateful_gateway_probe.v1\",";
  std::cout << "\"status\":\"" << (ok ? "ok" : "failed") << "\",";
  std::cout << "\"backend\":\"inprocess\",\"subprocess_backed\":false,";
  std::cout << "\"stateful_gateway_roundtrip_claim\":" <<
    (alpha_received ? "true" : "false") << ",";
  std::cout << "\"per_consumer_replay_claim\":" <<
    (beta_replayed ? "true" : "false") << ",";
  std::cout << "\"invalid_frame_http_status_fail_closed_claim\":" <<
    (invalid_status_propagated ? "true" : "false") << ",";
  std::cout << "\"published_request_count\":4,";
  std::cout << "\"unique_frame_count\":3,\"consumer_count\":2,";
  std::cout << "\"alpha_received_count\":" << (alpha_received ? 3 : 0) << ",";
  std::cout << "\"beta_received_count\":" << (beta_replayed ? 3 : 0) << ",";
  std::cout << "\"alpha_connections_created\":" << alpha.connections_created() << ",";
  std::cout << "\"alpha_handshakes_completed\":" << alpha.handshakes_completed() << ",";
  std::cout << "\"alpha_streams_opened\":" << alpha.streams_opened() << ",";
  std::cout << "\"alpha_connection_reuse_count\":" <<
    alpha.connection_reuse_count() << ",";
  std::cout << "\"beta_connections_created\":" << beta.connections_created() << ",";
  std::cout << "\"beta_handshakes_completed\":" << beta.handshakes_completed() << ",";
  std::cout << "\"beta_streams_opened\":" << beta.streams_opened() << ",";
  std::cout << "\"beta_connection_reuse_count\":" << beta.connection_reuse_count() << ",";
  std::cout << "\"invalid_error\":\"" << json_escape(invalid_error) << "\",";
  std::cout << "\"tls_peer_verification_required\":true,";
  std::cout << "\"quic_v1_h3\":true,\"production_readiness\":false}" << std::endl;
  return ok ? 0 : 1;
}

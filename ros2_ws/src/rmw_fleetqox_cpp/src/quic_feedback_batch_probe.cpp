#include "rmw_fleetqox_cpp/data_frame.hpp"
#include "rmw_fleetqox_cpp/quic_gateway_transport.hpp"

#include <cstdint>
#include <cstdlib>
#include <iomanip>
#include <iostream>
#include <sstream>
#include <string>
#include <vector>

namespace
{

constexpr const char * kTopic = "/fleetqox/closed_loop";

std::string frame(
  std::uint64_t sequence,
  const std::string & publisher_id,
  double age_ms,
  double qoe_debt,
  double criticality,
  bool repair_requested)
{
  const std::string text = "feedback-batch-" + std::to_string(sequence);
  return rmw_fleetqox_cpp::encode_data_frame(
    rmw_fleetqox_cpp::DataFrame{
      "feedback-robot",
      kTopic,
      publisher_id,
      sequence,
      static_cast<std::int64_t>(sequence * 1000000),
      std::vector<std::uint8_t>(text.begin(), text.end()),
      42,
      "std_msgs/msg/String",
      "control",
      100.0,
      age_ms,
      qoe_debt,
      criticality,
      repair_requested,
      0});
}

std::string hex_encode(const std::string & value)
{
  std::ostringstream encoded;
  encoded << std::hex << std::setfill('0');
  for (const unsigned char byte : value) {
    encoded << std::setw(2) << static_cast<unsigned int>(byte);
  }
  return encoded.str();
}

std::string batch(const std::string & first, const std::string & second)
{
  return
    "{\"schema_version\":\"fleetrmw.quic_gateway_frame_batch.v1\",\"frames\":[\"" +
    hex_encode(first) + "\",\"" + hex_encode(second) + "\"]}";
}

bool configure(
  rmw_fleetqox_cpp::QuicGatewayTransport * transport,
  const std::string & path)
{
  if (transport == nullptr) {
    return false;
  }
  const std::string uri = "https://localhost:4500" + path;
  if (::setenv("FLEETQOX_RMW_QUIC_URI", uri.c_str(), 1) != 0) {
    return false;
  }
  return transport->configure_from_environment();
}

bool receive_exact(
  rmw_fleetqox_cpp::QuicGatewayTransport * transport,
  const std::string & expected)
{
  std::string received;
  return transport != nullptr && transport->receive(&received) && received == expected;
}

}  // namespace

int main()
{
  const std::string low = frame(1, "low-publisher", 0.0, 0.0, 0.3, false);
  const std::string observed = frame(2, "observed-publisher", 0.0, 0.0, 0.3, false);
  const std::string repair_low = frame(3, "repair-low", 10.0, 0.1, 0.2, true);
  const std::string repair_high = frame(4, "repair-high", 90.0, 1.0, 1.0, true);
  const std::string observation =
    "{\"schema_version\":\"fleetrmw.quic_gateway_observation.v1\","
    "\"domain_id\":42,\"topic\":\"/fleetqox/closed_loop\","
    "\"publisher_id\":\"observed-publisher\",\"qoe_debt\":1.0,"
    "\"measured_loss\":1.0,\"measured_rtt_ms\":100.0,"
    "\"measured_jitter_ms\":100.0}";

  rmw_fleetqox_cpp::QuicGatewayTransport observation_transport;
  const bool observation_configured = configure(
    &observation_transport, "/fleetrmw/v1/observations");
  const bool observation_posted = observation_configured &&
    observation_transport.send(observation);

  rmw_fleetqox_cpp::QuicGatewayTransport batch_transport;
  const bool batch_configured = observation_posted && configure(
    &batch_transport, "/fleetrmw/v1/frame-batches");
  const bool normal_batch_posted = batch_configured &&
    batch_transport.send(batch(low, observed));
  const bool repair_batch_posted = normal_batch_posted &&
    batch_transport.send(batch(repair_low, repair_high));

  rmw_fleetqox_cpp::QuicGatewayTransport take_transport;
  const bool take_configured = repair_batch_posted && configure(
    &take_transport,
    "/fleetrmw/v1/frames?domain_id=42&topic=%2Ffleetqox%2Fclosed_loop&"
    "consumer_id=feedback-batch-consumer");
  const bool observation_adjusted_batch_priority = take_configured &&
    receive_exact(&take_transport, observed);
  const bool competing_repair_batch_priority = observation_adjusted_batch_priority &&
    receive_exact(&take_transport, repair_high);

  const std::uint64_t connections_created =
    observation_transport.connections_created() + batch_transport.connections_created() +
    take_transport.connections_created();
  const std::uint64_t handshakes_completed =
    observation_transport.handshakes_completed() + batch_transport.handshakes_completed() +
    take_transport.handshakes_completed();
  const std::uint64_t streams_opened =
    observation_transport.streams_opened() + batch_transport.streams_opened() +
    take_transport.streams_opened();
  const std::uint64_t connection_reuse_count =
    observation_transport.connection_reuse_count() + batch_transport.connection_reuse_count() +
    take_transport.connection_reuse_count();
  const bool session_reused =
    connections_created == 3 && handshakes_completed == 3 &&
    streams_opened == 5 && connection_reuse_count == 2;
  const bool inprocess =
    observation_transport.backend_name() == "inprocess" &&
    batch_transport.backend_name() == "inprocess" &&
    take_transport.backend_name() == "inprocess" &&
    !observation_transport.subprocess_backed() &&
    !batch_transport.subprocess_backed() &&
    !take_transport.subprocess_backed();
  const bool ok = observation_posted && observation_adjusted_batch_priority &&
    competing_repair_batch_priority && session_reused && inprocess;

  if (!ok) {
    std::cerr << "observation_error=" << observation_transport.error() << std::endl;
    std::cerr << "batch_error=" << batch_transport.error() << std::endl;
    std::cerr << "take_error=" << take_transport.error() << std::endl;
  }
  std::cout << "{\"schema_version\":\"fleetrmw.quic_feedback_batch_probe.v1\",";
  std::cout << "\"status\":\"" << (ok ? "ok" : "failed") << "\",";
  std::cout << "\"observation_posted\":" << (observation_posted ? "true" : "false") << ",";
  std::cout << "\"observation_adjusted_batch_priority\":" <<
    (observation_adjusted_batch_priority ? "true" : "false") << ",";
  std::cout << "\"competing_repair_batch_priority\":" <<
    (competing_repair_batch_priority ? "true" : "false") << ",";
  std::cout << "\"payloads_replayed\":" <<
    (competing_repair_batch_priority ? "true" : "false") << ",";
  std::cout << "\"connections_created\":" << connections_created << ",";
  std::cout << "\"handshakes_completed\":" << handshakes_completed << ",";
  std::cout << "\"streams_opened\":" << streams_opened << ",";
  std::cout << "\"connection_reuse_count\":" << connection_reuse_count << ",";
  std::cout << "\"closed_loop_observation_wire_claim\":" << (ok ? "true" : "false") << ",";
  std::cout << "\"score_prioritized_batch_admission_claim\":" <<
    (ok ? "true" : "false") << ",";
  std::cout << "\"competing_repair_batch_capacity_claim\":" <<
    (ok ? "true" : "false") << ",";
  std::cout << "\"tls_peer_verification_required\":true,";
  std::cout << "\"subprocess_backed\":false,\"production_readiness\":false}" << std::endl;

  observation_transport.stop();
  batch_transport.stop();
  take_transport.stop();
  return ok ? 0 : 1;
}

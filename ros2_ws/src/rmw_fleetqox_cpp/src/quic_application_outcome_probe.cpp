#include "rmw_fleetqox_cpp/data_frame.hpp"
#include "rmw_fleetqox_cpp/quic_gateway_transport.hpp"

#include <cstdint>
#include <cstdlib>
#include <iostream>
#include <string>
#include <vector>

namespace
{

constexpr const char * kTopic = "/fleetqox/application_outcome";
constexpr const char * kPublisher = "mtls-publisher";

std::string frame(std::uint64_t sequence, double criticality)
{
  const std::string text = "application-outcome-" + std::to_string(sequence);
  return rmw_fleetqox_cpp::encode_data_frame(
    rmw_fleetqox_cpp::DataFrame{
      "application-outcome-robot",
      kTopic,
      kPublisher,
      sequence,
      static_cast<std::int64_t>(sequence * 1000000),
      std::vector<std::uint8_t>(text.begin(), text.end()),
      42,
      "std_msgs/msg/String",
      "control",
      100.0,
      0.0,
      0.0,
      criticality,
      false,
      0});
}

std::string outcome(
  const std::string & publisher_id,
  std::uint64_t sequence,
  const std::string & delivered,
  const std::string & deadline_met)
{
  return
    "{\"schema_version\":\"fleetrmw.quic_gateway_application_outcome.v1\","
    "\"domain_id\":42,\"topic\":\"/fleetqox/application_outcome\","
    "\"publisher_id\":\"" + publisher_id + "\","
    "\"source_sequence_number\":" + std::to_string(sequence) + ","
    "\"delivered\":" + delivered + ",\"deadline_met\":" + deadline_met + ","
    "\"observed_latency_ms\":100.0,\"deadline_ms\":100.0,"
    "\"task_kind\":\"generic\",\"terminal_status\":\"failed\","
    "\"task_succeeded\":false}";
}

bool configure(
  rmw_fleetqox_cpp::QuicGatewayTransport * transport,
  const std::string & path)
{
  if (transport == nullptr) {
    return false;
  }
  const std::string uri = "https://localhost:4503" + path;
  if (::setenv("FLEETQOX_RMW_QUIC_URI", uri.c_str(), 1) != 0) {
    return false;
  }
  return transport->configure_from_environment();
}

bool status_error(
  const rmw_fleetqox_cpp::QuicGatewayTransport & transport,
  int status)
{
  return transport.error().find(
    "HTTP/3 response status " + std::to_string(status)) != std::string::npos;
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
  const std::string seed = frame(1, 1.0);
  const std::string low = frame(2, 0.2);

  rmw_fleetqox_cpp::QuicGatewayTransport frames;
  const bool frames_configured = configure(&frames, "/fleetrmw/v1/frames");
  const bool seed_admitted = frames_configured && frames.send(seed);
  const bool low_rejected_before_outcome = seed_admitted &&
    !frames.send(low) && status_error(frames, 429);

  rmw_fleetqox_cpp::QuicGatewayTransport outcomes;
  const bool outcomes_configured = low_rejected_before_outcome && configure(
    &outcomes, "/fleetrmw/v1/application-outcomes");
  const bool impersonation_rejected = outcomes_configured &&
    !outcomes.send(outcome("other-publisher", 1, "false", "false")) &&
    status_error(outcomes, 403);
  const bool unknown_frame_rejected = impersonation_rejected &&
    !outcomes.send(outcome(kPublisher, 99, "false", "false")) &&
    status_error(outcomes, 404);
  const bool malformed_outcome_rejected = unknown_frame_rejected &&
    !outcomes.send(outcome(kPublisher, 1, "\"false\"", "false")) &&
    status_error(outcomes, 400);
  const std::string failed_outcome = outcome(kPublisher, 1, "false", "false");
  const bool outcome_accepted = malformed_outcome_rejected &&
    outcomes.send(failed_outcome);
  const bool duplicate_outcome_idempotent = outcome_accepted &&
    outcomes.send(failed_outcome);
  const bool low_admitted_after_outcome = duplicate_outcome_idempotent &&
    frames.send(low);

  rmw_fleetqox_cpp::QuicGatewayTransport take;
  const bool take_configured = low_admitted_after_outcome && configure(
    &take,
    "/fleetrmw/v1/frames?domain_id=42&topic="
    "%2Ffleetqox%2Fapplication_outcome&consumer_id=application-outcome-probe");
  const bool payloads_replayed = take_configured &&
    receive_exact(&take, seed) && receive_exact(&take, low);

  const std::uint64_t connections_created =
    frames.connections_created() + outcomes.connections_created() +
    take.connections_created();
  const std::uint64_t handshakes_completed =
    frames.handshakes_completed() + outcomes.handshakes_completed() +
    take.handshakes_completed();
  const std::uint64_t streams_opened =
    frames.streams_opened() + outcomes.streams_opened() + take.streams_opened();
  const std::uint64_t connection_reuse_count =
    frames.connection_reuse_count() + outcomes.connection_reuse_count() +
    take.connection_reuse_count();
  const std::uint64_t reconnects =
    frames.reconnects() + outcomes.reconnects() + take.reconnects();
  const bool transport_accounting =
    connections_created == 7 && handshakes_completed == 7 &&
    streams_opened == 10 && connection_reuse_count == 3 && reconnects == 4;
  const bool inprocess =
    frames.backend_name() == "inprocess" &&
    outcomes.backend_name() == "inprocess" &&
    take.backend_name() == "inprocess" &&
    !frames.subprocess_backed() && !outcomes.subprocess_backed() &&
    !take.subprocess_backed();
  const bool ok =
    low_rejected_before_outcome && impersonation_rejected &&
    unknown_frame_rejected && malformed_outcome_rejected && outcome_accepted &&
    duplicate_outcome_idempotent && low_admitted_after_outcome &&
    payloads_replayed && transport_accounting && inprocess;

  if (!ok) {
    std::cerr << "frames_error=" << frames.error() << std::endl;
    std::cerr << "outcomes_error=" << outcomes.error() << std::endl;
    std::cerr << "take_error=" << take.error() << std::endl;
  }
  std::cout << "{\"schema_version\":"
    "\"fleetrmw.quic_application_outcome_probe.v1\",";
  std::cout << "\"status\":\"" << (ok ? "ok" : "failed") << "\",";
  std::cout << "\"seed_admitted\":" << (seed_admitted ? "true" : "false") << ",";
  std::cout << "\"low_rejected_before_outcome\":" <<
    (low_rejected_before_outcome ? "true" : "false") << ",";
  std::cout << "\"impersonation_rejected\":" <<
    (impersonation_rejected ? "true" : "false") << ",";
  std::cout << "\"unknown_frame_rejected\":" <<
    (unknown_frame_rejected ? "true" : "false") << ",";
  std::cout << "\"malformed_outcome_rejected\":" <<
    (malformed_outcome_rejected ? "true" : "false") << ",";
  std::cout << "\"outcome_accepted\":" <<
    (outcome_accepted ? "true" : "false") << ",";
  std::cout << "\"duplicate_outcome_idempotent\":" <<
    (duplicate_outcome_idempotent ? "true" : "false") << ",";
  std::cout << "\"low_admitted_after_outcome\":" <<
    (low_admitted_after_outcome ? "true" : "false") << ",";
  std::cout << "\"payloads_replayed\":" <<
    (payloads_replayed ? "true" : "false") << ",";
  std::cout << "\"connections_created\":" << connections_created << ",";
  std::cout << "\"handshakes_completed\":" << handshakes_completed << ",";
  std::cout << "\"streams_opened\":" << streams_opened << ",";
  std::cout << "\"connection_reuse_count\":" << connection_reuse_count << ",";
  std::cout << "\"reconnects\":" << reconnects << ",";
  std::cout << "\"application_outcome_qoe_debt_claim\":" <<
    (ok ? "true" : "false") << ",";
  std::cout << "\"application_task_outcome_failure_pressure_claim\":" <<
    (ok ? "true" : "false") << ",";
  std::cout << "\"tls_peer_verification_required\":true,";
  std::cout << "\"mutual_tls_required\":true,";
  std::cout << "\"subprocess_backed\":false,";
  std::cout << "\"production_readiness\":false}" << std::endl;

  frames.stop();
  outcomes.stop();
  take.stop();
  return ok ? 0 : 1;
}

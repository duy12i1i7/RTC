#include "rmw_fleetqox_cpp/data_frame.hpp"
#include "rmw_fleetqox_cpp/quic_gateway_transport.hpp"

#include <cstdint>
#include <cstdlib>
#include <iostream>
#include <string>
#include <vector>

namespace
{

constexpr const char * kTopic = "/fleetqox/durable_application_outcome";
constexpr const char * kPublisher = "mtls-publisher";

std::string frame(std::uint64_t sequence, double criticality)
{
  const std::string text = "durable-application-outcome-" + std::to_string(sequence);
  return rmw_fleetqox_cpp::encode_data_frame(
    rmw_fleetqox_cpp::DataFrame{
      "durable-application-outcome-robot",
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

std::string failed_outcome()
{
  return
    "{\"schema_version\":\"fleetrmw.quic_gateway_application_outcome.v1\","
    "\"domain_id\":42,\"topic\":\"/fleetqox/durable_application_outcome\","
    "\"publisher_id\":\"mtls-publisher\",\"source_sequence_number\":1,"
    "\"delivered\":false,\"deadline_met\":false,"
    "\"observed_latency_ms\":100.0,\"deadline_ms\":100.0}";
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

bool receive_exact(
  rmw_fleetqox_cpp::QuicGatewayTransport * transport,
  const std::string & expected)
{
  std::string received;
  return transport != nullptr && transport->receive(&received) && received == expected;
}

}  // namespace

int main(int argc, char ** argv)
{
  const std::string mode = argc > 1 ? argv[1] : "";
  if (mode != "seed" && mode != "resume") {
    std::cerr <<
      "usage: fleetrmw_quic_durable_application_outcome_failover_probe seed|resume\n";
    return 2;
  }

  const std::string seed = frame(1, 1.0);
  const std::string low = frame(2, 0.2);
  const std::string outcome = failed_outcome();
  rmw_fleetqox_cpp::QuicGatewayTransport frames;
  rmw_fleetqox_cpp::QuicGatewayTransport outcomes;
  rmw_fleetqox_cpp::QuicGatewayTransport take;

  bool seed_admitted = false;
  bool outcome_accepted = false;
  bool duplicate_outcome_idempotent = false;
  bool low_admitted_after_failover = false;
  bool payloads_replayed = false;
  if (mode == "seed") {
    seed_admitted = configure(&frames, "/fleetrmw/v1/frames") && frames.send(seed);
    outcome_accepted = seed_admitted &&
      configure(&outcomes, "/fleetrmw/v1/application-outcomes") &&
      outcomes.send(outcome);
  } else {
    duplicate_outcome_idempotent =
      configure(&outcomes, "/fleetrmw/v1/application-outcomes") &&
      outcomes.send(outcome);
    low_admitted_after_failover = duplicate_outcome_idempotent &&
      configure(&frames, "/fleetrmw/v1/frames") && frames.send(low);
    payloads_replayed = low_admitted_after_failover &&
      configure(
      &take,
      "/fleetrmw/v1/frames?domain_id=42&topic="
      "%2Ffleetqox%2Fdurable_application_outcome&consumer_id=durable-outcome-probe") &&
      receive_exact(&take, seed) && receive_exact(&take, low);
  }

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
  const bool seed_ok =
    mode == "seed" && seed_admitted && outcome_accepted &&
    connections_created == 2 && handshakes_completed == 2 &&
    streams_opened == 2 && connection_reuse_count == 0;
  const bool resume_ok =
    mode == "resume" && duplicate_outcome_idempotent &&
    low_admitted_after_failover && payloads_replayed &&
    connections_created == 3 && handshakes_completed == 3 &&
    streams_opened == 4 && connection_reuse_count == 1;
  const bool inprocess =
    frames.backend_name() == "inprocess" &&
    outcomes.backend_name() == "inprocess" &&
    !frames.subprocess_backed() && !outcomes.subprocess_backed() &&
    (mode == "seed" ||
    (take.backend_name() == "inprocess" && !take.subprocess_backed()));
  const bool ok = (seed_ok || resume_ok) && inprocess;

  if (!ok) {
    std::cerr << "frames_error=" << frames.error() << std::endl;
    std::cerr << "outcomes_error=" << outcomes.error() << std::endl;
    std::cerr << "take_error=" << take.error() << std::endl;
  }
  std::cout << "{\"schema_version\":"
    "\"fleetrmw.quic_durable_application_outcome_failover_probe.v1\",";
  std::cout << "\"status\":\"" << (ok ? "ok" : "failed") << "\",";
  std::cout << "\"mode\":\"" << mode << "\",";
  std::cout << "\"seed_admitted\":" << (seed_admitted ? "true" : "false") << ",";
  std::cout << "\"outcome_accepted\":" <<
    (outcome_accepted ? "true" : "false") << ",";
  std::cout << "\"duplicate_outcome_idempotent\":" <<
    (duplicate_outcome_idempotent ? "true" : "false") << ",";
  std::cout << "\"low_admitted_after_failover\":" <<
    (low_admitted_after_failover ? "true" : "false") << ",";
  std::cout << "\"payloads_replayed\":" <<
    (payloads_replayed ? "true" : "false") << ",";
  std::cout << "\"connections_created\":" << connections_created << ",";
  std::cout << "\"handshakes_completed\":" << handshakes_completed << ",";
  std::cout << "\"streams_opened\":" << streams_opened << ",";
  std::cout << "\"connection_reuse_count\":" << connection_reuse_count << ",";
  std::cout << "\"tls_peer_verification_required\":true,";
  std::cout << "\"mutual_tls_required\":true,";
  std::cout << "\"subprocess_backed\":false,";
  std::cout << "\"production_readiness\":false}" << std::endl;

  frames.stop();
  outcomes.stop();
  take.stop();
  return ok ? 0 : 1;
}

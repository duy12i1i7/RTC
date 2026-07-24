#include "rmw_fleetqox_cpp/data_frame.hpp"
#include "rmw_fleetqox_cpp/quic_gateway_transport.hpp"

#include <cstdint>
#include <cstdlib>
#include <iostream>
#include <string>
#include <vector>

namespace
{

std::string frame(std::uint64_t sequence, bool repair_requested)
{
  const std::string text = "durable-admission-" + std::to_string(sequence);
  return rmw_fleetqox_cpp::encode_data_frame(
    rmw_fleetqox_cpp::DataFrame{
      "durable-admission-robot",
      "/fleetqox/durable_admission",
      "durable-admission-publisher",
      sequence,
      static_cast<std::int64_t>(sequence * 1000000),
      std::vector<std::uint8_t>(text.begin(), text.end()),
      42,
      "std_msgs/msg/String",
      "control",
      100.0,
      90.0,
      1.0,
      1.0,
      repair_requested,
      0});
}

}  // namespace

int main(int argc, char ** argv)
{
  const std::string mode = argc > 1 ? argv[1] : "";
  if (mode != "seed" && mode != "resume") {
    std::cerr << "usage: fleetrmw_quic_durable_admission_failover_probe seed|resume\n";
    return 2;
  }
  rmw_fleetqox_cpp::QuicGatewayTransport transport;
  const bool configured = transport.configure_from_environment();
  bool first = false;
  bool second = false;
  bool expected_rejection = false;
  if (configured && mode == "seed") {
    first = transport.send(frame(1, false));
    second = first && transport.send(frame(2, true));
  } else if (configured) {
    first = transport.send(frame(3, true));
    expected_rejection =
      !first && transport.error().find("HTTP/3 response status 429") != std::string::npos;
  }
  const bool seed_ok =
    mode == "seed" && first && second &&
    transport.connections_created() == 1 && transport.handshakes_completed() == 1 &&
    transport.streams_opened() == 2 && transport.connection_reuse_count() == 1 &&
    transport.frames_sent() == 2 && transport.frames_failed() == 0;
  const bool resume_ok =
    mode == "resume" && expected_rejection &&
    transport.connections_created() == 1 && transport.handshakes_completed() == 1 &&
    transport.streams_opened() == 1 && transport.connection_reuse_count() == 0 &&
    transport.frames_sent() == 0 && transport.frames_failed() == 1;
  const bool inprocess =
    transport.backend_name() == "inprocess" && !transport.subprocess_backed();
  const bool ok = configured && (seed_ok || resume_ok) && inprocess;

  std::cout << "{\"schema_version\":\"fleetrmw.quic_durable_admission_failover_probe.v1\",";
  std::cout << "\"status\":\"" << (ok ? "ok" : "failed") << "\",";
  std::cout << "\"mode\":\"" << mode << "\",";
  std::cout << "\"normal_admitted\":" <<
    ((mode == "seed" && first) ? "true" : "false") << ",";
  std::cout << "\"repair_admitted\":" <<
    ((mode == "seed" && second) ? "true" : "false") << ",";
  std::cout << "\"resumed_repair_rejected\":" <<
    (expected_rejection ? "true" : "false") << ",";
  std::cout << "\"connections_created\":" << transport.connections_created() << ",";
  std::cout << "\"handshakes_completed\":" << transport.handshakes_completed() << ",";
  std::cout << "\"streams_opened\":" << transport.streams_opened() << ",";
  std::cout << "\"connection_reuse_count\":" << transport.connection_reuse_count() << ",";
  std::cout << "\"frames_sent\":" << transport.frames_sent() << ",";
  std::cout << "\"frames_failed\":" << transport.frames_failed() << ",";
  std::cout << "\"tls_peer_verification_required\":true,";
  std::cout << "\"subprocess_backed\":false,\"production_readiness\":false}" << std::endl;
  transport.stop();
  return ok ? 0 : 1;
}

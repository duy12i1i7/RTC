#include "rmw_fleetqox_cpp/data_frame.hpp"
#include "rmw_fleetqox_cpp/quic_gateway_transport.hpp"

#include <cstdint>
#include <cstdlib>
#include <iostream>
#include <string>
#include <vector>

namespace
{

std::string frame(
  std::uint64_t sequence,
  double age_ms,
  double qoe_debt,
  double criticality,
  bool repair_requested,
  std::uint64_t prior_attempts = 0)
{
  const std::string text = "qox-repair-" + std::to_string(sequence);
  return rmw_fleetqox_cpp::encode_data_frame(
    rmw_fleetqox_cpp::DataFrame{
      "qox-robot",
      "/fleetqox/qox_repair",
      "qox-publisher",
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
      prior_attempts});
}

bool receive_exact(
  rmw_fleetqox_cpp::QuicGatewayTransport * transport,
  const std::string & expected)
{
  std::string received;
  return transport != nullptr && transport->receive(&received) && received == expected;
}

bool status_error(
  const rmw_fleetqox_cpp::QuicGatewayTransport & transport,
  int status)
{
  return transport.error().find(
    "HTTP/3 response status " + std::to_string(status)) != std::string::npos;
}

}  // namespace

int main()
{
  const std::string low = frame(1, 0.0, 0.0, 0.0, false);
  const std::string high = frame(2, 80.0, 0.9, 1.0, false);
  const std::string repair_admitted = frame(3, 85.0, 1.0, 1.0, true);
  const std::string repair_deferred = frame(4, 90.0, 1.0, 1.0, true, 1);

  rmw_fleetqox_cpp::QuicGatewayTransport transport;
  const bool configured = transport.configure_from_environment();
  const bool low_score_rejected = configured && !transport.send(low) && status_error(transport, 429);
  const std::string low_score_error = transport.error();
  const bool high_score_admitted = low_score_rejected && transport.send(high);
  const bool repair_scheduler_admitted = high_score_admitted && transport.send(repair_admitted);
  const bool repair_capacity_deferred = repair_scheduler_admitted &&
    !transport.send(repair_deferred) && status_error(transport, 429);
  const bool payloads_replayed = repair_capacity_deferred &&
    receive_exact(&transport, high) && receive_exact(&transport, repair_admitted);
  const bool session_reused =
    transport.connections_created() == 3 && transport.handshakes_completed() == 3 &&
    transport.streams_opened() == 6 && transport.connection_reuse_count() == 3 &&
    transport.reconnects() == 2;
  const bool ok = payloads_replayed && session_reused &&
    transport.backend_name() == "inprocess" && !transport.subprocess_backed();
  if (!low_score_rejected) {
    std::cerr << "low_score_error=" << low_score_error << std::endl;
  }

  std::cout << "{\"schema_version\":\"fleetrmw.quic_qox_repair_probe.v1\",";
  std::cout << "\"status\":\"" << (ok ? "ok" : "failed") << "\",";
  std::cout << "\"low_score_rejected\":" <<
    (low_score_rejected ? "true" : "false") << ",";
  std::cout << "\"high_score_admitted\":" <<
    (high_score_admitted ? "true" : "false") << ",";
  std::cout << "\"repair_scheduler_admitted\":" <<
    (repair_scheduler_admitted ? "true" : "false") << ",";
  std::cout << "\"repair_capacity_deferred\":" <<
    (repair_capacity_deferred ? "true" : "false") << ",";
  std::cout << "\"payloads_replayed\":" << (payloads_replayed ? "true" : "false") << ",";
  std::cout << "\"connections_created\":" << transport.connections_created() << ",";
  std::cout << "\"handshakes_completed\":" << transport.handshakes_completed() << ",";
  std::cout << "\"streams_opened\":" << transport.streams_opened() << ",";
  std::cout << "\"connection_reuse_count\":" << transport.connection_reuse_count() << ",";
  std::cout << "\"qos_qoe_admission_repair_coupling_claim\":" <<
    (ok ? "true" : "false") << ",";
  std::cout << "\"tls_peer_verification_required\":true,";
  std::cout << "\"subprocess_backed\":false,\"production_readiness\":false}" << std::endl;
  transport.stop();
  return ok ? 0 : 1;
}

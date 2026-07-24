#include "rmw_fleetqox_cpp/data_frame.hpp"
#include "rmw_fleetqox_cpp/quic_gateway_transport.hpp"

#include <cstdint>
#include <cstdlib>
#include <iostream>
#include <string>
#include <vector>

namespace
{

constexpr const char * kTopic = "/fleetqox/durable_failover";

std::string frame(std::uint64_t sequence)
{
  const std::string text = "durable-failover-" + std::to_string(sequence);
  return rmw_fleetqox_cpp::encode_data_frame(
    rmw_fleetqox_cpp::DataFrame{
      "durable-robot",
      kTopic,
      "durable-publisher",
      sequence,
      static_cast<std::int64_t>(sequence * 1000000),
      std::vector<std::uint8_t>(text.begin(), text.end()),
      42,
      "std_msgs/msg/String"});
}

bool configure(
  rmw_fleetqox_cpp::QuicGatewayTransport * transport,
  const std::string & path)
{
  if (transport == nullptr) {
    return false;
  }
  const std::string uri = "https://localhost:4501" + path;
  return ::setenv("FLEETQOX_RMW_QUIC_URI", uri.c_str(), 1) == 0 &&
         transport->configure_from_environment();
}

bool receive_exact(
  rmw_fleetqox_cpp::QuicGatewayTransport * transport,
  const std::string & expected)
{
  std::string received;
  return transport != nullptr && transport->receive(&received) && received == expected;
}

void emit_common(
  const std::string & mode,
  bool ok,
  std::uint64_t connections,
  std::uint64_t handshakes,
  std::uint64_t streams,
  std::uint64_t reuse)
{
  std::cout << "{\"schema_version\":\"fleetrmw.quic_durable_failover_probe.v1\",";
  std::cout << "\"status\":\"" << (ok ? "ok" : "failed") << "\",";
  std::cout << "\"mode\":\"" << mode << "\",";
  std::cout << "\"connections_created\":" << connections << ",";
  std::cout << "\"handshakes_completed\":" << handshakes << ",";
  std::cout << "\"streams_opened\":" << streams << ",";
  std::cout << "\"connection_reuse_count\":" << reuse << ",";
  std::cout << "\"tls_peer_verification_required\":true,";
  std::cout << "\"subprocess_backed\":false,\"production_readiness\":false}" << std::endl;
}

}  // namespace

int main(int argc, char ** argv)
{
  const std::string mode = argc > 1 ? argv[1] : "";
  const std::string post_path =
    "/fleetrmw/v1/frames?domain_id=42&topic=%2Ffleetqox%2Fdurable_failover";
  const std::string take_path = post_path + "&consumer_id=durable-consumer";

  if (mode == "publish") {
    rmw_fleetqox_cpp::QuicGatewayTransport transport;
    const bool configured = configure(&transport, post_path);
    const bool published = configured && transport.send(frame(1)) &&
      transport.send(frame(2)) && transport.send(frame(3));
    const bool ok = published && transport.backend_name() == "inprocess" &&
      !transport.subprocess_backed() && transport.connections_created() == 1 &&
      transport.handshakes_completed() == 1 && transport.streams_opened() == 3 &&
      transport.connection_reuse_count() == 2;
    if (!ok) {
      std::cerr << "publish_error=" << transport.error() << std::endl;
    }
    emit_common(
      mode, ok, transport.connections_created(), transport.handshakes_completed(),
      transport.streams_opened(), transport.connection_reuse_count());
    transport.stop();
    return ok ? 0 : 1;
  }

  if (mode == "resume-prefix") {
    rmw_fleetqox_cpp::QuicGatewayTransport duplicate_transport;
    rmw_fleetqox_cpp::QuicGatewayTransport take_transport;
    const bool duplicate_configured = configure(&duplicate_transport, post_path);
    const bool restored_dedup_accepted = duplicate_configured &&
      duplicate_transport.send(frame(1));
    const bool take_configured = restored_dedup_accepted && configure(&take_transport, take_path);
    const bool replayed_prefix = take_configured &&
      receive_exact(&take_transport, frame(1)) && receive_exact(&take_transport, frame(2));
    const std::uint64_t connections = duplicate_transport.connections_created() +
      take_transport.connections_created();
    const std::uint64_t handshakes = duplicate_transport.handshakes_completed() +
      take_transport.handshakes_completed();
    const std::uint64_t streams = duplicate_transport.streams_opened() +
      take_transport.streams_opened();
    const std::uint64_t reuse = duplicate_transport.connection_reuse_count() +
      take_transport.connection_reuse_count();
    const bool ok = replayed_prefix && connections == 2 && handshakes == 2 &&
      streams == 3 && reuse == 1 && duplicate_transport.backend_name() == "inprocess" &&
      take_transport.backend_name() == "inprocess" &&
      !duplicate_transport.subprocess_backed() && !take_transport.subprocess_backed();
    if (!ok) {
      std::cerr << "duplicate_error=" << duplicate_transport.error() << std::endl;
      std::cerr << "prefix_take_error=" << take_transport.error() << std::endl;
    }
    emit_common(mode, ok, connections, handshakes, streams, reuse);
    duplicate_transport.stop();
    take_transport.stop();
    return ok ? 0 : 1;
  }

  if (mode == "resume-tail") {
    rmw_fleetqox_cpp::QuicGatewayTransport transport;
    const bool configured = configure(&transport, take_path);
    const bool replayed_tail = configured && receive_exact(&transport, frame(3));
    const bool ok = replayed_tail && transport.backend_name() == "inprocess" &&
      !transport.subprocess_backed() && transport.connections_created() == 1 &&
      transport.handshakes_completed() == 1 && transport.streams_opened() == 1 &&
      transport.connection_reuse_count() == 0;
    if (!ok) {
      std::cerr << "tail_take_error=" << transport.error() << std::endl;
    }
    emit_common(
      mode, ok, transport.connections_created(), transport.handshakes_completed(),
      transport.streams_opened(), transport.connection_reuse_count());
    transport.stop();
    return ok ? 0 : 1;
  }

  std::cerr << "usage: fleetrmw_quic_durable_failover_probe "
            << "publish|resume-prefix|resume-tail" << std::endl;
  return 2;
}

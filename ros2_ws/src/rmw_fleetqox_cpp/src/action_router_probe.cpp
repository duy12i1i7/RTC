#include <algorithm>
#include <array>
#include <cerrno>
#include <chrono>
#include <cstdint>
#include <cstdlib>
#include <cstring>
#include <iostream>
#include <sstream>
#include <string>
#include <thread>
#include <vector>

#include <arpa/inet.h>
#include <netdb.h>
#include <netinet/in.h>
#include <sys/socket.h>
#include <sys/time.h>
#include <unistd.h>

#include "rmw_fleetqox_cpp/data_frame.hpp"

namespace
{

constexpr size_t kMaxUdpPayloadBytes = 65507;
constexpr const char * kActionName = "/fleet/navigate";
constexpr const char * kActionType = "fleet_msgs/action/Navigate";
constexpr const char * kServerEndpoint = "fleet-action-server-1";
constexpr const char * kClientEndpoint = "fleet-action-client-1";

struct ProbeConfig
{
  std::string router{"127.0.0.1:48310"};
  std::string server_bind{"127.0.0.1:48311"};
  std::string client_bind{"127.0.0.1:48312"};
  int timeout_ms{3000};
};

std::string json_escape(const std::string & value)
{
  std::ostringstream out;
  for (const char c : value) {
    if (c == '\\' || c == '"') {
      out << '\\' << c;
    } else if (c == '\n') {
      out << "\\n";
    } else {
      out << c;
    }
  }
  return out.str();
}

bool parse_ipv4_endpoint(const std::string & endpoint, sockaddr_in * address)
{
  if (address == nullptr) {
    return false;
  }
  const auto separator = endpoint.rfind(':');
  if (separator == std::string::npos || separator == 0 || separator + 1 >= endpoint.size()) {
    return false;
  }

  const std::string host = endpoint.substr(0, separator);
  const std::string port_text = endpoint.substr(separator + 1);
  char * port_end = nullptr;
  errno = 0;
  const long port = std::strtol(port_text.c_str(), &port_end, 10);
  if (errno != 0 || port_end == port_text.c_str() || *port_end != '\0' || port < 0 || port > 65535) {
    return false;
  }

  sockaddr_in parsed{};
  parsed.sin_family = AF_INET;
  parsed.sin_port = htons(static_cast<std::uint16_t>(port));
  if (::inet_pton(AF_INET, host.c_str(), &parsed.sin_addr) != 1) {
    addrinfo hints{};
    hints.ai_family = AF_INET;
    hints.ai_socktype = SOCK_DGRAM;
    addrinfo * result = nullptr;
    if (::getaddrinfo(host.c_str(), nullptr, &hints, &result) != 0 || result == nullptr) {
      return false;
    }
    parsed.sin_addr = reinterpret_cast<sockaddr_in *>(result->ai_addr)->sin_addr;
    ::freeaddrinfo(result);
  }
  *address = parsed;
  return true;
}

ProbeConfig parse_args(int argc, char ** argv)
{
  ProbeConfig config;
  for (int i = 1; i < argc; ++i) {
    const std::string arg = argv[i];
    if (arg == "--router" && i + 1 < argc) {
      config.router = argv[++i];
    } else if (arg == "--server-bind" && i + 1 < argc) {
      config.server_bind = argv[++i];
    } else if (arg == "--client-bind" && i + 1 < argc) {
      config.client_bind = argv[++i];
    } else if (arg == "--timeout-ms" && i + 1 < argc) {
      config.timeout_ms = std::stoi(argv[++i]);
    }
  }
  return config;
}

int open_bound_socket(const sockaddr_in & bind_address)
{
  const int fd = ::socket(AF_INET, SOCK_DGRAM, 0);
  if (fd < 0) {
    return -1;
  }
  int reuse = 1;
  (void)::setsockopt(fd, SOL_SOCKET, SO_REUSEADDR, &reuse, sizeof(reuse));
  timeval timeout{};
  timeout.tv_sec = 0;
  timeout.tv_usec = 50000;
  if (::setsockopt(fd, SOL_SOCKET, SO_RCVTIMEO, &timeout, sizeof(timeout)) != 0) {
    ::close(fd);
    return -1;
  }
  if (::bind(fd, reinterpret_cast<const sockaddr *>(&bind_address), sizeof(bind_address)) != 0) {
    ::close(fd);
    return -1;
  }
  return fd;
}

bool send_payload(int fd, const sockaddr_in & target, const std::string & payload)
{
  const auto sent = ::sendto(
    fd,
    payload.data(),
    payload.size(),
    0,
    reinterpret_cast<const sockaddr *>(&target),
    sizeof(target));
  return sent >= 0 && static_cast<size_t>(sent) == payload.size();
}

std::int64_t monotonic_timestamp_ns()
{
  const auto now = std::chrono::steady_clock::now().time_since_epoch();
  return std::chrono::duration_cast<std::chrono::nanoseconds>(now).count();
}

rmw_fleetqox_cpp::GraphAdvertisement make_action_graph(
  const std::string & role,
  const std::string & endpoint_id)
{
  rmw_fleetqox_cpp::GraphAdvertisement advertisement{};
  advertisement.endpoint_id = endpoint_id;
  advertisement.action = "add";
  advertisement.entity_kind = role;
  advertisement.node_name = role == "action_server" ? "navigator" : "dispatcher";
  advertisement.node_namespace = role == "action_server" ? "/robot_1" : "/fleet";
  advertisement.topic = kActionName;
  advertisement.type_name = kActionType;
  advertisement.endpoint_gid = endpoint_id + "-gid";
  advertisement.lease_ms = 5000;
  return advertisement;
}

rmw_fleetqox_cpp::ActionFrame make_action_frame(
  const std::string & role,
  const std::string & endpoint_id,
  std::int64_t sequence_id)
{
  rmw_fleetqox_cpp::ActionFrame frame{};
  frame.role = role;
  frame.action_name = kActionName;
  frame.type_name = kActionType;
  frame.endpoint_id = endpoint_id;
  frame.goal_id = "goal-0001";
  frame.sequence_id = sequence_id;
  frame.source_timestamp_ns = monotonic_timestamp_ns();
  frame.lifespan_ns = 1000000000;
  frame.serialized_payload = {
    static_cast<std::uint8_t>(sequence_id & 0xFF),
    static_cast<std::uint8_t>((sequence_id + 1) & 0xFF)};
  return frame;
}

bool contains_role(const std::vector<std::string> & roles, const std::string & role)
{
  return std::find(roles.begin(), roles.end(), role) != roles.end();
}

void record_role(std::vector<std::string> * roles, const std::string & role)
{
  if (roles != nullptr && !contains_role(*roles, role)) {
    roles->push_back(role);
  }
}

void drain_action_frames(int fd, std::vector<std::string> * roles)
{
  std::array<char, kMaxUdpPayloadBytes> buffer{};
  for (;;) {
    sockaddr_in source_address{};
    socklen_t source_length = sizeof(source_address);
    const auto size = ::recvfrom(
      fd,
      buffer.data(),
      buffer.size(),
      0,
      reinterpret_cast<sockaddr *>(&source_address),
      &source_length);
    if (size < 0) {
      if (errno == EINTR) {
        continue;
      }
      return;
    }
    if (size == 0) {
      continue;
    }
    const std::string encoded_frame(buffer.data(), static_cast<size_t>(size));
    const auto decoded = rmw_fleetqox_cpp::decode_action_frame(encoded_frame);
    if (!decoded || decoded->action_name != kActionName) {
      continue;
    }
    record_role(roles, decoded->role);
  }
}

bool has_roles(
  const std::vector<std::string> & observed,
  const std::vector<std::string> & expected)
{
  return std::all_of(
    expected.begin(),
    expected.end(),
    [&](const std::string & role) {
      return contains_role(observed, role);
    });
}

void print_probe_json(
  const std::string & status,
  const ProbeConfig & config,
  const std::vector<std::string> & server_roles,
  const std::vector<std::string> & client_roles,
  const std::string & error = "")
{
  std::cout << "{\"schema_version\":\"fleetrmw.rmw_action_router_probe.v1\",";
  std::cout << "\"status\":\"" << json_escape(status) << "\",";
  std::cout << "\"router\":\"" << json_escape(config.router) << "\",";
  std::cout << "\"server_bind\":\"" << json_escape(config.server_bind) << "\",";
  std::cout << "\"client_bind\":\"" << json_escape(config.client_bind) << "\",";
  std::cout << "\"action_name\":\"" << json_escape(kActionName) << "\",";
  std::cout << "\"server_received_roles\":[";
  for (size_t i = 0; i < server_roles.size(); ++i) {
    if (i > 0) {
      std::cout << ",";
    }
    std::cout << "\"" << json_escape(server_roles[i]) << "\"";
  }
  std::cout << "],";
  std::cout << "\"client_received_roles\":[";
  for (size_t i = 0; i < client_roles.size(); ++i) {
    if (i > 0) {
      std::cout << ",";
    }
    std::cout << "\"" << json_escape(client_roles[i]) << "\"";
  }
  std::cout << "],";
  std::cout << "\"expected_server_roles\":[\"goal\",\"cancel\"],";
  std::cout << "\"expected_client_roles\":[\"feedback\",\"status\",\"result\"]";
  if (!error.empty()) {
    std::cout << ",\"error\":\"" << json_escape(error) << "\"";
  }
  std::cout << "}" << std::endl;
}

}  // namespace

int main(int argc, char ** argv)
{
  const ProbeConfig config = parse_args(argc, argv);

  sockaddr_in router_address{};
  sockaddr_in server_address{};
  sockaddr_in client_address{};
  if (!parse_ipv4_endpoint(config.router, &router_address) ||
    !parse_ipv4_endpoint(config.server_bind, &server_address) ||
    !parse_ipv4_endpoint(config.client_bind, &client_address))
  {
    print_probe_json("invalid_config", config, {}, {}, "invalid endpoint");
    return 1;
  }

  const int server_fd = open_bound_socket(server_address);
  if (server_fd < 0) {
    print_probe_json("socket_failed", config, {}, {}, "server socket failed");
    return 1;
  }
  const int client_fd = open_bound_socket(client_address);
  if (client_fd < 0) {
    ::close(server_fd);
    print_probe_json("socket_failed", config, {}, {}, "client socket failed");
    return 1;
  }

  bool sent = true;
  sent = sent && send_payload(
    server_fd,
    router_address,
    rmw_fleetqox_cpp::encode_graph_advertisement(
      make_action_graph("action_server", kServerEndpoint)));
  sent = sent && send_payload(
    client_fd,
    router_address,
    rmw_fleetqox_cpp::encode_graph_advertisement(
      make_action_graph("action_client", kClientEndpoint)));
  std::this_thread::sleep_for(std::chrono::milliseconds(100));
  sent = sent && send_payload(
    client_fd,
    router_address,
    rmw_fleetqox_cpp::encode_action_frame(make_action_frame("goal", kClientEndpoint, 1)));
  sent = sent && send_payload(
    server_fd,
    router_address,
    rmw_fleetqox_cpp::encode_action_frame(make_action_frame("feedback", kClientEndpoint, 2)));
  sent = sent && send_payload(
    server_fd,
    router_address,
    rmw_fleetqox_cpp::encode_action_frame(make_action_frame("status", kClientEndpoint, 3)));
  sent = sent && send_payload(
    server_fd,
    router_address,
    rmw_fleetqox_cpp::encode_action_frame(make_action_frame("result", kClientEndpoint, 4)));
  sent = sent && send_payload(
    client_fd,
    router_address,
    rmw_fleetqox_cpp::encode_action_frame(make_action_frame("cancel", kClientEndpoint, 5)));

  std::vector<std::string> server_roles;
  std::vector<std::string> client_roles;
  const auto deadline =
    std::chrono::steady_clock::now() + std::chrono::milliseconds(config.timeout_ms);
  while (std::chrono::steady_clock::now() < deadline) {
    drain_action_frames(server_fd, &server_roles);
    drain_action_frames(client_fd, &client_roles);
    if (has_roles(server_roles, {"goal", "cancel"}) &&
      has_roles(client_roles, {"feedback", "status", "result"}))
    {
      break;
    }
  }

  ::close(server_fd);
  ::close(client_fd);

  const bool ok = sent &&
                  has_roles(server_roles, {"goal", "cancel"}) &&
                  has_roles(client_roles, {"feedback", "status", "result"});
  print_probe_json(ok ? "ok" : "failed", config, server_roles, client_roles, sent ? "" : "send failed");
  return ok ? 0 : 1;
}

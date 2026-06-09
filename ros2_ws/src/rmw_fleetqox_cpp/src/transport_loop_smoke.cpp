#include "rmw_fleetqox_cpp/data_frame.hpp"

#include <arpa/inet.h>
#include <sys/select.h>
#include <sys/socket.h>
#include <unistd.h>

#include <cerrno>
#include <cstdio>
#include <cstring>
#include <iostream>
#include <map>
#include <sstream>
#include <stdexcept>
#include <string>
#include <vector>

namespace
{

using rmw_fleetqox_cpp::AckNackFeedback;
using rmw_fleetqox_cpp::DataFrame;
using rmw_fleetqox_cpp::SequenceState;

struct Summary
{
  int robot_count = 2;
  int samples_per_robot = 3;
  int skip_every = 0;
  bool skip_first = false;
  int published = 0;
  int taken = 0;
  int retransmitted = 0;
  int ack_nack_feedback = 0;
  int missing_sequence_range_count = 0;
  int late_out_of_order_count = 0;
};

int parse_int_arg(char ** argv, int argc, const std::string & name, int default_value)
{
  for (int i = 1; i + 1 < argc; ++i) {
    if (argv[i] == name) {
      return std::stoi(argv[i + 1]);
    }
  }
  return default_value;
}

bool has_flag(char ** argv, int argc, const std::string & name)
{
  for (int i = 1; i < argc; ++i) {
    if (argv[i] == name) {
      return true;
    }
  }
  return false;
}

int udp_socket()
{
  const int fd = ::socket(AF_INET, SOCK_DGRAM, 0);
  if (fd < 0) {
    throw std::runtime_error(std::string("socket failed: ") + std::strerror(errno));
  }
  sockaddr_in addr{};
  addr.sin_family = AF_INET;
  addr.sin_port = 0;
  addr.sin_addr.s_addr = htonl(INADDR_LOOPBACK);
  if (::bind(fd, reinterpret_cast<sockaddr *>(&addr), sizeof(addr)) != 0) {
    ::close(fd);
    throw std::runtime_error(std::string("bind failed: ") + std::strerror(errno));
  }
  return fd;
}

sockaddr_in socket_address(int fd)
{
  sockaddr_in addr{};
  socklen_t len = sizeof(addr);
  if (::getsockname(fd, reinterpret_cast<sockaddr *>(&addr), &len) != 0) {
    throw std::runtime_error(std::string("getsockname failed: ") + std::strerror(errno));
  }
  return addr;
}

sockaddr_in unused_address()
{
  const int fd = udp_socket();
  const auto addr = socket_address(fd);
  ::close(fd);
  return addr;
}

void send_to(int fd, const std::string & payload, const sockaddr_in & addr)
{
  const auto sent = ::sendto(
    fd,
    payload.data(),
    payload.size(),
    0,
    reinterpret_cast<const sockaddr *>(&addr),
    sizeof(addr));
  if (sent < 0) {
    throw std::runtime_error(std::string("sendto failed: ") + std::strerror(errno));
  }
}

std::pair<std::string, sockaddr_in> receive_from(int fd, int timeout_ms)
{
  fd_set read_fds;
  FD_ZERO(&read_fds);
  FD_SET(fd, &read_fds);
  timeval timeout{};
  timeout.tv_sec = timeout_ms / 1000;
  timeout.tv_usec = (timeout_ms % 1000) * 1000;
  const int ready = ::select(fd + 1, &read_fds, nullptr, nullptr, &timeout);
  if (ready <= 0) {
    throw std::runtime_error("receive timeout");
  }
  std::vector<char> buffer(65535);
  sockaddr_in remote{};
  socklen_t len = sizeof(remote);
  const auto n = ::recvfrom(fd, buffer.data(), buffer.size(), 0, reinterpret_cast<sockaddr *>(&remote), &len);
  if (n < 0) {
    throw std::runtime_error(std::string("recvfrom failed: ") + std::strerror(errno));
  }
  return {std::string(buffer.data(), static_cast<std::size_t>(n)), remote};
}

DataFrame sample_frame(const std::string & robot_id, std::uint64_t sequence)
{
  return DataFrame{
    robot_id,
    "/" + robot_id + "/cmd_vel",
    "fpub1-cpp-" + robot_id,
    sequence,
    static_cast<std::int64_t>(sequence * 1000000),
    {}};
}

std::string key_for(const DataFrame & frame)
{
  return rmw_fleetqox_cpp::stream_key(frame) + "|" + std::to_string(frame.source_sequence_number);
}

std::string json_summary(const Summary & summary)
{
  std::ostringstream out;
  out << "{\"schema_version\":\"fleetrmw.rmw_fleetqox_cpp_transport_smoke.v1\",";
  out << "\"robot_count\":" << summary.robot_count << ",";
  out << "\"samples_per_robot\":" << summary.samples_per_robot << ",";
  out << "\"skip_every\":" << summary.skip_every << ",";
  out << "\"skip_first\":" << (summary.skip_first ? "true" : "false") << ",";
  out << "\"published\":" << summary.published << ",";
  out << "\"taken\":" << summary.taken << ",";
  out << "\"retransmitted\":" << summary.retransmitted << ",";
  out << "\"ack_nack_feedback\":" << summary.ack_nack_feedback << ",";
  out << "\"missing_sequence_range_count\":" << summary.missing_sequence_range_count << ",";
  out << "\"late_out_of_order_count\":" << summary.late_out_of_order_count << "}";
  return out.str();
}

void process_listener_once(
  int listener_fd,
  std::map<std::string, SequenceState> & states,
  Summary & summary)
{
  auto [payload, remote] = receive_from(listener_fd, 1000);
  const auto frame = rmw_fleetqox_cpp::decode_data_frame(payload);
  if (!frame) {
    throw std::runtime_error("listener received non FleetRMW frame");
  }
  auto & state = states[rmw_fleetqox_cpp::stream_key(*frame)];
  const AckNackFeedback feedback = rmw_fleetqox_cpp::observe_frame(state, *frame);
  summary.taken += 1;
  summary.ack_nack_feedback += 1;
  summary.missing_sequence_range_count += static_cast<int>(feedback.missing_sequence_ranges.size());
  if (feedback.out_of_order) {
    summary.late_out_of_order_count += 1;
  }
  send_to(listener_fd, rmw_fleetqox_cpp::encode_ack_nack(*frame, feedback), remote);
}

std::string receive_feedback(int talker_fd)
{
  auto [payload, _remote] = receive_from(talker_fd, 1000);
  return payload;
}

}  // namespace

int main(int argc, char ** argv)
{
  try {
    Summary summary;
    summary.robot_count = parse_int_arg(argv, argc, "--robot-count", 2);
    summary.samples_per_robot = parse_int_arg(argv, argc, "--samples-per-robot", 3);
    summary.skip_every = parse_int_arg(argv, argc, "--skip-every", 0);
    summary.skip_first = has_flag(argv, argc, "--skip-first");
    const bool json = has_flag(argv, argc, "--json");

    const int talker_fd = udp_socket();
    const int listener_fd = udp_socket();
    const sockaddr_in listener_addr = socket_address(listener_fd);
    std::map<std::string, std::string> ledger;
    std::map<std::string, SequenceState> listener_states;

    for (int robot_index = 0; robot_index < summary.robot_count; ++robot_index) {
      char robot_buffer[32];
      std::snprintf(robot_buffer, sizeof(robot_buffer), "robot_%04d", robot_index);
      const std::string robot_id(robot_buffer);
      for (int sequence = 1; sequence <= summary.samples_per_robot; ++sequence) {
        const DataFrame frame = sample_frame(robot_id, static_cast<std::uint64_t>(sequence));
        const std::string encoded = rmw_fleetqox_cpp::encode_data_frame(frame);
        ledger[key_for(frame)] = encoded;
        const bool skip =
          (summary.skip_every > 0 && sequence % summary.skip_every == 0) ||
          (summary.skip_first && sequence == 1);
        send_to(talker_fd, encoded, skip ? unused_address() : listener_addr);
        summary.published += 1;
        if (skip) {
          continue;
        }
        process_listener_once(listener_fd, listener_states, summary);
        std::string feedback = receive_feedback(talker_fd);
        while (true) {
          const auto missing = rmw_fleetqox_cpp::missing_sequences_from_ack_nack(feedback);
          if (missing.empty()) {
            break;
          }
          const DataFrame missing_frame = sample_frame(robot_id, missing.front());
          const auto found = ledger.find(key_for(missing_frame));
          if (found == ledger.end()) {
            break;
          }
          send_to(talker_fd, found->second, listener_addr);
          summary.retransmitted += 1;
          process_listener_once(listener_fd, listener_states, summary);
          feedback = receive_feedback(talker_fd);
        }
      }
    }

    ::close(talker_fd);
    ::close(listener_fd);
    if (json) {
      std::cout << json_summary(summary) << std::endl;
    } else {
      std::cout << "fleetrmw-cpp-transport-smoke" << std::endl;
      std::cout << "  published: " << summary.published << std::endl;
      std::cout << "  taken: " << summary.taken << std::endl;
      std::cout << "  retransmitted: " << summary.retransmitted << std::endl;
      std::cout << "  missing_sequence_range_count: " << summary.missing_sequence_range_count << std::endl;
    }
    return 0;
  } catch (const std::exception & exc) {
    std::cerr << "error: " << exc.what() << std::endl;
    return 1;
  }
}

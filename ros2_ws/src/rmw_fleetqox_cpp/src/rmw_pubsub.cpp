#include <algorithm>
#include <array>
#include <atomic>
#include <chrono>
#include <cctype>
#include <cstdio>
#include <cstdint>
#include <cstring>
#include <cstdlib>
#include <deque>
#include <cerrno>
#include <fstream>
#include <limits>
#include <mutex>
#include <new>
#include <optional>
#include <sstream>
#include <string>
#include <thread>
#include <unordered_map>
#include <unordered_set>
#include <utility>
#include <vector>

#include <arpa/inet.h>
#include <netdb.h>
#include <netinet/in.h>
#include <sys/socket.h>
#include <sys/time.h>
#include <unistd.h>

#include "rmw_fleetqox_cpp/data_frame.hpp"

#include "rcutils/allocator.h"
#include "rosidl_runtime_c/string.h"
#include "rosidl_runtime_c/string_functions.h"
#include "rosidl_typesupport_c/identifier.h"
#include "rosidl_typesupport_c/message_type_support_dispatch.h"
#include "rosidl_typesupport_introspection_c/field_types.h"
#include "rosidl_typesupport_introspection_c/identifier.h"
#include "rosidl_typesupport_introspection_c/message_introspection.h"
#include "rmw/allocators.h"
#include "rmw/error_handling.h"
#include "rmw/rmw.h"
#include "rmw/serialized_message.h"

struct rmw_context_impl_s
{
  bool is_shutdown;
  rcutils_allocator_t allocator;
};

extern "C" void rmw_fleetqox_cpp_graph_apply_remote_advertisement_with_info(
  const char * action,
  const char * entity_kind,
  const char * node_name,
  const char * node_namespace,
  const char * topic_name,
  const char * type_name,
  const char * endpoint_id,
  const std::uint8_t * endpoint_gid,
  size_t endpoint_gid_size,
  const rmw_qos_profile_t * qos,
  std::uint64_t lease_ms);
extern "C" size_t rmw_fleetqox_cpp_graph_publisher_count(const char * topic_name);
extern "C" size_t rmw_fleetqox_cpp_graph_subscription_count(const char * topic_name);
extern "C" bool rmw_fleetqox_cpp_handle_service_frame(const char * encoded_frame, size_t size);

namespace
{

constexpr const char * kIdentifier = "rmw_fleetqox_cpp";
constexpr const char * kTypeErasedTypeSupportIdentifier = "rmw_fleetqox_cpp_type_erased_probe";
constexpr std::uint32_t kTypeErasedDescriptorSchemaVersion = 1;

struct FleetQoxPublisherData
{
  rcutils_allocator_t allocator;
  std::string topic_name;
  std::string type_name;
  std::string node_name;
  std::string node_namespace;
  std::string publisher_id;
  std::string endpoint_id;
  std::array<std::uint8_t, RMW_GID_STORAGE_SIZE> endpoint_gid;
  rmw_qos_profile_t qos;
  const rosidl_message_type_support_t * type_support;
  size_t typed_message_size;
  std::uint64_t next_source_sequence;
  std::int64_t last_graph_advertisement_ns;
};

struct FleetQoxSubscriptionData
{
  rcutils_allocator_t allocator;
  std::string topic_name;
  std::string type_name;
  std::string node_name;
  std::string node_namespace;
  std::string subscription_id;
  std::string endpoint_id;
  std::array<std::uint8_t, RMW_GID_STORAGE_SIZE> endpoint_gid;
  const rosidl_message_type_support_t * type_support;
  size_t typed_message_size;
  rmw_qos_profile_t qos;
  std::deque<std::string> frame_queue;
  std::unordered_map<std::string, rmw_fleetqox_cpp::SequenceState> sequence_states;
  rmw_event_callback_t on_new_message_callback;
  const void * on_new_message_user_data;
};

struct FleetQoxTypeErasedMessageDescriptor
{
  std::uint32_t schema_version;
  size_t message_size;
};

std::mutex g_bus_mutex;
std::vector<FleetQoxPublisherData *> g_publishers;
std::vector<FleetQoxSubscriptionData *> g_subscriptions;
std::vector<rmw_subscription_t *> g_subscription_handles;
std::unordered_map<std::string, std::string> g_retransmit_ledger;
std::atomic<std::uint64_t> g_next_publisher_id{1};
std::atomic<std::uint64_t> g_next_subscription_id{1};
std::atomic<bool> g_pubsub_graph_renewal_started{false};

std::mutex g_last_take_mutex;
std::string g_last_take_topic;
std::string g_last_take_publisher_id;
std::uint64_t g_last_take_source_sequence{0};
std::int64_t g_last_take_source_timestamp_ns{0};
std::int64_t g_last_take_timestamp_ns{0};
std::atomic<std::uint64_t> g_duplicate_data_frames_deduped{0};
std::atomic<std::uint64_t> g_out_of_order_data_frames_observed{0};
std::atomic<std::uint64_t> g_idle_repair_ack_nack_sent{0};

void enqueue_received_frame(const std::string & encoded_frame);
bool apply_received_graph_advertisement(const std::string & encoded_frame);
bool handle_ack_nack_feedback(const std::string & encoded_frame);
std::string retransmit_ledger_key(const std::string & publisher_id, std::uint64_t sequence);

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

std::string endpoint_to_string(const sockaddr_in & address)
{
  char host[INET_ADDRSTRLEN] = {};
  if (::inet_ntop(AF_INET, &address.sin_addr, host, sizeof(host)) == nullptr) {
    return "unknown:0";
  }
  return std::string(host) + ":" + std::to_string(ntohs(address.sin_port));
}

bool endpoints_match(const sockaddr_in & left, const sockaddr_in & right)
{
  return left.sin_family == right.sin_family &&
         left.sin_addr.s_addr == right.sin_addr.s_addr &&
         left.sin_port == right.sin_port;
}

std::string trim_copy(const std::string & text)
{
  size_t begin = 0;
  while (begin < text.size() && std::isspace(static_cast<unsigned char>(text[begin]))) {
    ++begin;
  }
  size_t end = text.size();
  while (end > begin && std::isspace(static_cast<unsigned char>(text[end - 1]))) {
    --end;
  }
  return text.substr(begin, end - begin);
}

std::vector<std::string> split_nonempty(const std::string & text, char delimiter)
{
  std::vector<std::string> values;
  size_t start = 0;
  while (start <= text.size()) {
    const size_t found = text.find(delimiter, start);
    const std::string item = trim_copy(text.substr(
      start,
      found == std::string::npos ? std::string::npos : found - start));
    if (!item.empty()) {
      values.push_back(item);
    }
    if (found == std::string::npos) {
      break;
    }
    start = found + 1;
  }
  return values;
}

struct FleetPathPlanRule
{
  std::string topic;
  std::vector<std::string> path_ids;
};

bool parse_peer_endpoints(
  const char * peer_env,
  std::vector<sockaddr_in> * peer_addresses,
  std::vector<std::string> * peer_path_ids,
  std::string * error)
{
  if (peer_addresses == nullptr || peer_path_ids == nullptr) {
    return false;
  }
  if (peer_env == nullptr || peer_env[0] == '\0') {
    return true;
  }

  std::string peers(peer_env);
  size_t start = 0;
  while (start < peers.size()) {
    const size_t comma = peers.find(',', start);
    std::string endpoint = trim_copy(peers.substr(
      start,
      comma == std::string::npos ? std::string::npos : comma - start));
    std::string path_id = "peer_" + std::to_string(peer_addresses->size());
    const size_t equals = endpoint.find('=');
    if (equals != std::string::npos && equals > 0 && equals + 1 < endpoint.size()) {
      path_id = trim_copy(endpoint.substr(0, equals));
      endpoint = trim_copy(endpoint.substr(equals + 1));
    }
    sockaddr_in parsed{};
    if (!parse_ipv4_endpoint(endpoint, &parsed)) {
      if (error != nullptr) {
        *error = "invalid FLEETQOX_RMW_PEERS endpoint: " + endpoint;
      }
      return false;
    }
    peer_addresses->push_back(parsed);
    peer_path_ids->push_back(path_id);
    if (comma == std::string::npos) {
      break;
    }
    start = comma + 1;
  }
  return true;
}

std::vector<FleetPathPlanRule> parse_fleet_path_plan(const char * plan_env)
{
  std::vector<FleetPathPlanRule> rules;
  if (plan_env == nullptr || plan_env[0] == '\0') {
    return rules;
  }
  for (const std::string & rule_text : split_nonempty(plan_env, ';')) {
    const size_t equals = rule_text.find('=');
    if (equals == std::string::npos || equals == 0 || equals + 1 >= rule_text.size()) {
      continue;
    }
    FleetPathPlanRule rule;
    rule.topic = trim_copy(rule_text.substr(0, equals));
    rule.path_ids = split_nonempty(rule_text.substr(equals + 1), '+');
    if (!rule.topic.empty() && !rule.path_ids.empty()) {
      rules.push_back(rule);
    }
  }
  return rules;
}

std::vector<std::uint64_t> parse_sequence_list(const char * sequence_env)
{
  std::vector<std::uint64_t> sequences;
  if (sequence_env == nullptr || sequence_env[0] == '\0') {
    return sequences;
  }
  std::string text(sequence_env);
  size_t start = 0;
  while (start < text.size()) {
    const size_t comma = text.find(',', start);
    const std::string item = text.substr(
      start,
      comma == std::string::npos ? std::string::npos : comma - start);
    if (!item.empty()) {
      char * end = nullptr;
      errno = 0;
      const auto value = std::strtoull(item.c_str(), &end, 10);
      if (errno == 0 && end != item.c_str() && *end == '\0') {
        sequences.push_back(static_cast<std::uint64_t>(value));
      }
    }
    if (comma == std::string::npos) {
      break;
    }
    start = comma + 1;
  }
  return sequences;
}

int parse_nonnegative_int_env(const char * name, int default_value, int max_value)
{
  const char * value = std::getenv(name);
  if (value == nullptr || value[0] == '\0') {
    return default_value;
  }
  char * end = nullptr;
  errno = 0;
  const long parsed = std::strtol(value, &end, 10);
  if (errno != 0 || end == value || *end != '\0' || parsed < 0) {
    return default_value;
  }
  return static_cast<int>(std::min<long>(parsed, max_value));
}

std::uint64_t fnv1a64(const std::string & text, std::uint64_t seed)
{
  std::uint64_t hash = seed;
  for (const unsigned char c : text) {
    hash ^= static_cast<std::uint64_t>(c);
    hash *= 1099511628211ULL;
  }
  return hash;
}

std::array<std::uint8_t, RMW_GID_STORAGE_SIZE> make_endpoint_gid(const std::string & endpoint_id)
{
  std::array<std::uint8_t, RMW_GID_STORAGE_SIZE> gid{};
  size_t offset = 0;
  std::uint64_t block = 0;
  while (offset < gid.size()) {
    const std::uint64_t value = fnv1a64(
      endpoint_id + "#" + std::to_string(block),
      1469598103934665603ULL + block);
    for (int byte = 0; byte < 8 && offset < gid.size(); ++byte) {
      gid[offset++] = static_cast<std::uint8_t>((value >> (byte * 8)) & 0xFFu);
    }
    ++block;
  }
  return gid;
}

std::string hex_encode_bytes(const std::uint8_t * data, size_t size)
{
  static constexpr char kHex[] = "0123456789abcdef";
  std::string encoded;
  encoded.reserve(size * 2);
  for (size_t i = 0; i < size; ++i) {
    encoded.push_back(kHex[(data[i] >> 4) & 0x0F]);
    encoded.push_back(kHex[data[i] & 0x0F]);
  }
  return encoded;
}

int hex_nibble(char c)
{
  if (c >= '0' && c <= '9') {
    return c - '0';
  }
  if (c >= 'a' && c <= 'f') {
    return c - 'a' + 10;
  }
  if (c >= 'A' && c <= 'F') {
    return c - 'A' + 10;
  }
  return -1;
}

std::array<std::uint8_t, RMW_GID_STORAGE_SIZE> endpoint_gid_from_hex(
  const std::string & endpoint_gid,
  const std::string & endpoint_id)
{
  if (endpoint_gid.empty() || endpoint_gid.size() % 2 != 0) {
    return make_endpoint_gid(endpoint_id);
  }
  std::array<std::uint8_t, RMW_GID_STORAGE_SIZE> gid{};
  const size_t max_bytes = std::min(endpoint_gid.size() / 2, gid.size());
  for (size_t i = 0; i < max_bytes; ++i) {
    const int high = hex_nibble(endpoint_gid[i * 2]);
    const int low = hex_nibble(endpoint_gid[i * 2 + 1]);
    if (high < 0 || low < 0) {
      return make_endpoint_gid(endpoint_id);
    }
    gid[i] = static_cast<std::uint8_t>((high << 4) | low);
  }
  return gid;
}

rmw_fleetqox_cpp::GraphQosProfile graph_qos_from_rmw(const rmw_qos_profile_t & qos)
{
  rmw_fleetqox_cpp::GraphQosProfile graph_qos{};
  graph_qos.history = static_cast<std::uint64_t>(qos.history);
  graph_qos.depth = static_cast<std::uint64_t>(qos.depth);
  graph_qos.reliability = static_cast<std::uint64_t>(qos.reliability);
  graph_qos.durability = static_cast<std::uint64_t>(qos.durability);
  graph_qos.deadline_sec = qos.deadline.sec;
  graph_qos.deadline_nsec = qos.deadline.nsec;
  graph_qos.lifespan_sec = qos.lifespan.sec;
  graph_qos.lifespan_nsec = qos.lifespan.nsec;
  graph_qos.liveliness = static_cast<std::uint64_t>(qos.liveliness);
  graph_qos.liveliness_lease_duration_sec = qos.liveliness_lease_duration.sec;
  graph_qos.liveliness_lease_duration_nsec = qos.liveliness_lease_duration.nsec;
  graph_qos.avoid_ros_namespace_conventions = qos.avoid_ros_namespace_conventions ? 1u : 0u;
  return graph_qos;
}

rmw_qos_profile_t rmw_qos_from_graph(const rmw_fleetqox_cpp::GraphQosProfile & graph_qos)
{
  rmw_qos_profile_t qos = rmw_qos_profile_default;
  qos.history = static_cast<rmw_qos_history_policy_t>(graph_qos.history);
  qos.depth = static_cast<size_t>(graph_qos.depth);
  qos.reliability = static_cast<rmw_qos_reliability_policy_t>(graph_qos.reliability);
  qos.durability = static_cast<rmw_qos_durability_policy_t>(graph_qos.durability);
  qos.deadline.sec = graph_qos.deadline_sec;
  qos.deadline.nsec = graph_qos.deadline_nsec;
  qos.lifespan.sec = graph_qos.lifespan_sec;
  qos.lifespan.nsec = graph_qos.lifespan_nsec;
  qos.liveliness = static_cast<rmw_qos_liveliness_policy_t>(graph_qos.liveliness);
  qos.liveliness_lease_duration.sec = graph_qos.liveliness_lease_duration_sec;
  qos.liveliness_lease_duration.nsec = graph_qos.liveliness_lease_duration_nsec;
  qos.avoid_ros_namespace_conventions = graph_qos.avoid_ros_namespace_conventions != 0;
  return qos;
}

class LoopbackSocketTransport
{
public:
  LoopbackSocketTransport()
  {
    start();
  }

  ~LoopbackSocketTransport()
  {
    stop();
  }

  rmw_ret_t send_frame(const std::string & encoded_frame)
  {
    return send_frame_with_qos(encoded_frame, nullptr);
  }

  rmw_ret_t send_data_frame(const std::string & encoded_frame, const rmw_qos_profile_t & qos)
  {
    return send_frame_with_qos(encoded_frame, &qos);
  }

  rmw_ret_t send_frame_with_qos(
    const std::string & encoded_frame,
    const rmw_qos_profile_t * qos)
  {
    if (!ready_) {
      RMW_SET_ERROR_MSG(init_error_.empty() ? "socket transport is not ready" : init_error_.c_str());
      return RMW_RET_ERROR;
    }
    if (encoded_frame.empty()) {
      RMW_SET_ERROR_MSG("encoded FleetRMW frame is empty");
      return RMW_RET_INVALID_ARGUMENT;
    }
    if (encoded_frame.size() > kMaxUdpPayloadBytes) {
      RMW_SET_ERROR_MSG("encoded FleetRMW frame exceeds UDP loopback payload limit");
      return RMW_RET_UNSUPPORTED;
    }

    if (should_drop_outbound_data_frame_for_test(encoded_frame)) {
      return RMW_RET_OK;
    }

    const std::optional<rmw_fleetqox_cpp::DataFrame> data_frame =
      rmw_fleetqox_cpp::decode_data_frame(encoded_frame);
    const bool is_data_frame = data_frame.has_value();
    const std::vector<sockaddr_in> targets =
      is_data_frame ? data_frame_targets(true, qos, data_frame) : frame_targets(true);
    if (targets.empty()) {
      RMW_SET_ERROR_MSG("socket transport has no local or peer target for frame");
      return RMW_RET_ERROR;
    }
    auto send_once = [&]() -> rmw_ret_t {
      const rmw_ret_t send_ret = send_payload_to_targets(encoded_frame, targets, "FleetRMW frame");
      if (send_ret == RMW_RET_OK) {
        frames_sent_.fetch_add(1, std::memory_order_relaxed);
      }
      return send_ret;
    };
    rmw_ret_t send_ret = send_once();
    if (send_ret != RMW_RET_OK || !is_data_frame || proactive_data_repeats_ <= 0) {
      return send_ret;
    }
    for (int repeat = 0; repeat < proactive_data_repeats_; ++repeat) {
      if (proactive_data_repeat_interval_ms_ > 0) {
        std::this_thread::sleep_for(std::chrono::milliseconds(proactive_data_repeat_interval_ms_));
      }
      send_ret = send_once();
      if (send_ret != RMW_RET_OK) {
        return send_ret;
      }
    }
    return RMW_RET_OK;
  }

  rmw_ret_t send_ack_nack(const std::string & payload)
  {
    const rmw_ret_t ret = send_control_payload(payload, true);
    if (ret == RMW_RET_OK) {
      ack_nack_sent_.fetch_add(1, std::memory_order_relaxed);
    }
    return ret;
  }

  rmw_ret_t send_retransmission_frame(const std::string & encoded_frame)
  {
    const rmw_ret_t ret = send_frame(encoded_frame);
    if (ret == RMW_RET_OK) {
      nack_retransmissions_.fetch_add(1, std::memory_order_relaxed);
    }
    return ret;
  }

  std::uint64_t frames_sent() const
  {
    return frames_sent_.load(std::memory_order_relaxed);
  }

  std::uint64_t frames_received() const
  {
    return frames_received_.load(std::memory_order_relaxed);
  }

  std::uint64_t ack_nack_sent() const
  {
    return ack_nack_sent_.load(std::memory_order_relaxed);
  }

  std::uint64_t ack_nack_received() const
  {
    return ack_nack_received_.load(std::memory_order_relaxed);
  }

  std::uint64_t ack_nack_duplicate_received() const
  {
    return ack_nack_duplicate_received_.load(std::memory_order_relaxed);
  }

  std::uint64_t ack_nack_out_of_order_received() const
  {
    return ack_nack_out_of_order_received_.load(std::memory_order_relaxed);
  }

  std::uint64_t nack_retransmissions() const
  {
    return nack_retransmissions_.load(std::memory_order_relaxed);
  }

  std::uint64_t test_dropped_frames() const
  {
    return test_dropped_frames_.load(std::memory_order_relaxed);
  }

  std::uint64_t adaptive_failovers() const
  {
    return adaptive_failovers_.load(std::memory_order_relaxed);
  }

  std::uint64_t adaptive_unicast_frames() const
  {
    return adaptive_unicast_frames_.load(std::memory_order_relaxed);
  }

  std::uint64_t adaptive_redundant_frames() const
  {
    return adaptive_redundant_frames_.load(std::memory_order_relaxed);
  }

  std::uint64_t fleet_plan_frames() const
  {
    return fleet_plan_frames_.load(std::memory_order_relaxed);
  }

  std::uint64_t fleet_plan_redundant_frames() const
  {
    return fleet_plan_redundant_frames_.load(std::memory_order_relaxed);
  }

  std::uint64_t fleet_plan_selected_path_count() const
  {
    return fleet_plan_selected_path_count_.load(std::memory_order_relaxed);
  }

  std::string fleet_plan_last_paths() const
  {
    std::lock_guard<std::mutex> lock(fleet_plan_mutex_);
    return fleet_plan_last_paths_;
  }

  std::uint64_t adaptive_peer_score_sum() const
  {
    std::lock_guard<std::mutex> lock(adaptive_mutex_);
    std::uint64_t sum = 0;
    for (const std::uint64_t score : adaptive_peer_scores_) {
      sum += score;
    }
    return sum;
  }

  size_t adaptive_selected_peer_index() const
  {
    if (peer_addresses_.empty()) {
      return 0;
    }
    return adaptive_selected_peer_index_.load(std::memory_order_relaxed) % peer_addresses_.size();
  }

  const std::string & peer_policy() const
  {
    return peer_policy_;
  }

  void record_ack_nack_received()
  {
    ack_nack_received_.fetch_add(1, std::memory_order_relaxed);
  }

  void record_ack_nack_feedback(const rmw_fleetqox_cpp::AckNackFrame & frame)
  {
    if (frame.duplicate) {
      ack_nack_duplicate_received_.fetch_add(1, std::memory_order_relaxed);
    }
    if (frame.out_of_order) {
      ack_nack_out_of_order_received_.fetch_add(1, std::memory_order_relaxed);
    }
    const bool adaptive_policy =
      peer_policy_ == "adaptive_failover" ||
      peer_policy_ == "adaptive_score" ||
      peer_policy_ == "adaptive_qos";
    if (!adaptive_policy || peer_addresses_.size() < 2) {
      return;
    }
    if (frame.missing_sequence_ranges.empty()) {
      if (peer_policy_ == "adaptive_score" || peer_policy_ == "adaptive_qos") {
        std::lock_guard<std::mutex> lock(adaptive_mutex_);
        const size_t selected = adaptive_selected_peer_index();
        if (selected < adaptive_peer_scores_.size() && adaptive_peer_scores_[selected] > 0) {
          --adaptive_peer_scores_[selected];
        }
      }
      return;
    }
    std::uint64_t missing_count = 0;
    for (const auto & range : frame.missing_sequence_ranges) {
      if (range.second >= range.first) {
        missing_count += range.second - range.first + 1;
      }
    }
    if (missing_count == 0) {
      missing_count = 1;
    }
    {
      std::ostringstream key;
      key << frame.publisher_id << "|";
      for (const auto & range : frame.missing_sequence_ranges) {
        key << range.first << "-" << range.second << ",";
      }
      std::lock_guard<std::mutex> lock(adaptive_mutex_);
      const std::string nack_key = key.str();
      if (nack_key == last_adaptive_nack_key_) {
        return;
      }
      last_adaptive_nack_key_ = nack_key;
      const size_t previous = adaptive_selected_peer_index();
      if ((peer_policy_ == "adaptive_score" || peer_policy_ == "adaptive_qos") &&
        previous < adaptive_peer_scores_.size())
      {
        adaptive_peer_scores_[previous] += 1000u * missing_count;
      }
      size_t next = (previous + 1) % peer_addresses_.size();
      if (peer_policy_ == "adaptive_score" || peer_policy_ == "adaptive_qos") {
        next = best_scored_peer_index_locked();
      }
      adaptive_selected_peer_index_.store(next, std::memory_order_relaxed);
      if (next != previous) {
        adaptive_failovers_.fetch_add(1, std::memory_order_relaxed);
      }
    }
  }

  bool adaptive_data_unicast_enabled() const
  {
    return peer_policy_ == "adaptive_failover" ||
           peer_policy_ == "adaptive_score" ||
           peer_policy_ == "adaptive_qos";
  }

  static std::int64_t duration_ns(const rmw_time_t & duration)
  {
    if (duration.sec == 0 && duration.nsec == 0) {
      return 0;
    }
    constexpr std::uint64_t kNanosecondsPerSecond = 1000000000ull;
    if (duration.sec > static_cast<std::uint64_t>(
        std::numeric_limits<std::int64_t>::max() / static_cast<std::int64_t>(kNanosecondsPerSecond)))
    {
      return std::numeric_limits<std::int64_t>::max();
    }
    const auto sec_ns = static_cast<std::int64_t>(duration.sec * kNanosecondsPerSecond);
    const auto nsec = static_cast<std::int64_t>(duration.nsec);
    if (std::numeric_limits<std::int64_t>::max() - sec_ns < nsec) {
      return std::numeric_limits<std::int64_t>::max();
    }
    return sec_ns + nsec;
  }

  bool qos_prefers_redundancy(const rmw_qos_profile_t * qos) const
  {
    if (peer_policy_ != "adaptive_qos" || qos == nullptr || peer_addresses_.size() < 2) {
      return false;
    }
    const std::int64_t deadline_ns = duration_ns(qos->deadline);
    return deadline_ns > 0 &&
           adaptive_redundant_deadline_ns_ > 0 &&
           deadline_ns <= adaptive_redundant_deadline_ns_;
  }

  size_t best_scored_peer_index_locked() const
  {
    if (adaptive_peer_scores_.empty()) {
      return adaptive_selected_peer_index();
    }
    size_t best = 0;
    std::uint64_t best_score = adaptive_peer_scores_[0];
    for (size_t i = 1; i < adaptive_peer_scores_.size(); ++i) {
      if (adaptive_peer_scores_[i] < best_score) {
        best = i;
        best_score = adaptive_peer_scores_[i];
      }
    }
    return best;
  }

  bool ready() const
  {
    return ready_;
  }

  const std::string & init_error() const
  {
    return init_error_;
  }

  const std::string & bound_endpoint() const
  {
    return bound_endpoint_;
  }

  size_t peer_count() const
  {
    return peer_addresses_.size();
  }

  rmw_ret_t send_subscription_advertisement(
    const std::string & topic_name,
    const std::string & type_name)
  {
    if (peer_addresses_.empty()) {
      return RMW_RET_OK;
    }
    const rmw_fleetqox_cpp::RouteAdvertisement advertisement{
      bound_endpoint_,
      "subscriber",
      topic_name,
      type_name,
      5000u};
    return send_to_peers(rmw_fleetqox_cpp::encode_route_advertisement(advertisement));
  }

  rmw_ret_t send_graph_advertisement(
    const std::string & action,
    const std::string & entity_kind,
    const std::string & node_name,
    const std::string & node_namespace,
    const std::string & topic_name,
    const std::string & type_name,
    const std::string & endpoint_id,
    const std::array<std::uint8_t, RMW_GID_STORAGE_SIZE> & endpoint_gid,
    const rmw_qos_profile_t & qos)
  {
    if (peer_addresses_.empty()) {
      return RMW_RET_OK;
    }
    const rmw_fleetqox_cpp::GraphAdvertisement advertisement{
      endpoint_id,
      action,
      entity_kind,
      node_name,
      node_namespace,
      topic_name,
      type_name,
      hex_encode_bytes(endpoint_gid.data(), endpoint_gid.size()),
      graph_qos_from_rmw(qos),
      5000u};
    return send_to_peers(rmw_fleetqox_cpp::encode_graph_advertisement(advertisement));
  }

private:
  static constexpr size_t kMaxUdpPayloadBytes = 65507;

  std::vector<sockaddr_in> frame_targets(bool include_local) const
  {
    std::vector<sockaddr_in> targets;
    if (include_local && address_.sin_addr.s_addr != htonl(INADDR_ANY)) {
      targets.push_back(address_);
    }
    for (const sockaddr_in & peer : peer_addresses_) {
      if (std::none_of(targets.begin(), targets.end(), [&](const sockaddr_in & target) {
          return endpoints_match(target, peer);
        }))
      {
        targets.push_back(peer);
      }
    }
    return targets;
  }

  std::vector<sockaddr_in> data_frame_targets(
    bool include_local,
    const rmw_qos_profile_t * qos,
    const std::optional<rmw_fleetqox_cpp::DataFrame> & frame)
  {
    if (peer_policy_ == "fleet_plan" && frame.has_value()) {
      const std::vector<sockaddr_in> planned_targets = fleet_plan_targets(*frame);
      if (!planned_targets.empty()) {
        fleet_plan_frames_.fetch_add(1, std::memory_order_relaxed);
        fleet_plan_selected_path_count_.fetch_add(planned_targets.size(), std::memory_order_relaxed);
        if (planned_targets.size() > 1) {
          fleet_plan_redundant_frames_.fetch_add(1, std::memory_order_relaxed);
        }
        return planned_targets;
      }
    }
    if (qos_prefers_redundancy(qos)) {
      adaptive_redundant_frames_.fetch_add(1, std::memory_order_relaxed);
      return frame_targets(include_local);
    }
    if (adaptive_data_unicast_enabled() && !peer_addresses_.empty()) {
      size_t selected = adaptive_selected_peer_index();
      if (peer_policy_ == "adaptive_score" || peer_policy_ == "adaptive_qos") {
        std::lock_guard<std::mutex> lock(adaptive_mutex_);
        selected = best_scored_peer_index_locked();
        adaptive_selected_peer_index_.store(selected, std::memory_order_relaxed);
      }
      adaptive_unicast_frames_.fetch_add(1, std::memory_order_relaxed);
      return std::vector<sockaddr_in>{peer_addresses_[selected]};
    }
    return frame_targets(include_local);
  }

  std::vector<sockaddr_in> fleet_plan_targets(const rmw_fleetqox_cpp::DataFrame & frame)
  {
    const std::vector<std::string> path_ids = fleet_plan_path_ids_for_topic(frame.topic);
    if (path_ids.empty()) {
      return {};
    }
    std::vector<sockaddr_in> targets;
    std::ostringstream selected_paths;
    for (const std::string & path_id : path_ids) {
      for (size_t i = 0; i < peer_addresses_.size() && i < peer_path_ids_.size(); ++i) {
        if (peer_path_ids_[i] != path_id) {
          continue;
        }
        if (std::none_of(targets.begin(), targets.end(), [&](const sockaddr_in & target) {
            return endpoints_match(target, peer_addresses_[i]);
          }))
        {
          if (selected_paths.tellp() > 0) {
            selected_paths << ",";
          }
          selected_paths << path_id;
          targets.push_back(peer_addresses_[i]);
        }
      }
    }
    if (!targets.empty()) {
      std::lock_guard<std::mutex> lock(fleet_plan_mutex_);
      fleet_plan_last_paths_ = selected_paths.str();
    }
    return targets;
  }

  std::vector<std::string> fleet_plan_path_ids_for_topic(const std::string & topic) const
  {
    refresh_fleet_path_plan_from_file();
    std::lock_guard<std::mutex> lock(fleet_plan_mutex_);
    for (const FleetPathPlanRule & rule : fleet_path_plan_) {
      if (rule.topic == topic) {
        return rule.path_ids;
      }
    }
    for (const FleetPathPlanRule & rule : fleet_path_plan_) {
      if (rule.topic == "*") {
        return rule.path_ids;
      }
    }
    return {};
  }

  void refresh_fleet_path_plan_from_file() const
  {
    if (fleet_path_plan_file_.empty()) {
      return;
    }
    std::ifstream input(fleet_path_plan_file_);
    if (!input) {
      return;
    }
    std::ostringstream buffer;
    buffer << input.rdbuf();
    const std::string plan_text = trim_copy(buffer.str());
    std::lock_guard<std::mutex> lock(fleet_plan_mutex_);
    if (plan_text.empty() && !fleet_path_plan_file_contents_.empty()) {
      return;
    }
    if (plan_text == fleet_path_plan_file_contents_) {
      return;
    }
    fleet_path_plan_ = parse_fleet_path_plan(plan_text.c_str());
    fleet_path_plan_file_contents_ = plan_text;
  }

  rmw_ret_t send_payload_to_targets(
    const std::string & payload,
    const std::vector<sockaddr_in> & targets,
    const char * label)
  {
    for (const sockaddr_in & target : targets) {
      const auto sent = ::sendto(
        fd_,
        payload.data(),
        payload.size(),
        0,
        reinterpret_cast<const sockaddr *>(&target),
        sizeof(target));
      if (sent < 0 || static_cast<size_t>(sent) != payload.size()) {
        RMW_SET_ERROR_MSG(label == nullptr ?
          "failed to send FleetRMW payload through UDP transport" :
          "failed to send FleetRMW payload through UDP transport");
        return RMW_RET_ERROR;
      }
    }
    return RMW_RET_OK;
  }

  bool should_drop_outbound_data_frame_for_test(const std::string & encoded_frame)
  {
    if (drop_source_sequences_.empty()) {
      return false;
    }
    const auto frame = rmw_fleetqox_cpp::decode_data_frame(encoded_frame);
    if (!frame) {
      return false;
    }
    const auto should_drop_sequence = std::find(
      drop_source_sequences_.begin(),
      drop_source_sequences_.end(),
      frame->source_sequence_number) != drop_source_sequences_.end();
    if (!should_drop_sequence) {
      return false;
    }
    const std::string key =
      frame->publisher_id + "|" + std::to_string(frame->source_sequence_number);
    std::lock_guard<std::mutex> lock(test_drop_mutex_);
    if (dropped_source_sequence_keys_.find(key) != dropped_source_sequence_keys_.end()) {
      return false;
    }
    dropped_source_sequence_keys_.insert(key);
    test_dropped_frames_.fetch_add(1, std::memory_order_relaxed);
    return true;
  }

  rmw_ret_t send_to_peers(const std::string & payload)
  {
    return send_control_payload(payload, false);
  }

  rmw_ret_t send_control_payload(const std::string & payload, bool include_local)
  {
    if (!ready_) {
      RMW_SET_ERROR_MSG(init_error_.empty() ? "socket transport is not ready" : init_error_.c_str());
      return RMW_RET_ERROR;
    }
    if (payload.empty()) {
      RMW_SET_ERROR_MSG("FleetRMW control payload is empty");
      return RMW_RET_INVALID_ARGUMENT;
    }
    if (payload.size() > kMaxUdpPayloadBytes) {
      RMW_SET_ERROR_MSG("FleetRMW control payload exceeds UDP payload limit");
      return RMW_RET_UNSUPPORTED;
    }
    return send_payload_to_targets(payload, frame_targets(include_local), "FleetRMW control payload");
  }

  void start()
  {
    fd_ = ::socket(AF_INET, SOCK_DGRAM, 0);
    if (fd_ < 0) {
      init_error_ = "failed to create UDP loopback socket";
      return;
    }

    timeval timeout{};
    timeout.tv_sec = 0;
    timeout.tv_usec = 100000;
    if (::setsockopt(fd_, SOL_SOCKET, SO_RCVTIMEO, &timeout, sizeof(timeout)) != 0) {
      init_error_ = "failed to configure UDP loopback receive timeout";
      ::close(fd_);
      fd_ = -1;
      return;
    }

    sockaddr_in bind_address{};
    const char * bind_env = std::getenv("FLEETQOX_RMW_BIND");
    if (bind_env != nullptr && bind_env[0] != '\0') {
      if (!parse_ipv4_endpoint(bind_env, &bind_address)) {
        init_error_ = "invalid FLEETQOX_RMW_BIND endpoint";
        ::close(fd_);
        fd_ = -1;
        return;
      }
    } else {
      bind_address.sin_family = AF_INET;
      bind_address.sin_addr.s_addr = htonl(INADDR_LOOPBACK);
      bind_address.sin_port = 0;
    }
    if (::bind(fd_, reinterpret_cast<const sockaddr *>(&bind_address), sizeof(bind_address)) != 0) {
      init_error_ = "failed to bind UDP loopback socket";
      ::close(fd_);
      fd_ = -1;
      return;
    }

    socklen_t address_length = sizeof(address_);
    if (::getsockname(fd_, reinterpret_cast<sockaddr *>(&address_), &address_length) != 0) {
      init_error_ = "failed to read UDP loopback socket address";
      ::close(fd_);
      fd_ = -1;
      return;
    }
    bound_endpoint_ = endpoint_to_string(address_);

    if (!parse_peer_endpoints(
        std::getenv("FLEETQOX_RMW_PEERS"),
        &peer_addresses_,
        &peer_path_ids_,
        &init_error_))
    {
      ::close(fd_);
      fd_ = -1;
      return;
    }
    fleet_path_plan_ = parse_fleet_path_plan(std::getenv("FLEETQOX_RMW_FLEET_PATH_PLAN"));
    if (const char * plan_file_env = std::getenv("FLEETQOX_RMW_FLEET_PATH_PLAN_FILE");
      plan_file_env != nullptr && plan_file_env[0] != '\0')
    {
      fleet_path_plan_file_ = plan_file_env;
      refresh_fleet_path_plan_from_file();
    }
    drop_source_sequences_ = parse_sequence_list(std::getenv("FLEETQOX_RMW_DROP_SOURCE_SEQUENCES"));
    proactive_data_repeats_ = parse_nonnegative_int_env(
      "FLEETQOX_RMW_PROACTIVE_DATA_REPEATS", 0, 5);
    proactive_data_repeat_interval_ms_ = parse_nonnegative_int_env(
      "FLEETQOX_RMW_PROACTIVE_DATA_REPEAT_INTERVAL_MS", 5, 100);
    if (const char * policy_env = std::getenv("FLEETQOX_RMW_PEER_POLICY");
      policy_env != nullptr && policy_env[0] != '\0')
    {
      peer_policy_ = policy_env;
    }
    if (const char * deadline_env = std::getenv("FLEETQOX_RMW_REDUNDANT_DEADLINE_MS");
      deadline_env != nullptr && deadline_env[0] != '\0')
    {
      char * end = nullptr;
      errno = 0;
      const long deadline_ms = std::strtol(deadline_env, &end, 10);
      if (errno == 0 && end != deadline_env && *end == '\0' && deadline_ms >= 0) {
        adaptive_redundant_deadline_ns_ =
          static_cast<std::int64_t>(deadline_ms) * 1000000ll;
      }
    }
    adaptive_peer_scores_.assign(peer_addresses_.size(), 0);

    running_.store(true, std::memory_order_release);
    try {
      receive_thread_ = std::thread([this]() { receive_loop(); });
    } catch (...) {
      running_.store(false, std::memory_order_release);
      ::close(fd_);
      fd_ = -1;
      init_error_ = "failed to start UDP loopback receive thread";
      return;
    }
    ready_ = true;
  }

  void stop()
  {
    running_.store(false, std::memory_order_release);
    if (fd_ >= 0) {
      ::shutdown(fd_, SHUT_RDWR);
    }
    if (receive_thread_.joinable()) {
      receive_thread_.join();
    }
    if (fd_ >= 0) {
      ::close(fd_);
      fd_ = -1;
    }
    ready_ = false;
  }

  void receive_loop()
  {
    std::array<char, kMaxUdpPayloadBytes> buffer{};
    while (running_.load(std::memory_order_acquire)) {
      const auto received = ::recvfrom(fd_, buffer.data(), buffer.size(), 0, nullptr, nullptr);
      if (received < 0) {
        if (!running_.load(std::memory_order_acquire)) {
          break;
        }
        if (errno == EINTR || errno == EAGAIN || errno == EWOULDBLOCK) {
          continue;
        }
        break;
      }
      if (received == 0) {
        continue;
      }
      frames_received_.fetch_add(1, std::memory_order_relaxed);
      const std::string encoded_frame(buffer.data(), static_cast<size_t>(received));
      if (handle_ack_nack_feedback(encoded_frame)) {
        continue;
      }
      if (apply_received_graph_advertisement(encoded_frame)) {
        continue;
      }
      if (rmw_fleetqox_cpp_handle_service_frame(encoded_frame.data(), encoded_frame.size())) {
        continue;
      }
      enqueue_received_frame(encoded_frame);
    }
  }

  int fd_{-1};
  sockaddr_in address_{};
  std::thread receive_thread_;
  std::atomic_bool running_{false};
  std::atomic<std::uint64_t> frames_sent_{0};
  std::atomic<std::uint64_t> frames_received_{0};
  std::atomic<std::uint64_t> ack_nack_sent_{0};
  std::atomic<std::uint64_t> ack_nack_received_{0};
  std::atomic<std::uint64_t> ack_nack_duplicate_received_{0};
  std::atomic<std::uint64_t> ack_nack_out_of_order_received_{0};
  std::atomic<std::uint64_t> nack_retransmissions_{0};
  std::atomic<std::uint64_t> test_dropped_frames_{0};
  std::atomic<std::uint64_t> adaptive_failovers_{0};
  std::atomic<std::uint64_t> adaptive_unicast_frames_{0};
  std::atomic<std::uint64_t> adaptive_redundant_frames_{0};
  std::atomic<std::uint64_t> fleet_plan_frames_{0};
  std::atomic<std::uint64_t> fleet_plan_redundant_frames_{0};
  std::atomic<std::uint64_t> fleet_plan_selected_path_count_{0};
  std::atomic<size_t> adaptive_selected_peer_index_{0};
  std::int64_t adaptive_redundant_deadline_ns_{50000000ll};
  bool ready_{false};
  std::string init_error_;
  std::string bound_endpoint_;
  std::string peer_policy_{"all"};
  std::vector<sockaddr_in> peer_addresses_;
  std::vector<std::string> peer_path_ids_;
  mutable std::vector<FleetPathPlanRule> fleet_path_plan_;
  mutable std::string fleet_path_plan_file_;
  mutable std::string fleet_path_plan_file_contents_;
  std::vector<std::uint64_t> drop_source_sequences_;
  int proactive_data_repeats_{0};
  int proactive_data_repeat_interval_ms_{5};
  std::mutex test_drop_mutex_;
  std::unordered_set<std::string> dropped_source_sequence_keys_;
  mutable std::mutex adaptive_mutex_;
  std::string last_adaptive_nack_key_;
  std::vector<std::uint64_t> adaptive_peer_scores_;
  mutable std::mutex fleet_plan_mutex_;
  std::string fleet_plan_last_paths_;
};

LoopbackSocketTransport & socket_transport()
{
  static LoopbackSocketTransport transport;
  return transport;
}

bool handle_ack_nack_feedback(const std::string & encoded_frame)
{
  const auto ack_nack = rmw_fleetqox_cpp::decode_ack_nack(encoded_frame);
  if (!ack_nack) {
    return false;
  }
  socket_transport().record_ack_nack_received();
  socket_transport().record_ack_nack_feedback(*ack_nack);

  std::vector<std::string> retransmit_frames;
  {
    std::lock_guard<std::mutex> lock(g_bus_mutex);
    for (const auto & range : ack_nack->missing_sequence_ranges) {
      for (std::uint64_t sequence = range.first; sequence <= range.second; ++sequence) {
        const auto found = g_retransmit_ledger.find(
          retransmit_ledger_key(ack_nack->publisher_id, sequence));
        if (found != g_retransmit_ledger.end()) {
          retransmit_frames.push_back(found->second);
        }
      }
    }
  }
  for (const std::string & frame : retransmit_frames) {
    const rmw_ret_t ret = socket_transport().send_retransmission_frame(frame);
    (void)ret;
  }
  return true;
}

std::string endpoint_id_for_local_id(const std::string & local_id)
{
  return socket_transport().bound_endpoint() + "|" + local_id;
}

std::string retransmit_ledger_key(const std::string & publisher_id, std::uint64_t sequence)
{
  return publisher_id + "|" + std::to_string(sequence);
}

bool identifier_matches(const char * identifier)
{
  return identifier != nullptr && std::strcmp(identifier, kIdentifier) == 0;
}

rmw_ret_t require_identifier(const char * identifier)
{
  if (!identifier_matches(identifier)) {
    RMW_SET_ERROR_MSG("rmw_fleetqox_cpp implementation identifier mismatch");
    return RMW_RET_INCORRECT_RMW_IMPLEMENTATION;
  }
  return RMW_RET_OK;
}

bool context_is_valid(const rmw_context_t * context)
{
  return context != nullptr &&
         identifier_matches(context->implementation_identifier) &&
         context->impl != nullptr &&
         !context->impl->is_shutdown;
}

bool node_is_valid(const rmw_node_t * node)
{
  return node != nullptr &&
         identifier_matches(node->implementation_identifier) &&
         context_is_valid(node->context);
}

bool topic_is_valid(const char * topic_name)
{
  return topic_name != nullptr && topic_name[0] == '/';
}

bool trace_take_enabled()
{
  const char * value = std::getenv("FLEETQOX_RMW_TRACE_TAKE");
  return value != nullptr && value[0] != '\0' && std::strcmp(value, "0") != 0;
}

std::int64_t monotonic_timestamp_ns()
{
  const auto now = std::chrono::steady_clock::now().time_since_epoch();
  return std::chrono::duration_cast<std::chrono::nanoseconds>(now).count();
}

const std::string & local_robot_id()
{
  static const std::string robot_id = []() {
      const char * configured = std::getenv("FLEETQOX_RMW_ROBOT_ID");
      return configured != nullptr && configured[0] != '\0' ?
             std::string(configured) : std::string("local");
    }();
  return robot_id;
}

std::int64_t qos_duration_ns(const rmw_time_t & duration)
{
  if (duration.sec == 0 && duration.nsec == 0) {
    return 0;
  }
  constexpr std::uint64_t kNanosecondsPerSecond = 1000000000ull;
  if (duration.sec > static_cast<std::uint64_t>(
      std::numeric_limits<std::int64_t>::max() / static_cast<std::int64_t>(kNanosecondsPerSecond)))
  {
    return std::numeric_limits<std::int64_t>::max();
  }
  const auto sec_ns = static_cast<std::int64_t>(duration.sec * kNanosecondsPerSecond);
  const auto nsec = static_cast<std::int64_t>(duration.nsec);
  if (std::numeric_limits<std::int64_t>::max() - sec_ns < nsec) {
    return std::numeric_limits<std::int64_t>::max();
  }
  return sec_ns + nsec;
}

bool frame_exceeds_lifespan(const rmw_qos_profile_t & qos, std::int64_t source_timestamp_ns)
{
  const std::int64_t lifespan_ns = qos_duration_ns(qos.lifespan);
  if (lifespan_ns <= 0 || source_timestamp_ns <= 0) {
    return false;
  }
  const std::int64_t now = monotonic_timestamp_ns();
  return now > source_timestamp_ns && now - source_timestamp_ns > lifespan_ns;
}

void enforce_subscription_depth_locked(FleetQoxSubscriptionData * data)
{
  if (data == nullptr ||
    data->qos.history != RMW_QOS_POLICY_HISTORY_KEEP_LAST ||
    data->qos.depth == 0)
  {
    return;
  }
  while (data->frame_queue.size() > data->qos.depth) {
    data->frame_queue.pop_front();
  }
}

std::string allocate_publisher_id()
{
  return "fpubcpp-" + socket_transport().bound_endpoint() + "-" +
         std::to_string(g_next_publisher_id.fetch_add(1));
}

std::string allocate_subscription_id()
{
  return "fsubcpp-" + socket_transport().bound_endpoint() + "-" +
         std::to_string(g_next_subscription_id.fetch_add(1));
}

std::string ros_type_name_from_introspection_members(
  const rosidl_typesupport_introspection_c__MessageMembers * members)
{
  if (members == nullptr || members->message_namespace_ == nullptr ||
    members->message_name_ == nullptr)
  {
    return "unknown";
  }
  std::string namespace_text = members->message_namespace_;
  size_t separator = 0;
  while ((separator = namespace_text.find("__", separator)) != std::string::npos) {
    namespace_text.replace(separator, 2, "/");
    separator += 1;
  }
  return namespace_text + "/" + members->message_name_;
}

size_t typed_message_size_from_type_support(const rosidl_message_type_support_t * type_support)
{
  if (type_support == nullptr ||
    type_support->typesupport_identifier == nullptr ||
    std::strcmp(type_support->typesupport_identifier, kTypeErasedTypeSupportIdentifier) != 0 ||
    type_support->data == nullptr)
  {
    return 0;
  }
  const auto * descriptor =
    static_cast<const FleetQoxTypeErasedMessageDescriptor *>(type_support->data);
  if (descriptor->schema_version != kTypeErasedDescriptorSchemaVersion ||
    descriptor->message_size == 0)
  {
    return 0;
  }
  return descriptor->message_size;
}

const rosidl_typesupport_introspection_c__MessageMembers * introspection_c_members(
  const rosidl_message_type_support_t * type_support)
{
  if (type_support == nullptr ||
    type_support->typesupport_identifier == nullptr ||
    std::strcmp(type_support->typesupport_identifier, rosidl_typesupport_introspection_c__identifier) != 0 ||
    type_support->data == nullptr)
  {
    return nullptr;
  }
  return static_cast<const rosidl_typesupport_introspection_c__MessageMembers *>(type_support->data);
}

const rosidl_message_type_support_t * resolve_effective_type_support(
  const rosidl_message_type_support_t * type_support)
{
  if (type_support == nullptr || type_support->typesupport_identifier == nullptr) {
    return type_support;
  }
  if (std::strcmp(
      type_support->typesupport_identifier,
      rosidl_typesupport_introspection_c__identifier) == 0)
  {
    return type_support;
  }
  if (std::strcmp(
      type_support->typesupport_identifier,
      rosidl_typesupport_c__typesupport_identifier) == 0)
  {
    const rosidl_message_type_support_t * resolved =
      rosidl_typesupport_c__get_message_typesupport_handle_function(
      type_support,
      rosidl_typesupport_introspection_c__identifier);
    if (resolved != nullptr) {
      return resolved;
    }
  }
  if (type_support->func != nullptr) {
    const rosidl_message_type_support_t * resolved =
      type_support->func(type_support, rosidl_typesupport_introspection_c__identifier);
    if (resolved != nullptr) {
      return resolved;
    }
  }
  return type_support;
}

std::string type_name_from_type_support(const rosidl_message_type_support_t * type_support)
{
  const auto * introspection_members = introspection_c_members(resolve_effective_type_support(type_support));
  if (introspection_members != nullptr) {
    return ros_type_name_from_introspection_members(introspection_members);
  }
  return type_support != nullptr && type_support->typesupport_identifier != nullptr ?
         type_support->typesupport_identifier : "unknown";
}

size_t primitive_size(uint8_t type_id)
{
  switch (type_id) {
    case rosidl_typesupport_introspection_c__ROS_TYPE_FLOAT:
      return sizeof(float);
    case rosidl_typesupport_introspection_c__ROS_TYPE_DOUBLE:
      return sizeof(double);
    case rosidl_typesupport_introspection_c__ROS_TYPE_LONG_DOUBLE:
      return sizeof(long double);
    case rosidl_typesupport_introspection_c__ROS_TYPE_CHAR:
      return sizeof(char);
    case rosidl_typesupport_introspection_c__ROS_TYPE_WCHAR:
      return sizeof(char16_t);
    case rosidl_typesupport_introspection_c__ROS_TYPE_BOOLEAN:
      return sizeof(bool);
    case rosidl_typesupport_introspection_c__ROS_TYPE_OCTET:
    case rosidl_typesupport_introspection_c__ROS_TYPE_UINT8:
      return sizeof(std::uint8_t);
    case rosidl_typesupport_introspection_c__ROS_TYPE_INT8:
      return sizeof(std::int8_t);
    case rosidl_typesupport_introspection_c__ROS_TYPE_UINT16:
      return sizeof(std::uint16_t);
    case rosidl_typesupport_introspection_c__ROS_TYPE_INT16:
      return sizeof(std::int16_t);
    case rosidl_typesupport_introspection_c__ROS_TYPE_UINT32:
      return sizeof(std::uint32_t);
    case rosidl_typesupport_introspection_c__ROS_TYPE_INT32:
      return sizeof(std::int32_t);
    case rosidl_typesupport_introspection_c__ROS_TYPE_UINT64:
      return sizeof(std::uint64_t);
    case rosidl_typesupport_introspection_c__ROS_TYPE_INT64:
      return sizeof(std::int64_t);
    default:
      return 0;
  }
}

void append_u64(std::vector<std::uint8_t> * out, std::uint64_t value)
{
  for (int i = 0; i < 8; ++i) {
    out->push_back(static_cast<std::uint8_t>((value >> (8 * i)) & 0xFFu));
  }
}

bool read_u64(const std::vector<std::uint8_t> & payload, size_t * offset, std::uint64_t * value)
{
  if (offset == nullptr || value == nullptr || *offset + 8 > payload.size()) {
    return false;
  }
  std::uint64_t decoded = 0;
  for (int i = 0; i < 8; ++i) {
    decoded |= static_cast<std::uint64_t>(payload[*offset + i]) << (8 * i);
  }
  *offset += 8;
  *value = decoded;
  return true;
}

void append_bytes(
  std::vector<std::uint8_t> * out,
  const void * data,
  size_t size)
{
  const auto * bytes = static_cast<const std::uint8_t *>(data);
  out->insert(out->end(), bytes, bytes + size);
}

bool read_bytes(
  const std::vector<std::uint8_t> & payload,
  size_t * offset,
  void * data,
  size_t size)
{
  if (offset == nullptr || data == nullptr || *offset + size > payload.size()) {
    return false;
  }
  std::memcpy(data, payload.data() + *offset, size);
  *offset += size;
  return true;
}

bool serialize_introspection_c_message(
  const rosidl_typesupport_introspection_c__MessageMembers * members,
  const void * ros_message,
  std::vector<std::uint8_t> * out);

bool deserialize_introspection_c_message(
  const rosidl_typesupport_introspection_c__MessageMembers * members,
  const std::vector<std::uint8_t> & payload,
  size_t * offset,
  void * ros_message);

bool serialize_introspection_c_member(
  const rosidl_typesupport_introspection_c__MessageMember & member,
  const void * member_data,
  std::vector<std::uint8_t> * out)
{
  if (out == nullptr || member_data == nullptr) {
    return false;
  }
  if (member.type_id_ == rosidl_typesupport_introspection_c__ROS_TYPE_STRING) {
    const auto * value = static_cast<const rosidl_runtime_c__String *>(member_data);
    const size_t size = value->data == nullptr ? 0 : value->size;
    append_u64(out, static_cast<std::uint64_t>(size));
    if (size > 0) {
      append_bytes(out, value->data, size);
    }
    return true;
  }
  if (member.type_id_ == rosidl_typesupport_introspection_c__ROS_TYPE_MESSAGE) {
    return serialize_introspection_c_message(introspection_c_members(member.members_), member_data, out);
  }
  const size_t size = primitive_size(member.type_id_);
  if (size == 0) {
    return false;
  }
  append_bytes(out, member_data, size);
  return true;
}

const void * array_const_member_ptr(
  const rosidl_typesupport_introspection_c__MessageMember & member,
  const void * array_data,
  size_t index)
{
  if (member.get_const_function != nullptr) {
    return member.get_const_function(array_data, index);
  }
  const auto * nested_members = member.type_id_ == rosidl_typesupport_introspection_c__ROS_TYPE_MESSAGE ?
    introspection_c_members(member.members_) : nullptr;
  const size_t element_size = member.type_id_ == rosidl_typesupport_introspection_c__ROS_TYPE_MESSAGE ?
    (nested_members == nullptr ? 0 : nested_members->size_of_) : primitive_size(member.type_id_);
  if (element_size == 0) {
    return nullptr;
  }
  return static_cast<const std::uint8_t *>(array_data) + (element_size * index);
}

void * array_member_ptr(
  const rosidl_typesupport_introspection_c__MessageMember & member,
  void * array_data,
  size_t index)
{
  if (member.get_function != nullptr) {
    return member.get_function(array_data, index);
  }
  const auto * nested_members = member.type_id_ == rosidl_typesupport_introspection_c__ROS_TYPE_MESSAGE ?
    introspection_c_members(member.members_) : nullptr;
  const size_t element_size = member.type_id_ == rosidl_typesupport_introspection_c__ROS_TYPE_MESSAGE ?
    (nested_members == nullptr ? 0 : nested_members->size_of_) : primitive_size(member.type_id_);
  if (element_size == 0) {
    return nullptr;
  }
  return static_cast<std::uint8_t *>(array_data) + (element_size * index);
}

bool serialize_introspection_c_field(
  const rosidl_typesupport_introspection_c__MessageMember & member,
  const void * ros_message,
  std::vector<std::uint8_t> * out)
{
  const auto * member_data = static_cast<const std::uint8_t *>(ros_message) + member.offset_;
  if (!member.is_array_) {
    return serialize_introspection_c_member(member, member_data, out);
  }

  const size_t element_count = member.size_function != nullptr ?
    member.size_function(member_data) : member.array_size_;
  append_u64(out, static_cast<std::uint64_t>(element_count));
  for (size_t i = 0; i < element_count; ++i) {
    const void * element = array_const_member_ptr(member, member_data, i);
    if (element == nullptr || !serialize_introspection_c_member(member, element, out)) {
      return false;
    }
  }
  return true;
}

bool serialize_introspection_c_message(
  const rosidl_typesupport_introspection_c__MessageMembers * members,
  const void * ros_message,
  std::vector<std::uint8_t> * out)
{
  if (members == nullptr || ros_message == nullptr || out == nullptr) {
    return false;
  }
  append_u64(out, static_cast<std::uint64_t>(members->member_count_));
  for (uint32_t i = 0; i < members->member_count_; ++i) {
    if (!serialize_introspection_c_field(members->members_[i], ros_message, out)) {
      return false;
    }
  }
  return true;
}

bool deserialize_introspection_c_member(
  const rosidl_typesupport_introspection_c__MessageMember & member,
  const std::vector<std::uint8_t> & payload,
  size_t * offset,
  void * member_data)
{
  if (offset == nullptr || member_data == nullptr) {
    return false;
  }
  if (member.type_id_ == rosidl_typesupport_introspection_c__ROS_TYPE_STRING) {
    std::uint64_t size = 0;
    if (!read_u64(payload, offset, &size) || *offset + size > payload.size()) {
      return false;
    }
    if (member.string_upper_bound_ > 0 && size > member.string_upper_bound_) {
      return false;
    }
    auto * value = static_cast<rosidl_runtime_c__String *>(member_data);
    const char * source = reinterpret_cast<const char *>(payload.data() + *offset);
    if (!rosidl_runtime_c__String__assignn(value, source, static_cast<size_t>(size))) {
      return false;
    }
    *offset += static_cast<size_t>(size);
    return true;
  }
  if (member.type_id_ == rosidl_typesupport_introspection_c__ROS_TYPE_MESSAGE) {
    return deserialize_introspection_c_message(
      introspection_c_members(member.members_), payload, offset, member_data);
  }
  const size_t size = primitive_size(member.type_id_);
  if (size == 0) {
    return false;
  }
  return read_bytes(payload, offset, member_data, size);
}

bool deserialize_introspection_c_field(
  const rosidl_typesupport_introspection_c__MessageMember & member,
  const std::vector<std::uint8_t> & payload,
  size_t * offset,
  void * ros_message)
{
  auto * member_data = static_cast<std::uint8_t *>(ros_message) + member.offset_;
  if (!member.is_array_) {
    return deserialize_introspection_c_member(member, payload, offset, member_data);
  }

  std::uint64_t element_count = 0;
  if (!read_u64(payload, offset, &element_count)) {
    return false;
  }
  if (member.is_upper_bound_ && element_count > member.array_size_) {
    return false;
  }
  if (member.resize_function != nullptr) {
    if (!member.resize_function(member_data, static_cast<size_t>(element_count))) {
      return false;
    }
  } else if (element_count != member.array_size_) {
    return false;
  }
  for (size_t i = 0; i < static_cast<size_t>(element_count); ++i) {
    void * element = array_member_ptr(member, member_data, i);
    if (element == nullptr ||
      !deserialize_introspection_c_member(member, payload, offset, element))
    {
      return false;
    }
  }
  return true;
}

bool deserialize_introspection_c_message(
  const rosidl_typesupport_introspection_c__MessageMembers * members,
  const std::vector<std::uint8_t> & payload,
  size_t * offset,
  void * ros_message)
{
  if (members == nullptr || offset == nullptr || ros_message == nullptr) {
    return false;
  }
  std::uint64_t member_count = 0;
  if (!read_u64(payload, offset, &member_count) || member_count != members->member_count_) {
    return false;
  }
  for (uint32_t i = 0; i < members->member_count_; ++i) {
    if (!deserialize_introspection_c_field(members->members_[i], payload, offset, ros_message)) {
      return false;
    }
  }
  return true;
}

template<typename T, typename... Args>
T * allocate_data(rcutils_allocator_t allocator, Args &&... args)
{
  if (!rcutils_allocator_is_valid(&allocator)) {
    return nullptr;
  }
  void * memory = allocator.allocate(sizeof(T), allocator.state);
  if (memory == nullptr) {
    return nullptr;
  }
  try {
    return new (memory) T{std::forward<Args>(args)...};
  } catch (...) {
    allocator.deallocate(memory, allocator.state);
    return nullptr;
  }
}

template<typename T>
void deallocate_data(T * data)
{
  if (data == nullptr) {
    return;
  }
  rcutils_allocator_t allocator = data->allocator;
  data->~T();
  allocator.deallocate(data, allocator.state);
}

FleetQoxPublisherData * publisher_data(const rmw_publisher_t * publisher)
{
  return publisher == nullptr ? nullptr : static_cast<FleetQoxPublisherData *>(publisher->data);
}

FleetQoxSubscriptionData * subscription_data(const rmw_subscription_t * subscription)
{
  return subscription == nullptr ? nullptr : static_cast<FleetQoxSubscriptionData *>(subscription->data);
}

void maybe_renew_publisher_graph(FleetQoxPublisherData * data);

rmw_ret_t publish_payload(FleetQoxPublisherData * data, const std::vector<std::uint8_t> & payload)
{
  if (data == nullptr) {
    RMW_SET_ERROR_MSG("publisher data is null");
    return RMW_RET_INVALID_ARGUMENT;
  }
  const auto source_sequence = data->next_source_sequence++;
  const rmw_fleetqox_cpp::DataFrame frame{
    local_robot_id(),
    data->topic_name,
    data->publisher_id,
    source_sequence,
    monotonic_timestamp_ns(),
    payload};
  const std::string encoded_frame = rmw_fleetqox_cpp::encode_data_frame(frame);
  {
    std::lock_guard<std::mutex> lock(g_bus_mutex);
    g_retransmit_ledger[retransmit_ledger_key(data->publisher_id, source_sequence)] = encoded_frame;
  }
  maybe_renew_publisher_graph(data);
  return socket_transport().send_data_frame(encoded_frame, data->qos);
}

int repair_nack_interval_ms()
{
  static const int interval_ms = parse_nonnegative_int_env(
    "FLEETQOX_RMW_REPAIR_NACK_INTERVAL_MS", 75, 5000);
  return interval_ms;
}

std::optional<rmw_fleetqox_cpp::DataFrame> repair_marker_frame_from_stream_key(
  const std::string & key,
  std::uint64_t highest_observed_sequence,
  std::int64_t timestamp_ns)
{
  const std::vector<std::string> parts = split_nonempty(key, '|');
  if (parts.size() != 3) {
    return std::nullopt;
  }
  return rmw_fleetqox_cpp::DataFrame{
    parts[0],
    parts[1],
    parts[2],
    highest_observed_sequence,
    timestamp_ns,
    {}};
}

std::vector<std::string> idle_repair_ack_nacks(FleetQoxSubscriptionData * data)
{
  std::vector<std::string> payloads;
  if (data == nullptr) {
    return payloads;
  }
  const std::int64_t now = monotonic_timestamp_ns();
  const std::int64_t min_interval_ns =
    static_cast<std::int64_t>(repair_nack_interval_ms()) * 1000000ll;
  std::lock_guard<std::mutex> lock(g_bus_mutex);
  for (auto & entry : data->sequence_states) {
    rmw_fleetqox_cpp::SequenceState & state = entry.second;
    if (!state.initialized ||
      state.highest_contiguous_sequence >= state.highest_observed_sequence)
    {
      continue;
    }
    if (state.last_repair_request_ns > 0 &&
      now - state.last_repair_request_ns < min_interval_ns)
    {
      continue;
    }
    const auto marker = repair_marker_frame_from_stream_key(
      entry.first,
      state.highest_observed_sequence,
      now);
    if (!marker) {
      continue;
    }
    const rmw_fleetqox_cpp::AckNackFeedback feedback =
      rmw_fleetqox_cpp::feedback_from_sequence_state(state);
    if (feedback.missing_sequence_ranges.empty()) {
      continue;
    }
    state.last_repair_request_ns = now;
    payloads.push_back(rmw_fleetqox_cpp::encode_ack_nack(*marker, feedback));
  }
  return payloads;
}

void maybe_send_idle_repair_ack_nacks(FleetQoxSubscriptionData * data)
{
  const std::vector<std::string> payloads = idle_repair_ack_nacks(data);
  for (const std::string & payload : payloads) {
    const rmw_ret_t ret = socket_transport().send_ack_nack(payload);
    if (ret == RMW_RET_OK) {
      g_idle_repair_ack_nack_sent.fetch_add(1, std::memory_order_relaxed);
    }
    (void)ret;
  }
}

rmw_ret_t take_payload(
  FleetQoxSubscriptionData * data,
  std::vector<std::uint8_t> * payload,
  bool * taken)
{
  if (data == nullptr || payload == nullptr || taken == nullptr) {
    RMW_SET_ERROR_MSG("subscription data, payload, and taken must be non-null");
    return RMW_RET_INVALID_ARGUMENT;
  }
  *taken = false;
  while (true) {
    std::string encoded_frame;
    {
      std::lock_guard<std::mutex> lock(g_bus_mutex);
      if (data->frame_queue.empty()) {
        encoded_frame.clear();
      } else {
        encoded_frame = std::move(data->frame_queue.front());
        data->frame_queue.pop_front();
      }
    }
    if (encoded_frame.empty()) {
      maybe_send_idle_repair_ack_nacks(data);
      return RMW_RET_OK;
    }
    const auto decoded_frame = rmw_fleetqox_cpp::decode_data_frame(encoded_frame);
    if (!decoded_frame) {
      RMW_SET_ERROR_MSG("failed to decode FleetRMW data frame from subscription queue");
      return RMW_RET_ERROR;
    }
    if (frame_exceeds_lifespan(data->qos, decoded_frame->source_timestamp_ns)) {
      continue;
    }
    {
      std::lock_guard<std::mutex> lock(g_last_take_mutex);
      g_last_take_topic = decoded_frame->topic;
      g_last_take_publisher_id = decoded_frame->publisher_id;
      g_last_take_source_sequence = decoded_frame->source_sequence_number;
      g_last_take_source_timestamp_ns = decoded_frame->source_timestamp_ns;
      g_last_take_timestamp_ns = monotonic_timestamp_ns();
    }
    *payload = decoded_frame->serialized_payload;
    *taken = true;
    return RMW_RET_OK;
  }
}

size_t count_publishers_locked(const std::string & topic_name)
{
  return static_cast<size_t>(std::count_if(
    g_publishers.begin(),
    g_publishers.end(),
    [&](const FleetQoxPublisherData * data) {
      return data != nullptr && data->topic_name == topic_name;
    }));
}

size_t count_subscriptions_locked(const std::string & topic_name)
{
  return static_cast<size_t>(std::count_if(
    g_subscriptions.begin(),
    g_subscriptions.end(),
    [&](const FleetQoxSubscriptionData * data) {
      return data != nullptr && data->topic_name == topic_name;
    }));
}

void send_publisher_graph_advertisement(const FleetQoxPublisherData * data, const char * action)
{
  if (data == nullptr || action == nullptr) {
    return;
  }
  const rmw_ret_t graph_advertisement_ret =
    socket_transport().send_graph_advertisement(
      action,
      "publisher",
      data->node_name,
      data->node_namespace,
      data->topic_name,
      data->type_name,
      data->endpoint_id,
      data->endpoint_gid,
      data->qos);
  (void)graph_advertisement_ret;
}

void send_subscription_graph_advertisement(const FleetQoxSubscriptionData * data, const char * action)
{
  if (data == nullptr || action == nullptr) {
    return;
  }
  const rmw_ret_t graph_advertisement_ret =
    socket_transport().send_graph_advertisement(
      action,
      "subscription",
      data->node_name,
      data->node_namespace,
      data->topic_name,
      data->type_name,
      data->endpoint_id,
      data->endpoint_gid,
      data->qos);
  (void)graph_advertisement_ret;
  if (std::strcmp(action, "add") == 0) {
    const rmw_ret_t advertisement_ret =
      socket_transport().send_subscription_advertisement(data->topic_name, data->type_name);
    (void)advertisement_ret;
  }
}

void pubsub_graph_renewal_loop()
{
  constexpr auto kRenewInterval = std::chrono::milliseconds(500);
  while (true) {
    std::this_thread::sleep_for(kRenewInterval);
    std::lock_guard<std::mutex> lock(g_bus_mutex);
    for (const FleetQoxPublisherData * data : g_publishers) {
      send_publisher_graph_advertisement(data, "add");
    }
    for (const FleetQoxSubscriptionData * data : g_subscriptions) {
      send_subscription_graph_advertisement(data, "add");
    }
  }
}

void ensure_pubsub_graph_renewal_thread()
{
  bool expected = false;
  if (!g_pubsub_graph_renewal_started.compare_exchange_strong(expected, true)) {
    return;
  }
  std::thread(pubsub_graph_renewal_loop).detach();
}

void maybe_renew_publisher_graph(FleetQoxPublisherData * data)
{
  constexpr std::int64_t kGraphRenewIntervalNs = 500000000;
  if (data == nullptr || socket_transport().peer_count() == 0) {
    return;
  }
  const std::int64_t now = monotonic_timestamp_ns();
  if (now - data->last_graph_advertisement_ns < kGraphRenewIntervalNs) {
    return;
  }
  data->last_graph_advertisement_ns = now;
  send_publisher_graph_advertisement(data, "add");
}

void enqueue_received_frame(const std::string & encoded_frame)
{
  const auto decoded_frame = rmw_fleetqox_cpp::decode_data_frame(encoded_frame);
  if (!decoded_frame) {
    return;
  }

  std::vector<std::pair<rmw_event_callback_t, const void *>> callbacks;
  std::vector<std::string> ack_nack_payloads;
  size_t matched_subscriptions = 0;
  {
    std::lock_guard<std::mutex> lock(g_bus_mutex);
    for (FleetQoxSubscriptionData * subscription : g_subscriptions) {
      if (subscription != nullptr && subscription->topic_name == decoded_frame->topic) {
        if (frame_exceeds_lifespan(subscription->qos, decoded_frame->source_timestamp_ns)) {
          continue;
        }
        auto & sequence_state =
          subscription->sequence_states[rmw_fleetqox_cpp::stream_key(*decoded_frame)];
        const rmw_fleetqox_cpp::AckNackFeedback feedback =
          rmw_fleetqox_cpp::observe_frame(sequence_state, *decoded_frame);
        ack_nack_payloads.push_back(
          rmw_fleetqox_cpp::encode_ack_nack(*decoded_frame, feedback));
        if (feedback.out_of_order) {
          g_out_of_order_data_frames_observed.fetch_add(1, std::memory_order_relaxed);
        }
        if (feedback.duplicate) {
          g_duplicate_data_frames_deduped.fetch_add(1, std::memory_order_relaxed);
          continue;
        }
        ++matched_subscriptions;
        subscription->frame_queue.push_back(encoded_frame);
        enforce_subscription_depth_locked(subscription);
        if (subscription->on_new_message_callback != nullptr) {
          callbacks.emplace_back(
            subscription->on_new_message_callback,
            subscription->on_new_message_user_data);
        }
      }
    }
  }
  for (const std::string & payload : ack_nack_payloads) {
    const rmw_ret_t ret = socket_transport().send_ack_nack(payload);
    (void)ret;
  }
  if (trace_take_enabled()) {
    std::fprintf(
      stderr,
      "fleetqox enqueue topic=%s matched_subscriptions=%zu callbacks=%zu\n",
      decoded_frame->topic.c_str(),
      matched_subscriptions,
      callbacks.size());
  }
  for (const auto & callback : callbacks) {
    callback.first(callback.second, 1);
  }
}

bool apply_received_graph_advertisement(const std::string & encoded_frame)
{
  const auto advertisement = rmw_fleetqox_cpp::decode_graph_advertisement(encoded_frame);
  if (!advertisement) {
    return false;
  }
  const std::array<std::uint8_t, RMW_GID_STORAGE_SIZE> endpoint_gid =
    endpoint_gid_from_hex(advertisement->endpoint_gid, advertisement->endpoint_id);
  const rmw_qos_profile_t qos = rmw_qos_from_graph(advertisement->qos);
  rmw_fleetqox_cpp_graph_apply_remote_advertisement_with_info(
    advertisement->action.c_str(),
    advertisement->entity_kind.c_str(),
    advertisement->node_name.c_str(),
    advertisement->node_namespace.c_str(),
    advertisement->topic.c_str(),
    advertisement->type_name.c_str(),
    advertisement->endpoint_id.c_str(),
    endpoint_gid.data(),
    endpoint_gid.size(),
    &qos,
    advertisement->lease_ms);
  return true;
}

}  // namespace

extern "C"
{

void rmw_fleetqox_cpp_graph_register_publisher_endpoint(
  const char * node_name,
  const char * node_namespace,
  const char * topic_name,
  const char * type_name,
  const char * endpoint_id,
  const std::uint8_t * endpoint_gid,
  size_t endpoint_gid_size,
  const rmw_qos_profile_t * qos);
void rmw_fleetqox_cpp_graph_unregister_publisher_endpoint(const char * endpoint_id);
void rmw_fleetqox_cpp_graph_register_subscription_endpoint(
  const char * node_name,
  const char * node_namespace,
  const char * topic_name,
  const char * type_name,
  const char * endpoint_id,
  const std::uint8_t * endpoint_gid,
  size_t endpoint_gid_size,
  const rmw_qos_profile_t * qos);
void rmw_fleetqox_cpp_graph_unregister_subscription_endpoint(const char * endpoint_id);
void rmw_fleetqox_cpp_graph_apply_remote_advertisement_with_info(
  const char * action,
  const char * entity_kind,
  const char * node_name,
  const char * node_namespace,
  const char * topic_name,
  const char * type_name,
  const char * endpoint_id,
  const std::uint8_t * endpoint_gid,
  size_t endpoint_gid_size,
  const rmw_qos_profile_t * qos,
  std::uint64_t lease_ms);

bool rmw_fleetqox_cpp_subscription_has_data(const rmw_subscription_t * subscription)
{
  if (subscription == nullptr || !identifier_matches(subscription->implementation_identifier)) {
    return false;
  }
  FleetQoxSubscriptionData * data = subscription_data(subscription);
  if (data == nullptr) {
    return false;
  }
  std::lock_guard<std::mutex> lock(g_bus_mutex);
  return !data->frame_queue.empty();
}

bool rmw_fleetqox_cpp_subscription_data_has_data(const void * subscription_impl)
{
  if (subscription_impl == nullptr) {
    return false;
  }
  const auto * data = static_cast<const FleetQoxSubscriptionData *>(subscription_impl);
  std::lock_guard<std::mutex> lock(g_bus_mutex);
  return !data->frame_queue.empty();
}

bool rmw_fleetqox_cpp_waitable_subscription_has_data(const void * waitable)
{
  if (waitable == nullptr) {
    return false;
  }
  std::lock_guard<std::mutex> lock(g_bus_mutex);
  for (const FleetQoxSubscriptionData * data : g_subscriptions) {
    if (data == waitable) {
      return !data->frame_queue.empty();
    }
  }
  for (const rmw_subscription_t * subscription : g_subscription_handles) {
    if (subscription == waitable) {
      const auto * data = static_cast<const FleetQoxSubscriptionData *>(subscription->data);
      return data != nullptr && !data->frame_queue.empty();
    }
  }
  return false;
}

std::uint64_t rmw_fleetqox_cpp_socket_frames_sent()
{
  return socket_transport().frames_sent();
}

std::uint64_t rmw_fleetqox_cpp_socket_frames_received()
{
  return socket_transport().frames_received();
}

std::uint64_t rmw_fleetqox_cpp_socket_ack_nack_sent()
{
  return socket_transport().ack_nack_sent();
}

std::uint64_t rmw_fleetqox_cpp_socket_ack_nack_received()
{
  return socket_transport().ack_nack_received();
}

std::uint64_t rmw_fleetqox_cpp_socket_ack_nack_duplicate_received()
{
  return socket_transport().ack_nack_duplicate_received();
}

std::uint64_t rmw_fleetqox_cpp_socket_ack_nack_out_of_order_received()
{
  return socket_transport().ack_nack_out_of_order_received();
}

std::uint64_t rmw_fleetqox_cpp_socket_nack_retransmissions()
{
  return socket_transport().nack_retransmissions();
}

std::uint64_t rmw_fleetqox_cpp_socket_idle_repair_ack_nack_sent()
{
  return g_idle_repair_ack_nack_sent.load(std::memory_order_relaxed);
}

std::uint64_t rmw_fleetqox_cpp_socket_test_dropped_frames()
{
  return socket_transport().test_dropped_frames();
}

std::uint64_t rmw_fleetqox_cpp_duplicate_data_frames_deduped()
{
  return g_duplicate_data_frames_deduped.load(std::memory_order_relaxed);
}

std::uint64_t rmw_fleetqox_cpp_out_of_order_data_frames_observed()
{
  return g_out_of_order_data_frames_observed.load(std::memory_order_relaxed);
}

std::uint64_t rmw_fleetqox_cpp_last_take_source_sequence()
{
  std::lock_guard<std::mutex> lock(g_last_take_mutex);
  return g_last_take_source_sequence;
}

std::int64_t rmw_fleetqox_cpp_last_take_source_timestamp_ns()
{
  std::lock_guard<std::mutex> lock(g_last_take_mutex);
  return g_last_take_source_timestamp_ns;
}

std::int64_t rmw_fleetqox_cpp_last_take_timestamp_ns()
{
  std::lock_guard<std::mutex> lock(g_last_take_mutex);
  return g_last_take_timestamp_ns;
}

const char * rmw_fleetqox_cpp_last_take_topic()
{
  static thread_local std::string topic;
  std::lock_guard<std::mutex> lock(g_last_take_mutex);
  topic = g_last_take_topic;
  return topic.c_str();
}

const char * rmw_fleetqox_cpp_last_take_publisher_id()
{
  static thread_local std::string publisher_id;
  std::lock_guard<std::mutex> lock(g_last_take_mutex);
  publisher_id = g_last_take_publisher_id;
  return publisher_id.c_str();
}

std::uint64_t rmw_fleetqox_cpp_socket_adaptive_failovers()
{
  return socket_transport().adaptive_failovers();
}

std::uint64_t rmw_fleetqox_cpp_socket_adaptive_unicast_frames()
{
  return socket_transport().adaptive_unicast_frames();
}

std::uint64_t rmw_fleetqox_cpp_socket_adaptive_redundant_frames()
{
  return socket_transport().adaptive_redundant_frames();
}

std::uint64_t rmw_fleetqox_cpp_socket_fleet_plan_frames()
{
  return socket_transport().fleet_plan_frames();
}

std::uint64_t rmw_fleetqox_cpp_socket_fleet_plan_redundant_frames()
{
  return socket_transport().fleet_plan_redundant_frames();
}

std::uint64_t rmw_fleetqox_cpp_socket_fleet_plan_selected_path_count()
{
  return socket_transport().fleet_plan_selected_path_count();
}

const char * rmw_fleetqox_cpp_socket_fleet_plan_last_paths()
{
  static thread_local std::string paths;
  paths = socket_transport().fleet_plan_last_paths();
  return paths.c_str();
}

std::uint64_t rmw_fleetqox_cpp_socket_adaptive_peer_score_sum()
{
  return socket_transport().adaptive_peer_score_sum();
}

size_t rmw_fleetqox_cpp_socket_adaptive_selected_peer_index()
{
  return socket_transport().adaptive_selected_peer_index();
}

const char * rmw_fleetqox_cpp_socket_peer_policy()
{
  return socket_transport().peer_policy().c_str();
}

const char * rmw_fleetqox_cpp_socket_bound_endpoint()
{
  return socket_transport().bound_endpoint().c_str();
}

bool rmw_fleetqox_cpp_socket_ensure_started()
{
  return socket_transport().ready();
}

const char * rmw_fleetqox_cpp_socket_init_error()
{
  return socket_transport().init_error().c_str();
}

size_t rmw_fleetqox_cpp_socket_peer_count()
{
  return socket_transport().peer_count();
}

rmw_ret_t rmw_fleetqox_cpp_send_encoded_frame(const char * encoded_frame, size_t size)
{
  if (encoded_frame == nullptr || size == 0) {
    RMW_SET_ERROR_MSG("encoded frame must be non-empty");
    return RMW_RET_INVALID_ARGUMENT;
  }
  return socket_transport().send_frame(std::string(encoded_frame, size));
}

rmw_ret_t rmw_fleetqox_cpp_send_graph_advertisement(
  const char * action,
  const char * entity_kind,
  const char * node_name,
  const char * node_namespace,
  const char * topic_name,
  const char * type_name,
  const char * endpoint_id,
  const rmw_qos_profile_t * qos)
{
  if (action == nullptr || entity_kind == nullptr || topic_name == nullptr || type_name == nullptr ||
    endpoint_id == nullptr)
  {
    RMW_SET_ERROR_MSG("graph advertisement arguments must be non-null");
    return RMW_RET_INVALID_ARGUMENT;
  }
  const rmw_qos_profile_t effective_qos = qos != nullptr ? *qos : rmw_qos_profile_default;
  return socket_transport().send_graph_advertisement(
    action,
    entity_kind,
    node_name != nullptr ? node_name : "",
    node_namespace != nullptr ? node_namespace : "",
    topic_name,
    type_name,
    endpoint_id,
    make_endpoint_gid(endpoint_id),
    effective_qos);
}

bool rmw_fleetqox_cpp_serialize_introspection_message(
  const rosidl_typesupport_introspection_c__MessageMembers * members,
  const void * ros_message,
  std::vector<std::uint8_t> * payload)
{
  if (members == nullptr || ros_message == nullptr || payload == nullptr) {
    return false;
  }
  return serialize_introspection_c_message(members, ros_message, payload);
}

bool rmw_fleetqox_cpp_deserialize_introspection_message(
  const rosidl_typesupport_introspection_c__MessageMembers * members,
  const std::vector<std::uint8_t> * payload,
  void * ros_message)
{
  if (members == nullptr || payload == nullptr || ros_message == nullptr) {
    return false;
  }
  size_t offset = 0;
  return deserialize_introspection_c_message(members, *payload, &offset, ros_message) &&
         offset == payload->size();
}

bool rmw_fleetqox_cpp_publisher_gid(const rmw_publisher_t * publisher, rmw_gid_t * gid)
{
  if (publisher == nullptr || gid == nullptr || !identifier_matches(publisher->implementation_identifier)) {
    return false;
  }
  const FleetQoxPublisherData * data = publisher_data(publisher);
  if (data == nullptr) {
    return false;
  }
  gid->implementation_identifier = kIdentifier;
  std::memset(gid->data, 0, sizeof(gid->data));
  std::memcpy(gid->data, data->endpoint_gid.data(), data->endpoint_gid.size());
  return true;
}

rmw_publisher_t * rmw_create_publisher(
  const rmw_node_t * node,
  const rosidl_message_type_support_t * type_support,
  const char * topic_name,
  const rmw_qos_profile_t * qos_profile,
  const rmw_publisher_options_t * publisher_options)
{
  if (!node_is_valid(node)) {
    RMW_SET_ERROR_MSG("node is not a valid rmw_fleetqox_cpp node");
    return nullptr;
  }
  if (type_support == nullptr || qos_profile == nullptr || publisher_options == nullptr) {
    RMW_SET_ERROR_MSG("publisher type support, qos, and options must be non-null");
    return nullptr;
  }
  if (!topic_is_valid(topic_name)) {
    RMW_SET_ERROR_MSG("publisher topic must be a fully qualified ROS topic");
    return nullptr;
  }
  if (!socket_transport().ready()) {
    RMW_SET_ERROR_MSG(socket_transport().init_error().empty() ?
      "socket transport is not ready" : socket_transport().init_error().c_str());
    return nullptr;
  }
  const rosidl_message_type_support_t * effective_type_support =
    resolve_effective_type_support(type_support);

  rmw_publisher_t * publisher = rmw_publisher_allocate();
  if (publisher == nullptr) {
    RMW_SET_ERROR_MSG("failed to allocate publisher handle");
    return nullptr;
  }
  rcutils_allocator_t allocator = node->context->options.allocator;
  const std::string type_name = type_name_from_type_support(effective_type_support);
  const std::string publisher_id = allocate_publisher_id();
  const std::string endpoint_id = endpoint_id_for_local_id(publisher_id);
  const std::array<std::uint8_t, RMW_GID_STORAGE_SIZE> endpoint_gid =
    make_endpoint_gid(endpoint_id);
  FleetQoxPublisherData * data = allocate_data<FleetQoxPublisherData>(
    allocator,
    allocator,
    std::string(topic_name),
    type_name,
    std::string(node->name != nullptr ? node->name : ""),
    std::string(node->namespace_ != nullptr ? node->namespace_ : ""),
    publisher_id,
    endpoint_id,
    endpoint_gid,
    *qos_profile,
    effective_type_support,
    typed_message_size_from_type_support(effective_type_support),
    1u,
    monotonic_timestamp_ns());
  if (data == nullptr) {
    rmw_publisher_free(publisher);
    RMW_SET_ERROR_MSG("failed to allocate publisher data");
    return nullptr;
  }

  publisher->implementation_identifier = kIdentifier;
  publisher->data = data;
  publisher->topic_name = data->topic_name.c_str();
  publisher->options = *publisher_options;
  publisher->can_loan_messages = false;

  std::lock_guard<std::mutex> lock(g_bus_mutex);
  g_publishers.push_back(data);
  rmw_fleetqox_cpp_graph_register_publisher_endpoint(
    data->node_name.c_str(),
    data->node_namespace.c_str(),
    data->topic_name.c_str(),
    data->type_name.c_str(),
    data->endpoint_id.c_str(),
    data->endpoint_gid.data(),
    data->endpoint_gid.size(),
    &data->qos);
  send_publisher_graph_advertisement(data, "add");
  ensure_pubsub_graph_renewal_thread();
  return publisher;
}

rmw_ret_t rmw_destroy_publisher(rmw_node_t * node, rmw_publisher_t * publisher)
{
  if (!node_is_valid(node) || publisher == nullptr) {
    RMW_SET_ERROR_MSG("node and publisher must be valid");
    return RMW_RET_INVALID_ARGUMENT;
  }
  rmw_ret_t ret = require_identifier(publisher->implementation_identifier);
  if (ret != RMW_RET_OK) {
    return ret;
  }
  FleetQoxPublisherData * data = publisher_data(publisher);
  if (data != nullptr) {
    rmw_fleetqox_cpp_graph_unregister_publisher_endpoint(data->endpoint_id.c_str());
    send_publisher_graph_advertisement(data, "remove");
  }
  {
    std::lock_guard<std::mutex> lock(g_bus_mutex);
    g_publishers.erase(std::remove(g_publishers.begin(), g_publishers.end(), data), g_publishers.end());
    if (data != nullptr) {
      const std::string prefix = data->publisher_id + "|";
      for (auto it = g_retransmit_ledger.begin(); it != g_retransmit_ledger.end();) {
        if (it->first.rfind(prefix, 0) == 0) {
          it = g_retransmit_ledger.erase(it);
        } else {
          ++it;
        }
      }
    }
  }
  deallocate_data(data);
  rmw_publisher_free(publisher);
  return RMW_RET_OK;
}

rmw_subscription_t * rmw_create_subscription(
  const rmw_node_t * node,
  const rosidl_message_type_support_t * type_support,
  const char * topic_name,
  const rmw_qos_profile_t * qos_policies,
  const rmw_subscription_options_t * subscription_options)
{
  if (!node_is_valid(node)) {
    RMW_SET_ERROR_MSG("node is not a valid rmw_fleetqox_cpp node");
    return nullptr;
  }
  if (type_support == nullptr || qos_policies == nullptr || subscription_options == nullptr) {
    RMW_SET_ERROR_MSG("subscription type support, qos, and options must be non-null");
    return nullptr;
  }
  if (!topic_is_valid(topic_name)) {
    RMW_SET_ERROR_MSG("subscription topic must be a fully qualified ROS topic");
    return nullptr;
  }
  if (!socket_transport().ready()) {
    RMW_SET_ERROR_MSG(socket_transport().init_error().empty() ?
      "socket transport is not ready" : socket_transport().init_error().c_str());
    return nullptr;
  }
  const rosidl_message_type_support_t * effective_type_support =
    resolve_effective_type_support(type_support);

  rmw_subscription_t * subscription = rmw_subscription_allocate();
  if (subscription == nullptr) {
    RMW_SET_ERROR_MSG("failed to allocate subscription handle");
    return nullptr;
  }
  rcutils_allocator_t allocator = node->context->options.allocator;
  const std::string type_name = type_name_from_type_support(effective_type_support);
  const std::string subscription_id = allocate_subscription_id();
  const std::string endpoint_id = endpoint_id_for_local_id(subscription_id);
  const std::array<std::uint8_t, RMW_GID_STORAGE_SIZE> endpoint_gid =
    make_endpoint_gid(endpoint_id);
  FleetQoxSubscriptionData * data = allocate_data<FleetQoxSubscriptionData>(
    allocator,
    allocator,
    std::string(topic_name),
    type_name,
    std::string(node->name != nullptr ? node->name : ""),
    std::string(node->namespace_ != nullptr ? node->namespace_ : ""),
    subscription_id,
    endpoint_id,
    endpoint_gid,
    effective_type_support,
    typed_message_size_from_type_support(effective_type_support),
    *qos_policies,
    std::deque<std::string>{},
    std::unordered_map<std::string, rmw_fleetqox_cpp::SequenceState>{},
    nullptr,
    nullptr);
  if (data == nullptr) {
    rmw_subscription_free(subscription);
    RMW_SET_ERROR_MSG("failed to allocate subscription data");
    return nullptr;
  }

  subscription->implementation_identifier = kIdentifier;
  subscription->data = data;
  subscription->topic_name = data->topic_name.c_str();
  subscription->options = *subscription_options;
  subscription->can_loan_messages = false;
  subscription->is_cft_enabled = false;

  std::lock_guard<std::mutex> lock(g_bus_mutex);
  g_subscriptions.push_back(data);
  g_subscription_handles.push_back(subscription);
  rmw_fleetqox_cpp_graph_register_subscription_endpoint(
    data->node_name.c_str(),
    data->node_namespace.c_str(),
    data->topic_name.c_str(),
    data->type_name.c_str(),
    data->endpoint_id.c_str(),
    data->endpoint_gid.data(),
    data->endpoint_gid.size(),
    &data->qos);
  send_subscription_graph_advertisement(data, "add");
  ensure_pubsub_graph_renewal_thread();
  return subscription;
}

rmw_ret_t rmw_destroy_subscription(rmw_node_t * node, rmw_subscription_t * subscription)
{
  if (!node_is_valid(node) || subscription == nullptr) {
    RMW_SET_ERROR_MSG("node and subscription must be valid");
    return RMW_RET_INVALID_ARGUMENT;
  }
  rmw_ret_t ret = require_identifier(subscription->implementation_identifier);
  if (ret != RMW_RET_OK) {
    return ret;
  }
  FleetQoxSubscriptionData * data = subscription_data(subscription);
  if (data != nullptr) {
    rmw_fleetqox_cpp_graph_unregister_subscription_endpoint(data->endpoint_id.c_str());
    send_subscription_graph_advertisement(data, "remove");
  }
  {
    std::lock_guard<std::mutex> lock(g_bus_mutex);
    g_subscriptions.erase(
      std::remove(g_subscriptions.begin(), g_subscriptions.end(), data),
      g_subscriptions.end());
    g_subscription_handles.erase(
      std::remove(g_subscription_handles.begin(), g_subscription_handles.end(), subscription),
      g_subscription_handles.end());
  }
  deallocate_data(data);
  rmw_subscription_free(subscription);
  return RMW_RET_OK;
}

rmw_ret_t rmw_publish(
  const rmw_publisher_t * publisher,
  const void * ros_message,
  rmw_publisher_allocation_t * allocation)
{
  (void)allocation;
  if (publisher == nullptr || ros_message == nullptr) {
    RMW_SET_ERROR_MSG("publisher and ros_message must be non-null");
    return RMW_RET_INVALID_ARGUMENT;
  }
  rmw_ret_t ret = require_identifier(publisher->implementation_identifier);
  if (ret != RMW_RET_OK) {
    return ret;
  }
  FleetQoxPublisherData * data = publisher_data(publisher);
  if (data == nullptr) {
    RMW_SET_ERROR_MSG("publisher data is null");
    return RMW_RET_INVALID_ARGUMENT;
  }
  const auto * introspection_members = introspection_c_members(data->type_support);
  if (introspection_members != nullptr) {
    std::vector<std::uint8_t> payload;
    if (!serialize_introspection_c_message(introspection_members, ros_message, &payload)) {
      RMW_SET_ERROR_MSG("failed to serialize ROS message with introspection C type support");
      return RMW_RET_UNSUPPORTED;
    }
    return publish_payload(data, payload);
  }
  if (data->typed_message_size == 0) {
    RMW_SET_ERROR_MSG("typed rmw_publish requires introspection C type support or rmw_fleetqox_cpp type-erased descriptor");
    return RMW_RET_UNSUPPORTED;
  }
  const auto * typed_bytes = static_cast<const std::uint8_t *>(ros_message);
  const std::vector<std::uint8_t> payload(typed_bytes, typed_bytes + data->typed_message_size);
  return publish_payload(data, payload);
}

rmw_ret_t rmw_publish_serialized_message(
  const rmw_publisher_t * publisher,
  const rmw_serialized_message_t * serialized_message,
  rmw_publisher_allocation_t * allocation)
{
  (void)allocation;
  if (publisher == nullptr || serialized_message == nullptr) {
    RMW_SET_ERROR_MSG("publisher and serialized_message must be non-null");
    return RMW_RET_INVALID_ARGUMENT;
  }
  rmw_ret_t ret = require_identifier(publisher->implementation_identifier);
  if (ret != RMW_RET_OK) {
    return ret;
  }
  FleetQoxPublisherData * data = publisher_data(publisher);
  if (data == nullptr) {
    RMW_SET_ERROR_MSG("publisher data is null");
    return RMW_RET_INVALID_ARGUMENT;
  }
  if (serialized_message->buffer_length > 0 && serialized_message->buffer == nullptr) {
    RMW_SET_ERROR_MSG("serialized message buffer is null");
    return RMW_RET_INVALID_ARGUMENT;
  }

  std::vector<std::uint8_t> payload(
    serialized_message->buffer,
    serialized_message->buffer + serialized_message->buffer_length);
  return publish_payload(data, payload);
}

rmw_ret_t rmw_take(
  const rmw_subscription_t * subscription,
  void * ros_message,
  bool * taken,
  rmw_subscription_allocation_t * allocation)
{
  (void)allocation;
  if (subscription == nullptr || ros_message == nullptr || taken == nullptr) {
    RMW_SET_ERROR_MSG("subscription, ros_message, and taken must be non-null");
    return RMW_RET_INVALID_ARGUMENT;
  }
  rmw_ret_t ret = require_identifier(subscription->implementation_identifier);
  if (ret != RMW_RET_OK) {
    return ret;
  }
  FleetQoxSubscriptionData * data = subscription_data(subscription);
  if (data == nullptr) {
    RMW_SET_ERROR_MSG("subscription data is null");
    return RMW_RET_INVALID_ARGUMENT;
  }
  const auto * introspection_members = introspection_c_members(data->type_support);
  if (introspection_members != nullptr) {
    std::vector<std::uint8_t> payload;
    ret = take_payload(data, &payload, taken);
    if (trace_take_enabled()) {
      std::fprintf(
        stderr,
        "fleetqox rmw_take topic=%s taken=%s payload_size=%zu introspection=true\n",
        data->topic_name.c_str(),
        *taken ? "true" : "false",
        payload.size());
    }
    if (ret != RMW_RET_OK || !*taken) {
      return ret;
    }
    size_t offset = 0;
    if (!deserialize_introspection_c_message(introspection_members, payload, &offset, ros_message) ||
      offset != payload.size())
    {
      *taken = false;
      if (trace_take_enabled()) {
        std::fprintf(
          stderr,
          "fleetqox rmw_take deserialize_failed topic=%s offset=%zu payload_size=%zu\n",
          data->topic_name.c_str(),
          offset,
          payload.size());
      }
      RMW_SET_ERROR_MSG("failed to deserialize ROS message with introspection C type support");
      return RMW_RET_ERROR;
    }
    if (trace_take_enabled()) {
      std::fprintf(
        stderr,
        "fleetqox rmw_take deserialize_ok topic=%s offset=%zu\n",
        data->topic_name.c_str(),
        offset);
    }
    return RMW_RET_OK;
  }
  if (data->typed_message_size == 0) {
    *taken = false;
    RMW_SET_ERROR_MSG("typed rmw_take requires introspection C type support or rmw_fleetqox_cpp type-erased descriptor");
    return RMW_RET_UNSUPPORTED;
  }
  std::vector<std::uint8_t> payload;
  ret = take_payload(data, &payload, taken);
  if (ret != RMW_RET_OK || !*taken) {
    return ret;
  }
  if (payload.size() != data->typed_message_size) {
    *taken = false;
    RMW_SET_ERROR_MSG("typed FleetRMW payload size does not match descriptor");
    return RMW_RET_ERROR;
  }
  std::memcpy(ros_message, payload.data(), payload.size());
  return RMW_RET_OK;
}

rmw_ret_t rmw_take_with_info(
  const rmw_subscription_t * subscription,
  void * ros_message,
  bool * taken,
  rmw_message_info_t * message_info,
  rmw_subscription_allocation_t * allocation)
{
  if (message_info == nullptr) {
    RMW_SET_ERROR_MSG("message_info must be non-null");
    return RMW_RET_INVALID_ARGUMENT;
  }
  *message_info = rmw_message_info_t{};
  return rmw_take(subscription, ros_message, taken, allocation);
}

rmw_ret_t rmw_take_serialized_message(
  const rmw_subscription_t * subscription,
  rmw_serialized_message_t * serialized_message,
  bool * taken,
  rmw_subscription_allocation_t * allocation)
{
  (void)allocation;
  if (subscription == nullptr || serialized_message == nullptr || taken == nullptr) {
    RMW_SET_ERROR_MSG("subscription, serialized_message, and taken must be non-null");
    return RMW_RET_INVALID_ARGUMENT;
  }
  rmw_ret_t ret = require_identifier(subscription->implementation_identifier);
  if (ret != RMW_RET_OK) {
    return ret;
  }
  FleetQoxSubscriptionData * data = subscription_data(subscription);
  if (data == nullptr) {
    RMW_SET_ERROR_MSG("subscription data is null");
    return RMW_RET_INVALID_ARGUMENT;
  }

  std::vector<std::uint8_t> payload;
  ret = take_payload(data, &payload, taken);
  if (ret != RMW_RET_OK || !*taken) {
    return ret;
  }

  if (payload.size() > serialized_message->buffer_capacity) {
    const auto resize_ret = rmw_serialized_message_resize(serialized_message, payload.size());
    if (resize_ret != RMW_RET_OK) {
      RMW_SET_ERROR_MSG("failed to resize serialized message output");
      return RMW_RET_BAD_ALLOC;
    }
  }
  if (!payload.empty()) {
    std::memcpy(serialized_message->buffer, payload.data(), payload.size());
  }
  serialized_message->buffer_length = payload.size();
  *taken = true;
  return RMW_RET_OK;
}

rmw_ret_t rmw_take_serialized_message_with_info(
  const rmw_subscription_t * subscription,
  rmw_serialized_message_t * serialized_message,
  bool * taken,
  rmw_message_info_t * message_info,
  rmw_subscription_allocation_t * allocation)
{
  if (message_info == nullptr) {
    RMW_SET_ERROR_MSG("message_info must be non-null");
    return RMW_RET_INVALID_ARGUMENT;
  }
  *message_info = rmw_message_info_t{};
  return rmw_take_serialized_message(subscription, serialized_message, taken, allocation);
}

rmw_ret_t rmw_publisher_count_matched_subscriptions(
  const rmw_publisher_t * publisher,
  size_t * subscription_count)
{
  if (publisher == nullptr || subscription_count == nullptr) {
    RMW_SET_ERROR_MSG("publisher and subscription_count must be non-null");
    return RMW_RET_INVALID_ARGUMENT;
  }
  rmw_ret_t ret = require_identifier(publisher->implementation_identifier);
  if (ret != RMW_RET_OK) {
    return ret;
  }
  FleetQoxPublisherData * data = publisher_data(publisher);
  if (data == nullptr) {
    RMW_SET_ERROR_MSG("publisher data is null");
    return RMW_RET_INVALID_ARGUMENT;
  }
  *subscription_count = rmw_fleetqox_cpp_graph_subscription_count(data->topic_name.c_str());
  return RMW_RET_OK;
}

rmw_ret_t rmw_subscription_count_matched_publishers(
  const rmw_subscription_t * subscription,
  size_t * publisher_count)
{
  if (subscription == nullptr || publisher_count == nullptr) {
    RMW_SET_ERROR_MSG("subscription and publisher_count must be non-null");
    return RMW_RET_INVALID_ARGUMENT;
  }
  rmw_ret_t ret = require_identifier(subscription->implementation_identifier);
  if (ret != RMW_RET_OK) {
    return ret;
  }
  FleetQoxSubscriptionData * data = subscription_data(subscription);
  if (data == nullptr) {
    RMW_SET_ERROR_MSG("subscription data is null");
    return RMW_RET_INVALID_ARGUMENT;
  }
  *publisher_count = rmw_fleetqox_cpp_graph_publisher_count(data->topic_name.c_str());
  return RMW_RET_OK;
}

rmw_ret_t rmw_publisher_get_actual_qos(
  const rmw_publisher_t * publisher,
  rmw_qos_profile_t * qos)
{
  if (publisher == nullptr || qos == nullptr) {
    RMW_SET_ERROR_MSG("publisher and qos must be non-null");
    return RMW_RET_INVALID_ARGUMENT;
  }
  rmw_ret_t ret = require_identifier(publisher->implementation_identifier);
  if (ret != RMW_RET_OK) {
    return ret;
  }
  FleetQoxPublisherData * data = publisher_data(publisher);
  if (data == nullptr) {
    RMW_SET_ERROR_MSG("publisher data is null");
    return RMW_RET_INVALID_ARGUMENT;
  }
  *qos = data->qos;
  return RMW_RET_OK;
}

rmw_ret_t rmw_subscription_get_actual_qos(
  const rmw_subscription_t * subscription,
  rmw_qos_profile_t * qos)
{
  if (subscription == nullptr || qos == nullptr) {
    RMW_SET_ERROR_MSG("subscription and qos must be non-null");
    return RMW_RET_INVALID_ARGUMENT;
  }
  rmw_ret_t ret = require_identifier(subscription->implementation_identifier);
  if (ret != RMW_RET_OK) {
    return ret;
  }
  FleetQoxSubscriptionData * data = subscription_data(subscription);
  if (data == nullptr) {
    RMW_SET_ERROR_MSG("subscription data is null");
    return RMW_RET_INVALID_ARGUMENT;
  }
  *qos = data->qos;
  return RMW_RET_OK;
}

rmw_ret_t rmw_subscription_set_on_new_message_callback(
  rmw_subscription_t * subscription,
  rmw_event_callback_t callback,
  const void * user_data)
{
  if (subscription == nullptr) {
    RMW_SET_ERROR_MSG("subscription is null");
    return RMW_RET_INVALID_ARGUMENT;
  }
  rmw_ret_t ret = require_identifier(subscription->implementation_identifier);
  if (ret != RMW_RET_OK) {
    return ret;
  }
  FleetQoxSubscriptionData * data = subscription_data(subscription);
  if (data == nullptr) {
    RMW_SET_ERROR_MSG("subscription data is null");
    return RMW_RET_INVALID_ARGUMENT;
  }
  std::lock_guard<std::mutex> lock(g_bus_mutex);
  data->on_new_message_callback = callback;
  data->on_new_message_user_data = user_data;
  return RMW_RET_OK;
}

}  // extern "C"

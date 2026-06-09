#include <algorithm>
#include <chrono>
#include <cstdint>
#include <cstring>
#include <iostream>
#include <sstream>
#include <string>
#include <thread>
#include <vector>

#include "rcutils/allocator.h"
#include "rmw/init.h"
#include "rmw/init_options.h"
#include "rmw/publisher_options.h"
#include "rmw/qos_profiles.h"
#include "rmw/rmw.h"
#include "rmw/serialized_message.h"
#include "rmw/subscription_options.h"
#include "rosidl_runtime_c/message_type_support_struct.h"

extern "C" std::uint64_t rmw_fleetqox_cpp_socket_ack_nack_received();
extern "C" std::uint64_t rmw_fleetqox_cpp_socket_ack_nack_sent();
extern "C" std::uint64_t rmw_fleetqox_cpp_socket_nack_retransmissions();
extern "C" std::uint64_t rmw_fleetqox_cpp_socket_test_dropped_frames();

namespace
{

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

void cleanup_context(rmw_context_t * context, rmw_init_options_t * options)
{
  const rmw_ret_t shutdown_ret = rmw_shutdown(context);
  const rmw_ret_t context_fini_ret = rmw_context_fini(context);
  const rmw_ret_t options_fini_ret = rmw_init_options_fini(options);
  (void)shutdown_ret;
  (void)context_fini_ret;
  (void)options_fini_ret;
}

bool init_serialized_message(
  rmw_serialized_message_t * message,
  const std::string & payload,
  rcutils_allocator_t * allocator)
{
  if (rmw_serialized_message_init(message, payload.size(), allocator) != RMW_RET_OK) {
    return false;
  }
  if (!payload.empty()) {
    std::memcpy(message->buffer, payload.data(), payload.size());
  }
  message->buffer_length = payload.size();
  return true;
}

std::string serialized_message_string(const rmw_serialized_message_t & message)
{
  if (message.buffer == nullptr || message.buffer_length == 0) {
    return "";
  }
  return std::string(
    reinterpret_cast<const char *>(message.buffer),
    reinterpret_cast<const char *>(message.buffer + message.buffer_length));
}

bool take_until(
  rmw_subscription_t * subscription,
  rmw_serialized_message_t * incoming,
  const std::string & expected,
  std::vector<std::string> * received_payloads,
  int timeout_ms)
{
  const auto deadline = std::chrono::steady_clock::now() + std::chrono::milliseconds(timeout_ms);
  while (std::chrono::steady_clock::now() < deadline) {
    bool taken = false;
    const rmw_ret_t ret = rmw_take_serialized_message(subscription, incoming, &taken, nullptr);
    if (ret != RMW_RET_OK) {
      return false;
    }
    if (taken) {
      const std::string payload = serialized_message_string(*incoming);
      received_payloads->push_back(payload);
      if (payload == expected) {
        return true;
      }
    }
    std::this_thread::sleep_for(std::chrono::milliseconds(1));
  }
  return false;
}

bool contains_payload(const std::vector<std::string> & payloads, const std::string & expected)
{
  return std::find(payloads.begin(), payloads.end(), expected) != payloads.end();
}

}  // namespace

int main()
{
  rcutils_allocator_t allocator = rcutils_get_default_allocator();
  rmw_init_options_t options = rmw_get_zero_initialized_init_options();
  rmw_ret_t ret = rmw_init_options_init(&options, allocator);
  if (ret != RMW_RET_OK) {
    std::cout << "{\"status\":\"init_options_failed\",\"ret\":" << ret << "}" << std::endl;
    return 1;
  }
  options.instance_id = 48;

  rmw_context_t context = rmw_get_zero_initialized_context();
  ret = rmw_init(&options, &context);
  if (ret != RMW_RET_OK) {
    const rmw_ret_t fini_ret = rmw_init_options_fini(&options);
    (void)fini_ret;
    std::cout << "{\"status\":\"init_failed\",\"ret\":" << ret << "}" << std::endl;
    return 1;
  }

  rmw_node_t * node = rmw_create_node(&context, "fleetqox_reliability_probe", "/fleetqox");
  if (node == nullptr) {
    cleanup_context(&context, &options);
    std::cout << "{\"status\":\"create_node_failed\"}" << std::endl;
    return 1;
  }

  rosidl_message_type_support_t type_support{};
  type_support.typesupport_identifier = "rmw_fleetqox_cpp_reliability_probe";
  rmw_publisher_options_t publisher_options = rmw_get_default_publisher_options();
  rmw_subscription_options_t subscription_options = rmw_get_default_subscription_options();
  rmw_qos_profile_t qos = rmw_qos_profile_default;
  const char * topic = "/fleetqox/reliability_probe";

  rmw_publisher_t * publisher =
    rmw_create_publisher(node, &type_support, topic, &qos, &publisher_options);
  rmw_subscription_t * subscription =
    rmw_create_subscription(node, &type_support, topic, &qos, &subscription_options);
  if (publisher == nullptr || subscription == nullptr) {
    std::cout << "{\"status\":\"create_pubsub_failed\"}" << std::endl;
    return 1;
  }

  rmw_serialized_message_t one = rmw_get_zero_initialized_serialized_message();
  rmw_serialized_message_t two = rmw_get_zero_initialized_serialized_message();
  rmw_serialized_message_t three = rmw_get_zero_initialized_serialized_message();
  rmw_serialized_message_t incoming = rmw_get_zero_initialized_serialized_message();
  if (!init_serialized_message(&one, "one", &allocator) ||
    !init_serialized_message(&two, "two", &allocator) ||
    !init_serialized_message(&three, "three", &allocator) ||
    rmw_serialized_message_init(&incoming, 1, &allocator) != RMW_RET_OK)
  {
    std::cout << "{\"status\":\"serialized_message_init_failed\"}" << std::endl;
    return 1;
  }

  const std::uint64_t dropped_before = rmw_fleetqox_cpp_socket_test_dropped_frames();
  const std::uint64_t ack_sent_before = rmw_fleetqox_cpp_socket_ack_nack_sent();
  const std::uint64_t ack_received_before = rmw_fleetqox_cpp_socket_ack_nack_received();
  const std::uint64_t retrans_before = rmw_fleetqox_cpp_socket_nack_retransmissions();

  std::vector<std::string> received_payloads;
  const rmw_ret_t publish_one_ret = rmw_publish_serialized_message(publisher, &one, nullptr);
  const bool took_one = publish_one_ret == RMW_RET_OK &&
    take_until(subscription, &incoming, "one", &received_payloads, 1000);

  const rmw_ret_t publish_two_ret = rmw_publish_serialized_message(publisher, &two, nullptr);
  const rmw_ret_t publish_three_ret = rmw_publish_serialized_message(publisher, &three, nullptr);
  const bool took_three = publish_three_ret == RMW_RET_OK &&
    take_until(subscription, &incoming, "three", &received_payloads, 1000);
  const bool took_retransmitted_two = publish_two_ret == RMW_RET_OK &&
    take_until(subscription, &incoming, "two", &received_payloads, 2000);

  const std::uint64_t dropped =
    rmw_fleetqox_cpp_socket_test_dropped_frames() - dropped_before;
  const std::uint64_t ack_sent =
    rmw_fleetqox_cpp_socket_ack_nack_sent() - ack_sent_before;
  const std::uint64_t ack_received =
    rmw_fleetqox_cpp_socket_ack_nack_received() - ack_received_before;
  const std::uint64_t retransmissions =
    rmw_fleetqox_cpp_socket_nack_retransmissions() - retrans_before;

  const rmw_ret_t one_fini_ret = rmw_serialized_message_fini(&one);
  const rmw_ret_t two_fini_ret = rmw_serialized_message_fini(&two);
  const rmw_ret_t three_fini_ret = rmw_serialized_message_fini(&three);
  const rmw_ret_t incoming_fini_ret = rmw_serialized_message_fini(&incoming);
  const rmw_ret_t destroy_pub_ret = rmw_destroy_publisher(node, publisher);
  const rmw_ret_t destroy_sub_ret = rmw_destroy_subscription(node, subscription);
  const rmw_ret_t destroy_node_ret = rmw_destroy_node(node);
  cleanup_context(&context, &options);

  const bool cleanup_ok =
    one_fini_ret == RMW_RET_OK &&
    two_fini_ret == RMW_RET_OK &&
    three_fini_ret == RMW_RET_OK &&
    incoming_fini_ret == RMW_RET_OK &&
    destroy_pub_ret == RMW_RET_OK &&
    destroy_sub_ret == RMW_RET_OK &&
    destroy_node_ret == RMW_RET_OK;
  const bool reliability_ok =
    took_one &&
    took_three &&
    took_retransmitted_two &&
    contains_payload(received_payloads, "one") &&
    contains_payload(received_payloads, "two") &&
    contains_payload(received_payloads, "three") &&
    dropped >= 1 &&
    ack_sent >= 2 &&
    ack_received >= 2 &&
    retransmissions >= 1;

  std::cout << "{\"schema_version\":\"fleetrmw.rmw_reliability_probe.v1\",";
  std::cout << "\"status\":\"" << (reliability_ok && cleanup_ok ? "ok" : "failed") << "\",";
  std::cout << "\"topic\":\"" << topic << "\",";
  std::cout << "\"drop_source_sequences\":[2],";
  std::cout << "\"test_dropped_frames\":" << dropped << ",";
  std::cout << "\"ack_nack_sent\":" << ack_sent << ",";
  std::cout << "\"ack_nack_received\":" << ack_received << ",";
  std::cout << "\"nack_retransmissions\":" << retransmissions << ",";
  std::cout << "\"received_payloads\":[";
  for (size_t i = 0; i < received_payloads.size(); ++i) {
    if (i > 0) {
      std::cout << ",";
    }
    std::cout << "\"" << json_escape(received_payloads[i]) << "\"";
  }
  std::cout << "]}";
  std::cout << std::endl;

  return reliability_ok && cleanup_ok ? 0 : 1;
}

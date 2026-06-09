#include <chrono>
#include <cstdint>
#include <cstring>
#include <iostream>
#include <sstream>
#include <string>
#include <thread>

#include "rcutils/allocator.h"
#include "rmw/init.h"
#include "rmw/init_options.h"
#include "rmw/publisher_options.h"
#include "rmw/qos_profiles.h"
#include "rmw/rmw.h"
#include "rmw/serialized_message.h"
#include "rmw/subscription_options.h"
#include "rosidl_runtime_c/message_type_support_struct.h"

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

}  // namespace

extern "C" std::uint64_t rmw_fleetqox_cpp_socket_frames_sent();
extern "C" std::uint64_t rmw_fleetqox_cpp_socket_frames_received();

int main()
{
  rcutils_allocator_t allocator = rcutils_get_default_allocator();
  rmw_init_options_t options = rmw_get_zero_initialized_init_options();
  rmw_ret_t ret = rmw_init_options_init(&options, allocator);
  if (ret != RMW_RET_OK) {
    std::cout << "{\"status\":\"init_options_failed\",\"ret\":" << ret << "}" << std::endl;
    return 1;
  }
  options.instance_id = 43;

  rmw_context_t context = rmw_get_zero_initialized_context();
  ret = rmw_init(&options, &context);
  if (ret != RMW_RET_OK) {
    const rmw_ret_t fini_ret = rmw_init_options_fini(&options);
    (void)fini_ret;
    std::cout << "{\"status\":\"init_failed\",\"ret\":" << ret << "}" << std::endl;
    return 1;
  }

  rmw_node_t * node = rmw_create_node(&context, "fleetqox_serialized_pubsub_probe", "/fleetqox");
  if (node == nullptr) {
    cleanup_context(&context, &options);
    std::cout << "{\"status\":\"create_node_failed\"}" << std::endl;
    return 1;
  }

  rosidl_message_type_support_t type_support{};
  type_support.typesupport_identifier = "rmw_fleetqox_cpp_serialized_probe";
  rmw_publisher_options_t publisher_options = rmw_get_default_publisher_options();
  rmw_subscription_options_t subscription_options = rmw_get_default_subscription_options();
  rmw_qos_profile_t qos = rmw_qos_profile_default;
  const char * topic = "/fleetqox/serialized_probe";

  rmw_publisher_t * publisher = rmw_create_publisher(
    node, &type_support, topic, &qos, &publisher_options);
  rmw_subscription_t * subscription = rmw_create_subscription(
    node, &type_support, topic, &qos, &subscription_options);
  if (publisher == nullptr || subscription == nullptr) {
    if (publisher != nullptr) {
      const rmw_ret_t destroy_pub_ret = rmw_destroy_publisher(node, publisher);
      (void)destroy_pub_ret;
    }
    if (subscription != nullptr) {
      const rmw_ret_t destroy_sub_ret = rmw_destroy_subscription(node, subscription);
      (void)destroy_sub_ret;
    }
    const rmw_ret_t destroy_node_ret = rmw_destroy_node(node);
    (void)destroy_node_ret;
    cleanup_context(&context, &options);
    std::cout << "{\"status\":\"create_pubsub_failed\"}" << std::endl;
    return 1;
  }

  const std::string payload = "fleetrmw-cdr-bytes";
  rmw_serialized_message_t outgoing = rmw_get_zero_initialized_serialized_message();
  rmw_serialized_message_t incoming = rmw_get_zero_initialized_serialized_message();
  if (rmw_serialized_message_init(&outgoing, payload.size(), &allocator) != RMW_RET_OK ||
    rmw_serialized_message_init(&incoming, 1, &allocator) != RMW_RET_OK)
  {
    std::cout << "{\"status\":\"serialized_message_init_failed\"}" << std::endl;
    return 1;
  }
  std::memcpy(outgoing.buffer, payload.data(), payload.size());
  outgoing.buffer_length = payload.size();

  const std::uint64_t socket_sent_before = rmw_fleetqox_cpp_socket_frames_sent();
  const std::uint64_t socket_received_before = rmw_fleetqox_cpp_socket_frames_received();
  ret = rmw_publish_serialized_message(publisher, &outgoing, nullptr);
  bool taken = false;
  if (ret == RMW_RET_OK) {
    for (int attempt = 0; attempt < 100 && !taken; ++attempt) {
      ret = rmw_take_serialized_message(subscription, &incoming, &taken, nullptr);
      if (ret != RMW_RET_OK || taken) {
        break;
      }
      std::this_thread::sleep_for(std::chrono::milliseconds(1));
    }
  }
  const std::uint64_t socket_frames_sent =
    rmw_fleetqox_cpp_socket_frames_sent() - socket_sent_before;
  const std::uint64_t socket_frames_received =
    rmw_fleetqox_cpp_socket_frames_received() - socket_received_before;

  size_t matched_subscriptions = 0;
  size_t matched_publishers = 0;
  const rmw_ret_t pub_count_ret =
    rmw_publisher_count_matched_subscriptions(publisher, &matched_subscriptions);
  const rmw_ret_t sub_count_ret =
    rmw_subscription_count_matched_publishers(subscription, &matched_publishers);
  (void)pub_count_ret;
  (void)sub_count_ret;

  std::string received;
  if (taken && incoming.buffer != nullptr) {
    received.assign(
      reinterpret_cast<const char *>(incoming.buffer),
      reinterpret_cast<const char *>(incoming.buffer + incoming.buffer_length));
  }

  std::cout << "{\"schema_version\":\"fleetrmw.rmw_serialized_pubsub_probe.v1\",";
  std::cout << "\"status\":\"" << (ret == RMW_RET_OK && taken && received == payload ? "ok" : "failed") << "\",";
  std::cout << "\"topic\":\"" << topic << "\",";
  std::cout << "\"published_bytes\":" << outgoing.buffer_length << ",";
  std::cout << "\"taken\":" << (taken ? "true" : "false") << ",";
  std::cout << "\"taken_bytes\":" << incoming.buffer_length << ",";
  std::cout << "\"data_frame_wrapped\":true,";
  std::cout << "\"data_frame_schema\":\"fleetrmw.data_frame.v1\",";
  std::cout << "\"socket_backed\":true,";
  std::cout << "\"socket_frames_sent\":" << socket_frames_sent << ",";
  std::cout << "\"socket_frames_received\":" << socket_frames_received << ",";
  std::cout << "\"matched_publishers\":" << matched_publishers << ",";
  std::cout << "\"matched_subscriptions\":" << matched_subscriptions << ",";
  std::cout << "\"payload\":\"" << json_escape(received) << "\"}" << std::endl;

  const rmw_ret_t outgoing_fini_ret = rmw_serialized_message_fini(&outgoing);
  const rmw_ret_t incoming_fini_ret = rmw_serialized_message_fini(&incoming);
  const rmw_ret_t destroy_pub_ret = rmw_destroy_publisher(node, publisher);
  const rmw_ret_t destroy_sub_ret = rmw_destroy_subscription(node, subscription);
  const rmw_ret_t destroy_node_ret = rmw_destroy_node(node);
  cleanup_context(&context, &options);
  return ret == RMW_RET_OK && taken && received == payload &&
         socket_frames_sent >= 1 &&
         socket_frames_received >= 1 &&
         outgoing_fini_ret == RMW_RET_OK &&
         incoming_fini_ret == RMW_RET_OK &&
         destroy_pub_ret == RMW_RET_OK &&
         destroy_sub_ret == RMW_RET_OK &&
         destroy_node_ret == RMW_RET_OK ? 0 : 1;
}

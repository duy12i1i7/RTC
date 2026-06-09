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

extern "C" std::uint64_t rmw_fleetqox_cpp_socket_frames_received();

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

bool wait_for_received_frames(std::uint64_t baseline, std::uint64_t expected_delta)
{
  for (int attempt = 0; attempt < 200; ++attempt) {
    if (rmw_fleetqox_cpp_socket_frames_received() >= baseline + expected_delta) {
      return true;
    }
    std::this_thread::sleep_for(std::chrono::milliseconds(1));
  }
  return false;
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
  options.instance_id = 47;

  rmw_context_t context = rmw_get_zero_initialized_context();
  ret = rmw_init(&options, &context);
  if (ret != RMW_RET_OK) {
    const rmw_ret_t fini_ret = rmw_init_options_fini(&options);
    (void)fini_ret;
    std::cout << "{\"status\":\"init_failed\",\"ret\":" << ret << "}" << std::endl;
    return 1;
  }

  rmw_node_t * node = rmw_create_node(&context, "fleetqox_qos_probe", "/fleetqox");
  if (node == nullptr) {
    cleanup_context(&context, &options);
    std::cout << "{\"status\":\"create_node_failed\"}" << std::endl;
    return 1;
  }

  rosidl_message_type_support_t type_support{};
  type_support.typesupport_identifier = "rmw_fleetqox_cpp_qos_probe";
  rmw_publisher_options_t publisher_options = rmw_get_default_publisher_options();
  rmw_subscription_options_t subscription_options = rmw_get_default_subscription_options();

  rmw_qos_profile_t depth_qos = rmw_qos_profile_default;
  depth_qos.history = RMW_QOS_POLICY_HISTORY_KEEP_LAST;
  depth_qos.depth = 1;
  const char * depth_topic = "/fleetqox/qos_depth_probe";
  rmw_publisher_t * depth_publisher = rmw_create_publisher(
    node, &type_support, depth_topic, &depth_qos, &publisher_options);
  rmw_subscription_t * depth_subscription = rmw_create_subscription(
    node, &type_support, depth_topic, &depth_qos, &subscription_options);

  rmw_qos_profile_t lifespan_qos = rmw_qos_profile_default;
  lifespan_qos.history = RMW_QOS_POLICY_HISTORY_KEEP_LAST;
  lifespan_qos.depth = 10;
  lifespan_qos.lifespan.sec = 0;
  lifespan_qos.lifespan.nsec = 5000000;
  const char * lifespan_topic = "/fleetqox/qos_lifespan_probe";
  rmw_publisher_t * lifespan_publisher = rmw_create_publisher(
    node, &type_support, lifespan_topic, &lifespan_qos, &publisher_options);
  rmw_subscription_t * lifespan_subscription = rmw_create_subscription(
    node, &type_support, lifespan_topic, &lifespan_qos, &subscription_options);

  if (depth_publisher == nullptr || depth_subscription == nullptr ||
    lifespan_publisher == nullptr || lifespan_subscription == nullptr)
  {
    std::cout << "{\"status\":\"create_pubsub_failed\"}" << std::endl;
    return 1;
  }

  rmw_serialized_message_t first = rmw_get_zero_initialized_serialized_message();
  rmw_serialized_message_t second = rmw_get_zero_initialized_serialized_message();
  rmw_serialized_message_t depth_incoming = rmw_get_zero_initialized_serialized_message();
  rmw_serialized_message_t expired = rmw_get_zero_initialized_serialized_message();
  rmw_serialized_message_t lifespan_incoming = rmw_get_zero_initialized_serialized_message();
  if (!init_serialized_message(&first, "first", &allocator) ||
    !init_serialized_message(&second, "second", &allocator) ||
    rmw_serialized_message_init(&depth_incoming, 1, &allocator) != RMW_RET_OK ||
    !init_serialized_message(&expired, "expired", &allocator) ||
    rmw_serialized_message_init(&lifespan_incoming, 1, &allocator) != RMW_RET_OK)
  {
    std::cout << "{\"status\":\"serialized_message_init_failed\"}" << std::endl;
    return 1;
  }

  const std::uint64_t depth_received_before = rmw_fleetqox_cpp_socket_frames_received();
  rmw_ret_t depth_publish_first_ret =
    rmw_publish_serialized_message(depth_publisher, &first, nullptr);
  rmw_ret_t depth_publish_second_ret =
    rmw_publish_serialized_message(depth_publisher, &second, nullptr);
  const bool depth_received_ready = wait_for_received_frames(depth_received_before, 2);
  bool depth_taken = false;
  rmw_ret_t depth_take_ret =
    rmw_take_serialized_message(depth_subscription, &depth_incoming, &depth_taken, nullptr);
  bool depth_second_take = false;
  rmw_ret_t depth_second_take_ret =
    rmw_take_serialized_message(depth_subscription, &depth_incoming, &depth_second_take, nullptr);
  const std::string depth_received = serialized_message_string(depth_incoming);

  const std::uint64_t lifespan_received_before = rmw_fleetqox_cpp_socket_frames_received();
  rmw_ret_t lifespan_publish_ret =
    rmw_publish_serialized_message(lifespan_publisher, &expired, nullptr);
  const bool lifespan_received_ready = wait_for_received_frames(lifespan_received_before, 1);
  std::this_thread::sleep_for(std::chrono::milliseconds(30));
  bool lifespan_taken = false;
  rmw_ret_t lifespan_take_ret =
    rmw_take_serialized_message(lifespan_subscription, &lifespan_incoming, &lifespan_taken, nullptr);
  const std::string lifespan_received = serialized_message_string(lifespan_incoming);

  const bool depth_ok =
    depth_publish_first_ret == RMW_RET_OK &&
    depth_publish_second_ret == RMW_RET_OK &&
    depth_received_ready &&
    depth_take_ret == RMW_RET_OK &&
    depth_taken &&
    depth_received == "second" &&
    depth_second_take_ret == RMW_RET_OK &&
    !depth_second_take;
  const bool lifespan_ok =
    lifespan_publish_ret == RMW_RET_OK &&
    lifespan_received_ready &&
    lifespan_take_ret == RMW_RET_OK &&
    !lifespan_taken;

  const rmw_ret_t first_fini_ret = rmw_serialized_message_fini(&first);
  const rmw_ret_t second_fini_ret = rmw_serialized_message_fini(&second);
  const rmw_ret_t depth_incoming_fini_ret = rmw_serialized_message_fini(&depth_incoming);
  const rmw_ret_t expired_fini_ret = rmw_serialized_message_fini(&expired);
  const rmw_ret_t lifespan_incoming_fini_ret = rmw_serialized_message_fini(&lifespan_incoming);
  const rmw_ret_t destroy_depth_pub_ret = rmw_destroy_publisher(node, depth_publisher);
  const rmw_ret_t destroy_depth_sub_ret = rmw_destroy_subscription(node, depth_subscription);
  const rmw_ret_t destroy_lifespan_pub_ret = rmw_destroy_publisher(node, lifespan_publisher);
  const rmw_ret_t destroy_lifespan_sub_ret =
    rmw_destroy_subscription(node, lifespan_subscription);
  const rmw_ret_t destroy_node_ret = rmw_destroy_node(node);
  cleanup_context(&context, &options);

  const bool cleanup_ok =
    first_fini_ret == RMW_RET_OK &&
    second_fini_ret == RMW_RET_OK &&
    depth_incoming_fini_ret == RMW_RET_OK &&
    expired_fini_ret == RMW_RET_OK &&
    lifespan_incoming_fini_ret == RMW_RET_OK &&
    destroy_depth_pub_ret == RMW_RET_OK &&
    destroy_depth_sub_ret == RMW_RET_OK &&
    destroy_lifespan_pub_ret == RMW_RET_OK &&
    destroy_lifespan_sub_ret == RMW_RET_OK &&
    destroy_node_ret == RMW_RET_OK;

  std::cout << "{\"schema_version\":\"fleetrmw.rmw_qos_probe.v1\",";
  std::cout << "\"status\":\"" << (depth_ok && lifespan_ok && cleanup_ok ? "ok" : "failed") << "\",";
  std::cout << "\"depth_topic\":\"" << depth_topic << "\",";
  std::cout << "\"depth_policy\":\"KEEP_LAST\",";
  std::cout << "\"depth_limit\":1,";
  std::cout << "\"depth_received_ready\":" << (depth_received_ready ? "true" : "false") << ",";
  std::cout << "\"depth_taken\":" << (depth_taken ? "true" : "false") << ",";
  std::cout << "\"depth_second_take\":" << (depth_second_take ? "true" : "false") << ",";
  std::cout << "\"depth_received\":\"" << json_escape(depth_received) << "\",";
  std::cout << "\"lifespan_topic\":\"" << lifespan_topic << "\",";
  std::cout << "\"lifespan_ns\":5000000,";
  std::cout << "\"lifespan_received_ready\":" << (lifespan_received_ready ? "true" : "false") << ",";
  std::cout << "\"lifespan_taken\":" << (lifespan_taken ? "true" : "false") << ",";
  std::cout << "\"lifespan_received\":\"" << json_escape(lifespan_received) << "\"}" << std::endl;

  return depth_ok && lifespan_ok && cleanup_ok ? 0 : 1;
}

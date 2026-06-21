#include <chrono>
#include <cstdint>
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
#include "rosidl_runtime_c/string_functions.h"
#include "rosidl_typesupport_interface/macros.h"
#include "std_msgs/msg/detail/string__functions.h"
#include "std_msgs/msg/detail/string__rosidl_typesupport_introspection_c.h"
#include "std_msgs/msg/detail/string__struct.h"

extern "C" std::uint64_t rmw_fleetqox_cpp_socket_frames_sent();
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

bool init_context(
  rcutils_allocator_t allocator,
  rmw_init_options_t * options,
  rmw_context_t * context)
{
  *options = rmw_get_zero_initialized_init_options();
  if (rmw_init_options_init(options, allocator) != RMW_RET_OK) {
    return false;
  }
  options->instance_id = 47;
  *context = rmw_get_zero_initialized_context();
  if (rmw_init(options, context) != RMW_RET_OK) {
    const rmw_ret_t fini_ret = rmw_init_options_fini(options);
    (void)fini_ret;
    return false;
  }
  return true;
}

}  // namespace

int main()
{
  rcutils_allocator_t allocator = rcutils_get_default_allocator();
  rmw_init_options_t options{};
  rmw_context_t context{};
  if (!init_context(allocator, &options, &context)) {
    std::cout << "{\"status\":\"init_failed\"}" << std::endl;
    return 1;
  }

  rmw_node_t * node = rmw_create_node(&context, "fleetqox_std_msgs_string_probe", "/fleetqox");
  if (node == nullptr) {
    cleanup_context(&context, &options);
    std::cout << "{\"status\":\"create_node_failed\"}" << std::endl;
    return 1;
  }

  const rosidl_message_type_support_t * type_support =
    ROSIDL_TYPESUPPORT_INTERFACE__MESSAGE_SYMBOL_NAME(
    rosidl_typesupport_introspection_c, std_msgs, msg, String)();
  rmw_publisher_options_t publisher_options = rmw_get_default_publisher_options();
  rmw_subscription_options_t subscription_options = rmw_get_default_subscription_options();
  rmw_qos_profile_t qos = rmw_qos_profile_default;
  const char * topic = "/fleetqox/std_msgs_string_probe";

  rmw_publisher_t * publisher =
    rmw_create_publisher(node, type_support, topic, &qos, &publisher_options);
  rmw_subscription_t * subscription =
    rmw_create_subscription(node, type_support, topic, &qos, &subscription_options);
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

  std_msgs__msg__String outgoing;
  std_msgs__msg__String incoming;
  std_msgs__msg__String standalone_roundtrip;
  if (!std_msgs__msg__String__init(&outgoing) ||
    !std_msgs__msg__String__init(&incoming) ||
    !std_msgs__msg__String__init(&standalone_roundtrip))
  {
    std::cout << "{\"status\":\"message_init_failed\"}" << std::endl;
    return 1;
  }
  const std::string payload = "fleetqox std_msgs/String over introspection C";
  if (!rosidl_runtime_c__String__assignn(&outgoing.data, payload.data(), payload.size())) {
    std::cout << "{\"status\":\"string_assign_failed\"}" << std::endl;
    return 1;
  }

  rmw_serialized_message_t standalone = rmw_get_zero_initialized_serialized_message();
  const bool standalone_init_ok =
    rmw_serialized_message_init(&standalone, 1, &allocator) == RMW_RET_OK;
  const rmw_ret_t standalone_serialize_ret = standalone_init_ok ?
    rmw_serialize(&outgoing, type_support, &standalone) : RMW_RET_ERROR;
  const rmw_ret_t standalone_deserialize_ret = standalone_serialize_ret == RMW_RET_OK ?
    rmw_deserialize(&standalone, type_support, &standalone_roundtrip) : RMW_RET_ERROR;
  const std::string standalone_received =
    standalone_roundtrip.data.data == nullptr ? "" : standalone_roundtrip.data.data;
  const bool standalone_ok =
    standalone_deserialize_ret == RMW_RET_OK && standalone_received == payload;

  const std::uint64_t socket_sent_before = rmw_fleetqox_cpp_socket_frames_sent();
  const std::uint64_t socket_received_before = rmw_fleetqox_cpp_socket_frames_received();
  rmw_ret_t ret = rmw_publish(publisher, &outgoing, nullptr);
  bool taken = false;
  if (ret == RMW_RET_OK) {
    for (int attempt = 0; attempt < 100 && !taken; ++attempt) {
      ret = rmw_take(subscription, &incoming, &taken, nullptr);
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
  const std::string received = incoming.data.data == nullptr ? "" : incoming.data.data;
  const bool ok = ret == RMW_RET_OK &&
                  taken &&
                  received == payload &&
                  standalone_ok &&
                  socket_frames_sent >= 1 &&
                  socket_frames_received >= 1;

  std::cout << "{\"schema_version\":\"fleetrmw.rmw_std_msgs_string_probe.v1\",";
  std::cout << "\"status\":\"" << (ok ? "ok" : "failed") << "\",";
  std::cout << "\"topic\":\"" << topic << "\",";
  std::cout << "\"data_frame_wrapped\":true,";
  std::cout << "\"socket_backed\":true,";
  std::cout << "\"standalone_serialization\":" << (standalone_ok ? "true" : "false") << ",";
  std::cout << "\"standalone_serialized_size\":" << standalone.buffer_length << ",";
  std::cout << "\"socket_frames_sent\":" << socket_frames_sent << ",";
  std::cout << "\"socket_frames_received\":" << socket_frames_received << ",";
  std::cout << "\"taken\":" << (taken ? "true" : "false") << ",";
  std::cout << "\"payload\":\"" << json_escape(received) << "\"}" << std::endl;

  std_msgs__msg__String__fini(&outgoing);
  std_msgs__msg__String__fini(&incoming);
  std_msgs__msg__String__fini(&standalone_roundtrip);
  const rmw_ret_t standalone_fini_ret = standalone_init_ok ?
    rmw_serialized_message_fini(&standalone) : RMW_RET_ERROR;
  const rmw_ret_t destroy_pub_ret = rmw_destroy_publisher(node, publisher);
  const rmw_ret_t destroy_sub_ret = rmw_destroy_subscription(node, subscription);
  const rmw_ret_t destroy_node_ret = rmw_destroy_node(node);
  cleanup_context(&context, &options);
  return ok &&
         destroy_pub_ret == RMW_RET_OK &&
         destroy_sub_ret == RMW_RET_OK &&
         standalone_fini_ret == RMW_RET_OK &&
         destroy_node_ret == RMW_RET_OK ? 0 : 1;
}

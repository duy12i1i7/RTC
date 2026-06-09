#include <chrono>
#include <cstdlib>
#include <cstdint>
#include <iostream>
#include <sstream>
#include <string>
#include <thread>

#include "rcl/init.h"
#include "rcl/init_options.h"
#include "rcl/node.h"
#include "rcl/publisher.h"
#include "rcl/subscription.h"
#include "rcutils/allocator.h"
#include "rosidl_runtime_c/string_functions.h"
#include "rosidl_typesupport_interface/macros.h"
#include "std_msgs/msg/detail/string__functions.h"
#include "std_msgs/msg/detail/string__rosidl_typesupport_introspection_c.h"
#include "std_msgs/msg/detail/string__struct.h"

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

void cleanup_rcl(
  rcl_subscription_t * subscription,
  rcl_publisher_t * publisher,
  rcl_node_t * node,
  rcl_context_t * context,
  rcl_init_options_t * init_options)
{
  if (subscription != nullptr) {
    const rcl_ret_t sub_ret = rcl_subscription_fini(subscription, node);
    (void)sub_ret;
  }
  if (publisher != nullptr) {
    const rcl_ret_t pub_ret = rcl_publisher_fini(publisher, node);
    (void)pub_ret;
  }
  if (node != nullptr) {
    const rcl_ret_t node_ret = rcl_node_fini(node);
    (void)node_ret;
  }
  if (context != nullptr) {
    const rcl_ret_t shutdown_ret = rcl_shutdown(context);
    const rcl_ret_t context_ret = rcl_context_fini(context);
    (void)shutdown_ret;
    (void)context_ret;
  }
  if (init_options != nullptr) {
    const rcl_ret_t options_ret = rcl_init_options_fini(init_options);
    (void)options_ret;
  }
}

}  // namespace

int main()
{
  setenv("RMW_IMPLEMENTATION", "rmw_fleetqox_cpp", 1);

  rcl_allocator_t allocator = rcl_get_default_allocator();
  rcl_init_options_t init_options = rcl_get_zero_initialized_init_options();
  rcl_ret_t ret = rcl_init_options_init(&init_options, allocator);
  if (ret != RCL_RET_OK) {
    std::cout << "{\"status\":\"init_options_failed\",\"ret\":" << ret << "}" << std::endl;
    return 1;
  }

  rcl_context_t context = rcl_get_zero_initialized_context();
  int argc = 0;
  char ** argv = nullptr;
  ret = rcl_init(argc, argv, &init_options, &context);
  if (ret != RCL_RET_OK) {
    const rcl_ret_t options_ret = rcl_init_options_fini(&init_options);
    (void)options_ret;
    std::cout << "{\"status\":\"rcl_init_failed\",\"ret\":" << ret << "}" << std::endl;
    return 1;
  }

  rcl_node_t node = rcl_get_zero_initialized_node();
  rcl_node_options_t node_options = rcl_node_get_default_options();
  ret = rcl_node_init(&node, "fleetqox_rcl_string_probe", "/fleetqox", &context, &node_options);
  if (ret != RCL_RET_OK) {
    cleanup_rcl(nullptr, nullptr, nullptr, &context, &init_options);
    std::cout << "{\"status\":\"node_init_failed\",\"ret\":" << ret << "}" << std::endl;
    return 1;
  }

  const rosidl_message_type_support_t * type_support =
    ROSIDL_TYPESUPPORT_INTERFACE__MESSAGE_SYMBOL_NAME(
    rosidl_typesupport_introspection_c, std_msgs, msg, String)();
  const char * topic = "/fleetqox/rcl_string_probe";
  rcl_publisher_t publisher = rcl_get_zero_initialized_publisher();
  rcl_subscription_t subscription = rcl_get_zero_initialized_subscription();
  rcl_publisher_options_t publisher_options = rcl_publisher_get_default_options();
  rcl_subscription_options_t subscription_options = rcl_subscription_get_default_options();
  ret = rcl_publisher_init(&publisher, &node, type_support, topic, &publisher_options);
  if (ret == RCL_RET_OK) {
    ret = rcl_subscription_init(&subscription, &node, type_support, topic, &subscription_options);
  }
  if (ret != RCL_RET_OK) {
    cleanup_rcl(
      ret == RCL_RET_OK ? &subscription : nullptr,
      &publisher,
      &node,
      &context,
      &init_options);
    std::cout << "{\"status\":\"pubsub_init_failed\",\"ret\":" << ret << "}" << std::endl;
    return 1;
  }

  std_msgs__msg__String outgoing;
  std_msgs__msg__String incoming;
  if (!std_msgs__msg__String__init(&outgoing) || !std_msgs__msg__String__init(&incoming)) {
    cleanup_rcl(&subscription, &publisher, &node, &context, &init_options);
    std::cout << "{\"status\":\"message_init_failed\"}" << std::endl;
    return 1;
  }
  const std::string payload = "fleetqox rcl std_msgs/String";
  if (!rosidl_runtime_c__String__assignn(&outgoing.data, payload.data(), payload.size())) {
    std_msgs__msg__String__fini(&outgoing);
    std_msgs__msg__String__fini(&incoming);
    cleanup_rcl(&subscription, &publisher, &node, &context, &init_options);
    std::cout << "{\"status\":\"string_assign_failed\"}" << std::endl;
    return 1;
  }

  ret = rcl_publish(&publisher, &outgoing, nullptr);
  bool taken = false;
  if (ret == RCL_RET_OK) {
    for (int attempt = 0; attempt < 100 && !taken; ++attempt) {
      rmw_message_info_t message_info{};
      ret = rcl_take(&subscription, &incoming, &message_info, nullptr);
      if (ret == RCL_RET_OK) {
        taken = true;
        break;
      }
      if (ret != RCL_RET_SUBSCRIPTION_TAKE_FAILED) {
        break;
      }
      std::this_thread::sleep_for(std::chrono::milliseconds(1));
    }
  }
  const std::string received = incoming.data.data == nullptr ? "" : incoming.data.data;
  const bool ok = ret == RCL_RET_OK && taken && received == payload;

  std::cout << "{\"schema_version\":\"fleetrmw.rcl_string_probe.v1\",";
  std::cout << "\"status\":\"" << (ok ? "ok" : "failed") << "\",";
  std::cout << "\"topic\":\"" << topic << "\",";
  std::cout << "\"taken\":" << (taken ? "true" : "false") << ",";
  std::cout << "\"payload\":\"" << json_escape(received) << "\"}" << std::endl;

  std_msgs__msg__String__fini(&outgoing);
  std_msgs__msg__String__fini(&incoming);
  cleanup_rcl(&subscription, &publisher, &node, &context, &init_options);
  return ok ? 0 : 1;
}

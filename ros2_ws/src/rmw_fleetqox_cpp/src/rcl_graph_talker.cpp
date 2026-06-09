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

int int_arg(int argc, char ** argv, const char * name, int default_value)
{
  for (int i = 1; i + 1 < argc; ++i) {
    if (std::string(argv[i]) == name) {
      return std::stoi(argv[i + 1]);
    }
  }
  return default_value;
}

std::string string_arg(int argc, char ** argv, const char * name, const std::string & default_value)
{
  for (int i = 1; i + 1 < argc; ++i) {
    if (std::string(argv[i]) == name) {
      return argv[i + 1];
    }
  }
  return default_value;
}

void cleanup_rcl(
  rcl_publisher_t * publisher,
  rcl_node_t * node,
  rcl_context_t * context,
  rcl_init_options_t * init_options)
{
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

int main(int argc, char ** argv)
{
  setenv("RMW_IMPLEMENTATION", "rmw_fleetqox_cpp", 1);

  const std::string topic = string_arg(argc, argv, "--topic", "/fleetqox/rcl_graph_talker");
  const std::string payload = string_arg(argc, argv, "--payload", "fleetqox rcl graph talker");
  const int hold_ms = int_arg(argc, argv, "--hold-ms", 2000);
  const int period_ms = int_arg(argc, argv, "--period-ms", 100);

  rcl_allocator_t allocator = rcl_get_default_allocator();
  rcl_init_options_t init_options = rcl_get_zero_initialized_init_options();
  rcl_ret_t ret = rcl_init_options_init(&init_options, allocator);
  if (ret != RCL_RET_OK) {
    std::cout << "{\"status\":\"init_options_failed\",\"ret\":" << ret << "}" << std::endl;
    return 1;
  }

  rcl_context_t context = rcl_get_zero_initialized_context();
  int rcl_argc = 0;
  char ** rcl_argv = nullptr;
  ret = rcl_init(rcl_argc, rcl_argv, &init_options, &context);
  if (ret != RCL_RET_OK) {
    const rcl_ret_t options_ret = rcl_init_options_fini(&init_options);
    (void)options_ret;
    std::cout << "{\"status\":\"rcl_init_failed\",\"ret\":" << ret << "}" << std::endl;
    return 1;
  }

  rcl_node_t node = rcl_get_zero_initialized_node();
  rcl_node_options_t node_options = rcl_node_get_default_options();
  ret = rcl_node_init(&node, "fleetqox_rcl_graph_talker", "/fleetqox", &context, &node_options);
  if (ret != RCL_RET_OK) {
    cleanup_rcl(nullptr, nullptr, &context, &init_options);
    std::cout << "{\"status\":\"node_init_failed\",\"ret\":" << ret << "}" << std::endl;
    return 1;
  }

  const rosidl_message_type_support_t * type_support =
    ROSIDL_TYPESUPPORT_INTERFACE__MESSAGE_SYMBOL_NAME(
    rosidl_typesupport_introspection_c, std_msgs, msg, String)();
  rcl_publisher_t publisher = rcl_get_zero_initialized_publisher();
  rcl_publisher_options_t publisher_options = rcl_publisher_get_default_options();
  ret = rcl_publisher_init(&publisher, &node, type_support, topic.c_str(), &publisher_options);
  if (ret != RCL_RET_OK) {
    cleanup_rcl(nullptr, &node, &context, &init_options);
    std::cout << "{\"status\":\"publisher_init_failed\",\"ret\":" << ret << "}" << std::endl;
    return 1;
  }

  std_msgs__msg__String outgoing;
  if (!std_msgs__msg__String__init(&outgoing)) {
    cleanup_rcl(&publisher, &node, &context, &init_options);
    std::cout << "{\"status\":\"message_init_failed\"}" << std::endl;
    return 1;
  }
  if (!rosidl_runtime_c__String__assignn(&outgoing.data, payload.data(), payload.size())) {
    std_msgs__msg__String__fini(&outgoing);
    cleanup_rcl(&publisher, &node, &context, &init_options);
    std::cout << "{\"status\":\"string_assign_failed\"}" << std::endl;
    return 1;
  }

  const auto start = std::chrono::steady_clock::now();
  const auto deadline = start + std::chrono::milliseconds(hold_ms);
  int publish_count = 0;
  ret = RCL_RET_OK;
  while (std::chrono::steady_clock::now() < deadline) {
    ret = rcl_publish(&publisher, &outgoing, nullptr);
    if (ret != RCL_RET_OK) {
      break;
    }
    ++publish_count;
    std::this_thread::sleep_for(std::chrono::milliseconds(period_ms));
  }
  const bool ok = ret == RCL_RET_OK && publish_count > 0;

  std::cout << "{\"schema_version\":\"fleetrmw.rcl_graph_talker.v1\",";
  std::cout << "\"status\":\"" << (ok ? "ok" : "failed") << "\",";
  std::cout << "\"topic\":\"" << json_escape(topic) << "\",";
  std::cout << "\"type\":\"std_msgs/msg/String\",";
  std::cout << "\"payload\":\"" << json_escape(payload) << "\",";
  std::cout << "\"publish_count\":" << publish_count << "}" << std::endl;

  std_msgs__msg__String__fini(&outgoing);
  cleanup_rcl(&publisher, &node, &context, &init_options);
  return ok ? 0 : 1;
}

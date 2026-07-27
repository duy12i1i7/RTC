#include <array>
#include <chrono>
#include <cmath>
#include <cstdint>
#include <iostream>
#include <string>
#include <thread>
#include <vector>

#include "geometry_msgs/msg/detail/pose__functions.h"
#include "geometry_msgs/msg/detail/pose__struct.h"
#include "geometry_msgs/msg/detail/pose__type_support.h"
#include "geometry_msgs/msg/detail/twist__type_support.hpp"
#include "geometry_msgs/msg/twist.hpp"
#include "rcutils/allocator.h"
#include "rmw/init.h"
#include "rmw/init_options.h"
#include "rmw/publisher_options.h"
#include "rmw/qos_profiles.h"
#include "rmw/rmw.h"
#include "rmw/serialized_message.h"
#include "rmw/subscription_content_filter_options.h"
#include "rmw/subscription_options.h"
#include "rosidl_typesupport_interface/macros.h"
#include "std_msgs/msg/detail/float64_multi_array__type_support.hpp"
#include "std_msgs/msg/float64_multi_array.hpp"

extern "C" std::uint64_t rmw_fleetqox_cpp_content_filters_evaluated();
extern "C" std::uint64_t rmw_fleetqox_cpp_content_filters_matched();
extern "C" std::uint64_t rmw_fleetqox_cpp_content_filters_dropped();
extern "C" std::uint64_t rmw_fleetqox_cpp_content_filter_typed_reflections();

namespace
{

struct ScenarioCounters
{
  std::uint64_t evaluated{0};
  std::uint64_t matched{0};
  std::uint64_t dropped{0};
  std::uint64_t reflected{0};
};

bool wait_for_evaluations(std::uint64_t baseline, std::uint64_t expected)
{
  for (int attempt = 0; attempt < 150; ++attempt) {
    if (rmw_fleetqox_cpp_content_filters_evaluated() >= baseline + expected) {
      return true;
    }
    std::this_thread::sleep_for(std::chrono::milliseconds(10));
  }
  return false;
}

bool set_filter(
  rmw_subscription_t * subscription,
  rcutils_allocator_t * allocator,
  const std::string & expression,
  const std::vector<std::string> & parameters)
{
  std::vector<const char *> parameter_pointers;
  parameter_pointers.reserve(parameters.size());
  for (const std::string & parameter : parameters) {
    parameter_pointers.push_back(parameter.c_str());
  }
  rmw_subscription_content_filter_options_t options =
    rmw_get_zero_initialized_content_filter_options();
  const rmw_ret_t init_ret = rmw_subscription_content_filter_options_init(
    expression.c_str(),
    parameter_pointers.size(),
    parameter_pointers.empty() ? nullptr : parameter_pointers.data(),
    allocator,
    &options);
  const rmw_ret_t set_ret = init_ret == RMW_RET_OK ?
    rmw_subscription_set_content_filter(subscription, &options) : init_ret;
  const rmw_ret_t fini_ret = init_ret == RMW_RET_OK ?
    rmw_subscription_content_filter_options_fini(&options, allocator) : RMW_RET_ERROR;
  return init_ret == RMW_RET_OK && set_ret == RMW_RET_OK &&
         fini_ret == RMW_RET_OK && subscription->is_cft_enabled;
}

ScenarioCounters scenario_counters_since(
  std::uint64_t evaluated,
  std::uint64_t matched,
  std::uint64_t dropped,
  std::uint64_t reflected)
{
  return {
    rmw_fleetqox_cpp_content_filters_evaluated() - evaluated,
    rmw_fleetqox_cpp_content_filters_matched() - matched,
    rmw_fleetqox_cpp_content_filters_dropped() - dropped,
    rmw_fleetqox_cpp_content_filter_typed_reflections() - reflected};
}

bool run_cpp_nested_scenario(
  rmw_node_t * node,
  rcutils_allocator_t * allocator,
  const rmw_qos_profile_t & qos,
  ScenarioCounters * counters)
{
  const auto * type_support =
    ROSIDL_TYPESUPPORT_INTERFACE__MESSAGE_SYMBOL_NAME(
    rosidl_typesupport_cpp, geometry_msgs, msg, Twist)();
  const rmw_publisher_options_t publisher_options = rmw_get_default_publisher_options();
  const rmw_subscription_options_t subscription_options =
    rmw_get_default_subscription_options();
  rmw_publisher_t * publisher = rmw_create_publisher(
    node, type_support, "/fleetqox/content_filter_typed_cpp", &qos, &publisher_options);
  rmw_subscription_t * subscription = rmw_create_subscription(
    node, type_support, "/fleetqox/content_filter_typed_cpp", &qos, &subscription_options);
  if (publisher == nullptr || subscription == nullptr) {
    if (publisher != nullptr) {
      const rmw_ret_t destroy_ret = rmw_destroy_publisher(node, publisher);
      (void)destroy_ret;
    }
    if (subscription != nullptr) {
      const rmw_ret_t destroy_ret = rmw_destroy_subscription(node, subscription);
      (void)destroy_ret;
    }
    return false;
  }
  const bool filter_ok = set_filter(
    subscription,
    allocator,
    "linear.x >= %0 AND linear.x < %1 AND angular.z = %2",
    {"1.0", "2.0", "0.25"});
  const std::uint64_t evaluated_before = rmw_fleetqox_cpp_content_filters_evaluated();
  const std::uint64_t matched_before = rmw_fleetqox_cpp_content_filters_matched();
  const std::uint64_t dropped_before = rmw_fleetqox_cpp_content_filters_dropped();
  const std::uint64_t reflected_before =
    rmw_fleetqox_cpp_content_filter_typed_reflections();

  std::array<geometry_msgs::msg::Twist, 4> messages;
  messages[0].linear.x = 0.5;
  messages[0].angular.z = 0.25;
  messages[1].linear.x = 1.25;
  messages[1].angular.z = 0.25;
  messages[2].linear.x = 1.75;
  messages[2].angular.z = 0.25;
  messages[3].linear.x = 1.5;
  messages[3].angular.z = 0.5;
  bool publish_ok = filter_ok;
  for (const auto & message : messages) {
    publish_ok = publish_ok && rmw_publish(publisher, &message, nullptr) == RMW_RET_OK;
  }
  rmw_serialized_message_t malformed = rmw_get_zero_initialized_serialized_message();
  const bool malformed_initialized =
    rmw_serialized_message_init(&malformed, sizeof(std::uint64_t), allocator) == RMW_RET_OK;
  if (malformed_initialized) {
    for (size_t index = 0; index < sizeof(std::uint64_t); ++index) {
      malformed.buffer[index] =
        static_cast<std::uint8_t>((99ULL >> (8 * index)) & 0xffU);
    }
    malformed.buffer_length = sizeof(std::uint64_t);
  }
  const rmw_ret_t malformed_publish_ret = malformed_initialized ?
    rmw_publish_serialized_message(publisher, &malformed, nullptr) : RMW_RET_ERROR;
  const rmw_ret_t malformed_fini_ret = malformed_initialized ?
    rmw_serialized_message_fini(&malformed) : RMW_RET_ERROR;
  publish_ok = publish_ok && malformed_publish_ret == RMW_RET_OK &&
    malformed_fini_ret == RMW_RET_OK;
  const bool evaluated_ok =
    publish_ok && wait_for_evaluations(evaluated_before, messages.size() + 1);

  std::vector<double> received;
  geometry_msgs::msg::Twist incoming;
  bool takes_ok = true;
  for (size_t index = 0; index < 3 && takes_ok; ++index) {
    bool taken = false;
    takes_ok = rmw_take(subscription, &incoming, &taken, nullptr) == RMW_RET_OK;
    if (index < 2) {
      takes_ok = takes_ok && taken;
      if (taken) {
        received.push_back(incoming.linear.x);
      }
    } else {
      takes_ok = takes_ok && !taken;
    }
  }
  *counters = scenario_counters_since(
    evaluated_before, matched_before, dropped_before, reflected_before);
  const bool received_ok =
    received.size() == 2 &&
    std::abs(received[0] - 1.25) < 1e-12 &&
    std::abs(received[1] - 1.75) < 1e-12;
  const bool destroy_ok =
    rmw_destroy_publisher(node, publisher) == RMW_RET_OK &&
    rmw_destroy_subscription(node, subscription) == RMW_RET_OK;
  return evaluated_ok && takes_ok && received_ok &&
         counters->evaluated == 5 && counters->matched == 2 &&
         counters->dropped == 3 && counters->reflected == 4 && destroy_ok;
}

bool run_c_nested_scenario(
  rmw_node_t * node,
  rcutils_allocator_t * allocator,
  const rmw_qos_profile_t & qos,
  ScenarioCounters * counters)
{
  const auto * type_support =
    ROSIDL_TYPESUPPORT_INTERFACE__MESSAGE_SYMBOL_NAME(
    rosidl_typesupport_c, geometry_msgs, msg, Pose)();
  const rmw_publisher_options_t publisher_options = rmw_get_default_publisher_options();
  const rmw_subscription_options_t subscription_options =
    rmw_get_default_subscription_options();
  rmw_publisher_t * publisher = rmw_create_publisher(
    node, type_support, "/fleetqox/content_filter_typed_c", &qos, &publisher_options);
  rmw_subscription_t * subscription = rmw_create_subscription(
    node, type_support, "/fleetqox/content_filter_typed_c", &qos, &subscription_options);
  if (publisher == nullptr || subscription == nullptr) {
    if (publisher != nullptr) {
      const rmw_ret_t destroy_ret = rmw_destroy_publisher(node, publisher);
      (void)destroy_ret;
    }
    if (subscription != nullptr) {
      const rmw_ret_t destroy_ret = rmw_destroy_subscription(node, subscription);
      (void)destroy_ret;
    }
    return false;
  }
  const bool filter_ok = set_filter(
    subscription,
    allocator,
    "position.x BETWEEN %0 AND %1 AND orientation.w >= %2",
    {"1.0", "4.0", "0.8"});
  const std::uint64_t evaluated_before = rmw_fleetqox_cpp_content_filters_evaluated();
  const std::uint64_t matched_before = rmw_fleetqox_cpp_content_filters_matched();
  const std::uint64_t dropped_before = rmw_fleetqox_cpp_content_filters_dropped();
  const std::uint64_t reflected_before =
    rmw_fleetqox_cpp_content_filter_typed_reflections();

  std::array<geometry_msgs__msg__Pose, 4> messages{};
  bool messages_ok = true;
  for (auto & message : messages) {
    messages_ok = geometry_msgs__msg__Pose__init(&message) && messages_ok;
  }
  messages[0].position.x = -1.0;
  messages[0].orientation.w = 1.0;
  messages[1].position.x = 2.0;
  messages[1].orientation.w = 0.9;
  messages[2].position.x = 4.0;
  messages[2].orientation.w = 0.95;
  messages[3].position.x = 3.0;
  messages[3].orientation.w = 0.5;
  bool publish_ok = filter_ok && messages_ok;
  for (const auto & message : messages) {
    publish_ok = publish_ok && rmw_publish(publisher, &message, nullptr) == RMW_RET_OK;
  }
  const bool evaluated_ok = publish_ok && wait_for_evaluations(evaluated_before, messages.size());

  geometry_msgs__msg__Pose incoming{};
  const bool incoming_initialized = geometry_msgs__msg__Pose__init(&incoming);
  std::vector<double> received;
  bool takes_ok = incoming_initialized;
  for (size_t index = 0; index < 3 && takes_ok; ++index) {
    bool taken = false;
    takes_ok = rmw_take(subscription, &incoming, &taken, nullptr) == RMW_RET_OK;
    if (index < 2) {
      takes_ok = takes_ok && taken;
      if (taken) {
        received.push_back(incoming.position.x);
      }
    } else {
      takes_ok = takes_ok && !taken;
    }
  }
  if (incoming_initialized) {
    geometry_msgs__msg__Pose__fini(&incoming);
  }
  for (auto & message : messages) {
    geometry_msgs__msg__Pose__fini(&message);
  }
  *counters = scenario_counters_since(
    evaluated_before, matched_before, dropped_before, reflected_before);
  const bool received_ok =
    received.size() == 2 &&
    std::abs(received[0] - 2.0) < 1e-12 &&
    std::abs(received[1] - 4.0) < 1e-12;
  const bool destroy_ok =
    rmw_destroy_publisher(node, publisher) == RMW_RET_OK &&
    rmw_destroy_subscription(node, subscription) == RMW_RET_OK;
  return evaluated_ok && takes_ok && received_ok &&
         counters->evaluated == 4 && counters->matched == 2 &&
         counters->dropped == 2 && counters->reflected == 4 && destroy_ok;
}

bool run_cpp_array_scenario(
  rmw_node_t * node,
  rcutils_allocator_t * allocator,
  const rmw_qos_profile_t & qos,
  ScenarioCounters * counters)
{
  const auto * type_support =
    ROSIDL_TYPESUPPORT_INTERFACE__MESSAGE_SYMBOL_NAME(
    rosidl_typesupport_cpp, std_msgs, msg, Float64MultiArray)();
  const rmw_publisher_options_t publisher_options = rmw_get_default_publisher_options();
  const rmw_subscription_options_t subscription_options =
    rmw_get_default_subscription_options();
  rmw_publisher_t * publisher = rmw_create_publisher(
    node, type_support, "/fleetqox/content_filter_typed_array", &qos, &publisher_options);
  rmw_subscription_t * subscription = rmw_create_subscription(
    node, type_support, "/fleetqox/content_filter_typed_array", &qos, &subscription_options);
  if (publisher == nullptr || subscription == nullptr) {
    if (publisher != nullptr) {
      const rmw_ret_t destroy_ret = rmw_destroy_publisher(node, publisher);
      (void)destroy_ret;
    }
    if (subscription != nullptr) {
      const rmw_ret_t destroy_ret = rmw_destroy_subscription(node, subscription);
      (void)destroy_ret;
    }
    return false;
  }
  const bool filter_ok = set_filter(
    subscription,
    allocator,
    "data._length = %0 AND data[1] >= %1 AND "
    "layout.dim._length = %2 AND layout.dim[0].label = %3",
    {"3", "2.5", "1", "fleet"});
  const std::uint64_t evaluated_before = rmw_fleetqox_cpp_content_filters_evaluated();
  const std::uint64_t matched_before = rmw_fleetqox_cpp_content_filters_matched();
  const std::uint64_t dropped_before = rmw_fleetqox_cpp_content_filters_dropped();
  const std::uint64_t reflected_before =
    rmw_fleetqox_cpp_content_filter_typed_reflections();

  std::array<std_msgs::msg::Float64MultiArray, 4> messages;
  for (auto & message : messages) {
    message.layout.dim.resize(1);
    message.layout.dim[0].label = "fleet";
    message.layout.dim[0].size = 3;
    message.layout.dim[0].stride = 3;
    message.data = {1.0, 3.0, 5.0};
  }
  messages[0].data = {1.0, 2.0, 5.0};
  messages[2].layout.dim[0].label = "other";
  messages[3].data = {1.0, 4.0};
  bool publish_ok = filter_ok;
  for (const auto & message : messages) {
    publish_ok = publish_ok && rmw_publish(publisher, &message, nullptr) == RMW_RET_OK;
  }
  const bool evaluated_ok = publish_ok && wait_for_evaluations(evaluated_before, messages.size());

  std::vector<double> received;
  std_msgs::msg::Float64MultiArray incoming;
  bool takes_ok = true;
  for (size_t index = 0; index < 2 && takes_ok; ++index) {
    bool taken = false;
    takes_ok = rmw_take(subscription, &incoming, &taken, nullptr) == RMW_RET_OK;
    if (index == 0) {
      takes_ok = takes_ok && taken && incoming.data.size() == 3;
      if (taken && incoming.data.size() == 3) {
        received.push_back(incoming.data[1]);
      }
    } else {
      takes_ok = takes_ok && !taken;
    }
  }
  *counters = scenario_counters_since(
    evaluated_before, matched_before, dropped_before, reflected_before);
  const bool received_ok =
    received.size() == 1 && std::abs(received[0] - 3.0) < 1e-12;
  const bool destroy_ok =
    rmw_destroy_publisher(node, publisher) == RMW_RET_OK &&
    rmw_destroy_subscription(node, subscription) == RMW_RET_OK;
  return evaluated_ok && takes_ok && received_ok &&
         counters->evaluated == 4 && counters->matched == 1 &&
         counters->dropped == 3 && counters->reflected == 4 && destroy_ok;
}

bool cleanup_context(rmw_context_t * context, rmw_init_options_t * options)
{
  return rmw_shutdown(context) == RMW_RET_OK &&
         rmw_context_fini(context) == RMW_RET_OK &&
         rmw_init_options_fini(options) == RMW_RET_OK;
}

}  // namespace

int main()
{
  rcutils_allocator_t allocator = rcutils_get_default_allocator();
  rmw_init_options_t options = rmw_get_zero_initialized_init_options();
  if (rmw_init_options_init(&options, allocator) != RMW_RET_OK) {
    return 1;
  }
  options.instance_id = 2057;
  rmw_context_t context = rmw_get_zero_initialized_context();
  if (rmw_init(&options, &context) != RMW_RET_OK) {
    const rmw_ret_t options_ret = rmw_init_options_fini(&options);
    (void)options_ret;
    return 1;
  }
  rmw_node_t * node =
    rmw_create_node(&context, "fleetqox_content_filter_typed_probe", "/fleetqox");
  if (node == nullptr) {
    (void)cleanup_context(&context, &options);
    return 1;
  }
  rmw_qos_profile_t qos = rmw_qos_profile_default;
  qos.history = RMW_QOS_POLICY_HISTORY_KEEP_LAST;
  qos.depth = 16;

  ScenarioCounters cpp_nested;
  ScenarioCounters c_nested;
  ScenarioCounters cpp_array;
  const bool cpp_nested_ok =
    run_cpp_nested_scenario(node, &allocator, qos, &cpp_nested);
  const bool c_nested_ok =
    run_c_nested_scenario(node, &allocator, qos, &c_nested);
  const bool cpp_array_ok =
    run_cpp_array_scenario(node, &allocator, qos, &cpp_array);
  const rmw_ret_t node_ret = rmw_destroy_node(node);
  const bool context_ok = cleanup_context(&context, &options);
  const bool cleanup_ok = node_ret == RMW_RET_OK && context_ok;
  const std::uint64_t total_reflected =
    cpp_nested.reflected + c_nested.reflected + cpp_array.reflected;
  const bool ok = cpp_nested_ok && c_nested_ok && cpp_array_ok &&
    total_reflected == 12 && cleanup_ok;

  std::cout << "{\"schema_version\":\"fleetrmw.content_filter_typed_probe.v1\","
            << "\"status\":\"" << (ok ? "ok" : "failed") << "\","
            << "\"cpp_nested_scalar_reflection\":"
            << (cpp_nested_ok ? "true" : "false") << ","
            << "\"c_nested_scalar_reflection\":"
            << (c_nested_ok ? "true" : "false") << ","
            << "\"cpp_array_index_and_length_reflection\":"
            << (cpp_array_ok ? "true" : "false") << ","
            << "\"malformed_typed_payload_fail_closed\":"
            << (cpp_nested_ok ? "true" : "false") << ","
            << "\"cpp_evaluated\":" << cpp_nested.evaluated << ","
            << "\"cpp_matched\":" << cpp_nested.matched << ","
            << "\"cpp_dropped\":" << cpp_nested.dropped << ","
            << "\"c_evaluated\":" << c_nested.evaluated << ","
            << "\"c_matched\":" << c_nested.matched << ","
            << "\"c_dropped\":" << c_nested.dropped << ","
            << "\"array_evaluated\":" << cpp_array.evaluated << ","
            << "\"array_matched\":" << cpp_array.matched << ","
            << "\"array_dropped\":" << cpp_array.dropped << ","
            << "\"typed_reflections\":" << total_reflected << ","
            << "\"content_filter_introspection_cpp_nested_fields_claim\":"
            << (cpp_nested_ok ? "true" : "false") << ","
            << "\"content_filter_introspection_c_nested_fields_claim\":"
            << (c_nested_ok ? "true" : "false") << ","
            << "\"content_filter_introspection_cpp_array_fields_claim\":"
            << (cpp_array_ok ? "true" : "false") << ","
            << "\"content_filter_malformed_typed_payload_fail_closed_claim\":"
            << (cpp_nested_ok ? "true" : "false") << ","
            << "\"clean_teardown\":" << (cleanup_ok ? "true" : "false") << "}"
            << std::endl;
  return ok ? 0 : 1;
}

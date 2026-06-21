#include <chrono>
#include <iostream>
#include <string>
#include <thread>

#include "rcutils/allocator.h"
#include "rmw/init.h"
#include "rmw/init_options.h"
#include "rmw/publisher_options.h"
#include "rmw/qos_profiles.h"
#include "rmw/rmw.h"
#include "rmw/subscription_options.h"
#include "rosidl_runtime_c/string_functions.h"
#include "rosidl_typesupport_interface/macros.h"
#include "std_msgs/msg/detail/string__functions.h"
#include "std_msgs/msg/detail/string__struct.h"
#include "std_msgs/msg/detail/string__type_support.h"
#include "std_msgs/msg/detail/string__type_support.hpp"
#include "std_msgs/msg/string.hpp"

int main()
{
  rcutils_allocator_t allocator = rcutils_get_default_allocator();
  rmw_init_options_t options = rmw_get_zero_initialized_init_options();
  rmw_context_t context = rmw_get_zero_initialized_context();
  bool initialized = rmw_init_options_init(&options, allocator) == RMW_RET_OK;
  if (initialized) {
    options.instance_id = 91;
    initialized = rmw_init(&options, &context) == RMW_RET_OK;
  }
  rmw_node_t * node = initialized ?
    rmw_create_node(&context, "fleetrmw_loaned_message_probe", "/fleetqox") : nullptr;
  const auto * type_support =
    ROSIDL_TYPESUPPORT_INTERFACE__MESSAGE_SYMBOL_NAME(
    rosidl_typesupport_cpp, std_msgs, msg, String)();
  rmw_qos_profile_t qos = rmw_qos_profile_default;
  rmw_publisher_options_t publisher_options = rmw_get_default_publisher_options();
  rmw_subscription_options_t subscription_options = rmw_get_default_subscription_options();
  rmw_publisher_t * publisher = node == nullptr ? nullptr : rmw_create_publisher(
    node, type_support, "/fleetqox/loaned", &qos, &publisher_options);
  rmw_subscription_t * subscription = node == nullptr ? nullptr : rmw_create_subscription(
    node, type_support, "/fleetqox/loaned", &qos, &subscription_options);
  const bool capabilities_ok = publisher != nullptr && subscription != nullptr &&
    publisher->can_loan_messages && subscription->can_loan_messages;

  void * publisher_loan = nullptr;
  const rmw_ret_t borrow_publisher_ret = publisher == nullptr ? RMW_RET_ERROR :
    rmw_borrow_loaned_message(publisher, type_support, &publisher_loan);
  if (borrow_publisher_ret == RMW_RET_OK && publisher_loan != nullptr) {
    static_cast<std_msgs::msg::String *>(publisher_loan)->data = "fleetrmw-loaned-message";
  }
  const rmw_ret_t publish_ret = publisher_loan == nullptr ? RMW_RET_ERROR :
    rmw_publish_loaned_message(publisher, publisher_loan, nullptr);

  void * subscription_loan = nullptr;
  bool taken = false;
  rmw_ret_t take_ret = RMW_RET_OK;
  for (int attempt = 0; attempt < 500 && !taken; ++attempt) {
    take_ret = rmw_take_loaned_message(subscription, &subscription_loan, &taken, nullptr);
    if (take_ret != RMW_RET_OK || taken) {
      break;
    }
    std::this_thread::sleep_for(std::chrono::milliseconds(1));
  }
  const bool payload_ok = taken && subscription_loan != nullptr &&
    static_cast<std_msgs::msg::String *>(subscription_loan)->data == "fleetrmw-loaned-message";
  const rmw_ret_t return_subscription_ret = subscription_loan == nullptr ? RMW_RET_ERROR :
    rmw_return_loaned_message_from_subscription(subscription, subscription_loan);

  void * returned_publisher_loan = nullptr;
  const rmw_ret_t second_borrow_ret = rmw_borrow_loaned_message(
    publisher, type_support, &returned_publisher_loan);
  const rmw_ret_t return_publisher_ret = returned_publisher_loan == nullptr ? RMW_RET_ERROR :
    rmw_return_loaned_message_from_publisher(publisher, returned_publisher_loan);

  const auto * c_type_support =
    ROSIDL_TYPESUPPORT_INTERFACE__MESSAGE_SYMBOL_NAME(
    rosidl_typesupport_c, std_msgs, msg, String)();
  rmw_publisher_t * c_publisher = node == nullptr ? nullptr : rmw_create_publisher(
    node, c_type_support, "/fleetqox/loaned_c", &qos, &publisher_options);
  rmw_subscription_t * c_subscription = node == nullptr ? nullptr : rmw_create_subscription(
    node, c_type_support, "/fleetqox/loaned_c", &qos, &subscription_options);
  void * c_publisher_loan = nullptr;
  const rmw_ret_t c_borrow_ret = c_publisher == nullptr ? RMW_RET_ERROR :
    rmw_borrow_loaned_message(c_publisher, c_type_support, &c_publisher_loan);
  const bool c_assign_ok = c_publisher_loan != nullptr && rosidl_runtime_c__String__assign(
    &static_cast<std_msgs__msg__String *>(c_publisher_loan)->data,
    "fleetrmw-c-loaned-message");
  const rmw_ret_t c_publish_ret = !c_assign_ok ? RMW_RET_ERROR :
    rmw_publish_loaned_message(c_publisher, c_publisher_loan, nullptr);
  void * c_subscription_loan = nullptr;
  bool c_taken = false;
  rmw_ret_t c_take_ret = RMW_RET_OK;
  for (int attempt = 0; attempt < 500 && !c_taken; ++attempt) {
    c_take_ret = rmw_take_loaned_message(
      c_subscription, &c_subscription_loan, &c_taken, nullptr);
    if (c_take_ret != RMW_RET_OK || c_taken) {
      break;
    }
    std::this_thread::sleep_for(std::chrono::milliseconds(1));
  }
  const bool c_payload_ok = c_taken && c_subscription_loan != nullptr &&
    static_cast<std_msgs__msg__String *>(c_subscription_loan)->data.data != nullptr &&
    std::string(static_cast<std_msgs__msg__String *>(c_subscription_loan)->data.data) ==
    "fleetrmw-c-loaned-message";
  const rmw_ret_t c_return_ret = c_subscription_loan == nullptr ? RMW_RET_ERROR :
    rmw_return_loaned_message_from_subscription(c_subscription, c_subscription_loan);

  const bool ok = initialized && capabilities_ok &&
    borrow_publisher_ret == RMW_RET_OK && publish_ret == RMW_RET_OK &&
    take_ret == RMW_RET_OK && payload_ok && return_subscription_ret == RMW_RET_OK &&
    second_borrow_ret == RMW_RET_OK && return_publisher_ret == RMW_RET_OK &&
    c_publisher != nullptr && c_subscription != nullptr &&
    c_publisher->can_loan_messages && c_subscription->can_loan_messages &&
    c_borrow_ret == RMW_RET_OK && c_publish_ret == RMW_RET_OK &&
    c_take_ret == RMW_RET_OK && c_payload_ok && c_return_ret == RMW_RET_OK;

  std::cout << "{\"schema_version\":\"fleetrmw.loaned_message_probe.v1\","
            << "\"status\":\"" << (ok ? "ok" : "failed") << "\","
            << "\"publisher_can_loan\":" << (publisher != nullptr && publisher->can_loan_messages ? "true" : "false") << ","
            << "\"subscription_can_loan\":" << (subscription != nullptr && subscription->can_loan_messages ? "true" : "false") << ","
            << "\"publisher_borrow_ok\":" << (borrow_publisher_ret == RMW_RET_OK ? "true" : "false") << ","
            << "\"publish_loan_ok\":" << (publish_ret == RMW_RET_OK ? "true" : "false") << ","
            << "\"subscription_take_loan_ok\":" << (payload_ok ? "true" : "false") << ","
            << "\"subscription_return_ok\":" << (return_subscription_ret == RMW_RET_OK ? "true" : "false") << ","
            << "\"publisher_return_without_publish_ok\":" << (return_publisher_ret == RMW_RET_OK ? "true" : "false") << ","
            << "\"introspection_c_loan_lifecycle_ok\":"
            << (c_payload_ok && c_return_ret == RMW_RET_OK ? "true" : "false") << "}\n";

  if (c_subscription != nullptr) {
    const rmw_ret_t destroy_c_subscription_ret = rmw_destroy_subscription(node, c_subscription);
    (void)destroy_c_subscription_ret;
  }
  if (c_publisher != nullptr) {
    const rmw_ret_t destroy_c_publisher_ret = rmw_destroy_publisher(node, c_publisher);
    (void)destroy_c_publisher_ret;
  }
  if (subscription != nullptr) {
    const rmw_ret_t destroy_subscription_ret = rmw_destroy_subscription(node, subscription);
    (void)destroy_subscription_ret;
  }
  if (publisher != nullptr) {
    const rmw_ret_t destroy_publisher_ret = rmw_destroy_publisher(node, publisher);
    (void)destroy_publisher_ret;
  }
  if (node != nullptr) {
    const rmw_ret_t destroy_node_ret = rmw_destroy_node(node);
    (void)destroy_node_ret;
  }
  if (initialized) {
    const rmw_ret_t shutdown_ret = rmw_shutdown(&context);
    const rmw_ret_t context_fini_ret = rmw_context_fini(&context);
    (void)shutdown_ret;
    (void)context_fini_ret;
  }
  const rmw_ret_t options_fini_ret = rmw_init_options_fini(&options);
  (void)options_fini_ret;
  return ok ? 0 : 1;
}

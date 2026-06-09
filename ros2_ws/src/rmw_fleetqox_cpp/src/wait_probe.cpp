#include <chrono>
#include <cstring>
#include <iostream>
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

int main()
{
  rcutils_allocator_t allocator = rcutils_get_default_allocator();
  rmw_init_options_t options = rmw_get_zero_initialized_init_options();
  if (rmw_init_options_init(&options, allocator) != RMW_RET_OK) {
    std::cout << "{\"status\":\"init_options_failed\"}" << std::endl;
    return 1;
  }
  options.instance_id = 44;
  rmw_context_t context = rmw_get_zero_initialized_context();
  if (rmw_init(&options, &context) != RMW_RET_OK) {
    const rmw_ret_t fini_ret = rmw_init_options_fini(&options);
    (void)fini_ret;
    std::cout << "{\"status\":\"init_failed\"}" << std::endl;
    return 1;
  }
  rmw_node_t * node = rmw_create_node(&context, "fleetqox_wait_probe", "/fleetqox");
  rmw_wait_set_t * wait_set = rmw_create_wait_set(&context, 2);
  if (node == nullptr || wait_set == nullptr) {
    if (wait_set != nullptr) {
      const rmw_ret_t destroy_wait_ret = rmw_destroy_wait_set(wait_set);
      (void)destroy_wait_ret;
    }
    if (node != nullptr) {
      const rmw_ret_t destroy_node_ret = rmw_destroy_node(node);
      (void)destroy_node_ret;
    }
    cleanup_context(&context, &options);
    std::cout << "{\"status\":\"create_wait_failed\"}" << std::endl;
    return 1;
  }

  const rmw_guard_condition_t * graph_guard = rmw_node_get_graph_guard_condition(node);
  const rmw_ret_t trigger_ret = rmw_trigger_guard_condition(graph_guard);
  void * guard_items[1] = {const_cast<rmw_guard_condition_t *>(graph_guard)};
  rmw_guard_conditions_t guard_conditions{1, guard_items};
  rmw_time_t zero_timeout{0, 0};
  const rmw_ret_t guard_wait_ret =
    rmw_wait(nullptr, &guard_conditions, nullptr, nullptr, nullptr, wait_set, &zero_timeout);
  const bool guard_ready = guard_wait_ret == RMW_RET_OK && guard_conditions.guard_conditions[0] != nullptr;

  rosidl_message_type_support_t type_support{};
  type_support.typesupport_identifier = "rmw_fleetqox_cpp_wait_probe";
  rmw_publisher_options_t publisher_options = rmw_get_default_publisher_options();
  rmw_subscription_options_t subscription_options = rmw_get_default_subscription_options();
  rmw_qos_profile_t qos = rmw_qos_profile_default;
  rmw_publisher_t * publisher = rmw_create_publisher(
    node, &type_support, "/fleetqox/wait_probe", &qos, &publisher_options);
  rmw_subscription_t * subscription = rmw_create_subscription(
    node, &type_support, "/fleetqox/wait_probe", &qos, &subscription_options);

  rmw_serialized_message_t outgoing = rmw_get_zero_initialized_serialized_message();
  const char payload[] = "wait-ready";
  const bool message_init_ok =
    rmw_serialized_message_init(&outgoing, sizeof(payload) - 1, &allocator) == RMW_RET_OK;
  if (message_init_ok) {
    std::memcpy(outgoing.buffer, payload, sizeof(payload) - 1);
    outgoing.buffer_length = sizeof(payload) - 1;
  }
  const rmw_ret_t publish_ret = publisher != nullptr && message_init_ok ?
    rmw_publish_serialized_message(publisher, &outgoing, nullptr) : RMW_RET_ERROR;
  void * subscription_items[1] = {subscription};
  rmw_subscriptions_t subscriptions{1, subscription_items};
  rmw_ret_t subscription_wait_ret = RMW_RET_TIMEOUT;
  bool subscription_ready = false;
  for (int attempt = 0; attempt < 100 && !subscription_ready; ++attempt) {
    subscription_items[0] = subscription;
    subscription_wait_ret =
      rmw_wait(&subscriptions, nullptr, nullptr, nullptr, nullptr, wait_set, &zero_timeout);
    subscription_ready =
      subscription_wait_ret == RMW_RET_OK && subscriptions.subscribers[0] != nullptr;
    if (!subscription_ready) {
      std::this_thread::sleep_for(std::chrono::milliseconds(1));
    }
  }

  std::cout << "{\"schema_version\":\"fleetrmw.rmw_wait_probe.v1\",";
  std::cout << "\"status\":\"" << (trigger_ret == RMW_RET_OK && guard_ready && subscription_ready ? "ok" : "failed") << "\",";
  std::cout << "\"graph_guard_ready\":" << (guard_ready ? "true" : "false") << ",";
  std::cout << "\"subscription_ready\":" << (subscription_ready ? "true" : "false") << ",";
  std::cout << "\"publish_ret\":" << publish_ret << "}" << std::endl;

  if (message_init_ok) {
    const rmw_ret_t message_fini_ret = rmw_serialized_message_fini(&outgoing);
    (void)message_fini_ret;
  }
  if (publisher != nullptr) {
    const rmw_ret_t destroy_pub_ret = rmw_destroy_publisher(node, publisher);
    (void)destroy_pub_ret;
  }
  if (subscription != nullptr) {
    const rmw_ret_t destroy_sub_ret = rmw_destroy_subscription(node, subscription);
    (void)destroy_sub_ret;
  }
  const rmw_ret_t destroy_wait_ret = rmw_destroy_wait_set(wait_set);
  const rmw_ret_t destroy_node_ret = rmw_destroy_node(node);
  (void)destroy_wait_ret;
  (void)destroy_node_ret;
  cleanup_context(&context, &options);
  return trigger_ret == RMW_RET_OK && guard_ready && subscription_ready && publish_ret == RMW_RET_OK ? 0 : 1;
}

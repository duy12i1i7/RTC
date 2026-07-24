#include <chrono>
#include <cstring>
#include <iostream>
#include <thread>

#include "rcutils/allocator.h"
#include "rmw/error_handling.h"
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
  rmw_node_t * other_node = rmw_create_node(
    &context, "fleetqox_wait_probe_other", "/fleetqox");
  rmw_wait_set_t * wait_set = rmw_create_wait_set(&context, 2);
  rmw_wait_set_t * bounded_wait_set = rmw_create_wait_set(&context, 1);
  rmw_wait_set_t * unbounded_wait_set = rmw_create_wait_set(&context, 0);
  if (node == nullptr || other_node == nullptr || wait_set == nullptr || bounded_wait_set == nullptr ||
    unbounded_wait_set == nullptr)
  {
    if (unbounded_wait_set != nullptr) {
      const rmw_ret_t destroy_unbounded_ret = rmw_destroy_wait_set(unbounded_wait_set);
      (void)destroy_unbounded_ret;
    }
    if (bounded_wait_set != nullptr) {
      const rmw_ret_t destroy_bounded_ret = rmw_destroy_wait_set(bounded_wait_set);
      (void)destroy_bounded_ret;
    }
    if (wait_set != nullptr) {
      const rmw_ret_t destroy_wait_ret = rmw_destroy_wait_set(wait_set);
      (void)destroy_wait_ret;
    }
    if (node != nullptr) {
      const rmw_ret_t destroy_node_ret = rmw_destroy_node(node);
      (void)destroy_node_ret;
    }
    if (other_node != nullptr) {
      const rmw_ret_t destroy_other_node_ret = rmw_destroy_node(other_node);
      (void)destroy_other_node_ret;
    }
    cleanup_context(&context, &options);
    std::cout << "{\"status\":\"create_wait_failed\"}" << std::endl;
    return 1;
  }

  const rmw_guard_condition_t * graph_guard = rmw_node_get_graph_guard_condition(node);
  void * guard_items[1] = {const_cast<rmw_guard_condition_t *>(graph_guard)};
  rmw_guard_conditions_t guard_conditions{1, guard_items};
  rmw_time_t zero_timeout{0, 0};
  const rmw_ret_t initial_guard_drain_ret =
    rmw_wait(nullptr, &guard_conditions, nullptr, nullptr, nullptr, wait_set, &zero_timeout);
  (void)initial_guard_drain_ret;

  rosidl_message_type_support_t type_support{};
  type_support.typesupport_identifier = "rmw_fleetqox_cpp_wait_probe";
  rmw_publisher_options_t publisher_options = rmw_get_default_publisher_options();
  rmw_subscription_options_t subscription_options = rmw_get_default_subscription_options();
  rmw_qos_profile_t qos = rmw_qos_profile_default;
  rmw_publisher_t * publisher = rmw_create_publisher(
    node, &type_support, "/fleetqox/wait_probe", &qos, &publisher_options);
  rmw_subscription_t * subscription = rmw_create_subscription(
    node, &type_support, "/fleetqox/wait_probe", &qos, &subscription_options);
  const rmw_ret_t wrong_publisher_owner_ret = publisher == nullptr ? RMW_RET_ERROR :
    rmw_destroy_publisher(other_node, publisher);
  const bool publisher_owner_node_enforced =
    wrong_publisher_owner_ret == RMW_RET_INVALID_ARGUMENT;
  rmw_reset_error();
  const rmw_ret_t wrong_subscription_owner_ret = subscription == nullptr ? RMW_RET_ERROR :
    rmw_destroy_subscription(other_node, subscription);
  const bool subscription_owner_node_enforced =
    wrong_subscription_owner_ret == RMW_RET_INVALID_ARGUMENT;
  rmw_reset_error();
  guard_items[0] = const_cast<rmw_guard_condition_t *>(graph_guard);
  const rmw_ret_t guard_wait_ret =
    rmw_wait(nullptr, &guard_conditions, nullptr, nullptr, nullptr, wait_set, &zero_timeout);
  const bool guard_ready =
    graph_guard != nullptr && guard_wait_ret == RMW_RET_OK &&
    guard_conditions.guard_conditions[0] != nullptr;

  void * bounded_subscription_items[2] = {subscription, subscription};
  rmw_subscriptions_t bounded_subscriptions{2, bounded_subscription_items};
  const rmw_ret_t max_conditions_ret = rmw_wait(
    &bounded_subscriptions,
    nullptr,
    nullptr,
    nullptr,
    nullptr,
    bounded_wait_set,
    &zero_timeout);
  const bool max_conditions_enforced = max_conditions_ret == RMW_RET_INVALID_ARGUMENT;
  rmw_reset_error();

  void * external_guard_items[2] = {
    const_cast<rmw_guard_condition_t *>(graph_guard),
    const_cast<rmw_guard_condition_t *>(graph_guard)};
  rmw_guard_conditions_t external_guards{2, external_guard_items};
  const rmw_ret_t external_guards_ret = rmw_wait(
    nullptr,
    &external_guards,
    nullptr,
    nullptr,
    nullptr,
    bounded_wait_set,
    &zero_timeout);
  const bool guard_conditions_external_to_capacity =
    external_guards_ret == RMW_RET_OK || external_guards_ret == RMW_RET_TIMEOUT;
  rmw_reset_error();

  void * null_subscription_items[1] = {nullptr};
  rmw_subscriptions_t null_subscriptions{1, null_subscription_items};
  const rmw_ret_t null_entry_ret = rmw_wait(
    &null_subscriptions, nullptr, nullptr, nullptr, nullptr, wait_set, &zero_timeout);
  const bool null_entry_rejected = null_entry_ret == RMW_RET_INVALID_ARGUMENT;
  rmw_reset_error();

  rmw_init_options_t foreign_options = rmw_get_zero_initialized_init_options();
  rmw_context_t foreign_context = rmw_get_zero_initialized_context();
  rmw_guard_condition_t * foreign_guard = nullptr;
  bool foreign_context_ready = false;
  if (rmw_init_options_init(&foreign_options, allocator) == RMW_RET_OK) {
    foreign_options.instance_id = 45;
    if (rmw_init(&foreign_options, &foreign_context) == RMW_RET_OK) {
      foreign_context_ready = true;
      foreign_guard = rmw_create_guard_condition(&foreign_context);
    }
  }
  void * foreign_guard_items[1] = {foreign_guard};
  rmw_guard_conditions_t foreign_guards{1, foreign_guard_items};
  const bool cross_context_same_domain = foreign_context_ready &&
    foreign_context.actual_domain_id == context.actual_domain_id;
  const rmw_ret_t cross_context_ret = foreign_guard == nullptr ? RMW_RET_ERROR : rmw_wait(
    nullptr, &foreign_guards, nullptr, nullptr, nullptr, wait_set, &zero_timeout);
  const bool cross_context_rejected = cross_context_same_domain &&
    cross_context_ret == RMW_RET_INVALID_ARGUMENT;
  rmw_reset_error();
  if (foreign_guard != nullptr) {
    const rmw_ret_t destroy_foreign_guard_ret = rmw_destroy_guard_condition(foreign_guard);
    (void)destroy_foreign_guard_ret;
  }
  if (foreign_context_ready) {
    cleanup_context(&foreign_context, &foreign_options);
  } else if (foreign_options.implementation_identifier != nullptr) {
    const rmw_ret_t foreign_options_fini_ret = rmw_init_options_fini(&foreign_options);
    (void)foreign_options_fini_ret;
  }

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
  const rmw_ret_t unbounded_trigger_ret = graph_guard == nullptr ? RMW_RET_ERROR :
    rmw_trigger_guard_condition(graph_guard);
  void * unbounded_subscription_items[1] = {subscription};
  void * unbounded_guard_items[1] = {const_cast<rmw_guard_condition_t *>(graph_guard)};
  rmw_subscriptions_t unbounded_subscriptions{1, unbounded_subscription_items};
  rmw_guard_conditions_t unbounded_guards{1, unbounded_guard_items};
  const rmw_ret_t unbounded_wait_ret = rmw_wait(
    &unbounded_subscriptions,
    &unbounded_guards,
    nullptr,
    nullptr,
    nullptr,
    unbounded_wait_set,
    &zero_timeout);
  const bool zero_max_conditions_unbounded =
    unbounded_trigger_ret == RMW_RET_OK && unbounded_wait_ret == RMW_RET_OK;
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

  rmw_init_options_t shutdown_options = rmw_get_zero_initialized_init_options();
  rmw_context_t shutdown_context = rmw_get_zero_initialized_context();
  rmw_wait_set_t * shutdown_wait_set = nullptr;
  bool shutdown_context_ready = false;
  rmw_ret_t shutdown_context_wait_ret = RMW_RET_ERROR;
  if (rmw_init_options_init(&shutdown_options, allocator) == RMW_RET_OK) {
    shutdown_options.instance_id = 46;
    if (rmw_init(&shutdown_options, &shutdown_context) == RMW_RET_OK) {
      shutdown_context_ready = true;
      shutdown_wait_set = rmw_create_wait_set(&shutdown_context, 0);
      if (shutdown_wait_set != nullptr && rmw_shutdown(&shutdown_context) == RMW_RET_OK) {
        shutdown_context_wait_ret = rmw_wait(
          nullptr, nullptr, nullptr, nullptr, nullptr, shutdown_wait_set, &zero_timeout);
      }
    }
  }
  const bool shutdown_context_rejected =
    shutdown_context_wait_ret == RMW_RET_INVALID_ARGUMENT;
  rmw_reset_error();
  if (shutdown_wait_set != nullptr) {
    const rmw_ret_t destroy_shutdown_wait_ret = rmw_destroy_wait_set(shutdown_wait_set);
    (void)destroy_shutdown_wait_ret;
  }
  if (shutdown_context_ready) {
    cleanup_context(&shutdown_context, &shutdown_options);
  } else if (shutdown_options.implementation_identifier != nullptr) {
    const rmw_ret_t shutdown_options_fini_ret = rmw_init_options_fini(&shutdown_options);
    (void)shutdown_options_fini_ret;
  }

  const bool wait_contract_ok = max_conditions_enforced &&
    guard_conditions_external_to_capacity &&
    zero_max_conditions_unbounded && null_entry_rejected &&
    cross_context_rejected && shutdown_context_rejected &&
    publisher_owner_node_enforced && subscription_owner_node_enforced;

  std::cout << "{\"schema_version\":\"fleetrmw.rmw_wait_probe.v1\",";
  std::cout << "\"status\":\"" <<
    (guard_ready && subscription_ready && wait_contract_ok ? "ok" : "failed") << "\",";
  std::cout << "\"graph_guard_automatic\":true,";
  std::cout << "\"graph_guard_ready\":" << (guard_ready ? "true" : "false") << ",";
  std::cout << "\"subscription_ready\":" << (subscription_ready ? "true" : "false") << ",";
  std::cout << "\"max_conditions_enforced\":" <<
    (max_conditions_enforced ? "true" : "false") << ",";
  std::cout << "\"guard_conditions_external_to_capacity\":" <<
    (guard_conditions_external_to_capacity ? "true" : "false") << ",";
  std::cout << "\"zero_max_conditions_unbounded\":" <<
    (zero_max_conditions_unbounded ? "true" : "false") << ",";
  std::cout << "\"null_entry_rejected\":" <<
    (null_entry_rejected ? "true" : "false") << ",";
  std::cout << "\"cross_context_same_domain\":" <<
    (cross_context_same_domain ? "true" : "false") << ",";
  std::cout << "\"cross_context_rejected\":" <<
    (cross_context_rejected ? "true" : "false") << ",";
  std::cout << "\"shutdown_context_rejected\":" <<
    (shutdown_context_rejected ? "true" : "false") << ",";
  std::cout << "\"publisher_owner_node_enforced\":" <<
    (publisher_owner_node_enforced ? "true" : "false") << ",";
  std::cout << "\"subscription_owner_node_enforced\":" <<
    (subscription_owner_node_enforced ? "true" : "false") << ",";
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
  const rmw_ret_t destroy_unbounded_ret = rmw_destroy_wait_set(unbounded_wait_set);
  const rmw_ret_t destroy_bounded_ret = rmw_destroy_wait_set(bounded_wait_set);
  const rmw_ret_t destroy_wait_ret = rmw_destroy_wait_set(wait_set);
  const rmw_ret_t destroy_node_ret = rmw_destroy_node(node);
  const rmw_ret_t destroy_other_node_ret = rmw_destroy_node(other_node);
  (void)destroy_wait_ret;
  (void)destroy_bounded_ret;
  (void)destroy_unbounded_ret;
  (void)destroy_node_ret;
  (void)destroy_other_node_ret;
  cleanup_context(&context, &options);
  return guard_ready && subscription_ready && wait_contract_ok && publish_ret == RMW_RET_OK ? 0 : 1;
}

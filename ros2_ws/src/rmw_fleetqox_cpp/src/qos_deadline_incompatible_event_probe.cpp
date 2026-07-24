#include <cstdint>
#include <iostream>

#include "rcutils/allocator.h"
#include "rmw/event.h"
#include "rmw/events_statuses/events_statuses.h"
#include "rmw/init.h"
#include "rmw/init_options.h"
#include "rmw/publisher_options.h"
#include "rmw/qos_profiles.h"
#include "rmw/rmw.h"
#include "rmw/subscription_options.h"
#include "rosidl_runtime_c/message_type_support_struct.h"

namespace
{

struct CallbackState
{
  std::uint64_t calls = 0;
  std::uint64_t events = 0;
};

struct DeadlineScenario
{
  bool ok = false;
  bool taken = false;
  bool wait_ready = false;
  std::int32_t total_count = 0;
  std::int32_t total_count_change = 0;
  rmw_qos_policy_kind_t last_policy_kind = RMW_QOS_POLICY_INVALID;
  std::uint64_t callback_events = 0;
  bool matched_taken = true;
  bool matched_wait_ready = true;
};

void event_callback(const void * user_data, size_t number_of_events)
{
  auto * state = const_cast<CallbackState *>(static_cast<const CallbackState *>(user_data));
  if (state != nullptr) {
    ++state->calls;
    state->events += number_of_events;
  }
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

rmw_ret_t wait_event_once(rmw_context_t * context, rmw_event_t * event, bool * ready)
{
  if (context == nullptr || event == nullptr || ready == nullptr) {
    return RMW_RET_INVALID_ARGUMENT;
  }
  rmw_wait_set_t * wait_set = rmw_create_wait_set(context, 1);
  if (wait_set == nullptr) {
    return RMW_RET_ERROR;
  }
  rmw_time_t zero_timeout{};
  void * event_handles[1] = {event};
  rmw_events_t events{1, event_handles};
  const rmw_ret_t wait_ret =
    rmw_wait(nullptr, nullptr, nullptr, nullptr, &events, wait_set, &zero_timeout);
  *ready = event_handles[0] != nullptr;
  const rmw_ret_t destroy_ret = rmw_destroy_wait_set(wait_set);
  if (wait_ret != RMW_RET_OK && wait_ret != RMW_RET_TIMEOUT) {
    return wait_ret;
  }
  return destroy_ret == RMW_RET_OK ? wait_ret : destroy_ret;
}

rmw_qos_profile_t offered_deadline_qos()
{
  rmw_qos_profile_t qos = rmw_qos_profile_default;
  qos.history = RMW_QOS_POLICY_HISTORY_KEEP_LAST;
  qos.depth = 8;
  qos.deadline.sec = 0;
  qos.deadline.nsec = 100000000;
  return qos;
}

rmw_qos_profile_t requested_deadline_qos()
{
  rmw_qos_profile_t qos = rmw_qos_profile_default;
  qos.history = RMW_QOS_POLICY_HISTORY_KEEP_LAST;
  qos.depth = 8;
  qos.deadline.sec = 0;
  qos.deadline.nsec = 10000000;
  return qos;
}

rmw_qos_profile_t missing_offered_deadline_qos()
{
  rmw_qos_profile_t qos = rmw_qos_profile_default;
  qos.history = RMW_QOS_POLICY_HISTORY_KEEP_LAST;
  qos.depth = 8;
  qos.deadline.sec = 0;
  qos.deadline.nsec = 0;
  return qos;
}

bool incompatible_status_ok(
  const rmw_qos_incompatible_event_status_t & status,
  rmw_qos_policy_kind_t policy_kind)
{
  return status.total_count == 1 &&
         status.total_count_change == 1 &&
         status.last_policy_kind == policy_kind;
}

DeadlineScenario run_offered_deadline_scenario(
  rmw_context_t * context,
  rmw_node_t * node,
  const rosidl_message_type_support_t * type_support,
  const rmw_publisher_options_t * publisher_options,
  const rmw_subscription_options_t * subscription_options,
  bool missing_offered)
{
  DeadlineScenario result;
  const rmw_qos_profile_t offered_qos = missing_offered ?
    missing_offered_deadline_qos() : offered_deadline_qos();
  const rmw_qos_profile_t requested_qos = requested_deadline_qos();
  const char * topic = missing_offered ?
    "/fleetqox/qos_deadline_missing_offered_probe" :
    "/fleetqox/qos_deadline_incompatible_offered_probe";
  rmw_publisher_t * publisher =
    rmw_create_publisher(node, type_support, topic, &offered_qos, publisher_options);
  rmw_event_t event = rmw_get_zero_initialized_event();
  rmw_event_t matched_event = rmw_get_zero_initialized_event();
  const rmw_ret_t event_init_ret = publisher == nullptr ?
    RMW_RET_ERROR :
    rmw_publisher_event_init(&event, publisher, RMW_EVENT_OFFERED_QOS_INCOMPATIBLE);
  const rmw_ret_t matched_event_init_ret = publisher == nullptr ?
    RMW_RET_ERROR :
    rmw_publisher_event_init(&matched_event, publisher, RMW_EVENT_PUBLICATION_MATCHED);
  CallbackState callback_state;
  const rmw_ret_t callback_ret = rmw_event_set_callback(&event, event_callback, &callback_state);
  rmw_subscription_t * subscription =
    rmw_create_subscription(node, type_support, topic, &requested_qos, subscription_options);
  const rmw_ret_t matched_wait_ret =
    wait_event_once(context, &matched_event, &result.matched_wait_ready);
  rmw_matched_status_t matched_status{};
  result.matched_taken = true;
  const rmw_ret_t matched_take_ret =
    rmw_take_event(&matched_event, &matched_status, &result.matched_taken);
  const rmw_ret_t wait_ret = wait_event_once(context, &event, &result.wait_ready);
  rmw_offered_qos_incompatible_event_status_t status{};
  result.taken = false;
  const rmw_ret_t take_ret = rmw_take_event(&event, &status, &result.taken);
  result.total_count = status.total_count;
  result.total_count_change = status.total_count_change;
  result.last_policy_kind = status.last_policy_kind;
  result.callback_events = callback_state.events;
  const rmw_ret_t destroy_subscription_ret = subscription == nullptr ?
    RMW_RET_ERROR : rmw_destroy_subscription(node, subscription);
  const rmw_ret_t matched_fini_ret = rmw_event_fini(&matched_event);
  const rmw_ret_t event_fini_ret = rmw_event_fini(&event);
  const rmw_ret_t destroy_publisher_ret = publisher == nullptr ?
    RMW_RET_ERROR : rmw_destroy_publisher(node, publisher);
  result.ok =
    event_init_ret == RMW_RET_OK &&
    matched_event_init_ret == RMW_RET_OK &&
    callback_ret == RMW_RET_OK &&
    matched_wait_ret == RMW_RET_TIMEOUT &&
    !result.matched_wait_ready &&
    matched_take_ret == RMW_RET_OK &&
    !result.matched_taken &&
    matched_status.current_count == 0 &&
    matched_status.current_count_change == 0 &&
    wait_ret == RMW_RET_OK &&
    result.wait_ready &&
    take_ret == RMW_RET_OK &&
    result.taken &&
    incompatible_status_ok(status, RMW_QOS_POLICY_DEADLINE) &&
    callback_state.calls >= 1 &&
    callback_state.events >= 1 &&
    destroy_subscription_ret == RMW_RET_OK &&
    matched_fini_ret == RMW_RET_OK &&
    event_fini_ret == RMW_RET_OK &&
    destroy_publisher_ret == RMW_RET_OK;
  return result;
}

DeadlineScenario run_requested_deadline_scenario(
  rmw_context_t * context,
  rmw_node_t * node,
  const rosidl_message_type_support_t * type_support,
  const rmw_publisher_options_t * publisher_options,
  const rmw_subscription_options_t * subscription_options,
  bool missing_offered)
{
  DeadlineScenario result;
  const rmw_qos_profile_t offered_qos = missing_offered ?
    missing_offered_deadline_qos() : offered_deadline_qos();
  const rmw_qos_profile_t requested_qos = requested_deadline_qos();
  const char * topic = missing_offered ?
    "/fleetqox/qos_deadline_missing_requested_probe" :
    "/fleetqox/qos_deadline_incompatible_requested_probe";
  rmw_subscription_t * subscription =
    rmw_create_subscription(node, type_support, topic, &requested_qos, subscription_options);
  rmw_event_t event = rmw_get_zero_initialized_event();
  rmw_event_t matched_event = rmw_get_zero_initialized_event();
  const rmw_ret_t event_init_ret = subscription == nullptr ?
    RMW_RET_ERROR :
    rmw_subscription_event_init(&event, subscription, RMW_EVENT_REQUESTED_QOS_INCOMPATIBLE);
  const rmw_ret_t matched_event_init_ret = subscription == nullptr ?
    RMW_RET_ERROR :
    rmw_subscription_event_init(&matched_event, subscription, RMW_EVENT_SUBSCRIPTION_MATCHED);
  CallbackState callback_state;
  const rmw_ret_t callback_ret = rmw_event_set_callback(&event, event_callback, &callback_state);
  rmw_publisher_t * publisher =
    rmw_create_publisher(node, type_support, topic, &offered_qos, publisher_options);
  const rmw_ret_t matched_wait_ret =
    wait_event_once(context, &matched_event, &result.matched_wait_ready);
  rmw_matched_status_t matched_status{};
  result.matched_taken = true;
  const rmw_ret_t matched_take_ret =
    rmw_take_event(&matched_event, &matched_status, &result.matched_taken);
  const rmw_ret_t wait_ret = wait_event_once(context, &event, &result.wait_ready);
  rmw_requested_qos_incompatible_event_status_t status{};
  result.taken = false;
  const rmw_ret_t take_ret = rmw_take_event(&event, &status, &result.taken);
  result.total_count = status.total_count;
  result.total_count_change = status.total_count_change;
  result.last_policy_kind = status.last_policy_kind;
  result.callback_events = callback_state.events;
  const rmw_ret_t destroy_publisher_ret = publisher == nullptr ?
    RMW_RET_ERROR : rmw_destroy_publisher(node, publisher);
  const rmw_ret_t matched_fini_ret = rmw_event_fini(&matched_event);
  const rmw_ret_t event_fini_ret = rmw_event_fini(&event);
  const rmw_ret_t destroy_subscription_ret = subscription == nullptr ?
    RMW_RET_ERROR : rmw_destroy_subscription(node, subscription);
  result.ok =
    event_init_ret == RMW_RET_OK &&
    matched_event_init_ret == RMW_RET_OK &&
    callback_ret == RMW_RET_OK &&
    matched_wait_ret == RMW_RET_TIMEOUT &&
    !result.matched_wait_ready &&
    matched_take_ret == RMW_RET_OK &&
    !result.matched_taken &&
    matched_status.current_count == 0 &&
    matched_status.current_count_change == 0 &&
    wait_ret == RMW_RET_OK &&
    result.wait_ready &&
    take_ret == RMW_RET_OK &&
    result.taken &&
    incompatible_status_ok(status, RMW_QOS_POLICY_DEADLINE) &&
    callback_state.calls >= 1 &&
    callback_state.events >= 1 &&
    destroy_publisher_ret == RMW_RET_OK &&
    matched_fini_ret == RMW_RET_OK &&
    event_fini_ret == RMW_RET_OK &&
    destroy_subscription_ret == RMW_RET_OK;
  return result;
}

}  // namespace

int main()
{
  rcutils_allocator_t allocator = rcutils_get_default_allocator();
  rmw_init_options_t options = rmw_get_zero_initialized_init_options();
  rmw_ret_t ret = rmw_init_options_init(&options, allocator);
  if (ret != RMW_RET_OK) {
    std::cout << "{\"status\":\"init_options_failed\",\"ret\":" << ret << "}\n";
    return 1;
  }
  options.instance_id = 64;

  rmw_context_t context = rmw_get_zero_initialized_context();
  ret = rmw_init(&options, &context);
  if (ret != RMW_RET_OK) {
    const rmw_ret_t fini_ret = rmw_init_options_fini(&options);
    (void)fini_ret;
    std::cout << "{\"status\":\"init_failed\",\"ret\":" << ret << "}\n";
    return 1;
  }

  rmw_node_t * node =
    rmw_create_node(&context, "fleetqox_qos_deadline_incompatible_event_probe", "/fleetqox");
  if (node == nullptr) {
    cleanup_context(&context, &options);
    std::cout << "{\"status\":\"create_node_failed\"}\n";
    return 1;
  }

  rosidl_message_type_support_t type_support{};
  type_support.typesupport_identifier =
    "rmw_fleetqox_cpp_qos_deadline_incompatible_event_probe";
  rmw_publisher_options_t publisher_options = rmw_get_default_publisher_options();
  rmw_subscription_options_t subscription_options = rmw_get_default_subscription_options();
  const bool offered_supported =
    rmw_event_type_is_supported(RMW_EVENT_OFFERED_QOS_INCOMPATIBLE);
  const bool requested_supported =
    rmw_event_type_is_supported(RMW_EVENT_REQUESTED_QOS_INCOMPATIBLE);
  const DeadlineScenario offered = run_offered_deadline_scenario(
    &context, node, &type_support, &publisher_options, &subscription_options, false);
  const DeadlineScenario requested = run_requested_deadline_scenario(
    &context, node, &type_support, &publisher_options, &subscription_options, false);
  const DeadlineScenario missing_offered = run_offered_deadline_scenario(
    &context, node, &type_support, &publisher_options, &subscription_options, true);
  const DeadlineScenario missing_requested = run_requested_deadline_scenario(
    &context, node, &type_support, &publisher_options, &subscription_options, true);
  const rmw_ret_t destroy_node_ret = rmw_destroy_node(node);
  cleanup_context(&context, &options);
  const bool ok =
    offered_supported &&
    requested_supported &&
    offered.ok &&
    requested.ok &&
    missing_offered.ok &&
    missing_requested.ok &&
    destroy_node_ret == RMW_RET_OK;

  std::cout << "{\"schema_version\":\"fleetrmw.qos_deadline_incompatible_event_probe.v1\",";
  std::cout << "\"status\":\"" << (ok ? "ok" : "failed") << "\",";
  std::cout << "\"qos_deadline_incompatible_event_production\":true,";
  std::cout << "\"qos_deadline_incompatible_event_scope\":\"local_same_process_deadline_mismatch\",";
  std::cout << "\"offered_taken\":" << (offered.taken ? "true" : "false") << ",";
  std::cout << "\"offered_wait_ready\":" << (offered.wait_ready ? "true" : "false") << ",";
  std::cout << "\"offered_total_count\":" << offered.total_count << ",";
  std::cout << "\"offered_total_count_change\":" << offered.total_count_change << ",";
  std::cout << "\"offered_last_policy_kind\":" <<
    static_cast<int>(offered.last_policy_kind) << ",";
  std::cout << "\"offered_callback_events\":" << offered.callback_events << ",";
  std::cout << "\"offered_incompatible_endpoint_matched_taken\":" <<
    (offered.matched_taken ? "true" : "false") << ",";
  std::cout << "\"offered_incompatible_endpoint_matched_wait_ready\":" <<
    (offered.matched_wait_ready ? "true" : "false") << ",";
  std::cout << "\"requested_taken\":" << (requested.taken ? "true" : "false") << ",";
  std::cout << "\"requested_wait_ready\":" << (requested.wait_ready ? "true" : "false") << ",";
  std::cout << "\"requested_total_count\":" << requested.total_count << ",";
  std::cout << "\"requested_total_count_change\":" << requested.total_count_change << ",";
  std::cout << "\"requested_last_policy_kind\":" <<
    static_cast<int>(requested.last_policy_kind) << ",";
  std::cout << "\"requested_callback_events\":" << requested.callback_events << ",";
  std::cout << "\"requested_incompatible_endpoint_matched_taken\":" <<
    (requested.matched_taken ? "true" : "false") << ",";
  std::cout << "\"requested_incompatible_endpoint_matched_wait_ready\":" <<
    (requested.matched_wait_ready ? "true" : "false") << ",";
  std::cout << "\"missing_offered_deadline_offered_event_claim\":" <<
    (missing_offered.ok ? "true" : "false") << ",";
  std::cout << "\"missing_offered_deadline_requested_event_claim\":" <<
    (missing_requested.ok ? "true" : "false") << ",";
  std::cout << "\"missing_offered_total_count\":" <<
    missing_offered.total_count << ",";
  std::cout << "\"missing_requested_total_count\":" <<
    missing_requested.total_count << ",";
  std::cout << "\"missing_offered_last_policy_kind\":" <<
    static_cast<int>(missing_offered.last_policy_kind) << ",";
  std::cout << "\"missing_requested_last_policy_kind\":" <<
    static_cast<int>(missing_requested.last_policy_kind) << ",";
  std::cout << "\"missing_offered_matched_taken\":" <<
    (missing_offered.matched_taken ? "true" : "false") << ",";
  std::cout << "\"missing_requested_matched_taken\":" <<
    (missing_requested.matched_taken ? "true" : "false") << ",";
  std::cout << "\"scenario_count\":4}\n";
  return ok ? 0 : 1;
}

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

extern "C" std::uint64_t rmw_fleetqox_cpp_qos_events_initialized();
extern "C" std::uint64_t rmw_fleetqox_cpp_qos_events_finalized();
extern "C" std::uint64_t rmw_fleetqox_cpp_qos_event_callbacks_set();

namespace
{

struct CallbackState
{
  std::uint64_t calls;
  std::uint64_t events;
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

rmw_ret_t wait_event_once(
  rmw_context_t * context,
  rmw_event_t * event,
  bool * ready)
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

bool incompatible_type_status_ok(const rmw_incompatible_type_status_t & status)
{
  return status.total_count == 1 && status.total_count_change == 1;
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
  options.instance_id = 59;

  rmw_context_t context = rmw_get_zero_initialized_context();
  ret = rmw_init(&options, &context);
  if (ret != RMW_RET_OK) {
    const rmw_ret_t fini_ret = rmw_init_options_fini(&options);
    (void)fini_ret;
    std::cout << "{\"status\":\"init_failed\",\"ret\":" << ret << "}\n";
    return 1;
  }

  rmw_node_t * node =
    rmw_create_node(&context, "fleetqox_type_incompatible_event_probe", "/fleetqox");
  if (node == nullptr) {
    cleanup_context(&context, &options);
    std::cout << "{\"status\":\"create_node_failed\"}\n";
    return 1;
  }

  rosidl_message_type_support_t type_a{};
  type_a.typesupport_identifier = "rmw_fleetqox_cpp_type_a";
  rosidl_message_type_support_t type_b{};
  type_b.typesupport_identifier = "rmw_fleetqox_cpp_type_b";
  rmw_qos_profile_t qos = rmw_qos_profile_default;
  qos.history = RMW_QOS_POLICY_HISTORY_KEEP_LAST;
  qos.depth = 8;
  rmw_publisher_options_t publisher_options = rmw_get_default_publisher_options();
  rmw_subscription_options_t subscription_options = rmw_get_default_subscription_options();

  const bool publisher_supported =
    rmw_event_type_is_supported(RMW_EVENT_PUBLISHER_INCOMPATIBLE_TYPE);
  const bool subscription_supported =
    rmw_event_type_is_supported(RMW_EVENT_SUBSCRIPTION_INCOMPATIBLE_TYPE);
  const std::uint64_t events_init_before = rmw_fleetqox_cpp_qos_events_initialized();
  const std::uint64_t events_fini_before = rmw_fleetqox_cpp_qos_events_finalized();
  const std::uint64_t callbacks_before = rmw_fleetqox_cpp_qos_event_callbacks_set();

  const char * publisher_topic = "/fleetqox/type_incompatible_publisher_probe";
  rmw_publisher_t * publisher =
    rmw_create_publisher(node, &type_a, publisher_topic, &qos, &publisher_options);
  rmw_event_t publisher_event = rmw_get_zero_initialized_event();
  const rmw_ret_t publisher_event_init_ret = publisher == nullptr ?
    RMW_RET_ERROR :
    rmw_publisher_event_init(
      &publisher_event, publisher, RMW_EVENT_PUBLISHER_INCOMPATIBLE_TYPE);
  rmw_event_t publisher_matched_event = rmw_get_zero_initialized_event();
  const rmw_ret_t publisher_matched_event_init_ret = publisher == nullptr ?
    RMW_RET_ERROR :
    rmw_publisher_event_init(
      &publisher_matched_event, publisher, RMW_EVENT_PUBLICATION_MATCHED);
  CallbackState publisher_callback_state{0, 0};
  const rmw_ret_t publisher_callback_ret =
    rmw_event_set_callback(&publisher_event, event_callback, &publisher_callback_state);
  bool publisher_initial_ready = true;
  const rmw_ret_t publisher_initial_wait_ret =
    wait_event_once(&context, &publisher_event, &publisher_initial_ready);
  rmw_incompatible_type_status_t publisher_initial_status{};
  bool publisher_initial_taken = true;
  const rmw_ret_t publisher_initial_take_ret =
    rmw_take_event(&publisher_event, &publisher_initial_status, &publisher_initial_taken);
  rmw_subscription_t * publisher_mismatched_subscription =
    rmw_create_subscription(node, &type_b, publisher_topic, &qos, &subscription_options);
  bool publisher_matched_ready = true;
  const rmw_ret_t publisher_matched_wait_ret =
    wait_event_once(&context, &publisher_matched_event, &publisher_matched_ready);
  rmw_matched_status_t publisher_matched_status{};
  bool publisher_matched_taken = true;
  const rmw_ret_t publisher_matched_take_ret =
    rmw_take_event(&publisher_matched_event, &publisher_matched_status, &publisher_matched_taken);
  bool publisher_ready = false;
  const rmw_ret_t publisher_wait_ret =
    wait_event_once(&context, &publisher_event, &publisher_ready);
  rmw_incompatible_type_status_t publisher_status{};
  bool publisher_taken = false;
  const rmw_ret_t publisher_take_ret =
    rmw_take_event(&publisher_event, &publisher_status, &publisher_taken);
  rmw_incompatible_type_status_t publisher_after_clear_status{};
  bool publisher_after_clear_taken = true;
  const rmw_ret_t publisher_after_clear_take_ret =
    rmw_take_event(
      &publisher_event, &publisher_after_clear_status, &publisher_after_clear_taken);
  const rmw_ret_t destroy_publisher_mismatched_subscription_ret =
    publisher_mismatched_subscription == nullptr ?
    RMW_RET_ERROR : rmw_destroy_subscription(node, publisher_mismatched_subscription);
  const rmw_ret_t publisher_matched_event_fini_ret = rmw_event_fini(&publisher_matched_event);
  const rmw_ret_t publisher_event_fini_ret = rmw_event_fini(&publisher_event);
  const rmw_ret_t destroy_publisher_ret = publisher == nullptr ?
    RMW_RET_ERROR : rmw_destroy_publisher(node, publisher);

  const char * subscription_topic = "/fleetqox/type_incompatible_subscription_probe";
  rmw_subscription_t * subscription =
    rmw_create_subscription(node, &type_a, subscription_topic, &qos, &subscription_options);
  rmw_event_t subscription_event = rmw_get_zero_initialized_event();
  const rmw_ret_t subscription_event_init_ret = subscription == nullptr ?
    RMW_RET_ERROR :
    rmw_subscription_event_init(
      &subscription_event, subscription, RMW_EVENT_SUBSCRIPTION_INCOMPATIBLE_TYPE);
  rmw_event_t subscription_matched_event = rmw_get_zero_initialized_event();
  const rmw_ret_t subscription_matched_event_init_ret = subscription == nullptr ?
    RMW_RET_ERROR :
    rmw_subscription_event_init(
      &subscription_matched_event, subscription, RMW_EVENT_SUBSCRIPTION_MATCHED);
  CallbackState subscription_callback_state{0, 0};
  const rmw_ret_t subscription_callback_ret =
    rmw_event_set_callback(&subscription_event, event_callback, &subscription_callback_state);
  bool subscription_initial_ready = true;
  const rmw_ret_t subscription_initial_wait_ret =
    wait_event_once(&context, &subscription_event, &subscription_initial_ready);
  rmw_incompatible_type_status_t subscription_initial_status{};
  bool subscription_initial_taken = true;
  const rmw_ret_t subscription_initial_take_ret =
    rmw_take_event(&subscription_event, &subscription_initial_status, &subscription_initial_taken);
  rmw_publisher_t * subscription_mismatched_publisher =
    rmw_create_publisher(node, &type_b, subscription_topic, &qos, &publisher_options);
  bool subscription_matched_ready = true;
  const rmw_ret_t subscription_matched_wait_ret =
    wait_event_once(&context, &subscription_matched_event, &subscription_matched_ready);
  rmw_matched_status_t subscription_matched_status{};
  bool subscription_matched_taken = true;
  const rmw_ret_t subscription_matched_take_ret =
    rmw_take_event(
      &subscription_matched_event, &subscription_matched_status, &subscription_matched_taken);
  bool subscription_ready = false;
  const rmw_ret_t subscription_wait_ret =
    wait_event_once(&context, &subscription_event, &subscription_ready);
  rmw_incompatible_type_status_t subscription_status{};
  bool subscription_taken = false;
  const rmw_ret_t subscription_take_ret =
    rmw_take_event(&subscription_event, &subscription_status, &subscription_taken);
  rmw_incompatible_type_status_t subscription_after_clear_status{};
  bool subscription_after_clear_taken = true;
  const rmw_ret_t subscription_after_clear_take_ret =
    rmw_take_event(
      &subscription_event, &subscription_after_clear_status, &subscription_after_clear_taken);
  const rmw_ret_t destroy_subscription_mismatched_publisher_ret =
    subscription_mismatched_publisher == nullptr ?
    RMW_RET_ERROR : rmw_destroy_publisher(node, subscription_mismatched_publisher);
  const rmw_ret_t subscription_matched_event_fini_ret =
    rmw_event_fini(&subscription_matched_event);
  const rmw_ret_t subscription_event_fini_ret = rmw_event_fini(&subscription_event);
  const rmw_ret_t destroy_subscription_ret = subscription == nullptr ?
    RMW_RET_ERROR : rmw_destroy_subscription(node, subscription);

  const rmw_ret_t destroy_node_ret = rmw_destroy_node(node);
  cleanup_context(&context, &options);

  const std::uint64_t events_init_delta =
    rmw_fleetqox_cpp_qos_events_initialized() - events_init_before;
  const std::uint64_t events_fini_delta =
    rmw_fleetqox_cpp_qos_events_finalized() - events_fini_before;
  const std::uint64_t callbacks_delta =
    rmw_fleetqox_cpp_qos_event_callbacks_set() - callbacks_before;
  const bool publisher_ok =
    publisher_supported &&
    publisher_event_init_ret == RMW_RET_OK &&
    publisher_matched_event_init_ret == RMW_RET_OK &&
    publisher_callback_ret == RMW_RET_OK &&
    publisher_initial_wait_ret == RMW_RET_TIMEOUT &&
    !publisher_initial_ready &&
    publisher_initial_take_ret == RMW_RET_OK &&
    !publisher_initial_taken &&
    publisher_matched_wait_ret == RMW_RET_TIMEOUT &&
    !publisher_matched_ready &&
    publisher_matched_take_ret == RMW_RET_OK &&
    !publisher_matched_taken &&
    publisher_matched_status.current_count == 0 &&
    publisher_matched_status.current_count_change == 0 &&
    publisher_wait_ret == RMW_RET_OK &&
    publisher_ready &&
    publisher_take_ret == RMW_RET_OK &&
    publisher_taken &&
    incompatible_type_status_ok(publisher_status) &&
    publisher_callback_state.calls >= 1 &&
    publisher_callback_state.events >= 1 &&
    publisher_after_clear_take_ret == RMW_RET_OK &&
    !publisher_after_clear_taken &&
    publisher_after_clear_status.total_count == publisher_status.total_count &&
    publisher_after_clear_status.total_count_change == 0 &&
    destroy_publisher_mismatched_subscription_ret == RMW_RET_OK &&
    publisher_matched_event_fini_ret == RMW_RET_OK &&
    publisher_event_fini_ret == RMW_RET_OK &&
    destroy_publisher_ret == RMW_RET_OK;
  const bool subscription_ok =
    subscription_supported &&
    subscription_event_init_ret == RMW_RET_OK &&
    subscription_matched_event_init_ret == RMW_RET_OK &&
    subscription_callback_ret == RMW_RET_OK &&
    subscription_initial_wait_ret == RMW_RET_TIMEOUT &&
    !subscription_initial_ready &&
    subscription_initial_take_ret == RMW_RET_OK &&
    !subscription_initial_taken &&
    subscription_matched_wait_ret == RMW_RET_TIMEOUT &&
    !subscription_matched_ready &&
    subscription_matched_take_ret == RMW_RET_OK &&
    !subscription_matched_taken &&
    subscription_matched_status.current_count == 0 &&
    subscription_matched_status.current_count_change == 0 &&
    subscription_wait_ret == RMW_RET_OK &&
    subscription_ready &&
    subscription_take_ret == RMW_RET_OK &&
    subscription_taken &&
    incompatible_type_status_ok(subscription_status) &&
    subscription_callback_state.calls >= 1 &&
    subscription_callback_state.events >= 1 &&
    subscription_after_clear_take_ret == RMW_RET_OK &&
    !subscription_after_clear_taken &&
    subscription_after_clear_status.total_count == subscription_status.total_count &&
    subscription_after_clear_status.total_count_change == 0 &&
    destroy_subscription_mismatched_publisher_ret == RMW_RET_OK &&
    subscription_matched_event_fini_ret == RMW_RET_OK &&
    subscription_event_fini_ret == RMW_RET_OK &&
    destroy_subscription_ret == RMW_RET_OK;
  const bool lifecycle_ok =
    events_init_delta == 4 &&
    events_fini_delta == 4 &&
    callbacks_delta == 2 &&
    destroy_node_ret == RMW_RET_OK;
  const bool ok = publisher_ok && subscription_ok && lifecycle_ok;

  std::cout << "{\"schema_version\":\"fleetrmw.type_incompatible_event_probe.v1\",";
  std::cout << "\"status\":\"" << (ok ? "ok" : "failed") << "\",";
  std::cout << "\"publisher_incompatible_type_supported\":" <<
    (publisher_supported ? "true" : "false") << ",";
  std::cout << "\"subscription_incompatible_type_supported\":" <<
    (subscription_supported ? "true" : "false") << ",";
  std::cout << "\"publisher_taken\":" << (publisher_taken ? "true" : "false") << ",";
  std::cout << "\"publisher_wait_ready\":" << (publisher_ready ? "true" : "false") << ",";
  std::cout << "\"publisher_total_count\":" << publisher_status.total_count << ",";
  std::cout << "\"publisher_total_count_change\":" <<
    publisher_status.total_count_change << ",";
  std::cout << "\"publisher_callback_calls\":" << publisher_callback_state.calls << ",";
  std::cout << "\"publisher_callback_events\":" << publisher_callback_state.events << ",";
  std::cout << "\"publisher_mismatched_endpoint_matched_taken\":" <<
    (publisher_matched_taken ? "true" : "false") << ",";
  std::cout << "\"publisher_mismatched_endpoint_matched_wait_ready\":" <<
    (publisher_matched_ready ? "true" : "false") << ",";
  std::cout << "\"subscription_taken\":" << (subscription_taken ? "true" : "false") << ",";
  std::cout << "\"subscription_wait_ready\":" <<
    (subscription_ready ? "true" : "false") << ",";
  std::cout << "\"subscription_total_count\":" << subscription_status.total_count << ",";
  std::cout << "\"subscription_total_count_change\":" <<
    subscription_status.total_count_change << ",";
  std::cout << "\"subscription_callback_calls\":" << subscription_callback_state.calls << ",";
  std::cout << "\"subscription_callback_events\":" << subscription_callback_state.events << ",";
  std::cout << "\"subscription_mismatched_endpoint_matched_taken\":" <<
    (subscription_matched_taken ? "true" : "false") << ",";
  std::cout << "\"subscription_mismatched_endpoint_matched_wait_ready\":" <<
    (subscription_matched_ready ? "true" : "false") << ",";
  std::cout << "\"events_initialized_delta\":" << events_init_delta << ",";
  std::cout << "\"events_finalized_delta\":" << events_fini_delta << ",";
  std::cout << "\"event_callbacks_set_delta\":" << callbacks_delta << ",";
  std::cout << "\"type_incompatible_event_production\":true,";
  std::cout << "\"type_incompatible_event_scope\":\"local_same_process_same_topic_type_mismatch\"";
  std::cout << "}\n";
  return ok ? 0 : 1;
}

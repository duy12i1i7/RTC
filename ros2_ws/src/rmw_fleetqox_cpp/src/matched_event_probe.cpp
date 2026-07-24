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

bool matched_status_connected(const rmw_matched_status_t & status)
{
  return status.total_count == 1 &&
         status.total_count_change == 1 &&
         status.current_count == 1 &&
         status.current_count_change == 1;
}

bool matched_status_disconnected(const rmw_matched_status_t & status)
{
  return status.total_count == 1 &&
         status.total_count_change == 0 &&
         status.current_count == 0 &&
         status.current_count_change == -1;
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
  options.instance_id = 57;

  rmw_context_t context = rmw_get_zero_initialized_context();
  ret = rmw_init(&options, &context);
  if (ret != RMW_RET_OK) {
    const rmw_ret_t fini_ret = rmw_init_options_fini(&options);
    (void)fini_ret;
    std::cout << "{\"status\":\"init_failed\",\"ret\":" << ret << "}\n";
    return 1;
  }

  rmw_node_t * node = rmw_create_node(&context, "fleetqox_matched_event_probe", "/fleetqox");
  if (node == nullptr) {
    cleanup_context(&context, &options);
    std::cout << "{\"status\":\"create_node_failed\"}\n";
    return 1;
  }

  rosidl_message_type_support_t type_support{};
  type_support.typesupport_identifier = "rmw_fleetqox_cpp_matched_event_probe";
  rmw_qos_profile_t qos = rmw_qos_profile_default;
  qos.history = RMW_QOS_POLICY_HISTORY_KEEP_LAST;
  qos.depth = 8;
  rmw_publisher_options_t publisher_options = rmw_get_default_publisher_options();
  rmw_subscription_options_t subscription_options = rmw_get_default_subscription_options();

  const bool publication_supported = rmw_event_type_is_supported(RMW_EVENT_PUBLICATION_MATCHED);
  const bool subscription_supported = rmw_event_type_is_supported(RMW_EVENT_SUBSCRIPTION_MATCHED);
  const std::uint64_t events_init_before = rmw_fleetqox_cpp_qos_events_initialized();
  const std::uint64_t events_fini_before = rmw_fleetqox_cpp_qos_events_finalized();
  const std::uint64_t callbacks_before = rmw_fleetqox_cpp_qos_event_callbacks_set();

  const char * publication_topic = "/fleetqox/matched_event_publication_probe";
  rmw_publisher_t * publication_publisher =
    rmw_create_publisher(node, &type_support, publication_topic, &qos, &publisher_options);
  rmw_event_t publication_event = rmw_get_zero_initialized_event();
  const rmw_ret_t publication_event_init_ret = publication_publisher == nullptr ?
    RMW_RET_ERROR :
    rmw_publisher_event_init(
      &publication_event, publication_publisher, RMW_EVENT_PUBLICATION_MATCHED);
  CallbackState publication_callback_state{0, 0};
  const rmw_ret_t publication_callback_ret =
    rmw_event_set_callback(&publication_event, event_callback, &publication_callback_state);
  bool publication_initial_ready = true;
  const rmw_ret_t publication_initial_wait_ret =
    wait_event_once(&context, &publication_event, &publication_initial_ready);
  rmw_matched_status_t publication_initial_status{};
  bool publication_initial_taken = true;
  const rmw_ret_t publication_initial_take_ret =
    rmw_take_event(&publication_event, &publication_initial_status, &publication_initial_taken);
  rmw_subscription_t * publication_subscription =
    rmw_create_subscription(node, &type_support, publication_topic, &qos, &subscription_options);
  bool publication_connect_ready = false;
  const rmw_ret_t publication_connect_wait_ret =
    wait_event_once(&context, &publication_event, &publication_connect_ready);
  rmw_matched_status_t publication_connect_status{};
  bool publication_connect_taken = false;
  const rmw_ret_t publication_connect_take_ret =
    rmw_take_event(&publication_event, &publication_connect_status, &publication_connect_taken);
  const rmw_ret_t destroy_publication_subscription_ret = publication_subscription == nullptr ?
    RMW_RET_ERROR : rmw_destroy_subscription(node, publication_subscription);
  bool publication_disconnect_ready = false;
  const rmw_ret_t publication_disconnect_wait_ret =
    wait_event_once(&context, &publication_event, &publication_disconnect_ready);
  rmw_matched_status_t publication_disconnect_status{};
  bool publication_disconnect_taken = false;
  const rmw_ret_t publication_disconnect_take_ret =
    rmw_take_event(
      &publication_event, &publication_disconnect_status, &publication_disconnect_taken);
  rmw_matched_status_t publication_after_clear_status{};
  bool publication_after_clear_taken = true;
  const rmw_ret_t publication_after_clear_take_ret =
    rmw_take_event(
      &publication_event, &publication_after_clear_status, &publication_after_clear_taken);
  const rmw_ret_t publication_event_fini_ret = rmw_event_fini(&publication_event);
  const rmw_ret_t destroy_publication_publisher_ret = publication_publisher == nullptr ?
    RMW_RET_ERROR : rmw_destroy_publisher(node, publication_publisher);

  const char * subscription_topic = "/fleetqox/matched_event_subscription_probe";
  rmw_subscription_t * subscription_subscription =
    rmw_create_subscription(node, &type_support, subscription_topic, &qos, &subscription_options);
  rmw_event_t subscription_event = rmw_get_zero_initialized_event();
  const rmw_ret_t subscription_event_init_ret = subscription_subscription == nullptr ?
    RMW_RET_ERROR :
    rmw_subscription_event_init(
      &subscription_event, subscription_subscription, RMW_EVENT_SUBSCRIPTION_MATCHED);
  CallbackState subscription_callback_state{0, 0};
  const rmw_ret_t subscription_callback_ret =
    rmw_event_set_callback(&subscription_event, event_callback, &subscription_callback_state);
  bool subscription_initial_ready = true;
  const rmw_ret_t subscription_initial_wait_ret =
    wait_event_once(&context, &subscription_event, &subscription_initial_ready);
  rmw_matched_status_t subscription_initial_status{};
  bool subscription_initial_taken = true;
  const rmw_ret_t subscription_initial_take_ret =
    rmw_take_event(&subscription_event, &subscription_initial_status, &subscription_initial_taken);
  rmw_publisher_t * subscription_publisher =
    rmw_create_publisher(node, &type_support, subscription_topic, &qos, &publisher_options);
  bool subscription_connect_ready = false;
  const rmw_ret_t subscription_connect_wait_ret =
    wait_event_once(&context, &subscription_event, &subscription_connect_ready);
  rmw_matched_status_t subscription_connect_status{};
  bool subscription_connect_taken = false;
  const rmw_ret_t subscription_connect_take_ret =
    rmw_take_event(&subscription_event, &subscription_connect_status, &subscription_connect_taken);
  const rmw_ret_t destroy_subscription_publisher_ret = subscription_publisher == nullptr ?
    RMW_RET_ERROR : rmw_destroy_publisher(node, subscription_publisher);
  bool subscription_disconnect_ready = false;
  const rmw_ret_t subscription_disconnect_wait_ret =
    wait_event_once(&context, &subscription_event, &subscription_disconnect_ready);
  rmw_matched_status_t subscription_disconnect_status{};
  bool subscription_disconnect_taken = false;
  const rmw_ret_t subscription_disconnect_take_ret =
    rmw_take_event(
      &subscription_event, &subscription_disconnect_status, &subscription_disconnect_taken);
  rmw_matched_status_t subscription_after_clear_status{};
  bool subscription_after_clear_taken = true;
  const rmw_ret_t subscription_after_clear_take_ret =
    rmw_take_event(
      &subscription_event, &subscription_after_clear_status, &subscription_after_clear_taken);
  const rmw_ret_t subscription_event_fini_ret = rmw_event_fini(&subscription_event);
  const rmw_ret_t destroy_subscription_subscription_ret = subscription_subscription == nullptr ?
    RMW_RET_ERROR : rmw_destroy_subscription(node, subscription_subscription);

  const rmw_ret_t destroy_node_ret = rmw_destroy_node(node);
  cleanup_context(&context, &options);

  const std::uint64_t events_init_delta =
    rmw_fleetqox_cpp_qos_events_initialized() - events_init_before;
  const std::uint64_t events_fini_delta =
    rmw_fleetqox_cpp_qos_events_finalized() - events_fini_before;
  const std::uint64_t callbacks_delta =
    rmw_fleetqox_cpp_qos_event_callbacks_set() - callbacks_before;
  const bool publication_ok =
    publication_supported &&
    publication_event_init_ret == RMW_RET_OK &&
    publication_callback_ret == RMW_RET_OK &&
    publication_initial_wait_ret == RMW_RET_TIMEOUT &&
    !publication_initial_ready &&
    publication_initial_take_ret == RMW_RET_OK &&
    !publication_initial_taken &&
    publication_connect_wait_ret == RMW_RET_OK &&
    publication_connect_ready &&
    publication_connect_take_ret == RMW_RET_OK &&
    publication_connect_taken &&
    matched_status_connected(publication_connect_status) &&
    destroy_publication_subscription_ret == RMW_RET_OK &&
    publication_disconnect_wait_ret == RMW_RET_OK &&
    publication_disconnect_ready &&
    publication_disconnect_take_ret == RMW_RET_OK &&
    publication_disconnect_taken &&
    matched_status_disconnected(publication_disconnect_status) &&
    publication_after_clear_take_ret == RMW_RET_OK &&
    !publication_after_clear_taken &&
    publication_after_clear_status.total_count == publication_disconnect_status.total_count &&
    publication_after_clear_status.total_count_change == 0 &&
    publication_after_clear_status.current_count == 0 &&
    publication_after_clear_status.current_count_change == 0 &&
    publication_callback_state.calls >= 2 &&
    publication_callback_state.events >= 2 &&
    publication_event_fini_ret == RMW_RET_OK &&
    destroy_publication_publisher_ret == RMW_RET_OK;
  const bool subscription_ok =
    subscription_supported &&
    subscription_event_init_ret == RMW_RET_OK &&
    subscription_callback_ret == RMW_RET_OK &&
    subscription_initial_wait_ret == RMW_RET_TIMEOUT &&
    !subscription_initial_ready &&
    subscription_initial_take_ret == RMW_RET_OK &&
    !subscription_initial_taken &&
    subscription_connect_wait_ret == RMW_RET_OK &&
    subscription_connect_ready &&
    subscription_connect_take_ret == RMW_RET_OK &&
    subscription_connect_taken &&
    matched_status_connected(subscription_connect_status) &&
    destroy_subscription_publisher_ret == RMW_RET_OK &&
    subscription_disconnect_wait_ret == RMW_RET_OK &&
    subscription_disconnect_ready &&
    subscription_disconnect_take_ret == RMW_RET_OK &&
    subscription_disconnect_taken &&
    matched_status_disconnected(subscription_disconnect_status) &&
    subscription_after_clear_take_ret == RMW_RET_OK &&
    !subscription_after_clear_taken &&
    subscription_after_clear_status.total_count == subscription_disconnect_status.total_count &&
    subscription_after_clear_status.total_count_change == 0 &&
    subscription_after_clear_status.current_count == 0 &&
    subscription_after_clear_status.current_count_change == 0 &&
    subscription_callback_state.calls >= 2 &&
    subscription_callback_state.events >= 2 &&
    subscription_event_fini_ret == RMW_RET_OK &&
    destroy_subscription_subscription_ret == RMW_RET_OK;
  const bool lifecycle_ok =
    events_init_delta == 2 &&
    events_fini_delta == 2 &&
    callbacks_delta == 2 &&
    destroy_node_ret == RMW_RET_OK;
  const bool ok = publication_ok && subscription_ok && lifecycle_ok;

  std::cout << "{\"schema_version\":\"fleetrmw.matched_event_probe.v1\",";
  std::cout << "\"status\":\"" << (ok ? "ok" : "failed") << "\",";
  std::cout << "\"publication_matched_supported\":" <<
    (publication_supported ? "true" : "false") << ",";
  std::cout << "\"subscription_matched_supported\":" <<
    (subscription_supported ? "true" : "false") << ",";
  std::cout << "\"publication_initial_wait_ready\":" <<
    (publication_initial_ready ? "true" : "false") << ",";
  std::cout << "\"publication_connect_wait_ready\":" <<
    (publication_connect_ready ? "true" : "false") << ",";
  std::cout << "\"publication_disconnect_wait_ready\":" <<
    (publication_disconnect_ready ? "true" : "false") << ",";
  std::cout << "\"publication_connect_taken\":" <<
    (publication_connect_taken ? "true" : "false") << ",";
  std::cout << "\"publication_disconnect_taken\":" <<
    (publication_disconnect_taken ? "true" : "false") << ",";
  std::cout << "\"publication_connect_current_count\":" <<
    publication_connect_status.current_count << ",";
  std::cout << "\"publication_disconnect_current_count\":" <<
    publication_disconnect_status.current_count << ",";
  std::cout << "\"publication_disconnect_current_count_change\":" <<
    publication_disconnect_status.current_count_change << ",";
  std::cout << "\"publication_callback_calls\":" << publication_callback_state.calls << ",";
  std::cout << "\"publication_callback_events\":" << publication_callback_state.events << ",";
  std::cout << "\"subscription_connect_taken\":" <<
    (subscription_connect_taken ? "true" : "false") << ",";
  std::cout << "\"subscription_initial_wait_ready\":" <<
    (subscription_initial_ready ? "true" : "false") << ",";
  std::cout << "\"subscription_connect_wait_ready\":" <<
    (subscription_connect_ready ? "true" : "false") << ",";
  std::cout << "\"subscription_disconnect_wait_ready\":" <<
    (subscription_disconnect_ready ? "true" : "false") << ",";
  std::cout << "\"subscription_disconnect_taken\":" <<
    (subscription_disconnect_taken ? "true" : "false") << ",";
  std::cout << "\"subscription_connect_current_count\":" <<
    subscription_connect_status.current_count << ",";
  std::cout << "\"subscription_disconnect_current_count\":" <<
    subscription_disconnect_status.current_count << ",";
  std::cout << "\"subscription_disconnect_current_count_change\":" <<
    subscription_disconnect_status.current_count_change << ",";
  std::cout << "\"subscription_callback_calls\":" << subscription_callback_state.calls << ",";
  std::cout << "\"subscription_callback_events\":" << subscription_callback_state.events << ",";
  std::cout << "\"events_initialized_delta\":" << events_init_delta << ",";
  std::cout << "\"events_finalized_delta\":" << events_fini_delta << ",";
  std::cout << "\"event_callbacks_set_delta\":" << callbacks_delta << ",";
  std::cout << "\"matched_event_production\":true,";
  std::cout << "\"matched_event_scope\":\"local_same_process_compatible_endpoint_create_destroy\"";
  std::cout << "}\n";
  return ok ? 0 : 1;
}

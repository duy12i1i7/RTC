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

bool incompatible_status_ok(
  const rmw_qos_incompatible_event_status_t & status,
  rmw_qos_policy_kind_t policy_kind)
{
  return status.total_count == 1 &&
         status.total_count_change == 1 &&
         status.last_policy_kind == policy_kind;
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
  options.instance_id = 58;

  rmw_context_t context = rmw_get_zero_initialized_context();
  ret = rmw_init(&options, &context);
  if (ret != RMW_RET_OK) {
    const rmw_ret_t fini_ret = rmw_init_options_fini(&options);
    (void)fini_ret;
    std::cout << "{\"status\":\"init_failed\",\"ret\":" << ret << "}\n";
    return 1;
  }

  rmw_node_t * node =
    rmw_create_node(&context, "fleetqox_qos_incompatible_event_probe", "/fleetqox");
  if (node == nullptr) {
    cleanup_context(&context, &options);
    std::cout << "{\"status\":\"create_node_failed\"}\n";
    return 1;
  }

  rosidl_message_type_support_t type_support{};
  type_support.typesupport_identifier = "rmw_fleetqox_cpp_qos_incompatible_event_probe";
  rmw_qos_profile_t offered_qos = rmw_qos_profile_default;
  offered_qos.history = RMW_QOS_POLICY_HISTORY_KEEP_LAST;
  offered_qos.depth = 8;
  offered_qos.reliability = RMW_QOS_POLICY_RELIABILITY_BEST_EFFORT;
  rmw_qos_profile_t requested_qos = rmw_qos_profile_default;
  requested_qos.history = RMW_QOS_POLICY_HISTORY_KEEP_LAST;
  requested_qos.depth = 8;
  requested_qos.reliability = RMW_QOS_POLICY_RELIABILITY_RELIABLE;
  rmw_qos_profile_t offered_durability_qos = rmw_qos_profile_default;
  offered_durability_qos.history = RMW_QOS_POLICY_HISTORY_KEEP_LAST;
  offered_durability_qos.depth = 8;
  offered_durability_qos.durability = RMW_QOS_POLICY_DURABILITY_VOLATILE;
  rmw_qos_profile_t requested_durability_qos = rmw_qos_profile_default;
  requested_durability_qos.history = RMW_QOS_POLICY_HISTORY_KEEP_LAST;
  requested_durability_qos.depth = 8;
  requested_durability_qos.durability = RMW_QOS_POLICY_DURABILITY_TRANSIENT_LOCAL;
  rmw_publisher_options_t publisher_options = rmw_get_default_publisher_options();
  rmw_subscription_options_t subscription_options = rmw_get_default_subscription_options();

  const bool offered_supported =
    rmw_event_type_is_supported(RMW_EVENT_OFFERED_QOS_INCOMPATIBLE);
  const bool requested_supported =
    rmw_event_type_is_supported(RMW_EVENT_REQUESTED_QOS_INCOMPATIBLE);
  const std::uint64_t events_init_before = rmw_fleetqox_cpp_qos_events_initialized();
  const std::uint64_t events_fini_before = rmw_fleetqox_cpp_qos_events_finalized();
  const std::uint64_t callbacks_before = rmw_fleetqox_cpp_qos_event_callbacks_set();

  const char * offered_topic = "/fleetqox/qos_incompatible_offered_probe";
  rmw_publisher_t * offered_publisher =
    rmw_create_publisher(node, &type_support, offered_topic, &offered_qos, &publisher_options);
  rmw_event_t offered_event = rmw_get_zero_initialized_event();
  const rmw_ret_t offered_event_init_ret = offered_publisher == nullptr ?
    RMW_RET_ERROR :
    rmw_publisher_event_init(
      &offered_event, offered_publisher, RMW_EVENT_OFFERED_QOS_INCOMPATIBLE);
  rmw_event_t offered_matched_event = rmw_get_zero_initialized_event();
  const rmw_ret_t offered_matched_event_init_ret = offered_publisher == nullptr ?
    RMW_RET_ERROR :
    rmw_publisher_event_init(
      &offered_matched_event, offered_publisher, RMW_EVENT_PUBLICATION_MATCHED);
  CallbackState offered_callback_state{0, 0};
  const rmw_ret_t offered_callback_ret =
    rmw_event_set_callback(&offered_event, event_callback, &offered_callback_state);
  bool offered_initial_ready = true;
  const rmw_ret_t offered_initial_wait_ret =
    wait_event_once(&context, &offered_event, &offered_initial_ready);
  rmw_offered_qos_incompatible_event_status_t offered_initial_status{};
  bool offered_initial_taken = true;
  const rmw_ret_t offered_initial_take_ret =
    rmw_take_event(&offered_event, &offered_initial_status, &offered_initial_taken);
  rmw_subscription_t * offered_subscription =
    rmw_create_subscription(
      node, &type_support, offered_topic, &requested_qos, &subscription_options);
  bool offered_matched_ready = true;
  const rmw_ret_t offered_matched_wait_ret =
    wait_event_once(&context, &offered_matched_event, &offered_matched_ready);
  rmw_matched_status_t offered_matched_status{};
  bool offered_matched_taken = true;
  const rmw_ret_t offered_matched_take_ret =
    rmw_take_event(&offered_matched_event, &offered_matched_status, &offered_matched_taken);
  bool offered_ready = false;
  const rmw_ret_t offered_wait_ret =
    wait_event_once(&context, &offered_event, &offered_ready);
  rmw_offered_qos_incompatible_event_status_t offered_status{};
  bool offered_taken = false;
  const rmw_ret_t offered_take_ret =
    rmw_take_event(&offered_event, &offered_status, &offered_taken);
  rmw_offered_qos_incompatible_event_status_t offered_after_clear_status{};
  bool offered_after_clear_taken = true;
  const rmw_ret_t offered_after_clear_take_ret =
    rmw_take_event(&offered_event, &offered_after_clear_status, &offered_after_clear_taken);
  const rmw_ret_t destroy_offered_subscription_ret = offered_subscription == nullptr ?
    RMW_RET_ERROR : rmw_destroy_subscription(node, offered_subscription);
  const rmw_ret_t offered_matched_event_fini_ret = rmw_event_fini(&offered_matched_event);
  const rmw_ret_t offered_event_fini_ret = rmw_event_fini(&offered_event);
  const rmw_ret_t destroy_offered_publisher_ret = offered_publisher == nullptr ?
    RMW_RET_ERROR : rmw_destroy_publisher(node, offered_publisher);

  const char * requested_topic = "/fleetqox/qos_incompatible_requested_probe";
  rmw_subscription_t * requested_subscription =
    rmw_create_subscription(
      node, &type_support, requested_topic, &requested_qos, &subscription_options);
  rmw_event_t requested_event = rmw_get_zero_initialized_event();
  const rmw_ret_t requested_event_init_ret = requested_subscription == nullptr ?
    RMW_RET_ERROR :
    rmw_subscription_event_init(
      &requested_event, requested_subscription, RMW_EVENT_REQUESTED_QOS_INCOMPATIBLE);
  rmw_event_t requested_matched_event = rmw_get_zero_initialized_event();
  const rmw_ret_t requested_matched_event_init_ret = requested_subscription == nullptr ?
    RMW_RET_ERROR :
    rmw_subscription_event_init(
      &requested_matched_event, requested_subscription, RMW_EVENT_SUBSCRIPTION_MATCHED);
  CallbackState requested_callback_state{0, 0};
  const rmw_ret_t requested_callback_ret =
    rmw_event_set_callback(&requested_event, event_callback, &requested_callback_state);
  bool requested_initial_ready = true;
  const rmw_ret_t requested_initial_wait_ret =
    wait_event_once(&context, &requested_event, &requested_initial_ready);
  rmw_requested_qos_incompatible_event_status_t requested_initial_status{};
  bool requested_initial_taken = true;
  const rmw_ret_t requested_initial_take_ret =
    rmw_take_event(&requested_event, &requested_initial_status, &requested_initial_taken);
  rmw_publisher_t * requested_publisher =
    rmw_create_publisher(
      node, &type_support, requested_topic, &offered_qos, &publisher_options);
  bool requested_matched_ready = true;
  const rmw_ret_t requested_matched_wait_ret =
    wait_event_once(&context, &requested_matched_event, &requested_matched_ready);
  rmw_matched_status_t requested_matched_status{};
  bool requested_matched_taken = true;
  const rmw_ret_t requested_matched_take_ret =
    rmw_take_event(
      &requested_matched_event, &requested_matched_status, &requested_matched_taken);
  bool requested_ready = false;
  const rmw_ret_t requested_wait_ret =
    wait_event_once(&context, &requested_event, &requested_ready);
  rmw_requested_qos_incompatible_event_status_t requested_status{};
  bool requested_taken = false;
  const rmw_ret_t requested_take_ret =
    rmw_take_event(&requested_event, &requested_status, &requested_taken);
  rmw_requested_qos_incompatible_event_status_t requested_after_clear_status{};
  bool requested_after_clear_taken = true;
  const rmw_ret_t requested_after_clear_take_ret =
    rmw_take_event(
      &requested_event, &requested_after_clear_status, &requested_after_clear_taken);
  const rmw_ret_t destroy_requested_publisher_ret = requested_publisher == nullptr ?
    RMW_RET_ERROR : rmw_destroy_publisher(node, requested_publisher);
  const rmw_ret_t requested_matched_event_fini_ret = rmw_event_fini(&requested_matched_event);
  const rmw_ret_t requested_event_fini_ret = rmw_event_fini(&requested_event);
  const rmw_ret_t destroy_requested_subscription_ret = requested_subscription == nullptr ?
    RMW_RET_ERROR : rmw_destroy_subscription(node, requested_subscription);

  const char * durability_offered_topic =
    "/fleetqox/qos_incompatible_durability_offered_probe";
  rmw_publisher_t * durability_offered_publisher =
    rmw_create_publisher(
      node,
      &type_support,
      durability_offered_topic,
      &offered_durability_qos,
      &publisher_options);
  rmw_event_t durability_offered_event = rmw_get_zero_initialized_event();
  const rmw_ret_t durability_offered_event_init_ret =
    durability_offered_publisher == nullptr ?
    RMW_RET_ERROR :
    rmw_publisher_event_init(
      &durability_offered_event,
      durability_offered_publisher,
      RMW_EVENT_OFFERED_QOS_INCOMPATIBLE);
  rmw_event_t durability_offered_matched_event = rmw_get_zero_initialized_event();
  const rmw_ret_t durability_offered_matched_event_init_ret =
    durability_offered_publisher == nullptr ?
    RMW_RET_ERROR :
    rmw_publisher_event_init(
      &durability_offered_matched_event,
      durability_offered_publisher,
      RMW_EVENT_PUBLICATION_MATCHED);
  CallbackState durability_offered_callback_state{0, 0};
  const rmw_ret_t durability_offered_callback_ret =
    rmw_event_set_callback(
      &durability_offered_event, event_callback, &durability_offered_callback_state);
  rmw_subscription_t * durability_offered_subscription =
    rmw_create_subscription(
      node,
      &type_support,
      durability_offered_topic,
      &requested_durability_qos,
      &subscription_options);
  bool durability_offered_matched_ready = true;
  const rmw_ret_t durability_offered_matched_wait_ret =
    wait_event_once(
      &context, &durability_offered_matched_event, &durability_offered_matched_ready);
  rmw_matched_status_t durability_offered_matched_status{};
  bool durability_offered_matched_taken = true;
  const rmw_ret_t durability_offered_matched_take_ret =
    rmw_take_event(
      &durability_offered_matched_event,
      &durability_offered_matched_status,
      &durability_offered_matched_taken);
  bool durability_offered_ready = false;
  const rmw_ret_t durability_offered_wait_ret =
    wait_event_once(&context, &durability_offered_event, &durability_offered_ready);
  rmw_offered_qos_incompatible_event_status_t durability_offered_status{};
  bool durability_offered_taken = false;
  const rmw_ret_t durability_offered_take_ret =
    rmw_take_event(&durability_offered_event, &durability_offered_status, &durability_offered_taken);
  const rmw_ret_t destroy_durability_offered_subscription_ret =
    durability_offered_subscription == nullptr ?
    RMW_RET_ERROR : rmw_destroy_subscription(node, durability_offered_subscription);
  const rmw_ret_t durability_offered_matched_event_fini_ret =
    rmw_event_fini(&durability_offered_matched_event);
  const rmw_ret_t durability_offered_event_fini_ret =
    rmw_event_fini(&durability_offered_event);
  const rmw_ret_t destroy_durability_offered_publisher_ret =
    durability_offered_publisher == nullptr ?
    RMW_RET_ERROR : rmw_destroy_publisher(node, durability_offered_publisher);

  const char * durability_requested_topic =
    "/fleetqox/qos_incompatible_durability_requested_probe";
  rmw_subscription_t * durability_requested_subscription =
    rmw_create_subscription(
      node,
      &type_support,
      durability_requested_topic,
      &requested_durability_qos,
      &subscription_options);
  rmw_event_t durability_requested_event = rmw_get_zero_initialized_event();
  const rmw_ret_t durability_requested_event_init_ret =
    durability_requested_subscription == nullptr ?
    RMW_RET_ERROR :
    rmw_subscription_event_init(
      &durability_requested_event,
      durability_requested_subscription,
      RMW_EVENT_REQUESTED_QOS_INCOMPATIBLE);
  rmw_event_t durability_requested_matched_event = rmw_get_zero_initialized_event();
  const rmw_ret_t durability_requested_matched_event_init_ret =
    durability_requested_subscription == nullptr ?
    RMW_RET_ERROR :
    rmw_subscription_event_init(
      &durability_requested_matched_event,
      durability_requested_subscription,
      RMW_EVENT_SUBSCRIPTION_MATCHED);
  CallbackState durability_requested_callback_state{0, 0};
  const rmw_ret_t durability_requested_callback_ret =
    rmw_event_set_callback(
      &durability_requested_event, event_callback, &durability_requested_callback_state);
  rmw_publisher_t * durability_requested_publisher =
    rmw_create_publisher(
      node,
      &type_support,
      durability_requested_topic,
      &offered_durability_qos,
      &publisher_options);
  bool durability_requested_matched_ready = true;
  const rmw_ret_t durability_requested_matched_wait_ret =
    wait_event_once(
      &context, &durability_requested_matched_event, &durability_requested_matched_ready);
  rmw_matched_status_t durability_requested_matched_status{};
  bool durability_requested_matched_taken = true;
  const rmw_ret_t durability_requested_matched_take_ret =
    rmw_take_event(
      &durability_requested_matched_event,
      &durability_requested_matched_status,
      &durability_requested_matched_taken);
  bool durability_requested_ready = false;
  const rmw_ret_t durability_requested_wait_ret =
    wait_event_once(&context, &durability_requested_event, &durability_requested_ready);
  rmw_requested_qos_incompatible_event_status_t durability_requested_status{};
  bool durability_requested_taken = false;
  const rmw_ret_t durability_requested_take_ret =
    rmw_take_event(
      &durability_requested_event, &durability_requested_status, &durability_requested_taken);
  const rmw_ret_t destroy_durability_requested_publisher_ret =
    durability_requested_publisher == nullptr ?
    RMW_RET_ERROR : rmw_destroy_publisher(node, durability_requested_publisher);
  const rmw_ret_t durability_requested_matched_event_fini_ret =
    rmw_event_fini(&durability_requested_matched_event);
  const rmw_ret_t durability_requested_event_fini_ret =
    rmw_event_fini(&durability_requested_event);
  const rmw_ret_t destroy_durability_requested_subscription_ret =
    durability_requested_subscription == nullptr ?
    RMW_RET_ERROR : rmw_destroy_subscription(node, durability_requested_subscription);

  const rmw_ret_t destroy_node_ret = rmw_destroy_node(node);
  cleanup_context(&context, &options);

  const std::uint64_t events_init_delta =
    rmw_fleetqox_cpp_qos_events_initialized() - events_init_before;
  const std::uint64_t events_fini_delta =
    rmw_fleetqox_cpp_qos_events_finalized() - events_fini_before;
  const std::uint64_t callbacks_delta =
    rmw_fleetqox_cpp_qos_event_callbacks_set() - callbacks_before;
  const bool offered_ok =
    offered_supported &&
    offered_event_init_ret == RMW_RET_OK &&
    offered_matched_event_init_ret == RMW_RET_OK &&
    offered_callback_ret == RMW_RET_OK &&
    offered_initial_wait_ret == RMW_RET_TIMEOUT &&
    !offered_initial_ready &&
    offered_initial_take_ret == RMW_RET_OK &&
    !offered_initial_taken &&
    offered_matched_wait_ret == RMW_RET_TIMEOUT &&
    !offered_matched_ready &&
    offered_matched_take_ret == RMW_RET_OK &&
    !offered_matched_taken &&
    offered_matched_status.current_count == 0 &&
    offered_matched_status.current_count_change == 0 &&
    offered_wait_ret == RMW_RET_OK &&
    offered_ready &&
    offered_take_ret == RMW_RET_OK &&
    offered_taken &&
    incompatible_status_ok(offered_status, RMW_QOS_POLICY_RELIABILITY) &&
    offered_callback_state.calls >= 1 &&
    offered_callback_state.events >= 1 &&
    offered_after_clear_take_ret == RMW_RET_OK &&
    !offered_after_clear_taken &&
    offered_after_clear_status.total_count == offered_status.total_count &&
    offered_after_clear_status.total_count_change == 0 &&
    offered_after_clear_status.last_policy_kind == offered_status.last_policy_kind &&
    destroy_offered_subscription_ret == RMW_RET_OK &&
    offered_matched_event_fini_ret == RMW_RET_OK &&
    offered_event_fini_ret == RMW_RET_OK &&
    destroy_offered_publisher_ret == RMW_RET_OK;
  const bool requested_ok =
    requested_supported &&
    requested_event_init_ret == RMW_RET_OK &&
    requested_matched_event_init_ret == RMW_RET_OK &&
    requested_callback_ret == RMW_RET_OK &&
    requested_initial_wait_ret == RMW_RET_TIMEOUT &&
    !requested_initial_ready &&
    requested_initial_take_ret == RMW_RET_OK &&
    !requested_initial_taken &&
    requested_matched_wait_ret == RMW_RET_TIMEOUT &&
    !requested_matched_ready &&
    requested_matched_take_ret == RMW_RET_OK &&
    !requested_matched_taken &&
    requested_matched_status.current_count == 0 &&
    requested_matched_status.current_count_change == 0 &&
    requested_wait_ret == RMW_RET_OK &&
    requested_ready &&
    requested_take_ret == RMW_RET_OK &&
    requested_taken &&
    incompatible_status_ok(requested_status, RMW_QOS_POLICY_RELIABILITY) &&
    requested_callback_state.calls >= 1 &&
    requested_callback_state.events >= 1 &&
    requested_after_clear_take_ret == RMW_RET_OK &&
    !requested_after_clear_taken &&
    requested_after_clear_status.total_count == requested_status.total_count &&
    requested_after_clear_status.total_count_change == 0 &&
    requested_after_clear_status.last_policy_kind == requested_status.last_policy_kind &&
    destroy_requested_publisher_ret == RMW_RET_OK &&
    requested_matched_event_fini_ret == RMW_RET_OK &&
    requested_event_fini_ret == RMW_RET_OK &&
    destroy_requested_subscription_ret == RMW_RET_OK;
  const bool durability_offered_ok =
    durability_offered_event_init_ret == RMW_RET_OK &&
    durability_offered_matched_event_init_ret == RMW_RET_OK &&
    durability_offered_callback_ret == RMW_RET_OK &&
    durability_offered_matched_wait_ret == RMW_RET_TIMEOUT &&
    !durability_offered_matched_ready &&
    durability_offered_matched_take_ret == RMW_RET_OK &&
    !durability_offered_matched_taken &&
    durability_offered_matched_status.current_count == 0 &&
    durability_offered_matched_status.current_count_change == 0 &&
    durability_offered_wait_ret == RMW_RET_OK &&
    durability_offered_ready &&
    durability_offered_take_ret == RMW_RET_OK &&
    durability_offered_taken &&
    incompatible_status_ok(durability_offered_status, RMW_QOS_POLICY_DURABILITY) &&
    durability_offered_callback_state.calls >= 1 &&
    durability_offered_callback_state.events >= 1 &&
    destroy_durability_offered_subscription_ret == RMW_RET_OK &&
    durability_offered_matched_event_fini_ret == RMW_RET_OK &&
    durability_offered_event_fini_ret == RMW_RET_OK &&
    destroy_durability_offered_publisher_ret == RMW_RET_OK;
  const bool durability_requested_ok =
    durability_requested_event_init_ret == RMW_RET_OK &&
    durability_requested_matched_event_init_ret == RMW_RET_OK &&
    durability_requested_callback_ret == RMW_RET_OK &&
    durability_requested_matched_wait_ret == RMW_RET_TIMEOUT &&
    !durability_requested_matched_ready &&
    durability_requested_matched_take_ret == RMW_RET_OK &&
    !durability_requested_matched_taken &&
    durability_requested_matched_status.current_count == 0 &&
    durability_requested_matched_status.current_count_change == 0 &&
    durability_requested_wait_ret == RMW_RET_OK &&
    durability_requested_ready &&
    durability_requested_take_ret == RMW_RET_OK &&
    durability_requested_taken &&
    incompatible_status_ok(durability_requested_status, RMW_QOS_POLICY_DURABILITY) &&
    durability_requested_callback_state.calls >= 1 &&
    durability_requested_callback_state.events >= 1 &&
    destroy_durability_requested_publisher_ret == RMW_RET_OK &&
    durability_requested_matched_event_fini_ret == RMW_RET_OK &&
    durability_requested_event_fini_ret == RMW_RET_OK &&
    destroy_durability_requested_subscription_ret == RMW_RET_OK;
  const bool lifecycle_ok =
    events_init_delta == 8 &&
    events_fini_delta == 8 &&
    callbacks_delta == 4 &&
    destroy_node_ret == RMW_RET_OK;
  const bool ok =
    offered_ok && requested_ok && durability_offered_ok && durability_requested_ok && lifecycle_ok;

  std::cout << "{\"schema_version\":\"fleetrmw.qos_incompatible_event_probe.v1\",";
  std::cout << "\"status\":\"" << (ok ? "ok" : "failed") << "\",";
  std::cout << "\"offered_qos_incompatible_supported\":" <<
    (offered_supported ? "true" : "false") << ",";
  std::cout << "\"requested_qos_incompatible_supported\":" <<
    (requested_supported ? "true" : "false") << ",";
  std::cout << "\"offered_taken\":" << (offered_taken ? "true" : "false") << ",";
  std::cout << "\"offered_wait_ready\":" << (offered_ready ? "true" : "false") << ",";
  std::cout << "\"offered_total_count\":" << offered_status.total_count << ",";
  std::cout << "\"offered_total_count_change\":" << offered_status.total_count_change << ",";
  std::cout << "\"offered_last_policy_kind\":" <<
    static_cast<int>(offered_status.last_policy_kind) << ",";
  std::cout << "\"offered_callback_calls\":" << offered_callback_state.calls << ",";
  std::cout << "\"offered_callback_events\":" << offered_callback_state.events << ",";
  std::cout << "\"offered_incompatible_endpoint_matched_taken\":" <<
    (offered_matched_taken ? "true" : "false") << ",";
  std::cout << "\"offered_incompatible_endpoint_matched_wait_ready\":" <<
    (offered_matched_ready ? "true" : "false") << ",";
  std::cout << "\"requested_taken\":" << (requested_taken ? "true" : "false") << ",";
  std::cout << "\"requested_wait_ready\":" << (requested_ready ? "true" : "false") << ",";
  std::cout << "\"requested_total_count\":" << requested_status.total_count << ",";
  std::cout << "\"requested_total_count_change\":" << requested_status.total_count_change << ",";
  std::cout << "\"requested_last_policy_kind\":" <<
    static_cast<int>(requested_status.last_policy_kind) << ",";
  std::cout << "\"requested_callback_calls\":" << requested_callback_state.calls << ",";
  std::cout << "\"requested_callback_events\":" << requested_callback_state.events << ",";
  std::cout << "\"requested_incompatible_endpoint_matched_taken\":" <<
    (requested_matched_taken ? "true" : "false") << ",";
  std::cout << "\"requested_incompatible_endpoint_matched_wait_ready\":" <<
    (requested_matched_ready ? "true" : "false") << ",";
  std::cout << "\"durability_offered_taken\":" <<
    (durability_offered_taken ? "true" : "false") << ",";
  std::cout << "\"durability_offered_wait_ready\":" <<
    (durability_offered_ready ? "true" : "false") << ",";
  std::cout << "\"durability_offered_total_count\":" <<
    durability_offered_status.total_count << ",";
  std::cout << "\"durability_offered_total_count_change\":" <<
    durability_offered_status.total_count_change << ",";
  std::cout << "\"durability_offered_last_policy_kind\":" <<
    static_cast<int>(durability_offered_status.last_policy_kind) << ",";
  std::cout << "\"durability_offered_callback_events\":" <<
    durability_offered_callback_state.events << ",";
  std::cout << "\"durability_offered_incompatible_endpoint_matched_taken\":" <<
    (durability_offered_matched_taken ? "true" : "false") << ",";
  std::cout << "\"durability_offered_incompatible_endpoint_matched_wait_ready\":" <<
    (durability_offered_matched_ready ? "true" : "false") << ",";
  std::cout << "\"durability_requested_taken\":" <<
    (durability_requested_taken ? "true" : "false") << ",";
  std::cout << "\"durability_requested_wait_ready\":" <<
    (durability_requested_ready ? "true" : "false") << ",";
  std::cout << "\"durability_requested_total_count\":" <<
    durability_requested_status.total_count << ",";
  std::cout << "\"durability_requested_total_count_change\":" <<
    durability_requested_status.total_count_change << ",";
  std::cout << "\"durability_requested_last_policy_kind\":" <<
    static_cast<int>(durability_requested_status.last_policy_kind) << ",";
  std::cout << "\"durability_requested_callback_events\":" <<
    durability_requested_callback_state.events << ",";
  std::cout << "\"durability_requested_incompatible_endpoint_matched_taken\":" <<
    (durability_requested_matched_taken ? "true" : "false") << ",";
  std::cout << "\"durability_requested_incompatible_endpoint_matched_wait_ready\":" <<
    (durability_requested_matched_ready ? "true" : "false") << ",";
  std::cout << "\"events_initialized_delta\":" << events_init_delta << ",";
  std::cout << "\"events_finalized_delta\":" << events_fini_delta << ",";
  std::cout << "\"event_callbacks_set_delta\":" << callbacks_delta << ",";
  std::cout << "\"qos_incompatible_event_production\":true,";
  std::cout << "\"qos_incompatible_event_scope\":\"local_same_process_reliability_and_durability_mismatch\"";
  std::cout << "}\n";
  return ok ? 0 : 1;
}

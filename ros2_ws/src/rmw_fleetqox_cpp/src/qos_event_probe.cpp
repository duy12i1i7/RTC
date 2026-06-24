#include <cstdint>
#include <iostream>
#include <sstream>

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

}  // namespace

int main()
{
  rcutils_allocator_t allocator = rcutils_get_default_allocator();
  rmw_init_options_t options = rmw_get_zero_initialized_init_options();
  rmw_ret_t ret = rmw_init_options_init(&options, allocator);
  if (ret != RMW_RET_OK) {
    std::cout << "{\"status\":\"init_options_failed\",\"ret\":" << ret << "}" << std::endl;
    return 1;
  }
  options.instance_id = 56;

  rmw_context_t context = rmw_get_zero_initialized_context();
  ret = rmw_init(&options, &context);
  if (ret != RMW_RET_OK) {
    const rmw_ret_t fini_ret = rmw_init_options_fini(&options);
    (void)fini_ret;
    std::cout << "{\"status\":\"init_failed\",\"ret\":" << ret << "}" << std::endl;
    return 1;
  }

  rmw_node_t * node = rmw_create_node(&context, "fleetqox_qos_event_probe", "/fleetqox");
  if (node == nullptr) {
    cleanup_context(&context, &options);
    std::cout << "{\"status\":\"create_node_failed\"}" << std::endl;
    return 1;
  }

  rosidl_message_type_support_t type_support{};
  type_support.typesupport_identifier = "rmw_fleetqox_cpp_qos_event_probe";
  rmw_qos_profile_t qos = rmw_qos_profile_default;
  qos.deadline.sec = 0;
  qos.deadline.nsec = 1000000;
  const char * topic = "/fleetqox/qos_event_probe";
  rmw_publisher_options_t publisher_options = rmw_get_default_publisher_options();
  rmw_subscription_options_t subscription_options = rmw_get_default_subscription_options();
  rmw_publisher_t * publisher = rmw_create_publisher(
    node, &type_support, topic, &qos, &publisher_options);
  rmw_subscription_t * subscription = rmw_create_subscription(
    node, &type_support, topic, &qos, &subscription_options);

  const bool offered_supported =
    rmw_event_type_is_supported(RMW_EVENT_OFFERED_DEADLINE_MISSED);
  const bool requested_supported =
    rmw_event_type_is_supported(RMW_EVENT_REQUESTED_DEADLINE_MISSED);
  const bool invalid_supported = rmw_event_type_is_supported(RMW_EVENT_INVALID);
  const std::uint64_t events_init_before = rmw_fleetqox_cpp_qos_events_initialized();
  const std::uint64_t events_fini_before = rmw_fleetqox_cpp_qos_events_finalized();
  const std::uint64_t callbacks_before = rmw_fleetqox_cpp_qos_event_callbacks_set();

  rmw_event_t publisher_event = rmw_get_zero_initialized_event();
  rmw_event_t subscription_event = rmw_get_zero_initialized_event();
  const rmw_ret_t publisher_event_init_ret = publisher == nullptr ?
    RMW_RET_ERROR :
    rmw_publisher_event_init(&publisher_event, publisher, RMW_EVENT_OFFERED_DEADLINE_MISSED);
  const rmw_ret_t subscription_event_init_ret = subscription == nullptr ?
    RMW_RET_ERROR :
    rmw_subscription_event_init(
      &subscription_event, subscription, RMW_EVENT_REQUESTED_DEADLINE_MISSED);

  CallbackState publisher_callback_state{0, 0};
  CallbackState subscription_callback_state{0, 0};
  const rmw_ret_t publisher_callback_ret =
    rmw_event_set_callback(&publisher_event, event_callback, &publisher_callback_state);
  const rmw_ret_t subscription_callback_ret =
    rmw_event_set_callback(&subscription_event, event_callback, &subscription_callback_state);

  rmw_offered_deadline_missed_status_t offered_status{};
  rmw_requested_deadline_missed_status_t requested_status{};
  bool publisher_taken = true;
  bool subscription_taken = true;
  const rmw_ret_t publisher_take_ret =
    rmw_take_event(&publisher_event, &offered_status, &publisher_taken);
  const rmw_ret_t subscription_take_ret =
    rmw_take_event(&subscription_event, &requested_status, &subscription_taken);

  const rmw_ret_t publisher_event_fini_ret = rmw_event_fini(&publisher_event);
  const rmw_ret_t subscription_event_fini_ret = rmw_event_fini(&subscription_event);
  const rmw_ret_t destroy_pub_ret = publisher == nullptr ?
    RMW_RET_ERROR : rmw_destroy_publisher(node, publisher);
  const rmw_ret_t destroy_sub_ret = subscription == nullptr ?
    RMW_RET_ERROR : rmw_destroy_subscription(node, subscription);
  const rmw_ret_t destroy_node_ret = rmw_destroy_node(node);
  cleanup_context(&context, &options);

  const std::uint64_t events_init_delta =
    rmw_fleetqox_cpp_qos_events_initialized() - events_init_before;
  const std::uint64_t events_fini_delta =
    rmw_fleetqox_cpp_qos_events_finalized() - events_fini_before;
  const std::uint64_t callbacks_delta =
    rmw_fleetqox_cpp_qos_event_callbacks_set() - callbacks_before;
  const bool event_object_ok =
    offered_supported &&
    requested_supported &&
    !invalid_supported &&
    publisher_event_init_ret == RMW_RET_OK &&
    subscription_event_init_ret == RMW_RET_OK &&
    publisher_callback_ret == RMW_RET_OK &&
    subscription_callback_ret == RMW_RET_OK &&
    publisher_take_ret == RMW_RET_OK &&
    subscription_take_ret == RMW_RET_OK &&
    !publisher_taken &&
    !subscription_taken &&
    publisher_event_fini_ret == RMW_RET_OK &&
    subscription_event_fini_ret == RMW_RET_OK &&
    events_init_delta == 2 &&
    events_fini_delta == 2 &&
    callbacks_delta == 2;
  const bool no_event_production_ok =
    publisher_callback_state.calls == 0 &&
    subscription_callback_state.calls == 0 &&
    offered_status.total_count == 0 &&
    offered_status.total_count_change == 0 &&
    requested_status.total_count == 0 &&
    requested_status.total_count_change == 0;
  const bool cleanup_ok =
    destroy_pub_ret == RMW_RET_OK &&
    destroy_sub_ret == RMW_RET_OK &&
    destroy_node_ret == RMW_RET_OK;
  const bool ok = event_object_ok && no_event_production_ok && cleanup_ok;

  std::cout << "{\"schema_version\":\"fleetrmw.qos_event_probe.v1\",";
  std::cout << "\"status\":\"" << (ok ? "ok" : "failed") << "\",";
  std::cout << "\"topic\":\"" << topic << "\",";
  std::cout << "\"publisher_event_init_ret\":" <<
    static_cast<int>(publisher_event_init_ret) << ",";
  std::cout << "\"subscription_event_init_ret\":" <<
    static_cast<int>(subscription_event_init_ret) << ",";
  std::cout << "\"publisher_callback_ret\":" <<
    static_cast<int>(publisher_callback_ret) << ",";
  std::cout << "\"subscription_callback_ret\":" <<
    static_cast<int>(subscription_callback_ret) << ",";
  std::cout << "\"publisher_take_ret\":" << static_cast<int>(publisher_take_ret) << ",";
  std::cout << "\"subscription_take_ret\":" << static_cast<int>(subscription_take_ret) << ",";
  std::cout << "\"publisher_taken\":" << (publisher_taken ? "true" : "false") << ",";
  std::cout << "\"subscription_taken\":" << (subscription_taken ? "true" : "false") << ",";
  std::cout << "\"events_initialized_delta\":" << events_init_delta << ",";
  std::cout << "\"events_finalized_delta\":" << events_fini_delta << ",";
  std::cout << "\"event_callbacks_set_delta\":" << callbacks_delta << ",";
  std::cout << "\"offered_deadline_supported\":" <<
    (offered_supported ? "true" : "false") << ",";
  std::cout << "\"requested_deadline_supported\":" <<
    (requested_supported ? "true" : "false") << ",";
  std::cout << "\"invalid_event_supported\":" << (invalid_supported ? "true" : "false") << ",";
  std::cout << "\"event_object_abi_ok\":" << (event_object_ok ? "true" : "false") << ",";
  std::cout << "\"event_production\":false}" << std::endl;
  return ok ? 0 : 1;
}

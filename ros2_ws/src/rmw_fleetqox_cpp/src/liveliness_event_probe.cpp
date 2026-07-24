#include <chrono>
#include <cstdint>
#include <iostream>
#include <thread>

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
  options.instance_id = 61;

  rmw_context_t context = rmw_get_zero_initialized_context();
  ret = rmw_init(&options, &context);
  if (ret != RMW_RET_OK) {
    const rmw_ret_t fini_ret = rmw_init_options_fini(&options);
    (void)fini_ret;
    std::cout << "{\"status\":\"init_failed\",\"ret\":" << ret << "}\n";
    return 1;
  }

  rmw_node_t * node =
    rmw_create_node(&context, "fleetqox_liveliness_event_probe", "/fleetqox");
  if (node == nullptr) {
    cleanup_context(&context, &options);
    std::cout << "{\"status\":\"create_node_failed\"}\n";
    return 1;
  }

  rosidl_message_type_support_t type_support{};
  type_support.typesupport_identifier = "rmw_fleetqox_cpp_liveliness_event_probe";
  rmw_qos_profile_t qos = rmw_qos_profile_default;
  qos.history = RMW_QOS_POLICY_HISTORY_KEEP_LAST;
  qos.depth = 1;
  qos.liveliness = RMW_QOS_POLICY_LIVELINESS_MANUAL_BY_TOPIC;
  qos.liveliness_lease_duration.sec = 0;
  qos.liveliness_lease_duration.nsec = 20000000;
  rmw_publisher_options_t publisher_options = rmw_get_default_publisher_options();
  rmw_subscription_options_t subscription_options = rmw_get_default_subscription_options();

  const bool liveliness_lost_supported =
    rmw_event_type_is_supported(RMW_EVENT_LIVELINESS_LOST);
  const bool liveliness_changed_supported =
    rmw_event_type_is_supported(RMW_EVENT_LIVELINESS_CHANGED);
  const std::uint64_t events_init_before = rmw_fleetqox_cpp_qos_events_initialized();
  const std::uint64_t events_fini_before = rmw_fleetqox_cpp_qos_events_finalized();
  const std::uint64_t callbacks_before = rmw_fleetqox_cpp_qos_event_callbacks_set();

  const char * topic = "/fleetqox/liveliness_event_probe";
  rmw_subscription_t * subscription =
    rmw_create_subscription(node, &type_support, topic, &qos, &subscription_options);
  rmw_event_t changed_event = rmw_get_zero_initialized_event();
  const rmw_ret_t changed_event_init_ret = subscription == nullptr ?
    RMW_RET_ERROR :
    rmw_subscription_event_init(&changed_event, subscription, RMW_EVENT_LIVELINESS_CHANGED);
  CallbackState changed_callback_state{0, 0};
  const rmw_ret_t changed_callback_ret =
    rmw_event_set_callback(&changed_event, event_callback, &changed_callback_state);

  bool initial_changed_ready = true;
  const rmw_ret_t initial_changed_wait_ret =
    wait_event_once(&context, &changed_event, &initial_changed_ready);
  rmw_liveliness_changed_status_t initial_changed_status{};
  bool initial_changed_taken = true;
  const rmw_ret_t initial_changed_take_ret =
    rmw_take_event(&changed_event, &initial_changed_status, &initial_changed_taken);

  rmw_publisher_t * publisher =
    rmw_create_publisher(node, &type_support, topic, &qos, &publisher_options);
  rmw_event_t lost_event = rmw_get_zero_initialized_event();
  const rmw_ret_t lost_event_init_ret = publisher == nullptr ?
    RMW_RET_ERROR :
    rmw_publisher_event_init(&lost_event, publisher, RMW_EVENT_LIVELINESS_LOST);
  CallbackState lost_callback_state{0, 0};
  const rmw_ret_t lost_callback_ret =
    rmw_event_set_callback(&lost_event, event_callback, &lost_callback_state);

  bool alive_ready = false;
  const rmw_ret_t alive_wait_ret = wait_event_once(&context, &changed_event, &alive_ready);
  rmw_liveliness_changed_status_t alive_status{};
  bool alive_taken = false;
  const rmw_ret_t alive_take_ret =
    rmw_take_event(&changed_event, &alive_status, &alive_taken);

  bool lost_initial_ready = true;
  const rmw_ret_t lost_initial_wait_ret =
    wait_event_once(&context, &lost_event, &lost_initial_ready);
  rmw_liveliness_lost_status_t lost_initial_status{};
  bool lost_initial_taken = true;
  const rmw_ret_t lost_initial_take_ret =
    rmw_take_event(&lost_event, &lost_initial_status, &lost_initial_taken);

  std::this_thread::sleep_for(std::chrono::milliseconds(80));

  bool lost_ready = false;
  const rmw_ret_t lost_wait_ret = wait_event_once(&context, &lost_event, &lost_ready);
  rmw_liveliness_lost_status_t lost_status{};
  bool lost_taken = false;
  const rmw_ret_t lost_take_ret = rmw_take_event(&lost_event, &lost_status, &lost_taken);

  bool not_alive_ready = false;
  const rmw_ret_t not_alive_wait_ret =
    wait_event_once(&context, &changed_event, &not_alive_ready);
  rmw_liveliness_changed_status_t not_alive_status{};
  bool not_alive_taken = false;
  const rmw_ret_t not_alive_take_ret =
    rmw_take_event(&changed_event, &not_alive_status, &not_alive_taken);

  const rmw_ret_t assert_ret =
    publisher == nullptr ? RMW_RET_ERROR : rmw_publisher_assert_liveliness(publisher);
  bool reassert_ready = false;
  const rmw_ret_t reassert_wait_ret =
    wait_event_once(&context, &changed_event, &reassert_ready);
  rmw_liveliness_changed_status_t reassert_status{};
  bool reassert_taken = false;
  const rmw_ret_t reassert_take_ret =
    rmw_take_event(&changed_event, &reassert_status, &reassert_taken);

  rmw_liveliness_lost_status_t lost_after_clear_status{};
  bool lost_after_clear_taken = true;
  const rmw_ret_t lost_after_clear_take_ret =
    rmw_take_event(&lost_event, &lost_after_clear_status, &lost_after_clear_taken);
  rmw_liveliness_changed_status_t changed_after_clear_status{};
  bool changed_after_clear_taken = true;
  const rmw_ret_t changed_after_clear_take_ret =
    rmw_take_event(&changed_event, &changed_after_clear_status, &changed_after_clear_taken);

  const rmw_ret_t lost_event_fini_ret = rmw_event_fini(&lost_event);
  const rmw_ret_t changed_event_fini_ret = rmw_event_fini(&changed_event);
  const rmw_ret_t destroy_publisher_ret =
    publisher == nullptr ? RMW_RET_ERROR : rmw_destroy_publisher(node, publisher);
  const rmw_ret_t destroy_subscription_ret =
    subscription == nullptr ? RMW_RET_ERROR : rmw_destroy_subscription(node, subscription);
  const rmw_ret_t destroy_node_ret = rmw_destroy_node(node);
  cleanup_context(&context, &options);

  const std::uint64_t events_init_delta =
    rmw_fleetqox_cpp_qos_events_initialized() - events_init_before;
  const std::uint64_t events_fini_delta =
    rmw_fleetqox_cpp_qos_events_finalized() - events_fini_before;
  const std::uint64_t callbacks_delta =
    rmw_fleetqox_cpp_qos_event_callbacks_set() - callbacks_before;

  const bool alive_ok =
    changed_event_init_ret == RMW_RET_OK &&
    changed_callback_ret == RMW_RET_OK &&
    initial_changed_wait_ret == RMW_RET_TIMEOUT &&
    !initial_changed_ready &&
    initial_changed_take_ret == RMW_RET_OK &&
    !initial_changed_taken &&
    alive_wait_ret == RMW_RET_OK &&
    alive_ready &&
    alive_take_ret == RMW_RET_OK &&
    alive_taken &&
    alive_status.alive_count == 1 &&
    alive_status.not_alive_count == 0 &&
    alive_status.alive_count_change == 1 &&
    alive_status.not_alive_count_change == 0;
  const bool lost_ok =
    lost_event_init_ret == RMW_RET_OK &&
    lost_callback_ret == RMW_RET_OK &&
    lost_initial_wait_ret == RMW_RET_TIMEOUT &&
    !lost_initial_ready &&
    lost_initial_take_ret == RMW_RET_OK &&
    !lost_initial_taken &&
    lost_wait_ret == RMW_RET_OK &&
    lost_ready &&
    lost_take_ret == RMW_RET_OK &&
    lost_taken &&
    lost_status.total_count == 1 &&
    lost_status.total_count_change == 1 &&
    lost_callback_state.calls >= 1 &&
    lost_callback_state.events >= 1;
  const bool not_alive_ok =
    not_alive_wait_ret == RMW_RET_OK &&
    not_alive_ready &&
    not_alive_take_ret == RMW_RET_OK &&
    not_alive_taken &&
    not_alive_status.alive_count == 0 &&
    not_alive_status.not_alive_count == 1 &&
    not_alive_status.alive_count_change == -1 &&
    not_alive_status.not_alive_count_change == 1;
  const bool reassert_ok =
    assert_ret == RMW_RET_OK &&
    reassert_wait_ret == RMW_RET_OK &&
    reassert_ready &&
    reassert_take_ret == RMW_RET_OK &&
    reassert_taken &&
    reassert_status.alive_count == 1 &&
    reassert_status.not_alive_count == 0 &&
    reassert_status.alive_count_change == 1 &&
    reassert_status.not_alive_count_change == -1 &&
    changed_callback_state.calls >= 3 &&
    changed_callback_state.events >= 3;
  const bool clear_ok =
    lost_after_clear_take_ret == RMW_RET_OK &&
    !lost_after_clear_taken &&
    lost_after_clear_status.total_count == lost_status.total_count &&
    lost_after_clear_status.total_count_change == 0 &&
    changed_after_clear_take_ret == RMW_RET_OK &&
    !changed_after_clear_taken &&
    changed_after_clear_status.alive_count == reassert_status.alive_count &&
    changed_after_clear_status.not_alive_count == reassert_status.not_alive_count &&
    changed_after_clear_status.alive_count_change == 0 &&
    changed_after_clear_status.not_alive_count_change == 0;
  const bool lifecycle_ok =
    events_init_delta == 2 &&
    events_fini_delta == 2 &&
    callbacks_delta == 2 &&
    lost_event_fini_ret == RMW_RET_OK &&
    changed_event_fini_ret == RMW_RET_OK &&
    destroy_publisher_ret == RMW_RET_OK &&
    destroy_subscription_ret == RMW_RET_OK &&
    destroy_node_ret == RMW_RET_OK;
  const bool ok =
    liveliness_lost_supported &&
    liveliness_changed_supported &&
    alive_ok &&
    lost_ok &&
    not_alive_ok &&
    reassert_ok &&
    clear_ok &&
    lifecycle_ok;

  std::cout << "{\"schema_version\":\"fleetrmw.liveliness_event_probe.v1\",";
  std::cout << "\"status\":\"" << (ok ? "ok" : "failed") << "\",";
  std::cout << "\"liveliness_lost_supported\":" <<
    (liveliness_lost_supported ? "true" : "false") << ",";
  std::cout << "\"liveliness_changed_supported\":" <<
    (liveliness_changed_supported ? "true" : "false") << ",";
  std::cout << "\"initial_changed_wait_ready\":" <<
    (initial_changed_ready ? "true" : "false") << ",";
  std::cout << "\"alive_wait_ready\":" << (alive_ready ? "true" : "false") << ",";
  std::cout << "\"lost_initial_wait_ready\":" <<
    (lost_initial_ready ? "true" : "false") << ",";
  std::cout << "\"lost_wait_ready\":" << (lost_ready ? "true" : "false") << ",";
  std::cout << "\"not_alive_wait_ready\":" <<
    (not_alive_ready ? "true" : "false") << ",";
  std::cout << "\"reassert_wait_ready\":" <<
    (reassert_ready ? "true" : "false") << ",";
  std::cout << "\"alive_taken\":" << (alive_taken ? "true" : "false") << ",";
  std::cout << "\"lost_taken\":" << (lost_taken ? "true" : "false") << ",";
  std::cout << "\"not_alive_taken\":" << (not_alive_taken ? "true" : "false") << ",";
  std::cout << "\"reassert_taken\":" << (reassert_taken ? "true" : "false") << ",";
  std::cout << "\"lost_total_count\":" << lost_status.total_count << ",";
  std::cout << "\"lost_total_count_change\":" << lost_status.total_count_change << ",";
  std::cout << "\"alive_count_after_loss\":" << not_alive_status.alive_count << ",";
  std::cout << "\"not_alive_count_after_loss\":" << not_alive_status.not_alive_count << ",";
  std::cout << "\"alive_count_after_reassert\":" << reassert_status.alive_count << ",";
  std::cout << "\"not_alive_count_after_reassert\":" << reassert_status.not_alive_count << ",";
  std::cout << "\"lost_callback_events\":" << lost_callback_state.events << ",";
  std::cout << "\"changed_callback_events\":" << changed_callback_state.events << ",";
  std::cout << "\"events_initialized_delta\":" << events_init_delta << ",";
  std::cout << "\"events_finalized_delta\":" << events_fini_delta << ",";
  std::cout << "\"event_callbacks_set_delta\":" << callbacks_delta << ",";
  std::cout << "\"liveliness_event_production\":true,";
  std::cout << "\"liveliness_event_scope\":\"local_same_process_finite_lease_timeout_and_reassert\"";
  std::cout << "}\n";
  return ok ? 0 : 1;
}

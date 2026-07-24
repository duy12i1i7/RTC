#include <atomic>
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

namespace
{

struct CallbackState
{
  std::atomic<std::uint64_t> calls{0};
  std::atomic<std::uint64_t> events{0};
};

void event_callback(const void * user_data, size_t number_of_events)
{
  auto * state = const_cast<CallbackState *>(
    static_cast<const CallbackState *>(user_data));
  if (state != nullptr) {
    state->calls.fetch_add(1, std::memory_order_relaxed);
    state->events.fetch_add(number_of_events, std::memory_order_relaxed);
  }
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
  rmw_time_t timeout{};
  void * handles[1] = {event};
  rmw_events_t events{1, handles};
  const rmw_ret_t wait_ret =
    rmw_wait(nullptr, nullptr, nullptr, nullptr, &events, wait_set, &timeout);
  *ready = handles[0] != nullptr;
  const rmw_ret_t destroy_ret = rmw_destroy_wait_set(wait_set);
  if (wait_ret != RMW_RET_OK && wait_ret != RMW_RET_TIMEOUT) {
    return wait_ret;
  }
  return destroy_ret == RMW_RET_OK ? wait_ret : destroy_ret;
}

bool cleanup_context(rmw_context_t * context, rmw_init_options_t * options)
{
  const rmw_ret_t shutdown_ret = rmw_shutdown(context);
  const rmw_ret_t context_ret = rmw_context_fini(context);
  const rmw_ret_t options_ret = rmw_init_options_fini(options);
  return shutdown_ret == RMW_RET_OK && context_ret == RMW_RET_OK &&
         options_ret == RMW_RET_OK;
}

}  // namespace

int main()
{
  constexpr int kLeaseMs = 20;
  constexpr int kIdleMs = 120;
  rcutils_allocator_t allocator = rcutils_get_default_allocator();
  rmw_init_options_t options = rmw_get_zero_initialized_init_options();
  if (rmw_init_options_init(&options, allocator) != RMW_RET_OK) {
    return 1;
  }
  options.instance_id = 63;
  rmw_context_t context = rmw_get_zero_initialized_context();
  if (rmw_init(&options, &context) != RMW_RET_OK) {
    const rmw_ret_t options_ret = rmw_init_options_fini(&options);
    return options_ret == RMW_RET_OK ? 1 : 2;
  }

  rmw_node_t * node =
    rmw_create_node(&context, "fleetqox_automatic_liveliness_probe", "/fleetqox");
  rosidl_message_type_support_t type_support{};
  type_support.typesupport_identifier = "rmw_fleetqox_cpp_automatic_liveliness_probe";
  rmw_qos_profile_t qos = rmw_qos_profile_default;
  qos.history = RMW_QOS_POLICY_HISTORY_KEEP_LAST;
  qos.depth = 1;
  qos.liveliness = RMW_QOS_POLICY_LIVELINESS_AUTOMATIC;
  qos.liveliness_lease_duration.sec = 0;
  qos.liveliness_lease_duration.nsec = kLeaseMs * 1000000u;
  const char * topic = "/fleetqox/automatic_liveliness_probe";
  rmw_subscription_options_t subscription_options = rmw_get_default_subscription_options();
  rmw_publisher_options_t publisher_options = rmw_get_default_publisher_options();
  rmw_subscription_t * subscription = node == nullptr ? nullptr :
    rmw_create_subscription(
    node, &type_support, topic, &qos, &subscription_options);
  rmw_event_t changed_event = rmw_get_zero_initialized_event();
  const rmw_ret_t changed_init_ret = subscription == nullptr ? RMW_RET_ERROR :
    rmw_subscription_event_init(
    &changed_event, subscription, RMW_EVENT_LIVELINESS_CHANGED);
  CallbackState changed_callback;
  const rmw_ret_t changed_callback_ret = changed_init_ret == RMW_RET_OK ?
    rmw_event_set_callback(&changed_event, event_callback, &changed_callback) : RMW_RET_ERROR;

  rmw_publisher_t * publisher = node == nullptr ? nullptr :
    rmw_create_publisher(node, &type_support, topic, &qos, &publisher_options);
  rmw_event_t lost_event = rmw_get_zero_initialized_event();
  const rmw_ret_t lost_init_ret = publisher == nullptr ? RMW_RET_ERROR :
    rmw_publisher_event_init(&lost_event, publisher, RMW_EVENT_LIVELINESS_LOST);
  CallbackState lost_callback;
  const rmw_ret_t lost_callback_ret = lost_init_ret == RMW_RET_OK ?
    rmw_event_set_callback(&lost_event, event_callback, &lost_callback) : RMW_RET_ERROR;

  bool alive_ready = false;
  const rmw_ret_t alive_wait_ret = changed_init_ret == RMW_RET_OK ?
    wait_event_once(&context, &changed_event, &alive_ready) : RMW_RET_ERROR;
  rmw_liveliness_changed_status_t alive_status{};
  bool alive_taken = false;
  const rmw_ret_t alive_take_ret = changed_init_ret == RMW_RET_OK ?
    rmw_take_event(&changed_event, &alive_status, &alive_taken) : RMW_RET_ERROR;

  bool initial_lost_ready = true;
  const rmw_ret_t initial_lost_wait_ret = lost_init_ret == RMW_RET_OK ?
    wait_event_once(&context, &lost_event, &initial_lost_ready) : RMW_RET_ERROR;
  rmw_liveliness_lost_status_t initial_lost_status{};
  bool initial_lost_taken = true;
  const rmw_ret_t initial_lost_take_ret = lost_init_ret == RMW_RET_OK ?
    rmw_take_event(&lost_event, &initial_lost_status, &initial_lost_taken) : RMW_RET_ERROR;

  std::this_thread::sleep_for(std::chrono::milliseconds(kIdleMs));

  bool idle_lost_ready = true;
  const rmw_ret_t idle_lost_wait_ret = lost_init_ret == RMW_RET_OK ?
    wait_event_once(&context, &lost_event, &idle_lost_ready) : RMW_RET_ERROR;
  rmw_liveliness_lost_status_t idle_lost_status{};
  bool idle_lost_taken = true;
  const rmw_ret_t idle_lost_take_ret = lost_init_ret == RMW_RET_OK ?
    rmw_take_event(&lost_event, &idle_lost_status, &idle_lost_taken) : RMW_RET_ERROR;

  bool idle_changed_ready = true;
  const rmw_ret_t idle_changed_wait_ret = changed_init_ret == RMW_RET_OK ?
    wait_event_once(&context, &changed_event, &idle_changed_ready) : RMW_RET_ERROR;
  rmw_liveliness_changed_status_t idle_changed_status{};
  bool idle_changed_taken = true;
  const rmw_ret_t idle_changed_take_ret = changed_init_ret == RMW_RET_OK ?
    rmw_take_event(
    &changed_event, &idle_changed_status, &idle_changed_taken) : RMW_RET_ERROR;

  bool teardown_ok = true;
  if (lost_init_ret == RMW_RET_OK) {
    teardown_ok = rmw_event_fini(&lost_event) == RMW_RET_OK && teardown_ok;
  }
  if (changed_init_ret == RMW_RET_OK) {
    teardown_ok = rmw_event_fini(&changed_event) == RMW_RET_OK && teardown_ok;
  }
  if (publisher != nullptr) {
    teardown_ok = rmw_destroy_publisher(node, publisher) == RMW_RET_OK && teardown_ok;
  }
  if (subscription != nullptr) {
    teardown_ok = rmw_destroy_subscription(node, subscription) == RMW_RET_OK && teardown_ok;
  }
  if (node != nullptr) {
    teardown_ok = rmw_destroy_node(node) == RMW_RET_OK && teardown_ok;
  }
  teardown_ok = cleanup_context(&context, &options) && teardown_ok;

  const bool ok =
    changed_init_ret == RMW_RET_OK && changed_callback_ret == RMW_RET_OK &&
    lost_init_ret == RMW_RET_OK && lost_callback_ret == RMW_RET_OK &&
    alive_wait_ret == RMW_RET_OK && alive_ready &&
    alive_take_ret == RMW_RET_OK && alive_taken &&
    alive_status.alive_count == 1 && alive_status.not_alive_count == 0 &&
    alive_status.alive_count_change == 1 && alive_status.not_alive_count_change == 0 &&
    initial_lost_wait_ret == RMW_RET_TIMEOUT && !initial_lost_ready &&
    initial_lost_take_ret == RMW_RET_OK && !initial_lost_taken &&
    initial_lost_status.total_count == 0 &&
    idle_lost_wait_ret == RMW_RET_TIMEOUT && !idle_lost_ready &&
    idle_lost_take_ret == RMW_RET_OK && !idle_lost_taken &&
    idle_lost_status.total_count == 0 && idle_lost_status.total_count_change == 0 &&
    idle_changed_wait_ret == RMW_RET_TIMEOUT && !idle_changed_ready &&
    idle_changed_take_ret == RMW_RET_OK && !idle_changed_taken &&
    idle_changed_status.alive_count == 1 && idle_changed_status.not_alive_count == 0 &&
    idle_changed_status.alive_count_change == 0 &&
    idle_changed_status.not_alive_count_change == 0 &&
    lost_callback.calls.load(std::memory_order_relaxed) == 0 &&
    lost_callback.events.load(std::memory_order_relaxed) == 0 &&
    changed_callback.calls.load(std::memory_order_relaxed) == 1 &&
    changed_callback.events.load(std::memory_order_relaxed) == 1 && teardown_ok;

  std::cout << "{\"schema_version\":\"fleetrmw.automatic_liveliness_probe.v1\",";
  std::cout << "\"status\":\"" << (ok ? "ok" : "failed") << "\",";
  std::cout << "\"automatic_idle_lease_renewal\":" << (ok ? "true" : "false") << ",";
  std::cout << "\"lease_ms\":" << kLeaseMs << ",";
  std::cout << "\"idle_ms\":" << kIdleMs << ",";
  std::cout << "\"idle_lease_multiples\":" << (kIdleMs / kLeaseMs) << ",";
  std::cout << "\"alive_count\":" << idle_changed_status.alive_count << ",";
  std::cout << "\"not_alive_count\":" << idle_changed_status.not_alive_count << ",";
  std::cout << "\"liveliness_lost_total_count\":" << idle_lost_status.total_count << ",";
  std::cout << "\"idle_lost_wait_ready\":" << (idle_lost_ready ? "true" : "false") << ",";
  std::cout << "\"idle_changed_wait_ready\":" <<
    (idle_changed_ready ? "true" : "false") << ",";
  std::cout << "\"lost_callback_events\":" <<
    lost_callback.events.load(std::memory_order_relaxed) << ",";
  std::cout << "\"changed_callback_events\":" <<
    changed_callback.events.load(std::memory_order_relaxed) << ",";
  std::cout << "\"clean_teardown\":" << (teardown_ok ? "true" : "false") << "}\n";
  return ok ? 0 : 1;
}

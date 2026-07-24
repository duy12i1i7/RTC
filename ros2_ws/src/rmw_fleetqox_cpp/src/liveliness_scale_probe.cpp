#include <atomic>
#include <chrono>
#include <cstdint>
#include <iostream>
#include <thread>
#include <vector>

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

constexpr size_t kManualPublisherCount = 64;
constexpr size_t kKeptAliveCount = 32;
constexpr size_t kSystemDefaultPublisherCount = 16;

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

template<typename StatusT>
bool wait_take_event(
  rmw_context_t * context,
  rmw_event_t * event,
  StatusT * status,
  int timeout_ms)
{
  rmw_wait_set_t * wait_set = rmw_create_wait_set(context, 1);
  if (wait_set == nullptr) {
    return false;
  }
  const auto deadline =
    std::chrono::steady_clock::now() + std::chrono::milliseconds(timeout_ms);
  bool taken = false;
  bool ok = false;
  while (std::chrono::steady_clock::now() < deadline) {
    void * handles[1] = {event};
    rmw_events_t events{1, handles};
    rmw_time_t timeout{};
    timeout.sec = 0;
    timeout.nsec = 20000000;
    const rmw_ret_t wait_ret =
      rmw_wait(nullptr, nullptr, nullptr, nullptr, &events, wait_set, &timeout);
    if (wait_ret == RMW_RET_OK && handles[0] != nullptr) {
      ok = rmw_take_event(event, status, &taken) == RMW_RET_OK && taken;
      break;
    }
    if (wait_ret != RMW_RET_TIMEOUT) {
      break;
    }
  }
  const rmw_ret_t destroy_ret = rmw_destroy_wait_set(wait_set);
  return ok && destroy_ret == RMW_RET_OK;
}

bool event_not_ready(rmw_context_t * context, rmw_event_t * event, int timeout_ms)
{
  rmw_wait_set_t * wait_set = rmw_create_wait_set(context, 1);
  if (wait_set == nullptr) {
    return false;
  }
  void * handles[1] = {event};
  rmw_events_t events{1, handles};
  rmw_time_t timeout{};
  timeout.sec = static_cast<std::uint64_t>(timeout_ms / 1000);
  timeout.nsec = static_cast<std::uint64_t>(timeout_ms % 1000) * 1000000u;
  const rmw_ret_t wait_ret =
    rmw_wait(nullptr, nullptr, nullptr, nullptr, &events, wait_set, &timeout);
  const bool not_ready = wait_ret == RMW_RET_TIMEOUT && handles[0] == nullptr;
  const rmw_ret_t destroy_ret = rmw_destroy_wait_set(wait_set);
  return not_ready && destroy_ret == RMW_RET_OK;
}

rmw_qos_profile_t liveliness_qos(
  rmw_qos_liveliness_policy_t policy,
  std::uint64_t lease_ms)
{
  rmw_qos_profile_t qos = rmw_qos_profile_default;
  qos.history = RMW_QOS_POLICY_HISTORY_KEEP_LAST;
  qos.depth = 8;
  qos.reliability = RMW_QOS_POLICY_RELIABILITY_BEST_EFFORT;
  qos.liveliness = policy;
  qos.liveliness_lease_duration.sec = lease_ms / 1000u;
  qos.liveliness_lease_duration.nsec = (lease_ms % 1000u) * 1000000u;
  return qos;
}

bool liveliness_status_is(
  const rmw_liveliness_changed_status_t & status,
  std::int32_t alive,
  std::int32_t not_alive,
  std::int32_t alive_change,
  std::int32_t not_alive_change)
{
  return status.alive_count == alive && status.not_alive_count == not_alive &&
         status.alive_count_change == alive_change &&
         status.not_alive_count_change == not_alive_change;
}

}  // namespace

int main()
{
  rcutils_allocator_t allocator = rcutils_get_default_allocator();
  rmw_init_options_t options = rmw_get_zero_initialized_init_options();
  if (rmw_init_options_init(&options, allocator) != RMW_RET_OK) {
    return 1;
  }
  options.instance_id = 825;
  rmw_context_t context = rmw_get_zero_initialized_context();
  if (rmw_init(&options, &context) != RMW_RET_OK) {
    const rmw_ret_t options_ret = rmw_init_options_fini(&options);
    return options_ret == RMW_RET_OK ? 1 : 2;
  }
  rmw_node_t * node = rmw_create_node(&context, "liveliness_scale_probe", "/fleetqox");
  rosidl_message_type_support_t type_support{};
  type_support.typesupport_identifier = "fleetrmw_liveliness_scale_type";
  const rmw_publisher_options_t publisher_options = rmw_get_default_publisher_options();
  const rmw_subscription_options_t subscription_options =
    rmw_get_default_subscription_options();

  const rmw_qos_profile_t manual_qos = liveliness_qos(
    RMW_QOS_POLICY_LIVELINESS_MANUAL_BY_TOPIC, 200);
  const char * manual_topic = "/fleetqox/liveliness_scale_manual";
  rmw_subscription_t * manual_subscription = node == nullptr ? nullptr :
    rmw_create_subscription(
    node, &type_support, manual_topic, &manual_qos, &subscription_options);
  rmw_event_t manual_changed_event = rmw_get_zero_initialized_event();
  rmw_event_t manual_matched_event = rmw_get_zero_initialized_event();
  bool manual_initialized = manual_subscription != nullptr &&
    rmw_subscription_event_init(
    &manual_changed_event,
    manual_subscription,
    RMW_EVENT_LIVELINESS_CHANGED) == RMW_RET_OK &&
    rmw_subscription_event_init(
    &manual_matched_event,
    manual_subscription,
    RMW_EVENT_SUBSCRIPTION_MATCHED) == RMW_RET_OK;
  CallbackState manual_callback;
  manual_initialized = manual_initialized &&
    rmw_event_set_callback(
    &manual_changed_event, event_callback, &manual_callback) == RMW_RET_OK;

  std::vector<rmw_publisher_t *> manual_publishers;
  manual_publishers.reserve(kManualPublisherCount);
  for (size_t index = 0; index < kManualPublisherCount && manual_initialized; ++index) {
    rmw_publisher_t * publisher = rmw_create_publisher(
      node, &type_support, manual_topic, &manual_qos, &publisher_options);
    if (publisher == nullptr) {
      manual_initialized = false;
      break;
    }
    manual_publishers.push_back(publisher);
  }

  rmw_liveliness_changed_status_t all_connected{};
  rmw_matched_status_t all_matched{};
  const bool all_connected_taken = manual_initialized &&
    wait_take_event(&context, &manual_changed_event, &all_connected, 2000);
  const bool all_matched_taken = manual_initialized &&
    wait_take_event(&context, &manual_matched_event, &all_matched, 2000);

  std::atomic<bool> keepalive_running{true};
  std::atomic<bool> keepalive_ok{true};
  std::atomic<std::uint64_t> keepalive_assertions{0};
  std::thread keepalive_thread([&]() {
      while (keepalive_running.load(std::memory_order_relaxed)) {
        for (size_t index = 0;
          index < kKeptAliveCount && index < manual_publishers.size(); ++index)
        {
          if (rmw_publisher_assert_liveliness(manual_publishers[index]) != RMW_RET_OK) {
            keepalive_ok.store(false, std::memory_order_relaxed);
          } else {
            keepalive_assertions.fetch_add(1, std::memory_order_relaxed);
          }
        }
        std::this_thread::sleep_for(std::chrono::milliseconds(50));
      }
    });
  std::this_thread::sleep_for(std::chrono::milliseconds(350));

  rmw_liveliness_changed_status_t half_expired{};
  const bool half_expired_taken = manual_initialized &&
    wait_take_event(&context, &manual_changed_event, &half_expired, 2000);
  bool reassert_ok = true;
  for (size_t index = kKeptAliveCount; index < manual_publishers.size(); ++index) {
    reassert_ok =
      rmw_publisher_assert_liveliness(manual_publishers[index]) == RMW_RET_OK && reassert_ok;
  }
  rmw_liveliness_changed_status_t all_reasserted{};
  const bool all_reasserted_taken = manual_initialized &&
    wait_take_event(&context, &manual_changed_event, &all_reasserted, 2000);

  keepalive_running.store(false, std::memory_order_relaxed);
  keepalive_thread.join();
  std::this_thread::sleep_for(std::chrono::milliseconds(350));
  rmw_liveliness_changed_status_t all_expired{};
  const bool all_expired_taken = manual_initialized &&
    wait_take_event(&context, &manual_changed_event, &all_expired, 2000);

  bool manual_publishers_destroyed = true;
  for (rmw_publisher_t * publisher : manual_publishers) {
    manual_publishers_destroyed =
      rmw_destroy_publisher(node, publisher) == RMW_RET_OK && manual_publishers_destroyed;
  }
  rmw_liveliness_changed_status_t all_removed{};
  rmw_matched_status_t all_unmatched{};
  const bool all_removed_taken = manual_initialized &&
    wait_take_event(&context, &manual_changed_event, &all_removed, 2000);
  const bool all_unmatched_taken = manual_initialized &&
    wait_take_event(&context, &manual_matched_event, &all_unmatched, 2000);

  const bool manual_scale_ok =
    manual_publishers.size() == kManualPublisherCount &&
    all_connected_taken && liveliness_status_is(all_connected, 64, 0, 64, 0) &&
    all_matched_taken && all_matched.current_count == 64 &&
    all_matched.current_count_change == 64 &&
    half_expired_taken && liveliness_status_is(half_expired, 32, 32, -32, 32) &&
    reassert_ok && all_reasserted_taken &&
    liveliness_status_is(all_reasserted, 64, 0, 32, -32) &&
    keepalive_ok.load(std::memory_order_relaxed) &&
    keepalive_assertions.load(std::memory_order_relaxed) >= 128 &&
    all_expired_taken && liveliness_status_is(all_expired, 0, 64, -64, 64) &&
    manual_publishers_destroyed && all_removed_taken &&
    liveliness_status_is(all_removed, 0, 0, 0, -64) &&
    all_unmatched_taken && all_unmatched.current_count == 0 &&
    all_unmatched.current_count_change == -64;

  const rmw_qos_profile_t system_qos = liveliness_qos(
    RMW_QOS_POLICY_LIVELINESS_SYSTEM_DEFAULT, 20);
  const char * system_topic = "/fleetqox/liveliness_scale_system_default";
  rmw_subscription_t * system_subscription = node == nullptr ? nullptr :
    rmw_create_subscription(
    node, &type_support, system_topic, &system_qos, &subscription_options);
  rmw_event_t system_changed_event = rmw_get_zero_initialized_event();
  bool system_initialized = system_subscription != nullptr &&
    rmw_subscription_event_init(
    &system_changed_event,
    system_subscription,
    RMW_EVENT_LIVELINESS_CHANGED) == RMW_RET_OK;
  std::vector<rmw_publisher_t *> system_publishers;
  system_publishers.reserve(kSystemDefaultPublisherCount);
  for (size_t index = 0; index < kSystemDefaultPublisherCount && system_initialized; ++index) {
    rmw_publisher_t * publisher = rmw_create_publisher(
      node, &type_support, system_topic, &system_qos, &publisher_options);
    if (publisher == nullptr) {
      system_initialized = false;
      break;
    }
    system_publishers.push_back(publisher);
  }
  rmw_liveliness_changed_status_t system_connected{};
  const bool system_connected_taken = system_initialized &&
    wait_take_event(&context, &system_changed_event, &system_connected, 2000);
  std::this_thread::sleep_for(std::chrono::milliseconds(120));
  const bool system_idle_quiet = system_initialized &&
    event_not_ready(&context, &system_changed_event, 0);
  rmw_liveliness_changed_status_t system_idle{};
  bool system_idle_taken = true;
  const rmw_ret_t system_idle_take_ret = system_initialized ?
    rmw_take_event(&system_changed_event, &system_idle, &system_idle_taken) : RMW_RET_ERROR;
  bool system_publishers_destroyed = true;
  for (rmw_publisher_t * publisher : system_publishers) {
    system_publishers_destroyed =
      rmw_destroy_publisher(node, publisher) == RMW_RET_OK && system_publishers_destroyed;
  }
  rmw_liveliness_changed_status_t system_removed{};
  const bool system_removed_taken = system_initialized &&
    wait_take_event(&context, &system_changed_event, &system_removed, 2000);
  const bool system_default_ok =
    system_publishers.size() == kSystemDefaultPublisherCount &&
    system_connected_taken && liveliness_status_is(system_connected, 16, 0, 16, 0) &&
    system_idle_quiet && system_idle_take_ret == RMW_RET_OK && !system_idle_taken &&
    liveliness_status_is(system_idle, 16, 0, 0, 0) &&
    system_publishers_destroyed && system_removed_taken &&
    liveliness_status_is(system_removed, 0, 0, -16, 0);

  bool teardown_ok = true;
  if (manual_initialized) {
    teardown_ok = rmw_event_fini(&manual_matched_event) == RMW_RET_OK && teardown_ok;
    teardown_ok = rmw_event_fini(&manual_changed_event) == RMW_RET_OK && teardown_ok;
  }
  if (system_initialized) {
    teardown_ok = rmw_event_fini(&system_changed_event) == RMW_RET_OK && teardown_ok;
  }
  if (manual_subscription != nullptr) {
    teardown_ok =
      rmw_destroy_subscription(node, manual_subscription) == RMW_RET_OK && teardown_ok;
  }
  if (system_subscription != nullptr) {
    teardown_ok =
      rmw_destroy_subscription(node, system_subscription) == RMW_RET_OK && teardown_ok;
  }
  if (node != nullptr) {
    teardown_ok = rmw_destroy_node(node) == RMW_RET_OK && teardown_ok;
  }
  const rmw_ret_t shutdown_ret = rmw_shutdown(&context);
  const rmw_ret_t context_ret = rmw_context_fini(&context);
  const rmw_ret_t options_ret = rmw_init_options_fini(&options);
  teardown_ok = shutdown_ret == RMW_RET_OK && context_ret == RMW_RET_OK &&
    options_ret == RMW_RET_OK && teardown_ok;
  const bool ok = manual_initialized && manual_scale_ok && system_initialized &&
    system_default_ok && manual_callback.calls.load(std::memory_order_relaxed) > 0 &&
    teardown_ok;

  std::cout << "{\"schema_version\":\"fleetrmw.liveliness_scale_probe.v1\","
            << "\"status\":\"" << (ok ? "ok" : "failed") << "\","
            << "\"manual_multi_endpoint_scale_claim\":"
            << (manual_scale_ok ? "true" : "false") << ","
            << "\"system_default_automatic_renewal_claim\":"
            << (system_default_ok ? "true" : "false") << ","
            << "\"manual_publisher_count\":" << kManualPublisherCount << ","
            << "\"kept_alive_publisher_count\":" << kKeptAliveCount << ","
            << "\"half_expired_alive_count\":" << half_expired.alive_count << ","
            << "\"half_expired_not_alive_count\":" << half_expired.not_alive_count << ","
            << "\"all_expired_not_alive_count\":" << all_expired.not_alive_count << ","
            << "\"system_default_publisher_count\":"
            << kSystemDefaultPublisherCount << ","
            << "\"system_default_idle_lease_multiples\":6,"
            << "\"system_default_idle_alive_count\":" << system_idle.alive_count << ","
            << "\"keepalive_assertions\":"
            << keepalive_assertions.load(std::memory_order_relaxed) << ","
            << "\"callback_events\":"
            << manual_callback.events.load(std::memory_order_relaxed) << ","
            << "\"clean_teardown\":" << (teardown_ok ? "true" : "false") << "}"
            << std::endl;
  return ok ? 0 : 1;
}

#include <atomic>
#include <chrono>
#include <cstdint>
#include <iostream>
#include <string>
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

extern "C" std::uint64_t rmw_fleetqox_cpp_remote_manual_liveliness_assertions_received();
extern "C" std::uint64_t rmw_fleetqox_cpp_remote_manual_liveliness_expiries();
extern "C" std::uint64_t rmw_fleetqox_cpp_remote_manual_liveliness_reassertions();

namespace
{

constexpr const char * kTopic = "/fleetqox/remote_liveliness_scale";
constexpr size_t kPublisherCount = 64;
constexpr size_t kKeptAliveCount = 32;
constexpr std::uint64_t kLeaseMs = 1000;

struct CallbackState
{
  std::atomic<std::uint64_t> calls{0};
  std::atomic<std::uint64_t> events{0};
};

struct LivelinessTransition
{
  rmw_liveliness_changed_status_t status{};
  std::int64_t alive_change_sum{0};
  std::int64_t not_alive_change_sum{0};
  size_t take_count{0};
};

struct MatchedTransition
{
  rmw_matched_status_t status{};
  std::int64_t current_change_sum{0};
  size_t take_count{0};
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

rmw_qos_profile_t manual_qos()
{
  rmw_qos_profile_t qos = rmw_qos_profile_default;
  qos.history = RMW_QOS_POLICY_HISTORY_KEEP_LAST;
  qos.depth = 8;
  qos.reliability = RMW_QOS_POLICY_RELIABILITY_BEST_EFFORT;
  qos.liveliness = RMW_QOS_POLICY_LIVELINESS_MANUAL_BY_TOPIC;
  qos.liveliness_lease_duration.sec = kLeaseMs / 1000u;
  qos.liveliness_lease_duration.nsec = (kLeaseMs % 1000u) * 1000000u;
  return qos;
}

bool init_context(
  rcutils_allocator_t allocator,
  std::uint64_t instance_id,
  rmw_init_options_t * options,
  rmw_context_t * context)
{
  if (options == nullptr || context == nullptr) {
    return false;
  }
  *options = rmw_get_zero_initialized_init_options();
  if (rmw_init_options_init(options, allocator) != RMW_RET_OK) {
    return false;
  }
  options->instance_id = instance_id;
  *context = rmw_get_zero_initialized_context();
  if (rmw_init(options, context) != RMW_RET_OK) {
    const rmw_ret_t fini_ret = rmw_init_options_fini(options);
    (void)fini_ret;
    return false;
  }
  return true;
}

bool fini_context(rmw_context_t * context, rmw_init_options_t * options)
{
  const rmw_ret_t shutdown_ret = rmw_shutdown(context);
  const rmw_ret_t context_ret = rmw_context_fini(context);
  const rmw_ret_t options_ret = rmw_init_options_fini(options);
  return shutdown_ret == RMW_RET_OK && context_ret == RMW_RET_OK &&
         options_ret == RMW_RET_OK;
}

bool wait_liveliness_state(
  rmw_context_t * context,
  rmw_event_t * event,
  std::int32_t expected_alive,
  std::int32_t expected_not_alive,
  int timeout_ms,
  LivelinessTransition * transition)
{
  if (context == nullptr || event == nullptr || transition == nullptr) {
    return false;
  }
  rmw_wait_set_t * wait_set = rmw_create_wait_set(context, 1);
  if (wait_set == nullptr) {
    return false;
  }
  const auto deadline =
    std::chrono::steady_clock::now() + std::chrono::milliseconds(timeout_ms);
  bool reached = false;
  while (std::chrono::steady_clock::now() < deadline) {
    void * handles[1] = {event};
    rmw_events_t events{1, handles};
    rmw_time_t timeout{};
    timeout.sec = 0;
    timeout.nsec = 50000000;
    const rmw_ret_t wait_ret =
      rmw_wait(nullptr, nullptr, nullptr, nullptr, &events, wait_set, &timeout);
    if (wait_ret == RMW_RET_TIMEOUT) {
      continue;
    }
    if (wait_ret != RMW_RET_OK || handles[0] == nullptr) {
      break;
    }
    rmw_liveliness_changed_status_t status{};
    bool taken = false;
    if (rmw_take_event(event, &status, &taken) != RMW_RET_OK || !taken) {
      break;
    }
    transition->status = status;
    transition->alive_change_sum += status.alive_count_change;
    transition->not_alive_change_sum += status.not_alive_count_change;
    ++transition->take_count;
    if (status.alive_count == expected_alive &&
      status.not_alive_count == expected_not_alive)
    {
      reached = true;
      break;
    }
  }
  const rmw_ret_t destroy_ret = rmw_destroy_wait_set(wait_set);
  return reached && destroy_ret == RMW_RET_OK;
}

bool wait_matched_state(
  rmw_context_t * context,
  rmw_event_t * event,
  size_t expected_current,
  int timeout_ms,
  MatchedTransition * transition)
{
  if (context == nullptr || event == nullptr || transition == nullptr) {
    return false;
  }
  rmw_wait_set_t * wait_set = rmw_create_wait_set(context, 1);
  if (wait_set == nullptr) {
    return false;
  }
  const auto deadline =
    std::chrono::steady_clock::now() + std::chrono::milliseconds(timeout_ms);
  bool reached = false;
  while (std::chrono::steady_clock::now() < deadline) {
    void * handles[1] = {event};
    rmw_events_t events{1, handles};
    rmw_time_t timeout{};
    timeout.sec = 0;
    timeout.nsec = 50000000;
    const rmw_ret_t wait_ret =
      rmw_wait(nullptr, nullptr, nullptr, nullptr, &events, wait_set, &timeout);
    if (wait_ret == RMW_RET_TIMEOUT) {
      continue;
    }
    if (wait_ret != RMW_RET_OK || handles[0] == nullptr) {
      break;
    }
    rmw_matched_status_t status{};
    bool taken = false;
    if (rmw_take_event(event, &status, &taken) != RMW_RET_OK || !taken) {
      break;
    }
    transition->status = status;
    transition->current_change_sum += status.current_count_change;
    ++transition->take_count;
    if (status.current_count == expected_current) {
      reached = true;
      break;
    }
  }
  const rmw_ret_t destroy_ret = rmw_destroy_wait_set(wait_set);
  return reached && destroy_ret == RMW_RET_OK;
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

int run_advertiser()
{
  rcutils_allocator_t allocator = rcutils_get_default_allocator();
  rmw_init_options_t options{};
  rmw_context_t context{};
  if (!init_context(allocator, 826, &options, &context)) {
    std::cout << "{\"status\":\"init_failed\"}\n";
    return 1;
  }
  rmw_node_t * node =
    rmw_create_node(&context, "remote_liveliness_scale_advertiser", "/fleetqox");
  rosidl_message_type_support_t type_support{};
  type_support.typesupport_identifier = "fleetrmw_remote_liveliness_scale_type";
  const rmw_qos_profile_t qos = manual_qos();
  const rmw_publisher_options_t publisher_options = rmw_get_default_publisher_options();
  std::vector<rmw_publisher_t *> publishers;
  publishers.reserve(kPublisherCount);
  for (size_t index = 0; index < kPublisherCount && node != nullptr; ++index) {
    rmw_publisher_t * publisher = rmw_create_publisher(
      node, &type_support, kTopic, &qos, &publisher_options);
    if (publisher == nullptr) {
      break;
    }
    publishers.push_back(publisher);
  }

  std::atomic<bool> keepalive_running{publishers.size() == kPublisherCount};
  std::atomic<bool> keepalive_ok{true};
  std::atomic<std::uint64_t> keepalive_assertions{0};
  std::thread keepalive_thread([&]() {
      while (keepalive_running.load(std::memory_order_relaxed)) {
        for (size_t index = 0; index < kKeptAliveCount; ++index) {
          if (rmw_publisher_assert_liveliness(publishers[index]) != RMW_RET_OK) {
            keepalive_ok.store(false, std::memory_order_relaxed);
          } else {
            keepalive_assertions.fetch_add(1, std::memory_order_relaxed);
          }
        }
        std::this_thread::sleep_for(std::chrono::milliseconds(100));
      }
    });
  std::this_thread::sleep_for(std::chrono::milliseconds(1600));

  bool second_half_reasserted = publishers.size() == kPublisherCount;
  for (size_t index = kKeptAliveCount; index < publishers.size(); ++index) {
    second_half_reasserted =
      rmw_publisher_assert_liveliness(publishers[index]) == RMW_RET_OK &&
      second_half_reasserted;
  }
  std::this_thread::sleep_for(std::chrono::milliseconds(300));
  keepalive_running.store(false, std::memory_order_relaxed);
  keepalive_thread.join();
  std::this_thread::sleep_for(std::chrono::milliseconds(1300));

  bool publishers_destroyed = true;
  for (rmw_publisher_t * publisher : publishers) {
    publishers_destroyed =
      rmw_destroy_publisher(node, publisher) == RMW_RET_OK && publishers_destroyed;
  }
  const rmw_ret_t node_ret = node == nullptr ? RMW_RET_ERROR : rmw_destroy_node(node);
  const bool context_ok = fini_context(&context, &options);
  const bool ok = publishers.size() == kPublisherCount &&
    second_half_reasserted && keepalive_ok.load(std::memory_order_relaxed) &&
    keepalive_assertions.load(std::memory_order_relaxed) >= 480 &&
    publishers_destroyed && node_ret == RMW_RET_OK && context_ok;
  std::cout <<
    "{\"schema_version\":\"fleetrmw.remote_liveliness_scale_probe.v1\","
            << "\"mode\":\"advertiser\",\"status\":\""
            << (ok ? "ok" : "failed") << "\","
            << "\"publisher_count\":" << publishers.size() << ","
            << "\"kept_alive_publisher_count\":" << kKeptAliveCount << ","
            << "\"keepalive_assertions\":"
            << keepalive_assertions.load(std::memory_order_relaxed) << ","
            << "\"keepalive_ok\":"
            << (keepalive_ok.load(std::memory_order_relaxed) ? "true" : "false") << ","
            << "\"second_half_reasserted\":"
            << (second_half_reasserted ? "true" : "false") << ","
            << "\"clean_teardown\":" << (ok ? "true" : "false") << "}"
            << std::endl;
  return ok ? 0 : 1;
}

int run_observer()
{
  rcutils_allocator_t allocator = rcutils_get_default_allocator();
  rmw_init_options_t options{};
  rmw_context_t context{};
  if (!init_context(allocator, 827, &options, &context)) {
    std::cout << "{\"status\":\"init_failed\"}\n";
    return 1;
  }
  rmw_node_t * node =
    rmw_create_node(&context, "remote_liveliness_scale_observer", "/fleetqox");
  rosidl_message_type_support_t type_support{};
  type_support.typesupport_identifier = "fleetrmw_remote_liveliness_scale_type";
  const rmw_qos_profile_t qos = manual_qos();
  const rmw_subscription_options_t subscription_options =
    rmw_get_default_subscription_options();
  rmw_subscription_t * subscription = node == nullptr ? nullptr :
    rmw_create_subscription(
    node, &type_support, kTopic, &qos, &subscription_options);
  rmw_event_t liveliness_event = rmw_get_zero_initialized_event();
  rmw_event_t matched_event = rmw_get_zero_initialized_event();
  const bool liveliness_initialized = subscription != nullptr &&
    rmw_subscription_event_init(
    &liveliness_event, subscription, RMW_EVENT_LIVELINESS_CHANGED) == RMW_RET_OK;
  const bool matched_initialized = subscription != nullptr &&
    rmw_subscription_event_init(
    &matched_event, subscription, RMW_EVENT_SUBSCRIPTION_MATCHED) == RMW_RET_OK;
  CallbackState callback_state;
  const bool callback_initialized = liveliness_initialized &&
    rmw_event_set_callback(
    &liveliness_event, event_callback, &callback_state) == RMW_RET_OK;
  const bool initialized = liveliness_initialized && matched_initialized && callback_initialized;
  const std::uint64_t assertions_before =
    rmw_fleetqox_cpp_remote_manual_liveliness_assertions_received();
  const std::uint64_t expiries_before =
    rmw_fleetqox_cpp_remote_manual_liveliness_expiries();
  const std::uint64_t reassertions_before =
    rmw_fleetqox_cpp_remote_manual_liveliness_reassertions();
  std::cout <<
    "{\"schema_version\":\"fleetrmw.remote_liveliness_scale_probe.v1\","
    "\"mode\":\"observer\",\"phase\":\"ready\",\"initialized\":"
            << (initialized ? "true" : "false") << "}" << std::endl;

  LivelinessTransition connected{};
  MatchedTransition matched{};
  LivelinessTransition half_expired{};
  LivelinessTransition reasserted{};
  LivelinessTransition all_expired{};
  LivelinessTransition removed{};
  MatchedTransition unmatched{};
  const bool connected_taken = initialized && wait_liveliness_state(
    &context, &liveliness_event, 64, 0, 7000, &connected);
  const bool matched_taken = initialized && wait_matched_state(
    &context, &matched_event, 64, 7000, &matched);
  const bool half_expired_taken = initialized && wait_liveliness_state(
    &context, &liveliness_event, 32, 32, 7000, &half_expired);
  size_t publishers_during_half_expiry = 0;
  const bool publishers_during_half_expiry_ok = node != nullptr &&
    rmw_count_publishers(node, kTopic, &publishers_during_half_expiry) == RMW_RET_OK;
  const bool matching_quiet_during_expiry = initialized &&
    event_not_ready(&context, &matched_event, 100);
  const bool reasserted_taken = initialized && wait_liveliness_state(
    &context, &liveliness_event, 64, 0, 7000, &reasserted);
  const bool all_expired_taken = initialized && wait_liveliness_state(
    &context, &liveliness_event, 0, 64, 7000, &all_expired);
  const bool removed_taken = initialized && wait_liveliness_state(
    &context, &liveliness_event, 0, 0, 7000, &removed);
  const bool unmatched_taken = initialized && wait_matched_state(
    &context, &matched_event, 0, 7000, &unmatched);
  size_t publishers_after_remove = 99;
  const bool publishers_after_remove_ok = node != nullptr &&
    rmw_count_publishers(node, kTopic, &publishers_after_remove) == RMW_RET_OK;

  const std::uint64_t assertions =
    rmw_fleetqox_cpp_remote_manual_liveliness_assertions_received() - assertions_before;
  const std::uint64_t expiries =
    rmw_fleetqox_cpp_remote_manual_liveliness_expiries() - expiries_before;
  const std::uint64_t reassertions =
    rmw_fleetqox_cpp_remote_manual_liveliness_reassertions() - reassertions_before;
  const bool transition_counts_ok =
    connected.alive_change_sum == 64 && connected.not_alive_change_sum == 0 &&
    half_expired.alive_change_sum == -32 &&
    half_expired.not_alive_change_sum == 32 &&
    reasserted.alive_change_sum == 32 && reasserted.not_alive_change_sum == -32 &&
    all_expired.alive_change_sum == -64 &&
    all_expired.not_alive_change_sum == 64 &&
    removed.alive_change_sum == 0 && removed.not_alive_change_sum == -64 &&
    matched.current_change_sum == 64 && unmatched.current_change_sum == -64;
  const bool scale_ok = connected_taken && matched_taken && half_expired_taken &&
    reasserted_taken && all_expired_taken && removed_taken && unmatched_taken &&
    transition_counts_ok && publishers_during_half_expiry_ok &&
    publishers_during_half_expiry == 64 && matching_quiet_during_expiry &&
    publishers_after_remove_ok && publishers_after_remove == 0 &&
    assertions >= 320 && expiries == 96 && reassertions == 32 &&
    callback_state.events.load(std::memory_order_relaxed) > 0;

  bool teardown_ok = true;
  if (matched_initialized) {
    teardown_ok = rmw_event_fini(&matched_event) == RMW_RET_OK && teardown_ok;
  }
  if (liveliness_initialized) {
    teardown_ok = rmw_event_fini(&liveliness_event) == RMW_RET_OK && teardown_ok;
  }
  if (subscription != nullptr) {
    teardown_ok =
      rmw_destroy_subscription(node, subscription) == RMW_RET_OK && teardown_ok;
  }
  if (node != nullptr) {
    teardown_ok = rmw_destroy_node(node) == RMW_RET_OK && teardown_ok;
  }
  teardown_ok = fini_context(&context, &options) && teardown_ok;
  const bool ok = initialized && scale_ok && teardown_ok;
  std::cout <<
    "{\"schema_version\":\"fleetrmw.remote_liveliness_scale_probe.v1\","
            << "\"mode\":\"observer\",\"status\":\""
            << (ok ? "ok" : "failed") << "\","
            << "\"remote_manual_64_endpoint_scale_claim\":"
            << (scale_ok ? "true" : "false") << ","
            << "\"exact_aggregate_transition_claim\":"
            << (transition_counts_ok ? "true" : "false") << ","
            << "\"expiry_preserves_matching_claim\":"
            << (matching_quiet_during_expiry ? "true" : "false") << ","
            << "\"publisher_count\":" << kPublisherCount << ","
            << "\"kept_alive_publisher_count\":" << kKeptAliveCount << ","
            << "\"publishers_during_half_expiry\":"
            << publishers_during_half_expiry << ","
            << "\"publishers_after_remove\":" << publishers_after_remove << ","
            << "\"connected_alive_change_sum\":"
            << connected.alive_change_sum << ","
            << "\"half_expired_alive_change_sum\":"
            << half_expired.alive_change_sum << ","
            << "\"half_expired_not_alive_change_sum\":"
            << half_expired.not_alive_change_sum << ","
            << "\"reasserted_alive_change_sum\":"
            << reasserted.alive_change_sum << ","
            << "\"all_expired_alive_change_sum\":"
            << all_expired.alive_change_sum << ","
            << "\"all_expired_not_alive_change_sum\":"
            << all_expired.not_alive_change_sum << ","
            << "\"removed_not_alive_change_sum\":"
            << removed.not_alive_change_sum << ","
            << "\"matched_change_sum\":" << matched.current_change_sum << ","
            << "\"unmatched_change_sum\":" << unmatched.current_change_sum << ","
            << "\"assertions_received\":" << assertions << ","
            << "\"manual_liveliness_expiries\":" << expiries << ","
            << "\"manual_liveliness_reassertions\":" << reassertions << ","
            << "\"callback_events\":"
            << callback_state.events.load(std::memory_order_relaxed) << ","
            << "\"clean_teardown\":" << (teardown_ok ? "true" : "false") << "}"
            << std::endl;
  return ok ? 0 : 1;
}

}  // namespace

int main(int argc, char ** argv)
{
  std::string mode;
  for (int index = 1; index + 1 < argc; ++index) {
    if (std::string(argv[index]) == "--mode") {
      mode = argv[index + 1];
    }
  }
  if (mode == "advertiser") {
    return run_advertiser();
  }
  if (mode == "observer") {
    return run_observer();
  }
  std::cout << "{\"status\":\"invalid_mode\"}\n";
  return 2;
}

#include <atomic>
#include <chrono>
#include <cstdint>
#include <iostream>
#include <string>
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

extern "C" std::uint64_t rmw_fleetqox_cpp_remote_manual_liveliness_assertions_received();
extern "C" std::uint64_t rmw_fleetqox_cpp_remote_manual_liveliness_expiries();
extern "C" std::uint64_t rmw_fleetqox_cpp_remote_manual_liveliness_reassertions();

namespace
{

constexpr const char * kTopic = "/fleetqox/remote_liveliness_multi_endpoint";

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

rmw_qos_profile_t manual_qos()
{
  rmw_qos_profile_t qos = rmw_qos_profile_default;
  qos.history = RMW_QOS_POLICY_HISTORY_KEEP_LAST;
  qos.depth = 8;
  qos.reliability = RMW_QOS_POLICY_RELIABILITY_BEST_EFFORT;
  qos.liveliness = RMW_QOS_POLICY_LIVELINESS_MANUAL_BY_TOPIC;
  qos.liveliness_lease_duration.sec = 0;
  qos.liveliness_lease_duration.nsec = 500000000;
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

template<typename StatusT>
bool wait_take_event(
  rmw_context_t * context,
  rmw_event_t * event,
  StatusT * status,
  int timeout_ms)
{
  if (context == nullptr || event == nullptr || status == nullptr) {
    return false;
  }
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
    timeout.nsec = 50000000;
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

bool liveliness_status_is(
  const rmw_liveliness_changed_status_t & status,
  std::int32_t alive,
  std::int32_t not_alive,
  std::int32_t alive_change,
  std::int32_t not_alive_change)
{
  return status.alive_count == alive &&
         status.not_alive_count == not_alive &&
         status.alive_count_change == alive_change &&
         status.not_alive_count_change == not_alive_change;
}

bool matched_status_is(
  const rmw_matched_status_t & status,
  size_t current,
  std::int32_t change)
{
  return status.current_count == current && status.current_count_change == change;
}

int run_advertiser()
{
  rcutils_allocator_t allocator = rcutils_get_default_allocator();
  rmw_init_options_t options{};
  rmw_context_t context{};
  if (!init_context(allocator, 821, &options, &context)) {
    std::cout << "{\"status\":\"init_failed\"}\n";
    return 1;
  }
  rmw_node_t * node =
    rmw_create_node(&context, "remote_liveliness_multi_advertiser", "/fleetqox");
  rosidl_message_type_support_t type_support{};
  type_support.typesupport_identifier = "fleetrmw_remote_liveliness_multi_type";
  const rmw_qos_profile_t qos = manual_qos();
  const rmw_publisher_options_t publisher_options = rmw_get_default_publisher_options();
  rmw_publisher_t * publisher_one = node == nullptr ? nullptr :
    rmw_create_publisher(node, &type_support, kTopic, &qos, &publisher_options);
  if (publisher_one == nullptr) {
    if (node != nullptr) {
      const rmw_ret_t node_ret = rmw_destroy_node(node);
      (void)node_ret;
    }
    const bool context_ok = fini_context(&context, &options);
    (void)context_ok;
    std::cout << "{\"status\":\"publisher_one_create_failed\"}\n";
    return 1;
  }

  std::atomic<bool> keep_asserting{true};
  std::atomic<std::uint64_t> keepalive_assertions{0};
  std::atomic<bool> keepalive_ok{true};
  std::thread keepalive_thread([&]() {
      std::this_thread::sleep_for(std::chrono::milliseconds(80));
      while (keep_asserting.load(std::memory_order_relaxed)) {
        if (rmw_publisher_assert_liveliness(publisher_one) != RMW_RET_OK) {
          keepalive_ok.store(false, std::memory_order_relaxed);
        } else {
          keepalive_assertions.fetch_add(1, std::memory_order_relaxed);
        }
        std::this_thread::sleep_for(std::chrono::milliseconds(100));
      }
    });

  std::this_thread::sleep_for(std::chrono::milliseconds(200));
  rmw_publisher_t * publisher_two =
    rmw_create_publisher(node, &type_support, kTopic, &qos, &publisher_options);
  const bool publisher_two_created = publisher_two != nullptr;
  std::this_thread::sleep_for(std::chrono::milliseconds(650));
  const bool publisher_two_reasserted = publisher_two_created &&
    rmw_publisher_assert_liveliness(publisher_two) == RMW_RET_OK;
  std::this_thread::sleep_for(std::chrono::milliseconds(200));

  keep_asserting.store(false, std::memory_order_relaxed);
  keepalive_thread.join();
  const rmw_ret_t publisher_one_ret = rmw_destroy_publisher(node, publisher_one);

  std::this_thread::sleep_for(std::chrono::milliseconds(650));
  const rmw_ret_t publisher_two_ret = publisher_two_created ?
    rmw_destroy_publisher(node, publisher_two) : RMW_RET_ERROR;

  std::this_thread::sleep_for(std::chrono::milliseconds(200));
  rmw_publisher_t * publisher_three =
    rmw_create_publisher(node, &type_support, kTopic, &qos, &publisher_options);
  const bool publisher_three_created = publisher_three != nullptr;
  std::this_thread::sleep_for(std::chrono::milliseconds(200));
  const rmw_ret_t publisher_three_ret = publisher_three_created ?
    rmw_destroy_publisher(node, publisher_three) : RMW_RET_ERROR;

  const rmw_ret_t node_ret = rmw_destroy_node(node);
  const bool context_ok = fini_context(&context, &options);
  const bool ok = publisher_two_created && publisher_two_reasserted &&
    keepalive_ok.load(std::memory_order_relaxed) &&
    keepalive_assertions.load(std::memory_order_relaxed) >= 8 &&
    publisher_one_ret == RMW_RET_OK && publisher_two_ret == RMW_RET_OK &&
    publisher_three_created && publisher_three_ret == RMW_RET_OK &&
    node_ret == RMW_RET_OK && context_ok;
  std::cout << "{\"schema_version\":\"fleetrmw.remote_liveliness_multi_endpoint_probe.v1\","
            << "\"mode\":\"advertiser\",\"status\":\""
            << (ok ? "ok" : "failed") << "\","
            << "\"keepalive_assertions\":"
            << keepalive_assertions.load(std::memory_order_relaxed) << ","
            << "\"keepalive_ok\":"
            << (keepalive_ok.load(std::memory_order_relaxed) ? "true" : "false") << ","
            << "\"publisher_two_reasserted\":"
            << (publisher_two_reasserted ? "true" : "false") << ","
            << "\"endpoint_recreated\":"
            << (publisher_three_created ? "true" : "false") << ","
            << "\"clean_teardown\":" << (ok ? "true" : "false") << "}"
            << std::endl;
  return ok ? 0 : 1;
}

int run_observer()
{
  rcutils_allocator_t allocator = rcutils_get_default_allocator();
  rmw_init_options_t options{};
  rmw_context_t context{};
  if (!init_context(allocator, 822, &options, &context)) {
    std::cout << "{\"status\":\"init_failed\"}\n";
    return 1;
  }
  rmw_node_t * node =
    rmw_create_node(&context, "remote_liveliness_multi_observer", "/fleetqox");
  rosidl_message_type_support_t type_support{};
  type_support.typesupport_identifier = "fleetrmw_remote_liveliness_multi_type";
  const rmw_qos_profile_t qos = manual_qos();
  const rmw_subscription_options_t subscription_options =
    rmw_get_default_subscription_options();
  rmw_subscription_t * subscription = node == nullptr ? nullptr :
    rmw_create_subscription(node, &type_support, kTopic, &qos, &subscription_options);
  rmw_event_t liveliness_event = rmw_get_zero_initialized_event();
  rmw_event_t matched_event = rmw_get_zero_initialized_event();
  bool initialized = subscription != nullptr &&
    rmw_subscription_event_init(
    &liveliness_event, subscription, RMW_EVENT_LIVELINESS_CHANGED) == RMW_RET_OK &&
    rmw_subscription_event_init(
    &matched_event, subscription, RMW_EVENT_SUBSCRIPTION_MATCHED) == RMW_RET_OK;
  CallbackState callback_state;
  initialized = initialized &&
    rmw_event_set_callback(
    &liveliness_event, event_callback, &callback_state) == RMW_RET_OK;
  const std::uint64_t assertions_before =
    rmw_fleetqox_cpp_remote_manual_liveliness_assertions_received();
  const std::uint64_t expiries_before =
    rmw_fleetqox_cpp_remote_manual_liveliness_expiries();
  const std::uint64_t reassertions_before =
    rmw_fleetqox_cpp_remote_manual_liveliness_reassertions();
  std::cout <<
    "{\"schema_version\":\"fleetrmw.remote_liveliness_multi_endpoint_probe.v1\","
    "\"mode\":\"observer\",\"phase\":\"ready\",\"initialized\":"
            << (initialized ? "true" : "false") << "}" << std::endl;

  rmw_liveliness_changed_status_t first_connect{};
  rmw_matched_status_t first_match{};
  rmw_liveliness_changed_status_t second_connect{};
  rmw_matched_status_t second_match{};
  rmw_liveliness_changed_status_t second_expiry{};
  rmw_liveliness_changed_status_t second_reassert{};
  rmw_liveliness_changed_status_t first_remove{};
  rmw_matched_status_t first_unmatch{};
  rmw_liveliness_changed_status_t second_expiry_again{};
  rmw_liveliness_changed_status_t second_remove{};
  rmw_matched_status_t second_unmatch{};
  rmw_liveliness_changed_status_t churn_connect{};
  rmw_matched_status_t churn_match{};
  rmw_liveliness_changed_status_t churn_remove{};
  rmw_matched_status_t churn_unmatch{};

  const bool first_connect_taken = initialized &&
    wait_take_event(&context, &liveliness_event, &first_connect, 4000);
  const bool first_match_taken = initialized &&
    wait_take_event(&context, &matched_event, &first_match, 4000);
  const bool second_connect_taken = initialized &&
    wait_take_event(&context, &liveliness_event, &second_connect, 4000);
  const bool second_match_taken = initialized &&
    wait_take_event(&context, &matched_event, &second_match, 4000);
  const bool second_expiry_taken = initialized &&
    wait_take_event(&context, &liveliness_event, &second_expiry, 4000);
  size_t publishers_during_expiry = 0;
  const bool publishers_during_expiry_ok = node != nullptr &&
    rmw_count_publishers(node, kTopic, &publishers_during_expiry) == RMW_RET_OK;
  const bool matched_quiet_during_expiry = initialized &&
    event_not_ready(&context, &matched_event, 80);
  const bool second_reassert_taken = initialized &&
    wait_take_event(&context, &liveliness_event, &second_reassert, 4000);
  const bool first_remove_taken = initialized &&
    wait_take_event(&context, &liveliness_event, &first_remove, 4000);
  const bool first_unmatch_taken = initialized &&
    wait_take_event(&context, &matched_event, &first_unmatch, 4000);
  const bool second_expiry_again_taken = initialized &&
    wait_take_event(&context, &liveliness_event, &second_expiry_again, 4000);
  const bool matched_quiet_during_second_expiry = initialized &&
    event_not_ready(&context, &matched_event, 80);
  const bool second_remove_taken = initialized &&
    wait_take_event(&context, &liveliness_event, &second_remove, 4000);
  const bool second_unmatch_taken = initialized &&
    wait_take_event(&context, &matched_event, &second_unmatch, 4000);
  const bool churn_connect_taken = initialized &&
    wait_take_event(&context, &liveliness_event, &churn_connect, 4000);
  const bool churn_match_taken = initialized &&
    wait_take_event(&context, &matched_event, &churn_match, 4000);
  const bool churn_remove_taken = initialized &&
    wait_take_event(&context, &liveliness_event, &churn_remove, 4000);
  const bool churn_unmatch_taken = initialized &&
    wait_take_event(&context, &matched_event, &churn_unmatch, 4000);

  size_t publishers_after_churn = 99;
  const bool publishers_after_churn_ok = node != nullptr &&
    rmw_count_publishers(node, kTopic, &publishers_after_churn) == RMW_RET_OK;
  const std::uint64_t assertions =
    rmw_fleetqox_cpp_remote_manual_liveliness_assertions_received() - assertions_before;
  const std::uint64_t expiries =
    rmw_fleetqox_cpp_remote_manual_liveliness_expiries() - expiries_before;
  const std::uint64_t reassertions =
    rmw_fleetqox_cpp_remote_manual_liveliness_reassertions() - reassertions_before;

  const bool liveliness_ok =
    first_connect_taken && liveliness_status_is(first_connect, 1, 0, 1, 0) &&
    second_connect_taken && liveliness_status_is(second_connect, 2, 0, 1, 0) &&
    second_expiry_taken && liveliness_status_is(second_expiry, 1, 1, -1, 1) &&
    second_reassert_taken && liveliness_status_is(second_reassert, 2, 0, 1, -1) &&
    first_remove_taken && liveliness_status_is(first_remove, 1, 0, -1, 0) &&
    second_expiry_again_taken &&
    liveliness_status_is(second_expiry_again, 0, 1, -1, 1) &&
    second_remove_taken && liveliness_status_is(second_remove, 0, 0, 0, -1) &&
    churn_connect_taken && liveliness_status_is(churn_connect, 1, 0, 1, 0) &&
    churn_remove_taken && liveliness_status_is(churn_remove, 0, 0, -1, 0);
  const bool matched_ok =
    first_match_taken && matched_status_is(first_match, 1, 1) &&
    second_match_taken && matched_status_is(second_match, 2, 1) &&
    first_unmatch_taken && matched_status_is(first_unmatch, 1, -1) &&
    second_unmatch_taken && matched_status_is(second_unmatch, 0, -1) &&
    churn_match_taken && matched_status_is(churn_match, 1, 1) &&
    churn_unmatch_taken && matched_status_is(churn_unmatch, 0, -1) &&
    matched_quiet_during_expiry && matched_quiet_during_second_expiry;
  const bool count_ok = publishers_during_expiry_ok &&
    publishers_during_expiry == 2 && publishers_after_churn_ok &&
    publishers_after_churn == 0;
  const bool counters_ok = assertions >= 9 && expiries == 2 && reassertions == 1;

  const rmw_ret_t liveliness_event_ret = initialized ?
    rmw_event_fini(&liveliness_event) : RMW_RET_ERROR;
  const rmw_ret_t matched_event_ret = initialized ?
    rmw_event_fini(&matched_event) : RMW_RET_ERROR;
  const rmw_ret_t subscription_ret = subscription == nullptr ?
    RMW_RET_ERROR : rmw_destroy_subscription(node, subscription);
  const rmw_ret_t node_ret = node == nullptr ? RMW_RET_ERROR : rmw_destroy_node(node);
  const bool context_ok = fini_context(&context, &options);
  const bool teardown_ok = liveliness_event_ret == RMW_RET_OK &&
    matched_event_ret == RMW_RET_OK && subscription_ret == RMW_RET_OK &&
    node_ret == RMW_RET_OK && context_ok;
  const bool ok = initialized && liveliness_ok && matched_ok && count_ok &&
    counters_ok && callback_state.events.load(std::memory_order_relaxed) >= 9 &&
    teardown_ok;

  std::cout <<
    "{\"schema_version\":\"fleetrmw.remote_liveliness_multi_endpoint_probe.v1\","
            << "\"mode\":\"observer\",\"status\":\""
            << (ok ? "ok" : "failed") << "\","
            << "\"multi_endpoint_independent_state_claim\":"
            << (liveliness_ok ? "true" : "false") << ","
            << "\"alive_remove_and_not_alive_remove_claim\":"
            << (liveliness_ok ? "true" : "false") << ","
            << "\"endpoint_churn_recreate_claim\":"
            << (churn_connect_taken && churn_remove_taken ? "true" : "false") << ","
            << "\"liveliness_expiry_preserves_matching_claim\":"
            << (matched_quiet_during_expiry && matched_quiet_during_second_expiry ?
    "true" : "false") << ","
            << "\"publishers_during_single_endpoint_expiry\":"
            << publishers_during_expiry << ","
            << "\"publishers_after_churn\":" << publishers_after_churn << ","
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
  for (int i = 1; i + 1 < argc; ++i) {
    if (std::string(argv[i]) == "--mode") {
      mode = argv[i + 1];
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

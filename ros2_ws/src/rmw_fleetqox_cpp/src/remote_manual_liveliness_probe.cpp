#include <atomic>
#include <chrono>
#include <cstdint>
#include <cstring>
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
#include "rmw/serialized_message.h"
#include "rmw/subscription_options.h"
#include "rosidl_runtime_c/message_type_support_struct.h"

extern "C" std::uint64_t rmw_fleetqox_cpp_remote_manual_liveliness_assertions_received();
extern "C" std::uint64_t rmw_fleetqox_cpp_remote_manual_liveliness_expiries();
extern "C" std::uint64_t rmw_fleetqox_cpp_remote_manual_liveliness_reassertions();

namespace
{

constexpr const char * kTopic = "/fleetqox/remote_manual_liveliness";

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
  qos.liveliness_lease_duration.nsec = 200000000;
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
  return rmw_shutdown(context) == RMW_RET_OK &&
         rmw_context_fini(context) == RMW_RET_OK &&
         rmw_init_options_fini(options) == RMW_RET_OK;
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
  return rmw_destroy_wait_set(wait_set) == RMW_RET_OK && not_ready;
}

bool status_is(
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

int run_advertiser()
{
  rcutils_allocator_t allocator = rcutils_get_default_allocator();
  rmw_init_options_t options{};
  rmw_context_t context{};
  if (!init_context(allocator, 811, &options, &context)) {
    std::cout << "{\"status\":\"init_failed\"}\n";
    return 1;
  }
  rmw_node_t * node =
    rmw_create_node(&context, "remote_manual_liveliness_advertiser", "/fleetqox");
  rosidl_message_type_support_t type_support{};
  type_support.typesupport_identifier = "fleetrmw_remote_manual_liveliness_type";
  const rmw_qos_profile_t qos = manual_qos();
  const rmw_publisher_options_t publisher_options = rmw_get_default_publisher_options();
  rmw_publisher_t * publisher = node == nullptr ? nullptr :
    rmw_create_publisher(node, &type_support, kTopic, &qos, &publisher_options);
  rmw_event_t lost_event = rmw_get_zero_initialized_event();
  CallbackState lost_callback_state;
  bool lost_event_initialized = publisher != nullptr &&
    rmw_publisher_event_init(
    &lost_event, publisher, RMW_EVENT_LIVELINESS_LOST) == RMW_RET_OK;
  lost_event_initialized = lost_event_initialized &&
    rmw_event_set_callback(
    &lost_event, event_callback, &lost_callback_state) == RMW_RET_OK;
  const bool initial_lost_not_ready = lost_event_initialized &&
    event_not_ready(&context, &lost_event, 0);
  std::cout << "{\"schema_version\":\"fleetrmw.remote_manual_liveliness_probe.v1\","
            << "\"mode\":\"advertiser\",\"phase\":\"ready\",\"created\":"
            << (publisher != nullptr ? "true" : "false") << ","
            << "\"lost_event_initialized\":"
            << (lost_event_initialized ? "true" : "false") << "}" << std::endl;
  if (publisher == nullptr || !lost_event_initialized) {
    if (lost_event_initialized) {
      const rmw_ret_t event_ret = rmw_event_fini(&lost_event);
      (void)event_ret;
    }
    if (publisher != nullptr) {
      const rmw_ret_t publisher_ret = rmw_destroy_publisher(node, publisher);
      (void)publisher_ret;
    }
    if (node != nullptr) {
      const rmw_ret_t node_ret = rmw_destroy_node(node);
      (void)node_ret;
    }
    const bool context_ok = fini_context(&context, &options);
    (void)context_ok;
    return 1;
  }

  std::this_thread::sleep_for(std::chrono::milliseconds(700));
  rmw_liveliness_lost_status_t first_lost{};
  const bool first_lost_taken =
    wait_take_event(&context, &lost_event, &first_lost, 1000);
  bool explicit_assert_ok = true;
  for (int i = 0; i < 5; ++i) {
    explicit_assert_ok =
      rmw_publisher_assert_liveliness(publisher) == RMW_RET_OK && explicit_assert_ok;
    std::this_thread::sleep_for(std::chrono::milliseconds(80));
  }

  std::this_thread::sleep_for(std::chrono::milliseconds(500));
  rmw_liveliness_lost_status_t second_lost{};
  const bool second_lost_taken =
    wait_take_event(&context, &lost_event, &second_lost, 1000);
  rmw_serialized_message_t outgoing = rmw_get_zero_initialized_serialized_message();
  const char payload[] = "remote-manual-liveliness-publish";
  const bool message_init_ok =
    rmw_serialized_message_init(&outgoing, sizeof(payload) - 1, &allocator) == RMW_RET_OK;
  if (message_init_ok) {
    std::memcpy(outgoing.buffer, payload, sizeof(payload) - 1);
    outgoing.buffer_length = sizeof(payload) - 1;
  }
  bool publish_ok = message_init_ok;
  for (int i = 0; i < 5 && message_init_ok; ++i) {
    publish_ok =
      rmw_publish_serialized_message(publisher, &outgoing, nullptr) == RMW_RET_OK && publish_ok;
    if (i + 1 < 5) {
      std::this_thread::sleep_for(std::chrono::milliseconds(80));
    }
  }
  std::this_thread::sleep_for(std::chrono::milliseconds(60));
  const bool lost_event_cleared = event_not_ready(&context, &lost_event, 20);

  const rmw_ret_t message_fini_ret = message_init_ok ?
    rmw_serialized_message_fini(&outgoing) : RMW_RET_ERROR;
  const rmw_ret_t lost_event_ret = rmw_event_fini(&lost_event);
  const rmw_ret_t publisher_ret = rmw_destroy_publisher(node, publisher);
  const rmw_ret_t node_ret = rmw_destroy_node(node);
  const bool context_ok = fini_context(&context, &options);
  const bool lost_event_ok = initial_lost_not_ready && first_lost_taken &&
    first_lost.total_count == 1 && first_lost.total_count_change == 1 &&
    second_lost_taken && second_lost.total_count == 2 &&
    second_lost.total_count_change == 1 &&
    lost_callback_state.events.load(std::memory_order_relaxed) == 2 &&
    lost_event_cleared;
  const bool ok = explicit_assert_ok && publish_ok && lost_event_ok &&
    message_fini_ret == RMW_RET_OK && lost_event_ret == RMW_RET_OK &&
    publisher_ret == RMW_RET_OK &&
    node_ret == RMW_RET_OK && context_ok;
  std::cout << "{\"schema_version\":\"fleetrmw.remote_manual_liveliness_probe.v1\","
            << "\"mode\":\"advertiser\",\"status\":\""
            << (ok ? "ok" : "failed") << "\","
            << "\"explicit_assert_count\":5,\"publish_assert_count\":5,"
            << "\"explicit_assert_ok\":" << (explicit_assert_ok ? "true" : "false") << ","
            << "\"publish_ok\":" << (publish_ok ? "true" : "false") << ","
            << "\"remote_publisher_liveliness_lost_event_claim\":"
            << (lost_event_ok ? "true" : "false") << ","
            << "\"initial_lost_not_ready\":"
            << (initial_lost_not_ready ? "true" : "false") << ","
            << "\"first_lost_taken\":" << (first_lost_taken ? "true" : "false") << ","
            << "\"first_lost_total_count\":" << first_lost.total_count << ","
            << "\"second_lost_taken\":" << (second_lost_taken ? "true" : "false") << ","
            << "\"second_lost_total_count\":" << second_lost.total_count << ","
            << "\"lost_callback_events\":"
            << lost_callback_state.events.load(std::memory_order_relaxed) << ","
            << "\"lost_event_cleared\":"
            << (lost_event_cleared ? "true" : "false") << ","
            << "\"clean_teardown\":" << (ok ? "true" : "false") << "}" << std::endl;
  return ok ? 0 : 1;
}

int run_observer()
{
  rcutils_allocator_t allocator = rcutils_get_default_allocator();
  rmw_init_options_t options{};
  rmw_context_t context{};
  if (!init_context(allocator, 812, &options, &context)) {
    std::cout << "{\"status\":\"init_failed\"}\n";
    return 1;
  }
  rmw_node_t * node =
    rmw_create_node(&context, "remote_manual_liveliness_observer", "/fleetqox");
  rosidl_message_type_support_t type_support{};
  type_support.typesupport_identifier = "fleetrmw_remote_manual_liveliness_type";
  const rmw_qos_profile_t qos = manual_qos();
  const rmw_subscription_options_t subscription_options =
    rmw_get_default_subscription_options();
  rmw_subscription_t * subscription = node == nullptr ? nullptr :
    rmw_create_subscription(
    node, &type_support, kTopic, &qos, &subscription_options);
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
  std::cout << "{\"schema_version\":\"fleetrmw.remote_manual_liveliness_probe.v1\","
            << "\"mode\":\"observer\",\"phase\":\"ready\",\"initialized\":"
            << (initialized ? "true" : "false") << "}" << std::endl;

  rmw_liveliness_changed_status_t connect{};
  rmw_matched_status_t matched_connect{};
  rmw_liveliness_changed_status_t idle_loss{};
  rmw_liveliness_changed_status_t explicit_reassert{};
  rmw_liveliness_changed_status_t second_loss{};
  rmw_liveliness_changed_status_t publish_reassert{};
  rmw_liveliness_changed_status_t disconnect{};
  rmw_matched_status_t matched_disconnect{};
  const bool connect_taken = initialized &&
    wait_take_event(&context, &liveliness_event, &connect, 3000);
  const bool matched_connect_taken = initialized &&
    wait_take_event(&context, &matched_event, &matched_connect, 3000);
  const bool idle_loss_taken = initialized &&
    wait_take_event(&context, &liveliness_event, &idle_loss, 3000);
  size_t publishers_after_idle_loss = 0;
  const bool count_after_idle_loss_ok = node != nullptr &&
    rmw_count_publishers(node, kTopic, &publishers_after_idle_loss) == RMW_RET_OK;
  const bool matched_still_quiet = initialized &&
    event_not_ready(&context, &matched_event, 80);
  const bool explicit_reassert_taken = initialized &&
    wait_take_event(&context, &liveliness_event, &explicit_reassert, 3000);
  const bool second_loss_taken = initialized &&
    wait_take_event(&context, &liveliness_event, &second_loss, 3000);
  const bool publish_reassert_taken = initialized &&
    wait_take_event(&context, &liveliness_event, &publish_reassert, 3000);

  rmw_serialized_message_t incoming = rmw_get_zero_initialized_serialized_message();
  const bool incoming_init_ok =
    rmw_serialized_message_init(&incoming, 1, &allocator) == RMW_RET_OK;
  bool payload_taken = false;
  if (incoming_init_ok) {
    const auto deadline =
      std::chrono::steady_clock::now() + std::chrono::milliseconds(1000);
    while (std::chrono::steady_clock::now() < deadline && !payload_taken) {
      const rmw_ret_t take_ret = rmw_take_serialized_message(
        subscription, &incoming, &payload_taken, nullptr);
      if (take_ret != RMW_RET_OK) {
        break;
      }
      if (!payload_taken) {
        std::this_thread::sleep_for(std::chrono::milliseconds(20));
      }
    }
  }
  const bool disconnect_taken = initialized &&
    wait_take_event(&context, &liveliness_event, &disconnect, 3000);
  const bool matched_disconnect_taken = initialized &&
    wait_take_event(&context, &matched_event, &matched_disconnect, 3000);

  const std::uint64_t assertions =
    rmw_fleetqox_cpp_remote_manual_liveliness_assertions_received() - assertions_before;
  const std::uint64_t expiries =
    rmw_fleetqox_cpp_remote_manual_liveliness_expiries() - expiries_before;
  const std::uint64_t reassertions =
    rmw_fleetqox_cpp_remote_manual_liveliness_reassertions() - reassertions_before;
  const rmw_ret_t incoming_fini_ret = incoming_init_ok ?
    rmw_serialized_message_fini(&incoming) : RMW_RET_ERROR;
  const rmw_ret_t liveliness_event_ret = initialized ?
    rmw_event_fini(&liveliness_event) : RMW_RET_ERROR;
  const rmw_ret_t matched_event_ret = initialized ?
    rmw_event_fini(&matched_event) : RMW_RET_ERROR;
  const rmw_ret_t subscription_ret = subscription == nullptr ?
    RMW_RET_ERROR : rmw_destroy_subscription(node, subscription);
  const rmw_ret_t node_ret = node == nullptr ? RMW_RET_ERROR : rmw_destroy_node(node);
  const bool context_ok = fini_context(&context, &options);

  const bool transition_ok =
    connect_taken && status_is(connect, 1, 0, 1, 0) &&
    idle_loss_taken && status_is(idle_loss, 0, 1, -1, 1) &&
    explicit_reassert_taken && status_is(explicit_reassert, 1, 0, 1, -1) &&
    second_loss_taken && status_is(second_loss, 0, 1, -1, 1) &&
    publish_reassert_taken && status_is(publish_reassert, 1, 0, 1, -1) &&
    disconnect_taken && status_is(disconnect, 0, 0, -1, 0);
  const bool matched_ok = matched_connect_taken &&
    matched_connect.current_count == 1 && matched_connect.current_count_change == 1 &&
    count_after_idle_loss_ok && publishers_after_idle_loss == 1 && matched_still_quiet &&
    matched_disconnect_taken && matched_disconnect.current_count == 0 &&
    matched_disconnect.current_count_change == -1;
  const bool counters_ok = assertions >= 10 && expiries == 2 && reassertions == 2;
  const bool teardown_ok = incoming_fini_ret == RMW_RET_OK &&
    liveliness_event_ret == RMW_RET_OK && matched_event_ret == RMW_RET_OK &&
    subscription_ret == RMW_RET_OK && node_ret == RMW_RET_OK && context_ok;
  const bool ok = initialized && transition_ok && matched_ok && counters_ok &&
    payload_taken && callback_state.events.load(std::memory_order_relaxed) >= 6 && teardown_ok;

  std::cout << "{\"schema_version\":\"fleetrmw.remote_manual_liveliness_probe.v1\","
            << "\"mode\":\"observer\",\"status\":\""
            << (ok ? "ok" : "failed") << "\","
            << "\"remote_manual_idle_timeout_claim\":"
            << (transition_ok ? "true" : "false") << ","
            << "\"remote_manual_explicit_reassert_claim\":"
            << (explicit_reassert_taken ? "true" : "false") << ","
            << "\"remote_manual_publish_reassert_claim\":"
            << (publish_reassert_taken && payload_taken ? "true" : "false") << ","
            << "\"graph_lease_independent_of_liveliness_lease\":"
            << (matched_ok ? "true" : "false") << ","
            << "\"connect_alive_count\":" << connect.alive_count << ","
            << "\"idle_loss_not_alive_count\":" << idle_loss.not_alive_count << ","
            << "\"explicit_reassert_alive_count\":" << explicit_reassert.alive_count << ","
            << "\"second_loss_not_alive_count\":" << second_loss.not_alive_count << ","
            << "\"publish_reassert_alive_count\":" << publish_reassert.alive_count << ","
            << "\"disconnect_alive_count\":" << disconnect.alive_count << ","
            << "\"disconnect_not_alive_count\":" << disconnect.not_alive_count << ","
            << "\"publishers_after_idle_loss\":" << publishers_after_idle_loss << ","
            << "\"matched_still_quiet_during_liveliness_loss\":"
            << (matched_still_quiet ? "true" : "false") << ","
            << "\"assertions_received\":" << assertions << ","
            << "\"manual_liveliness_expiries\":" << expiries << ","
            << "\"manual_liveliness_reassertions\":" << reassertions << ","
            << "\"payload_taken\":" << (payload_taken ? "true" : "false") << ","
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

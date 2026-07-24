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

namespace
{

constexpr const char * kTopic = "/fleetqox/remote_deadline_event";
constexpr std::uint64_t kDeadlineMs = 100;

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

rmw_qos_profile_t deadline_qos()
{
  rmw_qos_profile_t qos = rmw_qos_profile_default;
  qos.history = RMW_QOS_POLICY_HISTORY_KEEP_LAST;
  qos.depth = 8;
  qos.reliability = RMW_QOS_POLICY_RELIABILITY_BEST_EFFORT;
  qos.deadline.sec = 0;
  qos.deadline.nsec = kDeadlineMs * 1000000u;
  return qos;
}

bool init_context(
  rcutils_allocator_t allocator,
  std::uint64_t instance_id,
  rmw_init_options_t * options,
  rmw_context_t * context)
{
  *options = rmw_get_zero_initialized_init_options();
  if (rmw_init_options_init(options, allocator) != RMW_RET_OK) {
    return false;
  }
  options->instance_id = instance_id;
  *context = rmw_get_zero_initialized_context();
  if (rmw_init(options, context) != RMW_RET_OK) {
    const rmw_ret_t ret = rmw_init_options_fini(options);
    (void)ret;
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
  rmw_wait_set_t * wait_set = rmw_create_wait_set(context, 1);
  if (wait_set == nullptr) {
    return false;
  }
  const auto deadline =
    std::chrono::steady_clock::now() + std::chrono::milliseconds(timeout_ms);
  bool ok = false;
  while (std::chrono::steady_clock::now() < deadline) {
    void * handles[1] = {event};
    rmw_events_t events{1, handles};
    rmw_time_t timeout{};
    timeout.sec = 0;
    timeout.nsec = 20000000;
    const rmw_ret_t wait_ret =
      rmw_wait(nullptr, nullptr, nullptr, nullptr, &events, wait_set, &timeout);
    if (wait_ret == RMW_RET_TIMEOUT) {
      continue;
    }
    if (wait_ret != RMW_RET_OK || handles[0] == nullptr) {
      break;
    }
    bool taken = false;
    ok = rmw_take_event(event, status, &taken) == RMW_RET_OK && taken;
    break;
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

bool init_message(
  rmw_serialized_message_t * message,
  const char * payload,
  rcutils_allocator_t * allocator)
{
  const size_t length = std::strlen(payload);
  if (rmw_serialized_message_init(message, length, allocator) != RMW_RET_OK) {
    return false;
  }
  std::memcpy(message->buffer, payload, length);
  message->buffer_length = length;
  return true;
}

int run_advertiser()
{
  rcutils_allocator_t allocator = rcutils_get_default_allocator();
  rmw_init_options_t options{};
  rmw_context_t context{};
  if (!init_context(allocator, 829, &options, &context)) {
    return 1;
  }
  rmw_node_t * node =
    rmw_create_node(&context, "remote_deadline_advertiser", "/fleetqox");
  rosidl_message_type_support_t type_support{};
  type_support.typesupport_identifier = "fleetrmw_remote_deadline_event_type";
  const rmw_qos_profile_t qos = deadline_qos();
  const rmw_publisher_options_t publisher_options = rmw_get_default_publisher_options();
  rmw_publisher_t * publisher = node == nullptr ? nullptr : rmw_create_publisher(
    node, &type_support, kTopic, &qos, &publisher_options);
  rmw_event_t event = rmw_get_zero_initialized_event();
  const bool event_initialized = publisher != nullptr &&
    rmw_publisher_event_init(
    &event, publisher, RMW_EVENT_OFFERED_DEADLINE_MISSED) == RMW_RET_OK;
  CallbackState callback;
  const bool callback_initialized = event_initialized &&
    rmw_event_set_callback(&event, event_callback, &callback) == RMW_RET_OK;
  const bool initial_quiet = event_initialized && event_not_ready(&context, &event, 0);
  std::this_thread::sleep_for(std::chrono::milliseconds(300));
  rmw_serialized_message_t outgoing = rmw_get_zero_initialized_serialized_message();
  const bool message_initialized = init_message(
    &outgoing, "remote-deadline-anchor", &allocator);
  const bool published = message_initialized && publisher != nullptr &&
    rmw_publish_serialized_message(publisher, &outgoing, nullptr) == RMW_RET_OK;
  rmw_offered_deadline_missed_status_t status{};
  const bool event_taken = published && wait_take_event(
    &context, &event, &status, 2000);
  const bool cleared = event_initialized && event_not_ready(&context, &event, 0);

  bool teardown_ok = true;
  if (message_initialized) {
    teardown_ok = rmw_serialized_message_fini(&outgoing) == RMW_RET_OK && teardown_ok;
  }
  if (event_initialized) {
    teardown_ok = rmw_event_fini(&event) == RMW_RET_OK && teardown_ok;
  }
  if (publisher != nullptr) {
    teardown_ok = rmw_destroy_publisher(node, publisher) == RMW_RET_OK && teardown_ok;
  }
  if (node != nullptr) {
    teardown_ok = rmw_destroy_node(node) == RMW_RET_OK && teardown_ok;
  }
  teardown_ok = fini_context(&context, &options) && teardown_ok;
  const bool event_ok = event_taken && status.total_count >= 1 &&
    status.total_count_change >= 1 && callback.calls.load(std::memory_order_relaxed) >= 1 &&
    callback.events.load(std::memory_order_relaxed) >= 1;
  const bool ok = event_initialized && callback_initialized && initial_quiet &&
    published && event_ok && cleared && teardown_ok;
  std::cout <<
    "{\"schema_version\":\"fleetrmw.remote_deadline_event_probe.v1\","
            << "\"mode\":\"advertiser\",\"status\":\""
            << (ok ? "ok" : "failed") << "\","
            << "\"offered_deadline_missed_event_claim\":"
            << (event_ok ? "true" : "false") << ","
            << "\"initial_not_ready\":" << (initial_quiet ? "true" : "false") << ","
            << "\"cleared_not_ready\":" << (cleared ? "true" : "false") << ","
            << "\"total_count\":" << status.total_count << ","
            << "\"total_count_change\":" << status.total_count_change << ","
            << "\"callback_events\":"
            << callback.events.load(std::memory_order_relaxed) << ","
            << "\"clean_teardown\":" << (teardown_ok ? "true" : "false") << "}"
            << std::endl;
  return ok ? 0 : 1;
}

int run_observer()
{
  rcutils_allocator_t allocator = rcutils_get_default_allocator();
  rmw_init_options_t options{};
  rmw_context_t context{};
  if (!init_context(allocator, 830, &options, &context)) {
    return 1;
  }
  rmw_node_t * node =
    rmw_create_node(&context, "remote_deadline_observer", "/fleetqox");
  rosidl_message_type_support_t type_support{};
  type_support.typesupport_identifier = "fleetrmw_remote_deadline_event_type";
  const rmw_qos_profile_t qos = deadline_qos();
  const rmw_subscription_options_t subscription_options =
    rmw_get_default_subscription_options();
  rmw_subscription_t * subscription = node == nullptr ? nullptr :
    rmw_create_subscription(
    node, &type_support, kTopic, &qos, &subscription_options);
  rmw_event_t event = rmw_get_zero_initialized_event();
  const bool event_initialized = subscription != nullptr &&
    rmw_subscription_event_init(
    &event, subscription, RMW_EVENT_REQUESTED_DEADLINE_MISSED) == RMW_RET_OK;
  CallbackState callback;
  const bool callback_initialized = event_initialized &&
    rmw_event_set_callback(&event, event_callback, &callback) == RMW_RET_OK;
  const bool initial_quiet = event_initialized && event_not_ready(&context, &event, 0);
  std::cout <<
    "{\"schema_version\":\"fleetrmw.remote_deadline_event_probe.v1\","
    "\"mode\":\"observer\",\"phase\":\"ready\",\"initialized\":"
            << (event_initialized && callback_initialized ? "true" : "false") << "}"
            << std::endl;

  rmw_serialized_message_t incoming = rmw_get_zero_initialized_serialized_message();
  const bool message_initialized =
    rmw_serialized_message_init(&incoming, 1, &allocator) == RMW_RET_OK;
  bool sample_taken = false;
  const auto sample_deadline =
    std::chrono::steady_clock::now() + std::chrono::seconds(3);
  while (!sample_taken && subscription != nullptr && message_initialized &&
    std::chrono::steady_clock::now() < sample_deadline)
  {
    if (rmw_take_serialized_message(
        subscription, &incoming, &sample_taken, nullptr) != RMW_RET_OK)
    {
      break;
    }
    if (!sample_taken) {
      std::this_thread::sleep_for(std::chrono::milliseconds(2));
    }
  }
  rmw_requested_deadline_missed_status_t status{};
  const bool event_taken = sample_taken && wait_take_event(
    &context, &event, &status, 2000);
  const bool cleared = event_initialized && event_not_ready(&context, &event, 0);

  bool teardown_ok = true;
  if (message_initialized) {
    teardown_ok = rmw_serialized_message_fini(&incoming) == RMW_RET_OK && teardown_ok;
  }
  if (event_initialized) {
    teardown_ok = rmw_event_fini(&event) == RMW_RET_OK && teardown_ok;
  }
  if (subscription != nullptr) {
    teardown_ok =
      rmw_destroy_subscription(node, subscription) == RMW_RET_OK && teardown_ok;
  }
  if (node != nullptr) {
    teardown_ok = rmw_destroy_node(node) == RMW_RET_OK && teardown_ok;
  }
  teardown_ok = fini_context(&context, &options) && teardown_ok;
  const bool event_ok = event_taken && status.total_count >= 1 &&
    status.total_count_change >= 1 && callback.calls.load(std::memory_order_relaxed) >= 1 &&
    callback.events.load(std::memory_order_relaxed) >= 1;
  const bool ok = event_initialized && callback_initialized && initial_quiet &&
    sample_taken && event_ok && cleared && teardown_ok;
  std::cout <<
    "{\"schema_version\":\"fleetrmw.remote_deadline_event_probe.v1\","
            << "\"mode\":\"observer\",\"status\":\""
            << (ok ? "ok" : "failed") << "\","
            << "\"requested_deadline_missed_event_claim\":"
            << (event_ok ? "true" : "false") << ","
            << "\"sample_taken\":" << (sample_taken ? "true" : "false") << ","
            << "\"initial_not_ready\":" << (initial_quiet ? "true" : "false") << ","
            << "\"cleared_not_ready\":" << (cleared ? "true" : "false") << ","
            << "\"total_count\":" << status.total_count << ","
            << "\"total_count_change\":" << status.total_count_change << ","
            << "\"callback_events\":"
            << callback.events.load(std::memory_order_relaxed) << ","
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

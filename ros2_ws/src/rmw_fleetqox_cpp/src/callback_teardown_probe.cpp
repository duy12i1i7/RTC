#include <chrono>
#include <condition_variable>
#include <cstdint>
#include <future>
#include <iostream>
#include <mutex>
#include <string>

#include "rcutils/allocator.h"
#include "rmw/event.h"
#include "rmw/init.h"
#include "rmw/init_options.h"
#include "rmw/publisher_options.h"
#include "rmw/qos_profiles.h"
#include "rmw/rmw.h"
#include "rmw/subscription_options.h"
#include "rosidl_runtime_c/message_type_support_struct.h"

namespace
{

using namespace std::chrono_literals;

struct BlockingCallback
{
  std::mutex mutex;
  std::condition_variable condition;
  bool entered{false};
  bool released{false};
  size_t calls{0};
  size_t events{0};

  bool wait_until_entered()
  {
    std::unique_lock<std::mutex> lock(mutex);
    return condition.wait_for(lock, 2s, [this]() {return entered;});
  }

  void release()
  {
    {
      std::lock_guard<std::mutex> lock(mutex);
      released = true;
    }
    condition.notify_all();
  }
};

void blocking_callback(const void * user_data, size_t number_of_events)
{
  auto * state = const_cast<BlockingCallback *>(
    static_cast<const BlockingCallback *>(user_data));
  if (state == nullptr) {
    return;
  }
  std::unique_lock<std::mutex> lock(state->mutex);
  state->entered = true;
  ++state->calls;
  state->events += number_of_events;
  state->condition.notify_all();
  state->condition.wait(lock, [state]() {return state->released;});
}

struct CaseResult
{
  bool setup_ok{false};
  bool callback_entered{false};
  bool destroy_blocked_before_release{false};
  bool event_fini_ok{false};
  bool owner_destroy_ok{false};
  bool peer_destroy_ok{false};
  size_t callback_calls{0};
  size_t callback_events{0};

  bool ok() const
  {
    return setup_ok && callback_entered && destroy_blocked_before_release &&
           event_fini_ok && owner_destroy_ok && peer_destroy_ok &&
           callback_calls == 1 && callback_events >= 1;
  }
};

CaseResult exercise_publisher_callback_teardown(
  rmw_node_t * node,
  const rosidl_message_type_support_t * type_support,
  const rmw_qos_profile_t * qos,
  size_t iteration)
{
  CaseResult result;
  const std::string topic =
    "/fleetqox/callback_teardown/publisher_" + std::to_string(iteration);
  rmw_publisher_options_t publisher_options = rmw_get_default_publisher_options();
  rmw_subscription_options_t subscription_options = rmw_get_default_subscription_options();
  rmw_publisher_t * publisher =
    rmw_create_publisher(node, type_support, topic.c_str(), qos, &publisher_options);
  if (publisher == nullptr) {
    return result;
  }

  rmw_event_t event = rmw_get_zero_initialized_event();
  BlockingCallback callback;
  const rmw_ret_t event_init_ret =
    rmw_publisher_event_init(&event, publisher, RMW_EVENT_PUBLICATION_MATCHED);
  const rmw_ret_t callback_ret = event_init_ret == RMW_RET_OK ?
    rmw_event_set_callback(&event, blocking_callback, &callback) : RMW_RET_ERROR;
  result.setup_ok = event_init_ret == RMW_RET_OK && callback_ret == RMW_RET_OK;
  if (!result.setup_ok) {
    if (event_init_ret == RMW_RET_OK) {
      result.event_fini_ok = rmw_event_fini(&event) == RMW_RET_OK;
    }
    result.owner_destroy_ok = rmw_destroy_publisher(node, publisher) == RMW_RET_OK;
    return result;
  }

  auto peer_future = std::async(std::launch::async, [&]() {
      return rmw_create_subscription(
        node, type_support, topic.c_str(), qos, &subscription_options);
    });
  result.callback_entered = callback.wait_until_entered();
  result.event_fini_ok = rmw_event_fini(&event) == RMW_RET_OK;
  auto destroy_future = std::async(std::launch::async, [&]() {
      return rmw_destroy_publisher(node, publisher);
    });
  result.destroy_blocked_before_release = destroy_future.wait_for(75ms) ==
    std::future_status::timeout;
  callback.release();
  rmw_subscription_t * subscription = peer_future.get();
  result.owner_destroy_ok = destroy_future.get() == RMW_RET_OK;
  result.peer_destroy_ok = subscription != nullptr &&
    rmw_destroy_subscription(node, subscription) == RMW_RET_OK;
  result.callback_calls = callback.calls;
  result.callback_events = callback.events;
  return result;
}

CaseResult exercise_subscription_callback_teardown(
  rmw_node_t * node,
  const rosidl_message_type_support_t * type_support,
  const rmw_qos_profile_t * qos,
  size_t iteration)
{
  CaseResult result;
  const std::string topic =
    "/fleetqox/callback_teardown/subscription_" + std::to_string(iteration);
  rmw_publisher_options_t publisher_options = rmw_get_default_publisher_options();
  rmw_subscription_options_t subscription_options = rmw_get_default_subscription_options();
  rmw_subscription_t * subscription =
    rmw_create_subscription(node, type_support, topic.c_str(), qos, &subscription_options);
  if (subscription == nullptr) {
    return result;
  }

  rmw_event_t event = rmw_get_zero_initialized_event();
  BlockingCallback callback;
  const rmw_ret_t event_init_ret =
    rmw_subscription_event_init(&event, subscription, RMW_EVENT_SUBSCRIPTION_MATCHED);
  const rmw_ret_t callback_ret = event_init_ret == RMW_RET_OK ?
    rmw_event_set_callback(&event, blocking_callback, &callback) : RMW_RET_ERROR;
  result.setup_ok = event_init_ret == RMW_RET_OK && callback_ret == RMW_RET_OK;
  if (!result.setup_ok) {
    if (event_init_ret == RMW_RET_OK) {
      result.event_fini_ok = rmw_event_fini(&event) == RMW_RET_OK;
    }
    result.owner_destroy_ok = rmw_destroy_subscription(node, subscription) == RMW_RET_OK;
    return result;
  }

  auto peer_future = std::async(std::launch::async, [&]() {
      return rmw_create_publisher(
        node, type_support, topic.c_str(), qos, &publisher_options);
    });
  result.callback_entered = callback.wait_until_entered();
  result.event_fini_ok = rmw_event_fini(&event) == RMW_RET_OK;
  auto destroy_future = std::async(std::launch::async, [&]() {
      return rmw_destroy_subscription(node, subscription);
    });
  result.destroy_blocked_before_release = destroy_future.wait_for(75ms) ==
    std::future_status::timeout;
  callback.release();
  rmw_publisher_t * publisher = peer_future.get();
  result.owner_destroy_ok = destroy_future.get() == RMW_RET_OK;
  result.peer_destroy_ok = publisher != nullptr &&
    rmw_destroy_publisher(node, publisher) == RMW_RET_OK;
  result.callback_calls = callback.calls;
  result.callback_events = callback.events;
  return result;
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
  constexpr size_t kIterations = 8;
  rmw_init_options_t options = rmw_get_zero_initialized_init_options();
  rmw_ret_t ret = rmw_init_options_init(&options, rcutils_get_default_allocator());
  if (ret != RMW_RET_OK) {
    std::cout << "{\"status\":\"init_options_failed\",\"ret\":" << ret << "}\n";
    return 1;
  }
  options.instance_id = 73;

  rmw_context_t context = rmw_get_zero_initialized_context();
  ret = rmw_init(&options, &context);
  if (ret != RMW_RET_OK) {
    const rmw_ret_t fini_ret = rmw_init_options_fini(&options);
    (void)fini_ret;
    std::cout << "{\"status\":\"init_failed\",\"ret\":" << ret << "}\n";
    return 1;
  }
  rmw_node_t * node =
    rmw_create_node(&context, "fleetqox_callback_teardown_probe", "/fleetqox");
  if (node == nullptr) {
    cleanup_context(&context, &options);
    std::cout << "{\"status\":\"create_node_failed\"}\n";
    return 1;
  }

  rosidl_message_type_support_t type_support{};
  type_support.typesupport_identifier = "rmw_fleetqox_cpp_callback_teardown_probe";
  rmw_qos_profile_t qos = rmw_qos_profile_default;
  qos.history = RMW_QOS_POLICY_HISTORY_KEEP_LAST;
  qos.depth = 8;

  size_t publisher_cases_ok = 0;
  size_t subscription_cases_ok = 0;
  for (size_t iteration = 0; iteration < kIterations; ++iteration) {
    if (exercise_publisher_callback_teardown(node, &type_support, &qos, iteration).ok()) {
      ++publisher_cases_ok;
    }
    if (exercise_subscription_callback_teardown(node, &type_support, &qos, iteration).ok()) {
      ++subscription_cases_ok;
    }
  }

  const rmw_ret_t destroy_node_ret = rmw_destroy_node(node);
  const rmw_ret_t shutdown_ret = rmw_shutdown(&context);
  const rmw_ret_t context_fini_ret = rmw_context_fini(&context);
  const rmw_ret_t options_fini_ret = rmw_init_options_fini(&options);
  const bool teardown_ok = destroy_node_ret == RMW_RET_OK && shutdown_ret == RMW_RET_OK &&
    context_fini_ret == RMW_RET_OK && options_fini_ret == RMW_RET_OK;
  const bool ok = publisher_cases_ok == kIterations &&
    subscription_cases_ok == kIterations && teardown_ok;
  std::cout << "{\"schema_version\":\"fleetrmw.callback_teardown_probe.v1\","
            << "\"status\":\"" << (ok ? "ok" : "failed") << "\","
            << "\"iterations\":" << kIterations << ","
            << "\"publisher_cases_ok\":" << publisher_cases_ok << ","
            << "\"subscription_cases_ok\":" << subscription_cases_ok << ","
            << "\"teardown_ok\":" << (teardown_ok ? "true" : "false") << "}\n";
  return ok ? 0 : 1;
}

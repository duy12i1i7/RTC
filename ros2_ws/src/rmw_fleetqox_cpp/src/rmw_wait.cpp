#include <algorithm>
#include <cstring>
#include <chrono>
#include <atomic>
#include <cstdio>
#include <cstdlib>
#include <mutex>
#include <new>
#include <thread>
#include <utility>
#include <vector>

#include "rcutils/allocator.h"
#include "rmw/allocators.h"
#include "rmw/error_handling.h"
#include "rmw/rmw.h"

struct rmw_context_impl_s
{
  bool is_shutdown;
  rcutils_allocator_t allocator;
};

extern "C" bool rmw_fleetqox_cpp_subscription_has_data(const rmw_subscription_t * subscription);
extern "C" bool rmw_fleetqox_cpp_subscription_data_has_data(const void * subscription_impl);
extern "C" bool rmw_fleetqox_cpp_waitable_subscription_has_data(const void * waitable);
extern "C" bool rmw_fleetqox_cpp_waitable_service_has_request(const void * waitable);
extern "C" bool rmw_fleetqox_cpp_waitable_client_has_response(const void * waitable);

namespace
{

constexpr const char * kIdentifier = "rmw_fleetqox_cpp";

struct FleetQoxGuardConditionData
{
  rcutils_allocator_t allocator;
  std::atomic<bool> triggered;
};

struct FleetQoxWaitSetData
{
  rcutils_allocator_t allocator;
  rmw_context_t * context;
  size_t max_conditions;
};

std::mutex g_guard_condition_mutex;
std::vector<rmw_guard_condition_t *> g_guard_condition_handles;
std::vector<FleetQoxGuardConditionData *> g_guard_condition_data;

bool identifier_matches(const char * identifier)
{
  return identifier != nullptr && std::strcmp(identifier, kIdentifier) == 0;
}

bool trace_wait_enabled()
{
  const char * value = std::getenv("FLEETQOX_RMW_TRACE_WAIT");
  return value != nullptr && value[0] != '\0' && std::strcmp(value, "0") != 0;
}

bool context_is_valid(const rmw_context_t * context)
{
  return context != nullptr &&
         identifier_matches(context->implementation_identifier) &&
         context->impl != nullptr &&
         !context->impl->is_shutdown;
}

rmw_ret_t require_identifier(const char * identifier)
{
  if (!identifier_matches(identifier)) {
    RMW_SET_ERROR_MSG("rmw_fleetqox_cpp implementation identifier mismatch");
    return RMW_RET_INCORRECT_RMW_IMPLEMENTATION;
  }
  return RMW_RET_OK;
}

template<typename T, typename... Args>
T * allocate_data(rcutils_allocator_t allocator, Args &&... args)
{
  if (!rcutils_allocator_is_valid(&allocator)) {
    return nullptr;
  }
  void * memory = allocator.allocate(sizeof(T), allocator.state);
  if (memory == nullptr) {
    return nullptr;
  }
  try {
    return new (memory) T{std::forward<Args>(args)...};
  } catch (...) {
    allocator.deallocate(memory, allocator.state);
    return nullptr;
  }
}

template<typename T>
void deallocate_data(T * data)
{
  if (data == nullptr) {
    return;
  }
  rcutils_allocator_t allocator = data->allocator;
  data->~T();
  allocator.deallocate(data, allocator.state);
}

FleetQoxGuardConditionData * guard_data(const rmw_guard_condition_t * guard_condition)
{
  return guard_condition == nullptr ? nullptr :
         static_cast<FleetQoxGuardConditionData *>(guard_condition->data);
}

FleetQoxGuardConditionData * guard_data_from_waitable(void * waitable)
{
  if (waitable == nullptr) {
    return nullptr;
  }
  std::lock_guard<std::mutex> lock(g_guard_condition_mutex);
  for (FleetQoxGuardConditionData * data : g_guard_condition_data) {
    if (data == waitable) {
      return data;
    }
  }
  for (rmw_guard_condition_t * handle : g_guard_condition_handles) {
    if (handle == waitable) {
      return guard_data(handle);
    }
  }
  return nullptr;
}

FleetQoxWaitSetData * wait_set_data(const rmw_wait_set_t * wait_set)
{
  return wait_set == nullptr ? nullptr : static_cast<FleetQoxWaitSetData *>(wait_set->data);
}

bool guard_condition_is_ready(void * guard_condition)
{
  FleetQoxGuardConditionData * data = guard_data_from_waitable(guard_condition);
  if (data == nullptr || !data->triggered.exchange(false)) {
    return false;
  }
  return true;
}

bool guard_condition_is_triggered(void * guard_condition)
{
  FleetQoxGuardConditionData * data = guard_data_from_waitable(guard_condition);
  return data != nullptr && data->triggered.load();
}

bool subscription_is_ready(rmw_subscription_t * subscription)
{
  return rmw_fleetqox_cpp_waitable_subscription_has_data(subscription);
}

bool service_is_ready(void * service_waitable)
{
  return rmw_fleetqox_cpp_waitable_service_has_request(service_waitable);
}

bool client_is_ready(void * client_waitable)
{
  return rmw_fleetqox_cpp_waitable_client_has_response(client_waitable);
}

bool any_waitable_ready(
  rmw_subscriptions_t * subscriptions,
  rmw_services_t * services,
  rmw_clients_t * clients,
  rmw_guard_conditions_t * guard_conditions)
{
  if (subscriptions != nullptr) {
    for (size_t i = 0; i < subscriptions->subscriber_count; ++i) {
      auto * subscription = static_cast<rmw_subscription_t *>(subscriptions->subscribers[i]);
      if (subscription_is_ready(subscription)) {
        return true;
      }
    }
  }
  if (services != nullptr) {
    for (size_t i = 0; i < services->service_count; ++i) {
      if (service_is_ready(services->services[i])) {
        return true;
      }
    }
  }
  if (clients != nullptr) {
    for (size_t i = 0; i < clients->client_count; ++i) {
      if (client_is_ready(clients->clients[i])) {
        return true;
      }
    }
  }
  if (guard_conditions != nullptr) {
    for (size_t i = 0; i < guard_conditions->guard_condition_count; ++i) {
      if (guard_condition_is_triggered(guard_conditions->guard_conditions[i])) {
        return true;
      }
    }
  }
  return false;
}

std::chrono::nanoseconds wait_timeout_to_nanoseconds(const rmw_time_t * wait_timeout)
{
  if (wait_timeout == nullptr) {
    return std::chrono::nanoseconds::max();
  }
  constexpr std::uint64_t kNanosecondsPerSecond = 1000000000ull;
  if (wait_timeout->sec > static_cast<std::uint64_t>(std::chrono::nanoseconds::max().count() / kNanosecondsPerSecond)) {
    return std::chrono::nanoseconds::max();
  }
  const auto seconds = std::chrono::seconds(wait_timeout->sec);
  const auto nanoseconds = std::chrono::nanoseconds(wait_timeout->nsec);
  if (std::chrono::nanoseconds::max() - nanoseconds < seconds) {
    return std::chrono::nanoseconds::max();
  }
  return seconds + nanoseconds;
}

void clear_events(rmw_events_t * events)
{
  if (events != nullptr) {
    for (size_t i = 0; i < events->event_count; ++i) {
      events->events[i] = nullptr;
    }
  }
}

}  // namespace

extern "C"
{

rmw_guard_condition_t * rmw_create_guard_condition(rmw_context_t * context)
{
  if (!context_is_valid(context)) {
    RMW_SET_ERROR_MSG("context is not a valid rmw_fleetqox_cpp context");
    return nullptr;
  }
  rmw_guard_condition_t * guard_condition = rmw_guard_condition_allocate();
  if (guard_condition == nullptr) {
    RMW_SET_ERROR_MSG("failed to allocate guard condition");
    return nullptr;
  }
  rcutils_allocator_t allocator = context->options.allocator;
  FleetQoxGuardConditionData * data =
    allocate_data<FleetQoxGuardConditionData>(allocator, allocator, false);
  if (data == nullptr) {
    rmw_guard_condition_free(guard_condition);
    RMW_SET_ERROR_MSG("failed to allocate guard condition data");
    return nullptr;
  }
  guard_condition->implementation_identifier = kIdentifier;
  guard_condition->data = data;
  guard_condition->context = context;
  {
    std::lock_guard<std::mutex> lock(g_guard_condition_mutex);
    g_guard_condition_handles.push_back(guard_condition);
    g_guard_condition_data.push_back(data);
  }
  return guard_condition;
}

rmw_ret_t rmw_destroy_guard_condition(rmw_guard_condition_t * guard_condition)
{
  if (guard_condition == nullptr) {
    RMW_SET_ERROR_MSG("guard_condition is null");
    return RMW_RET_INVALID_ARGUMENT;
  }
  rmw_ret_t ret = require_identifier(guard_condition->implementation_identifier);
  if (ret != RMW_RET_OK) {
    return ret;
  }
  FleetQoxGuardConditionData * data = guard_data(guard_condition);
  {
    std::lock_guard<std::mutex> lock(g_guard_condition_mutex);
    g_guard_condition_handles.erase(
      std::remove(
        g_guard_condition_handles.begin(), g_guard_condition_handles.end(), guard_condition),
      g_guard_condition_handles.end());
    g_guard_condition_data.erase(
      std::remove(g_guard_condition_data.begin(), g_guard_condition_data.end(), data),
      g_guard_condition_data.end());
  }
  deallocate_data(data);
  rmw_guard_condition_free(guard_condition);
  return RMW_RET_OK;
}

rmw_ret_t rmw_trigger_guard_condition(const rmw_guard_condition_t * guard_condition)
{
  if (guard_condition == nullptr) {
    RMW_SET_ERROR_MSG("guard_condition is null");
    return RMW_RET_INVALID_ARGUMENT;
  }
  rmw_ret_t ret = require_identifier(guard_condition->implementation_identifier);
  if (ret != RMW_RET_OK) {
    return ret;
  }
  FleetQoxGuardConditionData * data = guard_data(guard_condition);
  if (data == nullptr) {
    RMW_SET_ERROR_MSG("guard condition data is null");
    return RMW_RET_INVALID_ARGUMENT;
  }
  data->triggered.store(true);
  return RMW_RET_OK;
}

rmw_wait_set_t * rmw_create_wait_set(rmw_context_t * context, size_t max_conditions)
{
  if (!context_is_valid(context)) {
    RMW_SET_ERROR_MSG("context is not a valid rmw_fleetqox_cpp context");
    return nullptr;
  }
  rmw_wait_set_t * wait_set = static_cast<rmw_wait_set_t *>(rmw_allocate(sizeof(rmw_wait_set_t)));
  if (wait_set == nullptr) {
    RMW_SET_ERROR_MSG("failed to allocate wait set");
    return nullptr;
  }
  rcutils_allocator_t allocator = context->options.allocator;
  FleetQoxWaitSetData * data =
    allocate_data<FleetQoxWaitSetData>(allocator, allocator, context, max_conditions);
  if (data == nullptr) {
    rmw_free(wait_set);
    RMW_SET_ERROR_MSG("failed to allocate wait set data");
    return nullptr;
  }
  wait_set->implementation_identifier = kIdentifier;
  wait_set->guard_conditions = nullptr;
  wait_set->data = data;
  return wait_set;
}

rmw_ret_t rmw_destroy_wait_set(rmw_wait_set_t * wait_set)
{
  if (wait_set == nullptr) {
    RMW_SET_ERROR_MSG("wait_set is null");
    return RMW_RET_INVALID_ARGUMENT;
  }
  rmw_ret_t ret = require_identifier(wait_set->implementation_identifier);
  if (ret != RMW_RET_OK) {
    return ret;
  }
  deallocate_data(wait_set_data(wait_set));
  rmw_free(wait_set);
  return RMW_RET_OK;
}

rmw_ret_t rmw_wait(
  rmw_subscriptions_t * subscriptions,
  rmw_guard_conditions_t * guard_conditions,
  rmw_services_t * services,
  rmw_clients_t * clients,
  rmw_events_t * events,
  rmw_wait_set_t * wait_set,
  const rmw_time_t * wait_timeout)
{
  if (wait_set == nullptr) {
    RMW_SET_ERROR_MSG("wait_set is null");
    return RMW_RET_INVALID_ARGUMENT;
  }
  rmw_ret_t ret = require_identifier(wait_set->implementation_identifier);
  if (ret != RMW_RET_OK) {
    return ret;
  }
  if (wait_set_data(wait_set) == nullptr) {
    RMW_SET_ERROR_MSG("wait set data is null");
    return RMW_RET_INVALID_ARGUMENT;
  }

  const auto timeout = wait_timeout_to_nanoseconds(wait_timeout);
  const auto start = std::chrono::steady_clock::now();
  while (!any_waitable_ready(subscriptions, services, clients, guard_conditions)) {
    if (timeout.count() == 0) {
      break;
    }
    if (timeout != std::chrono::nanoseconds::max() &&
      std::chrono::steady_clock::now() - start >= timeout)
    {
      break;
    }
    std::this_thread::sleep_for(std::chrono::milliseconds(1));
  }

  bool any_ready = false;
  size_t ready_subscriptions = 0;
  size_t ready_services = 0;
  size_t ready_clients = 0;
  if (subscriptions != nullptr) {
    for (size_t i = 0; i < subscriptions->subscriber_count; ++i) {
      auto * subscription = static_cast<rmw_subscription_t *>(subscriptions->subscribers[i]);
      if (!subscription_is_ready(subscription)) {
        subscriptions->subscribers[i] = nullptr;
      } else {
        any_ready = true;
        ++ready_subscriptions;
      }
    }
  }
  if (guard_conditions != nullptr) {
    for (size_t i = 0; i < guard_conditions->guard_condition_count; ++i) {
      if (!guard_condition_is_ready(guard_conditions->guard_conditions[i])) {
        guard_conditions->guard_conditions[i] = nullptr;
      } else {
        any_ready = true;
      }
    }
  }
  if (services != nullptr) {
    for (size_t i = 0; i < services->service_count; ++i) {
      if (!service_is_ready(services->services[i])) {
        services->services[i] = nullptr;
      } else {
        any_ready = true;
        ++ready_services;
      }
    }
  }
  if (clients != nullptr) {
    for (size_t i = 0; i < clients->client_count; ++i) {
      if (!client_is_ready(clients->clients[i])) {
        clients->clients[i] = nullptr;
      } else {
        any_ready = true;
        ++ready_clients;
      }
    }
  }
  clear_events(events);
  if (trace_wait_enabled()) {
    std::fprintf(
      stderr,
      "fleetqox rmw_wait subscriptions=%zu ready_subscriptions=%zu ready_services=%zu ready_clients=%zu any_ready=%s\n",
      subscriptions != nullptr ? subscriptions->subscriber_count : 0,
      ready_subscriptions,
      ready_services,
      ready_clients,
      any_ready ? "true" : "false");
  }
  return any_ready ? RMW_RET_OK : RMW_RET_TIMEOUT;
}

}  // extern "C"

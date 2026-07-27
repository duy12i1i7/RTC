#include <algorithm>
#include <chrono>
#include <cstdint>
#include <cstdlib>
#include <iostream>
#include <thread>
#include <vector>

#include "rcutils/allocator.h"
#include "rmw/init.h"
#include "rmw/init_options.h"
#include "rmw/qos_profiles.h"
#include "rmw/rmw.h"
#include "rosidl_typesupport_interface/macros.h"
#include "std_srvs/srv/detail/set_bool__functions.h"
#include "std_srvs/srv/detail/set_bool__rosidl_typesupport_introspection_c.h"
#include "std_srvs/srv/detail/set_bool__struct.h"

extern "C" std::uint64_t rmw_fleetqox_cpp_service_weighted_dequeues();

namespace
{

constexpr const char * kServiceName = "/fleetqox/service_weighted_fairness";
constexpr std::size_t kRequestsPerClient = 64;
constexpr std::size_t kMeasuredRequests = 40;
constexpr std::uint64_t kLowWeight = 1;
constexpr std::uint64_t kHighWeight = 3;

void cleanup_context(rmw_context_t * context, rmw_init_options_t * options)
{
  const rmw_ret_t shutdown_ret = rmw_shutdown(context);
  const rmw_ret_t context_fini_ret = rmw_context_fini(context);
  const rmw_ret_t options_fini_ret = rmw_init_options_fini(options);
  (void)shutdown_ret;
  (void)context_fini_ret;
  (void)options_fini_ret;
}

bool send_requests(const rmw_client_t * low_client, const rmw_client_t * high_client)
{
  if (low_client == nullptr || high_client == nullptr) {
    return false;
  }
  std_srvs__srv__SetBool_Request request;
  if (!std_srvs__srv__SetBool_Request__init(&request)) {
    return false;
  }
  bool ok = true;
  for (std::size_t index = 1; index <= kRequestsPerClient; ++index) {
    std::int64_t sequence = 0;
    request.data = false;
    ok = ok &&
      rmw_send_request(low_client, &request, &sequence) == RMW_RET_OK &&
      sequence == static_cast<std::int64_t>(index);
    request.data = true;
    ok = ok &&
      rmw_send_request(high_client, &request, &sequence) == RMW_RET_OK &&
      sequence == static_cast<std::int64_t>(index);
  }
  std_srvs__srv__SetBool_Request__fini(&request);
  return ok;
}

bool take_requests(
  const rmw_service_t * service,
  std::vector<std::int64_t> * order)
{
  if (service == nullptr || order == nullptr) {
    return false;
  }
  std_srvs__srv__SetBool_Request request;
  if (!std_srvs__srv__SetBool_Request__init(&request)) {
    return false;
  }
  bool ok = true;
  for (std::size_t index = 0; index < kMeasuredRequests; ++index) {
    rmw_service_info_t info{};
    bool taken = false;
    if (rmw_take_request(service, &info, &request, &taken) != RMW_RET_OK ||
      !taken)
    {
      ok = false;
      break;
    }
    order->push_back(
      request.data ?
      1000 + info.request_id.sequence_number :
      info.request_id.sequence_number);
  }
  std_srvs__srv__SetBool_Request__fini(&request);
  return ok;
}

bool per_client_fifo(const std::vector<std::int64_t> & order)
{
  std::int64_t previous_low = 0;
  std::int64_t previous_high = 1000;
  for (const std::int64_t sequence : order) {
    if (sequence >= 1000) {
      if (sequence <= previous_high) {
        return false;
      }
      previous_high = sequence;
    } else {
      if (sequence <= previous_low) {
        return false;
      }
      previous_low = sequence;
    }
  }
  return true;
}

std::size_t maximum_high_streak(const std::vector<std::int64_t> & order)
{
  std::size_t current = 0;
  std::size_t maximum = 0;
  for (const std::int64_t sequence : order) {
    if (sequence >= 1000) {
      ++current;
      maximum = std::max(maximum, current);
    } else {
      current = 0;
    }
  }
  return maximum;
}

}  // namespace

int main()
{
  rcutils_allocator_t allocator = rcutils_get_default_allocator();
  rmw_init_options_t options = rmw_get_zero_initialized_init_options();
  rmw_ret_t ret = rmw_init_options_init(&options, allocator);
  if (ret != RMW_RET_OK) {
    std::cout << "{\"status\":\"init_options_failed\"}" << std::endl;
    return 1;
  }
  options.instance_id = 95;
  rmw_context_t context = rmw_get_zero_initialized_context();
  ret = rmw_init(&options, &context);
  if (ret != RMW_RET_OK) {
    const rmw_ret_t fini_ret = rmw_init_options_fini(&options);
    (void)fini_ret;
    std::cout << "{\"status\":\"init_failed\"}" << std::endl;
    return 1;
  }

  rmw_node_t * node =
    rmw_create_node(&context, "fleetqox_service_weighted_fairness_probe", "/fleetqox");
  const rosidl_service_type_support_t * type_support =
    ROSIDL_TYPESUPPORT_INTERFACE__SERVICE_SYMBOL_NAME(
    rosidl_typesupport_introspection_c, std_srvs, srv, SetBool)();
  rmw_qos_profile_t qos = rmw_qos_profile_services_default;
  rmw_service_t * service =
    node == nullptr ? nullptr :
    rmw_create_service(node, type_support, kServiceName, &qos);

  setenv("FLEETQOX_RMW_SERVICE_CLIENT_WEIGHT", "1", 1);
  rmw_client_t * low_client =
    node == nullptr ? nullptr :
    rmw_create_client(node, type_support, kServiceName, &qos);
  setenv("FLEETQOX_RMW_SERVICE_CLIENT_WEIGHT", "3", 1);
  rmw_client_t * high_client =
    node == nullptr ? nullptr :
    rmw_create_client(node, type_support, kServiceName, &qos);
  unsetenv("FLEETQOX_RMW_SERVICE_CLIENT_WEIGHT");

  const bool setup_ok =
    node != nullptr && service != nullptr &&
    low_client != nullptr && high_client != nullptr;
  const bool send_ok = setup_ok && send_requests(low_client, high_client);
  if (send_ok) {
    std::this_thread::sleep_for(std::chrono::milliseconds(300));
  }
  std::vector<std::int64_t> order;
  const bool take_ok = send_ok && take_requests(service, &order);
  const std::size_t low_count = static_cast<std::size_t>(std::count_if(
      order.begin(), order.end(), [](std::int64_t sequence) {
        return sequence < 1000;
      }));
  const std::size_t high_count = order.size() - low_count;
  const std::size_t high_streak = maximum_high_streak(order);
  const bool ratio_ok = low_count == 10 && high_count == 30;
  const bool fifo_ok = per_client_fifo(order);
  const bool starvation_bound_ok = high_streak <= 3;
  const std::uint64_t weighted_dequeues =
    rmw_fleetqox_cpp_service_weighted_dequeues();

  const rmw_ret_t destroy_low_ret =
    low_client == nullptr ? RMW_RET_OK : rmw_destroy_client(node, low_client);
  const rmw_ret_t destroy_high_ret =
    high_client == nullptr ? RMW_RET_OK : rmw_destroy_client(node, high_client);
  const rmw_ret_t destroy_service_ret =
    service == nullptr ? RMW_RET_OK : rmw_destroy_service(node, service);
  const rmw_ret_t destroy_node_ret =
    node == nullptr ? RMW_RET_OK : rmw_destroy_node(node);
  const bool cleanup_ok =
    destroy_low_ret == RMW_RET_OK &&
    destroy_high_ret == RMW_RET_OK &&
    destroy_service_ret == RMW_RET_OK &&
    destroy_node_ret == RMW_RET_OK;
  cleanup_context(&context, &options);

  const bool ok =
    send_ok && take_ok && ratio_ok && fifo_ok && starvation_bound_ok &&
    weighted_dequeues == kMeasuredRequests && cleanup_ok;
  std::cout
    << "{\"schema_version\":\"fleetrmw.rmw_service_weighted_fairness_probe.v1\","
    << "\"status\":\"" << (ok ? "ok" : "failed") << "\","
    << "\"request_path\":\"rmw_send_request\","
    << "\"low_weight\":" << kLowWeight << ","
    << "\"high_weight\":" << kHighWeight << ","
    << "\"measured_requests\":" << order.size() << ","
    << "\"low_dequeues\":" << low_count << ","
    << "\"high_dequeues\":" << high_count << ","
    << "\"maximum_high_streak\":" << high_streak << ","
    << "\"weighted_dequeues\":" << weighted_dequeues << ","
    << "\"weighted_service_ratio_claim\":" << (ratio_ok ? "true" : "false") << ","
    << "\"per_client_fifo_claim\":" << (fifo_ok ? "true" : "false") << ","
    << "\"bounded_weighted_starvation_claim\":"
    << (starvation_bound_ok ? "true" : "false") << ","
    << "\"cleanup_ok\":" << (cleanup_ok ? "true" : "false") << "}"
    << std::endl;
  return ok ? 0 : 1;
}

#include <chrono>
#include <cstdint>
#include <cstdlib>
#include <iostream>
#include <vector>
#include <thread>

#include "rcutils/allocator.h"
#include "rmw/init.h"
#include "rmw/init_options.h"
#include "rmw/qos_profiles.h"
#include "rmw/rmw.h"
#include "rosidl_typesupport_interface/macros.h"
#include "std_srvs/srv/detail/set_bool__functions.h"
#include "std_srvs/srv/detail/set_bool__rosidl_typesupport_introspection_c.h"
#include "std_srvs/srv/detail/set_bool__struct.h"

extern "C" std::uint64_t rmw_fleetqox_cpp_service_deadline_dequeues();
extern "C" std::uint64_t rmw_fleetqox_cpp_service_deadline_aged_dequeues();

namespace
{

constexpr const char * kServiceName = "/fleetqox/service_deadline_scheduler";
constexpr std::uint64_t kUrgentDeadlineMs = 20;
constexpr std::uint64_t kRelaxedDeadlineMs = 200;
constexpr std::uint64_t kDeadlineAgingMs = 100;

void cleanup_context(rmw_context_t * context, rmw_init_options_t * options)
{
  const rmw_ret_t shutdown_ret = rmw_shutdown(context);
  const rmw_ret_t context_fini_ret = rmw_context_fini(context);
  const rmw_ret_t options_fini_ret = rmw_init_options_fini(options);
  (void)shutdown_ret;
  (void)context_fini_ret;
  (void)options_fini_ret;
}

bool send_request(
  const rmw_client_t * client,
  bool value,
  std::int64_t expected_sequence)
{
  if (client == nullptr) {
    return false;
  }
  std_srvs__srv__SetBool_Request request;
  if (!std_srvs__srv__SetBool_Request__init(&request)) {
    return false;
  }
  request.data = value;
  std::int64_t sequence = 0;
  const bool ok =
    rmw_send_request(client, &request, &sequence) == RMW_RET_OK &&
    sequence == expected_sequence;
  std_srvs__srv__SetBool_Request__fini(&request);
  return ok;
}

bool take_requests(
  const rmw_service_t * service,
  std::size_t count,
  std::vector<int> * order)
{
  if (service == nullptr || order == nullptr) {
    return false;
  }
  std_srvs__srv__SetBool_Request request;
  if (!std_srvs__srv__SetBool_Request__init(&request)) {
    return false;
  }
  bool ok = true;
  for (std::size_t index = 0; index < count; ++index) {
    rmw_service_info_t info{};
    bool taken = false;
    if (rmw_take_request(service, &info, &request, &taken) != RMW_RET_OK ||
      !taken)
    {
      ok = false;
      break;
    }
    order->push_back(request.data ? 1 : 0);
  }
  std_srvs__srv__SetBool_Request__fini(&request);
  return ok;
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
  options.instance_id = 96;
  rmw_context_t context = rmw_get_zero_initialized_context();
  ret = rmw_init(&options, &context);
  if (ret != RMW_RET_OK) {
    const rmw_ret_t fini_ret = rmw_init_options_fini(&options);
    (void)fini_ret;
    std::cout << "{\"status\":\"init_failed\"}" << std::endl;
    return 1;
  }

  rmw_node_t * node =
    rmw_create_node(&context, "fleetqox_service_deadline_probe", "/fleetqox");
  const rosidl_service_type_support_t * type_support =
    ROSIDL_TYPESUPPORT_INTERFACE__SERVICE_SYMBOL_NAME(
    rosidl_typesupport_introspection_c, std_srvs, srv, SetBool)();
  rmw_qos_profile_t qos = rmw_qos_profile_services_default;
  rmw_service_t * service =
    node == nullptr ? nullptr :
    rmw_create_service(node, type_support, kServiceName, &qos);

  setenv("FLEETQOX_RMW_SERVICE_CLIENT_DEADLINE_MS", "200", 1);
  rmw_client_t * relaxed_client =
    node == nullptr ? nullptr :
    rmw_create_client(node, type_support, kServiceName, &qos);
  setenv("FLEETQOX_RMW_SERVICE_CLIENT_DEADLINE_MS", "20", 1);
  rmw_client_t * urgent_client =
    node == nullptr ? nullptr :
    rmw_create_client(node, type_support, kServiceName, &qos);
  setenv("FLEETQOX_RMW_SERVICE_CLIENT_DEADLINE_MS", "0", 1);
  rmw_client_t * background_client =
    node == nullptr ? nullptr :
    rmw_create_client(node, type_support, kServiceName, &qos);
  unsetenv("FLEETQOX_RMW_SERVICE_CLIENT_DEADLINE_MS");

  const bool setup_ok =
    node != nullptr && service != nullptr &&
    relaxed_client != nullptr && urgent_client != nullptr &&
    background_client != nullptr;
  bool exercise_ok =
    setup_ok &&
    send_request(relaxed_client, false, 1) &&
    send_request(urgent_client, true, 1);
  if (exercise_ok) {
    std::this_thread::sleep_for(std::chrono::milliseconds(100));
  }
  std::vector<int> deadline_order;
  exercise_ok = exercise_ok && take_requests(service, 2, &deadline_order);

  exercise_ok = exercise_ok && send_request(background_client, false, 1);
  if (exercise_ok) {
    std::this_thread::sleep_for(std::chrono::milliseconds(150));
  }
  exercise_ok = exercise_ok && send_request(urgent_client, true, 2);
  if (exercise_ok) {
    std::this_thread::sleep_for(std::chrono::milliseconds(100));
  }
  std::vector<int> aging_order;
  exercise_ok = exercise_ok && take_requests(service, 2, &aging_order);

  const std::uint64_t deadline_dequeues =
    rmw_fleetqox_cpp_service_deadline_dequeues();
  const std::uint64_t aged_dequeues =
    rmw_fleetqox_cpp_service_deadline_aged_dequeues();
  const bool edf_ok = deadline_order == std::vector<int>({1, 0});
  const bool aging_ok =
    aging_order == std::vector<int>({0, 1}) && aged_dequeues == 1;

  const rmw_ret_t destroy_relaxed_ret =
    relaxed_client == nullptr ? RMW_RET_OK :
    rmw_destroy_client(node, relaxed_client);
  const rmw_ret_t destroy_urgent_ret =
    urgent_client == nullptr ? RMW_RET_OK :
    rmw_destroy_client(node, urgent_client);
  const rmw_ret_t destroy_background_ret =
    background_client == nullptr ? RMW_RET_OK :
    rmw_destroy_client(node, background_client);
  const rmw_ret_t destroy_service_ret =
    service == nullptr ? RMW_RET_OK : rmw_destroy_service(node, service);
  const rmw_ret_t destroy_node_ret =
    node == nullptr ? RMW_RET_OK : rmw_destroy_node(node);
  const bool cleanup_ok =
    destroy_relaxed_ret == RMW_RET_OK &&
    destroy_urgent_ret == RMW_RET_OK &&
    destroy_background_ret == RMW_RET_OK &&
    destroy_service_ret == RMW_RET_OK &&
    destroy_node_ret == RMW_RET_OK;
  cleanup_context(&context, &options);

  const bool ok =
    exercise_ok && edf_ok && aging_ok &&
    deadline_dequeues == 4 && cleanup_ok;
  std::cout
    << "{\"schema_version\":\"fleetrmw.rmw_service_deadline_scheduler_probe.v1\","
    << "\"status\":\"" << (ok ? "ok" : "failed") << "\","
    << "\"request_path\":\"rmw_send_request\","
    << "\"urgent_deadline_ms\":" << kUrgentDeadlineMs << ","
    << "\"relaxed_deadline_ms\":" << kRelaxedDeadlineMs << ","
    << "\"deadline_aging_ms\":" << kDeadlineAgingMs << ","
    << "\"deadline_order\":[";
  for (std::size_t index = 0; index < deadline_order.size(); ++index) {
    if (index > 0) {
      std::cout << ",";
    }
    std::cout << deadline_order[index];
  }
  std::cout << "],\"aging_order\":[";
  for (std::size_t index = 0; index < aging_order.size(); ++index) {
    if (index > 0) {
      std::cout << ",";
    }
    std::cout << aging_order[index];
  }
  std::cout
    << "],\"deadline_dequeues\":" << deadline_dequeues << ","
    << "\"deadline_aged_dequeues\":" << aged_dequeues << ","
    << "\"earliest_deadline_first_claim\":" << (edf_ok ? "true" : "false") << ","
    << "\"deadline_aging_starvation_bound_claim\":"
    << (aging_ok ? "true" : "false") << ","
    << "\"cleanup_ok\":" << (cleanup_ok ? "true" : "false") << "}"
    << std::endl;
  return ok ? 0 : 1;
}

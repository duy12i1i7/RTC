#include "rmw_fleetqox_cpp/data_frame.hpp"

#include <chrono>
#include <cstdint>
#include <iostream>
#include <string>
#include <thread>
#include <vector>

#include "rcutils/allocator.h"
#include "rmw/init.h"
#include "rmw/init_options.h"
#include "rmw/qos_profiles.h"
#include "rmw/rmw.h"
#include "rmw/serialized_message.h"
#include "rosidl_typesupport_interface/macros.h"
#include "std_srvs/srv/detail/set_bool__functions.h"
#include "std_srvs/srv/detail/set_bool__rosidl_typesupport_introspection_c.h"
#include "std_srvs/srv/detail/set_bool__struct.h"

extern "C" bool rmw_fleetqox_cpp_handle_service_frame(const char * encoded_frame, size_t size);
extern "C" const char * rmw_fleetqox_cpp_client_endpoint_id(const rmw_client_t * client);
extern "C" std::uint64_t rmw_fleetqox_cpp_service_priority_dequeues();
extern "C" std::uint64_t rmw_fleetqox_cpp_service_aged_priority_dequeues();

namespace
{

constexpr const char * kServiceName = "/fleetqox/service_priority";
constexpr const char * kServiceType = "std_srvs/srv/SetBool";

void cleanup_context(rmw_context_t * context, rmw_init_options_t * options)
{
  const rmw_ret_t shutdown_ret = rmw_shutdown(context);
  const rmw_ret_t context_fini_ret = rmw_context_fini(context);
  const rmw_ret_t options_fini_ret = rmw_init_options_fini(options);
  (void)shutdown_ret;
  (void)context_fini_ret;
  (void)options_fini_ret;
}

bool serialize_request(std::vector<std::uint8_t> * payload)
{
  if (payload == nullptr) {
    return false;
  }
  std_srvs__srv__SetBool_Request request;
  if (!std_srvs__srv__SetBool_Request__init(&request)) {
    return false;
  }
  request.data = true;
  const rosidl_message_type_support_t * type_support =
    ROSIDL_TYPESUPPORT_INTERFACE__MESSAGE_SYMBOL_NAME(
    rosidl_typesupport_introspection_c, std_srvs, srv, SetBool_Request)();
  rcutils_allocator_t allocator = rcutils_get_default_allocator();
  rmw_serialized_message_t serialized = rmw_get_zero_initialized_serialized_message();
  const bool initialized =
    rmw_serialized_message_init(&serialized, 0, &allocator) == RMW_RET_OK;
  const bool serialized_ok =
    initialized && rmw_serialize(&request, type_support, &serialized) == RMW_RET_OK;
  if (serialized_ok) {
    payload->assign(serialized.buffer, serialized.buffer + serialized.buffer_length);
  }
  if (initialized) {
    const rmw_ret_t fini_ret = rmw_serialized_message_fini(&serialized);
    (void)fini_ret;
  }
  std_srvs__srv__SetBool_Request__fini(&request);
  return serialized_ok;
}

bool inject_request(
  const std::string & client_endpoint_id,
  const std::vector<std::uint8_t> & payload,
  std::int64_t sequence_id,
  std::uint64_t priority,
  std::size_t domain_id)
{
  rmw_fleetqox_cpp::ServiceFrame frame{
    "request",
    kServiceName,
    kServiceType,
    client_endpoint_id,
    "",
    sequence_id,
    3000000 + sequence_id,
    0,
    payload,
    domain_id};
  frame.client_priority = priority;
  const std::string encoded = rmw_fleetqox_cpp::encode_service_frame(frame);
  return rmw_fleetqox_cpp_handle_service_frame(encoded.data(), encoded.size());
}

bool take_requests(
  const rmw_service_t * service,
  size_t count,
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
  for (size_t index = 0; index < count; ++index) {
    rmw_service_info_t info{};
    bool taken = false;
    if (rmw_take_request(service, &info, &request, &taken) != RMW_RET_OK ||
      !taken || !request.data)
    {
      ok = false;
      break;
    }
    order->push_back(info.request_id.sequence_number);
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
  options.instance_id = 94;
  rmw_context_t context = rmw_get_zero_initialized_context();
  ret = rmw_init(&options, &context);
  if (ret != RMW_RET_OK) {
    const rmw_ret_t fini_ret = rmw_init_options_fini(&options);
    (void)fini_ret;
    std::cout << "{\"status\":\"init_failed\"}" << std::endl;
    return 1;
  }

  rmw_node_t * node =
    rmw_create_node(&context, "fleetqox_service_priority_probe", "/fleetqox");
  const rosidl_service_type_support_t * type_support =
    ROSIDL_TYPESUPPORT_INTERFACE__SERVICE_SYMBOL_NAME(
    rosidl_typesupport_introspection_c, std_srvs, srv, SetBool)();
  rmw_qos_profile_t qos = rmw_qos_profile_services_default;
  rmw_service_t * service =
    node == nullptr ? nullptr :
    rmw_create_service(node, type_support, kServiceName, &qos);
  rmw_client_t * low_client =
    node == nullptr ? nullptr :
    rmw_create_client(node, type_support, kServiceName, &qos);
  rmw_client_t * normal_client =
    node == nullptr ? nullptr :
    rmw_create_client(node, type_support, kServiceName, &qos);
  rmw_client_t * high_client =
    node == nullptr ? nullptr :
    rmw_create_client(node, type_support, kServiceName, &qos);
  std::vector<std::uint8_t> payload;
  const bool setup_ok =
    node != nullptr && service != nullptr &&
    low_client != nullptr && normal_client != nullptr && high_client != nullptr &&
    serialize_request(&payload);

  const std::string low_endpoint =
    low_client == nullptr ? "" : rmw_fleetqox_cpp_client_endpoint_id(low_client);
  const std::string normal_endpoint =
    normal_client == nullptr ? "" : rmw_fleetqox_cpp_client_endpoint_id(normal_client);
  const std::string high_endpoint =
    high_client == nullptr ? "" : rmw_fleetqox_cpp_client_endpoint_id(high_client);
  std::vector<std::int64_t> priority_order;
  std::vector<std::int64_t> aging_order;
  bool exercise_ok = setup_ok;
  if (exercise_ok) {
    exercise_ok = exercise_ok &&
      inject_request(low_endpoint, payload, 1, 0, context.actual_domain_id) &&
      inject_request(normal_endpoint, payload, 100, 5, context.actual_domain_id) &&
      inject_request(high_endpoint, payload, 200, 10, context.actual_domain_id) &&
      take_requests(service, 3, &priority_order);

    exercise_ok = exercise_ok &&
      inject_request(low_endpoint, payload, 2, 0, context.actual_domain_id);
    std::this_thread::sleep_for(std::chrono::milliseconds(120));
    exercise_ok = exercise_ok &&
      inject_request(high_endpoint, payload, 201, 10, context.actual_domain_id) &&
      take_requests(service, 2, &aging_order);
  }

  const std::uint64_t priority_dequeues =
    rmw_fleetqox_cpp_service_priority_dequeues();
  const std::uint64_t aged_dequeues =
    rmw_fleetqox_cpp_service_aged_priority_dequeues();
  const bool strict_priority_ok =
    priority_order == std::vector<std::int64_t>({200, 100, 1});
  const bool starvation_bound_ok =
    aging_order == std::vector<std::int64_t>({2, 201}) &&
    aged_dequeues >= 1;

  const rmw_ret_t destroy_low_ret =
    low_client == nullptr ? RMW_RET_OK : rmw_destroy_client(node, low_client);
  const rmw_ret_t destroy_normal_ret =
    normal_client == nullptr ? RMW_RET_OK : rmw_destroy_client(node, normal_client);
  const rmw_ret_t destroy_high_ret =
    high_client == nullptr ? RMW_RET_OK : rmw_destroy_client(node, high_client);
  const rmw_ret_t destroy_service_ret =
    service == nullptr ? RMW_RET_OK : rmw_destroy_service(node, service);
  const rmw_ret_t destroy_node_ret =
    node == nullptr ? RMW_RET_OK : rmw_destroy_node(node);
  const bool cleanup_ok =
    destroy_low_ret == RMW_RET_OK &&
    destroy_normal_ret == RMW_RET_OK &&
    destroy_high_ret == RMW_RET_OK &&
    destroy_service_ret == RMW_RET_OK &&
    destroy_node_ret == RMW_RET_OK;
  cleanup_context(&context, &options);

  const bool ok =
    exercise_ok && strict_priority_ok && starvation_bound_ok &&
    priority_dequeues >= 3 && cleanup_ok;
  std::cout << "{\"schema_version\":\"fleetrmw.rmw_service_priority_probe.v1\","
            << "\"status\":\"" << (ok ? "ok" : "failed") << "\","
            << "\"priority_aging_ms\":10,"
            << "\"priority_order\":[";
  for (size_t index = 0; index < priority_order.size(); ++index) {
    if (index > 0) {
      std::cout << ",";
    }
    std::cout << priority_order[index];
  }
  std::cout << "],\"aging_order\":[";
  for (size_t index = 0; index < aging_order.size(); ++index) {
    if (index > 0) {
      std::cout << ",";
    }
    std::cout << aging_order[index];
  }
  std::cout << "],\"priority_dequeues\":" << priority_dequeues << ","
            << "\"aged_priority_dequeues\":" << aged_dequeues << ","
            << "\"strict_priority_claim\":"
            << (strict_priority_ok ? "true" : "false") << ","
            << "\"aging_starvation_bound_claim\":"
            << (starvation_bound_ok ? "true" : "false") << ","
            << "\"cleanup_ok\":" << (cleanup_ok ? "true" : "false") << "}"
            << std::endl;
  return ok ? 0 : 1;
}

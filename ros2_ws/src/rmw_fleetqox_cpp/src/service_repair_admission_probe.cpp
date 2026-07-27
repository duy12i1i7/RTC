#include <cstdint>
#include <iostream>
#include <set>

#include "rcutils/allocator.h"
#include "rmw/init.h"
#include "rmw/init_options.h"
#include "rmw/qos_profiles.h"
#include "rmw/rmw.h"
#include "rosidl_typesupport_interface/macros.h"
#include "std_srvs/srv/detail/set_bool__functions.h"
#include "std_srvs/srv/detail/set_bool__rosidl_typesupport_introspection_c.h"
#include "std_srvs/srv/detail/set_bool__struct.h"

extern "C" std::uint64_t rmw_fleetqox_cpp_service_request_repairs_scheduled();
extern "C" std::uint64_t rmw_fleetqox_cpp_service_request_repairs_cancelled();
extern "C" std::uint64_t
rmw_fleetqox_cpp_service_request_repair_global_admission_rejections();
extern "C" std::uint64_t
rmw_fleetqox_cpp_service_request_repair_client_admission_rejections();
extern "C" std::uint64_t
rmw_fleetqox_cpp_service_request_repair_pending_max_observed();

namespace
{

constexpr const char * kServiceName = "/fleetqox/service_repair_admission";

void cleanup_context(rmw_context_t * context, rmw_init_options_t * options)
{
  const rmw_ret_t shutdown_ret = rmw_shutdown(context);
  const rmw_ret_t context_fini_ret = rmw_context_fini(context);
  const rmw_ret_t options_fini_ret = rmw_init_options_fini(options);
  (void)shutdown_ret;
  (void)context_fini_ret;
  (void)options_fini_ret;
}

bool send_requests(
  const rmw_client_t * client,
  std::int64_t count,
  std::set<std::int64_t> * sequences)
{
  if (client == nullptr || sequences == nullptr) {
    return false;
  }
  std_srvs__srv__SetBool_Request request;
  if (!std_srvs__srv__SetBool_Request__init(&request)) {
    return false;
  }
  request.data = true;
  bool ok = true;
  for (std::int64_t index = 0; index < count; ++index) {
    std::int64_t sequence = 0;
    if (rmw_send_request(client, &request, &sequence) != RMW_RET_OK ||
      !sequences->insert(sequence).second)
    {
      ok = false;
      break;
    }
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
  options.instance_id = 93;
  rmw_context_t context = rmw_get_zero_initialized_context();
  ret = rmw_init(&options, &context);
  if (ret != RMW_RET_OK) {
    const rmw_ret_t fini_ret = rmw_init_options_fini(&options);
    (void)fini_ret;
    std::cout << "{\"status\":\"init_failed\"}" << std::endl;
    return 1;
  }

  rmw_node_t * node =
    rmw_create_node(&context, "fleetqox_service_repair_admission_probe", "/fleetqox");
  const rosidl_service_type_support_t * type_support =
    ROSIDL_TYPESUPPORT_INTERFACE__SERVICE_SYMBOL_NAME(
    rosidl_typesupport_introspection_c, std_srvs, srv, SetBool)();
  rmw_qos_profile_t qos = rmw_qos_profile_services_default;
  rmw_service_t * service =
    node == nullptr ? nullptr :
    rmw_create_service(node, type_support, kServiceName, &qos);
  rmw_client_t * first_client =
    node == nullptr ? nullptr :
    rmw_create_client(node, type_support, kServiceName, &qos);
  rmw_client_t * second_client =
    node == nullptr ? nullptr :
    rmw_create_client(node, type_support, kServiceName, &qos);

  std::set<std::int64_t> first_sequences;
  std::set<std::int64_t> second_sequences;
  const bool setup_ok =
    node != nullptr && service != nullptr &&
    first_client != nullptr && second_client != nullptr;
  const bool sends_ok =
    setup_ok &&
    send_requests(first_client, 4, &first_sequences) &&
    send_requests(second_client, 4, &second_sequences);

  const std::uint64_t repairs_scheduled =
    rmw_fleetqox_cpp_service_request_repairs_scheduled();
  const std::uint64_t global_rejections =
    rmw_fleetqox_cpp_service_request_repair_global_admission_rejections();
  const std::uint64_t client_rejections =
    rmw_fleetqox_cpp_service_request_repair_client_admission_rejections();
  const std::uint64_t pending_max =
    rmw_fleetqox_cpp_service_request_repair_pending_max_observed();

  const rmw_ret_t destroy_first_ret =
    first_client == nullptr ? RMW_RET_OK : rmw_destroy_client(node, first_client);
  const rmw_ret_t destroy_second_ret =
    second_client == nullptr ? RMW_RET_OK : rmw_destroy_client(node, second_client);
  const std::uint64_t repairs_cancelled =
    rmw_fleetqox_cpp_service_request_repairs_cancelled();
  const rmw_ret_t destroy_service_ret =
    service == nullptr ? RMW_RET_OK : rmw_destroy_service(node, service);
  const rmw_ret_t destroy_node_ret =
    node == nullptr ? RMW_RET_OK : rmw_destroy_node(node);
  const bool cleanup_ok =
    destroy_first_ret == RMW_RET_OK &&
    destroy_second_ret == RMW_RET_OK &&
    destroy_service_ret == RMW_RET_OK &&
    destroy_node_ret == RMW_RET_OK;
  cleanup_context(&context, &options);

  const bool sequences_ok =
    first_sequences == std::set<std::int64_t>({1, 2, 3, 4}) &&
    second_sequences == std::set<std::int64_t>({1, 2, 3, 4});
  const bool admission_ok =
    repairs_scheduled == 4 &&
    client_rejections == 1 &&
    global_rejections == 3 &&
    pending_max == 4 &&
    repairs_cancelled == 4;
  const bool ok =
    sends_ok && sequences_ok && admission_ok && cleanup_ok;

  std::cout << "{\"schema_version\":\"fleetrmw.rmw_service_repair_admission_probe.v1\","
            << "\"status\":\"" << (ok ? "ok" : "failed") << "\","
            << "\"client_count\":2,"
            << "\"requests_per_client\":4,"
            << "\"initial_sends_ok\":" << (sends_ok ? "true" : "false") << ","
            << "\"repair_pending_limit\":4,"
            << "\"repair_per_client_pending_limit\":3,"
            << "\"repairs_scheduled\":" << repairs_scheduled << ","
            << "\"repair_client_admission_rejections\":" << client_rejections << ","
            << "\"repair_global_admission_rejections\":" << global_rejections << ","
            << "\"repair_pending_max_observed\":" << pending_max << ","
            << "\"repairs_cancelled_on_destroy\":" << repairs_cancelled << ","
            << "\"cleanup_ok\":" << (cleanup_ok ? "true" : "false") << "}"
            << std::endl;
  return ok ? 0 : 1;
}

#include "rmw_fleetqox_cpp/data_frame.hpp"

#include <cstdint>
#include <iostream>
#include <sstream>
#include <string>

#include "rcutils/allocator.h"
#include "rmw/error_handling.h"
#include "rmw/init.h"
#include "rmw/init_options.h"
#include "rmw/qos_profiles.h"
#include "rmw/rmw.h"
#include "rosidl_typesupport_interface/macros.h"
#include "std_srvs/srv/detail/set_bool__functions.h"
#include "std_srvs/srv/detail/set_bool__rosidl_typesupport_introspection_c.h"
#include "std_srvs/srv/detail/set_bool__struct.h"

extern "C" bool rmw_fleetqox_cpp_handle_service_frame(const char * encoded_frame, size_t size);
extern "C" const char * rmw_fleetqox_cpp_service_endpoint_id(const rmw_service_t * service);
extern "C" const char * rmw_fleetqox_cpp_client_endpoint_id(const rmw_client_t * client);

namespace
{

std::string json_escape(const std::string & value)
{
  std::ostringstream out;
  for (const char c : value) {
    if (c == '\\' || c == '"') {
      out << '\\' << c;
    } else if (c == '\n') {
      out << "\\n";
    } else {
      out << c;
    }
  }
  return out.str();
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
  rcutils_allocator_t allocator = rcutils_get_default_allocator();
  rmw_init_options_t options = rmw_get_zero_initialized_init_options();
  rmw_ret_t ret = rmw_init_options_init(&options, allocator);
  if (ret != RMW_RET_OK) {
    std::cout << "{\"status\":\"init_options_failed\",\"ret\":" << ret << "}" << std::endl;
    return 1;
  }
  options.instance_id = 48;

  rmw_context_t context = rmw_get_zero_initialized_context();
  ret = rmw_init(&options, &context);
  if (ret != RMW_RET_OK) {
    const rmw_ret_t fini_ret = rmw_init_options_fini(&options);
    (void)fini_ret;
    std::cout << "{\"status\":\"init_failed\",\"ret\":" << ret << "}" << std::endl;
    return 1;
  }

  rmw_node_t * node = rmw_create_node(&context, "fleetqox_service_error_probe", "/fleetqox");
  if (node == nullptr) {
    cleanup_context(&context, &options);
    std::cout << "{\"status\":\"create_node_failed\"}" << std::endl;
    return 1;
  }

  const rosidl_service_type_support_t * type_support =
    ROSIDL_TYPESUPPORT_INTERFACE__SERVICE_SYMBOL_NAME(
    rosidl_typesupport_introspection_c, std_srvs, srv, SetBool)();
  rmw_qos_profile_t qos = rmw_qos_profile_default;
  const char * service_name = "/fleetqox/service_error_probe";
  rmw_service_t * service = rmw_create_service(node, type_support, service_name, &qos);
  rmw_client_t * client = rmw_create_client(node, type_support, service_name, &qos);
  if (service == nullptr || client == nullptr) {
    if (client != nullptr) {
      const rmw_ret_t destroy_client_ret = rmw_destroy_client(node, client);
      (void)destroy_client_ret;
    }
    if (service != nullptr) {
      const rmw_ret_t destroy_service_ret = rmw_destroy_service(node, service);
      (void)destroy_service_ret;
    }
    const rmw_ret_t destroy_node_ret = rmw_destroy_node(node);
    (void)destroy_node_ret;
    cleanup_context(&context, &options);
    std::cout << "{\"status\":\"create_service_client_failed\"}" << std::endl;
    return 1;
  }

  std_srvs__srv__SetBool_Response taken_response;
  if (!std_srvs__srv__SetBool_Response__init(&taken_response)) {
    std::cout << "{\"status\":\"message_init_failed\"}" << std::endl;
    return 1;
  }

  const std::string service_endpoint_id = rmw_fleetqox_cpp_service_endpoint_id(service);
  const std::string client_endpoint_id = rmw_fleetqox_cpp_client_endpoint_id(client);

  rmw_service_info_t empty_info{};
  bool empty_response_taken = false;
  const rmw_ret_t empty_take_ret =
    rmw_take_response(client, &empty_info, &taken_response, &empty_response_taken);

  const rmw_fleetqox_cpp::ServiceFrame malformed_response{
    "response",
    service_name,
    "std_srvs/srv/SetBool",
    client_endpoint_id,
    service_endpoint_id,
    77,
    1000000,
    0,
    {0x01, 0x02, 0x03}};
  const std::string malformed_encoded = rmw_fleetqox_cpp::encode_service_frame(malformed_response);
  const bool malformed_frame_handled =
    rmw_fleetqox_cpp_handle_service_frame(malformed_encoded.data(), malformed_encoded.size());

  rmw_service_info_t malformed_info{};
  bool malformed_response_taken = true;
  const rmw_ret_t malformed_take_ret =
    rmw_take_response(client, &malformed_info, &taken_response, &malformed_response_taken);
  if (malformed_take_ret != RMW_RET_OK) {
    rmw_reset_error();
  }

  rmw_service_info_t post_malformed_info{};
  bool post_malformed_taken = true;
  const rmw_ret_t post_malformed_take_ret =
    rmw_take_response(client, &post_malformed_info, &taken_response, &post_malformed_taken);

  const std::string invalid_frame = "not-a-fleetrmw-service-frame";
  const bool invalid_frame_accepted =
    rmw_fleetqox_cpp_handle_service_frame(invalid_frame.data(), invalid_frame.size());
  rmw_service_info_t after_invalid_info{};
  bool after_invalid_taken = true;
  const rmw_ret_t after_invalid_take_ret =
    rmw_take_response(client, &after_invalid_info, &taken_response, &after_invalid_taken);

  std_srvs__srv__SetBool_Response__fini(&taken_response);

  const rmw_ret_t destroy_client_ret = rmw_destroy_client(node, client);
  const rmw_ret_t destroy_service_ret = rmw_destroy_service(node, service);
  const rmw_ret_t destroy_node_ret = rmw_destroy_node(node);
  cleanup_context(&context, &options);

  const bool endpoint_ids_ok = !service_endpoint_id.empty() && !client_endpoint_id.empty();
  const bool empty_take_ok = empty_take_ret == RMW_RET_OK && !empty_response_taken;
  const bool malformed_response_ok =
    malformed_frame_handled &&
    malformed_take_ret == RMW_RET_UNSUPPORTED &&
    !malformed_response_taken &&
    post_malformed_take_ret == RMW_RET_OK &&
    !post_malformed_taken;
  const bool invalid_frame_ok =
    !invalid_frame_accepted &&
    after_invalid_take_ret == RMW_RET_OK &&
    !after_invalid_taken;
  const bool cleanup_ok =
    destroy_client_ret == RMW_RET_OK &&
    destroy_service_ret == RMW_RET_OK &&
    destroy_node_ret == RMW_RET_OK;
  const bool ok =
    endpoint_ids_ok && empty_take_ok && malformed_response_ok && invalid_frame_ok && cleanup_ok;

  std::cout << "{\"schema_version\":\"fleetrmw.rmw_service_error_probe.v1\",";
  std::cout << "\"status\":\"" << (ok ? "ok" : "failed") << "\",";
  std::cout << "\"service\":\"" << json_escape(service_name) << "\",";
  std::cout << "\"service_endpoint_id\":\"" << json_escape(service_endpoint_id) << "\",";
  std::cout << "\"client_endpoint_id\":\"" << json_escape(client_endpoint_id) << "\",";
  std::cout << "\"empty_response_take_ret\":" << empty_take_ret << ",";
  std::cout << "\"empty_response_taken\":" << (empty_response_taken ? "true" : "false") << ",";
  std::cout << "\"malformed_frame_handled\":" << (malformed_frame_handled ? "true" : "false") << ",";
  std::cout << "\"malformed_response_take_ret\":" << malformed_take_ret << ",";
  std::cout << "\"malformed_response_error\":"
            << (malformed_take_ret == RMW_RET_UNSUPPORTED ? "true" : "false") << ",";
  std::cout << "\"malformed_response_taken\":"
            << (malformed_response_taken ? "true" : "false") << ",";
  std::cout << "\"post_malformed_response_taken\":"
            << (post_malformed_taken ? "true" : "false") << ",";
  std::cout << "\"invalid_frame_rejected\":"
            << (!invalid_frame_accepted ? "true" : "false") << ",";
  std::cout << "\"after_invalid_response_taken\":"
            << (after_invalid_taken ? "true" : "false") << ",";
  std::cout << "\"cleanup_ok\":" << (cleanup_ok ? "true" : "false") << "}" << std::endl;

  return ok ? 0 : 1;
}

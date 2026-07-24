#include <chrono>
#include <cstdint>
#include <cstring>
#include <cstdlib>
#include <iostream>
#include <string>
#include <thread>

#include "rcutils/allocator.h"
#include "rcutils/strdup.h"
#include "rmw/error_handling.h"
#include "rmw/init.h"
#include "rmw/init_options.h"
#include "rmw/qos_profiles.h"
#include "rmw/rmw.h"
#include "rosidl_runtime_c/string_functions.h"
#include "rosidl_typesupport_interface/macros.h"
#include "std_srvs/srv/detail/set_bool__functions.h"
#include "std_srvs/srv/detail/set_bool__rosidl_typesupport_introspection_c.h"
#include "std_srvs/srv/detail/set_bool__struct.h"

extern "C" std::uint64_t rmw_fleetqox_cpp_sros2_service_request_publish_allowed();
extern "C" std::uint64_t rmw_fleetqox_cpp_sros2_service_request_publish_denied();
extern "C" std::uint64_t rmw_fleetqox_cpp_sros2_service_request_subscribe_allowed();
extern "C" std::uint64_t rmw_fleetqox_cpp_sros2_service_request_subscribe_denied();
extern "C" std::uint64_t rmw_fleetqox_cpp_sros2_service_response_publish_allowed();
extern "C" std::uint64_t rmw_fleetqox_cpp_sros2_service_response_publish_denied();
extern "C" std::uint64_t rmw_fleetqox_cpp_sros2_service_response_subscribe_allowed();
extern "C" std::uint64_t rmw_fleetqox_cpp_sros2_service_response_subscribe_denied();
extern "C" std::uint64_t rmw_fleetqox_cpp_sros2_service_authorization_parse_errors();
extern "C" bool rmw_fleetqox_cpp_sros2_permissions_xml_loaded();
extern "C" bool rmw_fleetqox_cpp_sros2_runtime_signature_verified();

namespace
{

constexpr const char * kSchema = "fleetrmw.sros2_service_permissions_probe.v1";
constexpr const char * kEnclave = "/fleetqox/security_probe";
constexpr std::size_t kDomainId = 7;
constexpr const char * kAllowedService = "/fleetqox/sros2_allowed_service";
constexpr const char * kRequestDeniedService =
  "/fleetqox/sros2_request_denied_service";
constexpr const char * kResponseDeniedService =
  "/fleetqox/sros2_response_denied_service";
constexpr const char * kDefaultDeniedService =
  "/fleetqox/sros2_default_denied_service";

void replace_enclave(rmw_init_options_t * options, const char * enclave)
{
  if (options == nullptr) {
    return;
  }
  if (options->enclave != nullptr && options->allocator.deallocate != nullptr) {
    options->allocator.deallocate(const_cast<char *>(options->enclave), options->allocator.state);
  }
  options->enclave = rcutils_strdup(enclave, options->allocator);
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

bool assign_response_message(
  std_srvs__srv__SetBool_Response * response,
  const char * text)
{
  return response != nullptr && text != nullptr &&
         rosidl_runtime_c__String__assign(&response->message, text);
}

bool wait_take_request(
  const rmw_service_t * service,
  rmw_service_info_t * info,
  std_srvs__srv__SetBool_Request * request,
  rmw_ret_t * take_ret)
{
  bool taken = false;
  for (int attempt = 0; attempt < 200 && !taken; ++attempt) {
    *take_ret = rmw_take_request(service, info, request, &taken);
    if (*take_ret != RMW_RET_OK || taken) {
      break;
    }
    std::this_thread::sleep_for(std::chrono::milliseconds(1));
  }
  return taken;
}

bool wait_take_response(
  const rmw_client_t * client,
  rmw_service_info_t * info,
  std_srvs__srv__SetBool_Response * response,
  rmw_ret_t * take_ret)
{
  bool taken = false;
  for (int attempt = 0; attempt < 200 && !taken; ++attempt) {
    *take_ret = rmw_take_response(client, info, response, &taken);
    if (*take_ret != RMW_RET_OK || taken) {
      break;
    }
    std::this_thread::sleep_for(std::chrono::milliseconds(1));
  }
  return taken;
}

bool take_request_once_empty(
  const rmw_service_t * service,
  std_srvs__srv__SetBool_Request * request)
{
  rmw_service_info_t info{};
  bool taken = true;
  return rmw_take_request(service, &info, request, &taken) == RMW_RET_OK && !taken;
}

bool take_response_once_empty(
  const rmw_client_t * client,
  std_srvs__srv__SetBool_Response * response)
{
  rmw_service_info_t info{};
  bool taken = true;
  return rmw_take_response(client, &info, response, &taken) == RMW_RET_OK && !taken;
}

}  // namespace

int main()
{
  rcutils_allocator_t allocator = rcutils_get_default_allocator();
  rmw_init_options_t options = rmw_get_zero_initialized_init_options();
  if (rmw_init_options_init(&options, allocator) != RMW_RET_OK) {
    std::cout << "{\"status\":\"init_options_failed\"}" << std::endl;
    return 1;
  }
  options.instance_id = 89;
  options.domain_id = kDomainId;
  replace_enclave(&options, kEnclave);
  if (options.enclave == nullptr) {
    const rmw_ret_t fini_ret = rmw_init_options_fini(&options);
    (void)fini_ret;
    std::cout << "{\"status\":\"enclave_allocation_failed\"}" << std::endl;
    return 1;
  }

  rmw_context_t context = rmw_get_zero_initialized_context();
  if (rmw_init(&options, &context) != RMW_RET_OK) {
    const rmw_ret_t fini_ret = rmw_init_options_fini(&options);
    (void)fini_ret;
    std::cout << "{\"status\":\"init_failed\"}" << std::endl;
    return 1;
  }
  rmw_node_t * node = rmw_create_node(
    &context, "sros2_service_permissions_probe", "/fleetqox");
  if (node == nullptr) {
    cleanup_context(&context, &options);
    std::cout << "{\"status\":\"create_node_failed\"}" << std::endl;
    return 1;
  }

  const rosidl_service_type_support_t * type_support =
    ROSIDL_TYPESUPPORT_INTERFACE__SERVICE_SYMBOL_NAME(
    rosidl_typesupport_introspection_c, std_srvs, srv, SetBool)();
  rmw_qos_profile_t qos = rmw_qos_profile_default;
  rmw_service_t * allowed_service =
    rmw_create_service(node, type_support, kAllowedService, &qos);
  rmw_client_t * allowed_client =
    rmw_create_client(node, type_support, kAllowedService, &qos);
  rmw_service_t * request_denied_service =
    rmw_create_service(node, type_support, kRequestDeniedService, &qos);
  rmw_client_t * request_denied_client =
    rmw_create_client(node, type_support, kRequestDeniedService, &qos);
  rmw_service_t * response_denied_service =
    rmw_create_service(node, type_support, kResponseDeniedService, &qos);
  rmw_client_t * response_denied_client =
    rmw_create_client(node, type_support, kResponseDeniedService, &qos);
  rmw_service_t * default_denied_service =
    rmw_create_service(node, type_support, kDefaultDeniedService, &qos);
  rmw_client_t * default_denied_client =
    rmw_create_client(node, type_support, kDefaultDeniedService, &qos);
  if (allowed_service == nullptr || allowed_client == nullptr ||
    request_denied_service == nullptr || request_denied_client == nullptr ||
    response_denied_service == nullptr || response_denied_client == nullptr ||
    default_denied_service == nullptr || default_denied_client == nullptr)
  {
    std::cout << "{\"status\":\"create_service_client_failed\"}" << std::endl;
    return 1;
  }

  std_srvs__srv__SetBool_Request request;
  std_srvs__srv__SetBool_Request taken_request;
  std_srvs__srv__SetBool_Response response;
  std_srvs__srv__SetBool_Response taken_response;
  if (!std_srvs__srv__SetBool_Request__init(&request) ||
    !std_srvs__srv__SetBool_Request__init(&taken_request) ||
    !std_srvs__srv__SetBool_Response__init(&response) ||
    !std_srvs__srv__SetBool_Response__init(&taken_response))
  {
    std::cout << "{\"status\":\"message_init_failed\"}" << std::endl;
    return 1;
  }
  request.data = true;
  response.success = true;
  if (!assign_response_message(&response, "sros2 service allowed")) {
    std::cout << "{\"status\":\"response_assign_failed\"}" << std::endl;
    return 1;
  }

  const std::uint64_t request_publish_allowed_before =
    rmw_fleetqox_cpp_sros2_service_request_publish_allowed();
  const std::uint64_t request_publish_denied_before =
    rmw_fleetqox_cpp_sros2_service_request_publish_denied();
  const std::uint64_t request_subscribe_allowed_before =
    rmw_fleetqox_cpp_sros2_service_request_subscribe_allowed();
  const std::uint64_t request_subscribe_denied_before =
    rmw_fleetqox_cpp_sros2_service_request_subscribe_denied();
  const std::uint64_t response_publish_allowed_before =
    rmw_fleetqox_cpp_sros2_service_response_publish_allowed();
  const std::uint64_t response_publish_denied_before =
    rmw_fleetqox_cpp_sros2_service_response_publish_denied();
  const std::uint64_t response_subscribe_allowed_before =
    rmw_fleetqox_cpp_sros2_service_response_subscribe_allowed();
  const std::uint64_t response_subscribe_denied_before =
    rmw_fleetqox_cpp_sros2_service_response_subscribe_denied();
  const std::uint64_t parse_errors_before =
    rmw_fleetqox_cpp_sros2_service_authorization_parse_errors();

  int64_t allowed_sequence = 0;
  const rmw_ret_t allowed_send_request_ret =
    rmw_send_request(allowed_client, &request, &allowed_sequence);
  rmw_service_info_t allowed_request_info{};
  rmw_ret_t allowed_take_request_ret = RMW_RET_ERROR;
  const bool allowed_request_taken = allowed_send_request_ret == RMW_RET_OK &&
    wait_take_request(
    allowed_service, &allowed_request_info, &taken_request, &allowed_take_request_ret);
  const rmw_ret_t allowed_send_response_ret = allowed_request_taken ?
    rmw_send_response(allowed_service, &allowed_request_info.request_id, &response) :
    RMW_RET_ERROR;
  rmw_service_info_t allowed_response_info{};
  rmw_ret_t allowed_take_response_ret = RMW_RET_ERROR;
  const bool allowed_response_taken = allowed_send_response_ret == RMW_RET_OK &&
    wait_take_response(
    allowed_client, &allowed_response_info, &taken_response, &allowed_take_response_ret);
  const bool allowed_payload_ok =
    allowed_response_taken && taken_response.success &&
    std::string(taken_response.message.data == nullptr ? "" : taken_response.message.data) ==
    "sros2 service allowed";

  int64_t request_denied_sequence = 0;
  const rmw_ret_t request_denied_send_ret =
    rmw_send_request(request_denied_client, &request, &request_denied_sequence);
  const bool request_denied_queue_empty =
    take_request_once_empty(request_denied_service, &taken_request);
  if (request_denied_send_ret != RMW_RET_OK) {
    rmw_reset_error();
  }

  int64_t default_denied_sequence = 0;
  const rmw_ret_t default_denied_send_ret =
    rmw_send_request(default_denied_client, &request, &default_denied_sequence);
  const bool default_denied_queue_empty =
    take_request_once_empty(default_denied_service, &taken_request);
  if (default_denied_send_ret != RMW_RET_OK) {
    rmw_reset_error();
  }

  int64_t response_denied_sequence = 0;
  const rmw_ret_t response_denied_send_request_ret =
    rmw_send_request(response_denied_client, &request, &response_denied_sequence);
  rmw_service_info_t response_denied_request_info{};
  rmw_ret_t response_denied_take_request_ret = RMW_RET_ERROR;
  const bool response_denied_request_taken =
    response_denied_send_request_ret == RMW_RET_OK &&
    wait_take_request(
    response_denied_service, &response_denied_request_info, &taken_request,
    &response_denied_take_request_ret);
  rmw_request_id_t response_denied_request_id{};
  response_denied_request_id.sequence_number = response_denied_sequence;
  const rmw_ret_t response_denied_send_response_ret = rmw_send_response(
    response_denied_service, &response_denied_request_id, &response);
  const bool response_denied_queue_empty =
    take_response_once_empty(response_denied_client, &taken_response);
  if (response_denied_send_response_ret != RMW_RET_OK) {
    rmw_reset_error();
  }

  const std::uint64_t request_publish_allowed_delta =
    rmw_fleetqox_cpp_sros2_service_request_publish_allowed() -
    request_publish_allowed_before;
  const std::uint64_t request_publish_denied_delta =
    rmw_fleetqox_cpp_sros2_service_request_publish_denied() -
    request_publish_denied_before;
  const std::uint64_t request_subscribe_allowed_delta =
    rmw_fleetqox_cpp_sros2_service_request_subscribe_allowed() -
    request_subscribe_allowed_before;
  const std::uint64_t request_subscribe_denied_delta =
    rmw_fleetqox_cpp_sros2_service_request_subscribe_denied() -
    request_subscribe_denied_before;
  const std::uint64_t response_publish_allowed_delta =
    rmw_fleetqox_cpp_sros2_service_response_publish_allowed() -
    response_publish_allowed_before;
  const std::uint64_t response_publish_denied_delta =
    rmw_fleetqox_cpp_sros2_service_response_publish_denied() -
    response_publish_denied_before;
  const std::uint64_t response_subscribe_allowed_delta =
    rmw_fleetqox_cpp_sros2_service_response_subscribe_allowed() -
    response_subscribe_allowed_before;
  const std::uint64_t response_subscribe_denied_delta =
    rmw_fleetqox_cpp_sros2_service_response_subscribe_denied() -
    response_subscribe_denied_before;
  const std::uint64_t parse_errors_delta =
    rmw_fleetqox_cpp_sros2_service_authorization_parse_errors() -
    parse_errors_before;

  const bool allowed_service_ok =
    allowed_send_request_ret == RMW_RET_OK && allowed_sequence > 0 &&
    allowed_take_request_ret == RMW_RET_OK && allowed_request_taken && taken_request.data &&
    allowed_send_response_ret == RMW_RET_OK &&
    allowed_take_response_ret == RMW_RET_OK && allowed_response_taken && allowed_payload_ok;
  const bool request_denied_ok =
    request_denied_send_ret != RMW_RET_OK && request_denied_sequence == 0 &&
    request_denied_queue_empty;
  const bool default_denied_ok =
    default_denied_send_ret != RMW_RET_OK && default_denied_sequence == 0 &&
    default_denied_queue_empty;
  const bool response_denied_ok =
    response_denied_send_request_ret == RMW_RET_OK && response_denied_sequence > 0 &&
    response_denied_take_request_ret == RMW_RET_OK && !response_denied_request_taken &&
    response_denied_send_response_ret != RMW_RET_OK && response_denied_queue_empty;
  const bool counters_ok =
    request_publish_allowed_delta == 2 && request_publish_denied_delta == 2 &&
    request_subscribe_allowed_delta == 1 && request_subscribe_denied_delta == 1 &&
    response_publish_allowed_delta == 1 && response_publish_denied_delta == 1 &&
    response_subscribe_allowed_delta == 1 && response_subscribe_denied_delta == 0 &&
    parse_errors_delta == 0;
  const bool policy_loaded = rmw_fleetqox_cpp_sros2_permissions_xml_loaded();
  const bool runtime_signature_verified =
    rmw_fleetqox_cpp_sros2_runtime_signature_verified();
  const bool ok = policy_loaded && runtime_signature_verified && allowed_service_ok &&
    request_denied_ok && default_denied_ok && response_denied_ok && counters_ok;

  std::cout << "{\"schema_version\":\"" << kSchema << "\",";
  std::cout << "\"status\":\"" << (ok ? "ok" : "failed") << "\",";
  std::cout << "\"policy_loaded\":" << (policy_loaded ? "true" : "false") << ",";
  std::cout << "\"runtime_signature_verified\":" <<
    (runtime_signature_verified ? "true" : "false") << ",";
  std::cout << "\"allowed_send_request_returncode\":" <<
    static_cast<int>(allowed_send_request_ret) << ",";
  std::cout << "\"allowed_request_taken\":" <<
    (allowed_request_taken ? "true" : "false") << ",";
  std::cout << "\"allowed_send_response_returncode\":" <<
    static_cast<int>(allowed_send_response_ret) << ",";
  std::cout << "\"allowed_response_taken\":" <<
    (allowed_response_taken ? "true" : "false") << ",";
  std::cout << "\"allowed_response_payload_ok\":" <<
    (allowed_payload_ok ? "true" : "false") << ",";
  std::cout << "\"request_denied_send_returncode\":" <<
    static_cast<int>(request_denied_send_ret) << ",";
  std::cout << "\"request_denied_queue_empty\":" <<
    (request_denied_queue_empty ? "true" : "false") << ",";
  std::cout << "\"default_denied_send_returncode\":" <<
    static_cast<int>(default_denied_send_ret) << ",";
  std::cout << "\"default_denied_queue_empty\":" <<
    (default_denied_queue_empty ? "true" : "false") << ",";
  std::cout << "\"response_denied_send_request_returncode\":" <<
    static_cast<int>(response_denied_send_request_ret) << ",";
  std::cout << "\"response_denied_request_taken\":" <<
    (response_denied_request_taken ? "true" : "false") << ",";
  std::cout << "\"response_denied_send_response_returncode\":" <<
    static_cast<int>(response_denied_send_response_ret) << ",";
  std::cout << "\"response_denied_queue_empty\":" <<
    (response_denied_queue_empty ? "true" : "false") << ",";
  std::cout << "\"service_request_publish_allowed_delta\":" <<
    request_publish_allowed_delta << ",";
  std::cout << "\"service_request_publish_denied_delta\":" <<
    request_publish_denied_delta << ",";
  std::cout << "\"service_request_subscribe_allowed_delta\":" <<
    request_subscribe_allowed_delta << ",";
  std::cout << "\"service_request_subscribe_denied_delta\":" <<
    request_subscribe_denied_delta << ",";
  std::cout << "\"service_response_publish_allowed_delta\":" <<
    response_publish_allowed_delta << ",";
  std::cout << "\"service_response_publish_denied_delta\":" <<
    response_publish_denied_delta << ",";
  std::cout << "\"service_response_subscribe_allowed_delta\":" <<
    response_subscribe_allowed_delta << ",";
  std::cout << "\"service_response_subscribe_denied_delta\":" <<
    response_subscribe_denied_delta << ",";
  std::cout << "\"service_authorization_parse_errors_delta\":" <<
    parse_errors_delta << ",";
  std::cout << "\"sros2_service_request_reply_authorization_claim\":" <<
    (ok ? "true" : "false") << ",";
  std::cout << "\"sros2_service_authorization_scope\":\"generated_permissions_request_reply_allow_explicit_deny_default_deny\",";
  std::cout << "\"sros2_action_authorization_claim\":false,";
  std::cout << "\"governance_xml_enforcement_claim\":false,";
  std::cout << "\"production_security_hardening_claim\":false}" << std::endl;

  std_srvs__srv__SetBool_Request__fini(&request);
  std_srvs__srv__SetBool_Request__fini(&taken_request);
  std_srvs__srv__SetBool_Response__fini(&response);
  std_srvs__srv__SetBool_Response__fini(&taken_response);
  const rmw_ret_t destroy_allowed_client = rmw_destroy_client(node, allowed_client);
  const rmw_ret_t destroy_allowed_service = rmw_destroy_service(node, allowed_service);
  const rmw_ret_t destroy_request_denied_client =
    rmw_destroy_client(node, request_denied_client);
  const rmw_ret_t destroy_request_denied_service =
    rmw_destroy_service(node, request_denied_service);
  const rmw_ret_t destroy_response_denied_client =
    rmw_destroy_client(node, response_denied_client);
  const rmw_ret_t destroy_response_denied_service =
    rmw_destroy_service(node, response_denied_service);
  const rmw_ret_t destroy_default_denied_client =
    rmw_destroy_client(node, default_denied_client);
  const rmw_ret_t destroy_default_denied_service =
    rmw_destroy_service(node, default_denied_service);
  const rmw_ret_t destroy_node = rmw_destroy_node(node);
  cleanup_context(&context, &options);
  const bool cleanup_ok =
    destroy_allowed_client == RMW_RET_OK && destroy_allowed_service == RMW_RET_OK &&
    destroy_request_denied_client == RMW_RET_OK &&
    destroy_request_denied_service == RMW_RET_OK &&
    destroy_response_denied_client == RMW_RET_OK &&
    destroy_response_denied_service == RMW_RET_OK &&
    destroy_default_denied_client == RMW_RET_OK &&
    destroy_default_denied_service == RMW_RET_OK && destroy_node == RMW_RET_OK;
  return ok && cleanup_ok ? 0 : 1;
}

#include <chrono>
#include <cstdint>
#include <cstring>
#include <iostream>
#include <string>
#include <thread>

#include "rcutils/allocator.h"
#include "rmw/init.h"
#include "rmw/init_options.h"
#include "rmw/qos_profiles.h"
#include "rmw/rmw.h"
#include "rosidl_runtime_c/string_functions.h"
#include "rosidl_typesupport_interface/macros.h"
#include "std_srvs/srv/detail/set_bool__functions.h"
#include "std_srvs/srv/detail/set_bool__rosidl_typesupport_introspection_c.h"
#include "std_srvs/srv/detail/set_bool__struct.h"

extern "C" std::uint64_t rmw_fleetqox_cpp_service_durable_replays_loaded();
extern "C" std::uint64_t rmw_fleetqox_cpp_service_durable_replays_persisted();
extern "C" std::uint64_t rmw_fleetqox_cpp_service_durable_replays_sent();
extern "C" std::uint64_t rmw_fleetqox_cpp_service_durable_replay_failures();

namespace
{

constexpr const char * kServiceName = "/fleetqox/service_durable_replay";
constexpr const char * kResponseMessage = "fleetqox durable replay";

void cleanup_context(rmw_context_t * context, rmw_init_options_t * options)
{
  const rmw_ret_t shutdown_ret = rmw_shutdown(context);
  const rmw_ret_t context_fini_ret = rmw_context_fini(context);
  const rmw_ret_t options_fini_ret = rmw_init_options_fini(options);
  (void)shutdown_ret;
  (void)context_fini_ret;
  (void)options_fini_ret;
}

bool wait_for_request(
  const rmw_service_t * service,
  rmw_service_info_t * request_info,
  std_srvs__srv__SetBool_Request * request,
  std::chrono::milliseconds timeout)
{
  const auto deadline = std::chrono::steady_clock::now() + timeout;
  while (std::chrono::steady_clock::now() < deadline) {
    bool taken = false;
    if (rmw_take_request(service, request_info, request, &taken) != RMW_RET_OK) {
      return false;
    }
    if (taken) {
      return true;
    }
    std::this_thread::sleep_for(std::chrono::milliseconds(10));
  }
  return false;
}

bool wait_for_response(
  const rmw_client_t * client,
  std_srvs__srv__SetBool_Response * response,
  std::chrono::milliseconds timeout)
{
  const auto deadline = std::chrono::steady_clock::now() + timeout;
  while (std::chrono::steady_clock::now() < deadline) {
    rmw_service_info_t response_info{};
    bool taken = false;
    if (rmw_take_response(client, &response_info, response, &taken) != RMW_RET_OK) {
      return false;
    }
    if (taken) {
      return true;
    }
    std::this_thread::sleep_for(std::chrono::milliseconds(10));
  }
  return false;
}

int run_server(bool replay_mode, bool crash_mode = false)
{
  rcutils_allocator_t allocator = rcutils_get_default_allocator();
  rmw_init_options_t options = rmw_get_zero_initialized_init_options();
  if (rmw_init_options_init(&options, allocator) != RMW_RET_OK) {
    return 1;
  }
  options.instance_id = replay_mode ? 98 : 97;
  rmw_context_t context = rmw_get_zero_initialized_context();
  if (rmw_init(&options, &context) != RMW_RET_OK) {
    (void)rmw_init_options_fini(&options);
    return 1;
  }
  rmw_node_t * node = rmw_create_node(
    &context,
    replay_mode ? "fleetqox_durable_replay_server" : "fleetqox_durable_first_server",
    "/fleetqox");
  const rosidl_service_type_support_t * type_support =
    ROSIDL_TYPESUPPORT_INTERFACE__SERVICE_SYMBOL_NAME(
    rosidl_typesupport_introspection_c, std_srvs, srv, SetBool)();
  rmw_qos_profile_t qos = rmw_qos_profile_services_default;
  rmw_service_t * service =
    node == nullptr ? nullptr :
    rmw_create_service(node, type_support, kServiceName, &qos);

  bool request_taken = false;
  bool response_sent = false;
  if (service != nullptr && !replay_mode) {
    std_srvs__srv__SetBool_Request request;
    std_srvs__srv__SetBool_Response response;
    const bool request_initialized =
      std_srvs__srv__SetBool_Request__init(&request);
    const bool response_initialized =
      std_srvs__srv__SetBool_Response__init(&response);
    rmw_service_info_t request_info{};
    request_taken =
      request_initialized && response_initialized &&
      wait_for_request(
      service, &request_info, &request, std::chrono::seconds(8));
    if (request_taken) {
      response.success = true;
      response_sent =
        rosidl_runtime_c__String__assign(&response.message, kResponseMessage) &&
        rmw_send_response(
        service, &request_info.request_id, &response) == RMW_RET_OK;
    }
    if (request_initialized) {
      std_srvs__srv__SetBool_Request__fini(&request);
    }
    if (response_initialized) {
      std_srvs__srv__SetBool_Response__fini(&response);
    }
    std::this_thread::sleep_for(std::chrono::milliseconds(300));
  } else if (service != nullptr) {
    const auto deadline =
      std::chrono::steady_clock::now() + std::chrono::seconds(8);
    std_srvs__srv__SetBool_Request request;
    const bool request_initialized =
      std_srvs__srv__SetBool_Request__init(&request);
    while (request_initialized && std::chrono::steady_clock::now() < deadline) {
      rmw_service_info_t request_info{};
      bool taken = false;
      if (rmw_take_request(service, &request_info, &request, &taken) != RMW_RET_OK) {
        break;
      }
      request_taken = request_taken || taken;
      if (rmw_fleetqox_cpp_service_durable_replays_sent() >= 1) {
        break;
      }
      std::this_thread::sleep_for(std::chrono::milliseconds(10));
    }
    if (request_initialized) {
      std_srvs__srv__SetBool_Request__fini(&request);
    }
  }

  const std::uint64_t loaded =
    rmw_fleetqox_cpp_service_durable_replays_loaded();
  const std::uint64_t persisted =
    rmw_fleetqox_cpp_service_durable_replays_persisted();
  const std::uint64_t replayed =
    rmw_fleetqox_cpp_service_durable_replays_sent();
  const std::uint64_t failures =
    rmw_fleetqox_cpp_service_durable_replay_failures();
  const bool ok =
    service != nullptr && failures == 0 &&
    (replay_mode ?
    (loaded >= 1 && replayed >= 1 && !request_taken) :
    (request_taken && response_sent && persisted >= 1));
  if (crash_mode && ok) {
    std::cout
      << "{\"schema_version\":\"fleetrmw.rmw_service_durable_replay_probe.v1\","
      << "\"status\":\"crash_ready\","
      << "\"role\":\"server_crash\","
      << "\"request_taken\":true,"
      << "\"application_response_sent\":true,"
      << "\"durable_replays_persisted\":" << persisted << ","
      << "\"durable_replay_failures\":" << failures << "}"
      << std::endl;
    std::this_thread::sleep_for(std::chrono::seconds(60));
    return 1;
  }

  const rmw_ret_t destroy_service_ret =
    service == nullptr ? RMW_RET_OK : rmw_destroy_service(node, service);
  const rmw_ret_t destroy_node_ret =
    node == nullptr ? RMW_RET_OK : rmw_destroy_node(node);
  cleanup_context(&context, &options);
  const bool cleanup_ok =
    destroy_service_ret == RMW_RET_OK && destroy_node_ret == RMW_RET_OK;
  std::cout
    << "{\"schema_version\":\"fleetrmw.rmw_service_durable_replay_probe.v1\","
    << "\"status\":\"" << (ok && cleanup_ok ? "ok" : "failed") << "\","
    << "\"role\":\"" << (replay_mode ? "server_replay" : "server_first") << "\","
    << "\"request_taken\":" << (request_taken ? "true" : "false") << ","
    << "\"application_response_sent\":" << (response_sent ? "true" : "false") << ","
    << "\"durable_replays_loaded\":" << loaded << ","
    << "\"durable_replays_persisted\":" << persisted << ","
    << "\"durable_replays_sent\":" << replayed << ","
    << "\"durable_replay_failures\":" << failures << ","
    << "\"cleanup_ok\":" << (cleanup_ok ? "true" : "false") << "}"
    << std::endl;
  return ok && cleanup_ok ? 0 : 1;
}

int run_client(bool expect_response)
{
  rcutils_allocator_t allocator = rcutils_get_default_allocator();
  rmw_init_options_t options = rmw_get_zero_initialized_init_options();
  if (rmw_init_options_init(&options, allocator) != RMW_RET_OK) {
    return 1;
  }
  options.instance_id = expect_response ? 100 : 99;
  rmw_context_t context = rmw_get_zero_initialized_context();
  if (rmw_init(&options, &context) != RMW_RET_OK) {
    (void)rmw_init_options_fini(&options);
    return 1;
  }
  rmw_node_t * node = rmw_create_node(
    &context,
    expect_response ? "fleetqox_durable_replay_client" : "fleetqox_durable_first_client",
    "/fleetqox");
  const rosidl_service_type_support_t * type_support =
    ROSIDL_TYPESUPPORT_INTERFACE__SERVICE_SYMBOL_NAME(
    rosidl_typesupport_introspection_c, std_srvs, srv, SetBool)();
  rmw_qos_profile_t qos = rmw_qos_profile_services_default;
  rmw_client_t * client =
    node == nullptr ? nullptr :
    rmw_create_client(node, type_support, kServiceName, &qos);

  std_srvs__srv__SetBool_Request request;
  std_srvs__srv__SetBool_Response response;
  const bool request_initialized = std_srvs__srv__SetBool_Request__init(&request);
  const bool response_initialized = std_srvs__srv__SetBool_Response__init(&response);
  request.data = true;
  std::int64_t sequence = 0;
  const bool request_sent =
    client != nullptr && request_initialized && response_initialized &&
    rmw_send_request(client, &request, &sequence) == RMW_RET_OK &&
    sequence == 1;
  bool response_taken = false;
  bool response_matches = false;
  if (request_sent && expect_response) {
    response_taken = wait_for_response(
      client, &response, std::chrono::seconds(8));
    response_matches =
      response_taken && response.success &&
      response.message.data != nullptr &&
      std::strcmp(response.message.data, kResponseMessage) == 0;
  } else if (request_sent) {
    std::this_thread::sleep_for(std::chrono::seconds(2));
  }

  if (request_initialized) {
    std_srvs__srv__SetBool_Request__fini(&request);
  }
  if (response_initialized) {
    std_srvs__srv__SetBool_Response__fini(&response);
  }
  const rmw_ret_t destroy_client_ret =
    client == nullptr ? RMW_RET_OK : rmw_destroy_client(node, client);
  const rmw_ret_t destroy_node_ret =
    node == nullptr ? RMW_RET_OK : rmw_destroy_node(node);
  cleanup_context(&context, &options);
  const bool cleanup_ok =
    destroy_client_ret == RMW_RET_OK && destroy_node_ret == RMW_RET_OK;
  const bool ok =
    request_sent && cleanup_ok &&
    (!expect_response || response_matches);
  std::cout
    << "{\"schema_version\":\"fleetrmw.rmw_service_durable_replay_probe.v1\","
    << "\"status\":\"" << (ok ? "ok" : "failed") << "\","
    << "\"role\":\"" << (expect_response ? "client_replay" : "client_first") << "\","
    << "\"request_sent\":" << (request_sent ? "true" : "false") << ","
    << "\"sequence\":" << sequence << ","
    << "\"response_taken\":" << (response_taken ? "true" : "false") << ","
    << "\"response_matches\":" << (response_matches ? "true" : "false") << ","
    << "\"cleanup_ok\":" << (cleanup_ok ? "true" : "false") << "}"
    << std::endl;
  return ok ? 0 : 1;
}

}  // namespace

int main(int argc, char ** argv)
{
  if (argc != 3 || std::string(argv[1]) != "--role") {
    std::cerr << "usage: service_durable_replay_probe --role "
              << "server-first|server-crash|server-replay|client-first|client-replay"
              << std::endl;
    return 2;
  }
  const std::string role = argv[2];
  if (role == "server-first") {
    return run_server(false);
  }
  if (role == "server-crash") {
    return run_server(false, true);
  }
  if (role == "server-replay") {
    return run_server(true);
  }
  if (role == "client-first") {
    return run_client(false);
  }
  if (role == "client-replay") {
    return run_client(true);
  }
  return 2;
}

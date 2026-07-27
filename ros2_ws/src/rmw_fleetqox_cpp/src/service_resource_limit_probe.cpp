#include "rmw_fleetqox_cpp/data_frame.hpp"

#include <chrono>
#include <cstdint>
#include <iostream>
#include <set>
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
extern "C" std::uint64_t rmw_fleetqox_cpp_service_request_queue_resource_drops();
extern "C" std::uint64_t rmw_fleetqox_cpp_service_response_queue_resource_drops();
extern "C" std::uint64_t rmw_fleetqox_cpp_service_request_dedupe_evictions();
extern "C" std::uint64_t rmw_fleetqox_cpp_service_response_dedupe_evictions();
extern "C" std::uint64_t rmw_fleetqox_cpp_service_response_replay_evictions();
extern "C" std::uint64_t rmw_fleetqox_cpp_service_request_queue_max_observed();
extern "C" std::uint64_t rmw_fleetqox_cpp_service_response_queue_max_observed();
extern "C" std::uint64_t rmw_fleetqox_cpp_service_pending_response_max_observed();
extern "C" std::uint64_t rmw_fleetqox_cpp_service_response_replay_max_observed();

namespace
{

constexpr const char * kServiceName = "/fleetqox/service_resource_limit";
constexpr const char * kServiceType = "std_srvs/srv/SetBool";
constexpr std::int64_t kRequestCount = 10;

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
  std::size_t domain_id)
{
  const rmw_fleetqox_cpp::ServiceFrame frame{
    "request",
    kServiceName,
    kServiceType,
    client_endpoint_id,
    "",
    sequence_id,
    1000000 + sequence_id,
    0,
    payload,
    domain_id};
  const std::string encoded = rmw_fleetqox_cpp::encode_service_frame(frame);
  return rmw_fleetqox_cpp_handle_service_frame(encoded.data(), encoded.size());
}

bool drain_requests(
  const rmw_service_t * service,
  std::set<std::int64_t> * request_sequences)
{
  if (service == nullptr || request_sequences == nullptr) {
    return false;
  }
  std_srvs__srv__SetBool_Request request;
  std_srvs__srv__SetBool_Response response;
  if (!std_srvs__srv__SetBool_Request__init(&request) ||
    !std_srvs__srv__SetBool_Response__init(&response))
  {
    return false;
  }
  bool ok = true;
  while (ok) {
    rmw_service_info_t info{};
    bool taken = false;
    const rmw_ret_t take_ret = rmw_take_request(service, &info, &request, &taken);
    if (take_ret != RMW_RET_OK) {
      ok = false;
      break;
    }
    if (!taken) {
      break;
    }
    ok = request.data && request_sequences->insert(
      info.request_id.sequence_number).second;
    response.success = true;
    if (ok && rmw_send_response(service, &info.request_id, &response) != RMW_RET_OK) {
      ok = false;
    }
  }
  std_srvs__srv__SetBool_Response__fini(&response);
  std_srvs__srv__SetBool_Request__fini(&request);
  return ok;
}

bool drain_responses(
  const rmw_client_t * client,
  size_t expected_count,
  std::set<std::int64_t> * response_sequences)
{
  if (client == nullptr || response_sequences == nullptr) {
    return false;
  }
  std_srvs__srv__SetBool_Response response;
  if (!std_srvs__srv__SetBool_Response__init(&response)) {
    return false;
  }
  const auto deadline = std::chrono::steady_clock::now() + std::chrono::seconds(2);
  bool ok = true;
  while (response_sequences->size() < expected_count &&
    std::chrono::steady_clock::now() < deadline)
  {
    rmw_service_info_t info{};
    bool taken = false;
    const rmw_ret_t take_ret = rmw_take_response(client, &info, &response, &taken);
    if (take_ret != RMW_RET_OK) {
      ok = false;
      break;
    }
    if (taken) {
      ok = response.success && response_sequences->insert(
        info.request_id.sequence_number).second;
    } else {
      std::this_thread::sleep_for(std::chrono::milliseconds(5));
    }
  }
  std_srvs__srv__SetBool_Response__fini(&response);
  return ok && response_sequences->size() == expected_count;
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
  options.instance_id = 91;
  rmw_context_t context = rmw_get_zero_initialized_context();
  ret = rmw_init(&options, &context);
  if (ret != RMW_RET_OK) {
    const rmw_ret_t fini_ret = rmw_init_options_fini(&options);
    (void)fini_ret;
    std::cout << "{\"status\":\"init_failed\"}" << std::endl;
    return 1;
  }
  rmw_node_t * node =
    rmw_create_node(&context, "fleetqox_service_resource_limit_probe", "/fleetqox");
  const rosidl_service_type_support_t * service_type_support =
    ROSIDL_TYPESUPPORT_INTERFACE__SERVICE_SYMBOL_NAME(
    rosidl_typesupport_introspection_c, std_srvs, srv, SetBool)();
  rmw_qos_profile_t qos = rmw_qos_profile_services_default;
  rmw_service_t * service =
    node == nullptr ? nullptr :
    rmw_create_service(node, service_type_support, kServiceName, &qos);
  rmw_client_t * client =
    node == nullptr ? nullptr :
    rmw_create_client(node, service_type_support, kServiceName, &qos);
  std::vector<std::uint8_t> payload;
  const bool setup_ok =
    node != nullptr && service != nullptr && client != nullptr &&
    serialize_request(&payload);

  std::set<std::int64_t> request_sequences;
  std::set<std::int64_t> response_sequences;
  bool exercise_ok = setup_ok;
  const std::string client_endpoint_id =
    client == nullptr ? "" : rmw_fleetqox_cpp_client_endpoint_id(client);
  if (exercise_ok) {
    for (std::int64_t sequence = 1; sequence <= kRequestCount; ++sequence) {
      exercise_ok = exercise_ok && inject_request(
        client_endpoint_id, payload, sequence, context.actual_domain_id);
    }
    exercise_ok = exercise_ok && inject_request(
      client_endpoint_id, payload, 1, context.actual_domain_id);
    exercise_ok = exercise_ok && drain_requests(service, &request_sequences);
    exercise_ok = exercise_ok && drain_responses(client, 4, &response_sequences);

    for (std::int64_t sequence = 5; sequence <= kRequestCount; ++sequence) {
      exercise_ok = exercise_ok && inject_request(
        client_endpoint_id, payload, sequence, context.actual_domain_id);
    }
    exercise_ok = exercise_ok && drain_requests(service, &request_sequences);
    exercise_ok = exercise_ok && drain_responses(client, 8, &response_sequences);

    for (std::int64_t sequence = 9; sequence <= kRequestCount; ++sequence) {
      exercise_ok = exercise_ok && inject_request(
        client_endpoint_id, payload, sequence, context.actual_domain_id);
    }
    exercise_ok = exercise_ok && drain_requests(service, &request_sequences);
    exercise_ok = exercise_ok && drain_responses(
      client, static_cast<size_t>(kRequestCount), &response_sequences);
  }

  const std::uint64_t request_resource_drops =
    rmw_fleetqox_cpp_service_request_queue_resource_drops();
  const std::uint64_t response_resource_drops =
    rmw_fleetqox_cpp_service_response_queue_resource_drops();
  const std::uint64_t request_dedupe_evictions =
    rmw_fleetqox_cpp_service_request_dedupe_evictions();
  const std::uint64_t response_dedupe_evictions =
    rmw_fleetqox_cpp_service_response_dedupe_evictions();
  const std::uint64_t replay_evictions =
    rmw_fleetqox_cpp_service_response_replay_evictions();
  const std::uint64_t request_queue_max =
    rmw_fleetqox_cpp_service_request_queue_max_observed();
  const std::uint64_t response_queue_max =
    rmw_fleetqox_cpp_service_response_queue_max_observed();
  const std::uint64_t pending_response_max =
    rmw_fleetqox_cpp_service_pending_response_max_observed();
  const std::uint64_t replay_max =
    rmw_fleetqox_cpp_service_response_replay_max_observed();

  const rmw_ret_t destroy_client_ret =
    client == nullptr ? RMW_RET_OK : rmw_destroy_client(node, client);
  const rmw_ret_t destroy_service_ret =
    service == nullptr ? RMW_RET_OK : rmw_destroy_service(node, service);
  const rmw_ret_t destroy_node_ret =
    node == nullptr ? RMW_RET_OK : rmw_destroy_node(node);
  const bool cleanup_ok =
    destroy_client_ret == RMW_RET_OK &&
    destroy_service_ret == RMW_RET_OK &&
    destroy_node_ret == RMW_RET_OK;
  cleanup_context(&context, &options);

  const bool limits_ok =
    request_resource_drops == 8 &&
    response_resource_drops == 0 &&
    request_dedupe_evictions == 6 &&
    response_dedupe_evictions == 6 &&
    replay_evictions == 6 &&
    request_queue_max == 4 &&
    response_queue_max <= 4 &&
    pending_response_max <= 1 &&
    replay_max == 4;
  const bool exact_delivery =
    request_sequences.size() == static_cast<size_t>(kRequestCount) &&
    response_sequences.size() == static_cast<size_t>(kRequestCount);
  const bool duplicate_request_suppressed =
    request_resource_drops == 8 &&
    request_sequences.size() == static_cast<size_t>(kRequestCount);
  const bool ok =
    exercise_ok && limits_ok && exact_delivery &&
    duplicate_request_suppressed && cleanup_ok;

  std::cout << "{\"schema_version\":\"fleetrmw.rmw_service_resource_limit_probe.v1\","
            << "\"status\":\"" << (ok ? "ok" : "failed") << "\","
            << "\"request_count\":" << kRequestCount << ","
            << "\"unique_requests_taken\":" << request_sequences.size() << ","
            << "\"unique_responses_taken\":" << response_sequences.size() << ","
            << "\"request_queue_limit\":4,"
            << "\"response_queue_limit\":4,"
            << "\"dedupe_history_limit\":4,"
            << "\"response_replay_limit\":4,"
            << "\"request_queue_resource_drops\":" << request_resource_drops << ","
            << "\"response_queue_resource_drops\":" << response_resource_drops << ","
            << "\"request_dedupe_evictions\":" << request_dedupe_evictions << ","
            << "\"response_dedupe_evictions\":" << response_dedupe_evictions << ","
            << "\"response_replay_evictions\":" << replay_evictions << ","
            << "\"request_queue_max_observed\":" << request_queue_max << ","
            << "\"response_queue_max_observed\":" << response_queue_max << ","
            << "\"pending_response_max_observed\":" << pending_response_max << ","
            << "\"response_replay_max_observed\":" << replay_max << ","
            << "\"duplicate_request_suppressed\":"
            << (duplicate_request_suppressed ? "true" : "false") << ","
            << "\"resource_repair_exact_delivery\":" << (exact_delivery ? "true" : "false")
            << ",\"cleanup_ok\":" << (cleanup_ok ? "true" : "false") << "}"
            << std::endl;
  return ok ? 0 : 1;
}

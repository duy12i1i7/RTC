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
extern "C" std::uint64_t rmw_fleetqox_cpp_service_request_per_client_resource_drops();
extern "C" std::uint64_t rmw_fleetqox_cpp_service_request_queue_max_observed();
extern "C" std::uint64_t rmw_fleetqox_cpp_service_request_per_client_max_observed();

namespace
{

constexpr const char * kServiceName = "/fleetqox/service_client_isolation";
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
  std::size_t domain_id)
{
  const rmw_fleetqox_cpp::ServiceFrame frame{
    "request",
    kServiceName,
    kServiceType,
    client_endpoint_id,
    "",
    sequence_id,
    2000000 + sequence_id,
    0,
    payload,
    domain_id};
  const std::string encoded = rmw_fleetqox_cpp::encode_service_frame(frame);
  return rmw_fleetqox_cpp_handle_service_frame(encoded.data(), encoded.size());
}

bool drain_requests(
  const rmw_service_t * service,
  std::set<std::int64_t> * all_sequences,
  std::set<std::int64_t> * batch_sequences)
{
  if (service == nullptr || all_sequences == nullptr || batch_sequences == nullptr) {
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
    const std::int64_t sequence = info.request_id.sequence_number;
    ok = request.data &&
      all_sequences->insert(sequence).second &&
      batch_sequences->insert(sequence).second;
    response.success = true;
    if (ok && rmw_send_response(service, &info.request_id, &response) != RMW_RET_OK) {
      ok = false;
    }
  }
  std_srvs__srv__SetBool_Response__fini(&response);
  std_srvs__srv__SetBool_Request__fini(&request);
  return ok;
}

bool drain_client_responses(
  const rmw_client_t * client,
  size_t expected_count,
  std::set<std::int64_t> * sequences)
{
  if (client == nullptr || sequences == nullptr) {
    return false;
  }
  std_srvs__srv__SetBool_Response response;
  if (!std_srvs__srv__SetBool_Response__init(&response)) {
    return false;
  }
  const auto deadline = std::chrono::steady_clock::now() + std::chrono::seconds(2);
  bool ok = true;
  while (sequences->size() < expected_count &&
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
      ok = response.success && sequences->insert(
        info.request_id.sequence_number).second;
    } else {
      std::this_thread::sleep_for(std::chrono::milliseconds(5));
    }
  }
  std_srvs__srv__SetBool_Response__fini(&response);
  return ok && sequences->size() == expected_count;
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
  options.instance_id = 92;
  rmw_context_t context = rmw_get_zero_initialized_context();
  ret = rmw_init(&options, &context);
  if (ret != RMW_RET_OK) {
    const rmw_ret_t fini_ret = rmw_init_options_fini(&options);
    (void)fini_ret;
    std::cout << "{\"status\":\"init_failed\"}" << std::endl;
    return 1;
  }
  rmw_node_t * node =
    rmw_create_node(&context, "fleetqox_service_client_isolation_probe", "/fleetqox");
  const rosidl_service_type_support_t * type_support =
    ROSIDL_TYPESUPPORT_INTERFACE__SERVICE_SYMBOL_NAME(
    rosidl_typesupport_introspection_c, std_srvs, srv, SetBool)();
  rmw_qos_profile_t qos = rmw_qos_profile_services_default;
  rmw_service_t * service =
    node == nullptr ? nullptr :
    rmw_create_service(node, type_support, kServiceName, &qos);
  rmw_client_t * noisy_client =
    node == nullptr ? nullptr :
    rmw_create_client(node, type_support, kServiceName, &qos);
  rmw_client_t * quiet_client =
    node == nullptr ? nullptr :
    rmw_create_client(node, type_support, kServiceName, &qos);
  std::vector<std::uint8_t> payload;
  const bool setup_ok =
    node != nullptr && service != nullptr &&
    noisy_client != nullptr && quiet_client != nullptr &&
    serialize_request(&payload);

  const std::string noisy_endpoint =
    noisy_client == nullptr ? "" : rmw_fleetqox_cpp_client_endpoint_id(noisy_client);
  const std::string quiet_endpoint =
    quiet_client == nullptr ? "" : rmw_fleetqox_cpp_client_endpoint_id(quiet_client);
  std::set<std::int64_t> requests;
  std::set<std::int64_t> noisy_responses;
  std::set<std::int64_t> quiet_responses;
  std::set<std::int64_t> first_batch;
  bool exercise_ok = setup_ok;
  if (exercise_ok) {
    for (std::int64_t sequence = 1; sequence <= 8; ++sequence) {
      exercise_ok = exercise_ok && inject_request(
        noisy_endpoint, payload, sequence, context.actual_domain_id);
    }
    exercise_ok = exercise_ok && inject_request(
      quiet_endpoint, payload, 100, context.actual_domain_id);
    exercise_ok = exercise_ok && inject_request(
      quiet_endpoint, payload, 101, context.actual_domain_id);
    exercise_ok = exercise_ok && drain_requests(service, &requests, &first_batch);
    exercise_ok = exercise_ok &&
      drain_client_responses(noisy_client, 2, &noisy_responses) &&
      drain_client_responses(quiet_client, 2, &quiet_responses);

    size_t noisy_expected = 2;
    for (std::int64_t first = 3; first <= 7; first += 2) {
      for (std::int64_t sequence = first; sequence <= 8; ++sequence) {
        exercise_ok = exercise_ok && inject_request(
          noisy_endpoint, payload, sequence, context.actual_domain_id);
      }
      std::set<std::int64_t> batch;
      exercise_ok = exercise_ok && drain_requests(service, &requests, &batch);
      noisy_expected += 2;
      exercise_ok = exercise_ok &&
        drain_client_responses(noisy_client, noisy_expected, &noisy_responses);
    }
  }

  const std::uint64_t global_resource_drops =
    rmw_fleetqox_cpp_service_request_queue_resource_drops();
  const std::uint64_t per_client_resource_drops =
    rmw_fleetqox_cpp_service_request_per_client_resource_drops();
  const std::uint64_t queue_max =
    rmw_fleetqox_cpp_service_request_queue_max_observed();
  const std::uint64_t per_client_max =
    rmw_fleetqox_cpp_service_request_per_client_max_observed();
  const bool quiet_admitted_first_wave =
    first_batch == std::set<std::int64_t>({1, 2, 100, 101});
  const bool exact_delivery =
    requests.size() == 10 &&
    noisy_responses.size() == 8 &&
    quiet_responses.size() == 2;
  const bool isolation_ok =
    global_resource_drops == 0 &&
    per_client_resource_drops == 12 &&
    queue_max == 4 &&
    per_client_max == 2 &&
    quiet_admitted_first_wave;

  const rmw_ret_t destroy_noisy_ret =
    noisy_client == nullptr ? RMW_RET_OK : rmw_destroy_client(node, noisy_client);
  const rmw_ret_t destroy_quiet_ret =
    quiet_client == nullptr ? RMW_RET_OK : rmw_destroy_client(node, quiet_client);
  const rmw_ret_t destroy_service_ret =
    service == nullptr ? RMW_RET_OK : rmw_destroy_service(node, service);
  const rmw_ret_t destroy_node_ret =
    node == nullptr ? RMW_RET_OK : rmw_destroy_node(node);
  const bool cleanup_ok =
    destroy_noisy_ret == RMW_RET_OK &&
    destroy_quiet_ret == RMW_RET_OK &&
    destroy_service_ret == RMW_RET_OK &&
    destroy_node_ret == RMW_RET_OK;
  cleanup_context(&context, &options);

  const bool ok =
    exercise_ok && isolation_ok && exact_delivery && cleanup_ok;
  std::cout << "{\"schema_version\":\"fleetrmw.rmw_service_client_isolation_probe.v1\","
            << "\"status\":\"" << (ok ? "ok" : "failed") << "\","
            << "\"noisy_request_count\":8,"
            << "\"quiet_request_count\":2,"
            << "\"request_queue_limit\":4,"
            << "\"per_client_request_queue_limit\":2,"
            << "\"global_resource_drops\":" << global_resource_drops << ","
            << "\"per_client_resource_drops\":" << per_client_resource_drops << ","
            << "\"request_queue_max_observed\":" << queue_max << ","
            << "\"per_client_max_observed\":" << per_client_max << ","
            << "\"first_wave_request_count\":" << first_batch.size() << ","
            << "\"quiet_admitted_first_wave\":"
            << (quiet_admitted_first_wave ? "true" : "false") << ","
            << "\"unique_requests_taken\":" << requests.size() << ","
            << "\"noisy_responses_taken\":" << noisy_responses.size() << ","
            << "\"quiet_responses_taken\":" << quiet_responses.size() << ","
            << "\"exact_delivery\":" << (exact_delivery ? "true" : "false") << ","
            << "\"cleanup_ok\":" << (cleanup_ok ? "true" : "false") << "}"
            << std::endl;
  return ok ? 0 : 1;
}

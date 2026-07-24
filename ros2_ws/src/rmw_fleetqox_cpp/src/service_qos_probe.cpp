#include <algorithm>
#include <chrono>
#include <cstdint>
#include <cstring>
#include <iostream>
#include <sstream>
#include <string>
#include <thread>

#include "rcutils/allocator.h"
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
#include "std_srvs/srv/detail/trigger__rosidl_typesupport_introspection_c.h"

extern "C" std::uint64_t rmw_fleetqox_cpp_socket_frames_sent();
extern "C" std::uint64_t rmw_fleetqox_cpp_service_frames_received();
extern "C" std::uint64_t rmw_fleetqox_cpp_service_expired_frames_dropped();
extern "C" bool rmw_fleetqox_cpp_waitable_service_has_request(const void * waitable);

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

bool wait_for_received_frames(std::uint64_t baseline, std::uint64_t expected_delta)
{
  for (int attempt = 0; attempt < 200; ++attempt) {
    if (rmw_fleetqox_cpp_service_frames_received() >= baseline + expected_delta) {
      return true;
    }
    std::this_thread::sleep_for(std::chrono::milliseconds(1));
  }
  return false;
}

bool assign_response_message(std_srvs__srv__SetBool_Response * response, const std::string & message)
{
  return rosidl_runtime_c__String__assignn(&response->message, message.data(), message.size());
}

bool gid_has_nonzero_data(const rmw_gid_t & gid)
{
  return std::any_of(
    gid.data,
    gid.data + RMW_GID_STORAGE_SIZE,
    [](const std::uint8_t value) {return value != 0;});
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
  options.instance_id = 47;

  rmw_context_t context = rmw_get_zero_initialized_context();
  ret = rmw_init(&options, &context);
  if (ret != RMW_RET_OK) {
    const rmw_ret_t fini_ret = rmw_init_options_fini(&options);
    (void)fini_ret;
    std::cout << "{\"status\":\"init_failed\",\"ret\":" << ret << "}" << std::endl;
    return 1;
  }

  rmw_node_t * node = rmw_create_node(&context, "fleetqox_service_qos_probe", "/fleetqox");
  rmw_node_t * other_node = rmw_create_node(
    &context, "fleetqox_service_qos_probe_other", "/fleetqox");
  if (node == nullptr || other_node == nullptr) {
    if (node != nullptr) {
      const rmw_ret_t destroy_node_ret = rmw_destroy_node(node);
      (void)destroy_node_ret;
    }
    if (other_node != nullptr) {
      const rmw_ret_t destroy_other_node_ret = rmw_destroy_node(other_node);
      (void)destroy_other_node_ret;
    }
    cleanup_context(&context, &options);
    std::cout << "{\"status\":\"create_node_failed\"}" << std::endl;
    return 1;
  }

  const rosidl_service_type_support_t * type_support =
    ROSIDL_TYPESUPPORT_INTERFACE__SERVICE_SYMBOL_NAME(
    rosidl_typesupport_introspection_c, std_srvs, srv, SetBool)();
  const rosidl_service_type_support_t * trigger_type_support =
    ROSIDL_TYPESUPPORT_INTERFACE__SERVICE_SYMBOL_NAME(
    rosidl_typesupport_introspection_c, std_srvs, srv, Trigger)();

  rmw_qos_profile_t service_qos = rmw_qos_profile_default;
  service_qos.lifespan.sec = 0;
  service_qos.lifespan.nsec = 5000000;
  rmw_qos_profile_t client_qos = rmw_qos_profile_default;
  client_qos.lifespan.sec = 0;
  client_qos.lifespan.nsec = 5000000;

  const char * service_name = "/fleetqox/service_qos_probe";
  rmw_service_t * service = rmw_create_service(node, type_support, service_name, &service_qos);
  rmw_client_t * client = rmw_create_client(node, type_support, service_name, &client_qos);
  rmw_client_t * peer_client = rmw_create_client(node, type_support, service_name, &client_qos);
  if (service == nullptr || client == nullptr || peer_client == nullptr) {
    if (peer_client != nullptr) {
      const rmw_ret_t destroy_peer_client_ret = rmw_destroy_client(node, peer_client);
      (void)destroy_peer_client_ret;
    }
    if (client != nullptr) {
      const rmw_ret_t destroy_client_ret = rmw_destroy_client(node, client);
      (void)destroy_client_ret;
    }
    if (service != nullptr) {
      const rmw_ret_t destroy_service_ret = rmw_destroy_service(node, service);
      (void)destroy_service_ret;
    }
    const rmw_ret_t destroy_node_ret = rmw_destroy_node(node);
    const rmw_ret_t destroy_other_node_ret = rmw_destroy_node(other_node);
    (void)destroy_node_ret;
    (void)destroy_other_node_ret;
    cleanup_context(&context, &options);
    std::cout << "{\"status\":\"create_service_client_failed\"}" << std::endl;
    return 1;
  }

  bool wrong_owner_available = false;
  const rmw_ret_t wrong_owner_availability_ret =
    rmw_service_server_is_available(other_node, client, &wrong_owner_available);
  const bool service_availability_owner_node_enforced =
    wrong_owner_availability_ret == RMW_RET_INVALID_ARGUMENT;
  rmw_reset_error();
  const rmw_ret_t wrong_owner_client_destroy_ret = rmw_destroy_client(other_node, client);
  const bool client_destroy_owner_node_enforced =
    wrong_owner_client_destroy_ret == RMW_RET_INVALID_ARGUMENT;
  rmw_reset_error();
  const rmw_ret_t wrong_owner_service_destroy_ret = rmw_destroy_service(other_node, service);
  const bool service_destroy_owner_node_enforced =
    wrong_owner_service_destroy_ret == RMW_RET_INVALID_ARGUMENT;
  rmw_reset_error();

  rmw_gid_t client_gid{};
  rmw_gid_t repeated_client_gid{};
  rmw_gid_t peer_client_gid{};
  const rmw_ret_t client_gid_ret = rmw_get_gid_for_client(client, &client_gid);
  const rmw_ret_t repeated_client_gid_ret =
    rmw_get_gid_for_client(client, &repeated_client_gid);
  const rmw_ret_t peer_client_gid_ret = rmw_get_gid_for_client(peer_client, &peer_client_gid);
  bool repeated_gid_equal = false;
  bool peer_gid_equal = true;
  const rmw_ret_t repeated_gid_compare_ret =
    client_gid_ret == RMW_RET_OK && repeated_client_gid_ret == RMW_RET_OK ?
    rmw_compare_gids_equal(&client_gid, &repeated_client_gid, &repeated_gid_equal) :
    RMW_RET_ERROR;
  const rmw_ret_t peer_gid_compare_ret =
    client_gid_ret == RMW_RET_OK && peer_client_gid_ret == RMW_RET_OK ?
    rmw_compare_gids_equal(&client_gid, &peer_client_gid, &peer_gid_equal) :
    RMW_RET_ERROR;
  const bool client_gid_stable =
    repeated_gid_compare_ret == RMW_RET_OK && repeated_gid_equal;
  const bool client_gids_distinct =
    peer_gid_compare_ret == RMW_RET_OK && !peer_gid_equal;
  const bool client_gid_nonzero =
    client_gid_ret == RMW_RET_OK && gid_has_nonzero_data(client_gid);
  bool matching_service_available = false;
  const rmw_ret_t matching_service_available_ret =
    rmw_service_server_is_available(node, client, &matching_service_available);

  std_srvs__srv__SetBool_Request stale_request;
  std_srvs__srv__SetBool_Request fresh_request;
  std_srvs__srv__SetBool_Request taken_request;
  std_srvs__srv__SetBool_Response response;
  std_srvs__srv__SetBool_Response taken_response;
  if (!std_srvs__srv__SetBool_Request__init(&stale_request) ||
    !std_srvs__srv__SetBool_Request__init(&fresh_request) ||
    !std_srvs__srv__SetBool_Request__init(&taken_request) ||
    !std_srvs__srv__SetBool_Response__init(&response) ||
    !std_srvs__srv__SetBool_Response__init(&taken_response))
  {
    std::cout << "{\"status\":\"message_init_failed\"}" << std::endl;
    return 1;
  }
  stale_request.data = true;
  fresh_request.data = true;
  response.success = true;
  if (!assign_response_message(&response, "fleetqox service qos accepted")) {
    std::cout << "{\"status\":\"response_assign_failed\"}" << std::endl;
    return 1;
  }

  const std::uint64_t expired_before = rmw_fleetqox_cpp_service_expired_frames_dropped();

  int64_t stale_sequence = 0;
  const std::uint64_t stale_received_before = rmw_fleetqox_cpp_service_frames_received();
  const rmw_ret_t stale_send_ret = rmw_send_request(client, &stale_request, &stale_sequence);
  const bool stale_frame_received = wait_for_received_frames(stale_received_before, 1);
  std::this_thread::sleep_for(std::chrono::milliseconds(30));
  rmw_service_info_t stale_request_info{};
  bool stale_request_taken = false;
  const rmw_ret_t stale_take_ret =
    rmw_take_request(service, &stale_request_info, &taken_request, &stale_request_taken);

  int64_t fresh_sequence = 0;
  const std::uint64_t fresh_received_before = rmw_fleetqox_cpp_service_frames_received();
  const rmw_ret_t fresh_send_ret = rmw_send_request(client, &fresh_request, &fresh_sequence);
  const bool fresh_frame_received = wait_for_received_frames(fresh_received_before, 1);
  rmw_service_info_t fresh_request_info{};
  bool fresh_request_taken = false;
  rmw_ret_t fresh_take_ret = RMW_RET_OK;
  for (int attempt = 0; attempt < 100 && !fresh_request_taken; ++attempt) {
    fresh_take_ret = rmw_take_request(service, &fresh_request_info, &taken_request, &fresh_request_taken);
    if (fresh_take_ret != RMW_RET_OK || fresh_request_taken) {
      break;
    }
    std::this_thread::sleep_for(std::chrono::milliseconds(1));
  }

  const std::uint64_t response_received_before = rmw_fleetqox_cpp_service_frames_received();
  const rmw_ret_t send_response_ret =
    fresh_request_taken ? rmw_send_response(service, &fresh_request_info.request_id, &response) :
    RMW_RET_ERROR;
  const bool response_frame_received =
    send_response_ret == RMW_RET_OK && wait_for_received_frames(response_received_before, 1);
  std::this_thread::sleep_for(std::chrono::milliseconds(30));
  rmw_service_info_t response_info{};
  bool stale_response_taken = false;
  const rmw_ret_t take_response_ret =
    rmw_take_response(client, &response_info, &taken_response, &stale_response_taken);

  rmw_request_id_t unknown_request_id{};
  unknown_request_id.sequence_number = 9999;
  const std::uint64_t unknown_response_sent_before = rmw_fleetqox_cpp_socket_frames_sent();
  const rmw_ret_t unknown_response_ret =
    rmw_send_response(service, &unknown_request_id, &response);
  const std::uint64_t unknown_response_sent_delta =
    rmw_fleetqox_cpp_socket_frames_sent() - unknown_response_sent_before;
  if (unknown_response_ret != RMW_RET_OK) {
    rmw_reset_error();
  }

  const char * type_mismatch_service_name =
    "/fleetqox/service_availability_type_mismatch";
  rmw_service_t * type_mismatch_service = rmw_create_service(
    node, trigger_type_support, type_mismatch_service_name, &service_qos);
  rmw_client_t * type_mismatch_client = rmw_create_client(
    node, type_support, type_mismatch_service_name, &client_qos);
  bool type_mismatch_available = true;
  const rmw_ret_t type_mismatch_available_ret =
    type_mismatch_service != nullptr && type_mismatch_client != nullptr ?
    rmw_service_server_is_available(node, type_mismatch_client, &type_mismatch_available) :
    RMW_RET_ERROR;

  const char * qos_mismatch_service_name =
    "/fleetqox/service_availability_qos_mismatch";
  rmw_qos_profile_t best_effort_service_qos = service_qos;
  best_effort_service_qos.reliability = RMW_QOS_POLICY_RELIABILITY_BEST_EFFORT;
  rmw_qos_profile_t reliable_client_qos = client_qos;
  reliable_client_qos.reliability = RMW_QOS_POLICY_RELIABILITY_RELIABLE;
  rmw_service_t * qos_mismatch_service = rmw_create_service(
    node, type_support, qos_mismatch_service_name, &best_effort_service_qos);
  rmw_client_t * qos_mismatch_client = rmw_create_client(
    node, type_support, qos_mismatch_service_name, &reliable_client_qos);
  bool qos_mismatch_available = true;
  const rmw_ret_t qos_mismatch_available_ret =
    qos_mismatch_service != nullptr && qos_mismatch_client != nullptr ?
    rmw_service_server_is_available(node, qos_mismatch_client, &qos_mismatch_available) :
    RMW_RET_ERROR;
  int64_t type_mismatch_sequence = 0;
  const std::uint64_t type_mismatch_received_before =
    rmw_fleetqox_cpp_service_frames_received();
  const rmw_ret_t type_mismatch_send_ret = type_mismatch_client != nullptr ?
    rmw_send_request(type_mismatch_client, &fresh_request, &type_mismatch_sequence) :
    RMW_RET_ERROR;
  const bool type_mismatch_frame_received =
    type_mismatch_send_ret == RMW_RET_OK &&
    wait_for_received_frames(type_mismatch_received_before, 1);
  const bool type_mismatch_request_queued =
    type_mismatch_service != nullptr &&
    rmw_fleetqox_cpp_waitable_service_has_request(type_mismatch_service);
  int64_t qos_mismatch_sequence = 0;
  const std::uint64_t qos_mismatch_received_before =
    rmw_fleetqox_cpp_service_frames_received();
  const rmw_ret_t qos_mismatch_send_ret = qos_mismatch_client != nullptr ?
    rmw_send_request(qos_mismatch_client, &fresh_request, &qos_mismatch_sequence) :
    RMW_RET_ERROR;
  const bool qos_mismatch_frame_received =
    qos_mismatch_send_ret == RMW_RET_OK &&
    wait_for_received_frames(qos_mismatch_received_before, 1);
  const bool qos_mismatch_request_queued =
    qos_mismatch_service != nullptr &&
    rmw_fleetqox_cpp_waitable_service_has_request(qos_mismatch_service);

  const std::uint64_t expired_after = rmw_fleetqox_cpp_service_expired_frames_dropped();
  const std::uint64_t expired_delta = expired_after - expired_before;

  const bool stale_request_ok =
    stale_send_ret == RMW_RET_OK &&
    stale_frame_received &&
    stale_take_ret == RMW_RET_OK &&
    !stale_request_taken;
  const bool stale_response_ok =
    fresh_send_ret == RMW_RET_OK &&
    fresh_frame_received &&
    fresh_take_ret == RMW_RET_OK &&
    fresh_request_taken &&
    send_response_ret == RMW_RET_OK &&
    response_frame_received &&
    take_response_ret == RMW_RET_OK &&
    !stale_response_taken;
  const bool unknown_response_ok =
    unknown_response_ret == RMW_RET_ERROR &&
    unknown_response_sent_delta == 0;
  const bool request_writer_gid_matches_client =
    fresh_request_taken &&
    std::memcmp(
    client_gid.data,
    fresh_request_info.request_id.writer_guid,
    RMW_GID_STORAGE_SIZE) == 0;
  const bool request_sequence_matches =
    fresh_request_taken &&
    fresh_request_info.request_id.sequence_number == fresh_sequence;
  const bool service_availability_matching_ok =
    matching_service_available_ret == RMW_RET_OK && matching_service_available;
  const bool service_availability_type_filter_ok =
    type_mismatch_available_ret == RMW_RET_OK && !type_mismatch_available;
  const bool service_availability_qos_filter_ok =
    qos_mismatch_available_ret == RMW_RET_OK && !qos_mismatch_available;
  const bool service_request_type_filter_ok =
    type_mismatch_send_ret == RMW_RET_OK && type_mismatch_frame_received &&
    !type_mismatch_request_queued;
  const bool service_request_qos_filter_ok =
    qos_mismatch_send_ret == RMW_RET_OK && qos_mismatch_frame_received &&
    !qos_mismatch_request_queued;

  std_srvs__srv__SetBool_Request__fini(&stale_request);
  std_srvs__srv__SetBool_Request__fini(&fresh_request);
  std_srvs__srv__SetBool_Request__fini(&taken_request);
  std_srvs__srv__SetBool_Response__fini(&response);
  std_srvs__srv__SetBool_Response__fini(&taken_response);

  const rmw_ret_t destroy_qos_mismatch_client_ret = qos_mismatch_client != nullptr ?
    rmw_destroy_client(node, qos_mismatch_client) : RMW_RET_ERROR;
  const rmw_ret_t destroy_qos_mismatch_service_ret = qos_mismatch_service != nullptr ?
    rmw_destroy_service(node, qos_mismatch_service) : RMW_RET_ERROR;
  const rmw_ret_t destroy_type_mismatch_client_ret = type_mismatch_client != nullptr ?
    rmw_destroy_client(node, type_mismatch_client) : RMW_RET_ERROR;
  const rmw_ret_t destroy_type_mismatch_service_ret = type_mismatch_service != nullptr ?
    rmw_destroy_service(node, type_mismatch_service) : RMW_RET_ERROR;
  const rmw_ret_t destroy_peer_client_ret = rmw_destroy_client(node, peer_client);
  const rmw_ret_t destroy_client_ret = rmw_destroy_client(node, client);
  const rmw_ret_t destroy_service_ret = rmw_destroy_service(node, service);
  const rmw_ret_t destroy_node_ret = rmw_destroy_node(node);
  const rmw_ret_t destroy_other_node_ret = rmw_destroy_node(other_node);
  cleanup_context(&context, &options);

  const bool cleanup_ok =
    destroy_qos_mismatch_client_ret == RMW_RET_OK &&
    destroy_qos_mismatch_service_ret == RMW_RET_OK &&
    destroy_type_mismatch_client_ret == RMW_RET_OK &&
    destroy_type_mismatch_service_ret == RMW_RET_OK &&
    destroy_peer_client_ret == RMW_RET_OK &&
    destroy_client_ret == RMW_RET_OK &&
    destroy_service_ret == RMW_RET_OK &&
    destroy_node_ret == RMW_RET_OK &&
    destroy_other_node_ret == RMW_RET_OK;
  const bool ok =
    stale_request_ok && stale_response_ok && unknown_response_ok &&
    client_gid_stable && client_gids_distinct && client_gid_nonzero &&
    request_writer_gid_matches_client && request_sequence_matches &&
    service_availability_matching_ok && service_availability_type_filter_ok &&
    service_availability_qos_filter_ok && service_request_type_filter_ok &&
    service_request_qos_filter_ok && service_availability_owner_node_enforced &&
    client_destroy_owner_node_enforced && service_destroy_owner_node_enforced &&
    expired_delta >= 2 && cleanup_ok;

  std::cout << "{\"schema_version\":\"fleetrmw.rmw_service_qos_probe.v1\",";
  std::cout << "\"status\":\"" << (ok ? "ok" : "failed") << "\",";
  std::cout << "\"service\":\"" << json_escape(service_name) << "\",";
  std::cout << "\"lifespan_ns\":5000000,";
  std::cout << "\"stale_request_sequence\":" << stale_sequence << ",";
  std::cout << "\"stale_request_frame_received\":" << (stale_frame_received ? "true" : "false") << ",";
  std::cout << "\"stale_request_taken\":" << (stale_request_taken ? "true" : "false") << ",";
  std::cout << "\"fresh_request_sequence\":" << fresh_sequence << ",";
  std::cout << "\"fresh_request_taken\":" << (fresh_request_taken ? "true" : "false") << ",";
  std::cout << "\"stale_response_frame_received\":" << (response_frame_received ? "true" : "false") << ",";
  std::cout << "\"stale_response_taken\":" << (stale_response_taken ? "true" : "false") << ",";
  std::cout << "\"unknown_response_ret\":" << unknown_response_ret << ",";
  std::cout << "\"unknown_response_error\":" << (unknown_response_ret == RMW_RET_ERROR ? "true" : "false") << ",";
  std::cout << "\"unknown_response_sent_delta\":" << unknown_response_sent_delta << ",";
  std::cout << "\"client_gid_ret\":" << client_gid_ret << ",";
  std::cout << "\"client_gid_stable\":" << (client_gid_stable ? "true" : "false") << ",";
  std::cout << "\"client_gids_distinct\":" << (client_gids_distinct ? "true" : "false") << ",";
  std::cout << "\"client_gid_nonzero\":" << (client_gid_nonzero ? "true" : "false") << ",";
  std::cout << "\"request_writer_gid_matches_client\":" <<
    (request_writer_gid_matches_client ? "true" : "false") << ",";
  std::cout << "\"request_sequence_matches\":" <<
    (request_sequence_matches ? "true" : "false") << ",";
  std::cout << "\"service_availability_matching_ok\":" <<
    (service_availability_matching_ok ? "true" : "false") << ",";
  std::cout << "\"service_availability_type_filter_ok\":" <<
    (service_availability_type_filter_ok ? "true" : "false") << ",";
  std::cout << "\"service_availability_qos_filter_ok\":" <<
    (service_availability_qos_filter_ok ? "true" : "false") << ",";
  std::cout << "\"service_request_type_filter_ok\":" <<
    (service_request_type_filter_ok ? "true" : "false") << ",";
  std::cout << "\"service_request_qos_filter_ok\":" <<
    (service_request_qos_filter_ok ? "true" : "false") << ",";
  std::cout << "\"service_availability_owner_node_enforced\":" <<
    (service_availability_owner_node_enforced ? "true" : "false") << ",";
  std::cout << "\"client_destroy_owner_node_enforced\":" <<
    (client_destroy_owner_node_enforced ? "true" : "false") << ",";
  std::cout << "\"service_destroy_owner_node_enforced\":" <<
    (service_destroy_owner_node_enforced ? "true" : "false") << ",";
  std::cout << "\"expired_frames_dropped_delta\":" << expired_delta << ",";
  std::cout << "\"cleanup_ok\":" << (cleanup_ok ? "true" : "false") << "}" << std::endl;

  return ok ? 0 : 1;
}

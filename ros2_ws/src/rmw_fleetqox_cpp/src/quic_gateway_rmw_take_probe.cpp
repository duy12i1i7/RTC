#include <chrono>
#include <cstdint>
#include <cstring>
#include <iostream>
#include <sstream>
#include <string>
#include <thread>

#include "rcutils/allocator.h"
#include "rmw/init.h"
#include "rmw/init_options.h"
#include "rmw/qos_profiles.h"
#include "rmw/rmw.h"
#include "rmw/serialized_message.h"
#include "rmw/subscription_options.h"
#include "rosidl_runtime_c/message_type_support_struct.h"

namespace
{

constexpr const char * kTopic = "/fleetqox/quic_gateway_rmw_take_probe";
constexpr const char * kExpectedPayload = "fleetqox-quic-gateway-rmw-take-v1";

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

extern "C" const char * rmw_fleetqox_cpp_transport_mode();
extern "C" const char * rmw_fleetqox_cpp_quic_gateway_uri();
extern "C" std::uint64_t rmw_fleetqox_cpp_quic_gateway_frames_received();
extern "C" std::uint64_t rmw_fleetqox_cpp_quic_gateway_bytes_received();
extern "C" std::uint64_t rmw_fleetqox_cpp_quic_gateway_frames_failed();
extern "C" int rmw_fleetqox_cpp_quic_gateway_last_exit_code();

int main()
{
  rcutils_allocator_t allocator = rcutils_get_default_allocator();
  rmw_init_options_t options = rmw_get_zero_initialized_init_options();
  rmw_ret_t ret = rmw_init_options_init(&options, allocator);
  if (ret != RMW_RET_OK) {
    std::cout << "{\"status\":\"init_options_failed\",\"ret\":" << ret << "}\n";
    return 1;
  }
  options.instance_id = 101;

  rmw_context_t context = rmw_get_zero_initialized_context();
  ret = rmw_init(&options, &context);
  if (ret != RMW_RET_OK) {
    const rmw_ret_t fini_ret = rmw_init_options_fini(&options);
    (void)fini_ret;
    std::cout << "{\"status\":\"init_failed\",\"ret\":" << ret << "}\n";
    return 1;
  }

  rmw_node_t * node = rmw_create_node(&context, "fleetqox_quic_gateway_rmw_take_probe", "/fleetqox");
  if (node == nullptr) {
    cleanup_context(&context, &options);
    std::cout << "{\"status\":\"create_node_failed\"}\n";
    return 1;
  }

  rosidl_message_type_support_t type_support{};
  type_support.typesupport_identifier = "rmw_fleetqox_cpp_quic_gateway_rmw_take_probe";
  rmw_subscription_options_t subscription_options = rmw_get_default_subscription_options();
  rmw_qos_profile_t qos = rmw_qos_profile_default;
  rmw_subscription_t * subscription = rmw_create_subscription(
    node, &type_support, kTopic, &qos, &subscription_options);
  if (subscription == nullptr) {
    const rmw_ret_t destroy_node_ret = rmw_destroy_node(node);
    (void)destroy_node_ret;
    cleanup_context(&context, &options);
    std::cout << "{\"status\":\"create_subscription_failed\"}\n";
    return 1;
  }

  rmw_serialized_message_t incoming = rmw_get_zero_initialized_serialized_message();
  if (rmw_serialized_message_init(&incoming, 1, &allocator) != RMW_RET_OK) {
    const rmw_ret_t destroy_sub_ret = rmw_destroy_subscription(node, subscription);
    const rmw_ret_t destroy_node_ret = rmw_destroy_node(node);
    (void)destroy_sub_ret;
    (void)destroy_node_ret;
    cleanup_context(&context, &options);
    std::cout << "{\"status\":\"serialized_message_init_failed\"}\n";
    return 1;
  }

  const std::uint64_t frames_received_before =
    rmw_fleetqox_cpp_quic_gateway_frames_received();
  const std::uint64_t bytes_received_before =
    rmw_fleetqox_cpp_quic_gateway_bytes_received();
  bool taken = false;
  for (int attempt = 0; attempt < 2 && !taken; ++attempt) {
    ret = rmw_take_serialized_message(subscription, &incoming, &taken, nullptr);
    if (ret != RMW_RET_OK || taken) {
      break;
    }
    std::this_thread::sleep_for(std::chrono::milliseconds(10));
  }
  const std::uint64_t frames_received =
    rmw_fleetqox_cpp_quic_gateway_frames_received() - frames_received_before;
  const std::uint64_t bytes_received =
    rmw_fleetqox_cpp_quic_gateway_bytes_received() - bytes_received_before;

  std::string received;
  if (taken && incoming.buffer != nullptr) {
    received.assign(
      reinterpret_cast<const char *>(incoming.buffer),
      reinterpret_cast<const char *>(incoming.buffer + incoming.buffer_length));
  }
  const bool payload_ok = received == kExpectedPayload;
  const bool ok =
    ret == RMW_RET_OK &&
    taken &&
    payload_ok &&
    frames_received == 1 &&
    bytes_received > 0 &&
    rmw_fleetqox_cpp_quic_gateway_last_exit_code() == 0;

  std::cout << "{\"schema_version\":\"fleetrmw.quic_gateway_rmw_take_probe.v1\",";
  std::cout << "\"status\":\"" << (ok ? "ok" : "failed") << "\",";
  std::cout << "\"topic\":\"" << kTopic << "\",";
  std::cout << "\"taken\":" << (taken ? "true" : "false") << ",";
  std::cout << "\"taken_bytes\":" << incoming.buffer_length << ",";
  std::cout << "\"payload_ok\":" << (payload_ok ? "true" : "false") << ",";
  std::cout << "\"payload\":\"" << json_escape(received) << "\",";
  std::cout << "\"transport_mode\":\"" << json_escape(rmw_fleetqox_cpp_transport_mode()) << "\",";
  std::cout << "\"endpoint_uri\":\"" << json_escape(rmw_fleetqox_cpp_quic_gateway_uri()) << "\",";
  std::cout << "\"quic_gateway_frames_received\":" << frames_received << ",";
  std::cout << "\"quic_gateway_bytes_received\":" << bytes_received << ",";
  std::cout << "\"quic_gateway_frames_failed\":" <<
    rmw_fleetqox_cpp_quic_gateway_frames_failed() << ",";
  std::cout << "\"quic_gateway_last_exit_code\":" <<
    rmw_fleetqox_cpp_quic_gateway_last_exit_code() << ",";
  std::cout << "\"quic_gateway_take_path_download\":true,";
  std::cout << "\"rmw_take_path_integrated\":true,";
  std::cout << "\"take_path_scope\":\"rmw_take_serialized_message_on_demand_quic_gateway_get\",";
  std::cout << "\"subprocess_backed\":true,";
  std::cout << "\"production_quic_backend\":false,";
  std::cout << "\"full_bidirectional_quic_backend\":false";
  if (ret != RMW_RET_OK) {
    std::cout << ",\"ret\":" << ret;
  }
  std::cout << "}\n";

  const rmw_ret_t incoming_fini_ret = rmw_serialized_message_fini(&incoming);
  const rmw_ret_t destroy_sub_ret = rmw_destroy_subscription(node, subscription);
  const rmw_ret_t destroy_node_ret = rmw_destroy_node(node);
  cleanup_context(&context, &options);
  return ok &&
         incoming_fini_ret == RMW_RET_OK &&
         destroy_sub_ret == RMW_RET_OK &&
         destroy_node_ret == RMW_RET_OK ? 0 : 1;
}

#include <cstdint>
#include <cstdlib>
#include <iostream>
#include <sstream>
#include <string>
#include <vector>

#include "rcutils/allocator.h"
#include "rmw/init.h"
#include "rmw/init_options.h"
#include "rmw/publisher_options.h"
#include "rmw/qos_profiles.h"
#include "rmw/rmw.h"
#include "rmw/subscription_options.h"
#include "rosidl_runtime_c/string_functions.h"
#include "rosidl_typesupport_interface/macros.h"
#include "std_msgs/msg/detail/string__functions.h"
#include "std_msgs/msg/detail/string__rosidl_typesupport_introspection_c.h"
#include "std_msgs/msg/detail/string__struct.h"

namespace
{

constexpr const char * kTopic = "/fleetqox/stateful_rmw";
constexpr int kMessageCount = 3;

std::string expected_payload(int index)
{
  return "fleetqox-stateful-rmw-" + std::to_string(index);
}

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

bool init_context(
  const std::string & mode,
  rcutils_allocator_t allocator,
  rmw_init_options_t * options,
  rmw_context_t * context)
{
  *options = rmw_get_zero_initialized_init_options();
  if (rmw_init_options_init(options, allocator) != RMW_RET_OK) {
    return false;
  }
  options->instance_id = mode == "publisher" ? 211 : 212;
  options->domain_id = 42;
  *context = rmw_get_zero_initialized_context();
  if (rmw_init(options, context) != RMW_RET_OK) {
    const rmw_ret_t fini_ret = rmw_init_options_fini(options);
    (void)fini_ret;
    return false;
  }
  return true;
}

}  // namespace

extern "C" const char * rmw_fleetqox_cpp_transport_mode();
extern "C" const char * rmw_fleetqox_cpp_quic_gateway_backend();
extern "C" bool rmw_fleetqox_cpp_quic_gateway_subprocess_backed();
extern "C" std::uint64_t rmw_fleetqox_cpp_quic_gateway_frames_sent();
extern "C" std::uint64_t rmw_fleetqox_cpp_quic_gateway_frames_received();
extern "C" std::uint64_t rmw_fleetqox_cpp_quic_gateway_frames_failed();
extern "C" std::uint64_t rmw_fleetqox_cpp_quic_gateway_connections_created();
extern "C" std::uint64_t rmw_fleetqox_cpp_quic_gateway_handshakes_completed();
extern "C" std::uint64_t rmw_fleetqox_cpp_quic_gateway_streams_opened();
extern "C" std::uint64_t rmw_fleetqox_cpp_quic_gateway_connection_reuse_count();
extern "C" std::uint64_t rmw_fleetqox_cpp_quic_gateway_reconnects();

int main(int argc, char ** argv)
{
  const std::string mode = argc == 3 && std::string(argv[1]) == "--mode" ? argv[2] : "";
  if (mode != "publisher" && mode != "subscriber") {
    std::cout << "{\"schema_version\":\"fleetrmw.quic_stateful_rmw_probe.v1\","
              << "\"status\":\"invalid_mode\"}\n";
    return 2;
  }

  rcutils_allocator_t allocator = rcutils_get_default_allocator();
  rmw_init_options_t options{};
  rmw_context_t context{};
  if (!init_context(mode, allocator, &options, &context)) {
    std::cout << "{\"schema_version\":\"fleetrmw.quic_stateful_rmw_probe.v1\","
              << "\"mode\":\"" << mode << "\",\"status\":\"init_failed\"}\n";
    return 1;
  }

  const std::string node_name = "fleetqox_quic_stateful_rmw_" + mode;
  rmw_node_t * node = rmw_create_node(&context, node_name.c_str(), "/fleetqox");
  if (node == nullptr) {
    cleanup_context(&context, &options);
    std::cout << "{\"schema_version\":\"fleetrmw.quic_stateful_rmw_probe.v1\","
              << "\"mode\":\"" << mode << "\",\"status\":\"create_node_failed\"}\n";
    return 1;
  }

  const rosidl_message_type_support_t * type_support =
    ROSIDL_TYPESUPPORT_INTERFACE__MESSAGE_SYMBOL_NAME(
    rosidl_typesupport_introspection_c, std_msgs, msg, String)();
  rmw_qos_profile_t qos = rmw_qos_profile_default;
  rmw_publisher_t * publisher = nullptr;
  rmw_subscription_t * subscription = nullptr;
  if (mode == "publisher") {
    rmw_publisher_options_t publisher_options = rmw_get_default_publisher_options();
    publisher = rmw_create_publisher(node, type_support, kTopic, &qos, &publisher_options);
  } else {
    rmw_subscription_options_t subscription_options = rmw_get_default_subscription_options();
    subscription = rmw_create_subscription(
      node, type_support, kTopic, &qos, &subscription_options);
  }
  if ((mode == "publisher" && publisher == nullptr) ||
    (mode == "subscriber" && subscription == nullptr))
  {
    const rmw_ret_t destroy_node_ret = rmw_destroy_node(node);
    (void)destroy_node_ret;
    cleanup_context(&context, &options);
    std::cout << "{\"schema_version\":\"fleetrmw.quic_stateful_rmw_probe.v1\","
              << "\"mode\":\"" << mode << "\",\"status\":\"create_endpoint_failed\"}\n";
    return 1;
  }

  int completed = 0;
  bool ordered_payloads = true;
  std::vector<std::string> received_payloads;
  rmw_ret_t operation_ret = RMW_RET_OK;
  if (mode == "publisher") {
    for (int index = 1; index <= kMessageCount; ++index) {
      std_msgs__msg__String outgoing;
      if (!std_msgs__msg__String__init(&outgoing)) {
        operation_ret = RMW_RET_BAD_ALLOC;
        break;
      }
      const std::string payload = expected_payload(index);
      const bool assigned = rosidl_runtime_c__String__assignn(
        &outgoing.data, payload.data(), payload.size());
      operation_ret = assigned ? rmw_publish(publisher, &outgoing, nullptr) : RMW_RET_BAD_ALLOC;
      std_msgs__msg__String__fini(&outgoing);
      if (operation_ret != RMW_RET_OK) {
        break;
      }
      ++completed;
    }
  } else {
    std_msgs__msg__String incoming;
    if (!std_msgs__msg__String__init(&incoming)) {
      operation_ret = RMW_RET_BAD_ALLOC;
    } else {
      for (int index = 1; index <= kMessageCount; ++index) {
        bool taken = false;
        operation_ret = rmw_take(subscription, &incoming, &taken, nullptr);
        if (operation_ret != RMW_RET_OK || !taken) {
          ordered_payloads = false;
          break;
        }
        const std::string received = incoming.data.data == nullptr ? "" : incoming.data.data;
        received_payloads.push_back(received);
        ordered_payloads = ordered_payloads && received == expected_payload(index);
        ++completed;
      }
      std_msgs__msg__String__fini(&incoming);
    }
  }

  const std::uint64_t connections = rmw_fleetqox_cpp_quic_gateway_connections_created();
  const std::uint64_t handshakes = rmw_fleetqox_cpp_quic_gateway_handshakes_completed();
  const std::uint64_t streams = rmw_fleetqox_cpp_quic_gateway_streams_opened();
  const std::uint64_t reuse = rmw_fleetqox_cpp_quic_gateway_connection_reuse_count();
  const std::uint64_t expected_sent = mode == "publisher" ? kMessageCount : 0;
  const std::uint64_t expected_received = mode == "subscriber" ? kMessageCount : 0;
  const bool ok =
    operation_ret == RMW_RET_OK && completed == kMessageCount && ordered_payloads &&
    std::string(rmw_fleetqox_cpp_transport_mode()) == "quic_gateway" &&
    std::string(rmw_fleetqox_cpp_quic_gateway_backend()) == "inprocess" &&
    !rmw_fleetqox_cpp_quic_gateway_subprocess_backed() &&
    rmw_fleetqox_cpp_quic_gateway_frames_sent() == expected_sent &&
    rmw_fleetqox_cpp_quic_gateway_frames_received() == expected_received &&
    rmw_fleetqox_cpp_quic_gateway_frames_failed() == 0 &&
    connections == 1 && handshakes == 1 && streams == kMessageCount &&
    reuse == kMessageCount - 1 && rmw_fleetqox_cpp_quic_gateway_reconnects() == 0;

  std::cout << "{\"schema_version\":\"fleetrmw.quic_stateful_rmw_probe.v1\",";
  std::cout << "\"mode\":\"" << mode << "\",";
  std::cout << "\"status\":\"" << (ok ? "ok" : "failed") << "\",";
  std::cout << "\"topic\":\"" << kTopic << "\",";
  std::cout << "\"message_count\":" << kMessageCount << ",";
  std::cout << "\"completed_count\":" << completed << ",";
  std::cout << "\"ordered_payloads\":" << (ordered_payloads ? "true" : "false") << ",";
  std::cout << "\"frames_sent\":" << rmw_fleetqox_cpp_quic_gateway_frames_sent() << ",";
  std::cout << "\"frames_received\":" << rmw_fleetqox_cpp_quic_gateway_frames_received() << ",";
  std::cout << "\"connections_created\":" << connections << ",";
  std::cout << "\"handshakes_completed\":" << handshakes << ",";
  std::cout << "\"streams_opened\":" << streams << ",";
  std::cout << "\"connection_reuse_count\":" << reuse << ",";
  std::cout << "\"rmw_publish_path_integrated\":" <<
    (mode == "publisher" ? "true" : "false") << ",";
  std::cout << "\"rmw_take_path_integrated\":" <<
    (mode == "subscriber" ? "true" : "false") << ",";
  std::cout << "\"stateful_gateway_interprocess_claim\":true,";
  std::cout << "\"tls_peer_verification_required\":true,";
  std::cout << "\"subprocess_backed\":false,";
  std::cout << "\"production_readiness\":false";
  if (operation_ret != RMW_RET_OK) {
    std::cout << ",\"ret\":" << operation_ret;
  }
  if (!received_payloads.empty()) {
    std::cout << ",\"last_payload\":\"" << json_escape(received_payloads.back()) << "\"";
  }
  std::cout << "}\n";

  const rmw_ret_t destroy_endpoint_ret = mode == "publisher" ?
    rmw_destroy_publisher(node, publisher) : rmw_destroy_subscription(node, subscription);
  const rmw_ret_t destroy_node_ret = rmw_destroy_node(node);
  cleanup_context(&context, &options);
  return ok && destroy_endpoint_ret == RMW_RET_OK && destroy_node_ret == RMW_RET_OK ? 0 : 1;
}

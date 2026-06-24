#include <chrono>
#include <cstdint>
#include <cstring>
#include <iostream>
#include <sstream>
#include <string>
#include <thread>

#include "rcutils/allocator.h"
#include "rmw/allocators.h"
#include "rmw/init.h"
#include "rmw/init_options.h"
#include "rmw/publisher_options.h"
#include "rmw/qos_profiles.h"
#include "rmw/rmw.h"
#include "rmw/serialized_message.h"
#include "rmw/subscription_options.h"
#include "rosidl_runtime_c/message_type_support_struct.h"

extern "C" std::uint64_t rmw_fleetqox_cpp_socket_frames_received();
extern "C" std::uint64_t rmw_fleetqox_cpp_publisher_allocations_initialized();
extern "C" std::uint64_t rmw_fleetqox_cpp_publisher_allocations_finalized();
extern "C" std::uint64_t rmw_fleetqox_cpp_subscription_allocations_initialized();
extern "C" std::uint64_t rmw_fleetqox_cpp_subscription_allocations_finalized();

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

bool init_serialized_message(
  rmw_serialized_message_t * message,
  const std::string & payload,
  rcutils_allocator_t * allocator)
{
  if (rmw_serialized_message_init(message, payload.size(), allocator) != RMW_RET_OK) {
    return false;
  }
  if (!payload.empty()) {
    std::memcpy(message->buffer, payload.data(), payload.size());
  }
  message->buffer_length = payload.size();
  return true;
}

std::string serialized_message_string(const rmw_serialized_message_t & message)
{
  if (message.buffer == nullptr || message.buffer_length == 0) {
    return "";
  }
  return std::string(
    reinterpret_cast<const char *>(message.buffer),
    reinterpret_cast<const char *>(message.buffer + message.buffer_length));
}

bool wait_for_received_frames(std::uint64_t baseline, std::uint64_t expected_delta)
{
  for (int attempt = 0; attempt < 200; ++attempt) {
    if (rmw_fleetqox_cpp_socket_frames_received() >= baseline + expected_delta) {
      return true;
    }
    std::this_thread::sleep_for(std::chrono::milliseconds(1));
  }
  return false;
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
  options.instance_id = 55;

  rmw_context_t context = rmw_get_zero_initialized_context();
  ret = rmw_init(&options, &context);
  if (ret != RMW_RET_OK) {
    const rmw_ret_t fini_ret = rmw_init_options_fini(&options);
    (void)fini_ret;
    std::cout << "{\"status\":\"init_failed\",\"ret\":" << ret << "}" << std::endl;
    return 1;
  }

  rmw_node_t * node = rmw_create_node(&context, "fleetqox_allocation_probe", "/fleetqox");
  if (node == nullptr) {
    cleanup_context(&context, &options);
    std::cout << "{\"status\":\"create_node_failed\"}" << std::endl;
    return 1;
  }

  rosidl_message_type_support_t type_support{};
  type_support.typesupport_identifier = "rmw_fleetqox_cpp_allocation_probe";
  rmw_publisher_allocation_t publisher_allocation{};
  rmw_subscription_allocation_t subscription_allocation{};
  const std::uint64_t pub_init_before = rmw_fleetqox_cpp_publisher_allocations_initialized();
  const std::uint64_t sub_init_before = rmw_fleetqox_cpp_subscription_allocations_initialized();
  const rmw_ret_t pub_alloc_init_ret =
    rmw_init_publisher_allocation(&type_support, nullptr, &publisher_allocation);
  const rmw_ret_t sub_alloc_init_ret =
    rmw_init_subscription_allocation(&type_support, nullptr, &subscription_allocation);

  rmw_publisher_options_t publisher_options = rmw_get_default_publisher_options();
  rmw_subscription_options_t subscription_options = rmw_get_default_subscription_options();
  rmw_qos_profile_t qos = rmw_qos_profile_default;
  qos.history = RMW_QOS_POLICY_HISTORY_KEEP_LAST;
  qos.depth = 4;
  const char * topic = "/fleetqox/allocation_probe";
  rmw_publisher_t * publisher = rmw_create_publisher(
    node, &type_support, topic, &qos, &publisher_options);
  rmw_subscription_t * subscription = rmw_create_subscription(
    node, &type_support, topic, &qos, &subscription_options);

  rmw_serialized_message_t outgoing = rmw_get_zero_initialized_serialized_message();
  rmw_serialized_message_t incoming = rmw_get_zero_initialized_serialized_message();
  const std::string payload = "fleetqox allocation ABI no-op publish/take";
  const bool messages_initialized =
    init_serialized_message(&outgoing, payload, &allocator) &&
    rmw_serialized_message_init(&incoming, 1, &allocator) == RMW_RET_OK;

  const std::uint64_t frames_before = rmw_fleetqox_cpp_socket_frames_received();
  const rmw_ret_t publish_ret = publisher == nullptr || !messages_initialized ?
    RMW_RET_ERROR :
    rmw_publish_serialized_message(publisher, &outgoing, &publisher_allocation);
  const bool receive_ready = wait_for_received_frames(frames_before, publish_ret == RMW_RET_OK ? 1 : 0);
  bool taken = false;
  const rmw_ret_t take_ret = subscription == nullptr || !messages_initialized ?
    RMW_RET_ERROR :
    rmw_take_serialized_message(subscription, &incoming, &taken, &subscription_allocation);
  const std::string received = serialized_message_string(incoming);

  const std::uint64_t pub_fini_before = rmw_fleetqox_cpp_publisher_allocations_finalized();
  const std::uint64_t sub_fini_before = rmw_fleetqox_cpp_subscription_allocations_finalized();
  const rmw_ret_t pub_alloc_fini_ret = rmw_fini_publisher_allocation(&publisher_allocation);
  const rmw_ret_t sub_alloc_fini_ret = rmw_fini_subscription_allocation(&subscription_allocation);

  const rmw_ret_t outgoing_fini_ret = rmw_serialized_message_fini(&outgoing);
  const rmw_ret_t incoming_fini_ret = rmw_serialized_message_fini(&incoming);
  const rmw_ret_t destroy_pub_ret = publisher == nullptr ?
    RMW_RET_ERROR : rmw_destroy_publisher(node, publisher);
  const rmw_ret_t destroy_sub_ret = subscription == nullptr ?
    RMW_RET_ERROR : rmw_destroy_subscription(node, subscription);
  const rmw_ret_t destroy_node_ret = rmw_destroy_node(node);
  cleanup_context(&context, &options);

  const std::uint64_t pub_init_delta =
    rmw_fleetqox_cpp_publisher_allocations_initialized() - pub_init_before;
  const std::uint64_t sub_init_delta =
    rmw_fleetqox_cpp_subscription_allocations_initialized() - sub_init_before;
  const std::uint64_t pub_fini_delta =
    rmw_fleetqox_cpp_publisher_allocations_finalized() - pub_fini_before;
  const std::uint64_t sub_fini_delta =
    rmw_fleetqox_cpp_subscription_allocations_finalized() - sub_fini_before;

  const bool allocation_lifecycle_ok =
    pub_alloc_init_ret == RMW_RET_OK &&
    sub_alloc_init_ret == RMW_RET_OK &&
    pub_alloc_fini_ret == RMW_RET_OK &&
    sub_alloc_fini_ret == RMW_RET_OK &&
    pub_init_delta == 1 &&
    sub_init_delta == 1 &&
    pub_fini_delta == 1 &&
    sub_fini_delta == 1;
  const bool publish_take_ok =
    publisher != nullptr &&
    subscription != nullptr &&
    messages_initialized &&
    publish_ret == RMW_RET_OK &&
    receive_ready &&
    take_ret == RMW_RET_OK &&
    taken &&
    received == payload;
  const bool cleanup_ok =
    outgoing_fini_ret == RMW_RET_OK &&
    incoming_fini_ret == RMW_RET_OK &&
    destroy_pub_ret == RMW_RET_OK &&
    destroy_sub_ret == RMW_RET_OK &&
    destroy_node_ret == RMW_RET_OK;
  const bool ok = allocation_lifecycle_ok && publish_take_ok && cleanup_ok;

  std::cout << "{\"schema_version\":\"fleetrmw.allocation_probe.v1\",";
  std::cout << "\"status\":\"" << (ok ? "ok" : "failed") << "\",";
  std::cout << "\"topic\":\"" << topic << "\",";
  std::cout << "\"publisher_allocation_init_ret\":" << static_cast<int>(pub_alloc_init_ret) << ",";
  std::cout << "\"subscription_allocation_init_ret\":" << static_cast<int>(sub_alloc_init_ret) << ",";
  std::cout << "\"publisher_allocation_fini_ret\":" << static_cast<int>(pub_alloc_fini_ret) << ",";
  std::cout << "\"subscription_allocation_fini_ret\":" << static_cast<int>(sub_alloc_fini_ret) << ",";
  std::cout << "\"publisher_allocation_init_delta\":" << pub_init_delta << ",";
  std::cout << "\"subscription_allocation_init_delta\":" << sub_init_delta << ",";
  std::cout << "\"publisher_allocation_fini_delta\":" << pub_fini_delta << ",";
  std::cout << "\"subscription_allocation_fini_delta\":" << sub_fini_delta << ",";
  std::cout << "\"publish_with_allocation_ret\":" << static_cast<int>(publish_ret) << ",";
  std::cout << "\"take_with_allocation_ret\":" << static_cast<int>(take_ret) << ",";
  std::cout << "\"receive_ready\":" << (receive_ready ? "true" : "false") << ",";
  std::cout << "\"taken\":" << (taken ? "true" : "false") << ",";
  std::cout << "\"received\":\"" << json_escape(received) << "\",";
  std::cout << "\"allocation_lifecycle_ok\":" <<
    (allocation_lifecycle_ok ? "true" : "false") << ",";
  std::cout << "\"publish_take_with_allocation_ok\":" <<
    (publish_take_ok ? "true" : "false") << ",";
  std::cout << "\"deep_preallocation\":false}" << std::endl;
  return ok ? 0 : 1;
}

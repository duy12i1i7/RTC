#include <cstdint>
#include <chrono>
#include <cstddef>
#include <iostream>
#include <sstream>
#include <string>
#include <thread>

#include "rcutils/allocator.h"
#include "rmw/init.h"
#include "rmw/init_options.h"
#include "rmw/publisher_options.h"
#include "rmw/qos_profiles.h"
#include "rmw/rmw.h"
#include "rosidl_runtime_c/string_functions.h"
#include "rosidl_typesupport_interface/macros.h"
#include "std_msgs/msg/detail/string__functions.h"
#include "std_msgs/msg/detail/string__rosidl_typesupport_introspection_c.h"
#include "std_msgs/msg/detail/string__struct.h"

extern "C" const char * rmw_fleetqox_cpp_transport_mode();
extern "C" std::uint64_t rmw_fleetqox_cpp_quic_gateway_frames_sent();
extern "C" std::uint64_t rmw_fleetqox_cpp_quic_gateway_bytes_sent();
extern "C" std::uint64_t rmw_fleetqox_cpp_quic_gateway_frames_enqueued();
extern "C" std::uint64_t rmw_fleetqox_cpp_quic_gateway_frames_failed();
extern "C" std::uint64_t rmw_fleetqox_cpp_quic_gateway_frames_dropped();
extern "C" size_t rmw_fleetqox_cpp_quic_gateway_queue_depth();
extern "C" size_t rmw_fleetqox_cpp_quic_gateway_max_queue_frames();
extern "C" bool rmw_fleetqox_cpp_quic_gateway_async_enabled();
extern "C" int rmw_fleetqox_cpp_quic_gateway_last_exit_code();
extern "C" const char * rmw_fleetqox_cpp_quic_gateway_uri();

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

bool init_context(
  rcutils_allocator_t allocator,
  rmw_init_options_t * options,
  rmw_context_t * context)
{
  *options = rmw_get_zero_initialized_init_options();
  if (rmw_init_options_init(options, allocator) != RMW_RET_OK) {
    return false;
  }
  options->instance_id = 53;
  *context = rmw_get_zero_initialized_context();
  if (rmw_init(options, context) != RMW_RET_OK) {
    const rmw_ret_t fini_ret = rmw_init_options_fini(options);
    (void)fini_ret;
    return false;
  }
  return true;
}

}  // namespace

int main()
{
  rcutils_allocator_t allocator = rcutils_get_default_allocator();
  rmw_init_options_t options{};
  rmw_context_t context{};
  if (!init_context(allocator, &options, &context)) {
    std::cout << "{\"status\":\"init_failed\"}" << std::endl;
    return 1;
  }

  rmw_node_t * node = rmw_create_node(&context, "fleetqox_quic_gateway_publish_probe", "/fleetqox");
  if (node == nullptr) {
    cleanup_context(&context, &options);
    std::cout << "{\"status\":\"create_node_failed\"}" << std::endl;
    return 1;
  }

  const rosidl_message_type_support_t * type_support =
    ROSIDL_TYPESUPPORT_INTERFACE__MESSAGE_SYMBOL_NAME(
    rosidl_typesupport_introspection_c, std_msgs, msg, String)();
  rmw_publisher_options_t publisher_options = rmw_get_default_publisher_options();
  rmw_qos_profile_t qos = rmw_qos_profile_default;
  const char * topic = "/fleetqox/quic_gateway_publish_probe";

  rmw_publisher_t * publisher =
    rmw_create_publisher(node, type_support, topic, &qos, &publisher_options);
  if (publisher == nullptr) {
    const rmw_ret_t destroy_node_ret = rmw_destroy_node(node);
    (void)destroy_node_ret;
    cleanup_context(&context, &options);
    std::cout << "{\"status\":\"create_publisher_failed\"}" << std::endl;
    return 1;
  }

  std_msgs__msg__String outgoing;
  if (!std_msgs__msg__String__init(&outgoing)) {
    std::cout << "{\"status\":\"message_init_failed\"}" << std::endl;
    return 1;
  }
  const std::string payload = "fleetqox quic gateway publish through rmw_publish";
  if (!rosidl_runtime_c__String__assignn(&outgoing.data, payload.data(), payload.size())) {
    std::cout << "{\"status\":\"string_assign_failed\"}" << std::endl;
    return 1;
  }

  const std::uint64_t quic_frames_before = rmw_fleetqox_cpp_quic_gateway_frames_sent();
  const std::uint64_t quic_bytes_before = rmw_fleetqox_cpp_quic_gateway_bytes_sent();
  const std::uint64_t quic_enqueued_before = rmw_fleetqox_cpp_quic_gateway_frames_enqueued();
  const std::uint64_t quic_failed_before = rmw_fleetqox_cpp_quic_gateway_frames_failed();
  const std::uint64_t quic_dropped_before = rmw_fleetqox_cpp_quic_gateway_frames_dropped();
  const bool quic_async_enabled = rmw_fleetqox_cpp_quic_gateway_async_enabled();
  const size_t quic_max_queue_frames = rmw_fleetqox_cpp_quic_gateway_max_queue_frames();
  const rmw_ret_t publish_ret = rmw_publish(publisher, &outgoing, nullptr);

  std::uint64_t quic_frames_sent = 0;
  std::uint64_t quic_bytes_sent = 0;
  std::uint64_t quic_frames_enqueued = 0;
  std::uint64_t quic_frames_failed = 0;
  std::uint64_t quic_frames_dropped = 0;
  size_t quic_queue_depth = 0;
  int quic_last_exit_code = 0;
  for (int attempt = 0; attempt < 120; ++attempt) {
    quic_frames_sent = rmw_fleetqox_cpp_quic_gateway_frames_sent() - quic_frames_before;
    quic_bytes_sent = rmw_fleetqox_cpp_quic_gateway_bytes_sent() - quic_bytes_before;
    quic_frames_enqueued =
      rmw_fleetqox_cpp_quic_gateway_frames_enqueued() - quic_enqueued_before;
    quic_frames_failed = rmw_fleetqox_cpp_quic_gateway_frames_failed() - quic_failed_before;
    quic_frames_dropped =
      rmw_fleetqox_cpp_quic_gateway_frames_dropped() - quic_dropped_before;
    quic_queue_depth = rmw_fleetqox_cpp_quic_gateway_queue_depth();
    quic_last_exit_code = rmw_fleetqox_cpp_quic_gateway_last_exit_code();
    if (publish_ret == RMW_RET_OK &&
      quic_frames_sent >= 1 &&
      quic_bytes_sent > 0 &&
      quic_last_exit_code == 0 &&
      (!quic_async_enabled || quic_frames_enqueued >= 1) &&
      quic_frames_failed == 0 &&
      quic_frames_dropped == 0)
    {
      break;
    }
    std::this_thread::sleep_for(std::chrono::milliseconds(100));
  }
  const std::string transport_mode = rmw_fleetqox_cpp_transport_mode();
  const std::string quic_uri = rmw_fleetqox_cpp_quic_gateway_uri();

  const bool ok = publish_ret == RMW_RET_OK &&
                  quic_frames_sent >= 1 &&
                  quic_bytes_sent > 0 &&
                  (!quic_async_enabled || quic_frames_enqueued >= 1) &&
                  quic_frames_failed == 0 &&
                  quic_frames_dropped == 0 &&
                  quic_last_exit_code == 0 &&
                  transport_mode.find("quic_gateway") != std::string::npos;

  std::cout << "{\"schema_version\":\"fleetrmw.quic_gateway_publish_probe.v1\",";
  std::cout << "\"status\":\"" << (ok ? "ok" : "failed") << "\",";
  std::cout << "\"topic\":\"" << topic << "\",";
  std::cout << "\"transport_mode\":\"" << json_escape(transport_mode) << "\",";
  std::cout << "\"quic_gateway_uri\":\"" << json_escape(quic_uri) << "\",";
  std::cout << "\"rmw_publish_returncode\":" << static_cast<int>(publish_ret) << ",";
  std::cout << "\"quic_gateway_frames_sent\":" << quic_frames_sent << ",";
  std::cout << "\"quic_gateway_bytes_sent\":" << quic_bytes_sent << ",";
  std::cout << "\"quic_gateway_async_enabled\":" << (quic_async_enabled ? "true" : "false") << ",";
  std::cout << "\"quic_gateway_frames_enqueued\":" << quic_frames_enqueued << ",";
  std::cout << "\"quic_gateway_frames_failed\":" << quic_frames_failed << ",";
  std::cout << "\"quic_gateway_frames_dropped\":" << quic_frames_dropped << ",";
  std::cout << "\"quic_gateway_queue_depth\":" << quic_queue_depth << ",";
  std::cout << "\"quic_gateway_max_queue_frames\":" << quic_max_queue_frames << ",";
  std::cout << "\"quic_gateway_last_exit_code\":" << quic_last_exit_code << ",";
  std::cout << "\"subprocess_backed\":true,";
  std::cout << "\"publish_returned_after_enqueue\":" <<
    (quic_async_enabled && quic_frames_enqueued >= 1 ? "true" : "false") << ",";
  std::cout << "\"rmw_publish_path_integrated\":true,";
  std::cout << "\"payload\":\"" << json_escape(payload) << "\"}" << std::endl;

  std_msgs__msg__String__fini(&outgoing);
  const rmw_ret_t destroy_pub_ret = rmw_destroy_publisher(node, publisher);
  const rmw_ret_t destroy_node_ret = rmw_destroy_node(node);
  cleanup_context(&context, &options);
  return ok && destroy_pub_ret == RMW_RET_OK && destroy_node_ret == RMW_RET_OK ? 0 : 1;
}

#include <condition_variable>
#include <cstddef>
#include <cstdint>
#include <iostream>
#include <mutex>
#include <sstream>
#include <string>
#include <thread>

#include "rcutils/allocator.h"
#include "rmw/init.h"
#include "rmw/init_options.h"
#include "rmw/publisher_options.h"
#include "rmw/qos_profiles.h"
#include "rmw/rmw.h"
#include "rmw/serialized_message.h"
#include "rmw/subscription_options.h"
#include "rosidl_runtime_c/string_functions.h"
#include "rosidl_typesupport_interface/macros.h"
#include "std_msgs/msg/detail/string__functions.h"
#include "std_msgs/msg/detail/string__rosidl_typesupport_introspection_c.h"
#include "std_msgs/msg/detail/string__struct.h"

namespace
{

constexpr const char * kPublishTopic = "/fleetqox/quic_inprocess_publish_probe";
constexpr const char * kTakeTopic = "/fleetqox/quic_gateway_rmw_take_probe";
constexpr const char * kExpectedTakePayload = "fleetqox-quic-gateway-rmw-take-v1";
constexpr int kDefaultPublishCount = 4;

int publish_count_from_environment()
{
  const char * raw = std::getenv("FLEETQOX_RMW_QUIC_INPROCESS_RMW_PUBLISH_COUNT");
  if (raw == nullptr || raw[0] == '\0') {
    return kDefaultPublishCount;
  }
  char * end = nullptr;
  const long parsed = std::strtol(raw, &end, 10);
  if (end == raw || *end != '\0' || parsed <= 0 || parsed > 512) {
    return kDefaultPublishCount;
  }
  return static_cast<int>(parsed);
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
extern "C" std::uint64_t rmw_fleetqox_cpp_quic_gateway_packets_sent();
extern "C" std::uint64_t rmw_fleetqox_cpp_quic_gateway_packets_received();
extern "C" std::uint64_t rmw_fleetqox_cpp_quic_gateway_reconnects();
extern "C" std::uint64_t rmw_fleetqox_cpp_quic_gateway_concurrent_stream_pairs();
extern "C" std::uint64_t
rmw_fleetqox_cpp_quic_gateway_max_concurrent_request_streams();
extern "C" std::uint64_t
rmw_fleetqox_cpp_quic_gateway_concurrent_api_operation_pairs();
extern "C" std::uint64_t rmw_fleetqox_cpp_quic_gateway_max_concurrent_api_calls();

int main()
{
  const int publish_count = publish_count_from_environment();
  rcutils_allocator_t allocator = rcutils_get_default_allocator();
  rmw_init_options_t options = rmw_get_zero_initialized_init_options();
  if (rmw_init_options_init(&options, allocator) != RMW_RET_OK) {
    std::cout << "{\"status\":\"init_options_failed\"}\n";
    return 1;
  }
  options.instance_id = 173;
  rmw_context_t context = rmw_get_zero_initialized_context();
  if (rmw_init(&options, &context) != RMW_RET_OK) {
    const rmw_ret_t options_fini_ret = rmw_init_options_fini(&options);
    (void)options_fini_ret;
    std::cout << "{\"status\":\"init_failed\"}\n";
    return 1;
  }
  rmw_node_t * node = rmw_create_node(
    &context, "fleetqox_quic_inprocess_rmw_bidirectional_probe", "/fleetqox");
  if (node == nullptr) {
    cleanup_context(&context, &options);
    std::cout << "{\"status\":\"create_node_failed\"}\n";
    return 1;
  }

  const rosidl_message_type_support_t * string_type_support =
    ROSIDL_TYPESUPPORT_INTERFACE__MESSAGE_SYMBOL_NAME(
    rosidl_typesupport_introspection_c, std_msgs, msg, String)();
  rmw_qos_profile_t qos = rmw_qos_profile_default;
  rmw_publisher_options_t publisher_options = rmw_get_default_publisher_options();
  rmw_publisher_t * publisher = rmw_create_publisher(
    node, string_type_support, kPublishTopic, &qos, &publisher_options);
  rosidl_message_type_support_t take_type_support{};
  take_type_support.typesupport_identifier =
    "rmw_fleetqox_cpp_quic_inprocess_rmw_bidirectional_probe";
  rmw_subscription_options_t subscription_options = rmw_get_default_subscription_options();
  rmw_subscription_t * subscription = rmw_create_subscription(
    node, &take_type_support, kTakeTopic, &qos, &subscription_options);
  if (publisher == nullptr || subscription == nullptr) {
    if (publisher != nullptr) {
      const rmw_ret_t destroy_pub_ret = rmw_destroy_publisher(node, publisher);
      (void)destroy_pub_ret;
    }
    if (subscription != nullptr) {
      const rmw_ret_t destroy_sub_ret = rmw_destroy_subscription(node, subscription);
      (void)destroy_sub_ret;
    }
    const rmw_ret_t destroy_node_ret = rmw_destroy_node(node);
    (void)destroy_node_ret;
    cleanup_context(&context, &options);
    std::cout << "{\"status\":\"create_endpoint_failed\"}\n";
    return 1;
  }

  int publishes_ok = 0;
  for (int index = 0; index < publish_count - 1; ++index) {
    std_msgs__msg__String outgoing;
    if (!std_msgs__msg__String__init(&outgoing)) {
      break;
    }
    const std::string value = "fleetqox-rmw-inprocess-publish-" + std::to_string(index);
    const bool assigned = rosidl_runtime_c__String__assignn(
      &outgoing.data, value.data(), value.size());
    const rmw_ret_t publish_ret = assigned ?
      rmw_publish(publisher, &outgoing, nullptr) : RMW_RET_BAD_ALLOC;
    std_msgs__msg__String__fini(&outgoing);
    if (publish_ret != RMW_RET_OK) {
      break;
    }
    ++publishes_ok;
  }

  rmw_serialized_message_t incoming = rmw_get_zero_initialized_serialized_message();
  const bool incoming_initialized =
    rmw_serialized_message_init(&incoming, 1, &allocator) == RMW_RET_OK;
  bool taken = false;
  rmw_ret_t take_ret = RMW_RET_ERROR;
  rmw_ret_t final_publish_ret = RMW_RET_ERROR;
  if (incoming_initialized && publishes_ok == publish_count - 1) {
    std::mutex start_mutex;
    std::condition_variable start_cv;
    int ready_threads = 0;
    bool start = false;
    auto await_start = [&]() {
        std::unique_lock<std::mutex> lock(start_mutex);
        ++ready_threads;
        start_cv.notify_all();
        start_cv.wait(lock, [&]() {return start;});
      };
    std::thread publish_thread([&]() {
        await_start();
        std_msgs__msg__String outgoing;
        if (!std_msgs__msg__String__init(&outgoing)) {
          final_publish_ret = RMW_RET_BAD_ALLOC;
          return;
        }
        const std::string value =
          "fleetqox-rmw-inprocess-publish-" + std::to_string(publish_count - 1);
        const bool assigned = rosidl_runtime_c__String__assignn(
          &outgoing.data, value.data(), value.size());
        final_publish_ret = assigned ?
          rmw_publish(publisher, &outgoing, nullptr) : RMW_RET_BAD_ALLOC;
        std_msgs__msg__String__fini(&outgoing);
      });
    std::thread take_thread([&]() {
        await_start();
        take_ret = rmw_take_serialized_message(subscription, &incoming, &taken, nullptr);
      });
    {
      std::unique_lock<std::mutex> lock(start_mutex);
      start_cv.wait(lock, [&]() {return ready_threads == 2;});
      start = true;
    }
    start_cv.notify_all();
    publish_thread.join();
    take_thread.join();
    if (final_publish_ret == RMW_RET_OK) {
      ++publishes_ok;
    }
  }
  std::string taken_payload;
  if (taken && incoming.buffer != nullptr) {
    taken_payload.assign(
      reinterpret_cast<const char *>(incoming.buffer), incoming.buffer_length);
  }

  const std::uint64_t connections =
    rmw_fleetqox_cpp_quic_gateway_connections_created();
  const std::uint64_t handshakes =
    rmw_fleetqox_cpp_quic_gateway_handshakes_completed();
  const std::uint64_t streams = rmw_fleetqox_cpp_quic_gateway_streams_opened();
  const std::uint64_t reuse =
    rmw_fleetqox_cpp_quic_gateway_connection_reuse_count();
  const std::uint64_t concurrent_stream_pairs =
    rmw_fleetqox_cpp_quic_gateway_concurrent_stream_pairs();
  const std::uint64_t max_concurrent_streams =
    rmw_fleetqox_cpp_quic_gateway_max_concurrent_request_streams();
  const std::uint64_t concurrent_api_pairs =
    rmw_fleetqox_cpp_quic_gateway_concurrent_api_operation_pairs();
  const std::uint64_t max_concurrent_api_calls =
    rmw_fleetqox_cpp_quic_gateway_max_concurrent_api_calls();
  const bool same_connection_bidirectional =
    connections == 1 && handshakes == 1 &&
    streams == static_cast<std::uint64_t>(publish_count + 1) &&
    reuse == static_cast<std::uint64_t>(publish_count);
  const bool concurrent_rmw_operation_pair =
    concurrent_stream_pairs == 1 && max_concurrent_streams >= 2 &&
    concurrent_api_pairs == 1 && max_concurrent_api_calls >= 2;
  const bool ok =
    publishes_ok == publish_count && take_ret == RMW_RET_OK && taken &&
    taken_payload == kExpectedTakePayload &&
    std::string(rmw_fleetqox_cpp_quic_gateway_backend()) == "inprocess" &&
    !rmw_fleetqox_cpp_quic_gateway_subprocess_backed() &&
    rmw_fleetqox_cpp_quic_gateway_frames_sent() ==
    static_cast<std::uint64_t>(publish_count) &&
    rmw_fleetqox_cpp_quic_gateway_frames_received() == 1 &&
    rmw_fleetqox_cpp_quic_gateway_frames_failed() == 0 &&
    same_connection_bidirectional && concurrent_rmw_operation_pair &&
    rmw_fleetqox_cpp_quic_gateway_packets_sent() > 0 &&
    rmw_fleetqox_cpp_quic_gateway_packets_received() > 0 &&
    rmw_fleetqox_cpp_quic_gateway_reconnects() == 0;

  std::cout <<
    "{\"schema_version\":\"fleetrmw.quic_inprocess_rmw_bidirectional_probe.v1\",";
  std::cout << "\"status\":\"" << (ok ? "ok" : "failed") << "\",";
  std::cout << "\"transport_mode\":\"" <<
    json_escape(rmw_fleetqox_cpp_transport_mode()) << "\",";
  std::cout << "\"backend\":\"" <<
    json_escape(rmw_fleetqox_cpp_quic_gateway_backend()) << "\",";
  std::cout << "\"subprocess_backed\":" <<
    (rmw_fleetqox_cpp_quic_gateway_subprocess_backed() ? "true" : "false") << ",";
  std::cout << "\"publish_count\":" << publish_count << ",";
  std::cout << "\"publishes_ok\":" << publishes_ok << ",";
  std::cout << "\"taken\":" << (taken ? "true" : "false") << ",";
  std::cout << "\"take_payload_ok\":" <<
    (taken_payload == kExpectedTakePayload ? "true" : "false") << ",";
  std::cout << "\"frames_sent\":" <<
    rmw_fleetqox_cpp_quic_gateway_frames_sent() << ",";
  std::cout << "\"frames_received\":" <<
    rmw_fleetqox_cpp_quic_gateway_frames_received() << ",";
  std::cout << "\"connections_created\":" << connections << ",";
  std::cout << "\"handshakes_completed\":" << handshakes << ",";
  std::cout << "\"streams_opened\":" << streams << ",";
  std::cout << "\"connection_reuse_count\":" << reuse << ",";
  std::cout << "\"concurrent_stream_pairs\":" << concurrent_stream_pairs << ",";
  std::cout << "\"max_concurrent_request_streams\":" << max_concurrent_streams << ",";
  std::cout << "\"concurrent_api_operation_pairs\":" << concurrent_api_pairs << ",";
  std::cout << "\"max_concurrent_api_calls\":" << max_concurrent_api_calls << ",";
  std::cout << "\"packets_sent\":" <<
    rmw_fleetqox_cpp_quic_gateway_packets_sent() << ",";
  std::cout << "\"packets_received\":" <<
    rmw_fleetqox_cpp_quic_gateway_packets_received() << ",";
  std::cout << "\"reconnects\":" << rmw_fleetqox_cpp_quic_gateway_reconnects() << ",";
  std::cout << "\"same_connection_bidirectional\":" <<
    (same_connection_bidirectional ? "true" : "false") << ",";
  std::cout << "\"concurrent_rmw_publish_take_operation_loop\":" <<
    (concurrent_rmw_operation_pair ? "true" : "false") << ",";
  std::cout << "\"rmw_publish_path_integrated\":true,";
  std::cout << "\"rmw_take_path_integrated\":true,";
  std::cout << "\"tls_peer_verification_required\":true,";
  std::cout << "\"application_protocol\":\"h3\",";
  std::cout << "\"serialized_operation_loop\":false,";
  std::cout << "\"multi_threaded_rmw_api_claim\":" <<
    (concurrent_rmw_operation_pair ? "true" : "false") << ",";
  std::cout << "\"production_readiness\":false}\n";

  if (incoming_initialized) {
    (void)rmw_serialized_message_fini(&incoming);
  }
  const rmw_ret_t destroy_sub_ret = rmw_destroy_subscription(node, subscription);
  const rmw_ret_t destroy_pub_ret = rmw_destroy_publisher(node, publisher);
  const rmw_ret_t destroy_node_ret = rmw_destroy_node(node);
  cleanup_context(&context, &options);
  return ok && destroy_sub_ret == RMW_RET_OK && destroy_pub_ret == RMW_RET_OK &&
         destroy_node_ret == RMW_RET_OK ? 0 : 1;
}

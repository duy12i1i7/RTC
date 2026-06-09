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
#include "rmw/publisher_options.h"
#include "rmw/qos_profiles.h"
#include "rmw/rmw.h"
#include "rmw/subscription_options.h"
#include "rosidl_runtime_c/message_type_support_struct.h"

extern "C" std::uint64_t rmw_fleetqox_cpp_socket_frames_sent();
extern "C" std::uint64_t rmw_fleetqox_cpp_socket_frames_received();

namespace
{

struct FleetQoxTypeErasedMessageDescriptor
{
  std::uint32_t schema_version;
  size_t message_size;
};

struct TypedProbeMessage
{
  std::uint32_t sequence;
  double linear_x;
  double angular_z;
  char label[16];
};

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
  options->instance_id = 46;
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

  rmw_node_t * node = rmw_create_node(&context, "fleetqox_typed_pubsub_probe", "/fleetqox");
  if (node == nullptr) {
    cleanup_context(&context, &options);
    std::cout << "{\"status\":\"create_node_failed\"}" << std::endl;
    return 1;
  }

  const FleetQoxTypeErasedMessageDescriptor descriptor{1, sizeof(TypedProbeMessage)};
  rosidl_message_type_support_t type_support{};
  type_support.typesupport_identifier = "rmw_fleetqox_cpp_type_erased_probe";
  type_support.data = &descriptor;
  rmw_publisher_options_t publisher_options = rmw_get_default_publisher_options();
  rmw_subscription_options_t subscription_options = rmw_get_default_subscription_options();
  rmw_qos_profile_t qos = rmw_qos_profile_default;
  const char * topic = "/fleetqox/typed_probe";

  rmw_publisher_t * publisher =
    rmw_create_publisher(node, &type_support, topic, &qos, &publisher_options);
  rmw_subscription_t * subscription =
    rmw_create_subscription(node, &type_support, topic, &qos, &subscription_options);
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
    std::cout << "{\"status\":\"create_pubsub_failed\"}" << std::endl;
    return 1;
  }

  TypedProbeMessage outgoing{};
  outgoing.sequence = 7;
  outgoing.linear_x = 0.42;
  outgoing.angular_z = -0.13;
  std::strncpy(outgoing.label, "typed-probe", sizeof(outgoing.label) - 1);
  TypedProbeMessage incoming{};

  const std::uint64_t socket_sent_before = rmw_fleetqox_cpp_socket_frames_sent();
  const std::uint64_t socket_received_before = rmw_fleetqox_cpp_socket_frames_received();
  rmw_ret_t ret = rmw_publish(publisher, &outgoing, nullptr);
  bool taken = false;
  if (ret == RMW_RET_OK) {
    for (int attempt = 0; attempt < 100 && !taken; ++attempt) {
      ret = rmw_take(subscription, &incoming, &taken, nullptr);
      if (ret != RMW_RET_OK || taken) {
        break;
      }
      std::this_thread::sleep_for(std::chrono::milliseconds(1));
    }
  }
  const std::uint64_t socket_frames_sent =
    rmw_fleetqox_cpp_socket_frames_sent() - socket_sent_before;
  const std::uint64_t socket_frames_received =
    rmw_fleetqox_cpp_socket_frames_received() - socket_received_before;

  const bool payload_ok = taken &&
                          incoming.sequence == outgoing.sequence &&
                          incoming.linear_x == outgoing.linear_x &&
                          incoming.angular_z == outgoing.angular_z &&
                          std::string(incoming.label) == outgoing.label;
  const bool ok = ret == RMW_RET_OK &&
                  payload_ok &&
                  socket_frames_sent >= 1 &&
                  socket_frames_received >= 1;

  std::cout << "{\"schema_version\":\"fleetrmw.rmw_typed_pubsub_probe.v1\",";
  std::cout << "\"status\":\"" << (ok ? "ok" : "failed") << "\",";
  std::cout << "\"topic\":\"" << topic << "\",";
  std::cout << "\"typed_message_size\":" << sizeof(TypedProbeMessage) << ",";
  std::cout << "\"data_frame_wrapped\":true,";
  std::cout << "\"socket_backed\":true,";
  std::cout << "\"socket_frames_sent\":" << socket_frames_sent << ",";
  std::cout << "\"socket_frames_received\":" << socket_frames_received << ",";
  std::cout << "\"taken\":" << (taken ? "true" : "false") << ",";
  std::cout << "\"sequence\":" << incoming.sequence << ",";
  std::cout << "\"linear_x\":" << incoming.linear_x << ",";
  std::cout << "\"angular_z\":" << incoming.angular_z << ",";
  std::cout << "\"label\":\"" << json_escape(incoming.label) << "\"}" << std::endl;

  const rmw_ret_t destroy_pub_ret = rmw_destroy_publisher(node, publisher);
  const rmw_ret_t destroy_sub_ret = rmw_destroy_subscription(node, subscription);
  const rmw_ret_t destroy_node_ret = rmw_destroy_node(node);
  cleanup_context(&context, &options);
  return ok &&
         destroy_pub_ret == RMW_RET_OK &&
         destroy_sub_ret == RMW_RET_OK &&
         destroy_node_ret == RMW_RET_OK ? 0 : 1;
}

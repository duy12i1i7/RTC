#include <chrono>
#include <cstdint>
#include <iostream>
#include <thread>

#include "geometry_msgs/msg/detail/twist__functions.h"
#include "geometry_msgs/msg/detail/twist__rosidl_typesupport_introspection_c.h"
#include "geometry_msgs/msg/detail/twist__struct.h"
#include "rcutils/allocator.h"
#include "rmw/init.h"
#include "rmw/init_options.h"
#include "rmw/publisher_options.h"
#include "rmw/qos_profiles.h"
#include "rmw/rmw.h"
#include "rmw/subscription_options.h"
#include "rosidl_typesupport_interface/macros.h"

extern "C" std::uint64_t rmw_fleetqox_cpp_socket_frames_sent();
extern "C" std::uint64_t rmw_fleetqox_cpp_socket_frames_received();

namespace
{

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
  options->instance_id = 48;
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

  rmw_node_t * node = rmw_create_node(&context, "fleetqox_geometry_twist_probe", "/fleetqox");
  if (node == nullptr) {
    cleanup_context(&context, &options);
    std::cout << "{\"status\":\"create_node_failed\"}" << std::endl;
    return 1;
  }

  const rosidl_message_type_support_t * type_support =
    ROSIDL_TYPESUPPORT_INTERFACE__MESSAGE_SYMBOL_NAME(
    rosidl_typesupport_introspection_c, geometry_msgs, msg, Twist)();
  rmw_publisher_options_t publisher_options = rmw_get_default_publisher_options();
  rmw_subscription_options_t subscription_options = rmw_get_default_subscription_options();
  rmw_qos_profile_t qos = rmw_qos_profile_default;
  const char * topic = "/fleetqox/cmd_vel_probe";

  rmw_publisher_t * publisher =
    rmw_create_publisher(node, type_support, topic, &qos, &publisher_options);
  rmw_subscription_t * subscription =
    rmw_create_subscription(node, type_support, topic, &qos, &subscription_options);
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

  geometry_msgs__msg__Twist outgoing;
  geometry_msgs__msg__Twist incoming;
  if (!geometry_msgs__msg__Twist__init(&outgoing) ||
    !geometry_msgs__msg__Twist__init(&incoming))
  {
    std::cout << "{\"status\":\"message_init_failed\"}" << std::endl;
    return 1;
  }
  outgoing.linear.x = 0.7;
  outgoing.linear.y = -0.2;
  outgoing.linear.z = 0.0;
  outgoing.angular.x = 0.01;
  outgoing.angular.y = -0.02;
  outgoing.angular.z = 0.33;

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
                          incoming.linear.x == outgoing.linear.x &&
                          incoming.linear.y == outgoing.linear.y &&
                          incoming.angular.z == outgoing.angular.z;
  const bool ok = ret == RMW_RET_OK &&
                  payload_ok &&
                  socket_frames_sent >= 1 &&
                  socket_frames_received >= 1;

  std::cout << "{\"schema_version\":\"fleetrmw.rmw_geometry_twist_probe.v1\",";
  std::cout << "\"status\":\"" << (ok ? "ok" : "failed") << "\",";
  std::cout << "\"topic\":\"" << topic << "\",";
  std::cout << "\"data_frame_wrapped\":true,";
  std::cout << "\"socket_backed\":true,";
  std::cout << "\"socket_frames_sent\":" << socket_frames_sent << ",";
  std::cout << "\"socket_frames_received\":" << socket_frames_received << ",";
  std::cout << "\"taken\":" << (taken ? "true" : "false") << ",";
  std::cout << "\"linear_x\":" << incoming.linear.x << ",";
  std::cout << "\"linear_y\":" << incoming.linear.y << ",";
  std::cout << "\"angular_z\":" << incoming.angular.z << "}" << std::endl;

  geometry_msgs__msg__Twist__fini(&outgoing);
  geometry_msgs__msg__Twist__fini(&incoming);
  const rmw_ret_t destroy_pub_ret = rmw_destroy_publisher(node, publisher);
  const rmw_ret_t destroy_sub_ret = rmw_destroy_subscription(node, subscription);
  const rmw_ret_t destroy_node_ret = rmw_destroy_node(node);
  cleanup_context(&context, &options);
  return ok &&
         destroy_pub_ret == RMW_RET_OK &&
         destroy_sub_ret == RMW_RET_OK &&
         destroy_node_ret == RMW_RET_OK ? 0 : 1;
}

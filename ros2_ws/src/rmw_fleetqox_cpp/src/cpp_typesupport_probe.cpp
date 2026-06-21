#include <cmath>
#include <iostream>
#include <string>

#include "geometry_msgs/msg/detail/pose_stamped__type_support.hpp"
#include "geometry_msgs/msg/detail/pose__functions.h"
#include "geometry_msgs/msg/detail/pose__struct.h"
#include "geometry_msgs/msg/detail/pose__type_support.h"
#include "geometry_msgs/msg/detail/pose__type_support.hpp"
#include "geometry_msgs/msg/pose.hpp"
#include "geometry_msgs/msg/pose_stamped.hpp"
#include "rcutils/allocator.h"
#include "rmw/error_handling.h"
#include "rmw/rmw.h"
#include "rmw/serialized_message.h"
#include "rosidl_runtime_c/message_type_support_struct.h"
#include "rosidl_typesupport_interface/macros.h"
#include "std_msgs/msg/detail/string__type_support.hpp"
#include "std_msgs/msg/string.hpp"

namespace
{

template<typename MessageT>
bool round_trip(
  const MessageT & outgoing,
  MessageT * incoming,
  const rosidl_message_type_support_t * type_support,
  size_t * serialized_size)
{
  if (incoming == nullptr || type_support == nullptr || serialized_size == nullptr) {
    return false;
  }
  rcutils_allocator_t allocator = rcutils_get_default_allocator();
  rmw_serialized_message_t serialized = rmw_get_zero_initialized_serialized_message();
  if (rmw_serialized_message_init(&serialized, 0, &allocator) != RMW_RET_OK) {
    return false;
  }
  const bool ok =
    rmw_serialize(&outgoing, type_support, &serialized) == RMW_RET_OK &&
    rmw_deserialize(&serialized, type_support, incoming) == RMW_RET_OK;
  *serialized_size = serialized.buffer_length;
  const bool fini_ok = rmw_serialized_message_fini(&serialized) == RMW_RET_OK;
  return ok && fini_ok;
}

}  // namespace

int main()
{
  std_msgs::msg::String string_out;
  string_out.data = "fleetqox-cpp-typesupport";
  std_msgs::msg::String string_in;
  size_t string_size = 0;
  const auto * string_type_support =
    ROSIDL_TYPESUPPORT_INTERFACE__MESSAGE_SYMBOL_NAME(
    rosidl_typesupport_cpp, std_msgs, msg, String)();
  const bool string_ok = round_trip(
    string_out, &string_in, string_type_support, &string_size) &&
    string_in.data == string_out.data;

  geometry_msgs::msg::PoseStamped pose_out;
  pose_out.header.stamp.sec = -7;
  pose_out.header.stamp.nanosec = 123456789u;
  pose_out.header.frame_id = "fleet/map";
  pose_out.pose.position.x = 1.25;
  pose_out.pose.position.y = -2.5;
  pose_out.pose.position.z = 0.75;
  pose_out.pose.orientation.x = 0.1;
  pose_out.pose.orientation.y = 0.2;
  pose_out.pose.orientation.z = 0.3;
  pose_out.pose.orientation.w = 0.9;
  geometry_msgs::msg::PoseStamped pose_in;
  size_t pose_size = 0;
  const auto * pose_type_support =
    ROSIDL_TYPESUPPORT_INTERFACE__MESSAGE_SYMBOL_NAME(
    rosidl_typesupport_cpp, geometry_msgs, msg, PoseStamped)();
  const bool pose_ok = round_trip(
    pose_out, &pose_in, pose_type_support, &pose_size) &&
    pose_in.header.stamp.sec == pose_out.header.stamp.sec &&
    pose_in.header.stamp.nanosec == pose_out.header.stamp.nanosec &&
    pose_in.header.frame_id == pose_out.header.frame_id &&
    std::abs(pose_in.pose.position.x - pose_out.pose.position.x) < 1e-12 &&
    std::abs(pose_in.pose.position.y - pose_out.pose.position.y) < 1e-12 &&
    std::abs(pose_in.pose.position.z - pose_out.pose.position.z) < 1e-12 &&
    std::abs(pose_in.pose.orientation.w - pose_out.pose.orientation.w) < 1e-12;

  geometry_msgs::msg::Pose bounded_pose_in;
  size_t bounded_pose_serialized_size = 0;
  size_t bounded_pose_max_size = 0;
  const auto * bounded_pose_type_support =
    ROSIDL_TYPESUPPORT_INTERFACE__MESSAGE_SYMBOL_NAME(
    rosidl_typesupport_cpp, geometry_msgs, msg, Pose)();
  const rmw_ret_t bounded_pose_size_ret = rmw_get_serialized_message_size(
    bounded_pose_type_support, nullptr, &bounded_pose_max_size);
  const bool bounded_pose_size_ok =
    bounded_pose_size_ret == RMW_RET_OK &&
    round_trip(
      pose_out.pose,
      &bounded_pose_in,
      bounded_pose_type_support,
      &bounded_pose_serialized_size) &&
    bounded_pose_max_size == bounded_pose_serialized_size &&
    bounded_pose_max_size == 80;

  geometry_msgs__msg__Pose bounded_c_pose_out{};
  geometry_msgs__msg__Pose bounded_c_pose_in{};
  const bool bounded_c_messages_initialized =
    geometry_msgs__msg__Pose__init(&bounded_c_pose_out) &&
    geometry_msgs__msg__Pose__init(&bounded_c_pose_in);
  bounded_c_pose_out.position.x = 1.25;
  bounded_c_pose_out.orientation.w = 0.9;
  size_t bounded_c_pose_serialized_size = 0;
  size_t bounded_c_pose_max_size = 0;
  const auto * bounded_c_pose_type_support =
    ROSIDL_TYPESUPPORT_INTERFACE__MESSAGE_SYMBOL_NAME(
    rosidl_typesupport_c, geometry_msgs, msg, Pose)();
  const rmw_ret_t bounded_c_pose_size_ret = rmw_get_serialized_message_size(
    bounded_c_pose_type_support, nullptr, &bounded_c_pose_max_size);
  const bool bounded_c_pose_size_ok =
    bounded_c_messages_initialized &&
    bounded_c_pose_size_ret == RMW_RET_OK &&
    round_trip(
      bounded_c_pose_out,
      &bounded_c_pose_in,
      bounded_c_pose_type_support,
      &bounded_c_pose_serialized_size) &&
    bounded_c_pose_max_size == bounded_c_pose_serialized_size &&
    bounded_c_pose_max_size == 80;
  geometry_msgs__msg__Pose__fini(&bounded_c_pose_out);
  geometry_msgs__msg__Pose__fini(&bounded_c_pose_in);

  size_t unbounded_string_max_size = 0;
  const rmw_ret_t unbounded_string_size_ret = rmw_get_serialized_message_size(
    string_type_support, nullptr, &unbounded_string_max_size);
  const bool unbounded_string_size_scoped = unbounded_string_size_ret == RMW_RET_UNSUPPORTED;
  if (unbounded_string_size_ret != RMW_RET_OK) {
    rmw_reset_error();
  }

  const bool ok = string_ok && pose_ok && bounded_pose_size_ok && bounded_c_pose_size_ok &&
    unbounded_string_size_scoped && string_size > 0 && pose_size > string_size;
  std::cout << "{\"schema_version\":\"fleetrmw.cpp_typesupport_probe.v1\","
            << "\"status\":\"" << (ok ? "ok" : "failed") << "\","
            << "\"string_roundtrip\":" << (string_ok ? "true" : "false") << ","
            << "\"pose_stamped_roundtrip\":" << (pose_ok ? "true" : "false") << ","
            << "\"bounded_pose_size_ok\":" << (bounded_pose_size_ok ? "true" : "false") << ","
            << "\"bounded_pose_max_bytes\":" << bounded_pose_max_size << ","
            << "\"bounded_pose_serialized_bytes\":" << bounded_pose_serialized_size << ","
            << "\"bounded_c_pose_size_ok\":"
            << (bounded_c_pose_size_ok ? "true" : "false") << ","
            << "\"bounded_c_pose_max_bytes\":" << bounded_c_pose_max_size << ","
            << "\"bounded_c_pose_serialized_bytes\":" << bounded_c_pose_serialized_size << ","
            << "\"unbounded_string_size_scoped\":"
            << (unbounded_string_size_scoped ? "true" : "false") << ","
            << "\"string_serialized_bytes\":" << string_size << ","
            << "\"pose_stamped_serialized_bytes\":" << pose_size << "}\n";
  return ok ? 0 : 1;
}

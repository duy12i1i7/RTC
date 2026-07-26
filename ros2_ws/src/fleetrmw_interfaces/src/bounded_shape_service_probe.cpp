#include <chrono>
#include <cmath>
#include <cstddef>
#include <cstdint>
#include <future>
#include <iostream>
#include <memory>
#include <string>
#include <utility>

#include "fleetrmw_interfaces/srv/fleet_shape.hpp"
#include "rclcpp/rclcpp.hpp"

using namespace std::chrono_literals;

namespace
{

constexpr std::size_t kTokenSize = 16;
constexpr std::size_t kRangeCount = 128;
constexpr std::size_t kWaypointCount = 16;
constexpr std::size_t kAdmittedIndexCount = 64;

fleetrmw_interfaces::srv::FleetShape::Request make_request()
{
  fleetrmw_interfaces::srv::FleetShape::Request request;
  request.robot_id = "robot_0042";
  for (std::size_t index = 0; index < request.session_token.size(); ++index) {
    request.session_token[index] = static_cast<std::uint8_t>(index * 7u);
  }
  request.ranges.reserve(kRangeCount);
  for (std::size_t index = 0; index < kRangeCount; ++index) {
    request.ranges.push_back(static_cast<float>(index) * 0.25f);
  }
  request.waypoints.reserve(kWaypointCount);
  for (std::size_t index = 0; index < kWaypointCount; ++index) {
    geometry_msgs::msg::PoseStamped pose;
    pose.header.stamp.sec = static_cast<std::int32_t>(index) - 8;
    pose.header.stamp.nanosec = static_cast<std::uint32_t>(index * 1000000u);
    pose.header.frame_id = "fleet/bounded/" + std::to_string(index);
    pose.pose.position.x = static_cast<double>(index) * 1.5;
    pose.pose.position.y = -static_cast<double>(index) * 0.75;
    pose.pose.orientation.z = static_cast<double>(index) / 20.0;
    pose.pose.orientation.w = 1.0;
    request.waypoints.push_back(std::move(pose));
  }
  request.budget.sec = -2;
  request.budget.nanosec = 500000000u;
  return request;
}

bool valid_request(const fleetrmw_interfaces::srv::FleetShape::Request & request)
{
  if (request.robot_id != "robot_0042" ||
    request.session_token.size() != kTokenSize ||
    request.ranges.size() != kRangeCount ||
    request.waypoints.size() != kWaypointCount ||
    request.budget.sec != -2 ||
    request.budget.nanosec != 500000000u)
  {
    return false;
  }
  for (std::size_t index = 0; index < request.session_token.size(); ++index) {
    if (request.session_token[index] != static_cast<std::uint8_t>(index * 7u)) {
      return false;
    }
  }
  for (std::size_t index = 0; index < request.ranges.size(); ++index) {
    if (std::abs(request.ranges[index] - static_cast<float>(index) * 0.25f) > 1e-6f) {
      return false;
    }
  }
  for (std::size_t index = 0; index < request.waypoints.size(); ++index) {
    const auto & pose = request.waypoints[index];
    if (pose.header.stamp.sec != static_cast<std::int32_t>(index) - 8 ||
      pose.header.stamp.nanosec != static_cast<std::uint32_t>(index * 1000000u) ||
      pose.header.frame_id != "fleet/bounded/" + std::to_string(index) ||
      std::abs(pose.pose.position.x - static_cast<double>(index) * 1.5) > 1e-12 ||
      std::abs(pose.pose.position.y + static_cast<double>(index) * 0.75) > 1e-12 ||
      std::abs(pose.pose.orientation.z - static_cast<double>(index) / 20.0) > 1e-12)
    {
      return false;
    }
  }
  return true;
}

void populate_response(
  const fleetrmw_interfaces::srv::FleetShape::Request & request,
  fleetrmw_interfaces::srv::FleetShape::Response * response)
{
  response->accepted = true;
  response->reason = "bounded-shape-cpp-python-ok";
  response->admitted_indices.reserve(kAdmittedIndexCount);
  for (std::size_t index = 0; index < kAdmittedIndexCount; ++index) {
    response->admitted_indices.push_back(static_cast<std::uint32_t>(index * 2u));
  }
  response->repaired_waypoints = request.waypoints;
  for (auto & pose : response->repaired_waypoints) {
    pose.header.frame_id += "/repaired";
    pose.pose.position.x += 100.0;
  }
}

bool valid_response(const fleetrmw_interfaces::srv::FleetShape::Response & response)
{
  if (!response.accepted ||
    response.reason != "bounded-shape-cpp-python-ok" ||
    response.admitted_indices.size() != kAdmittedIndexCount ||
    response.repaired_waypoints.size() != kWaypointCount)
  {
    return false;
  }
  for (std::size_t index = 0; index < response.admitted_indices.size(); ++index) {
    if (response.admitted_indices[index] != static_cast<std::uint32_t>(index * 2u)) {
      return false;
    }
  }
  for (std::size_t index = 0; index < response.repaired_waypoints.size(); ++index) {
    const auto & pose = response.repaired_waypoints[index];
    if (pose.header.frame_id !=
      "fleet/bounded/" + std::to_string(index) + "/repaired" ||
      std::abs(pose.pose.position.x -
      (static_cast<double>(index) * 1.5 + 100.0)) > 1e-12 ||
      std::abs(pose.pose.position.y + static_cast<double>(index) * 0.75) > 1e-12)
    {
      return false;
    }
  }
  return true;
}

int run_server()
{
  auto node = std::make_shared<rclcpp::Node>("fleetrmw_bounded_shape_cpp_server");
  bool request_received = false;
  bool request_valid = false;
  auto service = node->create_service<fleetrmw_interfaces::srv::FleetShape>(
    "/fleetqox/bounded_shape",
    [&](const std::shared_ptr<fleetrmw_interfaces::srv::FleetShape::Request> request,
      std::shared_ptr<fleetrmw_interfaces::srv::FleetShape::Response> response)
    {
      request_received = true;
      request_valid = valid_request(*request);
      if (request_valid) {
        populate_response(*request, response.get());
      }
    });
  rclcpp::executors::SingleThreadedExecutor executor;
  executor.add_node(node);
  const auto deadline = std::chrono::steady_clock::now() + 15s;
  while (rclcpp::ok() && !request_received && std::chrono::steady_clock::now() < deadline) {
    executor.spin_once(50ms);
  }
  const bool ok = request_received && request_valid;
  std::cout << "{\"schema_version\":\"fleetrmw.bounded_shape_cpp_server.v1\","
            << "\"status\":\"" << (ok ? "ok" : "failed") << "\","
            << "\"request_received\":" << (request_received ? "true" : "false") << ","
            << "\"request_valid\":" << (request_valid ? "true" : "false") << ","
            << "\"token_size\":" << kTokenSize << ","
            << "\"range_count\":" << kRangeCount << ","
            << "\"waypoint_count\":" << kWaypointCount << "}\n";
  executor.remove_node(node);
  service.reset();
  node.reset();
  return ok ? 0 : 1;
}

int run_client()
{
  auto node = std::make_shared<rclcpp::Node>("fleetrmw_bounded_shape_cpp_client");
  auto client = node->create_client<fleetrmw_interfaces::srv::FleetShape>(
    "/fleetqox/bounded_shape");
  rclcpp::executors::SingleThreadedExecutor executor;
  executor.add_node(node);
  const auto service_deadline = std::chrono::steady_clock::now() + 8s;
  while (rclcpp::ok() && !client->service_is_ready() &&
    std::chrono::steady_clock::now() < service_deadline)
  {
    executor.spin_once(50ms);
  }
  const bool service_available = client->service_is_ready();
  std::shared_future<
    std::shared_ptr<fleetrmw_interfaces::srv::FleetShape::Response>> future;
  if (service_available) {
    auto request =
      std::make_shared<fleetrmw_interfaces::srv::FleetShape::Request>(make_request());
    future = client->async_send_request(request).future.share();
  }
  bool response_valid = false;
  const auto deadline = std::chrono::steady_clock::now() + 12s;
  while (rclcpp::ok() && !response_valid && std::chrono::steady_clock::now() < deadline) {
    executor.spin_once(50ms);
    if (future.valid() && future.wait_for(0s) == std::future_status::ready) {
      const auto response = future.get();
      response_valid = response != nullptr && valid_response(*response);
    }
  }
  const bool ok = service_available && response_valid;
  std::cout << "{\"schema_version\":\"fleetrmw.bounded_shape_cpp_client.v1\","
            << "\"status\":\"" << (ok ? "ok" : "failed") << "\","
            << "\"service_available\":" << (service_available ? "true" : "false") << ","
            << "\"response_valid\":" << (response_valid ? "true" : "false") << ","
            << "\"admitted_index_count\":" << kAdmittedIndexCount << ","
            << "\"repaired_waypoint_count\":" << kWaypointCount << "}\n";
  executor.remove_node(node);
  client.reset();
  node.reset();
  return ok ? 0 : 1;
}

}  // namespace

int main(int argc, char ** argv)
{
  const std::string mode = argc > 1 ? argv[1] : "";
  int ros_argc = 1;
  rclcpp::init(ros_argc, argv);
  const int result = mode == "server" ? run_server() : mode == "client" ? run_client() : 2;
  rclcpp::shutdown();
  return result;
}

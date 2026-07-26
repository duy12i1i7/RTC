#include <atomic>
#include <chrono>
#include <cmath>
#include <cstddef>
#include <cstdint>
#include <future>
#include <iostream>
#include <memory>
#include <string>
#include <thread>
#include <utility>

#include "geometry_msgs/msg/pose_stamped.hpp"
#include "nav_msgs/msg/path.hpp"
#include "nav_msgs/srv/get_plan.hpp"
#include "rcl/client.h"
#include "rcl/publisher.h"
#include "rcl/service.h"
#include "rcl/subscription.h"
#include "rclcpp/rclcpp.hpp"
#include "rcutils/allocator.h"
#include "rmw/get_network_flow_endpoints.h"
#include "std_srvs/srv/set_bool.hpp"

using namespace std::chrono_literals;

namespace
{

void count_new_data_callback(const void * user_data, size_t number_of_events)
{
  if (user_data == nullptr) {
    return;
  }
  auto * count = static_cast<std::atomic<size_t> *>(const_cast<void *>(user_data));
  count->fetch_add(number_of_events, std::memory_order_relaxed);
}

bool valid_udp_flow(
  const rmw_network_flow_endpoint_array_t & endpoints,
  std::uint16_t expected_port)
{
  return endpoints.size == 1 && endpoints.network_flow_endpoint != nullptr &&
         endpoints.network_flow_endpoint[0].transport_protocol == RMW_TRANSPORT_PROTOCOL_UDP &&
         endpoints.network_flow_endpoint[0].internet_protocol == RMW_INTERNET_PROTOCOL_IPV4 &&
         endpoints.network_flow_endpoint[0].transport_port == expected_port &&
         std::string(endpoints.network_flow_endpoint[0].internet_address) == "0.0.0.0";
}

bool publisher_flow_ok(
  const rclcpp::PublisherBase::SharedPtr & publisher,
  std::uint16_t expected_port)
{
  rcutils_allocator_t allocator = rcutils_get_default_allocator();
  rmw_network_flow_endpoint_array_t endpoints =
    rmw_get_zero_initialized_network_flow_endpoint_array();
  const rmw_publisher_t * handle = rcl_publisher_get_rmw_handle(
    publisher->get_publisher_handle().get());
  const bool ok = handle != nullptr &&
    rmw_publisher_get_network_flow_endpoints(handle, &allocator, &endpoints) == RMW_RET_OK &&
    valid_udp_flow(endpoints, expected_port);
  if (endpoints.allocator != nullptr) {
    rmw_network_flow_endpoint_array_fini(&endpoints);
  }
  return ok;
}

bool subscription_flow_ok(
  const rclcpp::SubscriptionBase::SharedPtr & subscription,
  std::uint16_t expected_port)
{
  rcutils_allocator_t allocator = rcutils_get_default_allocator();
  rmw_network_flow_endpoint_array_t endpoints =
    rmw_get_zero_initialized_network_flow_endpoint_array();
  const rmw_subscription_t * handle = rcl_subscription_get_rmw_handle(
    subscription->get_subscription_handle().get());
  const bool ok = handle != nullptr &&
    rmw_subscription_get_network_flow_endpoints(handle, &allocator, &endpoints) == RMW_RET_OK &&
    valid_udp_flow(endpoints, expected_port);
  if (endpoints.allocator != nullptr) {
    rmw_network_flow_endpoint_array_fini(&endpoints);
  }
  return ok;
}

constexpr std::size_t kPathPoseCount = 64;
constexpr std::size_t kPlanPoseCount = 512;

nav_msgs::msg::Path make_path_request()
{
  nav_msgs::msg::Path path;
  path.header.stamp.sec = -11;
  path.header.stamp.nanosec = 987654321u;
  path.header.frame_id = "fleet/path";
  path.poses.reserve(kPathPoseCount);
  for (std::size_t index = 0; index < kPathPoseCount; ++index) {
    geometry_msgs::msg::PoseStamped pose;
    pose.header.stamp.sec = static_cast<std::int32_t>(index) - 32;
    pose.header.stamp.nanosec = static_cast<std::uint32_t>(index * 1000000u);
    pose.header.frame_id = "fleet/path/" + std::to_string(index);
    pose.pose.position.x = static_cast<double>(index) * 0.25;
    pose.pose.position.y = -static_cast<double>(index) * 0.5;
    pose.pose.position.z = static_cast<double>(index % 3);
    pose.pose.orientation.z = static_cast<double>(index) / 100.0;
    pose.pose.orientation.w = 1.0;
    path.poses.push_back(std::move(pose));
  }
  return path;
}

bool valid_path_request(const nav_msgs::msg::Path & path)
{
  if (path.header.stamp.sec != -11 ||
    path.header.stamp.nanosec != 987654321u ||
    path.header.frame_id != "fleet/path" ||
    path.poses.size() != kPathPoseCount)
  {
    return false;
  }
  for (std::size_t index = 0; index < path.poses.size(); ++index) {
    const auto & pose = path.poses[index];
    if (pose.header.stamp.sec != static_cast<std::int32_t>(index) - 32 ||
      pose.header.stamp.nanosec != static_cast<std::uint32_t>(index * 1000000u) ||
      pose.header.frame_id != "fleet/path/" + std::to_string(index) ||
      std::abs(pose.pose.position.x - static_cast<double>(index) * 0.25) > 1e-12 ||
      std::abs(pose.pose.position.y + static_cast<double>(index) * 0.5) > 1e-12 ||
      std::abs(pose.pose.position.z - static_cast<double>(index % 3)) > 1e-12 ||
      std::abs(pose.pose.orientation.z - static_cast<double>(index) / 100.0) > 1e-12 ||
      std::abs(pose.pose.orientation.w - 1.0) > 1e-12)
    {
      return false;
    }
  }
  return true;
}

bool valid_path_reply(const nav_msgs::msg::Path & path)
{
  if (path.header.frame_id != "fleet/path/ack" ||
    path.header.stamp.sec != -11 ||
    path.header.stamp.nanosec != 987654321u ||
    path.poses.size() != kPathPoseCount)
  {
    return false;
  }
  for (std::size_t index = 0; index < path.poses.size(); ++index) {
    const auto & pose = path.poses[index];
    if (pose.header.frame_id != "fleet/path/" + std::to_string(index) + "/ack" ||
      pose.header.stamp.sec != static_cast<std::int32_t>(index) - 32 ||
      pose.header.stamp.nanosec != static_cast<std::uint32_t>(index * 1000000u) ||
      std::abs(pose.pose.position.x - (static_cast<double>(index) * 0.25 + 100.0)) > 1e-12 ||
      std::abs(pose.pose.position.y + static_cast<double>(index) * 0.5) > 1e-12 ||
      std::abs(pose.pose.orientation.z - static_cast<double>(index) / 100.0) > 1e-12)
    {
      return false;
    }
  }
  return true;
}

nav_msgs::srv::GetPlan::Request make_plan_request()
{
  nav_msgs::srv::GetPlan::Request request;
  request.start.header.stamp.sec = -9;
  request.start.header.stamp.nanosec = 111222333u;
  request.start.header.frame_id = "fleet/plan_map";
  request.start.pose.position.x = -2.0;
  request.start.pose.position.y = 1.5;
  request.start.pose.orientation.w = 1.0;
  request.goal.header.stamp.sec = 19;
  request.goal.header.stamp.nanosec = 444555666u;
  request.goal.header.frame_id = "fleet/plan_map";
  request.goal.pose.position.x = 8.0;
  request.goal.pose.position.y = -3.5;
  request.goal.pose.orientation.w = 1.0;
  request.tolerance = 0.125f;
  return request;
}

bool valid_plan_request(const nav_msgs::srv::GetPlan::Request & request)
{
  return request.start.header.stamp.sec == -9 &&
         request.start.header.stamp.nanosec == 111222333u &&
         request.start.header.frame_id == "fleet/plan_map" &&
         std::abs(request.start.pose.position.x + 2.0) < 1e-12 &&
         std::abs(request.start.pose.position.y - 1.5) < 1e-12 &&
         request.goal.header.stamp.sec == 19 &&
         request.goal.header.stamp.nanosec == 444555666u &&
         request.goal.header.frame_id == "fleet/plan_map" &&
         std::abs(request.goal.pose.position.x - 8.0) < 1e-12 &&
         std::abs(request.goal.pose.position.y + 3.5) < 1e-12 &&
         std::abs(request.tolerance - 0.125f) < 1e-6f;
}

nav_msgs::msg::Path make_plan_response(const nav_msgs::srv::GetPlan::Request & request)
{
  nav_msgs::msg::Path plan;
  plan.header.stamp = request.goal.header.stamp;
  plan.header.frame_id = request.start.header.frame_id + "/plan";
  plan.poses.reserve(kPlanPoseCount);
  for (std::size_t index = 0; index < kPlanPoseCount; ++index) {
    const double ratio =
      static_cast<double>(index) / static_cast<double>(kPlanPoseCount - 1);
    geometry_msgs::msg::PoseStamped pose;
    pose.header.stamp.sec = static_cast<std::int32_t>(index) - 32;
    pose.header.stamp.nanosec = static_cast<std::uint32_t>(index * 1000000u);
    pose.header.frame_id = plan.header.frame_id + "/" + std::to_string(index);
    pose.pose.position.x =
      request.start.pose.position.x +
      ratio * (request.goal.pose.position.x - request.start.pose.position.x);
    pose.pose.position.y =
      request.start.pose.position.y +
      ratio * (request.goal.pose.position.y - request.start.pose.position.y);
    pose.pose.orientation.z = ratio;
    pose.pose.orientation.w = 1.0;
    plan.poses.push_back(std::move(pose));
  }
  return plan;
}

bool valid_plan_response(const nav_msgs::msg::Path & plan)
{
  const auto request = make_plan_request();
  if (plan.header.stamp.sec != request.goal.header.stamp.sec ||
    plan.header.stamp.nanosec != request.goal.header.stamp.nanosec ||
    plan.header.frame_id != "fleet/plan_map/plan" ||
    plan.poses.size() != kPlanPoseCount)
  {
    return false;
  }
  for (std::size_t index = 0; index < plan.poses.size(); ++index) {
    const double ratio =
      static_cast<double>(index) / static_cast<double>(kPlanPoseCount - 1);
    const auto & pose = plan.poses[index];
    if (pose.header.stamp.sec != static_cast<std::int32_t>(index) - 32 ||
      pose.header.stamp.nanosec != static_cast<std::uint32_t>(index * 1000000u) ||
      pose.header.frame_id != "fleet/plan_map/plan/" + std::to_string(index) ||
      std::abs(pose.pose.position.x - (-2.0 + ratio * 10.0)) > 1e-12 ||
      std::abs(pose.pose.position.y - (1.5 - ratio * 5.0)) > 1e-12 ||
      std::abs(pose.pose.orientation.z - ratio) > 1e-12 ||
      std::abs(pose.pose.orientation.w - 1.0) > 1e-12)
    {
      return false;
    }
  }
  return true;
}

int run_server()
{
  auto node = std::make_shared<rclcpp::Node>("fleetqox_cpp_interprocess_server");
  auto reply_publisher = node->create_publisher<geometry_msgs::msg::PoseStamped>(
    "/fleetqox/cpp_pose_reply", rclcpp::QoS(10).reliable());
  bool pose_received = false;
  bool path_received = false;
  bool path_valid = false;
  bool service_received = false;
  bool plan_service_received = false;
  bool plan_request_valid = false;
  auto subscription = node->create_subscription<geometry_msgs::msg::PoseStamped>(
    "/fleetqox/cpp_pose_request",
    rclcpp::QoS(10).reliable(),
    [&](geometry_msgs::msg::PoseStamped::ConstSharedPtr request) {
      geometry_msgs::msg::PoseStamped reply = *request;
      reply.header.frame_id += "/ack";
      reply.pose.position.x += 1.0;
      reply_publisher->publish(reply);
      pose_received = true;
    });
  auto path_reply_publisher = node->create_publisher<nav_msgs::msg::Path>(
    "/fleetqox/cpp_path_reply", rclcpp::QoS(10).reliable());
  auto path_subscription = node->create_subscription<nav_msgs::msg::Path>(
    "/fleetqox/cpp_path_request",
    rclcpp::QoS(10).reliable(),
    [&](nav_msgs::msg::Path::ConstSharedPtr request) {
      path_received = true;
      path_valid = valid_path_request(*request);
      if (!path_valid) {
        return;
      }
      nav_msgs::msg::Path reply = *request;
      reply.header.frame_id += "/ack";
      for (auto & pose : reply.poses) {
        pose.header.frame_id += "/ack";
        pose.pose.position.x += 100.0;
      }
      path_reply_publisher->publish(reply);
    });
  auto service = node->create_service<std_srvs::srv::SetBool>(
    "/fleetqox/cpp_set_bool",
    [&](const std::shared_ptr<std_srvs::srv::SetBool::Request> request,
      std::shared_ptr<std_srvs::srv::SetBool::Response> response)
    {
      service_received = true;
      response->success = request->data;
      response->message = request->data ? "cpp-service-ok" : "cpp-service-false";
    });
  auto plan_service = node->create_service<nav_msgs::srv::GetPlan>(
    "/fleetqox/cpp_get_plan",
    [&](const std::shared_ptr<nav_msgs::srv::GetPlan::Request> request,
      std::shared_ptr<nav_msgs::srv::GetPlan::Response> response)
    {
      plan_service_received = true;
      plan_request_valid = valid_plan_request(*request);
      if (plan_request_valid) {
        response->plan = make_plan_response(*request);
      }
    });
  std::atomic<size_t> request_callback_count{0};
  rmw_service_t * rmw_service = rcl_service_get_rmw_handle(
    service->get_service_handle().get());
  const bool request_callback_registered = rmw_service != nullptr &&
    rmw_service_set_on_new_request_callback(
    rmw_service, count_new_data_callback, &request_callback_count) == RMW_RET_OK;

  rclcpp::executors::SingleThreadedExecutor executor;
  executor.add_node(node);
  const auto deadline = std::chrono::steady_clock::now() + 15s;
  while (rclcpp::ok() && std::chrono::steady_clock::now() < deadline &&
    !(pose_received && path_received && path_valid && service_received &&
    plan_service_received && plan_request_valid))
  {
    executor.spin_once(50ms);
  }
  const bool request_callback_observed = request_callback_count.load() > 0;
  const bool ok = pose_received && path_received && path_valid && service_received &&
    plan_service_received && plan_request_valid && request_callback_registered &&
    request_callback_observed;
  std::cout << "{\"schema_version\":\"fleetrmw.rclcpp_interprocess_server.v1\","
            << "\"status\":\"" << (ok ? "ok" : "failed") << "\","
            << "\"pose_received\":" << (pose_received ? "true" : "false") << ","
            << "\"path_received\":" << (path_received ? "true" : "false") << ","
            << "\"path_valid\":" << (path_valid ? "true" : "false") << ","
            << "\"path_pose_count\":" << kPathPoseCount << ","
            << "\"service_received\":" << (service_received ? "true" : "false") << ","
            << "\"plan_service_received\":"
            << (plan_service_received ? "true" : "false") << ","
            << "\"plan_request_valid\":"
            << (plan_request_valid ? "true" : "false") << ","
            << "\"plan_pose_count\":" << kPlanPoseCount << ","
            << "\"request_callback_observed\":"
            << (request_callback_observed ? "true" : "false") << "}\n";
  executor.remove_node(node);
  plan_service.reset();
  service.reset();
  path_subscription.reset();
  path_reply_publisher.reset();
  subscription.reset();
  reply_publisher.reset();
  node.reset();
  return ok ? 0 : 1;
}

int run_client()
{
  auto node = std::make_shared<rclcpp::Node>("fleetqox_cpp_interprocess_client");
  auto request_publisher = node->create_publisher<geometry_msgs::msg::PoseStamped>(
    "/fleetqox/cpp_pose_request", rclcpp::QoS(10).reliable());
  bool pose_received = false;
  bool path_received = false;
  auto subscription = node->create_subscription<geometry_msgs::msg::PoseStamped>(
    "/fleetqox/cpp_pose_reply",
    rclcpp::QoS(10).reliable(),
    [&](geometry_msgs::msg::PoseStamped::ConstSharedPtr reply) {
      pose_received =
        reply->header.frame_id == "fleet/map/ack" &&
        reply->header.stamp.sec == -7 &&
        reply->header.stamp.nanosec == 123456789u &&
        std::abs(reply->pose.position.x - 2.25) < 1e-12 &&
        std::abs(reply->pose.position.y + 2.5) < 1e-12;
    });
  auto path_request_publisher = node->create_publisher<nav_msgs::msg::Path>(
    "/fleetqox/cpp_path_request", rclcpp::QoS(10).reliable());
  auto path_subscription = node->create_subscription<nav_msgs::msg::Path>(
    "/fleetqox/cpp_path_reply",
    rclcpp::QoS(10).reliable(),
    [&](nav_msgs::msg::Path::ConstSharedPtr reply) {
      path_received = valid_path_reply(*reply);
    });
  auto client = node->create_client<std_srvs::srv::SetBool>("/fleetqox/cpp_set_bool");
  auto plan_client = node->create_client<nav_msgs::srv::GetPlan>("/fleetqox/cpp_get_plan");
  std::atomic<size_t> response_callback_count{0};
  rmw_client_t * rmw_client = rcl_client_get_rmw_handle(client->get_client_handle().get());
  const bool response_callback_registered = rmw_client != nullptr &&
    rmw_client_set_on_new_response_callback(
    rmw_client, count_new_data_callback, &response_callback_count) == RMW_RET_OK;
  std::atomic<size_t> plan_response_callback_count{0};
  rmw_client_t * rmw_plan_client = rcl_client_get_rmw_handle(
    plan_client->get_client_handle().get());
  const bool plan_response_callback_registered = rmw_plan_client != nullptr &&
    rmw_client_set_on_new_response_callback(
    rmw_plan_client, count_new_data_callback, &plan_response_callback_count) == RMW_RET_OK;
  const bool publisher_network_flow = publisher_flow_ok(request_publisher, 49802);
  const bool subscription_network_flow = subscription_flow_ok(subscription, 49802);
  const bool path_publisher_network_flow = publisher_flow_ok(path_request_publisher, 49802);
  const bool path_subscription_network_flow = subscription_flow_ok(path_subscription, 49802);

  rclcpp::executors::SingleThreadedExecutor executor;
  executor.add_node(node);
  const auto service_deadline = std::chrono::steady_clock::now() + 8s;
  while (rclcpp::ok() &&
    !(client->service_is_ready() && plan_client->service_is_ready()) &&
    std::chrono::steady_clock::now() < service_deadline)
  {
    executor.spin_once(50ms);
  }
  const bool service_available = client->service_is_ready();
  const bool plan_service_available = plan_client->service_is_ready();
  std::shared_future<std::shared_ptr<std_srvs::srv::SetBool::Response>> service_future;
  if (service_available) {
    auto request = std::make_shared<std_srvs::srv::SetBool::Request>();
    request->data = true;
    service_future = client->async_send_request(request).future.share();
  }
  std::shared_future<std::shared_ptr<nav_msgs::srv::GetPlan::Response>> plan_future;
  if (plan_service_available) {
    auto request = std::make_shared<nav_msgs::srv::GetPlan::Request>(make_plan_request());
    plan_future = plan_client->async_send_request(request).future.share();
  }

  geometry_msgs::msg::PoseStamped pose;
  pose.header.stamp.sec = -7;
  pose.header.stamp.nanosec = 123456789u;
  pose.header.frame_id = "fleet/map";
  pose.pose.position.x = 1.25;
  pose.pose.position.y = -2.5;
  pose.pose.orientation.w = 1.0;
  const nav_msgs::msg::Path path = make_path_request();

  bool service_ok = false;
  bool plan_service_ok = false;
  const auto deadline = std::chrono::steady_clock::now() + 12s;
  auto next_publish = std::chrono::steady_clock::now();
  while (rclcpp::ok() && std::chrono::steady_clock::now() < deadline &&
    !(pose_received && path_received && service_ok && plan_service_ok))
  {
    if (std::chrono::steady_clock::now() >= next_publish && !pose_received) {
      request_publisher->publish(pose);
      if (!path_received) {
        path_request_publisher->publish(path);
      }
      next_publish = std::chrono::steady_clock::now() + 200ms;
    } else if (std::chrono::steady_clock::now() >= next_publish && !path_received) {
      path_request_publisher->publish(path);
      next_publish = std::chrono::steady_clock::now() + 200ms;
    }
    executor.spin_once(50ms);
    if (service_future.valid() && service_future.wait_for(0s) == std::future_status::ready) {
      const auto response = service_future.get();
      service_ok = response != nullptr && response->success &&
        response->message == "cpp-service-ok";
    }
    if (plan_future.valid() && plan_future.wait_for(0s) == std::future_status::ready) {
      const auto response = plan_future.get();
      plan_service_ok = response != nullptr && valid_plan_response(response->plan);
    }
  }
  const bool response_callback_observed = response_callback_count.load() > 0;
  const bool plan_response_callback_observed = plan_response_callback_count.load() > 0;
  const bool ok = service_available && service_ok &&
    plan_service_available && plan_service_ok && pose_received && path_received &&
    publisher_network_flow && subscription_network_flow &&
    path_publisher_network_flow && path_subscription_network_flow &&
    response_callback_registered && response_callback_observed &&
    plan_response_callback_registered && plan_response_callback_observed;
  std::cout << "{\"schema_version\":\"fleetrmw.rclcpp_interprocess_client.v1\","
            << "\"status\":\"" << (ok ? "ok" : "failed") << "\","
            << "\"service_available\":" << (service_available ? "true" : "false") << ","
            << "\"service_ok\":" << (service_ok ? "true" : "false") << ","
            << "\"plan_service_available\":"
            << (plan_service_available ? "true" : "false") << ","
            << "\"plan_service_ok\":" << (plan_service_ok ? "true" : "false") << ","
            << "\"plan_pose_count\":" << kPlanPoseCount << ","
            << "\"publisher_network_flow\":"
            << (publisher_network_flow ? "true" : "false") << ","
            << "\"subscription_network_flow\":"
            << (subscription_network_flow ? "true" : "false") << ","
            << "\"path_publisher_network_flow\":"
            << (path_publisher_network_flow ? "true" : "false") << ","
            << "\"path_subscription_network_flow\":"
            << (path_subscription_network_flow ? "true" : "false") << ","
            << "\"response_callback_observed\":"
            << (response_callback_observed ? "true" : "false") << ","
            << "\"plan_response_callback_observed\":"
            << (plan_response_callback_observed ? "true" : "false") << ","
            << "\"pose_roundtrip\":" << (pose_received ? "true" : "false") << ","
            << "\"path_roundtrip\":" << (path_received ? "true" : "false") << ","
            << "\"path_pose_count\":" << kPathPoseCount << "}\n";
  executor.remove_node(node);
  plan_client.reset();
  client.reset();
  path_subscription.reset();
  path_request_publisher.reset();
  subscription.reset();
  request_publisher.reset();
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

#include <chrono>
#include <cmath>
#include <atomic>
#include <future>
#include <iostream>
#include <memory>
#include <string>
#include <thread>

#include "geometry_msgs/msg/pose_stamped.hpp"
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

int run_server()
{
  auto node = std::make_shared<rclcpp::Node>("fleetqox_cpp_interprocess_server");
  auto reply_publisher = node->create_publisher<geometry_msgs::msg::PoseStamped>(
    "/fleetqox/cpp_pose_reply", rclcpp::QoS(10).reliable());
  bool pose_received = false;
  bool service_received = false;
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
  auto service = node->create_service<std_srvs::srv::SetBool>(
    "/fleetqox/cpp_set_bool",
    [&](const std::shared_ptr<std_srvs::srv::SetBool::Request> request,
      std::shared_ptr<std_srvs::srv::SetBool::Response> response)
    {
      service_received = true;
      response->success = request->data;
      response->message = request->data ? "cpp-service-ok" : "cpp-service-false";
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
    !(pose_received && service_received))
  {
    executor.spin_once(50ms);
  }
  const bool request_callback_observed = request_callback_count.load() > 0;
  const bool ok = pose_received && service_received && request_callback_registered &&
    request_callback_observed;
  std::cout << "{\"schema_version\":\"fleetrmw.rclcpp_interprocess_server.v1\","
            << "\"status\":\"" << (ok ? "ok" : "failed") << "\","
            << "\"pose_received\":" << (pose_received ? "true" : "false") << ","
            << "\"service_received\":" << (service_received ? "true" : "false") << ","
            << "\"request_callback_observed\":"
            << (request_callback_observed ? "true" : "false") << "}\n";
  executor.remove_node(node);
  service.reset();
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
  auto client = node->create_client<std_srvs::srv::SetBool>("/fleetqox/cpp_set_bool");
  std::atomic<size_t> response_callback_count{0};
  rmw_client_t * rmw_client = rcl_client_get_rmw_handle(client->get_client_handle().get());
  const bool response_callback_registered = rmw_client != nullptr &&
    rmw_client_set_on_new_response_callback(
    rmw_client, count_new_data_callback, &response_callback_count) == RMW_RET_OK;
  const bool publisher_network_flow = publisher_flow_ok(request_publisher, 49802);
  const bool subscription_network_flow = subscription_flow_ok(subscription, 49802);

  rclcpp::executors::SingleThreadedExecutor executor;
  executor.add_node(node);
  const auto service_deadline = std::chrono::steady_clock::now() + 8s;
  while (rclcpp::ok() && !client->service_is_ready() &&
    std::chrono::steady_clock::now() < service_deadline)
  {
    executor.spin_once(50ms);
  }
  const bool service_available = client->service_is_ready();
  std::shared_future<std::shared_ptr<std_srvs::srv::SetBool::Response>> service_future;
  if (service_available) {
    auto request = std::make_shared<std_srvs::srv::SetBool::Request>();
    request->data = true;
    service_future = client->async_send_request(request);
  }

  geometry_msgs::msg::PoseStamped pose;
  pose.header.stamp.sec = -7;
  pose.header.stamp.nanosec = 123456789u;
  pose.header.frame_id = "fleet/map";
  pose.pose.position.x = 1.25;
  pose.pose.position.y = -2.5;
  pose.pose.orientation.w = 1.0;

  bool service_ok = false;
  const auto deadline = std::chrono::steady_clock::now() + 12s;
  auto next_publish = std::chrono::steady_clock::now();
  while (rclcpp::ok() && std::chrono::steady_clock::now() < deadline &&
    !(pose_received && service_ok))
  {
    if (std::chrono::steady_clock::now() >= next_publish && !pose_received) {
      request_publisher->publish(pose);
      next_publish = std::chrono::steady_clock::now() + 200ms;
    }
    executor.spin_once(50ms);
    if (service_future.valid() && service_future.wait_for(0s) == std::future_status::ready) {
      const auto response = service_future.get();
      service_ok = response != nullptr && response->success &&
        response->message == "cpp-service-ok";
    }
  }
  const bool response_callback_observed = response_callback_count.load() > 0;
  const bool ok = service_available && service_ok && pose_received &&
    publisher_network_flow && subscription_network_flow &&
    response_callback_registered && response_callback_observed;
  std::cout << "{\"schema_version\":\"fleetrmw.rclcpp_interprocess_client.v1\","
            << "\"status\":\"" << (ok ? "ok" : "failed") << "\","
            << "\"service_available\":" << (service_available ? "true" : "false") << ","
            << "\"service_ok\":" << (service_ok ? "true" : "false") << ","
            << "\"publisher_network_flow\":"
            << (publisher_network_flow ? "true" : "false") << ","
            << "\"subscription_network_flow\":"
            << (subscription_network_flow ? "true" : "false") << ","
            << "\"response_callback_observed\":"
            << (response_callback_observed ? "true" : "false") << ","
            << "\"pose_roundtrip\":" << (pose_received ? "true" : "false") << "}\n";
  executor.remove_node(node);
  client.reset();
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

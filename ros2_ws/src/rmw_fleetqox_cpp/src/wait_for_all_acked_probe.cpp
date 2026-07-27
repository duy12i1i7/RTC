#include <chrono>
#include <cstdint>
#include <cstring>
#include <future>
#include <iostream>
#include <string>
#include <thread>
#include <utility>

#include "rcutils/allocator.h"
#include "rmw/error_handling.h"
#include "rmw/init.h"
#include "rmw/init_options.h"
#include "rmw/publisher_options.h"
#include "rmw/qos_profiles.h"
#include "rmw/rmw.h"
#include "rmw/serialized_message.h"
#include "rmw/subscription_options.h"
#include "rosidl_runtime_c/message_type_support_struct.h"

extern "C" std::uint64_t rmw_fleetqox_cpp_wait_for_all_acked_calls();
extern "C" std::uint64_t rmw_fleetqox_cpp_wait_for_all_acked_successes();
extern "C" std::uint64_t rmw_fleetqox_cpp_wait_for_all_acked_timeouts();
extern "C" std::uint64_t rmw_fleetqox_cpp_last_wait_for_all_acked_expected();
extern "C" std::uint64_t rmw_fleetqox_cpp_last_wait_for_all_acked_observed();

namespace
{

bool cleanup_context(rmw_context_t * context, rmw_init_options_t * options)
{
  const rmw_ret_t shutdown_ret = rmw_shutdown(context);
  const rmw_ret_t context_fini_ret = rmw_context_fini(context);
  const rmw_ret_t options_fini_ret = rmw_init_options_fini(options);
  return shutdown_ret == RMW_RET_OK && context_fini_ret == RMW_RET_OK &&
         options_fini_ret == RMW_RET_OK;
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

}  // namespace

int main()
{
  rcutils_allocator_t allocator = rcutils_get_default_allocator();
  rmw_init_options_t options = rmw_get_zero_initialized_init_options();
  if (rmw_init_options_init(&options, allocator) != RMW_RET_OK) {
    std::cout << "{\"status\":\"init_options_failed\"}\n";
    return 1;
  }
  options.instance_id = 182;
  rmw_context_t context = rmw_get_zero_initialized_context();
  if (rmw_init(&options, &context) != RMW_RET_OK) {
    const rmw_ret_t fini_ret = rmw_init_options_fini(&options);
    std::cout << "{\"status\":\"init_failed\"}\n";
    return fini_ret == RMW_RET_OK ? 1 : 2;
  }
  rmw_node_t * node = rmw_create_node(
    &context, "fleetqox_wait_for_all_acked_probe", "/fleetqox");
  if (node == nullptr) {
    const bool cleanup_ok = cleanup_context(&context, &options);
    std::cout << "{\"status\":\"create_node_failed\"}\n";
    return cleanup_ok ? 1 : 2;
  }

  rosidl_message_type_support_t type_support{};
  type_support.typesupport_identifier = "rmw_fleetqox_cpp_wait_for_all_acked_probe";
  rmw_qos_profile_t qos = rmw_qos_profile_default;
  qos.reliability = RMW_QOS_POLICY_RELIABILITY_RELIABLE;
  qos.history = RMW_QOS_POLICY_HISTORY_KEEP_ALL;
  qos.depth = 8;
  const char * topic = "/fleetqox/wait_for_all_acked";
  rmw_publisher_options_t publisher_options = rmw_get_default_publisher_options();
  rmw_subscription_options_t subscription_options = rmw_get_default_subscription_options();
  rmw_publisher_t * publisher = rmw_create_publisher(
    node, &type_support, topic, &qos, &publisher_options);
  rmw_subscription_t * first_subscription = rmw_create_subscription(
    node, &type_support, topic, &qos, &subscription_options);
  rmw_subscription_t * second_subscription = rmw_create_subscription(
    node, &type_support, topic, &qos, &subscription_options);
  if (publisher == nullptr || first_subscription == nullptr || second_subscription == nullptr) {
    std::cout << "{\"status\":\"create_endpoint_failed\"}\n";
    return 1;
  }

  size_t matched_subscription_count = 0;
  const rmw_ret_t matched_ret = rmw_publisher_count_matched_subscriptions(
    publisher, &matched_subscription_count);
  const rmw_time_t zero_timeout{0, 0};
  const rmw_ret_t empty_wait_ret = rmw_publisher_wait_for_all_acked(
    publisher, zero_timeout);

  rmw_serialized_message_t message = rmw_get_zero_initialized_serialized_message();
  const bool message_initialized = init_serialized_message(
    &message, "wait-for-both-acknowledgments", &allocator);
  const rmw_ret_t publish_ret = message_initialized ?
    rmw_publish_serialized_message(publisher, &message, nullptr) : RMW_RET_BAD_ALLOC;

  const rmw_time_t partial_timeout{0, 200000000};
  const auto partial_started = std::chrono::steady_clock::now();
  const rmw_ret_t partial_wait_ret = rmw_publisher_wait_for_all_acked(
    publisher, partial_timeout);
  const auto partial_elapsed_ms = std::chrono::duration_cast<std::chrono::milliseconds>(
    std::chrono::steady_clock::now() - partial_started).count();
  const std::uint64_t partial_expected =
    rmw_fleetqox_cpp_last_wait_for_all_acked_expected();
  const std::uint64_t partial_observed =
    rmw_fleetqox_cpp_last_wait_for_all_acked_observed();

  const rmw_time_t completion_timeout{1, 0};
  const rmw_ret_t completed_wait_ret = rmw_publisher_wait_for_all_acked(
    publisher, completion_timeout);
  const std::uint64_t completed_expected =
    rmw_fleetqox_cpp_last_wait_for_all_acked_expected();
  const std::uint64_t completed_observed =
    rmw_fleetqox_cpp_last_wait_for_all_acked_observed();
  const rmw_ret_t completed_zero_wait_ret = rmw_publisher_wait_for_all_acked(
    publisher, zero_timeout);

  const rmw_ret_t snapshot_publish_ret =
    rmw_publish_serialized_message(publisher, &message, nullptr);
  auto snapshot_wait_future = std::async(
    std::launch::async,
    [publisher]() {
      const rmw_time_t timeout{2, 0};
      const auto started = std::chrono::steady_clock::now();
      const rmw_ret_t ret = rmw_publisher_wait_for_all_acked(publisher, timeout);
      const auto elapsed_ms = std::chrono::duration_cast<std::chrono::milliseconds>(
        std::chrono::steady_clock::now() - started).count();
      return std::make_pair(ret, elapsed_ms);
    });
  std::this_thread::sleep_for(std::chrono::milliseconds(250));
  const rmw_ret_t later_publish_ret =
    rmw_publish_serialized_message(publisher, &message, nullptr);
  const auto snapshot_wait = snapshot_wait_future.get();
  const rmw_ret_t later_zero_wait_ret = rmw_publisher_wait_for_all_acked(
    publisher, zero_timeout);
  const rmw_time_t later_completion_timeout{2, 0};
  const rmw_ret_t later_completed_wait_ret = rmw_publisher_wait_for_all_acked(
    publisher, later_completion_timeout);
  const bool concurrent_snapshot_ok =
    snapshot_publish_ret == RMW_RET_OK && later_publish_ret == RMW_RET_OK &&
    snapshot_wait.first == RMW_RET_OK &&
    snapshot_wait.second >= 500 && snapshot_wait.second < 900 &&
    later_zero_wait_ret == RMW_RET_TIMEOUT &&
    later_completed_wait_ret == RMW_RET_OK;

  const rmw_ret_t concurrent_publish_ret =
    rmw_publish_serialized_message(publisher, &message, nullptr);
  auto finite_wait_future = std::async(
    std::launch::async,
    [publisher]() {
      const rmw_time_t timeout{2, 0};
      return rmw_publisher_wait_for_all_acked(publisher, timeout);
    });
  auto infinite_wait_future = std::async(
    std::launch::async,
    [publisher]() {
      return rmw_publisher_wait_for_all_acked(
        publisher, RMW_DURATION_INFINITE);
    });
  const rmw_ret_t finite_wait_ret = finite_wait_future.get();
  const rmw_ret_t infinite_wait_ret = infinite_wait_future.get();
  const bool concurrent_waiters_ok =
    concurrent_publish_ret == RMW_RET_OK &&
    finite_wait_ret == RMW_RET_OK && infinite_wait_ret == RMW_RET_OK;

  const rmw_ret_t unmatch_publish_ret =
    rmw_publish_serialized_message(publisher, &message, nullptr);
  auto unmatch_wait_future = std::async(
    std::launch::async,
    [publisher]() {
      const rmw_time_t timeout{2, 0};
      const auto started = std::chrono::steady_clock::now();
      const rmw_ret_t ret = rmw_publisher_wait_for_all_acked(publisher, timeout);
      const auto elapsed_ms = std::chrono::duration_cast<std::chrono::milliseconds>(
        std::chrono::steady_clock::now() - started).count();
      return std::make_pair(ret, elapsed_ms);
    });
  std::this_thread::sleep_for(std::chrono::milliseconds(150));
  const rmw_ret_t unmatch_destroy_ret =
    rmw_destroy_subscription(node, second_subscription);
  second_subscription = nullptr;
  const auto unmatch_wait = unmatch_wait_future.get();
  const bool unmatch_releases_wait =
    unmatch_publish_ret == RMW_RET_OK &&
    unmatch_destroy_ret == RMW_RET_OK &&
    unmatch_wait.first == RMW_RET_OK &&
    unmatch_wait.second >= 100 && unmatch_wait.second < 500;

  rmw_qos_profile_t best_effort_qos = qos;
  best_effort_qos.reliability = RMW_QOS_POLICY_RELIABILITY_BEST_EFFORT;
  rmw_publisher_t * best_effort_publisher = rmw_create_publisher(
    node,
    &type_support,
    "/fleetqox/wait_for_all_acked_best_effort",
    &best_effort_qos,
    &publisher_options);
  rmw_subscription_t * best_effort_subscription = rmw_create_subscription(
    node,
    &type_support,
    "/fleetqox/wait_for_all_acked_best_effort",
    &best_effort_qos,
    &subscription_options);
  const rmw_ret_t best_effort_publish_ret =
    best_effort_publisher != nullptr && best_effort_subscription != nullptr ?
    rmw_publish_serialized_message(best_effort_publisher, &message, nullptr) :
    RMW_RET_ERROR;
  const rmw_ret_t best_effort_wait_ret =
    best_effort_publisher != nullptr ?
    rmw_publisher_wait_for_all_acked(best_effort_publisher, zero_timeout) :
    RMW_RET_ERROR;
  const bool best_effort_immediate_ok =
    best_effort_publish_ret == RMW_RET_OK &&
    best_effort_wait_ret == RMW_RET_OK;

  rmw_publisher_t foreign_publisher = *publisher;
  foreign_publisher.implementation_identifier = "foreign_rmw";
  const rmw_ret_t foreign_publisher_ret = rmw_publisher_wait_for_all_acked(
    &foreign_publisher, zero_timeout);
  rmw_reset_error();

  const rmw_ret_t null_publisher_ret = rmw_publisher_wait_for_all_acked(
    nullptr, zero_timeout);
  rmw_reset_error();

  const bool behavior_ok =
    matched_ret == RMW_RET_OK && matched_subscription_count == 2 &&
    empty_wait_ret == RMW_RET_OK && publish_ret == RMW_RET_OK &&
    partial_wait_ret == RMW_RET_TIMEOUT && partial_elapsed_ms >= 150 &&
    partial_expected == 2 && partial_observed == 1 &&
    completed_wait_ret == RMW_RET_OK && completed_expected == 2 &&
    completed_observed == 2 && completed_zero_wait_ret == RMW_RET_OK &&
    concurrent_snapshot_ok && concurrent_waiters_ok &&
    unmatch_releases_wait && best_effort_immediate_ok &&
    foreign_publisher_ret == RMW_RET_INCORRECT_RMW_IMPLEMENTATION &&
    null_publisher_ret == RMW_RET_INVALID_ARGUMENT;

  const rmw_ret_t message_fini_ret = message_initialized ?
    rmw_serialized_message_fini(&message) : RMW_RET_OK;
  const rmw_ret_t first_destroy_ret = rmw_destroy_subscription(node, first_subscription);
  const rmw_ret_t best_effort_subscription_destroy_ret =
    best_effort_subscription == nullptr ? RMW_RET_ERROR :
    rmw_destroy_subscription(node, best_effort_subscription);
  const rmw_ret_t best_effort_publisher_destroy_ret =
    best_effort_publisher == nullptr ? RMW_RET_ERROR :
    rmw_destroy_publisher(node, best_effort_publisher);
  const rmw_ret_t publisher_destroy_ret = rmw_destroy_publisher(node, publisher);
  const rmw_ret_t node_destroy_ret = rmw_destroy_node(node);
  const bool context_cleanup_ok = cleanup_context(&context, &options);
  const bool cleanup_ok =
    message_fini_ret == RMW_RET_OK && first_destroy_ret == RMW_RET_OK &&
    best_effort_subscription_destroy_ret == RMW_RET_OK &&
    best_effort_publisher_destroy_ret == RMW_RET_OK &&
    publisher_destroy_ret == RMW_RET_OK &&
    node_destroy_ret == RMW_RET_OK && context_cleanup_ok;

  std::cout << "{\"schema_version\":\"fleetrmw.rmw_wait_for_all_acked_probe.v2\",";
  std::cout << "\"status\":\"" << (behavior_ok && cleanup_ok ? "ok" : "failed") << "\",";
  std::cout << "\"matched_subscription_count\":" << matched_subscription_count << ",";
  std::cout << "\"empty_wait_ok\":" << (empty_wait_ret == RMW_RET_OK ? "true" : "false") << ",";
  std::cout << "\"partial_ack_timeout\":" <<
    (partial_wait_ret == RMW_RET_TIMEOUT ? "true" : "false") << ",";
  std::cout << "\"partial_wait_elapsed_ms\":" << partial_elapsed_ms << ",";
  std::cout << "\"partial_expected_ack_count\":" << partial_expected << ",";
  std::cout << "\"partial_observed_ack_count\":" << partial_observed << ",";
  std::cout << "\"all_acked_wait_ok\":" <<
    (completed_wait_ret == RMW_RET_OK ? "true" : "false") << ",";
  std::cout << "\"completed_expected_ack_count\":" << completed_expected << ",";
  std::cout << "\"completed_observed_ack_count\":" << completed_observed << ",";
  std::cout << "\"zero_timeout_after_ack_ok\":" <<
    (completed_zero_wait_ret == RMW_RET_OK ? "true" : "false") << ",";
  std::cout << "\"snapshot_excludes_later_publish\":" <<
    (concurrent_snapshot_ok ? "true" : "false") << ",";
  std::cout << "\"snapshot_wait_elapsed_ms\":" << snapshot_wait.second << ",";
  std::cout << "\"later_publish_initially_unacked\":" <<
    (later_zero_wait_ret == RMW_RET_TIMEOUT ? "true" : "false") << ",";
  std::cout << "\"concurrent_waiters_ok\":" <<
    (concurrent_waiters_ok ? "true" : "false") << ",";
  std::cout << "\"infinite_wait_ok\":" <<
    (infinite_wait_ret == RMW_RET_OK ? "true" : "false") << ",";
  std::cout << "\"unmatch_releases_wait\":" <<
    (unmatch_releases_wait ? "true" : "false") << ",";
  std::cout << "\"unmatch_wait_elapsed_ms\":" << unmatch_wait.second << ",";
  std::cout << "\"best_effort_immediate_ok\":" <<
    (best_effort_immediate_ok ? "true" : "false") << ",";
  std::cout << "\"foreign_publisher_rejected\":" <<
    (foreign_publisher_ret == RMW_RET_INCORRECT_RMW_IMPLEMENTATION ? "true" : "false") << ",";
  std::cout << "\"null_publisher_rejected\":" <<
    (null_publisher_ret == RMW_RET_INVALID_ARGUMENT ? "true" : "false") << ",";
  std::cout << "\"wait_call_count\":" << rmw_fleetqox_cpp_wait_for_all_acked_calls() << ",";
  std::cout << "\"wait_success_count\":" <<
    rmw_fleetqox_cpp_wait_for_all_acked_successes() << ",";
  std::cout << "\"wait_timeout_count\":" <<
    rmw_fleetqox_cpp_wait_for_all_acked_timeouts() << "}\n";
  return behavior_ok && cleanup_ok ? 0 : 1;
}

#include <chrono>
#include <cstdint>
#include <cstring>
#include <iostream>
#include <string>
#include <thread>

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

extern "C" std::uint64_t rmw_fleetqox_cpp_last_wait_for_all_acked_expected();
extern "C" std::uint64_t rmw_fleetqox_cpp_last_wait_for_all_acked_observed();

namespace
{

constexpr const char * kSchema = "fleetrmw.remote_wait_for_all_acked_probe.v1";
constexpr const char * kTopic = "/fleetqox/remote_wait_for_all_acked";
constexpr const char * kPayload = "remote-two-reader-ack-snapshot";

rmw_qos_profile_t reliable_qos()
{
  rmw_qos_profile_t qos = rmw_qos_profile_default;
  qos.reliability = RMW_QOS_POLICY_RELIABILITY_RELIABLE;
  qos.history = RMW_QOS_POLICY_HISTORY_KEEP_ALL;
  qos.depth = 8;
  return qos;
}

bool init_context(
  rcutils_allocator_t allocator,
  std::uint64_t instance_id,
  rmw_init_options_t * options,
  rmw_context_t * context)
{
  if (options == nullptr || context == nullptr) {
    return false;
  }
  *options = rmw_get_zero_initialized_init_options();
  if (rmw_init_options_init(options, allocator) != RMW_RET_OK) {
    return false;
  }
  options->instance_id = instance_id;
  *context = rmw_get_zero_initialized_context();
  if (rmw_init(options, context) != RMW_RET_OK) {
    const rmw_ret_t fini_ret = rmw_init_options_fini(options);
    (void)fini_ret;
    return false;
  }
  return true;
}

bool fini_context(rmw_context_t * context, rmw_init_options_t * options)
{
  const rmw_ret_t shutdown_ret = rmw_shutdown(context);
  const rmw_ret_t context_ret = rmw_context_fini(context);
  const rmw_ret_t options_ret = rmw_init_options_fini(options);
  return shutdown_ret == RMW_RET_OK && context_ret == RMW_RET_OK &&
         options_ret == RMW_RET_OK;
}

bool init_serialized_message(
  rmw_serialized_message_t * message,
  const std::string & payload,
  rcutils_allocator_t * allocator)
{
  if (message == nullptr || allocator == nullptr ||
    rmw_serialized_message_init(message, payload.size(), allocator) != RMW_RET_OK)
  {
    return false;
  }
  if (!payload.empty()) {
    std::memcpy(message->buffer, payload.data(), payload.size());
  }
  message->buffer_length = payload.size();
  return true;
}

int run_publisher()
{
  rcutils_allocator_t allocator = rcutils_get_default_allocator();
  rmw_init_options_t options{};
  rmw_context_t context{};
  if (!init_context(allocator, 913, &options, &context)) {
    std::cout << "{\"schema_version\":\"" << kSchema <<
      "\",\"mode\":\"publisher\",\"status\":\"init_failed\"}" << std::endl;
    return 1;
  }

  rmw_node_t * node = rmw_create_node(
    &context, "remote_wait_for_all_acked_publisher", "/fleetqox");
  rosidl_message_type_support_t type_support{};
  type_support.typesupport_identifier = "fleetrmw_remote_wait_for_all_acked_type";
  const rmw_qos_profile_t qos = reliable_qos();
  const rmw_publisher_options_t publisher_options = rmw_get_default_publisher_options();
  rmw_publisher_t * publisher = node == nullptr ? nullptr : rmw_create_publisher(
    node, &type_support, kTopic, &qos, &publisher_options);
  std::cout << "{\"schema_version\":\"" << kSchema <<
    "\",\"mode\":\"publisher\",\"phase\":\"ready\",\"initialized\":" <<
    (publisher != nullptr ? "true" : "false") << "}" << std::endl;

  size_t matched_count = 0;
  bool two_readers_matched = false;
  const auto discovery_deadline =
    std::chrono::steady_clock::now() + std::chrono::seconds(6);
  while (publisher != nullptr && std::chrono::steady_clock::now() < discovery_deadline) {
    if (rmw_publisher_count_matched_subscriptions(publisher, &matched_count) == RMW_RET_OK &&
      matched_count == 2)
    {
      two_readers_matched = true;
      break;
    }
    std::this_thread::sleep_for(std::chrono::milliseconds(10));
  }

  const rmw_time_t zero_timeout{0, 0};
  const rmw_ret_t empty_wait_ret = publisher == nullptr ? RMW_RET_ERROR :
    rmw_publisher_wait_for_all_acked(publisher, zero_timeout);
  rmw_serialized_message_t outgoing = rmw_get_zero_initialized_serialized_message();
  const bool message_initialized = init_serialized_message(&outgoing, kPayload, &allocator);
  const rmw_ret_t publish_ret =
    publisher != nullptr && message_initialized && two_readers_matched ?
    rmw_publish_serialized_message(publisher, &outgoing, nullptr) : RMW_RET_ERROR;

  const rmw_time_t partial_timeout{0, 200000000};
  const auto partial_start = std::chrono::steady_clock::now();
  const rmw_ret_t partial_ret = publish_ret == RMW_RET_OK ?
    rmw_publisher_wait_for_all_acked(publisher, partial_timeout) : RMW_RET_ERROR;
  const auto partial_elapsed_ms = std::chrono::duration_cast<std::chrono::milliseconds>(
    std::chrono::steady_clock::now() - partial_start).count();
  const std::uint64_t partial_expected =
    rmw_fleetqox_cpp_last_wait_for_all_acked_expected();
  const std::uint64_t partial_observed =
    rmw_fleetqox_cpp_last_wait_for_all_acked_observed();

  const rmw_time_t completion_timeout{2, 0};
  const rmw_ret_t completed_ret = publish_ret == RMW_RET_OK ?
    rmw_publisher_wait_for_all_acked(publisher, completion_timeout) : RMW_RET_ERROR;
  const std::uint64_t completed_expected =
    rmw_fleetqox_cpp_last_wait_for_all_acked_expected();
  const std::uint64_t completed_observed =
    rmw_fleetqox_cpp_last_wait_for_all_acked_observed();
  const rmw_ret_t completed_zero_ret = completed_ret == RMW_RET_OK ?
    rmw_publisher_wait_for_all_acked(publisher, zero_timeout) : RMW_RET_ERROR;

  bool teardown_ok = true;
  if (message_initialized) {
    teardown_ok = rmw_serialized_message_fini(&outgoing) == RMW_RET_OK && teardown_ok;
  }
  if (publisher != nullptr) {
    teardown_ok = rmw_destroy_publisher(node, publisher) == RMW_RET_OK && teardown_ok;
  }
  if (node != nullptr) {
    teardown_ok = rmw_destroy_node(node) == RMW_RET_OK && teardown_ok;
  }
  teardown_ok = fini_context(&context, &options) && teardown_ok;

  const bool partial_ok = partial_ret == RMW_RET_TIMEOUT && partial_elapsed_ms >= 150 &&
    partial_expected == 2 && partial_observed == 1;
  const bool completed_ok = completed_ret == RMW_RET_OK && completed_expected == 2 &&
    completed_observed == 2 && completed_zero_ret == RMW_RET_OK;
  const bool ok = two_readers_matched && empty_wait_ret == RMW_RET_OK &&
    publish_ret == RMW_RET_OK && partial_ok && completed_ok && teardown_ok;
  std::cout << "{\"schema_version\":\"" << kSchema <<
    "\",\"mode\":\"publisher\",\"status\":\"" << (ok ? "ok" : "failed") <<
    "\",\"remote_two_reader_ack_snapshot_claim\":" << (ok ? "true" : "false") <<
    ",\"matched_subscription_count\":" << matched_count <<
    ",\"empty_wait_ok\":" << (empty_wait_ret == RMW_RET_OK ? "true" : "false") <<
    ",\"published\":" << (publish_ret == RMW_RET_OK ? "true" : "false") <<
    ",\"partial_ack_timeout\":" << (partial_ret == RMW_RET_TIMEOUT ? "true" : "false") <<
    ",\"partial_wait_elapsed_ms\":" << partial_elapsed_ms <<
    ",\"partial_expected_ack_count\":" << partial_expected <<
    ",\"partial_observed_ack_count\":" << partial_observed <<
    ",\"all_acked_wait_ok\":" << (completed_ret == RMW_RET_OK ? "true" : "false") <<
    ",\"completed_expected_ack_count\":" << completed_expected <<
    ",\"completed_observed_ack_count\":" << completed_observed <<
    ",\"zero_timeout_after_ack_ok\":" <<
    (completed_zero_ret == RMW_RET_OK ? "true" : "false") <<
    ",\"clean_teardown\":" << (teardown_ok ? "true" : "false") << "}" << std::endl;
  return ok ? 0 : 1;
}

int run_subscriber(int subscriber_index, int hold_ms)
{
  rcutils_allocator_t allocator = rcutils_get_default_allocator();
  rmw_init_options_t options{};
  rmw_context_t context{};
  if (!init_context(allocator, static_cast<std::uint64_t>(920 + subscriber_index), &options, &context)) {
    return 1;
  }
  const std::string node_name =
    "remote_wait_for_all_acked_subscriber_" + std::to_string(subscriber_index);
  rmw_node_t * node = rmw_create_node(&context, node_name.c_str(), "/fleetqox");
  rosidl_message_type_support_t type_support{};
  type_support.typesupport_identifier = "fleetrmw_remote_wait_for_all_acked_type";
  const rmw_qos_profile_t qos = reliable_qos();
  const rmw_subscription_options_t subscription_options = rmw_get_default_subscription_options();
  rmw_subscription_t * subscription = node == nullptr ? nullptr : rmw_create_subscription(
    node, &type_support, kTopic, &qos, &subscription_options);
  std::cout << "{\"schema_version\":\"" << kSchema <<
    "\",\"mode\":\"subscriber\",\"subscriber_index\":" << subscriber_index <<
    ",\"phase\":\"ready\",\"initialized\":" <<
    (subscription != nullptr ? "true" : "false") << "}" << std::endl;

  rmw_serialized_message_t incoming = rmw_get_zero_initialized_serialized_message();
  const bool message_initialized =
    rmw_serialized_message_init(&incoming, 1, &allocator) == RMW_RET_OK;
  bool taken = false;
  bool take_ok = subscription != nullptr && message_initialized;
  const auto take_deadline = std::chrono::steady_clock::now() + std::chrono::seconds(6);
  while (take_ok && !taken && std::chrono::steady_clock::now() < take_deadline) {
    take_ok = rmw_take_serialized_message(subscription, &incoming, &taken, nullptr) == RMW_RET_OK;
    if (!taken) {
      std::this_thread::sleep_for(std::chrono::milliseconds(2));
    }
  }
  const std::string payload = taken ?
    std::string(reinterpret_cast<const char *>(incoming.buffer), incoming.buffer_length) :
    std::string{};
  if (taken && hold_ms > 0) {
    std::this_thread::sleep_for(std::chrono::milliseconds(hold_ms));
  }

  bool teardown_ok = true;
  if (message_initialized) {
    teardown_ok = rmw_serialized_message_fini(&incoming) == RMW_RET_OK && teardown_ok;
  }
  if (subscription != nullptr) {
    teardown_ok = rmw_destroy_subscription(node, subscription) == RMW_RET_OK && teardown_ok;
  }
  if (node != nullptr) {
    teardown_ok = rmw_destroy_node(node) == RMW_RET_OK && teardown_ok;
  }
  teardown_ok = fini_context(&context, &options) && teardown_ok;
  const bool payload_ok = take_ok && taken && payload == kPayload;
  const bool ok = payload_ok && teardown_ok;
  std::cout << "{\"schema_version\":\"" << kSchema <<
    "\",\"mode\":\"subscriber\",\"subscriber_index\":" << subscriber_index <<
    ",\"status\":\"" << (ok ? "ok" : "failed") <<
    "\",\"sample_taken\":" << (taken ? "true" : "false") <<
    ",\"payload_ok\":" << (payload_ok ? "true" : "false") <<
    ",\"hold_ms\":" << hold_ms <<
    ",\"clean_teardown\":" << (teardown_ok ? "true" : "false") << "}" << std::endl;
  return ok ? 0 : 1;
}

}  // namespace

int main(int argc, char ** argv)
{
  std::string mode;
  int subscriber_index = 0;
  int hold_ms = 700;
  for (int index = 1; index + 1 < argc; ++index) {
    const std::string argument(argv[index]);
    if (argument == "--mode") {
      mode = argv[index + 1];
    } else if (argument == "--subscriber-index") {
      subscriber_index = std::stoi(argv[index + 1]);
    } else if (argument == "--hold-ms") {
      hold_ms = std::stoi(argv[index + 1]);
    }
  }
  if (mode == "publisher") {
    return run_publisher();
  }
  if (mode == "subscriber" && subscriber_index > 0 && hold_ms >= 0) {
    return run_subscriber(subscriber_index, hold_ms);
  }
  std::cout << "{\"schema_version\":\"" << kSchema <<
    "\",\"status\":\"invalid_arguments\"}" << std::endl;
  return 2;
}

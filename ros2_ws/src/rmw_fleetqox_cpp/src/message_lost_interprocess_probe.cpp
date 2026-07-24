#include <algorithm>
#include <chrono>
#include <cstdint>
#include <cstring>
#include <iostream>
#include <sstream>
#include <string>
#include <thread>
#include <vector>

#include "rcutils/allocator.h"
#include "rmw/event.h"
#include "rmw/events_statuses/events_statuses.h"
#include "rmw/init.h"
#include "rmw/init_options.h"
#include "rmw/publisher_options.h"
#include "rmw/qos_profiles.h"
#include "rmw/rmw.h"
#include "rmw/serialized_message.h"
#include "rmw/subscription_options.h"
#include "rosidl_runtime_c/message_type_support_struct.h"

extern "C" std::uint64_t rmw_fleetqox_cpp_socket_ack_nack_sent();
extern "C" std::uint64_t rmw_fleetqox_cpp_socket_ack_nack_received();
extern "C" std::uint64_t rmw_fleetqox_cpp_socket_nack_retransmissions();
extern "C" std::uint64_t rmw_fleetqox_cpp_socket_repair_budget_exhausted();
extern "C" std::uint64_t rmw_fleetqox_cpp_socket_repair_sequence_attempt_limit_exhausted();
extern "C" std::uint64_t rmw_fleetqox_cpp_socket_repair_not_admitted();
extern "C" std::uint64_t rmw_fleetqox_cpp_socket_test_dropped_frames();
extern "C" std::uint64_t rmw_fleetqox_cpp_socket_unrecoverable_loss_notices_sent();
extern "C" std::uint64_t rmw_fleetqox_cpp_socket_unrecoverable_loss_notices_received();
extern "C" std::uint64_t rmw_fleetqox_cpp_unrecoverable_loss_samples_reported();

namespace
{

struct Config
{
  std::string mode{"subscriber"};
  std::string topic{"/fleetqox/message_lost_interprocess_probe"};
  int timeout_ms{5000};
  int pre_publish_wait_ms{800};
  int publish_interval_ms{40};
  int publisher_depth{1};
  std::string terminal_repair_mode{"history_exhaustion"};
};

struct CallbackState
{
  std::uint64_t calls{0};
  std::uint64_t events{0};
};

void event_callback(const void * user_data, size_t number_of_events)
{
  auto * state = const_cast<CallbackState *>(
    static_cast<const CallbackState *>(user_data));
  if (state != nullptr) {
    ++state->calls;
    state->events += number_of_events;
  }
}

Config parse_args(int argc, char ** argv)
{
  Config config;
  for (int index = 1; index < argc; ++index) {
    const std::string argument(argv[index]);
    if (argument == "--mode" && index + 1 < argc) {
      config.mode = argv[++index];
    } else if (argument == "--topic" && index + 1 < argc) {
      config.topic = argv[++index];
    } else if (argument == "--timeout-ms" && index + 1 < argc) {
      config.timeout_ms = std::stoi(argv[++index]);
    } else if (argument == "--pre-publish-wait-ms" && index + 1 < argc) {
      config.pre_publish_wait_ms = std::stoi(argv[++index]);
    } else if (argument == "--publish-interval-ms" && index + 1 < argc) {
      config.publish_interval_ms = std::stoi(argv[++index]);
    } else if (argument == "--publisher-depth" && index + 1 < argc) {
      config.publisher_depth = std::stoi(argv[++index]);
    } else if (argument == "--terminal-repair-mode" && index + 1 < argc) {
      config.terminal_repair_mode = argv[++index];
    }
  }
  return config;
}

bool cleanup_context(rmw_context_t * context, rmw_init_options_t * options)
{
  const rmw_ret_t shutdown_ret = rmw_shutdown(context);
  const rmw_ret_t context_ret = rmw_context_fini(context);
  const rmw_ret_t options_ret = rmw_init_options_fini(options);
  return shutdown_ret == RMW_RET_OK && context_ret == RMW_RET_OK &&
         options_ret == RMW_RET_OK;
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
  options->instance_id = 61;
  *context = rmw_get_zero_initialized_context();
  if (rmw_init(options, context) != RMW_RET_OK) {
    const rmw_ret_t fini_ret = rmw_init_options_fini(options);
    (void)fini_ret;
    return false;
  }
  return true;
}

bool init_message(
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

std::string message_string(const rmw_serialized_message_t & message)
{
  if (message.buffer == nullptr || message.buffer_length == 0) {
    return "";
  }
  return std::string(
    reinterpret_cast<const char *>(message.buffer),
    reinterpret_cast<const char *>(message.buffer + message.buffer_length));
}

bool contains(const std::vector<std::string> & payloads, const std::string & expected)
{
  return std::find(payloads.begin(), payloads.end(), expected) != payloads.end();
}

bool terminal_repair_mode_valid(const std::string & mode)
{
  return mode == "history_exhaustion" || mode == "budget_exhaustion" ||
         mode == "attempt_limit" || mode == "admission_rejection";
}

std::uint64_t expected_dropped_frame_count(const Config & config)
{
  return config.terminal_repair_mode == "attempt_limit" ? 2u : 1u;
}

bool terminal_repair_control_observed(const Config & config)
{
  const std::uint64_t retransmissions =
    rmw_fleetqox_cpp_socket_nack_retransmissions();
  const std::uint64_t budget_exhausted =
    rmw_fleetqox_cpp_socket_repair_budget_exhausted();
  const std::uint64_t attempt_limit_exhausted =
    rmw_fleetqox_cpp_socket_repair_sequence_attempt_limit_exhausted();
  const std::uint64_t not_admitted =
    rmw_fleetqox_cpp_socket_repair_not_admitted();
  if (config.terminal_repair_mode == "history_exhaustion") {
    return retransmissions == 0 && budget_exhausted == 0 &&
           attempt_limit_exhausted == 0 && not_admitted == 0;
  }
  if (config.terminal_repair_mode == "budget_exhaustion") {
    return retransmissions == 0 && budget_exhausted >= 1 &&
           attempt_limit_exhausted == 0 && not_admitted == 0;
  }
  if (config.terminal_repair_mode == "attempt_limit") {
    return retransmissions == 1 && budget_exhausted == 0 &&
           attempt_limit_exhausted >= 1 && not_admitted == 0;
  }
  if (config.terminal_repair_mode == "admission_rejection") {
    return retransmissions == 0 && budget_exhausted == 0 &&
           attempt_limit_exhausted == 0 && not_admitted >= 1;
  }
  return false;
}

rmw_ret_t wait_event_once(
  rmw_context_t * context,
  rmw_event_t * event,
  bool * ready)
{
  if (context == nullptr || event == nullptr || ready == nullptr) {
    return RMW_RET_INVALID_ARGUMENT;
  }
  rmw_wait_set_t * wait_set = rmw_create_wait_set(context, 1);
  if (wait_set == nullptr) {
    return RMW_RET_ERROR;
  }
  rmw_time_t timeout{};
  void * handles[1] = {event};
  rmw_events_t events{1, handles};
  const rmw_ret_t wait_ret =
    rmw_wait(nullptr, nullptr, nullptr, nullptr, &events, wait_set, &timeout);
  *ready = handles[0] != nullptr;
  const rmw_ret_t destroy_ret = rmw_destroy_wait_set(wait_set);
  if (wait_ret != RMW_RET_OK && wait_ret != RMW_RET_TIMEOUT) {
    return wait_ret;
  }
  return destroy_ret == RMW_RET_OK ? wait_ret : destroy_ret;
}

void print_result(
  const Config & config,
  const char * status,
  const std::vector<std::string> & payloads,
  bool event_ready,
  bool event_taken,
  const rmw_message_lost_status_t & event_status,
  const CallbackState & callback)
{
  std::cout << "{\"schema_version\":\"fleetrmw.message_lost_interprocess_probe.v1\",";
  std::cout << "\"status\":\"" << status << "\",";
  std::cout << "\"mode\":\"" << config.mode << "\",";
  std::cout << "\"terminal_repair_mode\":\"" << config.terminal_repair_mode << "\",";
  std::cout << "\"publisher_depth\":" << std::max(config.publisher_depth, 1) << ",";
  std::cout << "\"message_lost_wait_ready\":" << (event_ready ? "true" : "false") << ",";
  std::cout << "\"message_lost_taken\":" << (event_taken ? "true" : "false") << ",";
  std::cout << "\"message_lost_total_count\":" << event_status.total_count << ",";
  std::cout << "\"message_lost_total_count_change\":" <<
    event_status.total_count_change << ",";
  std::cout << "\"message_lost_callback_calls\":" << callback.calls << ",";
  std::cout << "\"message_lost_callback_events\":" << callback.events << ",";
  std::cout << "\"ack_nack_sent\":" << rmw_fleetqox_cpp_socket_ack_nack_sent() << ",";
  std::cout << "\"ack_nack_received\":" << rmw_fleetqox_cpp_socket_ack_nack_received() << ",";
  std::cout << "\"nack_retransmissions\":" <<
    rmw_fleetqox_cpp_socket_nack_retransmissions() << ",";
  std::cout << "\"repair_budget_exhausted\":" <<
    rmw_fleetqox_cpp_socket_repair_budget_exhausted() << ",";
  std::cout << "\"repair_sequence_attempt_limit_exhausted\":" <<
    rmw_fleetqox_cpp_socket_repair_sequence_attempt_limit_exhausted() << ",";
  std::cout << "\"repair_not_admitted\":" <<
    rmw_fleetqox_cpp_socket_repair_not_admitted() << ",";
  std::cout << "\"test_dropped_frames\":" <<
    rmw_fleetqox_cpp_socket_test_dropped_frames() << ",";
  std::cout << "\"unrecoverable_loss_notices_sent\":" <<
    rmw_fleetqox_cpp_socket_unrecoverable_loss_notices_sent() << ",";
  std::cout << "\"unrecoverable_loss_notices_received\":" <<
    rmw_fleetqox_cpp_socket_unrecoverable_loss_notices_received() << ",";
  std::cout << "\"unrecoverable_loss_samples_reported\":" <<
    rmw_fleetqox_cpp_unrecoverable_loss_samples_reported() << ",";
  std::cout << "\"payloads\":[";
  for (size_t index = 0; index < payloads.size(); ++index) {
    if (index > 0) {
      std::cout << ",";
    }
    std::cout << "\"" << payloads[index] << "\"";
  }
  std::cout << "]}" << std::endl;
}

int run_publisher(const Config & config)
{
  rcutils_allocator_t allocator = rcutils_get_default_allocator();
  rmw_init_options_t options{};
  rmw_context_t context{};
  if (!init_context(allocator, &options, &context)) {
    return 1;
  }
  rmw_node_t * node = rmw_create_node(&context, "message_lost_remote_publisher", "/fleetqox");
  rosidl_message_type_support_t type_support{};
  type_support.typesupport_identifier = "rmw_fleetqox_cpp_message_lost_interprocess_probe";
  rmw_qos_profile_t qos = rmw_qos_profile_default;
  qos.reliability = RMW_QOS_POLICY_RELIABILITY_RELIABLE;
  qos.history = RMW_QOS_POLICY_HISTORY_KEEP_LAST;
  qos.depth = static_cast<size_t>(std::max(config.publisher_depth, 1));
  rmw_publisher_options_t publisher_options = rmw_get_default_publisher_options();
  rmw_publisher_t * publisher = node == nullptr ? nullptr :
    rmw_create_publisher(
    node, &type_support, config.topic.c_str(), &qos, &publisher_options);
  std::this_thread::sleep_for(
    std::chrono::milliseconds(std::max(config.pre_publish_wait_ms, 0)));

  bool publish_ok = publisher != nullptr;
  const std::vector<std::string> payloads{"remote-one", "remote-two", "remote-three", "remote-four"};
  for (const std::string & payload : payloads) {
    rmw_serialized_message_t message = rmw_get_zero_initialized_serialized_message();
    const bool initialized = init_message(&message, payload, &allocator);
    publish_ok = initialized && publisher != nullptr &&
      rmw_publish_serialized_message(publisher, &message, nullptr) == RMW_RET_OK && publish_ok;
    if (initialized) {
      const rmw_ret_t fini_ret = rmw_serialized_message_fini(&message);
      publish_ok = fini_ret == RMW_RET_OK && publish_ok;
    }
    std::this_thread::sleep_for(
      std::chrono::milliseconds(std::max(config.publish_interval_ms, 0)));
  }
  const auto deadline = std::chrono::steady_clock::now() +
    std::chrono::milliseconds(std::max(config.timeout_ms, 0));
  while (rmw_fleetqox_cpp_socket_unrecoverable_loss_notices_sent() == 0 &&
    std::chrono::steady_clock::now() < deadline)
  {
    std::this_thread::sleep_for(std::chrono::milliseconds(2));
  }
  std::this_thread::sleep_for(std::chrono::milliseconds(200));
  const bool behavior_ok = publish_ok && terminal_repair_mode_valid(
    config.terminal_repair_mode) && terminal_repair_control_observed(config) &&
    rmw_fleetqox_cpp_socket_test_dropped_frames() == expected_dropped_frame_count(config) &&
    rmw_fleetqox_cpp_socket_unrecoverable_loss_notices_sent() >= 1;
  const rmw_message_lost_status_t empty_status{};
  const CallbackState empty_callback{};

  bool teardown_ok = true;
  if (publisher != nullptr) {
    teardown_ok = rmw_destroy_publisher(node, publisher) == RMW_RET_OK && teardown_ok;
  }
  if (node != nullptr) {
    teardown_ok = rmw_destroy_node(node) == RMW_RET_OK && teardown_ok;
  }
  teardown_ok = cleanup_context(&context, &options) && teardown_ok;
  const bool ok = behavior_ok && teardown_ok;
  print_result(config, ok ? "ok" : "failed", payloads, false, false, empty_status, empty_callback);
  return ok ? 0 : 1;
}

int run_subscriber(const Config & config)
{
  rcutils_allocator_t allocator = rcutils_get_default_allocator();
  rmw_init_options_t options{};
  rmw_context_t context{};
  if (!init_context(allocator, &options, &context)) {
    return 1;
  }
  rmw_node_t * node = rmw_create_node(&context, "message_lost_remote_subscriber", "/fleetqox");
  rosidl_message_type_support_t type_support{};
  type_support.typesupport_identifier = "rmw_fleetqox_cpp_message_lost_interprocess_probe";
  rmw_qos_profile_t qos = rmw_qos_profile_default;
  qos.reliability = RMW_QOS_POLICY_RELIABILITY_RELIABLE;
  qos.history = RMW_QOS_POLICY_HISTORY_KEEP_LAST;
  qos.depth = 16;
  rmw_subscription_options_t subscription_options = rmw_get_default_subscription_options();
  rmw_subscription_t * subscription = node == nullptr ? nullptr :
    rmw_create_subscription(
    node, &type_support, config.topic.c_str(), &qos, &subscription_options);
  rmw_event_t event = rmw_get_zero_initialized_event();
  const rmw_ret_t event_init_ret = subscription == nullptr ? RMW_RET_ERROR :
    rmw_subscription_event_init(&event, subscription, RMW_EVENT_MESSAGE_LOST);
  CallbackState callback{};
  const rmw_ret_t callback_ret = event_init_ret == RMW_RET_OK ?
    rmw_event_set_callback(&event, event_callback, &callback) : RMW_RET_ERROR;
  bool initial_ready = true;
  const rmw_ret_t initial_wait_ret = event_init_ret == RMW_RET_OK ?
    wait_event_once(&context, &event, &initial_ready) : RMW_RET_ERROR;

  rmw_serialized_message_t incoming = rmw_get_zero_initialized_serialized_message();
  const bool message_ok = rmw_serialized_message_init(&incoming, 1, &allocator) == RMW_RET_OK;
  std::vector<std::string> payloads;
  bool event_ready = false;
  rmw_ret_t wait_ret = RMW_RET_TIMEOUT;
  rmw_ret_t take_ret = RMW_RET_OK;
  const auto deadline = std::chrono::steady_clock::now() +
    std::chrono::milliseconds(std::max(config.timeout_ms, 0));
  while (subscription != nullptr && message_ok && std::chrono::steady_clock::now() < deadline) {
    bool taken = false;
    take_ret = rmw_take_serialized_message(subscription, &incoming, &taken, nullptr);
    if (take_ret != RMW_RET_OK) {
      break;
    }
    if (taken) {
      payloads.push_back(message_string(incoming));
    }
    if (!event_ready) {
      wait_ret = wait_event_once(&context, &event, &event_ready);
      if (wait_ret != RMW_RET_OK && wait_ret != RMW_RET_TIMEOUT) {
        break;
      }
    }
    if (event_ready && payloads.size() >= 3) {
      break;
    }
    std::this_thread::sleep_for(std::chrono::milliseconds(1));
  }
  if (event_ready && payloads.size() >= 3) {
    // Keep the receiver alive long enough for the immediate and idle NACK
    // responses to arrive; duplicate notices must not increment the event.
    std::this_thread::sleep_for(std::chrono::milliseconds(250));
  }
  rmw_message_lost_status_t event_status{};
  bool event_taken = false;
  const rmw_ret_t event_take_ret = event_init_ret == RMW_RET_OK ?
    rmw_take_event(&event, &event_status, &event_taken) : RMW_RET_ERROR;
  const bool behavior_ok =
    event_init_ret == RMW_RET_OK && callback_ret == RMW_RET_OK &&
    initial_wait_ret == RMW_RET_TIMEOUT && !initial_ready &&
    take_ret == RMW_RET_OK && wait_ret == RMW_RET_OK && event_ready &&
    event_take_ret == RMW_RET_OK && event_taken &&
    event_status.total_count == 1 && event_status.total_count_change == 1 &&
    callback.calls >= 1 && callback.events == 1 &&
    payloads.size() == 3 && contains(payloads, "remote-one") &&
    contains(payloads, "remote-two") && !contains(payloads, "remote-three") &&
    contains(payloads, "remote-four") &&
    rmw_fleetqox_cpp_socket_unrecoverable_loss_notices_received() >= 1 &&
    rmw_fleetqox_cpp_unrecoverable_loss_samples_reported() == 1;

  bool teardown_ok = true;
  if (message_ok) {
    teardown_ok = rmw_serialized_message_fini(&incoming) == RMW_RET_OK && teardown_ok;
  }
  if (event_init_ret == RMW_RET_OK) {
    teardown_ok = rmw_event_fini(&event) == RMW_RET_OK && teardown_ok;
  }
  if (subscription != nullptr) {
    teardown_ok = rmw_destroy_subscription(node, subscription) == RMW_RET_OK && teardown_ok;
  }
  if (node != nullptr) {
    teardown_ok = rmw_destroy_node(node) == RMW_RET_OK && teardown_ok;
  }
  teardown_ok = cleanup_context(&context, &options) && teardown_ok;
  const bool ok = behavior_ok && teardown_ok;
  print_result(
    config, ok ? "ok" : "failed", payloads, event_ready, event_taken, event_status, callback);
  return ok ? 0 : 1;
}

}  // namespace

int main(int argc, char ** argv)
{
  const Config config = parse_args(argc, argv);
  if (config.mode == "publisher") {
    return run_publisher(config);
  }
  if (config.mode == "subscriber") {
    return run_subscriber(config);
  }
  return 1;
}

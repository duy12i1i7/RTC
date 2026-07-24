#include <algorithm>
#include <chrono>
#include <cstdint>
#include <cstdlib>
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

extern "C" std::uint64_t rmw_fleetqox_cpp_socket_data_frames_received();
extern "C" std::uint64_t rmw_fleetqox_cpp_socket_unrecoverable_loss_notices_sent();
extern "C" std::uint64_t rmw_fleetqox_cpp_socket_unrecoverable_loss_notices_received();
extern "C" std::uint64_t rmw_fleetqox_cpp_unrecoverable_loss_samples_reported();
extern "C" std::uint64_t rmw_fleetqox_cpp_qos_events_initialized();
extern "C" std::uint64_t rmw_fleetqox_cpp_qos_events_finalized();
extern "C" std::uint64_t rmw_fleetqox_cpp_qos_event_callbacks_set();

namespace
{

struct CallbackState
{
  std::uint64_t calls;
  std::uint64_t events;
};

void event_callback(const void * user_data, size_t number_of_events)
{
  auto * state = const_cast<CallbackState *>(static_cast<const CallbackState *>(user_data));
  if (state != nullptr) {
    ++state->calls;
    state->events += number_of_events;
  }
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

std::string serialized_message_string(const rmw_serialized_message_t & message)
{
  if (message.buffer == nullptr || message.buffer_length == 0) {
    return "";
  }
  return std::string(
    reinterpret_cast<const char *>(message.buffer),
    reinterpret_cast<const char *>(message.buffer + message.buffer_length));
}

bool wait_for_received_frames(std::uint64_t baseline, std::uint64_t expected_delta)
{
  for (int attempt = 0; attempt < 1000; ++attempt) {
    if (rmw_fleetqox_cpp_socket_data_frames_received() >= baseline + expected_delta) {
      return true;
    }
    std::this_thread::sleep_for(std::chrono::milliseconds(1));
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
  rmw_time_t zero_timeout{};
  void * event_handles[1] = {event};
  rmw_events_t events{1, event_handles};
  const rmw_ret_t wait_ret =
    rmw_wait(nullptr, nullptr, nullptr, nullptr, &events, wait_set, &zero_timeout);
  *ready = event_handles[0] != nullptr;
  const rmw_ret_t destroy_ret = rmw_destroy_wait_set(wait_set);
  if (wait_ret != RMW_RET_OK && wait_ret != RMW_RET_TIMEOUT) {
    return wait_ret;
  }
  return destroy_ret == RMW_RET_OK ? wait_ret : destroy_ret;
}

rmw_ret_t wait_for_event_ready(
  rmw_context_t * context,
  rmw_event_t * event,
  int timeout_ms,
  bool * ready)
{
  if (ready == nullptr) {
    return RMW_RET_INVALID_ARGUMENT;
  }
  *ready = false;
  const auto deadline =
    std::chrono::steady_clock::now() + std::chrono::milliseconds(std::max(0, timeout_ms));
  do {
    const rmw_ret_t ret = wait_event_once(context, event, ready);
    if (ret == RMW_RET_OK && *ready) {
      return RMW_RET_OK;
    }
    if (ret != RMW_RET_TIMEOUT) {
      return ret;
    }
    std::this_thread::sleep_for(std::chrono::milliseconds(1));
  } while (std::chrono::steady_clock::now() < deadline);
  return RMW_RET_TIMEOUT;
}

int configured_gap_grace_ms()
{
  const char * value = std::getenv("FLEETQOX_RMW_MESSAGE_LOST_GAP_GRACE_MS");
  if (value == nullptr || value[0] == '\0') {
    return 25;
  }
  char * end = nullptr;
  const long parsed = std::strtol(value, &end, 10);
  if (end == value || *end != '\0' || parsed < 0) {
    return 25;
  }
  return static_cast<int>(std::min<long>(parsed, 60000));
}

rmw_ret_t publish_text(
  const rmw_publisher_t * publisher,
  const std::string & payload,
  rcutils_allocator_t * allocator)
{
  if (publisher == nullptr || allocator == nullptr) {
    return RMW_RET_INVALID_ARGUMENT;
  }
  rmw_serialized_message_t message = rmw_get_zero_initialized_serialized_message();
  if (!init_serialized_message(&message, payload, allocator)) {
    return RMW_RET_BAD_ALLOC;
  }
  const rmw_ret_t publish_ret = rmw_publish_serialized_message(publisher, &message, nullptr);
  const rmw_ret_t fini_ret = rmw_serialized_message_fini(&message);
  return publish_ret == RMW_RET_OK ? fini_ret : publish_ret;
}

bool drain_payloads(
  const rmw_subscription_t * subscription,
  rcutils_allocator_t * allocator,
  std::vector<std::string> * payloads)
{
  if (subscription == nullptr || allocator == nullptr || payloads == nullptr) {
    return false;
  }
  rmw_serialized_message_t incoming = rmw_get_zero_initialized_serialized_message();
  if (rmw_serialized_message_init(&incoming, 1, allocator) != RMW_RET_OK) {
    return false;
  }
  bool ok = true;
  for (int attempt = 0; attempt < 32; ++attempt) {
    bool taken = false;
    const rmw_ret_t take_ret =
      rmw_take_serialized_message(subscription, &incoming, &taken, nullptr);
    if (take_ret != RMW_RET_OK) {
      ok = false;
      break;
    }
    if (!taken) {
      break;
    }
    payloads->push_back(serialized_message_string(incoming));
  }
  return rmw_serialized_message_fini(&incoming) == RMW_RET_OK && ok;
}

bool contains_payload(const std::vector<std::string> & payloads, const std::string & expected)
{
  return std::find(payloads.begin(), payloads.end(), expected) != payloads.end();
}

}  // namespace

int main()
{
  if (std::getenv("FLEETQOX_RMW_DROP_SOURCE_SEQUENCES") == nullptr) {
    setenv("FLEETQOX_RMW_DROP_SOURCE_SEQUENCES", "3", 0);
  }
  if (std::getenv("FLEETQOX_RMW_MESSAGE_LOST_GAP_GRACE_MS") == nullptr) {
    setenv("FLEETQOX_RMW_MESSAGE_LOST_GAP_GRACE_MS", "100", 0);
  }
  rcutils_allocator_t allocator = rcutils_get_default_allocator();
  rmw_init_options_t options = rmw_get_zero_initialized_init_options();
  rmw_ret_t ret = rmw_init_options_init(&options, allocator);
  if (ret != RMW_RET_OK) {
    std::cout << "{\"status\":\"init_options_failed\",\"ret\":" << ret << "}\n";
    return 1;
  }
  options.instance_id = 60;

  rmw_context_t context = rmw_get_zero_initialized_context();
  ret = rmw_init(&options, &context);
  if (ret != RMW_RET_OK) {
    const rmw_ret_t fini_ret = rmw_init_options_fini(&options);
    (void)fini_ret;
    std::cout << "{\"status\":\"init_failed\",\"ret\":" << ret << "}\n";
    return 1;
  }

  rmw_node_t * node =
    rmw_create_node(&context, "fleetqox_message_lost_event_probe", "/fleetqox");
  if (node == nullptr) {
    cleanup_context(&context, &options);
    std::cout << "{\"status\":\"create_node_failed\"}\n";
    return 1;
  }

  rosidl_message_type_support_t type_support{};
  type_support.typesupport_identifier = "rmw_fleetqox_cpp_message_lost_event_probe";
  rmw_qos_profile_t qos = rmw_qos_profile_default;
  qos.history = RMW_QOS_POLICY_HISTORY_KEEP_LAST;
  qos.depth = 1;
  rmw_publisher_options_t publisher_options = rmw_get_default_publisher_options();
  rmw_subscription_options_t subscription_options = rmw_get_default_subscription_options();

  const bool message_lost_supported = rmw_event_type_is_supported(RMW_EVENT_MESSAGE_LOST);
  const std::uint64_t events_init_before = rmw_fleetqox_cpp_qos_events_initialized();
  const std::uint64_t events_fini_before = rmw_fleetqox_cpp_qos_events_finalized();
  const std::uint64_t callbacks_before = rmw_fleetqox_cpp_qos_event_callbacks_set();

  const char * topic = "/fleetqox/message_lost_event_probe";
  rmw_publisher_t * publisher =
    rmw_create_publisher(node, &type_support, topic, &qos, &publisher_options);
  rmw_subscription_t * subscription =
    rmw_create_subscription(node, &type_support, topic, &qos, &subscription_options);
  rmw_event_t event = rmw_get_zero_initialized_event();
  const rmw_ret_t event_init_ret = subscription == nullptr ?
    RMW_RET_ERROR :
    rmw_subscription_event_init(&event, subscription, RMW_EVENT_MESSAGE_LOST);
  CallbackState callback_state{0, 0};
  const rmw_ret_t callback_ret =
    rmw_event_set_callback(&event, event_callback, &callback_state);

  bool initial_ready = true;
  const rmw_ret_t initial_wait_ret = wait_event_once(&context, &event, &initial_ready);
  rmw_message_lost_status_t initial_status{};
  bool initial_taken = true;
  const rmw_ret_t initial_take_ret =
    rmw_take_event(&event, &initial_status, &initial_taken);

  rmw_serialized_message_t first = rmw_get_zero_initialized_serialized_message();
  rmw_serialized_message_t second = rmw_get_zero_initialized_serialized_message();
  rmw_serialized_message_t incoming = rmw_get_zero_initialized_serialized_message();
  const bool serialized_init_ok =
    init_serialized_message(&first, "first", &allocator) &&
    init_serialized_message(&second, "second", &allocator) &&
    rmw_serialized_message_init(&incoming, 1, &allocator) == RMW_RET_OK;

  const std::uint64_t received_before = rmw_fleetqox_cpp_socket_data_frames_received();
  const rmw_ret_t publish_first_ret =
    serialized_init_ok && publisher != nullptr ?
    rmw_publish_serialized_message(publisher, &first, nullptr) : RMW_RET_ERROR;
  const rmw_ret_t publish_second_ret =
    serialized_init_ok && publisher != nullptr ?
    rmw_publish_serialized_message(publisher, &second, nullptr) : RMW_RET_ERROR;
  const bool received_ready = wait_for_received_frames(received_before, 2);

  bool wait_ready = false;
  const rmw_ret_t wait_ret = wait_event_once(&context, &event, &wait_ready);
  rmw_message_lost_status_t status{};
  bool taken = false;
  const rmw_ret_t take_ret = rmw_take_event(&event, &status, &taken);

  bool payload_taken = false;
  const rmw_ret_t payload_take_ret =
    subscription == nullptr ?
    RMW_RET_ERROR :
    rmw_take_serialized_message(subscription, &incoming, &payload_taken, nullptr);
  bool second_payload_taken = false;
  const rmw_ret_t second_payload_take_ret =
    subscription == nullptr ?
    RMW_RET_ERROR :
    rmw_take_serialized_message(subscription, &incoming, &second_payload_taken, nullptr);
  const std::string received_payload = serialized_message_string(incoming);

  bool after_clear_ready = true;
  const rmw_ret_t after_clear_wait_ret = wait_event_once(&context, &event, &after_clear_ready);
  rmw_message_lost_status_t after_clear_status{};
  bool after_clear_taken = true;
  const rmw_ret_t after_clear_take_ret =
    rmw_take_event(&event, &after_clear_status, &after_clear_taken);

  rmw_qos_profile_t best_effort_qos = rmw_qos_profile_default;
  best_effort_qos.reliability = RMW_QOS_POLICY_RELIABILITY_BEST_EFFORT;
  best_effort_qos.history = RMW_QOS_POLICY_HISTORY_KEEP_LAST;
  best_effort_qos.depth = 16;
  const char * gap_topic = "/fleetqox/message_lost_best_effort_gap_probe";
  rmw_publisher_t * gap_publisher =
    rmw_create_publisher(node, &type_support, gap_topic, &best_effort_qos, &publisher_options);
  rmw_subscription_t * gap_subscription =
    rmw_create_subscription(node, &type_support, gap_topic, &best_effort_qos, &subscription_options);
  rmw_event_t gap_event = rmw_get_zero_initialized_event();
  const rmw_ret_t gap_event_init_ret = gap_subscription == nullptr ?
    RMW_RET_ERROR :
    rmw_subscription_event_init(&gap_event, gap_subscription, RMW_EVENT_MESSAGE_LOST);
  CallbackState gap_callback_state{0, 0};
  const rmw_ret_t gap_callback_ret = gap_event_init_ret == RMW_RET_OK ?
    rmw_event_set_callback(&gap_event, event_callback, &gap_callback_state) :
    RMW_RET_ERROR;
  bool gap_initial_ready = true;
  const rmw_ret_t gap_initial_wait_ret = gap_event_init_ret == RMW_RET_OK ?
    wait_event_once(&context, &gap_event, &gap_initial_ready) :
    RMW_RET_ERROR;

  const std::uint64_t gap_received_before = rmw_fleetqox_cpp_socket_data_frames_received();
  bool gap_publish_ok = gap_publisher != nullptr;
  for (const std::string & payload :
    std::vector<std::string>{"gap-one", "gap-two", "gap-three", "gap-four"})
  {
    gap_publish_ok =
      publish_text(gap_publisher, payload, &allocator) == RMW_RET_OK && gap_publish_ok;
  }
  const bool gap_received_ready = wait_for_received_frames(gap_received_before, 3);
  const std::uint64_t gap_received_delta =
    rmw_fleetqox_cpp_socket_data_frames_received() - gap_received_before;
  bool gap_wait_ready = false;
  const rmw_ret_t gap_wait_ret = gap_event_init_ret == RMW_RET_OK ?
    wait_for_event_ready(
      &context, &gap_event, configured_gap_grace_ms() + 1000, &gap_wait_ready) :
    RMW_RET_ERROR;
  rmw_message_lost_status_t gap_status{};
  bool gap_taken = false;
  const rmw_ret_t gap_take_ret = gap_event_init_ret == RMW_RET_OK ?
    rmw_take_event(&gap_event, &gap_status, &gap_taken) :
    RMW_RET_ERROR;
  std::vector<std::string> gap_payloads;
  const bool gap_payloads_drained =
    drain_payloads(gap_subscription, &allocator, &gap_payloads);
  bool gap_after_clear_ready = true;
  const rmw_ret_t gap_after_clear_wait_ret = gap_event_init_ret == RMW_RET_OK ?
    wait_event_once(&context, &gap_event, &gap_after_clear_ready) :
    RMW_RET_ERROR;

  rmw_qos_profile_t reliable_qos = rmw_qos_profile_default;
  reliable_qos.reliability = RMW_QOS_POLICY_RELIABILITY_RELIABLE;
  reliable_qos.history = RMW_QOS_POLICY_HISTORY_KEEP_LAST;
  reliable_qos.depth = 16;
  const char * repair_topic = "/fleetqox/message_lost_repair_suppression_probe";
  rmw_publisher_t * repair_publisher =
    rmw_create_publisher(node, &type_support, repair_topic, &reliable_qos, &publisher_options);
  rmw_subscription_t * repair_reliable_subscription =
    rmw_create_subscription(
    node, &type_support, repair_topic, &reliable_qos, &subscription_options);
  rmw_subscription_t * repair_observer_subscription =
    rmw_create_subscription(
    node, &type_support, repair_topic, &best_effort_qos, &subscription_options);
  rmw_event_t repair_observer_event = rmw_get_zero_initialized_event();
  const rmw_ret_t repair_event_init_ret = repair_observer_subscription == nullptr ?
    RMW_RET_ERROR :
    rmw_subscription_event_init(
    &repair_observer_event, repair_observer_subscription, RMW_EVENT_MESSAGE_LOST);
  CallbackState repair_callback_state{0, 0};
  const rmw_ret_t repair_callback_ret = repair_event_init_ret == RMW_RET_OK ?
    rmw_event_set_callback(
    &repair_observer_event, event_callback, &repair_callback_state) :
    RMW_RET_ERROR;
  bool repair_initial_ready = true;
  const rmw_ret_t repair_initial_wait_ret = repair_event_init_ret == RMW_RET_OK ?
    wait_event_once(&context, &repair_observer_event, &repair_initial_ready) :
    RMW_RET_ERROR;

  const std::uint64_t repair_received_before = rmw_fleetqox_cpp_socket_data_frames_received();
  bool repair_publish_ok = repair_publisher != nullptr;
  for (const std::string & payload :
    std::vector<std::string>{"repair-one", "repair-two", "repair-three", "repair-four"})
  {
    repair_publish_ok =
      publish_text(repair_publisher, payload, &allocator) == RMW_RET_OK && repair_publish_ok;
  }
  const bool repair_received_ready = wait_for_received_frames(repair_received_before, 4);
  std::this_thread::sleep_for(
    std::chrono::milliseconds(configured_gap_grace_ms() + 50));
  const std::uint64_t repair_received_delta =
    rmw_fleetqox_cpp_socket_data_frames_received() - repair_received_before;
  bool repair_wait_ready = true;
  const rmw_ret_t repair_wait_ret = repair_event_init_ret == RMW_RET_OK ?
    wait_event_once(&context, &repair_observer_event, &repair_wait_ready) :
    RMW_RET_ERROR;
  rmw_message_lost_status_t repair_status{};
  bool repair_taken = true;
  const rmw_ret_t repair_take_ret = repair_event_init_ret == RMW_RET_OK ?
    rmw_take_event(&repair_observer_event, &repair_status, &repair_taken) :
    RMW_RET_ERROR;
  std::vector<std::string> repair_observer_payloads;
  std::vector<std::string> repair_reliable_payloads;
  const bool repair_observer_payloads_drained =
    drain_payloads(
    repair_observer_subscription, &allocator, &repair_observer_payloads);
  const bool repair_reliable_payloads_drained =
    drain_payloads(
    repair_reliable_subscription, &allocator, &repair_reliable_payloads);

  rmw_qos_profile_t exhausted_writer_qos = reliable_qos;
  exhausted_writer_qos.depth = 1;
  const char * exhausted_topic = "/fleetqox/message_lost_writer_history_exhausted_probe";
  rmw_publisher_t * exhausted_publisher = rmw_create_publisher(
    node, &type_support, exhausted_topic, &exhausted_writer_qos, &publisher_options);
  rmw_subscription_t * exhausted_subscription = rmw_create_subscription(
    node, &type_support, exhausted_topic, &reliable_qos, &subscription_options);
  rmw_event_t exhausted_event = rmw_get_zero_initialized_event();
  const rmw_ret_t exhausted_event_init_ret = exhausted_subscription == nullptr ?
    RMW_RET_ERROR :
    rmw_subscription_event_init(
    &exhausted_event, exhausted_subscription, RMW_EVENT_MESSAGE_LOST);
  CallbackState exhausted_callback_state{0, 0};
  const rmw_ret_t exhausted_callback_ret = exhausted_event_init_ret == RMW_RET_OK ?
    rmw_event_set_callback(&exhausted_event, event_callback, &exhausted_callback_state) :
    RMW_RET_ERROR;
  bool exhausted_initial_ready = true;
  const rmw_ret_t exhausted_initial_wait_ret = exhausted_event_init_ret == RMW_RET_OK ?
    wait_event_once(&context, &exhausted_event, &exhausted_initial_ready) :
    RMW_RET_ERROR;

  const std::uint64_t exhausted_received_before =
    rmw_fleetqox_cpp_socket_data_frames_received();
  const std::uint64_t loss_notices_sent_before =
    rmw_fleetqox_cpp_socket_unrecoverable_loss_notices_sent();
  const std::uint64_t loss_notices_received_before =
    rmw_fleetqox_cpp_socket_unrecoverable_loss_notices_received();
  const std::uint64_t loss_samples_reported_before =
    rmw_fleetqox_cpp_unrecoverable_loss_samples_reported();
  bool exhausted_publish_ok = exhausted_publisher != nullptr;
  for (const std::string & payload :
    std::vector<std::string>{
      "exhausted-one", "exhausted-two", "exhausted-three", "exhausted-four"})
  {
    exhausted_publish_ok =
      publish_text(exhausted_publisher, payload, &allocator) == RMW_RET_OK &&
      exhausted_publish_ok;
  }
  const bool exhausted_received_ready =
    wait_for_received_frames(exhausted_received_before, 3);
  bool exhausted_wait_ready = false;
  const rmw_ret_t exhausted_wait_ret = exhausted_event_init_ret == RMW_RET_OK ?
    wait_for_event_ready(&context, &exhausted_event, 1000, &exhausted_wait_ready) :
    RMW_RET_ERROR;
  const std::uint64_t exhausted_received_delta =
    rmw_fleetqox_cpp_socket_data_frames_received() - exhausted_received_before;
  const std::uint64_t loss_notices_sent_delta =
    rmw_fleetqox_cpp_socket_unrecoverable_loss_notices_sent() - loss_notices_sent_before;
  const std::uint64_t loss_notices_received_delta =
    rmw_fleetqox_cpp_socket_unrecoverable_loss_notices_received() -
    loss_notices_received_before;
  const std::uint64_t loss_samples_reported_delta =
    rmw_fleetqox_cpp_unrecoverable_loss_samples_reported() - loss_samples_reported_before;
  rmw_message_lost_status_t exhausted_status{};
  bool exhausted_taken = false;
  const rmw_ret_t exhausted_take_ret = exhausted_event_init_ret == RMW_RET_OK ?
    rmw_take_event(&exhausted_event, &exhausted_status, &exhausted_taken) :
    RMW_RET_ERROR;
  std::vector<std::string> exhausted_payloads;
  const bool exhausted_payloads_drained =
    drain_payloads(exhausted_subscription, &allocator, &exhausted_payloads);
  bool exhausted_after_clear_ready = true;
  const rmw_ret_t exhausted_after_clear_wait_ret = exhausted_event_init_ret == RMW_RET_OK ?
    wait_event_once(&context, &exhausted_event, &exhausted_after_clear_ready) :
    RMW_RET_ERROR;

  const rmw_ret_t first_fini_ret = rmw_serialized_message_fini(&first);
  const rmw_ret_t second_fini_ret = rmw_serialized_message_fini(&second);
  const rmw_ret_t incoming_fini_ret = rmw_serialized_message_fini(&incoming);
  const rmw_ret_t event_fini_ret = rmw_event_fini(&event);
  const rmw_ret_t gap_event_fini_ret = rmw_event_fini(&gap_event);
  const rmw_ret_t repair_event_fini_ret = rmw_event_fini(&repair_observer_event);
  const rmw_ret_t exhausted_event_fini_ret = rmw_event_fini(&exhausted_event);
  const rmw_ret_t destroy_publisher_ret =
    publisher == nullptr ? RMW_RET_ERROR : rmw_destroy_publisher(node, publisher);
  const rmw_ret_t destroy_subscription_ret =
    subscription == nullptr ? RMW_RET_ERROR : rmw_destroy_subscription(node, subscription);
  const rmw_ret_t destroy_gap_publisher_ret = gap_publisher == nullptr ?
    RMW_RET_ERROR : rmw_destroy_publisher(node, gap_publisher);
  const rmw_ret_t destroy_gap_subscription_ret = gap_subscription == nullptr ?
    RMW_RET_ERROR : rmw_destroy_subscription(node, gap_subscription);
  const rmw_ret_t destroy_repair_publisher_ret = repair_publisher == nullptr ?
    RMW_RET_ERROR : rmw_destroy_publisher(node, repair_publisher);
  const rmw_ret_t destroy_repair_reliable_subscription_ret =
    repair_reliable_subscription == nullptr ?
    RMW_RET_ERROR : rmw_destroy_subscription(node, repair_reliable_subscription);
  const rmw_ret_t destroy_repair_observer_subscription_ret =
    repair_observer_subscription == nullptr ?
    RMW_RET_ERROR : rmw_destroy_subscription(node, repair_observer_subscription);
  const rmw_ret_t destroy_exhausted_publisher_ret = exhausted_publisher == nullptr ?
    RMW_RET_ERROR : rmw_destroy_publisher(node, exhausted_publisher);
  const rmw_ret_t destroy_exhausted_subscription_ret = exhausted_subscription == nullptr ?
    RMW_RET_ERROR : rmw_destroy_subscription(node, exhausted_subscription);
  const rmw_ret_t destroy_node_ret = rmw_destroy_node(node);
  cleanup_context(&context, &options);

  const std::uint64_t events_init_delta =
    rmw_fleetqox_cpp_qos_events_initialized() - events_init_before;
  const std::uint64_t events_fini_delta =
    rmw_fleetqox_cpp_qos_events_finalized() - events_fini_before;
  const std::uint64_t callbacks_delta =
    rmw_fleetqox_cpp_qos_event_callbacks_set() - callbacks_before;

  const bool event_ok =
    message_lost_supported &&
    event_init_ret == RMW_RET_OK &&
    callback_ret == RMW_RET_OK &&
    initial_wait_ret == RMW_RET_TIMEOUT &&
    !initial_ready &&
    initial_take_ret == RMW_RET_OK &&
    !initial_taken &&
    publish_first_ret == RMW_RET_OK &&
    publish_second_ret == RMW_RET_OK &&
    received_ready &&
    wait_ret == RMW_RET_OK &&
    wait_ready &&
    take_ret == RMW_RET_OK &&
    taken &&
    status.total_count == 1 &&
    status.total_count_change == 1 &&
    callback_state.calls >= 1 &&
    callback_state.events >= 1 &&
    payload_take_ret == RMW_RET_OK &&
    payload_taken &&
    received_payload == "second" &&
    second_payload_take_ret == RMW_RET_OK &&
    !second_payload_taken &&
    after_clear_wait_ret == RMW_RET_TIMEOUT &&
    !after_clear_ready &&
    after_clear_take_ret == RMW_RET_OK &&
    !after_clear_taken &&
    after_clear_status.total_count == status.total_count &&
    after_clear_status.total_count_change == 0;
  const bool best_effort_gap_ok =
    gap_event_init_ret == RMW_RET_OK &&
    gap_callback_ret == RMW_RET_OK &&
    gap_initial_wait_ret == RMW_RET_TIMEOUT &&
    !gap_initial_ready &&
    gap_publish_ok &&
    gap_received_ready &&
    gap_received_delta == 3 &&
    gap_wait_ret == RMW_RET_OK &&
    gap_wait_ready &&
    gap_take_ret == RMW_RET_OK &&
    gap_taken &&
    gap_status.total_count == 1 &&
    gap_status.total_count_change == 1 &&
    gap_callback_state.calls >= 1 &&
    gap_callback_state.events >= 1 &&
    gap_payloads_drained &&
    gap_payloads.size() == 3 &&
    contains_payload(gap_payloads, "gap-one") &&
    contains_payload(gap_payloads, "gap-two") &&
    !contains_payload(gap_payloads, "gap-three") &&
    contains_payload(gap_payloads, "gap-four") &&
    gap_after_clear_wait_ret == RMW_RET_TIMEOUT &&
    !gap_after_clear_ready;
  const bool repair_suppression_ok =
    repair_event_init_ret == RMW_RET_OK &&
    repair_callback_ret == RMW_RET_OK &&
    repair_initial_wait_ret == RMW_RET_TIMEOUT &&
    !repair_initial_ready &&
    repair_publish_ok &&
    repair_received_ready &&
    repair_received_delta == 4 &&
    repair_wait_ret == RMW_RET_TIMEOUT &&
    !repair_wait_ready &&
    repair_take_ret == RMW_RET_OK &&
    !repair_taken &&
    repair_status.total_count == 0 &&
    repair_status.total_count_change == 0 &&
    repair_callback_state.calls == 0 &&
    repair_callback_state.events == 0 &&
    repair_observer_payloads_drained &&
    repair_reliable_payloads_drained &&
    repair_observer_payloads.size() == 4 &&
    repair_reliable_payloads.size() == 4 &&
    contains_payload(repair_observer_payloads, "repair-three") &&
    contains_payload(repair_reliable_payloads, "repair-three");
  const bool reliable_history_exhaustion_ok =
    exhausted_event_init_ret == RMW_RET_OK &&
    exhausted_callback_ret == RMW_RET_OK &&
    exhausted_initial_wait_ret == RMW_RET_TIMEOUT &&
    !exhausted_initial_ready &&
    exhausted_publish_ok &&
    exhausted_received_ready &&
    exhausted_received_delta == 3 &&
    exhausted_wait_ret == RMW_RET_OK &&
    exhausted_wait_ready &&
    exhausted_take_ret == RMW_RET_OK &&
    exhausted_taken &&
    exhausted_status.total_count == 1 &&
    exhausted_status.total_count_change == 1 &&
    exhausted_callback_state.calls >= 1 &&
    exhausted_callback_state.events == 1 &&
    loss_notices_sent_delta == 1 &&
    loss_notices_received_delta == 1 &&
    loss_samples_reported_delta == 1 &&
    exhausted_payloads_drained &&
    exhausted_payloads.size() == 3 &&
    contains_payload(exhausted_payloads, "exhausted-one") &&
    contains_payload(exhausted_payloads, "exhausted-two") &&
    !contains_payload(exhausted_payloads, "exhausted-three") &&
    contains_payload(exhausted_payloads, "exhausted-four") &&
    exhausted_after_clear_wait_ret == RMW_RET_TIMEOUT &&
    !exhausted_after_clear_ready;
  const bool lifecycle_ok =
    events_init_delta == 4 &&
    events_fini_delta == 4 &&
    callbacks_delta == 4 &&
    first_fini_ret == RMW_RET_OK &&
    second_fini_ret == RMW_RET_OK &&
    incoming_fini_ret == RMW_RET_OK &&
    event_fini_ret == RMW_RET_OK &&
    gap_event_fini_ret == RMW_RET_OK &&
    repair_event_fini_ret == RMW_RET_OK &&
    exhausted_event_fini_ret == RMW_RET_OK &&
    destroy_publisher_ret == RMW_RET_OK &&
    destroy_subscription_ret == RMW_RET_OK &&
    destroy_gap_publisher_ret == RMW_RET_OK &&
    destroy_gap_subscription_ret == RMW_RET_OK &&
    destroy_repair_publisher_ret == RMW_RET_OK &&
    destroy_repair_reliable_subscription_ret == RMW_RET_OK &&
    destroy_repair_observer_subscription_ret == RMW_RET_OK &&
    destroy_exhausted_publisher_ret == RMW_RET_OK &&
    destroy_exhausted_subscription_ret == RMW_RET_OK &&
    destroy_node_ret == RMW_RET_OK;
  const bool ok = event_ok && best_effort_gap_ok && repair_suppression_ok &&
    reliable_history_exhaustion_ok && lifecycle_ok;

  std::cout << "{\"schema_version\":\"fleetrmw.message_lost_event_probe.v1\",";
  std::cout << "\"status\":\"" << (ok ? "ok" : "failed") << "\",";
  std::cout << "\"message_lost_supported\":" <<
    (message_lost_supported ? "true" : "false") << ",";
  std::cout << "\"message_lost_taken\":" << (taken ? "true" : "false") << ",";
  std::cout << "\"message_lost_wait_ready\":" << (wait_ready ? "true" : "false") << ",";
  std::cout << "\"message_lost_total_count\":" << status.total_count << ",";
  std::cout << "\"message_lost_total_count_change\":" << status.total_count_change << ",";
  std::cout << "\"message_lost_callback_calls\":" << callback_state.calls << ",";
  std::cout << "\"message_lost_callback_events\":" << callback_state.events << ",";
  std::cout << "\"best_effort_gap_detected\":" <<
    (best_effort_gap_ok ? "true" : "false") << ",";
  std::cout << "\"best_effort_gap_received_frames\":" << gap_received_delta << ",";
  std::cout << "\"best_effort_gap_total_count\":" << gap_status.total_count << ",";
  std::cout << "\"best_effort_gap_total_count_change\":" <<
    gap_status.total_count_change << ",";
  std::cout << "\"best_effort_gap_callback_events\":" <<
    gap_callback_state.events << ",";
  std::cout << "\"best_effort_gap_payload_count\":" << gap_payloads.size() << ",";
  std::cout << "\"repair_suppressed_false_message_lost\":" <<
    (repair_suppression_ok ? "true" : "false") << ",";
  std::cout << "\"repair_received_frames\":" << repair_received_delta << ",";
  std::cout << "\"repair_observer_message_lost_taken\":" <<
    (repair_taken ? "true" : "false") << ",";
  std::cout << "\"repair_observer_message_lost_total_count\":" <<
    repair_status.total_count << ",";
  std::cout << "\"repair_observer_callback_events\":" <<
    repair_callback_state.events << ",";
  std::cout << "\"repair_observer_payload_count\":" <<
    repair_observer_payloads.size() << ",";
  std::cout << "\"repair_reliable_payload_count\":" <<
    repair_reliable_payloads.size() << ",";
  std::cout << "\"reliable_history_exhaustion_detected\":" <<
    (reliable_history_exhaustion_ok ? "true" : "false") << ",";
  std::cout << "\"reliable_history_exhaustion_received_frames\":" <<
    exhausted_received_delta << ",";
  std::cout << "\"reliable_history_exhaustion_total_count\":" <<
    exhausted_status.total_count << ",";
  std::cout << "\"reliable_history_exhaustion_callback_events\":" <<
    exhausted_callback_state.events << ",";
  std::cout << "\"unrecoverable_loss_notices_sent\":" <<
    loss_notices_sent_delta << ",";
  std::cout << "\"unrecoverable_loss_notices_received\":" <<
    loss_notices_received_delta << ",";
  std::cout << "\"unrecoverable_loss_samples_reported\":" <<
    loss_samples_reported_delta << ",";
  std::cout << "\"reliable_history_exhaustion_payload_count\":" <<
    exhausted_payloads.size() << ",";
  std::cout << "\"payload_taken\":" << (payload_taken ? "true" : "false") << ",";
  std::cout << "\"second_payload_taken\":" << (second_payload_taken ? "true" : "false") << ",";
  std::cout << "\"received_payload\":\"" << received_payload << "\",";
  std::cout << "\"events_initialized_delta\":" << events_init_delta << ",";
  std::cout << "\"events_finalized_delta\":" << events_fini_delta << ",";
  std::cout << "\"event_callbacks_set_delta\":" << callbacks_delta << ",";
  std::cout << "\"message_lost_event_production\":true,";
  std::cout << "\"message_lost_event_scope\":";
  std::cout << "\"local_keep_last_overwrite_best_effort_gap_repair_suppression_and_reliable_history_exhaustion\"";
  std::cout << "}\n";
  return ok ? 0 : 1;
}

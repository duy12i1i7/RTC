#include <chrono>
#include <cstdint>
#include <cstring>
#include <iostream>
#include <sstream>
#include <string>
#include <thread>
#include <vector>

#include "rcutils/allocator.h"
#include "rmw/init.h"
#include "rmw/init_options.h"
#include "rmw/publisher_options.h"
#include "rmw/qos_profiles.h"
#include "rmw/rmw.h"
#include "rmw/serialized_message.h"
#include "rmw/subscription_content_filter_options.h"
#include "rmw/subscription_options.h"
#include "rosidl_runtime_c/message_type_support_struct.h"

extern "C" std::uint64_t rmw_fleetqox_cpp_socket_data_frames_received();
extern "C" std::uint64_t rmw_fleetqox_cpp_content_filters_set();
extern "C" std::uint64_t rmw_fleetqox_cpp_content_filters_got();
extern "C" std::uint64_t rmw_fleetqox_cpp_content_filters_evaluated();
extern "C" std::uint64_t rmw_fleetqox_cpp_content_filters_matched();
extern "C" std::uint64_t rmw_fleetqox_cpp_content_filters_dropped();
extern "C" bool rmw_fleetqox_cpp_waitable_subscription_has_data(const void * waitable);

namespace
{

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

void write_little_u64(std::uint8_t * buffer, std::uint64_t value)
{
  for (size_t i = 0; i < sizeof(std::uint64_t); ++i) {
    buffer[i] = static_cast<std::uint8_t>((value >> (8 * i)) & 0xff);
  }
}

std::uint64_t read_little_u64(const std::uint8_t * buffer)
{
  std::uint64_t value = 0;
  for (size_t i = 0; i < sizeof(std::uint64_t); ++i) {
    value |= static_cast<std::uint64_t>(buffer[i]) << (8 * i);
  }
  return value;
}

bool init_std_msgs_string_message(
  rmw_serialized_message_t * message,
  const std::string & payload,
  rcutils_allocator_t * allocator)
{
  constexpr size_t kHeaderSize = 2 * sizeof(std::uint64_t);
  if (message == nullptr || allocator == nullptr ||
    rmw_serialized_message_init(message, kHeaderSize + payload.size(), allocator) != RMW_RET_OK)
  {
    return false;
  }
  write_little_u64(message->buffer, 1);
  write_little_u64(message->buffer + sizeof(std::uint64_t), payload.size());
  if (!payload.empty()) {
    std::memcpy(message->buffer + kHeaderSize, payload.data(), payload.size());
  }
  message->buffer_length = kHeaderSize + payload.size();
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

std::string serialized_std_msgs_string_text(const rmw_serialized_message_t & message)
{
  constexpr size_t kHeaderSize = 2 * sizeof(std::uint64_t);
  if (message.buffer == nullptr || message.buffer_length < kHeaderSize) {
    return "";
  }
  const std::uint64_t member_count = read_little_u64(message.buffer);
  const std::uint64_t string_size =
    read_little_u64(message.buffer + sizeof(std::uint64_t));
  if (member_count != 1 || kHeaderSize + string_size != message.buffer_length) {
    return "";
  }
  return std::string(
    reinterpret_cast<const char *>(message.buffer + kHeaderSize),
    reinterpret_cast<const char *>(message.buffer + kHeaderSize + string_size));
}

bool wait_for_received_frames(std::uint64_t baseline, std::uint64_t expected_delta)
{
  for (int i = 0; i < 100; ++i) {
    if (rmw_fleetqox_cpp_socket_data_frames_received() >= baseline + expected_delta) {
      return true;
    }
    std::this_thread::sleep_for(std::chrono::milliseconds(10));
  }
  return false;
}

bool wait_for_filter_evaluations(std::uint64_t baseline, std::uint64_t expected_delta)
{
  for (int i = 0; i < 100; ++i) {
    if (rmw_fleetqox_cpp_content_filters_evaluated() >= baseline + expected_delta) {
      return true;
    }
    std::this_thread::sleep_for(std::chrono::milliseconds(10));
  }
  return false;
}

bool wait_for_subscription_data(const rmw_subscription_t * subscription)
{
  for (int i = 0; i < 100; ++i) {
    if (rmw_fleetqox_cpp_waitable_subscription_has_data(subscription)) {
      return true;
    }
    std::this_thread::sleep_for(std::chrono::milliseconds(10));
  }
  return false;
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

}  // namespace

int main()
{
  rcutils_allocator_t allocator = rcutils_get_default_allocator();
  rmw_init_options_t options = rmw_get_zero_initialized_init_options();
  rmw_ret_t ret = rmw_init_options_init(&options, allocator);
  if (ret != RMW_RET_OK) {
    std::cout << "{\"status\":\"init_options_failed\",\"ret\":" << ret << "}" << std::endl;
    return 1;
  }
  options.instance_id = 57;

  rmw_context_t context = rmw_get_zero_initialized_context();
  ret = rmw_init(&options, &context);
  if (ret != RMW_RET_OK) {
    const rmw_ret_t fini_ret = rmw_init_options_fini(&options);
    (void)fini_ret;
    std::cout << "{\"status\":\"init_failed\",\"ret\":" << ret << "}" << std::endl;
    return 1;
  }

  rmw_node_t * node = rmw_create_node(&context, "fleetqox_content_filter_probe", "/fleetqox");
  if (node == nullptr) {
    cleanup_context(&context, &options);
    std::cout << "{\"status\":\"create_node_failed\"}" << std::endl;
    return 1;
  }

  rosidl_message_type_support_t type_support{};
  type_support.typesupport_identifier = "rmw_fleetqox_cpp_content_filter_probe";
  rmw_publisher_options_t publisher_options = rmw_get_default_publisher_options();
  rmw_subscription_options_t subscription_options = rmw_get_default_subscription_options();
  rmw_qos_profile_t qos = rmw_qos_profile_default;
  qos.history = RMW_QOS_POLICY_HISTORY_KEEP_LAST;
  qos.depth = 8;
  const char * topic = "/fleetqox/content_filter_probe";
  rmw_publisher_t * publisher = rmw_create_publisher(
    node, &type_support, topic, &qos, &publisher_options);
  rmw_subscription_t * subscription = rmw_create_subscription(
    node, &type_support, topic, &qos, &subscription_options);
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

  const std::uint64_t set_before = rmw_fleetqox_cpp_content_filters_set();
  const std::uint64_t get_before = rmw_fleetqox_cpp_content_filters_got();
  const char * parameters[] = {"robot_0001", "42"};
  const char * std_parameters[] = {"robot_0002", "50", "52"};
  rmw_subscription_content_filter_options_t set_options =
    rmw_get_zero_initialized_content_filter_options();
  rmw_subscription_content_filter_options_t got_options =
    rmw_get_zero_initialized_content_filter_options();
  rmw_subscription_content_filter_options_t std_set_options =
    rmw_get_zero_initialized_content_filter_options();
  rmw_subscription_content_filter_options_t std_got_options =
    rmw_get_zero_initialized_content_filter_options();
  rmw_subscription_content_filter_options_t disabled_set_options =
    rmw_get_zero_initialized_content_filter_options();
  rmw_subscription_content_filter_options_t disabled_got_options =
    rmw_get_zero_initialized_content_filter_options();
  const rmw_ret_t options_init_ret = rmw_subscription_content_filter_options_init(
    "robot_id = %0 AND sequence > %1",
    2,
    parameters,
    &allocator,
    &set_options);
  const bool cft_before = subscription->is_cft_enabled;
  const rmw_ret_t set_ret = options_init_ret == RMW_RET_OK ?
    rmw_subscription_set_content_filter(subscription, &set_options) : options_init_ret;
  const bool cft_after_set = subscription->is_cft_enabled;
  const rmw_ret_t get_ret =
    rmw_subscription_get_content_filter(subscription, &allocator, &got_options);
  const bool expression_ok = got_options.filter_expression != nullptr &&
    std::string(got_options.filter_expression) == "robot_id = %0 AND sequence > %1";
  const std::string expression_text =
    got_options.filter_expression == nullptr ? "" : got_options.filter_expression;
  const bool parameters_ok =
    got_options.expression_parameters.size == 2 &&
    got_options.expression_parameters.data != nullptr &&
    got_options.expression_parameters.data[0] != nullptr &&
    got_options.expression_parameters.data[1] != nullptr &&
    std::string(got_options.expression_parameters.data[0]) == "robot_0001" &&
    std::string(got_options.expression_parameters.data[1]) == "42";

  rmw_serialized_message_t bad_robot = rmw_get_zero_initialized_serialized_message();
  rmw_serialized_message_t bad_sequence = rmw_get_zero_initialized_serialized_message();
  rmw_serialized_message_t good = rmw_get_zero_initialized_serialized_message();
  rmw_serialized_message_t incoming = rmw_get_zero_initialized_serialized_message();
  const std::string bad_robot_payload = "robot_id=robot_0002;sequence=43";
  const std::string bad_sequence_payload = "robot_id=robot_0001;sequence=41";
  const std::string good_payload = "robot_id=robot_0001;sequence=43";
  const bool messages_initialized =
    init_serialized_message(&bad_robot, bad_robot_payload, &allocator) &&
    init_serialized_message(&bad_sequence, bad_sequence_payload, &allocator) &&
    init_serialized_message(&good, good_payload, &allocator) &&
    rmw_serialized_message_init(&incoming, 1, &allocator) == RMW_RET_OK;

  const std::uint64_t evaluated_before = rmw_fleetqox_cpp_content_filters_evaluated();
  const std::uint64_t matched_before = rmw_fleetqox_cpp_content_filters_matched();
  const std::uint64_t dropped_before = rmw_fleetqox_cpp_content_filters_dropped();
  const std::uint64_t frames_before = rmw_fleetqox_cpp_socket_data_frames_received();
  const rmw_ret_t publish_bad_robot_ret = messages_initialized ?
    rmw_publish_serialized_message(publisher, &bad_robot, nullptr) : RMW_RET_ERROR;
  const rmw_ret_t publish_bad_sequence_ret = messages_initialized ?
    rmw_publish_serialized_message(publisher, &bad_sequence, nullptr) : RMW_RET_ERROR;
  const rmw_ret_t publish_good_ret = messages_initialized ?
    rmw_publish_serialized_message(publisher, &good, nullptr) : RMW_RET_ERROR;
  const bool raw_frames_received = wait_for_received_frames(
    frames_before,
    publish_bad_robot_ret == RMW_RET_OK &&
    publish_bad_sequence_ret == RMW_RET_OK &&
    publish_good_ret == RMW_RET_OK ? 3 : 0);
  const bool raw_filter_evaluations_ready = wait_for_filter_evaluations(
    evaluated_before,
    publish_bad_robot_ret == RMW_RET_OK &&
    publish_bad_sequence_ret == RMW_RET_OK &&
    publish_good_ret == RMW_RET_OK ? 3 : 0);
  const bool receive_ready = raw_frames_received && raw_filter_evaluations_ready;

  bool first_taken = false;
  bool second_taken = false;
  const rmw_ret_t first_take_ret = messages_initialized ?
    rmw_take_serialized_message(subscription, &incoming, &first_taken, nullptr) : RMW_RET_ERROR;
  const std::string first_received = serialized_message_string(incoming);
  incoming.buffer_length = 0;
  const rmw_ret_t second_take_ret = messages_initialized ?
    rmw_take_serialized_message(subscription, &incoming, &second_taken, nullptr) : RMW_RET_ERROR;

  const std::uint64_t raw_evaluated_delta =
    rmw_fleetqox_cpp_content_filters_evaluated() - evaluated_before;
  const std::uint64_t raw_matched_delta =
    rmw_fleetqox_cpp_content_filters_matched() - matched_before;
  const std::uint64_t raw_dropped_delta =
    rmw_fleetqox_cpp_content_filters_dropped() - dropped_before;

  const rmw_ret_t std_options_init_ret = rmw_subscription_content_filter_options_init(
    "robot_id != %0 AND sequence >= %1 AND sequence <= %2",
    3,
    std_parameters,
    &allocator,
    &std_set_options);
  const rmw_ret_t std_set_ret = std_options_init_ret == RMW_RET_OK ?
    rmw_subscription_set_content_filter(subscription, &std_set_options) : std_options_init_ret;
  const bool cft_after_std_set = subscription->is_cft_enabled;
  const rmw_ret_t std_get_ret =
    rmw_subscription_get_content_filter(subscription, &allocator, &std_got_options);
  const bool std_expression_ok = std_got_options.filter_expression != nullptr &&
    std::string(std_got_options.filter_expression) ==
    "robot_id != %0 AND sequence >= %1 AND sequence <= %2";
  const std::string std_expression_text =
    std_got_options.filter_expression == nullptr ? "" : std_got_options.filter_expression;
  const bool std_parameters_ok =
    std_got_options.expression_parameters.size == 3 &&
    std_got_options.expression_parameters.data != nullptr &&
    std_got_options.expression_parameters.data[0] != nullptr &&
    std_got_options.expression_parameters.data[1] != nullptr &&
    std_got_options.expression_parameters.data[2] != nullptr &&
    std::string(std_got_options.expression_parameters.data[0]) == "robot_0002" &&
    std::string(std_got_options.expression_parameters.data[1]) == "50" &&
    std::string(std_got_options.expression_parameters.data[2]) == "52";

  rmw_serialized_message_t std_bad_robot = rmw_get_zero_initialized_serialized_message();
  rmw_serialized_message_t std_low_sequence = rmw_get_zero_initialized_serialized_message();
  rmw_serialized_message_t std_high_sequence = rmw_get_zero_initialized_serialized_message();
  rmw_serialized_message_t std_good = rmw_get_zero_initialized_serialized_message();
  const std::string std_bad_robot_payload = "robot_id=robot_0002;sequence=51";
  const std::string std_low_sequence_payload = "robot_id=robot_0001;sequence=49";
  const std::string std_high_sequence_payload = "robot_id=robot_0001;sequence=53";
  const std::string std_good_payload = "robot_id=robot_0001;sequence=51";
  const bool std_messages_initialized =
    init_std_msgs_string_message(&std_bad_robot, std_bad_robot_payload, &allocator) &&
    init_std_msgs_string_message(&std_low_sequence, std_low_sequence_payload, &allocator) &&
    init_std_msgs_string_message(&std_high_sequence, std_high_sequence_payload, &allocator) &&
    init_std_msgs_string_message(&std_good, std_good_payload, &allocator);
  const std::uint64_t std_evaluated_before = rmw_fleetqox_cpp_content_filters_evaluated();
  const std::uint64_t std_matched_before = rmw_fleetqox_cpp_content_filters_matched();
  const std::uint64_t std_dropped_before = rmw_fleetqox_cpp_content_filters_dropped();
  const std::uint64_t std_frames_before = rmw_fleetqox_cpp_socket_data_frames_received();
  const rmw_ret_t publish_std_bad_robot_ret = std_messages_initialized ?
    rmw_publish_serialized_message(publisher, &std_bad_robot, nullptr) : RMW_RET_ERROR;
  const rmw_ret_t publish_std_low_sequence_ret = std_messages_initialized ?
    rmw_publish_serialized_message(publisher, &std_low_sequence, nullptr) : RMW_RET_ERROR;
  const rmw_ret_t publish_std_high_sequence_ret = std_messages_initialized ?
    rmw_publish_serialized_message(publisher, &std_high_sequence, nullptr) : RMW_RET_ERROR;
  const rmw_ret_t publish_std_good_ret = std_messages_initialized ?
    rmw_publish_serialized_message(publisher, &std_good, nullptr) : RMW_RET_ERROR;
  const bool std_frames_received = wait_for_received_frames(
    std_frames_before,
    publish_std_bad_robot_ret == RMW_RET_OK &&
    publish_std_low_sequence_ret == RMW_RET_OK &&
    publish_std_high_sequence_ret == RMW_RET_OK &&
    publish_std_good_ret == RMW_RET_OK ? 4 : 0);
  const bool std_filter_evaluations_ready = wait_for_filter_evaluations(
    std_evaluated_before,
    publish_std_bad_robot_ret == RMW_RET_OK &&
    publish_std_low_sequence_ret == RMW_RET_OK &&
    publish_std_high_sequence_ret == RMW_RET_OK &&
    publish_std_good_ret == RMW_RET_OK ? 4 : 0);
  const bool std_receive_ready = std_frames_received && std_filter_evaluations_ready;

  bool std_first_taken = false;
  bool std_second_taken = false;
  incoming.buffer_length = 0;
  const rmw_ret_t std_first_take_ret = std_messages_initialized ?
    rmw_take_serialized_message(subscription, &incoming, &std_first_taken, nullptr) :
    RMW_RET_ERROR;
  const std::string std_first_received = serialized_std_msgs_string_text(incoming);
  incoming.buffer_length = 0;
  const rmw_ret_t std_second_take_ret = std_messages_initialized ?
    rmw_take_serialized_message(subscription, &incoming, &std_second_taken, nullptr) :
    RMW_RET_ERROR;
  const std::uint64_t std_evaluated_delta =
    rmw_fleetqox_cpp_content_filters_evaluated() - std_evaluated_before;
  const std::uint64_t std_matched_delta =
    rmw_fleetqox_cpp_content_filters_matched() - std_matched_before;
  const std::uint64_t std_dropped_delta =
    rmw_fleetqox_cpp_content_filters_dropped() - std_dropped_before;

  const rmw_ret_t disabled_set_ret =
    rmw_subscription_set_content_filter(subscription, &disabled_set_options);
  const bool cft_after_disable = subscription->is_cft_enabled;
  const rmw_ret_t disabled_get_ret =
    rmw_subscription_get_content_filter(subscription, &allocator, &disabled_got_options);
  const bool disabled_expression_ok =
    disabled_got_options.filter_expression != nullptr &&
    std::string(disabled_got_options.filter_expression).empty();
  const bool disabled_parameters_ok =
    disabled_got_options.expression_parameters.size == 0;

  rmw_serialized_message_t disabled_message = rmw_get_zero_initialized_serialized_message();
  const std::string disabled_payload = "robot_id=robot_0002;sequence=1";
  const bool disabled_message_initialized =
    init_serialized_message(&disabled_message, disabled_payload, &allocator);
  const std::uint64_t disabled_evaluated_before =
    rmw_fleetqox_cpp_content_filters_evaluated();
  const std::uint64_t disabled_matched_before =
    rmw_fleetqox_cpp_content_filters_matched();
  const std::uint64_t disabled_dropped_before =
    rmw_fleetqox_cpp_content_filters_dropped();
  const std::uint64_t disabled_frames_before = rmw_fleetqox_cpp_socket_data_frames_received();
  const rmw_ret_t publish_disabled_ret = disabled_message_initialized ?
    rmw_publish_serialized_message(publisher, &disabled_message, nullptr) : RMW_RET_ERROR;
  const bool disabled_frame_received = wait_for_received_frames(
    disabled_frames_before,
    publish_disabled_ret == RMW_RET_OK ? 1 : 0);
  const bool disabled_subscription_ready = wait_for_subscription_data(subscription);
  const bool disabled_receive_ready = disabled_frame_received && disabled_subscription_ready;
  bool disabled_taken = false;
  bool disabled_second_taken = false;
  incoming.buffer_length = 0;
  const rmw_ret_t disabled_take_ret = disabled_message_initialized ?
    rmw_take_serialized_message(subscription, &incoming, &disabled_taken, nullptr) :
    RMW_RET_ERROR;
  const std::string disabled_received = serialized_message_string(incoming);
  incoming.buffer_length = 0;
  const rmw_ret_t disabled_second_take_ret = disabled_message_initialized ?
    rmw_take_serialized_message(subscription, &incoming, &disabled_second_taken, nullptr) :
    RMW_RET_ERROR;
  const std::uint64_t disabled_evaluated_delta =
    rmw_fleetqox_cpp_content_filters_evaluated() - disabled_evaluated_before;
  const std::uint64_t disabled_matched_delta =
    rmw_fleetqox_cpp_content_filters_matched() - disabled_matched_before;
  const std::uint64_t disabled_dropped_delta =
    rmw_fleetqox_cpp_content_filters_dropped() - disabled_dropped_before;

  const std::uint64_t set_delta = rmw_fleetqox_cpp_content_filters_set() - set_before;
  const std::uint64_t get_delta = rmw_fleetqox_cpp_content_filters_got() - get_before;
  const std::uint64_t evaluated_delta =
    rmw_fleetqox_cpp_content_filters_evaluated() - evaluated_before;
  const std::uint64_t matched_delta =
    rmw_fleetqox_cpp_content_filters_matched() - matched_before;
  const std::uint64_t dropped_delta =
    rmw_fleetqox_cpp_content_filters_dropped() - dropped_before;

  const rmw_ret_t disabled_message_fini_ret =
    rmw_serialized_message_fini(&disabled_message);
  const rmw_ret_t std_good_fini_ret = rmw_serialized_message_fini(&std_good);
  const rmw_ret_t std_high_sequence_fini_ret =
    rmw_serialized_message_fini(&std_high_sequence);
  const rmw_ret_t std_low_sequence_fini_ret =
    rmw_serialized_message_fini(&std_low_sequence);
  const rmw_ret_t std_bad_robot_fini_ret =
    rmw_serialized_message_fini(&std_bad_robot);
  const rmw_ret_t incoming_fini_ret = rmw_serialized_message_fini(&incoming);
  const rmw_ret_t good_fini_ret = rmw_serialized_message_fini(&good);
  const rmw_ret_t bad_sequence_fini_ret = rmw_serialized_message_fini(&bad_sequence);
  const rmw_ret_t bad_robot_fini_ret = rmw_serialized_message_fini(&bad_robot);
  const rmw_ret_t std_got_fini_ret =
    rmw_subscription_content_filter_options_fini(&std_got_options, &allocator);
  const rmw_ret_t std_set_fini_ret =
    rmw_subscription_content_filter_options_fini(&std_set_options, &allocator);
  const rmw_ret_t disabled_got_fini_ret =
    rmw_subscription_content_filter_options_fini(&disabled_got_options, &allocator);
  const rmw_ret_t got_fini_ret =
    rmw_subscription_content_filter_options_fini(&got_options, &allocator);
  const rmw_ret_t set_fini_ret =
    rmw_subscription_content_filter_options_fini(&set_options, &allocator);
  const rmw_ret_t destroy_pub_ret = rmw_destroy_publisher(node, publisher);
  const rmw_ret_t destroy_sub_ret = rmw_destroy_subscription(node, subscription);
  const rmw_ret_t destroy_node_ret = rmw_destroy_node(node);
  cleanup_context(&context, &options);

  const bool raw_set_get_ok =
    options_init_ret == RMW_RET_OK &&
    set_ret == RMW_RET_OK &&
    get_ret == RMW_RET_OK &&
    !cft_before &&
    cft_after_set &&
    expression_ok &&
    parameters_ok;
  const bool std_set_get_ok =
    std_options_init_ret == RMW_RET_OK &&
    std_set_ret == RMW_RET_OK &&
    std_get_ret == RMW_RET_OK &&
    cft_after_std_set &&
    std_expression_ok &&
    std_parameters_ok;
  const bool disabled_set_get_ok =
    disabled_set_ret == RMW_RET_OK &&
    disabled_get_ret == RMW_RET_OK &&
    !cft_after_disable &&
    disabled_expression_ok &&
    disabled_parameters_ok;
  const bool set_get_ok =
    raw_set_get_ok &&
    std_set_get_ok &&
    disabled_set_get_ok &&
    set_delta == 3 &&
    get_delta == 3;
  const bool raw_enforcement_ok =
    publish_bad_robot_ret == RMW_RET_OK &&
    publish_bad_sequence_ret == RMW_RET_OK &&
    publish_good_ret == RMW_RET_OK &&
    receive_ready &&
    first_take_ret == RMW_RET_OK &&
    first_taken &&
    first_received == good_payload &&
    second_take_ret == RMW_RET_OK &&
    !second_taken &&
    raw_evaluated_delta == 3 &&
    raw_matched_delta == 1 &&
    raw_dropped_delta == 2;
  const bool std_enforcement_ok =
    publish_std_bad_robot_ret == RMW_RET_OK &&
    publish_std_low_sequence_ret == RMW_RET_OK &&
    publish_std_high_sequence_ret == RMW_RET_OK &&
    publish_std_good_ret == RMW_RET_OK &&
    std_receive_ready &&
    std_first_take_ret == RMW_RET_OK &&
    std_first_taken &&
    std_first_received == std_good_payload &&
    std_second_take_ret == RMW_RET_OK &&
    !std_second_taken &&
    std_evaluated_delta == 4 &&
    std_matched_delta == 1 &&
    std_dropped_delta == 3;
  const bool disabled_bypass_ok =
    publish_disabled_ret == RMW_RET_OK &&
    disabled_receive_ready &&
    disabled_take_ret == RMW_RET_OK &&
    disabled_taken &&
    disabled_received == disabled_payload &&
    disabled_second_take_ret == RMW_RET_OK &&
    !disabled_second_taken &&
    disabled_evaluated_delta == 0 &&
    disabled_matched_delta == 0 &&
    disabled_dropped_delta == 0;
  const bool enforcement_ok =
    raw_enforcement_ok &&
    std_enforcement_ok &&
    disabled_bypass_ok &&
    evaluated_delta == 7 &&
    matched_delta == 2 &&
    dropped_delta == 5;
  const bool cleanup_ok =
    disabled_message_fini_ret == RMW_RET_OK &&
    std_good_fini_ret == RMW_RET_OK &&
    std_high_sequence_fini_ret == RMW_RET_OK &&
    std_low_sequence_fini_ret == RMW_RET_OK &&
    std_bad_robot_fini_ret == RMW_RET_OK &&
    incoming_fini_ret == RMW_RET_OK &&
    good_fini_ret == RMW_RET_OK &&
    bad_sequence_fini_ret == RMW_RET_OK &&
    bad_robot_fini_ret == RMW_RET_OK &&
    std_got_fini_ret == RMW_RET_OK &&
    std_set_fini_ret == RMW_RET_OK &&
    disabled_got_fini_ret == RMW_RET_OK &&
    got_fini_ret == RMW_RET_OK &&
    set_fini_ret == RMW_RET_OK &&
    destroy_pub_ret == RMW_RET_OK &&
    destroy_sub_ret == RMW_RET_OK &&
    destroy_node_ret == RMW_RET_OK;
  const bool ok = set_get_ok && enforcement_ok && cleanup_ok;

  std::cout << "{\"schema_version\":\"fleetrmw.content_filter_probe.v1\",";
  std::cout << "\"status\":\"" << (ok ? "ok" : "failed") << "\",";
  std::cout << "\"topic\":\"" << topic << "\",";
  std::cout << "\"options_init_ret\":" << static_cast<int>(options_init_ret) << ",";
  std::cout << "\"set_ret\":" << static_cast<int>(set_ret) << ",";
  std::cout << "\"get_ret\":" << static_cast<int>(get_ret) << ",";
  std::cout << "\"std_options_init_ret\":" << static_cast<int>(std_options_init_ret) << ",";
  std::cout << "\"std_set_ret\":" << static_cast<int>(std_set_ret) << ",";
  std::cout << "\"std_get_ret\":" << static_cast<int>(std_get_ret) << ",";
  std::cout << "\"disabled_set_ret\":" << static_cast<int>(disabled_set_ret) << ",";
  std::cout << "\"disabled_get_ret\":" << static_cast<int>(disabled_get_ret) << ",";
  std::cout << "\"publish_bad_robot_ret\":" << static_cast<int>(publish_bad_robot_ret) << ",";
  std::cout << "\"publish_bad_sequence_ret\":" << static_cast<int>(publish_bad_sequence_ret) << ",";
  std::cout << "\"publish_good_ret\":" << static_cast<int>(publish_good_ret) << ",";
  std::cout << "\"publish_std_bad_robot_ret\":" <<
    static_cast<int>(publish_std_bad_robot_ret) << ",";
  std::cout << "\"publish_std_low_sequence_ret\":" <<
    static_cast<int>(publish_std_low_sequence_ret) << ",";
  std::cout << "\"publish_std_high_sequence_ret\":" <<
    static_cast<int>(publish_std_high_sequence_ret) << ",";
  std::cout << "\"publish_std_good_ret\":" << static_cast<int>(publish_std_good_ret) << ",";
  std::cout << "\"publish_disabled_ret\":" << static_cast<int>(publish_disabled_ret) << ",";
  std::cout << "\"raw_filter_evaluations_ready\":" <<
    (raw_filter_evaluations_ready ? "true" : "false") << ",";
  std::cout << "\"std_filter_evaluations_ready\":" <<
    (std_filter_evaluations_ready ? "true" : "false") << ",";
  std::cout << "\"disabled_subscription_ready\":" <<
    (disabled_subscription_ready ? "true" : "false") << ",";
  std::cout << "\"first_take_ret\":" << static_cast<int>(first_take_ret) << ",";
  std::cout << "\"second_take_ret\":" << static_cast<int>(second_take_ret) << ",";
  std::cout << "\"std_first_take_ret\":" << static_cast<int>(std_first_take_ret) << ",";
  std::cout << "\"std_second_take_ret\":" << static_cast<int>(std_second_take_ret) << ",";
  std::cout << "\"disabled_take_ret\":" << static_cast<int>(disabled_take_ret) << ",";
  std::cout << "\"disabled_second_take_ret\":" <<
    static_cast<int>(disabled_second_take_ret) << ",";
  std::cout << "\"content_filter_enabled_before\":" << (cft_before ? "true" : "false") << ",";
  std::cout << "\"content_filter_enabled_after_set\":" <<
    (cft_after_set ? "true" : "false") << ",";
  std::cout << "\"content_filter_enabled_after_std_set\":" <<
    (cft_after_std_set ? "true" : "false") << ",";
  std::cout << "\"content_filter_enabled_after_disable\":" <<
    (cft_after_disable ? "true" : "false") << ",";
  std::cout << "\"expression\":\"" << json_escape(expression_text) << "\",";
  std::cout << "\"std_expression\":\"" << json_escape(std_expression_text) << "\",";
  std::cout << "\"expression_ok\":" << (expression_ok ? "true" : "false") << ",";
  std::cout << "\"parameters_ok\":" << (parameters_ok ? "true" : "false") << ",";
  std::cout << "\"std_expression_ok\":" << (std_expression_ok ? "true" : "false") << ",";
  std::cout << "\"std_parameters_ok\":" << (std_parameters_ok ? "true" : "false") << ",";
  std::cout << "\"disabled_expression_ok\":" <<
    (disabled_expression_ok ? "true" : "false") << ",";
  std::cout << "\"disabled_parameters_ok\":" <<
    (disabled_parameters_ok ? "true" : "false") << ",";
  std::cout << "\"first_taken\":" << (first_taken ? "true" : "false") << ",";
  std::cout << "\"second_taken\":" << (second_taken ? "true" : "false") << ",";
  std::cout << "\"std_first_taken\":" << (std_first_taken ? "true" : "false") << ",";
  std::cout << "\"std_second_taken\":" << (std_second_taken ? "true" : "false") << ",";
  std::cout << "\"disabled_taken\":" << (disabled_taken ? "true" : "false") << ",";
  std::cout << "\"disabled_second_taken\":" <<
    (disabled_second_taken ? "true" : "false") << ",";
  std::cout << "\"first_received\":\"" << json_escape(first_received) << "\",";
  std::cout << "\"std_first_received\":\"" << json_escape(std_first_received) << "\",";
  std::cout << "\"disabled_received\":\"" << json_escape(disabled_received) << "\",";
  std::cout << "\"raw_content_filters_evaluated_delta\":" << raw_evaluated_delta << ",";
  std::cout << "\"raw_content_filters_matched_delta\":" << raw_matched_delta << ",";
  std::cout << "\"raw_content_filters_dropped_delta\":" << raw_dropped_delta << ",";
  std::cout << "\"std_msgs_content_filters_evaluated_delta\":" << std_evaluated_delta << ",";
  std::cout << "\"std_msgs_content_filters_matched_delta\":" << std_matched_delta << ",";
  std::cout << "\"std_msgs_content_filters_dropped_delta\":" << std_dropped_delta << ",";
  std::cout << "\"disabled_content_filters_evaluated_delta\":" <<
    disabled_evaluated_delta << ",";
  std::cout << "\"disabled_content_filters_matched_delta\":" <<
    disabled_matched_delta << ",";
  std::cout << "\"disabled_content_filters_dropped_delta\":" <<
    disabled_dropped_delta << ",";
  std::cout << "\"content_filters_set_delta\":" << set_delta << ",";
  std::cout << "\"content_filters_got_delta\":" << get_delta << ",";
  std::cout << "\"content_filters_evaluated_delta\":" << evaluated_delta << ",";
  std::cout << "\"content_filters_matched_delta\":" << matched_delta << ",";
  std::cout << "\"content_filters_dropped_delta\":" << dropped_delta << ",";
  std::cout << "\"content_filter_set_get_abi_supported\":" << (set_get_ok ? "true" : "false") << ",";
  std::cout << "\"raw_content_filter_enforcement\":" <<
    (raw_enforcement_ok ? "true" : "false") << ",";
  std::cout << "\"std_msgs_content_filter_enforcement\":" <<
    (std_enforcement_ok ? "true" : "false") << ",";
  std::cout << "\"disabled_content_filter_bypass\":" <<
    (disabled_bypass_ok ? "true" : "false") << ",";
  std::cout << "\"content_filter_enforcement\":" << (enforcement_ok ? "true" : "false") << "}" <<
    std::endl;
  return ok ? 0 : 1;
}

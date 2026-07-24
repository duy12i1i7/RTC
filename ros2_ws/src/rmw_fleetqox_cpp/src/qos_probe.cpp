#include <chrono>
#include <cstdint>
#include <cstring>
#include <iostream>
#include <initializer_list>
#include <sstream>
#include <string>
#include <thread>

#include "rcutils/allocator.h"
#include "rmw/init.h"
#include "rmw/init_options.h"
#include "rmw/publisher_options.h"
#include "rmw/qos_profiles.h"
#include "rmw/rmw.h"
#include "rmw/serialized_message.h"
#include "rmw/subscription_options.h"
#include "rosidl_runtime_c/message_type_support_struct.h"

extern "C" std::uint64_t rmw_fleetqox_cpp_socket_data_frames_received();

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
  for (int attempt = 0; attempt < 200; ++attempt) {
    if (rmw_fleetqox_cpp_socket_data_frames_received() >= baseline + expected_delta) {
      return true;
    }
    std::this_thread::sleep_for(std::chrono::milliseconds(1));
  }
  return false;
}

bool compatibility_case(
  const rmw_qos_profile_t & publisher,
  const rmw_qos_profile_t & subscription,
  rmw_qos_compatibility_type_t expected,
  std::initializer_list<const char *> reason_tokens,
  std::string * observed_reason = nullptr)
{
  char reason[512]{};
  rmw_qos_compatibility_type_t compatibility = RMW_QOS_COMPATIBILITY_OK;
  const rmw_ret_t ret = rmw_qos_profile_check_compatible(
    publisher, subscription, &compatibility, reason, sizeof(reason));
  if (observed_reason != nullptr) {
    *observed_reason = reason;
  }
  if (ret != RMW_RET_OK || compatibility != expected) {
    return false;
  }
  const std::string text(reason);
  for (const char * token : reason_tokens) {
    if (token == nullptr || text.find(token) == std::string::npos) {
      return false;
    }
  }
  return expected != RMW_QOS_COMPATIBILITY_OK || text.empty();
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
  options.instance_id = 47;

  rmw_context_t context = rmw_get_zero_initialized_context();
  ret = rmw_init(&options, &context);
  if (ret != RMW_RET_OK) {
    const rmw_ret_t fini_ret = rmw_init_options_fini(&options);
    (void)fini_ret;
    std::cout << "{\"status\":\"init_failed\",\"ret\":" << ret << "}" << std::endl;
    return 1;
  }

  rmw_node_t * node = rmw_create_node(&context, "fleetqox_qos_probe", "/fleetqox");
  if (node == nullptr) {
    cleanup_context(&context, &options);
    std::cout << "{\"status\":\"create_node_failed\"}" << std::endl;
    return 1;
  }

  rosidl_message_type_support_t type_support{};
  type_support.typesupport_identifier = "rmw_fleetqox_cpp_qos_probe";
  rmw_publisher_options_t publisher_options = rmw_get_default_publisher_options();
  rmw_subscription_options_t subscription_options = rmw_get_default_subscription_options();

  rmw_qos_profile_t depth_qos = rmw_qos_profile_default;
  depth_qos.history = RMW_QOS_POLICY_HISTORY_KEEP_LAST;
  depth_qos.depth = 1;
  const char * depth_topic = "/fleetqox/qos_depth_probe";
  rmw_publisher_t * depth_publisher = rmw_create_publisher(
    node, &type_support, depth_topic, &depth_qos, &publisher_options);
  rmw_subscription_t * depth_subscription = rmw_create_subscription(
    node, &type_support, depth_topic, &depth_qos, &subscription_options);

  rmw_qos_profile_t lifespan_qos = rmw_qos_profile_default;
  lifespan_qos.history = RMW_QOS_POLICY_HISTORY_KEEP_LAST;
  lifespan_qos.depth = 10;
  lifespan_qos.lifespan.sec = 0;
  lifespan_qos.lifespan.nsec = 5000000;
  const char * lifespan_topic = "/fleetqox/qos_lifespan_probe";
  rmw_publisher_t * lifespan_publisher = rmw_create_publisher(
    node, &type_support, lifespan_topic, &lifespan_qos, &publisher_options);
  rmw_subscription_t * lifespan_subscription = rmw_create_subscription(
    node, &type_support, lifespan_topic, &lifespan_qos, &subscription_options);

  if (depth_publisher == nullptr || depth_subscription == nullptr ||
    lifespan_publisher == nullptr || lifespan_subscription == nullptr)
  {
    std::cout << "{\"status\":\"create_pubsub_failed\"}" << std::endl;
    return 1;
  }

  rmw_serialized_message_t first = rmw_get_zero_initialized_serialized_message();
  rmw_serialized_message_t second = rmw_get_zero_initialized_serialized_message();
  rmw_serialized_message_t depth_incoming = rmw_get_zero_initialized_serialized_message();
  rmw_serialized_message_t expired = rmw_get_zero_initialized_serialized_message();
  rmw_serialized_message_t lifespan_incoming = rmw_get_zero_initialized_serialized_message();
  if (!init_serialized_message(&first, "first", &allocator) ||
    !init_serialized_message(&second, "second", &allocator) ||
    rmw_serialized_message_init(&depth_incoming, 1, &allocator) != RMW_RET_OK ||
    !init_serialized_message(&expired, "expired", &allocator) ||
    rmw_serialized_message_init(&lifespan_incoming, 1, &allocator) != RMW_RET_OK)
  {
    std::cout << "{\"status\":\"serialized_message_init_failed\"}" << std::endl;
    return 1;
  }

  const std::uint64_t depth_received_before = rmw_fleetqox_cpp_socket_data_frames_received();
  rmw_ret_t depth_publish_first_ret =
    rmw_publish_serialized_message(depth_publisher, &first, nullptr);
  rmw_ret_t depth_publish_second_ret =
    rmw_publish_serialized_message(depth_publisher, &second, nullptr);
  const bool depth_received_ready = wait_for_received_frames(depth_received_before, 2);
  bool depth_taken = false;
  rmw_ret_t depth_take_ret =
    rmw_take_serialized_message(depth_subscription, &depth_incoming, &depth_taken, nullptr);
  bool depth_second_take = false;
  rmw_ret_t depth_second_take_ret =
    rmw_take_serialized_message(depth_subscription, &depth_incoming, &depth_second_take, nullptr);
  const std::string depth_received = serialized_message_string(depth_incoming);

  const std::uint64_t lifespan_received_before = rmw_fleetqox_cpp_socket_data_frames_received();
  rmw_ret_t lifespan_publish_ret =
    rmw_publish_serialized_message(lifespan_publisher, &expired, nullptr);
  const bool lifespan_received_ready = wait_for_received_frames(lifespan_received_before, 1);
  std::this_thread::sleep_for(std::chrono::milliseconds(30));
  bool lifespan_taken = false;
  rmw_ret_t lifespan_take_ret =
    rmw_take_serialized_message(lifespan_subscription, &lifespan_incoming, &lifespan_taken, nullptr);
  const std::string lifespan_received = serialized_message_string(lifespan_incoming);

  const bool depth_ok =
    depth_publish_first_ret == RMW_RET_OK &&
    depth_publish_second_ret == RMW_RET_OK &&
    depth_received_ready &&
    depth_take_ret == RMW_RET_OK &&
    depth_taken &&
    depth_received == "second" &&
    depth_second_take_ret == RMW_RET_OK &&
    !depth_second_take;
  const bool lifespan_ok =
    lifespan_publish_ret == RMW_RET_OK &&
    lifespan_received_ready &&
    lifespan_take_ret == RMW_RET_OK &&
    !lifespan_taken;

  rmw_qos_profile_t compatible_publisher = rmw_qos_profile_default;
  compatible_publisher.reliability = RMW_QOS_POLICY_RELIABILITY_RELIABLE;
  compatible_publisher.durability = RMW_QOS_POLICY_DURABILITY_VOLATILE;
  compatible_publisher.liveliness = RMW_QOS_POLICY_LIVELINESS_AUTOMATIC;
  compatible_publisher.deadline = RMW_QOS_DEADLINE_DEFAULT;
  compatible_publisher.liveliness_lease_duration =
    RMW_QOS_LIVELINESS_LEASE_DURATION_DEFAULT;
  rmw_qos_profile_t compatible_subscription = compatible_publisher;
  const bool compatible_case_ok = compatibility_case(
    compatible_publisher, compatible_subscription, RMW_QOS_COMPATIBILITY_OK, {});

  rmw_qos_profile_t combined_error_publisher = compatible_publisher;
  combined_error_publisher.reliability = RMW_QOS_POLICY_RELIABILITY_BEST_EFFORT;
  rmw_qos_profile_t combined_error_subscription = compatible_subscription;
  combined_error_subscription.durability = RMW_QOS_POLICY_DURABILITY_TRANSIENT_LOCAL;
  std::string combined_error_reason;
  const bool combined_error_case_ok = compatibility_case(
    combined_error_publisher,
    combined_error_subscription,
    RMW_QOS_COMPATIBILITY_ERROR,
    {"best-effort", "transient-local"},
    &combined_error_reason);

  rmw_qos_profile_t deadline_missing_subscription = compatible_subscription;
  deadline_missing_subscription.deadline = rmw_time_t{0, 10000000};
  const bool deadline_missing_case_ok = compatibility_case(
    compatible_publisher,
    deadline_missing_subscription,
    RMW_QOS_COMPATIBILITY_ERROR,
    {"deadline but publisher does not"});

  rmw_qos_profile_t deadline_slow_publisher = compatible_publisher;
  deadline_slow_publisher.deadline = rmw_time_t{0, 20000000};
  rmw_qos_profile_t deadline_fast_subscription = compatible_subscription;
  deadline_fast_subscription.deadline = rmw_time_t{0, 10000000};
  const bool deadline_order_case_ok = compatibility_case(
    deadline_slow_publisher,
    deadline_fast_subscription,
    RMW_QOS_COMPATIBILITY_ERROR,
    {"deadline is less"});

  rmw_qos_profile_t manual_subscription = compatible_subscription;
  manual_subscription.liveliness = RMW_QOS_POLICY_LIVELINESS_MANUAL_BY_TOPIC;
  const bool liveliness_kind_case_ok = compatibility_case(
    compatible_publisher,
    manual_subscription,
    RMW_QOS_COMPATIBILITY_ERROR,
    {"manual-by-topic"});

  rmw_qos_profile_t lease_slow_publisher = compatible_publisher;
  lease_slow_publisher.liveliness_lease_duration = rmw_time_t{0, 20000000};
  rmw_qos_profile_t lease_fast_subscription = compatible_subscription;
  lease_fast_subscription.liveliness_lease_duration = rmw_time_t{0, 10000000};
  const bool lease_order_case_ok = compatibility_case(
    lease_slow_publisher,
    lease_fast_subscription,
    RMW_QOS_COMPATIBILITY_ERROR,
    {"subscription liveliness lease is less"});

  rmw_qos_profile_t warning_publisher = compatible_publisher;
  warning_publisher.reliability = RMW_QOS_POLICY_RELIABILITY_SYSTEM_DEFAULT;
  const bool warning_case_ok = compatibility_case(
    warning_publisher,
    compatible_subscription,
    RMW_QOS_COMPATIBILITY_WARNING,
    {"WARNING", "publisher reliability is unknown"});
  const bool compatibility_matrix_ok =
    compatible_case_ok && combined_error_case_ok && deadline_missing_case_ok &&
    deadline_order_case_ok && liveliness_kind_case_ok && lease_order_case_ok &&
    warning_case_ok;

  const rmw_ret_t first_fini_ret = rmw_serialized_message_fini(&first);
  const rmw_ret_t second_fini_ret = rmw_serialized_message_fini(&second);
  const rmw_ret_t depth_incoming_fini_ret = rmw_serialized_message_fini(&depth_incoming);
  const rmw_ret_t expired_fini_ret = rmw_serialized_message_fini(&expired);
  const rmw_ret_t lifespan_incoming_fini_ret = rmw_serialized_message_fini(&lifespan_incoming);
  const rmw_ret_t destroy_depth_pub_ret = rmw_destroy_publisher(node, depth_publisher);
  const rmw_ret_t destroy_depth_sub_ret = rmw_destroy_subscription(node, depth_subscription);
  const rmw_ret_t destroy_lifespan_pub_ret = rmw_destroy_publisher(node, lifespan_publisher);
  const rmw_ret_t destroy_lifespan_sub_ret =
    rmw_destroy_subscription(node, lifespan_subscription);
  const rmw_ret_t destroy_node_ret = rmw_destroy_node(node);
  cleanup_context(&context, &options);

  const bool cleanup_ok =
    first_fini_ret == RMW_RET_OK &&
    second_fini_ret == RMW_RET_OK &&
    depth_incoming_fini_ret == RMW_RET_OK &&
    expired_fini_ret == RMW_RET_OK &&
    lifespan_incoming_fini_ret == RMW_RET_OK &&
    destroy_depth_pub_ret == RMW_RET_OK &&
    destroy_depth_sub_ret == RMW_RET_OK &&
    destroy_lifespan_pub_ret == RMW_RET_OK &&
    destroy_lifespan_sub_ret == RMW_RET_OK &&
    destroy_node_ret == RMW_RET_OK;

  std::cout << "{\"schema_version\":\"fleetrmw.rmw_qos_probe.v2\",";
  std::cout << "\"status\":\"" <<
    (depth_ok && lifespan_ok && compatibility_matrix_ok && cleanup_ok ? "ok" : "failed") <<
    "\",";
  std::cout << "\"depth_topic\":\"" << depth_topic << "\",";
  std::cout << "\"depth_policy\":\"KEEP_LAST\",";
  std::cout << "\"depth_limit\":1,";
  std::cout << "\"depth_received_ready\":" << (depth_received_ready ? "true" : "false") << ",";
  std::cout << "\"depth_taken\":" << (depth_taken ? "true" : "false") << ",";
  std::cout << "\"depth_second_take\":" << (depth_second_take ? "true" : "false") << ",";
  std::cout << "\"depth_received\":\"" << json_escape(depth_received) << "\",";
  std::cout << "\"lifespan_topic\":\"" << lifespan_topic << "\",";
  std::cout << "\"lifespan_ns\":5000000,";
  std::cout << "\"lifespan_received_ready\":" << (lifespan_received_ready ? "true" : "false") << ",";
  std::cout << "\"lifespan_taken\":" << (lifespan_taken ? "true" : "false") << ",";
  std::cout << "\"lifespan_received\":\"" << json_escape(lifespan_received) << "\",";
  std::cout << "\"qos_compatibility_full_matrix\":" <<
    (compatibility_matrix_ok ? "true" : "false") << ",";
  std::cout << "\"qos_compatibility_error_reason_aggregation\":" <<
    (combined_error_case_ok ? "true" : "false") << ",";
  std::cout << "\"qos_compatibility_warning_semantics\":" <<
    (warning_case_ok ? "true" : "false") << ",";
  std::cout << "\"combined_error_reason\":\"" <<
    json_escape(combined_error_reason) << "\"}" << std::endl;

  return depth_ok && lifespan_ok && compatibility_matrix_ok && cleanup_ok ? 0 : 1;
}

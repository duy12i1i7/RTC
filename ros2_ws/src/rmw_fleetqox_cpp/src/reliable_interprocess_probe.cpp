#include <algorithm>
#include <chrono>
#include <cstdlib>
#include <cstdint>
#include <cstring>
#include <fstream>
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
#include "rmw/subscription_options.h"
#include "rosidl_runtime_c/message_type_support_struct.h"

extern "C" std::uint64_t rmw_fleetqox_cpp_socket_ack_nack_received();
extern "C" std::uint64_t rmw_fleetqox_cpp_socket_ack_nack_sent();
extern "C" std::uint64_t rmw_fleetqox_cpp_socket_ack_nack_duplicate_received();
extern "C" std::uint64_t rmw_fleetqox_cpp_socket_ack_nack_out_of_order_received();
extern "C" std::uint64_t rmw_fleetqox_cpp_socket_adaptive_failovers();
extern "C" std::uint64_t rmw_fleetqox_cpp_socket_adaptive_peer_score_sum();
extern "C" std::uint64_t rmw_fleetqox_cpp_socket_adaptive_redundant_frames();
extern "C" size_t rmw_fleetqox_cpp_socket_adaptive_selected_peer_index();
extern "C" std::uint64_t rmw_fleetqox_cpp_socket_adaptive_unicast_frames();
extern "C" std::uint64_t rmw_fleetqox_cpp_socket_fleet_plan_frames();
extern "C" const char * rmw_fleetqox_cpp_socket_fleet_plan_last_paths();
extern "C" std::uint64_t rmw_fleetqox_cpp_socket_fleet_plan_redundant_frames();
extern "C" std::uint64_t rmw_fleetqox_cpp_socket_fleet_plan_selected_path_count();
extern "C" std::uint64_t rmw_fleetqox_cpp_socket_frames_received();
extern "C" std::uint64_t rmw_fleetqox_cpp_socket_frames_sent();
extern "C" std::uint64_t rmw_fleetqox_cpp_socket_idle_repair_ack_nack_sent();
extern "C" std::uint64_t rmw_fleetqox_cpp_socket_nack_retransmissions();
extern "C" std::uint64_t rmw_fleetqox_cpp_duplicate_data_frames_deduped();
extern "C" std::uint64_t rmw_fleetqox_cpp_out_of_order_data_frames_observed();
extern "C" std::uint64_t rmw_fleetqox_cpp_last_take_source_sequence();
extern "C" std::int64_t rmw_fleetqox_cpp_last_take_source_timestamp_ns();
extern "C" std::int64_t rmw_fleetqox_cpp_last_take_timestamp_ns();
extern "C" const char * rmw_fleetqox_cpp_last_take_topic();
extern "C" const char * rmw_fleetqox_cpp_last_take_publisher_id();
extern "C" const char * rmw_fleetqox_cpp_socket_bound_endpoint();
extern "C" const char * rmw_fleetqox_cpp_socket_peer_policy();
extern "C" size_t rmw_fleetqox_cpp_socket_peer_count();

namespace
{

struct Config
{
  std::string mode{"subscriber"};
  std::string topic{"/fleetqox/reliable_interprocess_probe"};
  int timeout_ms{5000};
  int hold_ms{3000};
  int pre_publish_wait_ms{0};
  int publish_interval_ms{20};
  int pre_payload_warmup_count{0};
  std::string pre_payload_warmup_payload{"route_warmup"};
  int pre_payload_warmup_ack_count{0};
  int pre_payload_warmup_ack_timeout_ms{0};
  int app_repair_cycle_count{0};
  std::string app_repair_cycle_payloads{"one,two,three"};
  int tail_repair_repeat_count{0};
  std::string tail_repair_payload{"three"};
  int min_ack_nack_received{2};
  int min_ack_nack_sent{3};
  int min_retransmissions{1};
  int deadline_ms{0};
  int plan_update_after_publishes{-1};
  std::string post_recovery_payload;
  bool post_recovery_before_hold{false};
  int post_recovery_repeat_count{1};
  int post_payload_wait_ms{0};
  bool require_post_recovery_payload{false};
  std::string plan_update_text;
  std::string subscriber_telemetry_file;
  std::string robot_id{"robot_0000"};
  int subscriber_deadline_ms{0};
};

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

Config parse_args(int argc, char ** argv)
{
  Config config;
  for (int i = 1; i < argc; ++i) {
    const std::string arg = argv[i];
    if (arg == "--mode" && i + 1 < argc) {
      config.mode = argv[++i];
    } else if (arg == "--topic" && i + 1 < argc) {
      config.topic = argv[++i];
    } else if (arg == "--timeout-ms" && i + 1 < argc) {
      config.timeout_ms = std::stoi(argv[++i]);
    } else if (arg == "--hold-ms" && i + 1 < argc) {
      config.hold_ms = std::stoi(argv[++i]);
    } else if (arg == "--pre-publish-wait-ms" && i + 1 < argc) {
      config.pre_publish_wait_ms = std::stoi(argv[++i]);
    } else if (arg == "--publish-interval-ms" && i + 1 < argc) {
      config.publish_interval_ms = std::stoi(argv[++i]);
    } else if (arg == "--pre-payload-warmup-count" && i + 1 < argc) {
      config.pre_payload_warmup_count = std::stoi(argv[++i]);
    } else if (arg == "--pre-payload-warmup-payload" && i + 1 < argc) {
      config.pre_payload_warmup_payload = argv[++i];
    } else if (arg == "--pre-payload-warmup-ack-count" && i + 1 < argc) {
      config.pre_payload_warmup_ack_count = std::stoi(argv[++i]);
    } else if (arg == "--pre-payload-warmup-ack-timeout-ms" && i + 1 < argc) {
      config.pre_payload_warmup_ack_timeout_ms = std::stoi(argv[++i]);
    } else if (arg == "--app-repair-cycle-count" && i + 1 < argc) {
      config.app_repair_cycle_count = std::stoi(argv[++i]);
    } else if (arg == "--app-repair-cycle-payloads" && i + 1 < argc) {
      config.app_repair_cycle_payloads = argv[++i];
    } else if (arg == "--tail-repair-repeat-count" && i + 1 < argc) {
      config.tail_repair_repeat_count = std::stoi(argv[++i]);
    } else if (arg == "--tail-repair-payload" && i + 1 < argc) {
      config.tail_repair_payload = argv[++i];
    } else if (arg == "--min-ack-nack-received" && i + 1 < argc) {
      config.min_ack_nack_received = std::stoi(argv[++i]);
    } else if (arg == "--min-ack-nack-sent" && i + 1 < argc) {
      config.min_ack_nack_sent = std::stoi(argv[++i]);
    } else if (arg == "--min-retransmissions" && i + 1 < argc) {
      config.min_retransmissions = std::stoi(argv[++i]);
    } else if (arg == "--deadline-ms" && i + 1 < argc) {
      config.deadline_ms = std::stoi(argv[++i]);
    } else if (arg == "--plan-update-after-publishes" && i + 1 < argc) {
      config.plan_update_after_publishes = std::stoi(argv[++i]);
    } else if (arg == "--plan-update-text" && i + 1 < argc) {
      config.plan_update_text = argv[++i];
    } else if (arg == "--subscriber-telemetry-file" && i + 1 < argc) {
      config.subscriber_telemetry_file = argv[++i];
    } else if (arg == "--robot-id" && i + 1 < argc) {
      config.robot_id = argv[++i];
    } else if (arg == "--subscriber-deadline-ms" && i + 1 < argc) {
      config.subscriber_deadline_ms = std::stoi(argv[++i]);
    } else if (arg == "--post-recovery-payload" && i + 1 < argc) {
      config.post_recovery_payload = argv[++i];
    } else if (arg == "--post-recovery-before-hold") {
      config.post_recovery_before_hold = true;
    } else if (arg == "--post-recovery-repeat-count" && i + 1 < argc) {
      config.post_recovery_repeat_count = std::stoi(argv[++i]);
    } else if (arg == "--post-payload-wait-ms" && i + 1 < argc) {
      config.post_payload_wait_ms = std::stoi(argv[++i]);
    } else if (arg == "--require-post-recovery-payload") {
      config.require_post_recovery_payload = true;
    }
  }
  return config;
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

bool init_context(
  rcutils_allocator_t allocator,
  rmw_init_options_t * options,
  rmw_context_t * context)
{
  *options = rmw_get_zero_initialized_init_options();
  if (rmw_init_options_init(options, allocator) != RMW_RET_OK) {
    return false;
  }
  options->instance_id = 49;
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

void print_result(
  const Config & config,
  const std::string & status,
  const std::vector<std::string> & payloads)
{
  std::cout << "{\"schema_version\":\"fleetrmw.rmw_reliable_interprocess_probe.v1\",";
  std::cout << "\"status\":\"" << status << "\",";
  std::cout << "\"mode\":\"" << config.mode << "\",";
  std::cout << "\"topic\":\"" << json_escape(config.topic) << "\",";
  std::cout << "\"endpoint\":\"" << json_escape(rmw_fleetqox_cpp_socket_bound_endpoint()) << "\",";
  std::cout << "\"peer_count\":" << rmw_fleetqox_cpp_socket_peer_count() << ",";
  std::cout << "\"peer_policy\":\"" << json_escape(rmw_fleetqox_cpp_socket_peer_policy()) << "\",";
  std::cout << "\"adaptive_failovers\":" << rmw_fleetqox_cpp_socket_adaptive_failovers() << ",";
  std::cout << "\"adaptive_unicast_frames\":" << rmw_fleetqox_cpp_socket_adaptive_unicast_frames() << ",";
  std::cout << "\"adaptive_redundant_frames\":" <<
    rmw_fleetqox_cpp_socket_adaptive_redundant_frames() << ",";
  std::cout << "\"adaptive_peer_score_sum\":" <<
    rmw_fleetqox_cpp_socket_adaptive_peer_score_sum() << ",";
  std::cout << "\"adaptive_selected_peer_index\":" <<
    rmw_fleetqox_cpp_socket_adaptive_selected_peer_index() << ",";
  std::cout << "\"fleet_plan_frames\":" << rmw_fleetqox_cpp_socket_fleet_plan_frames() << ",";
  std::cout << "\"fleet_plan_redundant_frames\":" <<
    rmw_fleetqox_cpp_socket_fleet_plan_redundant_frames() << ",";
  std::cout << "\"fleet_plan_selected_path_count\":" <<
    rmw_fleetqox_cpp_socket_fleet_plan_selected_path_count() << ",";
  std::cout << "\"fleet_plan_last_paths\":\"" <<
    json_escape(rmw_fleetqox_cpp_socket_fleet_plan_last_paths()) << "\",";
  std::cout << "\"deadline_ms\":" << config.deadline_ms << ",";
  std::cout << "\"pre_publish_wait_ms\":" << std::max(config.pre_publish_wait_ms, 0) << ",";
  std::cout << "\"publish_interval_ms\":" << config.publish_interval_ms << ",";
  std::cout << "\"pre_payload_warmup_count\":" <<
    std::max(config.pre_payload_warmup_count, 0) << ",";
  std::cout << "\"pre_payload_warmup_payload\":\"" <<
    json_escape(config.pre_payload_warmup_payload) << "\",";
  std::cout << "\"pre_payload_warmup_ack_count\":" <<
    std::max(config.pre_payload_warmup_ack_count, 0) << ",";
  std::cout << "\"pre_payload_warmup_ack_timeout_ms\":" <<
    std::max(config.pre_payload_warmup_ack_timeout_ms, 0) << ",";
  std::cout << "\"app_repair_cycle_count\":" <<
    std::max(config.app_repair_cycle_count, 0) << ",";
  std::cout << "\"app_repair_cycle_payloads\":\"" <<
    json_escape(config.app_repair_cycle_payloads) << "\",";
  std::cout << "\"tail_repair_repeat_count\":" <<
    std::max(config.tail_repair_repeat_count, 0) << ",";
  std::cout << "\"tail_repair_payload\":\"" <<
    json_escape(config.tail_repair_payload) << "\",";
  std::cout << "\"plan_update_after_publishes\":" << config.plan_update_after_publishes << ",";
  std::cout << "\"plan_update_text\":\"" << json_escape(config.plan_update_text) << "\",";
  std::cout << "\"post_recovery_payload\":\"" << json_escape(config.post_recovery_payload) << "\",";
  std::cout << "\"post_recovery_before_hold\":" <<
    (config.post_recovery_before_hold ? "true" : "false") << ",";
  std::cout << "\"post_recovery_repeat_count\":" <<
    std::max(config.post_recovery_repeat_count, 0) << ",";
  std::cout << "\"post_payload_wait_ms\":" << std::max(config.post_payload_wait_ms, 0) << ",";
  std::cout << "\"require_post_recovery_payload\":" <<
    (config.require_post_recovery_payload ? "true" : "false") << ",";
  std::cout << "\"subscriber_telemetry_file\":\"" <<
    json_escape(config.subscriber_telemetry_file) << "\",";
  std::cout << "\"robot_id\":\"" << json_escape(config.robot_id) << "\",";
  std::cout << "\"subscriber_deadline_ms\":" << config.subscriber_deadline_ms << ",";
  std::cout << "\"min_ack_nack_received\":" << config.min_ack_nack_received << ",";
  std::cout << "\"min_ack_nack_sent\":" << config.min_ack_nack_sent << ",";
  std::cout << "\"min_retransmissions\":" << config.min_retransmissions << ",";
  std::cout << "\"socket_frames_sent\":" << rmw_fleetqox_cpp_socket_frames_sent() << ",";
  std::cout << "\"socket_frames_received\":" << rmw_fleetqox_cpp_socket_frames_received() << ",";
  std::cout << "\"ack_nack_sent\":" << rmw_fleetqox_cpp_socket_ack_nack_sent() << ",";
  std::cout << "\"ack_nack_received\":" << rmw_fleetqox_cpp_socket_ack_nack_received() << ",";
  std::cout << "\"ack_nack_duplicate_received\":" <<
    rmw_fleetqox_cpp_socket_ack_nack_duplicate_received() << ",";
  std::cout << "\"ack_nack_out_of_order_received\":" <<
    rmw_fleetqox_cpp_socket_ack_nack_out_of_order_received() << ",";
  std::cout << "\"idle_repair_ack_nack_sent\":" <<
    rmw_fleetqox_cpp_socket_idle_repair_ack_nack_sent() << ",";
  std::cout << "\"nack_retransmissions\":" << rmw_fleetqox_cpp_socket_nack_retransmissions() << ",";
  std::cout << "\"duplicate_data_frames_deduped\":" <<
    rmw_fleetqox_cpp_duplicate_data_frames_deduped() << ",";
  std::cout << "\"out_of_order_data_frames_observed\":" <<
    rmw_fleetqox_cpp_out_of_order_data_frames_observed() << ",";
  std::cout << "\"payloads\":[";
  for (size_t i = 0; i < payloads.size(); ++i) {
    if (i > 0) {
      std::cout << ",";
    }
    std::cout << "\"" << json_escape(payloads[i]) << "\"";
  }
  std::cout << "]}" << std::endl;
}

std::vector<std::string> required_payloads(const Config & config)
{
  std::vector<std::string> payloads{"one", "two", "three"};
  if (config.require_post_recovery_payload && !config.post_recovery_payload.empty()) {
    payloads.push_back(config.post_recovery_payload);
  }
  return payloads;
}

bool has_all_payloads(
  const Config & config,
  const std::vector<std::string> & payloads)
{
  for (const std::string & required : required_payloads(config)) {
    if (std::find(payloads.begin(), payloads.end(), required) == payloads.end()) {
      return false;
    }
  }
  return true;
}

void maybe_update_plan_file(const Config & config, size_t published_count)
{
  if (config.plan_update_text.empty() ||
    config.plan_update_after_publishes < 0 ||
    published_count != static_cast<size_t>(config.plan_update_after_publishes))
  {
    return;
  }
  const char * plan_file = std::getenv("FLEETQOX_RMW_FLEET_PATH_PLAN_FILE");
  if (plan_file == nullptr || plan_file[0] == '\0') {
    return;
  }
  std::ofstream output(plan_file);
  if (!output) {
    return;
  }
  output << config.plan_update_text << std::endl;
}

void append_subscriber_telemetry(const Config & config, const std::string & payload)
{
  if (config.subscriber_telemetry_file.empty()) {
    return;
  }
  std::ofstream out(config.subscriber_telemetry_file, std::ios::app);
  if (!out) {
    return;
  }
  const std::int64_t source_timestamp_ns = rmw_fleetqox_cpp_last_take_source_timestamp_ns();
  const std::int64_t take_timestamp_ns = rmw_fleetqox_cpp_last_take_timestamp_ns();
  const double latency_ms =
    source_timestamp_ns > 0 && take_timestamp_ns >= source_timestamp_ns ?
    static_cast<double>(take_timestamp_ns - source_timestamp_ns) / 1000000.0 : 0.0;
  const bool deadline_missed =
    config.subscriber_deadline_ms > 0 && latency_ms > static_cast<double>(config.subscriber_deadline_ms);
  out << "{\"schema_version\":\"fleetrmw.subscriber_delivery_telemetry.v1\",";
  out << "\"event\":\"take\",";
  out << "\"robot_id\":\"" << json_escape(config.robot_id) << "\",";
  out << "\"topic\":\"" << json_escape(rmw_fleetqox_cpp_last_take_topic()) << "\",";
  out << "\"publisher_id\":\"" << json_escape(rmw_fleetqox_cpp_last_take_publisher_id()) << "\",";
  out << "\"source_sequence_number\":" << rmw_fleetqox_cpp_last_take_source_sequence() << ",";
  out << "\"source_timestamp_ns\":" << source_timestamp_ns << ",";
  out << "\"take_timestamp_ns\":" << take_timestamp_ns << ",";
  out << "\"latency_ms\":" << latency_ms << ",";
  out << "\"deadline_ms\":" << config.subscriber_deadline_ms << ",";
  out << "\"deadline_missed\":" << (deadline_missed ? "true" : "false") << ",";
  out << "\"delivered\":true,";
  out << "\"duplicate\":false,";
  out << "\"payload\":\"" << json_escape(payload) << "\"";
  out << "}" << std::endl;
}

bool publish_payload_once(
  rmw_publisher_t * publisher,
  const std::string & payload,
  rcutils_allocator_t * allocator)
{
  rmw_serialized_message_t message = rmw_get_zero_initialized_serialized_message();
  const bool message_ok = init_message(&message, payload, allocator);
  bool publish_ok = false;
  if (message_ok && publisher != nullptr) {
    publish_ok = rmw_publish_serialized_message(publisher, &message, nullptr) == RMW_RET_OK;
  }
  if (message_ok) {
    const rmw_ret_t fini_ret = rmw_serialized_message_fini(&message);
    (void)fini_ret;
  }
  return message_ok && publish_ok;
}

std::vector<std::string> split_payloads(const std::string & text)
{
  std::vector<std::string> values;
  size_t start = 0;
  while (start <= text.size()) {
    const size_t comma = text.find(',', start);
    const std::string value = text.substr(
      start,
      comma == std::string::npos ? std::string::npos : comma - start);
    if (!value.empty()) {
      values.push_back(value);
    }
    if (comma == std::string::npos) {
      break;
    }
    start = comma + 1;
  }
  return values;
}

int run_publisher(const Config & config)
{
  rcutils_allocator_t allocator = rcutils_get_default_allocator();
  rmw_init_options_t options{};
  rmw_context_t context{};
  if (!init_context(allocator, &options, &context)) {
    print_result(config, "init_failed", {});
    return 1;
  }
  rmw_node_t * node = rmw_create_node(&context, "fleetqox_reliable_publisher", "/fleetqox");
  rosidl_message_type_support_t type_support{};
  type_support.typesupport_identifier = "rmw_fleetqox_cpp_reliable_interprocess_probe";
  rmw_publisher_options_t publisher_options = rmw_get_default_publisher_options();
  rmw_qos_profile_t qos = rmw_qos_profile_default;
  if (config.deadline_ms > 0) {
    qos.deadline.sec = static_cast<std::uint64_t>(config.deadline_ms / 1000);
    qos.deadline.nsec = static_cast<std::uint64_t>((config.deadline_ms % 1000) * 1000000);
  }
  rmw_publisher_t * publisher = node == nullptr ? nullptr :
    rmw_create_publisher(node, &type_support, config.topic.c_str(), &qos, &publisher_options);

  std::vector<rmw_serialized_message_t> messages(3);
  const std::vector<std::string> payloads{"one", "two", "three"};
  bool messages_ok = true;
  for (size_t i = 0; i < payloads.size(); ++i) {
    messages_ok = init_message(&messages[i], payloads[i], &allocator) && messages_ok;
  }

  bool publish_ok = publisher != nullptr && messages_ok;
  if (config.pre_publish_wait_ms > 0) {
    std::this_thread::sleep_for(std::chrono::milliseconds(config.pre_publish_wait_ms));
  }
  for (int i = 0; i < std::max(config.pre_payload_warmup_count, 0); ++i) {
    publish_ok =
      publish_payload_once(publisher, config.pre_payload_warmup_payload, &allocator) &&
      publish_ok;
    std::this_thread::sleep_for(std::chrono::milliseconds(std::max(config.publish_interval_ms, 0)));
  }
  const auto warmup_ack_deadline =
    std::chrono::steady_clock::now() +
    std::chrono::milliseconds(std::max(config.pre_payload_warmup_ack_timeout_ms, 0));
  while (
    config.pre_payload_warmup_ack_count > 0 &&
    config.pre_payload_warmup_ack_timeout_ms > 0 &&
    rmw_fleetqox_cpp_socket_ack_nack_received() <
      static_cast<std::uint64_t>(std::max(config.pre_payload_warmup_ack_count, 0)) &&
    std::chrono::steady_clock::now() < warmup_ack_deadline)
  {
    publish_ok =
      publish_payload_once(publisher, config.pre_payload_warmup_payload, &allocator) &&
      publish_ok;
    std::this_thread::sleep_for(std::chrono::milliseconds(std::max(config.publish_interval_ms, 0)));
  }
  size_t published_count = 0;
  for (rmw_serialized_message_t & message : messages) {
    publish_ok = rmw_publish_serialized_message(publisher, &message, nullptr) == RMW_RET_OK && publish_ok;
    ++published_count;
    maybe_update_plan_file(config, published_count);
    std::this_thread::sleep_for(std::chrono::milliseconds(std::max(config.publish_interval_ms, 0)));
  }

  const std::vector<std::string> app_repair_payloads =
    split_payloads(config.app_repair_cycle_payloads);
  for (int cycle = 0; cycle < std::max(config.app_repair_cycle_count, 0); ++cycle) {
    for (const std::string & payload : app_repair_payloads) {
      publish_ok = publish_payload_once(publisher, payload, &allocator) && publish_ok;
      std::this_thread::sleep_for(std::chrono::milliseconds(std::max(config.publish_interval_ms, 0)));
    }
  }

  for (int i = 0; i < std::max(config.tail_repair_repeat_count, 0); ++i) {
    publish_ok =
      publish_payload_once(publisher, config.tail_repair_payload, &allocator) &&
      publish_ok;
    std::this_thread::sleep_for(std::chrono::milliseconds(std::max(config.publish_interval_ms, 0)));
  }

  if (!config.post_recovery_payload.empty() && config.post_recovery_before_hold) {
    for (int i = 0; i < std::max(config.post_recovery_repeat_count, 1); ++i) {
      publish_ok =
        publish_payload_once(publisher, config.post_recovery_payload, &allocator) &&
        publish_ok;
      std::this_thread::sleep_for(std::chrono::milliseconds(std::max(config.publish_interval_ms, 0)));
    }
  }

  const auto deadline = std::chrono::steady_clock::now() + std::chrono::milliseconds(config.hold_ms);
  while (std::chrono::steady_clock::now() < deadline &&
    (rmw_fleetqox_cpp_socket_ack_nack_received() <
      static_cast<std::uint64_t>(std::max(config.min_ack_nack_received, 0)) ||
    rmw_fleetqox_cpp_socket_nack_retransmissions() <
      static_cast<std::uint64_t>(std::max(config.min_retransmissions, 0))))
  {
    std::this_thread::sleep_for(std::chrono::milliseconds(10));
  }

  if (!config.post_recovery_payload.empty() && !config.post_recovery_before_hold) {
    for (int i = 0; i < std::max(config.post_recovery_repeat_count, 1); ++i) {
      publish_ok =
        publish_payload_once(publisher, config.post_recovery_payload, &allocator) &&
        publish_ok;
      std::this_thread::sleep_for(std::chrono::milliseconds(std::max(config.publish_interval_ms, 0)));
    }
  }

  const bool ok = publish_ok &&
    rmw_fleetqox_cpp_socket_ack_nack_received() >=
      static_cast<std::uint64_t>(std::max(config.min_ack_nack_received, 0)) &&
    rmw_fleetqox_cpp_socket_nack_retransmissions() >=
      static_cast<std::uint64_t>(std::max(config.min_retransmissions, 0));
  std::vector<std::string> reported_payloads = payloads;
  if (!config.post_recovery_payload.empty()) {
    for (int i = 0; i < std::max(config.post_recovery_repeat_count, 1); ++i) {
      reported_payloads.push_back(config.post_recovery_payload);
    }
  }
  print_result(config, ok ? "ok" : "failed", reported_payloads);

  for (rmw_serialized_message_t & message : messages) {
    const rmw_ret_t fini_ret = rmw_serialized_message_fini(&message);
    (void)fini_ret;
  }
  if (publisher != nullptr) {
    const rmw_ret_t destroy_pub_ret = rmw_destroy_publisher(node, publisher);
    (void)destroy_pub_ret;
  }
  if (node != nullptr) {
    const rmw_ret_t destroy_node_ret = rmw_destroy_node(node);
    (void)destroy_node_ret;
  }
  cleanup_context(&context, &options);
  return ok ? 0 : 1;
}

int run_subscriber(const Config & config)
{
  rcutils_allocator_t allocator = rcutils_get_default_allocator();
  rmw_init_options_t options{};
  rmw_context_t context{};
  if (!init_context(allocator, &options, &context)) {
    print_result(config, "init_failed", {});
    return 1;
  }
  rmw_node_t * node = rmw_create_node(&context, "fleetqox_reliable_subscriber", "/fleetqox");
  rosidl_message_type_support_t type_support{};
  type_support.typesupport_identifier = "rmw_fleetqox_cpp_reliable_interprocess_probe";
  rmw_subscription_options_t subscription_options = rmw_get_default_subscription_options();
  rmw_qos_profile_t qos = rmw_qos_profile_default;
  if (config.deadline_ms > 0) {
    qos.deadline.sec = static_cast<std::uint64_t>(config.deadline_ms / 1000);
    qos.deadline.nsec = static_cast<std::uint64_t>((config.deadline_ms % 1000) * 1000000);
  }
  rmw_subscription_t * subscription = node == nullptr ? nullptr :
    rmw_create_subscription(node, &type_support, config.topic.c_str(), &qos, &subscription_options);

  rmw_serialized_message_t incoming = rmw_get_zero_initialized_serialized_message();
  const bool message_ok = rmw_serialized_message_init(&incoming, 1, &allocator) == RMW_RET_OK;
  std::vector<std::string> payloads;
  rmw_ret_t take_ret = RMW_RET_OK;
  const auto deadline = std::chrono::steady_clock::now() + std::chrono::milliseconds(config.timeout_ms);
  bool app_payloads_seen = false;
  auto app_payloads_seen_at = std::chrono::steady_clock::time_point{};
  while (subscription != nullptr && message_ok && std::chrono::steady_clock::now() < deadline) {
    bool taken = false;
    take_ret = rmw_take_serialized_message(subscription, &incoming, &taken, nullptr);
    if (take_ret != RMW_RET_OK) {
      break;
    }
    if (taken) {
      const std::string payload = message_string(incoming);
      payloads.push_back(payload);
      append_subscriber_telemetry(config, payload);
      if (has_all_payloads(config, payloads)) {
        if (
          config.require_post_recovery_payload ||
          config.post_recovery_payload.empty() ||
          config.post_payload_wait_ms <= 0 ||
          std::find(
            payloads.begin(), payloads.end(), config.post_recovery_payload) != payloads.end())
        {
          break;
        }
        if (!app_payloads_seen) {
          app_payloads_seen = true;
          app_payloads_seen_at = std::chrono::steady_clock::now();
        }
      }
    }
    if (app_payloads_seen) {
      const auto elapsed = std::chrono::duration_cast<std::chrono::milliseconds>(
        std::chrono::steady_clock::now() - app_payloads_seen_at);
      if (elapsed.count() >= std::max(config.post_payload_wait_ms, 0)) {
        break;
      }
    }
    std::this_thread::sleep_for(std::chrono::milliseconds(1));
  }

  const bool ok = take_ret == RMW_RET_OK && has_all_payloads(config, payloads) &&
                  rmw_fleetqox_cpp_socket_ack_nack_sent() >=
                  static_cast<std::uint64_t>(std::max(config.min_ack_nack_sent, 0));
  print_result(config, ok ? "ok" : "failed", payloads);

  if (message_ok) {
    const rmw_ret_t fini_ret = rmw_serialized_message_fini(&incoming);
    (void)fini_ret;
  }
  if (subscription != nullptr) {
    const rmw_ret_t destroy_sub_ret = rmw_destroy_subscription(node, subscription);
    (void)destroy_sub_ret;
  }
  if (node != nullptr) {
    const rmw_ret_t destroy_node_ret = rmw_destroy_node(node);
    (void)destroy_node_ret;
  }
  cleanup_context(&context, &options);
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
  print_result(config, "invalid_mode", {});
  return 1;
}

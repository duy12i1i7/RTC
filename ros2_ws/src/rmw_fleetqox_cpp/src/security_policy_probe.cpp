#include <chrono>
#include <cstdint>
#include <cstring>
#include <cstdlib>
#include <iostream>
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

extern "C" std::uint64_t rmw_fleetqox_cpp_security_policy_denied();

namespace
{

constexpr const char * kSchema = "fleetrmw.security_policy_probe.v1";
constexpr const char * kAllowedTopic = "/fleetqox/security_allowed";
constexpr const char * kDeniedTopic = "/fleetqox/security_denied";

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

bool wait_take(
  const rmw_subscription_t * subscription,
  rmw_serialized_message_t * incoming,
  std::string * received)
{
  bool taken = false;
  for (int attempt = 0; attempt < 100 && !taken; ++attempt) {
    const rmw_ret_t ret = rmw_take_serialized_message(subscription, incoming, &taken, nullptr);
    if (ret != RMW_RET_OK) {
      return false;
    }
    if (taken) {
      break;
    }
    std::this_thread::sleep_for(std::chrono::milliseconds(1));
  }
  if (taken && incoming != nullptr && incoming->buffer != nullptr && received != nullptr) {
    received->assign(
      reinterpret_cast<const char *>(incoming->buffer),
      reinterpret_cast<const char *>(incoming->buffer + incoming->buffer_length));
  }
  return taken;
}

bool take_once_no_message(
  const rmw_subscription_t * subscription,
  rmw_serialized_message_t * incoming)
{
  bool taken = true;
  const rmw_ret_t ret = rmw_take_serialized_message(subscription, incoming, &taken, nullptr);
  return ret == RMW_RET_OK && !taken;
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
  const char * policy = std::getenv("FLEETQOX_RMW_SECURITY_POLICY");
  rcutils_allocator_t allocator = rcutils_get_default_allocator();
  rmw_init_options_t options = rmw_get_zero_initialized_init_options();
  if (rmw_init_options_init(&options, allocator) != RMW_RET_OK) {
    std::cout << "{\"status\":\"init_options_failed\"}" << std::endl;
    return 1;
  }
  options.instance_id = 87;

  rmw_context_t context = rmw_get_zero_initialized_context();
  if (rmw_init(&options, &context) != RMW_RET_OK) {
    const rmw_ret_t fini_ret = rmw_init_options_fini(&options);
    (void)fini_ret;
    std::cout << "{\"status\":\"init_failed\"}" << std::endl;
    return 1;
  }

  rmw_node_t * node = rmw_create_node(&context, "fleetqox_security_policy_probe", "/fleetqox");
  if (node == nullptr) {
    cleanup_context(&context, &options);
    std::cout << "{\"status\":\"create_node_failed\"}" << std::endl;
    return 1;
  }

  rosidl_message_type_support_t type_support{};
  type_support.typesupport_identifier = "rmw_fleetqox_cpp_security_policy_probe";
  rmw_publisher_options_t publisher_options = rmw_get_default_publisher_options();
  rmw_subscription_options_t subscription_options = rmw_get_default_subscription_options();
  rmw_qos_profile_t qos = rmw_qos_profile_default;

  rmw_publisher_t * allowed_publisher =
    rmw_create_publisher(node, &type_support, kAllowedTopic, &qos, &publisher_options);
  rmw_subscription_t * allowed_subscription =
    rmw_create_subscription(node, &type_support, kAllowedTopic, &qos, &subscription_options);
  rmw_publisher_t * denied_publisher =
    rmw_create_publisher(node, &type_support, kDeniedTopic, &qos, &publisher_options);
  rmw_subscription_t * denied_subscription =
    rmw_create_subscription(node, &type_support, kDeniedTopic, &qos, &subscription_options);
  if (
    allowed_publisher == nullptr || allowed_subscription == nullptr ||
    denied_publisher == nullptr || denied_subscription == nullptr)
  {
    std::cout << "{\"status\":\"create_pubsub_failed\"}" << std::endl;
    return 1;
  }

  rmw_serialized_message_t allowed_out = rmw_get_zero_initialized_serialized_message();
  rmw_serialized_message_t denied_out = rmw_get_zero_initialized_serialized_message();
  rmw_serialized_message_t allowed_in = rmw_get_zero_initialized_serialized_message();
  rmw_serialized_message_t denied_in = rmw_get_zero_initialized_serialized_message();
  const std::string allowed_payload = "allowed-security-payload";
  const std::string denied_payload = "denied-security-payload";
  if (
    !init_serialized_message(&allowed_out, allowed_payload, &allocator) ||
    !init_serialized_message(&denied_out, denied_payload, &allocator) ||
    rmw_serialized_message_init(&allowed_in, 1, &allocator) != RMW_RET_OK ||
    rmw_serialized_message_init(&denied_in, 1, &allocator) != RMW_RET_OK)
  {
    std::cout << "{\"status\":\"serialized_message_init_failed\"}" << std::endl;
    return 1;
  }

  const std::uint64_t denied_before = rmw_fleetqox_cpp_security_policy_denied();
  const rmw_ret_t allowed_ret =
    rmw_publish_serialized_message(allowed_publisher, &allowed_out, nullptr);
  std::string received;
  const bool allowed_taken =
    allowed_ret == RMW_RET_OK && wait_take(allowed_subscription, &allowed_in, &received);
  const rmw_ret_t denied_ret =
    rmw_publish_serialized_message(denied_publisher, &denied_out, nullptr);
  const bool denied_taken = !take_once_no_message(denied_subscription, &denied_in);
  const std::uint64_t denied_delta =
    rmw_fleetqox_cpp_security_policy_denied() - denied_before;

  const bool allowed_ok =
    allowed_ret == RMW_RET_OK && allowed_taken && received == allowed_payload;
  const bool denied_ok = denied_ret != RMW_RET_OK && denied_delta == 1 && !denied_taken;
  const bool policy_configured = policy != nullptr && policy[0] != '\0';
  const bool ok = policy_configured && allowed_ok && denied_ok;

  std::cout << "{\"schema_version\":\"" << kSchema << "\",";
  std::cout << "\"status\":\"" << (ok ? "ok" : "failed") << "\",";
  std::cout << "\"policy_configured\":" << (policy_configured ? "true" : "false") << ",";
  std::cout << "\"policy\":\"" << json_escape(policy == nullptr ? "" : policy) << "\",";
  std::cout << "\"allowed_topic\":\"" << kAllowedTopic << "\",";
  std::cout << "\"denied_topic\":\"" << kDeniedTopic << "\",";
  std::cout << "\"allowed_publish_returncode\":" << static_cast<int>(allowed_ret) << ",";
  std::cout << "\"allowed_taken\":" << (allowed_taken ? "true" : "false") << ",";
  std::cout << "\"allowed_payload_ok\":" << (received == allowed_payload ? "true" : "false") << ",";
  std::cout << "\"denied_publish_returncode\":" << static_cast<int>(denied_ret) << ",";
  std::cout << "\"denied_taken\":" << (denied_taken ? "true" : "false") << ",";
  std::cout << "\"security_policy_denied_delta\":" << denied_delta << ",";
  std::cout << "\"fleetqox_security_policy_enforcement_claim\":" << (ok ? "true" : "false") << ",";
  std::cout << "\"security_policy_enforcement_scope\":\"fleetqox_publish_allow_deny_env_policy\",";
  std::cout << "\"sros2_policy_enforcement_claim\":false,";
  std::cout << "\"production_security_hardening_claim\":false}" << std::endl;

  const rmw_ret_t allowed_out_fini = rmw_serialized_message_fini(&allowed_out);
  const rmw_ret_t denied_out_fini = rmw_serialized_message_fini(&denied_out);
  const rmw_ret_t allowed_in_fini = rmw_serialized_message_fini(&allowed_in);
  const rmw_ret_t denied_in_fini = rmw_serialized_message_fini(&denied_in);
  const rmw_ret_t destroy_allowed_pub = rmw_destroy_publisher(node, allowed_publisher);
  const rmw_ret_t destroy_allowed_sub = rmw_destroy_subscription(node, allowed_subscription);
  const rmw_ret_t destroy_denied_pub = rmw_destroy_publisher(node, denied_publisher);
  const rmw_ret_t destroy_denied_sub = rmw_destroy_subscription(node, denied_subscription);
  const rmw_ret_t destroy_node = rmw_destroy_node(node);
  cleanup_context(&context, &options);
  return ok &&
         allowed_out_fini == RMW_RET_OK &&
         denied_out_fini == RMW_RET_OK &&
         allowed_in_fini == RMW_RET_OK &&
         denied_in_fini == RMW_RET_OK &&
         destroy_allowed_pub == RMW_RET_OK &&
         destroy_allowed_sub == RMW_RET_OK &&
         destroy_denied_pub == RMW_RET_OK &&
         destroy_denied_sub == RMW_RET_OK &&
         destroy_node == RMW_RET_OK ? 0 : 1;
}

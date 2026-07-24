#include <chrono>
#include <cstdint>
#include <cstring>
#include <cstdlib>
#include <iostream>
#include <sstream>
#include <string>
#include <thread>

#include "rcutils/allocator.h"
#include "rcutils/strdup.h"
#include "rmw/init.h"
#include "rmw/init_options.h"
#include "rmw/publisher_options.h"
#include "rmw/qos_profiles.h"
#include "rmw/rmw.h"
#include "rmw/serialized_message.h"
#include "rmw/subscription_options.h"
#include "rosidl_runtime_c/message_type_support_struct.h"

extern "C" bool rmw_fleetqox_cpp_sros2_governance_xml_loaded();
extern "C" bool rmw_fleetqox_cpp_sros2_signed_governance_source();
extern "C" bool rmw_fleetqox_cpp_sros2_governance_runtime_signature_verified();
extern "C" const char * rmw_fleetqox_cpp_sros2_governance_xml_error();
extern "C" int rmw_fleetqox_cpp_sros2_governance_authorization_decision(
  const char * operation, const char * topic_name, std::size_t domain_id);

namespace
{

constexpr const char * kSchema = "fleetrmw.sros2_governance_probe.v1";
constexpr const char * kEnclave = "/fleetqox/security_probe";
constexpr std::size_t kDomainId = 7;
constexpr const char * kAllowedTopic = "/fleetqox/sros2_allowed";
constexpr const char * kUncontrolledTopic = "/fleetqox/governance_uncontrolled";
constexpr const char * kDeniedTopic = "/fleetqox/sros2_denied";

std::string json_escape(const std::string & value)
{
  std::ostringstream out;
  for (const char c : value) {
    if (c == '\\' || c == '"') {
      out << '\\' << c;
    } else if (c == '\n') {
      out << "\\n";
    } else if (c == '\r') {
      out << "\\r";
    } else {
      out << c;
    }
  }
  return out.str();
}

void replace_enclave(rmw_init_options_t * options, const char * enclave)
{
  if (options == nullptr) {
    return;
  }
  if (options->enclave != nullptr && options->allocator.deallocate != nullptr) {
    options->allocator.deallocate(const_cast<char *>(options->enclave), options->allocator.state);
  }
  options->enclave = rcutils_strdup(enclave, options->allocator);
}

bool init_message(
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
  std::string * payload)
{
  bool taken = false;
  for (int attempt = 0; attempt < 150 && !taken; ++attempt) {
    if (rmw_take_serialized_message(subscription, incoming, &taken, nullptr) != RMW_RET_OK) {
      return false;
    }
    if (!taken) {
      std::this_thread::sleep_for(std::chrono::milliseconds(1));
    }
  }
  if (taken && incoming != nullptr && incoming->buffer != nullptr && payload != nullptr) {
    payload->assign(
      reinterpret_cast<const char *>(incoming->buffer), incoming->buffer_length);
  }
  return taken;
}

bool queue_empty(
  const rmw_subscription_t * subscription,
  rmw_serialized_message_t * incoming)
{
  std::this_thread::sleep_for(std::chrono::milliseconds(5));
  bool taken = true;
  return rmw_take_serialized_message(subscription, incoming, &taken, nullptr) == RMW_RET_OK &&
         !taken;
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
  const bool expect_protection_deny =
    std::getenv("FLEETQOX_RMW_SROS2_GOVERNANCE_EXPECT_PROTECTION_DENY") != nullptr;
  const bool expect_tampered =
    std::getenv("FLEETQOX_RMW_SROS2_GOVERNANCE_EXPECT_TAMPERED") != nullptr;
  const bool expect_fail_closed = expect_protection_deny || expect_tampered;

  rcutils_allocator_t allocator = rcutils_get_default_allocator();
  rmw_init_options_t options = rmw_get_zero_initialized_init_options();
  if (rmw_init_options_init(&options, allocator) != RMW_RET_OK) {
    std::cout << "{\"status\":\"init_options_failed\"}" << std::endl;
    return 1;
  }
  options.instance_id = 91;
  options.domain_id = kDomainId;
  replace_enclave(&options, kEnclave);
  rmw_context_t context = rmw_get_zero_initialized_context();
  if (options.enclave == nullptr || rmw_init(&options, &context) != RMW_RET_OK) {
    const rmw_ret_t fini_ret = rmw_init_options_fini(&options);
    (void)fini_ret;
    std::cout << "{\"status\":\"init_failed\"}" << std::endl;
    return 1;
  }
  rmw_node_t * node = rmw_create_node(&context, "sros2_governance_probe", "/fleetqox");
  if (node == nullptr) {
    cleanup_context(&context, &options);
    std::cout << "{\"status\":\"create_node_failed\"}" << std::endl;
    return 1;
  }

  rosidl_message_type_support_t type_support{};
  type_support.typesupport_identifier = "rmw_fleetqox_cpp_sros2_governance_probe";
  rmw_qos_profile_t qos = rmw_qos_profile_default;
  rmw_publisher_options_t publisher_options = rmw_get_default_publisher_options();
  rmw_subscription_options_t subscription_options = rmw_get_default_subscription_options();

  rmw_publisher_t * allowed_publisher =
    rmw_create_publisher(node, &type_support, kAllowedTopic, &qos, &publisher_options);
  rmw_subscription_t * allowed_subscription =
    rmw_create_subscription(node, &type_support, kAllowedTopic, &qos, &subscription_options);
  rmw_publisher_t * uncontrolled_publisher =
    rmw_create_publisher(node, &type_support, kUncontrolledTopic, &qos, &publisher_options);
  rmw_subscription_t * uncontrolled_subscription =
    rmw_create_subscription(node, &type_support, kUncontrolledTopic, &qos, &subscription_options);
  rmw_publisher_t * denied_publisher =
    rmw_create_publisher(node, &type_support, kDeniedTopic, &qos, &publisher_options);
  rmw_subscription_t * denied_subscription =
    rmw_create_subscription(node, &type_support, kDeniedTopic, &qos, &subscription_options);
  if (allowed_publisher == nullptr || allowed_subscription == nullptr ||
    uncontrolled_publisher == nullptr || uncontrolled_subscription == nullptr ||
    denied_publisher == nullptr || denied_subscription == nullptr)
  {
    std::cout << "{\"status\":\"create_pubsub_failed\"}" << std::endl;
    return 1;
  }

  rmw_serialized_message_t allowed_out = rmw_get_zero_initialized_serialized_message();
  rmw_serialized_message_t uncontrolled_out = rmw_get_zero_initialized_serialized_message();
  rmw_serialized_message_t denied_out = rmw_get_zero_initialized_serialized_message();
  rmw_serialized_message_t allowed_in = rmw_get_zero_initialized_serialized_message();
  rmw_serialized_message_t uncontrolled_in = rmw_get_zero_initialized_serialized_message();
  rmw_serialized_message_t denied_in = rmw_get_zero_initialized_serialized_message();
  const std::string allowed_payload = "governance-access-controlled";
  const std::string uncontrolled_payload = "governance-access-disabled";
  const std::string denied_payload = "governance-permissions-denied";
  if (!init_message(&allowed_out, allowed_payload, &allocator) ||
    !init_message(&uncontrolled_out, uncontrolled_payload, &allocator) ||
    !init_message(&denied_out, denied_payload, &allocator) ||
    rmw_serialized_message_init(&allowed_in, 1, &allocator) != RMW_RET_OK ||
    rmw_serialized_message_init(&uncontrolled_in, 1, &allocator) != RMW_RET_OK ||
    rmw_serialized_message_init(&denied_in, 1, &allocator) != RMW_RET_OK)
  {
    std::cout << "{\"status\":\"serialized_message_init_failed\"}" << std::endl;
    return 1;
  }

  const bool governance_loaded = rmw_fleetqox_cpp_sros2_governance_xml_loaded();
  const bool signed_source = rmw_fleetqox_cpp_sros2_signed_governance_source();
  const bool runtime_signature_verified =
    rmw_fleetqox_cpp_sros2_governance_runtime_signature_verified();
  const int allowed_publish_decision =
    rmw_fleetqox_cpp_sros2_governance_authorization_decision(
    "publish", kAllowedTopic, kDomainId);
  const int allowed_subscribe_decision =
    rmw_fleetqox_cpp_sros2_governance_authorization_decision(
    "subscribe", kAllowedTopic, kDomainId);
  const int uncontrolled_publish_decision =
    rmw_fleetqox_cpp_sros2_governance_authorization_decision(
    "publish", kUncontrolledTopic, kDomainId);
  const int uncontrolled_subscribe_decision =
    rmw_fleetqox_cpp_sros2_governance_authorization_decision(
    "subscribe", kUncontrolledTopic, kDomainId);

  const rmw_ret_t allowed_ret =
    rmw_publish_serialized_message(allowed_publisher, &allowed_out, nullptr);
  const rmw_ret_t uncontrolled_ret =
    rmw_publish_serialized_message(uncontrolled_publisher, &uncontrolled_out, nullptr);
  const rmw_ret_t denied_ret =
    rmw_publish_serialized_message(denied_publisher, &denied_out, nullptr);
  std::string allowed_received;
  std::string uncontrolled_received;
  const bool allowed_taken = allowed_ret == RMW_RET_OK &&
    wait_take(allowed_subscription, &allowed_in, &allowed_received);
  const bool uncontrolled_taken = uncontrolled_ret == RMW_RET_OK &&
    wait_take(uncontrolled_subscription, &uncontrolled_in, &uncontrolled_received);
  const bool denied_queue_empty = queue_empty(denied_subscription, &denied_in);
  const bool allowed_queue_empty = allowed_taken ? false :
    queue_empty(allowed_subscription, &allowed_in);
  const bool uncontrolled_queue_empty = uncontrolled_taken ? false :
    queue_empty(uncontrolled_subscription, &uncontrolled_in);

  const bool valid_decisions = allowed_publish_decision == 2 &&
    allowed_subscribe_decision == 2 && uncontrolled_publish_decision == 1 &&
    uncontrolled_subscribe_decision == 1;
  const bool valid_data_path = allowed_ret == RMW_RET_OK && allowed_taken &&
    allowed_received == allowed_payload && uncontrolled_ret == RMW_RET_OK &&
    uncontrolled_taken && uncontrolled_received == uncontrolled_payload &&
    denied_ret != RMW_RET_OK && denied_queue_empty;
  const bool protected_decisions = allowed_publish_decision == 4 &&
    allowed_subscribe_decision == 4 && uncontrolled_publish_decision == 4 &&
    uncontrolled_subscribe_decision == 4;
  const bool tampered_decisions = allowed_publish_decision == 6 &&
    allowed_subscribe_decision == 6 && uncontrolled_publish_decision == 6 &&
    uncontrolled_subscribe_decision == 6;
  const bool fail_closed_data_path = allowed_ret != RMW_RET_OK &&
    uncontrolled_ret != RMW_RET_OK && denied_ret != RMW_RET_OK &&
    allowed_queue_empty && uncontrolled_queue_empty && denied_queue_empty;
  const std::string governance_error =
    rmw_fleetqox_cpp_sros2_governance_xml_error() == nullptr ? "" :
    rmw_fleetqox_cpp_sros2_governance_xml_error();
  const bool load_state_ok = expect_tampered ?
    !governance_loaded && !runtime_signature_verified &&
    governance_error.find("governance_p7s_verify_failed") != std::string::npos :
    governance_loaded && signed_source && runtime_signature_verified && governance_error.empty();
  const bool mode_ok = expect_protection_deny ?
    protected_decisions && fail_closed_data_path :
    (expect_tampered ? tampered_decisions && fail_closed_data_path :
    valid_decisions && valid_data_path);
  const bool configured =
    std::getenv("FLEETQOX_RMW_SROS2_GOVERNANCE_P7S_FILE") != nullptr;
  const bool ok = configured && load_state_ok && mode_ok;

  std::cout << "{\"schema_version\":\"" << kSchema << "\",";
  std::cout << "\"status\":\"" << (ok ? "ok" : "failed") << "\",";
  std::cout << "\"probe_mode\":\"" <<
    (expect_protection_deny ? "transport_protection_fail_closed" :
    (expect_tampered ? "tampered_governance_fail_closed" :
    "signed_governance_access_control")) << "\",";
  std::cout << "\"governance_file_configured\":" << (configured ? "true" : "false") << ",";
  std::cout << "\"signed_governance_source\":" << (signed_source ? "true" : "false") << ",";
  std::cout << "\"runtime_signature_verified\":" <<
    (runtime_signature_verified ? "true" : "false") << ",";
  std::cout << "\"governance_xml_loaded\":" << (governance_loaded ? "true" : "false") << ",";
  std::cout << "\"governance_xml_error\":\"" << json_escape(governance_error) << "\",";
  std::cout << "\"allowed_publish_governance_decision\":" << allowed_publish_decision << ",";
  std::cout << "\"allowed_subscribe_governance_decision\":" << allowed_subscribe_decision << ",";
  std::cout << "\"uncontrolled_publish_governance_decision\":" <<
    uncontrolled_publish_decision << ",";
  std::cout << "\"uncontrolled_subscribe_governance_decision\":" <<
    uncontrolled_subscribe_decision << ",";
  std::cout << "\"allowed_publish_returncode\":" << static_cast<int>(allowed_ret) << ",";
  std::cout << "\"allowed_taken\":" << (allowed_taken ? "true" : "false") << ",";
  std::cout << "\"uncontrolled_publish_returncode\":" <<
    static_cast<int>(uncontrolled_ret) << ",";
  std::cout << "\"uncontrolled_taken\":" << (uncontrolled_taken ? "true" : "false") << ",";
  std::cout << "\"permissions_denied_publish_returncode\":" <<
    static_cast<int>(denied_ret) << ",";
  std::cout << "\"permissions_denied_queue_empty\":" <<
    (denied_queue_empty ? "true" : "false") << ",";
  std::cout << "\"sros2_governance_access_control_claim\":" <<
    (ok && !expect_fail_closed ? "true" : "false") << ",";
  std::cout << "\"sros2_governance_transport_protection_fail_closed_claim\":" <<
    (ok && expect_protection_deny ? "true" : "false") << ",";
  std::cout << "\"sros2_tampered_signed_governance_fail_closed_claim\":" <<
    (ok && expect_tampered ? "true" : "false") << ",";
  std::cout << "\"governance_transport_security_claim\":false,";
  std::cout << "\"sros2_policy_enforcement_claim\":false,";
  std::cout << "\"production_security_hardening_claim\":false}" << std::endl;

  const rmw_ret_t allowed_out_fini = rmw_serialized_message_fini(&allowed_out);
  const rmw_ret_t uncontrolled_out_fini = rmw_serialized_message_fini(&uncontrolled_out);
  const rmw_ret_t denied_out_fini = rmw_serialized_message_fini(&denied_out);
  const rmw_ret_t allowed_in_fini = rmw_serialized_message_fini(&allowed_in);
  const rmw_ret_t uncontrolled_in_fini = rmw_serialized_message_fini(&uncontrolled_in);
  const rmw_ret_t denied_in_fini = rmw_serialized_message_fini(&denied_in);
  const rmw_ret_t destroy_allowed_pub = rmw_destroy_publisher(node, allowed_publisher);
  const rmw_ret_t destroy_allowed_sub = rmw_destroy_subscription(node, allowed_subscription);
  const rmw_ret_t destroy_uncontrolled_pub = rmw_destroy_publisher(node, uncontrolled_publisher);
  const rmw_ret_t destroy_uncontrolled_sub =
    rmw_destroy_subscription(node, uncontrolled_subscription);
  const rmw_ret_t destroy_denied_pub = rmw_destroy_publisher(node, denied_publisher);
  const rmw_ret_t destroy_denied_sub = rmw_destroy_subscription(node, denied_subscription);
  const rmw_ret_t destroy_node = rmw_destroy_node(node);
  cleanup_context(&context, &options);
  return ok && allowed_out_fini == RMW_RET_OK && uncontrolled_out_fini == RMW_RET_OK &&
         denied_out_fini == RMW_RET_OK && allowed_in_fini == RMW_RET_OK &&
         uncontrolled_in_fini == RMW_RET_OK && denied_in_fini == RMW_RET_OK &&
         destroy_allowed_pub == RMW_RET_OK && destroy_allowed_sub == RMW_RET_OK &&
         destroy_uncontrolled_pub == RMW_RET_OK && destroy_uncontrolled_sub == RMW_RET_OK &&
         destroy_denied_pub == RMW_RET_OK && destroy_denied_sub == RMW_RET_OK &&
         destroy_node == RMW_RET_OK ? 0 : 1;
}

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

extern "C" std::uint64_t rmw_fleetqox_cpp_security_policy_denied();
extern "C" bool rmw_fleetqox_cpp_sros2_permissions_xml_loaded();
extern "C" bool rmw_fleetqox_cpp_sros2_signed_permissions_source();
extern "C" bool rmw_fleetqox_cpp_sros2_runtime_signature_verified();
extern "C" const char * rmw_fleetqox_cpp_sros2_permissions_xml_error();
extern "C" std::uint64_t rmw_fleetqox_cpp_sros2_permissions_xml_allowed();
extern "C" std::uint64_t rmw_fleetqox_cpp_sros2_permissions_xml_denied();
extern "C" std::uint64_t rmw_fleetqox_cpp_sros2_permissions_xml_parse_errors();
extern "C" std::uint64_t rmw_fleetqox_cpp_sros2_permissions_xml_subscribe_allowed();
extern "C" std::uint64_t rmw_fleetqox_cpp_sros2_permissions_xml_subscribe_denied();

namespace
{

constexpr const char * kSchema = "fleetrmw.sros2_permissions_probe.v1";
constexpr const char * kEnclave = "/fleetqox/security_probe";
constexpr std::size_t kDomainId = 7;
constexpr const char * kAllowedTopic = "/fleetqox/sros2_allowed";
constexpr const char * kDeniedTopic = "/fleetqox/sros2_denied";
constexpr const char * kDefaultDeniedTopic = "/fleetqox/sros2_default_denied";
constexpr const char * kSubscribeDeniedTopic = "/fleetqox/sros2_subscribe_denied";
constexpr const char * kSubscribeDefaultDeniedTopic =
  "/fleetqox/sros2_subscribe_default_denied";

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
    if (rmw_take_serialized_message(subscription, incoming, &taken, nullptr) != RMW_RET_OK) {
      return false;
    }
    if (!taken) {
      std::this_thread::sleep_for(std::chrono::milliseconds(1));
    }
  }
  if (taken && incoming != nullptr && incoming->buffer != nullptr && received != nullptr) {
    received->assign(
      reinterpret_cast<const char *>(incoming->buffer),
      reinterpret_cast<const char *>(incoming->buffer + incoming->buffer_length));
  }
  return taken;
}

bool no_message_available(
  const rmw_subscription_t * subscription,
  rmw_serialized_message_t * incoming)
{
  bool taken = true;
  return rmw_take_serialized_message(subscription, incoming, &taken, nullptr) == RMW_RET_OK && !taken;
}

bool wait_for_subscribe_decisions(std::uint64_t baseline, std::uint64_t expected_delta)
{
  for (int attempt = 0; attempt < 100; ++attempt) {
    if (rmw_fleetqox_cpp_sros2_permissions_xml_subscribe_allowed() +
      rmw_fleetqox_cpp_sros2_permissions_xml_subscribe_denied() >=
      baseline + expected_delta)
    {
      return true;
    }
    std::this_thread::sleep_for(std::chrono::milliseconds(1));
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
  const char * permissions_file = std::getenv("FLEETQOX_RMW_SROS2_PERMISSIONS_FILE");
  const char * signed_permissions_file =
    std::getenv("FLEETQOX_RMW_SROS2_PERMISSIONS_P7S_FILE");
  const char * permissions_ca_file =
    std::getenv("FLEETQOX_RMW_SROS2_PERMISSIONS_CA_FILE");
  const char * expect_invalid_env = std::getenv("FLEETQOX_RMW_SROS2_EXPECT_INVALID");
  const char * invalid_kind_env =
    std::getenv("FLEETQOX_RMW_SROS2_EXPECT_INVALID_KIND");
  const bool expect_invalid =
    expect_invalid_env != nullptr && std::strcmp(expect_invalid_env, "1") == 0;
  const bool tampered_signature_control = expect_invalid && invalid_kind_env != nullptr &&
    std::strcmp(invalid_kind_env, "tampered_signature") == 0;
  rcutils_allocator_t allocator = rcutils_get_default_allocator();
  rmw_init_options_t options = rmw_get_zero_initialized_init_options();
  if (rmw_init_options_init(&options, allocator) != RMW_RET_OK) {
    std::cout << "{\"status\":\"init_options_failed\"}" << std::endl;
    return 1;
  }
  options.instance_id = 88;
  options.domain_id = kDomainId;
  replace_enclave(&options, kEnclave);
  if (options.enclave == nullptr) {
    const rmw_ret_t fini_ret = rmw_init_options_fini(&options);
    (void)fini_ret;
    std::cout << "{\"status\":\"enclave_allocation_failed\"}" << std::endl;
    return 1;
  }

  rmw_context_t context = rmw_get_zero_initialized_context();
  if (rmw_init(&options, &context) != RMW_RET_OK) {
    const rmw_ret_t fini_ret = rmw_init_options_fini(&options);
    (void)fini_ret;
    std::cout << "{\"status\":\"init_failed\"}" << std::endl;
    return 1;
  }
  rmw_node_t * node = rmw_create_node(&context, "sros2_permissions_probe", "/fleetqox");
  if (node == nullptr) {
    cleanup_context(&context, &options);
    std::cout << "{\"status\":\"create_node_failed\"}" << std::endl;
    return 1;
  }

  rosidl_message_type_support_t type_support{};
  type_support.typesupport_identifier = "rmw_fleetqox_cpp_sros2_permissions_probe";
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
  rmw_publisher_t * default_denied_publisher =
    rmw_create_publisher(node, &type_support, kDefaultDeniedTopic, &qos, &publisher_options);
  rmw_subscription_t * default_denied_subscription =
    rmw_create_subscription(node, &type_support, kDefaultDeniedTopic, &qos, &subscription_options);
  rmw_publisher_t * subscribe_denied_publisher =
    rmw_create_publisher(node, &type_support, kSubscribeDeniedTopic, &qos, &publisher_options);
  rmw_subscription_t * subscribe_denied_subscription =
    rmw_create_subscription(
    node, &type_support, kSubscribeDeniedTopic, &qos, &subscription_options);
  rmw_publisher_t * subscribe_default_denied_publisher =
    rmw_create_publisher(
    node, &type_support, kSubscribeDefaultDeniedTopic, &qos, &publisher_options);
  rmw_subscription_t * subscribe_default_denied_subscription =
    rmw_create_subscription(
    node, &type_support, kSubscribeDefaultDeniedTopic, &qos, &subscription_options);
  if (allowed_publisher == nullptr || allowed_subscription == nullptr ||
    denied_publisher == nullptr || denied_subscription == nullptr ||
    default_denied_publisher == nullptr || default_denied_subscription == nullptr ||
    subscribe_denied_publisher == nullptr || subscribe_denied_subscription == nullptr ||
    subscribe_default_denied_publisher == nullptr ||
    subscribe_default_denied_subscription == nullptr)
  {
    std::cout << "{\"status\":\"create_pubsub_failed\"}" << std::endl;
    return 1;
  }

  rmw_serialized_message_t allowed_out = rmw_get_zero_initialized_serialized_message();
  rmw_serialized_message_t denied_out = rmw_get_zero_initialized_serialized_message();
  rmw_serialized_message_t default_denied_out = rmw_get_zero_initialized_serialized_message();
  rmw_serialized_message_t subscribe_denied_out = rmw_get_zero_initialized_serialized_message();
  rmw_serialized_message_t subscribe_default_denied_out =
    rmw_get_zero_initialized_serialized_message();
  rmw_serialized_message_t allowed_in = rmw_get_zero_initialized_serialized_message();
  rmw_serialized_message_t denied_in = rmw_get_zero_initialized_serialized_message();
  rmw_serialized_message_t default_denied_in = rmw_get_zero_initialized_serialized_message();
  rmw_serialized_message_t subscribe_denied_in = rmw_get_zero_initialized_serialized_message();
  rmw_serialized_message_t subscribe_default_denied_in =
    rmw_get_zero_initialized_serialized_message();
  const std::string allowed_payload = "sros2-allowed-payload";
  const std::string denied_payload = "sros2-denied-payload";
  const std::string default_denied_payload = "sros2-default-denied-payload";
  const std::string subscribe_denied_payload = "sros2-subscribe-denied-payload";
  const std::string subscribe_default_denied_payload =
    "sros2-subscribe-default-denied-payload";
  if (!init_serialized_message(&allowed_out, allowed_payload, &allocator) ||
    !init_serialized_message(&denied_out, denied_payload, &allocator) ||
    !init_serialized_message(&default_denied_out, default_denied_payload, &allocator) ||
    !init_serialized_message(&subscribe_denied_out, subscribe_denied_payload, &allocator) ||
    !init_serialized_message(
      &subscribe_default_denied_out, subscribe_default_denied_payload, &allocator) ||
    rmw_serialized_message_init(&allowed_in, 1, &allocator) != RMW_RET_OK ||
    rmw_serialized_message_init(&denied_in, 1, &allocator) != RMW_RET_OK ||
    rmw_serialized_message_init(&default_denied_in, 1, &allocator) != RMW_RET_OK ||
    rmw_serialized_message_init(&subscribe_denied_in, 1, &allocator) != RMW_RET_OK ||
    rmw_serialized_message_init(&subscribe_default_denied_in, 1, &allocator) != RMW_RET_OK)
  {
    std::cout << "{\"status\":\"serialized_message_init_failed\"}" << std::endl;
    return 1;
  }

  const bool permissions_xml_loaded = rmw_fleetqox_cpp_sros2_permissions_xml_loaded();
  const bool signed_permissions_source =
    rmw_fleetqox_cpp_sros2_signed_permissions_source();
  const bool runtime_signature_verified =
    rmw_fleetqox_cpp_sros2_runtime_signature_verified();
  const std::uint64_t policy_denied_before = rmw_fleetqox_cpp_security_policy_denied();
  const std::uint64_t xml_allowed_before = rmw_fleetqox_cpp_sros2_permissions_xml_allowed();
  const std::uint64_t xml_denied_before = rmw_fleetqox_cpp_sros2_permissions_xml_denied();
  const std::uint64_t xml_parse_errors_before =
    rmw_fleetqox_cpp_sros2_permissions_xml_parse_errors();
  const std::uint64_t xml_subscribe_allowed_before =
    rmw_fleetqox_cpp_sros2_permissions_xml_subscribe_allowed();
  const std::uint64_t xml_subscribe_denied_before =
    rmw_fleetqox_cpp_sros2_permissions_xml_subscribe_denied();
  const std::uint64_t subscribe_decisions_before =
    xml_subscribe_allowed_before + xml_subscribe_denied_before;

  const rmw_ret_t allowed_ret =
    rmw_publish_serialized_message(allowed_publisher, &allowed_out, nullptr);
  std::string received;
  const bool allowed_taken =
    allowed_ret == RMW_RET_OK && wait_take(allowed_subscription, &allowed_in, &received);
  const bool allowed_no_message =
    allowed_ret != RMW_RET_OK && no_message_available(allowed_subscription, &allowed_in);
  const rmw_ret_t denied_ret =
    rmw_publish_serialized_message(denied_publisher, &denied_out, nullptr);
  const bool denied_taken = !no_message_available(denied_subscription, &denied_in);
  const rmw_ret_t default_denied_ret =
    rmw_publish_serialized_message(default_denied_publisher, &default_denied_out, nullptr);
  const bool default_denied_taken =
    !no_message_available(default_denied_subscription, &default_denied_in);
  const rmw_ret_t subscribe_denied_publish_ret =
    rmw_publish_serialized_message(
    subscribe_denied_publisher, &subscribe_denied_out, nullptr);
  const rmw_ret_t subscribe_default_denied_publish_ret =
    rmw_publish_serialized_message(
    subscribe_default_denied_publisher, &subscribe_default_denied_out, nullptr);
  const bool subscribe_decisions_ready = expect_invalid ? true :
    wait_for_subscribe_decisions(subscribe_decisions_before, 3);
  const bool subscribe_denied_taken =
    !no_message_available(subscribe_denied_subscription, &subscribe_denied_in);
  const bool subscribe_default_denied_taken =
    !no_message_available(
    subscribe_default_denied_subscription, &subscribe_default_denied_in);

  const std::uint64_t policy_denied_delta =
    rmw_fleetqox_cpp_security_policy_denied() - policy_denied_before;
  const std::uint64_t xml_allowed_delta =
    rmw_fleetqox_cpp_sros2_permissions_xml_allowed() - xml_allowed_before;
  const std::uint64_t xml_denied_delta =
    rmw_fleetqox_cpp_sros2_permissions_xml_denied() - xml_denied_before;
  const std::uint64_t xml_parse_errors_delta =
    rmw_fleetqox_cpp_sros2_permissions_xml_parse_errors() - xml_parse_errors_before;
  const std::uint64_t xml_subscribe_allowed_delta =
    rmw_fleetqox_cpp_sros2_permissions_xml_subscribe_allowed() -
    xml_subscribe_allowed_before;
  const std::uint64_t xml_subscribe_denied_delta =
    rmw_fleetqox_cpp_sros2_permissions_xml_subscribe_denied() -
    xml_subscribe_denied_before;

  const bool allowed_ok = expect_invalid ?
    allowed_ret != RMW_RET_OK && !allowed_taken && allowed_no_message :
    allowed_ret == RMW_RET_OK && allowed_taken && received == allowed_payload;
  const bool explicit_deny_ok = denied_ret != RMW_RET_OK && !denied_taken;
  const bool default_deny_ok = default_denied_ret != RMW_RET_OK && !default_denied_taken;
  const bool subscribe_deny_ok = expect_invalid ?
    subscribe_denied_publish_ret != RMW_RET_OK &&
    subscribe_default_denied_publish_ret != RMW_RET_OK &&
    !subscribe_denied_taken && !subscribe_default_denied_taken :
    subscribe_denied_publish_ret == RMW_RET_OK &&
    subscribe_default_denied_publish_ret == RMW_RET_OK &&
    subscribe_decisions_ready && !subscribe_denied_taken &&
    !subscribe_default_denied_taken;
  const bool counters_ok = expect_invalid ?
    policy_denied_delta == 5 && xml_allowed_delta == 0 && xml_denied_delta == 5 &&
    xml_parse_errors_delta == 5 && xml_subscribe_allowed_delta == 0 &&
    xml_subscribe_denied_delta == 0 :
    policy_denied_delta == 2 && xml_allowed_delta == 3 && xml_denied_delta == 2 &&
    xml_parse_errors_delta == 0 && xml_subscribe_allowed_delta == 1 &&
    xml_subscribe_denied_delta == 2;
  const bool xml_file_configured = permissions_file != nullptr && permissions_file[0] != '\0';
  const bool signed_file_configured =
    signed_permissions_file != nullptr && signed_permissions_file[0] != '\0';
  const bool policy_configured = xml_file_configured || signed_file_configured;
  const bool load_state_ok = expect_invalid ?
    !permissions_xml_loaded && !runtime_signature_verified :
    permissions_xml_loaded && signed_permissions_source && runtime_signature_verified;
  const bool ok = policy_configured && load_state_ok && allowed_ok && explicit_deny_ok &&
    default_deny_ok && subscribe_deny_ok && counters_ok;

  std::cout << "{\"schema_version\":\"" << kSchema << "\",";
  std::cout << "\"status\":\"" << (ok ? "ok" : "failed") << "\",";
  std::cout << "\"probe_mode\":\"" <<
    (tampered_signature_control ? "tampered_signature_fail_closed" :
    (expect_invalid ? "malformed_fail_closed" : "valid_signed_permissions")) << "\",";
  std::cout << "\"permissions_file_configured\":" << (policy_configured ? "true" : "false") << ",";
  std::cout << "\"permissions_file\":\"" <<
    json_escape(signed_file_configured ? signed_permissions_file :
    (permissions_file == nullptr ? "" : permissions_file)) << "\",";
  std::cout << "\"signed_permissions_file_configured\":" <<
    (signed_file_configured ? "true" : "false") << ",";
  std::cout << "\"permissions_ca_file_configured\":" <<
    (permissions_ca_file != nullptr && permissions_ca_file[0] != '\0' ? "true" : "false") << ",";
  std::cout << "\"signed_permissions_source\":" <<
    (signed_permissions_source ? "true" : "false") << ",";
  std::cout << "\"runtime_signature_verified\":" <<
    (runtime_signature_verified ? "true" : "false") << ",";
  std::cout << "\"permissions_xml_loaded\":" << (permissions_xml_loaded ? "true" : "false") << ",";
  std::cout << "\"permissions_xml_error\":\"" <<
    json_escape(rmw_fleetqox_cpp_sros2_permissions_xml_error()) << "\",";
  std::cout << "\"enclave\":\"" << kEnclave << "\",";
  std::cout << "\"domain_id\":" << kDomainId << ",";
  std::cout << "\"allowed_publish_returncode\":" << static_cast<int>(allowed_ret) << ",";
  std::cout << "\"allowed_taken\":" << (allowed_taken ? "true" : "false") << ",";
  std::cout << "\"allowed_no_message\":" << (allowed_no_message ? "true" : "false") << ",";
  std::cout << "\"allowed_payload_ok\":" << (received == allowed_payload ? "true" : "false") << ",";
  std::cout << "\"explicit_denied_publish_returncode\":" << static_cast<int>(denied_ret) << ",";
  std::cout << "\"explicit_denied_taken\":" << (denied_taken ? "true" : "false") << ",";
  std::cout << "\"default_denied_publish_returncode\":" <<
    static_cast<int>(default_denied_ret) << ",";
  std::cout << "\"default_denied_taken\":" << (default_denied_taken ? "true" : "false") << ",";
  std::cout << "\"subscribe_denied_publish_returncode\":" <<
    static_cast<int>(subscribe_denied_publish_ret) << ",";
  std::cout << "\"subscribe_default_denied_publish_returncode\":" <<
    static_cast<int>(subscribe_default_denied_publish_ret) << ",";
  std::cout << "\"subscribe_decisions_ready\":" <<
    (subscribe_decisions_ready ? "true" : "false") << ",";
  std::cout << "\"subscribe_denied_taken\":" <<
    (subscribe_denied_taken ? "true" : "false") << ",";
  std::cout << "\"subscribe_default_denied_taken\":" <<
    (subscribe_default_denied_taken ? "true" : "false") << ",";
  std::cout << "\"security_policy_denied_delta\":" << policy_denied_delta << ",";
  std::cout << "\"sros2_permissions_xml_allowed_delta\":" << xml_allowed_delta << ",";
  std::cout << "\"sros2_permissions_xml_denied_delta\":" << xml_denied_delta << ",";
  std::cout << "\"sros2_permissions_xml_parse_errors_delta\":" << xml_parse_errors_delta << ",";
  std::cout << "\"sros2_permissions_xml_subscribe_allowed_delta\":" <<
    xml_subscribe_allowed_delta << ",";
  std::cout << "\"sros2_permissions_xml_subscribe_denied_delta\":" <<
    xml_subscribe_denied_delta << ",";
  std::cout << "\"sros2_permissions_xml_publish_enforcement_claim\":" <<
    (ok && !expect_invalid ? "true" : "false") << ",";
  std::cout << "\"sros2_permissions_xml_subscribe_enforcement_claim\":" <<
    (ok && !expect_invalid ? "true" : "false") << ",";
  std::cout << "\"sros2_permissions_xml_pubsub_enforcement_claim\":" <<
    (ok && !expect_invalid ? "true" : "false") << ",";
  std::cout << "\"malformed_permissions_fail_closed_claim\":" <<
    (ok && expect_invalid && !tampered_signature_control ? "true" : "false") << ",";
  std::cout << "\"tampered_signed_permissions_fail_closed_claim\":" <<
    (ok && tampered_signature_control ? "true" : "false") << ",";
  std::cout << "\"sros2_permissions_xml_scope\":\"grant_enclave_domain_validity_publish_subscribe_topic_default\",";
  std::cout << "\"sros2_policy_enforcement_claim\":false,";
  std::cout << "\"runtime_permissions_signature_validation\":" <<
    (ok && !expect_invalid && runtime_signature_verified ? "true" : "false") << ",";
  std::cout << "\"runtime_sros2_permissions_signature_validation_claim\":" <<
    (ok && !expect_invalid && runtime_signature_verified ? "true" : "false") << ",";
  std::cout << "\"governance_xml_enforcement_claim\":false,";
  std::cout << "\"production_security_hardening_claim\":false}" << std::endl;

  const rmw_ret_t allowed_out_fini = rmw_serialized_message_fini(&allowed_out);
  const rmw_ret_t denied_out_fini = rmw_serialized_message_fini(&denied_out);
  const rmw_ret_t default_denied_out_fini = rmw_serialized_message_fini(&default_denied_out);
  const rmw_ret_t subscribe_denied_out_fini =
    rmw_serialized_message_fini(&subscribe_denied_out);
  const rmw_ret_t subscribe_default_denied_out_fini =
    rmw_serialized_message_fini(&subscribe_default_denied_out);
  const rmw_ret_t allowed_in_fini = rmw_serialized_message_fini(&allowed_in);
  const rmw_ret_t denied_in_fini = rmw_serialized_message_fini(&denied_in);
  const rmw_ret_t default_denied_in_fini = rmw_serialized_message_fini(&default_denied_in);
  const rmw_ret_t subscribe_denied_in_fini =
    rmw_serialized_message_fini(&subscribe_denied_in);
  const rmw_ret_t subscribe_default_denied_in_fini =
    rmw_serialized_message_fini(&subscribe_default_denied_in);
  const rmw_ret_t destroy_allowed_pub = rmw_destroy_publisher(node, allowed_publisher);
  const rmw_ret_t destroy_allowed_sub = rmw_destroy_subscription(node, allowed_subscription);
  const rmw_ret_t destroy_denied_pub = rmw_destroy_publisher(node, denied_publisher);
  const rmw_ret_t destroy_denied_sub = rmw_destroy_subscription(node, denied_subscription);
  const rmw_ret_t destroy_default_denied_pub =
    rmw_destroy_publisher(node, default_denied_publisher);
  const rmw_ret_t destroy_default_denied_sub =
    rmw_destroy_subscription(node, default_denied_subscription);
  const rmw_ret_t destroy_subscribe_denied_pub =
    rmw_destroy_publisher(node, subscribe_denied_publisher);
  const rmw_ret_t destroy_subscribe_denied_sub =
    rmw_destroy_subscription(node, subscribe_denied_subscription);
  const rmw_ret_t destroy_subscribe_default_denied_pub =
    rmw_destroy_publisher(node, subscribe_default_denied_publisher);
  const rmw_ret_t destroy_subscribe_default_denied_sub =
    rmw_destroy_subscription(node, subscribe_default_denied_subscription);
  const rmw_ret_t destroy_node = rmw_destroy_node(node);
  cleanup_context(&context, &options);
  return ok && allowed_out_fini == RMW_RET_OK && denied_out_fini == RMW_RET_OK &&
         default_denied_out_fini == RMW_RET_OK && allowed_in_fini == RMW_RET_OK &&
         subscribe_denied_out_fini == RMW_RET_OK &&
         subscribe_default_denied_out_fini == RMW_RET_OK &&
         denied_in_fini == RMW_RET_OK && default_denied_in_fini == RMW_RET_OK &&
         subscribe_denied_in_fini == RMW_RET_OK &&
         subscribe_default_denied_in_fini == RMW_RET_OK &&
         destroy_allowed_pub == RMW_RET_OK && destroy_allowed_sub == RMW_RET_OK &&
         destroy_denied_pub == RMW_RET_OK && destroy_denied_sub == RMW_RET_OK &&
         destroy_default_denied_pub == RMW_RET_OK && destroy_default_denied_sub == RMW_RET_OK &&
         destroy_subscribe_denied_pub == RMW_RET_OK &&
         destroy_subscribe_denied_sub == RMW_RET_OK &&
         destroy_subscribe_default_denied_pub == RMW_RET_OK &&
         destroy_subscribe_default_denied_sub == RMW_RET_OK &&
         destroy_node == RMW_RET_OK ? 0 : 1;
}

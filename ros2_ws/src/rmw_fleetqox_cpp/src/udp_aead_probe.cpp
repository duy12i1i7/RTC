#include <chrono>
#include <cstdint>
#include <cstring>
#include <cstdlib>
#include <iostream>
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

extern "C" bool rmw_fleetqox_cpp_udp_aead_enabled();
extern "C" std::uint64_t rmw_fleetqox_cpp_udp_aead_encrypted_frames();
extern "C" std::uint64_t rmw_fleetqox_cpp_udp_aead_decrypted_frames();
extern "C" std::uint64_t rmw_fleetqox_cpp_udp_aead_authentication_failures();
extern "C" std::uint64_t rmw_fleetqox_cpp_udp_aead_unprotected_drops();
extern "C" std::uint64_t rmw_fleetqox_cpp_udp_aead_replay_drops();
extern "C" std::uint64_t rmw_fleetqox_cpp_udp_aead_session_keys_derived();
extern "C" std::uint64_t rmw_fleetqox_cpp_udp_aead_session_key_rotations();
extern "C" std::uint64_t rmw_fleetqox_cpp_udp_aead_session_key_reuses();

namespace
{

constexpr const char * kSchema = "fleetrmw.udp_aead_probe.v1";

void cleanup_context(rmw_context_t * context, rmw_init_options_t * options)
{
  const rmw_ret_t shutdown_ret = rmw_shutdown(context);
  const rmw_ret_t context_ret = rmw_context_fini(context);
  const rmw_ret_t options_ret = rmw_init_options_fini(options);
  (void)shutdown_ret;
  (void)context_ret;
  (void)options_ret;
}

bool wait_take(
  const rmw_subscription_t * subscription,
  rmw_serialized_message_t * message,
  bool * taken)
{
  *taken = false;
  for (int attempt = 0; attempt < 200 && !*taken; ++attempt) {
    if (rmw_take_serialized_message(subscription, message, taken, nullptr) != RMW_RET_OK) {
      return false;
    }
    if (!*taken) {
      std::this_thread::sleep_for(std::chrono::milliseconds(1));
    }
  }
  return true;
}

}  // namespace

int main()
{
  const bool tamper_mode =
    std::getenv("FLEETQOX_RMW_UDP_AEAD_TAMPER_OUTBOUND_ONCE") != nullptr;
  const char * rotation_env =
    std::getenv("FLEETQOX_RMW_UDP_SESSION_KEY_ROTATE_FRAMES");
  const bool rotation_mode = rotation_env != nullptr && std::string(rotation_env) != "0";
  rcutils_allocator_t allocator = rcutils_get_default_allocator();
  rmw_init_options_t options = rmw_get_zero_initialized_init_options();
  if (rmw_init_options_init(&options, allocator) != RMW_RET_OK) {
    std::cout << "{\"status\":\"init_options_failed\"}" << std::endl;
    return 1;
  }
  options.instance_id = 93;
  options.domain_id = 7;
  rmw_context_t context = rmw_get_zero_initialized_context();
  if (rmw_init(&options, &context) != RMW_RET_OK) {
    const rmw_ret_t fini_ret = rmw_init_options_fini(&options);
    (void)fini_ret;
    std::cout << "{\"status\":\"init_failed\"}" << std::endl;
    return 1;
  }
  rmw_node_t * node = rmw_create_node(&context, "udp_aead_probe", "/fleetqox");
  rosidl_message_type_support_t type_support{};
  type_support.typesupport_identifier = "rmw_fleetqox_cpp_udp_aead_probe";
  rmw_qos_profile_t qos = rmw_qos_profile_default;
  rmw_publisher_options_t publisher_options = rmw_get_default_publisher_options();
  rmw_subscription_options_t subscription_options = rmw_get_default_subscription_options();
  rmw_publisher_t * publisher = node == nullptr ? nullptr : rmw_create_publisher(
    node, &type_support, "/fleetqox/udp_aead", &qos, &publisher_options);
  rmw_subscription_t * subscription = node == nullptr ? nullptr : rmw_create_subscription(
    node, &type_support, "/fleetqox/udp_aead", &qos, &subscription_options);
  if (node == nullptr || publisher == nullptr || subscription == nullptr) {
    std::cout << "{\"status\":\"create_endpoint_failed\"}" << std::endl;
    return 1;
  }
  std::this_thread::sleep_for(std::chrono::milliseconds(20));
  const std::uint64_t encrypted_before = rmw_fleetqox_cpp_udp_aead_encrypted_frames();
  const std::uint64_t decrypted_before = rmw_fleetqox_cpp_udp_aead_decrypted_frames();
  const std::uint64_t failures_before =
    rmw_fleetqox_cpp_udp_aead_authentication_failures();
  const std::uint64_t unprotected_before = rmw_fleetqox_cpp_udp_aead_unprotected_drops();
  const std::uint64_t replay_before = rmw_fleetqox_cpp_udp_aead_replay_drops();
  const std::uint64_t session_keys_before =
    rmw_fleetqox_cpp_udp_aead_session_keys_derived();
  const std::uint64_t rotations_before =
    rmw_fleetqox_cpp_udp_aead_session_key_rotations();
  const std::uint64_t reuses_before =
    rmw_fleetqox_cpp_udp_aead_session_key_reuses();

  const std::string payload = "fleetqox-aes-256-gcm";
  rmw_serialized_message_t outgoing = rmw_get_zero_initialized_serialized_message();
  rmw_serialized_message_t incoming = rmw_get_zero_initialized_serialized_message();
  if (rmw_serialized_message_init(&outgoing, payload.size(), &allocator) != RMW_RET_OK ||
    rmw_serialized_message_init(&incoming, 1, &allocator) != RMW_RET_OK)
  {
    std::cout << "{\"status\":\"message_init_failed\"}" << std::endl;
    return 1;
  }
  std::memcpy(outgoing.buffer, payload.data(), payload.size());
  outgoing.buffer_length = payload.size();
  const rmw_ret_t publish_ret =
    rmw_publish_serialized_message(publisher, &outgoing, nullptr);
  bool taken = false;
  const bool take_ok = wait_take(subscription, &incoming, &taken);
  const std::string received = taken ? std::string(
    reinterpret_cast<const char *>(incoming.buffer), incoming.buffer_length) : "";
  const std::uint64_t encrypted_delta =
    rmw_fleetqox_cpp_udp_aead_encrypted_frames() - encrypted_before;
  const std::uint64_t decrypted_delta =
    rmw_fleetqox_cpp_udp_aead_decrypted_frames() - decrypted_before;
  const std::uint64_t failures_delta =
    rmw_fleetqox_cpp_udp_aead_authentication_failures() - failures_before;
  const std::uint64_t unprotected_delta =
    rmw_fleetqox_cpp_udp_aead_unprotected_drops() - unprotected_before;
  const std::uint64_t replay_delta =
    rmw_fleetqox_cpp_udp_aead_replay_drops() - replay_before;
  const std::uint64_t session_keys_delta =
    rmw_fleetqox_cpp_udp_aead_session_keys_derived() - session_keys_before;
  const std::uint64_t rotations_delta =
    rmw_fleetqox_cpp_udp_aead_session_key_rotations() - rotations_before;
  const std::uint64_t reuses_delta =
    rmw_fleetqox_cpp_udp_aead_session_key_reuses() - reuses_before;
  const bool enabled = rmw_fleetqox_cpp_udp_aead_enabled();
  const bool delivered_ok = enabled && publish_ret == RMW_RET_OK &&
    take_ok && taken && received == payload && encrypted_delta >= 1 &&
    decrypted_delta >= 1 && failures_delta == 0;
  const bool valid_ok = !tamper_mode && !rotation_mode && delivered_ok &&
    rmw_fleetqox_cpp_udp_aead_session_keys_derived() >= 2 && reuses_delta >= 1;
  const bool rotation_ok = !tamper_mode && rotation_mode && delivered_ok &&
    session_keys_delta >= 2 && rotations_delta >= 1;
  const bool tamper_ok = tamper_mode && enabled && publish_ret == RMW_RET_OK &&
    take_ok && !taken && encrypted_delta >= 1 && decrypted_delta == 0 &&
    failures_delta >= 1;
  const bool ok = valid_ok || rotation_ok || tamper_ok;

  std::cout << "{\"schema_version\":\"" << kSchema << "\",";
  std::cout << "\"status\":\"" << (ok ? "ok" : "failed") << "\",";
  std::cout << "\"probe_mode\":\"" <<
    (tamper_mode ? "tamper" : (rotation_mode ? "rotation" : "valid")) << "\",";
  std::cout << "\"udp_aead_enabled\":" << (enabled ? "true" : "false") << ",";
  std::cout << "\"publish_returncode\":" << static_cast<int>(publish_ret) << ",";
  std::cout << "\"taken\":" << (taken ? "true" : "false") << ",";
  std::cout << "\"payload_ok\":" << (received == payload ? "true" : "false") << ",";
  std::cout << "\"encrypted_frames_delta\":" << encrypted_delta << ",";
  std::cout << "\"decrypted_frames_delta\":" << decrypted_delta << ",";
  std::cout << "\"authentication_failures_delta\":" << failures_delta << ",";
  std::cout << "\"unprotected_drops_delta\":" << unprotected_delta << ",";
  std::cout << "\"replay_drops_delta\":" << replay_delta << ",";
  std::cout << "\"session_keys_derived\":" <<
    rmw_fleetqox_cpp_udp_aead_session_keys_derived() << ",";
  std::cout << "\"session_keys_derived_delta\":" << session_keys_delta << ",";
  std::cout << "\"session_key_rotations_delta\":" << rotations_delta << ",";
  std::cout << "\"session_key_reuses_delta\":" << reuses_delta << ",";
  std::cout << "\"udp_authenticated_psk_session_key_derivation_claim\":" <<
    (valid_ok ? "true" : "false") << ",";
  std::cout << "\"udp_session_key_rotation_claim\":" <<
    (rotation_ok ? "true" : "false") << ",";
  std::cout << "\"udp_aead_authenticated_encryption_claim\":" <<
    (valid_ok ? "true" : "false") << ",";
  std::cout << "\"udp_aead_tamper_fail_closed_claim\":" <<
    (tamper_ok ? "true" : "false") << ",";
  std::cout << "\"sros2_peer_identity_authentication_claim\":false,";
  std::cout << "\"forward_secrecy_claim\":false,";
  std::cout << "\"production_security_hardening_claim\":false}" << std::endl;

  const rmw_ret_t outgoing_fini = rmw_serialized_message_fini(&outgoing);
  const rmw_ret_t incoming_fini = rmw_serialized_message_fini(&incoming);
  const rmw_ret_t destroy_pub = rmw_destroy_publisher(node, publisher);
  const rmw_ret_t destroy_sub = rmw_destroy_subscription(node, subscription);
  const rmw_ret_t destroy_node = rmw_destroy_node(node);
  cleanup_context(&context, &options);
  return ok && outgoing_fini == RMW_RET_OK && incoming_fini == RMW_RET_OK &&
         destroy_pub == RMW_RET_OK && destroy_sub == RMW_RET_OK &&
         destroy_node == RMW_RET_OK ? 0 : 1;
}

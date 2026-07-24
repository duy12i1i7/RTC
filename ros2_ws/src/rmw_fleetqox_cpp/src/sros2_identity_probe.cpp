#include <cstdint>
#include <cstring>
#include <cstdlib>
#include <iostream>
#include <sstream>
#include <string>

#include "rcutils/allocator.h"
#include "rcutils/strdup.h"
#include "rmw/init.h"
#include "rmw/init_options.h"
#include "rmw/rmw.h"

extern "C" bool rmw_fleetqox_cpp_sros2_identity_credentials_configured();
extern "C" bool rmw_fleetqox_cpp_sros2_identity_certificate_chain_verified();
extern "C" bool rmw_fleetqox_cpp_sros2_identity_private_key_matches();
extern "C" const char * rmw_fleetqox_cpp_sros2_identity_subject_common_name();
extern "C" const char * rmw_fleetqox_cpp_sros2_identity_credentials_error();
extern "C" int rmw_fleetqox_cpp_sros2_identity_validation_decision(const char * enclave);

namespace
{

constexpr const char * kSchema = "fleetrmw.sros2_identity_probe.v1";
constexpr const char * kEnclave = "/fleetqox/security_probe";
constexpr const char * kWrongEnclave = "/fleetqox/wrong_enclave";
constexpr std::size_t kDomainId = 7;

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

}  // namespace

int main()
{
  const char * mode_env = std::getenv("FLEETQOX_RMW_SROS2_IDENTITY_PROBE_MODE");
  const std::string mode = mode_env == nullptr ? "valid" : mode_env;
  const bool expect_tampered = mode == "tampered_certificate";
  const bool expect_key_mismatch = mode == "private_key_mismatch";
  const bool expect_enclave_mismatch = mode == "enclave_mismatch";
  const char * checked_enclave = expect_enclave_mismatch ? kWrongEnclave : kEnclave;

  rcutils_allocator_t allocator = rcutils_get_default_allocator();
  rmw_init_options_t options = rmw_get_zero_initialized_init_options();
  if (rmw_init_options_init(&options, allocator) != RMW_RET_OK) {
    std::cout << "{\"status\":\"init_options_failed\"}" << std::endl;
    return 1;
  }
  options.instance_id = 92;
  options.domain_id = kDomainId;
  replace_enclave(&options, checked_enclave);
  if (options.enclave == nullptr) {
    const rmw_ret_t fini_ret = rmw_init_options_fini(&options);
    (void)fini_ret;
    std::cout << "{\"status\":\"enclave_allocation_failed\"}" << std::endl;
    return 1;
  }

  const bool configured = rmw_fleetqox_cpp_sros2_identity_credentials_configured();
  const bool chain_verified =
    rmw_fleetqox_cpp_sros2_identity_certificate_chain_verified();
  const bool private_key_matches =
    rmw_fleetqox_cpp_sros2_identity_private_key_matches();
  const std::string subject =
    rmw_fleetqox_cpp_sros2_identity_subject_common_name() == nullptr ? "" :
    rmw_fleetqox_cpp_sros2_identity_subject_common_name();
  const std::string credentials_error =
    rmw_fleetqox_cpp_sros2_identity_credentials_error() == nullptr ? "" :
    rmw_fleetqox_cpp_sros2_identity_credentials_error();
  const int decision =
    rmw_fleetqox_cpp_sros2_identity_validation_decision(checked_enclave);

  rmw_context_t context = rmw_get_zero_initialized_context();
  const rmw_ret_t init_ret = rmw_init(&options, &context);
  const bool valid_ok = mode == "valid" && configured && chain_verified &&
    private_key_matches && subject == kEnclave && credentials_error.empty() &&
    decision == 1 && init_ret == RMW_RET_OK;
  const bool tampered_ok = expect_tampered && configured && !chain_verified &&
    !credentials_error.empty() && decision == 2 &&
    init_ret != RMW_RET_OK;
  const bool key_mismatch_ok = expect_key_mismatch && configured &&
    !chain_verified && !private_key_matches &&
    credentials_error.find("identity_private_key_mismatch") != std::string::npos &&
    decision == 2 && init_ret != RMW_RET_OK;
  const bool enclave_mismatch_ok = expect_enclave_mismatch && configured &&
    chain_verified && private_key_matches && subject == kEnclave &&
    credentials_error.empty() && decision == 3 && init_ret != RMW_RET_OK;
  const bool ok = valid_ok || tampered_ok || key_mismatch_ok || enclave_mismatch_ok;

  std::cout << "{\"schema_version\":\"" << kSchema << "\",";
  std::cout << "\"status\":\"" << (ok ? "ok" : "failed") << "\",";
  std::cout << "\"probe_mode\":\"" << mode << "\",";
  std::cout << "\"identity_credentials_configured\":" <<
    (configured ? "true" : "false") << ",";
  std::cout << "\"identity_certificate_chain_verified\":" <<
    (chain_verified ? "true" : "false") << ",";
  std::cout << "\"identity_private_key_matches\":" <<
    (private_key_matches ? "true" : "false") << ",";
  std::cout << "\"identity_subject_common_name\":\"" << json_escape(subject) << "\",";
  std::cout << "\"checked_enclave\":\"" << checked_enclave << "\",";
  std::cout << "\"identity_credentials_error\":\"" <<
    json_escape(credentials_error) << "\",";
  std::cout << "\"identity_validation_decision\":" << decision << ",";
  std::cout << "\"rmw_init_returncode\":" << static_cast<int>(init_ret) << ",";
  std::cout << "\"sros2_local_identity_credentials_validation_claim\":" <<
    (valid_ok ? "true" : "false") << ",";
  std::cout << "\"sros2_tampered_identity_certificate_fail_closed_claim\":" <<
    (tampered_ok ? "true" : "false") << ",";
  std::cout << "\"sros2_identity_private_key_mismatch_fail_closed_claim\":" <<
    (key_mismatch_ok ? "true" : "false") << ",";
  std::cout << "\"sros2_identity_enclave_mismatch_fail_closed_claim\":" <<
    (enclave_mismatch_ok ? "true" : "false") << ",";
  std::cout << "\"sros2_peer_identity_authentication_claim\":false,";
  std::cout << "\"production_security_hardening_claim\":false}" << std::endl;

  bool cleanup_ok = true;
  if (init_ret == RMW_RET_OK) {
    cleanup_ok = rmw_shutdown(&context) == RMW_RET_OK &&
      rmw_context_fini(&context) == RMW_RET_OK;
  }
  cleanup_ok = rmw_init_options_fini(&options) == RMW_RET_OK && cleanup_ok;
  return ok && cleanup_ok ? 0 : 1;
}

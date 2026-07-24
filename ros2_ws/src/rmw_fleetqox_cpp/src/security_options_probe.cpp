#include <cstring>
#include <iostream>

#include "rcutils/allocator.h"
#include "rcutils/strdup.h"
#include "rmw/init.h"
#include "rmw/init_options.h"
#include "rmw/rmw.h"

namespace
{

constexpr const char * kSchema = "fleetrmw.security_options_probe.v1";
constexpr const char * kCustomEnclave = "/fleetqox/security_probe";

void json_bool(const char * key, bool value, bool comma = true)
{
  std::cout << "\"" << key << "\":" << (value ? "true" : "false");
  if (comma) {
    std::cout << ",";
  }
}

void json_int(const char * key, int value, bool comma = true)
{
  std::cout << "\"" << key << "\":" << value;
  if (comma) {
    std::cout << ",";
  }
}

void json_string(const char * key, const char * value, bool comma = true)
{
  std::cout << "\"" << key << "\":\"" << (value == nullptr ? "" : value) << "\"";
  if (comma) {
    std::cout << ",";
  }
}

bool string_equals(const char * lhs, const char * rhs)
{
  return lhs != nullptr && rhs != nullptr && std::strcmp(lhs, rhs) == 0;
}

void replace_enclave(rmw_init_options_t & options, const char * enclave)
{
  if (options.enclave != nullptr && options.allocator.deallocate != nullptr) {
    options.allocator.deallocate(const_cast<char *>(options.enclave), options.allocator.state);
  }
  options.enclave = rcutils_strdup(enclave, options.allocator);
}

}  // namespace

int main()
{
  rcutils_allocator_t allocator = rcutils_get_default_allocator();
  rmw_init_options_t options = rmw_get_zero_initialized_init_options();
  rmw_init_options_t copied = rmw_get_zero_initialized_init_options();
  rmw_context_t context = rmw_get_zero_initialized_context();

  bool init_ok = rmw_init_options_init(&options, allocator) == RMW_RET_OK;
  bool default_enclave_ok = init_ok && string_equals(options.enclave, "");
  bool custom_enclave_set = false;
  bool copy_ok = false;
  bool copy_preserves_enclave = false;
  bool deep_copy_ok = false;
  bool context_init_ok = false;
  bool context_enclave_copy_ok = false;
  bool shutdown_ok = false;
  bool context_fini_ok = false;
  bool copied_fini_ok = false;
  bool options_fini_ok = false;

  if (init_ok) {
    replace_enclave(options, kCustomEnclave);
    custom_enclave_set = string_equals(options.enclave, kCustomEnclave);
  }
  if (custom_enclave_set) {
    copy_ok = rmw_init_options_copy(&options, &copied) == RMW_RET_OK;
    copy_preserves_enclave = copy_ok && string_equals(copied.enclave, kCustomEnclave);
    deep_copy_ok = copy_preserves_enclave && copied.enclave != options.enclave;
  }
  if (deep_copy_ok) {
    context_init_ok = rmw_init(&copied, &context) == RMW_RET_OK;
    context_enclave_copy_ok = context_init_ok &&
      string_equals(context.options.enclave, kCustomEnclave) &&
      context.options.enclave != copied.enclave;
  }
  if (context_init_ok) {
    shutdown_ok = rmw_shutdown(&context) == RMW_RET_OK;
  }
  if (shutdown_ok) {
    context_fini_ok = rmw_context_fini(&context) == RMW_RET_OK;
  }
  if (copy_ok) {
    copied_fini_ok = rmw_init_options_fini(&copied) == RMW_RET_OK;
  }
  if (init_ok) {
    options_fini_ok = rmw_init_options_fini(&options) == RMW_RET_OK;
  }

  const bool ok = init_ok && default_enclave_ok && custom_enclave_set && copy_ok &&
    deep_copy_ok && context_init_ok && context_enclave_copy_ok && shutdown_ok &&
    context_fini_ok && copied_fini_ok && options_fini_ok;

  std::cout << "{";
  json_string("schema_version", kSchema);
  json_string("status", ok ? "ok" : "failed");
  json_bool("security_options_lifecycle_abi_supported", init_ok && copy_ok && copied_fini_ok && options_fini_ok);
  json_bool("default_enclave_initialized", default_enclave_ok);
  json_bool("custom_enclave_configured", custom_enclave_set);
  json_bool("init_options_copy_preserves_enclave", copy_preserves_enclave);
  json_bool("init_options_copy_deep_copies_enclave", deep_copy_ok);
  json_bool("context_init_copies_security_options", context_enclave_copy_ok);
  json_bool("context_shutdown_fini_ok", shutdown_ok && context_fini_ok);
  json_bool("sros2_policy_enforcement_claim", false);
  json_bool("production_security_hardening_claim", false);
  json_int("rmw_init_options_size", static_cast<int>(sizeof(rmw_init_options_t)), false);
  std::cout << "}\n";
  return ok ? 0 : 1;
}

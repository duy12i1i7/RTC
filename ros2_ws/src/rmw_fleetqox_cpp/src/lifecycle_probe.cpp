#include <iostream>
#include <sstream>
#include <string>

#include "rcutils/allocator.h"
#include "rmw/init.h"
#include "rmw/init_options.h"
#include "rmw/rmw.h"

namespace
{

std::string json_escape(const char * value)
{
  std::ostringstream out;
  if (value == nullptr) {
    return "";
  }
  for (const char c : std::string(value)) {
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

void cleanup_after_init_failure(rmw_context_t * context, rmw_init_options_t * options)
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
  rmw_init_options_t options = rmw_get_zero_initialized_init_options();
  rmw_ret_t ret = rmw_init_options_init(&options, rcutils_get_default_allocator());
  if (ret != RMW_RET_OK) {
    std::cout << "{\"status\":\"init_options_failed\",\"ret\":" << ret << "}" << std::endl;
    return 1;
  }
  options.instance_id = 42;

  rmw_context_t context = rmw_get_zero_initialized_context();
  ret = rmw_init(&options, &context);
  if (ret != RMW_RET_OK) {
    const rmw_ret_t options_fini_ret = rmw_init_options_fini(&options);
    (void)options_fini_ret;
    std::cout << "{\"status\":\"init_failed\",\"ret\":" << ret << "}" << std::endl;
    return 1;
  }

  rmw_node_t * node = rmw_create_node(&context, "fleetqox_lifecycle_probe", "/fleetqox");
  if (node == nullptr) {
    cleanup_after_init_failure(&context, &options);
    std::cout << "{\"status\":\"create_node_failed\"}" << std::endl;
    return 1;
  }

  std::cout << "{\"schema_version\":\"fleetrmw.rmw_lifecycle_probe.v1\",";
  std::cout << "\"status\":\"ok\",";
  std::cout << "\"implementation_identifier\":\"" << json_escape(context.implementation_identifier) << "\",";
  std::cout << "\"node_name\":\"" << json_escape(node->name) << "\",";
  std::cout << "\"node_namespace\":\"" << json_escape(node->namespace_) << "\",";
  std::cout << "\"instance_id\":" << context.instance_id << ",";
  std::cout << "\"actual_domain_id\":" << context.actual_domain_id << "}" << std::endl;

  ret = rmw_destroy_node(node);
  if (ret != RMW_RET_OK) {
    return 1;
  }
  ret = rmw_shutdown(&context);
  if (ret != RMW_RET_OK) {
    return 1;
  }
  ret = rmw_context_fini(&context);
  if (ret != RMW_RET_OK) {
    return 1;
  }
  ret = rmw_init_options_fini(&options);
  return ret == RMW_RET_OK ? 0 : 1;
}

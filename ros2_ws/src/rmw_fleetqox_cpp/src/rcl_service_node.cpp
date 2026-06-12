#include <chrono>
#include <cstdlib>
#include <cstdint>
#include <iostream>
#include <sstream>
#include <string>
#include <thread>

#include "rcl/init.h"
#include "rcl/init_options.h"
#include "rcl/node.h"
#include "rcl/service.h"
#include "rcl/error_handling.h"
#include "rcutils/allocator.h"
#include "rosidl_runtime_c/string_functions.h"
#include "rosidl_typesupport_interface/macros.h"
#include "std_srvs/srv/detail/set_bool__functions.h"
#include "std_srvs/srv/detail/set_bool__rosidl_typesupport_introspection_c.h"
#include "std_srvs/srv/detail/set_bool__struct.h"

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

int int_arg(int argc, char ** argv, const char * name, int default_value)
{
  for (int i = 1; i + 1 < argc; ++i) {
    if (std::string(argv[i]) == name) {
      return std::stoi(argv[i + 1]);
    }
  }
  return default_value;
}

std::string string_arg(int argc, char ** argv, const char * name, const std::string & default_value)
{
  for (int i = 1; i + 1 < argc; ++i) {
    if (std::string(argv[i]) == name) {
      return argv[i + 1];
    }
  }
  return default_value;
}

void cleanup_rcl(
  rcl_service_t * service,
  rcl_node_t * node,
  rcl_context_t * context,
  rcl_init_options_t * init_options)
{
  if (service != nullptr) {
    const rcl_ret_t service_ret = rcl_service_fini(service, node);
    (void)service_ret;
  }
  if (node != nullptr) {
    const rcl_ret_t node_ret = rcl_node_fini(node);
    (void)node_ret;
  }
  if (context != nullptr) {
    const rcl_ret_t shutdown_ret = rcl_shutdown(context);
    const rcl_ret_t context_ret = rcl_context_fini(context);
    (void)shutdown_ret;
    (void)context_ret;
  }
  if (init_options != nullptr) {
    const rcl_ret_t options_ret = rcl_init_options_fini(init_options);
    (void)options_ret;
  }
}

}  // namespace

int main(int argc, char ** argv)
{
  setenv("RMW_IMPLEMENTATION", "rmw_fleetqox_cpp", 1);

  const std::string service_name = string_arg(argc, argv, "--service", "/fleetqox/set_bool");
  const int hold_ms = int_arg(argc, argv, "--hold-ms", 5500);
  const int response_delay_ms = int_arg(argc, argv, "--response-delay-ms", 0);

  rcl_allocator_t allocator = rcl_get_default_allocator();
  rcl_init_options_t init_options = rcl_get_zero_initialized_init_options();
  rcl_ret_t ret = rcl_init_options_init(&init_options, allocator);
  if (ret != RCL_RET_OK) {
    std::cout << "{\"status\":\"init_options_failed\",\"ret\":" << ret << "}" << std::endl;
    return 1;
  }

  rcl_context_t context = rcl_get_zero_initialized_context();
  int rcl_argc = 0;
  char ** rcl_argv = nullptr;
  ret = rcl_init(rcl_argc, rcl_argv, &init_options, &context);
  if (ret != RCL_RET_OK) {
    const rcl_ret_t options_ret = rcl_init_options_fini(&init_options);
    (void)options_ret;
    std::cout << "{\"status\":\"rcl_init_failed\",\"ret\":" << ret << "}" << std::endl;
    return 1;
  }

  rcl_node_t node = rcl_get_zero_initialized_node();
  rcl_node_options_t node_options = rcl_node_get_default_options();
  ret = rcl_node_init(&node, "fleetqox_rcl_service_node", "/fleetqox", &context, &node_options);
  if (ret != RCL_RET_OK) {
    cleanup_rcl(nullptr, nullptr, &context, &init_options);
    std::cout << "{\"status\":\"node_init_failed\",\"ret\":" << ret << "}" << std::endl;
    return 1;
  }

  const rosidl_service_type_support_t * type_support =
    ROSIDL_TYPESUPPORT_INTERFACE__SERVICE_SYMBOL_NAME(
    rosidl_typesupport_introspection_c, std_srvs, srv, SetBool)();
  rcl_service_t service = rcl_get_zero_initialized_service();
  rcl_service_options_t service_options = rcl_service_get_default_options();
  ret = rcl_service_init(&service, &node, type_support, service_name.c_str(), &service_options);
  if (ret != RCL_RET_OK) {
    cleanup_rcl(nullptr, &node, &context, &init_options);
    std::cout << "{\"status\":\"service_init_failed\",\"ret\":" << ret << "}" << std::endl;
    return 1;
  }

  const auto deadline = std::chrono::steady_clock::now() + std::chrono::milliseconds(hold_ms);
  int request_count = 0;
  ret = RCL_RET_OK;
  while (std::chrono::steady_clock::now() < deadline) {
    rmw_request_id_t request_header{};
    std_srvs__srv__SetBool_Request request;
    if (!std_srvs__srv__SetBool_Request__init(&request)) {
      ret = RCL_RET_BAD_ALLOC;
      break;
    }
    const rcl_ret_t take_ret = rcl_take_request(&service, &request_header, &request);
    if (take_ret == RCL_RET_OK) {
      if (response_delay_ms > 0) {
        std::this_thread::sleep_for(std::chrono::milliseconds(response_delay_ms));
      }
      std_srvs__srv__SetBool_Response response;
      if (!std_srvs__srv__SetBool_Response__init(&response)) {
        std_srvs__srv__SetBool_Request__fini(&request);
        ret = RCL_RET_BAD_ALLOC;
        break;
      }
      response.success = request.data;
      const std::string message = request.data ? "fleetqox set_bool accepted" : "fleetqox set_bool rejected";
      if (!rosidl_runtime_c__String__assignn(&response.message, message.data(), message.size())) {
        std_srvs__srv__SetBool_Response__fini(&response);
        std_srvs__srv__SetBool_Request__fini(&request);
        ret = RCL_RET_BAD_ALLOC;
        break;
      }
      ret = rcl_send_response(&service, &request_header, &response);
      std_srvs__srv__SetBool_Response__fini(&response);
      if (ret != RCL_RET_OK) {
        std_srvs__srv__SetBool_Request__fini(&request);
        break;
      }
      ++request_count;
    } else if (take_ret == RCL_RET_SERVICE_TAKE_FAILED) {
      rcl_reset_error();
      std::this_thread::sleep_for(std::chrono::milliseconds(5));
    } else {
      ret = take_ret;
      std_srvs__srv__SetBool_Request__fini(&request);
      break;
    }
    std_srvs__srv__SetBool_Request__fini(&request);
  }
  const bool ok = ret == RCL_RET_OK;

  std::cout << "{\"schema_version\":\"fleetrmw.rcl_service_node.v1\",";
  std::cout << "\"status\":\"" << (ok ? "ok" : "failed") << "\",";
  std::cout << "\"service\":\"" << json_escape(service_name) << "\",";
  std::cout << "\"type\":\"std_srvs/srv/SetBool\",";
  std::cout << "\"response_delay_ms\":" << response_delay_ms << ",";
  std::cout << "\"request_count\":" << request_count << "}" << std::endl;

  cleanup_rcl(&service, &node, &context, &init_options);
  return ok ? 0 : 1;
}

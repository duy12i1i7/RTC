#include <chrono>
#include <cstdint>
#include <iostream>
#include <string>
#include <thread>

#include "rcutils/allocator.h"
#include "rcutils/types/string_array.h"
#include "rmw/get_topic_names_and_types.h"
#include "rmw/init.h"
#include "rmw/init_options.h"
#include "rmw/names_and_types.h"
#include "rmw/rmw.h"

extern "C" void rmw_fleetqox_cpp_graph_apply_remote_advertisement(
  const char * action,
  const char * entity_kind,
  const char * node_name,
  const char * node_namespace,
  const char * topic_name,
  const char * type_name,
  const char * endpoint_id,
  std::uint64_t lease_ms);

namespace
{

constexpr const char * kTopic = "/fleetqox/remote_graph_lease_probe";
constexpr const char * kType = "rmw_fleetqox_cpp_lease_probe";

struct GraphState
{
  bool topic_found{false};
  size_t node_count{0};
  size_t topic_count{0};
  size_t publisher_count{0};
};

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
  options->instance_id = 45;
  *context = rmw_get_zero_initialized_context();
  if (rmw_init(options, context) != RMW_RET_OK) {
    const rmw_ret_t fini_ret = rmw_init_options_fini(options);
    (void)fini_ret;
    return false;
  }
  return true;
}

GraphState read_graph(const rmw_node_t * node, rcutils_allocator_t * allocator)
{
  GraphState state;
  rmw_names_and_types_t names_and_types = rmw_get_zero_initialized_names_and_types();
  if (rmw_get_topic_names_and_types(node, allocator, false, &names_and_types) == RMW_RET_OK) {
    state.topic_count = names_and_types.names.size;
    for (size_t i = 0; i < names_and_types.names.size; ++i) {
      if (names_and_types.names.data[i] != nullptr && std::string(names_and_types.names.data[i]) == kTopic) {
        state.topic_found = true;
      }
    }
  }
  const rmw_ret_t topics_fini_ret = rmw_names_and_types_fini(&names_and_types);
  (void)topics_fini_ret;

  rcutils_string_array_t node_names = rcutils_get_zero_initialized_string_array();
  rcutils_string_array_t node_namespaces = rcutils_get_zero_initialized_string_array();
  if (rmw_get_node_names(node, &node_names, &node_namespaces) == RMW_RET_OK) {
    state.node_count = node_names.size;
  }
  const rcutils_ret_t names_fini_ret = rcutils_string_array_fini(&node_names);
  const rcutils_ret_t namespaces_fini_ret = rcutils_string_array_fini(&node_namespaces);
  (void)names_fini_ret;
  (void)namespaces_fini_ret;

  const rmw_ret_t count_ret = rmw_count_publishers(node, kTopic, &state.publisher_count);
  if (count_ret != RMW_RET_OK) {
    state.publisher_count = 0;
  }
  return state;
}

}  // namespace

int main()
{
  rcutils_allocator_t allocator = rcutils_get_default_allocator();
  rmw_init_options_t options{};
  rmw_context_t context{};
  if (!init_context(allocator, &options, &context)) {
    std::cout << "{\"status\":\"init_failed\"}" << std::endl;
    return 1;
  }

  rmw_node_t * node = rmw_create_node(&context, "fleetqox_remote_graph_lease_probe", "/fleetqox");
  if (node == nullptr) {
    cleanup_context(&context, &options);
    std::cout << "{\"status\":\"create_node_failed\"}" << std::endl;
    return 1;
  }

  rmw_fleetqox_cpp_graph_apply_remote_advertisement(
    "add",
    "publisher",
    "remote_lease_talker",
    "/fleetqox",
    kTopic,
    kType,
    "lease-endpoint-1",
    30);
  const GraphState before = read_graph(node, &allocator);
  std::this_thread::sleep_for(std::chrono::milliseconds(70));
  const GraphState after = read_graph(node, &allocator);

  const bool ok = before.topic_found &&
                  before.publisher_count == 1 &&
                  before.node_count >= 2 &&
                  !after.topic_found &&
                  after.publisher_count == 0 &&
                  after.node_count == 1;

  std::cout << "{\"schema_version\":\"fleetrmw.rmw_remote_graph_lease_probe.v1\",";
  std::cout << "\"status\":\"" << (ok ? "ok" : "failed") << "\",";
  std::cout << "\"topic\":\"" << kTopic << "\",";
  std::cout << "\"publisher_count_before\":" << before.publisher_count << ",";
  std::cout << "\"publisher_count_after\":" << after.publisher_count << ",";
  std::cout << "\"topic_found_before\":" << (before.topic_found ? "true" : "false") << ",";
  std::cout << "\"topic_found_after\":" << (after.topic_found ? "true" : "false") << ",";
  std::cout << "\"node_count_before\":" << before.node_count << ",";
  std::cout << "\"node_count_after\":" << after.node_count << "}" << std::endl;

  const rmw_ret_t destroy_node_ret = rmw_destroy_node(node);
  (void)destroy_node_ret;
  cleanup_context(&context, &options);
  return ok ? 0 : 1;
}

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
extern "C" void rmw_fleetqox_cpp_graph_apply_remote_advertisement_with_info(
  const char * action,
  const char * entity_kind,
  const char * node_name,
  const char * node_namespace,
  const char * topic_name,
  const char * type_name,
  const char * endpoint_id,
  const std::uint8_t * endpoint_gid,
  size_t endpoint_gid_size,
  const rmw_qos_profile_t * qos,
  std::uint64_t lease_ms);
extern "C" size_t rmw_fleetqox_cpp_graph_matching_service_count(
  const char * service_name,
  const char * type_name,
  const rmw_qos_profile_t * client_qos);
extern "C" bool rmw_fleetqox_cpp_graph_client_matches_service(
  const char * client_endpoint_id,
  const char * service_name,
  const char * type_name,
  const rmw_qos_profile_t * service_qos);

namespace
{

constexpr const char * kTopic = "/fleetqox/remote_graph_lease_probe";
constexpr const char * kMovedTopic = "/fleetqox/remote_graph_lease_probe_moved";
constexpr const char * kType = "rmw_fleetqox_cpp_lease_probe";
constexpr const char * kService = "/fleetqox/remote_service_matching_probe";
constexpr const char * kServiceType = "std_srvs/srv/SetBool";

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

GraphState read_graph(
  const rmw_node_t * node,
  rcutils_allocator_t * allocator,
  const char * topic_name)
{
  GraphState state;
  rmw_names_and_types_t names_and_types = rmw_get_zero_initialized_names_and_types();
  if (rmw_get_topic_names_and_types(node, allocator, false, &names_and_types) == RMW_RET_OK) {
    state.topic_count = names_and_types.names.size;
    for (size_t i = 0; i < names_and_types.names.size; ++i) {
      if (names_and_types.names.data[i] != nullptr &&
        std::string(names_and_types.names.data[i]) == topic_name)
      {
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

  const rmw_ret_t count_ret = rmw_count_publishers(node, topic_name, &state.publisher_count);
  if (count_ret != RMW_RET_OK) {
    state.publisher_count = 0;
  }
  return state;
}

bool wait_for_graph_guard(
  rmw_wait_set_t * wait_set,
  const rmw_guard_condition_t * graph_guard,
  std::uint64_t timeout_ms)
{
  void * guard_items[1] = {const_cast<rmw_guard_condition_t *>(graph_guard)};
  rmw_guard_conditions_t guard_conditions{1, guard_items};
  rmw_time_t timeout{timeout_ms / 1000, (timeout_ms % 1000) * 1000000};
  const rmw_ret_t ret = rmw_wait(
    nullptr, &guard_conditions, nullptr, nullptr, nullptr, wait_set, &timeout);
  return ret == RMW_RET_OK && guard_conditions.guard_conditions[0] != nullptr;
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
  rmw_wait_set_t * wait_set = rmw_create_wait_set(&context, 1);
  if (node == nullptr || wait_set == nullptr) {
    if (wait_set != nullptr) {
      const rmw_ret_t destroy_wait_ret = rmw_destroy_wait_set(wait_set);
      (void)destroy_wait_ret;
    }
    if (node != nullptr) {
      const rmw_ret_t destroy_node_ret = rmw_destroy_node(node);
      (void)destroy_node_ret;
    }
    cleanup_context(&context, &options);
    std::cout << "{\"status\":\"create_node_or_wait_set_failed\"}" << std::endl;
    return 1;
  }
  const rmw_guard_condition_t * graph_guard = rmw_node_get_graph_guard_condition(node);
  const bool initial_graph_guard = wait_for_graph_guard(wait_set, graph_guard, 0);
  (void)initial_graph_guard;

  rmw_fleetqox_cpp_graph_apply_remote_advertisement(
    "add",
    "publisher",
    "remote_moving_talker",
    "/fleetqox",
    kTopic,
    kType,
    "moving-endpoint-1",
    5000);
  const bool graph_guard_add_ok = wait_for_graph_guard(wait_set, graph_guard, 0);
  const GraphState move_before = read_graph(node, &allocator, kTopic);
  rmw_fleetqox_cpp_graph_apply_remote_advertisement(
    "add",
    "publisher",
    "remote_moving_talker",
    "/fleetqox",
    kTopic,
    kType,
    "moving-endpoint-1",
    5000);
  const bool graph_guard_renewal_dedup_ok =
    !wait_for_graph_guard(wait_set, graph_guard, 0);
  rmw_fleetqox_cpp_graph_apply_remote_advertisement(
    "add",
    "publisher",
    "remote_moving_talker",
    "/fleetqox",
    kMovedTopic,
    kType,
    "moving-endpoint-1",
    5000);
  const bool graph_guard_descriptor_change_ok = wait_for_graph_guard(wait_set, graph_guard, 0);
  const GraphState old_after_move = read_graph(node, &allocator, kTopic);
  const GraphState new_after_move = read_graph(node, &allocator, kMovedTopic);
  rmw_fleetqox_cpp_graph_apply_remote_advertisement(
    "remove",
    "publisher",
    "stale_descriptor_is_ignored",
    "/stale",
    kTopic,
    "stale/type",
    "moving-endpoint-1",
    5000);
  const bool graph_guard_remove_ok = wait_for_graph_guard(wait_set, graph_guard, 0);
  const GraphState moved_after_stale_remove = read_graph(node, &allocator, kMovedTopic);

  rmw_fleetqox_cpp_graph_apply_remote_advertisement(
    "add",
    "publisher",
    "remote_lease_talker",
    "/fleetqox",
    kTopic,
    kType,
    "lease-endpoint-1",
    30);
  const bool graph_guard_lease_add_ok = wait_for_graph_guard(wait_set, graph_guard, 0);
  const GraphState before = read_graph(node, &allocator, kTopic);
  std::this_thread::sleep_for(std::chrono::milliseconds(70));
  const bool graph_guard_expiry_ok = wait_for_graph_guard(wait_set, graph_guard, 100);
  const GraphState after = read_graph(node, &allocator, kTopic);

  rmw_qos_profile_t reliable_qos = rmw_qos_profile_default;
  reliable_qos.reliability = RMW_QOS_POLICY_RELIABILITY_RELIABLE;
  rmw_qos_profile_t best_effort_qos = reliable_qos;
  best_effort_qos.reliability = RMW_QOS_POLICY_RELIABILITY_BEST_EFFORT;
  rmw_fleetqox_cpp_graph_apply_remote_advertisement_with_info(
    "add", "service", "remote_service", "/fleetqox", kService, kServiceType,
    "remote-service-endpoint-1", nullptr, 0, &reliable_qos, 5000);
  const size_t remote_matching_count = rmw_fleetqox_cpp_graph_matching_service_count(
    kService, kServiceType, &reliable_qos);
  const size_t remote_wrong_type_count = rmw_fleetqox_cpp_graph_matching_service_count(
    kService, "std_srvs/srv/Trigger", &reliable_qos);
  rmw_fleetqox_cpp_graph_apply_remote_advertisement_with_info(
    "add", "service", "remote_service", "/fleetqox", kService, kServiceType,
    "remote-service-endpoint-1", nullptr, 0, &best_effort_qos, 5000);
  const size_t remote_incompatible_qos_count = rmw_fleetqox_cpp_graph_matching_service_count(
    kService, kServiceType, &reliable_qos);
  rmw_fleetqox_cpp_graph_apply_remote_advertisement_with_info(
    "add", "service", "remote_service", "/fleetqox", kService, kServiceType,
    "remote-service-endpoint-1", nullptr, 0, &reliable_qos, 5000);
  const size_t remote_restored_qos_count = rmw_fleetqox_cpp_graph_matching_service_count(
    kService, kServiceType, &reliable_qos);
  rmw_fleetqox_cpp_graph_apply_remote_advertisement(
    "remove", "service", "stale_service_descriptor", "/stale",
    "/stale/service", "stale/type", "remote-service-endpoint-1", 5000);
  const size_t remote_after_remove_count = rmw_fleetqox_cpp_graph_matching_service_count(
    kService, kServiceType, &reliable_qos);
  rmw_fleetqox_cpp_graph_apply_remote_advertisement_with_info(
    "add", "client", "remote_client", "/fleetqox", kService, kServiceType,
    "remote-client-endpoint-1", nullptr, 0, &reliable_qos, 5000);
  const bool remote_client_matches = rmw_fleetqox_cpp_graph_client_matches_service(
    "remote-client-endpoint-1", kService, kServiceType, &reliable_qos);
  const bool remote_client_wrong_type_matches = rmw_fleetqox_cpp_graph_client_matches_service(
    "remote-client-endpoint-1", kService, "std_srvs/srv/Trigger", &reliable_qos);
  rmw_fleetqox_cpp_graph_apply_remote_advertisement_with_info(
    "add", "client", "remote_client", "/fleetqox", kService, kServiceType,
    "remote-client-endpoint-1", nullptr, 0, &best_effort_qos, 5000);
  const bool remote_client_incompatible_qos_matches =
    rmw_fleetqox_cpp_graph_client_matches_service(
    "remote-client-endpoint-1", kService, kServiceType, &reliable_qos);
  rmw_fleetqox_cpp_graph_apply_remote_advertisement_with_info(
    "add", "client", "remote_client", "/fleetqox", kService, kServiceType,
    "remote-client-endpoint-1", nullptr, 0, &reliable_qos, 5000);
  const bool remote_client_restored_qos_matches =
    rmw_fleetqox_cpp_graph_client_matches_service(
    "remote-client-endpoint-1", kService, kServiceType, &reliable_qos);
  rmw_fleetqox_cpp_graph_apply_remote_advertisement(
    "remove", "client", "stale_client_descriptor", "/stale",
    "/stale/service", "stale/type", "remote-client-endpoint-1", 5000);
  const bool remote_client_after_remove_matches =
    rmw_fleetqox_cpp_graph_client_matches_service(
    "remote-client-endpoint-1", kService, kServiceType, &reliable_qos);

  const bool identity_update_ok =
                  move_before.topic_found &&
                  move_before.publisher_count == 1 &&
                  !old_after_move.topic_found &&
                  old_after_move.publisher_count == 0 &&
                  new_after_move.topic_found &&
                  new_after_move.publisher_count == 1 &&
                  new_after_move.node_count == 2 &&
                  !moved_after_stale_remove.topic_found &&
                  moved_after_stale_remove.publisher_count == 0 &&
                  moved_after_stale_remove.node_count == 1;
  const bool lease_expiry_ok = before.topic_found &&
                  before.publisher_count == 1 &&
                  before.node_count >= 2 &&
                  !after.topic_found &&
                  after.publisher_count == 0 &&
                  after.node_count == 1;
  const bool remote_service_matching_ok =
    remote_matching_count == 1 &&
    remote_wrong_type_count == 0 &&
    remote_incompatible_qos_count == 0 &&
    remote_restored_qos_count == 1 &&
    remote_after_remove_count == 0;
  const bool remote_client_matching_ok =
    remote_client_matches &&
    !remote_client_wrong_type_matches &&
    !remote_client_incompatible_qos_matches &&
    remote_client_restored_qos_matches &&
    !remote_client_after_remove_matches;
  const bool automatic_graph_guard_ok =
    graph_guard_add_ok && graph_guard_renewal_dedup_ok &&
    graph_guard_descriptor_change_ok && graph_guard_remove_ok &&
    graph_guard_lease_add_ok && graph_guard_expiry_ok;
  const bool ok = identity_update_ok && lease_expiry_ok &&
    remote_service_matching_ok && remote_client_matching_ok && automatic_graph_guard_ok;

  std::cout << "{\"schema_version\":\"fleetrmw.rmw_remote_graph_lease_probe.v1\",";
  std::cout << "\"status\":\"" << (ok ? "ok" : "failed") << "\",";
  std::cout << "\"topic\":\"" << kTopic << "\",";
  std::cout << "\"identity_update_ok\":" << (identity_update_ok ? "true" : "false") << ",";
  std::cout << "\"lease_expiry_ok\":" << (lease_expiry_ok ? "true" : "false") << ",";
  std::cout << "\"remote_service_matching_ok\":" <<
    (remote_service_matching_ok ? "true" : "false") << ",";
  std::cout << "\"remote_client_matching_ok\":" <<
    (remote_client_matching_ok ? "true" : "false") << ",";
  std::cout << "\"automatic_graph_guard_ok\":" <<
    (automatic_graph_guard_ok ? "true" : "false") << ",";
  std::cout << "\"graph_guard_renewal_dedup_ok\":" <<
    (graph_guard_renewal_dedup_ok ? "true" : "false") << ",";
  std::cout << "\"graph_guard_expiry_ok\":" <<
    (graph_guard_expiry_ok ? "true" : "false") << ",";
  std::cout << "\"remote_service_matching_count\":" << remote_matching_count << ",";
  std::cout << "\"remote_service_wrong_type_count\":" << remote_wrong_type_count << ",";
  std::cout << "\"remote_service_incompatible_qos_count\":" <<
    remote_incompatible_qos_count << ",";
  std::cout << "\"remote_service_restored_qos_count\":" << remote_restored_qos_count << ",";
  std::cout << "\"remote_service_after_remove_count\":" << remote_after_remove_count << ",";
  std::cout << "\"old_topic_count_after_move\":" << old_after_move.publisher_count << ",";
  std::cout << "\"new_topic_count_after_move\":" << new_after_move.publisher_count << ",";
  std::cout << "\"moved_topic_count_after_stale_remove\":"
            << moved_after_stale_remove.publisher_count << ",";
  std::cout << "\"publisher_count_before\":" << before.publisher_count << ",";
  std::cout << "\"publisher_count_after\":" << after.publisher_count << ",";
  std::cout << "\"topic_found_before\":" << (before.topic_found ? "true" : "false") << ",";
  std::cout << "\"topic_found_after\":" << (after.topic_found ? "true" : "false") << ",";
  std::cout << "\"node_count_before\":" << before.node_count << ",";
  std::cout << "\"node_count_after\":" << after.node_count << "}" << std::endl;

  const rmw_ret_t destroy_wait_ret = rmw_destroy_wait_set(wait_set);
  const rmw_ret_t destroy_node_ret = rmw_destroy_node(node);
  (void)destroy_wait_ret;
  (void)destroy_node_ret;
  cleanup_context(&context, &options);
  return ok ? 0 : 1;
}

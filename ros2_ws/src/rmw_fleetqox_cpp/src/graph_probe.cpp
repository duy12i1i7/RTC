#include <iostream>

#include "rcutils/allocator.h"
#include "rcutils/types/string_array.h"
#include "rmw/init.h"
#include "rmw/init_options.h"
#include "rmw/get_topic_names_and_types.h"
#include "rmw/names_and_types.h"
#include "rmw/publisher_options.h"
#include "rmw/qos_profiles.h"
#include "rmw/rmw.h"
#include "rmw/subscription_options.h"
#include "rosidl_runtime_c/message_type_support_struct.h"

namespace
{

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
  rcutils_allocator_t allocator = rcutils_get_default_allocator();
  rmw_init_options_t options = rmw_get_zero_initialized_init_options();
  if (rmw_init_options_init(&options, allocator) != RMW_RET_OK) {
    std::cout << "{\"status\":\"init_options_failed\"}" << std::endl;
    return 1;
  }
  options.instance_id = 45;
  rmw_context_t context = rmw_get_zero_initialized_context();
  if (rmw_init(&options, &context) != RMW_RET_OK) {
    const rmw_ret_t fini_ret = rmw_init_options_fini(&options);
    (void)fini_ret;
    std::cout << "{\"status\":\"init_failed\"}" << std::endl;
    return 1;
  }
  rmw_node_t * node = rmw_create_node(&context, "fleetqox_graph_probe", "/fleetqox");
  if (node == nullptr) {
    cleanup_context(&context, &options);
    std::cout << "{\"status\":\"create_node_failed\"}" << std::endl;
    return 1;
  }

  rosidl_message_type_support_t type_support{};
  type_support.typesupport_identifier = "fleetqox/msg/SerializedProbe";
  rmw_qos_profile_t qos = rmw_qos_profile_default;
  rmw_publisher_options_t publisher_options = rmw_get_default_publisher_options();
  rmw_subscription_options_t subscription_options = rmw_get_default_subscription_options();
  rmw_publisher_t * publisher = rmw_create_publisher(
    node, &type_support, "/fleetqox/graph_probe", &qos, &publisher_options);
  rmw_subscription_t * subscription = rmw_create_subscription(
    node, &type_support, "/fleetqox/graph_probe", &qos, &subscription_options);

  rcutils_string_array_t node_names = rcutils_get_zero_initialized_string_array();
  rcutils_string_array_t node_namespaces = rcutils_get_zero_initialized_string_array();
  rmw_names_and_types_t topic_names_and_types = rmw_get_zero_initialized_names_and_types();
  size_t publisher_count = 0;
  size_t subscriber_count = 0;
  const rmw_ret_t node_names_ret = rmw_get_node_names(node, &node_names, &node_namespaces);
  const rmw_ret_t topics_ret =
    rmw_get_topic_names_and_types(node, &allocator, false, &topic_names_and_types);
  const rmw_ret_t publisher_count_ret =
    rmw_count_publishers(node, "/fleetqox/graph_probe", &publisher_count);
  const rmw_ret_t subscriber_count_ret =
    rmw_count_subscribers(node, "/fleetqox/graph_probe", &subscriber_count);

  const bool ok = publisher != nullptr &&
                  subscription != nullptr &&
                  node_names_ret == RMW_RET_OK &&
                  topics_ret == RMW_RET_OK &&
                  publisher_count_ret == RMW_RET_OK &&
                  subscriber_count_ret == RMW_RET_OK &&
                  node_names.size >= 1 &&
                  topic_names_and_types.names.size >= 1 &&
                  publisher_count == 1 &&
                  subscriber_count == 1;

  std::cout << "{\"schema_version\":\"fleetrmw.rmw_graph_probe.v1\",";
  std::cout << "\"status\":\"" << (ok ? "ok" : "failed") << "\",";
  std::cout << "\"node_count\":" << node_names.size << ",";
  std::cout << "\"topic_count\":" << topic_names_and_types.names.size << ",";
  std::cout << "\"publisher_count\":" << publisher_count << ",";
  std::cout << "\"subscriber_count\":" << subscriber_count << ",";
  std::cout << "\"topic\":\"/fleetqox/graph_probe\"}" << std::endl;

  const rmw_ret_t topics_fini_ret = rmw_names_and_types_fini(&topic_names_and_types);
  const rcutils_ret_t names_fini_ret = rcutils_string_array_fini(&node_names);
  const rcutils_ret_t namespaces_fini_ret = rcutils_string_array_fini(&node_namespaces);
  (void)topics_fini_ret;
  (void)names_fini_ret;
  (void)namespaces_fini_ret;
  if (publisher != nullptr) {
    const rmw_ret_t destroy_pub_ret = rmw_destroy_publisher(node, publisher);
    (void)destroy_pub_ret;
  }
  if (subscription != nullptr) {
    const rmw_ret_t destroy_sub_ret = rmw_destroy_subscription(node, subscription);
    (void)destroy_sub_ret;
  }
  const rmw_ret_t destroy_node_ret = rmw_destroy_node(node);
  (void)destroy_node_ret;
  cleanup_context(&context, &options);
  return ok ? 0 : 1;
}

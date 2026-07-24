#include <chrono>
#include <cstdint>
#include <cstring>
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
#include "rosidl_typesupport_interface/macros.h"
#include "std_srvs/srv/detail/set_bool__functions.h"
#include "std_srvs/srv/detail/set_bool__rosidl_typesupport_introspection_c.h"

extern "C" void rmw_fleetqox_cpp_graph_apply_remote_advertisement_in_domain(
  const char * action,
  const char * entity_kind,
  const char * node_name,
  const char * node_namespace,
  const char * topic_name,
  const char * type_name,
  const char * endpoint_id,
  std::uint64_t domain_id,
  std::uint64_t lease_ms);

namespace
{

constexpr std::size_t kDomainA = 31;
constexpr std::size_t kDomainB = 32;

struct ContextBundle
{
  rmw_init_options_t options{rmw_get_zero_initialized_init_options()};
  rmw_context_t context{rmw_get_zero_initialized_context()};
  bool options_initialized{false};
  bool context_initialized{false};
};

bool initialize_context(
  ContextBundle * bundle,
  rcutils_allocator_t allocator,
  std::size_t domain_id,
  std::uint64_t instance_id)
{
  if (bundle == nullptr || rmw_init_options_init(&bundle->options, allocator) != RMW_RET_OK) {
    return false;
  }
  bundle->options_initialized = true;
  bundle->options.domain_id = domain_id;
  bundle->options.instance_id = instance_id;
  if (rmw_init(&bundle->options, &bundle->context) != RMW_RET_OK) {
    return false;
  }
  bundle->context_initialized = true;
  return true;
}

void cleanup_context(ContextBundle * bundle)
{
  if (bundle == nullptr) {
    return;
  }
  if (bundle->context_initialized) {
    const rmw_ret_t shutdown_ret = rmw_shutdown(&bundle->context);
    const rmw_ret_t fini_ret = rmw_context_fini(&bundle->context);
    (void)shutdown_ret;
    (void)fini_ret;
    bundle->context_initialized = false;
  }
  if (bundle->options_initialized) {
    const rmw_ret_t fini_ret = rmw_init_options_fini(&bundle->options);
    (void)fini_ret;
    bundle->options_initialized = false;
  }
}

bool graph_guard_ready(
  const rmw_guard_condition_t * graph_guard,
  rmw_wait_set_t * wait_set)
{
  if (graph_guard == nullptr || wait_set == nullptr) {
    return false;
  }
  void * guard_items[1] = {const_cast<rmw_guard_condition_t *>(graph_guard)};
  rmw_guard_conditions_t guards{1, guard_items};
  rmw_time_t timeout{0, 0};
  const rmw_ret_t ret = rmw_wait(
    nullptr, &guards, nullptr, nullptr, nullptr, wait_set, &timeout);
  return ret == RMW_RET_OK && guards.guard_conditions[0] != nullptr;
}

void drain_graph_guard(
  const rmw_guard_condition_t * graph_guard,
  rmw_wait_set_t * wait_set)
{
  (void)graph_guard_ready(graph_guard, wait_set);
}

bool take_serialized_with_retry(
  const rmw_subscription_t * subscription,
  rmw_serialized_message_t * message,
  bool * taken)
{
  if (subscription == nullptr || message == nullptr || taken == nullptr) {
    return false;
  }
  *taken = false;
  for (int attempt = 0; attempt < 200; ++attempt) {
    const rmw_ret_t ret = rmw_take_serialized_message(
      subscription, message, taken, nullptr);
    if (ret != RMW_RET_OK) {
      return false;
    }
    if (*taken) {
      return true;
    }
    std::this_thread::sleep_for(std::chrono::milliseconds(1));
  }
  return true;
}

}  // namespace

int main()
{
  rcutils_allocator_t allocator = rcutils_get_default_allocator();
  ContextBundle domain_a;
  ContextBundle domain_b;
  if (!initialize_context(&domain_a, allocator, kDomainA, 3101) ||
    !initialize_context(&domain_b, allocator, kDomainB, 3201))
  {
    cleanup_context(&domain_b);
    cleanup_context(&domain_a);
    std::cout << "{\"status\":\"context_init_failed\"}" << std::endl;
    return 1;
  }

  rmw_node_t * node_a = rmw_create_node(&domain_a.context, "domain_a", "/fleetqox");
  rmw_node_t * node_a_peer = rmw_create_node(&domain_a.context, "domain_a_peer", "/fleetqox");
  rmw_node_t * node_b = rmw_create_node(&domain_b.context, "domain_b", "/fleetqox");
  rmw_wait_set_t * wait_a = rmw_create_wait_set(&domain_a.context, 1);
  rmw_wait_set_t * wait_b = rmw_create_wait_set(&domain_b.context, 1);
  if (node_a == nullptr || node_a_peer == nullptr || node_b == nullptr ||
    wait_a == nullptr || wait_b == nullptr)
  {
    std::cout << "{\"status\":\"node_wait_set_create_failed\"}" << std::endl;
    return 1;
  }

  const rmw_guard_condition_t * guard_a = rmw_node_get_graph_guard_condition(node_a);
  const rmw_guard_condition_t * guard_b = rmw_node_get_graph_guard_condition(node_b);
  drain_graph_guard(guard_a, wait_a);
  drain_graph_guard(guard_b, wait_b);

  rosidl_message_type_support_t message_type_support{};
  message_type_support.typesupport_identifier = "rmw_fleetqox_cpp_domain_isolation_probe";
  rmw_qos_profile_t qos = rmw_qos_profile_default;
  rmw_publisher_options_t publisher_options = rmw_get_default_publisher_options();
  rmw_subscription_options_t subscription_options = rmw_get_default_subscription_options();
  const char * topic_name = "/fleetqox/domain_isolation";
  rmw_publisher_t * publisher_a = rmw_create_publisher(
    node_a, &message_type_support, topic_name, &qos, &publisher_options);
  const bool domain_a_guard_on_local_add = graph_guard_ready(guard_a, wait_a);
  const bool domain_b_guard_suppressed_on_domain_a_add = !graph_guard_ready(guard_b, wait_b);

  rmw_subscription_t * subscription_a = rmw_create_subscription(
    node_a_peer, &message_type_support, topic_name, &qos, &subscription_options);
  rmw_subscription_t * subscription_b = rmw_create_subscription(
    node_b, &message_type_support, topic_name, &qos, &subscription_options);

  size_t publishers_seen_from_a = 0;
  size_t publishers_seen_from_b = 0;
  size_t subscribers_seen_from_a = 0;
  size_t subscribers_seen_from_b = 0;
  const bool graph_counts_ok =
    rmw_count_publishers(node_a, topic_name, &publishers_seen_from_a) == RMW_RET_OK &&
    rmw_count_publishers(node_b, topic_name, &publishers_seen_from_b) == RMW_RET_OK &&
    rmw_count_subscribers(node_a, topic_name, &subscribers_seen_from_a) == RMW_RET_OK &&
    rmw_count_subscribers(node_b, topic_name, &subscribers_seen_from_b) == RMW_RET_OK &&
    publishers_seen_from_a == 1 && publishers_seen_from_b == 0 &&
    subscribers_seen_from_a == 1 && subscribers_seen_from_b == 1;

  rosidl_message_type_support_t wrong_message_type_support{};
  wrong_message_type_support.typesupport_identifier =
    "rmw_fleetqox_cpp_domain_isolation_wrong_type";
  rmw_subscription_t * wrong_type_subscription_a = rmw_create_subscription(
    node_a_peer, &wrong_message_type_support, topic_name, &qos, &subscription_options);

  rmw_serialized_message_t outgoing = rmw_get_zero_initialized_serialized_message();
  rmw_serialized_message_t incoming_a = rmw_get_zero_initialized_serialized_message();
  rmw_serialized_message_t incoming_b = rmw_get_zero_initialized_serialized_message();
  rmw_serialized_message_t incoming_wrong_type = rmw_get_zero_initialized_serialized_message();
  const char payload[] = "domain-a-only";
  const bool outgoing_initialized =
    rmw_serialized_message_init(&outgoing, sizeof(payload) - 1, &allocator) == RMW_RET_OK;
  const bool incoming_a_initialized = outgoing_initialized &&
    rmw_serialized_message_init(&incoming_a, sizeof(payload), &allocator) == RMW_RET_OK;
  const bool incoming_b_initialized = incoming_a_initialized &&
    rmw_serialized_message_init(&incoming_b, sizeof(payload), &allocator) == RMW_RET_OK;
  const bool incoming_wrong_type_initialized = incoming_b_initialized &&
    rmw_serialized_message_init(
    &incoming_wrong_type, sizeof(payload), &allocator) == RMW_RET_OK;
  const bool serialized_init_ok = incoming_wrong_type_initialized;
  if (serialized_init_ok) {
    std::memcpy(outgoing.buffer, payload, sizeof(payload) - 1);
    outgoing.buffer_length = sizeof(payload) - 1;
  }
  const rmw_ret_t publish_ret = publisher_a != nullptr && serialized_init_ok ?
    rmw_publish_serialized_message(publisher_a, &outgoing, nullptr) : RMW_RET_ERROR;
  bool same_domain_taken = false;
  bool cross_domain_taken = false;
  bool wrong_type_taken = false;
  const bool same_domain_take_ok = take_serialized_with_retry(
    subscription_a, &incoming_a, &same_domain_taken);
  const bool cross_domain_take_ok = take_serialized_with_retry(
    subscription_b, &incoming_b, &cross_domain_taken);
  const bool wrong_type_take_ok = take_serialized_with_retry(
    wrong_type_subscription_a, &incoming_wrong_type, &wrong_type_taken);
  const bool data_isolation_ok = publish_ret == RMW_RET_OK && same_domain_take_ok &&
    cross_domain_take_ok && wrong_type_take_ok && same_domain_taken &&
    !cross_domain_taken && !wrong_type_taken &&
    incoming_a.buffer_length == sizeof(payload) - 1 &&
    std::memcmp(incoming_a.buffer, payload, sizeof(payload) - 1) == 0;

  const rosidl_service_type_support_t * service_type_support =
    ROSIDL_TYPESUPPORT_INTERFACE__SERVICE_SYMBOL_NAME(
    rosidl_typesupport_introspection_c, std_srvs, srv, SetBool)();
  const char * service_name = "/fleetqox/domain_service";
  rmw_service_t * service_a = rmw_create_service(
    node_a, service_type_support, service_name, &qos);
  rmw_client_t * client_a = rmw_create_client(
    node_a_peer, service_type_support, service_name, &qos);
  rmw_client_t * client_b = rmw_create_client(
    node_b, service_type_support, service_name, &qos);
  bool same_service_available = false;
  bool cross_service_available = true;
  const bool service_availability_isolated =
    service_a != nullptr && client_a != nullptr && client_b != nullptr &&
    rmw_service_server_is_available(node_a_peer, client_a, &same_service_available) == RMW_RET_OK &&
    rmw_service_server_is_available(node_b, client_b, &cross_service_available) == RMW_RET_OK &&
    same_service_available && !cross_service_available;

  std_srvs__srv__SetBool_Request request;
  std_srvs__srv__SetBool_Request taken_request;
  const bool request_init_ok =
    std_srvs__srv__SetBool_Request__init(&request) &&
    std_srvs__srv__SetBool_Request__init(&taken_request);
  request.data = true;
  int64_t cross_sequence = 0;
  int64_t same_sequence = 0;
  const rmw_ret_t cross_send_ret = request_init_ok ?
    rmw_send_request(client_b, &request, &cross_sequence) : RMW_RET_ERROR;
  std::this_thread::sleep_for(std::chrono::milliseconds(30));
  rmw_service_info_t request_info{};
  bool cross_request_taken = true;
  const rmw_ret_t cross_take_ret = rmw_take_request(
    service_a, &request_info, &taken_request, &cross_request_taken);
  const rmw_ret_t same_send_ret = rmw_send_request(client_a, &request, &same_sequence);
  bool same_request_taken = false;
  rmw_ret_t same_take_ret = RMW_RET_OK;
  for (int attempt = 0; attempt < 200 && !same_request_taken; ++attempt) {
    same_take_ret = rmw_take_request(
      service_a, &request_info, &taken_request, &same_request_taken);
    if (same_take_ret != RMW_RET_OK || same_request_taken) {
      break;
    }
    std::this_thread::sleep_for(std::chrono::milliseconds(1));
  }
  const bool service_data_isolation_ok =
    cross_send_ret == RMW_RET_OK && cross_take_ret == RMW_RET_OK && !cross_request_taken &&
    same_send_ret == RMW_RET_OK && same_take_ret == RMW_RET_OK && same_request_taken;

  const char * remote_topic = "/fleetqox/domain_remote_graph";
  rmw_fleetqox_cpp_graph_apply_remote_advertisement_in_domain(
    "add", "publisher", "remote_b", "/fleetqox", remote_topic,
    "test_msgs/msg/Domain", "remote-domain-b-publisher", kDomainB, 5000);
  size_t remote_seen_from_a = 0;
  size_t remote_seen_from_b = 0;
  const bool remote_graph_isolation_ok =
    rmw_count_publishers(node_a, remote_topic, &remote_seen_from_a) == RMW_RET_OK &&
    rmw_count_publishers(node_b, remote_topic, &remote_seen_from_b) == RMW_RET_OK &&
    remote_seen_from_a == 0 && remote_seen_from_b == 1;
  rmw_fleetqox_cpp_graph_apply_remote_advertisement_in_domain(
    "remove", "publisher", "remote_b", "/fleetqox", remote_topic,
    "test_msgs/msg/Domain", "remote-domain-b-publisher", kDomainB, 5000);

  const bool ok = domain_a_guard_on_local_add &&
    domain_b_guard_suppressed_on_domain_a_add && graph_counts_ok && data_isolation_ok &&
    service_availability_isolated && service_data_isolation_ok && remote_graph_isolation_ok;

  std::cout << "{\"schema_version\":\"fleetrmw.rmw_domain_isolation_probe.v1\",";
  std::cout << "\"status\":\"" << (ok ? "ok" : "failed") << "\",";
  std::cout << "\"domain_a\":" << kDomainA << ",\"domain_b\":" << kDomainB << ",";
  std::cout << "\"graph_guard_domain_a_ready\":" <<
    (domain_a_guard_on_local_add ? "true" : "false") << ",";
  std::cout << "\"graph_guard_cross_domain_suppressed\":" <<
    (domain_b_guard_suppressed_on_domain_a_add ? "true" : "false") << ",";
  std::cout << "\"graph_counts_isolated\":" << (graph_counts_ok ? "true" : "false") << ",";
  std::cout << "\"data_plane_isolated\":" << (data_isolation_ok ? "true" : "false") << ",";
  std::cout << "\"same_domain_sample_taken\":" << (same_domain_taken ? "true" : "false") << ",";
  std::cout << "\"cross_domain_sample_taken\":" << (cross_domain_taken ? "true" : "false") << ",";
  std::cout << "\"wrong_type_sample_taken\":" << (wrong_type_taken ? "true" : "false") << ",";
  std::cout << "\"pubsub_type_data_plane_isolated\":" <<
    (!wrong_type_taken ? "true" : "false") << ",";
  std::cout << "\"service_availability_isolated\":" <<
    (service_availability_isolated ? "true" : "false") << ",";
  std::cout << "\"service_data_plane_isolated\":" <<
    (service_data_isolation_ok ? "true" : "false") << ",";
  std::cout << "\"remote_graph_isolated\":" <<
    (remote_graph_isolation_ok ? "true" : "false") << "}" << std::endl;

  if (request_init_ok) {
    std_srvs__srv__SetBool_Request__fini(&taken_request);
    std_srvs__srv__SetBool_Request__fini(&request);
  }
  if (client_b != nullptr) {
    const rmw_ret_t ret = rmw_destroy_client(node_b, client_b);
    (void)ret;
  }
  if (client_a != nullptr) {
    const rmw_ret_t ret = rmw_destroy_client(node_a_peer, client_a);
    (void)ret;
  }
  if (service_a != nullptr) {
    const rmw_ret_t ret = rmw_destroy_service(node_a, service_a);
    (void)ret;
  }
  if (incoming_b_initialized) {
    const rmw_ret_t ret = rmw_serialized_message_fini(&incoming_b);
    (void)ret;
  }
  if (incoming_wrong_type_initialized) {
    const rmw_ret_t ret = rmw_serialized_message_fini(&incoming_wrong_type);
    (void)ret;
  }
  if (incoming_a_initialized) {
    const rmw_ret_t ret = rmw_serialized_message_fini(&incoming_a);
    (void)ret;
  }
  if (outgoing_initialized) {
    const rmw_ret_t ret = rmw_serialized_message_fini(&outgoing);
    (void)ret;
  }
  if (subscription_b != nullptr) {
    const rmw_ret_t ret = rmw_destroy_subscription(node_b, subscription_b);
    (void)ret;
  }
  if (subscription_a != nullptr) {
    const rmw_ret_t ret = rmw_destroy_subscription(node_a_peer, subscription_a);
    (void)ret;
  }
  if (wrong_type_subscription_a != nullptr) {
    const rmw_ret_t ret = rmw_destroy_subscription(node_a_peer, wrong_type_subscription_a);
    (void)ret;
  }
  if (publisher_a != nullptr) {
    const rmw_ret_t ret = rmw_destroy_publisher(node_a, publisher_a);
    (void)ret;
  }
  const rmw_ret_t wait_b_ret = rmw_destroy_wait_set(wait_b);
  const rmw_ret_t wait_a_ret = rmw_destroy_wait_set(wait_a);
  const rmw_ret_t node_b_ret = rmw_destroy_node(node_b);
  const rmw_ret_t node_a_peer_ret = rmw_destroy_node(node_a_peer);
  const rmw_ret_t node_a_ret = rmw_destroy_node(node_a);
  (void)wait_b_ret;
  (void)wait_a_ret;
  (void)node_b_ret;
  (void)node_a_peer_ret;
  (void)node_a_ret;
  cleanup_context(&domain_b);
  cleanup_context(&domain_a);
  return ok ? 0 : 1;
}

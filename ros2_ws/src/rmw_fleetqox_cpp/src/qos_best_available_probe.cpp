#include <cstdint>
#include <iostream>

#include "rcutils/allocator.h"
#include "rmw/init.h"
#include "rmw/init_options.h"
#include "rmw/publisher_options.h"
#include "rmw/qos_profiles.h"
#include "rmw/rmw.h"
#include "rmw/subscription_options.h"
#include "rosidl_runtime_c/message_type_support_struct.h"

namespace
{

rmw_qos_profile_t liveliness_qos(
  rmw_qos_liveliness_policy_t policy,
  std::uint64_t lease_ms)
{
  rmw_qos_profile_t qos = rmw_qos_profile_default;
  qos.history = RMW_QOS_POLICY_HISTORY_KEEP_LAST;
  qos.depth = 8;
  qos.reliability = RMW_QOS_POLICY_RELIABILITY_RELIABLE;
  qos.durability = RMW_QOS_POLICY_DURABILITY_VOLATILE;
  qos.liveliness = policy;
  qos.liveliness_lease_duration.sec = lease_ms / 1000u;
  qos.liveliness_lease_duration.nsec = (lease_ms % 1000u) * 1000000u;
  return qos;
}

bool duration_ms_is(const rmw_time_t & duration, std::uint64_t expected_ms)
{
  return duration.sec == expected_ms / 1000u &&
         duration.nsec == (expected_ms % 1000u) * 1000000u;
}

bool duration_is_default(const rmw_time_t & duration)
{
  const rmw_time_t default_duration = RMW_QOS_LIVELINESS_LEASE_DURATION_DEFAULT;
  return duration.sec == default_duration.sec && duration.nsec == default_duration.nsec;
}

bool destroy_pair(
  rmw_node_t * node,
  rmw_publisher_t * publisher,
  rmw_subscription_t * subscription)
{
  const rmw_ret_t publisher_ret = publisher == nullptr ?
    RMW_RET_ERROR : rmw_destroy_publisher(node, publisher);
  const rmw_ret_t subscription_ret = subscription == nullptr ?
    RMW_RET_ERROR : rmw_destroy_subscription(node, subscription);
  return publisher_ret == RMW_RET_OK && subscription_ret == RMW_RET_OK;
}

}  // namespace

int main()
{
  rcutils_allocator_t allocator = rcutils_get_default_allocator();
  rmw_init_options_t options = rmw_get_zero_initialized_init_options();
  if (rmw_init_options_init(&options, allocator) != RMW_RET_OK) {
    std::cout << "{\"status\":\"init_options_failed\"}\n";
    return 1;
  }
  options.instance_id = 824;
  rmw_context_t context = rmw_get_zero_initialized_context();
  if (rmw_init(&options, &context) != RMW_RET_OK) {
    const rmw_ret_t options_ret = rmw_init_options_fini(&options);
    (void)options_ret;
    std::cout << "{\"status\":\"init_failed\"}\n";
    return 1;
  }
  rmw_node_t * node = rmw_create_node(&context, "qos_best_available_probe", "/fleetqox");
  rosidl_message_type_support_t type_support{};
  type_support.typesupport_identifier = "fleetrmw_qos_best_available_type";
  const rmw_publisher_options_t publisher_options = rmw_get_default_publisher_options();
  const rmw_subscription_options_t subscription_options =
    rmw_get_default_subscription_options();

  const rmw_qos_profile_t manual_200 = liveliness_qos(
    RMW_QOS_POLICY_LIVELINESS_MANUAL_BY_TOPIC, 200);
  rmw_subscription_t * manual_subscription = node == nullptr ? nullptr :
    rmw_create_subscription(
    node,
    &type_support,
    "/fleetqox/best_available_publisher",
    &manual_200,
    &subscription_options);
  rmw_publisher_t * best_publisher = node == nullptr ? nullptr :
    rmw_create_publisher(
    node,
    &type_support,
    "/fleetqox/best_available_publisher",
    &rmw_qos_profile_best_available,
    &publisher_options);
  rmw_qos_profile_t best_publisher_actual{};
  const bool best_publisher_actual_ok = best_publisher != nullptr &&
    rmw_publisher_get_actual_qos(best_publisher, &best_publisher_actual) == RMW_RET_OK;
  const bool best_publisher_manual = best_publisher_actual_ok &&
    best_publisher_actual.reliability == RMW_QOS_POLICY_RELIABILITY_RELIABLE &&
    best_publisher_actual.durability == RMW_QOS_POLICY_DURABILITY_TRANSIENT_LOCAL &&
    best_publisher_actual.liveliness == RMW_QOS_POLICY_LIVELINESS_MANUAL_BY_TOPIC &&
    duration_ms_is(best_publisher_actual.liveliness_lease_duration, 200);
  const rmw_ret_t manual_subscription_ret = manual_subscription == nullptr ?
    RMW_RET_ERROR : rmw_destroy_subscription(node, manual_subscription);
  rmw_qos_profile_t best_publisher_frozen_actual{};
  const bool best_publisher_frozen = best_publisher != nullptr &&
    rmw_publisher_get_actual_qos(best_publisher, &best_publisher_frozen_actual) == RMW_RET_OK &&
    best_publisher_frozen_actual.liveliness == RMW_QOS_POLICY_LIVELINESS_MANUAL_BY_TOPIC &&
    duration_ms_is(best_publisher_frozen_actual.liveliness_lease_duration, 200);
  const rmw_ret_t best_publisher_ret = best_publisher == nullptr ?
    RMW_RET_ERROR : rmw_destroy_publisher(node, best_publisher);
  const bool best_publisher_scenario = best_publisher_manual && best_publisher_frozen &&
    manual_subscription_ret == RMW_RET_OK && best_publisher_ret == RMW_RET_OK;

  const rmw_qos_profile_t automatic_300 = liveliness_qos(
    RMW_QOS_POLICY_LIVELINESS_AUTOMATIC, 300);
  rmw_publisher_t * automatic_publisher = node == nullptr ? nullptr :
    rmw_create_publisher(
    node,
    &type_support,
    "/fleetqox/best_available_subscription",
    &automatic_300,
    &publisher_options);
  rmw_subscription_t * best_subscription = node == nullptr ? nullptr :
    rmw_create_subscription(
    node,
    &type_support,
    "/fleetqox/best_available_subscription",
    &rmw_qos_profile_best_available,
    &subscription_options);
  rmw_qos_profile_t best_subscription_actual{};
  const bool best_subscription_actual_ok = best_subscription != nullptr &&
    rmw_subscription_get_actual_qos(best_subscription, &best_subscription_actual) == RMW_RET_OK;
  const bool best_subscription_automatic = best_subscription_actual_ok &&
    best_subscription_actual.reliability == RMW_QOS_POLICY_RELIABILITY_RELIABLE &&
    best_subscription_actual.durability == RMW_QOS_POLICY_DURABILITY_VOLATILE &&
    best_subscription_actual.liveliness == RMW_QOS_POLICY_LIVELINESS_AUTOMATIC &&
    duration_ms_is(best_subscription_actual.liveliness_lease_duration, 300);
  const bool best_subscription_teardown =
    destroy_pair(node, automatic_publisher, best_subscription);
  const bool best_subscription_scenario =
    best_subscription_automatic && best_subscription_teardown;

  rmw_publisher_t * zero_best_publisher = node == nullptr ? nullptr :
    rmw_create_publisher(
    node,
    &type_support,
    "/fleetqox/best_available_zero_publisher",
    &rmw_qos_profile_best_available,
    &publisher_options);
  rmw_qos_profile_t zero_best_publisher_actual{};
  const bool zero_best_publisher_ok = zero_best_publisher != nullptr &&
    rmw_publisher_get_actual_qos(
    zero_best_publisher, &zero_best_publisher_actual) == RMW_RET_OK &&
    zero_best_publisher_actual.liveliness == RMW_QOS_POLICY_LIVELINESS_AUTOMATIC &&
    duration_is_default(zero_best_publisher_actual.liveliness_lease_duration);
  const rmw_ret_t zero_best_publisher_ret = zero_best_publisher == nullptr ?
    RMW_RET_ERROR : rmw_destroy_publisher(node, zero_best_publisher);

  rmw_subscription_t * zero_best_subscription = node == nullptr ? nullptr :
    rmw_create_subscription(
    node,
    &type_support,
    "/fleetqox/best_available_zero_subscription",
    &rmw_qos_profile_best_available,
    &subscription_options);
  rmw_qos_profile_t zero_best_subscription_actual{};
  const bool zero_best_subscription_ok = zero_best_subscription != nullptr &&
    rmw_subscription_get_actual_qos(
    zero_best_subscription, &zero_best_subscription_actual) == RMW_RET_OK &&
    zero_best_subscription_actual.liveliness == RMW_QOS_POLICY_LIVELINESS_AUTOMATIC &&
    duration_is_default(zero_best_subscription_actual.liveliness_lease_duration);
  const rmw_ret_t zero_best_subscription_ret = zero_best_subscription == nullptr ?
    RMW_RET_ERROR : rmw_destroy_subscription(node, zero_best_subscription);
  const bool zero_endpoint_scenario = zero_best_publisher_ok && zero_best_subscription_ok &&
    zero_best_publisher_ret == RMW_RET_OK && zero_best_subscription_ret == RMW_RET_OK;

  const rmw_qos_profile_t automatic_100 = liveliness_qos(
    RMW_QOS_POLICY_LIVELINESS_AUTOMATIC, 100);
  const rmw_qos_profile_t manual_500 = liveliness_qos(
    RMW_QOS_POLICY_LIVELINESS_MANUAL_BY_TOPIC, 500);
  rmw_publisher_t * mixed_automatic = node == nullptr ? nullptr :
    rmw_create_publisher(
    node,
    &type_support,
    "/fleetqox/best_available_mixed",
    &automatic_100,
    &publisher_options);
  rmw_publisher_t * mixed_manual = node == nullptr ? nullptr :
    rmw_create_publisher(
    node,
    &type_support,
    "/fleetqox/best_available_mixed",
    &manual_500,
    &publisher_options);
  rmw_subscription_t * mixed_best = node == nullptr ? nullptr :
    rmw_create_subscription(
    node,
    &type_support,
    "/fleetqox/best_available_mixed",
    &rmw_qos_profile_best_available,
    &subscription_options);
  rmw_qos_profile_t mixed_best_actual{};
  const bool mixed_best_actual_ok = mixed_best != nullptr &&
    rmw_subscription_get_actual_qos(mixed_best, &mixed_best_actual) == RMW_RET_OK;
  const bool mixed_selects_automatic_max_lease = mixed_best_actual_ok &&
    mixed_best_actual.liveliness == RMW_QOS_POLICY_LIVELINESS_AUTOMATIC &&
    duration_ms_is(mixed_best_actual.liveliness_lease_duration, 500);
  const rmw_ret_t mixed_automatic_ret = mixed_automatic == nullptr ?
    RMW_RET_ERROR : rmw_destroy_publisher(node, mixed_automatic);
  rmw_qos_profile_t mixed_frozen_actual{};
  const bool mixed_policy_frozen = mixed_best != nullptr &&
    rmw_subscription_get_actual_qos(mixed_best, &mixed_frozen_actual) == RMW_RET_OK &&
    mixed_frozen_actual.liveliness == RMW_QOS_POLICY_LIVELINESS_AUTOMATIC &&
    duration_ms_is(mixed_frozen_actual.liveliness_lease_duration, 500);
  const rmw_ret_t mixed_manual_ret = mixed_manual == nullptr ?
    RMW_RET_ERROR : rmw_destroy_publisher(node, mixed_manual);
  const rmw_ret_t mixed_best_ret = mixed_best == nullptr ?
    RMW_RET_ERROR : rmw_destroy_subscription(node, mixed_best);
  const bool mixed_scenario = mixed_selects_automatic_max_lease && mixed_policy_frozen &&
    mixed_automatic_ret == RMW_RET_OK && mixed_manual_ret == RMW_RET_OK &&
    mixed_best_ret == RMW_RET_OK;

  const rmw_ret_t node_ret = node == nullptr ? RMW_RET_ERROR : rmw_destroy_node(node);
  const rmw_ret_t shutdown_ret = rmw_shutdown(&context);
  const rmw_ret_t context_ret = rmw_context_fini(&context);
  const rmw_ret_t options_ret = rmw_init_options_fini(&options);
  const bool clean_teardown = node_ret == RMW_RET_OK && shutdown_ret == RMW_RET_OK &&
    context_ret == RMW_RET_OK && options_ret == RMW_RET_OK;
  const bool ok = node != nullptr && best_publisher_scenario &&
    best_subscription_scenario && zero_endpoint_scenario && mixed_scenario &&
    clean_teardown;

  std::cout << "{\"schema_version\":\"fleetrmw.qos_best_available_probe.v1\","
            << "\"status\":\"" << (ok ? "ok" : "failed") << "\","
            << "\"best_publisher_manual_selection_claim\":"
            << (best_publisher_manual ? "true" : "false") << ","
            << "\"best_subscription_automatic_selection_claim\":"
            << (best_subscription_automatic ? "true" : "false") << ","
            << "\"zero_endpoint_best_available_defaults_claim\":"
            << (zero_endpoint_scenario ? "true" : "false") << ","
            << "\"mixed_publishers_automatic_max_lease_claim\":"
            << (mixed_selects_automatic_max_lease ? "true" : "false") << ","
            << "\"best_available_policy_frozen_after_create_claim\":"
            << (best_publisher_frozen && mixed_policy_frozen ? "true" : "false") << ","
            << "\"publisher_selected_lease_ms\":200,"
            << "\"subscription_selected_lease_ms\":300,"
            << "\"mixed_selected_lease_ms\":500,"
            << "\"zero_publisher_liveliness_policy\":"
            << zero_best_publisher_actual.liveliness << ","
            << "\"zero_publisher_lease_sec\":"
            << zero_best_publisher_actual.liveliness_lease_duration.sec << ","
            << "\"zero_publisher_lease_nsec\":"
            << zero_best_publisher_actual.liveliness_lease_duration.nsec << ","
            << "\"zero_subscription_liveliness_policy\":"
            << zero_best_subscription_actual.liveliness << ","
            << "\"zero_subscription_lease_sec\":"
            << zero_best_subscription_actual.liveliness_lease_duration.sec << ","
            << "\"zero_subscription_lease_nsec\":"
            << zero_best_subscription_actual.liveliness_lease_duration.nsec << ","
            << "\"scenario_count\":4,"
            << "\"clean_teardown\":" << (clean_teardown ? "true" : "false") << "}"
            << std::endl;
  return ok ? 0 : 1;
}

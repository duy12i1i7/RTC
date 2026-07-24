#include <algorithm>
#include <atomic>
#include <chrono>
#include <cstdint>
#include <cstdlib>
#include <iostream>
#include <string>
#include <thread>
#include <vector>

#include "rcutils/allocator.h"
#include "rmw/event.h"
#include "rmw/events_statuses/events_statuses.h"
#include "rmw/init.h"
#include "rmw/init_options.h"
#include "rmw/publisher_options.h"
#include "rmw/qos_profiles.h"
#include "rmw/rmw.h"
#include "rmw/subscription_options.h"
#include "rosidl_runtime_c/message_type_support_struct.h"

extern "C" std::uint64_t rmw_fleetqox_cpp_remote_graph_event_advertisements_received();
extern "C" std::uint64_t rmw_fleetqox_cpp_remote_graph_event_endpoint_adds();
extern "C" std::uint64_t rmw_fleetqox_cpp_remote_graph_event_endpoint_renewals();
extern "C" std::uint64_t rmw_fleetqox_cpp_remote_graph_event_endpoint_removes();
extern "C" std::uint64_t rmw_fleetqox_cpp_remote_graph_event_endpoint_expiries();
extern "C" size_t rmw_fleetqox_cpp_remote_graph_event_endpoint_count();

namespace
{

constexpr const char * kPublicationMatchTopic = "/fleetqox/remote_event/publication_match";
constexpr const char * kSubscriptionMatchTopic = "/fleetqox/remote_event/subscription_match";
constexpr const char * kOfferedQosTopic = "/fleetqox/remote_event/offered_qos";
constexpr const char * kRequestedQosTopic = "/fleetqox/remote_event/requested_qos";
constexpr const char * kOfferedDurabilityTopic =
  "/fleetqox/remote_event/offered_durability";
constexpr const char * kRequestedDurabilityTopic =
  "/fleetqox/remote_event/requested_durability";
constexpr const char * kOfferedDeadlineTopic = "/fleetqox/remote_event/offered_deadline";
constexpr const char * kRequestedDeadlineTopic = "/fleetqox/remote_event/requested_deadline";
constexpr const char * kPublisherTypeTopic = "/fleetqox/remote_event/publisher_type";
constexpr const char * kSubscriptionTypeTopic = "/fleetqox/remote_event/subscription_type";
constexpr const char * kLivelinessTopic = "/fleetqox/remote_event/liveliness";

struct ProbeConfig
{
  std::string mode{"observer"};
  int hold_ms{1400};
  int timeout_ms{9000};
  bool crash_without_remove{false};
  bool expect_expiry{false};
};

struct CallbackState
{
  std::atomic<std::uint64_t> calls{0};
  std::atomic<std::uint64_t> events{0};
};

void event_callback(const void * user_data, size_t number_of_events)
{
  auto * state = const_cast<CallbackState *>(static_cast<const CallbackState *>(user_data));
  if (state != nullptr) {
    state->calls.fetch_add(1, std::memory_order_relaxed);
    state->events.fetch_add(number_of_events, std::memory_order_relaxed);
  }
}

ProbeConfig parse_args(int argc, char ** argv)
{
  ProbeConfig config;
  for (int i = 1; i < argc; ++i) {
    const std::string arg = argv[i];
    if (arg == "--mode" && i + 1 < argc) {
      config.mode = argv[++i];
    } else if (arg == "--hold-ms" && i + 1 < argc) {
      config.hold_ms = std::stoi(argv[++i]);
    } else if (arg == "--timeout-ms" && i + 1 < argc) {
      config.timeout_ms = std::stoi(argv[++i]);
    } else if (arg == "--crash-without-remove") {
      config.crash_without_remove = true;
    } else if (arg == "--expect-expiry") {
      config.expect_expiry = true;
    }
  }
  config.hold_ms = std::max(config.hold_ms, 0);
  config.timeout_ms = std::max(config.timeout_ms, 1);
  return config;
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
  options->instance_id = 81;
  *context = rmw_get_zero_initialized_context();
  if (rmw_init(options, context) != RMW_RET_OK) {
    const rmw_ret_t fini_ret = rmw_init_options_fini(options);
    (void)fini_ret;
    return false;
  }
  return true;
}

void cleanup_context(rmw_context_t * context, rmw_init_options_t * options)
{
  const rmw_ret_t shutdown_ret = rmw_shutdown(context);
  const rmw_ret_t context_fini_ret = rmw_context_fini(context);
  const rmw_ret_t options_fini_ret = rmw_init_options_fini(options);
  (void)shutdown_ret;
  (void)context_fini_ret;
  (void)options_fini_ret;
}

rmw_qos_profile_t reliable_qos()
{
  rmw_qos_profile_t qos = rmw_qos_profile_default;
  qos.history = RMW_QOS_POLICY_HISTORY_KEEP_LAST;
  qos.depth = 8;
  qos.reliability = RMW_QOS_POLICY_RELIABILITY_RELIABLE;
  qos.durability = RMW_QOS_POLICY_DURABILITY_VOLATILE;
  return qos;
}

rmw_qos_profile_t best_effort_qos()
{
  rmw_qos_profile_t qos = reliable_qos();
  qos.reliability = RMW_QOS_POLICY_RELIABILITY_BEST_EFFORT;
  return qos;
}

rmw_qos_profile_t finite_liveliness_qos()
{
  rmw_qos_profile_t qos = reliable_qos();
  qos.liveliness = RMW_QOS_POLICY_LIVELINESS_AUTOMATIC;
  qos.liveliness_lease_duration.sec = 2;
  qos.liveliness_lease_duration.nsec = 0;
  return qos;
}

rmw_qos_profile_t transient_local_qos()
{
  rmw_qos_profile_t qos = reliable_qos();
  qos.durability = RMW_QOS_POLICY_DURABILITY_TRANSIENT_LOCAL;
  return qos;
}

rmw_qos_profile_t deadline_qos(std::uint64_t deadline_ms)
{
  rmw_qos_profile_t qos = reliable_qos();
  qos.deadline.sec = deadline_ms / 1000u;
  qos.deadline.nsec = (deadline_ms % 1000u) * 1000000u;
  return qos;
}

template<typename StatusT>
bool wait_take_event(
  rmw_event_t * event,
  StatusT * status,
  std::chrono::steady_clock::time_point deadline)
{
  if (event == nullptr || status == nullptr) {
    return false;
  }
  while (std::chrono::steady_clock::now() < deadline) {
    StatusT observed{};
    bool taken = false;
    if (rmw_take_event(event, &observed, &taken) != RMW_RET_OK) {
      return false;
    }
    if (taken) {
      *status = observed;
      return true;
    }
    std::this_thread::sleep_for(std::chrono::milliseconds(10));
  }
  return false;
}

template<typename StatusT>
bool event_is_clear(rmw_event_t * event, StatusT * status)
{
  bool taken = true;
  *status = StatusT{};
  return rmw_take_event(event, status, &taken) == RMW_RET_OK && !taken;
}

bool wait_for_graph_guard(
  rmw_wait_set_t * wait_set,
  const rmw_guard_condition_t * graph_guard,
  int timeout_ms)
{
  if (wait_set == nullptr || graph_guard == nullptr) {
    return false;
  }
  void * items[1] = {const_cast<rmw_guard_condition_t *>(graph_guard)};
  rmw_guard_conditions_t guard_conditions{1, items};
  const std::uint64_t bounded_ms = static_cast<std::uint64_t>(std::max(timeout_ms, 0));
  rmw_time_t timeout{bounded_ms / 1000u, (bounded_ms % 1000u) * 1000000u};
  const rmw_ret_t ret = rmw_wait(
    nullptr, &guard_conditions, nullptr, nullptr, nullptr, wait_set, &timeout);
  return ret == RMW_RET_OK && guard_conditions.guard_conditions[0] != nullptr;
}

void fini_events(const std::vector<rmw_event_t *> & events)
{
  for (rmw_event_t * event : events) {
    if (event != nullptr) {
      const rmw_ret_t ret = rmw_event_fini(event);
      (void)ret;
    }
  }
}

int run_advertiser(const ProbeConfig & config)
{
  rcutils_allocator_t allocator = rcutils_get_default_allocator();
  rmw_init_options_t options{};
  rmw_context_t context{};
  if (!init_context(allocator, &options, &context)) {
    std::cout << "{\"status\":\"init_failed\"}" << std::endl;
    return 1;
  }
  rmw_node_t * node = rmw_create_node(&context, "remote_event_advertiser", "/fleetqox");
  if (node == nullptr) {
    cleanup_context(&context, &options);
    std::cout << "{\"status\":\"create_node_failed\"}" << std::endl;
    return 1;
  }

  rosidl_message_type_support_t type_a{};
  type_a.typesupport_identifier = "fleetqox_remote_event_type_a";
  rosidl_message_type_support_t type_b{};
  type_b.typesupport_identifier = "fleetqox_remote_event_type_b";
  const rmw_qos_profile_t reliable = reliable_qos();
  const rmw_qos_profile_t best_effort = best_effort_qos();
  const rmw_qos_profile_t transient_local = transient_local_qos();
  const rmw_qos_profile_t deadline_100ms = deadline_qos(100);
  const rmw_qos_profile_t deadline_200ms = deadline_qos(200);
  const rmw_qos_profile_t liveliness = finite_liveliness_qos();
  const rmw_publisher_options_t publisher_options = rmw_get_default_publisher_options();
  const rmw_subscription_options_t subscription_options = rmw_get_default_subscription_options();

  std::vector<rmw_publisher_t *> publishers{
    rmw_create_publisher(
      node, &type_a, kSubscriptionMatchTopic, &reliable, &publisher_options),
    rmw_create_publisher(
      node, &type_a, kRequestedQosTopic, &best_effort, &publisher_options),
    rmw_create_publisher(
      node, &type_a, kRequestedDurabilityTopic, &reliable, &publisher_options),
    rmw_create_publisher(
      node, &type_a, kRequestedDeadlineTopic, &deadline_200ms, &publisher_options),
    rmw_create_publisher(
      node, &type_b, kSubscriptionTypeTopic, &reliable, &publisher_options),
    rmw_create_publisher(
      node, &type_a, kLivelinessTopic, &liveliness, &publisher_options)};
  std::vector<rmw_subscription_t *> subscriptions{
    rmw_create_subscription(
      node, &type_a, kPublicationMatchTopic, &reliable, &subscription_options),
    rmw_create_subscription(
      node, &type_a, kOfferedQosTopic, &reliable, &subscription_options),
    rmw_create_subscription(
      node, &type_a, kOfferedDurabilityTopic, &transient_local, &subscription_options),
    rmw_create_subscription(
      node, &type_a, kOfferedDeadlineTopic, &deadline_100ms, &subscription_options),
    rmw_create_subscription(
      node, &type_b, kPublisherTypeTopic, &reliable, &subscription_options)};

  const bool created =
    std::all_of(publishers.begin(), publishers.end(), [](const rmw_publisher_t * endpoint) {
      return endpoint != nullptr;
    }) &&
    std::all_of(
    subscriptions.begin(), subscriptions.end(), [](const rmw_subscription_t * endpoint) {
      return endpoint != nullptr;
    });
  std::cout << "{\"schema_version\":\"fleetrmw.remote_event_probe.v1\","
            << "\"mode\":\"advertiser\",\"phase\":\"ready\","
            << "\"created\":" << (created ? "true" : "false") << "}" << std::endl;
  if (!created) {
    for (rmw_subscription_t * subscription : subscriptions) {
      if (subscription != nullptr) {
        const rmw_ret_t ret = rmw_destroy_subscription(node, subscription);
        (void)ret;
      }
    }
    for (rmw_publisher_t * publisher : publishers) {
      if (publisher != nullptr) {
        const rmw_ret_t ret = rmw_destroy_publisher(node, publisher);
        (void)ret;
      }
    }
    const rmw_ret_t node_ret = rmw_destroy_node(node);
    (void)node_ret;
    cleanup_context(&context, &options);
    return 1;
  }

  std::this_thread::sleep_for(std::chrono::milliseconds(config.hold_ms));
  if (config.crash_without_remove) {
    std::cout << "{\"schema_version\":\"fleetrmw.remote_event_probe.v1\","
              << "\"mode\":\"advertiser\",\"status\":\"ok\","
              << "\"crash_without_remove\":true}" << std::endl;
    std::_Exit(0);
  }

  bool cleanup_ok = true;
  for (auto it = subscriptions.rbegin(); it != subscriptions.rend(); ++it) {
    cleanup_ok = rmw_destroy_subscription(node, *it) == RMW_RET_OK && cleanup_ok;
  }
  for (auto it = publishers.rbegin(); it != publishers.rend(); ++it) {
    cleanup_ok = rmw_destroy_publisher(node, *it) == RMW_RET_OK && cleanup_ok;
  }
  cleanup_ok = rmw_destroy_node(node) == RMW_RET_OK && cleanup_ok;
  cleanup_context(&context, &options);
  std::cout << "{\"schema_version\":\"fleetrmw.remote_event_probe.v1\","
            << "\"mode\":\"advertiser\",\"status\":\""
            << (cleanup_ok ? "ok" : "failed") << "\","
            << "\"crash_without_remove\":false}" << std::endl;
  return cleanup_ok ? 0 : 1;
}

int run_observer(const ProbeConfig & config)
{
  rcutils_allocator_t allocator = rcutils_get_default_allocator();
  rmw_init_options_t options{};
  rmw_context_t context{};
  if (!init_context(allocator, &options, &context)) {
    std::cout << "{\"status\":\"init_failed\"}" << std::endl;
    return 1;
  }
  rmw_node_t * node = rmw_create_node(&context, "remote_event_observer", "/fleetqox");
  rmw_wait_set_t * graph_wait_set = rmw_create_wait_set(&context, 1);
  if (node == nullptr || graph_wait_set == nullptr) {
    if (graph_wait_set != nullptr) {
      const rmw_ret_t ret = rmw_destroy_wait_set(graph_wait_set);
      (void)ret;
    }
    if (node != nullptr) {
      const rmw_ret_t ret = rmw_destroy_node(node);
      (void)ret;
    }
    cleanup_context(&context, &options);
    std::cout << "{\"status\":\"create_node_or_wait_set_failed\"}" << std::endl;
    return 1;
  }
  const rmw_guard_condition_t * graph_guard = rmw_node_get_graph_guard_condition(node);

  rosidl_message_type_support_t type_a{};
  type_a.typesupport_identifier = "fleetqox_remote_event_type_a";
  const rmw_qos_profile_t reliable = reliable_qos();
  const rmw_qos_profile_t best_effort = best_effort_qos();
  const rmw_qos_profile_t transient_local = transient_local_qos();
  const rmw_qos_profile_t deadline_100ms = deadline_qos(100);
  const rmw_qos_profile_t deadline_200ms = deadline_qos(200);
  const rmw_qos_profile_t liveliness = finite_liveliness_qos();
  const rmw_publisher_options_t publisher_options = rmw_get_default_publisher_options();
  const rmw_subscription_options_t subscription_options = rmw_get_default_subscription_options();

  rmw_publisher_t * publication_match_publisher = rmw_create_publisher(
    node, &type_a, kPublicationMatchTopic, &reliable, &publisher_options);
  rmw_subscription_t * subscription_match_subscription = rmw_create_subscription(
    node, &type_a, kSubscriptionMatchTopic, &reliable, &subscription_options);
  rmw_publisher_t * offered_qos_publisher = rmw_create_publisher(
    node, &type_a, kOfferedQosTopic, &best_effort, &publisher_options);
  rmw_subscription_t * requested_qos_subscription = rmw_create_subscription(
    node, &type_a, kRequestedQosTopic, &reliable, &subscription_options);
  rmw_publisher_t * offered_durability_publisher = rmw_create_publisher(
    node, &type_a, kOfferedDurabilityTopic, &reliable, &publisher_options);
  rmw_subscription_t * requested_durability_subscription = rmw_create_subscription(
    node, &type_a, kRequestedDurabilityTopic, &transient_local, &subscription_options);
  rmw_publisher_t * offered_deadline_publisher = rmw_create_publisher(
    node, &type_a, kOfferedDeadlineTopic, &deadline_200ms, &publisher_options);
  rmw_subscription_t * requested_deadline_subscription = rmw_create_subscription(
    node, &type_a, kRequestedDeadlineTopic, &deadline_100ms, &subscription_options);
  rmw_publisher_t * publisher_type_publisher = rmw_create_publisher(
    node, &type_a, kPublisherTypeTopic, &reliable, &publisher_options);
  rmw_subscription_t * subscription_type_subscription = rmw_create_subscription(
    node, &type_a, kSubscriptionTypeTopic, &reliable, &subscription_options);
  rmw_subscription_t * liveliness_subscription = rmw_create_subscription(
    node, &type_a, kLivelinessTopic, &liveliness, &subscription_options);

  rmw_event_t publication_match_event = rmw_get_zero_initialized_event();
  rmw_event_t subscription_match_event = rmw_get_zero_initialized_event();
  rmw_event_t offered_qos_event = rmw_get_zero_initialized_event();
  rmw_event_t requested_qos_event = rmw_get_zero_initialized_event();
  rmw_event_t offered_durability_event = rmw_get_zero_initialized_event();
  rmw_event_t requested_durability_event = rmw_get_zero_initialized_event();
  rmw_event_t offered_deadline_event = rmw_get_zero_initialized_event();
  rmw_event_t requested_deadline_event = rmw_get_zero_initialized_event();
  rmw_event_t publisher_type_event = rmw_get_zero_initialized_event();
  rmw_event_t subscription_type_event = rmw_get_zero_initialized_event();
  rmw_event_t liveliness_event = rmw_get_zero_initialized_event();

  bool initialized =
    publication_match_publisher != nullptr &&
    subscription_match_subscription != nullptr &&
    offered_qos_publisher != nullptr &&
    requested_qos_subscription != nullptr &&
    offered_durability_publisher != nullptr &&
    requested_durability_subscription != nullptr &&
    offered_deadline_publisher != nullptr &&
    requested_deadline_subscription != nullptr &&
    publisher_type_publisher != nullptr &&
    subscription_type_subscription != nullptr &&
    liveliness_subscription != nullptr;
  initialized = initialized &&
    rmw_publisher_event_init(
    &publication_match_event,
    publication_match_publisher,
    RMW_EVENT_PUBLICATION_MATCHED) == RMW_RET_OK;
  initialized = initialized &&
    rmw_subscription_event_init(
    &subscription_match_event,
    subscription_match_subscription,
    RMW_EVENT_SUBSCRIPTION_MATCHED) == RMW_RET_OK;
  initialized = initialized &&
    rmw_publisher_event_init(
    &offered_qos_event,
    offered_qos_publisher,
    RMW_EVENT_OFFERED_QOS_INCOMPATIBLE) == RMW_RET_OK;
  initialized = initialized &&
    rmw_subscription_event_init(
    &requested_qos_event,
    requested_qos_subscription,
    RMW_EVENT_REQUESTED_QOS_INCOMPATIBLE) == RMW_RET_OK;
  initialized = initialized &&
    rmw_publisher_event_init(
    &offered_durability_event,
    offered_durability_publisher,
    RMW_EVENT_OFFERED_QOS_INCOMPATIBLE) == RMW_RET_OK;
  initialized = initialized &&
    rmw_subscription_event_init(
    &requested_durability_event,
    requested_durability_subscription,
    RMW_EVENT_REQUESTED_QOS_INCOMPATIBLE) == RMW_RET_OK;
  initialized = initialized &&
    rmw_publisher_event_init(
    &offered_deadline_event,
    offered_deadline_publisher,
    RMW_EVENT_OFFERED_QOS_INCOMPATIBLE) == RMW_RET_OK;
  initialized = initialized &&
    rmw_subscription_event_init(
    &requested_deadline_event,
    requested_deadline_subscription,
    RMW_EVENT_REQUESTED_QOS_INCOMPATIBLE) == RMW_RET_OK;
  initialized = initialized &&
    rmw_publisher_event_init(
    &publisher_type_event,
    publisher_type_publisher,
    RMW_EVENT_PUBLISHER_INCOMPATIBLE_TYPE) == RMW_RET_OK;
  initialized = initialized &&
    rmw_subscription_event_init(
    &subscription_type_event,
    subscription_type_subscription,
    RMW_EVENT_SUBSCRIPTION_INCOMPATIBLE_TYPE) == RMW_RET_OK;
  initialized = initialized &&
    rmw_subscription_event_init(
    &liveliness_event,
    liveliness_subscription,
    RMW_EVENT_LIVELINESS_CHANGED) == RMW_RET_OK;

  CallbackState publication_callback;
  CallbackState subscription_callback;
  CallbackState offered_callback;
  CallbackState requested_callback;
  CallbackState offered_durability_callback;
  CallbackState requested_durability_callback;
  CallbackState offered_deadline_callback;
  CallbackState requested_deadline_callback;
  CallbackState publisher_type_callback;
  CallbackState subscription_type_callback;
  CallbackState liveliness_callback;
  initialized = initialized &&
    rmw_event_set_callback(
    &publication_match_event, event_callback, &publication_callback) == RMW_RET_OK;
  initialized = initialized &&
    rmw_event_set_callback(
    &subscription_match_event, event_callback, &subscription_callback) == RMW_RET_OK;
  initialized = initialized &&
    rmw_event_set_callback(&offered_qos_event, event_callback, &offered_callback) == RMW_RET_OK;
  initialized = initialized &&
    rmw_event_set_callback(&requested_qos_event, event_callback, &requested_callback) == RMW_RET_OK;
  initialized = initialized &&
    rmw_event_set_callback(
    &offered_durability_event, event_callback, &offered_durability_callback) == RMW_RET_OK;
  initialized = initialized &&
    rmw_event_set_callback(
    &requested_durability_event, event_callback, &requested_durability_callback) == RMW_RET_OK;
  initialized = initialized &&
    rmw_event_set_callback(
    &offered_deadline_event, event_callback, &offered_deadline_callback) == RMW_RET_OK;
  initialized = initialized &&
    rmw_event_set_callback(
    &requested_deadline_event, event_callback, &requested_deadline_callback) == RMW_RET_OK;
  initialized = initialized &&
    rmw_event_set_callback(
    &publisher_type_event, event_callback, &publisher_type_callback) == RMW_RET_OK;
  initialized = initialized &&
    rmw_event_set_callback(
    &subscription_type_event, event_callback, &subscription_type_callback) == RMW_RET_OK;
  initialized = initialized &&
    rmw_event_set_callback(&liveliness_event, event_callback, &liveliness_callback) == RMW_RET_OK;
  const bool local_graph_guard_drained =
    wait_for_graph_guard(graph_wait_set, graph_guard, 0);
  initialized = initialized && graph_guard != nullptr && local_graph_guard_drained;

  const std::uint64_t advertisements_before =
    rmw_fleetqox_cpp_remote_graph_event_advertisements_received();
  const std::uint64_t adds_before = rmw_fleetqox_cpp_remote_graph_event_endpoint_adds();
  const std::uint64_t renewals_before = rmw_fleetqox_cpp_remote_graph_event_endpoint_renewals();
  const std::uint64_t removes_before = rmw_fleetqox_cpp_remote_graph_event_endpoint_removes();
  const std::uint64_t expiries_before = rmw_fleetqox_cpp_remote_graph_event_endpoint_expiries();

  std::cout << "{\"schema_version\":\"fleetrmw.remote_event_probe.v1\","
            << "\"mode\":\"observer\",\"phase\":\"ready\","
            << "\"initialized\":" << (initialized ? "true" : "false") << "}" << std::endl;

  rmw_matched_status_t publication_connect{};
  rmw_matched_status_t subscription_connect{};
  rmw_offered_qos_incompatible_event_status_t offered_status{};
  rmw_requested_qos_incompatible_event_status_t requested_status{};
  rmw_offered_qos_incompatible_event_status_t offered_durability_status{};
  rmw_requested_qos_incompatible_event_status_t requested_durability_status{};
  rmw_offered_qos_incompatible_event_status_t offered_deadline_status{};
  rmw_requested_qos_incompatible_event_status_t requested_deadline_status{};
  rmw_incompatible_type_status_t publisher_type_status{};
  rmw_incompatible_type_status_t subscription_type_status{};
  rmw_liveliness_changed_status_t liveliness_connect{};
  rmw_matched_status_t publication_disconnect{};
  rmw_matched_status_t subscription_disconnect{};
  rmw_liveliness_changed_status_t liveliness_disconnect{};

  const auto deadline =
    std::chrono::steady_clock::now() + std::chrono::milliseconds(config.timeout_ms);
  const bool publication_connect_taken = initialized &&
    wait_take_event(&publication_match_event, &publication_connect, deadline);
  const bool subscription_connect_taken = initialized &&
    wait_take_event(&subscription_match_event, &subscription_connect, deadline);
  const bool offered_taken = initialized && wait_take_event(&offered_qos_event, &offered_status, deadline);
  const bool requested_taken = initialized &&
    wait_take_event(&requested_qos_event, &requested_status, deadline);
  const bool offered_durability_taken = initialized &&
    wait_take_event(&offered_durability_event, &offered_durability_status, deadline);
  const bool requested_durability_taken = initialized &&
    wait_take_event(&requested_durability_event, &requested_durability_status, deadline);
  const bool offered_deadline_taken = initialized &&
    wait_take_event(&offered_deadline_event, &offered_deadline_status, deadline);
  const bool requested_deadline_taken = initialized &&
    wait_take_event(&requested_deadline_event, &requested_deadline_status, deadline);
  const bool publisher_type_taken = initialized &&
    wait_take_event(&publisher_type_event, &publisher_type_status, deadline);
  const bool subscription_type_taken = initialized &&
    wait_take_event(&subscription_type_event, &subscription_type_status, deadline);
  const bool liveliness_connect_taken = initialized &&
    wait_take_event(&liveliness_event, &liveliness_connect, deadline);
  const bool remote_graph_guard_add_ready =
    wait_for_graph_guard(graph_wait_set, graph_guard, 0);
  const bool remote_graph_guard_renewal_suppressed =
    !wait_for_graph_guard(graph_wait_set, graph_guard, 650);
  const bool publication_disconnect_taken = initialized &&
    wait_take_event(&publication_match_event, &publication_disconnect, deadline);
  const bool subscription_disconnect_taken = initialized &&
    wait_take_event(&subscription_match_event, &subscription_disconnect, deadline);
  const bool liveliness_disconnect_taken = initialized &&
    wait_take_event(&liveliness_event, &liveliness_disconnect, deadline);
  const bool remote_graph_guard_disconnect_ready =
    wait_for_graph_guard(graph_wait_set, graph_guard, 100);

  std::this_thread::sleep_for(std::chrono::milliseconds(250));
  rmw_offered_qos_incompatible_event_status_t offered_after_clear{};
  rmw_requested_qos_incompatible_event_status_t requested_after_clear{};
  rmw_offered_qos_incompatible_event_status_t offered_durability_after_clear{};
  rmw_requested_qos_incompatible_event_status_t requested_durability_after_clear{};
  rmw_offered_qos_incompatible_event_status_t offered_deadline_after_clear{};
  rmw_requested_qos_incompatible_event_status_t requested_deadline_after_clear{};
  rmw_incompatible_type_status_t publisher_type_after_clear{};
  rmw_incompatible_type_status_t subscription_type_after_clear{};
  const bool no_duplicate_offered = event_is_clear(&offered_qos_event, &offered_after_clear);
  const bool no_duplicate_requested = event_is_clear(&requested_qos_event, &requested_after_clear);
  const bool no_duplicate_offered_durability =
    event_is_clear(&offered_durability_event, &offered_durability_after_clear);
  const bool no_duplicate_requested_durability =
    event_is_clear(&requested_durability_event, &requested_durability_after_clear);
  const bool no_duplicate_offered_deadline =
    event_is_clear(&offered_deadline_event, &offered_deadline_after_clear);
  const bool no_duplicate_requested_deadline =
    event_is_clear(&requested_deadline_event, &requested_deadline_after_clear);
  const bool no_duplicate_publisher_type =
    event_is_clear(&publisher_type_event, &publisher_type_after_clear);
  const bool no_duplicate_subscription_type =
    event_is_clear(&subscription_type_event, &subscription_type_after_clear);

  const std::uint64_t advertisements =
    rmw_fleetqox_cpp_remote_graph_event_advertisements_received() - advertisements_before;
  const std::uint64_t adds = rmw_fleetqox_cpp_remote_graph_event_endpoint_adds() - adds_before;
  const std::uint64_t renewals =
    rmw_fleetqox_cpp_remote_graph_event_endpoint_renewals() - renewals_before;
  const std::uint64_t removes =
    rmw_fleetqox_cpp_remote_graph_event_endpoint_removes() - removes_before;
  const std::uint64_t expiries =
    rmw_fleetqox_cpp_remote_graph_event_endpoint_expiries() - expiries_before;
  const size_t endpoint_count = rmw_fleetqox_cpp_remote_graph_event_endpoint_count();

  const bool matched_ok =
    publication_connect_taken && publication_connect.total_count == 1 &&
    publication_connect.current_count == 1 && publication_connect.current_count_change == 1 &&
    publication_disconnect_taken && publication_disconnect.total_count == 1 &&
    publication_disconnect.current_count == 0 &&
    publication_disconnect.current_count_change == -1 &&
    subscription_connect_taken && subscription_connect.total_count == 1 &&
    subscription_connect.current_count == 1 && subscription_connect.current_count_change == 1 &&
    subscription_disconnect_taken && subscription_disconnect.total_count == 1 &&
    subscription_disconnect.current_count == 0 &&
    subscription_disconnect.current_count_change == -1;
  const bool qos_ok =
    offered_taken && offered_status.total_count == 1 && offered_status.total_count_change == 1 &&
    offered_status.last_policy_kind == RMW_QOS_POLICY_RELIABILITY &&
    requested_taken && requested_status.total_count == 1 &&
    requested_status.total_count_change == 1 &&
    requested_status.last_policy_kind == RMW_QOS_POLICY_RELIABILITY &&
    offered_durability_taken && offered_durability_status.total_count == 1 &&
    offered_durability_status.total_count_change == 1 &&
    offered_durability_status.last_policy_kind == RMW_QOS_POLICY_DURABILITY &&
    requested_durability_taken && requested_durability_status.total_count == 1 &&
    requested_durability_status.total_count_change == 1 &&
    requested_durability_status.last_policy_kind == RMW_QOS_POLICY_DURABILITY &&
    offered_deadline_taken && offered_deadline_status.total_count == 1 &&
    offered_deadline_status.total_count_change == 1 &&
    offered_deadline_status.last_policy_kind == RMW_QOS_POLICY_DEADLINE &&
    requested_deadline_taken && requested_deadline_status.total_count == 1 &&
    requested_deadline_status.total_count_change == 1 &&
    requested_deadline_status.last_policy_kind == RMW_QOS_POLICY_DEADLINE &&
    no_duplicate_offered && no_duplicate_requested &&
    no_duplicate_offered_durability && no_duplicate_requested_durability &&
    no_duplicate_offered_deadline && no_duplicate_requested_deadline;
  const bool type_ok =
    publisher_type_taken && publisher_type_status.total_count == 1 &&
    publisher_type_status.total_count_change == 1 &&
    subscription_type_taken && subscription_type_status.total_count == 1 &&
    subscription_type_status.total_count_change == 1 &&
    no_duplicate_publisher_type && no_duplicate_subscription_type;
  const bool liveliness_ok =
    liveliness_connect_taken && liveliness_connect.alive_count == 1 &&
    liveliness_connect.alive_count_change == 1 && liveliness_connect.not_alive_count == 0 &&
    liveliness_disconnect_taken && liveliness_disconnect.alive_count == 0 &&
    liveliness_disconnect.alive_count_change == -1 &&
    liveliness_disconnect.not_alive_count == 0;
  const bool lease_path_ok = config.expect_expiry ?
    (expiries >= 11 && removes == 0) : (removes >= 11 && expiries == 0);
  const bool registry_ok =
    advertisements >= 33 && adds == 11 && renewals >= 11 && endpoint_count == 0 && lease_path_ok;
  const bool callbacks_ok =
    publication_callback.events.load(std::memory_order_relaxed) >= 2 &&
    subscription_callback.events.load(std::memory_order_relaxed) >= 2 &&
    offered_callback.events.load(std::memory_order_relaxed) == 1 &&
    requested_callback.events.load(std::memory_order_relaxed) == 1 &&
    offered_durability_callback.events.load(std::memory_order_relaxed) == 1 &&
    requested_durability_callback.events.load(std::memory_order_relaxed) == 1 &&
    offered_deadline_callback.events.load(std::memory_order_relaxed) == 1 &&
    requested_deadline_callback.events.load(std::memory_order_relaxed) == 1 &&
    publisher_type_callback.events.load(std::memory_order_relaxed) == 1 &&
    subscription_type_callback.events.load(std::memory_order_relaxed) == 1 &&
    liveliness_callback.events.load(std::memory_order_relaxed) >= 2;
  const bool graph_guard_ok =
    remote_graph_guard_add_ready && remote_graph_guard_renewal_suppressed &&
    remote_graph_guard_disconnect_ready;
  const bool ok = initialized && matched_ok && qos_ok && type_ok && liveliness_ok &&
    registry_ok && callbacks_ok && graph_guard_ok;

  std::cout << "{\"schema_version\":\"fleetrmw.remote_event_probe.v1\","
            << "\"mode\":\"observer\",\"status\":\"" << (ok ? "ok" : "failed") << "\","
            << "\"expect_expiry\":" << (config.expect_expiry ? "true" : "false") << ","
            << "\"matched_ok\":" << (matched_ok ? "true" : "false") << ","
            << "\"qos_ok\":" << (qos_ok ? "true" : "false") << ","
            << "\"type_ok\":" << (type_ok ? "true" : "false") << ","
            << "\"liveliness_ok\":" << (liveliness_ok ? "true" : "false") << ","
            << "\"graph_guard_ok\":" << (graph_guard_ok ? "true" : "false") << ","
            << "\"remote_graph_guard_add_ready\":"
            << (remote_graph_guard_add_ready ? "true" : "false") << ","
            << "\"remote_graph_guard_renewal_suppressed\":"
            << (remote_graph_guard_renewal_suppressed ? "true" : "false") << ","
            << "\"remote_graph_guard_disconnect_ready\":"
            << (remote_graph_guard_disconnect_ready ? "true" : "false") << ","
            << "\"renewal_deduplicated\":"
            << ((no_duplicate_offered && no_duplicate_requested &&
              no_duplicate_offered_durability && no_duplicate_requested_durability &&
              no_duplicate_offered_deadline && no_duplicate_requested_deadline &&
              no_duplicate_publisher_type && no_duplicate_subscription_type) ? "true" : "false")
            << ",\"publication_connect_current_count\":" << publication_connect.current_count
            << ",\"publication_disconnect_current_count\":" << publication_disconnect.current_count
            << ",\"subscription_connect_current_count\":" << subscription_connect.current_count
            << ",\"subscription_disconnect_current_count\":" << subscription_disconnect.current_count
            << ",\"offered_total_count\":" << offered_status.total_count
            << ",\"requested_total_count\":" << requested_status.total_count
            << ",\"offered_durability_total_count\":" << offered_durability_status.total_count
            << ",\"requested_durability_total_count\":" << requested_durability_status.total_count
            << ",\"offered_deadline_total_count\":" << offered_deadline_status.total_count
            << ",\"requested_deadline_total_count\":" << requested_deadline_status.total_count
            << ",\"publisher_type_total_count\":" << publisher_type_status.total_count
            << ",\"subscription_type_total_count\":" << subscription_type_status.total_count
            << ",\"liveliness_connect_alive_count\":" << liveliness_connect.alive_count
            << ",\"liveliness_disconnect_alive_count\":" << liveliness_disconnect.alive_count
            << ",\"advertisements_received\":" << advertisements
            << ",\"endpoint_adds\":" << adds
            << ",\"endpoint_renewals\":" << renewals
            << ",\"endpoint_removes\":" << removes
            << ",\"endpoint_expiries\":" << expiries
            << ",\"endpoint_count_after\":" << endpoint_count
            << ",\"publication_callback_events\":"
            << publication_callback.events.load(std::memory_order_relaxed)
            << ",\"subscription_callback_events\":"
            << subscription_callback.events.load(std::memory_order_relaxed)
            << ",\"liveliness_callback_events\":"
            << liveliness_callback.events.load(std::memory_order_relaxed) << "}" << std::endl;

  fini_events({
    &publication_match_event,
    &subscription_match_event,
    &offered_qos_event,
    &requested_qos_event,
    &offered_durability_event,
    &requested_durability_event,
    &offered_deadline_event,
    &requested_deadline_event,
    &publisher_type_event,
    &subscription_type_event,
    &liveliness_event});
  const std::vector<rmw_subscription_t *> subscriptions{
    liveliness_subscription,
    subscription_type_subscription,
    requested_deadline_subscription,
    requested_durability_subscription,
    requested_qos_subscription,
    subscription_match_subscription};
  for (rmw_subscription_t * subscription : subscriptions) {
    if (subscription != nullptr) {
      const rmw_ret_t ret = rmw_destroy_subscription(node, subscription);
      (void)ret;
    }
  }
  const std::vector<rmw_publisher_t *> publishers{
    publisher_type_publisher,
    offered_deadline_publisher,
    offered_durability_publisher,
    offered_qos_publisher,
    publication_match_publisher};
  for (rmw_publisher_t * publisher : publishers) {
    if (publisher != nullptr) {
      const rmw_ret_t ret = rmw_destroy_publisher(node, publisher);
      (void)ret;
    }
  }
  const rmw_ret_t wait_set_ret = rmw_destroy_wait_set(graph_wait_set);
  (void)wait_set_ret;
  const rmw_ret_t node_ret = rmw_destroy_node(node);
  (void)node_ret;
  cleanup_context(&context, &options);
  return ok ? 0 : 1;
}

}  // namespace

int main(int argc, char ** argv)
{
  const ProbeConfig config = parse_args(argc, argv);
  if (config.mode == "advertiser") {
    return run_advertiser(config);
  }
  if (config.mode == "observer") {
    return run_observer(config);
  }
  std::cout << "{\"status\":\"invalid_mode\"}" << std::endl;
  return 2;
}

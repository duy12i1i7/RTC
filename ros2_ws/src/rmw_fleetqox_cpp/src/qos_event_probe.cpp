#include <chrono>
#include <cstdint>
#include <cstring>
#include <iostream>
#include <sstream>
#include <string>
#include <thread>

#include "rcutils/allocator.h"
#include "rmw/event.h"
#include "rmw/events_statuses/events_statuses.h"
#include "rmw/init.h"
#include "rmw/init_options.h"
#include "rmw/publisher_options.h"
#include "rmw/qos_profiles.h"
#include "rmw/rmw.h"
#include "rmw/serialized_message.h"
#include "rmw/subscription_options.h"
#include "rosidl_runtime_c/message_type_support_struct.h"

extern "C" std::uint64_t rmw_fleetqox_cpp_socket_data_frames_received();
extern "C" std::uint64_t rmw_fleetqox_cpp_qos_events_initialized();
extern "C" std::uint64_t rmw_fleetqox_cpp_qos_events_finalized();
extern "C" std::uint64_t rmw_fleetqox_cpp_qos_event_callbacks_set();

namespace
{

struct CallbackState
{
  std::uint64_t calls;
  std::uint64_t events;
};

void event_callback(const void * user_data, size_t number_of_events)
{
  auto * state = const_cast<CallbackState *>(static_cast<const CallbackState *>(user_data));
  if (state != nullptr) {
    ++state->calls;
    state->events += number_of_events;
  }
}

bool init_serialized_message(
  rmw_serialized_message_t * message,
  const std::string & payload,
  rcutils_allocator_t * allocator)
{
  if (message == nullptr || allocator == nullptr ||
    rmw_serialized_message_init(message, payload.size(), allocator) != RMW_RET_OK)
  {
    return false;
  }
  if (!payload.empty()) {
    std::memcpy(message->buffer, payload.data(), payload.size());
  }
  message->buffer_length = payload.size();
  return true;
}

bool wait_for_received_frames(std::uint64_t baseline, std::uint64_t expected_delta)
{
  for (int i = 0; i < 100; ++i) {
    if (rmw_fleetqox_cpp_socket_data_frames_received() >= baseline + expected_delta) {
      return true;
    }
    std::this_thread::sleep_for(std::chrono::milliseconds(10));
  }
  return false;
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

}  // namespace

int main()
{
  rcutils_allocator_t allocator = rcutils_get_default_allocator();
  rmw_init_options_t options = rmw_get_zero_initialized_init_options();
  rmw_ret_t ret = rmw_init_options_init(&options, allocator);
  if (ret != RMW_RET_OK) {
    std::cout << "{\"status\":\"init_options_failed\",\"ret\":" << ret << "}" << std::endl;
    return 1;
  }
  options.instance_id = 56;

  rmw_context_t context = rmw_get_zero_initialized_context();
  ret = rmw_init(&options, &context);
  if (ret != RMW_RET_OK) {
    const rmw_ret_t fini_ret = rmw_init_options_fini(&options);
    (void)fini_ret;
    std::cout << "{\"status\":\"init_failed\",\"ret\":" << ret << "}" << std::endl;
    return 1;
  }

  rmw_node_t * node = rmw_create_node(&context, "fleetqox_qos_event_probe", "/fleetqox");
  if (node == nullptr) {
    cleanup_context(&context, &options);
    std::cout << "{\"status\":\"create_node_failed\"}" << std::endl;
    return 1;
  }

  rosidl_message_type_support_t type_support{};
  type_support.typesupport_identifier = "rmw_fleetqox_cpp_qos_event_probe";
  rmw_qos_profile_t qos = rmw_qos_profile_default;
  qos.history = RMW_QOS_POLICY_HISTORY_KEEP_LAST;
  qos.depth = 8;
  qos.deadline.sec = 0;
  qos.deadline.nsec = 250000000;
  const char * topic = "/fleetqox/qos_event_probe";
  rmw_publisher_options_t publisher_options = rmw_get_default_publisher_options();
  rmw_subscription_options_t subscription_options = rmw_get_default_subscription_options();
  rmw_publisher_t * publisher = rmw_create_publisher(
    node, &type_support, topic, &qos, &publisher_options);
  rmw_subscription_t * subscription = rmw_create_subscription(
    node, &type_support, topic, &qos, &subscription_options);

  const bool offered_supported =
    rmw_event_type_is_supported(RMW_EVENT_OFFERED_DEADLINE_MISSED);
  const bool requested_supported =
    rmw_event_type_is_supported(RMW_EVENT_REQUESTED_DEADLINE_MISSED);
  const bool invalid_supported = rmw_event_type_is_supported(RMW_EVENT_INVALID);
  const std::uint64_t events_init_before = rmw_fleetqox_cpp_qos_events_initialized();
  const std::uint64_t events_fini_before = rmw_fleetqox_cpp_qos_events_finalized();
  const std::uint64_t callbacks_before = rmw_fleetqox_cpp_qos_event_callbacks_set();

  rmw_event_t publisher_event = rmw_get_zero_initialized_event();
  rmw_event_t subscription_event = rmw_get_zero_initialized_event();
  const rmw_ret_t publisher_event_init_ret = publisher == nullptr ?
    RMW_RET_ERROR :
    rmw_publisher_event_init(&publisher_event, publisher, RMW_EVENT_OFFERED_DEADLINE_MISSED);
  const rmw_ret_t subscription_event_init_ret = subscription == nullptr ?
    RMW_RET_ERROR :
    rmw_subscription_event_init(
      &subscription_event, subscription, RMW_EVENT_REQUESTED_DEADLINE_MISSED);

  CallbackState publisher_callback_state{0, 0};
  CallbackState subscription_callback_state{0, 0};
  const rmw_ret_t publisher_callback_ret =
    rmw_event_set_callback(&publisher_event, event_callback, &publisher_callback_state);
  const rmw_ret_t subscription_callback_ret =
    rmw_event_set_callback(&subscription_event, event_callback, &subscription_callback_state);

  rmw_wait_set_t * wait_set = rmw_create_wait_set(&context, 2);
  rmw_time_t zero_timeout{};
  void * initial_wait_event_handles[2] = {&publisher_event, &subscription_event};
  rmw_events_t initial_wait_events{2, initial_wait_event_handles};
  const rmw_ret_t initial_wait_ret = wait_set == nullptr ?
    RMW_RET_ERROR :
    rmw_wait(nullptr, nullptr, nullptr, nullptr, &initial_wait_events, wait_set, &zero_timeout);
  const bool initial_publisher_wait_ready = initial_wait_event_handles[0] != nullptr;
  const bool initial_subscription_wait_ready = initial_wait_event_handles[1] != nullptr;

  rmw_offered_deadline_missed_status_t initial_offered_status{};
  rmw_requested_deadline_missed_status_t initial_requested_status{};
  bool initial_publisher_taken = true;
  bool initial_subscription_taken = true;
  const rmw_ret_t initial_publisher_take_ret =
    rmw_take_event(&publisher_event, &initial_offered_status, &initial_publisher_taken);
  const rmw_ret_t initial_subscription_take_ret =
    rmw_take_event(&subscription_event, &initial_requested_status, &initial_subscription_taken);

  rmw_serialized_message_t first = rmw_get_zero_initialized_serialized_message();
  rmw_serialized_message_t second = rmw_get_zero_initialized_serialized_message();
  const bool messages_initialized =
    init_serialized_message(&first, "deadline-one", &allocator) &&
    init_serialized_message(&second, "deadline-two", &allocator);
  const std::uint64_t frames_before = rmw_fleetqox_cpp_socket_data_frames_received();
  const rmw_ret_t first_publish_ret = messages_initialized ?
    rmw_publish_serialized_message(publisher, &first, nullptr) : RMW_RET_ERROR;
  const bool first_receive_ready =
    wait_for_received_frames(frames_before, first_publish_ret == RMW_RET_OK ? 1 : 0);
  std::this_thread::sleep_for(std::chrono::milliseconds(600));
  void * idle_wait_event_handles[2] = {&publisher_event, &subscription_event};
  rmw_events_t idle_wait_events{2, idle_wait_event_handles};
  const rmw_ret_t idle_wait_ret = wait_set == nullptr ?
    RMW_RET_ERROR :
    rmw_wait(nullptr, nullptr, nullptr, nullptr, &idle_wait_events, wait_set, &zero_timeout);
  const bool idle_publisher_wait_ready = idle_wait_event_handles[0] != nullptr;
  const bool idle_subscription_wait_ready = idle_wait_event_handles[1] != nullptr;
  std::this_thread::sleep_for(std::chrono::milliseconds(10));
  const rmw_ret_t second_publish_ret = messages_initialized ?
    rmw_publish_serialized_message(publisher, &second, nullptr) : RMW_RET_ERROR;
  const bool second_receive_ready =
    wait_for_received_frames(frames_before, second_publish_ret == RMW_RET_OK ? 2 : 0);
  std::this_thread::sleep_for(std::chrono::milliseconds(600));

  void * wait_event_handles[2] = {&publisher_event, &subscription_event};
  rmw_events_t wait_events{2, wait_event_handles};
  const rmw_ret_t wait_ret = wait_set == nullptr ?
    RMW_RET_ERROR :
    rmw_wait(nullptr, nullptr, nullptr, nullptr, &wait_events, wait_set, &zero_timeout);
  const bool publisher_wait_ready = wait_event_handles[0] != nullptr;
  const bool subscription_wait_ready = wait_event_handles[1] != nullptr;

  // Reset both deadline anchors before checking clear semantics. Without this
  // sample, a recurring deadline event can legitimately arrive between the
  // first and second rmw_take_event calls and make the probe scheduler-racy.
  const rmw_ret_t reset_publish_ret = messages_initialized ?
    rmw_publish_serialized_message(publisher, &second, nullptr) : RMW_RET_ERROR;
  const bool reset_receive_ready =
    wait_for_received_frames(frames_before, reset_publish_ret == RMW_RET_OK ? 3 : 0);

  rmw_offered_deadline_missed_status_t offered_status{};
  rmw_requested_deadline_missed_status_t requested_status{};
  bool publisher_taken = false;
  bool subscription_taken = false;
  const rmw_ret_t publisher_take_ret =
    rmw_take_event(&publisher_event, &offered_status, &publisher_taken);
  const rmw_ret_t subscription_take_ret =
    rmw_take_event(&subscription_event, &requested_status, &subscription_taken);

  rmw_offered_deadline_missed_status_t offered_after_clear{};
  rmw_requested_deadline_missed_status_t requested_after_clear{};
  bool publisher_taken_after_clear = true;
  bool subscription_taken_after_clear = true;
  const rmw_ret_t publisher_take_after_clear_ret =
    rmw_take_event(&publisher_event, &offered_after_clear, &publisher_taken_after_clear);
  const rmw_ret_t subscription_take_after_clear_ret =
    rmw_take_event(&subscription_event, &requested_after_clear, &subscription_taken_after_clear);

  void * wait_after_clear_event_handles[2] = {&publisher_event, &subscription_event};
  rmw_events_t wait_after_clear_events{2, wait_after_clear_event_handles};
  const rmw_ret_t wait_after_clear_ret = wait_set == nullptr ?
    RMW_RET_ERROR :
    rmw_wait(
      nullptr, nullptr, nullptr, nullptr, &wait_after_clear_events, wait_set, &zero_timeout);
  const bool publisher_wait_ready_after_clear = wait_after_clear_event_handles[0] != nullptr;
  const bool subscription_wait_ready_after_clear = wait_after_clear_event_handles[1] != nullptr;

  const rmw_ret_t first_fini_ret = rmw_serialized_message_fini(&first);
  const rmw_ret_t second_fini_ret = rmw_serialized_message_fini(&second);
  const rmw_ret_t publisher_event_fini_ret = rmw_event_fini(&publisher_event);
  const rmw_ret_t subscription_event_fini_ret = rmw_event_fini(&subscription_event);
  const rmw_ret_t destroy_wait_set_ret = wait_set == nullptr ?
    RMW_RET_ERROR : rmw_destroy_wait_set(wait_set);
  const rmw_ret_t destroy_pub_ret = publisher == nullptr ?
    RMW_RET_ERROR : rmw_destroy_publisher(node, publisher);
  const rmw_ret_t destroy_sub_ret = subscription == nullptr ?
    RMW_RET_ERROR : rmw_destroy_subscription(node, subscription);
  const rmw_ret_t destroy_node_ret = rmw_destroy_node(node);
  cleanup_context(&context, &options);

  const std::uint64_t events_init_delta =
    rmw_fleetqox_cpp_qos_events_initialized() - events_init_before;
  const std::uint64_t events_fini_delta =
    rmw_fleetqox_cpp_qos_events_finalized() - events_fini_before;
  const std::uint64_t callbacks_delta =
    rmw_fleetqox_cpp_qos_event_callbacks_set() - callbacks_before;
  const bool event_object_ok =
    offered_supported &&
    requested_supported &&
    !invalid_supported &&
    publisher_event_init_ret == RMW_RET_OK &&
    subscription_event_init_ret == RMW_RET_OK &&
    publisher_callback_ret == RMW_RET_OK &&
    subscription_callback_ret == RMW_RET_OK &&
    wait_set != nullptr &&
    initial_wait_ret == RMW_RET_TIMEOUT &&
    !initial_publisher_wait_ready &&
    !initial_subscription_wait_ready &&
    initial_publisher_take_ret == RMW_RET_OK &&
    initial_subscription_take_ret == RMW_RET_OK &&
    !initial_publisher_taken &&
    !initial_subscription_taken &&
    publisher_event_fini_ret == RMW_RET_OK &&
    subscription_event_fini_ret == RMW_RET_OK &&
    events_init_delta == 2 &&
    events_fini_delta == 2 &&
    callbacks_delta == 2;
  const bool wait_event_readiness_ok =
    wait_set != nullptr &&
    initial_wait_ret == RMW_RET_TIMEOUT &&
    !initial_publisher_wait_ready &&
    !initial_subscription_wait_ready &&
    wait_ret == RMW_RET_OK &&
    publisher_wait_ready &&
    subscription_wait_ready &&
    wait_after_clear_ret == RMW_RET_TIMEOUT &&
    !publisher_wait_ready_after_clear &&
    !subscription_wait_ready_after_clear;
  const bool timer_driven_idle_deadline_ok =
    idle_wait_ret == RMW_RET_OK &&
    idle_publisher_wait_ready &&
    idle_subscription_wait_ready;
  const bool event_production_ok =
    messages_initialized &&
    first_publish_ret == RMW_RET_OK &&
    second_publish_ret == RMW_RET_OK &&
    reset_publish_ret == RMW_RET_OK &&
    first_receive_ready &&
    timer_driven_idle_deadline_ok &&
    second_receive_ready &&
    reset_receive_ready &&
    wait_event_readiness_ok &&
    publisher_take_ret == RMW_RET_OK &&
    subscription_take_ret == RMW_RET_OK &&
    publisher_taken &&
    subscription_taken &&
    offered_status.total_count >= 1 &&
    offered_status.total_count_change >= 1 &&
    requested_status.total_count >= 1 &&
    requested_status.total_count_change >= 1 &&
    publisher_callback_state.calls >= 1 &&
    publisher_callback_state.events >= 1 &&
    subscription_callback_state.calls >= 1 &&
    subscription_callback_state.events >= 1 &&
    publisher_take_after_clear_ret == RMW_RET_OK &&
    subscription_take_after_clear_ret == RMW_RET_OK &&
    !publisher_taken_after_clear &&
    !subscription_taken_after_clear &&
    offered_after_clear.total_count == offered_status.total_count &&
    offered_after_clear.total_count_change == 0 &&
    requested_after_clear.total_count == requested_status.total_count &&
    requested_after_clear.total_count_change == 0;
  const bool cleanup_ok =
    first_fini_ret == RMW_RET_OK &&
    second_fini_ret == RMW_RET_OK &&
    destroy_wait_set_ret == RMW_RET_OK &&
    destroy_pub_ret == RMW_RET_OK &&
    destroy_sub_ret == RMW_RET_OK &&
    destroy_node_ret == RMW_RET_OK;
  const bool ok = event_object_ok && event_production_ok && cleanup_ok;

  std::cout << "{\"schema_version\":\"fleetrmw.qos_event_probe.v1\",";
  std::cout << "\"status\":\"" << (ok ? "ok" : "failed") << "\",";
  std::cout << "\"topic\":\"" << topic << "\",";
  std::cout << "\"publisher_event_init_ret\":" <<
    static_cast<int>(publisher_event_init_ret) << ",";
  std::cout << "\"subscription_event_init_ret\":" <<
    static_cast<int>(subscription_event_init_ret) << ",";
  std::cout << "\"publisher_callback_ret\":" <<
    static_cast<int>(publisher_callback_ret) << ",";
  std::cout << "\"subscription_callback_ret\":" <<
    static_cast<int>(subscription_callback_ret) << ",";
  std::cout << "\"initial_wait_ret\":" << static_cast<int>(initial_wait_ret) << ",";
  std::cout << "\"initial_publisher_wait_ready\":" <<
    (initial_publisher_wait_ready ? "true" : "false") << ",";
  std::cout << "\"initial_subscription_wait_ready\":" <<
    (initial_subscription_wait_ready ? "true" : "false") << ",";
  std::cout << "\"initial_publisher_taken\":" <<
    (initial_publisher_taken ? "true" : "false") << ",";
  std::cout << "\"initial_subscription_taken\":" <<
    (initial_subscription_taken ? "true" : "false") << ",";
  std::cout << "\"first_publish_ret\":" << static_cast<int>(first_publish_ret) << ",";
  std::cout << "\"second_publish_ret\":" << static_cast<int>(second_publish_ret) << ",";
  std::cout << "\"reset_publish_ret\":" << static_cast<int>(reset_publish_ret) << ",";
  std::cout << "\"first_receive_ready\":" << (first_receive_ready ? "true" : "false") << ",";
  std::cout << "\"idle_wait_ret\":" << static_cast<int>(idle_wait_ret) << ",";
  std::cout << "\"idle_publisher_wait_ready\":" <<
    (idle_publisher_wait_ready ? "true" : "false") << ",";
  std::cout << "\"idle_subscription_wait_ready\":" <<
    (idle_subscription_wait_ready ? "true" : "false") << ",";
  std::cout << "\"second_receive_ready\":" << (second_receive_ready ? "true" : "false") << ",";
  std::cout << "\"reset_receive_ready\":" << (reset_receive_ready ? "true" : "false") << ",";
  std::cout << "\"wait_ret\":" << static_cast<int>(wait_ret) << ",";
  std::cout << "\"publisher_wait_ready\":" << (publisher_wait_ready ? "true" : "false") << ",";
  std::cout << "\"subscription_wait_ready\":" <<
    (subscription_wait_ready ? "true" : "false") << ",";
  std::cout << "\"publisher_take_ret\":" << static_cast<int>(publisher_take_ret) << ",";
  std::cout << "\"subscription_take_ret\":" << static_cast<int>(subscription_take_ret) << ",";
  std::cout << "\"publisher_taken\":" << (publisher_taken ? "true" : "false") << ",";
  std::cout << "\"subscription_taken\":" << (subscription_taken ? "true" : "false") << ",";
  std::cout << "\"publisher_taken_after_clear\":" <<
    (publisher_taken_after_clear ? "true" : "false") << ",";
  std::cout << "\"subscription_taken_after_clear\":" <<
    (subscription_taken_after_clear ? "true" : "false") << ",";
  std::cout << "\"wait_after_clear_ret\":" << static_cast<int>(wait_after_clear_ret) << ",";
  std::cout << "\"publisher_wait_ready_after_clear\":" <<
    (publisher_wait_ready_after_clear ? "true" : "false") << ",";
  std::cout << "\"subscription_wait_ready_after_clear\":" <<
    (subscription_wait_ready_after_clear ? "true" : "false") << ",";
  std::cout << "\"offered_total_count\":" << offered_status.total_count << ",";
  std::cout << "\"offered_total_count_change\":" << offered_status.total_count_change << ",";
  std::cout << "\"requested_total_count\":" << requested_status.total_count << ",";
  std::cout << "\"requested_total_count_change\":" << requested_status.total_count_change << ",";
  std::cout << "\"publisher_callback_calls\":" << publisher_callback_state.calls << ",";
  std::cout << "\"publisher_callback_events\":" << publisher_callback_state.events << ",";
  std::cout << "\"subscription_callback_calls\":" << subscription_callback_state.calls << ",";
  std::cout << "\"subscription_callback_events\":" << subscription_callback_state.events << ",";
  std::cout << "\"events_initialized_delta\":" << events_init_delta << ",";
  std::cout << "\"events_finalized_delta\":" << events_fini_delta << ",";
  std::cout << "\"event_callbacks_set_delta\":" << callbacks_delta << ",";
  std::cout << "\"offered_deadline_supported\":" <<
    (offered_supported ? "true" : "false") << ",";
  std::cout << "\"requested_deadline_supported\":" <<
    (requested_supported ? "true" : "false") << ",";
  std::cout << "\"invalid_event_supported\":" << (invalid_supported ? "true" : "false") << ",";
  std::cout << "\"event_object_abi_ok\":" << (event_object_ok ? "true" : "false") << ",";
  std::cout << "\"deadline_event_production_scope\":\"timer_idle_and_next_publish_or_receive_after_gap\",";
  std::cout << "\"timer_driven_idle_deadline_events\":" <<
    (timer_driven_idle_deadline_ok ? "true" : "false") << ",";
  std::cout << "\"timer_driven_idle_deadline_scope\":\"after_first_publish_or_receive\",";
  std::cout << "\"wait_event_readiness\":" <<
    (wait_event_readiness_ok ? "true" : "false") << ",";
  std::cout << "\"wait_event_readiness_scope\":\"deadline_status_unread_count\",";
  std::cout << "\"event_production\":" << (event_production_ok ? "true" : "false") << "}" <<
    std::endl;
  return ok ? 0 : 1;
}

#include <algorithm>
#include <chrono>
#include <condition_variable>
#include <cstddef>
#include <cstdint>
#include <iostream>
#include <memory>
#include <mutex>
#include <string>
#include <thread>
#include <vector>

#include "rcutils/allocator.h"
#include "rmw/error_handling.h"
#include "rmw/init.h"
#include "rmw/init_options.h"
#include "rmw/message_sequence.h"
#include "rmw/publisher_options.h"
#include "rmw/qos_profiles.h"
#include "rmw/rmw.h"
#include "rmw/subscription_options.h"
#include "rosidl_runtime_c/string_functions.h"
#include "rosidl_typesupport_interface/macros.h"
#include "std_msgs/msg/detail/string__functions.h"
#include "std_msgs/msg/detail/string__rosidl_typesupport_introspection_c.h"
#include "std_msgs/msg/detail/string__struct.h"

extern "C" std::uint64_t rmw_fleetqox_cpp_socket_data_frames_received();

namespace
{

struct SequenceStorage
{
  explicit SequenceStorage(size_t count, rcutils_allocator_t * allocator)
  : count_(count), allocator_(allocator), messages_(std::make_unique<std_msgs__msg__String[]>(count))
  {
    message_sequence_ = rmw_get_zero_initialized_message_sequence();
    info_sequence_ = rmw_get_zero_initialized_message_info_sequence();
    initialized_ =
      rmw_message_sequence_init(&message_sequence_, count, allocator_) == RMW_RET_OK &&
      rmw_message_info_sequence_init(&info_sequence_, count, allocator_) == RMW_RET_OK;
    if (!initialized_) {
      return;
    }
    initialized_messages_ = 0;
    for (size_t index = 0; index < count_; ++index) {
      if (!std_msgs__msg__String__init(&messages_[index])) {
        initialized_ = false;
        return;
      }
      ++initialized_messages_;
      message_sequence_.data[index] = &messages_[index];
    }
    message_sequence_.size = count_;
    info_sequence_.size = count_;
  }

  ~SequenceStorage()
  {
    for (size_t index = 0; index < initialized_messages_; ++index) {
      std_msgs__msg__String__fini(&messages_[index]);
    }
    if (message_sequence_.allocator != nullptr) {
      (void)rmw_message_sequence_fini(&message_sequence_);
    }
    if (info_sequence_.allocator != nullptr) {
      (void)rmw_message_info_sequence_fini(&info_sequence_);
    }
  }

  bool initialized() const {return initialized_;}

  std::string value(size_t index) const
  {
    if (index >= count_ || messages_[index].data.data == nullptr) {
      return {};
    }
    return std::string(messages_[index].data.data, messages_[index].data.size);
  }

  size_t count_{0};
  rcutils_allocator_t * allocator_{nullptr};
  std::unique_ptr<std_msgs__msg__String[]> messages_;
  rmw_message_sequence_t message_sequence_{};
  rmw_message_info_sequence_t info_sequence_{};
  size_t initialized_messages_{0};
  bool initialized_{false};
};

bool publish_string(rmw_publisher_t * publisher, const std::string & value)
{
  std_msgs__msg__String message;
  if (!std_msgs__msg__String__init(&message)) {
    return false;
  }
  const bool assigned = rosidl_runtime_c__String__assignn(
    &message.data, value.data(), value.size());
  const rmw_ret_t ret = assigned ?
    rmw_publish(publisher, &message, nullptr) : RMW_RET_BAD_ALLOC;
  std_msgs__msg__String__fini(&message);
  return ret == RMW_RET_OK;
}

bool wait_for_received_frames(std::uint64_t baseline, std::uint64_t expected_delta)
{
  for (int attempt = 0; attempt < 1000; ++attempt) {
    if (rmw_fleetqox_cpp_socket_data_frames_received() >= baseline + expected_delta) {
      return true;
    }
    std::this_thread::sleep_for(std::chrono::milliseconds(1));
  }
  return false;
}

bool consecutive_publication_sequences(
  const SequenceStorage & storage, size_t taken, std::vector<std::int64_t> * output)
{
  if (output == nullptr || taken == 0 || storage.info_sequence_.size != taken) {
    return false;
  }
  for (size_t index = 0; index < taken; ++index) {
    const std::int64_t sequence =
      storage.info_sequence_.data[index].publication_sequence_number;
    output->push_back(sequence);
    if (index > 0 && sequence != output->at(output->size() - 2) + 1) {
      return false;
    }
  }
  return true;
}

bool cleanup_context(rmw_context_t * context, rmw_init_options_t * options)
{
  const rmw_ret_t shutdown_ret = rmw_shutdown(context);
  const rmw_ret_t context_fini_ret = rmw_context_fini(context);
  const rmw_ret_t options_fini_ret = rmw_init_options_fini(options);
  return shutdown_ret == RMW_RET_OK && context_fini_ret == RMW_RET_OK &&
         options_fini_ret == RMW_RET_OK;
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
  options.instance_id = 181;
  rmw_context_t context = rmw_get_zero_initialized_context();
  if (rmw_init(&options, &context) != RMW_RET_OK) {
    const rmw_ret_t options_fini_ret = rmw_init_options_fini(&options);
    std::cout << "{\"status\":\"init_failed\"}\n";
    return options_fini_ret == RMW_RET_OK ? 1 : 2;
  }
  rmw_node_t * node = rmw_create_node(&context, "fleetqox_take_sequence_probe", "/fleetqox");
  if (node == nullptr) {
    const bool context_cleanup_ok = cleanup_context(&context, &options);
    std::cout << "{\"status\":\"create_node_failed\"}\n";
    return context_cleanup_ok ? 1 : 2;
  }

  const rosidl_message_type_support_t * type_support =
    ROSIDL_TYPESUPPORT_INTERFACE__MESSAGE_SYMBOL_NAME(
    rosidl_typesupport_introspection_c, std_msgs, msg, String)();
  rmw_qos_profile_t qos = rmw_qos_profile_default;
  qos.history = RMW_QOS_POLICY_HISTORY_KEEP_ALL;
  qos.depth = 64;
  rmw_publisher_options_t publisher_options = rmw_get_default_publisher_options();
  rmw_subscription_options_t subscription_options = rmw_get_default_subscription_options();
  rmw_publisher_t * publisher = rmw_create_publisher(
    node, type_support, "/fleetqox/take_sequence", &qos, &publisher_options);
  rmw_subscription_t * subscription = rmw_create_subscription(
    node, type_support, "/fleetqox/take_sequence", &qos, &subscription_options);
  if (publisher == nullptr || subscription == nullptr) {
    const rmw_ret_t destroy_subscription_ret = subscription == nullptr ?
      RMW_RET_OK : rmw_destroy_subscription(node, subscription);
    const rmw_ret_t destroy_publisher_ret = publisher == nullptr ?
      RMW_RET_OK : rmw_destroy_publisher(node, publisher);
    const rmw_ret_t destroy_node_ret = rmw_destroy_node(node);
    const bool context_cleanup_ok = cleanup_context(&context, &options);
    std::cout << "{\"status\":\"create_endpoint_failed\"}\n";
    return destroy_subscription_ret == RMW_RET_OK && destroy_publisher_ret == RMW_RET_OK &&
           destroy_node_ret == RMW_RET_OK && context_cleanup_ok ? 1 : 2;
  }

  const std::uint64_t first_baseline = rmw_fleetqox_cpp_socket_data_frames_received();
  bool first_publish_ok = true;
  for (int index = 0; index < 5; ++index) {
    first_publish_ok = first_publish_ok &&
      publish_string(publisher, "initial-" + std::to_string(index));
  }
  first_publish_ok = first_publish_ok && wait_for_received_frames(first_baseline, 5);

  SequenceStorage first(3, &allocator);
  size_t first_taken = 0;
  const rmw_ret_t first_ret = first.initialized() ?
    rmw_take_sequence(
      subscription, 3, &first.message_sequence_, &first.info_sequence_,
      &first_taken, nullptr) : RMW_RET_BAD_ALLOC;
  const bool first_order_ok =
    first_ret == RMW_RET_OK && first_taken == 3 &&
    first.value(0) == "initial-0" && first.value(1) == "initial-1" &&
    first.value(2) == "initial-2" &&
    first.info_sequence_.data[0].publication_sequence_number == 1 &&
    first.info_sequence_.data[1].publication_sequence_number == 2 &&
    first.info_sequence_.data[2].publication_sequence_number == 3;

  SequenceStorage partial(3, &allocator);
  size_t partial_taken = 0;
  const rmw_ret_t partial_ret = partial.initialized() ?
    rmw_take_sequence(
      subscription, 3, &partial.message_sequence_, &partial.info_sequence_,
      &partial_taken, nullptr) : RMW_RET_BAD_ALLOC;
  const bool partial_ok =
    partial_ret == RMW_RET_OK && partial_taken == 2 &&
    partial.message_sequence_.size == 2 && partial.info_sequence_.size == 2 &&
    partial.value(0) == "initial-3" && partial.value(1) == "initial-4" &&
    partial.info_sequence_.data[0].publication_sequence_number == 4 &&
    partial.info_sequence_.data[1].publication_sequence_number == 5;

  const size_t empty_message_size_before = partial.message_sequence_.size;
  const size_t empty_info_size_before = partial.info_sequence_.size;
  size_t empty_taken = 99;
  const rmw_ret_t empty_ret = rmw_take_sequence(
    subscription, 3, &partial.message_sequence_, &partial.info_sequence_,
    &empty_taken, nullptr);
  const bool empty_unchanged_ok =
    empty_ret == RMW_RET_OK && empty_taken == 0 &&
    partial.message_sequence_.size == empty_message_size_before &&
    partial.info_sequence_.size == empty_info_size_before;

  SequenceStorage undersized(1, &allocator);
  size_t invalid_taken = 77;
  const size_t invalid_message_size_before = undersized.message_sequence_.size;
  const size_t invalid_info_size_before = undersized.info_sequence_.size;
  const rmw_ret_t invalid_ret = rmw_take_sequence(
    subscription, 2, &undersized.message_sequence_, &undersized.info_sequence_,
    &invalid_taken, nullptr);
  const bool invalid_unchanged_ok =
    invalid_ret == RMW_RET_INVALID_ARGUMENT && invalid_taken == 77 &&
    undersized.message_sequence_.size == invalid_message_size_before &&
    undersized.info_sequence_.size == invalid_info_size_before;
  rmw_reset_error();

  const std::uint64_t concurrent_baseline = rmw_fleetqox_cpp_socket_data_frames_received();
  bool concurrent_publish_ok = true;
  for (int index = 0; index < 20; ++index) {
    concurrent_publish_ok = concurrent_publish_ok &&
      publish_string(publisher, "concurrent-" + std::to_string(index));
  }
  concurrent_publish_ok = concurrent_publish_ok &&
    wait_for_received_frames(concurrent_baseline, 20);

  SequenceStorage concurrent_a(10, &allocator);
  SequenceStorage concurrent_b(10, &allocator);
  std::mutex start_mutex;
  std::condition_variable start_cv;
  int ready_threads = 0;
  bool start = false;
  auto await_start = [&]() {
      std::unique_lock<std::mutex> lock(start_mutex);
      ++ready_threads;
      start_cv.notify_all();
      start_cv.wait(lock, [&]() {return start;});
    };
  rmw_ret_t concurrent_a_ret = RMW_RET_ERROR;
  rmw_ret_t concurrent_b_ret = RMW_RET_ERROR;
  size_t concurrent_a_taken = 0;
  size_t concurrent_b_taken = 0;
  std::thread thread_a([&]() {
      await_start();
      concurrent_a_ret = rmw_take_sequence(
        subscription, 10, &concurrent_a.message_sequence_, &concurrent_a.info_sequence_,
        &concurrent_a_taken, nullptr);
    });
  std::thread thread_b([&]() {
      await_start();
      concurrent_b_ret = rmw_take_sequence(
        subscription, 10, &concurrent_b.message_sequence_, &concurrent_b.info_sequence_,
        &concurrent_b_taken, nullptr);
    });
  {
    std::unique_lock<std::mutex> lock(start_mutex);
    start_cv.wait(lock, [&]() {return ready_threads == 2;});
    start = true;
  }
  start_cv.notify_all();
  thread_a.join();
  thread_b.join();

  std::vector<std::int64_t> concurrent_sequences;
  const bool sequence_a_ok = consecutive_publication_sequences(
    concurrent_a, concurrent_a_taken, &concurrent_sequences);
  const bool sequence_b_ok = consecutive_publication_sequences(
    concurrent_b, concurrent_b_taken, &concurrent_sequences);
  std::sort(concurrent_sequences.begin(), concurrent_sequences.end());
  bool combined_order_ok = concurrent_sequences.size() == 20;
  for (size_t index = 0; index < concurrent_sequences.size(); ++index) {
    combined_order_ok = combined_order_ok &&
      concurrent_sequences[index] == static_cast<std::int64_t>(index + 6);
  }
  const bool concurrent_ok =
    concurrent_publish_ok && concurrent_a.initialized() && concurrent_b.initialized() &&
    concurrent_a_ret == RMW_RET_OK && concurrent_b_ret == RMW_RET_OK &&
    concurrent_a_taken == 10 && concurrent_b_taken == 10 &&
    sequence_a_ok && sequence_b_ok && combined_order_ok;

  const bool behavior_ok =
    first_publish_ok && first_order_ok && partial_ok && empty_unchanged_ok &&
    invalid_unchanged_ok && concurrent_ok;
  const rmw_ret_t destroy_subscription_ret = rmw_destroy_subscription(node, subscription);
  const rmw_ret_t destroy_publisher_ret = rmw_destroy_publisher(node, publisher);
  const rmw_ret_t destroy_node_ret = rmw_destroy_node(node);
  const bool context_cleanup_ok = cleanup_context(&context, &options);
  const bool cleanup_ok =
    destroy_subscription_ret == RMW_RET_OK && destroy_publisher_ret == RMW_RET_OK &&
    destroy_node_ret == RMW_RET_OK && context_cleanup_ok;

  std::cout << "{\"schema_version\":\"fleetrmw.rmw_take_sequence_probe.v1\",";
  std::cout << "\"status\":\"" << (behavior_ok && cleanup_ok ? "ok" : "failed") << "\",";
  std::cout << "\"symbol_exported\":true,";
  std::cout << "\"first_taken\":" << first_taken << ",";
  std::cout << "\"first_order_ok\":" << (first_order_ok ? "true" : "false") << ",";
  std::cout << "\"partial_taken\":" << partial_taken << ",";
  std::cout << "\"partial_take_ok\":" << (partial_ok ? "true" : "false") << ",";
  std::cout << "\"empty_sequences_unchanged\":" <<
    (empty_unchanged_ok ? "true" : "false") << ",";
  std::cout << "\"invalid_capacity_unchanged\":" <<
    (invalid_unchanged_ok ? "true" : "false") << ",";
  std::cout << "\"concurrent_call_count\":2,";
  std::cout << "\"concurrent_taken_total\":" <<
    (concurrent_a_taken + concurrent_b_taken) << ",";
  std::cout << "\"concurrent_sequences_consecutive\":" <<
    (sequence_a_ok && sequence_b_ok ? "true" : "false") << ",";
  std::cout << "\"concurrent_combined_order_complete\":" <<
    (combined_order_ok ? "true" : "false") << ",";
  std::cout << "\"thread_safe_same_subscription_take_sequence\":" <<
    (concurrent_ok ? "true" : "false") << "}\n";
  return behavior_ok && cleanup_ok ? 0 : 1;
}

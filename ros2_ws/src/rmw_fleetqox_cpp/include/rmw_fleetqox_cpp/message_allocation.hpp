#ifndef RMW_FLEETQOX_CPP__MESSAGE_ALLOCATION_HPP_
#define RMW_FLEETQOX_CPP__MESSAGE_ALLOCATION_HPP_

#include <atomic>
#include <cstddef>
#include <cstdint>
#include <mutex>
#include <vector>

#include "rosidl_runtime_c/message_type_support_struct.h"

namespace rmw_fleetqox_cpp
{

enum class MessageAllocationKind : std::uint8_t
{
  Publisher = 1,
  Subscription = 2,
};

constexpr std::uint64_t kMessageAllocationMagic = 0x46514f58414c4c4full;

struct MessageAllocationData
{
  explicit MessageAllocationData(
    MessageAllocationKind allocation_kind,
    const rosidl_message_type_support_t * allocation_type_support)
  : kind(allocation_kind),
    type_support(allocation_type_support)
  {
  }

  std::uint64_t magic{kMessageAllocationMagic};
  MessageAllocationKind kind;
  const rosidl_message_type_support_t * type_support;
  std::mutex mutex;
  std::vector<std::uint8_t> payload;
  std::size_t initial_capacity{0};
  std::atomic<std::uint64_t> uses{0};
  std::atomic<std::uint64_t> capacity_growths{0};
};

}  // namespace rmw_fleetqox_cpp

#endif  // RMW_FLEETQOX_CPP__MESSAGE_ALLOCATION_HPP_

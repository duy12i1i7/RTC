#ifndef RMW_FLEETQOX_CPP__SHARED_MEMORY_TRANSPORT_HPP_
#define RMW_FLEETQOX_CPP__SHARED_MEMORY_TRANSPORT_HPP_

#include <cstddef>
#include <cstdint>
#include <functional>
#include <memory>
#include <string>

namespace rmw_fleetqox_cpp
{

class SharedMemoryTransport
{
public:
  using ReceiveCallback = std::function<void(const std::string &)>;

  SharedMemoryTransport();
  ~SharedMemoryTransport();
  SharedMemoryTransport(const SharedMemoryTransport &) = delete;
  SharedMemoryTransport & operator=(const SharedMemoryTransport &) = delete;

  bool start(
    const std::string & name,
    ReceiveCallback receive_callback,
    bool unlink_if_owner);
  void stop();
  bool send(const std::string & payload);

  bool ready() const;
  const std::string & error() const;
  const std::string & name() const;
  std::uint64_t frames_sent() const;
  std::uint64_t frames_received() const;
  std::uint64_t overwritten_frames() const;
  static constexpr std::size_t max_payload_size() {return 262144;}

private:
  struct Impl;
  std::unique_ptr<Impl> impl_;
};

}  // namespace rmw_fleetqox_cpp

#endif  // RMW_FLEETQOX_CPP__SHARED_MEMORY_TRANSPORT_HPP_

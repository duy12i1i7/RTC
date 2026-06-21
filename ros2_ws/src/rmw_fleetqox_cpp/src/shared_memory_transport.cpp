#include "rmw_fleetqox_cpp/shared_memory_transport.hpp"

#include <algorithm>
#include <atomic>
#include <cerrno>
#include <chrono>
#include <cstring>
#include <string>
#include <thread>
#include <utility>
#include <vector>

#include <fcntl.h>
#include <pthread.h>
#include <sys/file.h>
#include <sys/mman.h>
#include <sys/stat.h>
#include <unistd.h>

namespace rmw_fleetqox_cpp
{
namespace
{

constexpr std::uint64_t kMagic = 0x464C54524D575348ULL;
constexpr std::uint32_t kVersion = 1;
constexpr std::size_t kSlotCount = 64;
constexpr std::size_t kPayloadSize = SharedMemoryTransport::max_payload_size();

struct SharedMemorySlot
{
  std::uint64_t sequence;
  std::uint32_t size;
  std::uint32_t reserved;
  char payload[kPayloadSize];
};

struct SharedMemoryRing
{
  std::uint64_t magic;
  std::uint32_t version;
  std::uint32_t slot_count;
  pthread_mutex_t mutex;
  pthread_cond_t condition;
  std::uint64_t write_sequence;
  SharedMemorySlot slots[kSlotCount];
};

bool valid_name(const std::string & name)
{
  return name.size() >= 2 && name.front() == '/' &&
         name.find('/', 1) == std::string::npos;
}

timespec realtime_after(std::chrono::milliseconds duration)
{
  timespec deadline{};
  clock_gettime(CLOCK_REALTIME, &deadline);
  const auto extra_ns =
    std::chrono::duration_cast<std::chrono::nanoseconds>(duration).count();
  deadline.tv_sec += static_cast<time_t>(extra_ns / 1000000000LL);
  deadline.tv_nsec += static_cast<long>(extra_ns % 1000000000LL);
  if (deadline.tv_nsec >= 1000000000L) {
    deadline.tv_sec += 1;
    deadline.tv_nsec -= 1000000000L;
  }
  return deadline;
}

}  // namespace

struct SharedMemoryTransport::Impl
{
  bool lock_ring()
  {
    const int result = pthread_mutex_lock(&ring->mutex);
#if defined(EOWNERDEAD)
    if (result == EOWNERDEAD) {
      pthread_mutex_consistent(&ring->mutex);
      return true;
    }
#endif
    return result == 0;
  }

  void receive_loop()
  {
    while (running.load(std::memory_order_acquire)) {
      std::vector<std::string> pending;
      if (!lock_ring()) {
        error = "failed to lock shared-memory receive ring";
        break;
      }
      while (running.load(std::memory_order_acquire) &&
        ring->write_sequence <= read_sequence)
      {
        const timespec deadline = realtime_after(std::chrono::milliseconds(100));
        const int wait_result = pthread_cond_timedwait(
          &ring->condition, &ring->mutex, &deadline);
        if (wait_result != 0 && wait_result != ETIMEDOUT) {
          error = "failed to wait on shared-memory receive ring";
          running.store(false, std::memory_order_release);
          break;
        }
      }

      const std::uint64_t latest = ring->write_sequence;
      std::uint64_t first = read_sequence + 1;
      if (latest >= first && latest - first + 1 > kSlotCount) {
        const std::uint64_t skipped = latest - first + 1 - kSlotCount;
        overwritten.fetch_add(skipped, std::memory_order_relaxed);
        first = latest - kSlotCount + 1;
      }
      for (std::uint64_t sequence = first; sequence <= latest; ++sequence) {
        const SharedMemorySlot & slot = ring->slots[(sequence - 1) % kSlotCount];
        if (slot.sequence != sequence || slot.size == 0 || slot.size > kPayloadSize) {
          overwritten.fetch_add(1, std::memory_order_relaxed);
          continue;
        }
        pending.emplace_back(slot.payload, slot.payload + slot.size);
      }
      read_sequence = latest;
      pthread_mutex_unlock(&ring->mutex);

      for (const std::string & payload : pending) {
        frames_received.fetch_add(1, std::memory_order_relaxed);
        if (callback) {
          callback(payload);
        }
      }
    }
  }

  int fd{-1};
  SharedMemoryRing * ring{nullptr};
  std::thread receive_thread;
  std::atomic_bool running{false};
  std::atomic<std::uint64_t> frames_sent{0};
  std::atomic<std::uint64_t> frames_received{0};
  std::atomic<std::uint64_t> overwritten{0};
  std::uint64_t read_sequence{0};
  bool is_ready{false};
  bool owner{false};
  bool unlink_if_owner{false};
  std::string name;
  std::string error;
  ReceiveCallback callback;
};

SharedMemoryTransport::SharedMemoryTransport()
: impl_(std::make_unique<Impl>())
{}

SharedMemoryTransport::~SharedMemoryTransport()
{
  stop();
}

bool SharedMemoryTransport::start(
  const std::string & name,
  ReceiveCallback receive_callback,
  bool unlink_if_owner)
{
  stop();
  impl_->error.clear();
  if (!valid_name(name)) {
    impl_->error = "shared-memory name must start with one slash and contain no other slash";
    return false;
  }
  impl_->name = name;
  impl_->unlink_if_owner = unlink_if_owner;
  impl_->callback = std::move(receive_callback);
  impl_->fd = shm_open(name.c_str(), O_CREAT | O_RDWR, 0600);
  if (impl_->fd < 0) {
    impl_->error = "failed to open POSIX shared-memory segment";
    return false;
  }
  if (flock(impl_->fd, LOCK_EX) != 0) {
    impl_->error = "failed to lock POSIX shared-memory segment";
    stop();
    return false;
  }

  struct stat status{};
  if (fstat(impl_->fd, &status) != 0) {
    impl_->error = "failed to inspect POSIX shared-memory segment";
    flock(impl_->fd, LOCK_UN);
    stop();
    return false;
  }
  impl_->owner = status.st_size != static_cast<off_t>(sizeof(SharedMemoryRing));
  if (impl_->owner && ftruncate(impl_->fd, sizeof(SharedMemoryRing)) != 0) {
    impl_->error = "failed to size POSIX shared-memory segment";
    flock(impl_->fd, LOCK_UN);
    stop();
    return false;
  }
  void * mapped = mmap(
    nullptr, sizeof(SharedMemoryRing), PROT_READ | PROT_WRITE, MAP_SHARED, impl_->fd, 0);
  if (mapped == MAP_FAILED) {
    impl_->error = "failed to map POSIX shared-memory segment";
    flock(impl_->fd, LOCK_UN);
    stop();
    return false;
  }
  impl_->ring = static_cast<SharedMemoryRing *>(mapped);
  if (!impl_->owner &&
    (impl_->ring->magic != kMagic || impl_->ring->version != kVersion ||
    impl_->ring->slot_count != kSlotCount))
  {
    impl_->owner = true;
  }
  if (impl_->owner) {
    std::memset(impl_->ring, 0, sizeof(SharedMemoryRing));
    pthread_mutexattr_t mutex_attributes;
    pthread_condattr_t condition_attributes;
    pthread_mutexattr_init(&mutex_attributes);
    pthread_condattr_init(&condition_attributes);
    pthread_mutexattr_setpshared(&mutex_attributes, PTHREAD_PROCESS_SHARED);
    pthread_condattr_setpshared(&condition_attributes, PTHREAD_PROCESS_SHARED);
#if defined(PTHREAD_MUTEX_ROBUST)
    pthread_mutexattr_setrobust(&mutex_attributes, PTHREAD_MUTEX_ROBUST);
#endif
    const int mutex_result = pthread_mutex_init(&impl_->ring->mutex, &mutex_attributes);
    const int condition_result = pthread_cond_init(
      &impl_->ring->condition, &condition_attributes);
    pthread_mutexattr_destroy(&mutex_attributes);
    pthread_condattr_destroy(&condition_attributes);
    if (mutex_result != 0 || condition_result != 0) {
      impl_->error = "failed to initialize process-shared synchronization";
      flock(impl_->fd, LOCK_UN);
      stop();
      return false;
    }
    impl_->ring->version = kVersion;
    impl_->ring->slot_count = kSlotCount;
    impl_->ring->magic = kMagic;
  }
  flock(impl_->fd, LOCK_UN);

  if (!impl_->lock_ring()) {
    impl_->error = "failed to read shared-memory sequence";
    stop();
    return false;
  }
  impl_->read_sequence = impl_->ring->write_sequence;
  pthread_mutex_unlock(&impl_->ring->mutex);
  impl_->running.store(true, std::memory_order_release);
  try {
    impl_->receive_thread = std::thread([this]() {impl_->receive_loop();});
  } catch (...) {
    impl_->running.store(false, std::memory_order_release);
    impl_->error = "failed to start shared-memory receive thread";
    stop();
    return false;
  }
  impl_->is_ready = true;
  return true;
}

void SharedMemoryTransport::stop()
{
  if (!impl_) {
    return;
  }
  impl_->running.store(false, std::memory_order_release);
  if (impl_->ring != nullptr && impl_->lock_ring()) {
    pthread_cond_broadcast(&impl_->ring->condition);
    pthread_mutex_unlock(&impl_->ring->mutex);
  }
  if (impl_->receive_thread.joinable()) {
    impl_->receive_thread.join();
  }
  if (impl_->ring != nullptr) {
    munmap(impl_->ring, sizeof(SharedMemoryRing));
    impl_->ring = nullptr;
  }
  if (impl_->fd >= 0) {
    close(impl_->fd);
    impl_->fd = -1;
  }
  if (impl_->owner && impl_->unlink_if_owner && !impl_->name.empty()) {
    shm_unlink(impl_->name.c_str());
  }
  impl_->is_ready = false;
  impl_->owner = false;
}

bool SharedMemoryTransport::send(const std::string & payload)
{
  if (!impl_->is_ready || impl_->ring == nullptr || payload.empty() ||
    payload.size() > kPayloadSize)
  {
    if (payload.size() > kPayloadSize) {
      impl_->error = "shared-memory payload exceeds slot capacity";
    }
    return false;
  }
  if (!impl_->lock_ring()) {
    impl_->error = "failed to lock shared-memory send ring";
    return false;
  }
  const std::uint64_t sequence = ++impl_->ring->write_sequence;
  SharedMemorySlot & slot = impl_->ring->slots[(sequence - 1) % kSlotCount];
  slot.sequence = 0;
  slot.size = static_cast<std::uint32_t>(payload.size());
  std::memcpy(slot.payload, payload.data(), payload.size());
  slot.sequence = sequence;
  pthread_cond_broadcast(&impl_->ring->condition);
  pthread_mutex_unlock(&impl_->ring->mutex);
  impl_->frames_sent.fetch_add(1, std::memory_order_relaxed);
  return true;
}

bool SharedMemoryTransport::ready() const {return impl_->is_ready;}
const std::string & SharedMemoryTransport::error() const {return impl_->error;}
const std::string & SharedMemoryTransport::name() const {return impl_->name;}
std::uint64_t SharedMemoryTransport::frames_sent() const {return impl_->frames_sent.load();}
std::uint64_t SharedMemoryTransport::frames_received() const {return impl_->frames_received.load();}
std::uint64_t SharedMemoryTransport::overwritten_frames() const {return impl_->overwritten.load();}

}  // namespace rmw_fleetqox_cpp

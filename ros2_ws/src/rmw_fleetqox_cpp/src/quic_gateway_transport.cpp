#include "rmw_fleetqox_cpp/quic_gateway_transport.hpp"

#include <algorithm>
#include <cerrno>
#include <cstring>
#include <cstdlib>
#include <fcntl.h>
#include <limits>
#include <sstream>
#include <sys/stat.h>
#include <sys/wait.h>
#include <unistd.h>
#include <vector>

namespace rmw_fleetqox_cpp
{
namespace
{

std::string trim_copy(const char * value)
{
  if (value == nullptr) {
    return {};
  }
  std::string text(value);
  const auto begin = text.find_first_not_of(" \t\r\n");
  if (begin == std::string::npos) {
    return {};
  }
  const auto end = text.find_last_not_of(" \t\r\n");
  return text.substr(begin, end - begin + 1);
}

std::string trim_copy(const std::string & value)
{
  return trim_copy(value.c_str());
}

bool truthy(const std::string & value)
{
  return value == "1" || value == "true" || value == "yes" || value == "quic_gateway";
}

std::size_t positive_size_from_env(const char * name, std::size_t fallback)
{
  const std::string value = trim_copy(std::getenv(name));
  if (value.empty()) {
    return fallback;
  }
  char * end = nullptr;
  errno = 0;
  const unsigned long parsed = std::strtoul(value.c_str(), &end, 10);
  if (errno != 0 || end == value.c_str() || *end != '\0' || parsed == 0) {
    return fallback;
  }
  const unsigned long capped = std::min<unsigned long>(
    parsed,
    static_cast<unsigned long>(std::numeric_limits<std::size_t>::max()));
  return static_cast<std::size_t>(capped);
}

bool write_all(int fd, const char * data, size_t size)
{
  size_t offset = 0;
  while (offset < size) {
    const ssize_t written = ::write(fd, data + offset, size - offset);
    if (written < 0) {
      if (errno == EINTR) {
        continue;
      }
      return false;
    }
    if (written == 0) {
      return false;
    }
    offset += static_cast<size_t>(written);
  }
  return true;
}

}  // namespace

QuicGatewayTransport::~QuicGatewayTransport()
{
  stop();
}

bool QuicGatewayTransport::configure_from_environment()
{
  stop();
  const std::string remote_transport = trim_copy(std::getenv("FLEETQOX_RMW_REMOTE_TRANSPORT"));
  const std::string gateway = trim_copy(std::getenv("FLEETQOX_RMW_QUIC_GATEWAY"));
  const bool explicitly_enabled = truthy(remote_transport) || !gateway.empty();
  if (!explicitly_enabled) {
    enabled_ = false;
    return true;
  }
  if (!remote_transport.empty() && remote_transport != "quic_gateway") {
    set_error("unsupported FLEETQOX_RMW_REMOTE_TRANSPORT; expected quic_gateway");
    return false;
  }
  if (gateway.empty()) {
    set_error("FLEETQOX_RMW_QUIC_GATEWAY must be host:port when quic_gateway is enabled");
    return false;
  }
  if (!parse_gateway(gateway)) {
    return false;
  }
  if (const std::string value = trim_copy(std::getenv("FLEETQOX_RMW_QUIC_CLIENT"));
    !value.empty())
  {
    client_path_ = value;
  }
  if (const std::string value = trim_copy(std::getenv("FLEETQOX_RMW_QUIC_SNI")); !value.empty()) {
    sni_ = value;
  }
  if (const std::string value = trim_copy(std::getenv("FLEETQOX_RMW_QUIC_URI")); !value.empty()) {
    uri_ = value;
  } else {
    uri_ = "https://" + sni_ + ":" + port_ + "/fleetrmw_frame";
  }
  if (const std::string value = trim_copy(std::getenv("FLEETQOX_RMW_QUIC_TIMEOUT"));
    !value.empty())
  {
    timeout_ = value;
  }
  qlog_dir_ = trim_copy(std::getenv("FLEETQOX_RMW_QUIC_QLOG_DIR"));
  log_path_ = trim_copy(std::getenv("FLEETQOX_RMW_QUIC_LOG"));
  if (const std::string value = trim_copy(std::getenv("FLEETQOX_RMW_QUIC_PAYLOAD_DIR"));
    !value.empty())
  {
    payload_dir_ = value;
  }
  async_enabled_ = truthy(trim_copy(std::getenv("FLEETQOX_RMW_QUIC_GATEWAY_ASYNC")));
  max_queue_frames_ = positive_size_from_env(
    "FLEETQOX_RMW_QUIC_GATEWAY_MAX_QUEUE_FRAMES", max_queue_frames_);
  enabled_ = true;
  if (async_enabled_) {
    stop_worker_ = false;
    try {
      worker_ = std::thread([this]() { worker_loop(); });
    } catch (...) {
      enabled_ = false;
      async_enabled_ = false;
      set_error("failed to start QUIC gateway async worker");
      return false;
    }
  }
  return true;
}

void QuicGatewayTransport::stop()
{
  {
    std::lock_guard<std::mutex> lock(queue_mutex_);
    stop_worker_ = true;
  }
  queue_cv_.notify_all();
  if (worker_.joinable()) {
    worker_.join();
  }
  {
    std::lock_guard<std::mutex> lock(queue_mutex_);
    pending_payloads_.clear();
    queue_depth_.store(0, std::memory_order_relaxed);
    stop_worker_ = false;
  }
}

bool QuicGatewayTransport::enabled() const
{
  return enabled_;
}

bool QuicGatewayTransport::async_enabled() const
{
  return enabled_ && async_enabled_;
}

bool QuicGatewayTransport::send(const std::string & payload)
{
  if (!enabled_) {
    set_error("QUIC gateway transport is not enabled");
    return false;
  }
  if (payload.empty()) {
    set_error("QUIC gateway payload is empty");
    return false;
  }
  if (async_enabled_) {
    return enqueue_payload(payload);
  }
  if (!send_blocking(payload)) {
    frames_failed_.fetch_add(1, std::memory_order_relaxed);
    return false;
  }
  return true;
}

bool QuicGatewayTransport::enqueue_payload(const std::string & payload)
{
  {
    std::lock_guard<std::mutex> lock(queue_mutex_);
    if (!worker_.joinable()) {
      set_error("QUIC gateway async worker is not running");
      frames_failed_.fetch_add(1, std::memory_order_relaxed);
      return false;
    }
    if (pending_payloads_.size() >= max_queue_frames_) {
      frames_dropped_.fetch_add(1, std::memory_order_relaxed);
      std::ostringstream error;
      error << "QUIC gateway async queue is full at " << max_queue_frames_ << " frame(s)";
      set_error(error.str());
      return false;
    }
    pending_payloads_.push_back(payload);
    frames_enqueued_.fetch_add(1, std::memory_order_relaxed);
    queue_depth_.store(pending_payloads_.size(), std::memory_order_relaxed);
  }
  queue_cv_.notify_one();
  return true;
}

bool QuicGatewayTransport::send_blocking(const std::string & payload)
{
  std::string payload_path;
  if (!write_payload_file(payload, &payload_path)) {
    return false;
  }
  const int exit_code = run_client(payload_path);
  ::unlink(payload_path.c_str());
  last_exit_code_.store(exit_code, std::memory_order_relaxed);
  if (exit_code != 0) {
    std::ostringstream error;
    error << "gtlsclient exited with code " << exit_code;
    set_error(error.str());
    return false;
  }
  frames_sent_.fetch_add(1, std::memory_order_relaxed);
  bytes_sent_.fetch_add(payload.size(), std::memory_order_relaxed);
  return true;
}

void QuicGatewayTransport::worker_loop()
{
  while (true) {
    std::string payload;
    {
      std::unique_lock<std::mutex> lock(queue_mutex_);
      queue_cv_.wait(lock, [this]() {
          return stop_worker_ || !pending_payloads_.empty();
        });
      if (stop_worker_ && pending_payloads_.empty()) {
        queue_depth_.store(0, std::memory_order_relaxed);
        return;
      }
      payload = std::move(pending_payloads_.front());
      pending_payloads_.pop_front();
      queue_depth_.store(pending_payloads_.size(), std::memory_order_relaxed);
    }
    if (!send_blocking(payload)) {
      frames_failed_.fetch_add(1, std::memory_order_relaxed);
    }
  }
}

std::uint64_t QuicGatewayTransport::frames_sent() const
{
  return frames_sent_.load(std::memory_order_relaxed);
}

std::uint64_t QuicGatewayTransport::bytes_sent() const
{
  return bytes_sent_.load(std::memory_order_relaxed);
}

std::uint64_t QuicGatewayTransport::frames_enqueued() const
{
  return frames_enqueued_.load(std::memory_order_relaxed);
}

std::uint64_t QuicGatewayTransport::frames_failed() const
{
  return frames_failed_.load(std::memory_order_relaxed);
}

std::uint64_t QuicGatewayTransport::frames_dropped() const
{
  return frames_dropped_.load(std::memory_order_relaxed);
}

std::size_t QuicGatewayTransport::queue_depth() const
{
  return queue_depth_.load(std::memory_order_relaxed);
}

std::size_t QuicGatewayTransport::max_queue_frames() const
{
  return max_queue_frames_;
}

int QuicGatewayTransport::last_exit_code() const
{
  return last_exit_code_.load(std::memory_order_relaxed);
}

std::string QuicGatewayTransport::endpoint_uri() const
{
  if (!enabled_) {
    return {};
  }
  return uri_;
}

std::string QuicGatewayTransport::error() const
{
  std::lock_guard<std::mutex> lock(mutex_);
  return error_;
}

bool QuicGatewayTransport::parse_gateway(const std::string & gateway)
{
  const auto separator = gateway.rfind(':');
  if (separator == std::string::npos || separator == 0 || separator + 1 >= gateway.size()) {
    set_error("invalid FLEETQOX_RMW_QUIC_GATEWAY endpoint; expected host:port");
    return false;
  }
  host_ = trim_copy(gateway.substr(0, separator));
  port_ = trim_copy(gateway.substr(separator + 1));
  if (host_.empty() || port_.empty()) {
    set_error("invalid FLEETQOX_RMW_QUIC_GATEWAY endpoint; host and port are required");
    return false;
  }
  char * end = nullptr;
  errno = 0;
  const long parsed_port = std::strtol(port_.c_str(), &end, 10);
  if (errno != 0 || end == port_.c_str() || *end != '\0' || parsed_port <= 0 || parsed_port > 65535) {
    set_error("invalid FLEETQOX_RMW_QUIC_GATEWAY port");
    return false;
  }
  return true;
}

bool QuicGatewayTransport::write_payload_file(const std::string & payload, std::string * path)
{
  std::string templ = payload_dir_;
  if (templ.empty() || templ.back() != '/') {
    templ += "/";
  }
  templ += "fleetrmw-quic-payload-XXXXXX";
  std::vector<char> mutable_path(templ.begin(), templ.end());
  mutable_path.push_back('\0');
  const int fd = ::mkstemp(mutable_path.data());
  if (fd < 0) {
    set_error(std::string("failed to create QUIC payload tempfile: ") + std::strerror(errno));
    return false;
  }
  const bool ok = write_all(fd, payload.data(), payload.size());
  const int close_ret = ::close(fd);
  if (!ok || close_ret != 0) {
    set_error(std::string("failed to write QUIC payload tempfile: ") + std::strerror(errno));
    ::unlink(mutable_path.data());
    return false;
  }
  *path = mutable_path.data();
  return true;
}

int QuicGatewayTransport::run_client(const std::string & payload_path)
{
  std::vector<std::string> args{
    client_path_,
    host_,
    port_,
    uri_,
    "--http-method=POST",
    "--data",
    payload_path,
    "--exit-on-all-streams-close",
    "--timeout=" + timeout_,
    "--sni=" + sni_,
    "--no-quic-dump",
    "--no-http-dump",
  };
  if (!qlog_dir_.empty()) {
    args.emplace_back("--qlog-dir");
    args.emplace_back(qlog_dir_);
  }
  std::vector<char *> argv;
  argv.reserve(args.size() + 1);
  for (std::string & arg : args) {
    argv.push_back(arg.data());
  }
  argv.push_back(nullptr);

  const pid_t child = ::fork();
  if (child < 0) {
    set_error(std::string("failed to fork gtlsclient: ") + std::strerror(errno));
    return 127;
  }
  if (child == 0) {
    const std::string redirect_path = log_path_.empty() ? "/dev/null" : log_path_;
    const int flags = log_path_.empty() ? O_WRONLY : (O_WRONLY | O_CREAT | O_APPEND);
    const int out_fd = ::open(redirect_path.c_str(), flags, S_IRUSR | S_IWUSR | S_IRGRP | S_IROTH);
    if (out_fd >= 0) {
      ::dup2(out_fd, STDOUT_FILENO);
      ::dup2(out_fd, STDERR_FILENO);
      if (out_fd > STDERR_FILENO) {
        ::close(out_fd);
      }
    }
    ::execvp(client_path_.c_str(), argv.data());
    _exit(127);
  }

  int status = 0;
  while (::waitpid(child, &status, 0) < 0) {
    if (errno == EINTR) {
      continue;
    }
    set_error(std::string("failed to wait for gtlsclient: ") + std::strerror(errno));
    return 127;
  }
  if (WIFEXITED(status)) {
    return WEXITSTATUS(status);
  }
  if (WIFSIGNALED(status)) {
    return 128 + WTERMSIG(status);
  }
  return 127;
}

void QuicGatewayTransport::set_error(const std::string & error)
{
  std::lock_guard<std::mutex> lock(mutex_);
  error_ = error;
}

}  // namespace rmw_fleetqox_cpp

#include "rmw_fleetqox_cpp/quic_gateway_transport.hpp"

#include <algorithm>
#include <cerrno>
#include <cstring>
#include <cstdlib>
#include <dirent.h>
#include <fcntl.h>
#include <fstream>
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

bool parse_timeout_ms(const std::string & value, std::uint64_t * timeout_ms)
{
  if (timeout_ms == nullptr || value.empty()) {
    return false;
  }
  std::string digits = value;
  std::uint64_t multiplier = 1000;
  if (value.size() > 2 && value.substr(value.size() - 2) == "ms") {
    digits = value.substr(0, value.size() - 2);
    multiplier = 1;
  } else if (value.back() == 's') {
    digits = value.substr(0, value.size() - 1);
    multiplier = 1000;
  }
  if (digits.empty()) {
    return false;
  }
  char * end = nullptr;
  errno = 0;
  const unsigned long long parsed = std::strtoull(digits.c_str(), &end, 10);
  if (errno != 0 || end == digits.c_str() || *end != '\0' || parsed == 0 ||
    parsed > std::numeric_limits<std::uint64_t>::max() / multiplier)
  {
    return false;
  }
  *timeout_ms = static_cast<std::uint64_t>(parsed) * multiplier;
  return true;
}

std::string request_path_from_uri(const std::string & uri)
{
  const auto scheme = uri.find("://");
  const std::size_t authority_begin = scheme == std::string::npos ? 0 : scheme + 3;
  const auto path_begin = uri.find('/', authority_begin);
  if (path_begin == std::string::npos) {
    return "/";
  }
  const auto fragment = uri.find('#', path_begin);
  return uri.substr(path_begin, fragment == std::string::npos ?
    std::string::npos : fragment - path_begin);
}

}  // namespace

QuicGatewayTransport::~QuicGatewayTransport()
{
  stop();
}

bool QuicGatewayTransport::configure_from_environment()
{
  stop();
  enabled_ = false;
  async_enabled_ = false;
  set_error({});
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
  backend_ = trim_copy(std::getenv("FLEETQOX_RMW_QUIC_BACKEND"));
  if (backend_.empty()) {
    backend_ = "subprocess";
  }
  if (backend_ != "subprocess" && backend_ != "inprocess") {
    set_error("unsupported FLEETQOX_RMW_QUIC_BACKEND; expected subprocess or inprocess");
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
  session_file_ = trim_copy(std::getenv("FLEETQOX_RMW_QUIC_SESSION_FILE"));
  transport_parameters_file_ = trim_copy(std::getenv("FLEETQOX_RMW_QUIC_TP_FILE"));
  token_file_ = trim_copy(std::getenv("FLEETQOX_RMW_QUIC_TOKEN_FILE"));
  change_local_addr_ = trim_copy(std::getenv("FLEETQOX_RMW_QUIC_CHANGE_LOCAL_ADDR"));
  key_update_ = trim_copy(std::getenv("FLEETQOX_RMW_QUIC_KEY_UPDATE"));
  ca_file_ = trim_copy(std::getenv("FLEETQOX_RMW_QUIC_CA_FILE"));
  client_certificate_file_ =
    trim_copy(std::getenv("FLEETQOX_RMW_QUIC_CLIENT_CERT_FILE"));
  client_private_key_file_ =
    trim_copy(std::getenv("FLEETQOX_RMW_QUIC_CLIENT_KEY_FILE"));
  if (client_certificate_file_.empty() != client_private_key_file_.empty()) {
    set_error(
      "FLEETQOX_RMW_QUIC_CLIENT_CERT_FILE and FLEETQOX_RMW_QUIC_CLIENT_KEY_FILE "
      "must be configured together");
    return false;
  }
  nat_rebinding_ = truthy(trim_copy(std::getenv("FLEETQOX_RMW_QUIC_NAT_REBINDING")));
  disable_early_data_ = truthy(trim_copy(std::getenv("FLEETQOX_RMW_QUIC_DISABLE_EARLY_DATA")));
  async_enabled_ = truthy(trim_copy(std::getenv("FLEETQOX_RMW_QUIC_GATEWAY_ASYNC")));
  max_queue_frames_ = positive_size_from_env(
    "FLEETQOX_RMW_QUIC_GATEWAY_MAX_QUEUE_FRAMES", max_queue_frames_);
  if (backend_ == "inprocess") {
    if (!InProcessQuicClient::compiled()) {
      set_error("in-process QUIC backend requested but ngtcp2/GnuTLS support was not compiled");
      return false;
    }
    if (!session_file_.empty() || !transport_parameters_file_.empty() || !token_file_.empty() ||
      !change_local_addr_.empty() || !key_update_.empty() || nat_rebinding_ || disable_early_data_)
    {
      set_error(
        "session-file, token, migration, key-update, and early-data controls are only "
        "available on the subprocess QUIC backend");
      return false;
    }
    std::uint64_t timeout_ms = 0;
    if (!parse_timeout_ms(timeout_, &timeout_ms)) {
      set_error("invalid FLEETQOX_RMW_QUIC_TIMEOUT for in-process backend; use N, Ns, or Nms");
      return false;
    }
    InProcessQuicClientConfig config;
    config.host = host_;
    config.port = port_;
    config.sni = sni_;
    config.request_path = request_path_from_uri(uri_);
    config.ca_file = ca_file_;
    config.client_certificate_file = client_certificate_file_;
    config.client_private_key_file = client_private_key_file_;
    config.qlog_dir = qlog_dir_;
    config.operation_timeout_ms = timeout_ms;
    config.concurrent_pair_wait_ms = static_cast<std::uint64_t>(positive_size_from_env(
      "FLEETQOX_RMW_QUIC_CONCURRENT_PAIR_WAIT_MS", 0));
    inprocess_client_ = std::make_unique<InProcessQuicClient>();
    if (!inprocess_client_->configure(config)) {
      set_error(inprocess_client_->error());
      inprocess_client_.reset();
      return false;
    }
  } else {
    if (!client_certificate_file_.empty()) {
      set_error("QUIC client-certificate authentication requires the in-process backend");
      return false;
    }
    inprocess_client_.reset();
  }
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
  if (inprocess_client_) {
    inprocess_client_->stop();
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

bool QuicGatewayTransport::receive(std::string * payload)
{
  if (!enabled_) {
    set_error("QUIC gateway transport is not enabled");
    return false;
  }
  if (async_enabled_ && backend_ != "inprocess") {
    set_error("QUIC gateway receive is not supported in async worker mode");
    return false;
  }
  if (payload == nullptr) {
    set_error("QUIC gateway receive payload output is null");
    return false;
  }
  if (!receive_blocking(payload)) {
    frames_failed_.fetch_add(1, std::memory_order_relaxed);
    return false;
  }
  return true;
}

bool QuicGatewayTransport::send_and_receive(
  const std::string & send_payload, std::string * received_payload)
{
  if (!enabled_) {
    set_error("QUIC gateway transport is not enabled");
    return false;
  }
  if (backend_ != "inprocess" || !inprocess_client_) {
    set_error("concurrent QUIC send/receive requires the in-process backend");
    return false;
  }
  if (async_enabled_) {
    set_error("concurrent QUIC send/receive is not available with the publish queue worker");
    return false;
  }
  if (send_payload.empty() || received_payload == nullptr) {
    set_error("concurrent QUIC send payload and receive output must be non-empty/non-null");
    return false;
  }
  if (!inprocess_client_->send_and_receive_frame(send_payload, received_payload)) {
    last_exit_code_.store(1, std::memory_order_relaxed);
    frames_failed_.fetch_add(1, std::memory_order_relaxed);
    set_error(inprocess_client_->error());
    return false;
  }
  last_exit_code_.store(0, std::memory_order_relaxed);
  frames_sent_.fetch_add(1, std::memory_order_relaxed);
  bytes_sent_.fetch_add(send_payload.size(), std::memory_order_relaxed);
  frames_received_.fetch_add(1, std::memory_order_relaxed);
  bytes_received_.fetch_add(received_payload->size(), std::memory_order_relaxed);
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
  if (backend_ == "inprocess") {
    if (!inprocess_client_) {
      set_error("in-process QUIC client is not configured");
      return false;
    }
    if (!inprocess_client_->send_frame(payload)) {
      last_exit_code_.store(1, std::memory_order_relaxed);
      set_error(inprocess_client_->error());
      return false;
    }
    last_exit_code_.store(0, std::memory_order_relaxed);
    frames_sent_.fetch_add(1, std::memory_order_relaxed);
    bytes_sent_.fetch_add(payload.size(), std::memory_order_relaxed);
    return true;
  }
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

std::uint64_t QuicGatewayTransport::frames_received() const
{
  return frames_received_.load(std::memory_order_relaxed);
}

std::uint64_t QuicGatewayTransport::bytes_received() const
{
  return bytes_received_.load(std::memory_order_relaxed);
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

std::string QuicGatewayTransport::backend_name() const
{
  return backend_;
}

bool QuicGatewayTransport::subprocess_backed() const
{
  return backend_ == "subprocess";
}

std::uint64_t QuicGatewayTransport::connections_created() const
{
  return inprocess_client_ ?
    inprocess_client_->connections_created() : frames_sent() + frames_received();
}

std::uint64_t QuicGatewayTransport::handshakes_completed() const
{
  return inprocess_client_ ?
    inprocess_client_->handshakes_completed() : frames_sent() + frames_received();
}

std::uint64_t QuicGatewayTransport::streams_opened() const
{
  return inprocess_client_ ? inprocess_client_->streams_opened() : frames_sent() + frames_received();
}

std::uint64_t QuicGatewayTransport::connection_reuse_count() const
{
  return inprocess_client_ ? inprocess_client_->connection_reuse_count() : 0;
}

std::uint64_t QuicGatewayTransport::packets_sent() const
{
  return inprocess_client_ ? inprocess_client_->packets_sent() : 0;
}

std::uint64_t QuicGatewayTransport::packets_received() const
{
  return inprocess_client_ ? inprocess_client_->packets_received() : 0;
}

std::uint64_t QuicGatewayTransport::reconnects() const
{
  return inprocess_client_ ? inprocess_client_->reconnects() : 0;
}

std::uint64_t QuicGatewayTransport::concurrent_stream_pairs() const
{
  return inprocess_client_ ? inprocess_client_->concurrent_stream_pairs() : 0;
}

std::uint64_t QuicGatewayTransport::max_concurrent_request_streams() const
{
  return inprocess_client_ ? inprocess_client_->max_concurrent_request_streams() : 0;
}

std::uint64_t QuicGatewayTransport::concurrent_api_operation_pairs() const
{
  return inprocess_client_ ? inprocess_client_->concurrent_api_operation_pairs() : 0;
}

std::uint64_t QuicGatewayTransport::max_concurrent_api_calls() const
{
  return inprocess_client_ ? inprocess_client_->max_concurrent_api_calls() : 0;
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

bool QuicGatewayTransport::receive_blocking(std::string * payload)
{
  if (payload == nullptr) {
    set_error("QUIC gateway receive payload output is null");
    return false;
  }
  if (backend_ == "inprocess") {
    if (!inprocess_client_) {
      set_error("in-process QUIC client is not configured");
      return false;
    }
    if (!inprocess_client_->receive_frame(payload)) {
      last_exit_code_.store(1, std::memory_order_relaxed);
      set_error(inprocess_client_->error());
      return false;
    }
    last_exit_code_.store(0, std::memory_order_relaxed);
    frames_received_.fetch_add(1, std::memory_order_relaxed);
    bytes_received_.fetch_add(payload->size(), std::memory_order_relaxed);
    return true;
  }
  std::string download_dir;
  if (!create_download_dir(&download_dir)) {
    return false;
  }
  const int exit_code = run_download_client(download_dir);
  last_exit_code_.store(exit_code, std::memory_order_relaxed);
  if (exit_code != 0) {
    std::ostringstream error;
    error << "gtlsclient download exited with code " << exit_code;
    set_error(error.str());
    remove_download_dir(download_dir);
    return false;
  }
  const bool read_ok = read_downloaded_payload(download_dir, payload);
  remove_download_dir(download_dir);
  if (!read_ok) {
    return false;
  }
  if (payload->empty()) {
    set_error("QUIC gateway downloaded payload is empty");
    return false;
  }
  frames_received_.fetch_add(1, std::memory_order_relaxed);
  bytes_received_.fetch_add(payload->size(), std::memory_order_relaxed);
  return true;
}

bool QuicGatewayTransport::create_download_dir(std::string * path)
{
  if (path == nullptr) {
    set_error("QUIC gateway download dir output is null");
    return false;
  }
  std::string templ = payload_dir_;
  if (templ.empty() || templ.back() != '/') {
    templ += "/";
  }
  templ += "fleetrmw-quic-download-XXXXXX";
  std::vector<char> mutable_path(templ.begin(), templ.end());
  mutable_path.push_back('\0');
  char * created = ::mkdtemp(mutable_path.data());
  if (created == nullptr) {
    set_error(std::string("failed to create QUIC download directory: ") + std::strerror(errno));
    return false;
  }
  *path = created;
  return true;
}

bool QuicGatewayTransport::read_downloaded_payload(const std::string & path, std::string * payload)
{
  if (payload == nullptr) {
    set_error("QUIC gateway download payload output is null");
    return false;
  }
  DIR * dir = ::opendir(path.c_str());
  if (dir == nullptr) {
    set_error(std::string("failed to open QUIC download directory: ") + std::strerror(errno));
    return false;
  }
  std::string selected;
  struct dirent * entry = nullptr;
  while ((entry = ::readdir(dir)) != nullptr) {
    const std::string name(entry->d_name);
    if (name == "." || name == "..") {
      continue;
    }
    const std::string candidate = path + "/" + name;
    struct stat st {};
    if (::stat(candidate.c_str(), &st) != 0 || !S_ISREG(st.st_mode)) {
      continue;
    }
    selected = candidate;
    break;
  }
  ::closedir(dir);
  if (selected.empty()) {
    set_error("QUIC gateway download directory did not contain a payload file");
    return false;
  }
  std::ifstream input(selected, std::ios::binary);
  if (!input) {
    set_error("failed to open QUIC downloaded payload");
    return false;
  }
  std::ostringstream buffer;
  buffer << input.rdbuf();
  *payload = buffer.str();
  return true;
}

void QuicGatewayTransport::remove_download_dir(const std::string & path)
{
  DIR * dir = ::opendir(path.c_str());
  if (dir != nullptr) {
    struct dirent * entry = nullptr;
    while ((entry = ::readdir(dir)) != nullptr) {
      const std::string name(entry->d_name);
      if (name == "." || name == "..") {
        continue;
      }
      const std::string candidate = path + "/" + name;
      ::unlink(candidate.c_str());
    }
    ::closedir(dir);
  }
  ::rmdir(path.c_str());
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
  if (!session_file_.empty()) {
    args.emplace_back("--session-file=" + session_file_);
  }
  if (!transport_parameters_file_.empty()) {
    args.emplace_back("--tp-file=" + transport_parameters_file_);
  }
  if (!token_file_.empty()) {
    args.emplace_back("--token-file=" + token_file_);
  }
  if (!change_local_addr_.empty()) {
    args.emplace_back("--change-local-addr=" + change_local_addr_);
  }
  if (!key_update_.empty()) {
    args.emplace_back("--key-update=" + key_update_);
  }
  if (nat_rebinding_) {
    args.emplace_back("--nat-rebinding");
  }
  if (disable_early_data_) {
    args.emplace_back("--disable-early-data");
  }
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

int QuicGatewayTransport::run_download_client(const std::string & download_dir)
{
  std::vector<std::string> args{
    client_path_,
    host_,
    port_,
    uri_,
    "--download",
    download_dir,
    "--exit-on-all-streams-close",
    "--timeout=" + timeout_,
    "--sni=" + sni_,
    "--no-quic-dump",
    "--no-http-dump",
  };
  if (!session_file_.empty()) {
    args.emplace_back("--session-file=" + session_file_);
  }
  if (!transport_parameters_file_.empty()) {
    args.emplace_back("--tp-file=" + transport_parameters_file_);
  }
  if (!token_file_.empty()) {
    args.emplace_back("--token-file=" + token_file_);
  }
  if (!change_local_addr_.empty()) {
    args.emplace_back("--change-local-addr=" + change_local_addr_);
  }
  if (!key_update_.empty()) {
    args.emplace_back("--key-update=" + key_update_);
  }
  if (nat_rebinding_) {
    args.emplace_back("--nat-rebinding");
  }
  if (disable_early_data_) {
    args.emplace_back("--disable-early-data");
  }
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
    set_error(std::string("failed to fork gtlsclient download: ") + std::strerror(errno));
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
    set_error(std::string("failed to wait for gtlsclient download: ") + std::strerror(errno));
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

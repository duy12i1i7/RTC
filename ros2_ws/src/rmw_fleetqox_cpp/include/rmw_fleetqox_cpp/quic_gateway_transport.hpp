#ifndef RMW_FLEETQOX_CPP__QUIC_GATEWAY_TRANSPORT_HPP_
#define RMW_FLEETQOX_CPP__QUIC_GATEWAY_TRANSPORT_HPP_

#include <atomic>
#include <condition_variable>
#include <cstddef>
#include <cstdint>
#include <deque>
#include <mutex>
#include <string>
#include <thread>

namespace rmw_fleetqox_cpp
{

class QuicGatewayTransport
{
public:
  ~QuicGatewayTransport();

  bool configure_from_environment();
  void stop();
  bool enabled() const;
  bool async_enabled() const;

  bool send(const std::string & payload);

  std::uint64_t frames_sent() const;
  std::uint64_t bytes_sent() const;
  std::uint64_t frames_enqueued() const;
  std::uint64_t frames_failed() const;
  std::uint64_t frames_dropped() const;
  std::size_t queue_depth() const;
  std::size_t max_queue_frames() const;
  int last_exit_code() const;
  std::string endpoint_uri() const;
  std::string error() const;

private:
  bool parse_gateway(const std::string & gateway);
  bool enqueue_payload(const std::string & payload);
  bool send_blocking(const std::string & payload);
  void worker_loop();
  bool write_payload_file(const std::string & payload, std::string * path);
  int run_client(const std::string & payload_path);
  void set_error(const std::string & error);

  bool enabled_{false};
  bool async_enabled_{false};
  std::string client_path_{"/usr/bin/gtlsclient"};
  std::string host_;
  std::string port_;
  std::string uri_;
  std::string sni_{"localhost"};
  std::string timeout_{"8s"};
  std::string qlog_dir_;
  std::string log_path_;
  std::string payload_dir_{"/tmp"};
  std::size_t max_queue_frames_{64};
  std::atomic<std::uint64_t> frames_sent_{0};
  std::atomic<std::uint64_t> bytes_sent_{0};
  std::atomic<std::uint64_t> frames_enqueued_{0};
  std::atomic<std::uint64_t> frames_failed_{0};
  std::atomic<std::uint64_t> frames_dropped_{0};
  std::atomic<std::size_t> queue_depth_{0};
  std::atomic<int> last_exit_code_{0};
  mutable std::mutex mutex_;
  std::string error_;
  mutable std::mutex queue_mutex_;
  std::condition_variable queue_cv_;
  std::deque<std::string> pending_payloads_;
  bool stop_worker_{false};
  std::thread worker_;
};

}  // namespace rmw_fleetqox_cpp

#endif  // RMW_FLEETQOX_CPP__QUIC_GATEWAY_TRANSPORT_HPP_

#ifndef RMW_FLEETQOX_CPP__QUIC_GATEWAY_TRANSPORT_HPP_
#define RMW_FLEETQOX_CPP__QUIC_GATEWAY_TRANSPORT_HPP_

#include <atomic>
#include <condition_variable>
#include <cstddef>
#include <cstdint>
#include <deque>
#include <mutex>
#include <memory>
#include <string>
#include <thread>

#include "rmw_fleetqox_cpp/inprocess_quic_client.hpp"

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
  bool receive(std::string * payload);
  bool send_and_receive(
    const std::string & send_payload, std::string * received_payload);

  std::uint64_t frames_sent() const;
  std::uint64_t bytes_sent() const;
  std::uint64_t frames_received() const;
  std::uint64_t bytes_received() const;
  std::uint64_t frames_enqueued() const;
  std::uint64_t frames_failed() const;
  std::uint64_t frames_dropped() const;
  std::size_t queue_depth() const;
  std::size_t max_queue_frames() const;
  int last_exit_code() const;
  std::string endpoint_uri() const;
  std::string backend_name() const;
  bool subprocess_backed() const;
  std::uint64_t connections_created() const;
  std::uint64_t handshakes_completed() const;
  std::uint64_t streams_opened() const;
  std::uint64_t connection_reuse_count() const;
  std::uint64_t packets_sent() const;
  std::uint64_t packets_received() const;
  std::uint64_t reconnects() const;
  std::uint64_t concurrent_stream_pairs() const;
  std::uint64_t max_concurrent_request_streams() const;
  std::uint64_t concurrent_api_operation_pairs() const;
  std::uint64_t max_concurrent_api_calls() const;
  std::string error() const;

private:
  bool parse_gateway(const std::string & gateway);
  bool enqueue_payload(const std::string & payload);
  bool send_blocking(const std::string & payload);
  bool receive_blocking(std::string * payload);
  void worker_loop();
  bool write_payload_file(const std::string & payload, std::string * path);
  bool create_download_dir(std::string * path);
  bool read_downloaded_payload(const std::string & path, std::string * payload);
  void remove_download_dir(const std::string & path);
  int run_client(const std::string & payload_path);
  int run_download_client(const std::string & download_dir);
  void set_error(const std::string & error);

  bool enabled_{false};
  bool async_enabled_{false};
  std::string backend_{"subprocess"};
  std::string client_path_{"/usr/bin/gtlsclient"};
  std::string host_;
  std::string port_;
  std::string uri_;
  std::string sni_{"localhost"};
  std::string timeout_{"8s"};
  std::string qlog_dir_;
  std::string log_path_;
  std::string payload_dir_{"/tmp"};
  std::string session_file_;
  std::string transport_parameters_file_;
  std::string token_file_;
  std::string change_local_addr_;
  std::string key_update_;
  std::string ca_file_;
  std::string client_certificate_file_;
  std::string client_private_key_file_;
  bool nat_rebinding_{false};
  bool disable_early_data_{false};
  std::size_t max_queue_frames_{64};
  std::atomic<std::uint64_t> frames_sent_{0};
  std::atomic<std::uint64_t> bytes_sent_{0};
  std::atomic<std::uint64_t> frames_received_{0};
  std::atomic<std::uint64_t> bytes_received_{0};
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
  std::unique_ptr<InProcessQuicClient> inprocess_client_;
};

}  // namespace rmw_fleetqox_cpp

#endif  // RMW_FLEETQOX_CPP__QUIC_GATEWAY_TRANSPORT_HPP_

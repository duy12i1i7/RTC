#ifndef RMW_FLEETQOX_CPP__INPROCESS_QUIC_CLIENT_HPP_
#define RMW_FLEETQOX_CPP__INPROCESS_QUIC_CLIENT_HPP_

#include <atomic>
#include <condition_variable>
#include <cstdint>
#include <memory>
#include <mutex>
#include <string>

namespace rmw_fleetqox_cpp
{

struct InProcessQuicClientConfig
{
  std::string host;
  std::string port;
  std::string sni{"localhost"};
  std::string request_path{"/fleetrmw_frame"};
  std::string ca_file;
  std::string client_certificate_file;
  std::string client_private_key_file;
  std::string qlog_dir;
  std::uint64_t operation_timeout_ms{8000};
  // When non-zero, independent send_frame()/receive_frame() callers may
  // rendezvous for this long and share one concurrent POST/GET stream drive.
  std::uint64_t concurrent_pair_wait_ms{0};
};

// A persistent QUIC v1 client using reliable bidirectional streams.  The
// implementation is compiled only when ngtcp2 and its GnuTLS crypto adapter
// are available; the API remains present so non-QUIC developer builds can
// report a precise capability error instead of failing to link.
class InProcessQuicClient
{
public:
  InProcessQuicClient();
  ~InProcessQuicClient();

  InProcessQuicClient(const InProcessQuicClient &) = delete;
  InProcessQuicClient & operator=(const InProcessQuicClient &) = delete;

  static bool compiled();

  bool configure(const InProcessQuicClientConfig & config);
  bool send_frame(const std::string & payload);
  bool receive_frame(std::string * payload);
  bool send_and_receive_frame(
    const std::string & send_payload, std::string * received_payload);
  void stop();

  std::string error() const;
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

private:
  class Impl;
  struct PendingOperation;

  bool exchange_coordinated(
    bool send_operation, const std::string & payload, std::string * received_payload);

  std::unique_ptr<Impl> impl_;
  mutable std::mutex impl_mutex_;
  mutable std::mutex rendezvous_mutex_;
  std::condition_variable rendezvous_cv_;
  std::shared_ptr<PendingOperation> pending_send_;
  std::shared_ptr<PendingOperation> pending_receive_;
  bool stopping_{false};
  std::uint64_t concurrent_pair_wait_ms_{0};
  std::atomic<std::uint64_t> concurrent_api_operation_pairs_{0};
  std::atomic<std::uint64_t> max_concurrent_api_calls_{0};
};

}  // namespace rmw_fleetqox_cpp

#endif  // RMW_FLEETQOX_CPP__INPROCESS_QUIC_CLIENT_HPP_

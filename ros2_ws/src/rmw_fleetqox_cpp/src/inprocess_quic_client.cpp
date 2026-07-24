/*
 * The QUIC event-loop and crypto callback wiring in this file is derived from
 * ngtcp2's examples/gtlssimpleclient.c (ngtcp2 v0.12.1).
 *
 * Copyright (c) 2021-2022 ngtcp2 contributors
 *
 * Permission is hereby granted, free of charge, to any person obtaining a
 * copy of this software and associated documentation files (the "Software"),
 * to deal in the Software without restriction, including without limitation
 * the rights to use, copy, modify, merge, publish, distribute, sublicense,
 * and/or sell copies of the Software, and to permit persons to whom the
 * Software is furnished to do so, subject to the following conditions:
 *
 * The above copyright notice and this permission notice shall be included in
 * all copies or substantial portions of the Software.
 *
 * THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
 * IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
 * FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
 * AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
 * LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING
 * FROM, OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS
 * IN THE SOFTWARE.
 */

#include "rmw_fleetqox_cpp/inprocess_quic_client.hpp"

#include <algorithm>
#include <array>
#include <chrono>
#include <cstring>
#include <filesystem>
#include <functional>
#include <limits>
#include <map>
#include <sstream>
#include <utility>

#ifdef FLEETQOX_HAS_INPROCESS_QUIC

#include <arpa/inet.h>
#include <cerrno>
#include <fcntl.h>
#include <netdb.h>
#include <poll.h>
#include <sys/socket.h>
#include <sys/stat.h>
#include <unistd.h>

#include <gnutls/crypto.h>
#include <gnutls/gnutls.h>
#include <ngtcp2/ngtcp2.h>
#include <ngtcp2/ngtcp2_crypto.h>
#include <ngtcp2/ngtcp2_crypto_gnutls.h>
#include <nghttp3/nghttp3.h>

#endif

namespace rmw_fleetqox_cpp
{

#ifdef FLEETQOX_HAS_INPROCESS_QUIC

namespace
{

ngtcp2_tstamp timestamp_ns()
{
  return static_cast<ngtcp2_tstamp>(
    std::chrono::duration_cast<std::chrono::nanoseconds>(
      std::chrono::steady_clock::now().time_since_epoch()).count());
}

bool is_numeric_host_family(const std::string & host, int family)
{
  std::uint8_t storage[sizeof(in6_addr)]{};
  return ::inet_pton(family, host.c_str(), storage) == 1;
}

bool is_numeric_host(const std::string & host)
{
  return is_numeric_host_family(host, AF_INET) || is_numeric_host_family(host, AF_INET6);
}

const char kTlsPriority[] =
  "NORMAL:-VERS-ALL:+VERS-TLS1.3:-CIPHER-ALL:+AES-128-GCM:+AES-256-GCM:"
  "+CHACHA20-POLY1305:+AES-128-CCM:-GROUP-ALL:+GROUP-SECP256R1:+GROUP-X25519:"
  "+GROUP-SECP384R1:+GROUP-SECP521R1:%DISABLE_TLS13_COMPAT_MODE";

const char kAlpn[] = "h3";

}  // namespace

class InProcessQuicClient::Impl
{
public:
  struct StreamState
  {
    std::string method;
    std::string scheme{"https"};
    std::string authority;
    std::string path;
    std::string content_length;
    std::string body;
    std::string response;
    bool body_provided{false};
    bool http_closed{false};
    bool quic_closed{false};
    int response_status{0};
    std::uint64_t app_error_code{0};
  };

  ~Impl()
  {
    close_connection(true);
    if (gnutls_initialized_) {
      ::gnutls_global_deinit();
    }
  }

  bool configure(const InProcessQuicClientConfig & config)
  {
    close_connection(true);
    error_.clear();
    if (config.host.empty() || config.port.empty() || config.sni.empty()) {
      return fail("in-process QUIC host, port, and SNI must be non-empty");
    }
    if (config.client_certificate_file.empty() != config.client_private_key_file.empty()) {
      return fail(
        "in-process QUIC client certificate and private key must be configured together");
    }
    if (config.request_path.empty() || config.request_path.front() != '/' ||
      config.request_path.find_first_of("\r\n") != std::string::npos)
    {
      return fail("in-process QUIC request path must be an absolute path without CR/LF");
    }
    if (config.operation_timeout_ms == 0) {
      return fail("in-process QUIC operation timeout must be positive");
    }
    if (config.concurrent_pair_wait_ms > config.operation_timeout_ms) {
      return fail("concurrent QUIC pair wait must not exceed the operation timeout");
    }
    if (!config.qlog_dir.empty()) {
      std::error_code error_code;
      const std::filesystem::path qlog_dir(config.qlog_dir);
      std::filesystem::create_directories(qlog_dir, error_code);
      if (error_code || !std::filesystem::is_directory(qlog_dir, error_code)) {
        return fail(
          std::string("failed to prepare in-process QUIC qlog directory: ") +
          (error_code ? error_code.message() : "path is not a directory"));
      }
    }
    config_ = config;
    configured_ = true;
    return true;
  }

  bool send_frame(const std::string & payload)
  {
    if (payload.empty()) {
      return fail("in-process QUIC frame payload is empty");
    }
    std::string response;
    return exchange("POST", payload, &response);
  }

  bool receive_frame(std::string * payload)
  {
    if (payload == nullptr) {
      return fail("in-process QUIC receive output is null");
    }
    return exchange("GET", {}, payload);
  }

  bool send_and_receive_frame(
    const std::string & send_payload, std::string * received_payload)
  {
    if (send_payload.empty()) {
      return fail("in-process QUIC concurrent send payload is empty");
    }
    if (received_payload == nullptr) {
      return fail("in-process QUIC concurrent receive output is null");
    }
    if (!ensure_connected()) {
      return false;
    }
    cleanup_closed_streams();
    const auto deadline = std::chrono::steady_clock::now() +
      std::chrono::milliseconds(config_.operation_timeout_ms);

    std::int64_t post_stream_id = -1;
    std::int64_t get_stream_id = -1;
    StreamState * post_stream = nullptr;
    StreamState * get_stream = nullptr;
    if (!open_request_stream(
        "POST", send_payload, deadline, &post_stream_id, &post_stream) ||
      !open_request_stream(
        "GET", {}, deadline, &get_stream_id, &get_stream))
    {
      close_connection(false);
      return false;
    }
    ++concurrent_stream_pairs_;
    max_concurrent_request_streams_ = std::max<std::uint64_t>(
      max_concurrent_request_streams_, 2);
    if (!drive_until(
        [post_stream, get_stream]() {
          return post_stream->http_closed && get_stream->http_closed;
        },
        deadline, "concurrent HTTP/3 POST/GET stream responses"))
    {
      close_connection(false);
      return false;
    }
    if (!stream_completed_without_error(post_stream_id, post_stream) ||
      !stream_completed_without_error(get_stream_id, get_stream))
    {
      close_connection(false);
      return false;
    }
    *received_payload = get_stream->response;
    if (post_stream->quic_closed) {
      streams_.erase(post_stream_id);
    }
    if (get_stream->quic_closed) {
      streams_.erase(get_stream_id);
    }
    error_.clear();
    return true;
  }

  void stop()
  {
    close_connection(true);
  }

  std::string error() const {return error_;}
  std::uint64_t connections_created() const {return connections_created_;}
  std::uint64_t handshakes_completed() const {return handshakes_completed_;}
  std::uint64_t streams_opened() const {return streams_opened_;}
  std::uint64_t connection_reuse_count() const {return connection_reuse_count_;}
  std::uint64_t packets_sent() const {return packets_sent_;}
  std::uint64_t packets_received() const {return packets_received_;}
  std::uint64_t reconnects() const {return reconnects_;}
  std::uint64_t concurrent_stream_pairs() const {return concurrent_stream_pairs_;}
  std::uint64_t max_concurrent_request_streams() const
  {
    return max_concurrent_request_streams_;
  }

private:
  static ngtcp2_conn * get_conn(ngtcp2_crypto_conn_ref * conn_ref)
  {
    auto * self = static_cast<Impl *>(conn_ref->user_data);
    return self->conn_;
  }

  static void rand_cb(
    std::uint8_t * dest, std::size_t destlen, const ngtcp2_rand_ctx * rand_ctx)
  {
    (void)rand_ctx;
    (void)::gnutls_rnd(GNUTLS_RND_RANDOM, dest, destlen);
  }

  static void qlog_write_cb(
    void * user_data, std::uint32_t flags, const void * data, std::size_t datalen)
  {
    auto * self = static_cast<Impl *>(user_data);
    if (self != nullptr) {
      self->write_qlog(flags, data, datalen);
    }
  }

  bool open_qlog(const ngtcp2_cid & dcid)
  {
    close_qlog();
    static constexpr char hex[] = "0123456789abcdef";
    std::string dcid_hex;
    dcid_hex.reserve(dcid.datalen * 2);
    for (std::size_t index = 0; index < dcid.datalen; ++index) {
      const std::uint8_t value = dcid.data[index];
      dcid_hex.push_back(hex[value >> 4]);
      dcid_hex.push_back(hex[value & 0x0f]);
    }
    const std::filesystem::path path =
      std::filesystem::path(config_.qlog_dir) /
      ("client-" + std::to_string(static_cast<long long>(::getpid())) + "-" +
      dcid_hex + ".sqlog");
    qlog_fd_ = ::open(
      path.c_str(), O_WRONLY | O_CREAT | O_EXCL | O_CLOEXEC, S_IRUSR | S_IWUSR);
    if (qlog_fd_ < 0) {
      return fail(
        std::string("failed to create in-process QUIC qlog ") + path.string() +
        ": " + std::strerror(errno));
    }
    qlog_path_ = path.string();
    qlog_write_failed_ = false;
    qlog_write_error_.clear();
    return true;
  }

  void write_qlog(std::uint32_t flags, const void * data, std::size_t datalen)
  {
    (void)flags;
    if (qlog_fd_ < 0 || qlog_write_failed_ || datalen == 0) {
      return;
    }
    const auto * bytes = static_cast<const std::uint8_t *>(data);
    std::size_t offset = 0;
    while (offset < datalen) {
      const ssize_t written = ::write(qlog_fd_, bytes + offset, datalen - offset);
      if (written < 0 && errno == EINTR) {
        continue;
      }
      if (written <= 0) {
        qlog_write_failed_ = true;
        qlog_write_error_ =
          std::string("failed to write in-process QUIC qlog ") + qlog_path_ +
          ": " + (written < 0 ? std::strerror(errno) : "zero-byte write");
        return;
      }
      offset += static_cast<std::size_t>(written);
    }
  }

  bool qlog_write_ok()
  {
    return !qlog_write_failed_ || fail(qlog_write_error_);
  }

  void close_qlog()
  {
    if (qlog_fd_ >= 0) {
      (void)::close(qlog_fd_);
      qlog_fd_ = -1;
    }
  }

  static int get_new_connection_id_cb(
    ngtcp2_conn * conn, ngtcp2_cid * cid, std::uint8_t * token,
    std::size_t cidlen, void * user_data)
  {
    (void)conn;
    (void)user_data;
    if (::gnutls_rnd(GNUTLS_RND_RANDOM, cid->data, cidlen) != 0) {
      return NGTCP2_ERR_CALLBACK_FAILURE;
    }
    cid->datalen = cidlen;
    if (::gnutls_rnd(
        GNUTLS_RND_RANDOM, token, NGTCP2_STATELESS_RESET_TOKENLEN) != 0)
    {
      return NGTCP2_ERR_CALLBACK_FAILURE;
    }
    return 0;
  }

  static int handshake_completed_cb(ngtcp2_conn * conn, void * user_data)
  {
    (void)conn;
    auto * self = static_cast<Impl *>(user_data);
    if (!self->handshake_complete_) {
      self->handshake_complete_ = true;
      ++self->handshakes_completed_;
    }
    return 0;
  }

  static int verify_peer_certificate_cb(gnutls_session_t session)
  {
    auto * conn_ref = static_cast<ngtcp2_crypto_conn_ref *>(::gnutls_session_get_ptr(session));
    auto * self = conn_ref == nullptr ? nullptr : static_cast<Impl *>(conn_ref->user_data);
    if (self == nullptr) {
      return GNUTLS_E_CERTIFICATE_ERROR;
    }
    unsigned int status = 0;
    const int rv = ::gnutls_certificate_verify_peers3(
      session, self->verify_name_.c_str(), &status);
    self->verification_status_ = status;
    if (rv < 0) {
      self->error_ = std::string("GnuTLS peer verification failed: ") + ::gnutls_strerror(rv);
      return rv;
    }
    if (status != 0) {
      gnutls_datum_t details{};
      std::ostringstream message;
      message << "QUIC peer certificate rejected for " << self->verify_name_ <<
        " with " << self->custom_trust_anchors_ << " custom trust anchor(s)";
      if (::gnutls_certificate_verification_status_print(
          status, GNUTLS_CRT_X509, &details, 0) == GNUTLS_E_SUCCESS)
      {
        message << ": " <<
          std::string(reinterpret_cast<char *>(details.data), details.size);
        ::gnutls_free(details.data);
      }
      self->error_ = message.str();
      return GNUTLS_E_CERTIFICATE_ERROR;
    }
    self->peer_certificate_verified_ = true;
    return 0;
  }

  static int recv_stream_data_cb(
    ngtcp2_conn * conn, std::uint32_t flags, std::int64_t stream_id,
    std::uint64_t offset, const std::uint8_t * data, std::size_t datalen,
    void * user_data, void * stream_user_data)
  {
    (void)offset;
    (void)stream_user_data;
    auto * self = static_cast<Impl *>(user_data);
    if (self->http3_conn_ == nullptr) {
      self->error_ = "received application stream data before HTTP/3 setup";
      return NGTCP2_ERR_CALLBACK_FAILURE;
    }
    const nghttp3_ssize consumed = ::nghttp3_conn_read_stream(
      self->http3_conn_, stream_id, data, datalen,
      (flags & NGTCP2_STREAM_DATA_FLAG_FIN) != 0);
    if (consumed < 0) {
      self->error_ = std::string("nghttp3 stream read failed: ") +
        ::nghttp3_strerror(consumed);
      return NGTCP2_ERR_CALLBACK_FAILURE;
    }
    ::ngtcp2_conn_extend_max_stream_offset(conn, stream_id, consumed);
    ::ngtcp2_conn_extend_max_offset(conn, consumed);
    return 0;
  }

  static int acked_stream_data_offset_cb(
    ngtcp2_conn * conn, std::int64_t stream_id, std::uint64_t offset,
    std::uint64_t datalen, void * user_data, void * stream_user_data)
  {
    (void)conn;
    (void)offset;
    (void)stream_user_data;
    auto * self = static_cast<Impl *>(user_data);
    if (self->http3_conn_ == nullptr) {
      return 0;
    }
    const int rv = ::nghttp3_conn_add_ack_offset(self->http3_conn_, stream_id, datalen);
    if (rv != 0) {
      self->error_ = std::string("nghttp3 ACK offset failed: ") + ::nghttp3_strerror(rv);
      return NGTCP2_ERR_CALLBACK_FAILURE;
    }
    return 0;
  }

  static int stream_close_cb(
    ngtcp2_conn * conn, std::uint32_t flags, std::int64_t stream_id,
    std::uint64_t app_error_code, void * user_data, void * stream_user_data)
  {
    (void)flags;
    auto * self = static_cast<Impl *>(user_data);
    auto * stream = static_cast<StreamState *>(stream_user_data);
    if (stream != nullptr) {
      stream->quic_closed = true;
      stream->app_error_code = app_error_code;
    }
    if (self->http3_conn_ != nullptr) {
      const std::uint64_t h3_error = app_error_code == 0 ? NGHTTP3_H3_NO_ERROR : app_error_code;
      const int rv = ::nghttp3_conn_close_stream(self->http3_conn_, stream_id, h3_error);
      if (rv != 0 && rv != NGHTTP3_ERR_STREAM_NOT_FOUND) {
        self->error_ = std::string("nghttp3 stream close failed: ") + ::nghttp3_strerror(rv);
        return NGTCP2_ERR_CALLBACK_FAILURE;
      }
      if (rv == NGHTTP3_ERR_STREAM_NOT_FOUND && !::ngtcp2_is_bidi_stream(stream_id) &&
        !::ngtcp2_conn_is_local_stream(conn, stream_id))
      {
        ::ngtcp2_conn_extend_max_streams_uni(conn, 1);
      }
    }
    return 0;
  }

  static int stream_reset_cb(
    ngtcp2_conn * conn, std::int64_t stream_id, std::uint64_t final_size,
    std::uint64_t app_error_code, void * user_data, void * stream_user_data)
  {
    (void)conn;
    (void)final_size;
    (void)app_error_code;
    (void)stream_user_data;
    auto * self = static_cast<Impl *>(user_data);
    if (self->http3_conn_ == nullptr) {
      return 0;
    }
    const int rv = ::nghttp3_conn_shutdown_stream_read(self->http3_conn_, stream_id);
    return rv == 0 ? 0 : NGTCP2_ERR_CALLBACK_FAILURE;
  }

  static int stream_stop_sending_cb(
    ngtcp2_conn * conn, std::int64_t stream_id, std::uint64_t app_error_code,
    void * user_data, void * stream_user_data)
  {
    (void)conn;
    (void)app_error_code;
    (void)stream_user_data;
    auto * self = static_cast<Impl *>(user_data);
    if (self->http3_conn_ == nullptr) {
      return 0;
    }
    const int rv = ::nghttp3_conn_shutdown_stream_read(self->http3_conn_, stream_id);
    return rv == 0 ? 0 : NGTCP2_ERR_CALLBACK_FAILURE;
  }

  static int extend_max_stream_data_cb(
    ngtcp2_conn * conn, std::int64_t stream_id, std::uint64_t max_data,
    void * user_data, void * stream_user_data)
  {
    (void)conn;
    (void)max_data;
    (void)stream_user_data;
    auto * self = static_cast<Impl *>(user_data);
    if (self->http3_conn_ == nullptr) {
      return 0;
    }
    const int rv = ::nghttp3_conn_unblock_stream(self->http3_conn_, stream_id);
    return rv == 0 ? 0 : NGTCP2_ERR_CALLBACK_FAILURE;
  }

  static int recv_rx_key_cb(
    ngtcp2_conn * conn, ngtcp2_crypto_level level, void * user_data)
  {
    (void)conn;
    if (level != NGTCP2_CRYPTO_LEVEL_APPLICATION) {
      return 0;
    }
    auto * self = static_cast<Impl *>(user_data);
    return self->setup_http3() ? 0 : NGTCP2_ERR_CALLBACK_FAILURE;
  }

  static nghttp3_ssize http_read_data_cb(
    nghttp3_conn * conn, std::int64_t stream_id, nghttp3_vec * vectors,
    std::size_t vector_count, std::uint32_t * flags, void * user_data,
    void * stream_user_data)
  {
    (void)conn;
    (void)stream_id;
    (void)user_data;
    auto * stream = static_cast<StreamState *>(stream_user_data);
    if (stream == nullptr || vector_count == 0 || stream->body_provided) {
      *flags |= NGHTTP3_DATA_FLAG_EOF;
      return 0;
    }
    vectors[0].base = reinterpret_cast<std::uint8_t *>(stream->body.data());
    vectors[0].len = stream->body.size();
    stream->body_provided = true;
    *flags |= NGHTTP3_DATA_FLAG_EOF;
    return 1;
  }

  static int http_recv_data_cb(
    nghttp3_conn * conn, std::int64_t stream_id, const std::uint8_t * data,
    std::size_t datalen, void * user_data, void * stream_user_data)
  {
    (void)conn;
    auto * self = static_cast<Impl *>(user_data);
    auto * stream = static_cast<StreamState *>(stream_user_data);
    if (stream != nullptr) {
      stream->response.append(reinterpret_cast<const char *>(data), datalen);
    }
    ::ngtcp2_conn_extend_max_stream_offset(self->conn_, stream_id, datalen);
    ::ngtcp2_conn_extend_max_offset(self->conn_, datalen);
    return 0;
  }

  static int http_recv_header_cb(
    nghttp3_conn * conn, std::int64_t stream_id, std::int32_t token,
    nghttp3_rcbuf * name, nghttp3_rcbuf * value, std::uint8_t flags,
    void * user_data, void * stream_user_data)
  {
    (void)conn;
    (void)stream_id;
    (void)token;
    (void)flags;
    (void)user_data;
    auto * stream = static_cast<StreamState *>(stream_user_data);
    if (stream == nullptr || name == nullptr || value == nullptr) {
      return 0;
    }
    const nghttp3_vec name_buffer = ::nghttp3_rcbuf_get_buf(name);
    if (name_buffer.len != 7 ||
      std::memcmp(name_buffer.base, ":status", name_buffer.len) != 0)
    {
      return 0;
    }
    const nghttp3_vec value_buffer = ::nghttp3_rcbuf_get_buf(value);
    if (value_buffer.len != 3) {
      return NGHTTP3_ERR_CALLBACK_FAILURE;
    }
    int status = 0;
    for (size_t index = 0; index < value_buffer.len; ++index) {
      const std::uint8_t digit = value_buffer.base[index];
      if (digit < '0' || digit > '9') {
        return NGHTTP3_ERR_CALLBACK_FAILURE;
      }
      status = status * 10 + static_cast<int>(digit - '0');
    }
    stream->response_status = status;
    return 0;
  }

  static int http_deferred_consume_cb(
    nghttp3_conn * conn, std::int64_t stream_id, std::size_t consumed,
    void * user_data, void * stream_user_data)
  {
    (void)conn;
    (void)stream_user_data;
    auto * self = static_cast<Impl *>(user_data);
    ::ngtcp2_conn_extend_max_stream_offset(self->conn_, stream_id, consumed);
    ::ngtcp2_conn_extend_max_offset(self->conn_, consumed);
    return 0;
  }

  static int http_stream_close_cb(
    nghttp3_conn * conn, std::int64_t stream_id, std::uint64_t app_error_code,
    void * user_data, void * stream_user_data)
  {
    (void)conn;
    (void)stream_id;
    (void)user_data;
    auto * stream = static_cast<StreamState *>(stream_user_data);
    if (stream != nullptr) {
      stream->http_closed = true;
      stream->app_error_code = app_error_code;
    }
    return 0;
  }

  static int http_stop_sending_cb(
    nghttp3_conn * conn, std::int64_t stream_id, std::uint64_t app_error_code,
    void * user_data, void * stream_user_data)
  {
    (void)conn;
    (void)stream_user_data;
    auto * self = static_cast<Impl *>(user_data);
    const int rv = ::ngtcp2_conn_shutdown_stream_read(self->conn_, stream_id, app_error_code);
    return rv == 0 ? 0 : NGHTTP3_ERR_CALLBACK_FAILURE;
  }

  static int http_reset_stream_cb(
    nghttp3_conn * conn, std::int64_t stream_id, std::uint64_t app_error_code,
    void * user_data, void * stream_user_data)
  {
    (void)conn;
    (void)stream_user_data;
    auto * self = static_cast<Impl *>(user_data);
    const int rv = ::ngtcp2_conn_shutdown_stream_write(self->conn_, stream_id, app_error_code);
    return rv == 0 ? 0 : NGHTTP3_ERR_CALLBACK_FAILURE;
  }

  static nghttp3_nv make_header(const char * name, const std::string & value)
  {
    nghttp3_nv header{};
    header.name = reinterpret_cast<std::uint8_t *>(const_cast<char *>(name));
    header.value = reinterpret_cast<std::uint8_t *>(const_cast<char *>(value.data()));
    header.namelen = std::strlen(name);
    header.valuelen = value.size();
    header.flags = NGHTTP3_NV_FLAG_NONE;
    return header;
  }

  bool setup_http3()
  {
    if (http3_conn_ != nullptr) {
      return true;
    }
    if (conn_ == nullptr || ::ngtcp2_conn_get_max_local_streams_uni(conn_) < 3) {
      return fail("QUIC peer did not grant the three unidirectional streams required by HTTP/3");
    }
    nghttp3_callbacks callbacks{};
    callbacks.stream_close = http_stream_close_cb;
    callbacks.recv_data = http_recv_data_cb;
    callbacks.recv_header = http_recv_header_cb;
    callbacks.deferred_consume = http_deferred_consume_cb;
    callbacks.stop_sending = http_stop_sending_cb;
    callbacks.reset_stream = http_reset_stream_cb;
    nghttp3_settings settings{};
    ::nghttp3_settings_default(&settings);
    settings.qpack_max_dtable_capacity = 4096;
    settings.qpack_blocked_streams = 100;
    const int create_rv = ::nghttp3_conn_client_new(
      &http3_conn_, &callbacks, &settings, ::nghttp3_mem_default(), this);
    if (create_rv != 0) {
      http3_conn_ = nullptr;
      return fail(std::string("nghttp3 client creation failed: ") +
        ::nghttp3_strerror(create_rv));
    }

    std::int64_t control_stream_id = -1;
    std::int64_t qpack_encoder_stream_id = -1;
    std::int64_t qpack_decoder_stream_id = -1;
    int rv = ::ngtcp2_conn_open_uni_stream(conn_, &control_stream_id, nullptr);
    if (rv == 0) {
      rv = ::nghttp3_conn_bind_control_stream(http3_conn_, control_stream_id);
    }
    if (rv == 0) {
      rv = ::ngtcp2_conn_open_uni_stream(conn_, &qpack_encoder_stream_id, nullptr);
    }
    if (rv == 0) {
      rv = ::ngtcp2_conn_open_uni_stream(conn_, &qpack_decoder_stream_id, nullptr);
    }
    if (rv == 0) {
      rv = ::nghttp3_conn_bind_qpack_streams(
        http3_conn_, qpack_encoder_stream_id, qpack_decoder_stream_id);
    }
    if (rv != 0) {
      return fail("failed to bind HTTP/3 control or QPACK streams");
    }
    return true;
  }

  bool submit_http_request(std::int64_t stream_id, StreamState * stream)
  {
    if (http3_conn_ == nullptr || stream == nullptr) {
      return fail("HTTP/3 client is not ready to submit a request");
    }
    std::array<nghttp3_nv, 6> headers{};
    std::size_t header_count = 0;
    headers[header_count++] = make_header(":method", stream->method);
    headers[header_count++] = make_header(":scheme", stream->scheme);
    headers[header_count++] = make_header(":authority", stream->authority);
    headers[header_count++] = make_header(":path", stream->path);
    const std::string content_type = "application/octet-stream";
    if (stream->method == "POST") {
      headers[header_count++] = make_header("content-type", content_type);
      headers[header_count++] = make_header("content-length", stream->content_length);
    }
    nghttp3_data_reader reader{};
    reader.read_data = http_read_data_cb;
    const int rv = ::nghttp3_conn_submit_request(
      http3_conn_, stream_id, headers.data(), header_count,
      stream->method == "POST" ? &reader : nullptr, stream);
    if (rv != 0) {
      return fail(std::string("HTTP/3 request submission failed: ") +
        ::nghttp3_strerror(rv));
    }
    return true;
  }

  bool fail(const std::string & message)
  {
    error_ = message;
    return false;
  }

  bool create_socket()
  {
    addrinfo hints{};
    hints.ai_family = AF_UNSPEC;
    hints.ai_socktype = SOCK_DGRAM;
    addrinfo * result = nullptr;
    const int gai = ::getaddrinfo(config_.host.c_str(), config_.port.c_str(), &hints, &result);
    if (gai != 0) {
      return fail(std::string("QUIC getaddrinfo failed: ") + ::gai_strerror(gai));
    }

    int selected_fd = -1;
    for (addrinfo * candidate = result; candidate != nullptr; candidate = candidate->ai_next) {
      selected_fd = ::socket(candidate->ai_family, candidate->ai_socktype, candidate->ai_protocol);
      if (selected_fd < 0) {
        continue;
      }
      if (::connect(selected_fd, candidate->ai_addr, candidate->ai_addrlen) == 0) {
        std::memset(&remote_addr_, 0, sizeof(remote_addr_));
        std::memcpy(&remote_addr_, candidate->ai_addr, candidate->ai_addrlen);
        remote_addrlen_ = static_cast<socklen_t>(candidate->ai_addrlen);
        break;
      }
      ::close(selected_fd);
      selected_fd = -1;
    }
    ::freeaddrinfo(result);
    if (selected_fd < 0) {
      return fail(std::string("QUIC UDP connect failed: ") + std::strerror(errno));
    }
    fd_ = selected_fd;
    local_addrlen_ = sizeof(local_addr_);
    if (::getsockname(fd_, reinterpret_cast<sockaddr *>(&local_addr_), &local_addrlen_) != 0) {
      const std::string message = std::string("QUIC getsockname failed: ") + std::strerror(errno);
      ::close(fd_);
      fd_ = -1;
      return fail(message);
    }
    const int flags = ::fcntl(fd_, F_GETFL, 0);
    if (flags < 0 || ::fcntl(fd_, F_SETFL, flags | O_NONBLOCK) != 0) {
      const std::string message =
        std::string("failed to make QUIC socket non-blocking: ") + std::strerror(errno);
      ::close(fd_);
      fd_ = -1;
      return fail(message);
    }
    return true;
  }

  bool initialize_tls()
  {
    if (!gnutls_initialized_) {
      const int rv = ::gnutls_global_init();
      if (rv != GNUTLS_E_SUCCESS) {
        return fail(std::string("gnutls_global_init failed: ") + ::gnutls_strerror(rv));
      }
      gnutls_initialized_ = true;
    }

    int rv = ::gnutls_certificate_allocate_credentials(&credentials_);
    if (rv != GNUTLS_E_SUCCESS) {
      return fail(std::string("GnuTLS credential allocation failed: ") + ::gnutls_strerror(rv));
    }
    (void)::gnutls_certificate_set_x509_system_trust(credentials_);
    custom_trust_anchors_ = 0;
    if (!config_.ca_file.empty()) {
      rv = ::gnutls_certificate_set_x509_trust_file(
        credentials_, config_.ca_file.c_str(), GNUTLS_X509_FMT_PEM);
      if (rv < 0) {
        return fail(std::string("failed to load QUIC CA file: ") + ::gnutls_strerror(rv));
      }
      custom_trust_anchors_ = rv;
    }
    if (!config_.client_certificate_file.empty()) {
      rv = ::gnutls_certificate_set_x509_key_file(
        credentials_,
        config_.client_certificate_file.c_str(),
        config_.client_private_key_file.c_str(),
        GNUTLS_X509_FMT_PEM);
      if (rv < 0) {
        return fail(
          std::string("failed to load QUIC client certificate/private key: ") +
          ::gnutls_strerror(rv));
      }
    }
    ::gnutls_certificate_set_verify_function(credentials_, verify_peer_certificate_cb);

    rv = ::gnutls_init(
      &tls_session_, GNUTLS_CLIENT | GNUTLS_ENABLE_EARLY_DATA | GNUTLS_NO_END_OF_EARLY_DATA);
    if (rv != GNUTLS_E_SUCCESS) {
      return fail(std::string("gnutls_init failed: ") + ::gnutls_strerror(rv));
    }
    if (::ngtcp2_crypto_gnutls_configure_client_session(tls_session_) != 0) {
      return fail("ngtcp2 failed to configure the GnuTLS client session");
    }
    rv = ::gnutls_priority_set_direct(tls_session_, kTlsPriority, nullptr);
    if (rv != GNUTLS_E_SUCCESS) {
      return fail(std::string("GnuTLS priority configuration failed: ") + ::gnutls_strerror(rv));
    }
    rv = ::gnutls_credentials_set(tls_session_, GNUTLS_CRD_CERTIFICATE, credentials_);
    if (rv != GNUTLS_E_SUCCESS) {
      return fail(std::string("GnuTLS credentials setup failed: ") + ::gnutls_strerror(rv));
    }
    const gnutls_datum_t alpn = {
      reinterpret_cast<unsigned char *>(const_cast<char *>(kAlpn)), sizeof(kAlpn) - 1};
    rv = ::gnutls_alpn_set_protocols(tls_session_, &alpn, 1, GNUTLS_ALPN_MANDATORY);
    if (rv != GNUTLS_E_SUCCESS) {
      return fail(std::string("GnuTLS ALPN setup failed: ") + ::gnutls_strerror(rv));
    }
    verify_name_ = is_numeric_host(config_.host) ? config_.sni : config_.host;
    rv = ::gnutls_server_name_set(
      tls_session_, GNUTLS_NAME_DNS, config_.sni.data(), config_.sni.size());
    if (rv != GNUTLS_E_SUCCESS) {
      return fail(std::string("GnuTLS SNI setup failed: ") + ::gnutls_strerror(rv));
    }
    conn_ref_.get_conn = get_conn;
    conn_ref_.user_data = this;
    ::gnutls_session_set_ptr(tls_session_, &conn_ref_);
    return true;
  }

  bool initialize_quic()
  {
    ngtcp2_cid dcid{};
    ngtcp2_cid scid{};
    dcid.datalen = NGTCP2_MIN_INITIAL_DCIDLEN;
    scid.datalen = 8;
    if (::gnutls_rnd(GNUTLS_RND_RANDOM, dcid.data, dcid.datalen) != 0 ||
      ::gnutls_rnd(GNUTLS_RND_RANDOM, scid.data, scid.datalen) != 0)
    {
      return fail("GnuTLS random generation failed for QUIC connection IDs");
    }

    ngtcp2_callbacks callbacks{};
    callbacks.client_initial = ngtcp2_crypto_client_initial_cb;
    callbacks.recv_crypto_data = ngtcp2_crypto_recv_crypto_data_cb;
    callbacks.handshake_completed = handshake_completed_cb;
    callbacks.encrypt = ngtcp2_crypto_encrypt_cb;
    callbacks.decrypt = ngtcp2_crypto_decrypt_cb;
    callbacks.hp_mask = ngtcp2_crypto_hp_mask_cb;
    callbacks.recv_stream_data = recv_stream_data_cb;
    callbacks.acked_stream_data_offset = acked_stream_data_offset_cb;
    callbacks.stream_close = stream_close_cb;
    callbacks.recv_retry = ngtcp2_crypto_recv_retry_cb;
    callbacks.rand = rand_cb;
    callbacks.get_new_connection_id = get_new_connection_id_cb;
    callbacks.update_key = ngtcp2_crypto_update_key_cb;
    callbacks.stream_reset = stream_reset_cb;
    callbacks.extend_max_stream_data = extend_max_stream_data_cb;
    callbacks.delete_crypto_aead_ctx = ngtcp2_crypto_delete_crypto_aead_ctx_cb;
    callbacks.delete_crypto_cipher_ctx = ngtcp2_crypto_delete_crypto_cipher_ctx_cb;
    callbacks.get_path_challenge_data = ngtcp2_crypto_get_path_challenge_data_cb;
    callbacks.stream_stop_sending = stream_stop_sending_cb;
    callbacks.version_negotiation = ngtcp2_crypto_version_negotiation_cb;
    callbacks.recv_rx_key = recv_rx_key_cb;

    ngtcp2_settings settings{};
    ::ngtcp2_settings_default(&settings);
    settings.initial_ts = timestamp_ns();
    if (!config_.qlog_dir.empty()) {
      if (!open_qlog(dcid)) {
        return false;
      }
      settings.qlog.write = qlog_write_cb;
    }

    ngtcp2_transport_params params{};
    ::ngtcp2_transport_params_default(&params);
    params.initial_max_streams_bidi = 16;
    params.initial_max_streams_uni = 3;
    params.initial_max_stream_data_bidi_local = 4 * 1024 * 1024;
    params.initial_max_stream_data_bidi_remote = 4 * 1024 * 1024;
    params.initial_max_stream_data_uni = 4 * 1024 * 1024;
    params.initial_max_data = 16 * 1024 * 1024;

    ngtcp2_path path = {
      {reinterpret_cast<sockaddr *>(&local_addr_), local_addrlen_},
      {reinterpret_cast<sockaddr *>(&remote_addr_), remote_addrlen_},
      nullptr};
    const int rv = ::ngtcp2_conn_client_new(
      &conn_, &dcid, &scid, &path, NGTCP2_PROTO_VER_V1,
      &callbacks, &settings, &params, nullptr, this);
    if (rv != 0) {
      return fail(std::string("ngtcp2_conn_client_new failed: ") + ::ngtcp2_strerror(rv));
    }
    if (!qlog_write_ok()) {
      return false;
    }
    ::ngtcp2_conn_set_tls_native_handle(conn_, tls_session_);
    ::ngtcp2_connection_close_error_default(&last_error_);
    ++connections_created_;
    if (connections_created_ > 1) {
      ++reconnects_;
    }
    return true;
  }

  bool ensure_connected()
  {
    if (!configured_) {
      return fail("in-process QUIC client is not configured");
    }
    if (conn_ != nullptr && handshake_complete_ && peer_certificate_verified_ &&
      http3_conn_ != nullptr &&
      !::ngtcp2_conn_is_in_closing_period(conn_) &&
      !::ngtcp2_conn_is_in_draining_period(conn_))
    {
      return true;
    }
    close_connection(false);
    error_.clear();
    if (!create_socket() || !initialize_tls() || !initialize_quic()) {
      close_connection(false);
      return false;
    }
    const auto deadline = std::chrono::steady_clock::now() +
      std::chrono::milliseconds(config_.operation_timeout_ms);
    if (!drive_until(
        [this]() {
          return handshake_complete_ && peer_certificate_verified_ && http3_conn_ != nullptr;
        },
        deadline, "QUIC/TLS/HTTP3 handshake"))
    {
      close_connection(false);
      return false;
    }
    return true;
  }

  bool exchange(
    const std::string & method, const std::string & body, std::string * response)
  {
    if (response == nullptr) {
      return fail("in-process QUIC exchange response output is null");
    }
    if (!ensure_connected()) {
      return false;
    }
    cleanup_closed_streams();
    const auto deadline = std::chrono::steady_clock::now() +
      std::chrono::milliseconds(config_.operation_timeout_ms);

    std::int64_t stream_id = -1;
    StreamState * stream_ptr = nullptr;
    if (!open_request_stream(method, body, deadline, &stream_id, &stream_ptr)) {
      close_connection(false);
      return false;
    }

    if (!drive_until(
        [stream_ptr]() {return stream_ptr->http_closed;},
        deadline, "HTTP/3 bidirectional stream response"))
    {
      close_connection(false);
      return false;
    }
    if (!stream_completed_without_error(stream_id, stream_ptr)) {
      close_connection(false);
      return false;
    }
    *response = stream_ptr->response;
    if (stream_ptr->quic_closed) {
      streams_.erase(stream_id);
    }
    error_.clear();
    return true;
  }

  bool open_request_stream(
    const std::string & method, const std::string & body,
    const std::chrono::steady_clock::time_point & deadline,
    std::int64_t * stream_id, StreamState ** stream_output)
  {
    if (stream_id == nullptr || stream_output == nullptr) {
      return fail("QUIC request stream outputs are null");
    }
    auto stream = std::make_unique<StreamState>();
    stream->method = method;
    stream->authority = config_.sni + ":" + config_.port;
    stream->path = config_.request_path;
    stream->body = body;
    stream->content_length = std::to_string(body.size());
    StreamState * stream_ptr = stream.get();
    while (true) {
      const int rv = ::ngtcp2_conn_open_bidi_stream(conn_, stream_id, stream_ptr);
      if (rv == 0) {
        break;
      }
      if (rv != NGTCP2_ERR_STREAM_ID_BLOCKED) {
        return fail(
          std::string("failed to open QUIC bidirectional stream: ") +
          ::ngtcp2_strerror(rv));
      }
      if (!drive_until(
          [this]() {return ::ngtcp2_conn_get_streams_bidi_left(conn_) > 0;},
          deadline, "QUIC stream credit"))
      {
        return false;
      }
    }
    streams_.emplace(*stream_id, std::move(stream));
    if (!submit_http_request(*stream_id, stream_ptr)) {
      streams_.erase(*stream_id);
      return false;
    }
    ++streams_opened_;
    if (streams_on_current_connection_ > 0) {
      ++connection_reuse_count_;
    }
    ++streams_on_current_connection_;
    *stream_output = stream_ptr;
    return true;
  }

  bool stream_completed_without_error(
    std::int64_t stream_id, const StreamState * stream)
  {
    if (stream == nullptr) {
      return fail("HTTP/3 stream state is null");
    }
    if (stream->app_error_code == NGHTTP3_H3_NO_ERROR) {
      if (stream->response_status >= 200 && stream->response_status < 300) {
        return true;
      }
      std::ostringstream message;
      message << "HTTP/3 response status " << stream->response_status <<
        " for stream " << stream_id;
      return fail(message.str());
    }
    std::ostringstream message;
    message << "HTTP/3 stream " << stream_id <<
      " closed with application error " << stream->app_error_code;
    return fail(message.str());
  }

  template<typename PredicateT>
  bool drive_until(
    PredicateT predicate, const std::chrono::steady_clock::time_point & deadline,
    const char * operation)
  {
    while (!predicate()) {
      if (std::chrono::steady_clock::now() >= deadline) {
        return fail(std::string(operation) + " timed out");
      }
      if (!write_packets()) {
        return false;
      }
      if (predicate()) {
        break;
      }

      const ngtcp2_tstamp now = timestamp_ns();
      const ngtcp2_tstamp expiry = ::ngtcp2_conn_get_expiry(conn_);
      const auto remaining_ms = std::max<std::int64_t>(
        1, std::chrono::duration_cast<std::chrono::milliseconds>(
          deadline - std::chrono::steady_clock::now()).count());
      std::int64_t expiry_ms = remaining_ms;
      if (expiry != std::numeric_limits<ngtcp2_tstamp>::max()) {
        expiry_ms = expiry <= now ? 0 : static_cast<std::int64_t>(
          std::min<ngtcp2_tstamp>(
            (expiry - now + NGTCP2_MILLISECONDS - 1) / NGTCP2_MILLISECONDS,
            static_cast<ngtcp2_tstamp>(remaining_ms)));
      }
      pollfd descriptor{fd_, POLLIN, 0};
      int poll_result = 0;
      do {
        poll_result = ::poll(&descriptor, 1, static_cast<int>(expiry_ms));
      } while (poll_result < 0 && errno == EINTR);
      if (poll_result < 0) {
        return fail(std::string("QUIC socket poll failed: ") + std::strerror(errno));
      }
      if (poll_result > 0 && (descriptor.revents & POLLIN) != 0) {
        if (!read_packets()) {
          return false;
        }
      }
      if ((descriptor.revents & (POLLERR | POLLHUP | POLLNVAL)) != 0) {
        return fail("QUIC socket reported an error or hangup");
      }
      const ngtcp2_tstamp after_poll = timestamp_ns();
      if (after_poll >= ::ngtcp2_conn_get_expiry(conn_)) {
        const int rv = ::ngtcp2_conn_handle_expiry(conn_, after_poll);
        if (rv != 0) {
          return fail(std::string("ngtcp2 expiry handling failed: ") + ::ngtcp2_strerror(rv));
        }
        if (!qlog_write_ok()) {
          return false;
        }
      }
    }
    return true;
  }

  bool read_packets()
  {
    std::uint8_t buffer[65536];
    while (true) {
      const ssize_t nread = ::recv(fd_, buffer, sizeof(buffer), MSG_DONTWAIT);
      if (nread < 0) {
        if (errno == EAGAIN || errno == EWOULDBLOCK) {
          return true;
        }
        if (errno == EINTR) {
          continue;
        }
        return fail(std::string("QUIC recv failed: ") + std::strerror(errno));
      }
      if (nread == 0) {
        return true;
      }
      ++packets_received_;
      ngtcp2_path path = {
        {reinterpret_cast<sockaddr *>(&local_addr_), local_addrlen_},
        {reinterpret_cast<sockaddr *>(&remote_addr_), remote_addrlen_},
        nullptr};
      ngtcp2_pkt_info packet_info{};
      const int rv = ::ngtcp2_conn_read_pkt(
        conn_, &path, &packet_info, buffer, static_cast<std::size_t>(nread), timestamp_ns());
      if (rv != 0) {
        std::ostringstream message;
        message << "ngtcp2 packet read failed: " << ::ngtcp2_strerror(rv);
        if (rv == NGTCP2_ERR_CRYPTO) {
          message << " (TLS alert " <<
            static_cast<unsigned int>(::ngtcp2_conn_get_tls_alert(conn_));
          const unsigned int verification_status = verification_status_ != 0 ?
            verification_status_ : ::gnutls_session_get_verify_cert_status(tls_session_);
          if (verification_status != 0) {
            gnutls_datum_t details{};
            if (::gnutls_certificate_verification_status_print(
                verification_status, GNUTLS_CRT_X509, &details, 0) == GNUTLS_E_SUCCESS)
            {
              message << "; certificate verification: " <<
                std::string(reinterpret_cast<char *>(details.data), details.size);
              ::gnutls_free(details.data);
            } else {
              message << "; certificate verification status=" << verification_status;
            }
          }
          message << "; verify_name=" << verify_name_ <<
            "; custom_trust_anchors=" << custom_trust_anchors_;
          message << ")";
        }
        return fail(message.str());
      }
      if (!qlog_write_ok()) {
        return false;
      }
    }
  }

  bool write_packets()
  {
    std::uint8_t buffer[1280];
    ngtcp2_path_storage path_storage{};
    ::ngtcp2_path_storage_zero(&path_storage);
    for (int iteration = 0; iteration < 128; ++iteration) {
      std::array<nghttp3_vec, 16> http_vectors{};
      std::int64_t stream_id = -1;
      int fin = 0;
      nghttp3_ssize vector_count = 0;
      if (http3_conn_ != nullptr && ::ngtcp2_conn_get_max_data_left(conn_) > 0) {
        vector_count = ::nghttp3_conn_writev_stream(
          http3_conn_, &stream_id, &fin, http_vectors.data(), http_vectors.size());
        if (vector_count < 0) {
          return fail(std::string("nghttp3 stream write failed: ") +
            ::nghttp3_strerror(vector_count));
        }
      }

      std::uint32_t write_flags = NGTCP2_WRITE_STREAM_FLAG_MORE;
      if (fin != 0) {
        write_flags |= NGTCP2_WRITE_STREAM_FLAG_FIN;
      }
      ngtcp2_pkt_info packet_info{};
      ngtcp2_ssize accepted = -1;
      const ngtcp2_ssize nwrite = ::ngtcp2_conn_writev_stream(
        conn_, &path_storage.path, &packet_info, buffer, sizeof(buffer), &accepted,
        write_flags, stream_id,
        reinterpret_cast<const ngtcp2_vec *>(http_vectors.data()),
        static_cast<std::size_t>(vector_count), timestamp_ns());
      if (!qlog_write_ok()) {
        return false;
      }
      if (nwrite == NGTCP2_ERR_STREAM_DATA_BLOCKED) {
        if (http3_conn_ != nullptr) {
          (void)::nghttp3_conn_block_stream(http3_conn_, stream_id);
        }
        continue;
      }
      if (nwrite == NGTCP2_ERR_STREAM_SHUT_WR) {
        if (http3_conn_ != nullptr) {
          (void)::nghttp3_conn_shutdown_stream_write(http3_conn_, stream_id);
        }
        continue;
      }
      if (nwrite == NGTCP2_ERR_WRITE_MORE) {
        if (accepted >= 0 && http3_conn_ != nullptr) {
          const int rv = ::nghttp3_conn_add_write_offset(http3_conn_, stream_id, accepted);
          if (rv != 0) {
            return fail(std::string("nghttp3 write offset failed: ") +
              ::nghttp3_strerror(rv));
          }
        }
        continue;
      }
      if (nwrite < 0) {
        return fail(std::string("ngtcp2 packet write failed: ") +
          ::ngtcp2_strerror(static_cast<int>(nwrite)));
      }
      if (accepted >= 0 && http3_conn_ != nullptr) {
        const int rv = ::nghttp3_conn_add_write_offset(http3_conn_, stream_id, accepted);
        if (rv != 0) {
          return fail(std::string("nghttp3 write offset failed: ") +
            ::nghttp3_strerror(rv));
        }
      }
      if (nwrite == 0) {
        return true;
      }
      ssize_t sent = -1;
      do {
        sent = ::send(fd_, buffer, static_cast<std::size_t>(nwrite), 0);
      } while (sent < 0 && errno == EINTR);
      if (sent < 0 || sent != nwrite) {
        return fail(std::string("QUIC UDP send failed: ") + std::strerror(errno));
      }
      ++packets_sent_;
    }
    return true;
  }

  void cleanup_closed_streams()
  {
    for (auto it = streams_.begin(); it != streams_.end(); ) {
      if (it->second->http_closed && it->second->quic_closed) {
        it = streams_.erase(it);
      } else {
        ++it;
      }
    }
  }

  void close_connection(bool send_close)
  {
    if (conn_ != nullptr && send_close && fd_ >= 0 &&
      !::ngtcp2_conn_is_in_closing_period(conn_) &&
      !::ngtcp2_conn_is_in_draining_period(conn_))
    {
      ngtcp2_path_storage path_storage{};
      ::ngtcp2_path_storage_zero(&path_storage);
      ngtcp2_pkt_info packet_info{};
      std::uint8_t buffer[1280];
      const ngtcp2_ssize nwrite = ::ngtcp2_conn_write_connection_close(
        conn_, &path_storage.path, &packet_info, buffer, sizeof(buffer),
        &last_error_, timestamp_ns());
      if (nwrite > 0 && ::send(fd_, buffer, static_cast<std::size_t>(nwrite), 0) == nwrite) {
        ++packets_sent_;
      }
    }
    if (http3_conn_ != nullptr) {
      ::nghttp3_conn_del(http3_conn_);
      http3_conn_ = nullptr;
    }
    if (conn_ != nullptr) {
      ::ngtcp2_conn_del(conn_);
      conn_ = nullptr;
    }
    close_qlog();
    if (tls_session_ != nullptr) {
      ::gnutls_deinit(tls_session_);
      tls_session_ = nullptr;
    }
    if (credentials_ != nullptr) {
      ::gnutls_certificate_free_credentials(credentials_);
      credentials_ = nullptr;
    }
    if (fd_ >= 0) {
      ::close(fd_);
      fd_ = -1;
    }
    streams_.clear();
    handshake_complete_ = false;
    streams_on_current_connection_ = 0;
    peer_certificate_verified_ = false;
    verification_status_ = 0;
  }

  InProcessQuicClientConfig config_;
  bool configured_{false};
  bool gnutls_initialized_{false};
  bool handshake_complete_{false};
  bool peer_certificate_verified_{false};
  int custom_trust_anchors_{0};
  unsigned int verification_status_{0};
  std::string verify_name_;
  int fd_{-1};
  sockaddr_storage local_addr_{};
  socklen_t local_addrlen_{0};
  sockaddr_storage remote_addr_{};
  socklen_t remote_addrlen_{0};
  gnutls_certificate_credentials_t credentials_{nullptr};
  gnutls_session_t tls_session_{nullptr};
  ngtcp2_crypto_conn_ref conn_ref_{};
  ngtcp2_conn * conn_{nullptr};
  nghttp3_conn * http3_conn_{nullptr};
  ngtcp2_connection_close_error last_error_{};
  int qlog_fd_{-1};
  bool qlog_write_failed_{false};
  std::string qlog_path_;
  std::string qlog_write_error_;
  std::map<std::int64_t, std::unique_ptr<StreamState>> streams_;
  std::string error_;
  std::uint64_t connections_created_{0};
  std::uint64_t handshakes_completed_{0};
  std::uint64_t streams_opened_{0};
  std::uint64_t streams_on_current_connection_{0};
  std::uint64_t connection_reuse_count_{0};
  std::uint64_t packets_sent_{0};
  std::uint64_t packets_received_{0};
  std::uint64_t reconnects_{0};
  std::uint64_t concurrent_stream_pairs_{0};
  std::uint64_t max_concurrent_request_streams_{0};
};

#else

class InProcessQuicClient::Impl
{
public:
  bool configure(const InProcessQuicClientConfig &)
  {
    error_ = "in-process QUIC was not compiled (ngtcp2/GnuTLS development packages missing)";
    return false;
  }
  bool send_frame(const std::string &) {return false;}
  bool receive_frame(std::string *) {return false;}
  bool send_and_receive_frame(const std::string &, std::string *) {return false;}
  void stop() {}
  std::string error() const {return error_;}
  std::uint64_t connections_created() const {return 0;}
  std::uint64_t handshakes_completed() const {return 0;}
  std::uint64_t streams_opened() const {return 0;}
  std::uint64_t connection_reuse_count() const {return 0;}
  std::uint64_t packets_sent() const {return 0;}
  std::uint64_t packets_received() const {return 0;}
  std::uint64_t reconnects() const {return 0;}
  std::uint64_t concurrent_stream_pairs() const {return 0;}
  std::uint64_t max_concurrent_request_streams() const {return 0;}

private:
  std::string error_;
};

#endif

struct InProcessQuicClient::PendingOperation
{
  bool send_operation{false};
  std::string payload;
  std::string response;
  bool paired{false};
  bool completed{false};
  bool result{false};
};

InProcessQuicClient::InProcessQuicClient()
: impl_(std::make_unique<Impl>())
{}

InProcessQuicClient::~InProcessQuicClient()
{
  stop();
}

bool InProcessQuicClient::compiled()
{
#ifdef FLEETQOX_HAS_INPROCESS_QUIC
  return true;
#else
  return false;
#endif
}

bool InProcessQuicClient::configure(const InProcessQuicClientConfig & config)
{
  {
    std::lock_guard<std::mutex> lock(rendezvous_mutex_);
    stopping_ = true;
    pending_send_.reset();
    pending_receive_.reset();
  }
  rendezvous_cv_.notify_all();
  bool configured = false;
  {
    std::lock_guard<std::mutex> lock(impl_mutex_);
    configured = impl_->configure(config);
  }
  {
    std::lock_guard<std::mutex> lock(rendezvous_mutex_);
    concurrent_pair_wait_ms_ = configured ? config.concurrent_pair_wait_ms : 0;
    stopping_ = false;
  }
  concurrent_api_operation_pairs_.store(0, std::memory_order_relaxed);
  max_concurrent_api_calls_.store(0, std::memory_order_relaxed);
  rendezvous_cv_.notify_all();
  return configured;
}

bool InProcessQuicClient::send_frame(const std::string & payload)
{
  return exchange_coordinated(true, payload, nullptr);
}

bool InProcessQuicClient::receive_frame(std::string * payload)
{
  return exchange_coordinated(false, {}, payload);
}

bool InProcessQuicClient::exchange_coordinated(
  bool send_operation, const std::string & payload, std::string * received_payload)
{
  if ((send_operation && payload.empty()) || (!send_operation && received_payload == nullptr)) {
    std::lock_guard<std::mutex> lock(impl_mutex_);
    return send_operation ? impl_->send_frame(payload) : impl_->receive_frame(received_payload);
  }

  auto operation = std::make_shared<PendingOperation>();
  operation->send_operation = send_operation;
  operation->payload = payload;
  std::shared_ptr<PendingOperation> counterpart;
  std::uint64_t pair_wait_ms = 0;
  {
    std::unique_lock<std::mutex> lock(rendezvous_mutex_);
    if (stopping_) {
      return false;
    }
    pair_wait_ms = concurrent_pair_wait_ms_;
    if (pair_wait_ms > 0) {
      auto & counterpart_slot = send_operation ? pending_receive_ : pending_send_;
      auto & own_slot = send_operation ? pending_send_ : pending_receive_;
      if (counterpart_slot != nullptr) {
        counterpart = std::move(counterpart_slot);
        counterpart->paired = true;
        operation->paired = true;
      } else if (own_slot == nullptr) {
        own_slot = operation;
        const auto pair_deadline = std::chrono::steady_clock::now() +
          std::chrono::milliseconds(pair_wait_ms);
        (void)rendezvous_cv_.wait_until(
          lock, pair_deadline,
          [this, &operation]() {return operation->paired || stopping_;});
        if (operation->paired) {
          rendezvous_cv_.wait(lock, [&operation]() {return operation->completed;});
          if (!send_operation && received_payload != nullptr) {
            *received_payload = operation->response;
          }
          return operation->result;
        }
        if (own_slot == operation) {
          own_slot.reset();
        }
        if (stopping_) {
          return false;
        }
      }
    }
  }

  if (counterpart != nullptr) {
    rendezvous_cv_.notify_all();
    const std::shared_ptr<PendingOperation> send =
      send_operation ? operation : counterpart;
    const std::shared_ptr<PendingOperation> receive =
      send_operation ? counterpart : operation;
    std::string response;
    bool result = false;
    {
      std::lock_guard<std::mutex> lock(impl_mutex_);
      result = impl_->send_and_receive_frame(send->payload, &response);
    }
    {
      std::lock_guard<std::mutex> lock(rendezvous_mutex_);
      send->result = result;
      receive->result = result;
      receive->response = response;
      send->completed = true;
      receive->completed = true;
    }
    if (result) {
      concurrent_api_operation_pairs_.fetch_add(1, std::memory_order_relaxed);
      std::uint64_t observed = max_concurrent_api_calls_.load(std::memory_order_relaxed);
      while (observed < 2 && !max_concurrent_api_calls_.compare_exchange_weak(
          observed, 2, std::memory_order_relaxed))
      {
      }
    }
    rendezvous_cv_.notify_all();
    if (!send_operation && received_payload != nullptr) {
      *received_payload = response;
    }
    return result;
  }

  std::lock_guard<std::mutex> lock(impl_mutex_);
  return send_operation ? impl_->send_frame(payload) : impl_->receive_frame(received_payload);
}

bool InProcessQuicClient::send_and_receive_frame(
  const std::string & send_payload, std::string * received_payload)
{
  std::lock_guard<std::mutex> lock(impl_mutex_);
  return impl_->send_and_receive_frame(send_payload, received_payload);
}

void InProcessQuicClient::stop()
{
  {
    std::lock_guard<std::mutex> lock(rendezvous_mutex_);
    stopping_ = true;
    concurrent_pair_wait_ms_ = 0;
    pending_send_.reset();
    pending_receive_.reset();
  }
  rendezvous_cv_.notify_all();
  {
    std::lock_guard<std::mutex> lock(impl_mutex_);
    impl_->stop();
  }
  {
    std::lock_guard<std::mutex> lock(rendezvous_mutex_);
    stopping_ = false;
  }
}

std::string InProcessQuicClient::error() const
{
  std::lock_guard<std::mutex> lock(impl_mutex_);
  return impl_->error();
}

#define FLEETQOX_QUIC_METRIC_GETTER(name) \
  std::uint64_t InProcessQuicClient::name() const \
  { \
    std::lock_guard<std::mutex> lock(impl_mutex_); \
    return impl_->name(); \
  }

FLEETQOX_QUIC_METRIC_GETTER(connections_created)
FLEETQOX_QUIC_METRIC_GETTER(handshakes_completed)
FLEETQOX_QUIC_METRIC_GETTER(streams_opened)
FLEETQOX_QUIC_METRIC_GETTER(connection_reuse_count)
FLEETQOX_QUIC_METRIC_GETTER(packets_sent)
FLEETQOX_QUIC_METRIC_GETTER(packets_received)
FLEETQOX_QUIC_METRIC_GETTER(reconnects)
FLEETQOX_QUIC_METRIC_GETTER(concurrent_stream_pairs)
FLEETQOX_QUIC_METRIC_GETTER(max_concurrent_request_streams)

#undef FLEETQOX_QUIC_METRIC_GETTER

std::uint64_t InProcessQuicClient::concurrent_api_operation_pairs() const
{
  return concurrent_api_operation_pairs_.load(std::memory_order_relaxed);
}

std::uint64_t InProcessQuicClient::max_concurrent_api_calls() const
{
  return max_concurrent_api_calls_.load(std::memory_order_relaxed);
}

}  // namespace rmw_fleetqox_cpp

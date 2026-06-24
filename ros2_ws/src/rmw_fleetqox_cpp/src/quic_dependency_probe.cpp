#include <cstdint>
#include <iostream>

#include <gnutls/gnutls.h>
#include <ngtcp2/ngtcp2.h>
#include <ngtcp2/ngtcp2_crypto_gnutls.h>

int main()
{
  const ngtcp2_info * info = ngtcp2_version(NGTCP2_VERSION_NUM);
  const bool version_ok = info != nullptr && info->version_str != nullptr &&
    info->version_num >= NGTCP2_VERSION_NUM;
  const bool quic_v1_supported = ngtcp2_is_supported_version(NGTCP2_PROTO_VER_V1) != 0;
  const gnutls_record_encryption_level_t initial_level =
    ngtcp2_crypto_gnutls_from_ngtcp2_level(NGTCP2_CRYPTO_LEVEL_INITIAL);
  const bool crypto_binding_ok = static_cast<int>(initial_level) >= 0;
  const char * gnutls_version = gnutls_check_version(nullptr);
  const bool gnutls_ok = gnutls_version != nullptr && gnutls_version[0] != '\0';
  const bool ok = version_ok && quic_v1_supported && crypto_binding_ok && gnutls_ok;

  std::cout << "{\"schema_version\":\"fleetrmw.quic_dependency_probe.v1\","
            << "\"status\":\"" << (ok ? "ok" : "failed") << "\","
            << "\"ngtcp2_version\":\"" << (info != nullptr && info->version_str != nullptr ?
                 info->version_str : "") << "\","
            << "\"ngtcp2_version_num\":" << (info != nullptr ? info->version_num : 0) << ","
            << "\"quic_v1_supported\":" << (quic_v1_supported ? "true" : "false") << ","
            << "\"gnutls_version\":\"" << (gnutls_version != nullptr ? gnutls_version : "") << "\","
            << "\"crypto_gnutls_binding_ok\":" << (crypto_binding_ok ? "true" : "false") << ","
            << "\"rmw_integrated_backend\":false}\n";
  return ok ? 0 : 1;
}

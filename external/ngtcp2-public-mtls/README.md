# FleetQoX public-API ngtcp2/GnuTLS server

This image rebuilds the official ngtcp2 `v0.12.1` GnuTLS HTTP/3 server
example at the exact source commit used by the Ubuntu 24.04 development
packages. The small auditable patch replaces the example's request-only
client-certificate behavior with:

- `GNUTLS_CERT_REQUIRE`;
- a mandatory PEM trust store loaded with
  `gnutls_certificate_set_x509_trust_file`;
- an optional CRL loaded with `gnutls_certificate_set_x509_crl_file`;
- handshake-time chain/revocation verification through
  `gnutls_certificate_set_verify_function` and
  `gnutls_certificate_verify_peers3`;
- client-auth EKU and optional exact URI-SAN enforcement.
- disabled TLS/QUIC early data at the server edge.

All TLS and QUIC operations use public GnuTLS/ngtcp2/nghttp3 APIs. This
closes the public-API mutual-TLS transport-server boundary. It does not by
itself replace the FleetQoX state/admission backend; that integration remains
a separate production-readiness boundary.

Build from the repository root:

```bash
docker build \
  -f external/ngtcp2-public-mtls/Dockerfile \
  -t localhost/fleetrmw/ngtcp2-public-mtls:0.12.1 \
  .
```

Run the canonical five-round Docker/netem proof:

```bash
python3 scripts/run_rmw_docker_ngtcp2_public_mtls_server_probe.py \
  --iterations 5
```

The summary is written to
`results_rmw_socket/docker_ngtcp2_public_mtls_server_summary.json`.

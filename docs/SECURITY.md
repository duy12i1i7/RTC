# Security

## Scope

FleetRMW security covers identity, authorization, confidentiality, integrity,
resource-pressure isolation, credential lifecycle, gateway state, and failure
behavior. Security claims are transport- and probe-specific; DDS Security
interoperability is not implied.

## Implemented controls

- UDP AEAD paths with authenticated fragment admission.
- X.509/SROS2-derived peer identity checks for selected UDP graph/data paths.
- Fail-closed rejection of unprotected fragment wrappers when protection is
  required.
- Fragment state isolation against an unauthorized but CA-trusted test peer.
- Source-scoped repair authorization and per-reader repair budgets.
- Bounded assembly/history/queue state under malformed or adversarial input.
- mTLS QUIC gateway probes, identity admission, CRL refresh slices, and active
  worker isolation in the public ngtcp2 work.
- Durable gateway/application outcome state with bounded failover probes.
- A repeated Docker stress/security campaign covering selected controls.

## Explicitly open claims

The capability manifest correctly keeps the following production-level claims
false:

- production fragment security;
- long-duration multi-attacker fragment soak;
- governance transport-security completeness;
- forward secrecy and asymmetric session-key exchange as a complete system;
- DDS Security interoperability;
- complete SROS2 policy enforcement;
- online client/server CA and certificate rotation for active sessions;
- active-session revocation through public APIs;
- production QUIC backend hardening;
- consensus, split-brain tolerance, regional recovery, and hardware fencing.

## Threat model for the research prototype

The current test boundary includes:

- malformed, oversized, colliding, duplicated, and incomplete frames;
- unauthorized publishers that can reach the UDP port;
- a CA-trusted peer with the wrong application identity;
- replay/duplicate repair pressure;
- process crash and bounded gateway failover;
- expired/revoked credentials in selected probes;
- queue and state exhaustion attempts.

It does not yet cover every production threat, including kernel compromise,
host credential theft, sophisticated traffic analysis, large botnets, full
Byzantine gateway behavior, supply-chain compromise, or physical robot capture.

## Production security completion gates

1. Freeze the protocol and cryptographic suites; remove ad-hoc/private API
   dependencies.
2. Define identity binding for robot, fleet, process, endpoint, and task.
3. Complete certificate issuance, rotation, expiry, revocation, and rollback.
4. Prove fail-closed behavior during CA/server/client rotation with active
   sessions and in-flight reliable data.
5. Add forward-secret asymmetric establishment and document replay windows.
6. Add distributed gateway election, quorum, fencing, and recovery tests.
7. Run long multi-attacker, malformed-input, resource-exhaustion, and credential
   churn soak tests with CPU/RSS/state limits.
8. Produce a security operations guide and independent review.

## Reporting rule

A passing Docker security probe proves only the tested control and topology.
It must not be summarized as "secure" or "production hardened" without the
completion gates above.

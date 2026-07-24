# FleetRMW / FleetQoX

FleetRMW is a research-oriented ROS 2 middleware project for large-scale robot
fleets. The long-term goal is a ROS 2-native, non-DDS RMW that keeps the ROS
programming model while replacing endpoint-centric topic delivery with
fleet-scale, task-aware, QoS/QoE/QoT communication.

This repository starts with the part that should be proven first:

- a project manifesto and research framing;
- a QoX model for control, state, perception, operator, and bulk flows;
- a causal-semantic deadline scheduler prototype;
- a predictive admission control prototype with semantic wire compaction;
- a supervisory intent transform for paths where short-horizon control is
  physically infeasible;
- a dependency-free FleetRMW sample contract boundary for identity, admission
  provenance, fidelity, and qualified delivery metadata;
- end-to-end `contract_id` propagation from ROS 2 shim batches through sidecar
  events, qualified wrappers, and projection-gate logs;
- source-derived `source_sample_id` propagation from ROS header stamps or
  RMW-visible publisher GID/sequence metadata where available;
- native `FleetRmwSampleEnvelope` propagation for FleetRMW-owned publisher
  identity, source sequence, and source/receive timestamps;
- a native `fleetrmw.data_frame.v1` packet path that can replace legacy
  sidecar event JSON on the sidecar-to-egress data plane;
- a minimal in-memory FleetRMW publish/take boundary that emits
  `fleetrmw.data_frame.v1` and receiver-side `fleetrmw.ack_nack.v1` feedback;
- a liveliness-backed ACK/NACK retransmission horizon for ROS 2 live bridge
  control leases, with a repeated `8`-robot Wi-Fi/WAN/roaming audit passing
  seeds `7,13,29`;
- a socket-backed minimal FleetRMW publish/take smoke where
  `fleetrmw.data_frame.v1` crosses UDP and `fleetrmw.ack_nack.v1` returns to the
  talker;
- a first C++ `rmw_fleetqox_cpp` transport-boundary reference package with a
  UDP loopback smoke matching the Python socket retransmit contract and initial
  RMW lifecycle symbols, now verified by Docker ROS Jazzy `colcon` build,
  Python-to-C++ frame probing, an init/context/node lifecycle probe, and a
  socket-backed serialized pub/sub data-frame path with both local loopback and
  env-configured inter-process peer probes, plus a Docker
  publisher-router-subscriber-observer route and lease-aware remote-graph
  synchronization probe and a two-context `ROS_DOMAIN_ID` isolation probe over
  graph guards/counts, data, services, reliability/control frames, and leased
  remote graph state, type-erased and introspection-C/C++ ROS typed
  publish/take probes, wait/guard, and graph probes; wait sets enforce bounded
  native-entity capacity (`0` means unbounded), non-null entries, active
  same-context membership, while externally owned `rcl` timer guard conditions
  do not consume capacity (matching Jazzy's omission of timers from
  `max_conditions`), plus exact entity-owner node lifecycle checks; a standalone C++
  type-support regression round-trips `String` and nested `PoseStamped`, checks
  exact bounded `Pose` serialized-size calculation, and deliberately scopes
  unbounded artificial sizing as unsupported; a
  two-container `rclcpp` probe routes nested PoseStamped pub/sub plus SetBool
  service traffic through the FleetRMW router; a separate two-container POSIX
  shared-memory gate transfers a 100 KB payload with no UDP peer or slot
  overwrite, reports zero network-flow endpoints in SHM mode, and proves an
  explicit UDP fallback path under injected SHM initialization failure; a
  hybrid gate then sends the same flow over local SHM and a remote UDP router,
  requires router forwarding, and proves application-level duplicate removal;
- a real publisher/subscription payload-scratch allocation ABI: init reserves
  a type-support-bound 64 KiB scratch vector, typed/serialized publish and take
  validate and reuse it, and `5/5` Docker runs each complete eight pairs with
  exact use counts, stable capacity, zero scratch growths, and fail-closed
  uninitialized handles. Frame/history/transport allocations remain, so this
  is not a deep all-hot-path preallocation or zero-copy claim;
- a real `rmw_take_sequence` ABI implementation with ordered full and partial
  takes, unchanged output sequences on empty/invalid calls, and a
  per-subscription lock that preserves consecutive queue ranges across
  concurrent takes. A five-run Docker probe passes every semantic check and
  an exported-symbol audit finds no Fast DDS Jazzy `rmw_*` symbol missing from
  FleetRMW (`283` FleetRMW versus `95` baseline symbols);
- a non-placeholder `rmw_publisher_wait_for_all_acked` path. ACK/NACK frames
  carry a backward-compatible subscriber identity, each reliable write
  snapshots its compatible subscription endpoint set, and the wait returns
  only after every still-matched endpoint has acknowledged or the requested
  timeout expires. In `5/5` Docker runs, a deliberately delayed second ACK
  yields `RMW_RET_TIMEOUT` at `1/2` ACKs and OK at `2/2`; full DDS writer-history
  and resource-limit equivalence remain outside this claim;
- a separate `5/5` four-container remote ACK gate routes one DATA frame and two
  subscriber-identified ACKs through the FleetRMW UDP router under netem. The
  second subscriber delays its ACK by 450 ms, so the publisher must first time
  out at `1/2` and then complete at `2/2`; all publisher/subscriber processes
  and the router exit cleanly;
- a QoS event ABI surface where publisher/subscription event init/fini,
  event callback setters, support checks, and offered/requested deadline missed
  event production pass in Docker; deadline misses are produced by a timer
  after the first publish/receive or on the next publish/receive after a
  deadline gap, become ready through `rmw_wait` while unread, and clear after
  `rmw_take_event`; local publication/subscription matched events are produced
  on same-process compatible endpoint create/destroy; local offered/requested
  reliability-, durability-, and deadline-incompatible QoS events are produced for
  best-effort publishers discovered by reliable subscriptions and volatile
  publishers discovered by transient-local subscriptions plus offered deadlines
  that exceed requested deadlines or omit a finite requested deadline; all four
  slower/missing offered/requested deadline directions pass `5/5`. Local publisher/subscription
  incompatible-type events are produced for same-topic type mismatches. The
  same matched, reliability/durability/deadline-incompatible, exact
  type-incompatible, and finite liveliness-changed lifecycle is now driven by UDP-learned remote graph
  endpoints as well: renewal advertisements are deduplicated, explicit remove
  disconnects immediately, and a killed peer disconnects after graph-lease
  expiry under two-container UDP/netem. A separate two-container UDP/netem artifact produces both offered and
  requested deadline-missed events after a real remote sample and idle gap,
  with wait/take/callback/cleared-readiness checks passing `5/5`. The graph
  artifact passes `5/5` runs across both removal
  paths and proves automatic graph-guard add/disconnect wakeups without renewal
  wakeup noise. The remote MANUAL_BY_TOPIC publisher now also proves
  `RMW_EVENT_LIVELINESS_LOST` twice per run through callback/wait/take/clear.
  A machine-readable aggregate validates at least one repeated real
  UDP/netem multi-container path for all `11` non-invalid Jazzy RMW event
  types (`35` source executions); it deliberately does not claim every
  DDS/vendor-specific event semantic. Local subscription message-lost events are produced for `KEEP_LAST`
  queue overwrite and `BEST_EFFORT` source-sequence gaps after a configurable
  reorder grace period; the first received sample establishes the join baseline,
  best-effort readers do not request repair, and a late reliable repair inside
  the grace period suppresses a false loss event. A reliable writer whose
  requested sample has already left `KEEP_LAST` history sends a
  subscriber-targeted unrecoverable-loss notice, producing one loss event
  instead of an endless NACK loop. A two-container UDP/netem probe repeats this
  remote writer-history-exhaustion path `20/20`: duplicate immediate/idle repair
  notices are received twice but counted as exactly one lost sample/event through
  callback, `rmw_wait`, and `rmw_take_event`. A second campaign keeps the missing
  sample in writer history and proves terminal budget exhaustion, max-attempt
  exhaustion, and strict admission rejection `5/5` each, with clean process
  teardown. Local manual liveliness lost/changed events are produced for finite
  lease timeout and reassert; AUTOMATIC publishers are renewed by the RMW while
  they exist, with an idle six-lease false-loss control passing `5/5`. A separate
  two-container UDP/netem probe passes `5/5` for remote MANUAL_BY_TOPIC idle
  timeout and explicit/publish wire reassertion while proving graph renewal does
  not renew the independent liveliness lease. Another `5/5` remote probe proves
  independent state for two simultaneous publishers, correct alive/not-alive
  removal, and clean endpoint recreate churn. Local offered/requested
  liveliness kind and slow/missing lease incompatibility events pass another
  seven-scenario `5/5` Docker artifact. A local 64-publisher MANUAL_BY_TOPIC
  scale probe verifies exact half-expiry/reassert/full-expiry/removal counts,
  while 16 SYSTEM_DEFAULT publishers survive six idle lease intervals; all
  five Docker repetitions pass. The same 64-publisher manual transition matrix
  also passes `5/5` across two UDP/netem containers, with exact matched and
  liveliness deltas, 96 expiries, and 32 reassertions per run. Default,
  non-expiring leases now retain alive/remove events for SYSTEM_DEFAULT,
  AUTOMATIC, MANUAL_BY_TOPIC, and BEST_AVAILABLE; UNKNOWN and deprecated
  MANUAL_BY_NODE endpoint inputs fail closed in another `5/5` control.
  BEST_AVAILABLE QoS selection now uses
  the Jazzy `rmw_dds_common` algorithm over FleetRMW graph queries and passes
  `5/5` for publisher/subscription, zero/mixed endpoint, actual-QoS, and frozen
  create-time policy controls. A separate
  `5/5` matrix covers `rmw_wait`/`rmw_take_event` for all eleven non-invalid
  Jazzy event types across `35/35` component executions. Full DDS
  message-lost/resource-limit semantics, deprecated participant-wide DDS
  liveliness semantics, complete DDS/vendor-specific remote event semantics,
  and the full QoS/type compatibility matrix remain out of scope; a separate
  aggregate nevertheless proves at least one repeated UDP/netem path for all
  eleven event types;
- a complete ROS 2 profile-compatibility check for the policies represented by
  `rmw_qos_profile_check_compatible`: reliability, durability, deadline,
  liveliness kind, and liveliness lease duration. The Docker v2 QoS probe
  verifies compatible, ERROR, aggregated-reason, and unknown-policy WARNING
  cases; this does not broaden the separate remote-event-production claim;
- a content-filter ABI where subscription filter set/get preserves expression
  parameters, toggles CFT-enabled state, dynamically reconfigures/disables the
  filter, and enforces parameterized comparisons plus SQL-like `AND/OR/NOT`
  precedence, parentheses, `LIKE`, `BETWEEN`, `IN/NOT IN`, `IS NULL`, and
  `IS NOT NULL` on key-value/std_msgs-style text payloads. Missing fields stay
  SQL `unknown` through negation; malformed expressions and missing
  parameter references fail closed; both the base and SQL-subset artifacts
  repeat `5/5`. Typed-field reflection and the full DDS SQL dialect remain out
  of scope;
- a middleware-owned loaned-message lifecycle for introspection C/C++ where
  publisher borrow/publish-or-return and subscription take/return pass in
  Docker; this is explicitly a lifecycle/allocation claim, not zero-copy;
- a real QUIC/TLS dependency gate using ngtcp2/GnuTLS `gtlsserver` and
  `gtlsclient` that completes a QUIC v1 handshake, negotiates ALPN `h3`,
  emits qlog, and transfers a payload in Docker; this dependency artifact is
  scoped below the newer integrated in-process path;
- a follow-on QUIC/FleetRMW wire-format gate that transfers a real
  `fleetrmw.data_frame.v1` through ngtcp2/GnuTLS QUIC/TLS/H3 and decodes it
  with the C++ `fleetrmw_frame_probe`, still scoped below integrated RMW
  publish/take transport;
- a Docker/netem QUIC/FleetRMW gate that repeats the frame transfer across two
  containers after applying `tc netem` to the client interface, with qdisc
  before/after counters and parsed ngtcp2 path telemetry;
- a publish-side QUIC gateway slice in `rmw_fleetqox_cpp` where `rmw_publish`
  posts the encoded FleetRMW frame through ngtcp2/GnuTLS QUIC/TLS/H3 and the
  Docker gates verify the server received the same frame byte count, including
  async enqueue/drain and burst-worker probes plus two-container `tc netem`
  single-publish and async-burst runs with qdisc counters and ngtcp2 path
  telemetry; this is subprocess-backed and not a full bidirectional production
  QUIC backend;
- QUIC gateway session/tp/token file plumbing through ngtcp2/GnuTLS
  `gtlsclient`, with a Docker burst probe that verifies session artifacts
  persist across multiple uploads and parses log telemetry that separates
  0-RTT packet attempts from accepted 0-RTT; this is not a 0-RTT, security
  hardening, or full-duplex transport claim;
- QUIC gateway take/download slices where the shared transport helper fetches
  a `fleetrmw.data_frame.v1` over ngtcp2/GnuTLS QUIC/TLS/H3 GET, verifies
  byte-for-byte payload integrity, and decodes it in C++, and an opt-in
  `FLEETQOX_RMW_QUIC_GATEWAY_TAKE_ON_DEMAND=1` smoke wires that download path
  into `rmw_take_serialized_message`; repeated RMW-take GETs also share
  ngtcp2/GnuTLS session/tp/token files and report conservative session/0-RTT
  telemetry. This is still subprocess-backed and not an accepted
  0-RTT/session-resumption or full bidirectional production QUIC backend claim;
- a same-server QUIC gateway bidirectional boundary probe where one
  ngtcp2/GnuTLS `gtlsserver` accepts an RMW publish POST and then serves an
  opt-in RMW take GET while both client invocations share session/tp/token
  files across `5/5` repeated publish+take pairs; this proves sequential
  publish+take gateway plumbing, not a production full-duplex backend. A
  disable-early-data control keeps 0-RTT packet telemetry at zero when
  `FLEETQOX_RMW_QUIC_DISABLE_EARLY_DATA=1`;
- an integrated in-process QUIC v1/H3 backend using ngtcp2, GnuTLS, and
  nghttp3. The Docker/netem gate executes 128 real `rmw_publish` calls and one
  on-demand `rmw_take_serialized_message` over one connection and one verified
  TLS handshake, observes 129 reliable bidirectional streams and 128
  same-connection reuses with zero reconnects, emits three native client qlogs
  plus three server qlogs, and rejects an unrelated CA. The final
  `rmw_publish` and `rmw_take_serialized_message`
  are launched by two independent threads and rendezvous into one POST/GET
  pair before either response is driven: the probe records one concurrent RMW
  API pair, two simultaneous API calls, and two simultaneous H3 streams. A
  second positive connection verifies the explicit paired transport API. The
  in-process client also rejects non-2xx HTTP/3 responses instead of silently
  accepting them;
- a stateful FleetQoX gateway service built on aioquic QUIC v1/H3. It validates
  `fleetrmw.data_frame.v1`, stores bounded per-domain/topic history,
  deduplicates `(publisher_id, sequence)`, and gives each consumer an
  independent replay cursor. The canonical two-container Docker/netem gate
  passes `5/5`: every run negotiates three H3 sessions, accepts three unique
  frames plus one duplicate, replays sequences `1..3` to two consumers over
  reused client sessions, propagates an invalid frame as HTTP 400, emits
  client/server qlogs, and tears down cleanly. This does not claim accepted
  0-RTT/resumption, clustered durability, predictive QoS/QoE admission, or a
  production QUIC backend;
- a follow-on public-RMW stateful gateway gate using three containers per run:
  one `rmw_publish` process writes three introspection-C `std_msgs/String`
  samples, a separate `rmw_take` process replays all three in order, and the
  aioquic service mediates the six H3 requests. It passes `5/5` under netem;
  both endpoints reuse one verified-TLS connection across three streams and
  emit qlogs. This closes the inter-process public-RMW integration slice, not
  the production security/admission boundary;
- a mutual-TLS stateful gateway gate using six containers per run. The
  in-process GnuTLS client loads a certificate/private-key pair, the aioquic
  gateway requires a client certificate signed by its configured client CA,
  and the Docker/netem artifact passes `5/5`: the trusted client writes one
  frame while a missing-certificate client and an unrelated-CA client both
  fail closed without changing gateway state. A second certificate signed by
  the trusted CA but with a publisher URI SAN different from `publisher_id`
  receives HTTP/3 403 under opt-in identity binding and also cannot mutate
  state. This
  gate also validates a CA-signed CRL at startup and rejects a trusted,
  correctly identified client whose certificate serial is revoked. This
  compatibility path now isolates the private TLS adapter, pins the Debian
  aioquic package to `0.9.25-3build2`, requires runtime version `0.9.25`, and
  fingerprints all three private method signatures before accepting traffic.
  Any version/signature drift fails startup, and authentication is marked only
  after CertificateVerify proves possession of the client private key. Current
  upstream aioquic still lacks a public server client-auth API, so this remains
  a guarded compatibility boundary; broader fleet identity policy, online
  revocation/rotation, clustered state, and production hardening remain open;
- a public-API ngtcp2/GnuTLS mutual-TLS server boundary. The image rebuilds
  the official ngtcp2 `v0.12.1` server at pinned commit
  `a4ba3f20d70d4a4d79674cee1093c55b4c1d78ed` and uses public GnuTLS APIs for
  client-CA chain validation, CRL revocation, client-auth EKU, exact URI SAN,
  and disabled early data. Its Docker/netem artifact passes `5/5`: every valid
  client receives six HTTP/3 responses over one session, while missing,
  unrelated-CA, wrong-URI, and revoked clients receive a TLS `CRYPTO_ERROR`
  before any HTTP response. A second `5/5` gate now connects this edge through
  a bounded Unix-socket protocol to the same `FleetQoxGatewayState` engine.
  Every round carries 12 stateful responses across four verified mTLS
  connections: three unique frames plus one duplicate, six ordered takes for
  two independent consumers, invalid-frame HTTP 400, and an authenticated
  publisher-impersonation HTTP 403 with no state mutation. The alpha and beta
  clients respectively reuse one connection across seven and three H3
  streams. This removes aioquic and its private hook from the tested stateful
  server runtime. A third matched `5/5` Docker/netem contrast now forwards
  public `ngtcp2_conn_get_conn_stat` RTT/RTT-variation/congestion values and
  `ngtcp2_conn_get_stream_loss_count` through versioned backend protocol v2.
  With the metric-to-admission switch disabled, the score-zero frame receives
  HTTP 429; with it enabled, the same policy/frame receives HTTP 200 and the
  frame is taken. Source accounting is `ngtcp2_public_api` and there are zero
  external observation-API requests. The stream-loss value remains a raw
  packet-loss count—not a fabricated ratio—because this ngtcp2 API exposes no
  sent-packet denominator. A fourth public-edge `5/5` gate keeps Unix backend
  I/O off libev through a bounded worker pool, returns HTTP 503 on global
  saturation, and generation-fences stale completions. A fifth gate derives
  per-connection publisher identities from verified URI SANs, rejects a
  CA-trusted out-of-prefix identity, returns HTTP 429 on a publisher's pending
  limit, and round-robins identity queues so another publisher overtakes the
  overloaded publisher's remaining request. A sixth matched `5/5` gate adds a
  configurable per-identity active-worker limit: limit one preserves a worker
  for another publisher, while the limit-two control lets the noisy publisher
  occupy both workers and delays the victim. The default remains the worker
  count for work-conserving compatibility. A seventh `5/5` Docker/netem gate
  enables per-handshake client-CRL reload through public GnuTLS APIs. Without
  restarting the server, a previously accepted client is rejected with
  `CRYPTO_ERROR` after its serial is added to the CRL, is accepted again after
  the original CRL is restored, and is rejected fail-closed when the replacement
  CRL is malformed. This applies to new TLS connections only. Weighted QoS
  scheduling, online client-CA/server-certificate rotation, active-session
  revocation, clustered public-edge state, and production hardening remain the
  production QUIC boundary;
- a scoped fleet-admission gate inside the stateful QUIC service. A validated
  JSON policy assigns domain/topic streams to traffic classes, allowlists
  publishers, caps each stream, and caps total accepted frames across the
  fleet. The two-container Docker/netem artifact passes `5/5`: it admits and
  replays two control plus one bulk frame, then returns HTTP/3 429 for both
  stream- and fleet-quota exhaustion and HTTP/3 403 for an unauthorized
  publisher, without creating state for rejected frames. After the one-second
  monotonic epoch rolls over, the previously fleet-quota-rejected state frame
  is admitted and replayed, with cumulative and current-epoch counters kept
  distinct. This is deterministic quota admission, not live predictive
  QoS/QoE control;
- a frame-carried QoS/QoE admission and repair-coupling gate. The C++
  `fleetrmw.data_frame.v1` encoder now optionally carries traffic class,
  deadline/age, QoE debt, task criticality, repair intent, and prior attempts.
  The gateway computes a bounded criticality/debt/urgency score and invokes the
  existing fleet repair scheduler when normal quota rejects a repair. The
  Docker/netem artifact passes `5/5`: low score is rejected, high score is
  admitted, one quota-overflow repair is assigned to private 5G, the next is
  deferred by shared repair capacity, and both admitted payloads replay over
  real H3. A follow-on `5/5` gate adds a versioned observation POST with a
  bounded TTL and a two-frame batch endpoint. An externally supplied loss,
  RTT, jitter, and debt observation raises the observed publisher's effective
  score, so it wins a one-frame admission quota despite arriving second in the
  request. A second batch places two repair requests against one shared
  1024-byte budget: the high-criticality request is scheduled first and uses
  622 bytes on private 5G, while the lower-score request is deferred; only the
  two winners replay over H3. This is observation-fed, score-prioritized
  sequential batch admission. A separate mTLS contrast gate now passes `5/5`
  without calling the observation API: the baseline service rejects the same
  frame at score threshold 0.32, while `--native-path-observations` reads the
  authenticated QUIC session's smoothed RTT, RTT-variation proxy, and detected
  packet-loss ratio and admits it. Observation source accounting proves all
  five accepted cases are `quic_session_native`. This aioquic recovery adapter
  is exact-version/signature gated and still private. A follow-on `5/5` mTLS
  contrast keeps publisher debt at zero and raises the threshold so path-only
  scoring rejects, while an opt-in gateway policy derives EWMA debt from
  authenticated loss, RTT/deadline, and RTT-variation/deadline pressure and
  admits the same frame. Provenance is `gateway_derived_path`; startup requires
  mTLS and certificate publisher binding. This remains a path-pressure proxy,
  not application jitter. A follow-on `5/5` mTLS/netem gate accepts a versioned
  application-outcome report only for a known accepted publisher sequence,
  binds its `publisher_id` to the client-certificate URI SAN, rejects
  impersonation/unknown/malformed reports, and makes duplicate reports
  idempotent. The report carries consistent `task_kind`, `terminal_status`, and
  `task_succeeded` fields; a failed task delivery/deadline derives
  provenance-tagged EWMA debt from delivery, deadline, latency, and task
  pressure and changes the next
  low-criticality frame from HTTP 429 to admission. A further `5/5`
  mTLS/netem gate persists the authenticated outcome key and post-outcome
  admission snapshot in the same SQLite transaction. A replacement gateway
  restores both, treats replay as a duplicate without applying debt twice, then
  admits and replays the low-criticality frame. This proves sequential
  cross-gateway idempotence on one shared WAL store. The same scenario also
  passes `5/5` against networked PostgreSQL 16 with `synchronous_commit=on`,
  lease/fence tokens `1->2`, scrubbed connection telemetry, and a maximum
  measured replacement-cycle latency of 4245 ms. Database-process failover is
  deliberately not claimed by that artifact. The concurrency-8 Nav2/RMF Docker
  workload now maps actual terminal action results (`SUCCEEDED`, `CANCELED`) and
  an actual RMF submit response into three strict gateway-schema documents. It
  proves that result delivery and task success remain distinct. The historical
  concurrency-8 artifact explicitly records
  `task_outcome_gateway_submission_performed=false`; a chained `5/5`
  Docker/netem gate consumes its exact three documents,
  seeds their known frame identities, and submits all three over mTLS/H3 with
  one reused outcome session; every run records three task updates and one task
  failure. A second `5/5` gate now performs this path directly in the still-live
  ROS client process: the client PID matches the H3 submitter PID, `rclpy` and
  its node remain active, and each run uses one verified mTLS handshake for six
  H3 streams (five reuses). Netem is active on both the ROS client and gateway.
  Two duplicate request/response transmissions on this live workload repair an
  observed RMF batch response loss; all five canonical runs complete the RMF
  batch and stop every container with code zero. The evidence is
  `results_rmw_socket/docker_nav2_rmf_live_task_outcome_probe_summary.json`.
  A public stable path API, globally optimal joint batch scheduling, and
  cluster-wide replicated capacity state remain open;
- a scoped active/passive durability gate for the aioquic gateway. With
  `--state-db`, accepted frames, bounded dedup keys, and per-consumer replay
  cursors commit through SQLite WAL with `synchronous=FULL`. The canonical
  Docker/netem artifact passes `5/5`; each run starts three fresh gateway
  instances against one run-local database. Instance A publishes three frames,
  B recovers them and recognizes a replayed publish as a duplicate before
  taking frames 1 and 2, and C recovers the committed cursor and takes only
  frame 3. This proves sequential active/passive recovery on shared durable
  storage, not active/active consensus, automatic leader election, replicated
  storage, or cluster-wide admission/repair state. A follow-on `5/5` gate now
  commits each accepted frame and its post-decision quota/repair snapshot in
  one SQLite transaction. A replacement restores the exhausted normal quota,
  cumulative counts, repair allocation, and repair count, then rejects a third
  repair instead of resetting capacity. The policy has a deterministic
  fingerprint: changed policy configuration and legacy retained frames lacking
  admission state fail closed. This is still sequential shared-store failover,
  not concurrent active/active coordination. A third `5/5` Docker/netem gate
  adds a renewable SQLite single-writer lease and monotonic fence token. A
  concurrent standby fails startup while the active lease is live; after clean
  release, a replacement acquires token 2 and restores the exhausted
  admission/repair state. Both frame/admission and consumer-cursor transactions
  recheck holder, token, and expiry under `BEGIN IMMEDIATE`, so stale writers
  fail closed. A fourth `5/5` gate starts B before A stops: B waits on the live
  lease, then the same process automatically acquires token 2, opens H3, and
  restores admission state after A exits. Measured stop-to-ready takeover is
  203--208 ms. This is automatic shared-file standby takeover, not quorum or
  consensus leader election; replicated/distributed storage, partition
  tolerance, active/active operation, and regional disaster recovery remain
  unclaimed. A fifth `5/5` Docker/netem gate replaces the shared host file with
  a fresh PostgreSQL 16 database container per run. Both gateways connect over
  the Docker network; frame plus admission state commits with
  `synchronous_commit=on`, lease changes serialize under a PostgreSQL advisory
  transaction lock, and frame/cursor writes recheck the lease row `FOR UPDATE`.
  B waits while A owns token 1, automatically acquires token 2 after A stops,
  restores the exhausted repair state, and rejects the next repair over real
  QUIC/H3. Observed stop-to-ready takeover is 429--715 ms. This removes the
  gateway shared-filesystem requirement, but the database is still one
  process: database-process failover, replication, quorum/consensus, partition
  tolerance, and production readiness remain unclaimed by that artifact. A
  sixth `5/5` campaign adds a PostgreSQL synchronous streaming standby. It
  verifies `streaming|sync` and positive flush/replay WAL positions after the
  two acknowledged frame/admission commits, kills the primary process, waits
  for A to detect lease-store loss and exit fail-closed, promotes the replica,
  and lets pre-started B reconnect through a read-write multi-host DSN. B
  acquires token 2, recovers both frames plus admission/repair state, and
  rejects the next repair over QUIC/H3. Database-failure-to-gateway-ready is
  3.129--3.154 s. This proves controlled synchronous database-process failover
  without seeded acknowledged-state loss. Promotion is still issued by the
  test orchestrator: automatic database leader election, a quorum DCS,
  split-brain tolerance under partition, active/active gateways, regional DR,
  and production readiness remain unclaimed at that stage. A seventh `5/5`
  campaign adds a three-member etcd 3.5.17 Raft DCS and two independent
  failover controllers plus a scoped Docker fence agent. It removes quorum by
  killing two etcd members, then applies 100% egress loss in the still-running
  PostgreSQL primary network namespace. The active gateway exits fail-closed,
  the replica remains read-only, B remains unready, and both controllers record
  DCS denial before quorum is restored. Exactly one controller then wins a
  TTL-bound compare-and-put lease. The fence agent performs a linearizable,
  mTLS-authenticated etcd lookup, matches controller value and lease ID, kills
  only the configured primary through the Docker socket, and confirms it is
  stopped; the controller calls `pg_promote` only after that confirmation. The
  loser only observes promotion. B reconnects, acquires token 2, and restores
  state over QUIC/H3. Failure-to-ready is 9.934--10.478 s. The HTTPS fence
  endpoint requires a CA-verified client certificate and binds its CN to the
  requested controller ID. A client without a certificate and an authenticated
  client presenting a forged lease are both rejected while the primary remains
  live. All etcd client/peer and controller/fence links require mutual TLS. This
  proves scoped DCS-authorized Docker STONITH and one live-primary
  partition/fence sequence. Each run then rebuilds the fenced primary from a
  fresh physical basebackup with a dedicated slot and requires the new primary
  to report it as `streaming|sync`; the rebuilt node is read-only and contains
  both frames plus admission state. This restores Docker-scoped post-failover
  redundancy. Each run then starts two independent automatic failback policy
  controllers. Both first reject an intentionally asynchronous replica while
  database roles remain unchanged. After synchronous `streaming|sync` with a
  zero-byte replay gap is restored under 1/3 etcd, both still fail closed for
  lack of quorum. Restoring 2/3 quorum yields exactly one failback lease winner.
  A separate mTLS switchover agent binds certificate CN to controller ID,
  validates its live DCS lease, and gracefully stops the current primary before
  the winner promotes the original primary. Gateway C then acquires fence token
  3, recovers the two frames plus admission state, and repeats the
  exhausted-repair rejection over verified QUIC/H3. Automatic
  failback-to-gateway-ready is 1.699--3.449 s. Finally, the former primary is
  rebuilt from a fresh physical basebackup and must return as a synchronous
  read-only standby containing the seeded state. This proves scoped automatic
  policy/DCS failback in Docker, not production orchestration. The fence is not
  a hardware/cloud fence, and broader split-brain partitions, certificate
  rotation/revocation, production-grade automatic rejoin/failback, regional
  DR, and production readiness remain false;
- a repeated async-burst QUIC gateway soak runner that aggregates frames,
  bytes, qlog size, drops/failures, and optional Docker/netem path telemetry
  across multiple iterations; this is smoke/repeat evidence, not a long
  security/stress campaign or full-duplex QUIC backend claim;
- a Docker security-options ABI probe that verifies `rmw_init_options`
  security/enclave lifecycle, deep-copy behavior, context init copy, shutdown,
  and fini across `5/5` repeated runs. A separate opt-in
  `FLEETQOX_RMW_SECURITY_POLICY` probe enforces FleetQoX publish allow/deny
  rules across `5/5` repeated runs. A second security path uses `ros2 security`
  to generate an enclave and signed DDS permissions artifact, verifies the
  S/MIME signature against the permissions CA, validates the recovered XML
  against the SROS2 XSD, and enforces grant/enclave, validity, domain,
  publish/subscribe topic allow/deny, wildcard, and default-action semantics across
  `5/5` runs. FleetRMW repeats the `permissions.p7s` signature/CA verification
  inside the RMW before parsing; malformed XML and a byte-tampered signed policy
  are denied fail-closed. The same generated policy is enforced on real
  `rmw_send/take_request` and `rmw_send/take_response` SetBool paths, including
  request/reply allow, explicit deny, and default deny. It also enforces the
  SROS2 Action `call`/`execute` expansion on a real rclpy
  `tf2_msgs/action/LookupTransform` path: the allowed action completes
  goal/result/feedback, an explicit call deny fails in `rmw_send_request`, and
  an execute deny drops the request before the server callback. This Action
  matrix passes `5/5`. FleetRMW also verifies signed `governance.p7s`, applies
  domain/topic read-write access-control switches, and repeats that path `5/5`;
  the stock SROS2 Governance profile requesting ENCRYPT/SIGN and a tampered
  governance signature are both denied fail-closed. Local identity credentials
  are also checked before `rmw_init`: certificate chain, private-key match, and
  certificate-CN/enclave equality pass `5/5`, while tampered cert, wrong key,
  and wrong enclave controls fail closed. An opt-in UDP envelope provides
  AES-256-GCM authenticated encryption, unique nonces, replay tracking, strict
  key configuration, and tamper rejection across `5/5`. A certificate-signed
  envelope authenticates remote SROS2 X.509 identities across `5/5`, with
  allowlist, signature-tamper, and untrusted-CA controls failing closed. It
  verifies an X.509 CRL and rejects revoked peers. HKDF-SHA256 derives and
  rotates per-process session keys from the PSK plus a signed random salt. This
  establishes scoped PSK sessions, but does not provide forward secrecy or
  DDS-Security asymmetric key exchange; production hardening remains open;
- a Docker stress/security campaign runner that aggregates security-options,
  FleetQoX security policy, SROS2 permissions XML, UDP AEAD/peer auth,
  dynamic serialization/take, allocation, QoS event,
  content-filter, and QUIC async-burst soak components into one artifact. The
  repeated profile has passed `48/48` component runs. The default long profile
  subsequently passed eight full rounds over 3793 seconds under netem
  (`20±5 ms`, `0.5%` loss): `80/80` component executions and `1680/1680`
  probe runs, so the long campaign claim is now true;
- an installed `rmw_fleetqox_cpp/capabilities.json` contract that marks the
  implementation `production_ready=false` and machine-scopes supported,
  partial, and unsupported ABI surfaces;
- a unified benchmark report aggregator that reads existing JSON summaries and
  the capability manifest, normalizes status/run counts/key metrics, and emits
  a single JSON/Markdown view while preserving claim-boundary guards. Its
  all-artifact status deliberately includes retained historical/debug/negative
  runs, while the current capability-manifest status and true/false claim
  counts are reported separately;
- a repeated ROS 2 Docker T3 harness for packet-format/RMW matrices across
  publisher seeds and named netem profiles;
- a three-seed Wi-Fi ROS 2 packet-format/RMW matrix where
  `data_frame/rmw_zenoh_cpp` is the current non-dominated operating point;
- a three-seed WAN ROS 2 packet-format/RMW matrix showing that the Pareto
  frontier changes by network profile;
- a three-seed roaming ROS 2 packet-format/RMW matrix showing that the frontier
  changes again and depends on the active QoS/QoE objective vector;
- a profile/objective-aware ROS 2 transport selector that ranks measured
  packet-format/RMW candidates under safety/utility, teleop-latency, autonomy
  safety, or throughput objectives;
- a runtime `TransportBinding` payload that lets the ROS 2 shim/sidecar batch
  carry the selected packet-format/RMW policy and choose per-batch packet
  framing in the sidecar runtime;
- a rule-based online binding manager that infers Wi-Fi/WAN/roaming from link
  telemetry and selects the corresponding measured transport binding;
- an adaptive binding estimator that smooths link telemetry and applies
  hysteresis/min-dwell before switching measured transport bindings;
- a live continuous binding loop that refreshes `TransportBinding` and adaptive
  profile estimates on each ROS 2 bridge batch, then lets the sidecar choose
  per-batch packet framing;
- a Docker T3 profile-transition harness that applies Wi-Fi/WAN/roaming
  `tc netem` changes inside one ROS 2 live bridge run and records binding
  switch evidence;
- a Docker T3 adaptive-vs-static transition binding matrix that compares
  adaptive binding against static Wi-Fi/WAN/roaming bindings under the same
  live ROS 2 workload;
- a three-seed ROS 2 live transition binding matrix that quantifies adaptive
  switch latency, missing switches, flapping, and objective-specific wins
  against static bindings;
- a three-seed ROS 2 live dynamic-objective transition matrix where the same
  bridge session changes both network profile and QoS/QoE objective, then
  records matched profile switches, matched objective switches, policy
  switches, switch latency, and flapping in the sidecar decision log;
- a two-robot, three-seed ROS 2 live dynamic-objective transition matrix that
  expands the same bridge session across multiple robot namespaces and records
  decision, receiver, and egress coverage per robot;
- a two-robot, three-seed ROS 2 live dynamic-objective local-services matrix
  where the local controller, projection quality gate, and monitor are
  namespace-aware and observe both robot IDs under the same live transition;
- a two-robot, three-seed ROS 2 live per-robot QoS budget matrix that reports
  Jain fairness, worst-robot control delivery, worst-robot deadline miss, and
  budget pass/fail under the same dynamic profile/objective transition;
- a per-robot budget-aware admission wrapper that converts robot-level SLO debt
  into virtual-queue pressure on future critical-flow scheduling decisions;
- a fleet-level telemetry-scored QoS/QoE path optimizer that combines path
  loss, latency, jitter, NACKs, deadline misses, utilization, per-robot QoE
  debt, flow class, deadline, criticality, and fleet capacity to choose
  unicast, redundant, degraded, or deferred routing;
- an online fleet path-plan controller that smooths per-path observations,
  applies an anti-flapping dwell guard, and exports
  `FLEETQOX_RMW_FLEET_PATH_PLAN` rules for selected ROS topics;
- a C++ `rmw_fleetqox_cpp` fleet-plan mode that reads controller-written path
  plans from a file and reloads updated topic-to-path rules in the same
  publisher process;
- a router telemetry closed-loop probe where live router JSONL records feed a
  host-side controller, which rewrites the RMW fleet-plan file during the same
  ROS 2 publisher session;
- subscriber delivery telemetry for `rmw_take` source sequence/timestamp,
  receive/take timestamp, latency, deadline status, and robot ID, feeding robot
  QoE state back into the live path-plan controller;
- a multi-robot Docker live telemetry probe where `/robot_0000/cmd_vel` and
  `/robot_0001/odom` share the same RMW plan file but receive different
  controller decisions: redundant `backup_5g+primary_wifi` for urgent control
  and unicast `backup_5g` for lower-criticality state, with duplicate redundant
  data frames counted and de-duplicated before application delivery;
- a multi-robot live telemetry profile matrix over `wifi`, `wan`, and
  `roaming` router-telemetry profiles, preserving the same Docker RMW
  publisher/router/subscriber path while varying path latency, jitter, loss,
  NACK rate, deadline-miss ratio, and capacity metadata;
- a multi-robot live netem matrix that runs the same ROS 2/RMW
  publisher-router-subscriber topology while router containers apply real
  Docker `tc qdisc` delay/jitter/rate shaping, optionally requiring successful
  `NET_ADMIN` qdisc application and scaling stochastic packet loss, with a
  dedicated reproducible image in `external/rmw-netem`;
- a stochastic live netem matrix that turns on `tc netem loss random` while
  recording seed values as repetition IDs, because the current image's netem
  implementation does not expose explicit RNG seeding;
- a stochastic live netem sweep that runs multiple loss multipliers over the
  same RMW topology, reports the strongest tested loss scale where all profiles
  pass, records first-failure loss scale by profile, classifies failure kind,
  and can reuse a single colcon build across campaign rows;
- a stochastic live netem ablation campaign that holds the same ROS 2/RMW
  topology, profiles, seeds, and loss scales constant while comparing
  `none`, `state_only`, and `control_state` proactive repair modes for
  delivery resilience, latency, and duplicate-frame/ACK repair cost;
- a matched four-robot FleetRMW live telemetry matrix where
  `deadline_sequence_repair_v1` combines route-warmup ACK gating, semantic
  application repair cycles, idle missing-range ACK/NACK feedback, and terminal
  guard repeats to pass Wi-Fi/WAN/roaming Docker `tc netem` rows over seeds
  `7,13,29`;
- a FleetRMW live baseline comparison report that normalizes the native
  `rmw_fleetqox_cpp` ablation against existing ROS 2 live-bridge
  Fast DDS/Cyclone DDS/Zenoh profile winners while explicitly marking the
  result as an indirect baseline map, not a direct superiority benchmark;
- a direct ROS 2 RMW netem baseline probe/matrix that runs publisher and
  subscriber containers under the same named Wi-Fi/WAN/roaming impairment
  profiles, records missing RMW packages as `skipped`, and seeds the future
  same-envelope DDS/Zenoh comparison against FleetRMW-native routing;
- a repeated `8/16/32`-robot, three-repetition split-scope comparison under
  data-plane netem where all four FleetRMW/Fast DDS/Cyclone DDS/Zenoh systems
  pass `9/9` rows in the current image; equal publisher reliability horizons,
  Zenoh router bootstrap, and 95% confidence intervals are recorded, while the
  v2 report still sets cross-topology superiority to `allowed=false` because
  FleetRMW has a router hop and the baseline application paths are direct;
- a separate matched-hop `8/16/32`-robot, three-seed Docker/netem comparison
  where every system uses publisher-middle-subscriber. Cyclone DDS and Zenoh
  pass `9/9`, FleetRMW passes `8/9`, and Fast DDS passes `6/9` (`32/36`
  overall). The four failures retain genuine missing-payload observations.
  Delivery/reliability comparison is allowed, but latency and architectural
  superiority remain disallowed because FleetRMW forwards raw frames while the
  common DDS/Zenoh relay deserializes and republishes `std_msgs/String`;
- a repeated `8/16/32` actuated-repair capacity frontier where all `27/27`
  rows and `9/9` robot/capacity groups pass: sequence `2` is dropped once on
  both paths for repair candidates, admitted gaps are repaired on time,
  deferred gaps are observably rejected, and live QoE coverage rises
  monotonically from `0.625` to `0.75` to `1.0` with shared capacity;
- a native ns-3 3.41 Docker matrix with `27/27` successful rows across
  `8/16/32` robots, Wi-Fi/WAN/roaming parameter envelopes, and seeds
  `7,13,29`; it compares FIFO, static-priority, and guarded FleetQoX schedules
  on identical traces and explicitly forbids a high-fidelity wireless claim
  because the current topology is shared CSMA plus an independent receive
  error model;
- a second native ns-3 matrix with `27/27` successful rows over the same fleet
  sizes and seeds on a single-AP 802.11g infrastructure topology. Stationary,
  moderate-mobility, and edge-mobility profiles exercise Wi-Fi contention and
  moving stations with positive receive counts in every policy row. The
  artifact permits Wi-Fi/mobility-model claims but explicitly forbids roaming
  handoff claims because there is only one AP;
- a dual-AP ns-3 roaming matrix with `27/27` successful rows and `585/585`
  measured endpoint handoffs. AP association/disassociation trace events and
  positive packet receive counts are mandatory gates, while a bridged
  backhaul preserves each station's IP address across the transition. This
  permits a scoped roaming-handoff claim, not a general high-fidelity wireless
  or policy-superiority claim;
- a pinned OMNeT++ 6.4.0/INET 4.7.0 ARM64 Docker runtime with a real
  `TraceDrivenUdpApp` UDP path. Its matched routed-P2P parity matrix replays
  identical traces, seeds, rates, delays, PER targets, and policy sets in ns-3
  3.41 and INET. All `27/27` runtime pairs and `27/27` bounded-parity cases pass
  across `8/16/32` robots and seeds `7,13,29` (`72,213` packet rows); maximum
  delivery delta is `0.018314`, p99 delta `1.234667 ms`, relative utility delta
  `0.023683`, and deadline-miss delta `0`. This closes the scoped runtime/parity
  gap, while full TSN/mesh and high-fidelity wireless parity remain false;
- an upstream Nav2/RMF router workload where `nav2_msgs/action/NavigateToPose`
  passes success, feedback, cancel, and result semantics while RMF
  `SubmitTask`/`CancelTask` services carry nested task types through the same
  FleetRMW router; an additional batch proves four concurrent upstream
  navigation goals and four RMF submissions; the upstream
  `nav2_lifecycle_manager` C++ node drives a lifecycle companion through
  configure/activate/deactivate/cleanup, bringing the contract to `82/82`
  service frames with zero invalid frames; separate real Nav2
  planner/controller probes configure `planner_server` with
  `nav2_navfn_planner::NavfnPlanner` and `controller_server` with
  `dwb_core::DWBLocalPlanner` through FleetRMW lifecycle services, then publish
  repeated dynamic `/tf` over the same router and activate both nodes to
  `active [3]`. A planner runtime probe also publishes repeated `/map` and
  `/tf` through FleetRMW, sends upstream `ComputePathToPose`, and receives a
  successful Navfn path (`error_code=0`). A controller runtime probe publishes
  repeated `/map`, `/tf`, and `/odom`, sends upstream `FollowPath`, and receives
  a successful DWB result (`error_code=0`). The current full-stack CI-light
  Nav2 probe starts `bt_navigator` with a minimal
  `ComputePathToPose -> FollowPath` behavior tree and sends upstream
  `NavigateToPose`; planner, controller, and BT navigator all reach
  `active [3]`, the goal succeeds with `error_code=0`, and FleetRMW forwards
  the nested action/status/feedback traffic. A repeated same-pose wrapper
  repeats that stack twice with fresh Docker processes, and a moving-base
  probe sends a short `x=0.6` goal while a fake base consumes `/cmd_vel` and
  republishes dynamic `/odom` and `/tf` through FleetRMW; the fake base records
  four command messages and about `0.406 m` of motion. An extended moving-base
  probe sends `x=1.2`, succeeds, forwards `/cmd_vel`, and records about
  `0.956 m` of fake-base motion. A direct Nav2
  `behavior_server` Spin recovery-action probe also activates
  `nav2_behaviors::Spin`, sends `/spin`, forwards `/cmd_vel`, and rotates the
  fake base about `0.616 rad`. A `NavigateToPose` recovery-tree probe then
  runs a `RecoveryNode` where an intentional `MissingPlanner` compute-path
  failure triggers `Spin`; the top-level goal aborts as expected after retry,
  but `/spin`, `/cmd_vel`, and fake-base rotation prove the BT fallback path.
  A recovered-success probe now executes `Spin` first and then successfully
  completes a short `ComputePathToPose -> FollowPath` `NavigateToPose` goal
  (`error_code=0`) while forwarding `/spin`, `/cmd_vel`, `/map`, `/odom`, and
  `/tf`; a repeated wrapper runs that recovered-success path twice with fresh
  Docker processes. A long moving-base wrapper repeats the unobstructed
  `x=1.2` Nav2 BT pipeline three times with fresh Docker processes, requiring
  repeated success, `/cmd_vel` forwarding, and aggregate fake-base motion. A
  planner-level obstacle repair probe blocks `ComputePathToPose` with a static
  occupancy-grid wall (`error_code=208`), then replaces the map with a clear
  grid and replans successfully with `14` path poses. A follow-on full-stack
  `NavigateToPose` obstacle retry probe starts planner, controller, and
  `bt_navigator`, blocks an `x=0.8` goal with the wall (`ABORTED`,
  `error_code=208`), then retries after publishing a clear map and succeeds
  (`error_code=0`) while forwarding `62` service frames and recording about
  `0.610 m` of fake-base motion. A same-goal obstacle recovery probe then keeps
  one `NavigateToPose` goal active, lets the BT observe a planner failure,
  executes a real `Wait` recovery action, publishes a clear map during that same
  goal, and succeeds (`error_code=0`) with about `0.610 m` of fake-base motion
  and `1989` forwarded service frames. This closes the scoped same-goal
  external static-map repair claim; dynamic obstacle avoidance and production
  costmap-clearing policy remain unclaimed. The Nav2/RMF router workload also
  passes concurrency-8/16/32/64/128/256/512/1024/2048 upstream action/service
  batches, with the concurrency-2048 run forwarding `12346` service frames.
  The larger runs exercise FleetRMW UDP large-frame fragmentation/reassembly
  plus router fragment passthrough for oversized action status/service bursts.
  A concurrency-4096 single-batch run is retained as a negative Docker boundary
  artifact because its all-at-once action send-goal phase still
  loses/backpressures a small subset of `NavigateToPose` requests. The
  admission-controlled total-4096 rerun with an 8-goal action window now passes
  in Docker: `4096/4096` `NavigateToPose` goals are accepted and completed,
  `4096/4096` RMF `SubmitTask` calls return, lifecycle-manager traffic remains
  green, and the router forwards `106088` service frames with zero invalid
  frames. This supports a scoped total-4096 upstream workload claim only with
  admission/windowing, UDP socket-buffer/send-pacing tuning, and duplicate-safe
  service-frame request/response repeats; unwindowed 4096 action bursts remain
  outside the claim. The concurrency-8 artifact also records strict v1
  application-outcome documents derived from real Nav2 success/cancel results
  and a real RMF submit response. A separate chained `5/5` mTLS/netem artifact
  submits those exact documents to the gateway with session reuse, while the
  same-live-process claim remains false. Local compatible actions remain as CI fallbacks;
- a controller-level live plan scale probe that drives the same planner across
  N robots and 2N ROS-style topics, measuring decision latency, final rule
  count, plan byte size, and redundant/unicast mode shape before larger
  Docker/netem campaigns;
- a sidecar runtime `fleet_optimizer` payload boundary that actuates optimizer
  decisions as event annotations, semantic degradation, defer/drop decisions,
  and per-path UDP target transmissions in a deterministic runtime probe;
- a ROS 2 Docker T3 path with typed `cmd_vel` egress and robot-local lease
  gating through velocity, acceleration, and jerk profiles;
- typed FleetRMW-local projections for admitted `cmd_vel`, odometry, and
  downsampled laser scan semantic payloads;
- generated `fleetrmw_interfaces` ROS 2 messages for projection quality and
  qualified odometry/laser-scan wrappers;
- a local projection-quality gate that forwards accepted odometry and scan
  projections to consumer-facing topics after validating sample-local quality;
- a deterministic simulation benchmark for large robot fleets.

The prototype is intentionally dependency-light and runs with the Python
standard library.

## Quick Start

```bash
python3 -m scripts.run_benchmark --robots 100 --seconds 60 --seed 7
python3 -m scripts.run_suite
python3 -m scripts.export_traces --scenario warehouse_50_constrained
python3 -m scripts.export_traces --scenario warehouse_50_constrained --format csv
python3 -m scripts.export_traces --scenario warehouse_50_constrained --format csv --policy fleetqox_predictive
python3 -m scripts.replay_trace traces/warehouse_50_constrained.csv --transport-model udp_like --queue-policy class_priority
python3 -m scripts.run_sidecar_runtime --listen-port 8765 --udp-port 9201
python3 -m scripts.feed_sidecar_synthetic --port 8765 --robots 10 --seconds 2
python3 -m scripts.analyze_sidecar_runtime \
  --decisions results_sidecar_runtime/runtime_v1_decisions.jsonl \
  --received results_sidecar_runtime/runtime_v1_received.jsonl
python3 -m scripts.run_sidecar_netem --run --analyze --scenario sidecar_netem_v1
python3 -m scripts.run_sidecar_netem --run --analyze --scenario sidecar_netem_matrix_v1 --all-policies --output-dir results_sidecar_netem_matrix
python3 -m scripts.run_sidecar_netem --run --analyze --scenario sidecar_netem_closed_loop_v1 --all-policies --closed-loop-feed --output-dir results_sidecar_netem_closed_loop
python3 -m scripts.run_sidecar_netem --run --analyze --scenario sidecar_netem_lagrangian_v3 --policy fleetqox_predictive_lagrangian --closed-loop-feed --output-dir results_sidecar_netem_lagrangian_v3
python3 -m scripts.run_lagrangian_sweep --robots 10,25 --seeds 7,13 --seconds 5
python3 -m scripts.adapt_lagrangian_from_netem \
  --summary results_sidecar_repeated/lag_variants_v1_summary.json \
  --manifest experiments/lagrangian_variants_v1.json \
  --next-label lag_adapt_001
python3 -m scripts.run_sidecar_repeated_netem --scenario-prefix sidecar_repeated_v1 --all-policies --seeds 7,13,29 --closed-loop-feed
python3 -m scripts.run_sidecar_repeated_netem \
  --scenario-prefix sidecar_lag012_v1 \
  --policy fleetqox_predictive_lagrangian \
  --policy-label lag_012 \
  --lagrangian-deadline-risk-budget 0.08 \
  --lagrangian-initial-deadline-lambda 1.8 \
  --lagrangian-risk-barrier-start 0.62 \
  --lagrangian-risk-barrier-scale 12.0 \
  --lagrangian-deadline-drop-risk 0.45 \
  --seeds 7,13 \
  --closed-loop-feed
python3 -m scripts.run_sidecar_repeated_netem \
  --scenario-prefix sidecar_profile_robustness_v1 \
  --profile lan \
  --profile wan \
  --profile roaming \
  --policy fleetqox_csds \
  --policy fleetqox_predictive \
  --policy fleetqox_predictive_guarded \
  --policy fleetqox_predictive_lagrangian \
  --policy-label lag_adapt_003 \
  --closed-loop-feed
python3 -m scripts.run_sidecar_repeated_netem \
  --scenario-prefix sidecar_profiled_wan_v1 \
  --profile wan \
  --policy fleetqox_predictive_guarded \
  --policy fleetqox_predictive_lagrangian \
  --policy fleetqox_predictive_profiled \
  --policy-label lag_adapt_003 \
  --closed-loop-feed
python3 -m scripts.run_sidecar_repeated_netem \
  --scenario-prefix sidecar_intent_wan_v1 \
  --profile wan \
  --policy fleetqox_predictive_guarded \
  --policy fleetqox_predictive_profiled \
  --policy fleetqox_predictive_contextual \
  --policy fleetqox_predictive_intent \
  --closed-loop-feed
python3 -m scripts.run_sidecar_repeated_netem \
  --scenario-prefix sidecar_semantic_contract_wan_v1 \
  --profile wan \
  --policy fleetqox_predictive_profiled \
  --policy fleetqox_predictive_intent \
  --policy fleetqox_semantic_contract \
  --closed-loop-feed
python3 -m scripts.run_sidecar_repeated_netem \
  --scenario-prefix sidecar_semantic_contract_lossaware_compare_wan_v1 \
  --profile wan \
  --policy fleetqox_predictive_intent \
  --policy fleetqox_semantic_contract \
  --policy fleetqox_semantic_contract_lossaware \
  --closed-loop-feed
python3 -m scripts.run_sidecar_repeated_netem \
  --scenario-prefix sidecar_semantic_contract_adaptive_wan_v1 \
  --profile wan \
  --policy fleetqox_predictive_intent \
  --policy fleetqox_semantic_contract \
  --policy fleetqox_semantic_contract_lossaware \
  --policy fleetqox_semantic_contract_adaptive \
  --closed-loop-feed
python3 -m scripts.report_sidecar_repeated \
  --metrics results_sidecar_netem_closed_loop/sidecar_netem_closed_loop_v1_matrix_metrics.jsonl \
  --metrics results_sidecar_netem_lagrangian_v3_matrix/sidecar_netem_lagrangian_v3_matrix_matrix_metrics.jsonl \
  --markdown docs/SIDECAR_REPEATED_STATS_V1.md
python3 -m scripts.run_t2s_network_sim --prepare-inputs
python3 -m scripts.replay_trace traces/warehouse_50_constrained.csv
python3 -m scripts.run_t2e_netem --prepare-inputs
python3 -m scripts.run_t1_ros2_perf --plan-commands
python3 -m scripts.run_t1_ros2_perf --run
python3 -m scripts.run_t2e_ros2_netem --dry-run
python3 -m scripts.run_t2e_ros2_netem --all-rmws --components control,state --runtime-s 30 --run --analyze
python3 -m scripts.run_t2e_ros2_netem --rmw rmw_zenoh_cpp --runtime-s 30 --run --analyze
python3 -m scripts.run_ros2_docker_live_bridge --run --analyze --scenario ros2_live_bridge_t3_local_profiles_jerk_v1 --json
python3 -m scripts.run_ros2_docker_live_bridge \
  --run \
  --analyze \
  --all-rmws \
  --scenario ros2_live_bridge_t3_rmw_metadata_v2 \
  --policy fleetqox_semantic_contract_adaptive \
  --bridge-config experiments/ros2_live_bridge_tb4_typed_projection_v1.json \
  --seconds 2 \
  --rate-hz 20 \
  --bridge-max-batches 20 \
  --delay-ms 20 \
  --jitter-ms 5 \
  --loss-percent 0.5 \
  --rate-mbit 20 \
  --quality-gate-identity-mode wrapper \
  --quality-message-mode typed \
  --projection-quality-message-mode typed \
  --projection-quality-delivery-mode wrapper \
  --projection-quality-payload-mode compact \
  --json
python3 -m scripts.run_ros2_docker_live_bridge \
  --run \
  --analyze \
  --packet-format data_frame \
  --scenario ros2_live_bridge_t3_data_frame_v1 \
  --json
python3 -m scripts.run_rmw_boundary_smoke \
  --robot-count 2 \
  --samples-per-robot 3 \
  --skip-take robot_0000:2 \
  --json
python3 -m scripts.run_ros2_docker_live_bridge \
  --run \
  --analyze \
  --packet-format-matrix \
  --scenario ros2_live_bridge_t3_packet_format_compare_v1 \
  --policy fleetqox_semantic_contract_adaptive \
  --bridge-config experiments/ros2_live_bridge_tb4_typed_projection_v1.json \
  --seconds 2 \
  --rate-hz 20 \
  --bridge-max-batches 20 \
  --delay-ms 20 \
  --jitter-ms 5 \
  --loss-percent 0.5 \
  --rate-mbit 20 \
  --quality-gate-identity-mode wrapper \
  --quality-message-mode typed \
  --projection-quality-message-mode typed \
  --projection-quality-delivery-mode wrapper \
  --projection-quality-payload-mode compact \
  --json
python3 -m scripts.run_ros2_docker_live_bridge \
  --run \
  --analyze \
  --all-rmws \
  --packet-format-matrix \
  --scenario ros2_live_bridge_t3_packet_format_rmw_matrix_v1 \
  --policy fleetqox_semantic_contract_adaptive \
  --bridge-config experiments/ros2_live_bridge_tb4_typed_projection_v1.json \
  --seconds 2 \
  --rate-hz 20 \
  --bridge-max-batches 20 \
  --delay-ms 20 \
  --jitter-ms 5 \
  --loss-percent 0.5 \
  --rate-mbit 20 \
  --quality-gate-identity-mode wrapper \
  --quality-message-mode typed \
  --projection-quality-message-mode typed \
  --projection-quality-delivery-mode wrapper \
  --projection-quality-payload-mode compact \
  --json
python3 -m scripts.run_ros2_docker_live_bridge \
  --run \
  --analyze \
  --all-rmws \
  --packet-format-matrix \
  --seeds 7,13,29 \
  --profile wifi \
  --scenario ros2_live_bridge_t3_repeated_packet_wifi_3seed_v1 \
  --policy fleetqox_semantic_contract_adaptive \
  --bridge-config experiments/ros2_live_bridge_tb4_typed_projection_v1.json \
  --seconds 2 \
  --rate-hz 20 \
  --bridge-max-batches 20 \
  --quality-gate-identity-mode wrapper \
  --quality-message-mode typed \
  --projection-quality-message-mode typed \
  --projection-quality-delivery-mode wrapper \
  --projection-quality-payload-mode compact
python3 -m scripts.select_ros2_transport \
  --summary results_ros2_live_bridge/ros2_live_bridge_t3_repeated_packet_wifi_3seed_v1_summary.json \
  --summary results_ros2_live_bridge/ros2_live_bridge_t3_repeated_packet_wan_3seed_v1_summary.json \
  --summary results_ros2_live_bridge/ros2_live_bridge_t3_repeated_packet_roaming_3seed_v1_summary.json \
  --objective balanced_safety_utility \
  --summary-json results_ros2_live_bridge/profile_objective_selector_balanced_v1_summary.json \
  --markdown results_ros2_live_bridge/profile_objective_selector_balanced_v1_report.md
python3 -m scripts.run_ros2_sidecar_adapter \
  --scenario ros2_shim_transport_binding_runtime_smoke_v1 \
  --decision-log results_ros2_shim/transport_binding_runtime_smoke_decisions.jsonl \
  --transport-binding-summary results_ros2_live_bridge/profile_objective_selector_balanced_v1_summary.json \
  --transport-profile wifi \
  --json
python3 -m scripts.run_ros2_sidecar_adapter \
  --scenario ros2_shim_transport_binding_auto_profile_smoke_v1 \
  --decision-log results_ros2_shim/transport_binding_auto_profile_smoke_decisions.jsonl \
  --transport-binding-summary results_ros2_live_bridge/profile_objective_selector_balanced_v1_summary.json \
  --auto-transport-profile \
  --json
python3 -m scripts.run_ros2_sidecar_adapter \
  --scenario ros2_shim_transport_binding_adaptive_profile_smoke_v1 \
  --decision-log results_ros2_shim/transport_binding_adaptive_profile_smoke_decisions.jsonl \
  --transport-binding-summary results_ros2_live_bridge/profile_objective_selector_balanced_v1_summary.json \
  --adaptive-transport-profile \
  --json
python3 -m scripts.smoke_ros2_live_bridge_binding \
  --selector-summary results_ros2_live_bridge/profile_objective_selector_balanced_v1_summary.json \
  --mode adaptive \
  --process-runtime \
  --output results_ros2_live_bridge/live_bridge_adaptive_binding_runtime_smoke_v1.json \
  --json
python3 -m scripts.run_ros2_docker_live_bridge \
  --run \
  --analyze \
  --scenario ros2_live_bridge_t3_profile_transition_v1 \
  --bridge-config experiments/ros2_live_bridge_tb4_binding_v1.json \
  --transition-profile wifi \
  --transition-profile wan \
  --transition-profile roaming \
  --transition-segment-s 2 \
  --seconds 6 \
  --rate-hz 20 \
  --bridge-max-batches 120 \
  --json
python3 -m scripts.run_ros2_docker_live_bridge \
  --run \
  --analyze \
  --scenario ros2_live_bridge_t3_profile_transition_binding_matrix_v1 \
  --bridge-config experiments/ros2_live_bridge_tb4_binding_v1.json \
  --rmw rmw_zenoh_cpp \
  --transition-profile wifi \
  --transition-profile wan \
  --transition-profile roaming \
  --transition-segment-s 2 \
  --seconds 6 \
  --rate-hz 20 \
  --bridge-max-batches 120 \
  --transition-binding-matrix \
  --title "ROS 2 Live Transition Binding Matrix T3 V1" \
  --json
python3 -m scripts.run_ros2_docker_live_bridge \
  --run \
  --analyze \
  --scenario ros2_live_bridge_t3_profile_transition_binding_matrix_3seed_v1 \
  --bridge-config experiments/ros2_live_bridge_tb4_binding_v1.json \
  --rmw rmw_zenoh_cpp \
  --seeds 7,13,29 \
  --transition-profile wifi \
  --transition-profile wan \
  --transition-profile roaming \
  --transition-segment-s 2 \
  --seconds 6 \
  --rate-hz 20 \
  --bridge-max-batches 120 \
  --transition-binding-matrix \
  --transition-summary-json results_ros2_live_bridge/profile_transition_binding_matrix_3seed_summary.json \
  --transition-markdown results_ros2_live_bridge/profile_transition_binding_matrix_3seed_report.md \
  --title "ROS 2 Live Transition Binding Matrix 3-Seed T3 V1" \
  --json
python3 -m scripts.select_ros2_transport \
  --summary results_ros2_live_bridge/ros2_live_bridge_t3_repeated_packet_wifi_3seed_v1_summary.json \
  --summary results_ros2_live_bridge/ros2_live_bridge_t3_repeated_packet_wan_3seed_v1_summary.json \
  --summary results_ros2_live_bridge/ros2_live_bridge_t3_repeated_packet_roaming_3seed_v1_summary.json \
  --objective autonomy_safety \
  --summary-json results_ros2_live_bridge/profile_objective_selector_autonomy_v1_summary.json \
  --markdown results_ros2_live_bridge/profile_objective_selector_autonomy_v1_report.md
python3 -m scripts.run_ros2_docker_live_bridge \
  --run \
  --analyze \
  --dynamic-objective-transition-matrix \
  --scenario ros2_live_bridge_t3_dynamic_objective_transition_3seed_v1 \
  --bridge-config experiments/ros2_live_bridge_tb4_binding_v1.json \
  --rmw rmw_zenoh_cpp \
  --seeds 7,13,29 \
  --transition-profile wifi \
  --transition-profile wan \
  --transition-profile roaming \
  --transition-segment-s 2 \
  --seconds 6 \
  --rate-hz 20 \
  --bridge-max-batches 120 \
  --binding-objective-summary autonomy_safety:results_ros2_live_bridge/profile_objective_selector_autonomy_v1_summary.json \
  --binding-objective-schedule balanced_safety_utility@0,autonomy_safety@2,balanced_safety_utility@4 \
  --transition-summary-json results_ros2_live_bridge/dynamic_objective_transition_3seed_summary.json \
  --transition-markdown results_ros2_live_bridge/dynamic_objective_transition_3seed_report.md \
  --title "ROS 2 Live Dynamic Objective Transition 3-Seed T3 V1" \
  --json
python3 -m scripts.run_ros2_docker_live_bridge \
  --run \
  --analyze \
  --dynamic-objective-transition-matrix \
  --scenario ros2_live_bridge_t3_dynamic_objective_transition_2robot_3seed_v1 \
  --bridge-config experiments/ros2_live_bridge_tb4_binding_v1.json \
  --rmw rmw_zenoh_cpp \
  --seeds 7,13,29 \
  --robot-count 2 \
  --transition-profile wifi \
  --transition-profile wan \
  --transition-profile roaming \
  --transition-segment-s 2 \
  --seconds 6 \
  --rate-hz 12 \
  --bridge-max-batches 120 \
  --binding-objective-summary autonomy_safety:results_ros2_live_bridge/profile_objective_selector_autonomy_v1_summary.json \
  --binding-objective-schedule balanced_safety_utility@0,autonomy_safety@2,balanced_safety_utility@4 \
  --transition-summary-json results_ros2_live_bridge/dynamic_objective_transition_2robot_3seed_summary.json \
  --transition-markdown results_ros2_live_bridge/dynamic_objective_transition_2robot_3seed_report.md \
  --title "ROS 2 Live Dynamic Objective Transition 2-Robot 3-Seed T3 V1" \
  --json
python3 -m scripts.run_ros2_docker_live_bridge \
  --run \
  --analyze \
  --dynamic-objective-transition-matrix \
  --scenario ros2_live_bridge_t3_dynamic_objective_transition_2robot_local_services_3seed_v1 \
  --bridge-config experiments/ros2_live_bridge_tb4_binding_v1.json \
  --rmw rmw_zenoh_cpp \
  --seeds 7,13,29 \
  --robot-count 2 \
  --transition-profile wifi \
  --transition-profile wan \
  --transition-profile roaming \
  --transition-segment-s 2 \
  --seconds 6 \
  --rate-hz 12 \
  --bridge-max-batches 120 \
  --binding-objective-summary autonomy_safety:results_ros2_live_bridge/profile_objective_selector_autonomy_v1_summary.json \
  --binding-objective-schedule balanced_safety_utility@0,autonomy_safety@2,balanced_safety_utility@4 \
  --transition-summary-json results_ros2_live_bridge/dynamic_objective_transition_2robot_local_services_3seed_summary.json \
  --transition-markdown results_ros2_live_bridge/dynamic_objective_transition_2robot_local_services_3seed_report.md \
  --title "ROS 2 Live Dynamic Objective Transition 2-Robot Local Services 3-Seed T3 V1" \
  --json
python3 -m scripts.run_ros2_docker_live_bridge \
  --run \
  --analyze \
  --dynamic-objective-transition-matrix \
  --scenario ros2_live_bridge_t3_dynamic_objective_transition_2robot_fair_budget_3seed_v1 \
  --bridge-config experiments/ros2_live_bridge_tb4_binding_v1.json \
  --rmw rmw_zenoh_cpp \
  --seeds 7,13,29 \
  --robot-count 2 \
  --transition-profile wifi \
  --transition-profile wan \
  --transition-profile roaming \
  --transition-segment-s 2 \
  --seconds 6 \
  --rate-hz 12 \
  --bridge-max-batches 120 \
  --binding-objective-summary autonomy_safety:results_ros2_live_bridge/profile_objective_selector_autonomy_v1_summary.json \
  --binding-objective-schedule balanced_safety_utility@0,autonomy_safety@2,balanced_safety_utility@4 \
  --transition-summary-json results_ros2_live_bridge/dynamic_objective_transition_2robot_fair_budget_3seed_summary.json \
  --transition-markdown results_ros2_live_bridge/dynamic_objective_transition_2robot_fair_budget_3seed_report.md \
  --title "ROS 2 Live Dynamic Objective Transition 2-Robot Fair Budget 3-Seed T3 V1" \
  --json
python3 -m scripts.report_robot_budget_controller \
  --ticks 12 \
  --summary-json results_robot_budget/robot_budget_controller_smoke_summary.json \
  --markdown results_robot_budget/robot_budget_controller_smoke_report.md
python3 -m scripts.compare_ros2_robot_budget_summaries \
  --summary baseline:results_ros2_live_bridge/dynamic_objective_transition_2robot_fair_budget_3seed_summary.json \
  --summary budgeted:results_ros2_live_bridge/dynamic_objective_transition_2robot_budgeted_3seed_summary.json \
  --summary budgeted_floor:results_ros2_live_bridge/dynamic_objective_transition_2robot_budgeted_floor_3seed_summary.json \
  --summary tailrisk:results_ros2_live_bridge/dynamic_objective_transition_2robot_budgeted_tailrisk_3seed_summary.json \
  --summary-json results_ros2_live_bridge/robot_budget_policy_compare_summary.json \
  --markdown results_ros2_live_bridge/robot_budget_policy_compare_report.md \
  --title "ROS 2 Robot Budget Policy Comparison T3 V1"
python3 -m scripts.report_t2e_results \
  --metrics results_t2e_ros2/metrics.jsonl \
  --markdown results_t2e_ros2/report.md \
  --csv results_t2e_ros2/report.csv
python3 -m scripts.compare_t2e_baselines \
  --baseline wifi_v1:results_t2e_ros2/baseline_wifi_v1_metrics.jsonl:results_t2e_ros2/baseline_wifi_v1_summary.json \
  --baseline roaming_v1:results_t2e_ros2/baseline_roaming_v1_metrics.jsonl:results_t2e_ros2/baseline_roaming_v1_summary.json
python3 -m scripts.run_fleet_scale_benchmark --robots 10,25,50,100 --seeds 7,13,29 --seconds 30
python3 scripts/run_fleet_optimizer_probe.py --json
python3 scripts/run_online_fleet_plan_probe.py --json
python3 scripts/run_fleet_optimizer_runtime_probe.py --json
python3 scripts/run_rmw_docker_router_fleet_plan_probe.py --json
python3 scripts/run_rmw_docker_router_live_telemetry_plan_probe.py --json
python3 -m unittest discover -s tests
```

## Project Structure

```text
docs/
  KIM_CHI_NAM.md          Project mindset and non-negotiable principles
  RESEARCH_PLAN.md        Research gap, novelty, and evaluation plan
  ARCHITECTURE.md         FleetRMW/FleetQoX system architecture
  RMW_ROADMAP.md          Roadmap from simulator to ROS 2 RMW
  FLEETRMW_SAMPLE_ENVELOPE_V1.md  Native publisher/sample identity envelope
  FLEETRMW_DATA_FRAME_V1.md  Dependency-free FleetRMW data-plane frame codec
  ROS2_RMW_DATA_FRAME_MATRIX_V1.md  FastDDS/CycloneDDS/Zenoh frame-mode matrix
  ROS2_PROFILE_OBJECTIVE_SELECTOR_V1.md  Profile/objective-aware packet/RMW selector
  FLEET_LEVEL_QOS_QOE_OPTIMIZER_V1.md  Fleet-level path optimizer over RMW/router telemetry
  ONLINE_FLEET_PATH_PLAN_CONTROLLER_V1.md  Online telemetry-to-path-plan controller probe
  FLEET_OPTIMIZER_RUNTIME_ACTUATION_V1.md  Sidecar runtime optimizer actuation probe
  RMW_ROUTER_FLEET_PLAN_PROBE_V1.md  C++ RMW path-ID to router-peer actuation probe
  RMW_ROUTER_LIVE_TELEMETRY_PLAN_PROBE_V1.md  Router telemetry to live RMW plan update probe
  ROS2_LIVE_CONTINUOUS_BINDING_V1.md  Live bridge adaptive transport binding refresh
  ROS2_LIVE_PROFILE_TRANSITION_T3_V1.md  Docker T3 Wi-Fi/WAN/roaming live transition evidence
  ROS2_LIVE_PROFILE_TRANSITION_BASELINES_T3_V1.md  Adaptive-vs-static live transition binding matrix
  ROS2_LIVE_PROFILE_TRANSITION_BINDING_3SEED_T3_V1.md  Three-seed adaptive-vs-static transition binding evidence
  ROS2_LIVE_DYNAMIC_OBJECTIVE_BINDING_T3_V1.md  Three-seed live profile/objective transition evidence
  ROS2_LIVE_DYNAMIC_OBJECTIVE_MULTI_ROBOT_T3_V1.md  Two-robot live profile/objective transition and local-service evidence
  ROBOT_BUDGET_AWARE_CONTROLLER_V1.md  Per-robot virtual-queue budget-aware admission controller
  ROS2_PACKET_FORMAT_COMPARE_V1.md  Legacy JSON vs FleetRMW data-frame comparison
  ROS2_PACKET_FORMAT_RMW_MATRIX_V1.md  2 x 3 packet-format/RMW transition matrix
  ROS2_REPEATED_PACKET_FORMAT_RMW_HARNESS_V1.md  Repeated seed/profile ROS 2 matrix harness
  ROS2_REPEATED_PACKET_FORMAT_RMW_WIFI_3SEED_V1.md  Full 3-seed Wi-Fi packet-format/RMW evidence
  ROS2_REPEATED_PACKET_FORMAT_RMW_WAN_3SEED_V1.md  Full 3-seed WAN packet-format/RMW evidence
  ROS2_REPEATED_PACKET_FORMAT_RMW_ROAMING_3SEED_V1.md  Full 3-seed roaming packet-format/RMW evidence
  RMW_SAMPLE_CONTRACT_V1.md  Dependency-free post-admission sample contract
  RMW_MULTI_ROBOT_LIVE_STOCHASTIC_NETEM_SWEEP_V1.md  Live RMW stochastic loss-envelope sweep
  RMW_MULTI_ROBOT_LIVE_STOCHASTIC_NETEM_ABLATION_V1.md  Proactive repair ablation over the live stochastic sweep
  RMW_LIVE_BASELINE_COMPARISON_V1.md  Indirect FleetRMW-native vs ROS 2 live-bridge baseline map
  ROS2_DIRECT_RMW_NETEM_MATRIX_V1.md  Direct ROS 2 RMW pub/sub netem baseline seed
  ROS2_RMW_SOURCE_METADATA_MATRIX_V1.md  FastDDS/CycloneDDS/Zenoh callback metadata matrix
  EXPERIMENTAL_RESULTS_V1.md  First evidence snapshot and research gaps
  SIDECAR_REPLAY_V1.md    Sidecar trace/replay evidence
  SIDECAR_RUNTIME_V1.md   Live sidecar TCP/UDP runtime smoke
  SIDECAR_NETEM_V1.md     Live sidecar through Docker/tc-netem
  SIDECAR_NETEM_MATRIX_V1.md  FIFO/static/CSDS/predictive sidecar-netem matrix
  SIDECAR_NETEM_MATRIX_V2.md  Adds risk-guarded predictive sidecar-netem matrix
  SIDECAR_CLOSED_LOOP_V1.md   Closed-loop sidecar feedback over Docker/tc-netem
  SIDECAR_LAGRANGIAN_V1.md    Soft risk-constrained predictive admission
  LAGRANGIAN_SWEEP_V1.md      Offline Lagrangian parameter sweep and risk-reset signal
  LAGRANGIAN_OUTCOME_ADAPTATION_V1.md  Outcome-driven Lagrangian update proposal
  SIDECAR_LAGRANGIAN_VARIANTS_NETEM_V1.md  Labeled Lagrangian netem variants
  SIDECAR_LAGRANGIAN_OUTCOME_ADAPTATION_NETEM_V2.md  Adapted Lagrangian netem evidence
  SIDECAR_LAG_ADAPT_002_5SEED_NETEM.md  Five-seed adapted Lagrangian evidence
  LAGRANGIAN_OUTCOME_ADAPTATION_V3.md  Second measured Lagrangian update proposal
  SIDECAR_LAGRANGIAN_OUTCOME_ADAPTATION_NETEM_V3_5SEED.md  Five-seed lag_adapt_003 evidence
  SIDECAR_PROFILE_ROBUSTNESS_V1.md  LAN/WAN/roaming profile robustness smoke
  SIDECAR_PROFILE_AWARE_LAGRANGIAN_V1.md  Profile-aware Lagrangian controller evidence
  SIDECAR_INTENT_WAN_V1.md  Control-intent WAN feasibility evidence
  ROS2_SHIM_BOUNDARY_V1.md  Dependency-free ROS 2 sample/QoS adapter boundary
  ROS2_LIVE_BRIDGE_V1.md  Live rclpy-to-sidecar ingress bridge
  ROS2_EGRESS_BRIDGE_V1.md  Sidecar UDP to ROS 2 egress envelope and typed Twist bridge
  ROS2_LOCAL_CONTROL_LEASE_V1.md  Robot-side lease gate for typed cmd_vel
  ROS2_PROJECTION_QUALITY_GATE_V1.md  Consumer-side gate for typed state/scan projections
  ROS2_DOCKER_LIVE_BRIDGE_T3.md  Dockerized ROS 2 live integration harness
  ROS2_8ROBOT_LIVELINESS_ACK_HORIZON_V1.md  8-robot source ACK/NACK recovery horizon evidence
  SEMANTIC_CONTRACT_V1.md  Feasibility-aware semantic contract layer
  SIDECAR_SEMANTIC_CONTRACT_WAN_V1.md  Semantic-contract scheduler WAN smoke
  SIDECAR_SEMANTIC_CONTRACT_LOSSAWARE_COMPARE_WAN_V1.md  Loss-aware semantic scheduler comparison
  SIDECAR_SEMANTIC_CONTRACT_ADAPTIVE_WAN_V1.md  Adaptive semantic variant selector comparison
  SIDECAR_SEMANTIC_CONTRACT_SUPERVISORY_ROAMING_PREFLIGHT_V1.md  Supervisory intent roaming preflight
  SIDECAR_SEMANTIC_CONTRACT_ADAPTIVE_ROAMING_V1.md  Supervisory/adaptive roaming netem evidence
  SIDECAR_REPEATED_STATS_V1.md  Repeated-run CI and Pareto evidence

fleetqox/
  model.py                QoX, flow, network, and decision data models
  control_plane.py        Predictive, guarded, Lagrangian, profile/contextual, intent, semantic-contract, and adaptive semantic schedulers
  semantic_contract.py    Flow contracts, semantic transforms, and feasibility certificates
  lagrangian_sweep.py     Offline parameter sweep for Lagrangian admission
  lagrangian_adaptation.py  Outcome-driven Lagrangian variant adaptation
  local_control_lease.py  Robot-side typed command lease evaluator
  projection_quality_gate.py  Consumer-side typed projection quality evaluator
  rmw_contract.py         Post-admission FleetRMW sample identity/delivery contract
  rmw_socket.py           UDP socket-backed FleetRMW data-frame and ACK/NACK boundary
  rmw_transport_loop.py   Persistent multi-stream socket loop with NACK retransmit
  sidecar_contract.py     Sidecar/RMW-shim decision trace contract
  sidecar_egress.py       Dependency-free sidecar packet decode and egress routing
  sidecar_runtime.py      TCP sidecar skeleton with pluggable policies and UDP emission
  sidecar_metrics.py      Runtime decision/receive, per-robot QoS, and budget metric analysis
  sidecar_repeated.py     Repeated-run sidecar statistics and Pareto analysis
  transport_selector.py   Profile/objective-aware packet-format/RMW selector
  scheduler.py            Causal Semantic Deadline Scheduler
  ros2_shim.py            Dependency-free ROS 2 sample/QoS to sidecar batch adapter
  ros2_live_bridge.py     Live ROS 2 callback buffer and sidecar TCP client
  simulator.py            Fleet workload and baseline comparison
  comparison.py           Cross-baseline report helpers
  fleet_scale.py          Fleet-scale benchmark matrix helpers

experiments/
  local_controller_profiles_v1.json  Robot/controller lease safety profiles
  ros2_live_bridge_tb4_binding_v1.json  ROS 2 live bridge config with adaptive binding
  ros2_live_bridge_tb4_typed_projection_v1.json  ROS 2 typed projection coverage config

scripts/
  run_benchmark.py        CLI benchmark entry point
  compare_t2e_baselines.py  Compare ROS 2/netem baseline reports
  run_fleet_scale_benchmark.py  Run local fleet-scale benchmark matrix
  run_sidecar_netem.py    Run live sidecar policies through Docker/tc-netem
  run_lagrangian_sweep.py Run offline Lagrangian parameter sweeps
  adapt_lagrangian_from_netem.py  Generate next Lagrangian variant from measured netem outcomes
  run_sidecar_repeated_netem.py  Run repeated sidecar-netem sweeps over seeds
  report_sidecar_repeated.py  Summarize sidecar metrics across repeated runs
  select_ros2_transport.py    Select packet-format/RMW policy from repeated summaries
  report_robot_budget_controller.py  Offline smoke for per-robot budget-aware admission
  compare_ros2_robot_budget_summaries.py  Compare ROS 2 per-robot budget policy summaries
  smoke_ros2_live_bridge_binding.py  Dependency-free live bridge binding refresh smoke
  apply_netem_transition.py   Apply timed tc/netem profile transitions inside Docker
  run_ros2_docker_live_bridge.py  Docker ROS 2 live bridge, RMW/packet matrices, transition, multi-robot, and binding baseline runner
  feed_sidecar_closed_loop.py  Feed sidecar with per-flow action feedback
  run_ros2_egress_bridge.py    Publish sidecar UDP events back into ROS 2 topics
  run_ros2_local_controller_lease.py  Gate typed Twist with namespace-aware local control leases
  run_ros2_projection_quality_gate.py Gate typed odom/scan from namespace-aware wrapped or identity-carrying projection quality
  run_ros2_string_monitor.py   Monitor ROS 2 String and typed egress topics across robot namespaces in Docker T3
  run_rmw_socket_smoke.py      Exercise FleetRMW data-frame and ACK/NACK over UDP sockets
  run_rmw_docker_multi_robot_live_stochastic_netem_sweep.py  Sweep live RMW Docker netem loss scales
  run_rmw_docker_multi_robot_live_stochastic_netem_ablation.py  Compare proactive repair modes over the live stochastic sweep
  compare_fleetrmw_live_baselines.py  Normalize FleetRMW-native and ROS 2 live-bridge evidence with comparability caveats
  run_ros2_direct_rmw_netem_probe.py  Direct ROS 2 pub/sub RMW baseline under one netem profile
  run_ros2_direct_rmw_netem_matrix.py  Matrix runner for direct ROS 2 RMW netem baselines

ros2_ws/src/
  fleetrmw_interfaces/         ROS 2 message wrappers for FleetRMW projection quality
  rmw_fleetqox_cpp/            C++ FleetRMW transport-boundary reference package
```

## Core Thesis

ROS 2 middleware for robot fleets should not merely deliver topics. It should
prioritize information by the amount of task risk it reduces under real network
constraints.

FleetRMW therefore treats DDS, Zenoh, QUIC, WebRTC, and shared memory as data
plane options. The research contribution is the control plane: causal-semantic
QoX scheduling for large ROS 2 robot fleets.

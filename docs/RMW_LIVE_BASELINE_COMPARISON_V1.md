# FleetRMW Live Baseline Comparison V1

This artifact normalizes the current FleetRMW-native live evidence and existing
ROS 2 live-bridge RMW baselines into one comparison map.

- Script: `scripts/compare_fleetrmw_live_baselines.py`
- Summary:
  `results_rmw_socket/fleetrmw_live_baseline_comparison_summary.json`
- Report:
  `results_rmw_socket/fleetrmw_live_baseline_comparison_report.md`
- Schema: `fleetrmw.live_baseline_comparison.v1`

## Scope

This is not a direct superiority benchmark. It is a baseline map and research
gap register.

The FleetRMW side uses the live `rmw_fleetqox_cpp`
publisher-router-subscriber topology under stochastic Docker `tc netem`.
The comparison also includes the matched four-robot FleetRMW telemetry matrix
with deadline-sequence repair enabled.

The ROS 2 baseline side uses existing live-bridge packet-format/RMW summaries
for Wi-Fi, WAN, and roaming profiles. Those rows compare Fast DDS, Cyclone DDS,
and Zenoh through the sidecar/egress live bridge, not through the FleetRMW
router topology.

When direct ROS 2 RMW netem matrix summaries are present, the comparison also
includes them as `direct_single_path_pubsub` seed rows. These rows are closer to
the desired same-envelope baseline, but still do not include FleetRMW router
redundancy or the QoE path planner.

Because the topology, workload, and metric definitions differ, the report keeps
`direct_claim_allowed=false`.

## Current Evidence

The current FleetRMW-native ablation winner is
`rmw_fleetqox_cpp/control_state`:

- `27/27` OK rows;
- maximum all-profile OK loss scale `0.5`;
- control mean latency `76.18 ms`;
- state mean latency `49.11 ms`;
- repair cost `14.30`.

Existing ROS 2 live-bridge profile winners are:

- Wi-Fi: `data_frame/rmw_zenoh_cpp`;
- WAN: `event_json/rmw_zenoh_cpp`;
- roaming: `event_json/rmw_zenoh_cpp`.

The profile winners changing between Wi-Fi and WAN/roaming is itself important:
RMW and packet-format choice remains profile-dependent, which supports a
fleet-aware middleware/control-plane design rather than a single static RMW
choice.

The full direct ROS 2 RMW matrix now exists for the same named profiles and
seeds.  The current stored result is `16/27` OK:

- Fast DDS direct pub/sub: `7/9` OK;
- Cyclone DDS direct pub/sub: `9/9` OK;
- Zenoh direct pub/sub: `0/9` OK in this harness, with
  `delivery_failed:missing_control_state` after the publisher observed zero
  subscriptions in the debug probe;
- qdisc was applied in all `27/27` direct rows.

The matched four-robot FleetRMW router/redundancy matrix now uses the same
profiles, seeds `7,13,29`, loss scale `0.1`, and robot/topic count as the
direct RMW four-robot matrix. It completes `9/9` rows OK with qdisc applied in
`9/9`, application payload delivery `12/12` for control and `12/12` for state
in every row, and router status OK in every row. The active repair envelope is
`deadline_sequence_repair_v1`: publishers gate application payload release on a
pre-payload route-warmup ACK or a `2000 ms` timeout, repeat the semantic
`one,two,three` application cycle twice for route-repair coverage, then emit
five `terminal_guard` sequences after the three required application samples.
Routers require sequence `4` and dwell for `4000 ms` to forward later guard
repeats, while subscribers can emit idle missing-range ACK/NACK repair feedback
and success still only requires the compact route-warmup plus application
payload set.

This improves the baseline map substantially, but it still does not authorize a
final superiority claim because the direct rows are single-path pub/sub rows.
They do not include FleetRMW's router, proactive repair, route advertisements,
source-sequence ACK/NACK, or QoE path planner.

## Research Gap

The next paper-grade comparison must equalize topology and metric semantics
across:

- `rmw_fleetqox_cpp`;
- Fast DDS;
- Cyclone DDS;
- Zenoh.

The missing piece is no longer package availability, a one-RMW smoke, or the
four-robot FleetRMW matched workload. The remaining gap is stricter topology
equivalence: either run DDS/Zenoh through comparable router/repair semantics,
or make the direct-RMW rows expose equivalent terminal-horizon, ACK/NACK,
QoE, and route-control metrics.

## Example

```bash
python3 scripts/compare_fleetrmw_live_baselines.py --json
```

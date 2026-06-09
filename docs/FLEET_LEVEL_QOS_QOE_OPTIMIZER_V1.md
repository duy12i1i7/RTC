# Fleet-Level QoS/QoE Optimizer V1

This artifact introduces the fleet-level path optimizer above the RMW/router data plane.

- Summary: `results_fleet_optimizer/fleet_optimizer_probe_summary.json`
- Robots: `16`
- Capacity bytes/tick: `58000`

## Policy Comparison

| policy | delivery | deadline success | control fairness | QoE utility | redundant | drops | bytes |
|---|---:|---:|---:|---:|---:|---:|---:|
| static_primary | 0.8200 | 0.6250 | 1.0000 | 28.3064 | 0 | 20 | 57960 |
| fleet_qoe_optimizer | 0.9768 | 1.0000 | 1.0000 | 70.5969 | 16 | 13 | 57700 |

## Improvement

- `expected_delivery_delta`: `0.1568`
- `deadline_success_delta`: `0.3750`
- `qoe_utility_delta`: `42.2905`
- `control_fairness_delta`: `0.0000`

## Interpretation

- The optimizer scores each path using loss, latency, jitter, NACK rate, deadline misses, and utilization.
- Robot-level QoE debt increases utility for robots with weak recent delivery or deadline performance.
- The policy can choose unicast, redundant routing, semantic degradation, or defer/drop under fleet capacity pressure.

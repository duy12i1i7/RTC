# Sidecar Semantic Contract Supervisory Roaming Preflight V1

## Purpose

The attempted Docker/tc-netem roaming sweep could not run because the Docker
daemon was unavailable. Before waiting for Docker, this preflight checks the
control-plane decision logic on the same roaming profile:

```text
capacity = 70 KB/s
rtt      = 160 ms
jitter   = 25 ms
loss     = 3%
seeds    = 7, 13, 29, 41, 53
```

## Result

The preflight exposed a semantic feasibility gap: the original short control
lifespan is smaller than the path tail, so raw `/cmd_vel` and short
`control_intent` are not meaningful. `supervisory_intent` fixes that by sending
a compact goal/constraint lease with its own validity horizon.

| policy | mean tx | mean control tx | mean bytes tx | roaming behavior |
| --- | ---: | ---: | ---: | --- |
| `fleetqox_predictive_intent` | 57.4 | 0.0 | 8388.6 | drops all control under this profile |
| `fleetqox_semantic_contract` | 91.2 | 37.8 | 15534.0 | sends supervisory control but admits more non-control traffic |
| `fleetqox_semantic_contract_lossaware` | 39.8 | 37.8 | 2280.4 | keeps supervisory control and sheds most non-control traffic |
| `fleetqox_semantic_contract_adaptive` | 40.0 | 37.8 | 2301.8 | selects tail-shield almost everywhere, preserving supervisory control |

## Interpretation

This is not a replacement for Docker/netem metrics because it has no packet
loss, latency, or receiver-side deadline measurements. It is still useful
because it validates the control-plane semantic change before the expensive
network run: under roaming assumptions, the old intent wrapper delivers no
control decisions, while the semantic-contract policies produce
`send_supervisory_intent` packets.

The next Docker run should re-run the roaming profile after Docker is available
and verify whether supervisory intents improve measured control delivery and
deadline behavior under actual `tc netem`.

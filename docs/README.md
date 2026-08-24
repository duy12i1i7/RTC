# FleetRMW Documentation

The root [README](../README.md) is the canonical project overview and current
status. This directory contains only material needed to understand, implement,
verify, and finish the project.

## Start here

- [Architecture](ARCHITECTURE.md) — components, planes, state, and data flow.
- [Status and Roadmap](STATUS_AND_ROADMAP.md) — detailed completion gates,
  priorities, and estimates.
- [Development](DEVELOPMENT.md) — build, test, Docker, artifacts, and
  contribution discipline.
- [Integration and Validation](INTEGRATION_AND_VALIDATION.md) — Nav2, RMF,
  simulators, baselines, stress, and HIL scope.
- [Security](SECURITY.md) — implemented controls, threat boundary, and open
  production gaps.

## RMW and protocol contracts

- [Minimal RMW Boundary](RMW_MINIMAL_BOUNDARY_V1.md)
- [FleetRMW Data Frame](FLEETRMW_DATA_FRAME_V1.md)
- [Sample Envelope](FLEETRMW_SAMPLE_ENVELOPE_V1.md)
- [Sample Contract](RMW_SAMPLE_CONTRACT_V1.md)
- [ACK/NACK](RMW_ACK_NACK_V1.md)
- [Action Frame Contract](RMW_ACTION_FRAME_CONTRACT_V1.md)
- [Action QoS](RMW_ACTION_QOS_V1.md)
- [Service QoS](RMW_SERVICE_QOS_V1.md)
- [Semantic Contract](SEMANTIC_CONTRACT_V1.md)
- [Trace Schema](TRACE_SCHEMA.md)

## Fleet control

- [Multi-Robot QoS Scheduler](RMW_MULTI_ROBOT_QOS_SCHEDULER_V1.md)
- [Robot Budget-Aware Controller](ROBOT_BUDGET_AWARE_CONTROLLER_V1.md)
- [ROS 2 Profile/Objective Selector](ROS2_PROFILE_OBJECTIVE_SELECTOR_V1.md)

## Evidence

- [Experimental Methodology](EXPERIMENTAL_METHODOLOGY.md)
- [Experimental Results](EXPERIMENTAL_RESULTS_V1.md)

Generated reports, traces, build trees, and logs belong in ignored
`results_*`, `traces_*`, `build`, `install`, or `log` directories. They are not
source documentation and must not be committed.

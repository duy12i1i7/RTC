"""Run the FleetRMW sidecar runtime skeleton."""

from __future__ import annotations

import argparse
import os
from pathlib import Path

from fleetqox.sidecar_runtime import RuntimeConfig, SIDECAR_POLICIES, SidecarRuntime, serve_tcp


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--listen-host", default="127.0.0.1")
    parser.add_argument("--listen-port", type=int, default=8765)
    parser.add_argument("--udp-host", default="127.0.0.1")
    parser.add_argument("--udp-port", type=int, default=9100)
    parser.add_argument(
        "--policy",
        choices=SIDECAR_POLICIES,
        default="fleetqox_predictive",
    )
    parser.add_argument("--policy-label", default=os.environ.get("SIDECAR_POLICY_LABEL"))
    parser.add_argument(
        "--lagrangian-deadline-risk-budget",
        type=float,
        default=_env_float("SIDECAR_LAGRANGIAN_DEADLINE_RISK_BUDGET"),
    )
    parser.add_argument(
        "--lagrangian-initial-deadline-lambda",
        type=float,
        default=_env_float("SIDECAR_LAGRANGIAN_INITIAL_DEADLINE_LAMBDA"),
    )
    parser.add_argument(
        "--lagrangian-risk-barrier-start",
        type=float,
        default=_env_float("SIDECAR_LAGRANGIAN_RISK_BARRIER_START"),
    )
    parser.add_argument(
        "--lagrangian-risk-barrier-scale",
        type=float,
        default=_env_float("SIDECAR_LAGRANGIAN_RISK_BARRIER_SCALE"),
    )
    parser.add_argument(
        "--lagrangian-deadline-drop-risk",
        type=float,
        default=_env_float("SIDECAR_LAGRANGIAN_DEADLINE_DROP_RISK"),
    )
    parser.add_argument("--decision-log", type=Path, default=Path("results_sidecar_runtime/decisions.jsonl"))
    parser.add_argument(
        "--packet-format",
        choices=("event_json", "data_frame"),
        default=os.environ.get("SIDECAR_PACKET_FORMAT", "event_json"),
    )
    parser.add_argument(
        "--transport-volatility-probe-max-per-tick",
        type=int,
        default=_env_int("SIDECAR_TRANSPORT_VOLATILITY_PROBE_MAX_PER_TICK"),
    )
    parser.add_argument(
        "--transport-volatility-probe-quota-scale",
        type=float,
        default=_env_float("SIDECAR_TRANSPORT_VOLATILITY_PROBE_QUOTA_SCALE"),
    )
    parser.add_argument(
        "--transport-volatility-probe-max-per-robot-per-tick",
        type=int,
        default=_env_int("SIDECAR_TRANSPORT_VOLATILITY_PROBE_MAX_PER_ROBOT_PER_TICK"),
    )
    parser.add_argument(
        "--control-lease-adaptive-redundancy",
        choices=("auto", "on", "off"),
        default=os.environ.get("SIDECAR_CONTROL_LEASE_ADAPTIVE_REDUNDANCY", "auto"),
    )
    parser.add_argument(
        "--control-lease-adaptive-max-redundancy",
        type=int,
        default=_env_int("SIDECAR_CONTROL_LEASE_ADAPTIVE_MAX_REDUNDANCY"),
    )
    parser.add_argument(
        "--control-lease-adaptive-extra-max-per-tick",
        type=int,
        default=_env_int("SIDECAR_CONTROL_LEASE_ADAPTIVE_EXTRA_MAX_PER_TICK"),
    )
    parser.add_argument(
        "--control-lease-adaptive-extra-quota-scale",
        type=float,
        default=_env_float("SIDECAR_CONTROL_LEASE_ADAPTIVE_EXTRA_QUOTA_SCALE"),
    )
    parser.add_argument(
        "--control-lease-residual-loss-budget",
        type=float,
        default=_env_float("SIDECAR_CONTROL_LEASE_RESIDUAL_LOSS_BUDGET"),
    )
    parser.add_argument(
        "--control-lease-drain-grace-s",
        type=float,
        default=_env_float("SIDECAR_CONTROL_LEASE_DRAIN_GRACE_S"),
    )
    parser.add_argument(
        "--control-lease-terminal-replay-attempts",
        type=int,
        default=_env_int("SIDECAR_CONTROL_LEASE_TERMINAL_REPLAY_ATTEMPTS"),
    )
    parser.add_argument(
        "--control-lease-terminal-replay-interval-s",
        type=float,
        default=_env_float("SIDECAR_CONTROL_LEASE_TERMINAL_REPLAY_INTERVAL_S"),
    )
    parser.add_argument(
        "--control-lease-terminal-replay-history-per-robot",
        type=int,
        default=_env_int("SIDECAR_CONTROL_LEASE_TERMINAL_REPLAY_HISTORY_PER_ROBOT"),
    )
    parser.add_argument(
        "--control-lease-ack-retransmit",
        choices=("on", "off"),
        default=os.environ.get("SIDECAR_CONTROL_LEASE_ACK_RETRANSMIT", "off"),
    )
    parser.add_argument(
        "--control-lease-ack-retransmit-max-attempts",
        type=int,
        default=_env_int("SIDECAR_CONTROL_LEASE_ACK_RETRANSMIT_MAX_ATTEMPTS"),
    )
    parser.add_argument(
        "--control-lease-ack-retransmit-max-per-tick",
        type=int,
        default=_env_int("SIDECAR_CONTROL_LEASE_ACK_RETRANSMIT_MAX_PER_TICK"),
    )
    parser.add_argument(
        "--control-lease-ack-retransmit-timeout-ms",
        type=float,
        default=_env_float("SIDECAR_CONTROL_LEASE_ACK_RETRANSMIT_TIMEOUT_MS"),
    )
    parser.add_argument(
        "--control-lease-ack-retransmit-horizon-ms",
        type=float,
        default=_env_float("SIDECAR_CONTROL_LEASE_ACK_RETRANSMIT_HORIZON_MS"),
    )
    parser.add_argument(
        "--control-lease-ack-history-per-robot",
        type=int,
        default=_env_int("SIDECAR_CONTROL_LEASE_ACK_HISTORY_PER_ROBOT"),
    )
    parser.add_argument(
        "--control-lease-transition-guard",
        choices=("on", "off"),
        default=os.environ.get("SIDECAR_CONTROL_LEASE_TRANSITION_GUARD", "on"),
    )
    parser.add_argument(
        "--control-lease-transition-guard-min-confidence",
        type=float,
        default=_env_float("SIDECAR_CONTROL_LEASE_TRANSITION_GUARD_MIN_CONFIDENCE"),
    )
    parser.add_argument(
        "--control-lease-transition-guard-min-margin",
        type=float,
        default=_env_float("SIDECAR_CONTROL_LEASE_TRANSITION_GUARD_MIN_MARGIN"),
    )
    parser.add_argument(
        "--control-lease-transition-guard-max-dwell-ticks",
        type=int,
        default=_env_int("SIDECAR_CONTROL_LEASE_TRANSITION_GUARD_MAX_DWELL_TICKS"),
    )
    parser.add_argument(
        "--control-lease-transition-guard-redundancy",
        type=int,
        default=_env_int("SIDECAR_CONTROL_LEASE_TRANSITION_GUARD_REDUNDANCY"),
    )
    parser.add_argument("--idle-timeout-s", type=float, default=30.0)
    parser.add_argument("--max-runtime-s", type=float, default=300.0)
    args = parser.parse_args()

    runtime = SidecarRuntime(
        RuntimeConfig(
            udp_host=args.udp_host,
            udp_port=args.udp_port,
            policy=args.policy,
            policy_label=args.policy_label,
            lagrangian_overrides=_lagrangian_overrides(args),
            decision_log=args.decision_log,
            packet_format=args.packet_format,
            transport_volatility_probe_max_per_tick=(
                args.transport_volatility_probe_max_per_tick
            ),
            transport_volatility_probe_quota_scale=(
                args.transport_volatility_probe_quota_scale
                if args.transport_volatility_probe_quota_scale is not None
                else RuntimeConfig.transport_volatility_probe_quota_scale
            ),
            transport_volatility_probe_max_per_robot_per_tick=(
                args.transport_volatility_probe_max_per_robot_per_tick
                if args.transport_volatility_probe_max_per_robot_per_tick is not None
                else RuntimeConfig.transport_volatility_probe_max_per_robot_per_tick
            ),
            control_lease_adaptive_redundancy=_adaptive_redundancy_mode(
                args.control_lease_adaptive_redundancy
            ),
            control_lease_adaptive_max_redundancy=(
                args.control_lease_adaptive_max_redundancy
                if args.control_lease_adaptive_max_redundancy is not None
                else RuntimeConfig.control_lease_adaptive_max_redundancy
            ),
            control_lease_adaptive_extra_max_per_tick=(
                args.control_lease_adaptive_extra_max_per_tick
            ),
            control_lease_adaptive_extra_quota_scale=(
                args.control_lease_adaptive_extra_quota_scale
                if args.control_lease_adaptive_extra_quota_scale is not None
                else RuntimeConfig.control_lease_adaptive_extra_quota_scale
            ),
            control_lease_residual_loss_budget=(
                args.control_lease_residual_loss_budget
                if args.control_lease_residual_loss_budget is not None
                else RuntimeConfig.control_lease_residual_loss_budget
            ),
            control_lease_drain_grace_s=(
                args.control_lease_drain_grace_s
                if args.control_lease_drain_grace_s is not None
                else RuntimeConfig.control_lease_drain_grace_s
            ),
            control_lease_terminal_replay_attempts=(
                args.control_lease_terminal_replay_attempts
                if args.control_lease_terminal_replay_attempts is not None
                else RuntimeConfig.control_lease_terminal_replay_attempts
            ),
            control_lease_terminal_replay_interval_s=(
                args.control_lease_terminal_replay_interval_s
                if args.control_lease_terminal_replay_interval_s is not None
                else RuntimeConfig.control_lease_terminal_replay_interval_s
            ),
            control_lease_terminal_replay_history_per_robot=(
                args.control_lease_terminal_replay_history_per_robot
                if args.control_lease_terminal_replay_history_per_robot is not None
                else RuntimeConfig.control_lease_terminal_replay_history_per_robot
            ),
            control_lease_ack_retransmit_enabled=(
                _on_off(args.control_lease_ack_retransmit)
            ),
            control_lease_ack_retransmit_max_attempts=(
                args.control_lease_ack_retransmit_max_attempts
                if args.control_lease_ack_retransmit_max_attempts is not None
                else RuntimeConfig.control_lease_ack_retransmit_max_attempts
            ),
            control_lease_ack_retransmit_max_per_tick=(
                args.control_lease_ack_retransmit_max_per_tick
            ),
            control_lease_ack_retransmit_timeout_ms=(
                args.control_lease_ack_retransmit_timeout_ms
            ),
            control_lease_ack_retransmit_horizon_ms=(
                args.control_lease_ack_retransmit_horizon_ms
            ),
            control_lease_ack_history_per_robot=(
                args.control_lease_ack_history_per_robot
                if args.control_lease_ack_history_per_robot is not None
                else RuntimeConfig.control_lease_ack_history_per_robot
            ),
            control_lease_transition_guard_enabled=(
                _on_off(args.control_lease_transition_guard)
            ),
            control_lease_transition_guard_min_confidence=(
                args.control_lease_transition_guard_min_confidence
                if args.control_lease_transition_guard_min_confidence is not None
                else RuntimeConfig.control_lease_transition_guard_min_confidence
            ),
            control_lease_transition_guard_min_margin=(
                args.control_lease_transition_guard_min_margin
                if args.control_lease_transition_guard_min_margin is not None
                else RuntimeConfig.control_lease_transition_guard_min_margin
            ),
            control_lease_transition_guard_max_dwell_ticks=(
                args.control_lease_transition_guard_max_dwell_ticks
                if args.control_lease_transition_guard_max_dwell_ticks is not None
                else RuntimeConfig.control_lease_transition_guard_max_dwell_ticks
            ),
            control_lease_transition_guard_redundancy=(
                args.control_lease_transition_guard_redundancy
                if args.control_lease_transition_guard_redundancy is not None
                else RuntimeConfig.control_lease_transition_guard_redundancy
            ),
        )
    )
    try:
        serve_tcp(
            host=args.listen_host,
            port=args.listen_port,
            runtime=runtime,
            idle_timeout_s=args.idle_timeout_s,
            max_runtime_s=args.max_runtime_s,
        )
    finally:
        runtime.close()


def _lagrangian_overrides(args: argparse.Namespace) -> dict[str, float]:
    fields = {
        "deadline_risk_budget": args.lagrangian_deadline_risk_budget,
        "initial_deadline_lambda": args.lagrangian_initial_deadline_lambda,
        "risk_barrier_start": args.lagrangian_risk_barrier_start,
        "risk_barrier_scale": args.lagrangian_risk_barrier_scale,
        "deadline_drop_risk": args.lagrangian_deadline_drop_risk,
    }
    return {key: value for key, value in fields.items() if value is not None}


def _adaptive_redundancy_mode(value: str) -> bool | None:
    if value == "auto":
        return None
    if value == "on":
        return True
    if value == "off":
        return False
    raise SystemExit("SIDECAR_CONTROL_LEASE_ADAPTIVE_REDUNDANCY must be auto, on, or off")


def _on_off(value: str) -> bool:
    if value == "on":
        return True
    if value == "off":
        return False
    raise SystemExit("value must be on or off")


def _env_float(name: str) -> float | None:
    value = os.environ.get(name)
    if value in {None, ""}:
        return None
    try:
        return float(value)
    except ValueError as exc:
        raise SystemExit(f"{name} must be a number") from exc


def _env_int(name: str) -> int | None:
    value = os.environ.get(name)
    if value in {None, ""}:
        return None
    try:
        return int(value)
    except ValueError as exc:
        raise SystemExit(f"{name} must be an integer") from exc


if __name__ == "__main__":
    main()

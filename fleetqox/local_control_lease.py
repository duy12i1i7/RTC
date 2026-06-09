"""Local robot-side control lease evaluation.

This module is dependency-free so lease semantics can be tested without ROS 2.
A ROS adapter can feed it control-lease envelopes and typed commands, then
publish only commands that are fresh and inside local safety bounds.
"""

from __future__ import annotations

from dataclasses import dataclass
import json
import math
from pathlib import Path
from typing import Mapping


CONTROL_LEASE_SCHEMA_VERSION = "fleetrmw.local_control_lease.v1"
PROFILE_SCHEMA_VERSION = "fleetrmw.local_controller_profiles.v1"
REQUIRED_PROFILE_FIELDS = (
    "max_linear_x",
    "max_abs_linear_y",
    "max_abs_linear_z",
    "max_abs_angular_x",
    "max_abs_angular_y",
    "max_abs_angular_z",
    "max_linear_accel_x",
    "max_abs_angular_accel_z",
    "max_linear_jerk_x",
    "max_abs_angular_jerk_z",
    "max_local_lifespan_ms",
    "pending_command_window_ms",
    "expiry_action",
)
POSITIVE_PROFILE_FIELDS = ("max_linear_x", "max_local_lifespan_ms")
NONNEGATIVE_PROFILE_FIELDS = tuple(
    key for key in REQUIRED_PROFILE_FIELDS if key not in {"expiry_action", *POSITIVE_PROFILE_FIELDS}
)


@dataclass(frozen=True)
class TwistCommand:
    linear_x: float = 0.0
    linear_y: float = 0.0
    linear_z: float = 0.0
    angular_x: float = 0.0
    angular_y: float = 0.0
    angular_z: float = 0.0

    @classmethod
    def zero(cls) -> "TwistCommand":
        return cls()

    @classmethod
    def from_mapping(cls, payload: Mapping[str, object]) -> "TwistCommand":
        linear = _mapping(payload.get("linear"))
        angular = _mapping(payload.get("angular"))
        return cls(
            linear_x=_float(linear.get("x")),
            linear_y=_float(linear.get("y")),
            linear_z=_float(linear.get("z")),
            angular_x=_float(angular.get("x")),
            angular_y=_float(angular.get("y")),
            angular_z=_float(angular.get("z")),
        )

    def as_payload(self) -> dict[str, dict[str, float]]:
        return {
            "linear": {"x": self.linear_x, "y": self.linear_y, "z": self.linear_z},
            "angular": {"x": self.angular_x, "y": self.angular_y, "z": self.angular_z},
        }

    def is_zero(self) -> bool:
        return all(
            abs(value) <= 1e-9
            for value in (
                self.linear_x,
                self.linear_y,
                self.linear_z,
                self.angular_x,
                self.angular_y,
                self.angular_z,
            )
        )


@dataclass(frozen=True)
class TwistAcceleration:
    linear_x: float = 0.0
    angular_z: float = 0.0

    @classmethod
    def zero(cls) -> "TwistAcceleration":
        return cls()


@dataclass(frozen=True)
class DynamicLimitResult:
    command: TwistCommand
    acceleration: TwistAcceleration
    acceleration_clipped: bool = False
    jerk_clipped: bool = False

    @property
    def clipped(self) -> bool:
        return self.acceleration_clipped or self.jerk_clipped

    @property
    def stages(self) -> tuple[str, ...]:
        stages: list[str] = []
        if self.acceleration_clipped:
            stages.append("acceleration")
        if self.jerk_clipped:
            stages.append("jerk")
        return tuple(stages)


@dataclass(frozen=True)
class LeasePolicy:
    controller_profile: str = "diff_drive_safe_v1"
    max_linear_x: float = 0.25
    max_abs_linear_y: float = 0.0
    max_abs_linear_z: float = 0.0
    max_abs_angular_x: float = 0.0
    max_abs_angular_y: float = 0.0
    max_abs_angular_z: float = 0.35
    max_linear_accel_x: float = 1.0
    max_abs_angular_accel_z: float = 2.0
    max_linear_jerk_x: float = 20.0
    max_abs_angular_jerk_z: float = 40.0
    max_local_lifespan_ms: float = 500.0
    pending_command_window_ms: float = 120.0
    publish_stop_on_expiry: bool = True
    expiry_action: str = "stop"

    @classmethod
    def from_mapping(cls, profile_name: str, payload: Mapping[str, object]) -> "LeasePolicy":
        expiry_action = str(payload.get("expiry_action", "stop"))
        if expiry_action not in {"stop", "hold_last", "drop"}:
            raise ValueError(f"invalid expiry_action for {profile_name}: {expiry_action}")
        return cls(
            controller_profile=profile_name,
            max_linear_x=_positive_float(payload.get("max_linear_x"), cls.max_linear_x),
            max_abs_linear_y=_nonnegative_float(payload.get("max_abs_linear_y"), cls.max_abs_linear_y),
            max_abs_linear_z=_nonnegative_float(payload.get("max_abs_linear_z"), cls.max_abs_linear_z),
            max_abs_angular_x=_nonnegative_float(payload.get("max_abs_angular_x"), cls.max_abs_angular_x),
            max_abs_angular_y=_nonnegative_float(payload.get("max_abs_angular_y"), cls.max_abs_angular_y),
            max_abs_angular_z=_nonnegative_float(payload.get("max_abs_angular_z"), cls.max_abs_angular_z),
            max_linear_accel_x=_nonnegative_float(payload.get("max_linear_accel_x"), cls.max_linear_accel_x),
            max_abs_angular_accel_z=_nonnegative_float(
                payload.get("max_abs_angular_accel_z"),
                cls.max_abs_angular_accel_z,
            ),
            max_linear_jerk_x=_nonnegative_float(payload.get("max_linear_jerk_x"), cls.max_linear_jerk_x),
            max_abs_angular_jerk_z=_nonnegative_float(
                payload.get("max_abs_angular_jerk_z"),
                cls.max_abs_angular_jerk_z,
            ),
            max_local_lifespan_ms=_positive_float(
                payload.get("max_local_lifespan_ms"),
                cls.max_local_lifespan_ms,
            ),
            pending_command_window_ms=_nonnegative_float(
                payload.get("pending_command_window_ms"),
                cls.pending_command_window_ms,
            ),
            publish_stop_on_expiry=_bool(payload.get("publish_stop_on_expiry"), cls.publish_stop_on_expiry),
            expiry_action=expiry_action,
        )


@dataclass(frozen=True)
class ControlLease:
    event_id: int | None
    robot_id: str
    flow_id: str
    kind: str
    wire_mode: str
    action: str
    source_topic: str
    policy: str
    deadline_ms: float | None
    lifespan_ms: float
    received_monotonic_ms: float
    local_expires_at_ms: float
    reason: str = ""

    @classmethod
    def from_envelope(
        cls,
        payload: str | Mapping[str, object],
        *,
        received_monotonic_ms: float,
        policy: LeasePolicy | None = None,
    ) -> "ControlLease":
        data = json.loads(payload) if isinstance(payload, str) else dict(payload)
        lease_policy = policy or LeasePolicy()
        lifespan_ms = _positive_float(data.get("lifespan_ms"), lease_policy.max_local_lifespan_ms)
        local_lifespan_ms = min(lifespan_ms, lease_policy.max_local_lifespan_ms)
        return cls(
            event_id=_optional_int(data.get("event_id")),
            robot_id=str(data.get("robot_id", "unknown_robot")),
            flow_id=str(data.get("flow_id", "")),
            kind=str(data.get("kind", "")),
            wire_mode=str(data.get("wire_mode", "")),
            action=str(data.get("action", "")),
            source_topic=str(data.get("source_topic", "")),
            policy=str(data.get("policy", "")),
            deadline_ms=_optional_float(data.get("deadline_ms")),
            lifespan_ms=local_lifespan_ms,
            received_monotonic_ms=received_monotonic_ms,
            local_expires_at_ms=received_monotonic_ms + local_lifespan_ms,
            reason=str(data.get("reason", "")),
        )

    def expired(self, now_ms: float) -> bool:
        return now_ms > self.local_expires_at_ms


@dataclass(frozen=True)
class LeaseDecision:
    status: str
    reason: str
    publish: bool
    safe_command: TwistCommand
    requested_command: TwistCommand | None
    lease: ControlLease | None
    now_ms: float
    clipped: bool = False
    clip_stages: tuple[str, ...] = ()

    def as_log_record(self) -> dict[str, object]:
        return {
            "schema_version": CONTROL_LEASE_SCHEMA_VERSION,
            "status": self.status,
            "reason": self.reason,
            "publish": self.publish,
            "clipped": self.clipped,
            "clip_stages": list(self.clip_stages),
            "now_ms": self.now_ms,
            "safe_command": self.safe_command.as_payload(),
            "requested_command": self.requested_command.as_payload() if self.requested_command else None,
            "lease": lease_log_record(self.lease),
        }


class LocalControlLeaseState:
    """State machine for local control-lease enforcement."""

    def __init__(self, policy: LeasePolicy | None = None) -> None:
        self.policy = policy or LeasePolicy()
        self.active_lease: ControlLease | None = None
        self._last_output = TwistCommand.zero()
        self._last_output_ms: float | None = None
        self._last_accel = TwistAcceleration.zero()
        self._fallback_event_ids: set[int | None] = set()
        self._pending_command: tuple[TwistCommand, float] | None = None

    def ingest_lease(self, lease: ControlLease) -> LeaseDecision:
        stale_decision = self._stale_or_duplicate_lease_decision(lease)
        if stale_decision is not None:
            return stale_decision
        self.active_lease = lease
        if lease.event_id not in self._fallback_event_ids:
            self._fallback_event_ids.discard(lease.event_id)
        decision = LeaseDecision(
            status="lease_update",
            reason="lease accepted into local controller state",
            publish=False,
            safe_command=self._last_output,
            requested_command=None,
            lease=lease,
            now_ms=lease.received_monotonic_ms,
        )
        if self._pending_command:
            command, received_ms = self._pending_command
            if lease.received_monotonic_ms - received_ms <= self.policy.pending_command_window_ms:
                self._pending_command = None
                return self.evaluate_command(command, now_ms=lease.received_monotonic_ms)
        return decision

    def _stale_or_duplicate_lease_decision(self, lease: ControlLease) -> LeaseDecision | None:
        active = self.active_lease
        if active is None or active.event_id is None or lease.event_id is None:
            return None
        if lease.event_id > active.event_id:
            return None
        status = "duplicate_lease" if lease.event_id == active.event_id else "stale_lease"
        reason = (
            "duplicate control lease ignored without extending local expiry"
            if status == "duplicate_lease"
            else "stale control lease ignored because a newer lease is active"
        )
        return LeaseDecision(
            status=status,
            reason=reason,
            publish=False,
            safe_command=self._last_output,
            requested_command=None,
            lease=active,
            now_ms=lease.received_monotonic_ms,
        )

    def evaluate_command(self, command: TwistCommand, *, now_ms: float) -> LeaseDecision:
        lease = self.active_lease
        if lease is None:
            self._pending_command = (command, now_ms)
            return LeaseDecision(
                status="drop_no_lease",
                reason="typed command arrived before any active control lease",
                publish=False,
                safe_command=TwistCommand.zero(),
                requested_command=command,
                lease=None,
                now_ms=now_ms,
            )
        if lease.expired(now_ms):
            return self._expiry_decision(lease=lease, now_ms=now_ms, reason="active lease expired before command")

        bounded, bound_clipped = clip_command(command, self.policy)
        dynamic_result = apply_dynamic_limits(
            bounded,
            previous=self._last_output,
            previous_ms=self._last_output_ms,
            previous_accel=self._last_accel,
            now_ms=now_ms,
            policy=self.policy,
        )
        safe = dynamic_result.command
        dynamic_stages = dynamic_result.stages
        rate_clipped = dynamic_result.clipped
        clipped = bound_clipped or rate_clipped
        self._last_output = safe
        self._last_output_ms = now_ms
        self._last_accel = dynamic_result.acceleration
        clip_stages = tuple(["safety_bound"] if bound_clipped else []) + dynamic_stages
        return LeaseDecision(
            status="clip" if clipped else "accept",
            reason=clip_reason(bound_clipped=bound_clipped, dynamic_stages=dynamic_stages)
            if clipped
            else "command accepted under active lease",
            publish=True,
            safe_command=safe,
            requested_command=command,
            lease=lease,
            now_ms=now_ms,
            clipped=clipped,
            clip_stages=clip_stages,
        )

    def tick(self, *, now_ms: float) -> LeaseDecision | None:
        lease = self.active_lease
        if lease is None or not self.policy.publish_stop_on_expiry:
            return None
        if not lease.expired(now_ms):
            return None
        if lease.event_id in self._fallback_event_ids:
            return None
        return self._expiry_decision(lease=lease, now_ms=now_ms, reason="active lease expired")

    def _fallback_stop(self, *, lease: ControlLease, now_ms: float, reason: str) -> LeaseDecision:
        self._fallback_event_ids.add(lease.event_id)
        self._last_output = TwistCommand.zero()
        self._last_output_ms = now_ms
        self._last_accel = TwistAcceleration.zero()
        return LeaseDecision(
            status="fallback_stop",
            reason=reason,
            publish=True,
            safe_command=TwistCommand.zero(),
            requested_command=None,
            lease=lease,
            now_ms=now_ms,
        )

    def _expiry_decision(self, *, lease: ControlLease, now_ms: float, reason: str) -> LeaseDecision:
        action = self.policy.expiry_action.lower()
        if action == "hold_last":
            self._fallback_event_ids.add(lease.event_id)
            return LeaseDecision(
                status="fallback_hold_last",
                reason=f"{reason}; holding last safe command",
                publish=True,
                safe_command=self._last_output,
                requested_command=None,
                lease=lease,
                now_ms=now_ms,
            )
        if action == "drop":
            self._fallback_event_ids.add(lease.event_id)
            return LeaseDecision(
                status="fallback_drop",
                reason=f"{reason}; no fallback command published",
                publish=False,
                safe_command=self._last_output,
                requested_command=None,
                lease=lease,
                now_ms=now_ms,
            )
        return self._fallback_stop(lease=lease, now_ms=now_ms, reason=f"{reason}; publishing fallback stop")


def clip_command(command: TwistCommand, policy: LeasePolicy) -> tuple[TwistCommand, bool]:
    safe = TwistCommand(
        linear_x=_clamp(command.linear_x, -policy.max_linear_x, policy.max_linear_x),
        linear_y=_clamp(command.linear_y, -policy.max_abs_linear_y, policy.max_abs_linear_y),
        linear_z=_clamp(command.linear_z, -policy.max_abs_linear_z, policy.max_abs_linear_z),
        angular_x=_clamp(command.angular_x, -policy.max_abs_angular_x, policy.max_abs_angular_x),
        angular_y=_clamp(command.angular_y, -policy.max_abs_angular_y, policy.max_abs_angular_y),
        angular_z=_clamp(command.angular_z, -policy.max_abs_angular_z, policy.max_abs_angular_z),
    )
    return safe, safe != command


def apply_rate_limits(
    command: TwistCommand,
    *,
    previous: TwistCommand,
    previous_ms: float | None,
    now_ms: float,
    policy: LeasePolicy,
) -> tuple[TwistCommand, bool]:
    result = apply_dynamic_limits(
        command,
        previous=previous,
        previous_ms=previous_ms,
        previous_accel=TwistAcceleration.zero(),
        now_ms=now_ms,
        policy=policy,
    )
    return result.command, result.clipped


def apply_dynamic_limits(
    command: TwistCommand,
    *,
    previous: TwistCommand,
    previous_ms: float | None,
    previous_accel: TwistAcceleration | None,
    now_ms: float,
    policy: LeasePolicy,
) -> DynamicLimitResult:
    if previous_ms is None or now_ms <= previous_ms:
        return DynamicLimitResult(command=command, acceleration=TwistAcceleration.zero())
    dt_s = (now_ms - previous_ms) / 1000.0
    desired_linear_accel = (command.linear_x - previous.linear_x) / dt_s
    desired_angular_accel = (command.angular_z - previous.angular_z) / dt_s
    accel_limited = TwistAcceleration(
        linear_x=_clamp(desired_linear_accel, -policy.max_linear_accel_x, policy.max_linear_accel_x),
        angular_z=_clamp(desired_angular_accel, -policy.max_abs_angular_accel_z, policy.max_abs_angular_accel_z),
    )
    acceleration_clipped = (
        not math.isclose(accel_limited.linear_x, desired_linear_accel, rel_tol=0.0, abs_tol=1e-12)
        or not math.isclose(accel_limited.angular_z, desired_angular_accel, rel_tol=0.0, abs_tol=1e-12)
    )
    prior_accel = previous_accel or TwistAcceleration.zero()
    jerk_limited = TwistAcceleration(
        linear_x=_step_toward(
            prior_accel.linear_x,
            accel_limited.linear_x,
            max(0.0, policy.max_linear_jerk_x) * dt_s,
        ),
        angular_z=_step_toward(
            prior_accel.angular_z,
            accel_limited.angular_z,
            max(0.0, policy.max_abs_angular_jerk_z) * dt_s,
        ),
    )
    jerk_clipped = jerk_limited != accel_limited
    safe = TwistCommand(
        linear_x=previous.linear_x + jerk_limited.linear_x * dt_s,
        linear_y=command.linear_y,
        linear_z=command.linear_z,
        angular_x=command.angular_x,
        angular_y=command.angular_y,
        angular_z=previous.angular_z + jerk_limited.angular_z * dt_s,
    )
    return DynamicLimitResult(
        command=safe,
        acceleration=jerk_limited,
        acceleration_clipped=acceleration_clipped,
        jerk_clipped=jerk_clipped,
    )


def clip_reason(*, bound_clipped: bool, dynamic_stages: tuple[str, ...]) -> str:
    if bound_clipped and dynamic_stages:
        return f"command clipped to local safety, {', '.join(dynamic_stages)} bounds"
    if dynamic_stages:
        return f"command clipped to local {', '.join(dynamic_stages)} bounds"
    return "command clipped to local safety bounds"


def lease_log_record(lease: ControlLease | None) -> dict[str, object] | None:
    if lease is None:
        return None
    return {
        "event_id": lease.event_id,
        "robot_id": lease.robot_id,
        "flow_id": lease.flow_id,
        "kind": lease.kind,
        "wire_mode": lease.wire_mode,
        "action": lease.action,
        "source_topic": lease.source_topic,
        "policy": lease.policy,
        "deadline_ms": lease.deadline_ms,
        "lifespan_ms": lease.lifespan_ms,
        "received_monotonic_ms": lease.received_monotonic_ms,
        "local_expires_at_ms": lease.local_expires_at_ms,
        "reason": lease.reason,
    }


def load_lease_policy(
    path: str | Path,
    *,
    profile_name: str | None = None,
    overrides: Mapping[str, object] | None = None,
) -> LeasePolicy:
    with Path(path).open("r", encoding="utf-8") as handle:
        config = json.load(handle)
    if not isinstance(config, Mapping):
        raise ValueError("lease profile config must be a JSON object")
    schema = config.get("schema_version")
    if schema != PROFILE_SCHEMA_VERSION:
        raise ValueError(f"unsupported profile schema_version: {schema}")
    profiles = config.get("profiles")
    if not isinstance(profiles, Mapping):
        raise ValueError("lease profile config must contain profiles")
    selected = profile_name or str(config.get("default_profile", ""))
    if not selected:
        raise ValueError("lease profile config needs a selected or default profile")
    profile_payload = profiles.get(selected)
    if not isinstance(profile_payload, Mapping):
        available = ", ".join(sorted(str(key) for key in profiles.keys()))
        raise ValueError(f"unknown lease profile: {selected}; available: {available}")
    merged = dict(profile_payload)
    for key, value in (overrides or {}).items():
        if value is not None:
            merged[key] = value
    _validate_profile_payload(selected, merged)
    return LeasePolicy.from_mapping(selected, merged)


def _validate_profile_payload(profile_name: str, payload: Mapping[str, object]) -> None:
    missing = [key for key in REQUIRED_PROFILE_FIELDS if key not in payload]
    if missing:
        raise ValueError(f"lease profile {profile_name} missing fields: {', '.join(missing)}")
    expiry_action = str(payload.get("expiry_action"))
    if expiry_action not in {"stop", "hold_last", "drop"}:
        raise ValueError(f"invalid expiry_action for {profile_name}: {expiry_action}")
    for key in POSITIVE_PROFILE_FIELDS:
        value = _optional_float(payload.get(key))
        if value is None or not math.isfinite(value) or value <= 0:
            raise ValueError(f"lease profile {profile_name} field {key} must be positive")
    for key in NONNEGATIVE_PROFILE_FIELDS:
        value = _optional_float(payload.get(key))
        if value is None or not math.isfinite(value) or value < 0:
            raise ValueError(f"lease profile {profile_name} field {key} must be non-negative")


def _mapping(value: object) -> Mapping[str, object]:
    return value if isinstance(value, Mapping) else {}


def _clamp(value: float, lower: float, upper: float) -> float:
    return min(upper, max(lower, value))


def _step_toward(previous: float, target: float, max_step: float) -> float:
    if max_step <= 0:
        return previous
    delta = target - previous
    if abs(delta) <= max_step:
        return target
    return previous + max_step if delta > 0 else previous - max_step


def _positive_float(value: object, default: float) -> float:
    parsed = _optional_float(value)
    if parsed is None or parsed <= 0:
        return default
    return parsed


def _nonnegative_float(value: object, default: float) -> float:
    parsed = _optional_float(value)
    if parsed is None or parsed < 0:
        return default
    return parsed


def _bool(value: object, default: bool) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    return str(value).lower() in {"1", "true", "yes", "on"}


def _optional_float(value: object) -> float | None:
    try:
        return float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None


def _float(value: object) -> float:
    return _optional_float(value) or 0.0


def _optional_int(value: object) -> int | None:
    try:
        return int(float(value))  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None

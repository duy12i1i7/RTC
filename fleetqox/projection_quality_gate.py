"""Local consumer gate for FleetRMW typed projection quality.

The egress bridge can reconstruct typed ROS 2 messages from semantic payloads,
but local consumers still need to know whether those messages are
raw-equivalent, degraded, or downsampled.  This module keeps that admission
logic dependency-free so ROS adapters can apply it without embedding policy
rules in callback code.
"""

from __future__ import annotations

from dataclasses import dataclass
import json
from typing import Mapping


PROJECTION_QUALITY_GATE_SCHEMA_VERSION = "fleetrmw.projection_quality_gate.v1"


@dataclass(frozen=True)
class ProjectionQuality:
    schema_version: str
    kind: str
    contract_id: str
    source_sample_id: str
    event_id: int | None
    robot_id: str
    flow_id: str
    source_topic: str
    source_msg_type: str
    projection_kind: str
    projection_topic: str
    projection_msg_type: str
    fidelity_class: str
    lossy: bool
    degradation_reasons: tuple[str, ...]
    source_sample_count: int | None
    projected_sample_count: int | None
    downsample_stride: int | None
    age_ms: float | None
    deadline_ms: float | None
    task_criticality: float | None
    collision_risk: float | None
    operator_attention: float | None
    projection_signature: str
    projection_signature_algorithm: str
    projection_signature_version: str
    projection_payload_embedded: bool
    projection_payload: Mapping[str, object]

    @classmethod
    def from_payload(cls, payload: str | Mapping[str, object]) -> "ProjectionQuality":
        data = json.loads(payload) if isinstance(payload, str) else dict(payload)
        if not isinstance(data, Mapping):
            raise ValueError("projection quality payload must be a JSON object")
        reasons = data.get("degradation_reasons", [])
        projection_payload = data.get("projection_payload")
        return cls(
            schema_version=str(data.get("schema_version", "")),
            kind=str(data.get("kind", "")),
            contract_id=str(data.get("contract_id", "")),
            source_sample_id=str(data.get("source_sample_id", "")),
            event_id=_optional_int(data.get("event_id")),
            robot_id=str(data.get("robot_id", "")),
            flow_id=str(data.get("flow_id", "")),
            source_topic=str(data.get("source_topic", "")),
            source_msg_type=str(data.get("source_msg_type", "")),
            projection_kind=str(data.get("projection_kind", "")),
            projection_topic=str(data.get("projection_topic", "")),
            projection_msg_type=str(data.get("projection_msg_type", "")),
            fidelity_class=str(data.get("fidelity_class", "")),
            lossy=_bool(data.get("lossy"), default=True),
            degradation_reasons=tuple(str(item) for item in reasons) if isinstance(reasons, list) else (),
            source_sample_count=_optional_int(data.get("source_sample_count")),
            projected_sample_count=_optional_int(data.get("projected_sample_count")),
            downsample_stride=_optional_int(data.get("downsample_stride")),
            age_ms=_optional_float(data.get("age_ms")),
            deadline_ms=_optional_float(data.get("deadline_ms")),
            task_criticality=_optional_float(data.get("task_criticality")),
            collision_risk=_optional_float(data.get("collision_risk")),
            operator_attention=_optional_float(data.get("operator_attention")),
            projection_signature=str(data.get("projection_signature", "")),
            projection_signature_algorithm=str(data.get("projection_signature_algorithm", "")),
            projection_signature_version=str(data.get("projection_signature_version", "")),
            projection_payload_embedded=_bool(data.get("projection_payload_embedded"), default=isinstance(projection_payload, Mapping)),
            projection_payload=dict(projection_payload) if isinstance(projection_payload, Mapping) else {},
        )


@dataclass(frozen=True)
class ProjectionGatePolicy:
    allow_raw_equivalent: bool = True
    allow_semantic_projection: bool = True
    allow_degraded_projection: bool = False
    allow_downsampled_projection: bool = True
    max_projection_age_ms: float = 350.0
    max_downsample_stride: int = 3
    min_projected_scan_ranges: int = 30
    reject_downsampled_collision_risk_at: float = 0.65
    allowed_projection_kinds: tuple[str, ...] = ("typed_odom", "typed_scan")


@dataclass(frozen=True)
class ProjectionGateDecision:
    status: str
    reason: str
    publish: bool
    quality: ProjectionQuality | None = None

    def as_log_record(self) -> dict[str, object]:
        return {
            "schema_version": PROJECTION_QUALITY_GATE_SCHEMA_VERSION,
            "status": self.status,
            "reason": self.reason,
            "publish": self.publish,
            "contract_id": self.quality.contract_id if self.quality else None,
            "source_sample_id": self.quality.source_sample_id if self.quality else None,
            "event_id": self.quality.event_id if self.quality else None,
            "robot_id": self.quality.robot_id if self.quality else None,
            "flow_id": self.quality.flow_id if self.quality else None,
            "source_topic": self.quality.source_topic if self.quality else None,
            "projection_kind": self.quality.projection_kind if self.quality else None,
            "projection_topic": self.quality.projection_topic if self.quality else None,
            "projection_msg_type": self.quality.projection_msg_type if self.quality else None,
            "fidelity_class": self.quality.fidelity_class if self.quality else None,
            "lossy": self.quality.lossy if self.quality else None,
            "degradation_reasons": list(self.quality.degradation_reasons) if self.quality else [],
            "source_sample_count": self.quality.source_sample_count if self.quality else None,
            "projected_sample_count": self.quality.projected_sample_count if self.quality else None,
            "downsample_stride": self.quality.downsample_stride if self.quality else None,
            "age_ms": self.quality.age_ms if self.quality else None,
            "deadline_ms": self.quality.deadline_ms if self.quality else None,
            "task_criticality": self.quality.task_criticality if self.quality else None,
            "collision_risk": self.quality.collision_risk if self.quality else None,
            "operator_attention": self.quality.operator_attention if self.quality else None,
            "projection_signature": self.quality.projection_signature if self.quality else None,
            "projection_signature_algorithm": self.quality.projection_signature_algorithm if self.quality else None,
            "projection_signature_version": self.quality.projection_signature_version if self.quality else None,
            "projection_payload_embedded": self.quality.projection_payload_embedded if self.quality else None,
            "projection_payload_present": bool(self.quality and self.quality.projection_payload),
            "projection_payload_event_id": (
                self.quality.projection_payload.get("event_id") if self.quality and self.quality.projection_payload else None
            ),
        }


class ProjectionQualityGate:
    def __init__(self, policy: ProjectionGatePolicy | None = None) -> None:
        self.policy = policy or ProjectionGatePolicy()

    def evaluate(self, quality: ProjectionQuality) -> ProjectionGateDecision:
        return evaluate_projection_quality(quality, self.policy)


def evaluate_projection_quality(
    quality: ProjectionQuality,
    policy: ProjectionGatePolicy,
) -> ProjectionGateDecision:
    if quality.kind != "typed_projection_quality":
        return ProjectionGateDecision(
            status="drop_invalid_quality",
            reason=f"unsupported quality kind: {quality.kind}",
            publish=False,
            quality=quality,
        )
    if quality.projection_kind not in policy.allowed_projection_kinds:
        return ProjectionGateDecision(
            status="ignore_projection_kind",
            reason=f"projection kind is not managed by this gate: {quality.projection_kind}",
            publish=False,
            quality=quality,
        )
    if quality.age_ms is not None and quality.age_ms > policy.max_projection_age_ms:
        return ProjectionGateDecision(
            status="drop_stale_projection",
            reason=f"projection age {quality.age_ms:.2f}ms exceeds {policy.max_projection_age_ms:.2f}ms",
            publish=False,
            quality=quality,
        )

    fidelity = quality.fidelity_class
    if fidelity == "raw_equivalent_projection":
        return _decision(
            quality,
            publish=policy.allow_raw_equivalent,
            reason="raw-equivalent projection accepted",
            reject_reason="raw-equivalent projections disabled by policy",
        )
    if fidelity == "semantic_projection":
        return _decision(
            quality,
            publish=policy.allow_semantic_projection,
            reason="semantic projection accepted",
            reject_reason="semantic projections disabled by policy",
        )
    if fidelity == "degraded_projection":
        return _decision(
            quality,
            publish=policy.allow_degraded_projection,
            reason="degraded projection accepted",
            reject_reason="degraded projection rejected by local consumer policy",
        )
    if fidelity == "downsampled_projection":
        return _evaluate_downsampled(quality, policy)
    return ProjectionGateDecision(
        status="drop_unknown_fidelity",
        reason=f"unknown projection fidelity class: {fidelity}",
        publish=False,
        quality=quality,
    )


def _evaluate_downsampled(
    quality: ProjectionQuality,
    policy: ProjectionGatePolicy,
) -> ProjectionGateDecision:
    if not policy.allow_downsampled_projection:
        return ProjectionGateDecision(
            status="drop_downsampled_projection",
            reason="downsampled projections disabled by policy",
            publish=False,
            quality=quality,
        )
    stride = quality.downsample_stride or 1
    if stride > policy.max_downsample_stride:
        return ProjectionGateDecision(
            status="drop_downsampled_projection",
            reason=f"downsample stride {stride} exceeds {policy.max_downsample_stride}",
            publish=False,
            quality=quality,
        )
    projected_count = quality.projected_sample_count or 0
    if projected_count < policy.min_projected_scan_ranges:
        return ProjectionGateDecision(
            status="drop_downsampled_projection",
            reason=f"projected scan range count {projected_count} below {policy.min_projected_scan_ranges}",
            publish=False,
            quality=quality,
        )
    collision_risk = quality.collision_risk or 0.0
    if collision_risk >= policy.reject_downsampled_collision_risk_at:
        return ProjectionGateDecision(
            status="drop_high_risk_downsampled_projection",
            reason=(
                f"collision risk {collision_risk:.2f} rejects downsampled projection "
                f"at threshold {policy.reject_downsampled_collision_risk_at:.2f}"
            ),
            publish=False,
            quality=quality,
        )
    return ProjectionGateDecision(
        status="accept",
        reason="downsampled projection accepted within local consumer envelope",
        publish=True,
        quality=quality,
    )


def _decision(
    quality: ProjectionQuality,
    *,
    publish: bool,
    reason: str,
    reject_reason: str,
) -> ProjectionGateDecision:
    return ProjectionGateDecision(
        status="accept" if publish else "drop_projection",
        reason=reason if publish else reject_reason,
        publish=publish,
        quality=quality,
    )


def _optional_float(value: object) -> float | None:
    try:
        return None if value is None else float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None


def _optional_int(value: object) -> int | None:
    try:
        return None if value is None else int(float(value))  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None


def _bool(value: object, *, default: bool) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    return str(value).lower() in {"1", "true", "yes", "on"}

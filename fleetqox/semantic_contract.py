"""Feasibility-aware semantic communication contracts.

This module is the transport-independent core for the next FleetQoX step. It
does not choose a final schedule by itself. Instead, it states which semantic
representations a ROS-like flow can use and whether each representation is
feasible on the currently observed IP path.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from enum import Enum
from typing import Iterable

from .model import FlowClass, FlowObservation, FlowSpec, NetworkLink


class TransformKind(str, Enum):
    RAW = "raw"
    SEMANTIC_DELTA = "semantic_delta"
    DEGRADED = "degraded"
    CONTROL_INTENT = "control_intent"
    SUPERVISORY_INTENT = "supervisory_intent"


@dataclass(frozen=True)
class SemanticTransform:
    kind: TransformKind
    action: str
    wire_mode: str
    size_ratio: float
    value_ratio: float
    effective_deadline_ms: float
    effective_lifespan_ms: float | None
    reliability: str
    description: str


@dataclass(frozen=True)
class FlowContract:
    flow_id: str
    flow_class: FlowClass
    source_deadline_ms: float
    lifespan_ms: float
    transforms: tuple[SemanticTransform, ...]
    min_delivery_ratio: float
    max_deadline_risk: float

    def transform(self, kind: TransformKind) -> SemanticTransform | None:
        for item in self.transforms:
            if item.kind is kind:
                return item
        return None


@dataclass(frozen=True)
class FeasibilityCertificate:
    flow_id: str
    transform: SemanticTransform
    allocated_bytes: int
    feasible: bool
    estimated_wire_ms: float
    predicted_arrival_age_ms: float
    slack_after_wire_ms: float
    deadline_risk: float
    reason: str


@dataclass(frozen=True)
class TransformCandidate:
    contract: FlowContract
    transform: SemanticTransform
    allocated_bytes: int
    certificate: FeasibilityCertificate


def build_flow_contract(
    spec: FlowSpec,
    obs: FlowObservation,
    link: NetworkLink,
    *,
    semantic_compaction_ratio: float = 0.55,
    degraded_ratio: float = 0.14,
    intent_ratio: float = 0.50,
) -> FlowContract:
    """Build concrete semantic representations for one flow on one link."""

    spec.validates()
    link.validates()
    transforms = [
        SemanticTransform(
            kind=TransformKind.RAW,
            action="send",
            wire_mode="native",
            size_ratio=1.0,
            value_ratio=1.0,
            effective_deadline_ms=spec.qos.deadline_ms,
            effective_lifespan_ms=None,
            reliability=_default_reliability(spec, obs, link),
            description="raw ROS sample",
        )
    ]
    if spec.flow_class in {
        FlowClass.SAFETY,
        FlowClass.CONTROL,
        FlowClass.COORDINATION,
        FlowClass.STATE,
    }:
        transforms.append(
            SemanticTransform(
                kind=TransformKind.SEMANTIC_DELTA,
                action="send_compacted",
                wire_mode="semantic_delta",
                size_ratio=semantic_compaction_ratio,
                value_ratio=0.88,
                effective_deadline_ms=spec.qos.deadline_ms,
                effective_lifespan_ms=None,
                reliability=_default_reliability(spec, obs, link),
                description="semantic delta sample",
            )
        )
    if spec.flow_class is FlowClass.CONTROL:
        transforms.append(
            SemanticTransform(
                kind=TransformKind.CONTROL_INTENT,
                action="send_intent",
                wire_mode="control_intent",
                size_ratio=intent_ratio,
                value_ratio=0.92,
                effective_deadline_ms=control_intent_deadline_ms(spec, link),
                effective_lifespan_ms=None,
                reliability="best_effort_fresh",
                description="path-aware control intent horizon",
            )
        )
        transforms.append(
            SemanticTransform(
                kind=TransformKind.SUPERVISORY_INTENT,
                action="send_supervisory_intent",
                wire_mode="supervisory_intent",
                size_ratio=min(intent_ratio, 0.42),
                value_ratio=0.74,
                effective_deadline_ms=supervisory_intent_deadline_ms(spec, link),
                effective_lifespan_ms=supervisory_intent_deadline_ms(spec, link),
                reliability="best_effort_fresh",
                description="supervisory goal/constraint lease",
            )
        )
    if spec.flow_class in {
        FlowClass.PERCEPTION,
        FlowClass.HUMAN_QOE,
        FlowClass.DEBUG,
        FlowClass.BULK,
    }:
        transforms.append(
            SemanticTransform(
                kind=TransformKind.DEGRADED,
                action="send_degraded",
                wire_mode="degraded",
                size_ratio=degraded_ratio,
                value_ratio=0.72,
                effective_deadline_ms=spec.qos.deadline_ms,
                effective_lifespan_ms=None,
                reliability="best_effort_fresh",
                description="degraded QoE representation",
            )
        )

    return FlowContract(
        flow_id=spec.flow_id,
        flow_class=spec.flow_class,
        source_deadline_ms=spec.qos.deadline_ms,
        lifespan_ms=spec.qos.lifespan_ms,
        transforms=tuple(transforms),
        min_delivery_ratio=_min_delivery_ratio(spec.flow_class),
        max_deadline_risk=_max_deadline_risk(spec.flow_class),
    )


def transform_candidates(
    spec: FlowSpec,
    obs: FlowObservation,
    link: NetworkLink,
    *,
    min_intent_bytes: int = 48,
    semantic_compaction_ratio: float = 0.55,
    degraded_ratio: float = 0.14,
    intent_ratio: float = 0.50,
) -> tuple[TransformCandidate, ...]:
    contract = build_flow_contract(
        spec,
        obs,
        link,
        semantic_compaction_ratio=semantic_compaction_ratio,
        degraded_ratio=degraded_ratio,
        intent_ratio=intent_ratio,
    )
    base_size = base_payload_size(spec, obs)
    candidates = []
    for transform in contract.transforms:
        allocated = max(1, int(base_size * transform.size_ratio))
        if transform.kind in {
            TransformKind.CONTROL_INTENT,
            TransformKind.SUPERVISORY_INTENT,
        }:
            allocated = max(min_intent_bytes, min(base_size, allocated))
        certificate = certify_transform(
            spec,
            obs,
            link,
            transform,
            allocated_bytes=allocated,
        )
        candidates.append(
            TransformCandidate(
                contract=contract,
                transform=transform,
                allocated_bytes=allocated,
                certificate=certificate,
            )
        )
    return tuple(candidates)


def certify_transform(
    spec: FlowSpec,
    obs: FlowObservation,
    link: NetworkLink,
    transform: SemanticTransform,
    *,
    allocated_bytes: int,
) -> FeasibilityCertificate:
    wire_ms = path_tail_wire_ms(link, allocated_bytes)
    source_age_ms = _source_age_for_transform(obs, transform)
    arrival_age_ms = source_age_ms + wire_ms
    lifespan_ms = transform.effective_lifespan_ms or spec.qos.lifespan_ms
    slack_after_wire_ms = transform.effective_deadline_ms - arrival_age_ms
    risk = logistic_deadline_risk(-slack_after_wire_ms)
    risk_limit = (
        0.50
        if transform.kind in {
            TransformKind.CONTROL_INTENT,
            TransformKind.SUPERVISORY_INTENT,
        }
        else _max_deadline_risk(spec.flow_class)
    )
    feasible = (
        slack_after_wire_ms >= 0.0
        and risk <= risk_limit
        and arrival_age_ms <= lifespan_ms
    )
    if feasible:
        reason = "feasible"
    elif arrival_age_ms > lifespan_ms:
        reason = "violates lifespan"
    elif slack_after_wire_ms < 0.0:
        reason = "violates effective deadline"
    else:
        reason = "deadline risk too high"
    return FeasibilityCertificate(
        flow_id=spec.flow_id,
        transform=transform,
        allocated_bytes=allocated_bytes,
        feasible=feasible,
        estimated_wire_ms=wire_ms,
        predicted_arrival_age_ms=arrival_age_ms,
        slack_after_wire_ms=slack_after_wire_ms,
        deadline_risk=risk,
        reason=reason,
    )


def _source_age_for_transform(
    obs: FlowObservation,
    transform: SemanticTransform,
) -> float:
    if transform.kind in {
        TransformKind.SEMANTIC_DELTA,
        TransformKind.DEGRADED,
        TransformKind.CONTROL_INTENT,
        TransformKind.SUPERVISORY_INTENT,
    }:
        return 0.0
    return obs.age_ms


def best_feasible_candidate(
    candidates: Iterable[TransformCandidate],
) -> TransformCandidate | None:
    feasible = [candidate for candidate in candidates if candidate.certificate.feasible]
    if not feasible:
        return None
    return max(
        feasible,
        key=lambda item: (
            item.transform.value_ratio,
            -item.certificate.deadline_risk,
            -item.allocated_bytes,
        ),
    )


def base_payload_size(spec: FlowSpec, obs: FlowObservation) -> int:
    return max(1, int(spec.nominal_size_bytes * spec.semantic_delta_ratio * obs.queue_depth))


def path_tail_wire_ms(link: NetworkLink, allocated_bytes: int) -> float:
    link.validates()
    serialization_ms = 20.0 * allocated_bytes / max(1.0, float(link.capacity_bytes_per_tick))
    return (
        0.5 * link.rtt_ms
        + 1.35 * link.jitter_ms
        + 0.22 * link.loss * link.rtt_ms
        + serialization_ms
    )


def control_intent_deadline_ms(spec: FlowSpec, link: NetworkLink) -> float:
    """Return the path-aware validity horizon for a control-intent packet."""

    one_way_tail_ms = 0.5 * link.rtt_ms + 1.35 * link.jitter_ms
    horizon_ms = one_way_tail_ms + 1.5 * spec.qos.deadline_ms
    return min(spec.qos.lifespan_ms, max(spec.qos.deadline_ms, horizon_ms))


def supervisory_intent_deadline_ms(spec: FlowSpec, link: NetworkLink) -> float:
    """Return the lease horizon for control that cannot be teleoperated directly.

    A supervisory intent is not the next velocity sample. It is a compact
    goal/constraint lease that lets the local robot controller continue safely
    when the network path is already longer than the original control lifespan.
    """

    one_way_tail_ms = 0.5 * link.rtt_ms + 1.35 * link.jitter_ms
    return max(spec.qos.lifespan_ms, one_way_tail_ms + 4.0 * spec.qos.deadline_ms)


def logistic_deadline_risk(margin_ms: float, *, temperature_ms: float = 12.0) -> float:
    temperature = max(1.0, temperature_ms)
    x = max(-60.0, min(60.0, margin_ms / temperature))
    return 1.0 / (1.0 + math.exp(-x))


def _default_reliability(
    spec: FlowSpec,
    obs: FlowObservation,
    link: NetworkLink,
) -> str:
    slack = spec.qos.deadline_ms - obs.age_ms
    retry_feasible = slack > link.rtt_ms * 1.35
    if spec.flow_class in {FlowClass.SAFETY, FlowClass.CONTROL, FlowClass.COORDINATION}:
        return "reliable" if retry_feasible and link.loss >= 0.03 else "best_effort_fresh"
    if spec.flow_class is FlowClass.STATE:
        return "reliable" if retry_feasible and link.loss < 0.08 else "best_effort_fresh"
    return "best_effort_fresh"


def _min_delivery_ratio(flow_class: FlowClass) -> float:
    if flow_class is FlowClass.SAFETY:
        return 0.995
    if flow_class is FlowClass.CONTROL:
        return 0.98
    if flow_class is FlowClass.COORDINATION:
        return 0.94
    if flow_class is FlowClass.STATE:
        return 0.85
    if flow_class is FlowClass.HUMAN_QOE:
        return 0.75
    return 0.0


def _max_deadline_risk(flow_class: FlowClass) -> float:
    if flow_class is FlowClass.SAFETY:
        return 0.02
    if flow_class is FlowClass.CONTROL:
        return 0.08
    if flow_class is FlowClass.COORDINATION:
        return 0.12
    if flow_class is FlowClass.STATE:
        return 0.22
    if flow_class is FlowClass.HUMAN_QOE:
        return 0.28
    return 0.50

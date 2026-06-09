"""Profile/objective-aware transport selection for ROS 2 fleet experiments."""

from __future__ import annotations

import json
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Literal, Mapping


ObjectiveDirection = Literal["max", "min"]
ConstraintOperator = Literal[">=", "<=", ">", "<"]
DEFAULT_TICKS_PER_SECOND = 50


@dataclass(frozen=True)
class MetricConstraint:
    """Hard eligibility constraint for one metric."""

    metric: str
    operator: ConstraintOperator
    threshold: float

    def satisfied_by(self, value: float) -> bool:
        if self.operator == ">=":
            return value >= self.threshold
        if self.operator == "<=":
            return value <= self.threshold
        if self.operator == ">":
            return value > self.threshold
        if self.operator == "<":
            return value < self.threshold
        raise ValueError(f"unknown constraint operator: {self.operator}")

    def as_dict(self) -> dict[str, object]:
        return {
            "metric": self.metric,
            "operator": self.operator,
            "threshold": self.threshold,
        }


@dataclass(frozen=True)
class TransportObjective:
    """Weighted objective vector used to rank transport candidates."""

    name: str
    description: str
    weights: Mapping[str, float]
    directions: Mapping[str, ObjectiveDirection]
    constraints: tuple[MetricConstraint, ...] = ()

    def __post_init__(self) -> None:
        missing = [metric for metric in self.weights if metric not in self.directions]
        if missing:
            raise ValueError(f"missing objective directions for: {', '.join(missing)}")
        for metric, weight in self.weights.items():
            if weight < 0:
                raise ValueError(f"objective weight must be non-negative: {metric}")

    def as_dict(self) -> dict[str, object]:
        return {
            "name": self.name,
            "description": self.description,
            "weights": dict(self.weights),
            "directions": dict(self.directions),
            "constraints": [constraint.as_dict() for constraint in self.constraints],
        }


@dataclass(frozen=True)
class TransportBinding:
    """Runtime transport decision that can cross the shim/sidecar boundary."""

    profile: str
    objective: str
    policy: str
    packet_format: str
    rmw: str
    score: float
    source: str | None = None
    eligible: bool = True
    constraint_relaxed: bool = False
    constraint_violations: tuple[Mapping[str, object], ...] = ()

    @classmethod
    def from_selection(cls, selection: Mapping[str, object]) -> "TransportBinding":
        return cls(
            profile=str(selection.get("profile", "unknown")),
            objective=str(selection.get("objective", "unknown")),
            policy=str(selection.get("selected_policy", "")),
            packet_format=str(selection.get("packet_format", "")),
            rmw=str(selection.get("rmw", "")),
            score=_numeric(selection.get("raw_score", selection.get("score", 0.0))),
            source=_optional_str(selection.get("source")),
            eligible=bool(selection.get("eligible", True)),
            constraint_relaxed=bool(selection.get("constraint_relaxed", False)),
            constraint_violations=tuple(
                item
                for item in selection.get("constraint_violations", [])
                if isinstance(item, Mapping)
            ),
        )

    @classmethod
    def from_payload(cls, payload: object) -> "TransportBinding | None":
        if payload is None or payload == "":
            return None
        if isinstance(payload, TransportBinding):
            return payload
        if not isinstance(payload, Mapping):
            raise ValueError("transport binding payload must be an object")
        return cls(
            profile=str(payload.get("profile", "unknown")),
            objective=str(payload.get("objective", "unknown")),
            policy=str(payload.get("policy", payload.get("selected_policy", ""))),
            packet_format=str(payload.get("packet_format", "")),
            rmw=str(payload.get("rmw", "")),
            score=_numeric(payload.get("score", payload.get("raw_score", 0.0))),
            source=_optional_str(payload.get("source")),
            eligible=bool(payload.get("eligible", True)),
            constraint_relaxed=bool(payload.get("constraint_relaxed", False)),
            constraint_violations=tuple(
                item
                for item in payload.get("constraint_violations", [])
                if isinstance(item, Mapping)
            ),
        )

    def as_payload(self) -> dict[str, object]:
        return {
            "schema_version": "fleetrmw.transport_binding.v1",
            "profile": self.profile,
            "objective": self.objective,
            "policy": self.policy,
            "packet_format": self.packet_format,
            "rmw": self.rmw,
            "score": self.score,
            "source": self.source,
            "eligible": self.eligible,
            "constraint_relaxed": self.constraint_relaxed,
            "constraint_violations": [
                dict(item) for item in self.constraint_violations
            ],
        }


@dataclass(frozen=True)
class ProfileObservation:
    """Runtime network observation used by the binding manager."""

    capacity_bytes_per_second: float
    rtt_ms: float
    jitter_ms: float
    loss: float

    @classmethod
    def from_link_payload(
        cls,
        payload: object,
        *,
        ticks_per_second: float = DEFAULT_TICKS_PER_SECOND,
    ) -> "ProfileObservation":
        data = dict(payload) if isinstance(payload, Mapping) else {}
        if "capacity_bytes_per_second" in data:
            capacity = _numeric(data.get("capacity_bytes_per_second"))
        else:
            capacity = _numeric(data.get("capacity_bytes_per_tick", 0.0))
            capacity *= ticks_per_second
        return cls(
            capacity_bytes_per_second=capacity,
            rtt_ms=_numeric(data.get("rtt_ms", data.get("delay_ms", 20.0))),
            jitter_ms=_numeric(data.get("jitter_ms", 0.0)),
            loss=_loss_fraction(data.get("loss", data.get("loss_percent", 0.0))),
        )

    def as_payload(self) -> dict[str, object]:
        return {
            "capacity_bytes_per_second": self.capacity_bytes_per_second,
            "rtt_ms": self.rtt_ms,
            "jitter_ms": self.jitter_ms,
            "loss": self.loss,
        }


@dataclass(frozen=True)
class ProfilePrototype:
    """Measured profile centroid used by the adaptive estimator."""

    profile: str
    observation: ProfileObservation

    @classmethod
    def from_config(
        cls,
        profile: str,
        config: Mapping[str, object],
    ) -> "ProfilePrototype":
        delay_ms = _numeric(config.get("delay_ms", config.get("rtt_ms", 20.0)))
        rtt_ms = _numeric(config.get("rtt_ms", delay_ms * 2.0))
        return cls(
            profile=profile,
            observation=ProfileObservation(
                capacity_bytes_per_second=_numeric(
                    config.get("capacity_bytes_per_second", 0.0)
                ),
                rtt_ms=rtt_ms,
                jitter_ms=_numeric(config.get("jitter_ms", 0.0)),
                loss=_loss_fraction(
                    config.get("loss", config.get("loss_percent", 0.0))
                ),
            ),
        )


@dataclass(frozen=True)
class ProfileEstimate:
    """Current adaptive profile decision and confidence."""

    profile: str
    candidate_profile: str
    confidence: float
    margin: float
    changed: bool
    dwell_ticks: int
    smoothed_observation: ProfileObservation
    scores: Mapping[str, float]

    def as_payload(self) -> dict[str, object]:
        return {
            "profile": self.profile,
            "candidate_profile": self.candidate_profile,
            "confidence": self.confidence,
            "margin": self.margin,
            "changed": self.changed,
            "dwell_ticks": self.dwell_ticks,
            "smoothed_observation": self.smoothed_observation.as_payload(),
            "scores": dict(self.scores),
        }


@dataclass(frozen=True)
class AdaptiveBindingDecision:
    """Adaptive estimator output for one tick/window."""

    binding: TransportBinding
    estimate: ProfileEstimate

    def as_payload(self) -> dict[str, object]:
        return {
            "binding": self.binding.as_payload(),
            "estimate": self.estimate.as_payload(),
        }


class TransportBindingManager:
    """Resolve a runtime transport binding from profile observations."""

    def __init__(self, selector_result: Mapping[str, object]) -> None:
        bindings = selector_result.get("bindings", [])
        if not isinstance(bindings, list) or not bindings:
            bindings = [
                TransportBinding.from_selection(selection).as_payload()
                for selection in selector_result.get("selections", [])
                if isinstance(selection, Mapping)
            ]
        self.bindings = tuple(
            binding
            for binding in (
                TransportBinding.from_payload(item) for item in bindings
            )
            if binding is not None
        )
        if not self.bindings:
            raise ValueError("selector result does not contain transport bindings")
        self.prototypes = tuple(_profile_prototypes(selector_result, self.bindings))

    @classmethod
    def from_summary_path(cls, path: str | Path) -> "TransportBindingManager":
        return cls(load_repeated_summary(path))

    def binding_for_profile(
        self,
        profile: str,
        *,
        objective: str | None = None,
    ) -> TransportBinding:
        if objective:
            for binding in self.bindings:
                if binding.profile == profile and binding.objective == objective:
                    return binding
            choices = ", ".join(
                sorted(
                    f"{binding.profile}/{binding.objective}"
                    for binding in self.bindings
                )
            )
            raise ValueError(
                "transport profile/objective not found: "
                f"{profile}/{objective}; choices: {choices}"
            )
        for binding in self.bindings:
            if binding.profile == profile:
                return binding
        choices = ", ".join(sorted({binding.profile for binding in self.bindings}))
        raise ValueError(f"transport profile not found: {profile}; choices: {choices}")

    def binding_for_observation(
        self,
        observation: ProfileObservation,
        *,
        objective: str | None = None,
    ) -> TransportBinding:
        return self.binding_for_profile(
            classify_network_profile(observation),
            objective=objective,
        )

    def binding_for_link_payload(
        self,
        payload: object,
        *,
        ticks_per_second: float = DEFAULT_TICKS_PER_SECOND,
        objective: str | None = None,
    ) -> TransportBinding:
        observation = ProfileObservation.from_link_payload(
            payload,
            ticks_per_second=ticks_per_second,
        )
        return self.binding_for_observation(observation, objective=objective)

    def adaptive_estimator(
        self,
        *,
        smoothing_alpha: float = 0.35,
        hysteresis_margin: float = 0.06,
        min_dwell_ticks: int = 2,
    ) -> "AdaptiveTransportBindingEstimator":
        return AdaptiveTransportBindingEstimator(
            self,
            prototypes=self.prototypes,
            smoothing_alpha=smoothing_alpha,
            hysteresis_margin=hysteresis_margin,
            min_dwell_ticks=min_dwell_ticks,
        )


class AdaptiveTransportBindingEstimator:
    """Smooth link telemetry and avoid profile flapping before binding changes."""

    def __init__(
        self,
        manager: TransportBindingManager,
        *,
        prototypes: Iterable[ProfilePrototype],
        smoothing_alpha: float = 0.35,
        hysteresis_margin: float = 0.06,
        min_dwell_ticks: int = 2,
    ) -> None:
        if not 0 < smoothing_alpha <= 1:
            raise ValueError("smoothing_alpha must be in (0, 1]")
        if hysteresis_margin < 0:
            raise ValueError("hysteresis_margin must be non-negative")
        if min_dwell_ticks < 0:
            raise ValueError("min_dwell_ticks must be non-negative")
        self.manager = manager
        self.prototypes = tuple(prototypes)
        if not self.prototypes:
            raise ValueError("at least one profile prototype is required")
        self.smoothing_alpha = smoothing_alpha
        self.hysteresis_margin = hysteresis_margin
        self.min_dwell_ticks = min_dwell_ticks
        self._smoothed: ProfileObservation | None = None
        self._active_profile: str | None = None
        self._dwell_ticks = 0

    def update(
        self,
        observation: ProfileObservation,
        *,
        objective: str | None = None,
    ) -> AdaptiveBindingDecision:
        self._smoothed = (
            observation
            if self._smoothed is None
            else _smooth_observation(
                previous=self._smoothed,
                current=observation,
                alpha=self.smoothing_alpha,
            )
        )
        scores = score_profile_observation(self._smoothed, self.prototypes)
        ranked = sorted(scores.items(), key=lambda item: item[1], reverse=True)
        candidate_profile, candidate_score = ranked[0]
        second_score = ranked[1][1] if len(ranked) > 1 else 0.0
        margin = max(0.0, candidate_score - second_score)
        changed = False

        if self._active_profile is None:
            self._active_profile = candidate_profile
            self._dwell_ticks = 0
            changed = True
        else:
            active_score = scores.get(self._active_profile, 0.0)
            can_switch = self._dwell_ticks >= self.min_dwell_ticks
            strong_candidate = (
                candidate_score >= active_score + self.hysteresis_margin
            )
            if (
                candidate_profile != self._active_profile
                and can_switch
                and strong_candidate
            ):
                self._active_profile = candidate_profile
                self._dwell_ticks = 0
                changed = True
            else:
                self._dwell_ticks += 1

        confidence = max(0.0, min(1.0, candidate_score * (0.5 + margin / 2.0)))
        estimate = ProfileEstimate(
            profile=self._active_profile,
            candidate_profile=candidate_profile,
            confidence=confidence,
            margin=margin,
            changed=changed,
            dwell_ticks=self._dwell_ticks,
            smoothed_observation=self._smoothed,
            scores=scores,
        )
        return AdaptiveBindingDecision(
            binding=self.manager.binding_for_profile(
                self._active_profile,
                objective=objective,
            ),
            estimate=estimate,
        )

    def update_from_link_payload(
        self,
        payload: object,
        *,
        ticks_per_second: float = DEFAULT_TICKS_PER_SECOND,
        objective: str | None = None,
    ) -> AdaptiveBindingDecision:
        return self.update(
            ProfileObservation.from_link_payload(
                payload,
                ticks_per_second=ticks_per_second,
            ),
            objective=objective,
        )


DEFAULT_PROFILE_CONFIGS: dict[str, dict[str, object]] = {
    "wifi": {
        "capacity_bytes_per_second": 120_000,
        "delay_ms": 20,
        "jitter_ms": 5,
        "loss_percent": 1,
    },
    "wan": {
        "capacity_bytes_per_second": 90_000,
        "delay_ms": 60,
        "jitter_ms": 15,
        "loss_percent": 1.5,
    },
    "roaming": {
        "capacity_bytes_per_second": 70_000,
        "delay_ms": 80,
        "jitter_ms": 25,
        "loss_percent": 3,
    },
}


BUILTIN_TRANSPORT_OBJECTIVES: dict[str, TransportObjective] = {
    "balanced_safety_utility": TransportObjective(
        name="balanced_safety_utility",
        description=(
            "Balanced fleet objective for shared autonomy: preserve semantic "
            "utility, control delivery, deadline behavior, and tail latency."
        ),
        weights={
            "semantic_utility_delivered_mean": 0.28,
            "control_delivery_ratio_mean": 0.20,
            "control_starvation_events_mean": 0.14,
            "deadline_miss_ratio_mean": 0.14,
            "loss_ratio_mean": 0.10,
            "latency_p95_ms_mean": 0.10,
            "control_non_delivery_events_mean": 0.04,
        },
        directions={
            "semantic_utility_delivered_mean": "max",
            "control_delivery_ratio_mean": "max",
            "control_starvation_events_mean": "min",
            "deadline_miss_ratio_mean": "min",
            "loss_ratio_mean": "min",
            "latency_p95_ms_mean": "min",
            "control_non_delivery_events_mean": "min",
        },
        constraints=(
            MetricConstraint("control_delivery_ratio_mean", ">=", 0.90),
            MetricConstraint("control_non_delivery_events_mean", "<=", 0.0),
        ),
    ),
    "teleop_latency": TransportObjective(
        name="teleop_latency",
        description=(
            "Latency-first objective for remote supervision or teleoperation "
            "while still enforcing basic control delivery."
        ),
        weights={
            "latency_p95_ms_mean": 0.34,
            "latency_p99_ms_mean": 0.16,
            "control_delivery_ratio_mean": 0.18,
            "deadline_miss_ratio_mean": 0.12,
            "loss_ratio_mean": 0.10,
            "semantic_utility_delivered_mean": 0.10,
        },
        directions={
            "latency_p95_ms_mean": "min",
            "latency_p99_ms_mean": "min",
            "control_delivery_ratio_mean": "max",
            "deadline_miss_ratio_mean": "min",
            "loss_ratio_mean": "min",
            "semantic_utility_delivered_mean": "max",
        },
        constraints=(
            MetricConstraint("control_delivery_ratio_mean", ">=", 0.90),
            MetricConstraint("control_non_delivery_events_mean", "<=", 0.0),
        ),
    ),
    "autonomy_safety": TransportObjective(
        name="autonomy_safety",
        description=(
            "Safety-biased autonomous fleet objective: prioritize control "
            "continuity, low loss, and deadline protection before throughput."
        ),
        weights={
            "control_delivery_ratio_mean": 0.28,
            "control_starvation_events_mean": 0.20,
            "deadline_miss_ratio_mean": 0.18,
            "loss_ratio_mean": 0.16,
            "latency_p95_ms_mean": 0.10,
            "semantic_utility_delivered_mean": 0.08,
        },
        directions={
            "control_delivery_ratio_mean": "max",
            "control_starvation_events_mean": "min",
            "deadline_miss_ratio_mean": "min",
            "loss_ratio_mean": "min",
            "latency_p95_ms_mean": "min",
            "semantic_utility_delivered_mean": "max",
        },
        constraints=(
            MetricConstraint("control_delivery_ratio_mean", ">=", 0.95),
            MetricConstraint("control_non_delivery_events_mean", "<=", 0.0),
        ),
    ),
    "throughput_utility": TransportObjective(
        name="throughput_utility",
        description=(
            "Fleet telemetry objective: maximize delivered semantic utility and "
            "received samples while keeping loss and deadlines visible."
        ),
        weights={
            "semantic_utility_delivered_mean": 0.34,
            "rx_mean": 0.22,
            "bytes_rx_mean": 0.10,
            "control_delivery_ratio_mean": 0.14,
            "loss_ratio_mean": 0.10,
            "deadline_miss_ratio_mean": 0.10,
        },
        directions={
            "semantic_utility_delivered_mean": "max",
            "rx_mean": "max",
            "bytes_rx_mean": "max",
            "control_delivery_ratio_mean": "max",
            "loss_ratio_mean": "min",
            "deadline_miss_ratio_mean": "min",
        },
        constraints=(
            MetricConstraint("control_delivery_ratio_mean", ">=", 0.85),
            MetricConstraint("control_non_delivery_events_mean", "<=", 0.0),
        ),
    ),
}


def load_repeated_summary(path: str | Path) -> dict[str, object]:
    """Load one repeated-run summary JSON file."""

    return json.loads(Path(path).read_text(encoding="utf-8"))


def select_transports_from_paths(
    paths: Iterable[str | Path],
    objective: str | TransportObjective = "balanced_safety_utility",
) -> dict[str, object]:
    """Select transport candidates for repeated-run summaries on disk."""

    resolved_objective = resolve_transport_objective(objective)
    selections = []
    sources = []
    for path in paths:
        source = Path(path)
        summary = load_repeated_summary(source)
        sources.append(str(source))
        selections.append(
            select_transport_for_profile(
                summary,
                objective=resolved_objective,
                source=str(source),
            )
        )
    return {
        "objective": resolved_objective.as_dict(),
        "sources": sources,
        "selections": selections,
        "bindings": [
            TransportBinding.from_selection(selection).as_payload()
            for selection in selections
        ],
    }


def select_transport_for_profile(
    summary: Mapping[str, object],
    *,
    objective: str | TransportObjective = "balanced_safety_utility",
    profile: str | None = None,
    source: str | None = None,
) -> dict[str, object]:
    """Rank transport candidates for a single profile summary."""

    resolved_objective = resolve_transport_objective(objective)
    policies = _summary_policies(summary)
    if not policies:
        raise ValueError("summary does not contain policies")

    profile_label = profile or _summary_profile(summary, source)
    profile_config = _summary_profile_config(summary)
    ranked = rank_transport_candidates(policies, resolved_objective)
    selected = ranked[0]

    return {
        "profile": profile_label,
        "source": source,
        "profile_config": profile_config,
        "objective": resolved_objective.name,
        "selected_policy": selected["policy"],
        "packet_format": selected["packet_format"],
        "rmw": selected["rmw"],
        "score": selected["score"],
        "raw_score": selected["raw_score"],
        "eligible": selected["eligible"],
        "constraint_relaxed": selected["constraint_relaxed"],
        "constraint_violations": selected["constraint_violations"],
        "pareto_frontier": list(summary.get("pareto_frontier", [])),
        "explanation": _explain_selection(profile_label, selected, resolved_objective),
        "ranking": ranked,
    }


def rank_transport_candidates(
    policies: Iterable[Mapping[str, object]],
    objective: TransportObjective,
) -> list[dict[str, object]]:
    """Return ranked transport candidates with normalized objective scores."""

    rows = [dict(policy) for policy in policies]
    metrics = list(objective.weights)
    normalized = _normalize_metrics(rows, metrics, objective.directions)
    violations_by_policy = {
        str(row.get("policy", "")): _constraint_violations(row, objective.constraints)
        for row in rows
    }
    any_feasible = any(not violations for violations in violations_by_policy.values())
    total_weight = sum(objective.weights.values())
    if total_weight <= 0:
        raise ValueError("objective must contain at least one positive weight")

    candidates = []
    for row in rows:
        policy = str(row.get("policy", ""))
        packet_format, rmw = split_policy_name(policy)
        weighted_terms = {
            metric: normalized[policy][metric] * objective.weights[metric]
            for metric in metrics
        }
        raw_score = sum(weighted_terms.values()) / total_weight
        violations = violations_by_policy[policy]
        eligible = not violations or not any_feasible
        score = raw_score if eligible else -1.0
        candidates.append(
            {
                "policy": policy,
                "packet_format": packet_format,
                "rmw": rmw,
                "score": score,
                "raw_score": raw_score,
                "rank_score": score,
                "eligible": eligible,
                "constraint_relaxed": bool(violations and not any_feasible),
                "constraint_violations": violations,
                "pareto_frontier": bool(row.get("pareto_frontier", False)),
                "metrics": {
                    metric: _numeric(row.get(metric, 0.0)) for metric in metrics
                },
                "normalized_metrics": normalized[policy],
                "weighted_terms": weighted_terms,
            }
        )

    candidates.sort(
        key=lambda candidate: (
            1 if candidate["eligible"] else 0,
            float(candidate["score"]),
            1 if candidate["pareto_frontier"] else 0,
            str(candidate["policy"]),
        ),
        reverse=True,
    )
    for index, candidate in enumerate(candidates, start=1):
        candidate["rank"] = index
    return candidates


def resolve_transport_objective(
    objective: str | TransportObjective,
) -> TransportObjective:
    if isinstance(objective, TransportObjective):
        return objective
    if objective not in BUILTIN_TRANSPORT_OBJECTIVES:
        choices = ", ".join(sorted(BUILTIN_TRANSPORT_OBJECTIVES))
        raise ValueError(
            f"unknown transport objective: {objective}; choices: {choices}"
        )
    return BUILTIN_TRANSPORT_OBJECTIVES[objective]


def binding_from_selection(selection: Mapping[str, object]) -> TransportBinding:
    return TransportBinding.from_selection(selection)


def transport_binding_payload(
    binding: TransportBinding | Mapping[str, object] | None,
) -> dict[str, object] | None:
    resolved = TransportBinding.from_payload(binding)
    return resolved.as_payload() if resolved else None


def classify_network_profile(observation: ProfileObservation) -> str:
    """Classify a runtime link into the measured selector profile set."""

    if (
        observation.capacity_bytes_per_second <= 80_000
        or observation.loss >= 0.025
        or observation.jitter_ms >= 20
        or observation.rtt_ms >= 140
    ):
        return "roaming"
    if (
        observation.capacity_bytes_per_second <= 100_000
        or observation.loss >= 0.012
        or observation.jitter_ms >= 10
        or observation.rtt_ms >= 80
    ):
        return "wan"
    return "wifi"


def score_profile_observation(
    observation: ProfileObservation,
    prototypes: Iterable[ProfilePrototype],
) -> dict[str, float]:
    """Return profile-likelihood scores in [0, 1] for one observation."""

    scores = {}
    for prototype in prototypes:
        distance = _profile_distance(observation, prototype.observation)
        scores[prototype.profile] = 1.0 / (1.0 + distance)
    return scores


def split_policy_name(policy: str) -> tuple[str, str]:
    if "/" in policy:
        packet_format, rmw = policy.split("/", 1)
        return packet_format, rmw
    return "unknown", policy


def render_transport_selection_markdown(
    result: Mapping[str, object],
    *,
    title: str = "ROS 2 Profile Objective Transport Selector",
) -> str:
    """Render a Markdown selector report."""

    objective = result.get("objective", {})
    objective_name = (
        objective.get("name", "unknown")
        if isinstance(objective, dict)
        else "unknown"
    )
    description = (
        objective.get("description", "")
        if isinstance(objective, dict)
        else ""
    )
    selections = [
        selection
        for selection in result.get("selections", [])
        if isinstance(selection, dict)
    ]
    lines = [
        f"# {title}",
        "",
        "## Objective",
        "",
        f"- Name: `{objective_name}`",
        f"- Description: {description}",
        "",
    ]
    if isinstance(objective, dict):
        lines.extend(_objective_lines(objective))
    lines.extend(
        [
            "## Selected Policies",
            "",
            _markdown_table(
                [
                    "profile",
                    "selected policy",
                    "packet",
                    "RMW",
                    "score",
                    "eligible",
                    "utility",
                    "ctrl delivery",
                    "deadline miss",
                    "loss",
                    "p95 ms",
                ],
                [_selection_row(selection) for selection in selections],
            ),
            "",
        ]
    )
    for selection in selections:
        lines.extend(_profile_selection_lines(selection))
        lines.append("")
    return "\n".join(lines)


def write_transport_selection_json(
    result: Mapping[str, object],
    output: str | Path,
) -> None:
    output_path = Path(output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(result, indent=2, sort_keys=True),
        encoding="utf-8",
    )


def write_transport_selection_markdown(
    result: Mapping[str, object],
    output: str | Path,
    *,
    title: str = "ROS 2 Profile Objective Transport Selector",
) -> None:
    output_path = Path(output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        render_transport_selection_markdown(result, title=title),
        encoding="utf-8",
    )


def _normalize_metrics(
    policies: list[dict[str, object]],
    metrics: list[str],
    directions: Mapping[str, ObjectiveDirection],
) -> dict[str, dict[str, float]]:
    values_by_metric = {
        metric: [_numeric(row.get(metric, 0.0)) for row in policies]
        for metric in metrics
    }
    normalized: dict[str, dict[str, float]] = {}
    for row in policies:
        policy = str(row.get("policy", ""))
        normalized[policy] = {}
        for metric in metrics:
            values = values_by_metric[metric]
            minimum = min(values)
            maximum = max(values)
            value = _numeric(row.get(metric, 0.0))
            if math.isclose(maximum, minimum, rel_tol=0.0, abs_tol=1e-12):
                score = 1.0
            elif directions[metric] == "max":
                score = (value - minimum) / (maximum - minimum)
            elif directions[metric] == "min":
                score = (maximum - value) / (maximum - minimum)
            else:
                raise ValueError(f"unknown objective direction: {directions[metric]}")
            normalized[policy][metric] = max(0.0, min(1.0, score))
    return normalized


def _profile_prototypes(
    selector_result: Mapping[str, object],
    bindings: Iterable[TransportBinding],
) -> list[ProfilePrototype]:
    configs: dict[str, Mapping[str, object]] = {}
    for selection in selector_result.get("selections", []):
        if not isinstance(selection, Mapping):
            continue
        profile = selection.get("profile")
        config = selection.get("profile_config")
        if isinstance(profile, str) and isinstance(config, Mapping):
            configs[profile] = config
    for profile_summary in selector_result.get("profiles", []):
        if not isinstance(profile_summary, Mapping):
            continue
        profile = profile_summary.get("profile")
        config = profile_summary.get("config")
        if isinstance(profile, str) and isinstance(config, Mapping):
            configs.setdefault(profile, config)

    prototypes = []
    for profile in sorted({binding.profile for binding in bindings}):
        config = configs.get(profile) or DEFAULT_PROFILE_CONFIGS.get(profile)
        if config:
            prototypes.append(ProfilePrototype.from_config(profile, config))
    if prototypes:
        return prototypes
    return [
        ProfilePrototype.from_config(profile, config)
        for profile, config in sorted(DEFAULT_PROFILE_CONFIGS.items())
    ]


def _smooth_observation(
    *,
    previous: ProfileObservation,
    current: ProfileObservation,
    alpha: float,
) -> ProfileObservation:
    return ProfileObservation(
        capacity_bytes_per_second=_ewma(
            previous.capacity_bytes_per_second,
            current.capacity_bytes_per_second,
            alpha,
        ),
        rtt_ms=_ewma(previous.rtt_ms, current.rtt_ms, alpha),
        jitter_ms=_ewma(previous.jitter_ms, current.jitter_ms, alpha),
        loss=_ewma(previous.loss, current.loss, alpha),
    )


def _ewma(previous: float, current: float, alpha: float) -> float:
    return previous * (1.0 - alpha) + current * alpha


def _profile_distance(
    observation: ProfileObservation,
    prototype: ProfileObservation,
) -> float:
    capacity_distance = _log_ratio_distance(
        observation.capacity_bytes_per_second,
        prototype.capacity_bytes_per_second,
    )
    rtt_distance = _relative_distance(observation.rtt_ms, prototype.rtt_ms, 180.0)
    jitter_distance = _relative_distance(
        observation.jitter_ms,
        prototype.jitter_ms,
        30.0,
    )
    loss_distance = _relative_distance(observation.loss, prototype.loss, 0.04)
    return (
        capacity_distance * 0.30
        + rtt_distance * 0.25
        + jitter_distance * 0.20
        + loss_distance * 0.25
    )


def _relative_distance(left: float, right: float, floor: float) -> float:
    scale = max(abs(left), abs(right), floor, 1e-9)
    return abs(left - right) / scale


def _log_ratio_distance(left: float, right: float) -> float:
    left = max(left, 1.0)
    right = max(right, 1.0)
    return abs(math.log(left / right, 2.0))


def _constraint_violations(
    row: Mapping[str, object],
    constraints: Iterable[MetricConstraint],
) -> list[dict[str, object]]:
    violations = []
    for constraint in constraints:
        value = _numeric(row.get(constraint.metric, 0.0))
        if not constraint.satisfied_by(value):
            violations.append(
                {
                    "metric": constraint.metric,
                    "operator": constraint.operator,
                    "threshold": constraint.threshold,
                    "value": value,
                }
            )
    return violations


def _summary_policies(summary: Mapping[str, object]) -> list[Mapping[str, object]]:
    policies = summary.get("policies", [])
    if isinstance(policies, list) and policies:
        return [row for row in policies if isinstance(row, Mapping)]
    profiles = summary.get("profiles", [])
    if isinstance(profiles, list):
        for profile in profiles:
            if isinstance(profile, Mapping):
                nested = profile.get("policies", [])
                if isinstance(nested, list) and nested:
                    return [row for row in nested if isinstance(row, Mapping)]
    return []


def _summary_profile(summary: Mapping[str, object], source: str | None) -> str:
    direct = summary.get("profile")
    if isinstance(direct, str) and direct:
        return direct
    profiles = summary.get("profiles", [])
    if isinstance(profiles, list):
        for profile in profiles:
            if isinstance(profile, Mapping):
                label = profile.get("profile")
                if isinstance(label, str) and label:
                    return label
    if source:
        stem = Path(source).stem
        for label in ("wifi", "wan", "roaming", "lan"):
            if f"_{label}_" in f"_{stem}_":
                return label
        return stem
    return "unknown"


def _summary_profile_config(summary: Mapping[str, object]) -> dict[str, object]:
    config = summary.get("config")
    if isinstance(config, Mapping):
        return dict(config)
    profiles = summary.get("profiles", [])
    if isinstance(profiles, list):
        for profile in profiles:
            if isinstance(profile, Mapping):
                profile_config = profile.get("config")
                if isinstance(profile_config, Mapping):
                    return dict(profile_config)
    return {}


def _explain_selection(
    profile: str,
    selected: Mapping[str, object],
    objective: TransportObjective,
) -> str:
    metrics = selected.get("metrics", {})
    if not isinstance(metrics, Mapping):
        metrics = {}
    top_metrics = sorted(
        objective.weights,
        key=lambda metric: objective.weights[metric],
        reverse=True,
    )[:4]
    metric_text = ", ".join(
        f"{metric}={_format_number(_numeric(metrics.get(metric, 0.0)))}"
        for metric in top_metrics
    )
    policy = selected.get("policy", "")
    score = _format_number(float(selected.get("raw_score", 0.0)))
    if selected.get("constraint_relaxed"):
        eligibility = (
            "No candidate satisfied every hard constraint, so constraints were "
            "relaxed."
        )
    elif selected.get("eligible"):
        eligibility = "It satisfies every hard constraint."
    else:
        eligibility = (
            "It is ranked behind feasible candidates because it violates a "
            "constraint."
        )
    return (
        f"For `{profile}`, `{policy}` scores `{score}` under "
        f"`{objective.name}`. {eligibility} Key objective metrics: {metric_text}."
    )


def _objective_lines(objective: Mapping[str, object]) -> list[str]:
    weights = objective.get("weights", {})
    directions = objective.get("directions", {})
    constraints = objective.get("constraints", [])
    lines = [
        "### Metrics",
        "",
        _markdown_table(
            ["metric", "direction", "weight"],
            [
                [
                    str(metric),
                    (
                        str(directions.get(metric, ""))
                        if isinstance(directions, Mapping)
                        else ""
                    ),
                    _format_number(_numeric(weight)),
                ]
                for metric, weight in (
                    weights.items() if isinstance(weights, Mapping) else []
                )
            ],
        ),
        "",
        "### Constraints",
        "",
    ]
    if isinstance(constraints, list) and constraints:
        for constraint in constraints:
            if not isinstance(constraint, Mapping):
                continue
            lines.append(
                "- "
                f"`{constraint.get('metric')}` "
                f"{constraint.get('operator')} "
                f"`{_format_number(_numeric(constraint.get('threshold', 0.0)))}`"
            )
    else:
        lines.append("- None")
    lines.append("")
    return lines


def _profile_selection_lines(selection: Mapping[str, object]) -> list[str]:
    profile = selection.get("profile", "unknown")
    explanation = selection.get("explanation", "")
    ranking = [
        row
        for row in selection.get("ranking", [])
        if isinstance(row, Mapping)
    ]
    lines = [
        f"## Profile `{profile}`",
        "",
        str(explanation),
        "",
        _markdown_table(
            [
                "rank",
                "policy",
                "score",
                "eligible",
                "pareto",
                "utility",
                "ctrl delivery",
                "deadline miss",
                "loss",
                "p95 ms",
            ],
            [_ranking_row(row) for row in ranking],
        ),
    ]
    return lines


def _selection_row(selection: Mapping[str, object]) -> list[str]:
    selected_policy = str(selection.get("selected_policy", ""))
    selected = _selected_candidate(selection)
    metrics = selected.get("metrics", {}) if isinstance(selected, Mapping) else {}
    if not isinstance(metrics, Mapping):
        metrics = {}
    return [
        str(selection.get("profile", "")),
        selected_policy,
        str(selection.get("packet_format", "")),
        str(selection.get("rmw", "")),
        _format_number(float(selection.get("raw_score", selection.get("score", 0.0)))),
        "yes" if selection.get("eligible") else "no",
        _format_number(_numeric(metrics.get("semantic_utility_delivered_mean", 0.0))),
        _format_number(_numeric(metrics.get("control_delivery_ratio_mean", 0.0))),
        _format_number(_numeric(metrics.get("deadline_miss_ratio_mean", 0.0))),
        _format_number(_numeric(metrics.get("loss_ratio_mean", 0.0))),
        _format_number(_numeric(metrics.get("latency_p95_ms_mean", 0.0))),
    ]


def _ranking_row(row: Mapping[str, object]) -> list[str]:
    metrics = row.get("metrics", {})
    if not isinstance(metrics, Mapping):
        metrics = {}
    return [
        str(row.get("rank", "")),
        str(row.get("policy", "")),
        _format_number(float(row.get("raw_score", row.get("score", 0.0)))),
        "yes" if row.get("eligible") else "no",
        "yes" if row.get("pareto_frontier") else "no",
        _format_number(_numeric(metrics.get("semantic_utility_delivered_mean", 0.0))),
        _format_number(_numeric(metrics.get("control_delivery_ratio_mean", 0.0))),
        _format_number(_numeric(metrics.get("deadline_miss_ratio_mean", 0.0))),
        _format_number(_numeric(metrics.get("loss_ratio_mean", 0.0))),
        _format_number(_numeric(metrics.get("latency_p95_ms_mean", 0.0))),
    ]


def _selected_candidate(selection: Mapping[str, object]) -> Mapping[str, object]:
    selected_policy = selection.get("selected_policy")
    ranking = selection.get("ranking", [])
    if isinstance(ranking, list):
        for row in ranking:
            if isinstance(row, Mapping) and row.get("policy") == selected_policy:
                return row
    return {}


def _markdown_table(headers: list[str], rows: list[list[str]]) -> str:
    header = "| " + " | ".join(headers) + " |"
    separator = "| " + " | ".join("---" for _ in headers) + " |"
    body = ["| " + " | ".join(str(value) for value in row) + " |" for row in rows]
    return "\n".join([header, separator, *body])


def _numeric(value: object) -> float:
    try:
        number = float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return 0.0
    if math.isnan(number) or math.isinf(number):
        return 0.0
    return number


def _optional_str(value: object) -> str | None:
    if value is None or value == "":
        return None
    return str(value)


def _loss_fraction(value: object) -> float:
    loss = _numeric(value)
    return loss / 100.0 if loss > 1.0 else loss


def _format_number(value: float) -> str:
    if math.isclose(value, round(value), abs_tol=1e-9):
        return str(int(round(value)))
    if abs(value) < 1:
        return f"{value:.4f}"
    return f"{value:.2f}"

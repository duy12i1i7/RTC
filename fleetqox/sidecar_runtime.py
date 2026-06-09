"""Runtime skeleton for a FleetRMW sidecar.

The runtime receives ROS-like flow observations over a local TCP socket, applies
FleetQoX predictive admission, logs sidecar contract events, and emits admitted
messages as UDP packets. It is intentionally small and dependency-free so it can
run inside Docker/netem before a real RMW implementation exists.
"""

from __future__ import annotations

import json
import math
import random
import socket
import threading
import time
from dataclasses import dataclass
from collections import Counter
from pathlib import Path
from typing import Callable, Iterable, Mapping

from .control_plane import (
    AdaptiveSemanticContractAdmissionController,
    ContextualProfiledLagrangianAdmissionController,
    IntentAwareContextualAdmissionController,
    LagrangianAdmissionConfig,
    LagrangianRiskPredictiveAdmissionController,
    PredictiveAdmissionController,
    ProfileAwareLagrangianAdmissionController,
    RiskConstrainedPredictiveAdmissionController,
    RobotBudgetAwareAdmissionController,
    RobotBudgetConfig,
    SemanticContractAdmissionController,
)
from .model import (
    FlowClass,
    FlowDecision,
    FlowObservation,
    FlowSpec,
    NetworkLink,
    QoEProfile,
    QoSProfile,
    TaskContext,
)
from .fleet_optimizer import (
    FleetFlowDemand,
    FleetOptimizerConfig,
    FleetPathDecision,
    FleetQoEPathOptimizer,
    PathTelemetry,
    RobotQoEState,
    TransportMode,
)
from .rmw_frame import data_frame_from_sidecar_event, encode_data_frame
from .sidecar_contract import SIDECAR_TRACE_SCHEMA_VERSION, is_admitted_action, validate_event
from .scheduler import CausalSemanticDeadlineScheduler
from .semantic_contract import control_intent_deadline_ms, supervisory_intent_deadline_ms
from .simulator import (
    _task_for,
    _utility,
    _vary_capacity,
    build_fleet_workload,
    fifo_policy,
    static_priority_policy,
)
from .transport_selector import TransportBinding


SIDECAR_POLICIES = (
    "fifo",
    "static_priority",
    "fleetqox_csds",
    "fleetqox_predictive",
    "fleetqox_predictive_guarded",
    "fleetqox_predictive_lagrangian",
    "fleetqox_predictive_profiled",
    "fleetqox_predictive_contextual",
    "fleetqox_predictive_intent",
    "fleetqox_semantic_contract",
    "fleetqox_semantic_contract_lossaware",
    "fleetqox_semantic_contract_adaptive",
    "fleetqox_semantic_contract_budgeted",
    "fleetqox_semantic_contract_budgeted_deadline_first",
    "fleetqox_semantic_contract_budgeted_action_deadline_first",
)
PolicyFn = Callable[[list[tuple[FlowSpec, FlowObservation]], NetworkLink], list[FlowDecision]]
TICKS_PER_SECOND = 50
ADMITTED_OR_CONSUMED_ACTIONS = {
    "send",
    "send_degraded",
    "send_compacted",
    "send_intent",
    "send_supervisory_intent",
    "drop",
}
VALID_PACKET_FORMATS = frozenset({"event_json", "data_frame"})


@dataclass(frozen=True)
class RuntimeConfig:
    udp_host: str = "127.0.0.1"
    udp_port: int = 9100
    policy: str = "fleetqox_predictive"
    policy_label: str | None = None
    lagrangian_overrides: Mapping[str, float] | None = None
    decision_log: Path | None = None
    validate_events: bool = True
    packet_format: str = "event_json"
    control_lease_redundancy: int | None = None
    control_lease_paced_redundancy: bool | None = None
    control_lease_retransmit_max_per_tick: int | None = None
    control_lease_adaptive_redundancy: bool | None = None
    control_lease_adaptive_max_redundancy: int = 3
    control_lease_adaptive_extra_max_per_tick: int | None = None
    control_lease_adaptive_extra_quota_scale: float = 1.0
    control_lease_residual_loss_budget: float = 0.01
    control_lease_drain_grace_s: float = 1.0
    control_lease_high_loss_same_batch_drain: bool = True
    control_lease_high_loss_same_batch_erasure_threshold: float = 0.10
    control_lease_terminal_replay_enabled: bool = True
    control_lease_terminal_replay_attempts: int = 2
    control_lease_terminal_replay_interval_s: float = 0.15
    control_lease_terminal_replay_history_per_robot: int = 4
    control_lease_ack_retransmit_enabled: bool = False
    control_lease_ack_retransmit_max_attempts: int = 2
    control_lease_ack_retransmit_max_per_tick: int | None = None
    control_lease_ack_retransmit_timeout_ms: float | None = None
    control_lease_ack_retransmit_horizon_ms: float | None = None
    control_lease_ack_history_per_robot: int = 4
    control_lease_transition_guard_enabled: bool = True
    control_lease_transition_guard_min_confidence: float = 0.55
    control_lease_transition_guard_min_margin: float = 0.06
    control_lease_transition_guard_max_dwell_ticks: int = 2
    control_lease_transition_guard_redundancy: int = 3
    transport_volatility_guard: bool = True
    transport_volatility_min_confidence: float = 0.65
    transport_volatility_min_margin: float = 0.08
    transport_volatility_min_dwell_ticks: int = 2
    transport_volatility_probe_enabled: bool = True
    transport_volatility_probe_period_ticks: int = 8
    transport_volatility_probe_min_slack_ms: float = 0.0
    transport_volatility_probe_min_confidence: float = 0.50
    transport_volatility_probe_min_margin: float = 0.12
    transport_volatility_probe_min_dwell_ticks: int = 8
    transport_volatility_probe_max_per_tick: int | None = None
    transport_volatility_probe_quota_scale: float = 1.0
    transport_volatility_probe_max_per_robot_per_tick: int = 1
    transport_volatility_recovery_probe_enabled: bool = True
    fleet_optimizer_enabled: bool = True
    transport_volatility_probe_flow_classes: tuple[str, ...] = (
        "state",
        "perception",
        "human_qoe",
    )
    transport_volatility_probe_wire_modes: tuple[str, ...] = (
        "semantic_delta",
        "degraded",
    )


class SidecarRuntime:
    """Apply FleetQoX decisions and emit admitted packets over UDP."""

    def __init__(self, config: RuntimeConfig | None = None) -> None:
        self.config = config or RuntimeConfig()
        self.policy = policy_from_name(
            self.config.policy,
            lagrangian_overrides=self.config.lagrangian_overrides,
        )
        self._control_lease_redundancy = control_lease_redundancy_for_config(self.config)
        self._pace_control_lease_redundancy = paced_control_lease_redundancy_for_config(self.config)
        self._pending_control_lease_retransmits: list[dict[str, object]] = []
        self._recent_control_lease_events: dict[str, list[dict[str, object]]] = {}
        self._control_lease_extra_robot_last_tick: dict[str, int] = {}
        self._control_lease_ack_feedback_seen = False
        self._control_lease_ack_tracker: dict[tuple[str, int], dict[str, object]] = {}
        self._control_lease_ack_source_index: dict[tuple[str, ...], tuple[str, int]] = {}
        self._control_lease_ack_robot_last_retransmit_tick: dict[str, int] = {}
        self._volatility_probe_last_tick: dict[tuple[str, str], int] = {}
        self._volatility_probe_robot_last_tick: dict[str, int] = {}
        self._udp = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self._event_id = 0
        self._log_handle = None
        if self.config.decision_log:
            self.config.decision_log.parent.mkdir(parents=True, exist_ok=True)
            self._log_handle = self.config.decision_log.open("w", encoding="utf-8")

    def close(self) -> None:
        if self._pending_control_lease_retransmits:
            try:
                emitted = self._flush_paced_control_lease_retransmits(
                    self.config.packet_format,
                    drain_all=True,
                )
                emitted += self._flush_control_lease_ack_retransmits(
                    self.config.packet_format,
                    tick=0,
                    drain_all=True,
                )
                emitted += self._replay_recent_control_lease_events()
                if emitted > 0 and self.config.control_lease_drain_grace_s > 0:
                    time.sleep(self.config.control_lease_drain_grace_s)
            except OSError:
                pass
        if self._log_handle:
            self._log_handle.close()
            self._log_handle = None
        self._udp.close()

    def process_message(self, message: Mapping[str, object]) -> dict[str, object]:
        msg_type = str(message.get("type", "batch"))
        if msg_type == "stop":
            emitted = self._flush_paced_control_lease_retransmits(
                self.config.packet_format,
                drain_all=True,
            )
            emitted += self._flush_control_lease_ack_retransmits(
                self.config.packet_format,
                tick=0,
                drain_all=True,
            )
            emitted += self._replay_recent_control_lease_events()
            return {
                "status": "stopping",
                "emitted": emitted,
                "drain_grace_s": (
                    self.config.control_lease_drain_grace_s if emitted > 0 else 0.0
                ),
            }
        if msg_type == "robot_feedback":
            return self.process_robot_feedback(message)
        if msg_type != "batch":
            raise ValueError(f"unknown message type: {msg_type}")
        return self.process_batch(message)

    def process_robot_feedback(self, message: Mapping[str, object]) -> dict[str, object]:
        raw_records = message.get("feedback", message.get("records", []))
        if isinstance(raw_records, Mapping):
            records = [raw_records]
        elif isinstance(raw_records, list):
            records = [item for item in raw_records if isinstance(item, Mapping)]
        else:
            records = []
        ack_result = self._apply_control_lease_ack_feedback(records)
        target = self._feedback_target()
        if target is None:
            if (
                int(ack_result["ack_feedback_records"]) > 0
                or int(ack_result["nack_feedback_records"]) > 0
            ):
                return {
                    "status": "ok",
                    "feedback_type": "control_lease_ack",
                    "applied": ack_result["acked_control_lease_events"],
                    "control_lease_ack": ack_result,
                }
            return {
                "status": "ignored",
                "reason": "active policy does not accept robot feedback",
            }
        result = target.apply_feedback_records(records)
        return {
            "status": "ok",
            "feedback_type": "robot_budget",
            "control_lease_ack": ack_result,
            **result,
        }

    def process_batch(self, message: Mapping[str, object]) -> dict[str, object]:
        scenario = str(message.get("scenario", "sidecar_runtime"))
        timestamp_ms = float(message.get("timestamp_ms", 0.0))
        tick = int(message.get("tick", 0))
        include_feedback = bool(message.get("include_feedback", False))
        link = link_from_payload(message.get("link", {}))
        transport_binding = TransportBinding.from_payload(
            message.get("transport_binding")
        )
        transport_binding_estimate = _mapping_or_none(
            message.get("transport_binding_estimate")
        )
        fleet_optimizer_payload = _mapping_or_none(message.get("fleet_optimizer"))
        packet_format = packet_format_for_binding(
            transport_binding,
            fallback=self.config.packet_format,
        )
        flow_payloads = list(message.get("flows", []))

        candidates: list[tuple[FlowSpec, FlowObservation]] = []
        semantic_payloads: dict[str, Mapping[str, object]] = {}
        contract_ids: dict[str, str] = {}
        source_sample_ids: dict[str, str] = {}
        source_metadata_by_flow: dict[str, Mapping[str, object]] = {}
        sample_envelopes_by_flow: dict[str, Mapping[str, object]] = {}
        for item in flow_payloads:
            if not isinstance(item, Mapping):
                continue
            spec = flow_spec_from_payload(item.get("flow", {}))
            obs = observation_from_payload(item.get("observation", {}), spec)
            candidates.append((spec, obs))
            contract_id = item.get("contract_id")
            if contract_id is not None and contract_id != "":
                contract_ids[spec.flow_id] = str(contract_id)
            source_sample_id = item.get("source_sample_id")
            if source_sample_id is not None and source_sample_id != "":
                source_sample_ids[spec.flow_id] = str(source_sample_id)
            semantic_payload = item.get("semantic_payload")
            if isinstance(semantic_payload, Mapping):
                semantic_payloads[spec.flow_id] = semantic_payload
            source_metadata = item.get("source_metadata")
            if isinstance(source_metadata, Mapping):
                source_metadata_by_flow[spec.flow_id] = dict(source_metadata)
            sample_envelope = item.get("sample_envelope")
            if isinstance(sample_envelope, Mapping):
                sample_envelopes_by_flow[spec.flow_id] = dict(sample_envelope)

        decisions = self.policy(candidates, link)
        by_id = {decision.flow_id: decision for decision in decisions}
        fleet_path_decisions = self._fleet_optimizer_decisions(
            fleet_optimizer_payload,
            candidates,
            link,
        )
        fleet_path_targets = fleet_path_targets_from_optimizer_payload(
            fleet_optimizer_payload
        )
        events: list[dict[str, object]] = []
        for spec, obs in candidates:
            decision = by_id.get(spec.flow_id)
            if decision is None:
                continue
            fleet_path_decision = fleet_path_decisions.get(spec.flow_id)
            if fleet_path_decision is not None:
                decision = apply_fleet_optimizer_decision(decision, fleet_path_decision)
            event = build_sidecar_event(
                event_id=self._next_event_id(),
                scenario=scenario,
                policy=self.config.policy_label or self.config.policy,
                timestamp_ms=timestamp_ms,
                tick=tick,
                flow=spec,
                obs=obs,
                link=link,
                decision=decision,
                contract_id=contract_ids.get(spec.flow_id),
                source_sample_id=source_sample_ids.get(spec.flow_id),
                source_metadata=source_metadata_by_flow.get(spec.flow_id),
                sample_envelope=sample_envelopes_by_flow.get(spec.flow_id),
                semantic_payload=semantic_payloads.get(spec.flow_id),
                transport_binding=(
                    transport_binding.as_payload() if transport_binding else None
                ),
                transport_binding_estimate=transport_binding_estimate,
            )
            if fleet_path_decision is not None:
                event = annotate_fleet_optimizer_event(
                    event,
                    fleet_path_decision,
                    path_targets=fleet_path_targets,
                )
            events.append(event)

        events = self._apply_transport_volatility_guard_to_events(
            events,
            transport_binding_estimate,
        )
        events = self._annotate_control_lease_redundancy_to_events(events)
        emitted = 0
        logged = 0
        feedback: list[dict[str, object]] = []
        emitted += self._flush_paced_control_lease_retransmits(packet_format)
        emitted += self._flush_control_lease_ack_retransmits(packet_format, tick=tick)
        for event in events:
            if self.config.validate_events:
                validate_event(event)
            self._write_event(event)
            logged += 1
            if include_feedback:
                feedback.append(feedback_for_event(event))
            if event["event_type"] == "packet":
                emitted += self._emit_event_with_redundancy(event, packet_format)
        if self._control_lease_same_batch_drain_required(events):
            emitted += self._flush_paced_control_lease_retransmits(
                packet_format,
                drain_all=True,
            )

        response: dict[str, object] = {
            "status": "ok",
            "accepted": len(candidates),
            "decisions": logged,
            "emitted": emitted,
            "tick": tick,
            "timestamp_ms": timestamp_ms,
            "packet_format": packet_format,
        }
        if transport_binding:
            response["transport_binding"] = transport_binding.as_payload()
        if transport_binding_estimate:
            response["transport_binding_estimate"] = transport_binding_estimate
        if fleet_path_decisions:
            response["fleet_optimizer"] = fleet_optimizer_response_payload(
                fleet_path_decisions.values()
            )
        if include_feedback:
            response["feedback"] = feedback
            response["action_counts"] = dict(Counter(str(item["action"]) for item in feedback))
        return response

    def _fleet_optimizer_decisions(
        self,
        payload: Mapping[str, object] | None,
        candidates: Iterable[tuple[FlowSpec, FlowObservation]],
        link: NetworkLink,
    ) -> dict[str, FleetPathDecision]:
        if not self.config.fleet_optimizer_enabled or payload is None:
            return {}
        if not bool(payload.get("enabled", True)):
            return {}
        paths = path_telemetry_from_optimizer_payload(payload, link)
        robot_states = robot_qoe_states_from_optimizer_payload(payload)
        capacity = int(
            _float_from_mapping(
                payload,
                "capacity_bytes_per_tick",
                default=float(link.capacity_bytes_per_tick),
            )
        )
        defaults = FleetOptimizerConfig(capacity_bytes_per_tick=max(0, capacity))
        config = FleetOptimizerConfig(
            capacity_bytes_per_tick=max(0, capacity),
            redundant_deadline_ms=_float_from_mapping(
                payload,
                "redundant_deadline_ms",
                default=defaults.redundant_deadline_ms,
            ),
            redundancy_risk_threshold=_float_from_mapping(
                payload,
                "redundancy_risk_threshold",
                default=defaults.redundancy_risk_threshold,
            ),
            failover_risk_margin=_float_from_mapping(
                payload,
                "failover_risk_margin",
                default=defaults.failover_risk_margin,
            ),
            degrade_floor=_float_from_mapping(
                payload,
                "degrade_floor",
                default=defaults.degrade_floor,
            ),
            min_critical_admission_score=_float_from_mapping(
                payload,
                "min_critical_admission_score",
                default=defaults.min_critical_admission_score,
            ),
            min_best_effort_admission_score=_float_from_mapping(
                payload,
                "min_best_effort_admission_score",
                default=defaults.min_best_effort_admission_score,
            ),
            max_redundant_paths=max(
                1,
                int(
                    _float_from_mapping(
                        payload,
                        "max_redundant_paths",
                        default=float(defaults.max_redundant_paths),
                    )
                ),
            ),
        )
        demands = [
            fleet_flow_demand_from_runtime(flow, obs)
            for flow, obs in candidates
        ]
        decisions = FleetQoEPathOptimizer(config).decide(demands, paths, robot_states)
        return {decision.flow_id: decision for decision in decisions}

    def _emit_event_with_redundancy(
        self,
        event: Mapping[str, object],
        packet_format: str,
    ) -> int:
        count = max(
            transmission_count_for_event(event, self._control_lease_redundancy),
            fleet_path_redundancy_for_event(event),
        )
        path_targets = fleet_path_targets_for_event(event)
        if path_targets:
            if is_control_lease_event(event):
                self._track_control_lease_event(event, packet_format)
                self._remember_recent_control_lease_event(event, packet_format)
            emitted = 0
            for path_id, target in path_targets:
                path_event = dict(event)
                path_event["fleet_transport_path"] = path_id
                emitted += self._send_udp_event(
                    path_event,
                    packet_format,
                    target=target,
                )
            return emitted
        if (
            self._pace_control_lease_redundancy
            and count > 1
            and is_control_lease_event(event)
        ):
            self._track_control_lease_event(event, packet_format)
            self._remember_recent_control_lease_event(event, packet_format)
            emitted = self._send_udp_event(event, packet_format)
            for attempt in range(1, count):
                queued = dict(event)
                queued["paced_retransmit_attempt"] = attempt
                queued["_packet_format"] = packet_format
                self._pending_control_lease_retransmits.append(queued)
            return emitted
        emitted = 0
        if is_control_lease_event(event):
            self._track_control_lease_event(event, packet_format)
            self._remember_recent_control_lease_event(event, packet_format)
        for _ in range(count):
            emitted += self._send_udp_event(event, packet_format)
        return emitted

    def _annotate_control_lease_redundancy(
        self,
        event: Mapping[str, object],
    ) -> dict[str, object]:
        plan = control_lease_redundancy_plan_for_event(
            event,
            self.config,
            base_redundancy=self._control_lease_redundancy,
        )
        return self._annotate_control_lease_redundancy_with_plan(event, plan)

    def _annotate_control_lease_redundancy_to_events(
        self,
        events: Iterable[Mapping[str, object]],
    ) -> list[dict[str, object]]:
        annotated = [dict(event) for event in events]
        plans: dict[int, dict[str, object]] = {}
        eligible: list[tuple[int, dict[str, object]]] = []
        for index, event in enumerate(annotated):
            plan = control_lease_redundancy_plan_for_event(
                event,
                self.config,
                base_redundancy=self._control_lease_redundancy,
            )
            plans[index] = plan
            if (
                bool(plan["adaptive"])
                and int(plan["count"]) > int(plan["base"])
                and not bool(plan.get("quota_exempt", False))
            ):
                eligible.append((index, event))
        selected = {
            index
            for index, plan in plans.items()
            if bool(plan.get("quota_exempt", False))
        }
        selected.update(self._select_adaptive_control_lease_extra_copies(annotated, eligible))
        result: list[dict[str, object]] = []
        for index, event in enumerate(annotated):
            plan = dict(plans[index])
            if index not in selected and bool(plan["adaptive"]):
                plan["count"] = plan["base"]
                plan["adaptive"] = False
                plan["quota_deferred"] = True
            result.append(self._annotate_control_lease_redundancy_with_plan(event, plan))
        return result

    def _annotate_control_lease_redundancy_with_plan(
        self,
        event: Mapping[str, object],
        plan: Mapping[str, object],
    ) -> dict[str, object]:
        annotated = dict(event)
        if not is_control_lease_event(annotated):
            return annotated
        annotated["control_lease_redundancy"] = plan["count"]
        annotated["control_lease_redundancy_base"] = plan["base"]
        annotated["control_lease_redundancy_needed"] = plan["needed"]
        annotated["control_lease_redundancy_strategy"] = plan["strategy"]
        annotated["control_lease_erasure_probability"] = plan["erasure_probability"]
        if bool(plan.get("quota_deferred", False)):
            annotated["control_lease_adaptive_quota_deferred"] = True
        if bool(plan["adaptive"]):
            self._mark_control_lease_extra_copy(annotated)
            reason = str(annotated.get("reason", ""))
            prefix = (
                "control_lease_adaptive_redundancy="
                f"{plan['count']}x; erasure_p={plan['erasure_probability']:.3f}; "
                f"target={plan['residual_loss_budget']:.3f}"
            )
            if bool(plan.get("transition_guard", False)):
                annotated["control_lease_transition_guard"] = True
                prefix += "; transition_guard=active"
            annotated["reason"] = f"{prefix}; {reason}"
        return annotated

    def _select_adaptive_control_lease_extra_copies(
        self,
        batch: Iterable[Mapping[str, object]],
        eligible: list[tuple[int, Mapping[str, object]]],
    ) -> set[int]:
        if not eligible:
            return set()
        quota = self._adaptive_control_lease_extra_tick_quota(batch)
        if quota <= 0:
            return set()
        selected: set[int] = set()
        for index, _event in sorted(
            eligible,
            key=lambda item: self._control_lease_extra_rank(item[1]),
        ):
            selected.add(index)
            if len(selected) >= quota:
                break
        return selected

    def _adaptive_control_lease_extra_tick_quota(
        self,
        batch: Iterable[Mapping[str, object]],
    ) -> int:
        explicit = self.config.control_lease_adaptive_extra_max_per_tick
        if explicit is not None:
            return max(0, int(explicit))
        robots = {
            str(event.get("robot_id", ""))
            for event in batch
            if is_control_lease_event(event) and str(event.get("robot_id", ""))
        }
        robot_count = max(1, len(robots))
        scaled = self.config.control_lease_adaptive_extra_quota_scale * math.sqrt(
            robot_count
        )
        return max(1, int(math.ceil(scaled)))

    def _control_lease_extra_rank(self, event: Mapping[str, object]) -> tuple[object, ...]:
        robot_id = str(event.get("robot_id", ""))
        last_tick = self._control_lease_extra_robot_last_tick.get(robot_id)
        last_rank = -1_000_000_000 if last_tick is None else last_tick
        erasure_probability = _float_from_mapping(
            event,
            "control_lease_erasure_probability",
            default=control_lease_erasure_probability(event),
        )
        return (
            last_rank,
            -erasure_probability,
            robot_id,
            int(event.get("event_id", 0)),
        )

    def _mark_control_lease_extra_copy(self, event: Mapping[str, object]) -> None:
        robot_id = str(event.get("robot_id", ""))
        if not robot_id:
            return
        self._control_lease_extra_robot_last_tick[robot_id] = int(event.get("tick", 0))

    def _remember_recent_control_lease_event(
        self,
        event: Mapping[str, object],
        packet_format: str,
    ) -> None:
        robot_id = str(event.get("robot_id", "") or event.get("dst", ""))
        if not robot_id:
            robot_id = str(event.get("flow_id", ""))
        if not robot_id:
            return
        remembered = dict(event)
        remembered["_packet_format"] = packet_format
        history = self._recent_control_lease_events.setdefault(robot_id, [])
        event_id = _optional_int_value(remembered.get("event_id"))
        if event_id is not None:
            history[:] = [
                item
                for item in history
                if _optional_int_value(item.get("event_id")) != event_id
            ]
        history.append(remembered)
        limit = max(1, int(self.config.control_lease_terminal_replay_history_per_robot))
        if len(history) > limit:
            del history[: len(history) - limit]

    def _replay_recent_control_lease_events(self) -> int:
        if not self.config.control_lease_terminal_replay_enabled:
            return 0
        attempts = max(0, int(self.config.control_lease_terminal_replay_attempts))
        if attempts <= 0 or not self._recent_control_lease_events:
            self._recent_control_lease_events.clear()
            return 0
        interval_s = max(0.0, float(self.config.control_lease_terminal_replay_interval_s))
        events = [
            dict(event)
            for _robot_id, history in sorted(self._recent_control_lease_events.items())
            for event in history
        ]
        emitted = 0
        for attempt in range(1, attempts + 1):
            if attempt > 1 and interval_s > 0.0:
                time.sleep(interval_s)
            for event in events:
                event["terminal_replay_attempt"] = attempt
                packet_format = str(event.get("_packet_format", self.config.packet_format))
                emitted += self._send_udp_event(event, packet_format)
        self._recent_control_lease_events.clear()
        return emitted

    def _track_control_lease_event(
        self,
        event: Mapping[str, object],
        packet_format: str,
    ) -> None:
        if not self.config.control_lease_ack_retransmit_enabled:
            return
        key = _control_lease_ack_key(event)
        if key is None:
            return
        now_ns = time.monotonic_ns()
        state = self._control_lease_ack_tracker.get(key)
        if state is None:
            state = {
                "event": dict(event),
                "packet_format": packet_format,
                "first_send_ns": now_ns,
                "last_send_ns": 0,
                "send_count": 0,
                "ack_retransmit_attempts": 0,
            }
            self._control_lease_ack_tracker[key] = state
        else:
            state["event"] = dict(event)
            state["packet_format"] = packet_format
        self._drop_control_lease_ack_source_index(key)
        for source_key in _control_lease_source_ack_keys(event):
            self._control_lease_ack_source_index[source_key] = key
        self._trim_control_lease_ack_history(str(key[0]))

    def _note_control_lease_packet_sent(self, event: Mapping[str, object]) -> None:
        key = _control_lease_ack_key(event)
        if key is None:
            return
        state = self._control_lease_ack_tracker.get(key)
        if state is None:
            return
        state["last_send_ns"] = int(event.get("send_monotonic_ns", time.monotonic_ns()))
        state["send_count"] = int(state.get("send_count", 0)) + 1

    def _apply_control_lease_ack_feedback(
        self,
        records: Iterable[Mapping[str, object]],
    ) -> dict[str, object]:
        ack_records = 0
        acked = 0
        unknown = 0
        source_acked = 0
        source_unknown = 0
        nack_records = 0
        nack_requested = 0
        nack_unknown = 0
        nack_gap_ranges = 0
        for record in records:
            robot_id = str(record.get("robot_id", ""))
            event_ids = _control_lease_ack_event_ids_from_feedback(record)
            source_keys = _control_lease_source_ack_keys(record)
            nack_source_keys = _control_lease_nack_source_keys_from_feedback(record)
            if not event_ids and not source_keys and not nack_source_keys:
                continue
            if event_ids or source_keys:
                ack_records += 1
            if nack_source_keys:
                nack_records += 1
                nack_gap_ranges += len(
                    _control_lease_nack_missing_ranges_from_feedback(record)
                )
            self._control_lease_ack_feedback_seen = True
            for event_id in event_ids:
                if not robot_id:
                    continue
                key = (robot_id, event_id)
                if key in self._control_lease_ack_tracker:
                    self._forget_control_lease_ack_key(key)
                    acked += 1
                else:
                    unknown += 1
            for source_key in source_keys:
                key = self._control_lease_ack_source_index.get(source_key)
                if key is not None and key in self._control_lease_ack_tracker:
                    self._forget_control_lease_ack_key(key)
                    acked += 1
                    source_acked += 1
                elif not event_ids:
                    source_unknown += 1
            for source_key in nack_source_keys:
                key = self._control_lease_ack_source_index.get(source_key)
                if key is None:
                    nack_unknown += 1
                    continue
                state = self._control_lease_ack_tracker.get(key)
                if state is None:
                    nack_unknown += 1
                    continue
                state["last_send_ns"] = 0
                state["ack_nack_gap_request_count"] = int(
                    state.get("ack_nack_gap_request_count", 0)
                ) + 1
                nack_requested += 1
        return {
            "ack_feedback_records": ack_records,
            "nack_feedback_records": nack_records,
            "acked_control_lease_events": acked,
            "source_acked_control_lease_events": source_acked,
            "nack_requested_control_lease_events": nack_requested,
            "unknown_control_lease_acks": unknown,
            "unknown_control_lease_source_acks": source_unknown,
            "unknown_control_lease_nacks": nack_unknown,
            "nack_missing_sequence_ranges": nack_gap_ranges,
            "tracked_unacked_control_lease_events": len(self._control_lease_ack_tracker),
        }

    def _flush_control_lease_ack_retransmits(
        self,
        packet_format: str,
        *,
        tick: int,
        drain_all: bool = False,
    ) -> int:
        if (
            not self.config.control_lease_ack_retransmit_enabled
            or not self._control_lease_ack_feedback_seen
            or not self._control_lease_ack_tracker
        ):
            return 0
        now_ns = time.monotonic_ns()
        self._prune_control_lease_ack_tracker(now_ns=now_ns)
        candidates = self._control_lease_ack_retransmit_candidates(
            now_ns=now_ns,
            drain_all=drain_all,
        )
        if not candidates:
            return 0
        limit = (
            len(candidates)
            if drain_all
            else self._control_lease_ack_retransmit_tick_quota(candidates)
        )
        emitted = 0
        for key, state in sorted(
            candidates,
            key=lambda item: self._control_lease_ack_retransmit_rank(
                item[0],
                item[1],
            ),
        ):
            if emitted >= limit:
                break
            event = dict(state["event"])
            attempts = int(state.get("ack_retransmit_attempts", 0)) + 1
            event["ack_retransmit_attempt"] = attempts
            event["_packet_format"] = state.get("packet_format", packet_format)
            reason = str(event.get("reason", ""))
            event["reason"] = f"control_lease_ack_retransmit={attempts}; {reason}"
            state["ack_retransmit_attempts"] = attempts
            self._control_lease_ack_robot_last_retransmit_tick[str(key[0])] = tick
            emitted += self._send_udp_event(
                event,
                str(event.get("_packet_format", packet_format)),
            )
        return emitted

    def _control_lease_ack_retransmit_candidates(
        self,
        *,
        now_ns: int,
        drain_all: bool,
    ) -> list[tuple[tuple[str, int], dict[str, object]]]:
        max_attempts = max(0, int(self.config.control_lease_ack_retransmit_max_attempts))
        candidates: list[tuple[tuple[str, int], dict[str, object]]] = []
        for key, state in self._control_lease_ack_tracker.items():
            attempts = int(state.get("ack_retransmit_attempts", 0))
            if attempts >= max_attempts:
                continue
            event = state.get("event", {})
            if not isinstance(event, Mapping):
                continue
            if drain_all:
                candidates.append((key, state))
                continue
            last_send_ns = int(state.get("last_send_ns", state.get("first_send_ns", 0)))
            age_since_last_send_ms = max(0.0, (now_ns - last_send_ns) / 1_000_000.0)
            if age_since_last_send_ms < self._control_lease_ack_timeout_ms(event):
                continue
            first_send_ns = int(state.get("first_send_ns", last_send_ns))
            age_since_first_send_ms = max(0.0, (now_ns - first_send_ns) / 1_000_000.0)
            if age_since_first_send_ms > self._control_lease_ack_horizon_ms(event):
                continue
            candidates.append((key, state))
        return candidates

    def _control_lease_ack_retransmit_tick_quota(
        self,
        candidates: Iterable[tuple[tuple[str, int], Mapping[str, object]]],
    ) -> int:
        explicit = self.config.control_lease_ack_retransmit_max_per_tick
        if explicit is not None:
            return max(0, int(explicit))
        robots = {str(key[0]) for key, _state in candidates}
        robot_count = max(1, len(robots))
        return max(1, int(math.ceil(math.sqrt(robot_count))))

    def _control_lease_ack_retransmit_rank(
        self,
        key: tuple[str, int],
        state: Mapping[str, object],
    ) -> tuple[object, ...]:
        robot_id = str(key[0])
        last_tick = self._control_lease_ack_robot_last_retransmit_tick.get(robot_id)
        last_rank = -1_000_000_000 if last_tick is None else last_tick
        event = state.get("event", {})
        erasure_probability = (
            _float_from_mapping(
                event,
                "control_lease_erasure_probability",
                default=control_lease_erasure_probability(event),
            )
            if isinstance(event, Mapping)
            else 0.0
        )
        first_send_ns = int(state.get("first_send_ns", 0))
        attempts = int(state.get("ack_retransmit_attempts", 0))
        return (last_rank, attempts, -erasure_probability, first_send_ns, robot_id)

    def _control_lease_ack_timeout_ms(self, event: Mapping[str, object]) -> float:
        explicit = self.config.control_lease_ack_retransmit_timeout_ms
        if explicit is not None:
            return max(0.0, float(explicit))
        deadline_ms = _float_from_mapping(event, "deadline_ms", default=90.0)
        rtt_ms = _float_from_mapping(event, "link_rtt_ms", default=40.0)
        jitter_ms = _float_from_mapping(event, "link_jitter_ms", default=5.0)
        return max(10.0, min(0.45 * deadline_ms, 0.5 * rtt_ms + 2.0 * jitter_ms))

    def _control_lease_ack_horizon_ms(self, event: Mapping[str, object]) -> float:
        explicit = self.config.control_lease_ack_retransmit_horizon_ms
        if explicit is not None:
            return max(0.0, float(explicit))
        deadline_ms = _float_from_mapping(event, "deadline_ms", default=90.0)
        rtt_ms = _float_from_mapping(event, "link_rtt_ms", default=40.0)
        jitter_ms = _float_from_mapping(event, "link_jitter_ms", default=5.0)
        liveliness_lease_ms = _float_from_mapping(
            event,
            "liveliness_lease_ms",
            default=500.0,
        )
        return max(
            500.0,
            4.0 * deadline_ms,
            4.0 * liveliness_lease_ms,
            rtt_ms + 4.0 * jitter_ms,
        )

    def _prune_control_lease_ack_tracker(self, *, now_ns: int) -> None:
        expired: list[tuple[str, int]] = []
        for key, state in self._control_lease_ack_tracker.items():
            event = state.get("event", {})
            if not isinstance(event, Mapping):
                expired.append(key)
                continue
            first_send_ns = int(state.get("first_send_ns", 0))
            age_ms = max(0.0, (now_ns - first_send_ns) / 1_000_000.0)
            if age_ms > 2.0 * self._control_lease_ack_horizon_ms(event):
                expired.append(key)
        for key in expired:
            self._forget_control_lease_ack_key(key)

    def _trim_control_lease_ack_history(self, robot_id: str) -> None:
        limit = self._control_lease_ack_history_limit(robot_id)
        items = [
            (key, state)
            for key, state in self._control_lease_ack_tracker.items()
            if str(key[0]) == robot_id
        ]
        if len(items) <= limit:
            return
        items.sort(key=lambda item: int(item[1].get("first_send_ns", 0)))
        for key, _state in items[: len(items) - limit]:
            self._forget_control_lease_ack_key(key)

    def _control_lease_ack_history_limit(self, robot_id: str) -> int:
        floor = max(1, int(self.config.control_lease_ack_history_per_robot))
        if not self.config.control_lease_ack_retransmit_enabled:
            return floor
        dynamic = floor
        for key, state in self._control_lease_ack_tracker.items():
            if str(key[0]) != robot_id:
                continue
            event = state.get("event", {})
            if not isinstance(event, Mapping):
                continue
            source_deadline_ms = max(
                1.0,
                _float_from_mapping(
                    event,
                    "source_deadline_ms",
                    default=_float_from_mapping(event, "deadline_ms", default=90.0),
                ),
            )
            horizon_ms = self._control_lease_ack_horizon_ms(event)
            dynamic = max(dynamic, int(math.ceil(horizon_ms / source_deadline_ms)) + 2)
        return min(dynamic, max(floor, 128))

    def _forget_control_lease_ack_key(self, key: tuple[str, int]) -> None:
        self._control_lease_ack_tracker.pop(key, None)
        self._drop_control_lease_ack_source_index(key)

    def _drop_control_lease_ack_source_index(self, key: tuple[str, int]) -> None:
        for source_key, event_key in list(self._control_lease_ack_source_index.items()):
            if event_key == key:
                self._control_lease_ack_source_index.pop(source_key, None)

    def _control_lease_same_batch_drain_required(
        self,
        events: Iterable[Mapping[str, object]],
    ) -> bool:
        if not self.config.control_lease_high_loss_same_batch_drain:
            return False
        threshold = self.config.control_lease_high_loss_same_batch_erasure_threshold
        for event in events:
            if not is_control_lease_event(event):
                continue
            erasure_probability = _float_from_mapping(
                event,
                "control_lease_erasure_probability",
                default=control_lease_erasure_probability(event),
            )
            if erasure_probability >= threshold:
                return True
        return False

    def _flush_paced_control_lease_retransmits(
        self,
        packet_format: str,
        *,
        drain_all: bool = False,
    ) -> int:
        if not self._pending_control_lease_retransmits:
            return 0
        max_per_tick = self.config.control_lease_retransmit_max_per_tick
        limit = (
            len(self._pending_control_lease_retransmits)
            if drain_all or max_per_tick is None
            else max(0, int(max_per_tick))
        )
        if not drain_all and max_per_tick is None:
            robots = {
                str(event.get("robot_id", "") or event.get("dst", ""))
                for event in self._pending_control_lease_retransmits
            }
            limit = max(1, len({robot for robot in robots if robot}))
        emitted = 0
        remaining: list[dict[str, object]] = []
        pending = sorted(
            self._pending_control_lease_retransmits,
            key=lambda event: (
                int(event.get("paced_retransmit_attempt", 0)),
                str(event.get("robot_id", "") or event.get("dst", "")),
                int(event.get("event_id", 0)),
            ),
        )
        for event in pending:
            if emitted < limit:
                event_packet_format = str(event.get("_packet_format", packet_format))
                emitted += self._send_udp_event(event, event_packet_format)
            else:
                remaining.append(event)
        self._pending_control_lease_retransmits = remaining
        return emitted

    def _send_udp_event(
        self,
        event: Mapping[str, object],
        packet_format: str,
        *,
        target: tuple[str, int] | None = None,
    ) -> int:
        payload_event = dict(event)
        payload_event.pop("_packet_format", None)
        payload_event["send_monotonic_ns"] = time.monotonic_ns()
        udp_target = target or (self.config.udp_host, self.config.udp_port)
        if target is not None:
            payload_event["fleet_udp_target"] = {
                "udp_host": udp_target[0],
                "udp_port": udp_target[1],
            }
        payload = payload_for_event(payload_event, packet_format=packet_format)
        self._udp.sendto(payload, udp_target)
        self._note_control_lease_packet_sent(payload_event)
        return 1

    def _next_event_id(self) -> int:
        event_id = self._event_id
        self._event_id += 1
        return event_id

    def _write_event(self, event: dict[str, object]) -> None:
        if not self._log_handle:
            return
        self._log_handle.write(json.dumps(event, sort_keys=True) + "\n")
        self._log_handle.flush()

    def _feedback_target(self):
        owner = getattr(self.policy, "__self__", None)
        if owner is not None and hasattr(owner, "apply_feedback_records"):
            return owner
        return None

    def _apply_transport_volatility_guard(
        self,
        event: Mapping[str, object],
        estimate: Mapping[str, object] | None,
    ) -> dict[str, object]:
        if not transport_volatility_guard_applies(
            event,
            estimate,
            enabled=self.config.transport_volatility_guard,
            min_confidence=self.config.transport_volatility_min_confidence,
            min_margin=self.config.transport_volatility_min_margin,
            min_dwell_ticks=self.config.transport_volatility_min_dwell_ticks,
        ):
            return dict(event)
        candidate = self._transport_volatility_probe_candidate(event, estimate)
        if candidate is not None:
            return self._allow_transport_volatility_probe(candidate, estimate)
        return apply_transport_volatility_guard(
            event,
            estimate,
            enabled=self.config.transport_volatility_guard,
            min_confidence=self.config.transport_volatility_min_confidence,
            min_margin=self.config.transport_volatility_min_margin,
            min_dwell_ticks=self.config.transport_volatility_min_dwell_ticks,
        )

    def _apply_transport_volatility_guard_to_events(
        self,
        events: Iterable[Mapping[str, object]],
        estimate: Mapping[str, object] | None,
    ) -> list[dict[str, object]]:
        batch = [dict(event) for event in events]
        guarded: list[dict[str, object] | None] = [None] * len(batch)
        eligible: list[tuple[int, dict[str, object], dict[str, object]]] = []
        for index, event in enumerate(batch):
            if not transport_volatility_guard_applies(
                event,
                estimate,
                enabled=self.config.transport_volatility_guard,
                min_confidence=self.config.transport_volatility_min_confidence,
                min_margin=self.config.transport_volatility_min_margin,
                min_dwell_ticks=self.config.transport_volatility_min_dwell_ticks,
            ):
                guarded[index] = event
                continue
            candidate = self._transport_volatility_probe_candidate(event, estimate)
            if candidate is not None:
                eligible.append((index, event, candidate))
                continue
            guarded[index] = apply_transport_volatility_guard(
                event,
                estimate,
                enabled=self.config.transport_volatility_guard,
                min_confidence=self.config.transport_volatility_min_confidence,
                min_margin=self.config.transport_volatility_min_margin,
                min_dwell_ticks=self.config.transport_volatility_min_dwell_ticks,
            )

        selected = self._select_transport_volatility_probes(
            batch,
            [(index, candidate) for index, _, candidate in eligible],
        )
        for index, event, candidate in eligible:
            if index in selected:
                guarded[index] = self._allow_transport_volatility_probe(
                    candidate,
                    estimate,
                )
            else:
                guarded[index] = apply_transport_volatility_guard(
                    event,
                    estimate,
                    enabled=self.config.transport_volatility_guard,
                    min_confidence=self.config.transport_volatility_min_confidence,
                    min_margin=self.config.transport_volatility_min_margin,
                    min_dwell_ticks=self.config.transport_volatility_min_dwell_ticks,
                )
        return [event for event in guarded if event is not None]

    def _transport_volatility_probe_candidate(
        self,
        event: Mapping[str, object],
        estimate: Mapping[str, object] | None,
    ) -> dict[str, object] | None:
        if self._transport_volatility_probe_allowed(event, estimate):
            return dict(event)
        return self._transport_volatility_recovery_probe_candidate(event, estimate)

    def _transport_volatility_probe_allowed(
        self,
        event: Mapping[str, object],
        estimate: Mapping[str, object] | None,
    ) -> bool:
        if not self.config.transport_volatility_probe_enabled:
            return False
        if not isinstance(estimate, Mapping):
            return False
        confidence = _float_from_mapping(estimate, "confidence", default=0.0)
        margin = _float_from_mapping(estimate, "margin", default=0.0)
        dwell_ticks = int(_float_from_mapping(estimate, "dwell_ticks", default=0.0))
        if confidence < self.config.transport_volatility_probe_min_confidence:
            return False
        if margin < self.config.transport_volatility_probe_min_margin:
            return False
        if dwell_ticks < self.config.transport_volatility_probe_min_dwell_ticks:
            return False
        if bool(estimate.get("changed", False)) and dwell_ticks <= 0:
            return False
        flow_class = str(event.get("flow_class", ""))
        if flow_class not in self.config.transport_volatility_probe_flow_classes:
            return False
        wire_mode = str(event.get("wire_mode", ""))
        if wire_mode not in self.config.transport_volatility_probe_wire_modes:
            return False
        if str(event.get("action", "")) not in {"send_degraded", "send_compacted"}:
            return False
        predicted_slack_ms = _float_from_mapping(
            event,
            "predicted_slack_ms",
            default=0.0,
        )
        if predicted_slack_ms < self.config.transport_volatility_probe_min_slack_ms:
            return False
        tick = int(event.get("tick", 0))
        period = max(1, int(self.config.transport_volatility_probe_period_ticks))
        last_tick = self._volatility_probe_last_tick.get(
            self._volatility_probe_key(event)
        )
        return last_tick is None or tick - last_tick >= period

    def _transport_volatility_recovery_probe_candidate(
        self,
        event: Mapping[str, object],
        estimate: Mapping[str, object] | None,
    ) -> dict[str, object] | None:
        if not self.config.transport_volatility_probe_enabled:
            return None
        if not self.config.transport_volatility_recovery_probe_enabled:
            return None
        if not isinstance(estimate, Mapping):
            return None
        flow_class = str(event.get("flow_class", ""))
        if flow_class not in self.config.transport_volatility_probe_flow_classes:
            return None
        if str(event.get("action", "")) not in {"send", "send_degraded", "send_compacted"}:
            return None
        semantic_payload = event.get("semantic_payload")
        if not isinstance(semantic_payload, Mapping):
            return None
        predicted_slack_ms = _float_from_mapping(
            event,
            "predicted_slack_ms",
            default=0.0,
        )
        if predicted_slack_ms < self.config.transport_volatility_probe_min_slack_ms:
            return None
        tick = int(event.get("tick", 0))
        period = max(1, int(self.config.transport_volatility_probe_period_ticks))
        last_tick = self._volatility_probe_last_tick.get(
            self._volatility_probe_key(event)
        )
        if last_tick is not None and tick - last_tick < period:
            return None

        msg_type = str(semantic_payload.get("msg_type") or event.get("source_msg_type", ""))
        action = str(event.get("action", ""))
        wire_mode = str(event.get("wire_mode", ""))
        if action in {"send_degraded", "send_compacted"} and wire_mode in self.config.transport_volatility_probe_wire_modes:
            return dict(event)
        if flow_class == "state" or msg_type == "nav_msgs/msg/Odometry":
            return self._downgrade_transport_volatility_probe(
                event,
                action="send_compacted",
                wire_mode="semantic_delta",
            )
        if flow_class == "perception" or msg_type == "sensor_msgs/msg/LaserScan":
            return self._downgrade_transport_volatility_probe(
                event,
                action="send_degraded",
                wire_mode="degraded",
            )
        return None

    def _downgrade_transport_volatility_probe(
        self,
        event: Mapping[str, object],
        *,
        action: str,
        wire_mode: str,
    ) -> dict[str, object]:
        candidate = dict(event)
        previous = str(event.get("wire_mode", "") or event.get("action", ""))
        reason = str(candidate.get("reason", ""))
        candidate.update(
            {
                "action": action,
                "wire_mode": wire_mode,
                "degraded": wire_mode != "native",
                "reason": (
                    "transport_volatility_recovery_probe="
                    f"{wire_mode}_from_{previous or 'unknown'}; "
                    f"{reason}"
                ),
            }
        )
        return candidate

    def _select_transport_volatility_probes(
        self,
        batch: Iterable[Mapping[str, object]],
        eligible: list[tuple[int, dict[str, object]]],
    ) -> set[int]:
        quota = self._transport_volatility_probe_tick_quota(batch)
        if quota <= 0 or not eligible:
            return set()
        max_per_robot = max(
            1,
            int(self.config.transport_volatility_probe_max_per_robot_per_tick),
        )
        selected: set[int] = set()
        robot_counts: Counter[str] = Counter()
        for index, event in sorted(
            eligible,
            key=lambda item: self._volatility_probe_rank(item[1]),
        ):
            robot_id = str(event.get("robot_id", ""))
            if robot_counts[robot_id] >= max_per_robot:
                continue
            selected.add(index)
            robot_counts[robot_id] += 1
            if len(selected) >= quota:
                break
        return selected

    def _transport_volatility_probe_tick_quota(
        self,
        batch: Iterable[Mapping[str, object]],
    ) -> int:
        explicit = self.config.transport_volatility_probe_max_per_tick
        if explicit is not None:
            return max(0, int(explicit))
        robots = {
            str(event.get("robot_id", ""))
            for event in batch
            if str(event.get("robot_id", ""))
        }
        robot_count = max(1, len(robots))
        scaled = (
            self.config.transport_volatility_probe_quota_scale
            * math.sqrt(robot_count)
        )
        return max(1, int(math.ceil(scaled)))

    def _volatility_probe_rank(self, event: Mapping[str, object]) -> tuple[object, ...]:
        key = self._volatility_probe_key(event)
        robot_id = str(event.get("robot_id", ""))
        robot_last_tick = self._volatility_probe_robot_last_tick.get(robot_id)
        last_tick = self._volatility_probe_last_tick.get(key)
        robot_rank = -1_000_000_000 if robot_last_tick is None else robot_last_tick
        last_rank = -1_000_000_000 if last_tick is None else last_tick
        semantic_utility = _float_from_mapping(event, "semantic_utility", default=0.0)
        predicted_slack_ms = _float_from_mapping(
            event,
            "predicted_slack_ms",
            default=0.0,
        )
        return (
            robot_rank,
            last_rank,
            -semantic_utility,
            -predicted_slack_ms,
            robot_id,
            str(event.get("flow_class", "")),
            str(event.get("flow_id", "")),
        )

    def _allow_transport_volatility_probe(
        self,
        event: Mapping[str, object],
        estimate: Mapping[str, object] | None,
    ) -> dict[str, object]:
        allowed = dict(event)
        reason = str(allowed.get("reason", ""))
        allowed["reason"] = (
            "transport_volatility_guard=allow_probe; "
            f"{transport_volatility_reason(estimate)}; "
            f"period_ticks={self.config.transport_volatility_probe_period_ticks}; "
            f"{reason}"
        )
        self._mark_transport_volatility_probe(allowed)
        return allowed

    def _mark_transport_volatility_probe(self, event: Mapping[str, object]) -> None:
        tick = int(event.get("tick", 0))
        self._volatility_probe_last_tick[self._volatility_probe_key(event)] = tick
        robot_id = str(event.get("robot_id", ""))
        if robot_id:
            self._volatility_probe_robot_last_tick[robot_id] = tick

    def _volatility_probe_key(self, event: Mapping[str, object]) -> tuple[str, str]:
        return (
            str(event.get("robot_id", "")),
            str(event.get("flow_class", "")),
        )


def serve_tcp(
    *,
    host: str,
    port: int,
    runtime: SidecarRuntime,
    idle_timeout_s: float = 30.0,
    max_runtime_s: float = 300.0,
) -> None:
    """Serve newline-delimited JSON batches over TCP."""

    started = time.monotonic()
    last_activity = started
    stop_event = threading.Event()
    runtime_lock = threading.Lock()
    connection_threads: list[threading.Thread] = []

    def handle_connection(conn: socket.socket) -> None:
        nonlocal last_activity
        with conn:
            conn_file = conn.makefile("rwb")
            for raw in conn_file:
                last_activity = time.monotonic()
                message = json.loads(raw.decode("utf-8"))
                with runtime_lock:
                    response = runtime.process_message(message)
                conn_file.write((json.dumps(response, sort_keys=True) + "\n").encode("utf-8"))
                conn_file.flush()
                if response.get("status") == "stopping":
                    drain_grace_s = _float_from_mapping(
                        response,
                        "drain_grace_s",
                        default=0.0,
                    )
                    if drain_grace_s > 0.0:
                        time.sleep(drain_grace_s)
                    stop_event.set()
                    return

    with socket.create_server((host, port), reuse_port=False) as server:
        server.settimeout(0.25)
        while not stop_event.is_set():
            now = time.monotonic()
            if now - started > max_runtime_s:
                break
            if now - last_activity > idle_timeout_s:
                break
            try:
                conn, _ = server.accept()
            except socket.timeout:
                continue
            thread = threading.Thread(target=handle_connection, args=(conn,), daemon=True)
            thread.start()
            connection_threads.append(thread)
    for thread in connection_threads:
        thread.join(timeout=1.0)


def send_batches(
    *,
    host: str,
    port: int,
    batches: Iterable[dict[str, object]],
    stop_after: bool = True,
) -> list[dict[str, object]]:
    responses: list[dict[str, object]] = []
    with socket.create_connection((host, port), timeout=10.0) as conn:
        conn_file = conn.makefile("rwb")
        for batch in batches:
            conn_file.write((json.dumps(batch, sort_keys=True) + "\n").encode("utf-8"))
            conn_file.flush()
            responses.append(json.loads(conn_file.readline().decode("utf-8")))
        if stop_after:
            conn_file.write(b'{"type":"stop"}\n')
            conn_file.flush()
            responses.append(json.loads(conn_file.readline().decode("utf-8")))
    return responses


class RobotFeedbackTcpClient:
    """Reusable newline-delimited TCP client for robot feedback records."""

    def __init__(self, *, host: str, port: int, timeout_s: float = 1.0) -> None:
        self.host = host
        self.port = int(port)
        self.timeout_s = float(timeout_s)
        self._conn: socket.socket | None = None
        self._conn_file = None

    def __enter__(self) -> "RobotFeedbackTcpClient":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.close()

    def send_feedback(
        self,
        records: Iterable[Mapping[str, object]],
    ) -> dict[str, object]:
        return self.send_message(
            {
                "type": "robot_feedback",
                "feedback": [dict(record) for record in records],
            }
        )

    def send_message(self, message: Mapping[str, object]) -> dict[str, object]:
        try:
            conn_file = self._connection_file()
            conn_file.write((json.dumps(message, sort_keys=True) + "\n").encode("utf-8"))
            conn_file.flush()
            raw = conn_file.readline()
            if not raw:
                raise ConnectionError("sidecar feedback connection closed")
            return json.loads(raw.decode("utf-8"))
        except (OSError, TimeoutError, json.JSONDecodeError, ConnectionError):
            self.close()
            raise

    def close(self) -> None:
        if self._conn_file is not None:
            try:
                self._conn_file.close()
            except OSError:
                pass
            self._conn_file = None
        if self._conn is not None:
            try:
                self._conn.close()
            except OSError:
                pass
            self._conn = None

    def _connection_file(self):
        if self._conn_file is None:
            self._conn = socket.create_connection(
                (self.host, self.port),
                timeout=self.timeout_s,
            )
            self._conn_file = self._conn.makefile("rwb")
        return self._conn_file


def send_robot_feedback(
    *,
    host: str,
    port: int,
    records: Iterable[Mapping[str, object]],
    timeout_s: float = 1.0,
) -> dict[str, object]:
    with RobotFeedbackTcpClient(host=host, port=port, timeout_s=timeout_s) as client:
        return client.send_feedback(records)



def policy_from_name(
    name: str,
    *,
    lagrangian_overrides: Mapping[str, float] | None = None,
) -> PolicyFn:
    if name == "fifo":
        return fifo_policy
    if name == "static_priority":
        return static_priority_policy
    if name == "fleetqox_csds":
        return CausalSemanticDeadlineScheduler().schedule
    if name == "fleetqox_predictive":
        return PredictiveAdmissionController().schedule
    if name == "fleetqox_predictive_guarded":
        return RiskConstrainedPredictiveAdmissionController().schedule
    if name == "fleetqox_predictive_lagrangian":
        return LagrangianRiskPredictiveAdmissionController(
            config=lagrangian_config_from_overrides(lagrangian_overrides),
        ).schedule
    if name == "fleetqox_predictive_profiled":
        return ProfileAwareLagrangianAdmissionController().schedule
    if name == "fleetqox_predictive_contextual":
        return ContextualProfiledLagrangianAdmissionController().schedule
    if name == "fleetqox_predictive_intent":
        return IntentAwareContextualAdmissionController().schedule
    if name == "fleetqox_semantic_contract":
        return SemanticContractAdmissionController().schedule
    if name == "fleetqox_semantic_contract_lossaware":
        return SemanticContractAdmissionController(enable_loss_shadow=True).schedule
    if name == "fleetqox_semantic_contract_adaptive":
        return AdaptiveSemanticContractAdmissionController().schedule
    if name == "fleetqox_semantic_contract_budgeted":
        return RobotBudgetAwareAdmissionController(
            AdaptiveSemanticContractAdmissionController().schedule
        ).schedule
    if name == "fleetqox_semantic_contract_budgeted_deadline_first":
        return RobotBudgetAwareAdmissionController(
            AdaptiveSemanticContractAdmissionController().schedule,
            config=RobotBudgetConfig(
                deadline_shaping_gain=0.35,
                n_aware_control_floor_enabled=True,
            ),
        ).schedule
    if name == "fleetqox_semantic_contract_budgeted_action_deadline_first":
        return RobotBudgetAwareAdmissionController(
            AdaptiveSemanticContractAdmissionController().schedule,
            config=RobotBudgetConfig(
                deadline_shaping_gain=0.35,
                deadline_horizon_lift_enabled=True,
                n_aware_control_floor_enabled=True,
                action_deadline_learning_rate=1.0,
                action_deadline_horizon_lift_min_deficit=0.02,
            ),
        ).schedule
    raise ValueError(f"unknown sidecar policy: {name}")


def lagrangian_config_from_overrides(
    overrides: Mapping[str, float] | None,
) -> LagrangianAdmissionConfig:
    if not overrides:
        return LagrangianAdmissionConfig()
    allowed = set(LagrangianAdmissionConfig.__dataclass_fields__)
    unknown = sorted(set(overrides) - allowed)
    if unknown:
        raise ValueError(f"unknown Lagrangian config fields: {', '.join(unknown)}")
    return LagrangianAdmissionConfig(**dict(overrides))


def packet_format_for_binding(
    binding: TransportBinding | None,
    *,
    fallback: str,
) -> str:
    packet_format = fallback if binding is None else binding.packet_format
    if packet_format not in VALID_PACKET_FORMATS:
        choices = ", ".join(sorted(VALID_PACKET_FORMATS))
        raise ValueError(f"unknown packet_format: {packet_format}; choices: {choices}")
    return packet_format


def path_telemetry_from_optimizer_payload(
    payload: Mapping[str, object],
    link: NetworkLink,
) -> list[PathTelemetry]:
    raw_paths = payload.get("paths", [])
    paths = []
    for index, raw_path in enumerate(_sequence_value(raw_paths)):
        if not isinstance(raw_path, Mapping):
            continue
        path_id = str(
            raw_path.get("path_id")
            or raw_path.get("id")
            or raw_path.get("name")
            or f"path_{index}"
        )
        rtt_ms = _float_from_mapping(raw_path, "rtt_ms", default=link.rtt_ms)
        latency_ms = _float_from_mapping(
            raw_path,
            "latency_ms",
            default=_float_from_mapping(
                raw_path,
                "one_way_latency_ms",
                default=max(0.0, rtt_ms / 2.0),
            ),
        )
        loss = _loss_fraction_value(
            raw_path.get("loss", raw_path.get("loss_percent", link.loss))
        )
        paths.append(
            PathTelemetry(
                path_id=path_id,
                latency_ms=max(0.0, latency_ms),
                jitter_ms=max(
                    0.0,
                    _float_from_mapping(raw_path, "jitter_ms", default=link.jitter_ms),
                ),
                loss=loss,
                nack_rate=_loss_fraction_value(raw_path.get("nack_rate", 0.0)),
                deadline_miss_ratio=_loss_fraction_value(
                    raw_path.get("deadline_miss_ratio", 0.0)
                ),
                bandwidth_utilization=_loss_fraction_value(
                    raw_path.get("bandwidth_utilization", 0.0)
                ),
            )
        )
    if paths:
        return paths
    return [
        PathTelemetry(
            path_id="default_link",
            latency_ms=max(0.0, link.rtt_ms / 2.0),
            jitter_ms=max(0.0, link.jitter_ms),
            loss=link.loss,
            bandwidth_utilization=0.0,
        )
    ]


def robot_qoe_states_from_optimizer_payload(
    payload: Mapping[str, object],
) -> list[RobotQoEState]:
    raw_states = payload.get("robot_states", payload.get("robots", []))
    states = []
    for raw_state in _sequence_value(raw_states):
        if not isinstance(raw_state, Mapping):
            continue
        robot_id = str(raw_state.get("robot_id", raw_state.get("id", "")))
        if not robot_id:
            continue
        states.append(
            RobotQoEState(
                robot_id=robot_id,
                control_delivery_ratio=_loss_fraction_value(
                    raw_state.get("control_delivery_ratio", 1.0)
                ),
                deadline_miss_ratio=_loss_fraction_value(
                    raw_state.get("deadline_miss_ratio", 0.0)
                ),
                qoe_score=_loss_fraction_value(raw_state.get("qoe_score", 1.0)),
            )
        )
    return states


def fleet_path_targets_from_optimizer_payload(
    payload: Mapping[str, object] | None,
) -> dict[str, tuple[str, int]]:
    if payload is None:
        return {}
    raw_targets = payload.get("path_targets", payload.get("targets", {}))
    targets: dict[str, tuple[str, int]] = {}
    if isinstance(raw_targets, Mapping):
        iterable = raw_targets.items()
    else:
        iterable = (
            (item.get("path_id", item.get("id", "")), item)
            for item in _sequence_value(raw_targets)
            if isinstance(item, Mapping)
        )
    for raw_path_id, raw_target in iterable:
        path_id = str(raw_path_id)
        target = udp_target_from_payload(raw_target)
        if path_id and target is not None:
            targets[path_id] = target
    return targets


def udp_target_from_payload(payload: object) -> tuple[str, int] | None:
    if isinstance(payload, str):
        host, sep, port = payload.rpartition(":")
        if not sep:
            return None
        try:
            return host or "127.0.0.1", int(port)
        except ValueError:
            return None
    if isinstance(payload, Mapping):
        host = str(payload.get("udp_host", payload.get("host", "127.0.0.1")))
        port = _optional_int_value(payload.get("udp_port", payload.get("port")))
        if port is None:
            return None
        return host, port
    return None


def fleet_flow_demand_from_runtime(
    flow: FlowSpec,
    obs: FlowObservation,
) -> FleetFlowDemand:
    return FleetFlowDemand(
        flow_id=flow.flow_id,
        robot_id=flow.robot_id,
        flow_class=flow.flow_class,
        deadline_ms=flow.qos.deadline_ms,
        payload_bytes=_original_size(flow, obs),
        rate_hz=flow.nominal_rate_hz,
        criticality=max(
            flow.causal_task_gain,
            obs.task.task_criticality,
            obs.task.collision_risk,
            obs.task.coordination_pressure,
        ),
        qoe_weight=runtime_qoe_weight(flow),
        age_ms=obs.age_ms,
        lifespan_ms=flow.qos.lifespan_ms,
    )


def runtime_qoe_weight(flow: FlowSpec) -> float:
    operator_visible = 0.35 if flow.qoe.operator_visible else 0.0
    return _clamp_float(
        operator_visible
        + flow.qoe.smoothness_weight
        + flow.qoe.freeze_penalty
        + flow.qoe.visual_confidence_weight,
        lower=0.0,
        upper=1.0,
    )


def apply_fleet_optimizer_decision(
    decision: FlowDecision,
    fleet_decision: FleetPathDecision,
) -> FlowDecision:
    reason = (
        f"fleet_optimizer={fleet_decision.mode.value}; "
        f"paths={','.join(fleet_decision.selected_paths) or 'none'}; "
        f"{fleet_decision.reason}; {decision.reason}"
    )
    if not is_admitted_action(decision.action):
        return FlowDecision(
            flow_id=decision.flow_id,
            action=decision.action,
            priority=decision.priority,
            allocated_bytes=decision.allocated_bytes,
            reason=reason,
            degraded=decision.degraded,
            reliability=decision.reliability,
            wire_mode=decision.wire_mode,
            predicted_slack_ms=decision.predicted_slack_ms,
        )
    if fleet_decision.action in {"drop", "defer"} or fleet_decision.mode is TransportMode.DROP:
        return FlowDecision(
            flow_id=decision.flow_id,
            action="defer" if fleet_decision.action != "drop" else "drop",
            priority=decision.priority,
            allocated_bytes=0,
            reason=reason,
            degraded=False,
            reliability=decision.reliability,
            wire_mode="",
            predicted_slack_ms=0.0,
        )
    if fleet_decision.mode is TransportMode.DEGRADED or fleet_decision.action == "send_degraded":
        return FlowDecision(
            flow_id=decision.flow_id,
            action="send_degraded",
            priority=decision.priority,
            allocated_bytes=max(1, fleet_decision.allocated_bytes),
            reason=reason,
            degraded=True,
            reliability=decision.reliability,
            wire_mode="degraded",
            predicted_slack_ms=decision.predicted_slack_ms,
        )
    return FlowDecision(
        flow_id=decision.flow_id,
        action=decision.action,
        priority=decision.priority,
        allocated_bytes=decision.allocated_bytes,
        reason=reason,
        degraded=decision.degraded,
        reliability=decision.reliability,
        wire_mode=decision.wire_mode,
        predicted_slack_ms=decision.predicted_slack_ms,
    )


def annotate_fleet_optimizer_event(
    event: Mapping[str, object],
    fleet_decision: FleetPathDecision,
    *,
    path_targets: Mapping[str, tuple[str, int]] | None = None,
) -> dict[str, object]:
    annotated = dict(event)
    paths = list(fleet_decision.selected_paths)
    annotated["fleet_optimizer"] = {
        "schema_version": "fleetrmw.fleet_optimizer_decision.v1",
        "action": fleet_decision.action,
        "mode": fleet_decision.mode.value,
        "selected_paths": paths,
        "allocated_bytes": fleet_decision.allocated_bytes,
        "utility_score": fleet_decision.utility_score,
        "best_path_score": fleet_decision.best_path_score,
        "fleet_fairness_debt": fleet_decision.fleet_fairness_debt,
        "reason": fleet_decision.reason,
    }
    annotated["fleet_transport_mode"] = fleet_decision.mode.value
    annotated["fleet_transport_paths"] = paths
    annotated["fleet_optimizer_action"] = fleet_decision.action
    selected_targets = {
        path_id: {"udp_host": target[0], "udp_port": target[1]}
        for path_id, target in (path_targets or {}).items()
        if path_id in paths
    }
    if selected_targets:
        annotated["fleet_path_targets"] = selected_targets
    if fleet_decision.mode is TransportMode.REDUNDANT:
        annotated["fleet_path_redundancy"] = max(1, len(paths))
    return annotated


def fleet_path_targets_for_event(
    event: Mapping[str, object],
) -> list[tuple[str, tuple[str, int]]]:
    raw_targets = event.get("fleet_path_targets")
    if not isinstance(raw_targets, Mapping):
        return []
    targets = {
        str(path_id): target
        for path_id, raw_target in raw_targets.items()
        if (target := udp_target_from_payload(raw_target)) is not None
    }
    result = []
    for raw_path_id in _sequence_value(event.get("fleet_transport_paths", [])):
        path_id = str(raw_path_id)
        if path_id in targets:
            result.append((path_id, targets[path_id]))
    return result


def fleet_path_redundancy_for_event(event: Mapping[str, object]) -> int:
    try:
        return max(1, int(event.get("fleet_path_redundancy", 1)))
    except (TypeError, ValueError):
        return 1


def fleet_optimizer_response_payload(
    decisions: Iterable[FleetPathDecision],
) -> dict[str, object]:
    items = list(decisions)
    mode_counts = Counter(decision.mode.value for decision in items)
    action_counts = Counter(decision.action for decision in items)
    return {
        "schema_version": "fleetrmw.fleet_optimizer_runtime.v1",
        "decision_count": len(items),
        "send_count": sum(1 for decision in items if decision.action.startswith("send")),
        "redundant_count": mode_counts.get(TransportMode.REDUNDANT.value, 0),
        "degraded_count": mode_counts.get(TransportMode.DEGRADED.value, 0),
        "drop_count": sum(1 for decision in items if decision.action in {"drop", "defer"}),
        "mode_counts": dict(mode_counts),
        "action_counts": dict(action_counts),
    }


def _loss_fraction_value(value: object) -> float:
    try:
        parsed = float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return 0.0
    if parsed > 1.0:
        parsed /= 100.0
    return _clamp_float(parsed, lower=0.0, upper=1.0)


def control_lease_redundancy_for_config(config: RuntimeConfig) -> int:
    explicit = config.control_lease_redundancy
    if explicit is not None:
        return max(1, int(explicit))
    if config.policy in {
        "fleetqox_semantic_contract_budgeted_deadline_first",
        "fleetqox_semantic_contract_budgeted_action_deadline_first",
    }:
        return 2
    return 1


def adaptive_control_lease_redundancy_for_config(config: RuntimeConfig) -> bool:
    explicit = config.control_lease_adaptive_redundancy
    if explicit is not None:
        return bool(explicit)
    return config.policy in {
        "fleetqox_semantic_contract_budgeted_deadline_first",
        "fleetqox_semantic_contract_budgeted_action_deadline_first",
    }


def paced_control_lease_redundancy_for_config(config: RuntimeConfig) -> bool:
    explicit = config.control_lease_paced_redundancy
    if explicit is not None:
        return bool(explicit)
    return config.policy in {
        "fleetqox_semantic_contract_budgeted_deadline_first",
        "fleetqox_semantic_contract_budgeted_action_deadline_first",
    }


def transmission_count_for_event(
    event: Mapping[str, object],
    control_lease_redundancy: int,
) -> int:
    if not is_control_lease_event(event):
        return 1
    explicit = event.get("control_lease_redundancy")
    if explicit is not None:
        try:
            return max(1, int(explicit))
        except (TypeError, ValueError):
            pass
    return max(1, int(control_lease_redundancy))


def control_lease_redundancy_plan_for_event(
    event: Mapping[str, object],
    config: RuntimeConfig,
    *,
    base_redundancy: int | None = None,
) -> dict[str, object]:
    base = (
        control_lease_redundancy_for_config(config)
        if base_redundancy is None
        else max(1, int(base_redundancy))
    )
    base_count = transmission_count_for_event(event, base)
    erasure_probability = control_lease_erasure_probability(event)
    residual_loss_budget = _clamp_float(
        float(config.control_lease_residual_loss_budget),
        lower=1e-6,
        upper=0.50,
    )
    max_redundancy = max(base_count, int(config.control_lease_adaptive_max_redundancy))
    adaptive_enabled = adaptive_control_lease_redundancy_for_config(config)
    needed = control_lease_redundancy_for_residual_loss(
        erasure_probability,
        residual_loss_budget,
    )
    transition_guard = control_lease_transition_guard_applies(event, config)
    if transition_guard:
        needed = max(
            needed,
            max(base_count, int(config.control_lease_transition_guard_redundancy)),
        )
        max_redundancy = max(max_redundancy, needed)
    count = base_count
    adaptive = False
    if adaptive_enabled and is_control_lease_event(event):
        count = max(base_count, min(max_redundancy, needed))
        adaptive = count > base_count
    return {
        "count": count,
        "base": base_count,
        "needed": needed,
        "adaptive": adaptive,
        "strategy": "residual_loss_budget" if adaptive_enabled else "fixed",
        "erasure_probability": erasure_probability,
        "residual_loss_budget": residual_loss_budget,
        "transition_guard": transition_guard,
        "quota_exempt": transition_guard,
    }


def control_lease_redundancy_for_residual_loss(
    erasure_probability: float,
    residual_loss_budget: float,
) -> int:
    p = _clamp_float(erasure_probability, lower=0.0, upper=0.999999)
    target = _clamp_float(residual_loss_budget, lower=1e-6, upper=0.50)
    if p <= 0.0:
        return 1
    return max(1, int(math.ceil(math.log(target) / math.log(p))))


def control_lease_erasure_probability(event: Mapping[str, object]) -> float:
    loss = _clamp_float(
        _float_from_mapping(event, "link_loss", default=0.0),
        lower=0.0,
        upper=0.95,
    )
    deadline_ms = max(1.0, _float_from_mapping(event, "deadline_ms", default=90.0))
    rtt_ms = max(0.0, _float_from_mapping(event, "link_rtt_ms", default=0.0))
    jitter_ms = max(0.0, _float_from_mapping(event, "link_jitter_ms", default=0.0))
    burst_factor = 1.0 + min(6.0, jitter_ms / 5.0)
    burst_loss = 1.0 - ((1.0 - loss) ** burst_factor)
    one_way_tail_ms = 0.5 * rtt_ms + 3.0 * jitter_ms
    tail_pressure = max(0.0, (one_way_tail_ms - 1.5 * deadline_ms) / deadline_ms)
    tail_erasure = 1.0 - math.exp(-1.25 * tail_pressure)
    return _clamp_float(
        1.0 - (1.0 - burst_loss) * (1.0 - tail_erasure),
        lower=0.0,
        upper=0.999999,
    )


def control_lease_transition_guard_applies(
    event: Mapping[str, object],
    config: RuntimeConfig,
) -> bool:
    if not config.control_lease_transition_guard_enabled:
        return False
    if not is_control_lease_event(event):
        return False
    estimate = event.get("transport_binding_estimate")
    if not isinstance(estimate, Mapping):
        return False
    if bool(estimate.get("changed", False)):
        return True
    confidence = _float_from_mapping(estimate, "confidence", default=1.0)
    margin = _float_from_mapping(estimate, "margin", default=1.0)
    dwell_ticks = int(_float_from_mapping(estimate, "dwell_ticks", default=999999.0))
    if confidence < float(config.control_lease_transition_guard_min_confidence):
        return True
    if margin < float(config.control_lease_transition_guard_min_margin):
        return True
    return dwell_ticks <= int(config.control_lease_transition_guard_max_dwell_ticks)


def is_control_lease_event(event: Mapping[str, object]) -> bool:
    if str(event.get("flow_class", "")) != "control":
        return False
    action = str(event.get("action", ""))
    wire_mode = str(event.get("wire_mode", ""))
    return action in {"send_intent", "send_supervisory_intent"} or wire_mode in {
        "control_intent",
        "supervisory_intent",
    }


def _control_lease_ack_key(event: Mapping[str, object]) -> tuple[str, int] | None:
    if not is_control_lease_event(event):
        return None
    robot_id = str(event.get("robot_id", "") or event.get("dst", "")).strip()
    if not robot_id:
        return None
    event_id = _optional_int_value(event.get("event_id"))
    if event_id is None:
        return None
    return (robot_id, event_id)


def _control_lease_ack_event_ids_from_feedback(
    record: Mapping[str, object],
) -> list[int]:
    raw_ids = record.get(
        "control_lease_event_ids",
        record.get("acked_control_lease_event_ids", record.get("event_ids")),
    )
    ids: list[int] = []
    if isinstance(raw_ids, (list, tuple, set)):
        for item in raw_ids:
            event_id = _optional_int_value(item)
            if event_id is not None:
                ids.append(event_id)
    event_id = _optional_int_value(record.get("event_id"))
    if (
        event_id is not None
        and str(record.get("flow_class", "")).strip().lower() == "control"
        and bool(record.get("control_delivered", record.get("received", False)))
    ):
        ids.append(event_id)
    return sorted(set(ids))


def _control_lease_source_ack_keys(record: Mapping[str, object]) -> list[tuple[str, ...]]:
    robot_id = str(record.get("robot_id", "") or record.get("dst", "")).strip()
    if not robot_id:
        return []
    keys: list[tuple[str, ...]] = []
    ack = _mapping_value(record, "ack")
    sample_id = _first_optional_str(
        record.get("source_sample_id"),
        _mapping_value(ack, "source_sample_id"),
        _mapping_value(record.get("sample_envelope"), "source_sample_id"),
        _mapping_value(record.get("semantic_payload"), "source_sample_id"),
    )
    if sample_id:
        keys.append(("sample", robot_id, sample_id))
    sequence_number = _first_optional_int(
        record.get("source_sequence_number"),
        _mapping_value(ack, "source_sequence_number"),
        _mapping_value(record.get("source_metadata"), "source_sequence_number"),
        _mapping_value(record.get("source_metadata"), "sequence_number"),
        _mapping_value(record.get("sample_envelope"), "source_sequence_number"),
        _mapping_value(record.get("semantic_payload"), "source_sequence_number"),
        _mapping_value(_mapping_value(record.get("semantic_payload"), "source_metadata"), "sequence_number"),
    )
    if sequence_number is None:
        return keys
    stream = _first_optional_str(
        record.get("source_topic"),
        record.get("topic"),
        _mapping_value(record.get("sample_envelope"), "topic"),
        _mapping_value(record.get("semantic_payload"), "source_topic"),
        record.get("flow_id"),
    )
    if stream:
        keys.append(("sequence", robot_id, stream, str(sequence_number)))
    return keys


def _control_lease_nack_source_keys_from_feedback(
    record: Mapping[str, object],
) -> list[tuple[str, ...]]:
    ranges = _control_lease_nack_missing_ranges_from_feedback(record)
    if not ranges:
        return []
    stream_key = _sequence_value(record.get("stream_key"))
    robot_id = _first_optional_str(
        record.get("robot_id"),
        stream_key[1] if len(stream_key) > 1 else None,
    )
    stream = _first_optional_str(
        record.get("source_topic"),
        record.get("topic"),
        stream_key[2] if len(stream_key) > 2 else None,
        record.get("flow_id"),
    )
    if not robot_id or not stream:
        return []
    keys: list[tuple[str, ...]] = []
    budget = 512
    for start, end in ranges:
        for sequence in range(start, end + 1):
            keys.append(("sequence", robot_id, stream, str(sequence)))
            if len(keys) >= budget:
                return keys
    return keys


def _control_lease_nack_missing_ranges_from_feedback(
    record: Mapping[str, object],
) -> list[tuple[int, int]]:
    nack = _mapping_value(record, "nack")
    raw_ranges = _mapping_value(nack, "missing_sequence_ranges")
    if raw_ranges is None:
        raw_ranges = record.get("missing_sequence_ranges")
    ranges: list[tuple[int, int]] = []
    for raw_range in _sequence_value(raw_ranges):
        items = _sequence_value(raw_range)
        if len(items) < 2:
            continue
        start = _optional_int_value(items[0])
        end = _optional_int_value(items[1])
        if start is None or end is None:
            continue
        if start > end:
            start, end = end, start
        ranges.append((start, end))
    return ranges


def _mapping_value(value: object, key: str) -> object:
    if not isinstance(value, Mapping):
        return None
    return value.get(key)


def _sequence_value(value: object) -> list:
    return list(value) if isinstance(value, list | tuple) else []


def _first_optional_str(*values: object) -> str | None:
    for value in values:
        if value is None or value == "":
            continue
        return str(value)
    return None


def _first_optional_int(*values: object) -> int | None:
    for value in values:
        parsed = _optional_int_value(value)
        if parsed is not None:
            return parsed
    return None


def _optional_int_value(value: object) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def apply_transport_volatility_guard(
    event: Mapping[str, object],
    estimate: Mapping[str, object] | None,
    *,
    enabled: bool = True,
    min_confidence: float = 0.65,
    min_margin: float = 0.08,
    min_dwell_ticks: int = 2,
) -> dict[str, object]:
    guarded = dict(event)
    if not transport_volatility_guard_applies(
        guarded,
        estimate,
        enabled=enabled,
        min_confidence=min_confidence,
        min_margin=min_margin,
        min_dwell_ticks=min_dwell_ticks,
    ):
        return guarded
    reason = str(guarded.get("reason", ""))
    guarded.update(
        {
            "event_type": "decision",
            "action": "defer",
            "bytes": 0,
            "degraded": False,
            "wire_mode": "",
            "predicted_slack_ms": 0.0,
            "reason": (
                "transport_volatility_guard=defer_noncontrol; "
                f"{transport_volatility_reason(estimate)}; "
                f"from={event.get('wire_mode', '') or event.get('action', '')}; "
                f"{reason}"
            ),
        }
    )
    return guarded


def transport_volatility_guard_applies(
    event: Mapping[str, object],
    estimate: Mapping[str, object] | None,
    *,
    enabled: bool = True,
    min_confidence: float = 0.65,
    min_margin: float = 0.08,
    min_dwell_ticks: int = 2,
) -> bool:
    if not enabled or not isinstance(estimate, Mapping):
        return False
    if str(event.get("event_type", "")) != "packet":
        return False
    if str(event.get("flow_class", "")) in {"control", "safety"}:
        return False
    if str(event.get("action", "")) not in ADMITTED_OR_CONSUMED_ACTIONS:
        return False
    confidence = _float_from_mapping(estimate, "confidence", default=1.0)
    margin = _float_from_mapping(estimate, "margin", default=1.0)
    dwell_ticks = int(_float_from_mapping(estimate, "dwell_ticks", default=999.0))
    changed = bool(estimate.get("changed", False))
    return (
        confidence < min_confidence
        or margin < min_margin
        or (changed and dwell_ticks < min_dwell_ticks)
    )


def transport_volatility_reason(estimate: Mapping[str, object] | None) -> str:
    if not isinstance(estimate, Mapping):
        return "estimate=missing"
    confidence = _float_from_mapping(estimate, "confidence", default=1.0)
    margin = _float_from_mapping(estimate, "margin", default=1.0)
    dwell_ticks = int(_float_from_mapping(estimate, "dwell_ticks", default=0.0))
    changed = bool(estimate.get("changed", False))
    profile = str(estimate.get("profile", ""))
    candidate = str(estimate.get("candidate_profile", ""))
    return (
        f"profile={profile}; "
        f"candidate={candidate}; "
        f"confidence={confidence:.3f}; "
        f"margin={margin:.3f}; "
        f"dwell_ticks={dwell_ticks}; "
        f"changed={changed}"
    )


def _float_from_mapping(
    payload: Mapping[str, object],
    key: str,
    *,
    default: float,
) -> float:
    try:
        return float(payload.get(key, default))
    except (TypeError, ValueError):
        return default


def _clamp_float(value: float, *, lower: float, upper: float) -> float:
    return min(upper, max(lower, float(value)))


def generate_synthetic_batches(
    *,
    scenario: str,
    robots: int,
    seconds: int,
    seed: int,
    capacity_bytes_per_second: int | None = None,
    link_rtt_ms: float | None = None,
    link_jitter_ms: float | None = None,
    link_loss: float | None = None,
    max_ticks: int | None = None,
) -> list[dict[str, object]]:
    return list(
        SyntheticBatchStream(
            scenario=scenario,
            robots=robots,
            seconds=seconds,
            seed=seed,
            capacity_bytes_per_second=capacity_bytes_per_second,
            link_rtt_ms=link_rtt_ms,
            link_jitter_ms=link_jitter_ms,
            link_loss=link_loss,
            max_ticks=max_ticks,
        )
    )


class SyntheticBatchStream:
    """Generate ROS-like batches, optionally with closed-loop age feedback."""

    def __init__(
        self,
        *,
        scenario: str,
        robots: int,
        seconds: int,
        seed: int,
        capacity_bytes_per_second: int | None = None,
        link_rtt_ms: float | None = None,
        link_jitter_ms: float | None = None,
        link_loss: float | None = None,
        max_ticks: int | None = None,
        include_feedback: bool = False,
    ) -> None:
        self.scenario = scenario
        self.seed = seed
        self.ticks_per_second = TICKS_PER_SECOND
        self.tick_ms = 1000.0 / self.ticks_per_second
        self.ticks = seconds * self.ticks_per_second
        if max_ticks is not None:
            self.ticks = min(self.ticks, max_ticks)
        self.capacity_per_tick = (
            capacity_bytes_per_second
            if capacity_bytes_per_second is not None
            else max(200_000, robots * 6_000)
        ) // self.ticks_per_second
        self.rng = random.Random(seed)
        self.flows = build_fleet_workload(robots, seed)
        self.ages = {flow.flow_id: 0.0 for flow in self.flows}
        self.include_feedback = include_feedback
        self.link_rtt_ms = link_rtt_ms
        self.link_jitter_ms = link_jitter_ms
        self.link_loss = link_loss

    def __iter__(self) -> Iterable[dict[str, object]]:
        for tick in range(self.ticks):
            yield self.batch(tick)

    def batch(self, tick: int) -> dict[str, object]:
        link = self.link_for_tick(tick)
        batch_flows = []
        for flow in self.flows:
            self.ages[flow.flow_id] += self.tick_ms
            if self.rng.random() > min(0.95, flow.nominal_rate_hz / self.ticks_per_second):
                continue
            obs = FlowObservation(
                age_ms=self.ages[flow.flow_id],
                queue_depth=1 if self.rng.random() < 0.8 else 2,
                measured_loss=link.loss,
                measured_rtt_ms=link.rtt_ms,
                observed_jitter_ms=link.jitter_ms,
                task=_task_for(flow, self.rng),
            )
            batch_flows.append(
                {
                    "flow": flow_spec_to_payload(flow),
                    "observation": observation_to_payload(obs),
                }
            )
        batch = {
            "type": "batch",
            "scenario": self.scenario,
            "timestamp_ms": tick * self.tick_ms,
            "tick": tick,
            "link": link_to_payload(link),
            "flows": batch_flows,
        }
        if self.include_feedback:
            batch["include_feedback"] = True
        return batch

    def apply_feedback(self, response: Mapping[str, object]) -> None:
        feedback = response.get("feedback", [])
        if not isinstance(feedback, list):
            return
        for item in feedback:
            if not isinstance(item, Mapping):
                continue
            flow_id = str(item.get("flow_id", ""))
            action = str(item.get("action", ""))
            if action in ADMITTED_OR_CONSUMED_ACTIONS and flow_id in self.ages:
                self.ages[flow_id] = 0.0

    def link_for_tick(self, tick: int) -> NetworkLink:
        base_loss = 0.04 if self.link_loss is None else self.link_loss
        base_jitter_ms = 8.0 if self.link_jitter_ms is None else self.link_jitter_ms
        base_rtt_ms = 22.0 if self.link_rtt_ms is None else self.link_rtt_ms
        loss_burst = 0.10 if self.link_loss is None and tick % 83 in range(8) else 0.0
        jitter_burst = 18.0 if self.link_jitter_ms is None and tick % 57 in range(6) else 0.0
        rtt_burst = 35.0 if self.link_rtt_ms is None and tick % 67 in range(4) else 0.0
        return NetworkLink(
            capacity_bytes_per_tick=_vary_capacity(self.capacity_per_tick, tick),
            loss=min(1.0, base_loss + loss_burst),
            jitter_ms=base_jitter_ms + jitter_burst,
            rtt_ms=base_rtt_ms + rtt_burst,
        )


def build_sidecar_event(
    *,
    event_id: int,
    scenario: str,
    policy: str,
    timestamp_ms: float,
    tick: int,
    flow: FlowSpec,
    obs: FlowObservation,
    link: NetworkLink,
    decision: FlowDecision,
    contract_id: str | None = None,
    source_sample_id: str | None = None,
    source_metadata: Mapping[str, object] | None = None,
    sample_envelope: Mapping[str, object] | None = None,
    semantic_payload: Mapping[str, object] | None = None,
    transport_binding: Mapping[str, object] | None = None,
    transport_binding_estimate: Mapping[str, object] | None = None,
) -> dict[str, object]:
    original_bytes = _original_size(flow, obs)
    admitted = is_admitted_action(decision.action)
    deadline_ms = effective_deadline_ms(flow, decision, link)
    lifespan_ms = effective_lifespan_ms(flow, decision, link)
    event = {
        "schema_version": SIDECAR_TRACE_SCHEMA_VERSION,
        "event_type": "packet" if admitted else "decision",
        "experiment": "fleetrmw_runtime_sidecar",
        "scenario": scenario,
        "policy": policy,
        **({"contract_id": contract_id} if contract_id else {}),
        **({"source_sample_id": source_sample_id} if source_sample_id else {}),
        **({"source_metadata": dict(source_metadata)} if source_metadata else {}),
        **({"sample_envelope": dict(sample_envelope)} if sample_envelope else {}),
        **(
            {"transport_binding": dict(transport_binding)}
            if transport_binding
            else {}
        ),
        **(
            {"transport_binding_estimate": dict(transport_binding_estimate)}
            if transport_binding_estimate
            else {}
        ),
        "event_id": event_id,
        "timestamp_ms": timestamp_ms,
        "tick": tick,
        "flow_id": flow.flow_id,
        "flow_class": flow.flow_class.value,
        "topic": flow.topic,
        "source_msg_type": flow.tags.get("ros2_msg_type", ""),
        "robot_id": flow.robot_id,
        "src": source_for(flow),
        "dst": destination_for(flow),
        "action": decision.action,
        "bytes": decision.allocated_bytes,
        "original_bytes": original_bytes,
        "degraded": decision.degraded,
        "deadline_ms": deadline_ms,
        "source_deadline_ms": flow.qos.deadline_ms,
        "lifespan_ms": lifespan_ms,
        "source_lifespan_ms": flow.qos.lifespan_ms,
        "liveliness_lease_ms": flow.qos.liveliness_lease_ms,
        "qos_reliability": flow.qos.reliability,
        "reliability": decision.reliability or flow.qos.reliability,
        "wire_mode": decision.wire_mode or "native",
        "predicted_slack_ms": decision.predicted_slack_ms,
        "reason": decision.reason,
        "priority": decision.priority,
        "semantic_utility": _utility(flow, obs, degraded=decision.degraded),
        "age_ms": obs.age_ms,
        "queue_depth": obs.queue_depth,
        "task_criticality": obs.task.task_criticality,
        "collision_risk": obs.task.collision_risk,
        "operator_attention": obs.task.operator_attention,
        "coordination_pressure": obs.task.coordination_pressure,
        "link_capacity_bytes_per_tick": link.capacity_bytes_per_tick,
        "link_loss": link.loss,
        "link_jitter_ms": link.jitter_ms,
        "link_rtt_ms": link.rtt_ms,
    }
    if semantic_payload:
        event["semantic_payload"] = dict(semantic_payload)
    return event


def _mapping_or_none(value: object) -> dict[str, object] | None:
    return dict(value) if isinstance(value, Mapping) else None


def effective_deadline_ms(
    flow: FlowSpec,
    decision: FlowDecision,
    link: NetworkLink,
) -> float:
    if decision.wire_mode == "control_intent":
        return control_intent_deadline_ms(flow, link)
    if decision.wire_mode == "supervisory_intent":
        return supervisory_intent_deadline_ms(flow, link)
    return flow.qos.deadline_ms


def effective_lifespan_ms(
    flow: FlowSpec,
    decision: FlowDecision,
    link: NetworkLink,
) -> float:
    if decision.wire_mode == "control_intent":
        return max(flow.qos.lifespan_ms, control_intent_deadline_ms(flow, link))
    if decision.wire_mode == "supervisory_intent":
        return max(flow.qos.lifespan_ms, supervisory_intent_deadline_ms(flow, link))
    return flow.qos.lifespan_ms


def payload_for_event(event: Mapping[str, object], *, packet_format: str = "event_json") -> bytes:
    target_size = max(1, int(float(event.get("bytes", 1))))
    if packet_format == "event_json":
        body = json.dumps(event, sort_keys=True, separators=(",", ":")).encode("utf-8")
        if len(body) >= target_size:
            return body
        return body + b" " * (target_size - len(body))
    if packet_format == "data_frame":
        return encode_data_frame(data_frame_from_sidecar_event(event), target_size=target_size)
    raise ValueError(f"unknown packet_format: {packet_format}")


def feedback_for_event(event: Mapping[str, object]) -> dict[str, object]:
    return {
        "contract_id": str(event.get("contract_id", "")),
        "source_sample_id": str(event.get("source_sample_id", "")),
        "event_id": int(event.get("event_id", -1)),
        "flow_id": str(event.get("flow_id", "")),
        "flow_class": str(event.get("flow_class", "")),
        "action": str(event.get("action", "")),
        "event_type": str(event.get("event_type", "")),
        "bytes": int(event.get("bytes", 0)),
        "predicted_slack_ms": float(event.get("predicted_slack_ms", 0.0)),
    }


def flow_spec_to_payload(flow: FlowSpec) -> dict[str, object]:
    return {
        "flow_id": flow.flow_id,
        "robot_id": flow.robot_id,
        "topic": flow.topic,
        "flow_class": flow.flow_class.value,
        "qos": {
            "reliability": flow.qos.reliability,
            "durability": flow.qos.durability,
            "depth": flow.qos.depth,
            "deadline_ms": flow.qos.deadline_ms,
            "lifespan_ms": flow.qos.lifespan_ms,
            "liveliness_lease_ms": flow.qos.liveliness_lease_ms,
        },
        "qoe": {
            "operator_visible": flow.qoe.operator_visible,
            "smoothness_weight": flow.qoe.smoothness_weight,
            "freeze_penalty": flow.qoe.freeze_penalty,
            "visual_confidence_weight": flow.qoe.visual_confidence_weight,
        },
        "nominal_size_bytes": flow.nominal_size_bytes,
        "nominal_rate_hz": flow.nominal_rate_hz,
        "causal_task_gain": flow.causal_task_gain,
        "redundancy": flow.redundancy,
        "semantic_delta_ratio": flow.semantic_delta_ratio,
        "tags": dict(flow.tags),
    }


def observation_to_payload(obs: FlowObservation) -> dict[str, object]:
    return {
        "age_ms": obs.age_ms,
        "queue_depth": obs.queue_depth,
        "measured_loss": obs.measured_loss,
        "measured_rtt_ms": obs.measured_rtt_ms,
        "observed_jitter_ms": obs.observed_jitter_ms,
        "task": {
            "task_id": obs.task.task_id,
            "robot_id": obs.task.robot_id,
            "task_criticality": obs.task.task_criticality,
            "collision_risk": obs.task.collision_risk,
            "operator_attention": obs.task.operator_attention,
            "coordination_pressure": obs.task.coordination_pressure,
        },
    }


def link_to_payload(link: NetworkLink) -> dict[str, object]:
    return {
        "capacity_bytes_per_tick": link.capacity_bytes_per_tick,
        "loss": link.loss,
        "jitter_ms": link.jitter_ms,
        "rtt_ms": link.rtt_ms,
    }


def flow_spec_from_payload(payload: object) -> FlowSpec:
    data = dict(payload) if isinstance(payload, Mapping) else {}
    qos_data = dict(data.get("qos", {})) if isinstance(data.get("qos", {}), Mapping) else {}
    qoe_data = dict(data.get("qoe", {})) if isinstance(data.get("qoe", {}), Mapping) else {}
    return FlowSpec(
        flow_id=str(data["flow_id"]),
        robot_id=str(data["robot_id"]),
        topic=str(data["topic"]),
        flow_class=FlowClass(str(data["flow_class"])),
        qos=QoSProfile(
            reliability=str(qos_data.get("reliability", "best_effort")),
            durability=str(qos_data.get("durability", "volatile")),
            depth=int(qos_data.get("depth", 1)),
            deadline_ms=float(qos_data.get("deadline_ms", 100.0)),
            lifespan_ms=float(qos_data.get("lifespan_ms", 250.0)),
            liveliness_lease_ms=float(qos_data.get("liveliness_lease_ms", 500.0)),
        ),
        qoe=QoEProfile(
            operator_visible=bool(qoe_data.get("operator_visible", False)),
            smoothness_weight=float(qoe_data.get("smoothness_weight", 0.0)),
            freeze_penalty=float(qoe_data.get("freeze_penalty", 0.0)),
            visual_confidence_weight=float(qoe_data.get("visual_confidence_weight", 0.0)),
        ),
        nominal_size_bytes=int(data.get("nominal_size_bytes", 1)),
        nominal_rate_hz=float(data.get("nominal_rate_hz", 1.0)),
        causal_task_gain=float(data.get("causal_task_gain", 0.0)),
        redundancy=float(data.get("redundancy", 0.0)),
        semantic_delta_ratio=float(data.get("semantic_delta_ratio", 1.0)),
        tags=dict(data.get("tags", {})) if isinstance(data.get("tags", {}), Mapping) else {},
    )


def observation_from_payload(payload: object, flow: FlowSpec) -> FlowObservation:
    data = dict(payload) if isinstance(payload, Mapping) else {}
    task_data = dict(data.get("task", {})) if isinstance(data.get("task", {}), Mapping) else {}
    return FlowObservation(
        age_ms=float(data.get("age_ms", 0.0)),
        queue_depth=int(data.get("queue_depth", 1)),
        measured_loss=float(data.get("measured_loss", 0.0)),
        measured_rtt_ms=float(data.get("measured_rtt_ms", 20.0)),
        observed_jitter_ms=float(data.get("observed_jitter_ms", 0.0)),
        task=TaskContext(
            task_id=str(task_data.get("task_id", "unknown")),
            robot_id=str(task_data.get("robot_id", flow.robot_id)),
            task_criticality=float(task_data.get("task_criticality", 0.0)),
            collision_risk=float(task_data.get("collision_risk", 0.0)),
            operator_attention=float(task_data.get("operator_attention", 0.0)),
            coordination_pressure=float(task_data.get("coordination_pressure", 0.0)),
        ),
    )


def link_from_payload(payload: object) -> NetworkLink:
    data = dict(payload) if isinstance(payload, Mapping) else {}
    return NetworkLink(
        capacity_bytes_per_tick=int(data.get("capacity_bytes_per_tick", 1)),
        loss=float(data.get("loss", 0.0)),
        jitter_ms=float(data.get("jitter_ms", 0.0)),
        rtt_ms=float(data.get("rtt_ms", 20.0)),
    )


def source_for(flow: FlowSpec) -> str:
    if flow.flow_class is FlowClass.CONTROL:
        return "fleet_controller"
    return flow.robot_id


def destination_for(flow: FlowSpec) -> str:
    if flow.flow_class is FlowClass.CONTROL:
        return flow.robot_id
    if flow.flow_class is FlowClass.HUMAN_QOE:
        return "operator_ui"
    return "fleet_router"


def _original_size(flow: FlowSpec, obs: FlowObservation) -> int:
    return max(1, int(flow.nominal_size_bytes * flow.semantic_delta_ratio * max(1, obs.queue_depth)))

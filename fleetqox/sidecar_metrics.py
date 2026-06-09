"""Metrics for FleetRMW sidecar runtime decision logs."""

from __future__ import annotations

import json
import math
from dataclasses import dataclass, field
from pathlib import Path
from statistics import mean
from typing import Iterable, Mapping


PER_ROBOT_QOS_SCHEMA_VERSION = "fleetrmw.per_robot_qos.v1"


@dataclass
class SidecarRuntimeStats:
    policy: str
    tx: int = 0
    rx: int = 0
    bytes_tx: int = 0
    bytes_rx: int = 0
    compacted_tx: int = 0
    compacted_rx: int = 0
    intent_tx: int = 0
    intent_rx: int = 0
    deadline_miss: int = 0
    control_starvation_events: int = 0
    control_decisions: int = 0
    control_tx: int = 0
    control_rx: int = 0
    control_drop_events: int = 0
    control_defer_events: int = 0
    qoe_freeze_events: int = 0
    semantic_utility_delivered: float = 0.0
    latencies_ms: list[float] = field(default_factory=list)

    def as_record(self) -> dict[str, object]:
        lost = max(0, self.tx - self.rx)
        return {
            "policy": self.policy,
            "tx": self.tx,
            "rx": self.rx,
            "lost": lost,
            "loss_ratio": lost / max(1, self.tx),
            "bytes_tx": self.bytes_tx,
            "bytes_rx": self.bytes_rx,
            "compacted_tx": self.compacted_tx,
            "compacted_rx": self.compacted_rx,
            "intent_tx": self.intent_tx,
            "intent_rx": self.intent_rx,
            "deadline_miss_ratio": self.deadline_miss / max(1, self.rx),
            "control_starvation_events": self.control_starvation_events,
            "control_decisions": self.control_decisions,
            "control_tx": self.control_tx,
            "control_rx": self.control_rx,
            "control_drop_events": self.control_drop_events,
            "control_defer_events": self.control_defer_events,
            "control_non_delivery_events": self.control_drop_events + self.control_defer_events,
            "control_tx_ratio": self.control_tx / max(1, self.control_decisions),
            "control_delivery_ratio": self.control_rx / max(1, self.control_decisions),
            "qoe_freeze_events": self.qoe_freeze_events,
            "semantic_utility_delivered": self.semantic_utility_delivered,
            "latency_mean_ms": mean(self.latencies_ms) if self.latencies_ms else 0.0,
            "latency_p50_ms": percentile(self.latencies_ms, 50),
            "latency_p95_ms": percentile(self.latencies_ms, 95),
            "latency_p99_ms": percentile(self.latencies_ms, 99),
        }


@dataclass
class RobotRuntimeStats:
    robot_id: str
    tx: int = 0
    rx: int = 0
    bytes_tx: int = 0
    bytes_rx: int = 0
    control_decisions: int = 0
    control_tx: int = 0
    control_rx: int = 0
    control_drop_events: int = 0
    control_defer_events: int = 0
    deadline_miss: int = 0
    control_starvation_events: int = 0
    qoe_freeze_events: int = 0
    semantic_utility_delivered: float = 0.0
    latencies_ms: list[float] = field(default_factory=list)
    flow_class_tx: dict[str, int] = field(default_factory=dict)
    flow_class_rx: dict[str, int] = field(default_factory=dict)

    def as_record(self) -> dict[str, object]:
        lost = max(0, self.tx - self.rx)
        deadline_miss_ratio = self.deadline_miss / max(1, self.rx)
        return {
            "robot_id": self.robot_id,
            "tx": self.tx,
            "rx": self.rx,
            "lost": lost,
            "loss_ratio": lost / max(1, self.tx),
            "bytes_tx": self.bytes_tx,
            "bytes_rx": self.bytes_rx,
            "control_decisions": self.control_decisions,
            "control_tx": self.control_tx,
            "control_rx": self.control_rx,
            "control_drop_events": self.control_drop_events,
            "control_defer_events": self.control_defer_events,
            "control_non_delivery_events": self.control_drop_events + self.control_defer_events,
            "control_tx_ratio": self.control_tx / max(1, self.control_decisions),
            "control_delivery_ratio": self.control_rx / max(1, self.control_decisions),
            "deadline_miss": self.deadline_miss,
            "deadline_miss_ratio": deadline_miss_ratio,
            "deadline_success_ratio": max(0.0, 1.0 - deadline_miss_ratio),
            "control_starvation_events": self.control_starvation_events,
            "qoe_freeze_events": self.qoe_freeze_events,
            "semantic_utility_delivered": self.semantic_utility_delivered,
            "latency_mean_ms": mean(self.latencies_ms) if self.latencies_ms else 0.0,
            "latency_p50_ms": percentile(self.latencies_ms, 50),
            "latency_p95_ms": percentile(self.latencies_ms, 95),
            "latency_p99_ms": percentile(self.latencies_ms, 99),
            "flow_class_tx": dict(sorted(self.flow_class_tx.items())),
            "flow_class_rx": dict(sorted(self.flow_class_rx.items())),
        }


def analyze_sidecar_runtime(
    decision_jsonl: str | Path,
    received_jsonl: str | Path,
) -> list[dict[str, object]]:
    stats, events = _tx_stats(decision_jsonl)
    seen_received_event_ids: set[int] = set()
    with Path(received_jsonl).open("r", encoding="utf-8") as handle:
        for line in handle:
            if not line.strip():
                continue
            packet = json.loads(line)
            event_id = int(packet["event_id"])
            if event_id in seen_received_event_ids:
                continue
            seen_received_event_ids.add(event_id)
            policy = str(packet["policy"])
            event = events.get(event_id, {})
            stat = stats.setdefault(policy, SidecarRuntimeStats(policy=policy))
            stat.rx += 1
            stat.bytes_rx += int(packet["bytes"])
            latency_ms = float(packet["latency_ms"])
            deadline_ms = float(packet["deadline_ms"])
            stat.latencies_ms.append(latency_ms)
            stat.semantic_utility_delivered += float(packet["semantic_utility"])
            if packet["flow_class"] == "control":
                stat.control_rx += 1
            if event.get("action") == "send_compacted":
                stat.compacted_rx += 1
            if event.get("action") in {"send_intent", "send_supervisory_intent"}:
                stat.intent_rx += 1
            if latency_ms > deadline_ms and not _is_control_lease_event(event, packet):
                stat.deadline_miss += 1
                if packet["flow_class"] == "control":
                    stat.control_starvation_events += 1
                if packet["flow_class"] == "human_qoe":
                    stat.qoe_freeze_events += 1
    return [stats[key].as_record() for key in sorted(stats)]


def analyze_sidecar_runtime_by_robot(
    decision_jsonl: str | Path,
    received_jsonl: str | Path,
) -> dict[str, object]:
    stats, events = _tx_stats_by_robot(decision_jsonl)
    seen_received_event_ids: set[int] = set()
    with Path(received_jsonl).open("r", encoding="utf-8") as handle:
        for line in handle:
            if not line.strip():
                continue
            packet = json.loads(line)
            event_id = int(packet.get("event_id", -1))
            if event_id in seen_received_event_ids:
                continue
            seen_received_event_ids.add(event_id)
            event = events.get(event_id, {})
            robot_id = _robot_id_from_mapping(packet) or _robot_id_from_mapping(event)
            if not robot_id:
                continue
            stat = stats.setdefault(robot_id, RobotRuntimeStats(robot_id=robot_id))
            stat.rx += 1
            stat.bytes_rx += int(packet.get("bytes", 0))
            flow_class = str(packet.get("flow_class", ""))
            _increment(stat.flow_class_rx, flow_class)
            latency_ms = float(packet.get("latency_ms", 0.0))
            deadline_ms = float(packet.get("deadline_ms", 0.0))
            stat.latencies_ms.append(latency_ms)
            stat.semantic_utility_delivered += float(packet.get("semantic_utility", 0.0))
            if flow_class == "control":
                stat.control_rx += 1
            if latency_ms > deadline_ms and not _is_control_lease_event(event, packet):
                stat.deadline_miss += 1
                if flow_class == "control":
                    stat.control_starvation_events += 1
                if flow_class == "human_qoe":
                    stat.qoe_freeze_events += 1
    records = [stats[key].as_record() for key in sorted(stats)]
    return {
        "schema_version": PER_ROBOT_QOS_SCHEMA_VERSION,
        "robot_count": len(records),
        "robots": [str(record["robot_id"]) for record in records],
        "by_robot": {str(record["robot_id"]): record for record in records},
        "fairness": per_robot_fairness(records),
    }


def per_robot_fairness(records: Iterable[Mapping[str, object]]) -> dict[str, object]:
    rows = [dict(record) for record in records]
    return {
        "rx_jain_index": jain_index(_metric_values(rows, "rx")),
        "control_delivery_jain_index": jain_index(_metric_values(rows, "control_delivery_ratio")),
        "deadline_success_jain_index": jain_index(_metric_values(rows, "deadline_success_ratio")),
        "semantic_utility_jain_index": jain_index(_metric_values(rows, "semantic_utility_delivered")),
        "min_control_delivery_ratio": min(_metric_values(rows, "control_delivery_ratio"), default=0.0),
        "max_deadline_miss_ratio": max(_metric_values(rows, "deadline_miss_ratio"), default=0.0),
        "min_deadline_success_ratio": min(_metric_values(rows, "deadline_success_ratio"), default=0.0),
        "latency_p95_spread_ms": spread(_metric_values(rows, "latency_p95_ms")),
        "rx_spread": spread(_metric_values(rows, "rx")),
        "semantic_utility_spread": spread(_metric_values(rows, "semantic_utility_delivered")),
        "worst_control_delivery_robot": _robot_for_extreme(rows, "control_delivery_ratio", minimum=True),
        "worst_deadline_miss_robot": _robot_for_extreme(rows, "deadline_miss_ratio", minimum=False),
        "worst_latency_p95_robot": _robot_for_extreme(rows, "latency_p95_ms", minimum=False),
    }


def per_robot_budget_report(
    per_robot_summary: Mapping[str, object],
    *,
    min_control_delivery_ratio: float = 0.90,
    max_deadline_miss_ratio: float = 0.35,
    min_rx_jain_index: float = 0.90,
    min_control_delivery_jain_index: float = 0.95,
    min_deadline_success_jain_index: float = 0.95,
) -> dict[str, object]:
    fairness_obj = per_robot_summary.get("fairness", {})
    fairness = fairness_obj if isinstance(fairness_obj, Mapping) else {}
    checks = [
        _budget_check(
            "min_control_delivery_ratio",
            float(fairness.get("min_control_delivery_ratio", 0.0)),
            min_control_delivery_ratio,
            comparator=">=",
        ),
        _budget_check(
            "max_deadline_miss_ratio",
            float(fairness.get("max_deadline_miss_ratio", 0.0)),
            max_deadline_miss_ratio,
            comparator="<=",
        ),
        _budget_check(
            "rx_jain_index",
            float(fairness.get("rx_jain_index", 0.0)),
            min_rx_jain_index,
            comparator=">=",
        ),
        _budget_check(
            "control_delivery_jain_index",
            float(fairness.get("control_delivery_jain_index", 0.0)),
            min_control_delivery_jain_index,
            comparator=">=",
        ),
        _budget_check(
            "deadline_success_jain_index",
            float(fairness.get("deadline_success_jain_index", 0.0)),
            min_deadline_success_jain_index,
            comparator=">=",
        ),
    ]
    return {
        "schema_version": "fleetrmw.per_robot_qos_budget.v1",
        "pass": all(bool(check["pass"]) for check in checks),
        "checks": checks,
        "violations": [check for check in checks if not bool(check["pass"])],
    }


def write_sidecar_metrics_jsonl(records: Iterable[dict[str, object]], output: str | Path) -> None:
    Path(output).parent.mkdir(parents=True, exist_ok=True)
    with Path(output).open("w", encoding="utf-8") as handle:
        for record in records:
            handle.write(json.dumps(record, sort_keys=True) + "\n")


def _tx_stats(
    decision_jsonl: str | Path,
) -> tuple[dict[str, SidecarRuntimeStats], dict[int, dict[str, object]]]:
    stats: dict[str, SidecarRuntimeStats] = {}
    events: dict[int, dict[str, object]] = {}
    with Path(decision_jsonl).open("r", encoding="utf-8") as handle:
        for line in handle:
            if not line.strip():
                continue
            event = json.loads(line)
            policy = str(event["policy"])
            stat = stats.setdefault(policy, SidecarRuntimeStats(policy=policy))
            if event.get("flow_class") == "control":
                stat.control_decisions += 1
                action = str(event.get("action", ""))
                if action == "drop":
                    stat.control_drop_events += 1
                elif action == "defer":
                    stat.control_defer_events += 1
            if event.get("event_type") != "packet":
                continue
            event_id = int(event["event_id"])
            events[event_id] = event
            stat.tx += 1
            stat.bytes_tx += int(event["bytes"])
            if event.get("flow_class") == "control":
                stat.control_tx += 1
            if event.get("action") == "send_compacted":
                stat.compacted_tx += 1
            if event.get("action") in {"send_intent", "send_supervisory_intent"}:
                stat.intent_tx += 1
    return stats, events


def _tx_stats_by_robot(
    decision_jsonl: str | Path,
) -> tuple[dict[str, RobotRuntimeStats], dict[int, dict[str, object]]]:
    stats: dict[str, RobotRuntimeStats] = {}
    events: dict[int, dict[str, object]] = {}
    with Path(decision_jsonl).open("r", encoding="utf-8") as handle:
        for line in handle:
            if not line.strip():
                continue
            event = json.loads(line)
            robot_id = _robot_id_from_mapping(event)
            if not robot_id:
                continue
            stat = stats.setdefault(robot_id, RobotRuntimeStats(robot_id=robot_id))
            flow_class = str(event.get("flow_class", ""))
            if flow_class == "control":
                stat.control_decisions += 1
                action = str(event.get("action", ""))
                if action == "drop":
                    stat.control_drop_events += 1
                elif action == "defer":
                    stat.control_defer_events += 1
            if event.get("event_type") != "packet":
                continue
            event_id = int(event.get("event_id", -1))
            events[event_id] = event
            stat.tx += 1
            stat.bytes_tx += int(event.get("bytes", 0))
            _increment(stat.flow_class_tx, flow_class)
            if flow_class == "control":
                stat.control_tx += 1
    return stats, events


def _robot_id_from_mapping(payload: Mapping[str, object]) -> str:
    robot_id = str(payload.get("robot_id", "") or "")
    if robot_id:
        return robot_id
    for key in ("flow_id", "src", "dst", "topic", "source_topic"):
        candidate = _robot_id_from_text(str(payload.get(key, "") or ""))
        if candidate:
            return candidate
    return ""


def _robot_id_from_text(value: str) -> str:
    for part in value.replace("/", " ").replace(":", " ").split():
        if part.startswith("robot_") and len(part) >= len("robot_0000"):
            return part
    return ""


def _is_control_lease_event(
    event: Mapping[str, object],
    packet: Mapping[str, object],
) -> bool:
    flow_class = str(packet.get("flow_class", event.get("flow_class", "")))
    action = str(event.get("action", packet.get("action", "")))
    wire_mode = str(event.get("wire_mode", packet.get("wire_mode", "")))
    return flow_class == "control" and (
        action in {"send_intent", "send_supervisory_intent"}
        or wire_mode in {"control_intent", "supervisory_intent"}
    )


def _increment(counts: dict[str, int], key: str) -> None:
    if key:
        counts[key] = counts.get(key, 0) + 1


def _metric_values(rows: list[dict[str, object]], metric: str) -> list[float]:
    values: list[float] = []
    for row in rows:
        try:
            values.append(float(row.get(metric, 0.0)))
        except (TypeError, ValueError):
            values.append(0.0)
    return values


def jain_index(values: Iterable[float]) -> float:
    samples = [max(0.0, float(value)) for value in values]
    if not samples:
        return 0.0
    denominator = len(samples) * sum(value * value for value in samples)
    if denominator == 0.0:
        return 1.0
    return (sum(samples) ** 2) / denominator


def spread(values: Iterable[float]) -> float:
    samples = list(values)
    if not samples:
        return 0.0
    return max(samples) - min(samples)


def _robot_for_extreme(rows: list[dict[str, object]], metric: str, *, minimum: bool) -> str:
    if not rows:
        return ""
    key = lambda row: float(row.get(metric, 0.0))
    row = min(rows, key=key) if minimum else max(rows, key=key)
    return str(row.get("robot_id", ""))


def _budget_check(name: str, observed: float, threshold: float, *, comparator: str) -> dict[str, object]:
    if comparator == ">=":
        passed = observed >= threshold
    elif comparator == "<=":
        passed = observed <= threshold
    else:
        raise ValueError(f"unsupported comparator: {comparator}")
    return {
        "name": name,
        "observed": observed,
        "threshold": threshold,
        "comparator": comparator,
        "pass": passed,
    }


def percentile(values: list[float], pct: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    index = max(0, min(len(ordered) - 1, math.ceil((pct / 100.0) * len(ordered)) - 1))
    return ordered[index]

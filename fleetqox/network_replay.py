"""Trace-driven discrete-event network replay.

This module is not a replacement for ns-3 or OMNeT++. It is a lightweight
sanity replay for FleetQoX CSV traces. It validates that traces contain enough
information for packet-level simulation and provides quick queueing/deadline
metrics before running heavier external simulators.
"""

from __future__ import annotations

import csv
import heapq
import json
import math
import random
from dataclasses import dataclass, field
from pathlib import Path
from statistics import mean
from typing import Iterable


@dataclass(frozen=True)
class ReplayConfig:
    data_rate_mbps: float = 20.0
    base_delay_ms: float = 5.0
    jitter_ms: float = 0.0
    loss: float = 0.0
    seed: int = 7
    queue_policy: str = "fifo"
    transport_model: str = "udp_like"
    retransmit_delay_ms: float = 8.0

    def validate(self) -> None:
        if self.data_rate_mbps <= 0:
            raise ValueError("data_rate_mbps must be positive")
        if self.base_delay_ms < 0 or self.jitter_ms < 0 or self.retransmit_delay_ms < 0:
            raise ValueError("delay and jitter must be non-negative")
        if not 0 <= self.loss <= 1:
            raise ValueError("loss must be in [0, 1]")
        if self.queue_policy not in {"fifo", "class_priority"}:
            raise ValueError("queue_policy must be fifo or class_priority")
        if self.transport_model not in {"udp_like", "adaptive_reliability"}:
            raise ValueError("transport_model must be udp_like or adaptive_reliability")


@dataclass(frozen=True)
class PacketEvent:
    event_id: int
    timestamp_ms: float
    policy: str
    flow_id: str
    flow_class: str
    src: str
    dst: str
    bytes: int
    deadline_ms: float
    semantic_utility: float
    action: str = "send"
    reliability: str = "best_effort"
    wire_mode: str = "native"
    predicted_slack_ms: float = 0.0


@dataclass
class ReplayStats:
    policy: str
    tx: int = 0
    rx: int = 0
    lost: int = 0
    bytes_delivered: int = 0
    deadline_miss: int = 0
    control_starvation_events: int = 0
    qoe_freeze_events: int = 0
    retransmissions: int = 0
    compacted_rx: int = 0
    semantic_utility_delivered: float = 0.0
    latencies_ms: list[float] = field(default_factory=list)

    def as_record(self) -> dict[str, object]:
        return {
            "policy": self.policy,
            "tx": self.tx,
            "rx": self.rx,
            "lost": self.lost,
            "bytes_delivered": self.bytes_delivered,
            "deadline_miss_ratio": self.deadline_miss / max(1, self.rx),
            "control_starvation_events": self.control_starvation_events,
            "qoe_freeze_events": self.qoe_freeze_events,
            "retransmissions": self.retransmissions,
            "compacted_rx": self.compacted_rx,
            "semantic_utility_delivered": self.semantic_utility_delivered,
            "latency_mean_ms": mean(self.latencies_ms) if self.latencies_ms else 0.0,
            "latency_p50_ms": percentile(self.latencies_ms, 50),
            "latency_p95_ms": percentile(self.latencies_ms, 95),
            "latency_p99_ms": percentile(self.latencies_ms, 99),
        }


def load_packet_trace(path: str | Path) -> list[PacketEvent]:
    """Load FleetQoX simulator CSV rows as packet events."""

    events: list[PacketEvent] = []
    with Path(path).open("r", newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        for row in reader:
            events.append(
                PacketEvent(
                    event_id=int(row["event_id"]),
                    timestamp_ms=float(row["timestamp_ms"]),
                    policy=row["policy"],
                    flow_id=row["flow_id"],
                    flow_class=row["flow_class"],
                    src=row["src"],
                    dst=row["dst"],
                    bytes=int(float(row["bytes"])),
                    deadline_ms=float(row["deadline_ms"]),
                    semantic_utility=float(row["semantic_utility"]),
                    action=row.get("action", "send"),
                    reliability=row.get("reliability", "best_effort"),
                    wire_mode=row.get("wire_mode", "native"),
                    predicted_slack_ms=float(row.get("predicted_slack_ms") or 0.0),
                )
            )
    events.sort(key=lambda event: (event.policy, event.timestamp_ms, event.event_id))
    return events


def replay_trace(events: Iterable[PacketEvent], config: ReplayConfig) -> list[dict[str, object]]:
    """Replay packet events through a shared bottleneck queue."""

    config.validate()
    rng = random.Random(config.seed)
    by_policy: dict[str, list[PacketEvent]] = {}
    for event in events:
        by_policy.setdefault(event.policy, []).append(event)

    records = []
    for policy, policy_events in sorted(by_policy.items()):
        stats = _replay_policy(policy, policy_events, config, rng)
        record = stats.as_record()
        record.update(
            {
                "data_rate_mbps": config.data_rate_mbps,
                "base_delay_ms": config.base_delay_ms,
                "jitter_ms": config.jitter_ms,
                "loss": config.loss,
                "queue_policy": config.queue_policy,
                "transport_model": config.transport_model,
                "retransmit_delay_ms": config.retransmit_delay_ms,
            }
        )
        records.append(record)
    return records


def write_replay_jsonl(records: Iterable[dict[str, object]], output: str | Path) -> None:
    with Path(output).open("w", encoding="utf-8") as handle:
        for record in records:
            handle.write(json.dumps(record, sort_keys=True) + "\n")


def _replay_policy(
    policy: str,
    events: list[PacketEvent],
    config: ReplayConfig,
    rng: random.Random,
) -> ReplayStats:
    stats = ReplayStats(policy=policy)
    events = sorted(events, key=lambda event: (event.timestamp_ms, event.event_id))
    if config.queue_policy == "class_priority":
        return _replay_policy_class_priority(policy, events, config, rng, stats)

    server_free_ms = 0.0
    flow_last_delivery: dict[str, float] = {}
    for event in events:
        stats.tx += 1
        server_free_ms = _attempt_delivery(
            event,
            server_free_ms,
            config,
            rng,
            stats,
            flow_last_delivery,
        )
    return stats


def _replay_policy_class_priority(
    policy: str,
    events: list[PacketEvent],
    config: ReplayConfig,
    rng: random.Random,
    stats: ReplayStats,
) -> ReplayStats:
    ready: list[tuple[int, float, int, PacketEvent]] = []
    flow_last_delivery: dict[str, float] = {}
    event_index = 0
    server_free_ms = 0.0
    sequence = 0

    while event_index < len(events) or ready:
        if not ready and event_index < len(events):
            server_free_ms = max(server_free_ms, events[event_index].timestamp_ms)

        while event_index < len(events) and events[event_index].timestamp_ms <= server_free_ms:
            event = events[event_index]
            stats.tx += 1
            event_index += 1
            heapq.heappush(
                ready,
                (
                    -_class_priority(event.flow_class),
                    event.timestamp_ms,
                    sequence,
                    event,
                ),
            )
            sequence += 1

        if not ready:
            continue

        _, _, _, event = heapq.heappop(ready)
        server_free_ms = _attempt_delivery(
            event,
            server_free_ms,
            config,
            rng,
            stats,
            flow_last_delivery,
        )

    return stats


def _attempt_delivery(
    event: PacketEvent,
    server_free_ms: float,
    config: ReplayConfig,
    rng: random.Random,
    stats: ReplayStats,
    flow_last_delivery: dict[str, float],
) -> float:
    if rng.random() >= config.loss:
        return _deliver(event, server_free_ms, config, rng, stats, flow_last_delivery)
    if config.transport_model == "adaptive_reliability" and event.reliability == "reliable":
        stats.retransmissions += 1
        if rng.random() >= config.loss:
            return _deliver(
                event,
                server_free_ms,
                config,
                rng,
                stats,
                flow_last_delivery,
                extra_delay_ms=config.retransmit_delay_ms,
            )
    stats.lost += 1
    return server_free_ms


def _deliver(
    event: PacketEvent,
    server_free_ms: float,
    config: ReplayConfig,
    rng: random.Random,
    stats: ReplayStats,
    flow_last_delivery: dict[str, float],
    extra_delay_ms: float = 0.0,
) -> float:
    service_ms = event.bytes * 8.0 / (config.data_rate_mbps * 1_000_000.0) * 1000.0
    start_ms = max(event.timestamp_ms, server_free_ms)
    new_server_free_ms = start_ms + service_ms
    jitter = rng.uniform(0.0, config.jitter_ms) if config.jitter_ms else 0.0
    delivery_ms = new_server_free_ms + config.base_delay_ms + jitter + extra_delay_ms
    latency_ms = delivery_ms - event.timestamp_ms

    stats.rx += 1
    stats.bytes_delivered += event.bytes
    stats.latencies_ms.append(latency_ms)
    stats.semantic_utility_delivered += event.semantic_utility
    if event.wire_mode == "semantic_delta" or event.action == "send_compacted":
        stats.compacted_rx += 1
    if latency_ms > event.deadline_ms:
        stats.deadline_miss += 1
        if event.flow_class == "control":
            stats.control_starvation_events += 1
        if event.flow_class == "human_qoe":
            stats.qoe_freeze_events += 1

    last_delivery = flow_last_delivery.get(event.flow_id)
    if event.flow_class == "human_qoe" and last_delivery is not None:
        if delivery_ms - last_delivery > max(2 * event.deadline_ms, 250.0):
            stats.qoe_freeze_events += 1
    flow_last_delivery[event.flow_id] = delivery_ms
    return new_server_free_ms


def _class_priority(flow_class: str) -> int:
    return {
        "safety": 8,
        "control": 7,
        "coordination": 6,
        "state": 5,
        "human_qoe": 4,
        "perception": 3,
        "debug": 1,
        "bulk": 0,
    }.get(flow_class, 0)


def percentile(values: list[float], pct: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    index = max(0, min(len(ordered) - 1, math.ceil((pct / 100.0) * len(ordered)) - 1))
    return ordered[index]

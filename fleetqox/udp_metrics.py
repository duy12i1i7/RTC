"""Metrics for Docker/netem UDP trace emulation."""

from __future__ import annotations

import csv
import json
import math
from dataclasses import dataclass, field
from pathlib import Path
from statistics import mean
from typing import Iterable


@dataclass
class UdpPolicyStats:
    policy: str
    tx: int = 0
    rx: int = 0
    bytes_rx: int = 0
    deadline_miss: int = 0
    control_starvation_events: int = 0
    qoe_freeze_events: int = 0
    semantic_utility_delivered: float = 0.0
    latencies_ms: list[float] = field(default_factory=list)

    def record_rx(self, packet: dict[str, object]) -> None:
        self.rx += 1
        self.bytes_rx += int(packet["bytes"])
        latency_ms = float(packet["latency_ms"])
        deadline_ms = float(packet["deadline_ms"])
        self.latencies_ms.append(latency_ms)
        self.semantic_utility_delivered += float(packet["semantic_utility"])
        if latency_ms > deadline_ms:
            self.deadline_miss += 1
            if packet["flow_class"] == "control":
                self.control_starvation_events += 1
            if packet["flow_class"] == "human_qoe":
                self.qoe_freeze_events += 1

    def as_record(self) -> dict[str, object]:
        lost = max(0, self.tx - self.rx)
        return {
            "policy": self.policy,
            "tx": self.tx,
            "rx": self.rx,
            "lost": lost,
            "loss_ratio": lost / max(1, self.tx),
            "bytes_rx": self.bytes_rx,
            "deadline_miss_ratio": self.deadline_miss / max(1, self.rx),
            "control_starvation_events": self.control_starvation_events,
            "qoe_freeze_events": self.qoe_freeze_events,
            "semantic_utility_delivered": self.semantic_utility_delivered,
            "latency_mean_ms": mean(self.latencies_ms) if self.latencies_ms else 0.0,
            "latency_p50_ms": percentile(self.latencies_ms, 50),
            "latency_p95_ms": percentile(self.latencies_ms, 95),
            "latency_p99_ms": percentile(self.latencies_ms, 99),
        }


def analyze_udp_trace(
    trace_csv: str | Path,
    received_jsonl: str | Path,
) -> list[dict[str, object]]:
    stats = _tx_stats(trace_csv)
    with Path(received_jsonl).open("r", encoding="utf-8") as handle:
        for line in handle:
            if not line.strip():
                continue
            packet = json.loads(line)
            policy = str(packet["policy"])
            stats.setdefault(policy, UdpPolicyStats(policy=policy)).record_rx(packet)
    return [stats[key].as_record() for key in sorted(stats)]


def _tx_stats(trace_csv: str | Path) -> dict[str, UdpPolicyStats]:
    stats: dict[str, UdpPolicyStats] = {}
    with Path(trace_csv).open("r", newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        for row in reader:
            policy = row["policy"]
            stats.setdefault(policy, UdpPolicyStats(policy=policy)).tx += 1
    return stats


def write_metrics_jsonl(records: Iterable[dict[str, object]], output: str | Path) -> None:
    with Path(output).open("w", encoding="utf-8") as handle:
        for record in records:
            handle.write(json.dumps(record, sort_keys=True) + "\n")


def percentile(values: list[float], pct: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    index = max(0, min(len(ordered) - 1, math.ceil((pct / 100.0) * len(ordered)) - 1))
    return ordered[index]

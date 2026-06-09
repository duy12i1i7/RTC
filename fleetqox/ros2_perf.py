"""ROS 2 performance_test command planning and result parsing."""

from __future__ import annotations

import csv
import json
import math
import shlex
import subprocess
from dataclasses import dataclass
from pathlib import Path
from statistics import mean
from typing import Iterable

from .testbed import ExperimentScenario


DEFAULT_EXECUTOR = "rclcpp-single-threaded-executor"


@dataclass(frozen=True)
class PerfCommand:
    scenario: str
    rmw: str
    component: str
    logfile: Path
    command: list[str]
    env: dict[str, str]

    def shell(self) -> str:
        env = " ".join(f"{key}={_quote(value)}" for key, value in sorted(self.env.items()))
        args = " ".join(_quote(part) for part in self.command)
        return f"{env} {args}".strip()


def build_perf_commands(
    scenario: ExperimentScenario,
    output_dir: str | Path,
    *,
    executable: str = "perf_test",
) -> list[PerfCommand]:
    """Build performance_test commands for one T1 scenario."""

    output = Path(output_dir)
    config = scenario.config
    components = config.get("components")
    if not components:
        components = [
            {
                "name": config["name"],
                "msg": config.get("performance_msg", "Array1k"),
                "rate_hz": config.get("rate_hz", 100),
                "runtime_s": config.get("runtime_s", 30),
                "qos": config.get("qos", "reliable_keep_last_1"),
                "num_pub_threads": config.get("num_pub_threads", 1),
                "num_sub_threads": config.get("num_sub_threads", 1),
            }
        ]

    commands: list[PerfCommand] = []
    for rmw in scenario.baselines:
        for component in components:
            component_name = str(component["name"])
            logfile = output / scenario.name / rmw / f"{component_name}.csv"
            command = shlex.split(executable) + [
                "--communicator",
                str(component.get("communication", DEFAULT_EXECUTOR)),
                "--msg",
                str(component["msg"]),
                "--rate",
                str(component.get("rate_hz", 100)),
                "--topic",
                f"/fleetqox_perf/{scenario.name}/{component_name}",
                "--max-runtime",
                str(component.get("runtime_s", 30)),
                "--num-pub-threads",
                str(component.get("num_pub_threads", 1)),
                "--num-sub-threads",
                str(component.get("num_sub_threads", 1)),
                "--logfile",
                str(logfile),
            ]
            _apply_qos_flags(command, str(component.get("qos", "reliable_keep_last_1")))
            commands.append(
                PerfCommand(
                    scenario=scenario.name,
                    rmw=rmw,
                    component=component_name,
                    logfile=logfile,
                    command=command,
                    env={
                        "RMW_IMPLEMENTATION": rmw,
                        "ROS_DOMAIN_ID": str(component.get("ros_domain_id", 71)),
                        "APEX_PERFORMANCE_TEST": json.dumps(
                            {
                                "suite": "fleetqox",
                                "tier": "T1",
                                "scenario": scenario.name,
                                "rmw": rmw,
                                "component": component_name,
                            },
                            sort_keys=True,
                        ),
                    },
                )
            )
    return commands


def parse_perf_csv(path: str | Path, *, deadline_ms: float | None = None) -> dict[str, object]:
    """Parse a performance_test CSV log with best-effort column detection."""

    rows = list(_read_csv_rows(path))
    latency_values = _numeric_column(
        rows,
        ["latency_mean", "latency mean", "latency_ms", "latency_ns", "latency_us", "latency"],
    )
    latency_min_values = _numeric_column(rows, ["latency_min", "latency min"])
    latency_max_values = _numeric_column(rows, ["latency_max", "latency max"])
    cpu_values = _numeric_column(rows, ["cpu", "cpu_usage", "cpu_percent"])
    memory_values = _numeric_column(rows, ["ru_maxrss", "rss", "resident", "memory", "resident_memory"])
    sent_values = _numeric_column(rows, ["sent", "samples_sent", "num_sent"])
    received_values = _numeric_column(rows, ["received", "samples_received", "num_received"])
    lost_values = _numeric_column(rows, ["lost", "samples_lost", "num_lost"])
    data_received_values = _numeric_column(rows, ["data_received", "bytes_received"])
    experiment_time_values = _numeric_column(rows, ["T_experiment", "experiment_time"])

    latency_ms = [_to_ms(value, rows, ["latency"]) for value in latency_values]
    latency_min_ms = [_to_ms(value, rows, ["latency"]) for value in latency_min_values]
    latency_max_ms = [_to_ms(value, rows, ["latency"]) for value in latency_max_values]
    jitter_ms = _pairwise_abs_delta(latency_ms)
    sent = _count_total(sent_values, rows)
    received = _count_total(received_values, rows)
    lost = _count_total(lost_values, rows)
    if not _looks_like_performance_test_rows(rows) and lost == 0 and sent > received:
        lost = sent - received

    loss_denominator = sent if sent > 0 else received + lost
    duration_s = max(experiment_time_values) if experiment_time_values else 0.0
    data_received_bytes = sum(data_received_values)
    throughput_mbps = (data_received_bytes * 8.0 / duration_s / 1_000_000.0) if duration_s > 0 else 0.0
    deadline_miss_ratio = _deadline_miss_ratio(rows, deadline_ms) if deadline_ms else 0.0
    observed_samples = received + lost

    return {
        "path": str(path),
        "rows": len(rows),
        "latency_mean_ms": mean(latency_ms) if latency_ms else 0.0,
        "latency_min_ms": min(latency_min_ms) if latency_min_ms else 0.0,
        "latency_max_ms": max(latency_max_ms) if latency_max_ms else 0.0,
        "latency_p50_ms": percentile(latency_ms, 50),
        "latency_p95_ms": percentile(latency_ms, 95),
        "latency_p99_ms": percentile(latency_ms, 99),
        "jitter_mean_ms": mean(jitter_ms) if jitter_ms else 0.0,
        "jitter_p95_ms": percentile(jitter_ms, 95),
        "cpu_mean": mean(cpu_values) if cpu_values else 0.0,
        "memory_mean": mean(memory_values) if memory_values else 0.0,
        "duration_s": duration_s,
        "data_received_bytes": data_received_bytes,
        "throughput_mbps": throughput_mbps,
        "samples_sent": sent,
        "samples_received": received,
        "samples_lost": lost,
        "loss_ratio": lost / max(1.0, loss_denominator),
        "delivery_ratio": received / max(1.0, observed_samples),
        "deadline_miss_ratio": deadline_miss_ratio,
        "no_samples": observed_samples == 0,
    }


def parse_many_perf_csv(paths: Iterable[str | Path]) -> list[dict[str, object]]:
    return [parse_perf_csv(path) for path in paths]


def run_perf_command(command: PerfCommand) -> dict[str, object]:
    """Run a planned performance_test command and parse its output CSV."""

    command.logfile.parent.mkdir(parents=True, exist_ok=True)
    env = None
    if command.env:
        import os

        env = os.environ.copy()
        env.update(command.env)
    completed = subprocess.run(
        command.command,
        check=False,
        capture_output=True,
        text=True,
        env=env,
    )
    record: dict[str, object] = {
        "scenario": command.scenario,
        "rmw": command.rmw,
        "component": command.component,
        "logfile": str(command.logfile),
        "returncode": completed.returncode,
        "stdout_tail": _tail(completed.stdout),
        "stderr_tail": _tail(completed.stderr),
        "status": "ok" if completed.returncode == 0 else "failed",
    }
    if command.logfile.exists():
        parsed = parse_perf_csv(command.logfile)
        record.update(parsed)
    return record


def write_perf_records_jsonl(records: Iterable[dict[str, object]], output: str | Path) -> None:
    Path(output).parent.mkdir(parents=True, exist_ok=True)
    with Path(output).open("w", encoding="utf-8") as handle:
        for record in records:
            handle.write(json.dumps(record, sort_keys=True) + "\n")


def read_perf_records_jsonl(path: str | Path) -> list[dict[str, object]]:
    records = []
    with Path(path).open("r", encoding="utf-8") as handle:
        for line in handle:
            if line.strip():
                records.append(json.loads(line))
    return records


def summarize_perf_records(records: Iterable[dict[str, object]]) -> dict[str, object]:
    groups: dict[tuple[str, str, str], list[dict[str, object]]] = {}
    for record in records:
        key = (
            str(record.get("scenario", "")),
            str(record.get("component", "")),
            str(record.get("rmw", "")),
        )
        groups.setdefault(key, []).append(record)

    rows = []
    for (scenario, component, rmw), group in sorted(groups.items()):
        row = {
            "scenario": scenario,
            "component": component,
            "rmw": rmw,
            "runs": len(group),
            "latency_p95_ms_mean": _record_mean(group, "latency_p95_ms"),
            "latency_p99_ms_mean": _record_mean(group, "latency_p99_ms"),
            "jitter_p95_ms_mean": _record_mean(group, "jitter_p95_ms"),
            "loss_ratio_mean": _record_mean(group, "loss_ratio"),
            "deadline_miss_ratio_mean": _record_mean(group, "deadline_miss_ratio"),
            "throughput_mbps_mean": _record_mean(group, "throughput_mbps"),
            "cpu_mean": _record_mean(group, "cpu_mean"),
            "memory_mean": _record_mean(group, "memory_mean"),
            "qoe_score_mean": _record_mean(group, "qoe_score"),
        }
        row["rank_score"] = _rank_score(row)
        rows.append(row)

    ranking = sorted(
        rows,
        key=lambda row: (
            -float(row["rank_score"]),
            float(row["latency_p95_ms_mean"]),
            float(row["loss_ratio_mean"]),
        ),
    )
    return {"groups": rows, "ranking": ranking}


def _apply_qos_flags(command: list[str], qos: str) -> None:
    """Append common performance_test QoS flags when supported by a build.

    performance_test exposes the authoritative option list through `--help`.
    These flags are common across recent versions, but runners should still be
    treated as command plans until validated on the target ROS distribution.
    """

    if "best_effort" in qos:
        command.extend(["--reliability", "BEST_EFFORT"])
    elif "reliable" in qos:
        command.extend(["--reliability", "RELIABLE"])
    if "keep_last" in qos:
        depth = qos.rsplit("_", 1)[-1]
        if depth.isdigit():
            command.extend(["--history", "KEEP_LAST", "--history-depth", depth])


def _read_csv_rows(path: str | Path) -> list[dict[str, str]]:
    with Path(path).open("r", newline="", encoding="utf-8") as handle:
        lines = handle.readlines()

    start = 0
    for index, line in enumerate(lines):
        if line.strip().startswith("T_experiment"):
            start = index
            break
    table_lines = [
        line
        for line in lines[start:]
        if line.strip() and not line.strip().startswith("---")
    ]
    reader = csv.DictReader(table_lines, skipinitialspace=True)
    rows = []
    for row in reader:
        clean = {
            str(key).strip(): str(value).strip()
            for key, value in row.items()
            if key is not None and value is not None
        }
        if clean:
            rows.append(clean)
    return rows


def _numeric_column(rows: list[dict[str, str]], names: list[str]) -> list[float]:
    if not rows:
        return []
    lowered = {key.lower(): key for key in rows[0]}
    for name in names:
        target = name.lower()
        for lowered_key, original in lowered.items():
            if target in lowered_key:
                values = []
                for row in rows:
                    try:
                        value = float(row[original])
                    except (TypeError, ValueError):
                        continue
                    if math.isfinite(value):
                        values.append(value)
                return values
    return []


def _to_ms(value: float, rows: list[dict[str, str]], hints: list[str]) -> float:
    if not rows:
        return value
    header = " ".join(rows[0].keys()).lower()
    if any(f"{hint}_ns" in header or f"{hint} ns" in header for hint in hints):
        return value / 1_000_000.0
    if any(f"{hint}_us" in header or f"{hint} us" in header for hint in hints):
        return value / 1_000.0
    return value


def _last_or_zero(values: list[float]) -> float:
    return values[-1] if values else 0.0


def _count_total(values: list[float], rows: list[dict[str, str]]) -> float:
    if not values:
        return 0.0
    if _looks_like_performance_test_rows(rows):
        return sum(values)
    return values[-1]


def _looks_like_performance_test_rows(rows: list[dict[str, str]]) -> bool:
    return bool(rows) and any(key.strip() == "T_loop" for key in rows[0])


def _pairwise_abs_delta(values: list[float]) -> list[float]:
    return [abs(right - left) for left, right in zip(values, values[1:])]


def _deadline_miss_ratio(rows: list[dict[str, str]], deadline_ms: float | None) -> float:
    if not rows or deadline_ms is None:
        return 0.0
    total = 0.0
    missed = 0.0
    for row in rows:
        received = _float_or_zero(_row_value(row, "received"))
        lost = _float_or_zero(_row_value(row, "lost"))
        latency = _float_or_zero(_row_value(row, "latency_mean"))
        weight = received + lost
        total += weight
        missed += lost
        if latency > deadline_ms:
            missed += received
    return missed / max(1.0, total)


def _row_value(row: dict[str, str], needle: str) -> str | None:
    needle = needle.lower()
    for key, value in row.items():
        if needle in key.lower():
            return value
    return None


def _float_or_zero(value: str | None) -> float:
    if value is None:
        return 0.0
    try:
        parsed = float(value)
    except ValueError:
        return 0.0
    return parsed if math.isfinite(parsed) else 0.0


def _record_mean(records: list[dict[str, object]], key: str) -> float:
    values = []
    for record in records:
        value = record.get(key)
        if isinstance(value, (int, float)) and math.isfinite(float(value)):
            values.append(float(value))
    return mean(values) if values else 0.0


def _rank_score(row: dict[str, object]) -> float:
    qoe = float(row.get("qoe_score_mean", 0.0))
    latency_penalty = min(1.0, float(row.get("latency_p95_ms_mean", 0.0)) / 500.0)
    loss_penalty = min(1.0, float(row.get("loss_ratio_mean", 0.0)))
    deadline_penalty = min(1.0, float(row.get("deadline_miss_ratio_mean", 0.0)))
    return max(0.0, qoe - 0.15 * latency_penalty - 0.25 * loss_penalty - 0.25 * deadline_penalty)


def percentile(values: list[float], pct: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    index = max(0, min(len(ordered) - 1, math.ceil((pct / 100.0) * len(ordered)) - 1))
    return ordered[index]


def _quote(value: str) -> str:
    if not value:
        return "''"
    if any(char.isspace() or char in "'\"" for char in value):
        return "'" + value.replace("'", "'\"'\"'") + "'"
    return value


def _tail(text: str, lines: int = 20) -> str:
    parts = text.splitlines()
    return "\n".join(parts[-lines:])

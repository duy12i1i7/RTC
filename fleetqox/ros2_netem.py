"""Planning helpers for ROS 2 performance_test over Docker/netem."""

from __future__ import annotations

import json
import shlex
from dataclasses import dataclass
from pathlib import Path

from .testbed import ExperimentScenario


@dataclass(frozen=True)
class Ros2NetemPlan:
    scenario: str
    rmw: str
    component: str
    run_label: str | None
    topology: str
    result_log: Path
    subscriber_command: str
    publisher_command: str
    rate_hz: float
    runtime_s: float
    deadline_ms: float
    env: dict[str, str]


def build_ros2_netem_plan(
    scenario: ExperimentScenario,
    *,
    rmw: str,
    component: str = "control",
    results_dir: str | Path = "results_t2e_ros2",
    run_label: str | None = None,
    runtime_s: float | int | None = None,
    rate_hz: float | int | None = None,
    msg: str | None = None,
    qos: str | None = None,
    zenoh_topology: str = "auto",
) -> Ros2NetemPlan:
    """Build subscriber/publisher commands for a T2E ROS/netem run."""

    config = scenario.config
    if run_label:
        result_log = Path(results_dir) / scenario.name / rmw / component / f"{run_label}.csv"
    else:
        result_log = Path(results_dir) / scenario.name / rmw / f"{component}.csv"
    result_log.parent.mkdir(parents=True, exist_ok=True)

    msg_value = str(msg or config.get("performance_msg", _msg_for_component(component)))
    rate_value = float(rate_hz if rate_hz is not None else config.get("rate_hz", _rate_for_component(component)))
    runtime_value = float(runtime_s if runtime_s is not None else config.get("runtime_s", 30))
    qos_value = str(qos or config.get("qos", _qos_for_component(component)))
    deadline_ms = float(config.get("deadline_ms", _deadline_for_component(component, rate_value)))
    topology = _resolve_topology(rmw, zenoh_topology)
    topic = f"/fleetqox_netem/{scenario.name}/{component}"

    base = [
        "ros2",
        "run",
        "performance_test",
        "perf_test",
        "--communicator",
        "rclcpp-single-threaded-executor",
        "--msg",
        msg_value,
        "--rate",
        _format_number(rate_value),
        "--topic",
        topic,
        "--max-runtime",
        _format_number(runtime_value),
    ]
    _apply_qos_flags(base, qos_value)

    subscriber = base + [
        "--num-sub-threads",
        "1",
        "--num-pub-threads",
        "0",
        "--logfile",
        str(result_log),
    ]
    publisher = base + [
        "--num-sub-threads",
        "0",
        "--num-pub-threads",
        "1",
    ]

    metadata = {
        "suite": "fleetqox",
        "tier": "T2E",
        "scenario": scenario.name,
        "rmw": rmw,
        "component": component,
        "topology": topology,
        "rate_hz": _format_number(rate_value),
        "runtime_s": _format_number(runtime_value),
        "deadline_ms": _format_number(deadline_ms),
    }
    if run_label:
        metadata["run_label"] = run_label
    return Ros2NetemPlan(
        scenario=scenario.name,
        rmw=rmw,
        component=component,
        run_label=run_label,
        topology=topology,
        result_log=result_log,
        subscriber_command=_shell(subscriber),
        publisher_command=_shell(publisher),
        rate_hz=rate_value,
        runtime_s=runtime_value,
        deadline_ms=deadline_ms,
        env={
            "RMW_IMPLEMENTATION": rmw,
            "ROS_DOMAIN_ID": str(config.get("ros_domain_id", 81)),
            "NETEM_DELAY_MS": str(config.get("delay_ms", 20)),
            "NETEM_JITTER_MS": str(config.get("jitter_ms", 5)),
            "NETEM_LOSS_PERCENT": str(config.get("loss_percent", 1)),
            "NETEM_RATE_MBIT": str(config.get("rate_mbit", 20)),
            "SUBSCRIBER_WARMUP_S": str(config.get("subscriber_warmup_s", 2)),
            "PERF_SUB_COMMAND": _shell(subscriber),
            "PERF_PUB_COMMAND": _shell(publisher),
            "APEX_PERFORMANCE_TEST_SUB": json.dumps({**metadata, "role": "subscriber"}, sort_keys=True),
            "APEX_PERFORMANCE_TEST_PUB": json.dumps({**metadata, "role": "publisher"}, sort_keys=True),
            **_topology_env(topology),
        },
    )


def _msg_for_component(component: str) -> str:
    return "Array1m" if component in {"sensor", "video"} else "Array1k"


def _rate_for_component(component: str) -> int:
    return {
        "control": 50,
        "state": 20,
        "sensor": 10,
        "debug": 5,
    }.get(component, 50)


def _qos_for_component(component: str) -> str:
    if component in {"sensor", "debug", "video"}:
        return "best_effort_keep_last_1"
    if component == "state":
        return "reliable_keep_last_3"
    return "reliable_keep_last_1"


def _deadline_for_component(component: str, rate_hz: float) -> float:
    period_ms = 1000.0 / max(rate_hz, 0.001)
    if component == "control":
        return period_ms
    if component == "state":
        return period_ms * 2.0
    if component in {"sensor", "video"}:
        return period_ms * 3.0
    return period_ms * 5.0


def _resolve_topology(rmw: str, zenoh_topology: str) -> str:
    if rmw != "rmw_zenoh_cpp":
        return "dds_bridge"
    if zenoh_topology == "peer":
        return "zenoh_peer"
    return "zenoh_router"


def _topology_env(topology: str) -> dict[str, str]:
    if topology != "zenoh_router":
        return {}
    return {
        "ZENOH_SESSION_CONFIG_URI": "/work/external/ros2-netem/zenoh/session-router.json5",
    }


def _apply_qos_flags(command: list[str], qos: str) -> None:
    if "best_effort" in qos:
        command.extend(["--reliability", "BEST_EFFORT"])
    elif "reliable" in qos:
        command.extend(["--reliability", "RELIABLE"])
    if "keep_last" in qos:
        depth = qos.rsplit("_", 1)[-1]
        if depth.isdigit():
            command.extend(["--history", "KEEP_LAST", "--history-depth", depth])


def _shell(parts: list[str]) -> str:
    return " ".join(shlex.quote(part) for part in parts)


def _format_number(value: float) -> str:
    return str(int(value)) if value.is_integer() else str(value)

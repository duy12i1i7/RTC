"""Run the ROS 2 live-bridge integration harness in Docker."""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
from collections import Counter
from copy import copy
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping

from fleetqox.sidecar_repeated import (
    summarize_repeated_sidecar_metrics,
    write_repeated_markdown_report,
    write_repeated_summary_json,
)
from fleetqox.sidecar_metrics import (
    analyze_sidecar_runtime,
    analyze_sidecar_runtime_by_robot,
    per_robot_budget_report,
    write_sidecar_metrics_jsonl,
)
from fleetqox.sidecar_runtime import SIDECAR_POLICIES
from scripts.apply_netem_transition import parse_transition_schedule
from scripts.run_sidecar_repeated_netem import NETEM_PROFILES


COMPOSE_FILE = Path("external/ros2-live-bridge/docker-compose.yml")
ZENOH_COMPOSE_FILE = Path("external/ros2-live-bridge/docker-compose.zenoh.yml")
DEFAULT_MATRIX_RMWS = ("rmw_fastrtps_cpp", "rmw_cyclonedds_cpp", "rmw_zenoh_cpp")
SOURCE_METADATA_FIELDS = ("publisher_gid", "sequence_number", "source_timestamp_ns", "received_timestamp_ns")


@dataclass(frozen=True)
class Ros2LiveRepeatedRun:
    scenario: str
    seed: int
    profile: str | None = None


@dataclass(frozen=True)
class Ros2LiveTransitionBindingRun:
    scenario: str
    seed: int
    binding_mode: str
    binding_profile: str | None = None

    @property
    def binding_label(self) -> str:
        if self.binding_mode == "static" and self.binding_profile:
            return f"static_{self.binding_profile}"
        return self.binding_mode


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--run", action="store_true")
    parser.add_argument("--analyze", action="store_true")
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--scenario", default="ros2_live_bridge_v1")
    parser.add_argument("--policy", choices=SIDECAR_POLICIES, default="fleetqox_semantic_contract_adaptive")
    parser.add_argument("--bridge-config", type=Path, default=Path("experiments/ros2_live_bridge_tb4_v1.json"))
    parser.add_argument("--output-dir", type=Path, default=Path("results_ros2_live_bridge"))
    parser.add_argument("--ros-domain-id", type=int, default=91)
    parser.add_argument("--rmw", default="rmw_fastrtps_cpp")
    parser.add_argument("--rmw-matrix", help="Comma-separated RMW implementations to run as a metadata matrix")
    parser.add_argument("--all-rmws", action="store_true", help="Run the live bridge metadata matrix over the default RMW set")
    parser.add_argument("--stop-on-error", action="store_true", help="Stop matrix execution on the first failed RMW")
    parser.add_argument("--seconds", type=float, default=2.0)
    parser.add_argument("--rate-hz", type=float, default=20.0)
    parser.add_argument(
        "--robot-count",
        type=int,
        default=1,
        help="Number of robot topic namespaces to publish and bridge in the live Docker workload.",
    )
    parser.add_argument("--per-robot-min-control-delivery", type=float, default=0.90)
    parser.add_argument("--per-robot-max-deadline-miss", type=float, default=0.35)
    parser.add_argument("--per-robot-min-rx-fairness", type=float, default=0.90)
    parser.add_argument("--per-robot-min-control-delivery-fairness", type=float, default=0.95)
    parser.add_argument("--per-robot-min-deadline-success-fairness", type=float, default=0.95)
    parser.add_argument("--transport-volatility-probe-max-per-tick", type=int)
    parser.add_argument("--transport-volatility-probe-quota-scale", type=float)
    parser.add_argument("--transport-volatility-probe-max-per-robot-per-tick", type=int)
    parser.add_argument(
        "--control-lease-adaptive-redundancy",
        choices=("auto", "on", "off"),
        default="auto",
    )
    parser.add_argument("--control-lease-adaptive-max-redundancy", type=int)
    parser.add_argument("--control-lease-adaptive-extra-max-per-tick", type=int)
    parser.add_argument("--control-lease-adaptive-extra-quota-scale", type=float)
    parser.add_argument("--control-lease-residual-loss-budget", type=float)
    parser.add_argument("--control-lease-drain-grace-s", type=float)
    parser.add_argument("--control-lease-terminal-replay-attempts", type=int)
    parser.add_argument("--control-lease-terminal-replay-interval-s", type=float)
    parser.add_argument("--control-lease-terminal-replay-history-per-robot", type=int)
    parser.add_argument("--control-lease-ack-retransmit", choices=("on", "off"), default="off")
    parser.add_argument("--control-lease-ack-retransmit-max-attempts", type=int)
    parser.add_argument("--control-lease-ack-retransmit-max-per-tick", type=int)
    parser.add_argument("--control-lease-ack-retransmit-timeout-ms", type=float)
    parser.add_argument("--control-lease-ack-retransmit-horizon-ms", type=float)
    parser.add_argument("--control-lease-ack-history-per-robot", type=int)
    parser.add_argument("--control-lease-transition-guard", choices=("on", "off"), default="on")
    parser.add_argument("--control-lease-transition-guard-min-confidence", type=float)
    parser.add_argument("--control-lease-transition-guard-min-margin", type=float)
    parser.add_argument("--control-lease-transition-guard-max-dwell-ticks", type=int)
    parser.add_argument("--control-lease-transition-guard-redundancy", type=int)
    parser.add_argument("--seeds", help="Comma-separated publisher workload seeds for repeated live-bridge runs")
    parser.add_argument("--bridge-max-batches", type=int, default=20)
    parser.add_argument("--bridge-start-delay-s", type=float, default=2.0)
    parser.add_argument("--publisher-start-delay-s", type=float, default=5.0)
    parser.add_argument("--delay-ms", type=float, default=80.0)
    parser.add_argument("--jitter-ms", type=float, default=25.0)
    parser.add_argument("--loss-percent", type=float, default=3.0)
    parser.add_argument("--rate-mbit", type=float, default=5.0)
    parser.add_argument(
        "--profile",
        action="append",
        choices=sorted(NETEM_PROFILES),
        help="Run one or more named netem profiles; implies repeated mode when used.",
    )
    parser.add_argument(
        "--transition-profile",
        action="append",
        choices=sorted(NETEM_PROFILES),
        help="Apply multiple named netem profiles inside one continuous live-bridge run.",
    )
    parser.add_argument(
        "--transition-segment-s",
        type=float,
        default=3.0,
        help="Seconds between --transition-profile changes.",
    )
    parser.add_argument(
        "--transition-schedule",
        help="Explicit transition schedule such as wifi@0,wan@3,roaming@6.",
    )
    parser.add_argument(
        "--transition-binding-matrix",
        action="store_true",
        help="Run adaptive binding plus static profile baselines on the same transition workload.",
    )
    parser.add_argument(
        "--dynamic-objective-transition-matrix",
        action="store_true",
        help=(
            "Run repeated live profile transitions with a timed binding "
            "objective schedule and summarize objective/policy switch evidence."
        ),
    )
    parser.add_argument(
        "--transition-binding-profile",
        action="append",
        choices=sorted(NETEM_PROFILES),
        dest="transition_binding_profiles",
        help="Static binding profile to include in --transition-binding-matrix; defaults to transition profiles.",
    )
    parser.add_argument(
        "--binding-objective-summary",
        action="append",
        help=(
            "Additional objective selector summary as objective:path. "
            "Used by live transport_binding objective_schedule."
        ),
    )
    parser.add_argument(
        "--binding-objective-schedule",
        help=(
            "Timed live binding objective schedule such as "
            "balanced_safety_utility@0,autonomy_safety@2."
        ),
    )
    parser.add_argument("--quality-gate-identity-mode", choices=("signature", "payload", "wrapper"), default="wrapper")
    parser.add_argument("--quality-message-mode", choices=("typed", "string"), default="typed")
    parser.add_argument("--projection-quality-message-mode", choices=("typed", "string"), default="typed")
    parser.add_argument("--projection-quality-delivery-mode", choices=("sideband", "wrapper", "both"), default="wrapper")
    parser.add_argument("--projection-quality-payload-mode", choices=("compact", "full"), default="compact")
    parser.add_argument("--egress-feedback", action="store_true")
    parser.add_argument("--egress-feedback-every-packets", type=int, default=12)
    parser.add_argument("--egress-feedback-control-lease-ack-immediate", action="store_true")
    parser.add_argument("--egress-feedback-control-lease-ack-window-events", type=int, default=0)
    parser.add_argument("--egress-feedback-control-lease-ack-adaptive", action="store_true")
    parser.add_argument("--egress-feedback-control-lease-ack-adaptive-min-events", type=int, default=8)
    parser.add_argument("--egress-feedback-control-lease-ack-adaptive-max-events", type=int, default=48)
    parser.add_argument("--egress-feedback-control-lease-ack-adaptive-success-step", type=int, default=1)
    parser.add_argument("--egress-feedback-control-lease-ack-adaptive-failure-multiplier", type=float, default=2.0)
    parser.add_argument("--egress-feedback-control-lease-ack-adaptive-max-age-ms", type=float, default=120.0)
    parser.add_argument(
        "--egress-feedback-control-lease-ack-adaptive-no-piggyback-first",
        action="store_false",
        dest="egress_feedback_control_lease_ack_adaptive_piggyback_first",
        default=True,
    )
    parser.add_argument("--local-feedback", action="store_true")
    parser.add_argument("--local-feedback-every-decisions", type=int, default=12)
    parser.add_argument("--quality-feedback", action="store_true")
    parser.add_argument("--quality-feedback-every-decisions", type=int, default=12)
    parser.add_argument("--packet-format", choices=("event_json", "data_frame"), default="event_json")
    parser.add_argument(
        "--packet-format-matrix",
        action="store_true",
        help="Run both legacy event_json and fleetrmw.data_frame packet formats",
    )
    parser.add_argument("--base-image", default=os.environ.get("ROS2_LIVE_BASE_IMAGE", "ros:jazzy-ros-base"))
    parser.add_argument(
        "--repeated-summary-json",
        type=Path,
        default=Path("results_ros2_live_bridge/repeated_packet_format_rmw_summary.json"),
    )
    parser.add_argument(
        "--repeated-markdown",
        type=Path,
        default=Path("results_ros2_live_bridge/repeated_packet_format_rmw_report.md"),
    )
    parser.add_argument(
        "--transition-summary-json",
        type=Path,
        default=Path("results_ros2_live_bridge/profile_transition_binding_matrix_summary.json"),
    )
    parser.add_argument(
        "--transition-markdown",
        type=Path,
        default=Path("results_ros2_live_bridge/profile_transition_binding_matrix_report.md"),
    )
    parser.add_argument("--title", default="ROS 2 Packet-Format/RMW Repeated Matrix")
    parser.add_argument(
        "--report",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Write repeated summary JSON and Markdown when repeated mode is used.",
    )
    args = parser.parse_args()

    probe = probe_docker()
    args.output_dir.mkdir(parents=True, exist_ok=True)
    rmws = resolve_rmws(args)
    packet_formats = resolve_packet_formats(args)
    if args.transition_binding_matrix:
        suite = run_transition_binding_matrix(args, probe, rmws, packet_formats)
        if args.json:
            print(json.dumps(suite, sort_keys=True))
        else:
            print_transition_binding_human(suite)
        return
    if args.dynamic_objective_transition_matrix:
        suite = run_dynamic_objective_transition_matrix(
            args,
            probe,
            rmws,
            packet_formats,
        )
        if args.json:
            print(json.dumps(suite, sort_keys=True))
        else:
            print_dynamic_objective_transition_human(suite)
        return
    seeds = resolve_seeds(args)
    if seeds:
        suite = run_repeated(args, probe, rmws, packet_formats, seeds)
        if args.json:
            print(json.dumps(suite, sort_keys=True))
        else:
            print_repeated_human(suite)
        return
    if len(rmws) > 1 or len(packet_formats) > 1:
        suite = run_matrix(args, probe, rmws, packet_formats)
        if args.json:
            print(json.dumps(suite, sort_keys=True))
        else:
            print_matrix_human(suite)
        return

    record = run_one(args, probe=probe, scenario=args.scenario, rmw=rmws[0], ros_domain_id=args.ros_domain_id)
    if args.json:
        print(json.dumps(record, sort_keys=True))
    else:
        print_human(record)


def resolve_rmws(args: argparse.Namespace) -> list[str]:
    if args.all_rmws:
        return list(DEFAULT_MATRIX_RMWS)
    if args.rmw_matrix:
        return [part.strip() for part in args.rmw_matrix.split(",") if part.strip()]
    return [args.rmw]


def resolve_packet_formats(args: argparse.Namespace) -> list[str]:
    if args.packet_format_matrix:
        return ["event_json", "data_frame"]
    return [args.packet_format]


def resolve_seeds(args: argparse.Namespace) -> list[int]:
    if args.seeds:
        return parse_ints(args.seeds, "--seeds")
    if args.profile:
        return [7]
    return []


def parse_ints(value: str, option: str) -> list[int]:
    try:
        parsed = [int(part.strip()) for part in value.split(",") if part.strip()]
    except ValueError as exc:
        raise SystemExit(f"{option} must be a comma-separated integer list") from exc
    if not parsed or any(item < 0 for item in parsed):
        raise SystemExit(f"{option} must contain non-negative integers")
    return parsed


def run_repeated(
    args: argparse.Namespace,
    probe: dict[str, object],
    rmws: list[str],
    packet_formats: list[str],
    seeds: list[int],
) -> dict[str, object]:
    plans = build_repeated_plan(args.scenario, seeds, args.profile)
    run_suites = []
    records = []
    width = max(1, len(rmws) * len(packet_formats))
    stopped = False
    for index, plan in enumerate(plans):
        per_args = copy(args)
        per_args.scenario = plan.scenario
        per_args.seed = plan.seed
        per_args.profile_label = plan.profile
        per_args.ros_domain_id = args.ros_domain_id + index * width
        apply_netem_profile(per_args, plan.profile)
        suite = run_matrix(per_args, probe, rmws, packet_formats)
        suite["seed"] = plan.seed
        suite["profile"] = plan.profile or "custom"
        run_suites.append(suite)
        records.extend(suite["records"])
        if args.stop_on_error and any(record.get("status") == "failed" for record in suite["records"]):
            stopped = True
            break

    repeated_summary = summarize_repeated_packet_format_records(records)
    if repeated_summary and args.profile:
        repeated_summary["profiles"] = summarize_repeated_profiles(records, args.profile)
    report_paths = write_repeated_report_if_requested(args, repeated_summary, records)
    return {
        "kind": "ros2_live_bridge_repeated_packet_format_rmw_matrix",
        "scenario": args.scenario,
        "rmws": rmws,
        "packet_formats": packet_formats,
        "seeds": seeds,
        "profiles": args.profile or ["custom"],
        "runs": len(run_suites),
        "stopped": stopped,
        "run_suites": run_suites,
        "records": records,
        "metadata_matrix": metadata_matrix(records),
        "packet_format_comparison": packet_format_comparison(records),
        "repeated_summary": repeated_summary,
        "status_counts": dict(sorted(Counter(str(record.get("status", "")) for record in records).items())),
        "probe": probe,
        **report_paths,
    }


def build_repeated_plan(
    scenario_prefix: str,
    seeds: list[int],
    profiles: list[str] | None = None,
) -> list[Ros2LiveRepeatedRun]:
    plans = []
    if not profiles:
        for seed in seeds:
            plans.append(Ros2LiveRepeatedRun(scenario=f"{scenario_prefix}_seed_{seed}", seed=seed))
        return plans
    for profile in profiles:
        if profile not in NETEM_PROFILES:
            raise SystemExit(f"unknown --profile: {profile}")
        for seed in seeds:
            plans.append(
                Ros2LiveRepeatedRun(
                    scenario=f"{scenario_prefix}_{profile}_seed_{seed}",
                    seed=seed,
                    profile=profile,
                )
            )
    return plans


def build_transition_binding_plan(
    scenario_prefix: str,
    seeds: list[int],
    static_profiles: list[str],
) -> list[Ros2LiveTransitionBindingRun]:
    plans: list[Ros2LiveTransitionBindingRun] = []
    multi_seed = len(seeds) > 1
    for seed in seeds:
        seed_prefix = f"{scenario_prefix}_seed_{seed}" if multi_seed else scenario_prefix
        plans.append(
            Ros2LiveTransitionBindingRun(
                scenario=f"{seed_prefix}_adaptive",
                seed=seed,
                binding_mode="adaptive",
            )
        )
        for profile in static_profiles:
            if profile not in NETEM_PROFILES:
                raise SystemExit(f"unknown --transition-binding-profile: {profile}")
            plans.append(
                Ros2LiveTransitionBindingRun(
                    scenario=f"{seed_prefix}_static_{profile}",
                    seed=seed,
                    binding_mode="static",
                    binding_profile=profile,
                )
            )
    return plans


def resolve_transition_binding_profiles(args: argparse.Namespace) -> list[str]:
    profiles = list(
        getattr(args, "transition_binding_profiles", None)
        or args.transition_profile
        or ["wifi", "wan", "roaming"]
    )
    unique_profiles = list(dict.fromkeys(profiles))
    unknown = [profile for profile in unique_profiles if profile not in NETEM_PROFILES]
    if unknown:
        raise SystemExit(
            "--transition-binding-profile contains unknown profile(s): "
            + ", ".join(unknown)
        )
    return unique_profiles


def apply_netem_profile(args: argparse.Namespace, profile: str | None) -> None:
    if profile is None:
        return
    config = NETEM_PROFILES[profile].as_config()
    args.delay_ms = float(config["delay_ms"])
    args.jitter_ms = float(config["jitter_ms"])
    args.loss_percent = float(config["loss_percent"])
    args.rate_mbit = float(config["rate_mbit"])


def transition_schedule_for_args(args: argparse.Namespace):
    if args.transition_schedule:
        return parse_transition_schedule(args.transition_schedule)
    profiles = list(args.transition_profile or [])
    if not profiles:
        return []
    if args.transition_segment_s <= 0:
        raise SystemExit("--transition-segment-s must be positive")
    return parse_transition_schedule(
        ",".join(
            f"{profile}@{index * args.transition_segment_s:g}"
            for index, profile in enumerate(profiles)
        )
    )


def binding_objective_summaries_for_args(args: argparse.Namespace) -> dict[str, str]:
    values = getattr(args, "binding_objective_summary", None) or []
    summaries: dict[str, str] = {}
    for value in values:
        if ":" not in value:
            raise SystemExit(
                "--binding-objective-summary must use objective:path syntax"
            )
        objective, path = value.split(":", 1)
        objective = objective.strip()
        path = path.strip()
        if not objective or not path:
            raise SystemExit(
                "--binding-objective-summary must use objective:path syntax"
            )
        summaries[objective] = path
    return summaries


def binding_objective_schedule_for_args(args: argparse.Namespace) -> list[dict[str, object]]:
    value = getattr(args, "binding_objective_schedule", None)
    if not value:
        return []
    rows = []
    for part in value.split(","):
        item = part.strip()
        if not item:
            continue
        if "@" not in item:
            raise SystemExit(
                "--binding-objective-schedule must use objective@seconds syntax"
            )
        objective, at_s = item.rsplit("@", 1)
        objective = objective.strip()
        if not objective:
            raise SystemExit(
                "--binding-objective-schedule objective must be non-empty"
            )
        try:
            scheduled_at = float(at_s)
        except ValueError as exc:
            raise SystemExit(
                "--binding-objective-schedule times must be numeric seconds"
            ) from exc
        if scheduled_at < 0:
            raise SystemExit("--binding-objective-schedule times must be non-negative")
        rows.append({"objective": objective, "at_s": scheduled_at})
    rows.sort(key=lambda row: float(row["at_s"]))
    return rows


def schedule_string_for_transitions(transitions: list[object]) -> str:
    return ",".join(
        f"{transition.profile}@{transition.at_s:g}"  # type: ignore[attr-defined]
        for transition in transitions
    )


def write_transition_bridge_config(
    base_config: Path,
    output_config: Path,
    transitions: list[object],
    *,
    binding_profile: str | None = None,
    objective_summaries: Mapping[str, str] | None = None,
    objective_schedule: list[dict[str, object]] | None = None,
    robot_count: int = 1,
) -> Path:
    with base_config.open("r", encoding="utf-8") as handle:
        payload = json.load(handle)
    if robot_count <= 0:
        raise ValueError("robot_count must be positive")
    if robot_count > 1:
        payload["topics"] = expand_bridge_topics_for_robots(
            payload.get("topics", []),
            robot_count=robot_count,
        )
        payload["robot_count"] = robot_count
    binding_payload = payload.get("transport_binding", {})
    if binding_profile or objective_summaries or objective_schedule:
        if not isinstance(binding_payload, Mapping):
            raise ValueError("base transport_binding must be an object")
        summary = binding_payload.get("summary", binding_payload.get("summary_json"))
        if summary is None or summary == "":
            raise ValueError("base transport_binding.summary is required")
        updated_binding = dict(binding_payload)
        updated_binding["summary"] = str(summary)
        if binding_profile:
            updated_binding = {
                "summary": str(summary),
                "profile": binding_profile,
            }
        if objective_summaries:
            updated_binding["objective_summaries"] = dict(objective_summaries)
        if objective_schedule:
            updated_binding["objective_schedule"] = list(objective_schedule)
        payload["transport_binding"] = updated_binding
    link_schedule = [
        link_schedule_payload_for_profile(
            transition.profile,  # type: ignore[attr-defined]
            at_s=float(transition.at_s),  # type: ignore[attr-defined]
        )
        for transition in transitions
    ]
    if link_schedule:
        payload["link"] = {
            key: value
            for key, value in link_schedule[0].items()
            if key
            in {
                "capacity_bytes_per_tick",
                "rtt_ms",
                "jitter_ms",
                "loss",
            }
        }
    payload["link_schedule"] = link_schedule
    output_config.parent.mkdir(parents=True, exist_ok=True)
    output_config.write_text(
        json.dumps(payload, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    return output_config


def expand_bridge_topics_for_robots(
    topics: object,
    *,
    robot_count: int,
) -> list[dict[str, object]]:
    if not isinstance(topics, list):
        raise ValueError("topics must be a list")
    expanded = []
    for robot_index in range(robot_count):
        robot_id = robot_id_for_index(robot_index)
        for item in topics:
            if not isinstance(item, Mapping):
                continue
            expanded.append(_replace_robot_token(item, robot_id))
    return expanded


def robot_id_for_index(index: int) -> str:
    if index < 0:
        raise ValueError("robot index must be non-negative")
    return f"robot_{index:04d}"


def _replace_robot_token(value: object, robot_id: str) -> object:
    if isinstance(value, str):
        return value.replace("robot_0000", robot_id)
    if isinstance(value, Mapping):
        return {
            str(key): _replace_robot_token(item, robot_id)
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [_replace_robot_token(item, robot_id) for item in value]
    return value


def link_schedule_payload_for_profile(profile: str, *, at_s: float) -> dict[str, object]:
    config = NETEM_PROFILES[profile].as_config()
    return {
        "at_s": at_s,
        "profile": profile,
        "capacity_bytes_per_tick": int(
            round(float(config["capacity_bytes_per_second"]) / 50.0)
        ),
        "rtt_ms": float(config["delay_ms"]) * 2.0,
        "jitter_ms": float(config["jitter_ms"]),
        "loss": float(config["loss_percent"]) / 100.0,
    }


def run_matrix(
    args: argparse.Namespace,
    probe: dict[str, object],
    rmws: list[str],
    packet_formats: list[str],
) -> dict[str, object]:
    records = []
    index = 0
    multi_rmw = len(rmws) > 1
    multi_format = len(packet_formats) > 1
    stopped = False
    for packet_format in packet_formats:
        for rmw in rmws:
            tokens = []
            if multi_format:
                tokens.append(_scenario_token(packet_format))
            if multi_rmw:
                tokens.append(_scenario_token(rmw))
            scenario = "_".join([args.scenario, *tokens]) if tokens else args.scenario
            per_args = copy(args)
            per_args.packet_format = packet_format
            record = run_one(
                per_args,
                probe=probe,
                scenario=scenario,
                rmw=rmw,
                ros_domain_id=args.ros_domain_id + index,
            )
            records.append(record)
            index += 1
            if args.stop_on_error and record.get("status") == "failed":
                stopped = True
                break
        if stopped:
            break
    return {
        "kind": "ros2_live_bridge_rmw_metadata_matrix",
        "scenario": args.scenario,
        "rmws": rmws,
        "packet_formats": packet_formats,
        "records": records,
        "metadata_matrix": metadata_matrix(records),
        "packet_format_comparison": packet_format_comparison(records),
        "status_counts": dict(sorted(Counter(str(record.get("status", "")) for record in records).items())),
        "probe": probe,
    }


def run_transition_binding_matrix(
    args: argparse.Namespace,
    probe: dict[str, object],
    rmws: list[str],
    packet_formats: list[str],
) -> dict[str, object]:
    transition_schedule = transition_schedule_for_args(args)
    if not transition_schedule:
        raise SystemExit(
            "--transition-binding-matrix requires --transition-profile or --transition-schedule"
        )
    seeds = parse_ints(args.seeds, "--seeds") if args.seeds else [7]
    static_profiles = resolve_transition_binding_profiles(args)
    plans = build_transition_binding_plan(args.scenario, seeds, static_profiles)
    records = []
    planned_runs = len(rmws) * len(packet_formats) * len(plans)
    stopped = False
    index = 0
    multi_rmw = len(rmws) > 1
    multi_format = len(packet_formats) > 1
    for seed in seeds:
        seed_plans = [plan for plan in plans if plan.seed == seed]
        for packet_format in packet_formats:
            for rmw in rmws:
                for plan in seed_plans:
                    tokens = []
                    if multi_format:
                        tokens.append(_scenario_token(packet_format))
                    if multi_rmw:
                        tokens.append(_scenario_token(rmw))
                    scenario = "_".join([plan.scenario, *tokens]) if tokens else plan.scenario
                    per_args = copy(args)
                    per_args.packet_format = packet_format
                    per_args.seed = seed
                    per_args.transition_binding_mode = plan.binding_mode
                    per_args.transition_binding_profile_override = plan.binding_profile
                    per_args.transition_binding_label = plan.binding_label
                    record = run_one(
                        per_args,
                        probe=probe,
                        scenario=scenario,
                        rmw=rmw,
                        ros_domain_id=args.ros_domain_id + index,
                    )
                    records.append(record)
                    index += 1
                    if args.stop_on_error and record.get("status") == "failed":
                        stopped = True
                        break
                if stopped:
                    break
            if stopped:
                break
        if stopped:
            break

    summary = transition_binding_matrix_summary(
        records,
        transitions=transition_schedule,
        static_profiles=static_profiles,
    )
    report_paths = write_transition_binding_report_if_requested(args, summary, records)
    return {
        "kind": "ros2_live_bridge_transition_binding_matrix",
        "scenario": args.scenario,
        "rmws": rmws,
        "packet_formats": packet_formats,
        "seeds": seeds,
        "static_profiles": static_profiles,
        "transition_schedule": [
            transition.as_payload() for transition in transition_schedule
        ],
        "runs": len(records),
        "planned_runs": planned_runs,
        "stopped": stopped,
        "records": records,
        "transition_binding_comparison": transition_binding_comparison(records),
        "transition_binding_summary": summary,
        "status_counts": dict(sorted(Counter(str(record.get("status", "")) for record in records).items())),
        "probe": probe,
        **report_paths,
    }


def run_dynamic_objective_transition_matrix(
    args: argparse.Namespace,
    probe: dict[str, object],
    rmws: list[str],
    packet_formats: list[str],
) -> dict[str, object]:
    transition_schedule = transition_schedule_for_args(args)
    if not transition_schedule:
        raise SystemExit(
            "--dynamic-objective-transition-matrix requires "
            "--transition-profile or --transition-schedule"
        )
    objective_schedule = binding_objective_schedule_for_args(args)
    if not objective_schedule:
        raise SystemExit(
            "--dynamic-objective-transition-matrix requires "
            "--binding-objective-schedule"
        )
    seeds = parse_ints(args.seeds, "--seeds") if args.seeds else [7]
    records = []
    planned_runs = len(rmws) * len(packet_formats) * len(seeds)
    stopped = False
    index = 0
    multi_seed = len(seeds) > 1
    multi_rmw = len(rmws) > 1
    multi_format = len(packet_formats) > 1
    for seed in seeds:
        seed_prefix = f"{args.scenario}_seed_{seed}" if multi_seed else args.scenario
        for packet_format in packet_formats:
            for rmw in rmws:
                tokens = []
                if multi_format:
                    tokens.append(_scenario_token(packet_format))
                if multi_rmw:
                    tokens.append(_scenario_token(rmw))
                scenario = "_".join([seed_prefix, *tokens]) if tokens else seed_prefix
                per_args = copy(args)
                per_args.packet_format = packet_format
                per_args.seed = seed
                record = run_one(
                    per_args,
                    probe=probe,
                    scenario=scenario,
                    rmw=rmw,
                    ros_domain_id=args.ros_domain_id + index,
                )
                records.append(record)
                index += 1
                if args.stop_on_error and record.get("status") == "failed":
                    stopped = True
                    break
            if stopped:
                break
        if stopped:
            break

    summary = dynamic_objective_transition_summary(
        records,
        transitions=transition_schedule,
        objective_schedule=objective_schedule,
    )
    report_paths = write_dynamic_objective_transition_report_if_requested(
        args,
        summary,
        records,
    )
    return {
        "kind": "ros2_live_bridge_dynamic_objective_transition_matrix",
        "scenario": args.scenario,
        "rmws": rmws,
        "packet_formats": packet_formats,
        "seeds": seeds,
        "transition_schedule": [
            transition.as_payload() for transition in transition_schedule
        ],
        "binding_objective_schedule": list(objective_schedule),
        "binding_objective_summaries": binding_objective_summaries_for_args(args),
        "runs": len(records),
        "planned_runs": planned_runs,
        "stopped": stopped,
        "records": records,
        "dynamic_objective_comparison": dynamic_objective_transition_comparison(records),
        "dynamic_objective_summary": summary,
        "status_counts": dict(sorted(Counter(str(record.get("status", "")) for record in records).items())),
        "probe": probe,
        **report_paths,
    }


def run_one(
    args: argparse.Namespace,
    *,
    probe: dict[str, object],
    scenario: str,
    rmw: str,
    ros_domain_id: int,
) -> dict[str, object]:
    transition_schedule = transition_schedule_for_args(args)
    objective_summaries = binding_objective_summaries_for_args(args)
    objective_schedule = binding_objective_schedule_for_args(args)
    robot_count = int(getattr(args, "robot_count", 1))
    bridge_config = args.bridge_config
    netem_transition_log = args.output_dir / f"{scenario}_netem_transition.jsonl"
    if transition_schedule or objective_summaries or objective_schedule or robot_count > 1:
        bridge_config = write_transition_bridge_config(
            args.bridge_config,
            args.output_dir / f"{scenario}_bridge_transition_config.json",
            transition_schedule,
            binding_profile=getattr(args, "transition_binding_profile_override", None),
            objective_summaries=objective_summaries,
            objective_schedule=objective_schedule,
            robot_count=robot_count,
        )
    decisions = args.output_dir / f"{scenario}_decisions.jsonl"
    received = args.output_dir / f"{scenario}_received.jsonl"
    egress_publications = args.output_dir / f"{scenario}_egress_publications.jsonl"
    egress_monitor = args.output_dir / f"{scenario}_egress_monitor.jsonl"
    lease_decisions = args.output_dir / f"{scenario}_lease_decisions.jsonl"
    quality_gate_decisions = args.output_dir / f"{scenario}_quality_gate_decisions.jsonl"
    metrics = args.output_dir / f"{scenario}_metrics.jsonl"
    record: dict[str, object] = {
        "scenario": scenario,
        "status": "ready" if probe["docker_ready"] else "missing_tool",
        "reason": probe["reason"],
        "probe": probe,
        "policy": args.policy,
        "rmw": rmw,
        "ros_domain_id": ros_domain_id,
        "bridge_config": str(bridge_config),
        "quality_gate_identity_mode": args.quality_gate_identity_mode,
        "quality_message_mode": args.quality_message_mode,
        "projection_quality_message_mode": args.projection_quality_message_mode,
        "projection_quality_delivery_mode": args.projection_quality_delivery_mode,
        "projection_quality_payload_mode": args.projection_quality_payload_mode,
        "packet_format": args.packet_format,
        "seed": int(getattr(args, "seed", 7)),
        "robot_count": robot_count,
        "start_delays": {
            "bridge_start_delay_s": args.bridge_start_delay_s,
            "publisher_start_delay_s": args.publisher_start_delay_s,
            "netem_transition_start_delay_s": args.publisher_start_delay_s,
        },
        "per_robot_budget": {
            "min_control_delivery_ratio": args.per_robot_min_control_delivery,
            "max_deadline_miss_ratio": args.per_robot_max_deadline_miss,
            "min_rx_jain_index": args.per_robot_min_rx_fairness,
            "min_control_delivery_jain_index": args.per_robot_min_control_delivery_fairness,
            "min_deadline_success_jain_index": args.per_robot_min_deadline_success_fairness,
        },
        "transport_volatility_probe": {
            "max_per_tick": args.transport_volatility_probe_max_per_tick,
            "quota_scale": args.transport_volatility_probe_quota_scale,
            "max_per_robot_per_tick": (
                args.transport_volatility_probe_max_per_robot_per_tick
            ),
        },
        "profile": str(getattr(args, "profile_label", "custom") or "custom"),
        "netem": {
            "delay_ms": args.delay_ms,
            "jitter_ms": args.jitter_ms,
            "loss_percent": args.loss_percent,
            "rate_mbit": args.rate_mbit,
        },
        "decisions": str(decisions),
        "received": str(received),
        "egress_publications": str(egress_publications),
        "egress_monitor": str(egress_monitor),
        "lease_decisions": str(lease_decisions),
        "quality_gate_decisions": str(quality_gate_decisions),
        "metrics": str(metrics),
    }
    binding_mode = str(getattr(args, "transition_binding_mode", ""))
    if binding_mode:
        binding_profile = getattr(args, "transition_binding_profile_override", None)
        record["binding_mode"] = binding_mode
        record["binding_profile"] = str(binding_profile or binding_mode)
        record["binding_label"] = str(getattr(args, "transition_binding_label", binding_mode))
    if transition_schedule:
        record["transition_schedule"] = [
            transition.as_payload() for transition in transition_schedule
        ]
        record["netem_transition_log"] = str(netem_transition_log)
    if objective_summaries:
        record["binding_objective_summaries"] = dict(objective_summaries)
    if objective_schedule:
        record["binding_objective_schedule"] = list(objective_schedule)

    if args.run:
        if not probe["docker_ready"]:
            record["status"] = "missing_tool"
        else:
            compose_args = copy(args)
            compose_args.bridge_config = bridge_config
            compose_args.netem_transition_schedule = schedule_string_for_transitions(
                transition_schedule
            )
            compose_args.netem_transition_log = netem_transition_log
            try:
                run_compose(
                    compose_args,
                    decisions,
                    received,
                    egress_publications,
                    egress_monitor,
                    lease_decisions,
                    quality_gate_decisions,
                    rmw=rmw,
                    ros_domain_id=ros_domain_id,
                )
                record["status"] = "ran"
            except subprocess.CalledProcessError as exc:
                record["status"] = "failed"
                record["reason"] = f"docker compose failed with exit code {exc.returncode}"
    if args.analyze and decisions.exists() and received.exists():
        metric_records = analyze_sidecar_runtime(decisions, received)
        for item in metric_records:
            item["scenario"] = scenario
        write_sidecar_metrics_jsonl(metric_records, metrics)
        record["summary"] = metric_records
        per_robot_qos = analyze_sidecar_runtime_by_robot(decisions, received)
        record["per_robot_qos_summary"] = per_robot_qos
        record["per_robot_budget_report"] = per_robot_budget_report(
            per_robot_qos,
            min_control_delivery_ratio=args.per_robot_min_control_delivery,
            max_deadline_miss_ratio=args.per_robot_max_deadline_miss,
            min_rx_jain_index=args.per_robot_min_rx_fairness,
            min_control_delivery_jain_index=args.per_robot_min_control_delivery_fairness,
            min_deadline_success_jain_index=args.per_robot_min_deadline_success_fairness,
        )
        record["action_counts"] = action_counts(decisions)
        record["wire_mode_counts"] = wire_mode_counts(decisions)
        record["transport_binding_transition_summary"] = (
            transport_binding_transition_summary(decisions)
        )
        record["decision_packet_source_metadata_counts"] = nested_field_presence_counts(
            decisions,
            "source_metadata",
            SOURCE_METADATA_FIELDS,
            event_type="packet",
        )
        record["decision_packet_source_metadata_summary"] = source_metadata_summary(decisions)
        record["decision_robot_coverage"] = robot_coverage_summary(decisions)
        record["received_robot_coverage"] = robot_coverage_summary(received)
        if egress_publications.exists():
            record["egress_publication_counts"] = field_counts(egress_publications, "kind")
            record["egress_publication_msg_type_counts"] = field_counts(egress_publications, "msg_type")
            record["egress_publication_topic_counts"] = field_counts(egress_publications, "topic")
            record["egress_robot_coverage"] = robot_coverage_summary(
                egress_publications
            )
        if egress_monitor.exists():
            record["egress_monitor_counts"] = field_counts(egress_monitor, "kind")
            record["egress_monitor_msg_type_counts"] = field_counts(egress_monitor, "msg_type")
            record["egress_monitor_topic_counts"] = field_counts(egress_monitor, "topic")
            record["egress_monitor_robot_coverage"] = robot_coverage_summary(egress_monitor)
        if lease_decisions.exists():
            record["lease_status_counts"] = field_counts(lease_decisions, "status")
            record["lease_event_type_counts"] = field_counts(lease_decisions, "event_type")
            record["lease_robot_coverage"] = robot_coverage_summary(lease_decisions)
        if quality_gate_decisions.exists():
            record["quality_gate_status_counts"] = field_counts(quality_gate_decisions, "status")
            record["quality_gate_projection_counts"] = field_counts(quality_gate_decisions, "projection_kind")
            record["quality_gate_fidelity_counts"] = field_counts(quality_gate_decisions, "fidelity_class")
            record["quality_gate_identity_mode_counts"] = field_counts(quality_gate_decisions, "projection_identity_mode")
            record["quality_gate_message_mode_counts"] = field_counts(quality_gate_decisions, "quality_message_mode")
            record["quality_gate_signature_match_counts"] = field_counts(quality_gate_decisions, "projection_signature_match")
            record["quality_gate_payload_present_counts"] = field_counts(quality_gate_decisions, "projection_payload_present")
            record["quality_gate_contract_id_counts"] = field_counts(quality_gate_decisions, "contract_id")
            record["quality_gate_source_sample_id_counts"] = field_counts(quality_gate_decisions, "source_sample_id")
            record["quality_gate_identity_match_summary"] = quality_gate_identity_match_summary(
                decisions,
                quality_gate_decisions,
            )
            record["quality_gate_robot_coverage"] = robot_coverage_summary(quality_gate_decisions)
        if netem_transition_log.exists():
            record["netem_transition_summary"] = netem_transition_summary(
                netem_transition_log
            )
    elif args.analyze:
        record["analysis_status"] = "missing_logs"
        if args.run:
            record["status"] = "failed"
            record["reason"] = "docker compose completed without decision/received logs"
    elif transition_schedule and netem_transition_log.exists():
        record["netem_transition_summary"] = netem_transition_summary(netem_transition_log)
    return record


def probe_docker() -> dict[str, object]:
    docker = shutil.which("docker")
    if not docker:
        return {"docker": None, "docker_ready": False, "compose_ready": False, "reason": "docker command not found"}
    compose = subprocess.run([docker, "compose", "version"], check=False, capture_output=True, text=True)
    info = subprocess.run([docker, "info", "--format", "{{.ServerVersion}}"], check=False, capture_output=True, text=True)
    ready = info.returncode == 0 and bool(info.stdout.strip())
    return {
        "docker": docker,
        "docker_ready": ready,
        "compose_ready": compose.returncode == 0,
        "compose_version": compose.stdout.strip(),
        "server_version": info.stdout.strip(),
        "reason": "docker daemon ready" if ready else (info.stderr.strip() or "docker daemon not available"),
    }


def _optional_env_value(value: object) -> str:
    return "" if value is None else str(value)


def run_compose(
    args: argparse.Namespace,
    decisions: Path,
    received: Path,
    egress_publications: Path,
    egress_monitor: Path,
    lease_decisions: Path,
    quality_gate_decisions: Path,
    *,
    rmw: str,
    ros_domain_id: int,
) -> None:
    if not COMPOSE_FILE.exists():
        raise SystemExit(f"missing compose file: {COMPOSE_FILE}")
    env = os.environ.copy()
    env.update(
        {
            "ROS2_LIVE_BASE_IMAGE": args.base_image,
            "ROS_DOMAIN_ID": str(ros_domain_id),
            "RMW_IMPLEMENTATION": rmw,
            "SIDECAR_POLICY": args.policy,
            "SIDECAR_PACKET_FORMAT": args.packet_format,
            "SIDECAR_TRANSPORT_VOLATILITY_PROBE_MAX_PER_TICK": _optional_env_value(
                args.transport_volatility_probe_max_per_tick
            ),
            "SIDECAR_TRANSPORT_VOLATILITY_PROBE_QUOTA_SCALE": _optional_env_value(
                args.transport_volatility_probe_quota_scale
            ),
            "SIDECAR_TRANSPORT_VOLATILITY_PROBE_MAX_PER_ROBOT_PER_TICK": _optional_env_value(
                args.transport_volatility_probe_max_per_robot_per_tick
            ),
            "SIDECAR_CONTROL_LEASE_ADAPTIVE_REDUNDANCY": args.control_lease_adaptive_redundancy,
            "SIDECAR_CONTROL_LEASE_ADAPTIVE_MAX_REDUNDANCY": _optional_env_value(
                args.control_lease_adaptive_max_redundancy
            ),
            "SIDECAR_CONTROL_LEASE_ADAPTIVE_EXTRA_MAX_PER_TICK": _optional_env_value(
                args.control_lease_adaptive_extra_max_per_tick
            ),
            "SIDECAR_CONTROL_LEASE_ADAPTIVE_EXTRA_QUOTA_SCALE": _optional_env_value(
                args.control_lease_adaptive_extra_quota_scale
            ),
            "SIDECAR_CONTROL_LEASE_RESIDUAL_LOSS_BUDGET": _optional_env_value(
                args.control_lease_residual_loss_budget
            ),
            "SIDECAR_CONTROL_LEASE_DRAIN_GRACE_S": _optional_env_value(
                args.control_lease_drain_grace_s
            ),
            "SIDECAR_CONTROL_LEASE_TERMINAL_REPLAY_ATTEMPTS": _optional_env_value(
                args.control_lease_terminal_replay_attempts
            ),
            "SIDECAR_CONTROL_LEASE_TERMINAL_REPLAY_INTERVAL_S": _optional_env_value(
                args.control_lease_terminal_replay_interval_s
            ),
            "SIDECAR_CONTROL_LEASE_TERMINAL_REPLAY_HISTORY_PER_ROBOT": _optional_env_value(
                args.control_lease_terminal_replay_history_per_robot
            ),
            "SIDECAR_CONTROL_LEASE_ACK_RETRANSMIT": args.control_lease_ack_retransmit,
            "SIDECAR_CONTROL_LEASE_ACK_RETRANSMIT_MAX_ATTEMPTS": _optional_env_value(
                args.control_lease_ack_retransmit_max_attempts
            ),
            "SIDECAR_CONTROL_LEASE_ACK_RETRANSMIT_MAX_PER_TICK": _optional_env_value(
                args.control_lease_ack_retransmit_max_per_tick
            ),
            "SIDECAR_CONTROL_LEASE_ACK_RETRANSMIT_TIMEOUT_MS": _optional_env_value(
                args.control_lease_ack_retransmit_timeout_ms
            ),
            "SIDECAR_CONTROL_LEASE_ACK_RETRANSMIT_HORIZON_MS": _optional_env_value(
                args.control_lease_ack_retransmit_horizon_ms
            ),
            "SIDECAR_CONTROL_LEASE_ACK_HISTORY_PER_ROBOT": _optional_env_value(
                args.control_lease_ack_history_per_robot
            ),
            "SIDECAR_CONTROL_LEASE_TRANSITION_GUARD": args.control_lease_transition_guard,
            "SIDECAR_CONTROL_LEASE_TRANSITION_GUARD_MIN_CONFIDENCE": _optional_env_value(
                args.control_lease_transition_guard_min_confidence
            ),
            "SIDECAR_CONTROL_LEASE_TRANSITION_GUARD_MIN_MARGIN": _optional_env_value(
                args.control_lease_transition_guard_min_margin
            ),
            "SIDECAR_CONTROL_LEASE_TRANSITION_GUARD_MAX_DWELL_TICKS": _optional_env_value(
                args.control_lease_transition_guard_max_dwell_ticks
            ),
            "SIDECAR_CONTROL_LEASE_TRANSITION_GUARD_REDUNDANCY": _optional_env_value(
                args.control_lease_transition_guard_redundancy
            ),
            "BRIDGE_CONFIG": str(args.bridge_config),
            "DECISION_FILE": str(decisions),
            "RESULT_FILE": str(received),
            "EGRESS_PUBLICATION_FILE": str(egress_publications),
            "EGRESS_MONITOR_FILE": str(egress_monitor),
            "LEASE_DECISION_FILE": str(lease_decisions),
            "QUALITY_GATE_DECISION_FILE": str(quality_gate_decisions),
            "QUALITY_GATE_IDENTITY_MODE": args.quality_gate_identity_mode,
            "QUALITY_GATE_MESSAGE_MODE": args.quality_message_mode,
            "PROJECTION_QUALITY_MESSAGE_MODE": args.projection_quality_message_mode,
            "PROJECTION_QUALITY_DELIVERY_MODE": args.projection_quality_delivery_mode,
            "PROJECTION_QUALITY_PAYLOAD_MODE": args.projection_quality_payload_mode,
            "EGRESS_FEEDBACK_SIDECAR_HOST": "sidecar" if args.egress_feedback else "",
            "EGRESS_FEEDBACK_SIDECAR_PORT": "8765",
            "EGRESS_FEEDBACK_EVERY_PACKETS": str(args.egress_feedback_every_packets),
            "EGRESS_FEEDBACK_CONTROL_LEASE_ACK_IMMEDIATE_FLAG": (
                "--feedback-control-lease-ack-immediate"
                if args.egress_feedback_control_lease_ack_immediate
                else ""
            ),
            "EGRESS_FEEDBACK_CONTROL_LEASE_ACK_WINDOW_EVENTS": str(
                args.egress_feedback_control_lease_ack_window_events
            ),
            "EGRESS_FEEDBACK_CONTROL_LEASE_ACK_ADAPTIVE_FLAG": (
                "--feedback-control-lease-ack-adaptive"
                if args.egress_feedback_control_lease_ack_adaptive
                else ""
            ),
            "EGRESS_FEEDBACK_CONTROL_LEASE_ACK_ADAPTIVE_MIN_EVENTS": str(
                args.egress_feedback_control_lease_ack_adaptive_min_events
            ),
            "EGRESS_FEEDBACK_CONTROL_LEASE_ACK_ADAPTIVE_MAX_EVENTS": str(
                args.egress_feedback_control_lease_ack_adaptive_max_events
            ),
            "EGRESS_FEEDBACK_CONTROL_LEASE_ACK_ADAPTIVE_SUCCESS_STEP": str(
                args.egress_feedback_control_lease_ack_adaptive_success_step
            ),
            "EGRESS_FEEDBACK_CONTROL_LEASE_ACK_ADAPTIVE_FAILURE_MULTIPLIER": str(
                args.egress_feedback_control_lease_ack_adaptive_failure_multiplier
            ),
            "EGRESS_FEEDBACK_CONTROL_LEASE_ACK_ADAPTIVE_MAX_AGE_MS": str(
                args.egress_feedback_control_lease_ack_adaptive_max_age_ms
            ),
            "EGRESS_FEEDBACK_CONTROL_LEASE_ACK_ADAPTIVE_NO_PIGGYBACK_FIRST_FLAG": (
                ""
                if args.egress_feedback_control_lease_ack_adaptive_piggyback_first
                else "--feedback-control-lease-ack-adaptive-no-piggyback-first"
            ),
            "LOCAL_FEEDBACK_SIDECAR_HOST": "sidecar" if args.local_feedback else "",
            "LOCAL_FEEDBACK_SIDECAR_PORT": "8765",
            "LOCAL_FEEDBACK_EVERY_DECISIONS": str(args.local_feedback_every_decisions),
            "QUALITY_FEEDBACK_SIDECAR_HOST": "sidecar" if args.quality_feedback else "",
            "QUALITY_FEEDBACK_SIDECAR_PORT": "8765",
            "QUALITY_FEEDBACK_EVERY_DECISIONS": str(args.quality_feedback_every_decisions),
            "ROS2_TEST_SECONDS": str(args.seconds),
            "ROS2_TEST_RATE_HZ": str(args.rate_hz),
            "ROS2_TEST_SEED": str(int(getattr(args, "seed", 7))),
            "ROS2_TEST_ROBOT_COUNT": str(int(getattr(args, "robot_count", 1))),
            "BRIDGE_MAX_BATCHES": str(args.bridge_max_batches),
            "BRIDGE_START_DELAY_S": str(args.bridge_start_delay_s),
            "PUBLISHER_START_DELAY_S": str(args.publisher_start_delay_s),
            "NETEM_TRANSITION_START_DELAY_S": str(args.publisher_start_delay_s),
            "ZENOH_ROUTER_MAX_RUNTIME_S": str(max(45.0, args.seconds + 20.0)),
            "NETEM_DELAY_MS": str(args.delay_ms),
            "NETEM_JITTER_MS": str(args.jitter_ms),
            "NETEM_LOSS_PERCENT": str(args.loss_percent),
            "NETEM_RATE_MBIT": str(args.rate_mbit),
        }
    )
    transition_schedule = getattr(args, "netem_transition_schedule", "")
    if transition_schedule:
        env["NETEM_TRANSITION_SCHEDULE"] = str(transition_schedule)
        env["NETEM_TRANSITION_LOG"] = str(
            getattr(args, "netem_transition_log", "results_ros2_live_bridge/netem_transition.jsonl")
        )
    if args.base_image.startswith("ros:") and not env.get("ROS2_LIVE_PLATFORM"):
        env["ROS2_LIVE_PLATFORM"] = "linux/amd64"
    compose_args = compose_files_for_rmw(rmw)
    try:
        subprocess.run(
            ["docker", "compose", *compose_args, "up", "--build", "--remove-orphans"],
            env=env,
            cwd=Path.cwd(),
            check=True,
        )
    finally:
        subprocess.run(
            ["docker", "compose", *compose_args, "down", "--remove-orphans", "--volumes"],
            env=env,
            cwd=Path.cwd(),
            check=False,
        )


def compose_files_for_rmw(rmw: str) -> list[str]:
    args = ["-f", str(COMPOSE_FILE)]
    if rmw == "rmw_zenoh_cpp":
        args.extend(["-f", str(ZENOH_COMPOSE_FILE)])
    return args


def action_counts(path: Path) -> dict[str, int]:
    counts: Counter[str] = Counter()
    for event in _events(path):
        counts[str(event.get("action", ""))] += 1
    return dict(sorted(counts.items()))


def wire_mode_counts(path: Path) -> dict[str, int]:
    counts: Counter[str] = Counter()
    for event in _events(path):
        counts[str(event.get("wire_mode", ""))] += 1
    return dict(sorted(counts.items()))


def field_counts(path: Path, field: str) -> dict[str, int]:
    counts: Counter[str] = Counter()
    for event in _events(path):
        counts[str(event.get(field, ""))] += 1
    return dict(sorted(counts.items()))


def transport_binding_transition_summary(path: Path) -> dict[str, object]:
    tick_rows: dict[int, dict[str, object]] = {}
    rows = 0
    rows_with_binding = 0
    rows_with_estimate = 0
    first_timestamp_ms: float | None = None
    for event in _events(path):
        rows += 1
        binding = event.get("transport_binding")
        estimate = event.get("transport_binding_estimate")
        if isinstance(binding, Mapping):
            rows_with_binding += 1
        if isinstance(estimate, Mapping):
            rows_with_estimate += 1
        if not isinstance(binding, Mapping):
            continue
        tick = int(event.get("tick", len(tick_rows)))
        timestamp_ms = _optional_metric(event, "timestamp_ms")
        if timestamp_ms is not None and first_timestamp_ms is None:
            first_timestamp_ms = timestamp_ms
        elapsed_s = (
            max(0.0, (timestamp_ms - first_timestamp_ms) / 1000.0)
            if timestamp_ms is not None and first_timestamp_ms is not None
            else None
        )
        tick_rows.setdefault(
            tick,
            {
                "tick": tick,
                "timestamp_ms": timestamp_ms if timestamp_ms is not None else 0.0,
                "elapsed_s": elapsed_s if elapsed_s is not None else 0.0,
                "profile": str(binding.get("profile", "")),
                "objective": str(binding.get("objective", "")),
                "policy": str(binding.get("policy", "")),
                "packet_format": str(binding.get("packet_format", "")),
                "estimate_profile": (
                    str(estimate.get("profile", ""))
                    if isinstance(estimate, Mapping)
                    else ""
                ),
                "estimate_candidate_profile": (
                    str(estimate.get("candidate_profile", ""))
                    if isinstance(estimate, Mapping)
                    else ""
                ),
                "estimate_confidence": (
                    float(estimate.get("confidence", 0.0))
                    if isinstance(estimate, Mapping)
                    else 0.0
                ),
            },
        )
    ordered_ticks = [tick_rows[key] for key in sorted(tick_rows)]
    switches = []
    objective_switches = []
    policy_switches = []
    previous: Mapping[str, object] | None = None
    for row in ordered_ticks:
        if previous is not None and row.get("profile") != previous.get("profile"):
            switches.append(
                {
                    "tick": row["tick"],
                    "elapsed_s": row.get("elapsed_s", 0.0),
                    "from_profile": previous.get("profile", ""),
                    "to_profile": row.get("profile", ""),
                    "from_policy": previous.get("policy", ""),
                    "to_policy": row.get("policy", ""),
                }
            )
        if previous is not None and row.get("objective") != previous.get("objective"):
            objective_switches.append(
                {
                    "tick": row["tick"],
                    "elapsed_s": row.get("elapsed_s", 0.0),
                    "from_objective": previous.get("objective", ""),
                    "to_objective": row.get("objective", ""),
                    "profile": row.get("profile", ""),
                    "from_policy": previous.get("policy", ""),
                    "to_policy": row.get("policy", ""),
                }
            )
        if previous is not None and row.get("policy") != previous.get("policy"):
            policy_switches.append(
                {
                    "tick": row["tick"],
                    "elapsed_s": row.get("elapsed_s", 0.0),
                    "from_policy": previous.get("policy", ""),
                    "to_policy": row.get("policy", ""),
                    "from_profile": previous.get("profile", ""),
                    "to_profile": row.get("profile", ""),
                    "from_objective": previous.get("objective", ""),
                    "to_objective": row.get("objective", ""),
                }
            )
        previous = row
    return {
        "rows": rows,
        "rows_with_transport_binding": rows_with_binding,
        "rows_with_transport_binding_estimate": rows_with_estimate,
        "duration_s": (
            float(ordered_ticks[-1].get("elapsed_s", 0.0)) if ordered_ticks else 0.0
        ),
        "ticks": ordered_ticks,
        "switch_count": len(switches),
        "switches": switches,
        "objective_switch_count": len(objective_switches),
        "objective_switches": objective_switches,
        "policy_switch_count": len(policy_switches),
        "policy_switches": policy_switches,
        "profiles": sorted({str(row.get("profile", "")) for row in ordered_ticks if row.get("profile")}),
        "objectives": sorted({str(row.get("objective", "")) for row in ordered_ticks if row.get("objective")}),
        "packet_formats": sorted({str(row.get("packet_format", "")) for row in ordered_ticks if row.get("packet_format")}),
    }


def netem_transition_summary(path: Path) -> dict[str, object]:
    rows = _events(path)
    return {
        "rows": len(rows),
        "profiles": [str(row.get("profile", "")) for row in rows],
        "statuses": dict(sorted(Counter(str(row.get("status", "")) for row in rows).items())),
        "scheduled_at_s": [float(row.get("scheduled_at_s", 0.0)) for row in rows],
    }


def switch_latency_summary(
    transition_summary: Mapping[str, object],
    schedule: object,
) -> dict[str, object]:
    schedule_rows = [
        row for row in _transition_schedule_rows(schedule) if row.get("profile")
    ]
    expected = schedule_rows[1:] if len(schedule_rows) > 1 else []
    switches = [
        row
        for row in transition_summary.get("switches", [])
        if isinstance(row, Mapping)
    ]
    matched = []
    unmatched = []
    used_switch_ids: set[int] = set()
    for expected_row in expected:
        profile = str(expected_row.get("profile", ""))
        expected_at_s = _metric(expected_row, "at_s")
        match_index = None
        for index, switch in enumerate(switches):
            if index in used_switch_ids:
                continue
            if str(switch.get("to_profile", "")) != profile:
                continue
            match_index = index
            break
        if match_index is None:
            matched.append(
                {
                    "profile": profile,
                    "expected_at_s": expected_at_s,
                    "matched": False,
                    "latency_s": None,
                }
            )
            continue
        used_switch_ids.add(match_index)
        switch = switches[match_index]
        switch_elapsed_s = _metric(switch, "elapsed_s")
        matched.append(
            {
                "profile": profile,
                "expected_at_s": expected_at_s,
                "matched": True,
                "tick": int(switch.get("tick", 0)),
                "switch_elapsed_s": switch_elapsed_s,
                "latency_s": switch_elapsed_s - expected_at_s,
                "from_profile": str(switch.get("from_profile", "")),
                "to_profile": str(switch.get("to_profile", "")),
                "from_policy": str(switch.get("from_policy", "")),
                "to_policy": str(switch.get("to_policy", "")),
            }
        )
    for index, switch in enumerate(switches):
        if index not in used_switch_ids:
            unmatched.append(
                {
                    "tick": int(switch.get("tick", 0)),
                    "elapsed_s": _metric(switch, "elapsed_s"),
                    "from_profile": str(switch.get("from_profile", "")),
                    "to_profile": str(switch.get("to_profile", "")),
                    "from_policy": str(switch.get("from_policy", "")),
                    "to_policy": str(switch.get("to_policy", "")),
                }
            )
    latencies = [
        float(row["latency_s"])
        for row in matched
        if row.get("matched") and row.get("latency_s") is not None
    ]
    return {
        "expected_switch_count": len(expected),
        "matched_switch_count": len(latencies),
        "missing_switch_count": sum(1 for row in matched if not row.get("matched")),
        "unmatched_switch_count": len(unmatched),
        "flapping_switch_count": len(unmatched),
        "switch_latencies_s": latencies,
        "mean_switch_latency_s": sum(latencies) / len(latencies) if latencies else 0.0,
        "mean_abs_switch_latency_s": (
            sum(abs(value) for value in latencies) / len(latencies) if latencies else 0.0
        ),
        "max_abs_switch_latency_s": max((abs(value) for value in latencies), default=0.0),
        "matched_switches": matched,
        "unmatched_switches": unmatched,
    }


def objective_switch_latency_summary(
    transition_summary: Mapping[str, object],
    schedule: object,
) -> dict[str, object]:
    schedule_rows = [
        row for row in _objective_schedule_rows(schedule) if row.get("objective")
    ]
    expected = schedule_rows[1:] if len(schedule_rows) > 1 else []
    switches = [
        row
        for row in transition_summary.get("objective_switches", [])
        if isinstance(row, Mapping)
    ]
    matched = []
    unmatched = []
    used_switch_ids: set[int] = set()
    for expected_row in expected:
        objective = str(expected_row.get("objective", ""))
        expected_at_s = _metric(expected_row, "at_s")
        match_index = None
        for index, switch in enumerate(switches):
            if index in used_switch_ids:
                continue
            if str(switch.get("to_objective", "")) != objective:
                continue
            match_index = index
            break
        if match_index is None:
            matched.append(
                {
                    "objective": objective,
                    "expected_at_s": expected_at_s,
                    "matched": False,
                    "latency_s": None,
                }
            )
            continue
        used_switch_ids.add(match_index)
        switch = switches[match_index]
        switch_elapsed_s = _metric(switch, "elapsed_s")
        matched.append(
            {
                "objective": objective,
                "expected_at_s": expected_at_s,
                "matched": True,
                "tick": int(switch.get("tick", 0)),
                "switch_elapsed_s": switch_elapsed_s,
                "latency_s": switch_elapsed_s - expected_at_s,
                "from_objective": str(switch.get("from_objective", "")),
                "to_objective": str(switch.get("to_objective", "")),
                "from_policy": str(switch.get("from_policy", "")),
                "to_policy": str(switch.get("to_policy", "")),
            }
        )
    for index, switch in enumerate(switches):
        if index not in used_switch_ids:
            unmatched.append(
                {
                    "tick": int(switch.get("tick", 0)),
                    "elapsed_s": _metric(switch, "elapsed_s"),
                    "from_objective": str(switch.get("from_objective", "")),
                    "to_objective": str(switch.get("to_objective", "")),
                    "from_policy": str(switch.get("from_policy", "")),
                    "to_policy": str(switch.get("to_policy", "")),
                }
            )
    latencies = [
        float(row["latency_s"])
        for row in matched
        if row.get("matched") and row.get("latency_s") is not None
    ]
    return {
        "expected_objective_switch_count": len(expected),
        "matched_objective_switch_count": len(latencies),
        "missing_objective_switch_count": sum(
            1 for row in matched if not row.get("matched")
        ),
        "unmatched_objective_switch_count": len(unmatched),
        "objective_flapping_switch_count": len(unmatched),
        "objective_switch_latencies_s": latencies,
        "mean_objective_switch_latency_s": (
            sum(latencies) / len(latencies) if latencies else 0.0
        ),
        "mean_abs_objective_switch_latency_s": (
            sum(abs(value) for value in latencies) / len(latencies)
            if latencies
            else 0.0
        ),
        "max_abs_objective_switch_latency_s": max(
            (abs(value) for value in latencies),
            default=0.0,
        ),
        "matched_objective_switches": matched,
        "unmatched_objective_switches": unmatched,
    }


def _transition_schedule_rows(schedule: object) -> list[Mapping[str, object]]:
    rows: list[Mapping[str, object]] = []
    if not isinstance(schedule, list):
        return rows
    for item in schedule:
        if isinstance(item, Mapping):
            rows.append(item)
        elif hasattr(item, "as_payload"):
            payload = item.as_payload()
            if isinstance(payload, Mapping):
                rows.append(payload)
    return rows


def _objective_schedule_rows(schedule: object) -> list[Mapping[str, object]]:
    rows: list[Mapping[str, object]] = []
    if not isinstance(schedule, list):
        return rows
    for item in schedule:
        if isinstance(item, Mapping):
            rows.append(item)
    return rows


def nested_field_presence_counts(
    path: Path,
    parent_field: str,
    fields: tuple[str, ...],
    *,
    event_type: str | None = None,
) -> dict[str, int]:
    counts = {field: 0 for field in fields}
    counts["records_with_metadata"] = 0
    counts["records_without_metadata"] = 0
    for event in _events(path):
        if event_type is not None and event.get("event_type") != event_type:
            continue
        metadata = event.get(parent_field)
        if not isinstance(metadata, Mapping):
            counts["records_without_metadata"] += 1
            continue
        counts["records_with_metadata"] += 1
        for field in fields:
            if metadata.get(field) not in (None, ""):
                counts[field] += 1
    return counts


def source_metadata_summary(path: Path) -> dict[str, object]:
    summary: dict[str, object] = {
        "packet_count": 0,
        "records_with_metadata": 0,
        "records_without_metadata": 0,
        "fields": {field: 0 for field in SOURCE_METADATA_FIELDS},
        "by_topic": {},
        "by_topic_msg_type": {},
    }
    for event in _events(path):
        if event.get("event_type") != "packet":
            continue
        summary["packet_count"] = int(summary["packet_count"]) + 1
        topic = str(event.get("topic", ""))
        msg_type = str(event.get("source_msg_type", ""))
        metadata = event.get("source_metadata")
        if not isinstance(metadata, Mapping):
            summary["records_without_metadata"] = int(summary["records_without_metadata"]) + 1
            _increment_metadata_bucket(summary["by_topic"], topic, None)
            _increment_metadata_bucket(summary["by_topic_msg_type"], _topic_msg_key(topic, msg_type), None)
            continue
        summary["records_with_metadata"] = int(summary["records_with_metadata"]) + 1
        for field in SOURCE_METADATA_FIELDS:
            if metadata.get(field) not in (None, ""):
                fields = summary["fields"]
                assert isinstance(fields, dict)
                fields[field] = int(fields[field]) + 1
        _increment_metadata_bucket(summary["by_topic"], topic, metadata)
        _increment_metadata_bucket(summary["by_topic_msg_type"], _topic_msg_key(topic, msg_type), metadata)
    return summary


def robot_coverage_summary(path: Path) -> dict[str, object]:
    by_robot: dict[str, dict[str, object]] = {}
    event_count = 0
    for event in _events(path):
        event_count += 1
        robot_id = _robot_id_from_event(event)
        if not robot_id:
            continue
        bucket = by_robot.setdefault(
            robot_id,
            {
                "events": 0,
                "packets": 0,
                "flow_classes": {},
                "topics": {},
                "kinds": {},
            },
        )
        bucket["events"] = int(bucket["events"]) + 1
        if event.get("event_type") == "packet" or "event_id" in event:
            bucket["packets"] = int(bucket["packets"]) + 1
        _increment_counter_bucket(bucket["flow_classes"], str(event.get("flow_class", "")))
        _increment_counter_bucket(bucket["topics"], str(event.get("topic", "")))
        _increment_counter_bucket(bucket["kinds"], str(event.get("kind", "")))
    robots = sorted(by_robot)
    return {
        "event_count": event_count,
        "robot_count": len(robots),
        "robots": robots,
        "by_robot": by_robot,
    }


def _robot_id_from_event(event: Mapping[str, object]) -> str:
    robot_id = str(event.get("robot_id", "") or "")
    if robot_id:
        return robot_id
    for key in ("flow_id", "src", "dst", "topic", "source_topic"):
        candidate = _robot_id_from_text(str(event.get(key, "") or ""))
        if candidate:
            return candidate
    return ""


def _robot_id_from_text(value: str) -> str:
    parts = value.replace("/", " ").replace(":", " ").split()
    for part in parts:
        if part.startswith("robot_") and len(part) >= len("robot_0000"):
            return part
    return ""


def _increment_counter_bucket(parent: object, key: str) -> None:
    if not key:
        return
    counts = parent
    assert isinstance(counts, dict)
    counts[key] = int(counts.get(key, 0)) + 1


def _increment_metadata_bucket(parent: object, key: str, metadata: Mapping[str, object] | None) -> None:
    buckets = parent
    assert isinstance(buckets, dict)
    bucket = buckets.setdefault(
        key,
        {
            "packet_count": 0,
            "records_with_metadata": 0,
            "records_without_metadata": 0,
            "fields": {field: 0 for field in SOURCE_METADATA_FIELDS},
        },
    )
    bucket["packet_count"] = int(bucket["packet_count"]) + 1
    if metadata is None:
        bucket["records_without_metadata"] = int(bucket["records_without_metadata"]) + 1
        return
    bucket["records_with_metadata"] = int(bucket["records_with_metadata"]) + 1
    fields = bucket["fields"]
    assert isinstance(fields, dict)
    for field in SOURCE_METADATA_FIELDS:
        if metadata.get(field) not in (None, ""):
            fields[field] = int(fields[field]) + 1


def metadata_matrix(records: list[dict[str, object]]) -> list[dict[str, object]]:
    matrix = []
    for record in records:
        summary = record.get("decision_packet_source_metadata_summary")
        if not isinstance(summary, Mapping):
            matrix.append(
                {
                    "rmw": record.get("rmw", ""),
                    "scenario": record.get("scenario", ""),
                    "status": record.get("status", ""),
                    "packet_count": 0,
                    "records_with_metadata": 0,
                    "publisher_gid": 0,
                    "sequence_number": 0,
                    "source_timestamp_ns": 0,
                    "received_timestamp_ns": 0,
                }
            )
            continue
        fields = summary.get("fields", {})
        field_map = fields if isinstance(fields, Mapping) else {}
        matrix.append(
            {
                "rmw": record.get("rmw", ""),
                "scenario": record.get("scenario", ""),
                "status": record.get("status", ""),
                "packet_count": int(summary.get("packet_count", 0)),
                "records_with_metadata": int(summary.get("records_with_metadata", 0)),
                "publisher_gid": int(field_map.get("publisher_gid", 0)),
                "sequence_number": int(field_map.get("sequence_number", 0)),
                "source_timestamp_ns": int(field_map.get("source_timestamp_ns", 0)),
                "received_timestamp_ns": int(field_map.get("received_timestamp_ns", 0)),
            }
        )
    return matrix


def packet_format_comparison(records: list[dict[str, object]]) -> list[dict[str, object]]:
    rows = []
    for record in records:
        summary_records = record.get("summary", [])
        metrics = summary_records[0] if isinstance(summary_records, list) and summary_records else {}
        metrics_map = metrics if isinstance(metrics, Mapping) else {}
        gate_counts = record.get("quality_gate_status_counts", {})
        gate_map = gate_counts if isinstance(gate_counts, Mapping) else {}
        identity = record.get("quality_gate_identity_match_summary", {})
        identity_map = identity if isinstance(identity, Mapping) else {}
        rows.append(
            {
                "rmw": str(record.get("rmw", "")),
                "packet_format": str(record.get("packet_format", "")),
                "scenario": str(record.get("scenario", "")),
                "status": str(record.get("status", "")),
                "tx": int(metrics_map.get("tx", 0)),
                "rx": int(metrics_map.get("rx", 0)),
                "loss_ratio": float(metrics_map.get("loss_ratio", 0.0)),
                "control_delivery_ratio": float(metrics_map.get("control_delivery_ratio", 0.0)),
                "latency_p95_ms": float(metrics_map.get("latency_p95_ms", 0.0)),
                "quality_gate_accept": int(gate_map.get("accept", 0)),
                "contract_matches": int(identity_map.get("contract_matches", 0)),
                "contract_gate_total": int(identity_map.get("contract_gate_total", 0)),
                "source_matches": int(identity_map.get("source_matches", 0)),
                "source_gate_total": int(identity_map.get("source_gate_total", 0)),
            }
        )
    return rows


def transition_binding_comparison(records: list[dict[str, object]]) -> list[dict[str, object]]:
    rows = []
    for record in records:
        metrics_map = _first_summary_metrics(record)
        transition = record.get("transport_binding_transition_summary", {})
        transition_map = transition if isinstance(transition, Mapping) else {}
        switch_latency = switch_latency_summary(
            transition_map,
            record.get("transition_schedule", []),
        )
        objective_latency = objective_switch_latency_summary(
            transition_map,
            record.get("binding_objective_schedule", []),
        )
        netem = record.get("netem_transition_summary", {})
        netem_map = netem if isinstance(netem, Mapping) else {}
        decision_robot_coverage = _coverage_mapping(record.get("decision_robot_coverage", {}))
        received_robot_coverage = _coverage_mapping(record.get("received_robot_coverage", {}))
        egress_robot_coverage = _coverage_mapping(record.get("egress_robot_coverage", {}))
        lease_robot_coverage = _coverage_mapping(record.get("lease_robot_coverage", {}))
        quality_gate_robot_coverage = _coverage_mapping(record.get("quality_gate_robot_coverage", {}))
        monitor_robot_coverage = _coverage_mapping(record.get("egress_monitor_robot_coverage", {}))
        per_robot_qos = _coverage_mapping(record.get("per_robot_qos_summary", {}))
        per_robot_fairness = _coverage_mapping(per_robot_qos.get("fairness", {}))
        per_robot_budget = _coverage_mapping(record.get("per_robot_budget_report", {}))
        per_robot_budget_pass = bool(per_robot_budget.get("pass", False))
        robot_count = max(1, int(record.get("robot_count", 1)))
        decision_robot_count = int(decision_robot_coverage.get("robot_count", 0))
        received_robot_count = int(received_robot_coverage.get("robot_count", 0))
        egress_robot_count = int(egress_robot_coverage.get("robot_count", 0))
        lease_robot_count = int(lease_robot_coverage.get("robot_count", 0))
        quality_gate_robot_count = int(
            quality_gate_robot_coverage.get("robot_count", 0)
        )
        monitor_robot_count = int(monitor_robot_coverage.get("robot_count", 0))
        rows.append(
            {
                "scenario": str(record.get("scenario", "")),
                "status": str(record.get("status", "")),
                "seed": int(record.get("seed", 0)),
                "robot_count": robot_count,
                "decision_robot_count_observed": decision_robot_count,
                "received_robot_count_observed": received_robot_count,
                "egress_robot_count_observed": egress_robot_count,
                "lease_robot_count_observed": lease_robot_count,
                "quality_gate_robot_count_observed": quality_gate_robot_count,
                "egress_monitor_robot_count_observed": monitor_robot_count,
                "decision_robot_coverage_ratio": _ratio(
                    decision_robot_count,
                    robot_count,
                ),
                "received_robot_coverage_ratio": _ratio(
                    received_robot_count,
                    robot_count,
                ),
                "egress_robot_coverage_ratio": _ratio(
                    egress_robot_count,
                    robot_count,
                ),
                "lease_robot_coverage_ratio": _ratio(
                    lease_robot_count,
                    robot_count,
                ),
                "quality_gate_robot_coverage_ratio": _ratio(
                    quality_gate_robot_count,
                    robot_count,
                ),
                "egress_monitor_robot_coverage_ratio": _ratio(
                    monitor_robot_count,
                    robot_count,
                ),
                "per_robot_budget_pass": per_robot_budget_pass,
                "per_robot_budget_pass_value": 1.0 if per_robot_budget_pass else 0.0,
                "per_robot_rx_jain_index": float(
                    per_robot_fairness.get("rx_jain_index", 0.0)
                ),
                "per_robot_control_delivery_jain_index": float(
                    per_robot_fairness.get("control_delivery_jain_index", 0.0)
                ),
                "per_robot_deadline_success_jain_index": float(
                    per_robot_fairness.get("deadline_success_jain_index", 0.0)
                ),
                "per_robot_min_control_delivery_ratio": float(
                    per_robot_fairness.get("min_control_delivery_ratio", 0.0)
                ),
                "per_robot_max_deadline_miss_ratio": float(
                    per_robot_fairness.get("max_deadline_miss_ratio", 0.0)
                ),
                "per_robot_latency_p95_spread_ms": float(
                    per_robot_fairness.get("latency_p95_spread_ms", 0.0)
                ),
                "per_robot_worst_control_delivery_robot": str(
                    per_robot_fairness.get("worst_control_delivery_robot", "")
                ),
                "per_robot_worst_deadline_miss_robot": str(
                    per_robot_fairness.get("worst_deadline_miss_robot", "")
                ),
                "per_robot_worst_latency_p95_robot": str(
                    per_robot_fairness.get("worst_latency_p95_robot", "")
                ),
                "decision_robots_observed": list(
                    decision_robot_coverage.get("robots", [])
                )
                if isinstance(decision_robot_coverage.get("robots", []), list)
                else [],
                "received_robots_observed": list(
                    received_robot_coverage.get("robots", [])
                )
                if isinstance(received_robot_coverage.get("robots", []), list)
                else [],
                "egress_robots_observed": list(
                    egress_robot_coverage.get("robots", [])
                )
                if isinstance(egress_robot_coverage.get("robots", []), list)
                else [],
                "lease_robots_observed": list(
                    lease_robot_coverage.get("robots", [])
                )
                if isinstance(lease_robot_coverage.get("robots", []), list)
                else [],
                "quality_gate_robots_observed": list(
                    quality_gate_robot_coverage.get("robots", [])
                )
                if isinstance(quality_gate_robot_coverage.get("robots", []), list)
                else [],
                "egress_monitor_robots_observed": list(
                    monitor_robot_coverage.get("robots", [])
                )
                if isinstance(monitor_robot_coverage.get("robots", []), list)
                else [],
                "rmw": str(record.get("rmw", "")),
                "sidecar_policy": str(record.get("policy", "")),
                "packet_format": str(record.get("packet_format", "")),
                "binding_mode": str(record.get("binding_mode", "")),
                "binding_profile": str(record.get("binding_profile", "")),
                "binding_label": str(record.get("binding_label", "")),
                "tx": int(metrics_map.get("tx", 0)),
                "rx": int(metrics_map.get("rx", 0)),
                "loss_ratio": float(metrics_map.get("loss_ratio", 0.0)),
                "control_delivery_ratio": float(metrics_map.get("control_delivery_ratio", 0.0)),
                "control_non_delivery_events": int(metrics_map.get("control_non_delivery_events", 0)),
                "control_starvation_events": int(metrics_map.get("control_starvation_events", 0)),
                "deadline_miss_ratio": float(metrics_map.get("deadline_miss_ratio", 0.0)),
                "semantic_utility_delivered": float(metrics_map.get("semantic_utility_delivered", 0.0)),
                "latency_p95_ms": float(metrics_map.get("latency_p95_ms", 0.0)),
                "latency_p99_ms": float(metrics_map.get("latency_p99_ms", 0.0)),
                "compacted_rx": int(metrics_map.get("compacted_rx", 0)),
                "intent_rx": int(metrics_map.get("intent_rx", 0)),
                "bytes_rx": int(metrics_map.get("bytes_rx", 0)),
                "switch_count": int(transition_map.get("switch_count", 0)),
                "objective_switch_count": int(
                    transition_map.get("objective_switch_count", 0)
                ),
                "policy_switch_count": int(
                    transition_map.get("policy_switch_count", 0)
                ),
                "expected_objective_switch_count": int(
                    objective_latency.get("expected_objective_switch_count", 0)
                ),
                "matched_objective_switch_count": int(
                    objective_latency.get("matched_objective_switch_count", 0)
                ),
                "missing_objective_switch_count": int(
                    objective_latency.get("missing_objective_switch_count", 0)
                ),
                "unmatched_objective_switch_count": int(
                    objective_latency.get("unmatched_objective_switch_count", 0)
                ),
                "objective_flapping_switch_count": int(
                    objective_latency.get("objective_flapping_switch_count", 0)
                ),
                "mean_objective_switch_latency_s": float(
                    objective_latency.get("mean_objective_switch_latency_s", 0.0)
                ),
                "mean_abs_objective_switch_latency_s": float(
                    objective_latency.get("mean_abs_objective_switch_latency_s", 0.0)
                ),
                "max_abs_objective_switch_latency_s": float(
                    objective_latency.get("max_abs_objective_switch_latency_s", 0.0)
                ),
                "objective_switch_latencies_s": list(
                    objective_latency.get("objective_switch_latencies_s", [])
                )
                if isinstance(objective_latency.get("objective_switch_latencies_s", []), list)
                else [],
                "expected_switch_count": int(switch_latency.get("expected_switch_count", 0)),
                "matched_switch_count": int(switch_latency.get("matched_switch_count", 0)),
                "missing_switch_count": int(switch_latency.get("missing_switch_count", 0)),
                "unmatched_switch_count": int(switch_latency.get("unmatched_switch_count", 0)),
                "flapping_switch_count": int(switch_latency.get("flapping_switch_count", 0)),
                "mean_switch_latency_s": float(switch_latency.get("mean_switch_latency_s", 0.0)),
                "mean_abs_switch_latency_s": float(switch_latency.get("mean_abs_switch_latency_s", 0.0)),
                "max_abs_switch_latency_s": float(switch_latency.get("max_abs_switch_latency_s", 0.0)),
                "switch_latencies_s": list(switch_latency.get("switch_latencies_s", []))
                if isinstance(switch_latency.get("switch_latencies_s", []), list)
                else [],
                "binding_rows": int(transition_map.get("rows", 0)),
                "rows_with_transport_binding": int(transition_map.get("rows_with_transport_binding", 0)),
                "rows_with_transport_binding_estimate": int(
                    transition_map.get("rows_with_transport_binding_estimate", 0)
                ),
                "binding_profiles_observed": list(transition_map.get("profiles", []))
                if isinstance(transition_map.get("profiles", []), list)
                else [],
                "binding_objectives_observed": list(transition_map.get("objectives", []))
                if isinstance(transition_map.get("objectives", []), list)
                else [],
                "binding_packet_formats_observed": list(transition_map.get("packet_formats", []))
                if isinstance(transition_map.get("packet_formats", []), list)
                else [],
                "netem_profiles": list(netem_map.get("profiles", []))
                if isinstance(netem_map.get("profiles", []), list)
                else [],
                "netem_statuses": dict(netem_map.get("statuses", {}))
                if isinstance(netem_map.get("statuses", {}), Mapping)
                else {},
            }
        )
    return rows


def transition_binding_matrix_summary(
    records: list[dict[str, object]],
    *,
    transitions: list[object],
    static_profiles: list[str],
) -> dict[str, object]:
    comparison_rows = transition_binding_comparison(records)
    metric_rows = [
        _transition_metric_row(row)
        for row in comparison_rows
        if row.get("status") == "ran" and row.get("binding_label")
    ]
    if not metric_rows:
        return {
            "records": 0,
            "comparison_rows": comparison_rows,
            "policies": [],
            "pareto_frontier": [],
            "adaptive_advantage": [],
            "transition_schedule": [
                transition.as_payload() for transition in transitions
            ],
            "static_profiles": static_profiles,
            "grouping": "transition_binding",
        }
    summary = summarize_repeated_sidecar_metrics(metric_rows)
    summary["grouping"] = "transition_binding"
    summary["comparison_rows"] = comparison_rows
    summary["transition_schedule"] = [
        transition.as_payload() for transition in transitions
    ]
    summary["static_profiles"] = static_profiles
    _augment_transition_policy_summaries(summary, metric_rows)
    summary["adaptive_advantage"] = transition_binding_adaptive_advantage(
        summary,
        static_profiles,
    )
    summary["best_policy"] = transition_binding_best_policy(summary)
    return summary


def dynamic_objective_transition_comparison(records: list[dict[str, object]]) -> list[dict[str, object]]:
    return transition_binding_comparison(records)


def dynamic_objective_transition_summary(
    records: list[dict[str, object]],
    *,
    transitions: list[object],
    objective_schedule: list[dict[str, object]],
) -> dict[str, object]:
    comparison_rows = dynamic_objective_transition_comparison(records)
    metric_rows = [
        _dynamic_objective_metric_row(row)
        for row in comparison_rows
        if row.get("status") == "ran"
    ]
    if not metric_rows:
        return {
            "records": 0,
            "comparison_rows": comparison_rows,
            "policies": [],
            "pareto_frontier": [],
            "transition_schedule": [
                transition.as_payload() for transition in transitions
            ],
            "objective_schedule": list(objective_schedule),
            "grouping": "dynamic_objective_transition",
        }
    summary = summarize_repeated_sidecar_metrics(metric_rows)
    summary["grouping"] = "dynamic_objective_transition"
    summary["comparison_rows"] = comparison_rows
    summary["transition_schedule"] = [
        transition.as_payload() for transition in transitions
    ]
    summary["objective_schedule"] = list(objective_schedule)
    _augment_transition_policy_summaries(summary, metric_rows)
    summary["best_policy"] = transition_binding_best_policy(summary)
    return summary


def _transition_metric_row(row: Mapping[str, object]) -> dict[str, object]:
    metric_row = dict(row)
    metric_row["policy"] = str(row.get("binding_label", ""))
    return metric_row


def _dynamic_objective_metric_row(row: Mapping[str, object]) -> dict[str, object]:
    metric_row = dict(row)
    rmw = str(row.get("rmw", ""))
    sidecar_policy = str(row.get("sidecar_policy", ""))
    parts = ["dynamic_objective"]
    if sidecar_policy:
        parts.append(sidecar_policy)
    if rmw:
        parts.append(rmw)
    metric_row["policy"] = "/".join(parts)
    return metric_row


def _augment_transition_policy_summaries(
    summary: dict[str, object],
    metric_rows: list[dict[str, object]],
) -> None:
    for policy in summary.get("policies", []):
        if not isinstance(policy, dict):
            continue
        label = str(policy.get("policy", ""))
        rows = [row for row in metric_rows if row.get("policy") == label]
        policy["robot_count_mean"] = _mean_metric(rows, "robot_count")
        policy["decision_robot_count_observed_mean"] = _mean_metric(
            rows,
            "decision_robot_count_observed",
        )
        policy["received_robot_count_observed_mean"] = _mean_metric(
            rows,
            "received_robot_count_observed",
        )
        policy["egress_robot_count_observed_mean"] = _mean_metric(
            rows,
            "egress_robot_count_observed",
        )
        policy["lease_robot_count_observed_mean"] = _mean_metric(
            rows,
            "lease_robot_count_observed",
        )
        policy["quality_gate_robot_count_observed_mean"] = _mean_metric(
            rows,
            "quality_gate_robot_count_observed",
        )
        policy["egress_monitor_robot_count_observed_mean"] = _mean_metric(
            rows,
            "egress_monitor_robot_count_observed",
        )
        policy["decision_robot_coverage_ratio_mean"] = _mean_metric(
            rows,
            "decision_robot_coverage_ratio",
        )
        policy["received_robot_coverage_ratio_mean"] = _mean_metric(
            rows,
            "received_robot_coverage_ratio",
        )
        policy["egress_robot_coverage_ratio_mean"] = _mean_metric(
            rows,
            "egress_robot_coverage_ratio",
        )
        policy["lease_robot_coverage_ratio_mean"] = _mean_metric(
            rows,
            "lease_robot_coverage_ratio",
        )
        policy["quality_gate_robot_coverage_ratio_mean"] = _mean_metric(
            rows,
            "quality_gate_robot_coverage_ratio",
        )
        policy["egress_monitor_robot_coverage_ratio_mean"] = _mean_metric(
            rows,
            "egress_monitor_robot_coverage_ratio",
        )
        policy["decision_robots_observed"] = _sorted_union(
            rows,
            "decision_robots_observed",
        )
        policy["received_robots_observed"] = _sorted_union(
            rows,
            "received_robots_observed",
        )
        policy["egress_robots_observed"] = _sorted_union(
            rows,
            "egress_robots_observed",
        )
        policy["lease_robots_observed"] = _sorted_union(
            rows,
            "lease_robots_observed",
        )
        policy["quality_gate_robots_observed"] = _sorted_union(
            rows,
            "quality_gate_robots_observed",
        )
        policy["egress_monitor_robots_observed"] = _sorted_union(
            rows,
            "egress_monitor_robots_observed",
        )
        policy["per_robot_budget_pass_ratio"] = _mean_metric(
            rows,
            "per_robot_budget_pass_value",
        )
        policy["per_robot_rx_jain_index_mean"] = _mean_metric(
            rows,
            "per_robot_rx_jain_index",
        )
        policy["per_robot_control_delivery_jain_index_mean"] = _mean_metric(
            rows,
            "per_robot_control_delivery_jain_index",
        )
        policy["per_robot_deadline_success_jain_index_mean"] = _mean_metric(
            rows,
            "per_robot_deadline_success_jain_index",
        )
        policy["per_robot_min_control_delivery_ratio_mean"] = _mean_metric(
            rows,
            "per_robot_min_control_delivery_ratio",
        )
        policy["per_robot_max_deadline_miss_ratio_mean"] = _mean_metric(
            rows,
            "per_robot_max_deadline_miss_ratio",
        )
        policy["per_robot_latency_p95_spread_ms_mean"] = _mean_metric(
            rows,
            "per_robot_latency_p95_spread_ms",
        )
        policy["switch_count_mean"] = _mean_metric(rows, "switch_count")
        policy["objective_switch_count_mean"] = _mean_metric(
            rows,
            "objective_switch_count",
        )
        policy["expected_objective_switch_count_mean"] = _mean_metric(
            rows,
            "expected_objective_switch_count",
        )
        policy["matched_objective_switch_count_mean"] = _mean_metric(
            rows,
            "matched_objective_switch_count",
        )
        policy["missing_objective_switch_count_mean"] = _mean_metric(
            rows,
            "missing_objective_switch_count",
        )
        policy["objective_flapping_switch_count_mean"] = _mean_metric(
            rows,
            "objective_flapping_switch_count",
        )
        policy["mean_objective_switch_latency_s_mean"] = _mean_metric(
            rows,
            "mean_objective_switch_latency_s",
        )
        policy["mean_abs_objective_switch_latency_s_mean"] = _mean_metric(
            rows,
            "mean_abs_objective_switch_latency_s",
        )
        policy["max_abs_objective_switch_latency_s_mean"] = _mean_metric(
            rows,
            "max_abs_objective_switch_latency_s",
        )
        policy["policy_switch_count_mean"] = _mean_metric(
            rows,
            "policy_switch_count",
        )
        policy["expected_switch_count_mean"] = _mean_metric(rows, "expected_switch_count")
        policy["matched_switch_count_mean"] = _mean_metric(rows, "matched_switch_count")
        policy["missing_switch_count_mean"] = _mean_metric(rows, "missing_switch_count")
        policy["flapping_switch_count_mean"] = _mean_metric(rows, "flapping_switch_count")
        policy["mean_switch_latency_s_mean"] = _mean_metric(rows, "mean_switch_latency_s")
        policy["mean_abs_switch_latency_s_mean"] = _mean_metric(rows, "mean_abs_switch_latency_s")
        policy["max_abs_switch_latency_s_mean"] = _mean_metric(rows, "max_abs_switch_latency_s")
        policy["binding_rows_mean"] = _mean_metric(rows, "binding_rows")
        policy["rows_with_transport_binding_estimate_mean"] = _mean_metric(
            rows,
            "rows_with_transport_binding_estimate",
        )
        policy["binding_profiles_observed"] = _sorted_union(
            rows,
            "binding_profiles_observed",
        )
        policy["binding_objectives_observed"] = _sorted_union(
            rows,
            "binding_objectives_observed",
        )
        policy["binding_packet_formats_observed"] = _sorted_union(
            rows,
            "binding_packet_formats_observed",
        )


def transition_binding_adaptive_advantage(
    summary: Mapping[str, object],
    static_profiles: list[str],
) -> list[dict[str, object]]:
    policies = {
        str(row.get("policy", "")): row
        for row in summary.get("policies", [])
        if isinstance(row, Mapping)
    }
    adaptive = policies.get("adaptive")
    if adaptive is None:
        return []
    rows = []
    for profile in static_profiles:
        static_label = f"static_{profile}"
        static = policies.get(static_label)
        if static is None:
            continue
        rows.append(
            {
                "baseline": static_label,
                "control_delivery_delta": _metric(adaptive, "control_delivery_ratio_mean")
                - _metric(static, "control_delivery_ratio_mean"),
                "loss_ratio_delta": _metric(static, "loss_ratio_mean")
                - _metric(adaptive, "loss_ratio_mean"),
                "deadline_miss_delta": _metric(static, "deadline_miss_ratio_mean")
                - _metric(adaptive, "deadline_miss_ratio_mean"),
                "latency_p95_delta_ms": _metric(static, "latency_p95_ms_mean")
                - _metric(adaptive, "latency_p95_ms_mean"),
                "semantic_utility_delta": _metric(adaptive, "semantic_utility_delivered_mean")
                - _metric(static, "semantic_utility_delivered_mean"),
                "adaptive_switch_count_mean": _metric(adaptive, "switch_count_mean"),
                "baseline_switch_count_mean": _metric(static, "switch_count_mean"),
                "adaptive_mean_abs_switch_latency_s": _metric(
                    adaptive, "mean_abs_switch_latency_s_mean"
                ),
                "baseline_mean_abs_switch_latency_s": _metric(
                    static, "mean_abs_switch_latency_s_mean"
                ),
                "adaptive_flapping_switch_count_mean": _metric(
                    adaptive, "flapping_switch_count_mean"
                ),
                "baseline_flapping_switch_count_mean": _metric(
                    static, "flapping_switch_count_mean"
                ),
            }
        )
    return rows


def transition_binding_best_policy(summary: Mapping[str, object]) -> dict[str, str]:
    policies = [row for row in summary.get("policies", []) if isinstance(row, Mapping)]
    if not policies:
        return {}
    return {
        "control_delivery": str(
            max(policies, key=lambda row: _metric(row, "control_delivery_ratio_mean")).get("policy", "")
        ),
        "loss_ratio": str(
            min(policies, key=lambda row: _metric(row, "loss_ratio_mean")).get("policy", "")
        ),
        "deadline_miss_ratio": str(
            min(policies, key=lambda row: _metric(row, "deadline_miss_ratio_mean")).get("policy", "")
        ),
        "latency_p95_ms": str(
            min(policies, key=lambda row: _metric(row, "latency_p95_ms_mean")).get("policy", "")
        ),
        "semantic_utility_delivered": str(
            max(policies, key=lambda row: _metric(row, "semantic_utility_delivered_mean")).get("policy", "")
        ),
    }


def summarize_repeated_packet_format_records(records: list[dict[str, object]]) -> dict[str, object]:
    metric_rows = repeated_metric_rows(records)
    if not metric_rows:
        return {"records": 0, "policies": [], "pareto_frontier": []}
    summary = summarize_repeated_sidecar_metrics(metric_rows)
    summary["grouping"] = "packet_format/rmw"
    return summary


def repeated_metric_rows(records: list[dict[str, object]]) -> list[dict[str, object]]:
    rows = []
    for record in records:
        if record.get("status") != "ran":
            continue
        summary_records = record.get("summary", [])
        if not isinstance(summary_records, list) or not summary_records:
            continue
        metrics = summary_records[0]
        if not isinstance(metrics, Mapping):
            continue
        row = dict(metrics)
        packet_format = str(record.get("packet_format", ""))
        rmw = str(record.get("rmw", ""))
        row["policy"] = f"{packet_format}/{rmw}"
        row["packet_format"] = packet_format
        row["rmw"] = rmw
        row["scenario"] = str(record.get("scenario", ""))
        row["seed"] = int(record.get("seed", 0))
        row["profile"] = str(record.get("profile", "custom"))
        identity = record.get("quality_gate_identity_match_summary", {})
        identity_map = identity if isinstance(identity, Mapping) else {}
        contract_total = int(identity_map.get("contract_gate_total", 0))
        source_total = int(identity_map.get("source_gate_total", 0))
        row["quality_gate_accept"] = _count_from_mapping(record.get("quality_gate_status_counts", {}), "accept")
        row["contract_match_ratio"] = _ratio(int(identity_map.get("contract_matches", 0)), contract_total)
        row["source_match_ratio"] = _ratio(int(identity_map.get("source_matches", 0)), source_total)
        rows.append(row)
    return rows


def summarize_repeated_profiles(
    records: list[dict[str, object]],
    profiles: list[str],
) -> list[dict[str, object]]:
    metric_rows = repeated_metric_rows(records)
    summaries = []
    for profile in profiles:
        profile_rows = [row for row in metric_rows if row.get("profile") == profile]
        if not profile_rows:
            continue
        summary = summarize_repeated_sidecar_metrics(profile_rows)
        summary["profile"] = profile
        summary["config"] = NETEM_PROFILES[profile].as_config()
        summary["grouping"] = "packet_format/rmw"
        summaries.append(summary)
    return summaries


def write_repeated_report_if_requested(
    args: argparse.Namespace,
    summary: dict[str, object],
    records: list[dict[str, object]],
) -> dict[str, object]:
    if not args.report or not args.run or not records:
        return {}
    if int(summary.get("records", 0)) <= 0:
        return {}
    metric_paths = [
        str(record["metrics"])
        for record in records
        if isinstance(record.get("metrics"), str) and Path(str(record["metrics"])).exists()
    ]
    write_repeated_summary_json(summary, args.repeated_summary_json)
    write_repeated_markdown_report(
        summary,
        args.repeated_markdown,
        title=args.title,
        metrics_paths=metric_paths,
    )
    return {
        "repeated_summary_json": str(args.repeated_summary_json),
        "repeated_markdown": str(args.repeated_markdown),
    }


def write_transition_binding_report_if_requested(
    args: argparse.Namespace,
    summary: dict[str, object],
    records: list[dict[str, object]],
) -> dict[str, object]:
    if not args.report or not args.run or not records:
        return {}
    if int(summary.get("records", 0)) <= 0:
        return {}
    metric_paths = [
        str(record["metrics"])
        for record in records
        if isinstance(record.get("metrics"), str) and Path(str(record["metrics"])).exists()
    ]
    args.transition_summary_json.parent.mkdir(parents=True, exist_ok=True)
    args.transition_summary_json.write_text(
        json.dumps(summary, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    args.transition_markdown.parent.mkdir(parents=True, exist_ok=True)
    args.transition_markdown.write_text(
        render_transition_binding_markdown_report(
            summary,
            title=args.title,
            metrics_paths=metric_paths,
        ),
        encoding="utf-8",
    )
    return {
        "transition_summary_json": str(args.transition_summary_json),
        "transition_markdown": str(args.transition_markdown),
    }


def write_dynamic_objective_transition_report_if_requested(
    args: argparse.Namespace,
    summary: dict[str, object],
    records: list[dict[str, object]],
) -> dict[str, object]:
    if not args.report or not args.run or not records:
        return {}
    if int(summary.get("records", 0)) <= 0:
        return {}
    metric_paths = [
        str(record["metrics"])
        for record in records
        if isinstance(record.get("metrics"), str) and Path(str(record["metrics"])).exists()
    ]
    args.transition_summary_json.parent.mkdir(parents=True, exist_ok=True)
    args.transition_summary_json.write_text(
        json.dumps(summary, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    args.transition_markdown.parent.mkdir(parents=True, exist_ok=True)
    args.transition_markdown.write_text(
        render_dynamic_objective_transition_markdown_report(
            summary,
            title=args.title,
            metrics_paths=metric_paths,
        ),
        encoding="utf-8",
    )
    return {
        "transition_summary_json": str(args.transition_summary_json),
        "transition_markdown": str(args.transition_markdown),
    }


def render_transition_binding_markdown_report(
    summary: Mapping[str, object],
    *,
    title: str,
    metrics_paths: list[str] | tuple[str, ...],
) -> str:
    schedule = [
        row
        for row in summary.get("transition_schedule", [])
        if isinstance(row, Mapping)
    ]
    policies = [
        row
        for row in summary.get("policies", [])
        if isinstance(row, Mapping)
    ]
    advantage_rows = [
        row
        for row in summary.get("adaptive_advantage", [])
        if isinstance(row, Mapping)
    ]
    max_runs = max((int(row.get("runs", 0) or 0) for row in policies), default=0)
    adaptive_row = next((row for row in policies if row.get("policy") == "adaptive"), None)
    lines = [
        f"# {title}",
        "",
        "## Inputs",
        "",
        f"- Metric rows: `{summary.get('records', 0)}`",
        f"- Static baselines: `{', '.join(str(item) for item in summary.get('static_profiles', []))}`",
    ]
    for path in metrics_paths:
        lines.append(f"- Metrics: `{path}`")
    lines.extend(
        [
            "",
            "## Transition Schedule",
            "",
            _markdown_table(
                ["profile", "at s", "rtt ms", "jitter ms", "loss"],
                [
                    [
                        str(row.get("profile", "")),
                        _format_number(row.get("at_s", 0.0)),
                        _format_number(_transition_schedule_rtt_ms(row)),
                        _format_number(_transition_schedule_jitter_ms(row)),
                        _format_number(_transition_schedule_loss(row)),
                    ]
                    for row in schedule
                ],
            ),
            "",
            "## Binding Summary",
            "",
            _markdown_table(
                [
                    "policy",
                    "runs",
                    "robots",
                    "decision robots",
                    "received robots",
                    "egress robots",
                    "lease robots",
                    "gate robots",
                    "monitor robots",
                    "robot budget",
                    "rx fairness",
                    "ctrl fairness",
                    "deadline fairness",
                    "pareto",
                    "rx",
                    "loss",
                    "ctrl delivery",
                    "ctrl non-delivery",
                    "deadline miss",
                    "p95 ms",
                    "switches",
                    "obj switches",
                    "matched",
                    "abs switch s",
                    "flaps",
                    "observed profiles",
                    "objectives",
                    "formats",
                ],
                [
                    [
                        str(row.get("policy", "")),
                        str(row.get("runs", 0)),
                        _format_number(row.get("robot_count_mean", 0.0)),
                        _format_number(row.get("decision_robot_count_observed_mean", 0.0)),
                        _format_number(row.get("received_robot_count_observed_mean", 0.0)),
                        _format_number(row.get("egress_robot_count_observed_mean", 0.0)),
                        _format_number(row.get("lease_robot_count_observed_mean", 0.0)),
                        _format_number(row.get("quality_gate_robot_count_observed_mean", 0.0)),
                        _format_number(row.get("egress_monitor_robot_count_observed_mean", 0.0)),
                        _format_number(row.get("per_robot_budget_pass_ratio", 0.0)),
                        _format_number(row.get("per_robot_rx_jain_index_mean", 0.0)),
                        _format_number(row.get("per_robot_control_delivery_jain_index_mean", 0.0)),
                        _format_number(row.get("per_robot_deadline_success_jain_index_mean", 0.0)),
                        "yes" if row.get("pareto_frontier") else "no",
                        _format_number(row.get("rx_mean", 0.0)),
                        _format_number(row.get("loss_ratio_mean", 0.0)),
                        _format_number(row.get("control_delivery_ratio_mean", 0.0)),
                        _format_number(row.get("control_non_delivery_events_mean", 0.0)),
                        _format_number(row.get("deadline_miss_ratio_mean", 0.0)),
                        _format_number(row.get("latency_p95_ms_mean", 0.0)),
                        _format_number(row.get("switch_count_mean", 0.0)),
                        _format_number(row.get("objective_switch_count_mean", 0.0)),
                        _format_number(row.get("matched_switch_count_mean", 0.0)),
                        _format_number(row.get("mean_abs_switch_latency_s_mean", 0.0)),
                        _format_number(row.get("flapping_switch_count_mean", 0.0)),
                        ", ".join(str(item) for item in row.get("binding_profiles_observed", [])),
                        ", ".join(str(item) for item in row.get("binding_objectives_observed", [])),
                        ", ".join(str(item) for item in row.get("binding_packet_formats_observed", [])),
                    ]
                    for row in policies
                ],
            ),
            "",
            "## Adaptive Delta",
            "",
            _markdown_table(
                [
                    "baseline",
                    "ctrl delivery +",
                    "loss +",
                    "deadline +",
                    "p95 ms +",
                    "utility +",
                ],
                [
                    [
                        str(row.get("baseline", "")),
                        _format_number(row.get("control_delivery_delta", 0.0)),
                        _format_number(row.get("loss_ratio_delta", 0.0)),
                        _format_number(row.get("deadline_miss_delta", 0.0)),
                        _format_number(row.get("latency_p95_delta_ms", 0.0)),
                        _format_number(row.get("semantic_utility_delta", 0.0)),
                    ]
                    for row in advantage_rows
                ],
            ),
            "",
            "## Best Policy",
            "",
        ]
    )
    best = summary.get("best_policy", {})
    if isinstance(best, Mapping):
        for metric, policy in sorted(best.items()):
            lines.append(f"- `{metric}`: `{policy}`")
    lines.append("")
    interpretation = [
        "- Positive values in Adaptive Delta mean adaptive binding improved over the static baseline for that metric.",
    ]
    if max_runs > 1:
        interpretation.append(
            "- Policy rows are repeated-seed means; confidence intervals and per-seed rows remain in the JSON summary."
        )
    else:
        interpretation.append(
            "- Policy rows are single-realization values; repeated seeds are required before treating deltas as statistical claims."
        )
    if adaptive_row is not None:
        interpretation.append(
            "- Adaptive switch evidence: "
            f"matched `{_format_number(adaptive_row.get('matched_switch_count_mean', 0.0))}` scheduled switches/run, "
            f"mean absolute switch latency `{_format_number(adaptive_row.get('mean_abs_switch_latency_s_mean', 0.0))}` s, "
            f"and flapping `{_format_number(adaptive_row.get('flapping_switch_count_mean', 0.0))}`/run."
        )
    interpretation.append(
        "- Treat adaptive binding as an objective-specific control-plane operating point, not as a universal winner across every raw metric."
    )
    lines.extend(["## Interpretation", "", *interpretation, ""])
    return "\n".join(lines)


def render_dynamic_objective_transition_markdown_report(
    summary: Mapping[str, object],
    *,
    title: str,
    metrics_paths: list[str] | tuple[str, ...],
) -> str:
    transition_schedule = [
        row
        for row in summary.get("transition_schedule", [])
        if isinstance(row, Mapping)
    ]
    objective_schedule = [
        row
        for row in summary.get("objective_schedule", [])
        if isinstance(row, Mapping)
    ]
    policies = [
        row
        for row in summary.get("policies", [])
        if isinstance(row, Mapping)
    ]
    max_runs = max((int(row.get("runs", 0) or 0) for row in policies), default=0)
    lines = [
        f"# {title}",
        "",
        "## Inputs",
        "",
        f"- Metric rows: `{summary.get('records', 0)}`",
    ]
    for path in metrics_paths:
        lines.append(f"- Metrics: `{path}`")
    lines.extend(
        [
            "",
            "## Profile Schedule",
            "",
            _markdown_table(
                ["profile", "at s", "rtt ms", "jitter ms", "loss"],
                [
                    [
                        str(row.get("profile", "")),
                        _format_number(row.get("at_s", 0.0)),
                        _format_number(_transition_schedule_rtt_ms(row)),
                        _format_number(_transition_schedule_jitter_ms(row)),
                        _format_number(_transition_schedule_loss(row)),
                    ]
                    for row in transition_schedule
                ],
            ),
            "",
            "## Objective Schedule",
            "",
            _markdown_table(
                ["objective", "at s"],
                [
                    [
                        str(row.get("objective", "")),
                        _format_number(row.get("at_s", 0.0)),
                    ]
                    for row in objective_schedule
                ],
            ),
            "",
            "## Dynamic Binding Summary",
            "",
            _markdown_table(
                [
                    "policy",
                    "runs",
                    "robots",
                    "decision robots",
                    "received robots",
                    "egress robots",
                    "lease robots",
                    "gate robots",
                    "monitor robots",
                    "robot budget",
                    "rx fairness",
                    "ctrl fairness",
                    "deadline fairness",
                    "pareto",
                    "rx",
                    "loss",
                    "ctrl delivery",
                    "deadline miss",
                    "p95 ms",
                    "profile switches",
                    "matched profile",
                    "profile abs s",
                    "objective switches",
                    "matched objective",
                    "objective abs s",
                    "policy switches",
                    "profiles",
                    "objectives",
                    "formats",
                ],
                [
                    [
                        str(row.get("policy", "")),
                        str(row.get("runs", 0)),
                        _format_number(row.get("robot_count_mean", 0.0)),
                        _format_number(row.get("decision_robot_count_observed_mean", 0.0)),
                        _format_number(row.get("received_robot_count_observed_mean", 0.0)),
                        _format_number(row.get("egress_robot_count_observed_mean", 0.0)),
                        _format_number(row.get("lease_robot_count_observed_mean", 0.0)),
                        _format_number(row.get("quality_gate_robot_count_observed_mean", 0.0)),
                        _format_number(row.get("egress_monitor_robot_count_observed_mean", 0.0)),
                        _format_number(row.get("per_robot_budget_pass_ratio", 0.0)),
                        _format_number(row.get("per_robot_rx_jain_index_mean", 0.0)),
                        _format_number(row.get("per_robot_control_delivery_jain_index_mean", 0.0)),
                        _format_number(row.get("per_robot_deadline_success_jain_index_mean", 0.0)),
                        "yes" if row.get("pareto_frontier") else "no",
                        _format_number(row.get("rx_mean", 0.0)),
                        _format_number(row.get("loss_ratio_mean", 0.0)),
                        _format_number(row.get("control_delivery_ratio_mean", 0.0)),
                        _format_number(row.get("deadline_miss_ratio_mean", 0.0)),
                        _format_number(row.get("latency_p95_ms_mean", 0.0)),
                        _format_number(row.get("switch_count_mean", 0.0)),
                        _format_number(row.get("matched_switch_count_mean", 0.0)),
                        _format_number(row.get("mean_abs_switch_latency_s_mean", 0.0)),
                        _format_number(row.get("objective_switch_count_mean", 0.0)),
                        _format_number(row.get("matched_objective_switch_count_mean", 0.0)),
                        _format_number(row.get("mean_abs_objective_switch_latency_s_mean", 0.0)),
                        _format_number(row.get("policy_switch_count_mean", 0.0)),
                        ", ".join(str(item) for item in row.get("binding_profiles_observed", [])),
                        ", ".join(str(item) for item in row.get("binding_objectives_observed", [])),
                        ", ".join(str(item) for item in row.get("binding_packet_formats_observed", [])),
                    ]
                    for row in policies
                ],
            ),
            "",
            "## Best Policy",
            "",
        ]
    )
    best = summary.get("best_policy", {})
    if isinstance(best, Mapping):
        for metric, policy in sorted(best.items()):
            lines.append(f"- `{metric}`: `{policy}`")
    per_robot_rows = [
        row
        for row in summary.get("comparison_rows", [])
        if isinstance(row, Mapping) and "per_robot_rx_jain_index" in row
    ]
    if per_robot_rows:
        lines.extend(
            [
                "",
                "## Per-Robot QoS Budget",
                "",
                _markdown_table(
                    [
                        "seed",
                        "pass",
                        "rx fairness",
                        "ctrl fairness",
                        "deadline fairness",
                        "min ctrl delivery",
                        "max deadline miss",
                        "p95 spread ms",
                        "worst ctrl",
                        "worst deadline",
                    ],
                    [
                        [
                            str(row.get("seed", "")),
                            "yes" if row.get("per_robot_budget_pass") else "no",
                            _format_number(row.get("per_robot_rx_jain_index", 0.0)),
                            _format_number(row.get("per_robot_control_delivery_jain_index", 0.0)),
                            _format_number(row.get("per_robot_deadline_success_jain_index", 0.0)),
                            _format_number(row.get("per_robot_min_control_delivery_ratio", 0.0)),
                            _format_number(row.get("per_robot_max_deadline_miss_ratio", 0.0)),
                            _format_number(row.get("per_robot_latency_p95_spread_ms", 0.0)),
                            str(row.get("per_robot_worst_control_delivery_robot", "")),
                            str(row.get("per_robot_worst_deadline_miss_robot", "")),
                        ]
                        for row in per_robot_rows
                    ],
                ),
            ]
        )
    lines.extend(
        [
            "",
            "## Interpretation",
            "",
            (
                "- Policy rows are repeated-seed means; confidence intervals "
                "and per-seed rows remain in the JSON summary."
                if max_runs > 1
                else "- Policy rows are single-realization values."
            ),
            "- Profile switch latency and objective switch latency are measured against their own schedules.",
            "- Packet-format changes can take effect in the sidecar path; RMW changes remain target metadata until the decision moves into a true RMW boundary.",
            "",
        ]
    )
    return "\n".join(lines)


def _first_summary_metrics(record: Mapping[str, object]) -> Mapping[str, object]:
    summary_records = record.get("summary", [])
    if isinstance(summary_records, list) and summary_records and isinstance(summary_records[0], Mapping):
        return summary_records[0]
    return {}


def _coverage_mapping(payload: object) -> Mapping[str, object]:
    return payload if isinstance(payload, Mapping) else {}


def _mean_metric(rows: list[Mapping[str, object]], key: str) -> float:
    if not rows:
        return 0.0
    return sum(_metric(row, key) for row in rows) / len(rows)


def _sorted_union(rows: list[Mapping[str, object]], key: str) -> list[str]:
    values: set[str] = set()
    for row in rows:
        payload = row.get(key, [])
        if isinstance(payload, list):
            values.update(str(item) for item in payload if item not in (None, ""))
    return sorted(values)


def _metric(row: Mapping[str, object], key: str) -> float:
    try:
        return float(row.get(key, 0.0))
    except (TypeError, ValueError):
        return 0.0


def _optional_metric(row: Mapping[str, object], key: str) -> float | None:
    value = row.get(key)
    if value in (None, ""):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _format_number(value: object) -> str:
    number = _metric({"value": value}, "value")
    if abs(number) >= 100:
        return f"{number:.1f}"
    return f"{number:.4f}"


def _transition_schedule_rtt_ms(row: Mapping[str, object]) -> float:
    if "rtt_ms" in row:
        return _metric(row, "rtt_ms")
    config = row.get("config", {})
    if isinstance(config, Mapping):
        return _metric(config, "delay_ms") * 2.0
    return 0.0


def _transition_schedule_jitter_ms(row: Mapping[str, object]) -> float:
    if "jitter_ms" in row:
        return _metric(row, "jitter_ms")
    config = row.get("config", {})
    if isinstance(config, Mapping):
        return _metric(config, "jitter_ms")
    return 0.0


def _transition_schedule_loss(row: Mapping[str, object]) -> float:
    if "loss" in row:
        return _metric(row, "loss")
    config = row.get("config", {})
    if isinstance(config, Mapping):
        return _metric(config, "loss_percent") / 100.0
    return 0.0


def _markdown_table(headers: list[str], rows: list[list[str]]) -> str:
    lines = [
        "| " + " | ".join(headers) + " |",
        "| " + " | ".join("---" for _ in headers) + " |",
    ]
    for row in rows:
        lines.append("| " + " | ".join(str(item) for item in row) + " |")
    return "\n".join(lines)


def _count_from_mapping(payload: object, key: str) -> int:
    if not isinstance(payload, Mapping):
        return 0
    return int(payload.get(key, 0))


def _ratio(numerator: int, denominator: int) -> float:
    if denominator <= 0:
        return 0.0
    return numerator / denominator


def quality_gate_identity_match_summary(decisions: Path, quality_gate_decisions: Path) -> dict[str, int]:
    decision_events = [
        event
        for event in _events(decisions)
        if event.get("event_type") == "packet"
        and _is_state_or_scan_topic(str(event.get("topic", "")))
    ]
    gate_events = _events(quality_gate_decisions)
    decision_contracts = {event.get("contract_id") for event in decision_events if event.get("contract_id")}
    gate_contracts = {event.get("contract_id") for event in gate_events if event.get("contract_id")}
    decision_sources = {event.get("source_sample_id") for event in decision_events if event.get("source_sample_id")}
    gate_sources = {event.get("source_sample_id") for event in gate_events if event.get("source_sample_id")}
    return {
        "decision_state_scan_packets": len(decision_events),
        "gate_decisions": len(gate_events),
        "contract_matches": len(decision_contracts & gate_contracts),
        "contract_gate_total": len(gate_contracts),
        "source_matches": len(decision_sources & gate_sources),
        "source_gate_total": len(gate_sources),
    }


def _is_state_or_scan_topic(topic: str) -> bool:
    return topic.endswith("/odom") or topic.endswith("/scan")


def _topic_msg_key(topic: str, msg_type: str) -> str:
    return f"{topic}|{msg_type}" if msg_type else topic


def _events(path: Path) -> list[dict[str, object]]:
    events = []
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            if line.strip():
                events.append(json.loads(line))
    return events


def print_human(record: dict[str, object]) -> None:
    print(f"ros2-docker-live-bridge {record['scenario']}")
    print(f"  status: {record['status']}")
    print(f"  reason: {record['reason']}")
    print(f"  policy: {record['policy']}")
    print(f"  rmw: {record.get('rmw', '')}")
    print(f"  decisions: {record['decisions']}")
    print(f"  received: {record['received']}")
    print(f"  egress_publications: {record['egress_publications']}")
    print(f"  egress_monitor: {record['egress_monitor']}")
    print(f"  lease_decisions: {record['lease_decisions']}")
    print(f"  quality_gate_decisions: {record['quality_gate_decisions']}")
    if "transition_schedule" in record:
        print(f"  transition_schedule: {record['transition_schedule']}")
        print(f"  netem_transition_log: {record.get('netem_transition_log', '')}")
    if "summary" in record:
        for item in record["summary"]:
            print(
                "  "
                f"tx={item['tx']} rx={item['rx']} "
                f"loss={item['loss_ratio']:.3f} p95={item['latency_p95_ms']:.2f}ms "
                f"deadline={item['deadline_miss_ratio']:.3f}"
            )
        print(f"  actions: {record.get('action_counts', {})}")
        print(f"  wire_modes: {record.get('wire_mode_counts', {})}")
        print(f"  egress_publications: {record.get('egress_publication_counts', {})}")
        print(f"  egress_monitor: {record.get('egress_monitor_counts', {})}")
        print(f"  lease_status: {record.get('lease_status_counts', {})}")
        print(f"  quality_gate_status: {record.get('quality_gate_status_counts', {})}")
        print(f"  source_metadata: {record.get('decision_packet_source_metadata_counts', {})}")
        print(f"  transport_binding_transition: {record.get('transport_binding_transition_summary', {})}")
        print(f"  netem_transition: {record.get('netem_transition_summary', {})}")


def print_matrix_human(suite: dict[str, object]) -> None:
    print(f"ros2-docker-live-bridge RMW metadata matrix {suite['scenario']}")
    print(f"  rmws: {', '.join(str(item) for item in suite['rmws'])}")
    print(f"  packet_formats: {', '.join(str(item) for item in suite.get('packet_formats', []))}")
    print(f"  statuses: {suite['status_counts']}")
    for row in suite["metadata_matrix"]:
        print(
            "  - "
            f"{row['rmw']} status={row['status']} "
            f"packets={row['packet_count']} metadata={row['records_with_metadata']} "
            f"gid={row['publisher_gid']} seq={row['sequence_number']} "
            f"source_ts={row['source_timestamp_ns']} recv_ts={row['received_timestamp_ns']}"
        )
    for row in suite.get("packet_format_comparison", []):
        print(
            "  * "
            f"{row['rmw']} {row['packet_format']} status={row['status']} "
            f"tx={row['tx']} rx={row['rx']} loss={row['loss_ratio']:.4f} "
            f"control={row['control_delivery_ratio']:.4f} p95={row['latency_p95_ms']:.2f}ms "
            f"gate={row['quality_gate_accept']} "
            f"contract={row['contract_matches']}/{row['contract_gate_total']} "
            f"source={row['source_matches']}/{row['source_gate_total']}"
        )


def print_repeated_human(suite: dict[str, object]) -> None:
    print(f"ros2-docker-live-bridge repeated matrix {suite['scenario']}")
    print(f"  rmws: {', '.join(str(item) for item in suite['rmws'])}")
    print(f"  packet_formats: {', '.join(str(item) for item in suite.get('packet_formats', []))}")
    print(f"  seeds: {', '.join(str(item) for item in suite.get('seeds', []))}")
    print(f"  profiles: {', '.join(str(item) for item in suite.get('profiles', []))}")
    print(f"  runs: {suite.get('runs', 0)} statuses={suite.get('status_counts', {})}")
    if "repeated_markdown" in suite:
        print(f"  markdown: {suite['repeated_markdown']}")
    if "repeated_summary_json" in suite:
        print(f"  summary_json: {suite['repeated_summary_json']}")
    summary = suite.get("repeated_summary", {})
    policies = summary.get("policies", []) if isinstance(summary, Mapping) else []
    if not policies:
        print("  no successful metric rows; repeated report was not written")
    for row in policies:
        if not isinstance(row, Mapping):
            continue
        print(
            "  * "
            f"{row.get('policy', '')} runs={row.get('runs', 0)} "
            f"rx={float(row.get('rx_mean', 0.0)):.1f} "
            f"loss={float(row.get('loss_ratio_mean', 0.0)):.4f} "
            f"control={float(row.get('control_delivery_ratio_mean', 0.0)):.4f} "
            f"p95={float(row.get('latency_p95_ms_mean', 0.0)):.2f}ms"
        )


def print_transition_binding_human(suite: dict[str, object]) -> None:
    print(f"ros2-docker-live-bridge transition binding matrix {suite['scenario']}")
    print(f"  rmws: {', '.join(str(item) for item in suite['rmws'])}")
    print(f"  packet_formats: {', '.join(str(item) for item in suite.get('packet_formats', []))}")
    print(f"  seeds: {', '.join(str(item) for item in suite.get('seeds', []))}")
    print(f"  static_profiles: {', '.join(str(item) for item in suite.get('static_profiles', []))}")
    print(
        f"  runs: {suite.get('runs', 0)}/{suite.get('planned_runs', 0)} "
        f"statuses={suite.get('status_counts', {})}"
    )
    if "transition_markdown" in suite:
        print(f"  markdown: {suite['transition_markdown']}")
    if "transition_summary_json" in suite:
        print(f"  summary_json: {suite['transition_summary_json']}")
    summary = suite.get("transition_binding_summary", {})
    policies = summary.get("policies", []) if isinstance(summary, Mapping) else []
    if not policies:
        print("  no successful metric rows; transition binding report was not written")
    for row in policies:
        if not isinstance(row, Mapping):
            continue
        print(
            "  * "
            f"{row.get('policy', '')} runs={row.get('runs', 0)} "
            f"rx={float(row.get('rx_mean', 0.0)):.1f} "
            f"loss={float(row.get('loss_ratio_mean', 0.0)):.4f} "
            f"control={float(row.get('control_delivery_ratio_mean', 0.0)):.4f} "
            f"p95={float(row.get('latency_p95_ms_mean', 0.0)):.2f}ms "
            f"switches={float(row.get('switch_count_mean', 0.0)):.1f} "
            f"robot_budget={float(row.get('per_robot_budget_pass_ratio', 0.0)):.2f} "
            f"rx_fair={float(row.get('per_robot_rx_jain_index_mean', 0.0)):.3f}"
        )
    advantage_rows = summary.get("adaptive_advantage", []) if isinstance(summary, Mapping) else []
    for row in advantage_rows:
        if not isinstance(row, Mapping):
            continue
        print(
            "  delta "
            f"vs {row.get('baseline', '')}: "
            f"control={float(row.get('control_delivery_delta', 0.0)):.4f} "
            f"loss={float(row.get('loss_ratio_delta', 0.0)):.4f} "
            f"p95={float(row.get('latency_p95_delta_ms', 0.0)):.2f}ms"
        )


def print_dynamic_objective_transition_human(suite: dict[str, object]) -> None:
    print(f"ros2-docker-live-bridge dynamic objective transition {suite['scenario']}")
    print(f"  rmws: {', '.join(str(item) for item in suite['rmws'])}")
    print(f"  packet_formats: {', '.join(str(item) for item in suite.get('packet_formats', []))}")
    print(f"  seeds: {', '.join(str(item) for item in suite.get('seeds', []))}")
    print(
        f"  runs: {suite.get('runs', 0)}/{suite.get('planned_runs', 0)} "
        f"statuses={suite.get('status_counts', {})}"
    )
    if "transition_markdown" in suite:
        print(f"  markdown: {suite['transition_markdown']}")
    if "transition_summary_json" in suite:
        print(f"  summary_json: {suite['transition_summary_json']}")
    summary = suite.get("dynamic_objective_summary", {})
    policies = summary.get("policies", []) if isinstance(summary, Mapping) else []
    if not policies:
        print("  no successful metric rows; dynamic objective report was not written")
    for row in policies:
        if not isinstance(row, Mapping):
            continue
        print(
            "  * "
            f"{row.get('policy', '')} runs={row.get('runs', 0)} "
            f"rx={float(row.get('rx_mean', 0.0)):.1f} "
            f"loss={float(row.get('loss_ratio_mean', 0.0)):.4f} "
            f"control={float(row.get('control_delivery_ratio_mean', 0.0)):.4f} "
            f"p95={float(row.get('latency_p95_ms_mean', 0.0)):.2f}ms "
            f"profile_switches={float(row.get('switch_count_mean', 0.0)):.1f} "
            f"objective_switches={float(row.get('objective_switch_count_mean', 0.0)):.1f} "
            f"robot_budget={float(row.get('per_robot_budget_pass_ratio', 0.0)):.2f} "
            f"rx_fair={float(row.get('per_robot_rx_jain_index_mean', 0.0)):.3f}"
        )


def _scenario_token(value: str) -> str:
    return "".join(char if char.isalnum() else "_" for char in value).strip("_")


if __name__ == "__main__":
    main()

"""Run the Docker multi-robot live telemetry probe across network profiles."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
import time
from typing import Any, Iterable

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.run_rmw_docker_multi_robot_live_telemetry_plan_probe import (
    DEFAULT_IMAGE,
    FINAL_PATH_PLAN,
    INITIAL_PATH_PLAN,
    ROUTER_TELEMETRY_PROFILES,
    cleanup_live_plan_build,
    ensure_live_plan_build,
    profile_by_name,
    run_probe,
)


SCHEMA_VERSION = "fleetrmw.rmw_multi_robot_live_telemetry_matrix.v1"
DEFAULT_PROFILES = "wifi,wan,roaming"
DEFAULT_SEEDS = "7"
INTER_RUN_SETTLE_S = 2.0


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--image", default=DEFAULT_IMAGE)
    parser.add_argument("--profiles", default=DEFAULT_PROFILES)
    parser.add_argument("--seeds", default=DEFAULT_SEEDS)
    parser.add_argument("--robot-count", type=int, default=1)
    parser.add_argument(
        "--summary-json",
        type=Path,
        default=Path("results_rmw_socket/docker_multi_robot_live_telemetry_matrix_summary.json"),
    )
    parser.add_argument(
        "--markdown",
        type=Path,
        default=Path("results_rmw_socket/docker_multi_robot_live_telemetry_matrix_report.md"),
    )
    parser.add_argument("--enable-netem", action="store_true")
    parser.add_argument("--require-netem", action="store_true")
    parser.add_argument(
        "--netem-loss-scale",
        type=float,
        default=0.0,
        help="multiplier applied to profile packet loss for tc netem",
    )
    parser.add_argument(
        "--netem-drain-s",
        type=float,
        default=2.0,
        help="seconds to keep router containers alive after router exit under netem",
    )
    parser.add_argument(
        "--reuse-build",
        action="store_true",
        help="build rmw_fleetqox_cpp once for the matrix and clean it after the run",
    )
    parser.add_argument(
        "--control-proactive-data-repeats",
        type=int,
        default=None,
        help="override control data-frame proactive repair repeats; default auto",
    )
    parser.add_argument(
        "--state-proactive-data-repeats",
        type=int,
        default=None,
        help="override state data-frame proactive repair repeats; default auto",
    )
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    profiles = parse_profiles(args.profiles)
    seeds = parse_ints(args.seeds, "--seeds")
    summary = run_matrix(
        root=ROOT,
        image=args.image,
        profiles=profiles,
        seeds=seeds,
        enable_netem=args.enable_netem,
        require_netem=args.require_netem,
        netem_loss_scale=args.netem_loss_scale,
        netem_drain_s=args.netem_drain_s,
        robot_count=args.robot_count,
        reuse_build=args.reuse_build,
        control_proactive_data_repeats=args.control_proactive_data_repeats,
        state_proactive_data_repeats=args.state_proactive_data_repeats,
    )
    write_json(summary, args.summary_json)
    write_markdown(render_markdown(summary), args.markdown)

    result = {
        "schema_version": summary["schema_version"],
        "status": summary["status"],
        "profiles": summary["profiles"],
        "seeds": summary["seeds"],
        "image": summary["image"],
        "netem_enabled": summary["netem_enabled"],
        "robot_count": summary["robot_count"],
        "reuse_build": summary["reuse_build"],
        "build_performed": summary["build_performed"],
        "control_proactive_data_repeats": summary["control_proactive_data_repeats"],
        "state_proactive_data_repeats": summary["state_proactive_data_repeats"],
        "runs": len(summary["runs"]),
        "summary": str(args.summary_json),
        "markdown": str(args.markdown),
    }
    if args.json:
        print(json.dumps(result, sort_keys=True))
    else:
        print("fleetrmw-multi-robot-live-telemetry-matrix")
        print(f"  status: {result['status']}")
        print(f"  profiles: {','.join(result['profiles'])}")
        print(f"  runs: {result['runs']}")
        print(f"  summary: {args.summary_json}")
    return 0 if summary["status"] == "ok" else 1


def run_matrix(
    *,
    root: Path,
    image: str,
    profiles: Iterable[str],
    seeds: Iterable[int],
    enable_netem: bool = False,
    require_netem: bool = False,
    netem_loss_scale: float = 0.0,
    netem_drain_s: float = 2.0,
    robot_count: int = 1,
    schema_version: str = SCHEMA_VERSION,
    reuse_build: bool = False,
    prepare_reused_build: bool = True,
    cleanup_reused_build: bool = True,
    control_proactive_data_repeats: int | None = None,
    state_proactive_data_repeats: int | None = None,
) -> dict[str, object]:
    if netem_loss_scale < 0.0:
        raise ValueError("netem_loss_scale must be non-negative")
    if netem_drain_s < 0.0:
        raise ValueError("netem_drain_s must be non-negative")
    if robot_count <= 0:
        raise ValueError("robot_count must be positive")
    if control_proactive_data_repeats is not None and control_proactive_data_repeats < 0:
        raise ValueError("control_proactive_data_repeats must be non-negative")
    if state_proactive_data_repeats is not None and state_proactive_data_repeats < 0:
        raise ValueError("state_proactive_data_repeats must be non-negative")
    profile_list = list(profiles)
    seed_list = list(seeds)
    runs = []
    build_performed = False
    if reuse_build and prepare_reused_build:
        build_performed = ensure_live_plan_build(root, image, clean=True)
    try:
        for profile in profile_list:
            profile_by_name(profile)
            for seed in seed_list:
                summary = run_probe(
                    root=root,
                    image=image,
                    profile=profile,
                    enable_netem=enable_netem,
                    require_netem=require_netem,
                    netem_loss_scale=netem_loss_scale,
                    netem_drain_s=netem_drain_s,
                    repetition_seed=seed,
                    robot_count=robot_count,
                    reuse_build=reuse_build,
                    cleanup_build=not reuse_build,
                    control_proactive_data_repeats=control_proactive_data_repeats,
                    state_proactive_data_repeats=state_proactive_data_repeats,
                )
                runs.append(run_record_from_summary(summary, seed=seed))
                if len(profile_list) * len(seed_list) > 1:
                    time.sleep(INTER_RUN_SETTLE_S)
    finally:
        if reuse_build and cleanup_reused_build:
            cleanup_live_plan_build(root, image)
    matrix_summary = summarize_runs(runs)
    return {
        "schema_version": schema_version,
        "status": "ok" if all(run["status"] == "ok" for run in runs) else "failed",
        "image": image,
        "profiles": profile_list,
        "seeds": seed_list,
        "netem_enabled": enable_netem,
        "netem_required": require_netem,
        "netem_loss_scale": netem_loss_scale,
        "netem_drain_s": netem_drain_s,
        "robot_count": robot_count,
        "reuse_build": reuse_build,
        "build_performed": build_performed,
        "control_proactive_data_repeats": control_proactive_data_repeats,
        "state_proactive_data_repeats": state_proactive_data_repeats,
        "inter_run_settle_s": INTER_RUN_SETTLE_S if len(profile_list) * len(seed_list) > 1 else 0.0,
        "seed_semantics": (
            "repetition_id_only; current tc netem image does not support explicit RNG seed"
            if enable_netem else "runner repetition id"
        ),
        "expected_initial_path_plan": INITIAL_PATH_PLAN,
        "expected_final_path_plan": FINAL_PATH_PLAN,
        "runs": runs,
        "summary": matrix_summary,
    }


def run_record_from_summary(summary: dict[str, Any], *, seed: int) -> dict[str, object]:
    controller = _dict(summary.get("controller"))
    control_publisher = _dict(summary.get("control_publisher"))
    state_publisher = _dict(summary.get("state_publisher"))
    control_subscriber = _dict(summary.get("control_subscriber"))
    state_subscriber = _dict(summary.get("state_subscriber"))
    primary_router = _dict(summary.get("primary_router"))
    backup_router = _dict(summary.get("backup_router"))
    failure = _dict(summary.get("failure"))
    failure_logs = _dict(failure.get("container_logs"))
    topic_specs = [
        item for item in summary.get("topic_specs", [])
        if isinstance(item, dict)
    ]
    return {
        "schema_version": "fleetrmw.rmw_multi_robot_live_telemetry_matrix_run.v1",
        "status": str(summary.get("status", "missing")),
        "profile": str(summary.get("profile", "")),
        "image": str(summary.get("image", "")),
        "seed": seed,
        "repetition_seed": summary.get("repetition_seed"),
        "profile_config": _dict(summary.get("profile_config")),
        "robot_count": int(summary.get("robot_count", 1)),
        "topic_count": int(summary.get("topic_count", len(summary.get("topics", [])))),
        "topic_specs": topic_specs,
        "netem_enabled": bool(summary.get("netem_enabled", False)),
        "netem_required": bool(summary.get("netem_required", False)),
        "netem_loss_scale": _float(summary.get("netem_loss_scale", 0.0)),
        "netem_drain_s": _float(summary.get("netem_drain_s", 0.0)),
        "netem_seed_semantics": str(summary.get("netem_seed_semantics", "")),
        "stochastic_netem": bool(summary.get("stochastic_netem", False)),
        "reuse_build": bool(summary.get("reuse_build", False)),
        "build_performed": bool(summary.get("build_performed", False)),
        "control_duplicate_dedup_required": bool(
            summary.get("control_duplicate_dedup_required", True)
        ),
        "control_duplicate_ack_required": bool(
            summary.get("control_duplicate_ack_required", True)
        ),
        "state_duplicate_dedup_required": bool(
            summary.get("state_duplicate_dedup_required", True)
        ),
        "state_duplicate_ack_required": bool(
            summary.get("state_duplicate_ack_required", True)
        ),
        "control_proactive_data_repeats": int(summary.get("control_proactive_data_repeats", 0)),
        "state_proactive_data_repeats": int(summary.get("state_proactive_data_repeats", 0)),
        "state_terminal_guard_payload": str(summary.get("state_terminal_guard_payload", "")),
        "terminal_guard_algorithm": str(summary.get("terminal_guard_algorithm", "")),
        "terminal_guard_repeat_count": int(summary.get("terminal_guard_repeat_count", 1)),
        "terminal_guard_router_dwell_ms": int(summary.get("terminal_guard_router_dwell_ms", 0)),
        "terminal_guard_required_sequence": int(summary.get("terminal_guard_required_sequence", 0)),
        "terminal_horizon": _dict(summary.get("terminal_horizon")),
        "terminal_guard_startup_settle_ms": int(
            _dict(summary.get("terminal_horizon")).get("startup_settle_ms", 0)
        ),
        "terminal_guard_pre_publish_wait_ms": int(
            _dict(summary.get("terminal_horizon")).get("pre_publish_wait_ms", 0)
        ),
        "terminal_guard_app_repair_cycle_count": int(
            _dict(summary.get("terminal_horizon")).get("app_repair_cycle_count", 0)
        ),
        "terminal_guard_warmup_ack_count": int(
            _dict(summary.get("terminal_horizon")).get("pre_payload_warmup_ack_count", 0)
        ),
        "terminal_guard_warmup_ack_timeout_ms": int(
            _dict(summary.get("terminal_horizon")).get("pre_payload_warmup_ack_timeout_ms", 0)
        ),
        "control_payloads_per_publisher": int(summary.get("control_payloads_per_publisher", 3)),
        "state_payloads_per_publisher": int(summary.get("state_payloads_per_publisher", 3)),
        "control_wire_payloads_per_publisher": int(
            summary.get("control_wire_payloads_per_publisher", summary.get("control_payloads_per_publisher", 3))
        ),
        "state_wire_payloads_per_publisher": int(
            summary.get("state_wire_payloads_per_publisher", summary.get("state_payloads_per_publisher", 3))
        ),
        "primary_expected_forwarded_topic_source_sequences": str(
            summary.get("primary_expected_forwarded_topic_source_sequences", "")
        ),
        "backup_expected_forwarded_topic_source_sequences": str(
            summary.get("backup_expected_forwarded_topic_source_sequences", "")
        ),
        "failure_phase": str(failure.get("phase", "")),
        "failure_command": _excerpt(failure.get("command", ""), max_chars=500),
        "failure_returncode": _optional_int(failure.get("returncode", summary.get("returncode"))),
        "failure_stdout_excerpt": _excerpt(
            failure.get("stdout_excerpt", summary.get("stdout", "")),
        ),
        "failure_stderr_excerpt": _excerpt(
            failure.get("stderr_excerpt", summary.get("stderr", "")),
        ),
        "failure_container_log_excerpt": _excerpt(
            "\n".join(str(value) for value in failure_logs.values()),
        ),
        "netem": _dict(summary.get("netem")),
        "netem_status": _dict(summary.get("netem_status")),
        "initial_path_plan": str(summary.get("initial_path_plan", "")),
        "expected_initial_path_plan": str(summary.get("expected_initial_path_plan", INITIAL_PATH_PLAN)),
        "controller_final_path_plan": str(summary.get("controller_final_path_plan", "")),
        "expected_final_path_plan": str(summary.get("expected_final_path_plan", FINAL_PATH_PLAN)),
        "final_plan_ready": bool(summary.get("final_plan_ready", False)),
        "control_publisher_status": str(control_publisher.get("status", "")),
        "state_publisher_status": str(state_publisher.get("status", "")),
        "control_subscriber_status": str(control_subscriber.get("status", "")),
        "state_subscriber_status": str(state_subscriber.get("status", "")),
        "primary_router_status": str(primary_router.get("status", "")),
        "backup_router_status": str(backup_router.get("status", "")),
        "control_publisher_returncode": int(summary.get("control_publisher_returncode", -999)),
        "state_publisher_returncode": int(summary.get("state_publisher_returncode", -999)),
        "control_subscriber_returncode": int(summary.get("control_subscriber_returncode", -999)),
        "state_subscriber_returncode": int(summary.get("state_subscriber_returncode", -999)),
        "primary_router_returncode": int(summary.get("primary_router_returncode", -999)),
        "backup_router_returncode": int(summary.get("backup_router_returncode", -999)),
        "router_record_count": int(controller.get("record_count", 0)),
        "subscriber_record_count": int(controller.get("subscriber_record_count", 0)),
        "control_redundant_frames": int(
            control_publisher.get("fleet_plan_redundant_frames", 0)
        ),
        "control_selected_path_count": int(
            control_publisher.get("fleet_plan_selected_path_count", 0)
        ),
        "state_redundant_frames": int(state_publisher.get("fleet_plan_redundant_frames", 0)),
        "state_selected_path_count": int(
            state_publisher.get("fleet_plan_selected_path_count", 0)
        ),
        "control_duplicate_ack_received": int(
            control_publisher.get("ack_nack_duplicate_received", 0)
        ),
        "state_duplicate_ack_received": int(
            state_publisher.get("ack_nack_duplicate_received", 0)
        ),
        "control_duplicate_data_frames_deduped": int(
            control_subscriber.get("duplicate_data_frames_deduped", 0)
        ),
        "state_duplicate_data_frames_deduped": int(
            state_subscriber.get("duplicate_data_frames_deduped", 0)
        ),
        "control_idle_repair_ack_nack_sent": int(
            control_subscriber.get("idle_repair_ack_nack_sent", 0)
        ),
        "state_idle_repair_ack_nack_sent": int(
            state_subscriber.get("idle_repair_ack_nack_sent", 0)
        ),
        "control_payload_count": _payload_count(control_subscriber),
        "state_payload_count": _payload_count(state_subscriber),
        "control_payloads": _payloads(control_subscriber),
        "state_payloads": _payloads(state_subscriber),
        "primary_ack_nack_forwarded": int(primary_router.get("ack_nack_forwarded", 0)),
        "primary_expected_ack_nack_forwarded": int(
            primary_router.get("expected_ack_nack_forwarded", 0)
        ),
        "backup_ack_nack_forwarded": int(backup_router.get("ack_nack_forwarded", 0)),
        "backup_expected_ack_nack_forwarded": int(
            backup_router.get("expected_ack_nack_forwarded", 0)
        ),
        "control_delivery_latency_ms_mean": _mean_latency_for_kind(summary, "control"),
        "state_delivery_latency_ms_mean": _mean_latency_for_kind(summary, "state"),
    }


def summarize_runs(runs: Iterable[dict[str, object]]) -> dict[str, object]:
    rows = list(runs)
    by_profile: dict[str, list[dict[str, object]]] = {}
    for row in rows:
        by_profile.setdefault(str(row.get("profile", "")), []).append(row)
    profile_rows = []
    for profile, group in sorted(by_profile.items()):
        profile_rows.append(
            {
                "profile": profile,
                "runs": len(group),
                "ok_runs": sum(1 for row in group if row.get("status") == "ok"),
                "netem_applied_runs": sum(1 for row in group if _all_netem_applied(row)),
                "router_record_count_mean": _mean_metric(group, "router_record_count"),
                "subscriber_record_count_mean": _mean_metric(group, "subscriber_record_count"),
                "control_redundant_frames_mean": _mean_metric(
                    group,
                    "control_redundant_frames",
                ),
                "control_duplicate_data_frames_deduped_mean": _mean_metric(
                    group,
                    "control_duplicate_data_frames_deduped",
                ),
                "state_duplicate_data_frames_deduped_mean": _mean_metric(
                    group,
                    "state_duplicate_data_frames_deduped",
                ),
                "control_idle_repair_ack_nack_sent_mean": _mean_metric(
                    group,
                    "control_idle_repair_ack_nack_sent",
                ),
                "state_idle_repair_ack_nack_sent_mean": _mean_metric(
                    group,
                    "state_idle_repair_ack_nack_sent",
                ),
                "control_delivery_latency_ms_mean": _mean_metric(
                    group,
                    "control_delivery_latency_ms_mean",
                ),
                "state_delivery_latency_ms_mean": _mean_metric(
                    group,
                    "state_delivery_latency_ms_mean",
                ),
                "control_proactive_data_repeats_mean": _mean_metric(
                    group,
                    "control_proactive_data_repeats",
                ),
                "state_proactive_data_repeats_mean": _mean_metric(
                    group,
                    "state_proactive_data_repeats",
                ),
                "terminal_guard_algorithm": next(
                    (
                        str(row.get("terminal_guard_algorithm", ""))
                        for row in group
                        if row.get("terminal_guard_algorithm")
                    ),
                    "",
                ),
                "terminal_guard_repeat_count_mean": _mean_metric(
                    group,
                    "terminal_guard_repeat_count",
                ),
                "terminal_guard_router_dwell_ms_mean": _mean_metric(
                    group,
                    "terminal_guard_router_dwell_ms",
                ),
                "terminal_guard_startup_settle_ms_mean": _mean_metric(
                    group,
                    "terminal_guard_startup_settle_ms",
                ),
                "terminal_guard_pre_publish_wait_ms_mean": _mean_metric(
                    group,
                    "terminal_guard_pre_publish_wait_ms",
                ),
                "terminal_guard_app_repair_cycle_count_mean": _mean_metric(
                    group,
                    "terminal_guard_app_repair_cycle_count",
                ),
                "terminal_guard_warmup_ack_count_mean": _mean_metric(
                    group,
                    "terminal_guard_warmup_ack_count",
                ),
                "terminal_guard_warmup_ack_timeout_ms_mean": _mean_metric(
                    group,
                    "terminal_guard_warmup_ack_timeout_ms",
                ),
            }
        )
    return {
        "run_count": len(rows),
        "ok_run_count": sum(1 for row in rows if row.get("status") == "ok"),
        "netem_applied_run_count": sum(1 for row in rows if _all_netem_applied(row)),
        "profiles": profile_rows,
    }


def render_markdown(summary: dict[str, object]) -> str:
    rows = list(_dict(summary.get("summary")).get("profiles", []))
    lines = [
        "# RMW Multi-Robot Live Telemetry Matrix V1",
        "",
        f"- Status: `{summary.get('status')}`",
        f"- Profiles: `{', '.join(str(item) for item in summary.get('profiles', []))}`",
        f"- Image: `{summary.get('image', '')}`",
        f"- Seeds: `{', '.join(str(item) for item in summary.get('seeds', []))}`",
        f"- Seed semantics: `{summary.get('seed_semantics', '')}`",
        f"- Netem enabled: `{summary.get('netem_enabled', False)}`",
        f"- Netem required: `{summary.get('netem_required', False)}`",
        f"- Robot count: `{summary.get('robot_count', 1)}`",
        f"- Netem loss scale: `{summary.get('netem_loss_scale', 0.0)}`",
        f"- Netem drain seconds: `{summary.get('netem_drain_s', 0.0)}`",
        f"- Reuse build: `{summary.get('reuse_build', False)}`",
        f"- Build performed: `{summary.get('build_performed', False)}`",
        f"- Requested control proactive data repeats: `{summary.get('control_proactive_data_repeats')}`",
        f"- Requested state proactive data repeats: `{summary.get('state_proactive_data_repeats')}`",
        f"- Inter-run settle seconds: `{summary.get('inter_run_settle_s', 0.0)}`",
        f"- Runs: `{len(summary.get('runs', []))}`",
        "",
        "## Profile Summary",
        "",
        "| profile | ok/runs | netem applied | router records | subscriber records | effective data repeats | guard horizon | repair NACKs | control redundant | control de-dup | state de-dup | control latency ms | state latency ms |",
        "|---|---:|---:|---:|---:|---|---|---:|---:|---:|---:|---:|---:|",
    ]
    for row in rows:
        if not isinstance(row, dict):
            continue
        ok_runs = int(row.get("ok_runs", 0))
        runs = int(row.get("runs", 0))
        lines.append(
            "| "
            f"{row.get('profile')} | "
            f"{ok_runs}/{runs} | "
            f"{int(row.get('netem_applied_runs', 0))}/{runs} | "
            f"{_format(row.get('router_record_count_mean'))} | "
            f"{_format(row.get('subscriber_record_count_mean'))} | "
            f"c={_format(row.get('control_proactive_data_repeats_mean'))},s={_format(row.get('state_proactive_data_repeats_mean'))} | "
            f"{row.get('terminal_guard_algorithm', '') or '-'} r={_format(row.get('terminal_guard_repeat_count_mean'))},a={_format(row.get('terminal_guard_app_repair_cycle_count_mean'))},w={_format(row.get('terminal_guard_warmup_ack_count_mean'))}/{_format(row.get('terminal_guard_warmup_ack_timeout_ms_mean'))}ms,d={_format(row.get('terminal_guard_router_dwell_ms_mean'))}ms,s={_format(row.get('terminal_guard_startup_settle_ms_mean'))}ms,p={_format(row.get('terminal_guard_pre_publish_wait_ms_mean'))}ms | "
            f"c={_format(row.get('control_idle_repair_ack_nack_sent_mean'))},s={_format(row.get('state_idle_repair_ack_nack_sent_mean'))} | "
            f"{_format(row.get('control_redundant_frames_mean'))} | "
            f"{_format(row.get('control_duplicate_data_frames_deduped_mean'))} | "
            f"{_format(row.get('state_duplicate_data_frames_deduped_mean'))} | "
            f"{_format(row.get('control_delivery_latency_ms_mean'))} | "
            f"{_format(row.get('state_delivery_latency_ms_mean'))} |"
        )
    lines.extend(
        [
            "",
            "## Interpretation",
            "",
            "- Each run uses the live Docker RMW publisher/router/subscriber path.",
            "- The matrix varies router telemetry profiles while keeping the selected fleet workload fixed.",
            "- When netem is enabled, router containers also apply `tc qdisc` to their Docker `eth0` links.",
            "- A passing run requires control redundancy, state unicast, subscriber QoE telemetry, and redundant-path de-duplication.",
            "",
        ]
    )
    return "\n".join(lines)


def parse_profiles(value: str) -> list[str]:
    profiles = [part.strip() for part in value.split(",") if part.strip()]
    if not profiles:
        raise SystemExit("--profiles must contain at least one profile")
    unknown = [profile for profile in profiles if profile not in ROUTER_TELEMETRY_PROFILES]
    if unknown:
        choices = ", ".join(sorted(ROUTER_TELEMETRY_PROFILES))
        raise SystemExit(f"unknown --profiles value(s): {', '.join(unknown)}; choices: {choices}")
    return list(dict.fromkeys(profiles))


def parse_ints(value: str, option: str) -> list[int]:
    try:
        parsed = [int(part.strip()) for part in value.split(",") if part.strip()]
    except ValueError as exc:
        raise SystemExit(f"{option} must be a comma-separated integer list") from exc
    if not parsed or any(item <= 0 for item in parsed):
        raise SystemExit(f"{option} must contain positive integers")
    return parsed


def write_json(summary: dict[str, object], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(summary, indent=2, sort_keys=True), encoding="utf-8")


def write_markdown(markdown: str, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(markdown, encoding="utf-8")


def _mean_latency(summary: dict[str, Any], robot_id: str) -> float:
    telemetry = _dict(summary.get("subscriber_telemetry"))
    records = telemetry.get(robot_id, [])
    if not isinstance(records, list):
        return 0.0
    values = []
    for record in records:
        if isinstance(record, dict):
            values.append(_float(record.get("latency_ms", 0.0)))
    return sum(values) / len(values) if values else 0.0


def _mean_latency_for_kind(summary: dict[str, Any], kind: str) -> float:
    topic_specs = [
        item for item in summary.get("topic_specs", [])
        if isinstance(item, dict) and item.get("kind") == kind
    ]
    if not topic_specs:
        return _mean_latency(summary, "robot_0000" if kind == "control" else "robot_0001")
    telemetry = _dict(summary.get("subscriber_telemetry"))
    values = []
    for spec in topic_specs:
        key = str(spec.get("flow_id", ""))
        records = telemetry.get(key, [])
        if not isinstance(records, list):
            continue
        for record in records:
            if isinstance(record, dict):
                values.append(_float(record.get("latency_ms", 0.0)))
    return sum(values) / len(values) if values else 0.0


def _mean_metric(rows: Iterable[dict[str, object]], key: str) -> float:
    values = [_float(row.get(key, 0.0)) for row in rows]
    return sum(values) / len(values) if values else 0.0


def _dict(value: object) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _float(value: object) -> float:
    try:
        return float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return 0.0


def _optional_int(value: object) -> int | None:
    if value is None or value == "":
        return None
    try:
        return int(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None


def _format(value: object) -> str:
    return f"{_float(value):.3f}"


def _excerpt(value: object, *, max_chars: int = 2000) -> str:
    text = "" if value is None else str(value)
    text = " ".join(text.strip().split())
    if len(text) <= max_chars:
        return text
    return text[-max_chars:]


def _payload_count(component: dict[str, Any]) -> int:
    payloads = component.get("payloads", [])
    return len(payloads) if isinstance(payloads, list) else 0


def _payloads(component: dict[str, Any]) -> list[str]:
    payloads = component.get("payloads", [])
    if not isinstance(payloads, list):
        return []
    return [str(payload) for payload in payloads]


def _all_netem_applied(row: dict[str, object]) -> bool:
    if not row.get("netem_enabled"):
        return False
    statuses = _dict(row.get("netem_status"))
    for path_id in ("primary_wifi", "backup_5g"):
        status = statuses.get(path_id)
        if not isinstance(status, dict) or status.get("status") != "applied":
            return False
    return True


if __name__ == "__main__":
    raise SystemExit(main())

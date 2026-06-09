"""Ablate proactive repair modes over the live stochastic netem RMW sweep."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import Iterable

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.run_rmw_docker_multi_robot_live_stochastic_netem_sweep import (
    DEFAULT_LOSS_SCALES,
    format_counts,
    parse_loss_scales,
    run_sweep,
)
from scripts.run_rmw_docker_multi_robot_live_telemetry_matrix import (
    DEFAULT_PROFILES,
    DEFAULT_SEEDS,
    parse_ints,
    parse_profiles,
    write_json,
    write_markdown,
)
from scripts.run_rmw_docker_multi_robot_live_telemetry_plan_probe import (
    DEFAULT_IMAGE,
    cleanup_live_plan_build,
    ensure_live_plan_build,
)


SCHEMA_VERSION = "fleetrmw.rmw_multi_robot_live_stochastic_netem_ablation.v1"
DEFAULT_MODES = "none,state_only,control_state"
MODE_DEFINITIONS: dict[str, dict[str, object]] = {
    "none": {
        "control_proactive_data_repeats": 0,
        "state_proactive_data_repeats": 0,
        "description": "no proactive data-frame repeats; only gap-triggered ACK/NACK can repair",
    },
    "state_only": {
        "control_proactive_data_repeats": 0,
        "state_proactive_data_repeats": 1,
        "description": "repeat lower-criticality state once to expose terminal-loss repair cost",
    },
    "control_state": {
        "control_proactive_data_repeats": 1,
        "state_proactive_data_repeats": 1,
        "description": "repeat both urgent control and state once under stochastic loss",
    },
    "auto": {
        "control_proactive_data_repeats": None,
        "state_proactive_data_repeats": None,
        "description": "delegate repeat counts to the probe default for the current netem mode",
    },
}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--image", default=DEFAULT_IMAGE)
    parser.add_argument("--profiles", default=DEFAULT_PROFILES)
    parser.add_argument("--seeds", default=DEFAULT_SEEDS)
    parser.add_argument("--loss-scales", default=DEFAULT_LOSS_SCALES)
    parser.add_argument("--modes", default=DEFAULT_MODES)
    parser.add_argument("--robot-count", type=int, default=1)
    parser.add_argument(
        "--summary-json",
        type=Path,
        default=Path("results_rmw_socket/docker_multi_robot_live_stochastic_netem_ablation_summary.json"),
    )
    parser.add_argument(
        "--markdown",
        type=Path,
        default=Path("results_rmw_socket/docker_multi_robot_live_stochastic_netem_ablation_report.md"),
    )
    parser.add_argument("--require-netem", action="store_true")
    parser.add_argument(
        "--netem-drain-s",
        type=float,
        default=2.0,
        help="seconds to keep router containers alive after router exit so qdisc queues drain",
    )
    parser.add_argument(
        "--reuse-build",
        action="store_true",
        help="build rmw_fleetqox_cpp once for the full ablation campaign and clean it after the run",
    )
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    profiles = parse_profiles(args.profiles)
    seeds = parse_ints(args.seeds, "--seeds")
    loss_scales = parse_loss_scales(args.loss_scales)
    modes = parse_modes(args.modes)
    summary = run_ablation(
        root=ROOT,
        image=args.image,
        profiles=profiles,
        seeds=seeds,
        loss_scales=loss_scales,
        modes=modes,
        robot_count=args.robot_count,
        require_netem=args.require_netem,
        netem_drain_s=args.netem_drain_s,
        reuse_build=args.reuse_build,
    )
    write_json(summary, args.summary_json)
    write_markdown(render_markdown(summary), args.markdown)

    result = {
        "schema_version": summary["schema_version"],
        "status": summary["status"],
        "image": summary["image"],
        "profiles": summary["profiles"],
        "seeds": summary["seeds"],
        "loss_scales": summary["loss_scales"],
        "modes": summary["modes"],
        "robot_count": summary["robot_count"],
        "best_mode": summary["summary"]["best_mode"],
        "run_count": summary["summary"]["run_count"],
        "ok_run_count": summary["summary"]["ok_run_count"],
        "reuse_build": summary["reuse_build"],
        "build_performed": summary["build_performed"],
        "summary": str(args.summary_json),
        "markdown": str(args.markdown),
    }
    if args.json:
        print(json.dumps(result, sort_keys=True))
    else:
        print("fleetrmw-multi-robot-live-stochastic-netem-ablation")
        print(f"  status: {result['status']}")
        print(f"  image: {result['image']}")
        print(f"  profiles: {','.join(result['profiles'])}")
        print(f"  modes: {','.join(result['modes'])}")
        print(f"  ok/runs: {result['ok_run_count']}/{result['run_count']}")
        print(f"  best_mode: {result['best_mode']}")
        print(f"  summary: {args.summary_json}")
    return 0 if summary["status"] == "ok" else 1


def run_ablation(
    *,
    root: Path,
    image: str,
    profiles: Iterable[str],
    seeds: Iterable[int],
    loss_scales: Iterable[float],
    modes: Iterable[str],
    require_netem: bool,
    netem_drain_s: float,
    robot_count: int = 1,
    reuse_build: bool = False,
) -> dict[str, object]:
    profile_list = list(profiles)
    seed_list = list(seeds)
    loss_scale_list = list(loss_scales)
    mode_list = list(modes)
    if netem_drain_s < 0.0:
        raise ValueError("netem_drain_s must be non-negative")
    if robot_count <= 0:
        raise ValueError("robot_count must be positive")

    build_performed = False
    sweeps = []
    mode_results = []
    if reuse_build:
        build_performed = ensure_live_plan_build(root, image, clean=True)
    try:
        for mode in mode_list:
            control_repeats, state_repeats = repeat_config_for_mode(mode)
            sweep = run_sweep(
                root=root,
                image=image,
                profiles=profile_list,
                seeds=seed_list,
                loss_scales=loss_scale_list,
                robot_count=robot_count,
                require_netem=require_netem,
                netem_drain_s=netem_drain_s,
                reuse_build=reuse_build,
                prepare_reused_build=not reuse_build,
                cleanup_reused_build=not reuse_build,
                control_proactive_data_repeats=control_repeats,
                state_proactive_data_repeats=state_repeats,
            )
            sweeps.append({"mode": mode, "sweep": sweep})
            mode_results.append(
                mode_record_from_sweep(
                    mode=mode,
                    sweep=sweep,
                    control_proactive_data_repeats=control_repeats,
                    state_proactive_data_repeats=state_repeats,
                )
            )
    finally:
        if reuse_build:
            cleanup_live_plan_build(root, image)

    ablation_summary = summarize_ablation(mode_results)
    return {
        "schema_version": SCHEMA_VERSION,
        "status": ablation_summary["status"],
        "image": image,
        "profiles": profile_list,
        "seeds": seed_list,
        "loss_scales": loss_scale_list,
        "modes": mode_list,
        "robot_count": robot_count,
        "mode_definitions": {
            mode: MODE_DEFINITIONS[mode]
            for mode in mode_list
        },
        "netem_required": require_netem,
        "netem_drain_s": netem_drain_s,
        "reuse_build": reuse_build,
        "build_performed": build_performed,
        "seed_semantics": "repetition_id_only; current tc netem image does not support explicit RNG seed",
        "mode_results": mode_results,
        "sweeps": sweeps,
        "summary": ablation_summary,
    }


def mode_record_from_sweep(
    *,
    mode: str,
    sweep: dict[str, object],
    control_proactive_data_repeats: int | None,
    state_proactive_data_repeats: int | None,
) -> dict[str, object]:
    sweep_summary = _dict(sweep.get("summary"))
    runs = [row for row in sweep.get("runs", []) if isinstance(row, dict)]
    return {
        "mode": mode,
        "description": str(MODE_DEFINITIONS[mode]["description"]),
        "sweep_status": str(sweep.get("status", "")),
        "control_proactive_data_repeats": control_proactive_data_repeats,
        "state_proactive_data_repeats": state_proactive_data_repeats,
        "run_count": int(sweep_summary.get("run_count", 0)),
        "ok_run_count": int(sweep_summary.get("ok_run_count", 0)),
        "failed_run_count": int(sweep_summary.get("failed_run_count", 0)),
        "netem_applied_run_count": int(sweep_summary.get("netem_applied_run_count", 0)),
        "failure_kind_counts": _dict(sweep_summary.get("failure_kind_counts")),
        "max_all_profiles_ok_loss_scale": sweep_summary.get("max_all_profiles_ok_loss_scale"),
        "first_failed_loss_scale_by_profile": _dict(
            sweep_summary.get("first_failed_loss_scale_by_profile")
        ),
        "ok_control_delivery_latency_ms_mean": _mean_metric(
            runs,
            "control_delivery_latency_ms_mean",
            ok_only=True,
        ),
        "ok_state_delivery_latency_ms_mean": _mean_metric(
            runs,
            "state_delivery_latency_ms_mean",
            ok_only=True,
        ),
        "control_redundant_frames_mean": _mean_metric(
            runs,
            "control_redundant_frames",
            ok_only=True,
        ),
        "state_redundant_frames_mean": _mean_metric(
            runs,
            "state_redundant_frames",
            ok_only=True,
        ),
        "control_duplicate_data_frames_deduped_mean": _mean_metric(
            runs,
            "control_duplicate_data_frames_deduped",
            ok_only=True,
        ),
        "state_duplicate_data_frames_deduped_mean": _mean_metric(
            runs,
            "state_duplicate_data_frames_deduped",
            ok_only=True,
        ),
        "control_duplicate_ack_received_mean": _mean_metric(
            runs,
            "control_duplicate_ack_received",
            ok_only=True,
        ),
        "state_duplicate_ack_received_mean": _mean_metric(
            runs,
            "state_duplicate_ack_received",
            ok_only=True,
        ),
        "repair_cost_frames_mean": _mean_composite(
            runs,
            (
                "control_duplicate_data_frames_deduped",
                "state_duplicate_data_frames_deduped",
                "control_duplicate_ack_received",
                "state_duplicate_ack_received",
            ),
            ok_only=True,
        ),
    }


def summarize_ablation(mode_results: Iterable[dict[str, object]]) -> dict[str, object]:
    rows = list(mode_results)
    ranking = rank_modes(rows)
    best_mode = str(ranking[0]["mode"]) if ranking else ""
    ok_run_count = sum(int(row.get("ok_run_count", 0)) for row in rows)
    run_count = sum(int(row.get("run_count", 0)) for row in rows)
    status = "ok" if ranking and int(ranking[0].get("ok_run_count", 0)) > 0 else "failed"
    return {
        "status": status,
        "mode_count": len(rows),
        "run_count": run_count,
        "ok_run_count": ok_run_count,
        "failed_run_count": sum(int(row.get("failed_run_count", 0)) for row in rows),
        "netem_applied_run_count": sum(
            int(row.get("netem_applied_run_count", 0))
            for row in rows
        ),
        "best_mode": best_mode,
        "ranking": [
            {"rank": index + 1, **row}
            for index, row in enumerate(ranking)
        ],
    }


def rank_modes(mode_results: Iterable[dict[str, object]]) -> list[dict[str, object]]:
    return sorted((dict(row) for row in mode_results), key=_rank_key)


def parse_modes(value: str) -> list[str]:
    modes = [part.strip() for part in value.split(",") if part.strip()]
    if not modes:
        raise SystemExit("--modes must contain at least one mode")
    unknown = [mode for mode in modes if mode not in MODE_DEFINITIONS]
    if unknown:
        choices = ", ".join(sorted(MODE_DEFINITIONS))
        raise SystemExit(f"unknown --modes value(s): {', '.join(unknown)}; choices: {choices}")
    return list(dict.fromkeys(modes))


def repeat_config_for_mode(mode: str) -> tuple[int | None, int | None]:
    if mode not in MODE_DEFINITIONS:
        raise ValueError(f"unknown mode: {mode}")
    definition = MODE_DEFINITIONS[mode]
    return (
        _optional_int(definition.get("control_proactive_data_repeats")),
        _optional_int(definition.get("state_proactive_data_repeats")),
    )


def render_markdown(summary: dict[str, object]) -> str:
    ablation = _dict(summary.get("summary"))
    ranking = [row for row in ablation.get("ranking", []) if isinstance(row, dict)]
    lines = [
        "# RMW Multi-Robot Live Stochastic Netem Ablation V1",
        "",
        f"- Status: `{summary.get('status')}`",
        f"- Image: `{summary.get('image')}`",
        f"- Profiles: `{', '.join(str(item) for item in summary.get('profiles', []))}`",
        f"- Seeds: `{', '.join(str(item) for item in summary.get('seeds', []))}`",
        f"- Seed semantics: `{summary.get('seed_semantics')}`",
        f"- Loss scales: `{', '.join(str(item) for item in summary.get('loss_scales', []))}`",
        f"- Modes: `{', '.join(str(item) for item in summary.get('modes', []))}`",
        f"- Netem required: `{summary.get('netem_required')}`",
        f"- Reuse build: `{summary.get('reuse_build', False)}`",
        f"- Build performed: `{summary.get('build_performed', False)}`",
        f"- Runs: `{ablation.get('ok_run_count', 0)}/{ablation.get('run_count', 0)} ok`",
        f"- Best mode: `{ablation.get('best_mode', '')}`",
        "",
        "## Mode Ranking",
        "",
        "| rank | mode | control repeats | state repeats | ok/runs | netem applied | max all-profiles-ok loss | failure kinds | control latency ms | state latency ms | repair cost |",
        "|---:|---|---:|---:|---:|---:|---:|---|---:|---:|---:|",
    ]
    for row in ranking:
        lines.append(
            "| "
            f"{int(row.get('rank', 0))} | "
            f"{row.get('mode')} | "
            f"{_format_optional_int(row.get('control_proactive_data_repeats'))} | "
            f"{_format_optional_int(row.get('state_proactive_data_repeats'))} | "
            f"{int(row.get('ok_run_count', 0))}/{int(row.get('run_count', 0))} | "
            f"{int(row.get('netem_applied_run_count', 0))}/{int(row.get('run_count', 0))} | "
            f"{_format_nullable(row.get('max_all_profiles_ok_loss_scale'))} | "
            f"{format_counts(_dict(row.get('failure_kind_counts')))} | "
            f"{_format(row.get('ok_control_delivery_latency_ms_mean'))} | "
            f"{_format(row.get('ok_state_delivery_latency_ms_mean'))} | "
            f"{_format(row.get('repair_cost_frames_mean'))} |"
        )
    lines.extend(
        [
            "",
            "## Failure Boundary By Mode",
            "",
            "| mode | first failed loss scale by profile |",
            "|---|---|",
        ]
    )
    for row in ranking:
        first_failed = _dict(row.get("first_failed_loss_scale_by_profile"))
        lines.append(
            "| "
            f"{row.get('mode')} | "
            f"{format_loss_map(first_failed)} |"
        )
    lines.extend(
        [
            "",
            "## Interpretation",
            "",
            "- This is a controlled ablation over the same live ROS 2/RMW Docker topology and the same stochastic `tc netem` profiles.",
            "- Ranking favors delivery resilience first, then the strongest all-profile loss boundary, then lower latency and lower repair overhead.",
            "- `none` is the gap-triggered ACK/NACK baseline; `state_only` and `control_state` expose whether terminal-loss repair is worth its duplicate-frame cost.",
            "- Failed mode rows are expected research evidence when they reveal the boundary where a repair policy stops satisfying QoS/QoE.",
            "",
        ]
    )
    return "\n".join(lines)


def format_loss_map(values: dict[str, object]) -> str:
    if not values:
        return "-"
    return ",".join(
        f"{key}:{_format(value)}"
        for key, value in sorted(values.items())
    )


def _rank_key(row: dict[str, object]) -> tuple[float, float, float, float, str]:
    run_count = int(row.get("run_count", 0))
    ok_run_count = int(row.get("ok_run_count", 0))
    ok_ratio = ok_run_count / run_count if run_count else 0.0
    max_loss = _nullable_float(row.get("max_all_profiles_ok_loss_scale"), default=-1.0)
    latency_cost = _float(row.get("ok_control_delivery_latency_ms_mean")) + _float(
        row.get("ok_state_delivery_latency_ms_mean")
    )
    repair_cost = _float(row.get("repair_cost_frames_mean"))
    return (-ok_ratio, -max_loss, latency_cost, repair_cost, str(row.get("mode", "")))


def _mean_metric(rows: Iterable[dict[str, object]], key: str, *, ok_only: bool) -> float:
    values = []
    for row in rows:
        if ok_only and row.get("status") != "ok":
            continue
        value = row.get(key)
        if value in (None, ""):
            continue
        values.append(_float(value))
    return sum(values) / len(values) if values else 0.0


def _mean_composite(
    rows: Iterable[dict[str, object]],
    keys: Iterable[str],
    *,
    ok_only: bool,
) -> float:
    values = []
    key_list = list(keys)
    for row in rows:
        if ok_only and row.get("status") != "ok":
            continue
        values.append(sum(_float(row.get(key)) for key in key_list))
    return sum(values) / len(values) if values else 0.0


def _dict(value: object) -> dict[str, object]:
    return value if isinstance(value, dict) else {}


def _float(value: object) -> float:
    try:
        return float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return 0.0


def _nullable_float(value: object, *, default: float) -> float:
    if value is None or value == "":
        return default
    return _float(value)


def _optional_int(value: object) -> int | None:
    if value is None or value == "":
        return None
    return int(value)  # type: ignore[arg-type]


def _format(value: object) -> str:
    return f"{_float(value):.3f}"


def _format_nullable(value: object) -> str:
    if value is None or value == "":
        return "-"
    return _format(value)


def _format_optional_int(value: object) -> str:
    if value is None or value == "":
        return "-"
    return str(int(value))  # type: ignore[arg-type]


if __name__ == "__main__":
    raise SystemExit(main())

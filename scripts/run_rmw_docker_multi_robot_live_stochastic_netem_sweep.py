"""Sweep stochastic tc-netem loss scales for the live multi-robot RMW path."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import Iterable

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.run_rmw_docker_multi_robot_live_telemetry_matrix import (
    DEFAULT_PROFILES,
    DEFAULT_SEEDS,
    parse_ints,
    parse_profiles,
    run_matrix,
    write_json,
    write_markdown,
)
from scripts.run_rmw_docker_multi_robot_live_telemetry_plan_probe import (
    DEFAULT_IMAGE,
    cleanup_live_plan_build,
    ensure_live_plan_build,
)


SCHEMA_VERSION = "fleetrmw.rmw_multi_robot_live_stochastic_netem_sweep.v1"
MATRIX_SCHEMA_VERSION = "fleetrmw.rmw_multi_robot_live_stochastic_netem_matrix.v1"
DEFAULT_LOSS_SCALES = "0.1,0.25,0.5"
COMPONENT_STATUS_KEYS = (
    "control_publisher_status",
    "state_publisher_status",
    "control_subscriber_status",
    "state_subscriber_status",
    "primary_router_status",
    "backup_router_status",
)
COMPONENT_RETURNCODE_KEYS = (
    "control_publisher_returncode",
    "state_publisher_returncode",
    "control_subscriber_returncode",
    "state_subscriber_returncode",
    "primary_router_returncode",
    "backup_router_returncode",
)
NON_SUBSCRIBER_STATUS_KEYS = (
    "control_publisher_status",
    "state_publisher_status",
    "primary_router_status",
    "backup_router_status",
)
NON_SUBSCRIBER_RETURNCODE_KEYS = (
    "control_publisher_returncode",
    "state_publisher_returncode",
    "primary_router_returncode",
    "backup_router_returncode",
)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--image", default=DEFAULT_IMAGE)
    parser.add_argument("--profiles", default=DEFAULT_PROFILES)
    parser.add_argument("--seeds", default=DEFAULT_SEEDS)
    parser.add_argument("--loss-scales", default=DEFAULT_LOSS_SCALES)
    parser.add_argument("--robot-count", type=int, default=1)
    parser.add_argument(
        "--summary-json",
        type=Path,
        default=Path("results_rmw_socket/docker_multi_robot_live_stochastic_netem_sweep_summary.json"),
    )
    parser.add_argument(
        "--markdown",
        type=Path,
        default=Path("results_rmw_socket/docker_multi_robot_live_stochastic_netem_sweep_report.md"),
    )
    parser.add_argument("--require-netem", action="store_true")
    parser.add_argument(
        "--netem-drain-s",
        type=float,
        default=2.0,
        help="seconds to keep router containers alive after router exit so qdisc queues drain",
    )
    parser.add_argument(
        "--fail-on-row-failure",
        action="store_true",
        help="return non-zero when any profile/seed/loss row fails",
    )
    parser.add_argument(
        "--reuse-build",
        action="store_true",
        help="build rmw_fleetqox_cpp once for the whole sweep and clean it after the run",
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
    loss_scales = parse_loss_scales(args.loss_scales)
    summary = run_sweep(
        root=ROOT,
        image=args.image,
        profiles=profiles,
        seeds=seeds,
        loss_scales=loss_scales,
        robot_count=args.robot_count,
        require_netem=args.require_netem,
        netem_drain_s=args.netem_drain_s,
        reuse_build=args.reuse_build,
        control_proactive_data_repeats=args.control_proactive_data_repeats,
        state_proactive_data_repeats=args.state_proactive_data_repeats,
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
        "robot_count": summary["robot_count"],
        "run_count": summary["summary"]["run_count"],
        "ok_run_count": summary["summary"]["ok_run_count"],
        "reuse_build": summary["reuse_build"],
        "build_performed": summary["build_performed"],
        "control_proactive_data_repeats": summary["control_proactive_data_repeats"],
        "state_proactive_data_repeats": summary["state_proactive_data_repeats"],
        "summary": str(args.summary_json),
        "markdown": str(args.markdown),
    }
    if args.json:
        print(json.dumps(result, sort_keys=True))
    else:
        print("fleetrmw-multi-robot-live-stochastic-netem-sweep")
        print(f"  status: {result['status']}")
        print(f"  image: {result['image']}")
        print(f"  profiles: {','.join(result['profiles'])}")
        print(f"  loss_scales: {','.join(str(item) for item in result['loss_scales'])}")
        print(f"  ok/runs: {result['ok_run_count']}/{result['run_count']}")
        print(f"  summary: {args.summary_json}")
    if args.fail_on_row_failure and summary["status"] != "ok":
        return 1
    return 0


def run_sweep(
    *,
    root: Path,
    image: str,
    profiles: Iterable[str],
    seeds: Iterable[int],
    loss_scales: Iterable[float],
    require_netem: bool,
    netem_drain_s: float,
    robot_count: int = 1,
    reuse_build: bool = False,
    prepare_reused_build: bool = True,
    cleanup_reused_build: bool = True,
    control_proactive_data_repeats: int | None = None,
    state_proactive_data_repeats: int | None = None,
) -> dict[str, object]:
    profile_list = list(profiles)
    seed_list = list(seeds)
    loss_scale_list = list(loss_scales)
    if control_proactive_data_repeats is not None and control_proactive_data_repeats < 0:
        raise ValueError("control_proactive_data_repeats must be non-negative")
    if state_proactive_data_repeats is not None and state_proactive_data_repeats < 0:
        raise ValueError("state_proactive_data_repeats must be non-negative")
    if robot_count <= 0:
        raise ValueError("robot_count must be positive")
    matrices = []
    runs = []
    build_performed = False
    if reuse_build and prepare_reused_build:
        build_performed = ensure_live_plan_build(root, image, clean=True)
    try:
        for loss_scale in loss_scale_list:
            matrix = run_matrix(
                root=root,
                image=image,
                profiles=profile_list,
                seeds=seed_list,
                enable_netem=True,
                require_netem=require_netem,
                netem_loss_scale=loss_scale,
                netem_drain_s=netem_drain_s,
                robot_count=robot_count,
                schema_version=MATRIX_SCHEMA_VERSION,
                reuse_build=reuse_build,
                prepare_reused_build=False,
                cleanup_reused_build=False,
                control_proactive_data_repeats=control_proactive_data_repeats,
                state_proactive_data_repeats=state_proactive_data_repeats,
            )
            matrices.append(matrix)
            for run in matrix["runs"]:  # type: ignore[index]
                row = dict(run)
                row["loss_scale"] = loss_scale
                row["failure_kind"] = classify_failure(row)
                runs.append(row)
    finally:
        if reuse_build and cleanup_reused_build:
            cleanup_live_plan_build(root, image)
    sweep_summary = summarize_sweep(runs, profiles=profile_list)
    status = "ok" if sweep_summary["failed_run_count"] == 0 else "partial"
    if sweep_summary["ok_run_count"] == 0:
        status = "failed"
    return {
        "schema_version": SCHEMA_VERSION,
        "status": status,
        "image": image,
        "profiles": profile_list,
        "seeds": seed_list,
        "loss_scales": loss_scale_list,
        "robot_count": robot_count,
        "netem_required": require_netem,
        "netem_drain_s": netem_drain_s,
        "reuse_build": reuse_build,
        "build_performed": build_performed,
        "control_proactive_data_repeats": control_proactive_data_repeats,
        "state_proactive_data_repeats": state_proactive_data_repeats,
        "seed_semantics": "repetition_id_only; current tc netem image does not support explicit RNG seed",
        "matrices": matrices,
        "runs": runs,
        "summary": sweep_summary,
    }


def summarize_sweep(
    runs: Iterable[dict[str, object]],
    *,
    profiles: Iterable[str],
) -> dict[str, object]:
    rows = list(runs)
    profile_set = set(profiles)
    by_loss: dict[float, list[dict[str, object]]] = {}
    by_pair: dict[tuple[str, float], list[dict[str, object]]] = {}
    for row in rows:
        loss_scale = _float(row.get("loss_scale"))
        profile = str(row.get("profile", ""))
        if row.get("failure_kind") in (None, ""):
            row["failure_kind"] = classify_failure(row)
        by_loss.setdefault(loss_scale, []).append(row)
        by_pair.setdefault((profile, loss_scale), []).append(row)

    loss_rows = []
    max_all_profiles_ok: float | None = None
    for loss_scale, group in sorted(by_loss.items()):
        ok_runs = sum(1 for row in group if row.get("status") == "ok")
        profiles_ok = {
            str(row.get("profile", ""))
            for row in group
            if row.get("status") == "ok"
        }
        all_profiles_ok = profile_set.issubset(profiles_ok)
        if all_profiles_ok:
            max_all_profiles_ok = loss_scale
        loss_rows.append(
            {
                "loss_scale": loss_scale,
                "runs": len(group),
                "ok_runs": ok_runs,
                "failed_runs": len(group) - ok_runs,
                "netem_applied_runs": sum(1 for row in group if _all_netem_applied(row)),
                "failure_kind_counts": failure_kind_counts(group),
                "all_profiles_ok": all_profiles_ok,
                "control_delivery_latency_ms_mean": _mean_metric(
                    group,
                    "control_delivery_latency_ms_mean",
                ),
                "state_delivery_latency_ms_mean": _mean_metric(
                    group,
                    "state_delivery_latency_ms_mean",
                ),
            }
        )

    pair_rows = []
    first_failed_by_profile: dict[str, float] = {}
    for (profile, loss_scale), group in sorted(by_pair.items(), key=lambda item: (item[0][0], item[0][1])):
        ok_runs = sum(1 for row in group if row.get("status") == "ok")
        failed_runs = len(group) - ok_runs
        if failed_runs > 0 and profile not in first_failed_by_profile:
            first_failed_by_profile[profile] = loss_scale
        pair_rows.append(
            {
                "profile": profile,
                "loss_scale": loss_scale,
                "runs": len(group),
                "ok_runs": ok_runs,
                "failed_runs": failed_runs,
                "netem_applied_runs": sum(1 for row in group if _all_netem_applied(row)),
                "failure_kind_counts": failure_kind_counts(group),
                "control_delivery_latency_ms_mean": _mean_metric(
                    group,
                    "control_delivery_latency_ms_mean",
                ),
                "state_delivery_latency_ms_mean": _mean_metric(
                    group,
                    "state_delivery_latency_ms_mean",
                ),
                "control_redundant_frames_mean": _mean_metric(
                    group,
                    "control_redundant_frames",
                ),
                "control_duplicate_data_frames_deduped_mean": _mean_metric(
                    group,
                    "control_duplicate_data_frames_deduped",
                ),
            }
        )
    return {
        "run_count": len(rows),
        "ok_run_count": sum(1 for row in rows if row.get("status") == "ok"),
        "failed_run_count": sum(1 for row in rows if row.get("status") != "ok"),
        "netem_applied_run_count": sum(1 for row in rows if _all_netem_applied(row)),
        "failure_kind_counts": failure_kind_counts(rows),
        "max_all_profiles_ok_loss_scale": max_all_profiles_ok,
        "first_failed_loss_scale_by_profile": first_failed_by_profile,
        "loss_scales": loss_rows,
        "profile_loss_scales": pair_rows,
    }


def render_markdown(summary: dict[str, object]) -> str:
    sweep = _dict(summary.get("summary"))
    lines = [
        "# RMW Multi-Robot Live Stochastic Netem Sweep V1",
        "",
        f"- Status: `{summary.get('status')}`",
        f"- Image: `{summary.get('image')}`",
        f"- Profiles: `{', '.join(str(item) for item in summary.get('profiles', []))}`",
        f"- Seeds: `{', '.join(str(item) for item in summary.get('seeds', []))}`",
        f"- Seed semantics: `{summary.get('seed_semantics')}`",
        f"- Loss scales: `{', '.join(str(item) for item in summary.get('loss_scales', []))}`",
        f"- Netem required: `{summary.get('netem_required')}`",
        f"- Reuse build: `{summary.get('reuse_build', False)}`",
        f"- Build performed: `{summary.get('build_performed', False)}`",
        f"- Control proactive data repeats: `{summary.get('control_proactive_data_repeats')}`",
        f"- State proactive data repeats: `{summary.get('state_proactive_data_repeats')}`",
        f"- Runs: `{sweep.get('ok_run_count', 0)}/{sweep.get('run_count', 0)} ok`",
        f"- Max all-profiles-ok loss scale: `{sweep.get('max_all_profiles_ok_loss_scale')}`",
        f"- Failure kinds: `{format_counts(_dict(sweep.get('failure_kind_counts')))}`",
        "",
        "## Loss Scale Summary",
        "",
        "| loss scale | ok/runs | netem applied | all profiles ok | failure kinds | control latency ms | state latency ms |",
        "|---:|---:|---:|---:|---|---:|---:|",
    ]
    for row in sweep.get("loss_scales", []):
        if not isinstance(row, dict):
            continue
        lines.append(
            "| "
            f"{_format(row.get('loss_scale'))} | "
            f"{int(row.get('ok_runs', 0))}/{int(row.get('runs', 0))} | "
            f"{int(row.get('netem_applied_runs', 0))}/{int(row.get('runs', 0))} | "
            f"{bool(row.get('all_profiles_ok', False))} | "
            f"{format_counts(_dict(row.get('failure_kind_counts')))} | "
            f"{_format(row.get('control_delivery_latency_ms_mean'))} | "
            f"{_format(row.get('state_delivery_latency_ms_mean'))} |"
        )
    lines.extend(
        [
            "",
            "## Profile/Loss Detail",
            "",
            "| profile | loss scale | ok/runs | failure kinds | control redundant | control de-dup | control latency ms | state latency ms |",
            "|---|---:|---:|---|---:|---:|---:|---:|",
        ]
    )
    for row in sweep.get("profile_loss_scales", []):
        if not isinstance(row, dict):
            continue
        lines.append(
            "| "
            f"{row.get('profile')} | "
            f"{_format(row.get('loss_scale'))} | "
            f"{int(row.get('ok_runs', 0))}/{int(row.get('runs', 0))} | "
            f"{format_counts(_dict(row.get('failure_kind_counts')))} | "
            f"{_format(row.get('control_redundant_frames_mean'))} | "
            f"{_format(row.get('control_duplicate_data_frames_deduped_mean'))} | "
            f"{_format(row.get('control_delivery_latency_ms_mean'))} | "
            f"{_format(row.get('state_delivery_latency_ms_mean'))} |"
        )
    failed_runs = [row for row in summary.get("runs", []) if isinstance(row, dict) and row.get("status") != "ok"]
    if failed_runs:
        lines.extend(
            [
                "",
                "## Failure Detail",
                "",
                "| kind | profile | loss scale | seed | statuses | payloads control/state | subscriber records | router ACK forwarded primary/backup | exception |",
                "|---|---|---:|---:|---|---:|---:|---:|---|",
            ]
        )
        for row in failed_runs:
            statuses = ",".join(
                [
                    f"cpub={row.get('control_publisher_status', '')}",
                    f"spub={row.get('state_publisher_status', '')}",
                    f"csub={row.get('control_subscriber_status', '')}",
                    f"ssub={row.get('state_subscriber_status', '')}",
                    f"pr={row.get('primary_router_status', '')}",
                    f"br={row.get('backup_router_status', '')}",
                ]
            )
            primary_ack = (
                f"{int(row.get('primary_ack_nack_forwarded', 0))}/"
                f"{int(row.get('primary_expected_ack_nack_forwarded', 0))}"
            )
            backup_ack = (
                f"{int(row.get('backup_ack_nack_forwarded', 0))}/"
                f"{int(row.get('backup_expected_ack_nack_forwarded', 0))}"
            )
            exception = compact_exception(row)
            lines.append(
                "| "
                f"{row.get('failure_kind', classify_failure(row))} | "
                f"{row.get('profile')} | "
                f"{_format(row.get('loss_scale'))} | "
                f"{row.get('seed')} | "
                f"{statuses} | "
                f"{int(row.get('control_payload_count', 0))}/{int(row.get('state_payload_count', 0))} | "
                f"{int(row.get('subscriber_record_count', 0))} | "
                f"{primary_ack}/{backup_ack} | "
                f"{exception} |"
            )
    lines.extend(
        [
            "",
            "## Interpretation",
            "",
            "- `partial` means the sweep completed and exposed at least one failing operating point.",
            "- `failure_kind` separates harness/netem/component failures from actual message delivery failures.",
            "- `max_all_profiles_ok_loss_scale` is the strongest tested loss multiplier where every profile had at least one successful repetition.",
            "- Seeds are repetition identifiers; this image's `tc netem` does not support deterministic RNG seeding.",
            "",
        ]
    )
    return "\n".join(lines)


def parse_loss_scales(value: str) -> list[float]:
    try:
        parsed = [float(part.strip()) for part in value.split(",") if part.strip()]
    except ValueError as exc:
        raise SystemExit("--loss-scales must be a comma-separated number list") from exc
    if not parsed or any(item < 0.0 for item in parsed):
        raise SystemExit("--loss-scales must contain non-negative numbers")
    return list(dict.fromkeys(parsed))


def classify_failure(row: dict[str, object]) -> str:
    if row.get("status") == "ok":
        return "none"
    if row.get("netem_required") and not _all_netem_applied(row):
        return "netem_not_applied"
    failure_returncode = row.get("failure_returncode")
    if failure_returncode not in (None, "", 0):
        return "harness_exception"
    if _looks_like_delivery_failure(row):
        return "delivery_failed"
    for key in COMPONENT_RETURNCODE_KEYS:
        returncode = _optional_int(row.get(key))
        if returncode is not None and returncode not in (-999, 0):
            return "component_failed"
    for key in COMPONENT_STATUS_KEYS:
        status = str(row.get(key, ""))
        if status in {"failed", "parse_failed", "missing"}:
            return "component_failed"
    if _looks_like_harness_failure_without_diagnostics(row):
        return "harness_exception_missing_diagnostics"
    if int(_float(row.get("control_payload_count"))) < 3 or int(_float(row.get("state_payload_count"))) < 3:
        return "delivery_failed"
    if int(_float(row.get("subscriber_record_count"))) < 6 or int(_float(row.get("router_record_count"))) < 6:
        return "telemetry_missing"
    if row.get("control_duplicate_ack_required", True) and int(
        _float(row.get("control_duplicate_ack_received"))
    ) < 1:
        return "contract_evidence_failed"
    if row.get("control_duplicate_dedup_required", True) and int(
        _float(row.get("control_duplicate_data_frames_deduped"))
    ) < 1:
        return "contract_evidence_failed"
    return "unknown_failed"


def failure_kind_counts(rows: Iterable[dict[str, object]]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for row in rows:
        if row.get("status") == "ok":
            continue
        kind = str(row.get("failure_kind") or classify_failure(row))
        counts[kind] = counts.get(kind, 0) + 1
    return counts


def format_counts(counts: dict[str, object]) -> str:
    if not counts:
        return "-"
    parts = []
    for key in sorted(counts):
        parts.append(f"{key}:{int(_float(counts[key]))}")
    return ",".join(parts)


def compact_exception(row: dict[str, object]) -> str:
    phase = str(row.get("failure_phase", ""))
    returncode = row.get("failure_returncode")
    stderr = str(row.get("failure_stderr_excerpt", ""))
    stdout = str(row.get("failure_stdout_excerpt", ""))
    logs = str(row.get("failure_container_log_excerpt", ""))
    parts = []
    if phase:
        parts.append(f"phase={phase}")
    if returncode not in (None, ""):
        parts.append(f"rc={returncode}")
    excerpt = stderr or stdout or logs
    if excerpt:
        parts.append(markdown_cell(excerpt, max_chars=120))
    return "; ".join(parts) if parts else "-"


def markdown_cell(value: str, *, max_chars: int = 160) -> str:
    text = " ".join(str(value).split())
    text = text.replace("|", "/")
    if len(text) <= max_chars:
        return text
    return text[: max_chars - 3] + "..."


def _looks_like_harness_failure_without_diagnostics(row: dict[str, object]) -> bool:
    statuses = [str(row.get(key, "")) for key in COMPONENT_STATUS_KEYS]
    returncodes = [_optional_int(row.get(key)) for key in COMPONENT_RETURNCODE_KEYS]
    no_component_snapshot = all(status == "" for status in statuses)
    default_returncodes = all(returncode in (None, -999) for returncode in returncodes)
    no_records = int(_float(row.get("router_record_count"))) == 0 and int(
        _float(row.get("subscriber_record_count"))
    ) == 0
    return no_component_snapshot and default_returncodes and no_records


def _looks_like_delivery_failure(row: dict[str, object]) -> bool:
    control_payloads = int(_float(row.get("control_payload_count")))
    state_payloads = int(_float(row.get("state_payload_count")))
    if control_payloads >= 3 and state_payloads >= 3:
        return False
    for key in NON_SUBSCRIBER_RETURNCODE_KEYS:
        returncode = _optional_int(row.get(key))
        if returncode is not None and returncode not in (-999, 0):
            return False
    for key in NON_SUBSCRIBER_STATUS_KEYS:
        status = str(row.get(key, ""))
        if status in {"failed", "parse_failed", "missing"}:
            return False
    return True


def _all_netem_applied(row: dict[str, object]) -> bool:
    if not row.get("netem_enabled"):
        return False
    statuses = _dict(row.get("netem_status"))
    for path_id in ("primary_wifi", "backup_5g"):
        status = statuses.get(path_id)
        if not isinstance(status, dict) or status.get("status") != "applied":
            return False
    return True


def _mean_metric(rows: Iterable[dict[str, object]], key: str) -> float:
    values = [_float(row.get(key, 0.0)) for row in rows]
    return sum(values) / len(values) if values else 0.0


def _dict(value: object) -> dict[str, object]:
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


if __name__ == "__main__":
    raise SystemExit(main())

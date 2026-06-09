"""Run direct ROS 2 RMW pub/sub netem probes across RMWs, profiles, and seeds."""

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
    write_json,
    write_markdown,
)
from scripts.run_rmw_docker_multi_robot_live_telemetry_plan_probe import DEFAULT_IMAGE
from scripts.run_ros2_direct_rmw_netem_probe import (
    DEFAULT_RMWS,
    SCHEMA_VERSION as PROBE_SCHEMA_VERSION,
    run_probe,
)


SCHEMA_VERSION = "fleetrmw.ros2_direct_rmw_netem_matrix.v1"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--image", default=DEFAULT_IMAGE)
    parser.add_argument("--rmws", default=DEFAULT_RMWS)
    parser.add_argument("--profiles", default=DEFAULT_PROFILES)
    parser.add_argument("--seeds", default=DEFAULT_SEEDS)
    parser.add_argument("--netem-loss-scale", type=float, default=0.1)
    parser.add_argument("--require-netem", action="store_true")
    parser.add_argument("--samples", type=int, default=3)
    parser.add_argument("--robot-count", type=int, default=1)
    parser.add_argument("--publish-interval-ms", type=int, default=500)
    parser.add_argument("--timeout-s", type=float, default=15.0)
    parser.add_argument(
        "--summary-json",
        type=Path,
        default=Path("results_rmw_socket/ros2_direct_rmw_netem_matrix_summary.json"),
    )
    parser.add_argument(
        "--markdown",
        type=Path,
        default=Path("results_rmw_socket/ros2_direct_rmw_netem_matrix_report.md"),
    )
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    rmws = parse_csv(args.rmws, "--rmws")
    profiles = parse_profiles(args.profiles)
    seeds = parse_ints(args.seeds, "--seeds")
    summary = run_matrix(
        root=ROOT,
        image=args.image,
        rmws=rmws,
        profiles=profiles,
        seeds=seeds,
        netem_loss_scale=args.netem_loss_scale,
        require_netem=args.require_netem,
        samples=args.samples,
        robot_count=args.robot_count,
        publish_interval_ms=args.publish_interval_ms,
        timeout_s=args.timeout_s,
    )
    write_json(summary, args.summary_json)
    write_markdown(render_markdown(summary), args.markdown)

    result = {
        "schema_version": summary["schema_version"],
        "status": summary["status"],
        "run_count": summary["summary"]["run_count"],
        "ok_run_count": summary["summary"]["ok_run_count"],
        "skipped_run_count": summary["summary"]["skipped_run_count"],
        "failed_run_count": summary["summary"]["failed_run_count"],
        "summary": str(args.summary_json),
        "markdown": str(args.markdown),
    }
    if args.json:
        print(json.dumps(result, sort_keys=True))
    else:
        print("ros2-direct-rmw-netem-matrix")
        print(f"  status: {result['status']}")
        print(f"  ok/skipped/failed: {result['ok_run_count']}/{result['skipped_run_count']}/{result['failed_run_count']}")
        print(f"  summary: {args.summary_json}")
    return 0 if summary["status"] in {"ok", "partial"} else 1


def run_matrix(
    *,
    root: Path,
    image: str,
    rmws: Iterable[str],
    profiles: Iterable[str],
    seeds: Iterable[int],
    netem_loss_scale: float,
    require_netem: bool,
    samples: int,
    robot_count: int,
    publish_interval_ms: int,
    timeout_s: float,
) -> dict[str, object]:
    rmw_list = list(rmws)
    profile_list = list(profiles)
    seed_list = list(seeds)
    rows = []
    for rmw in rmw_list:
        for profile in profile_list:
            for seed in seed_list:
                probe = run_probe(
                    root=root,
                    image=image,
                    rmw=rmw,
                    profile=profile,
                    enable_netem=True,
                    require_netem=require_netem,
                    netem_loss_scale=netem_loss_scale,
                    repetition_seed=seed,
                    samples=samples,
                    robot_count=robot_count,
                    publish_interval_ms=publish_interval_ms,
                    timeout_s=timeout_s,
                )
                rows.append(row_from_probe(probe, seed=seed))
    matrix_summary = summarize_rows(rows)
    return {
        "schema_version": SCHEMA_VERSION,
        "probe_schema_version": PROBE_SCHEMA_VERSION,
        "status": matrix_summary["status"],
        "image": image,
        "rmws": rmw_list,
        "profiles": profile_list,
        "seeds": seed_list,
        "netem_loss_scale": netem_loss_scale,
        "netem_required": require_netem,
        "samples": samples,
        "robot_count": robot_count,
        "runs": rows,
        "summary": matrix_summary,
    }


def row_from_probe(probe: dict[str, object], *, seed: int) -> dict[str, object]:
    return {
        "schema_version": "fleetrmw.ros2_direct_rmw_netem_matrix_run.v1",
        "status": str(probe.get("status", "missing")),
        "reason": direct_failure_reason(probe),
        "rmw": str(probe.get("rmw", "")),
        "profile": str(probe.get("profile", "")),
        "seed": seed,
        "robot_count": int(_float(probe.get("robot_count"))),
        "topic_count": int(_float(probe.get("topic_count"))),
        "netem_applied": _netem_applied(probe),
        "control_payload_count": int(_float(probe.get("control_payload_count"))),
        "state_payload_count": int(_float(probe.get("state_payload_count"))),
        "control_expected_count": int(_float(probe.get("control_expected_count"))),
        "state_expected_count": int(_float(probe.get("state_expected_count"))),
        "control_delivery_ratio": _float(probe.get("control_delivery_ratio")),
        "state_delivery_ratio": _float(probe.get("state_delivery_ratio")),
        "control_latency_ms_mean": _float(probe.get("control_latency_ms_mean")),
        "state_latency_ms_mean": _float(probe.get("state_latency_ms_mean")),
        "control_latency_ms_p95": _float(probe.get("control_latency_ms_p95")),
        "state_latency_ms_p95": _float(probe.get("state_latency_ms_p95")),
        "min_topic_delivery_ratio": _float(probe.get("min_topic_delivery_ratio")),
        "rmw_available": bool(_dict(probe.get("rmw_probe")).get("available", False)),
    }


def direct_failure_reason(probe: dict[str, object]) -> str:
    explicit = str(probe.get("reason", ""))
    status = str(probe.get("status", ""))
    if status in {"ok", "skipped"}:
        return explicit
    if explicit and explicit != "subscriber_failed":
        return explicit
    if int(_float(probe.get("publisher_returncode"))) != 0:
        return "publisher_failed"
    if bool(probe.get("netem_required", False)) and not _netem_applied(probe):
        return "netem_not_applied"

    expected = int(_float(probe.get("samples")))
    expected_control = int(_float(probe.get("control_expected_count"))) or expected
    expected_state = int(_float(probe.get("state_expected_count"))) or expected
    control_count = int(_float(probe.get("control_payload_count")))
    state_count = int(_float(probe.get("state_payload_count")))
    missing = []
    if control_count == 0 or (expected_control and control_count < expected_control):
        missing.append("control")
    if state_count == 0 or (expected_state and state_count < expected_state):
        missing.append("state")
    if missing:
        return "delivery_failed:missing_" + "_".join(missing)
    if explicit:
        return explicit
    if int(_float(probe.get("subscriber_returncode"))) != 0:
        return "subscriber_failed"
    return "probe_failed"


def summarize_rows(rows: Iterable[dict[str, object]]) -> dict[str, object]:
    row_list = list(rows)
    by_rmw_profile: dict[tuple[str, str], list[dict[str, object]]] = {}
    for row in row_list:
        by_rmw_profile.setdefault((str(row.get("rmw", "")), str(row.get("profile", ""))), []).append(row)
    groups = []
    for (rmw, profile), group in sorted(by_rmw_profile.items()):
        groups.append(
            {
                "rmw": rmw,
                "profile": profile,
                "runs": len(group),
                "ok_runs": sum(1 for row in group if row.get("status") == "ok"),
                "skipped_runs": sum(1 for row in group if row.get("status") == "skipped"),
                "failed_runs": sum(1 for row in group if row.get("status") not in {"ok", "skipped"}),
                "netem_applied_runs": sum(1 for row in group if row.get("netem_applied")),
                "control_delivery_ratio_mean": _mean_metric(group, "control_delivery_ratio"),
                "state_delivery_ratio_mean": _mean_metric(group, "state_delivery_ratio"),
                "min_topic_delivery_ratio_mean": _mean_metric(group, "min_topic_delivery_ratio"),
                "control_latency_ms_p95_mean": _mean_metric(group, "control_latency_ms_p95"),
                "state_latency_ms_p95_mean": _mean_metric(group, "state_latency_ms_p95"),
            }
        )
    ok_runs = sum(1 for row in row_list if row.get("status") == "ok")
    skipped_runs = sum(1 for row in row_list if row.get("status") == "skipped")
    failed_runs = sum(1 for row in row_list if row.get("status") not in {"ok", "skipped"})
    if failed_runs == 0 and skipped_runs == 0:
        status = "ok"
    elif ok_runs > 0:
        status = "partial"
    else:
        status = "failed"
    return {
        "status": status,
        "run_count": len(row_list),
        "ok_run_count": ok_runs,
        "skipped_run_count": skipped_runs,
        "failed_run_count": failed_runs,
        "groups": groups,
    }


def render_markdown(summary: dict[str, object]) -> str:
    matrix = _dict(summary.get("summary"))
    lines = [
        "# ROS 2 Direct RMW Netem Matrix V1",
        "",
        f"- Status: `{summary.get('status')}`",
        f"- Image: `{summary.get('image')}`",
        f"- RMWs: `{', '.join(str(item) for item in summary.get('rmws', []))}`",
        f"- Profiles: `{', '.join(str(item) for item in summary.get('profiles', []))}`",
        f"- Seeds: `{', '.join(str(item) for item in summary.get('seeds', []))}`",
        f"- Robot count: `{summary.get('robot_count', 1)}`",
        f"- Netem loss scale: `{summary.get('netem_loss_scale')}`",
        f"- Netem required: `{summary.get('netem_required')}`",
        f"- Runs: `{matrix.get('ok_run_count', 0)}/{matrix.get('run_count', 0)} ok`, `{matrix.get('skipped_run_count', 0)}` skipped",
        "",
        "## Groups",
        "",
        "| rmw | profile | ok/skipped/failed | netem applied | control delivery | state delivery | min topic delivery | control p95 ms | state p95 ms |",
        "|---|---|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for row in matrix.get("groups", []):
        if not isinstance(row, dict):
            continue
        lines.append(
            "| "
            f"{row.get('rmw')} | "
            f"{row.get('profile')} | "
            f"{int(row.get('ok_runs', 0))}/{int(row.get('skipped_runs', 0))}/{int(row.get('failed_runs', 0))} | "
            f"{int(row.get('netem_applied_runs', 0))}/{int(row.get('runs', 0))} | "
            f"{_format(row.get('control_delivery_ratio_mean'))} | "
            f"{_format(row.get('state_delivery_ratio_mean'))} | "
            f"{_format(row.get('min_topic_delivery_ratio_mean'))} | "
            f"{_format(row.get('control_latency_ms_p95_mean'))} | "
            f"{_format(row.get('state_latency_ms_p95_mean'))} |"
        )
    failed_rows = [
        row for row in summary.get("runs", [])
        if isinstance(row, dict) and row.get("status") not in {"ok", "skipped"}
    ]
    if failed_rows:
        lines.extend(
            [
                "",
                "## Failed Rows",
                "",
                "| rmw | profile | seed | reason | control payloads | state payloads |",
                "|---|---|---:|---|---:|---:|",
            ]
        )
        for row in failed_rows:
            lines.append(
                "| "
                f"{row.get('rmw')} | "
                f"{row.get('profile')} | "
                f"{int(_float(row.get('seed')))} | "
                f"{row.get('reason', '') or '-'} | "
                f"{int(_float(row.get('control_payload_count')))} | "
                f"{int(_float(row.get('state_payload_count')))} |"
            )
    lines.extend(
        [
            "",
            "## Interpretation",
            "",
            "- `skipped` means the requested RMW package is not installed in the Docker image.",
            "- This matrix is the direct ROS 2 pub/sub baseline path; it does not include FleetRMW router redundancy or QoE path planning.",
            "- Use it as the same-envelope baseline seed before widening to larger robot/topic counts.",
            "",
        ]
    )
    return "\n".join(lines)


def parse_csv(value: str, option: str) -> list[str]:
    parsed = [part.strip() for part in value.split(",") if part.strip()]
    if not parsed:
        raise SystemExit(f"{option} must contain at least one value")
    return list(dict.fromkeys(parsed))


def _netem_applied(probe: dict[str, object]) -> bool:
    status = _dict(_dict(probe.get("netem_status")).get("direct_pub"))
    return status.get("status") == "applied"


def _mean_metric(rows: Iterable[dict[str, object]], key: str) -> float:
    values = [_float(row.get(key)) for row in rows if row.get("status") == "ok"]
    return sum(values) / len(values) if values else 0.0


def _dict(value: object) -> dict[str, object]:
    return value if isinstance(value, dict) else {}


def _float(value: object) -> float:
    try:
        return float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return 0.0


def _format(value: object) -> str:
    return f"{_float(value):.3f}"


if __name__ == "__main__":
    raise SystemExit(main())

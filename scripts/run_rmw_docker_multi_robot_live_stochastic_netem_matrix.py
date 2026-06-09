"""Run the Docker multi-robot live RMW probe with stochastic tc-netem loss."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.run_rmw_docker_multi_robot_live_netem_matrix import render_markdown
from scripts.run_rmw_docker_multi_robot_live_telemetry_matrix import (
    DEFAULT_PROFILES,
    DEFAULT_SEEDS,
    parse_ints,
    parse_profiles,
    run_matrix,
    write_json,
    write_markdown,
)
from scripts.run_rmw_docker_multi_robot_live_telemetry_plan_probe import DEFAULT_IMAGE


SCHEMA_VERSION = "fleetrmw.rmw_multi_robot_live_stochastic_netem_matrix.v1"
DEFAULT_LOSS_SCALE = 0.1


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--image", default=DEFAULT_IMAGE)
    parser.add_argument("--profiles", default=DEFAULT_PROFILES)
    parser.add_argument("--seeds", default=DEFAULT_SEEDS)
    parser.add_argument(
        "--summary-json",
        type=Path,
        default=Path("results_rmw_socket/docker_multi_robot_live_stochastic_netem_matrix_summary.json"),
    )
    parser.add_argument(
        "--markdown",
        type=Path,
        default=Path("results_rmw_socket/docker_multi_robot_live_stochastic_netem_matrix_report.md"),
    )
    parser.add_argument("--require-netem", action="store_true")
    parser.add_argument(
        "--netem-loss-scale",
        type=float,
        default=DEFAULT_LOSS_SCALE,
        help="multiplier applied to profile random packet loss",
    )
    parser.add_argument(
        "--netem-drain-s",
        type=float,
        default=2.0,
        help="seconds to keep router containers alive after router exit so qdisc queues drain",
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
        enable_netem=True,
        require_netem=args.require_netem,
        netem_loss_scale=args.netem_loss_scale,
        netem_drain_s=args.netem_drain_s,
        schema_version=SCHEMA_VERSION,
        reuse_build=args.reuse_build,
        control_proactive_data_repeats=args.control_proactive_data_repeats,
        state_proactive_data_repeats=args.state_proactive_data_repeats,
    )
    write_json(summary, args.summary_json)
    write_markdown(render_markdown(summary).replace(
        "# RMW Multi-Robot Live Netem Matrix V1",
        "# RMW Multi-Robot Live Stochastic Netem Matrix V1",
        1,
    ), args.markdown)

    result = {
        "schema_version": summary["schema_version"],
        "status": summary["status"],
        "image": summary["image"],
        "profiles": summary["profiles"],
        "seeds": summary["seeds"],
        "netem_required": summary["netem_required"],
        "netem_loss_scale": summary["netem_loss_scale"],
        "netem_drain_s": summary["netem_drain_s"],
        "reuse_build": summary["reuse_build"],
        "build_performed": summary["build_performed"],
        "control_proactive_data_repeats": summary["control_proactive_data_repeats"],
        "state_proactive_data_repeats": summary["state_proactive_data_repeats"],
        "seed_semantics": summary["seed_semantics"],
        "runs": len(summary["runs"]),
        "summary": str(args.summary_json),
        "markdown": str(args.markdown),
    }
    if args.json:
        print(json.dumps(result, sort_keys=True))
    else:
        print("fleetrmw-multi-robot-live-stochastic-netem-matrix")
        print(f"  status: {result['status']}")
        print(f"  image: {result['image']}")
        print(f"  profiles: {','.join(result['profiles'])}")
        print(f"  netem_loss_scale: {result['netem_loss_scale']}")
        print(f"  runs: {result['runs']}")
        print(f"  summary: {args.summary_json}")
    return 0 if summary["status"] == "ok" else 1


if __name__ == "__main__":
    raise SystemExit(main())

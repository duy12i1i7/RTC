"""Generate the next Lagrangian variant from measured netem outcomes."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from fleetqox.lagrangian_adaptation import (
    OutcomeTargets,
    adapt_from_repeated_summary,
    load_variant_manifest,
    write_adaptation_json,
    write_adaptation_markdown,
)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--summary", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--next-label", default="lag_adapt_001")
    parser.add_argument("--source-label")
    parser.add_argument("--deadline-miss-target", type=float, default=0.002)
    parser.add_argument("--control-starvation-target", type=float, default=2.0)
    parser.add_argument("--loss-target", type=float, default=0.012)
    parser.add_argument("--reference-policy", default="fleetqox_predictive")
    parser.add_argument(
        "--output-json",
        type=Path,
        default=Path("results_sidecar_repeated/lag_adaptation_v1.json"),
    )
    parser.add_argument(
        "--markdown",
        type=Path,
        default=Path("docs/LAGRANGIAN_OUTCOME_ADAPTATION_V1.md"),
    )
    parser.add_argument("--title", default="Lagrangian Outcome Adaptation V1")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    summary = json.loads(args.summary.read_text(encoding="utf-8"))
    variants = load_variant_manifest(args.manifest)
    adaptation = adapt_from_repeated_summary(
        summary,
        variants,
        next_label=args.next_label,
        source_label=args.source_label,
        targets=OutcomeTargets(
            deadline_miss_ratio=args.deadline_miss_target,
            control_starvation_events=args.control_starvation_target,
            loss_ratio=args.loss_target,
            reference_policy=args.reference_policy,
        ),
    )
    write_adaptation_json(adaptation, args.output_json)
    write_adaptation_markdown(adaptation, args.markdown, title=args.title)

    result = {
        "output_json": str(args.output_json),
        "markdown": str(args.markdown),
        "source_label": adaptation["source_label"],
        "next_label": adaptation["next_label"],
        "next_params": adaptation["next_params"],
        "run_command": adaptation["run_command"],
    }
    if args.json:
        print(json.dumps(result, sort_keys=True))
        return
    print(f"Lagrangian adaptation written: {args.markdown}")
    print(f"Lagrangian adaptation JSON written: {args.output_json}")


if __name__ == "__main__":
    main()

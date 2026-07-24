"""Validate OMNeT++/INET project sources and large manifest inputs.

Runtime/parity is executed by ``run_omnetpp_docker_parity.py`` in the pinned
OMNeT++ 6.4.0/INET 4.7.0 image. This companion probe validates the in-repo
project source contract, discovers the larger OMNeT++ manifest scenarios,
prepares their FleetQoX CSV traces, and records whether local host commands are
available. It intentionally never infers runtime/parity from source integrity.
"""

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path
import sys
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from fleetqox.testbed import iter_scenarios, load_manifest  # noqa: E402
from scripts.run_t2s_network_sim import (  # noqa: E402
    DEFAULT_MANIFEST,
    prepare_trace_input,
    probe_network_simulators,
)


SCHEMA_VERSION = "fleetqox.omnetpp_template_integrity_probe.v1"
REQUIRED_TEMPLATE_FILES = (
    "external/omnetpp/FleetQoxTraceReplay.ned",
    "external/omnetpp/TraceDrivenUdpApp.ned",
    "external/omnetpp/omnetpp.ini",
    "external/omnetpp/README.md",
    "external/omnetpp/Dockerfile",
    "external/omnetpp/TraceDrivenUdpApp.h",
    "external/omnetpp/TraceDrivenUdpApp.cc",
)
REQUIRED_NED_TOKENS = (
    "network FleetQoxTraceReplay",
    "robot[numRobots]: StandardHost",
    "fleetRouter: StandardHost",
    "TraceDrivenUdpApp",
    "FleetQoxPointToPointLink",
    "socket_.sendTo",
    "OMNETPP_COMMIT",
)
REQUIRED_TRACE_COLUMNS = (
    "timestamp_ms",
    "topic",
    "robot_id",
    "flow_class",
    "bytes",
    "deadline_ms",
)


def template_checks(root: Path) -> dict[str, Any]:
    files: dict[str, bool] = {}
    for relative in REQUIRED_TEMPLATE_FILES:
        files[relative] = (root / relative).exists()
    combined = "\n".join(
        (root / relative).read_text(encoding="utf-8", errors="replace")
        for relative, exists in files.items()
        if exists
    )
    tokens = {token: token in combined for token in REQUIRED_NED_TOKENS}
    return {
        "files": files,
        "required_files_present": all(files.values()),
        "tokens": tokens,
        "required_tokens_present": all(tokens.values()),
    }


def omnetpp_scenarios(manifest_path: Path) -> list[Any]:
    manifest = load_manifest(manifest_path)
    return [
        scenario
        for scenario in iter_scenarios(manifest)
        if scenario.tier == "T2S"
        and str(scenario.config.get("simulator", "")).startswith("omnetpp")
    ]


def validate_trace(path: Path) -> dict[str, Any]:
    try:
        with path.open(newline="", encoding="utf-8") as handle:
            reader = csv.DictReader(handle)
            columns = list(reader.fieldnames or [])
            row_count = sum(1 for _ in reader)
    except OSError as exc:
        return {
            "status": "failed",
            "reason": str(exc),
            "columns": [],
            "row_count": 0,
            "required_columns_present": False,
        }
    return {
        "status": "ok",
        "columns": columns,
        "row_count": row_count,
        "required_columns_present": all(column in columns for column in REQUIRED_TRACE_COLUMNS),
    }


def run_probe(
    *,
    root: Path,
    manifest_path: Path,
    output_dir: Path,
    require_runtime: bool,
) -> dict[str, Any]:
    checks = template_checks(root)
    scenarios = omnetpp_scenarios(manifest_path)
    output_dir.mkdir(parents=True, exist_ok=True)
    prepared: list[dict[str, Any]] = []
    for scenario in scenarios:
        trace_path, packet_rows = prepare_trace_input(scenario, output_dir)
        validation = validate_trace(trace_path)
        prepared.append(
            {
                "scenario": scenario.name,
                "simulator": scenario.config.get("simulator"),
                "robots": scenario.config.get("robots"),
                "network": scenario.config.get("network"),
                "trace_path": str(trace_path.relative_to(root) if trace_path.is_relative_to(root) else trace_path),
                "packet_rows": packet_rows,
                "trace_validation": validation,
            }
    )
    probe = probe_network_simulators()
    runtime_ready = bool(probe.get("omnetpp_ready"))
    missing_runtime_commands = [
        command
        for command in ("opp_run", "nedtool")
        if not probe.get(command)
    ]
    runtime_executed = False
    runtime_gap_reason = (
        "local_omnetpp_commands_missing_use_pinned_docker_runner"
        if missing_runtime_commands
        else "local_runtime_available_but_not_executed_by_source_probe"
    )
    runtime_gap_next_step = (
        "run scripts/run_omnetpp_docker_parity.py with the pinned Docker image"
        if missing_runtime_commands
        else "run scripts/run_omnetpp_docker_parity.py for runtime/parity evidence"
    )
    parity_blocker = (
        "not_evaluated_by_source_integrity_probe_use_docker_parity_runner"
    )
    prepared_ok = bool(prepared) and all(
        row["packet_rows"] > 0
        and row["trace_validation"]["status"] == "ok"
        and row["trace_validation"]["required_columns_present"]
        for row in prepared
    )
    ok = (
        checks["required_files_present"]
        and checks["required_tokens_present"]
        and prepared_ok
        and (runtime_ready or not require_runtime)
    )
    return {
        "schema_version": SCHEMA_VERSION,
        "status": "ok" if ok else "failed",
        "template_files_present": checks["required_files_present"],
        "template_tokens_present": checks["required_tokens_present"],
        "omnetpp_scenario_count": len(scenarios),
        "prepared_trace_count": len(prepared),
        "total_packet_rows": sum(int(row["packet_rows"]) for row in prepared),
        "omnetpp_runtime_ready": runtime_ready,
        "omnetpp_runtime_required": require_runtime,
        "omnetpp_runtime_executed": runtime_executed,
        "omnetpp_missing_runtime_commands": missing_runtime_commands,
        "omnetpp_runtime_gap_reason": runtime_gap_reason,
        "omnetpp_runtime_gap_next_step": runtime_gap_next_step,
        "omnetpp_parity_blocker": parity_blocker,
        "ns3_ready": bool(probe.get("ns3_ready")),
        "ns3_omnetpp_parity_scope": "source_and_large_input_integrity_only",
        "docker_runtime_runner": "scripts/run_omnetpp_docker_parity.py",
        "opp_run": probe.get("opp_run"),
        "nedtool": probe.get("nedtool"),
        "omnetpp_template_integrity_claim": bool(
            checks["required_files_present"]
            and checks["required_tokens_present"]
            and prepared_ok
        ),
        "omnetpp_input_trace_claim": bool(prepared_ok),
        "omnetpp_inet_runtime_claim": False,
        "omnetpp_parity_claim": False,
        "ns3_omnetpp_parity_claim": False,
        "reason": (
            "template_and_inputs_ready_runtime_not_claimed"
            if ok and not runtime_ready
            else "template_and_inputs_ready_runtime_available_but_not_executed"
            if ok
            else "template_or_input_contract_failed"
        ),
        "template_checks": checks,
        "prepared_traces": prepared,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("results_omnetpp/template_inputs_v1"),
    )
    parser.add_argument(
        "--summary-json",
        type=Path,
        default=Path("results_omnetpp/omnetpp_template_integrity_probe_summary.json"),
    )
    parser.add_argument("--require-runtime", action="store_true")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    summary = run_probe(
        root=ROOT,
        manifest_path=args.manifest,
        output_dir=args.output_dir,
        require_runtime=args.require_runtime,
    )
    output = ROOT / args.summary_json
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    if args.json:
        print(json.dumps(summary, sort_keys=True))
    else:
        print(
            f"status={summary['status']} scenarios={summary['omnetpp_scenario_count']} "
            f"traces={summary['prepared_trace_count']} runtime={summary['omnetpp_runtime_ready']} "
            f"parity={summary['omnetpp_parity_claim']}"
        )
    return 0 if summary["status"] == "ok" else 1


if __name__ == "__main__":
    raise SystemExit(main())

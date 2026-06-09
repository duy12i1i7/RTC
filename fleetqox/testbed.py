"""Manifest-driven testbed helpers."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class ExperimentScenario:
    tier: str
    suite: str
    experiment: str
    runner: str
    name: str
    config: dict[str, Any]
    baselines: list[str]
    metrics: list[str]


def load_manifest(path: str | Path) -> dict[str, Any]:
    manifest_path = Path(path)
    with manifest_path.open("r", encoding="utf-8") as handle:
        data = json.load(handle)
    _validate_manifest(data)
    return data


def iter_scenarios(manifest: dict[str, Any]) -> list[ExperimentScenario]:
    scenarios: list[ExperimentScenario] = []
    suite = str(manifest["suite"])
    for tier in manifest["tiers"]:
        for scenario in tier.get("scenarios", []):
            scenarios.append(
                ExperimentScenario(
                    tier=str(tier["tier"]),
                    suite=suite,
                    experiment=str(tier["name"]),
                    runner=str(tier["runner"]),
                    name=str(scenario["name"]),
                    config=dict(scenario),
                    baselines=list(tier.get("baselines", [])),
                    metrics=list(tier.get("metrics", [])),
                )
            )
    return scenarios


def _validate_manifest(data: dict[str, Any]) -> None:
    if "suite" not in data:
        raise ValueError("manifest missing suite")
    tiers = data.get("tiers")
    if not isinstance(tiers, list) or not tiers:
        raise ValueError("manifest must contain non-empty tiers")
    for tier in tiers:
        for key in ("tier", "name", "runner", "purpose", "scenarios", "metrics"):
            if key not in tier:
                raise ValueError(f"tier missing {key}: {tier}")
        if not tier["scenarios"]:
            raise ValueError(f"tier has no scenarios: {tier['name']}")
        for scenario in tier["scenarios"]:
            if "name" not in scenario:
                raise ValueError(f"scenario missing name in tier {tier['name']}")

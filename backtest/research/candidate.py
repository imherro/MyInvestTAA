from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from engine.asset_registry.loader import ROOT


V12_SPEC_PATH = ROOT / "config" / "research_candidate_v12.json"
V12_REPORT_PATH = ROOT / "reports" / "v12_candidate_report.json"


@dataclass(frozen=True)
class ResearchCandidateSpec:
    strategy_id: str
    status: str
    model_family: str
    predecessor: str
    added_asset_id: str
    expected_universe_count: int
    guidance_role: str
    production_actionable: bool

    @classmethod
    def load(cls, path: Path = V12_SPEC_PATH) -> "ResearchCandidateSpec":
        value = json.loads(path.read_text(encoding="utf-8"))
        spec = cls(**value)
        if spec.production_actionable is not False:
            raise ValueError("research candidate cannot be production actionable")
        if spec.status != "shadow_candidate":
            raise ValueError("research candidate status must be shadow_candidate")
        return spec


def build_v12_candidate_report(spec, research, comparison, execution) -> dict:
    errors = []
    included = research.get("universe_scope", {}).get("included_asset_ids", [])
    if research.get("strategy") != spec.strategy_id:
        errors.append("research strategy identifier mismatch")
    if spec.added_asset_id not in included:
        errors.append("added asset is absent from candidate universe")
    if research.get("universe_count") != spec.expected_universe_count:
        errors.append("candidate universe count mismatch")
    if comparison.get("added_asset_id") != spec.added_asset_id:
        errors.append("universe comparison does not match candidate")
    return {
        "available": not errors,
        "strategy_id": spec.strategy_id,
        "status": spec.status,
        "model_family": spec.model_family,
        "predecessor": spec.predecessor,
        "guidance_role": spec.guidance_role,
        "production_actionable": False,
        "period": research.get("period"),
        "universe_count": research.get("universe_count"),
        "added_asset_id": spec.added_asset_id,
        "research_metrics": research.get("metrics"),
        "baseline_comparison": {
            "period": comparison.get("comparison_period"),
            "metric_deltas": comparison.get("metric_deltas"),
            "selection_impact": comparison.get("selection_impact"),
        },
        "execution_validation": {
            "period": execution.get("period"),
            "metrics": execution.get("metrics"),
            "gap": execution.get("execution_gap"),
            "mapping_summary": execution.get("mapping_summary"),
            "ready_for_execution_validation": execution.get("decision", {}).get(
                "ready_for_execution_validation"
            ),
        },
        "relationship_to_v11": (
            "V12 is an expanded-universe research and Shadow candidate. "
            "It does not replace V11_PRODUCTION_FUSION."
        ),
        "errors": errors,
    }


def write_v12_candidate_report(value: dict, path: Path = V12_REPORT_PATH) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    return path

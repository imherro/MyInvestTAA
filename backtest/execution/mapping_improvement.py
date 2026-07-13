from __future__ import annotations

import json
from pathlib import Path

from engine.asset_registry.loader import ROOT


EXECUTION_MAPPING_IMPROVEMENT_REPORT = ROOT / "reports" / "execution_mapping_improvement_report.json"


def build_mapping_improvement_report(execution_report: dict) -> dict:
    mapping_rows = {
        row["research_asset_id"]: row
        for row in [*execution_report.get("unmapped_assets", []), *execution_report.get("low_quality_proxy_assets", [])]
    }.values()
    mapping_rows = list(mapping_rows)
    weights: dict[str, float] = {}
    for allocation in execution_report.get("monthly_allocations", []):
        for asset_id, value in allocation.get("cash_breakdown", {}).items():
            if asset_id != "research_cash":
                weights[asset_id] = weights.get(asset_id, 0.0) + float(value)
    unmapped = [row for row in mapping_rows if row.get("mapping_quality") == "none"]
    low = [row for row in mapping_rows if row.get("mapping_quality") == "low"]
    ranked = sorted(
        unmapped,
        key=lambda row: sum(
            float(item.get("weights", {}).get(row["research_asset_id"], 0.0))
            for item in execution_report.get("source_research_allocations", [])
        ),
        reverse=True,
    )
    return {
        "unmapped_research_assets": [row["research_asset_id"] for row in unmapped],
        "low_quality_proxy_assets": [row["research_asset_id"] for row in low],
        "highest_weight_unmapped_assets": [row["research_asset_id"] for row in ranked],
        "recommended_actions": [
            {
                "research_asset_id": row["research_asset_id"],
                "issue": f"mapping_quality_{row['mapping_quality']}",
                "suggestion": "identify primary ETF proxy or keep as research-only asset",
            }
            for row in [*ranked, *low]
        ],
        "warning": "Suggestions only. asset_mapping.json is not modified automatically.",
    }


def write_mapping_improvement_report(report: dict, path: Path | None = None) -> Path:
    target = path or EXECUTION_MAPPING_IMPROVEMENT_REPORT
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return target


def load_mapping_improvement_report(path: Path | None = None) -> dict:
    target = path or EXECUTION_MAPPING_IMPROVEMENT_REPORT
    if not target.exists():
        return {"available": False, "message": "execution mapping improvement report not generated yet"}
    report = json.loads(target.read_text(encoding="utf-8"))
    report["available"] = True
    return report

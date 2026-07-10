from __future__ import annotations

from datetime import UTC, datetime
import json
from pathlib import Path

from engine.asset_registry.loader import ROOT, research_assets_by_id


RESEARCH_METADATA_SUGGESTIONS_REPORT = ROOT / "reports" / "research_universe_metadata_suggestions.json"


def build_metadata_suggestions(data_audit_report: dict) -> dict:
    asset_lookup = research_assets_by_id()
    suggestions = []
    blocked_assets = []

    for row in data_audit_report.get("rows", []):
        asset_id = str(row.get("asset_id", ""))
        asset = asset_lookup.get(asset_id)
        if row.get("available") and row.get("first_date") and row.get("last_date"):
            suggestions.append(
                {
                    "asset_id": asset_id,
                    "name": row.get("name") or (asset.name if asset else ""),
                    "data_start_date": row["first_date"],
                    "investable_start_date": row["first_date"],
                    "last_date": row["last_date"],
                    "source": _suggestion_source(data_audit_report),
                    "confidence": "high" if row.get("row_count", 0) > 0 else "low",
                    "current_data_start_date": asset.data_start_date if asset else None,
                    "current_investable_start_date": asset.investable_start_date if asset else None,
                }
            )
        else:
            blocked_assets.append(
                {
                    "asset_id": asset_id,
                    "name": row.get("name") or (asset.name if asset else ""),
                    "reason": row.get("error") or "data_unavailable",
                    "source": _suggestion_source(data_audit_report),
                }
            )

    return {
        "available": True,
        "source_report_provider": data_audit_report.get("provider"),
        "source_report_path": data_audit_report.get("report_path"),
        "generated_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "suggestion_count": len(suggestions),
        "blocked_asset_count": len(blocked_assets),
        "suggestions": suggestions,
        "blocked_assets": blocked_assets,
    }


def write_metadata_suggestions(report: dict, path: Path | None = None) -> Path:
    target = path or RESEARCH_METADATA_SUGGESTIONS_REPORT
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return target


def load_metadata_suggestions_report(path: Path | None = None) -> dict:
    target = path or RESEARCH_METADATA_SUGGESTIONS_REPORT
    if not target.exists():
        return {
            "available": False,
            "message": f"research universe metadata suggestions report not found: {target.name}",
        }
    with target.open("r", encoding="utf-8") as f:
        payload = json.load(f)
    payload["available"] = True
    payload["report_path"] = str(target)
    return payload


def _suggestion_source(data_audit_report: dict) -> str:
    provider = str(data_audit_report.get("provider") or "unknown")
    return f"{provider}_audit"

from __future__ import annotations

from datetime import UTC, datetime
import json
from pathlib import Path

from engine.asset_registry.loader import ROOT, research_assets_by_id


RESEARCH_RETURN_BASIS_REVIEW_REPORT = ROOT / "reports" / "research_universe_return_basis_review.json"
MANUAL_REVIEW_ASSET_IDS = {"399606.SZ"}


def build_return_basis_review(data_audit_report: dict) -> dict:
    asset_lookup = research_assets_by_id()
    confirmed_total_return = []
    needs_manual_review = []
    unavailable_total_return = []
    price_index_monitor_assets = []

    for row in data_audit_report.get("rows", []):
        asset_id = str(row.get("asset_id", ""))
        asset = asset_lookup.get(asset_id)
        return_basis = str(row.get("return_basis") or (asset.return_basis if asset else ""))
        available = bool(row.get("available"))

        if asset_id in MANUAL_REVIEW_ASSET_IDS:
            needs_manual_review.append(
                _review_row(
                    row,
                    asset,
                    reason="manual_return_basis_confirmation_required",
                )
            )
            continue

        if return_basis == "total_return" and available:
            confirmed_total_return.append(_review_row(row, asset, reason="available_total_return_source"))
        elif return_basis == "total_return":
            unavailable_total_return.append(_review_row(row, asset, reason=row.get("error") or "data_unavailable"))
        elif return_basis == "price_index":
            price_index_monitor_assets.append(
                _review_row(
                    row,
                    asset,
                    reason="price_index_monitor_only",
                )
            )
            if asset and asset.eligible_for_allocation:
                needs_manual_review.append(
                    _review_row(
                        row,
                        asset,
                        reason="price_index_marked_eligible_for_allocation",
                    )
                )
        else:
            needs_manual_review.append(_review_row(row, asset, reason="unknown_return_basis"))

    return {
        "available": True,
        "source_report_provider": data_audit_report.get("provider"),
        "source_report_path": data_audit_report.get("report_path"),
        "generated_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "confirmed_total_return": confirmed_total_return,
        "needs_manual_review": needs_manual_review,
        "unavailable_total_return": unavailable_total_return,
        "price_index_monitor_assets": price_index_monitor_assets,
    }


def write_return_basis_review(report: dict, path: Path | None = None) -> Path:
    target = path or RESEARCH_RETURN_BASIS_REVIEW_REPORT
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return target


def load_return_basis_review_report(path: Path | None = None) -> dict:
    target = path or RESEARCH_RETURN_BASIS_REVIEW_REPORT
    if not target.exists():
        return {
            "available": False,
            "message": f"research universe return basis review report not found: {target.name}",
        }
    with target.open("r", encoding="utf-8") as f:
        payload = json.load(f)
    payload["available"] = True
    payload["report_path"] = str(target)
    return payload


def _review_row(row: dict, asset, *, reason: str) -> dict:
    return {
        "asset_id": row.get("asset_id"),
        "name": row.get("name") or (asset.name if asset else ""),
        "data_api": row.get("data_api") or (asset.data_api if asset else ""),
        "return_basis": row.get("return_basis") or (asset.return_basis if asset else ""),
        "provider_return_types": row.get("provider_return_types") or [],
        "available": bool(row.get("available")),
        "row_count": int(row.get("row_count") or 0),
        "first_date": row.get("first_date"),
        "last_date": row.get("last_date"),
        "eligible_for_allocation": bool(asset.eligible_for_allocation) if asset else None,
        "reason": reason,
    }

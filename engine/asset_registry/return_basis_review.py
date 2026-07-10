from __future__ import annotations

from datetime import UTC, datetime
import json
from pathlib import Path

from engine.asset_registry.loader import ROOT, research_assets_by_id


RESEARCH_RETURN_BASIS_REVIEW_REPORT = ROOT / "reports" / "research_universe_return_basis_review.json"
MANUAL_REVIEW_ASSET_IDS = {"399606.SZ"}


def build_return_basis_review(data_audit_report: dict) -> dict:
    asset_lookup = research_assets_by_id()
    registered_total_return_available = []
    basis_confirmed_total_return = []
    provider_metadata_mismatch = []
    needs_manual_review = []
    unavailable_total_return = []
    price_index_monitor_assets = []

    for row in data_audit_report.get("rows", []):
        asset_id = str(row.get("asset_id", ""))
        asset = asset_lookup.get(asset_id)
        return_basis = str(row.get("return_basis") or (asset.return_basis if asset else ""))
        available = bool(row.get("available"))

        if return_basis == "total_return" and available:
            registered_row = _review_row(
                row,
                asset,
                reason="registered_total_return_index_available",
                basis_evidence="asset_registry_return_basis",
                basis_confidence=_basis_confidence(row),
            )
            registered_total_return_available.append(registered_row)
            if row.get("provider_return_types") == ["total_return"]:
                basis_confirmed_total_return.append(
                    _review_row(
                        row,
                        asset,
                        reason="provider_marks_total_return",
                        basis_evidence="provider_return_type",
                        basis_confidence="high",
                    )
                )
            else:
                provider_metadata_mismatch.append(
                    _review_row(
                        row,
                        asset,
                        reason="registry_declared_total_return_but_provider_marks_price",
                        basis_evidence="asset_registry_return_basis",
                        basis_confidence="medium",
                    )
                )

        if asset_id in MANUAL_REVIEW_ASSET_IDS:
            needs_manual_review.append(
                _review_row(
                    row,
                    asset,
                    reason="manual_return_basis_confirmation_required",
                    basis_evidence="manual_review_policy",
                    basis_confidence="low",
                )
            )
            continue

        if return_basis == "total_return" and not available:
            unavailable_total_return.append(
                _review_row(
                    row,
                    asset,
                    reason=row.get("error") or "data_unavailable",
                    basis_evidence="asset_registry_return_basis",
                    basis_confidence="low",
                )
            )
        elif return_basis == "price_index":
            price_index_monitor_assets.append(
                _review_row(
                    row,
                    asset,
                    reason="price_index_monitor_only",
                    basis_evidence="asset_registry_return_basis",
                    basis_confidence="high",
                )
            )
            if asset and asset.eligible_for_allocation:
                needs_manual_review.append(
                    _review_row(
                        row,
                        asset,
                        reason="price_index_marked_eligible_for_allocation",
                        basis_evidence="allocation_gate",
                        basis_confidence="high",
                    )
                )
        elif return_basis != "total_return":
            needs_manual_review.append(
                _review_row(
                    row,
                    asset,
                    reason="unknown_return_basis",
                    basis_evidence="unknown",
                    basis_confidence="low",
                )
            )

    return {
        "available": True,
        "source_report_provider": data_audit_report.get("provider"),
        "source_report_path": data_audit_report.get("report_path"),
        "generated_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "registered_total_return_available": registered_total_return_available,
        "basis_confirmed_total_return": basis_confirmed_total_return,
        "provider_metadata_mismatch": provider_metadata_mismatch,
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


def _review_row(
    row: dict,
    asset,
    *,
    reason: str,
    basis_evidence: str,
    basis_confidence: str,
) -> dict:
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
        "basis_evidence": basis_evidence,
        "basis_confidence": basis_confidence,
    }


def _basis_confidence(row: dict) -> str:
    if row.get("provider_return_types") == ["total_return"]:
        return "high"
    return "medium"

from __future__ import annotations

from engine.asset_registry.data_audit import load_research_data_availability_report
from engine.asset_registry.loader import load_asset_mappings, load_research_universe
from engine.asset_registry.return_basis_review import MANUAL_REVIEW_ASSET_IDS, load_return_basis_review_report


def build_research_universe_readiness() -> dict:
    assets = load_research_universe()
    audit = load_research_data_availability_report(tushare=True)
    review = load_return_basis_review_report()

    blocked_assets = _blocked_assets(assets, audit, review)
    warnings = _readiness_warnings(review)
    checks = {
        "has_real_tushare_audit": bool(audit.get("available") and audit.get("provider") == "tushare"),
        "metadata_dates_backfilled": all(asset.data_start_date and asset.investable_start_date for asset in assets),
        "no_price_index_in_allocation": all(
            not asset.eligible_for_allocation for asset in assets if asset.return_basis == "price_index"
        ),
        "manual_review_assets_excluded": all(
            not asset.eligible_for_allocation for asset in assets if asset.asset_id in MANUAL_REVIEW_ASSET_IDS
        ),
        "has_execution_mapping_report": bool(load_asset_mappings()),
    }

    return {
        "available": True,
        "ready_for_research_backtest": all(checks.values()) and not blocked_assets,
        "eligible_assets": sum(1 for asset in assets if asset.eligible_for_allocation),
        "blocked_assets": blocked_assets,
        "warnings": warnings,
        "checks": checks,
    }


def _blocked_assets(assets, audit: dict, review: dict) -> list[dict]:
    blocked: list[dict] = []
    asset_lookup = {asset.asset_id: asset for asset in assets}

    for asset_id in sorted(MANUAL_REVIEW_ASSET_IDS):
        asset = asset_lookup.get(asset_id)
        blocked.append(
            {
                "asset_id": asset_id,
                "name": asset.name if asset else "",
                "reason": "return_basis_manual_review",
            }
        )

    if audit.get("available"):
        for row in audit.get("rows", []):
            if not row.get("available"):
                blocked.append(
                    {
                        "asset_id": row.get("asset_id"),
                        "name": row.get("name", ""),
                        "reason": row.get("error") or "data_unavailable",
                    }
                )

    if review.get("available"):
        for row in review.get("unavailable_total_return", []):
            blocked.append(
                {
                    "asset_id": row.get("asset_id"),
                    "name": row.get("name", ""),
                    "reason": row.get("reason") or "unavailable_total_return",
                }
            )

    seen = set()
    unique = []
    for row in blocked:
        key = (row.get("asset_id"), row.get("reason"))
        if key in seen:
            continue
        seen.add(key)
        unique.append(row)
    return unique


def _readiness_warnings(review: dict) -> list[str]:
    warnings: list[str] = []
    if review.get("provider_metadata_mismatch"):
        warnings.append(
            "provider metadata marks registered total-return indices as price; registry return_basis remains the source of truth"
        )
    if review.get("needs_manual_review"):
        warnings.append("manual return-basis review assets are excluded from allocation")
    return warnings

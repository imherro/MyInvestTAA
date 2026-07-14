from __future__ import annotations

from engine.asset_registry import build_research_universe_readiness, load_research_universe
from engine.asset_registry.models import ResearchAsset


ALLOWED_RESEARCH_RETURN_BASIS = {"total_return", "net_return"}


def load_research_backtest_universe(readiness_report: dict | None = None) -> list[ResearchAsset]:
    readiness = readiness_report or build_research_universe_readiness()
    blocked_ids = {str(row.get("asset_id")) for row in readiness.get("blocked_assets", [])}
    return [
        asset
        for asset in load_research_universe()
        if _asset_is_research_backtest_eligible(asset, blocked_ids)
    ]


def validate_research_backtest_inputs(
    assets: list[ResearchAsset],
    price_data: dict[str, list],
    readiness_report: dict | None = None,
    *,
    min_assets: int = 5,
) -> dict:
    readiness = readiness_report or build_research_universe_readiness()
    blocked_ids = {str(row.get("asset_id")) for row in readiness.get("blocked_assets", [])}
    valid_assets = []
    excluded_assets = []
    unavailable_assets = []

    for asset in assets:
        reason = _exclusion_reason(asset, blocked_ids)
        if reason:
            excluded_assets.append(_asset_row(asset, reason))
            continue
        rows = price_data.get(asset.asset_id, [])
        if not rows:
            unavailable_assets.append(_asset_row(asset, "missing_price_data"))
            continue
        valid_assets.append(asset)

    errors = []
    if len(valid_assets) < min_assets:
        errors.append(f"research backtest requires at least {min_assets} available assets")

    return {
        "valid": not errors,
        "valid_assets": valid_assets,
        "excluded_assets": excluded_assets,
        "unavailable_assets": unavailable_assets,
        "errors": errors,
        "warnings": [
            "Research backtest uses index-level registry return_basis, not ETF execution prices",
        ],
    }


def _asset_is_research_backtest_eligible(asset: ResearchAsset, blocked_ids: set[str]) -> bool:
    return _exclusion_reason(asset, blocked_ids) is None


def _exclusion_reason(asset: ResearchAsset, blocked_ids: set[str]) -> str | None:
    if asset.asset_id in blocked_ids:
        return "readiness_blocked"
    if not asset.eligible_for_allocation:
        return "not_eligible_for_allocation"
    if asset.return_basis not in ALLOWED_RESEARCH_RETURN_BASIS:
        return "unsupported_return_basis"
    if asset.category == "industry" or asset.sleeve == "industry_monitor":
        return "industry_monitor_excluded"
    if not asset.data_start_date or not asset.investable_start_date:
        return "missing_metadata_dates"
    return None


def _asset_row(asset: ResearchAsset, reason: str) -> dict:
    return {
        "asset_id": asset.asset_id,
        "name": asset.name,
        "category": asset.category,
        "sleeve": asset.sleeve,
        "return_basis": asset.return_basis,
        "eligible_for_allocation": asset.eligible_for_allocation,
        "reason": reason,
    }

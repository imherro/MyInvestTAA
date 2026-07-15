from __future__ import annotations

from collections import Counter

from engine.asset_registry.models import AssetMapping, ExecutionAsset, ResearchAsset


ALLOWED_RESEARCH_ROLES = {"research", "monitor"}
ALLOWED_EXECUTION_ROLES = {"execution"}
ALLOWED_DATA_APIS = {"index_daily", "sw_daily", "fund_daily", "fund_adj", "daily", "custom"}
ALLOWED_MAPPING_QUALITIES = {"high", "medium", "low", "none"}
ALLOWED_EXECUTION_APPROVALS = {"quality_policy", "human_approved", "research_only"}
ALLOWED_RETURN_BASIS = {"total_return", "net_return", "price_index", "qfq", "hfq", "price"}


def validate_research_assets(
    assets: list[ResearchAsset],
    *,
    allow_price_index_allocation: bool = False,
) -> list[str]:
    errors: list[str] = []
    _append_duplicate_errors(errors, "research asset", [asset.asset_id for asset in assets])

    for asset in assets:
        if asset.role not in ALLOWED_RESEARCH_ROLES:
            errors.append(f"{asset.asset_id} has invalid role: {asset.role}")
        if asset.data_api not in ALLOWED_DATA_APIS:
            errors.append(f"{asset.asset_id} has invalid data_api: {asset.data_api}")
        if asset.return_basis not in ALLOWED_RETURN_BASIS:
            errors.append(f"{asset.asset_id} has invalid return_basis: {asset.return_basis}")
        if not isinstance(asset.eligible_for_allocation, bool):
            errors.append(f"{asset.asset_id} eligible_for_allocation must be bool")
        if _is_industry_monitor(asset) and asset.eligible_for_allocation is not False:
            errors.append(f"{asset.asset_id} industry monitor must be excluded from allocation")
        if (
            asset.return_basis == "price_index"
            and asset.eligible_for_allocation
            and not allow_price_index_allocation
        ):
            errors.append(f"{asset.asset_id} price_index cannot be eligible for allocation")
    return errors


def validate_execution_assets(assets: list[ExecutionAsset]) -> list[str]:
    errors: list[str] = []
    _append_duplicate_errors(errors, "execution asset", [asset.asset_id for asset in assets])

    for asset in assets:
        if asset.role not in ALLOWED_EXECUTION_ROLES:
            errors.append(f"{asset.asset_id} has invalid role: {asset.role}")
        if asset.data_api not in ALLOWED_DATA_APIS:
            errors.append(f"{asset.asset_id} has invalid data_api: {asset.data_api}")
        if asset.return_basis not in ALLOWED_RETURN_BASIS:
            errors.append(f"{asset.asset_id} has invalid return_basis: {asset.return_basis}")
    return errors


def validate_mappings(
    mappings: list[AssetMapping],
    research_assets: list[ResearchAsset],
    execution_assets: list[ExecutionAsset],
) -> list[str]:
    errors: list[str] = []
    _append_duplicate_errors(errors, "asset mapping", [mapping.research_asset_id for mapping in mappings])

    research_ids = {asset.asset_id for asset in research_assets}
    execution_ids = {asset.asset_id for asset in execution_assets}
    for mapping in mappings:
        if mapping.research_asset_id not in research_ids:
            errors.append(f"{mapping.research_asset_id} mapping references unknown research asset")
        if mapping.mapping_quality not in ALLOWED_MAPPING_QUALITIES:
            errors.append(f"{mapping.research_asset_id} has invalid mapping_quality: {mapping.mapping_quality}")
        if mapping.execution_approval not in ALLOWED_EXECUTION_APPROVALS:
            errors.append(
                f"{mapping.research_asset_id} has invalid execution_approval: "
                f"{mapping.execution_approval}"
            )
        if mapping.execution_approval == "human_approved" and not mapping.primary_execution_proxy:
            errors.append(
                f"{mapping.research_asset_id} human-approved mapping must have a primary proxy"
            )
        if mapping.mapping_quality == "none":
            if mapping.primary_execution_proxy is not None:
                errors.append(f"{mapping.research_asset_id} mapping_quality=none must not have primary proxy")
            if mapping.execution_proxies:
                errors.append(f"{mapping.research_asset_id} mapping_quality=none must not have proxies")
        if mapping.primary_execution_proxy is not None and mapping.primary_execution_proxy not in mapping.execution_proxies:
            errors.append(f"{mapping.research_asset_id} primary proxy must be listed in execution_proxies")
        for proxy in mapping.execution_proxies:
            if proxy not in execution_ids:
                errors.append(f"{mapping.research_asset_id} mapping references unknown execution proxy: {proxy}")
    return errors


def validate_registry(
    research_assets: list[ResearchAsset],
    execution_assets: list[ExecutionAsset],
    mappings: list[AssetMapping],
) -> list[str]:
    return [
        *validate_research_assets(research_assets),
        *validate_execution_assets(execution_assets),
        *validate_mappings(mappings, research_assets, execution_assets),
    ]


def _is_industry_monitor(asset: ResearchAsset) -> bool:
    return asset.category == "industry" or asset.sleeve == "industry_monitor"


def _append_duplicate_errors(errors: list[str], label: str, values: list[str]) -> None:
    counts = Counter(values)
    for value, count in sorted(counts.items()):
        if count > 1:
            errors.append(f"duplicate {label}: {value}")

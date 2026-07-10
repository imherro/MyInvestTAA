from __future__ import annotations

from collections import Counter

from engine.asset_registry.loader import (
    load_asset_mappings,
    load_execution_universe,
    load_research_universe,
)
from engine.asset_registry.models import AssetMapping, ResearchAsset
from engine.asset_registry.validator import validate_registry


def build_research_universe_audit() -> dict:
    research_assets = load_research_universe(validate=False)
    execution_assets = load_execution_universe(validate=False)
    mappings = load_asset_mappings(validate=False)
    errors = validate_registry(research_assets, execution_assets, mappings)
    warnings = _build_warnings(research_assets, mappings)

    return {
        "research_asset_count": len(research_assets),
        "execution_asset_count": len(execution_assets),
        "mapping_count": len(mappings),
        "eligible_for_allocation_count": sum(1 for asset in research_assets if asset.eligible_for_allocation),
        "industry_monitor_count": sum(1 for asset in research_assets if _is_industry_monitor(asset)),
        "return_basis_counts": _counter_dict(asset.return_basis for asset in research_assets),
        "data_api_counts": _counter_dict(
            [asset.data_api for asset in research_assets]
            + [asset.data_api for asset in execution_assets]
        ),
        "mapping_quality_counts": _counter_dict(mapping.mapping_quality for mapping in mappings),
        "warnings": warnings,
        "errors": errors,
    }


def _build_warnings(research_assets: list[ResearchAsset], mappings: list[AssetMapping]) -> list[str]:
    warnings: list[str] = []
    mapped_ids = {mapping.research_asset_id for mapping in mappings}
    for asset in research_assets:
        if asset.return_basis == "price_index":
            warnings.append(
                f"{asset.asset_id} {asset.name} uses price_index and is excluded from allocation"
            )
        if asset.asset_id not in mapped_ids:
            warnings.append(f"{asset.asset_id} {asset.name} has no execution mapping")
    for mapping in mappings:
        if mapping.mapping_quality == "none":
            warnings.append(f"{mapping.research_asset_id} has no execution proxy")
        if mapping.mapping_quality == "low":
            warnings.append(f"{mapping.research_asset_id} has low-quality execution mapping")
    return warnings


def _is_industry_monitor(asset: ResearchAsset) -> bool:
    return asset.category == "industry" or asset.sleeve == "industry_monitor"


def _counter_dict(values) -> dict[str, int]:
    return dict(sorted(Counter(values).items()))

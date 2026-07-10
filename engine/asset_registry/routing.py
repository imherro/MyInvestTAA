from __future__ import annotations

from data.models import PriceBar
from engine.asset_registry.models import ExecutionAsset, ResearchAsset


AssetConfig = ResearchAsset | ExecutionAsset


def get_asset_history(
    provider,
    asset: AssetConfig,
    start: str | None = None,
    end: str | None = None,
) -> list[PriceBar]:
    if asset.data_api == "index_daily":
        return provider.get_index_history(asset.asset_id, start=start, end=end)
    if asset.data_api == "sw_daily":
        return provider.get_sw_index_history(asset.asset_id, start=start, end=end)
    if asset.data_api == "fund_daily":
        return provider.get_price_history(asset.asset_id, start=start, end=end)
    if asset.data_api == "daily":
        return provider.get_stock_price_history(asset.asset_id, start=start, end=end)
    raise ValueError(f"unsupported data_api for asset history routing: {asset.data_api}")

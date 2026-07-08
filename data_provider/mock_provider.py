from __future__ import annotations

from data.models import AssetMetadata, PriceBar
from engine.asset_repository import load_assets, load_price_histories


class MockProvider:
    name = "mock"

    def __init__(
        self,
        assets: list[dict] | None = None,
        histories: dict[str, list[dict]] | None = None,
        return_type: str = "price",
    ) -> None:
        self._assets = assets
        self._histories = histories
        self.return_type = return_type

    def get_price_history(
        self,
        asset_id: str,
        start: str | None = None,
        end: str | None = None,
    ) -> list[PriceBar]:
        histories = self._histories if self._histories is not None else load_price_histories()
        if asset_id not in histories:
            raise ValueError(f"history not found for asset_id: {asset_id}")
        return [
            PriceBar.from_mapping(
                asset_id,
                {
                    **row,
                    "adjust_type": row.get("adjust_type") or _adjust_type_from_return_type(self.return_type),
                    "return_type": row.get("return_type") or self.return_type,
                },
                source=self.name,
            )
            for row in histories[asset_id]
            if _in_range(str(row["date"]), start, end)
        ]

    def get_index_history(
        self,
        index_id: str,
        start: str | None = None,
        end: str | None = None,
    ) -> list[PriceBar]:
        return self.get_price_history(index_id, start=start, end=end)

    def get_etf_list(self) -> list[AssetMetadata]:
        assets = self._assets if self._assets is not None else load_assets()
        return [AssetMetadata.from_mapping(asset, source=self.name) for asset in assets]

    def provider_status(self) -> dict:
        return {
            "name": self.name,
            "available": True,
            "mode": "sample_json",
        }


def _in_range(value: str, start: str | None, end: str | None) -> bool:
    if start is not None and value < start:
        return False
    if end is not None and value > end:
        return False
    return True


def _adjust_type_from_return_type(return_type: str) -> str:
    return "none" if return_type == "price" else return_type

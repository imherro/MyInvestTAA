from __future__ import annotations

from typing import Protocol

from data.models import AssetMetadata, PriceBar


class MarketDataProvider(Protocol):
    name: str

    def get_price_history(
        self,
        asset_id: str,
        start: str | None = None,
        end: str | None = None,
    ) -> list[PriceBar]:
        ...

    def get_index_history(
        self,
        index_id: str,
        start: str | None = None,
        end: str | None = None,
    ) -> list[PriceBar]:
        ...

    def get_sw_index_history(
        self,
        sw_index_id: str,
        start: str | None = None,
        end: str | None = None,
    ) -> list[PriceBar]:
        ...

    def get_stock_price_history(
        self,
        stock_id: str,
        start: str | None = None,
        end: str | None = None,
    ) -> list[PriceBar]:
        ...

    def get_etf_list(self) -> list[AssetMetadata]:
        ...

    def provider_status(self) -> dict:
        ...

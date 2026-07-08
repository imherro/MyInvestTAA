from __future__ import annotations

import os

from data.models import AssetMetadata, PriceBar


class TushareProvider:
    name = "tushare"

    def __init__(self, token: str | None = None) -> None:
        self.token = token or os.getenv("TUSHARE_TOKEN")

    def get_price_history(
        self,
        asset_id: str,
        start: str | None = None,
        end: str | None = None,
    ) -> list[PriceBar]:
        pro = self._client()
        frame = pro.fund_daily(
            ts_code=_to_ts_code(asset_id),
            start_date=_to_tushare_date(start),
            end_date=_to_tushare_date(end),
        )
        return _price_bars_from_frame(asset_id, frame)

    def get_index_history(
        self,
        index_id: str,
        start: str | None = None,
        end: str | None = None,
    ) -> list[PriceBar]:
        pro = self._client()
        frame = pro.index_daily(
            ts_code=_to_ts_code(index_id),
            start_date=_to_tushare_date(start),
            end_date=_to_tushare_date(end),
        )
        return _price_bars_from_frame(index_id, frame)

    def get_etf_list(self) -> list[AssetMetadata]:
        pro = self._client()
        frame = pro.fund_basic(market="E")
        rows = frame.to_dict("records") if hasattr(frame, "to_dict") else []
        return [
            AssetMetadata(
                asset_id=str(row.get("ts_code")),
                name=str(row.get("name") or row.get("fund_name") or row.get("ts_code")),
                asset_class="etf",
                market="CN",
                source=self.name,
            )
            for row in rows
        ]

    def provider_status(self) -> dict:
        return {
            "name": self.name,
            "available": bool(self.token),
            "mode": "live_adapter",
            "requires": ["tushare", "TUSHARE_TOKEN"],
        }

    def _client(self):
        if not self.token:
            raise RuntimeError("TUSHARE_TOKEN is required for TushareProvider")
        try:
            import tushare as ts
        except ImportError as exc:
            raise RuntimeError("tushare package is not installed") from exc
        ts.set_token(self.token)
        return ts.pro_api()


def _price_bars_from_frame(asset_id: str, frame) -> list[PriceBar]:
    rows = frame.to_dict("records") if hasattr(frame, "to_dict") else []
    bars = [
        PriceBar(
            asset_id=asset_id,
            date=_from_tushare_date(str(row["trade_date"])),
            close=float(row["close"]),
            open=_optional_float(row.get("open")),
            high=_optional_float(row.get("high")),
            low=_optional_float(row.get("low")),
            volume=_optional_float(row.get("vol")),
            source="tushare",
        )
        for row in rows
        if row.get("trade_date") and row.get("close") is not None
    ]
    return sorted(bars, key=lambda item: item.date)


def _to_ts_code(asset_id: str) -> str:
    if "." in asset_id:
        return asset_id
    suffix = "SH" if asset_id.startswith(("5", "6", "9")) else "SZ"
    return f"{asset_id}.{suffix}"


def _to_tushare_date(value: str | None) -> str | None:
    return None if value is None else value.replace("-", "")


def _from_tushare_date(value: str) -> str:
    return f"{value[0:4]}-{value[4:6]}-{value[6:8]}"


def _optional_float(value: object) -> float | None:
    if value is None or value == "":
        return None
    return float(value)

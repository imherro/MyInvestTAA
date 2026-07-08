from __future__ import annotations

import os

from data.models import AssetMetadata, PriceBar


class TushareProvider:
    name = "tushare"

    def __init__(self, token: str | None = None, return_type: str = "price") -> None:
        self.token = token or os.getenv("TUSHARE_TOKEN")
        self.return_type = return_type

    def get_price_history(
        self,
        asset_id: str,
        start: str | None = None,
        end: str | None = None,
    ) -> list[PriceBar]:
        pro = self._client()
        ts_code = _to_ts_code(asset_id)
        frame = pro.fund_daily(
            ts_code=ts_code,
            start_date=_to_tushare_date(start),
            end_date=_to_tushare_date(end),
        )
        adjustment_frame = None
        if self.return_type != "price":
            adjustment_frame = pro.fund_adj(
                ts_code=ts_code,
                start_date=_to_tushare_date(start),
                end_date=_to_tushare_date(end),
            )
        return _price_bars_from_frame(asset_id, frame, self.return_type, adjustment_frame)

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
        return _price_bars_from_frame(index_id, frame, self.return_type)

    def get_stock_price_history(
        self,
        stock_id: str,
        start: str | None = None,
        end: str | None = None,
    ) -> list[PriceBar]:
        pro = self._client()
        frame = pro.daily(
            ts_code=_to_ts_code(stock_id),
            start_date=_to_tushare_date(start),
            end_date=_to_tushare_date(end),
        )
        return _price_bars_from_frame(stock_id, frame, "price")

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
            "return_type": self.return_type,
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


def _price_bars_from_frame(asset_id: str, frame, return_type: str = "price", adjustment_frame=None) -> list[PriceBar]:
    rows = frame.to_dict("records") if hasattr(frame, "to_dict") else []
    factors = _adjustment_factors(adjustment_frame)
    bars = [
        PriceBar(
            asset_id=asset_id,
            date=_from_tushare_date(str(row["trade_date"])),
            close=_adjusted_value(str(row["trade_date"]), row.get("close"), return_type, factors),
            open=_adjusted_value(str(row["trade_date"]), row.get("open"), return_type, factors),
            high=_adjusted_value(str(row["trade_date"]), row.get("high"), return_type, factors),
            low=_adjusted_value(str(row["trade_date"]), row.get("low"), return_type, factors),
            volume=_optional_float(row.get("vol")),
            source="tushare",
            adjust_type=_adjust_type_from_return_type(return_type),
            return_type=return_type,
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


def _adjust_type_from_return_type(return_type: str) -> str:
    return "none" if return_type == "price" else return_type


def _adjustment_factors(frame) -> dict[str, float]:
    rows = frame.to_dict("records") if hasattr(frame, "to_dict") else []
    return {
        str(row["trade_date"]): float(row["adj_factor"])
        for row in rows
        if row.get("trade_date") and row.get("adj_factor") is not None
    }


def _adjusted_value(trade_date: str, value: object, return_type: str, factors: dict[str, float]) -> float | None:
    raw = _optional_float(value)
    if raw is None or return_type == "price":
        return raw
    factor = _factor_for_date(trade_date, factors)
    if return_type == "qfq":
        latest_factor = _latest_factor(factors)
        return round(raw * factor / latest_factor, 6)
    return round(raw * factor, 6)


def _factor_for_date(trade_date: str, factors: dict[str, float]) -> float:
    if not factors:
        raise RuntimeError("Tushare fund_adj returned no adjustment factors")
    if trade_date in factors:
        return factors[trade_date]
    earlier_dates = [date for date in factors if date <= trade_date]
    if earlier_dates:
        return factors[max(earlier_dates)]
    return factors[min(factors)]


def _latest_factor(factors: dict[str, float]) -> float:
    if not factors:
        raise RuntimeError("Tushare fund_adj returned no adjustment factors")
    return factors[max(factors)]


def _optional_float(value: object) -> float | None:
    if value is None or value == "":
        return None
    return float(value)

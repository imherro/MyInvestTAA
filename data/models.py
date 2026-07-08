from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class PriceBar:
    asset_id: str
    date: str
    close: float
    open: float | None = None
    high: float | None = None
    low: float | None = None
    volume: float | None = None
    source: str = "mock"
    adjust_type: str = "none"

    @classmethod
    def from_mapping(cls, asset_id: str, row: dict, source: str = "mock") -> "PriceBar":
        return cls(
            asset_id=asset_id,
            date=str(row["date"]),
            close=float(row["close"]),
            open=_optional_float(row.get("open")),
            high=_optional_float(row.get("high")),
            low=_optional_float(row.get("low")),
            volume=_optional_float(row.get("volume")),
            source=source,
            adjust_type=str(row.get("adjust_type") or row.get("adjust") or "none"),
        )

    def as_dict(self) -> dict:
        payload = {
            "asset_id": self.asset_id,
            "date": self.date,
            "close": self.close,
            "source": self.source,
            "adjust_type": self.adjust_type,
        }
        for field in ("open", "high", "low", "volume"):
            value = getattr(self, field)
            if value is not None:
                payload[field] = value
        return payload

    def as_price_row(self) -> dict:
        return {"date": self.date, "close": self.close}


@dataclass(frozen=True)
class AssetMetadata:
    asset_id: str
    name: str
    asset_class: str
    market: str = "CN"
    source: str = "mock"

    @classmethod
    def from_mapping(cls, row: dict, source: str = "mock") -> "AssetMetadata":
        return cls(
            asset_id=str(row.get("id") or row.get("asset_id") or row.get("ts_code")),
            name=str(row.get("name") or row.get("fund_name") or row.get("asset_id")),
            asset_class=str(row.get("asset_class") or row.get("type") or "unknown"),
            market=str(row.get("market") or "CN"),
            source=source,
        )

    def as_dict(self) -> dict:
        return {
            "asset_id": self.asset_id,
            "name": self.name,
            "asset_class": self.asset_class,
            "market": self.market,
            "source": self.source,
        }


def _optional_float(value: object) -> float | None:
    if value is None or value == "":
        return None
    return float(value)

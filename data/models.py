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
    return_type: str = "price"

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
            return_type=str(row.get("return_type") or "price"),
        )

    def as_dict(self) -> dict:
        payload = {
            "asset_id": self.asset_id,
            "date": self.date,
            "close": self.close,
            "source": self.source,
            "adjust_type": self.adjust_type,
            "return_type": self.return_type,
        }
        for field in ("open", "high", "low", "volume"):
            value = getattr(self, field)
            if value is not None:
                payload[field] = value
        return payload

    def as_price_row(self) -> dict:
        return {"date": self.date, "close": self.close}

def _optional_float(value: object) -> float | None:
    if value is None or value == "":
        return None
    return float(value)

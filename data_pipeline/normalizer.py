from __future__ import annotations

from data.models import PriceBar
from storage.models import StoredPrice


def price_bars_to_history(bars: list[PriceBar]) -> list[dict]:
    return [
        {"date": bar.date, "close": bar.close, "adjust_type": bar.adjust_type}
        for bar in sorted(bars, key=lambda item: item.date)
    ]


def stored_prices_to_history(prices: list[StoredPrice]) -> list[dict]:
    return [
        {"date": price.date, "close": price.close, "adjust_type": price.adjust_type}
        for price in sorted(prices, key=lambda item: item.date)
    ]

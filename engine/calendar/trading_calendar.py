from __future__ import annotations

from datetime import date, timedelta


CN_MARKET_HOLIDAYS = {
    "2024-01-01",
    "2024-02-09",
    "2024-02-12",
    "2024-02-13",
    "2024-02-14",
    "2024-02-15",
    "2024-02-16",
    "2024-04-04",
    "2024-04-05",
    "2024-05-01",
    "2024-05-02",
    "2024-05-03",
    "2024-06-10",
    "2024-09-16",
    "2024-09-17",
    "2024-10-01",
    "2024-10-02",
    "2024-10-03",
    "2024-10-04",
    "2024-10-07",
}


def is_trading_day(value: str | date) -> bool:
    day = _to_date(value)
    if day.weekday() >= 5:
        return False
    return day.isoformat() not in CN_MARKET_HOLIDAYS


def previous_trading_day(value: str | date) -> str:
    day = _to_date(value) - timedelta(days=1)
    while not is_trading_day(day):
        day -= timedelta(days=1)
    return day.isoformat()


def _to_date(value: str | date) -> date:
    if isinstance(value, date):
        return value
    return date.fromisoformat(value)

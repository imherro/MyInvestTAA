from __future__ import annotations

import json
from pathlib import Path

from engine.asset_registry.loader import ROOT


CALENDAR_PATH = ROOT / "data" / "market" / "cn_equity_trade_calendar.json"


def load_trade_calendar(path: Path | None = None) -> dict:
    target = path or CALENDAR_PATH
    value = json.loads(target.read_text(encoding="utf-8"))
    dates = [_iso_date(item) for item in value.get("dates", [])]
    if value.get("verified") is not True or not dates or dates != sorted(set(dates)):
        raise ValueError("verified, sorted, unique local trade calendar is required")
    return {**value, "dates": dates}


def next_trade_date(dates: list[str], signal_date: str) -> str | None:
    return next((value for value in dates if value > signal_date), None)


def _iso_date(value: object) -> str:
    text = str(value)
    if len(text) == 8 and text.isdigit():
        return f"{text[:4]}-{text[4:6]}-{text[6:]}"
    return text

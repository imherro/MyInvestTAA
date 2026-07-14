from __future__ import annotations

import json
from datetime import date
from pathlib import Path

from engine.asset_registry.loader import ROOT


CALENDAR_PATH = ROOT / "data" / "market" / "cn_equity_trade_calendar.json"


def load_trade_calendar(path: Path | None = None) -> dict:
    target = path or CALENDAR_PATH
    value = json.loads(target.read_text(encoding="utf-8"))
    required = {"schema_version", "exchange", "source", "source_query", "verified", "dates"}
    if not required.issubset(value):
        raise ValueError("trade calendar required fields are missing")
    dates = [_iso_date(item) for item in value.get("dates", [])]
    if (
        value.get("schema_version") != "1.0"
        or value.get("exchange") != "SSE"
        or not value.get("source")
        or value.get("verified") is not True
        or not dates
        or dates != sorted(set(dates))
    ):
        raise ValueError("verified, sorted, unique local trade calendar is required")
    try:
        parsed = [date.fromisoformat(item) for item in dates]
        coverage_start = date.fromisoformat(_iso_date(value["source_query"]["start_date"]))
        coverage_end = date.fromisoformat(_iso_date(value["source_query"]["end_date"]))
    except (KeyError, TypeError, ValueError) as exc:
        raise ValueError("trade calendar dates and coverage must be valid ISO dates") from exc
    if parsed[0] < coverage_start or parsed[-1] > coverage_end:
        raise ValueError("trade calendar dates exceed declared coverage")
    return {**value, "dates": dates}


def next_trade_date(dates: list[str], signal_date: str) -> str | None:
    return next((value for value in dates if value > signal_date), None)


def _iso_date(value: object) -> str:
    text = str(value)
    if len(text) == 8 and text.isdigit():
        return f"{text[:4]}-{text[4:6]}-{text[6:]}"
    return text
